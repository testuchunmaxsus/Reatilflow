"""
Tickets servis qatlami — murojaat biznes mantiq.

Funksiyalar:
  create_ticket(db, data, actor_id, user, redis) → Ticket
  add_message(db, ticket_id, data, actor_id, user) → TicketMessage
  update_status(db, ticket_id, data, actor_id, user) → Ticket
  get_ticket(db, ticket_id, user, with_messages) → Ticket
  list_tickets(db, user, filters...) → (list[Ticket], total)

Qoidalar:
  - Holat mashinasi: new→in_progress→resolved→closed; resolved→in_progress (qayta ochish).
  - Faqat admin/buxgalter holat o'zgartira oladi (tickets:edit ruxsati).
  - Scope/IDOR: do'kon → o'z murojaatlari; agent → o'z do'konlari yoki o'zi yaratgan;
                admin/buxgalter → barchasi.
  - client_uuid Redis idempotentlik.
  - Har mutatsiyada audit_log + outbox_event yoziladi.
  - version optimistik lock.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models.audit import AuditLog
from app.models.outbox import OutboxEvent
from app.models.store import AgentStore, Store
from app.models.ticket import Ticket, TicketMessage, is_valid_transition
from app.models.user import AppUser
from app.modules.tickets.schemas import (
    TicketCreate,
    TicketMessageCreate,
    TicketStatusUpdate,
)

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:tickets:create"

_RESOLVE_ROLES = frozenset({"administrator", "accountant"})
_BRANCH_ADMIN_ROLES = frozenset({"administrator", "accountant"})


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="ticket",
        entity_id=entity_id,
        before_json=json.dumps(before, default=str) if before else None,
        after_json=json.dumps(after, default=str) if after else None,
    )
    db.add(log)


async def _write_outbox(
    db: AsyncSession,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """outbox_event ga yozuv qo'shadi."""
    event = OutboxEvent(
        aggregate_type="ticket",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


async def _get_allowed_store_ids(
    db: AsyncSession,
    user: AppUser,
) -> list[uuid.UUID] | None:
    """
    Foydalanuvchiga ruxsat etilgan do'kon ID larini qaytaradi.

    None → barcha do'konlarga ruxsat (admin/buxgalter).
    Bo'sh ro'yxat → hech narsa ko'rinmaydi.
    """
    if user.role in _BRANCH_ADMIN_ROLES:
        return None  # filtr yo'q — barchasi

    if user.role == "agent":
        # Agent: o'zi agent_id bo'lgan yoki AgentStore orqali biriktirilgan do'konlar
        agent_store_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        stmt = select(Store.id).where(
            or_(
                Store.agent_id == user.id,
                Store.id.in_(agent_store_subq),
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    if user.role == "store":
        # Store: faqat o'z do'koni
        stmt = select(Store.id).where(Store.user_id == user.id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # courier va boshqalar: faqat o'zi yaratgan murojaatlar (store_id bo'yicha filtr yo'q)
    return None


# ─── Get (scope/IDOR) ─────────────────────────────────────────────────────────


async def get_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user: AppUser | None = None,
    with_messages: bool = False,
) -> Ticket:
    """
    ID bo'yicha murojaat oladi.

    Scope/IDOR:
      - do'kon → faqat o'z do'koni murojaatlari
      - agent → faqat o'z do'konlari yoki o'zi yaratgan
      - admin/buxgalter → barchasi
      - Scope tashqarisi → 404 (mavjudlikni oshkor qilmaslik)

    Raises:
        AppError("tickets.not_found"): topilmasa yoki scope tashqarisi.
    """
    if with_messages:
        stmt = (
            select(Ticket)
            .options(selectinload(Ticket.messages))
            .where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None))
        )
    else:
        stmt = select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.deleted_at.is_(None),
        )

    if user is not None:
        stmt = await _apply_ticket_scope(db, stmt, user)

    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise AppError("tickets.not_found", status_code=404)
    return ticket


