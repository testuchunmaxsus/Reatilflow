"""
Ombor servis qatlami — harakatlar va qoldiqlar biznes mantiq.

Funksiyalar:
  record_movement(db, data, actor_id, redis) → StockMovement
  get_balance(db, product_id, warehouse_id) → StockBalance
  list_movements(db, product_id, warehouse_id, ...) → (list[StockMovement], int)

MUHIM QOIDALAR:
  - stock_movement APPEND-ONLY: faqat INSERT. UPDATE/DELETE TAQIQLANGAN.
  - StockBalance — with_for_update() qulflanadi (optimistik lock).
  - qty — Decimal (float emas).
  - client_uuid Redis idempotentlik (24h TTL).
  - Har harakatda audit_log + outbox_event yoziladi.
  - Redis pub/sub: stock:balance:{product_id}:{warehouse_id} kanaliga xabar (ixtiyoriy).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.outbox import OutboxEvent
from app.models.stock import StockBalance, StockMovement
from app.modules.rbac.enterprise_scope import apply_enterprise_filter
from app.modules.stock.schemas import StockMovementCreate

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400       # 24 soat
_IDEM_PREFIX = "idem:stock:movement"
_PUBSUB_PREFIX = "stock:balance"  # Redis pub/sub kanal prefiksi


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="stock_movement",
        entity_id=entity_id,
        before_json=None,
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
        aggregate_type="stock_movement",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


async def _publish_balance_update(
    redis,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    qty_on_hand: Decimal,
) -> None:
    """
    Redis pub/sub: balans yangilanganda real-time xabar yuborish (ixtiyoriy).

    Kanal: stock:balance:{product_id}:{warehouse_id}
    Xato bo'lsa log + graceful degradation (ishlashni to'xtamaslik).
    """
    if redis is None:
        return
    channel = f"{_PUBSUB_PREFIX}:{product_id}:{warehouse_id}"
    payload = json.dumps({
        "product_id": str(product_id),
        "warehouse_id": str(warehouse_id),
        "qty_on_hand": str(qty_on_hand),
    })
    try:
        await redis.publish(channel, payload)
    except Exception as exc:
        logger.warning(
            "stock: Redis pub/sub xatosi (kanal=%s, xato=%r). Ishni davom ettiramiz.",
            channel, exc,
        )


# ─── record_movement ──────────────────────────────────────────────────────────


async def record_movement(
    db: AsyncSession,
    data: StockMovementCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> StockMovement:
    """
    Yangi ombor harakati qayd etadi — APPEND-ONLY INSERT.

    Jarayon:
      1. Redis idempotentlik tekshiruvi (client_uuid).
      2. Mahsulot mavjudligi tekshiruvi.
      3. StockMovement INSERT (APPEND-ONLY — hech qachon UPDATE/DELETE qilinmaydi).
      4. StockBalance yangilash (with_for_update + optimistik version).
         - out uchun: qoldiq yetarli ekanini tekshirish.
      5. audit_log + outbox_event INSERT.
      6. Redis idempotentlik kalitini saqlash.
      7. Redis pub/sub: balans xabari.

    Args:
        db:       Primary DB sessiyasi (yozish uchun).
        data:     StockMovementCreate sxemasi.
        actor_id: Kim bajardi (FK → app_user).
        redis:    Redis klient (idempotentlik + pub/sub uchun).

    Returns:
        Yaratilgan StockMovement yozuvi.

    Raises:
        AppError("stock.product_not_found", 404): mahsulot topilmasa.
        AppError("stock.insufficient_quantity", 409): chiqim qoldiqdan ko'p bo'lsa.

    Izoh (version_conflict YO'Q):
        Pessimistik qulf (with_for_update) ishlatiladi — optimistik lock kerak emas.
        balance.version += 1 faqat bookkeeping sifatida qoladi (audit izi).
    """
    # ── 1. Redis idempotentlik (atomik SET NX) ─────────────────────────────
    # IZOH: DB `client_uuid` unique partial index — asosiy idempotentlik himoyasi;
    #       Redis NX — tezkor kesh (GET→SET race oynasini yopadi).
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                # Mavjud yozuvni qaytarish
                stmt = select(StockMovement).where(StockMovement.id == uuid.UUID(cached_id))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "record_movement: idem_key=%s yozuv topilmadi, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "record_movement: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi harakat yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── 2. Mahsulot mavjudligi tekshiruvi (enterprise filtr bilan) ─────────
    prod_stmt = select(Product.id).where(
        Product.id == data.product_id,
        Product.is_active.is_(True),
    )
    prod_stmt = apply_enterprise_filter(prod_stmt, enterprise_id, Product.enterprise_id)
    prod_result = await db.execute(prod_stmt)
    if prod_result.scalar_one_or_none() is None:
        raise AppError("stock.product_not_found", status_code=404)

    # ── 3. StockMovement INSERT — APPEND-ONLY ───────────────────────────────
    # qty ishorasi: out uchun harakatni qayd etamiz musbat miqdor bilan,
    # balansda ayiramiz. adjust uchun data.qty musbat → kirim, manfiy → chiqim
    # (lekin sxema faqat musbat qty qabul qiladi, type orqali yo'nalish aniqlanadi).
    movement = StockMovement(
        product_id=data.product_id,
        warehouse_id=data.warehouse_id,
        type=data.type,
        qty=data.qty,
        ref_type=data.ref_type,
        ref_id=data.ref_id,
        moved_by=actor_id,
        moved_at=_now(),
        client_uuid=data.client_uuid,
        created_at=_now(),
        enterprise_id=enterprise_id,  # MT2: server-authoritative
    )
    db.add(movement)
    await db.flush()

    # ── 4. StockBalance yangilash ───────────────────────────────────────────
    balance = await _get_or_create_balance(db, data.product_id, data.warehouse_id, enterprise_id)

    # Qoldiq hisoblash
    if data.type == "in":
        new_qty = balance.qty_on_hand + data.qty
    elif data.type == "out":
        if balance.qty_on_hand < data.qty:
            raise AppError(
                "stock.insufficient_quantity",
                status_code=409,
                params={
                    "available": str(balance.qty_on_hand),
                    "requested": str(data.qty),
                },
            )
        new_qty = balance.qty_on_hand - data.qty
    elif data.type == "transfer":
        # Transfer: chiqim sifatida qayd (kiruvchi tomonda alohida harakat kerak)
        if balance.qty_on_hand < data.qty:
            raise AppError(
                "stock.insufficient_quantity",
                status_code=409,
                params={
                    "available": str(balance.qty_on_hand),
                    "requested": str(data.qty),
                },
            )
        new_qty = balance.qty_on_hand - data.qty
    elif data.type == "adjust":
        # adjust FAQAT OSHIRADI (delta += qty): sxema qty > 0 talab qiladi (musbat).
        # Kamaytirish uchun `out` turini ishlating.
        # Izoh: absolyut qiymat o'rnatish emas — delta qo'shish yondashuvi.
        new_qty = balance.qty_on_hand + data.qty
    else:
        new_qty = balance.qty_on_hand

    balance.qty_on_hand = new_qty
    balance.version = balance.version + 1
    balance.updated_at = _now()
    await db.flush()

    # ── 5. Audit + Outbox ──────────────────────────────────────────────────
    after_payload = {
        "id": str(movement.id),
        "product_id": str(data.product_id),
        "warehouse_id": str(data.warehouse_id),
        "type": data.type,
        "qty": str(data.qty),
        "balance_after": str(new_qty),
    }
    await _write_audit(db, actor_id, "create", str(movement.id), after=after_payload)
    await _write_outbox(db, str(movement.id), "stock_movement.created", after_payload)

    # ── 6. Redis kalit saqlash (atomik SET NX EX) ────────────────────────
    # SET key val NX EX 86400 — atomic: faqat mavjud bo'lmasa yozadi (race-safe).
    # Asosiy idempotentlik: DB unique index; Redis — tezkor kesh qatlami.
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(movement.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "record_movement: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    # ── 7. Redis pub/sub ───────────────────────────────────────────────────
    await _publish_balance_update(redis, data.product_id, data.warehouse_id, new_qty)

    return movement


# ─── _get_or_create_balance ───────────────────────────────────────────────────


async def _get_or_create_balance(
    db: AsyncSession,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    enterprise_id: uuid.UUID | None = None,
) -> StockBalance:
    """
    StockBalance yozuvini oladi yoki yaratadi (with_for_update qulfi bilan).

    with_for_update() — bir vaqtda bir nechta so'rov race condition dan saqlaydi.
    """
    stmt = (
        select(StockBalance)
        .where(
            StockBalance.product_id == product_id,
            StockBalance.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    balance = result.scalar_one_or_none()

    if balance is None:
        balance = StockBalance(
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_on_hand=Decimal("0"),
            qty_reserved=Decimal("0"),
            version=1,
            updated_at=_now(),
            enterprise_id=enterprise_id,
        )
        db.add(balance)
        await db.flush()

    return balance


# ─── get_balance ──────────────────────────────────────────────────────────────


async def get_balance(
    db: AsyncSession,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> StockBalance:
    """
    Mahsulot + ombor qoldig'ini qaytaradi.

    Yozuv mavjud bo'lmasa — noldan boshlangan yangi balans qaytaradi
    (INSERT qilinmaydi, faqat virtual).

    Izoh: stock qoldig'i primary DB dan o'qiladi (replica kechikishini oldini olish).
    Bu funksiya doim primary sessiya bilan chaqirilishi kerak.
    """
    stmt = select(StockBalance).where(
        StockBalance.product_id == product_id,
        StockBalance.warehouse_id == warehouse_id,
    )
    result = await db.execute(stmt)
    balance = result.scalar_one_or_none()

    if balance is None:
        # Virtual balans — DB ga yozilmaydi, faqat qaytariladi
        balance = StockBalance(
            id=uuid7(),
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_on_hand=Decimal("0"),
            qty_reserved=Decimal("0"),
            version=0,
            updated_at=_now(),
        )

    return balance


# ─── list_movements ───────────────────────────────────────────────────────────


async def list_movements(
    db: AsyncSession,
    *,
    enterprise_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    movement_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[StockMovement], int]:
    """
    Paginated ombor harakatlari ro'yxati.

    Filtrlar:
      - product_id: mahsulot bo'yicha
      - warehouse_id: ombor bo'yicha
      - movement_type: harakat turi bo'yicha (in | out | transfer | adjust)

    Scope izohi:
      Bu funksiya qator darajasida filtr QILMAYDI (ataylab keng).
      Rol asosida cheklash router/endpoint darajasida amalga oshiriladi.
      agent, courier, accountant, administrator — barcha harakatlarni ko'radi.

    Returns:
        (harakatlar ro'yxati, jami son)
    """
    conditions = []
    if enterprise_id is not None:
        conditions.append(StockMovement.enterprise_id == enterprise_id)
    if product_id is not None:
        conditions.append(StockMovement.product_id == product_id)
    if warehouse_id is not None:
        conditions.append(StockMovement.warehouse_id == warehouse_id)
    if movement_type is not None:
        conditions.append(StockMovement.type == movement_type)

    # Count
    count_stmt = select(func.count()).select_from(StockMovement)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List
    stmt = (
        select(StockMovement)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total
