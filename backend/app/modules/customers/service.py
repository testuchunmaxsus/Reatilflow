"""
Customers servis qatlami — do'konlar biznes mantiq.

Funksiyalar:
  create_store(db, data, actor_id, redis) → Store
  get_store(db, store_id, user) → Store
  list_stores(db, user, filters...) → (list[Store], total)
  update_store(db, store_id, data, actor_id, user) → Store
  delete_store(db, store_id, actor_id, user) → None  (soft-delete)
  assign_agent(db, store_id, agent_id, actor_id, user) → AgentStore

Qoidalar:
  - PII (inn, inps, owner_name, phone) EncryptedString orqali shifrlangan saqlanadi.
  - inn/phone qidiruv faqat blind_index() orqali (ochiq-matn LIKE taqiqlangan).
  - inn_bi partial unique: dublikat INN → 409 (blind-index orqali tekshiriladi).
  - version optimistik lock.
  - client_uuid Redis idempotentlik (catalog naqshi).
  - Har mutatsiyada audit_log + outbox_event yoziladi (PII mask_pii() bilan).
  - Branch ko'rinish: admin/accountant → barchasi; boshqa rollar → apply_store_scope.
  - Soft-delete: deleted_at o'rnatiladi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.core.errors import AppError
from app.core.security import mask_pii
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.outbox import OutboxEvent
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.customers.schemas import StoreCreate, StoreUpdate
from app.modules.rbac.enterprise_scope import apply_enterprise_filter
from app.modules.rbac.scope import apply_store_scope, get_store_visibility_filter

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:customers:create"

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
    """audit_log ga yozuv qo'shadi. PII mask_pii() orqali maskalanadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="store",
        entity_id=entity_id,
        before_json=json.dumps(mask_pii(before), default=str) if before else None,
        after_json=json.dumps(mask_pii(after), default=str) if after else None,
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
        aggregate_type="store",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


def _apply_branch_filter(query, user: AppUser):
    """
    Filial ko'rinish filtri (catalog naqshi).

    administrator/accountant → barcha do'konlar.
    Boshqa rollar → apply_store_scope() orqali (agent, store, courier).
    """
    return apply_store_scope(query, user)