async def _apply_ticket_scope(
    db: AsyncSession,
    stmt,
    user: AppUser,
):
    """
    Murojaat so'roviga rol asosida WHERE sharti qo'shadi.

    admin/buxgalter → filtr yo'q (barchasi).
    agent → o'z do'konlari murojaatlari YOKI o'zi yaratgan.
    store → faqat o'z do'koni murojaatlari.
    courier/boshqalar → faqat o'zi yaratgan.
    """
    role = user.role

    if role in _BRANCH_ADMIN_ROLES:
        # Branch filtr (agar branch_id berilgan bo'lsa)
        if user.branch_id is not None:
            stmt = stmt.join(
                Store, Ticket.store_id == Store.id, isouter=True
            ).where(
                or_(
                    Ticket.store_id.is_(None),
                    Store.branch_id == user.branch_id,
                )
            )
        return stmt

    if role == "agent":
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if allowed_store_ids is not None:
            stmt = stmt.where(
                or_(
                    Ticket.author_id == user.id,
                    Ticket.store_id.in_(allowed_store_ids) if allowed_store_ids else False,
                )
            )
        return stmt

    if role == "store":
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if not allowed_store_ids:
            stmt = stmt.where(Ticket.id.is_(None))  # hech narsa
        else:
            stmt = stmt.where(Ticket.store_id.in_(allowed_store_ids))
        return stmt

    # courier va boshqalar — faqat o'zi yaratgan
    stmt = stmt.where(Ticket.author_id == user.id)
    return stmt


# ─── List ─────────────────────────────────────────────────────────────────────


