"""
Yetkazib berish servis qatlami — T18 Delivery.

HOLAT MASHINASI (server-avtoritar, ADR §3.5):
  assigned → started → delivering → delivered
  istalgan holat → failed (delivered bundan mustasno — TERMINAL)
  Noqonuniy o'tish → AppError("delivery.invalid_transition", 422)

GPS INTEGRATSIYA (ADR §3.7):
  Yetkazish GPS treki GpsPoint (TimescaleDB, ALOHIDA BAZA) da saqlanadi.
  Cross-DB FK YO'Q — GpsPoint.delivery_id faqat UUID reference.
  KEY NUQTALAR (delivery jadvalida):
    started   → start_gps_lat/lng yoziladi
    delivered → delivery_gps_lat/lng yoziladi
  TO'LIQ TREK: GET /gps/track/{delivery_id} (GPS moduli)

IDEMPOTENTLIK:
  client_uuid unique partial index (IS NOT NULL) — takroriy tayinlashdan himoya.
  IntegrityError → mavjud yetkazish qaytariladi (graceful).

AUDIT/OUTBOX:
  Har mutatsiyada audit_log + outbox_event yoziladi.

IDOR/SCOPE:
  Kuryer: FAQAT o'ziga tayinlangan yetkazishni o'zgartiradi.
  Agent: faqat o'z buyurtmasi yetkazishini ko'radi.
  Do'kon: faqat o'z buyurtmasi yetkazishini ko'radi.
  Admin/Accountant: barchasi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.delivery import Delivery, VALID_TRANSITIONS
from app.models.order import Order
from app.models.outbox import OutboxEvent
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.delivery.schemas import DeliveryCreate, DeliveryStatusUpdate
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_PREFIX = "idem:delivery:create"
_IDEM_TTL_SECONDS = 86400  # 24 soat

# Buyurtma holatlari yetkazishga yaratishga ruxsat beruvchi
_ALLOWED_ORDER_STATUSES = frozenset({"confirmed", "packed", "delivering"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Audit / Outbox yordamchilari ─────────────────────────────────────────────


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    after: dict | None = None,
    before: dict | None = None,
) -> None:
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=json.dumps(before, default=str) if before else None,
        after_json=json.dumps(after, default=str) if after else None,
    )
    db.add(log)


async def _write_outbox(
    db: AsyncSession,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


# ─── Scope/IDOR tekshiruv ─────────────────────────────────────────────────────


async def _check_delivery_access(
    db: AsyncSession,
    delivery: Delivery,
    user: AppUser,
) -> None:
    """
    IDOR himoya: foydalanuvchi berilgan yetkazishga kirish huquqini tekshiradi.

    - administrator/accountant: barchasi (branch_id tekshiruvi ixtiyoriy).
    - courier: FAQAT o'ziga tayinlangan yetkazish.
    - agent: faqat o'z buyurtmalari yetkazishi.
    - store: faqat o'z buyurtmalari yetkazishi.
    - Ruxsatsiz → AppError("delivery.forbidden", 403/404).
    """
    role = user.role

    if role in ("administrator", "accountant"):
        if user.branch_id is not None and delivery.branch_id is not None:
            if delivery.branch_id != user.branch_id:
                raise AppError("delivery.forbidden", status_code=404)
        return

    if role == "courier":
        # Kuryer FAQAT o'ziga tayinlangan yetkazishni ko'ra/o'zgartira oladi (IDOR)
        if delivery.courier_id != user.id:
            raise AppError("delivery.forbidden", status_code=403)
        return

    if role == "agent":
        # Agent faqat o'z buyurtmalari yetkazishini ko'radi
        stmt = select(Order).where(
            Order.id == delivery.order_id,
            Order.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            raise AppError("delivery.forbidden", status_code=404)

        # Agent o'z do'konlari buyurtmalarini ko'radi
        allowed_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        from sqlalchemy import or_
        store_stmt = select(Store.id).where(
            Store.id == order.store_id,
            or_(
                Store.agent_id == user.id,
                Store.id.in_(allowed_subq),
            ),
        )
        store_result = await db.execute(store_stmt)
        if store_result.scalar_one_or_none() is None:
            raise AppError("delivery.forbidden", status_code=404)
        return

    if role == "store":
        # Do'kon faqat o'z buyurtmasi yetkazishini ko'radi
        stmt = select(Order).where(
            Order.id == delivery.order_id,
            Order.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            raise AppError("delivery.forbidden", status_code=404)

        store_stmt = select(Store.id).where(
            Store.id == order.store_id,
            Store.user_id == user.id,
        )
        store_result = await db.execute(store_stmt)
        if store_result.scalar_one_or_none() is None:
            raise AppError("delivery.forbidden", status_code=404)
        return

    raise AppError("delivery.forbidden", status_code=403)


# ─── create_delivery ──────────────────────────────────────────────────────────


async def create_delivery(
    db: AsyncSession,
    data: DeliveryCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> Delivery:
    """
    Yangi yetkazish yaratadi — kuryer tayinlash.

    Tekshiruvlar:
      1. client_uuid idempotentlik (Redis SET NX + DB partial unique).
      2. Buyurtma mavjudligi va holati (_ALLOWED_ORDER_STATUSES).
      3. Kuryer roli tekshiruvi (app_user.role == "courier").
      4. Delivery INSERT.
      5. Audit + Outbox.

    Status boshlang'ich: "assigned"

    Raises:
        AppError("delivery.order_not_found", 404): buyurtma topilmasa.
        AppError("delivery.invalid_transition", 422): buyurtma noto'g'ri holatda.
        AppError("delivery.not_courier", 422): tayinlanadigan foydalanuvchi kuryer emas.
    """
    # ── 1. client_uuid idempotentlik ─────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Delivery).where(Delivery.id == uuid.UUID(cached_id))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_delivery: idem_key=%s yozuv topilmadi, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_delivery: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r).",
                idem_key, exc,
            )
            idem_key = None

    # ── 2. Buyurtma mavjudligi va holati (enterprise filtr bilan) ────────
    order_stmt = select(Order).where(
        Order.id == data.order_id,
        Order.deleted_at.is_(None),
    )
    order_stmt = apply_enterprise_filter(order_stmt, enterprise_id, Order.enterprise_id)
    order_result = await db.execute(order_stmt)
    order = order_result.scalar_one_or_none()
    if order is None:
        raise AppError("delivery.order_not_found", status_code=404)

    if order.status not in _ALLOWED_ORDER_STATUSES:
        raise AppError(
            "delivery.invalid_transition",
            status_code=422,
            params={
                "from_status": order.status,
                "to_status": "assigned",
            },
        )

    # ── 3a. Agent uchun order-scope tekshiruvi (cross-tenant IDOR himoya) ────
    # Agent FAQAT o'z do'konlariga tegishli buyurtmalarga kuryer tayinlay oladi.
    # Admin/accountant — barcha buyurtmalarga tayinlay oladi.
    # store roli — router darajasida bloklangan (delivery:create yo'q).
    if user is not None and user.role == "agent":
        from sqlalchemy import or_
        allowed_stores_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        scope_stmt = select(Store.id).where(
            Store.id == order.store_id,
            Store.deleted_at.is_(None),
            or_(
                Store.agent_id == user.id,
                Store.id.in_(allowed_stores_subq),
            ),
        )
        scope_result = await db.execute(scope_stmt)
        if scope_result.scalar_one_or_none() is None:
            raise AppError("delivery.order_not_found", status_code=404)

    # ── 3b. Kuryer roli tekshiruvi ────────────────────────────────────────
    courier_stmt = select(AppUser).where(
        AppUser.id == data.courier_id,
        AppUser.is_active.is_(True),
    )
    courier_result = await db.execute(courier_stmt)
    courier = courier_result.scalar_one_or_none()
    if courier is None or courier.role != "courier":
        raise AppError("delivery.not_courier", status_code=422)

    # ── 3c. Aktiv yetkazish tekshiruvi (operatsion yaxlitlik) ─────────────
    # Bir buyurtmaga faqat bitta aktiv yetkazish bo'lishi mumkin.
    # Aktiv = status NOT IN ('delivered', 'failed') AND deleted_at IS NULL.
    # Bu servis darajasidagi tekshiruv race conditiondan oldin ishlaydi.
    # DB darajasidagi partial unique index (Postgres) — ikkinchi himoya qatlami.
    active_stmt = select(Delivery.id).where(
        Delivery.order_id == data.order_id,
        Delivery.status.not_in(("delivered", "failed")),
        Delivery.deleted_at.is_(None),
    )
    active_result = await db.execute(active_stmt)
    if active_result.scalar_one_or_none() is not None:
        raise AppError("delivery.already_assigned", status_code=409)

    # ── 4. Delivery INSERT ────────────────────────────────────────────────
    delivery = Delivery(
        id=uuid7(),
        order_id=data.order_id,
        courier_id=data.courier_id,
        status="assigned",
        assigned_at=_now(),
        branch_id=order.branch_id,
        client_uuid=data.client_uuid,
        version=1,
        created_at=_now(),
        updated_at=_now(),
        enterprise_id=enterprise_id,  # MT2: server-authoritative
    )
    db.add(delivery)
    try:
        # Savepoint orqali flush — IntegrityError holatida faqat shu nuqta rollback bo'ladi,
        # session holati (audit/outbox yuqorida emas — ular keyin yoziladi) saqlanadi.
        # Bu rollback'dan keyin ifloslangan session muammosini oldini oladi:
        #   - `begin_nested()` SAVEPOINT yaratadi.
        #   - IntegrityError → savepoint rollback (session saqlanadi, boshqa ob'ektlar saqlanadi).
        #   - Muvaffaqiyatli → savepoint commit (asosiy tranzaksiya davom etadi).
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        # Savepoint rollback bo'ldi — session hali tirik, audit/outbox yozilmagan (OK).
        # 1) client_uuid takrori → mavjud yetkazish qaytariladi (idempotentlik).
        if data.client_uuid is not None:
            existing_stmt = select(Delivery).where(
                Delivery.client_uuid == data.client_uuid,
                Delivery.deleted_at.is_(None),
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                return existing
        # 2) Partial unique (order aktiv konflikti) yoki boshqa IntegrityError
        #    → race condition holati: servis tekshiruvi o'tib ketgan, DB blokladi.
        #    order_id aktiv tekshiruvi yetarli ekanligini bildiradi.
        raise AppError("delivery.already_assigned", status_code=409) from exc

    # ── 5. Audit + Outbox ─────────────────────────────────────────────────
    after_payload = {
        "id": str(delivery.id),
        "order_id": str(data.order_id),
        "courier_id": str(data.courier_id),
        "status": "assigned",
    }
    await _write_audit(db, actor_id, "create", "delivery", str(delivery.id), after=after_payload)
    await _write_outbox(db, "delivery", str(delivery.id), "delivery.created", after_payload)

    # ── 6. Redis idempotentlik kaliti ─────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(delivery.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_delivery: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return delivery


# ─── update_status ────────────────────────────────────────────────────────────


async def update_status(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    data: DeliveryStatusUpdate,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Delivery:
    """
    Yetkazish holatini o'zgartiradi — server-avtoritar holat mashinasi.

    Qonuniy o'tishlar:
      assigned  → started, failed
      started   → delivering, failed
      delivering → delivered, failed
      delivered → (hech qaerga, TERMINAL)
      failed    → (hech qaerga, TERMINAL)

    GPS YOZISH:
      started holati:   start_gps_lat/lng yoziladi (agar gps_lat/lng berilsa).
      delivered holati: delivery_gps_lat/lng yoziladi (agar gps_lat/lng berilsa).
      GPS trek: GpsPoint(delivery_id=...) — alohida TimescaleDB, cross-DB FK yo'q.

    IDOR: kuryer FAQAT o'ziga tayinlangan yetkazishni o'zgartiradi.

    Raises:
        AppError("delivery.not_found", 404): yetkazish topilmasa.
        AppError("delivery.invalid_transition", 422): noqonuniy o'tish.
        AppError("orders.version_conflict", 409): versiya mos kelmasa.
        AppError("delivery.forbidden", 403): boshqa kuryerning yetkazishi.
    """
    # SELECT ... FOR UPDATE — holat mashinasi race condition oldini olish.
    # Ikkita parallel PATCH so'rovi bir vaqtda kelsa, biri lock kutadi.
    # Bu optimistik lock (version) + pessimistik lock (FOR UPDATE) kombinatsiyasi:
    #   - FOR UPDATE: DB darajasida seriallash (race window yo'q).
    #   - version check: klient-tarafda parallel yangilash aniqlanadi (409).
    # SQLite (test): with_for_update() e'tiborga olinmaydi — bu OK (test seriyali).
    stmt = (
        select(Delivery)
        .where(
            Delivery.id == delivery_id,
            Delivery.deleted_at.is_(None),
        )
        .with_for_update()
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Delivery.enterprise_id)
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise AppError("delivery.not_found", status_code=404)

    # IDOR: RBAC scope tekshiruvi
    if user is not None:
        await _check_delivery_access(db, delivery, user)

    # KURYER O'ZINING YETKAZISHI — IDOR qo'shimcha tekshiruv
    if user is not None and user.role == "courier":
        if delivery.courier_id != user.id:
            raise AppError("delivery.forbidden", status_code=403)

    # Versiya optimistik lock
    if delivery.version != data.version:
        raise AppError("orders.version_conflict", status_code=409)

    # Holat mashinasi tekshiruvi
    allowed_next = VALID_TRANSITIONS.get(delivery.status, set())
    if data.status not in allowed_next:
        raise AppError(
            "delivery.invalid_transition",
            status_code=422,
            params={
                "from_status": delivery.status,
                "to_status": data.status,
            },
        )

    before_payload = {
        "status": delivery.status,
        "version": delivery.version,
    }

    actor_id = user.id if user else None
    now = _now()

    # ── Holat-spesifik maydonlarni yangilash ──────────────────────────────
    if data.status == "started":
        delivery.started_at = now
        # GPS boshlash nuqtasi (ADR §3.7 — key nuqta)
        if data.gps_lat is not None:
            delivery.start_gps_lat = data.gps_lat
        if data.gps_lng is not None:
            delivery.start_gps_lng = data.gps_lng

    elif data.status == "delivered":
        delivery.delivered_at = now
        # GPS yetkazish nuqtasi
        if data.gps_lat is not None:
            delivery.delivery_gps_lat = data.gps_lat
        if data.gps_lng is not None:
            delivery.delivery_gps_lng = data.gps_lng

    elif data.status == "failed":
        if data.failure_reason:
            delivery.failure_reason = data.failure_reason

    delivery.status = data.status
    delivery.version = delivery.version + 1
    delivery.updated_at = now
    await db.flush()

    # Audit + Outbox
    after_payload = {
        "id": str(delivery.id),
        "order_id": str(delivery.order_id),
        "status": data.status,
        "version": delivery.version,
    }
    await _write_audit(
        db, actor_id, "update_status", "delivery", str(delivery.id),
        before=before_payload, after=after_payload,
    )
    await _write_outbox(
        db, "delivery", str(delivery.id), "delivery.status_updated", after_payload,
    )

    return delivery


# ─── set_proof_photo ─────────────────────────────────────────────────────────


async def set_proof_photo(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    photo_url: str,
    user: AppUser | None = None,
) -> Delivery:
    """
    Yetkazish dalil rasmini saqlaydi.

    Rasm URL — storage'dan (magic-byte validatsiyasi storage qatlamida).
    delivered holati uchun rasm saqlash majburiy emas, ixtiyoriy.

    IDOR: kuryer FAQAT o'ziga tayinlangan yetkazish rasmi yuklaydi.

    Raises:
        AppError("delivery.not_found", 404): yetkazish topilmasa.
        AppError("delivery.forbidden", 403): boshqa kuryerning yetkazishi.
    """
    stmt = select(Delivery).where(
        Delivery.id == delivery_id,
        Delivery.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise AppError("delivery.not_found", status_code=404)

    # IDOR scope
    if user is not None:
        await _check_delivery_access(db, delivery, user)

    actor_id = user.id if user else None
    before_payload = {"proof_photo_url": delivery.proof_photo_url}

    delivery.proof_photo_url = photo_url
    delivery.updated_at = _now()
    await db.flush()

    await _write_audit(
        db, actor_id, "set_proof_photo", "delivery", str(delivery.id),
        before=before_payload,
        after={"proof_photo_url": photo_url},
    )

    return delivery


# ─── get_delivery ─────────────────────────────────────────────────────────────


async def get_delivery(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Delivery:
    """
    Bitta yetkazishni qaytaradi.

    RBAC scope: IDOR himoya.
    Ruxsatsiz → AppError("delivery.not_found", 404).
    """
    stmt = select(Delivery).where(
        Delivery.id == delivery_id,
        Delivery.deleted_at.is_(None),
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Delivery.enterprise_id)
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise AppError("delivery.not_found", status_code=404)

    if user is not None:
        await _check_delivery_access(db, delivery, user)

    return delivery


# ─── list_deliveries ──────────────────────────────────────────────────────────


async def list_deliveries(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    status: str | None = None,
    courier_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Delivery], int]:
    """
    Paginated yetkazishlar ro'yxati.

    RBAC scope:
      - courier:        faqat o'ziga tayinlangan.
      - agent:          faqat o'z buyurtmalari yetkazishi.
      - store:          faqat o'z buyurtmalari yetkazishi.
      - administrator/accountant: barchasi (branch_id bo'yicha).
    """
    from sqlalchemy import or_

    conditions = [Delivery.deleted_at.is_(None)]

    # MT2: Enterprise izolyatsiyasi
    if enterprise_id is not None:
        conditions.append(Delivery.enterprise_id == enterprise_id)

    if user is not None:
        role = user.role

        if role == "courier":
            # Kuryer faqat o'ziga tayinlangan
            conditions.append(Delivery.courier_id == user.id)

        elif role == "agent":
            # Agent faqat o'z buyurtmalari yetkazishi
            allowed_subq = (
                select(AgentStore.store_id)
                .where(AgentStore.agent_id == user.id)
                .scalar_subquery()
            )
            agent_order_subq = (
                select(Order.id).where(
                    Order.deleted_at.is_(None),
                    or_(
                        Order.store_id.in_(
                            select(Store.id).where(Store.agent_id == user.id)
                        ),
                        Order.store_id.in_(allowed_subq),
                    ),
                ).scalar_subquery()
            )
            conditions.append(Delivery.order_id.in_(agent_order_subq))

        elif role == "store":
            # Do'kon faqat o'z buyurtmalari yetkazishi
            store_order_subq = (
                select(Order.id).where(
                    Order.deleted_at.is_(None),
                    Order.store_id.in_(
                        select(Store.id).where(Store.user_id == user.id)
                    ),
                ).scalar_subquery()
            )
            conditions.append(Delivery.order_id.in_(store_order_subq))

        elif role in ("administrator", "accountant"):
            if user.branch_id is not None:
                conditions.append(
                    or_(
                        Delivery.branch_id == user.branch_id,
                        Delivery.branch_id.is_(None),
                    )
                )

    # Qo'shimcha filtrlar
    if status is not None:
        conditions.append(Delivery.status == status)
    if courier_id is not None:
        conditions.append(Delivery.courier_id == courier_id)
    if order_id is not None:
        conditions.append(Delivery.order_id == order_id)
    if date_from is not None:
        conditions.append(Delivery.assigned_at >= date_from)
    if date_to is not None:
        conditions.append(Delivery.assigned_at <= date_to)

    # Count
    count_stmt = select(func.count()).select_from(Delivery)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List
    stmt = (
        select(Delivery)
        .order_by(Delivery.assigned_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total