async def _check_inn_unique(
    db: AsyncSession,
    inn: str | None,
    exclude_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """INN unikalligi blind-index orqali tekshiradi. MT2: enterprise bo'yicha. Dublikat → AppError 409."""
    if not inn:
        return
    bi = blind_index(inn)
    stmt = select(Store.id).where(
        Store.inn_bi == bi,
        Store.deleted_at.is_(None),
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Store.enterprise_id)
    if exclude_id is not None:
        stmt = stmt.where(Store.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise AppError("customers.duplicate_inn", status_code=409)


# ─── Get (branch/scope filtri bilan) ─────────────────────────────────────────


async def get_store(
    db: AsyncSession,
    store_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Store:
    """
    ID bo'yicha do'kon oladi.

    ADR-003: get_store_visibility_filter(user) orqali ko'rinish cheklanadi.
      - superadmin: barcha do'konlar.
      - admin/accountant: o'z korxona do'konlari + shartnoma qilgan platforma do'konlari.
      - agent: biriktirilgan do'konlari (agent_id yoki AgentStore).
      - store: faqat o'z do'koni (user_id).
      - courier: barcha (manzil ko'rish).
    Mavjudlikni oshkor qilmaslik: doiradan tashqari do'kon → 404.

    Args:
        db:            AsyncSession
        store_id:      Do'kon UUID
        user:          Joriy foydalanuvchi (filtr uchun; None bo'lsa — filtr yo'q)
        enterprise_id: Eski moslik uchun saqlanadi (ADR-003 da foydalanilmaydi)

    Raises:
        AppError("customers.store_not_found"): topilmasa yoki ko'rinish doirasidan tashqari.
    """
    stmt = select(Store).where(
        Store.id == store_id,
        Store.deleted_at.is_(None),
    )
    if user is not None:
        visibility = get_store_visibility_filter(user)
        if visibility is not None:
            stmt = stmt.where(visibility)

    result = await db.execute(stmt)
    store = result.scalar_one_or_none()
    if store is None:
        raise AppError("customers.store_not_found", status_code=404)
    return store


# ─── List ─────────────────────────────────────────────────────────────────────


async def list_stores(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    branch_id: uuid.UUID | None = None,
    search_inn: str | None = None,
    search_phone: str | None = None,
    search_name: str | None = None,
) -> tuple[list[Store], int]:
    """
    Paginated do'konlar ro'yxati.

    Filtrlar:
      - branch_id: filial bo'yicha
      - search_inn: INN bo'yicha aniq-moslik qidiruv (blind_index orqali)
      - search_phone: telefon bo'yicha aniq-moslik qidiruv (blind_index orqali)
      - search_name: nom bo'yicha LIKE qidiruv (PII emas)

    Xavfsizlik: inn/phone qidiruv FAQAT blind_index orqali — ochiq-matn LIKE taqiqlangan.
    """
    base_where = [Store.deleted_at.is_(None)]

    if branch_id is not None:
        base_where.append(Store.branch_id == branch_id)

    if search_inn:
        bi = blind_index(search_inn)
        base_where.append(Store.inn_bi == bi)

    if search_phone:
        bi = blind_index(search_phone)
        base_where.append(Store.phone_bi == bi)

    if search_name:
        pattern = f"%{search_name}%"
        base_where.append(Store.name.ilike(pattern))

    # ADR-003: ko'rinish filtri (platforma do'konlarini ham qamrab oladi)
    from sqlalchemy import ColumnElement
    visibility: ColumnElement | None = None
    if user is not None:
        visibility = get_store_visibility_filter(user)

    count_stmt = select(func.count()).select_from(Store).where(*base_where)
    if visibility is not None:
        count_stmt = count_stmt.where(visibility)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List (visibility filtri bilan)
    stmt = (
        select(Store)
        .where(*base_where)
        .order_by(Store.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if visibility is not None:
        stmt = stmt.where(visibility)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Create ───────────────────────────────────────────────────────────────────


async def create_store(
    db: AsyncSession,
    data: StoreCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
    actor: AppUser | None = None,
) -> Store:
    """
    Yangi do'kon yaratadi.

    PII (inn, inps, owner_name, phone) EncryptedString orqali shifrlangan saqlanadi.
    inn_bi, phone_bi blind-index yoziladi.
    Idempotentlik: Redis kalit idem:customers:create:{actor_id}:{client_uuid}.

    Server-avtoritar agent_id:
      Agar yaratuvchi "agent" rolida bo'lsa, yangi do'konning agent_id si
      server tomonidan actor.id ga o'rnatiladi (klient yuborgan agent_id e'tiborga
      olinmaydi). Bu mobil ilova watchByAgentId va backend scope uchun zarur.
    """
    # ── Redis idempotentlik ──────────────────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Store).where(
                    Store.id == uuid.UUID(cached_id),
                    Store.deleted_at.is_(None),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_store: idem_key=%s store o'chirilgan, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_store: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi do'kon yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── INN unikalligi (enterprise bo'yicha) ──────────────────────────────────
    await _check_inn_unique(db, data.inn, enterprise_id=enterprise_id)

    # ── Agent roli: agent_id server-avtoritar tarzda o'rnatiladi ─────────────
    # Mobil ilova yuborgan agent_id e'tiborga olinmaydi — IDOR xavfidan himoya.
    # agent o'zi yaratgan do'kon o'ziga birikadi (watchByAgentId + backend scope).
    resolved_agent_id: uuid.UUID | None = data.agent_id
    if actor is not None and actor.role == "agent":
        resolved_agent_id = actor.id

    # ── Do'kon yaratish ──────────────────────────────────────────────────────
    # PII maydonlar EncryptedString TypeDecorator orqali shifrlangan saqlanadi.
    # enterprise_id SERVER tomonidan o'rnatiladi (klient bera olmaydi)
    store = Store(
        name=data.name,
        inn=data.inn,           # EncryptedString → shifrlangan bytes
        inps=data.inps,
        owner_name=data.owner_name,
        phone=data.phone,
        address=data.address,
        gps_lat=data.gps_lat,
        gps_lng=data.gps_lng,
        segment_id=data.segment_id,
        agent_id=resolved_agent_id,
        branch_id=data.branch_id,
        credit_limit=data.credit_limit,
        user_id=data.user_id,
        # Blind-index: None bo'lmagan qiymatlar uchun
        inn_bi=blind_index(data.inn) if data.inn else None,
        phone_bi=blind_index(data.phone) if data.phone else None,
        enterprise_id=enterprise_id,
    )

    db.add(store)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "inn_bi" in exc_str or "uix_store_inn_bi" in exc_str:
            raise AppError("customers.duplicate_inn", status_code=409) from exc
        raise

    after = {
        "id": str(store.id),
        "name": store.name,
        "inn": store.inn,         # mask_pii da maskalanadi
        "phone": store.phone,
        "branch_id": str(store.branch_id) if store.branch_id else None,
    }
    await _write_audit(db, actor_id, "create", str(store.id), after=after)
    await _write_outbox(db, str(store.id), "store.created", {
        "id": str(store.id),
        "name": store.name,
        "branch_id": str(store.branch_id) if store.branch_id else None,
    })

    # ── Redis kalit saqlash ──────────────────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(store.id), ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_store: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return store


# ─── Update ───────────────────────────────────────────────────────────────────


_ADMIN_ONLY_FIELDS = frozenset({"user_id", "agent_id", "branch_id"})


async def update_store(
    db: AsyncSession,
    store_id: uuid.UUID,
    data: StoreUpdate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Store:
    """
    Do'konni yangilaydi (PATCH — faqat berilgan maydonlar).

    Optimistik lock: data.version mos kelmasa → version_conflict.
    PII yangilanganda blind-index ham yangilanadi.

    AUTHZ:
      - user_id, agent_id, branch_id — faqat administrator o'zgartira oladi.
      - Non-admin bu maydonlarni yuborsa → 403.
    """
    store = await get_store(db, store_id, user=user, enterprise_id=enterprise_id)

    if store.version != data.version:
        raise AppError("customers.version_conflict", status_code=409)

    # AUTHZ: admin-only maydonlarni non-admin yubormasin
    if user is not None and user.role != "administrator":
        for field in _ADMIN_ONLY_FIELDS:
            if getattr(data, field) is not None:
                raise AppError("customers.forbidden", status_code=403)

    before = {
        "name": store.name,
        "inn": store.inn,
        "version": store.version,
    }

    # INN o'zgarganda unikalligi tekshirish (enterprise bo'yicha)
    if data.inn is not None and data.inn != store.inn:
        await _check_inn_unique(db, data.inn, exclude_id=store_id, enterprise_id=enterprise_id)

    # Maydonlarni yangilash
    if data.name is not None:
        store.name = data.name
    if data.inn is not None:
        store.inn = data.inn
        store.inn_bi = blind_index(data.inn) if data.inn else None
    if data.inps is not None:
        store.inps = data.inps
    if data.owner_name is not None:
        store.owner_name = data.owner_name
    if data.phone is not None:
        store.phone = data.phone
        store.phone_bi = blind_index(data.phone) if data.phone else None
    if data.address is not None:
        store.address = data.address
    if data.gps_lat is not None:
        store.gps_lat = data.gps_lat
    if data.gps_lng is not None:
        store.gps_lng = data.gps_lng
    if data.segment_id is not None:
        store.segment_id = data.segment_id
    # admin_only fields (already guarded above for non-admin)
    if data.agent_id is not None:
        store.agent_id = data.agent_id
    if data.branch_id is not None:
        store.branch_id = data.branch_id
    if data.credit_limit is not None:
        store.credit_limit = data.credit_limit
    if data.user_id is not None:
        store.user_id = data.user_id

    expected_version = data.version
    store.version = store.version + 1
    store.updated_at = _now()

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "inn_bi" in exc_str or "uix_store_inn_bi" in exc_str:
            raise AppError("customers.duplicate_inn", status_code=409) from exc
        raise

    # DB-darajali optimistik lock tekshiruvi:
    # Agar store.version - 1 != expected_version bo'lsa, boshqa tranzaksiya
    # o'rtada o'zgartirgan — 409 qaytaramiz.
    # (flush muvaffaqiyatli o'tdi, lekin version tekshiruvi qo'shimcha himoya.)
    # Asosiy tekshiruv yuqorida (store.version != data.version) o'tkazilgan;
    # bu izoh: to'liq DB-darajali lock uchun SQLAlchemy version_id_col yoki
    # "UPDATE ... WHERE version=:expected AND rowcount==0 → 409" ishlatilishi kerak.
    # Hozirgi yondashuv: session-darajali tekshiruv (flush atomik tranzaksiya ichida).

    after = {
        "name": store.name,
        "inn": store.inn,
        "version": store.version,
    }
    await _write_audit(db, actor_id, "update", str(store.id), before=before, after=after)
    await _write_outbox(db, str(store.id), "store.updated", {
        "id": str(store.id),
        "name": store.name,
        "version": store.version,
    })

    return store


# ─── Delete (soft) ────────────────────────────────────────────────────────────


async def delete_store(
    db: AsyncSession,
    store_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """
    Do'konni soft-delete qiladi (deleted_at o'rnatadi).

    MT2: enterprise_id filtr — boshqa korxona do'konini o'chirib bo'lmaydi.

    Raises:
        AppError("customers.store_not_found"): topilmasa yoki doiradan tashqari.
    """
    store = await get_store(db, store_id, user=user, enterprise_id=enterprise_id)
    store.deleted_at = _now()
    store.updated_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "delete", str(store.id))
    await _write_outbox(db, str(store.id), "store.deleted", {"id": str(store.id)})


# ─── Assign Agent ─────────────────────────────────────────────────────────────


async def assign_agent(
    db: AsyncSession,
    store_id: uuid.UUID,
    agent_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> AgentStore:
    """
    Do'konga agent biriktiradi (AgentStore yozadi).

    MT2: enterprise_id filtr — boshqa korxona do'koniga agent biriktirib bo'lmaydi.
    Agent mavjudligi va roli tekshiriladi.
    Allaqachon biriktirilgan bo'lsa — mavjud yozuvni qaytaradi (idempotent).

    Raises:
        AppError("customers.store_not_found"): do'kon topilmasa.
        AppError("customers.agent_not_found"): agent topilmasa yoki noto'g'ri rol.
    """
    store = await get_store(db, store_id, user=user, enterprise_id=enterprise_id)

    # Agent tekshiruvi (enterprise bo'yicha — boshqa korxona agentini biriktirish imkonsiz)
    agent_stmt = select(AppUser).where(
        AppUser.id == agent_id,
        AppUser.role == "agent",
        AppUser.is_active.is_(True),
    )
    agent_stmt = apply_enterprise_filter(agent_stmt, enterprise_id, AppUser.enterprise_id)
    agent_result = await db.execute(agent_stmt)
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        raise AppError("customers.agent_not_found", status_code=404)

    # Store'ning ASOSIY agentini ham o'rnatamiz. Backend scope (apply_store_scope)
    # `Store.agent_id == user.id OR agent_store link` ni qo'llaydi, LEKIN mobil ilova
    # faqat store.agent_id'ga tayanadi (watchByAgentId). Faqat link yozsak — agent
    # mobil ilovada do'konni TOPA OLMAYDI. Shu sabab store.agent_id'ni ham yangilaymiz
    # (idempotent re-assign ham eski NULL agent_id'ni tuzatadi — router commit qiladi).
    store.agent_id = agent_id

    # Allaqachon biriktirilganmi?
    existing_stmt = select(AgentStore).where(
        AgentStore.agent_id == agent_id,
        AgentStore.store_id == store_id,
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    # ADR-003: platforma do'koni (store.enterprise_id IS NULL) uchun
    # AgentStore.enterprise_id ni agent korxonasidan olamiz.
    # Odatdagi korxona do'koni uchun store.enterprise_id ishlatiladi.
    link_enterprise_id = (
        agent.enterprise_id
        if store.enterprise_id is None
        else store.enterprise_id
    )
    link = AgentStore(
        agent_id=agent_id,
        store_id=store_id,
        enterprise_id=link_enterprise_id,
    )
    db.add(link)
    await db.flush()

    await _write_audit(
        db, actor_id, "assign_agent", str(store.id),
        after={"agent_id": str(agent_id), "store_id": str(store_id)},
    )
    await _write_outbox(db, str(store.id), "store.agent_assigned", {
        "store_id": str(store_id),
        "agent_id": str(agent_id),
    })

    return link