async def list_tickets(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    limit: int = 20,
    offset: int = 0,
    status_filter: str | None = None,
    type_filter: str | None = None,
    store_id: uuid.UUID | None = None,
) -> tuple[list[Ticket], int]:
    """
    Paginated murojaat ro'yxati.

    Filtrlar:
      - status_filter: new | in_progress | resolved | closed
      - type_filter: taklif | etiroz
      - store_id: do'kon bo'yicha

    Scope: admin/buxgalter barchasi; agent/store → o'z doirasi.
    """
    base_where = [Ticket.deleted_at.is_(None)]

    if status_filter:
        base_where.append(Ticket.status == status_filter)
    if type_filter:
        base_where.append(Ticket.ticket_type == type_filter)
    if store_id is not None:
        base_where.append(Ticket.store_id == store_id)

    count_stmt = select(func.count()).select_from(Ticket).where(*base_where)
    list_stmt = (
        select(Ticket)
        .where(*base_where)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if user is not None:
        count_stmt = await _apply_ticket_scope(db, count_stmt, user)
        list_stmt = await _apply_ticket_scope(db, list_stmt, user)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    result = await db.execute(list_stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Create ───────────────────────────────────────────────────────────────────


async def create_ticket(
    db: AsyncSession,
    data: TicketCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
) -> Ticket:
    """
    Yangi murojaat yaratadi.

    Scope: store roli faqat o'z do'koni uchun yarata oladi.
    agent → store_id berilsa, o'z do'konlari ichida bo'lishi shart.
    Idempotentlik: Redis kalit idem:tickets:create:{actor_id}:{client_uuid}.
    """
    # ── Scope: store/agent o'z do'konlari uchun ─────────────────────────────
    if user is not None and data.store_id is not None:
        allowed = await _get_allowed_store_ids(db, user)
        if allowed is not None and data.store_id not in allowed:
            raise AppError("tickets.not_found", status_code=404)

    # ── Redis idempotentlik ──────────────────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Ticket).where(
                    Ticket.id == uuid.UUID(cached_id),
                    Ticket.deleted_at.is_(None),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_ticket: idem_key=%s murojaat o'chirilgan, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_ticket: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi murojaat yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── Murojaat yaratish ────────────────────────────────────────────────────
    ticket = Ticket(
        store_id=data.store_id,
        author_id=actor_id,
        ticket_type=data.ticket_type,
        subject=data.subject,
        body=data.body,
        status="new",
        branch_id=data.branch_id,
        client_uuid=data.client_uuid,
        version=1,
    )

    db.add(ticket)
    try:
        await db.flush()
    except IntegrityError as exc:
        # client_uuid race: parallel so'rov bir xil client_uuid bilan DB ga yetdi.
        # Rollback qilib mavjud ticketni qaytaramiz (idempotentlik).
        await db.rollback()
        if data.client_uuid is not None:
            existing_stmt = select(Ticket).where(
                Ticket.client_uuid == data.client_uuid,
                Ticket.deleted_at.is_(None),
            )
            existing_result = await db.execute(existing_stmt)
            existing_ticket = existing_result.scalar_one_or_none()
            if existing_ticket is not None:
                return existing_ticket
        # client_uuid yo'q yoki topilmasa — asl xatoni qayta raise qilamiz
        raise

    after = {
        "id": str(ticket.id),
        "store_id": str(ticket.store_id) if ticket.store_id else None,
        "author_id": str(ticket.author_id) if ticket.author_id else None,
        "ticket_type": ticket.ticket_type,
        "subject": ticket.subject,
        "status": ticket.status,
    }
    await _write_audit(db, actor_id, "create", str(ticket.id), after=after)
    await _write_outbox(db, str(ticket.id), "ticket.created", {
        "id": str(ticket.id),
        "store_id": str(ticket.store_id) if ticket.store_id else None,
        "ticket_type": ticket.ticket_type,
        "status": ticket.status,
    })

    # ── Redis kalit saqlash ──────────────────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(ticket.id), ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_ticket: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return ticket


# ─── Add Message ──────────────────────────────────────────────────────────────


async def add_message(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    data: TicketMessageCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> TicketMessage:
    """
    Murojaatga xabar qo'shadi.

    Ruxsat: murojaat ishtirokchilari (author_id == user.id yoki store_id scope)
            yoki admin/buxgalter.
    Murojaat topilmasa yoki scope tashqarisi → 404.

    attachment_url: storage'dan olingan URL — bu servis faqat saqlaydi,
                    validatsiya router da amalga oshiriladi.
    """
    # Scope tekshiruvi + murojaat olish
    ticket = await get_ticket(db, ticket_id, user=user)

    msg = TicketMessage(
        ticket_id=ticket.id,
        author_id=actor_id,
        body=data.body,
        attachment_url=data.attachment_url,
    )
    db.add(msg)
    await db.flush()

    # Murojaat updated_at ni yangilash
    ticket.updated_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "add_message", str(ticket.id), after={
        "message_id": str(msg.id),
        "ticket_id": str(ticket.id),
        "has_attachment": msg.attachment_url is not None,
    })
    await _write_outbox(db, str(ticket.id), "ticket.message_added", {
        "ticket_id": str(ticket.id),
        "message_id": str(msg.id),
    })

    return msg


# ─── Update Status ────────────────────────────────────────────────────────────


async def update_status(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    data: TicketStatusUpdate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> Ticket:
    """
    Murojaat holatini yangilaydi (server-avtoritar holat mashinasi).

    Holat matritsasi:
      new → in_progress
      in_progress → resolved | closed
      resolved → in_progress (qayta ochish) | closed
      closed → hech qayerga (terminal)

    Faqat admin/buxgalter (tickets:edit ruxsati).
    version optimistik lock.

    Raises:
        AppError("tickets.invalid_transition", 422): noqonuniy o'tish.
        AppError("tickets.forbidden", 403): ruxsatsiz rol.
        AppError("tickets.not_found", 404): murojaat topilmasa.
    """
    # AUTHZ: faqat admin/buxgalter holat o'zgartira oladi
    if user is not None and user.role not in _RESOLVE_ROLES:
        raise AppError("tickets.forbidden", status_code=403)

    # Admin/buxgalter barcha murojaatlarni ko'ra oladi — scope yo'q
    ticket = await get_ticket(db, ticket_id, user=None)

    # Optimistik lock
    if ticket.version != data.version:
        raise AppError("tickets.version_conflict", status_code=409)

    # Holat o'tishini tekshirish
    if not is_valid_transition(ticket.status, data.status):
        raise AppError(
            "tickets.invalid_transition",
            status_code=422,
            params={"from_status": ticket.status, "to_status": data.status},
        )

    before = {"status": ticket.status, "version": ticket.version}

    ticket.status = data.status
    ticket.version = ticket.version + 1
    ticket.updated_at = _now()

    await db.flush()

    after = {"status": ticket.status, "version": ticket.version}
    await _write_audit(db, actor_id, "status_change", str(ticket.id), before=before, after=after)
    await _write_outbox(db, str(ticket.id), "ticket.status_changed", {
        "id": str(ticket.id),
        "from_status": before["status"],
        "to_status": ticket.status,
        "version": ticket.version,
    })

    return ticket
