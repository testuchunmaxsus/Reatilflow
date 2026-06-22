"""
Buyurtma servis qatlami — T11 Buyurtma yadrosi.

ATOMIKLIK KAFOLATI (eng muhim invariant):
  create_order() BITTA DB tranzaksiyasida (bitta get_db() sessiyasi) bajariladi:
    1. Order + OrderLine INSERT
    2. Har qator uchun stock chiqimi → _record_movement_tx() (flush, commit YO'Q)
    3. LedgerEntry debit (do'kon qarzi) → _record_entry_tx() (flush, commit YO'Q)
  get_db() request oxirida BITTA commit qiladi.
  Agar qoldiq yetmasa → AppError → session.rollback() → hech narsa yozilmaydi.

Stock/Finance transaksiya yordamchilari:
  _record_movement_tx(db, data, actor_id) — record_movement() ning tranzaksiya-xavfsiz varianti.
    FARQI: Redis idempotentlik va pub/sub CHAQIRILMAYDI (Redis create_order ichida ixtiyoriy).
    Faqat DB operatsiyalari: INSERT movement + UPDATE balance (flush, commit YO'Q).
  _record_entry_tx(db, data, actor_id) — record_entry() ning tranzaksiya-xavfsiz varianti.
    Faqat DB operatsiyalari: INSERT ledger_entry + UPDATE account_balance (flush, commit YO'Q).

Nima uchun alohida _tx variantlar?
  record_movement() va record_entry() da Redis idempotentlik va commit'siz ishlash uchun
  to'liq sessiyani nazoratlash mumkin emas (ular Redis SET NX bajaradi, aks holda muammo).
  _tx variantlar faqat DB flush qiladi va caller commit qiladi.

Holat mashinasi (server-avtoritar, ADR §3.5):
  draft → confirmed → packed → delivering → delivered
  har holatdan → canceled (delivered BUNDAN MUSTASNO — terminal)
  Noqonuniy o'tish → AppError("orders.invalid_transition", 422)

NARX XAVFSIZLIGI (CRITICAL):
  Narx FAQAT server tomonida katalogdan olinadi:
  - _get_product_price(product_id, store.segment_id) — do'kon segmenti bo'yicha.
  - Klient unit_price/segment_id/discount bera olmaydi (schema darajasida olib tashlangan).
  - Segment narxi topilmasa → AppError("orders.no_price", 422) — deterministik xato.
  - "Eng yangi/birinchi narx" fallback YO'Q — faqat aniq segment bo'yicha.

KOMPENSATSIYA (canceled):
  Agar confirmed/packed/delivering holatdagi buyurtma canceled bo'lsa —
  BITTA ACID tranzaksiyada:
    - Teskari ombor harakati (type=in — qaytim) — har qator uchun.
    - Teskari ledger (type=credit — qarzni qaytar) — total_amount.
  Bu yondashuv pul/qoldiq izchilligini kafolatlaydi.

IDEMPOTENTLIK IZCHILLIGI:
  Redis kaliti: {actor_id}:{store_id}:{client_uuid} (aktor+do'kon-mahalliy).
  DB unique constraint: (store_id, client_uuid) — izchil.
  Yechim: IntegrityError ushlanadi, mavjud buyurtma (store_id + client_uuid) qaytariladi.
  Boshqa aktor bir xil store+client_uuid ishlatsa → AppError("orders.idempotency_conflict", 409).

RBAC scope (qator-darajali):
  - agent: faqat o'z do'konlari (AgentStore yoki Store.agent_id)
  - store: faqat o'z do'koni (Store.user_id == user.id)
  - accountant/administrator: branch_id bo'yicha yoki barchasi
  - boshqa do'kon buyurtmasi → 404 (IDOR: mavjudlikni oshkor qilmaslik)
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
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.catalog import Product, ProductPrice
from app.models.finance import AccountBalance, LedgerEntry
from app.models.order import Order, OrderLine, OrderTemplate, OrderTemplateLine, VALID_TRANSITIONS
from app.models.outbox import OutboxEvent
from app.models.stock import StockBalance, StockMovement
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.orders.schemas import (
    OrderCreate,
    OrderStatusUpdate,
    OrderLineIn,
    OrderTemplateCreate,
    TemplateLineIn,
    ApplyTemplateIn,
)
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400       # 24 soat
_IDEM_PREFIX = "idem:orders:create"

# Default warehouse ID — settings orqali konfiguratsiya qilinadi (MEDIUM #6)
def _get_default_warehouse() -> uuid.UUID:
    return uuid.UUID(settings.default_warehouse_id)


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


# ─── Tranzaksiya-xavfsiz stock yordamchisi ────────────────────────────────────


async def _record_movement_tx(
    db: AsyncSession,
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    qty: Decimal,
    actor_id: uuid.UUID | None,
    ref_type: str = "order",
    ref_id: uuid.UUID | None = None,
    movement_type: str = "out",
) -> StockMovement:
    """
    Tranzaksiya ichida ombor harakatini qayd etadi.

    movement_type="out" — chiqim (buyurtma yaratish).
    movement_type="in"  — qaytim (kompensatsiya, canceldan so'ng).

    MUHIM FARQ record_movement() DAN:
      - Redis idempotentlik CHAQIRILMAYDI (caller tranzaksiya boshqaradi).
      - Redis pub/sub CHAQIRILMAYDI.
      - Faqat DB INSERT + UPDATE (flush, COMMIT YO'Q).
      - Caller (create_order) commit qiladi.

    LOCK TARTIBI (MEDIUM #8): LOCK → check → INSERT
    Qoldiq yetmasa (type=out) → AppError("orders.insufficient_stock", 409) ko'taradi.
    """
    # MUHIM: Avval pessimistik qulf ol (mantiqiy tartib: LOCK→check→INSERT)
    balance_stmt = (
        select(StockBalance)
        .where(
            StockBalance.product_id == product_id,
            StockBalance.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    balance_result = await db.execute(balance_stmt)
    balance = balance_result.scalar_one_or_none()

    if balance is None:
        balance = StockBalance(
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_on_hand=Decimal("0"),
            qty_reserved=Decimal("0"),
            version=1,
            updated_at=_now(),
        )
        db.add(balance)
        await db.flush()

    if movement_type == "out" and balance.qty_on_hand < qty:
        raise AppError(
            "orders.insufficient_stock",
            status_code=409,
            params={
                "available": str(balance.qty_on_hand),
                "requested": str(qty),
            },
        )

    # StockMovement INSERT
    movement = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        type=movement_type,
        qty=qty,
        ref_type=ref_type,
        ref_id=ref_id,
        moved_by=actor_id,
        moved_at=_now(),
        client_uuid=None,
        created_at=_now(),
    )
    db.add(movement)
    await db.flush()

    # StockBalance yangilash
    if movement_type == "out":
        balance.qty_on_hand = balance.qty_on_hand - qty
    else:
        balance.qty_on_hand = balance.qty_on_hand + qty

    balance.version = balance.version + 1
    balance.updated_at = _now()
    await db.flush()

    return movement


# ─── Tranzaksiya-xavfsiz finance yordamchisi ─────────────────────────────────


async def _record_entry_tx(
    db: AsyncSession,
    store_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    actor_id: uuid.UUID | None,
    ref_type: str = "order",
    ref_id: uuid.UUID | None = None,
    entry_type: str = "debit",
) -> LedgerEntry:
    """
    Tranzaksiya ichida ledger yozuvini qayd etadi.

    entry_type="debit"  — do'kon qarzi (buyurtma yaratish).
    entry_type="credit" — qarzni qaytarish (kompensatsiya, canceldan so'ng).

    MUHIM FARQ record_entry() DAN:
      - Redis idempotentlik CHAQIRILMAYDI.
      - Faqat DB INSERT + UPDATE (flush, COMMIT YO'Q).
      - Caller (create_order) commit qiladi.
      - Do'kon mavjudligi tekshiruvi caller darajasida amalga oshiriladi.

    LOCK TARTIBI (MEDIUM SRE): LOCK → check → INSERT
    _record_movement_tx bilan izchil tartib: avval AccountBalance qulflanadi,
    keyin LedgerEntry INSERT + balans yangilash.
    Bu deadlock xavfini oldini oladi (bir tranzaksiyada ikkala _tx chaqirilganda).
    """
    # MUHIM: Avval pessimistik qulf ol (mantiqiy tartib: LOCK → check → INSERT)
    bal_stmt = (
        select(AccountBalance)
        .where(AccountBalance.store_id == store_id)
        .with_for_update()
    )
    bal_result = await db.execute(bal_stmt)
    acct_balance = bal_result.scalar_one_or_none()

    if acct_balance is None:
        acct_balance = AccountBalance(
            store_id=store_id,
            balance=Decimal("0"),
            currency=currency,
            last_recalc_at=_now(),
            version=1,
        )
        db.add(acct_balance)
        await db.flush()

    # LedgerEntry INSERT
    entry = LedgerEntry(
        store_id=store_id,
        type=entry_type,
        amount=amount,
        currency=currency,
        ref_type=ref_type,
        ref_id=ref_id,
        entry_date=_now(),
        created_by=actor_id,
        client_uuid=None,
        created_at=_now(),
    )
    db.add(entry)
    await db.flush()

    # Valyuta muvofiqligini tekshirish
    if acct_balance.currency != currency:
        raise AppError(
            "finance.currency_mismatch",
            status_code=409,
            params={
                "existing": acct_balance.currency,
                "incoming": currency,
            },
        )

    if entry_type == "debit":
        acct_balance.balance = acct_balance.balance + amount
    else:
        # credit — qarzni kamaytirish (qaytarish)
        acct_balance.balance = acct_balance.balance - amount

    acct_balance.version = acct_balance.version + 1
    acct_balance.last_recalc_at = _now()
    await db.flush()

    return entry


# ─── Narx qidirish ────────────────────────────────────────────────────────────


async def _get_product_price(
    db: AsyncSession,
    product_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> Decimal | None:
    """
    Mahsulot narxini katalogdan oladi — ANIQ SEGMENT bo'yicha.

    XAVFSIZLIK (HIGH):
      - segment_id MAJBURIY: do'kon (Store.segment_id) dan server tomonida olinadi.
      - "Eng yangi/birinchi narx" fallback YO'Q — deterministik bo'lsin.
      - Narx topilmasa → None qaytaradi (caller AppError ko'taradi).

    Args:
        product_id: Mahsulot ID.
        segment_id: Do'kon segmenti ID (Store.segment_id dan olinadi).

    Returns:
        Decimal narx yoki None (topilmasa).
    """
    stmt = select(ProductPrice).where(
        ProductPrice.product_id == product_id,
        ProductPrice.segment_id == segment_id,
        ProductPrice.valid_to.is_(None),  # ochiq narx
    )
    # Deterministik: valid_from bo'yicha eng yangi, lekin FAQAT segment bo'yicha
    stmt = stmt.order_by(ProductPrice.valid_from.desc()).limit(1)
    result = await db.execute(stmt)
    price_row = result.scalar_one_or_none()

    return price_row.price if price_row else None


# ─── Scope tekshiruvi ─────────────────────────────────────────────────────────


async def _check_order_access(
    db: AsyncSession,
    order: Order,
    user: AppUser,
) -> None:
    """
    IDOR himoya: foydalanuvchi berilgan buyurtmaga kirish huquqini tekshiradi.

    - administrator/accountant: barcha buyurtmalar (branch_id filtr ixtiyoriy).
    - agent: faqat o'z do'konlari buyurtmalari.
    - store: faqat o'z do'koni buyurtmalari.
    - Ruxsatsiz → AppError("orders.order_not_found", 404).
    """
    role = user.role

    if role in ("administrator", "accountant"):
        if user.branch_id is not None and order.branch_id is not None:
            if order.branch_id != user.branch_id:
                raise AppError("orders.order_not_found", status_code=404)
        return

    if role == "agent":
        # Agent o'z do'konlari buyurtmalarini ko'radi
        allowed_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        stmt = select(Store.id).where(
            Store.id == order.store_id,
            or_(
                Store.agent_id == user.id,
                Store.id.in_(allowed_subq),
            ),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("orders.order_not_found", status_code=404)
        return

    if role == "store":
        # Do'kon faqat o'z do'koni
        stmt = select(Store.id).where(
            Store.id == order.store_id,
            Store.user_id == user.id,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("orders.order_not_found", status_code=404)
        return

    # Boshqa rollar (courier) — buyurtma ko'rish ruxsati yo'q
    raise AppError("orders.order_not_found", status_code=404)


async def _check_store_access_for_create(
    db: AsyncSession,
    store_id: uuid.UUID,
    user: AppUser,
) -> None:
    """
    Yaratish uchun do'konga kirish huquqini tekshiradi.
    agent faqat o'z do'konlari uchun buyurtma yaratadi.
    administrator istalgan do'kon uchun.
    """
    role = user.role

    if role in ("administrator", "accountant"):
        return  # Har qanday do'kon uchun

    if role == "agent":
        allowed_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        stmt = select(Store.id).where(
            Store.id == store_id,
            Store.deleted_at.is_(None),
            or_(
                Store.agent_id == user.id,
                Store.id.in_(allowed_subq),
            ),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("orders.order_not_found", status_code=404)
        return

    if role == "store":
        raise AppError("rbac.permission_denied", status_code=403, params={
            "module": "orders", "action": "create", "role": role,
        })

    raise AppError("rbac.permission_denied", status_code=403, params={
        "module": "orders", "action": "create", "role": role,
    })


# ─── create_order ─────────────────────────────────────────────────────────────


async def create_order(
    db: AsyncSession,
    data: OrderCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> Order:
    """
    Yangi buyurtma yaratadi — ATOMIK tranzaksiya.

    NARX XAVFSIZLIGI:
      Klient unit_price/segment_id/discount bera olmaydi (schema darajasida olib tashlangan).
      Narx FAQAT do'kon segmenti (Store.segment_id) bo'yicha katalogdan olinadi.
      Segment narxi topilmasa → AppError("orders.no_price", 422).

    ATOMIKLIK MEXANIZMI:
      Bu funksiya caller (router endpoint) tomonidan get_db() sessiyasi bilan
      chaqiriladi. get_db() request oxirida BITTA commit qiladi.
      Bu funksiya faqat flush() qiladi — commit qilmaydi.
      Xato bo'lsa get_db() rollback() chaqiradi → barcha yozuvlar bekor qilinadi.

    IDEMPOTENTLIK:
      Redis kaliti: {actor_id}:{client_uuid} — aktor-mahalliy.
      IntegrityError ushlanadi → mavjud buyurtma qaytariladi (graceful).
      Boshqa aktor bir xil client_uuid ishlatsa → 409 idempotency_conflict.

    Jarayon:
      1. client_uuid idempotentlik tekshiruvi (Redis SET NX + DB unique).
      2. Do'kon mavjudligi + RBAC scope tekshiruvi.
      3. Do'kon segmenti (server tomonidan) olish.
      4. Har qator uchun mahsulot mavjudligi + narx (segment bo'yicha) olish.
      5. Order + OrderLine INSERT.
      6. Har qator uchun stock chiqimi (_record_movement_tx, LOCK→check→INSERT).
         Qoldiq yetmasa → AppError → rollback.
      7. LedgerEntry debit (_record_entry_tx).
      8. Audit + Outbox.
      9. Redis idempotentlik kalitini saqlash.

    Boshlang'ich status: "confirmed"
      Sabab: DoD bo'yicha yaratishda atomik stock chiqimi bo'ladi.

    Raises:
        AppError("orders.empty_lines", 422): qatorlar bo'sh.
        AppError("orders.product_not_found", 404): mahsulot topilmasa.
        AppError("customers.store_not_found", 404): do'kon topilmasa.
        AppError("orders.no_price", 422): segment narxi topilmasa.
        AppError("orders.insufficient_stock", 409): qoldiq yetmasa.
        AppError("orders.idempotency_conflict", 409): boshqa aktor bir xil client_uuid.
    """
    # ── 1. client_uuid idempotentlik ──────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.store_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = (
                    select(Order)
                    .options(selectinload(Order.lines))
                    .where(Order.id == uuid.UUID(cached_id))
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_order: idem_key=%s yozuv topilmadi, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_order: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r).",
                idem_key, exc,
            )
            idem_key = None

    # ── 2. Bo'sh lines tekshiruvi ─────────────────────────────────────────
    if not data.lines:
        raise AppError("orders.empty_lines", status_code=422)

    # ── 3. Do'kon mavjudligi (enterprise filtr bilan) ─────────────────────
    store_stmt = select(Store).where(
        Store.id == data.store_id,
        Store.deleted_at.is_(None),
    )
    store_stmt = apply_enterprise_filter(store_stmt, enterprise_id, Store.enterprise_id)
    store_result = await db.execute(store_stmt)
    store = store_result.scalar_one_or_none()
    if store is None:
        raise AppError("customers.store_not_found", status_code=404)

    # ── 4. RBAC scope: foydalanuvchi bu do'kon uchun buyurtma yarata oladimi?
    if user is not None:
        await _check_store_access_for_create(db, data.store_id, user)

    # ── 5. Do'kon segmenti — server tomonidan (HIGH: klient segment_id bera olmaydi)
    store_segment_id: uuid.UUID | None = store.segment_id

    # ── 6. Har qator uchun mahsulot + narx tekshiruvi ─────────────────────
    warehouse_id = data.warehouse_id or _get_default_warehouse()

    # (line_in, unit_price, line_total, segment_id_used, server_discount)
    resolved_lines: list[tuple[OrderLineIn, Decimal, Decimal, uuid.UUID | None, Decimal]] = []

    for line_in in data.lines:
        # Mahsulot mavjudligi
        prod_stmt = select(Product).where(
            Product.id == line_in.product_id,
            Product.is_active.is_(True),
        )
        prod_result = await db.execute(prod_stmt)
        product = prod_result.scalar_one_or_none()
        if product is None:
            raise AppError("orders.product_not_found", status_code=404)

        # Narx: FAQAT server tomonida, do'kon segmenti bo'yicha (CRITICAL)
        if store_segment_id is None:
            # Do'konda segment yo'q — narx topib bo'lmaydi
            raise AppError(
                "orders.no_price",
                status_code=422,
                params={},
            )

        cat_price = await _get_product_price(db, line_in.product_id, store_segment_id)
        if cat_price is None:
            raise AppError(
                "orders.no_price",
                status_code=422,
                params={},
            )
        unit_price = cat_price

        # SERVER-AVTORITAR chegirma: promo servisidan hisoblash (T25).
        # Klient discount bera olmaydi — OrderLineIn sxemasida discount maydoni yo'q.
        # Mos promo yo'q → Decimal("0") (mavjud order testlari buzilmaydi).
        # Import shu yerda (modular monolit: orders → promo servis interfeysi orqali)
        from app.modules.promo.service import compute_line_discount  # noqa: PLC0415
        server_discount = await compute_line_discount(
            db,
            product_id=line_in.product_id,
            segment_id=store_segment_id,
            qty=line_in.qty,
            unit_price=unit_price,
            enterprise_id=enterprise_id,
        )

        line_total = (unit_price * line_in.qty - server_discount).quantize(Decimal("0.01"))
        # line_total manfiy bo'lmasligi kerak
        if line_total < Decimal("0"):
            line_total = Decimal("0.00")

        resolved_lines.append((line_in, unit_price, line_total, store_segment_id, server_discount))

    # ── 7. total_amount hisoblash ─────────────────────────────────────────
    total_amount = sum(lt for _, _, lt, _, _ in resolved_lines)
    total_amount = Decimal(str(total_amount)).quantize(Decimal("0.01"))

    # ── 8. Order INSERT ───────────────────────────────────────────────────
    order_id = uuid7()
    order = Order(
        id=order_id,
        store_id=data.store_id,
        agent_id=actor_id if (user is not None and user.role == "agent") else None,
        mode=data.mode,
        status="confirmed",
        total_amount=total_amount,
        currency=data.currency,
        ordered_at=_now(),
        client_uuid=data.client_uuid,
        branch_id=store.branch_id,
        warehouse_id=warehouse_id,
        version=1,
        created_at=_now(),
        updated_at=_now(),
        enterprise_id=enterprise_id,  # MT2: server-authoritative
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError as exc:
        # (store_id, client_uuid) dublikati — boshqa sessiya allaqachon bu yozuvni yaratgan
        await db.rollback()
        # Mavjud buyurtmani AYNI store_id + client_uuid bo'yicha qidiramiz
        # (faqat client_uuid bo'yicha qidirish → MultipleResultsFound va cross-store xavfi)
        if data.client_uuid is not None:
            existing_stmt = (
                select(Order)
                .options(selectinload(Order.lines))
                .where(
                    Order.store_id == data.store_id,
                    Order.client_uuid == data.client_uuid,
                )
            )
            existing_result = await db.execute(existing_stmt)
            existing_order = existing_result.scalar_one_or_none()
            if existing_order is not None:
                # Bir xil aktor (agent_id mos) yoki admin/tizim so'rovi → idempotent qaytarish
                # actor_id is None bo'lsa ham store_id tekshiruvi yuqorida o'tdi —
                # boshqa do'kon buyurtmasi hech qachon tushib qolmaydi (store_id filtr bor)
                if (
                    existing_order.agent_id == actor_id
                    or existing_order.agent_id is None
                    or actor_id is None
                ):
                    return existing_order
                # Bir xil store+client_uuid lekin boshqa aktor → 409 (DoS himoyasi)
                raise AppError("orders.idempotency_conflict", status_code=409) from exc
        raise AppError("orders.idempotency_conflict", status_code=409) from exc

    # ── 9. OrderLine INSERT ───────────────────────────────────────────────
    for line_in, unit_price, line_total, seg_id, server_discount in resolved_lines:
        ol = OrderLine(
            order_id=order.id,
            product_id=line_in.product_id,
            qty=line_in.qty,
            unit_price=unit_price,
            segment_id=seg_id,
            discount=server_discount,
            line_total=line_total,
        )
        db.add(ol)
    await db.flush()

    # ── 10. Stock chiqimi (atomik — bir sessiyada) ─────────────────────────
    # Qoldiq yetmasa → AppError → get_db() rollback() → butun tranzaksiya bekor
    for line_in, _, _, _, _ in resolved_lines:
        await _record_movement_tx(
            db=db,
            product_id=line_in.product_id,
            warehouse_id=warehouse_id,
            qty=line_in.qty,
            actor_id=actor_id,
            ref_type="order",
            ref_id=order.id,
            movement_type="out",
        )

    # ── 11. LedgerEntry debit (do'kon qarzi) ─────────────────────────────
    if total_amount > Decimal("0"):
        await _record_entry_tx(
            db=db,
            store_id=data.store_id,
            amount=total_amount,
            currency=data.currency,
            actor_id=actor_id,
            ref_type="order",
            ref_id=order.id,
            entry_type="debit",
        )

    # ── 12. Audit + Outbox ────────────────────────────────────────────────
    after_payload = {
        "id": str(order.id),
        "store_id": str(data.store_id),
        "mode": data.mode,
        "status": "confirmed",
        "total_amount": str(total_amount),
        "currency": data.currency,
        "lines_count": len(resolved_lines),
    }
    await _write_audit(
        db, actor_id, "create", "order", str(order.id), after=after_payload,
    )
    await _write_outbox(
        db, "order", str(order.id), "order.created", after_payload,
    )

    # ── 13. Redis idempotentlik kaliti ────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(order.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_order: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    # lines ni selectinload bilan yuklash (N+1 oldini olish)
    await db.refresh(order, ["lines"])
    return order


# ─── update_status ────────────────────────────────────────────────────────────


async def update_status(
    db: AsyncSession,
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Order:
    """
    Buyurtma holatini o'zgartiradi — server-avtoritar holat mashinasi.

    Qonuniy o'tishlar (ADR §3.5):
      draft → confirmed, canceled
      confirmed → packed, canceled
      packed → delivering, canceled
      delivering → delivered, canceled
      delivered → (hech qaerga, TERMINAL)
      canceled → (hech qaerga, TERMINAL)

    KOMPENSATSIYA (HIGH SRE):
      confirmed/packed/delivering → canceled bo'lganda BITTA ACID tranzaksiyada:
        - Har qator uchun teskari ombor harakati (type=in — qaytim).
        - Teskari ledger (type=credit — qarzni qaytar).
      Bu pul/qoldiq izchilligini kafolatlaydi.

    version optimistik lock: berilgan version != joriy version → AppError.

    Raises:
        AppError("orders.order_not_found", 404): buyurtma topilmasa.
        AppError("orders.invalid_transition", 422): noqonuniy o'tish.
        AppError("orders.version_conflict", 409): versiya mos kelmasa.
    """
    # Buyurtmani olish (lines bilan birga — kompensatsiya uchun kerak)
    stmt = (
        select(Order)
        .options(selectinload(Order.lines))
        .where(
            Order.id == order_id,
            Order.deleted_at.is_(None),
        )
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Order.enterprise_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise AppError("orders.order_not_found", status_code=404)

    # RBAC scope tekshiruvi
    if user is not None:
        await _check_order_access(db, order, user)

    # Version optimistik lock
    if order.version != data.version:
        raise AppError("orders.version_conflict", status_code=409)

    # Holat mashinasi tekshiruvi
    allowed_next = VALID_TRANSITIONS.get(order.status, set())
    if data.status not in allowed_next:
        raise AppError(
            "orders.invalid_transition",
            status_code=422,
            params={
                "from_status": order.status,
                "to_status": data.status,
            },
        )

    before_payload = {"status": order.status, "version": order.version}

    # KOMPENSATSIYA: confirmed/packed/delivering → canceled
    # Bu holatlar stock chiqimi va ledger debit yozilgan — qaytarilishi kerak.
    COMPENSABLE_STATUSES = {"confirmed", "packed", "delivering"}
    actor_id = user.id if user else None

    if data.status == "canceled" and order.status in COMPENSABLE_STATUSES:
        # Do'kon ombor ID ni aniqlash: order.warehouse_id (buyurtma yaratilganidagi ombor).
        # _get_default_warehouse() emas — kompensatsiya TO'G'RI omborga borishi kerak.
        warehouse_id = order.warehouse_id or _get_default_warehouse()

        # Har qator uchun teskari ombor harakati (in — qaytim)
        for line in order.lines:
            await _record_movement_tx(
                db=db,
                product_id=line.product_id,
                warehouse_id=warehouse_id,
                qty=line.qty,
                actor_id=actor_id,
                ref_type="order_cancel",
                ref_id=order.id,
                movement_type="in",
            )

        # Teskari ledger (credit — qarzni qaytar)
        if order.total_amount > Decimal("0"):
            await _record_entry_tx(
                db=db,
                store_id=order.store_id,
                amount=order.total_amount,
                currency=order.currency,
                actor_id=actor_id,
                ref_type="order_cancel",
                ref_id=order.id,
                entry_type="credit",
            )

    order.status = data.status
    order.version = order.version + 1
    order.updated_at = _now()
    await db.flush()

    # Audit + Outbox
    # store_id payload'ga qo'shiladi — agent/do'kon o'z buyurtmasi holat
    # o'zgarishini sinxronlay olishi uchun (_can_see_scoped_event store_id ishlatadi).
    after_payload = {
        "id": str(order.id),
        "store_id": str(order.store_id) if order.store_id else None,
        "status": data.status,
        "version": order.version,
    }
    await _write_audit(
        db, actor_id, "update_status", "order", str(order.id),
        before=before_payload, after=after_payload,
    )
    await _write_outbox(
        db, "order", str(order.id), "order.status_updated", after_payload,
    )

    await db.refresh(order, ["lines"])
    return order


# ─── get_order ────────────────────────────────────────────────────────────────


async def get_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Order:
    """
    Bitta buyurtmani qaytaradi.

    RBAC scope: foydalanuvchi ruxsatli buyurtmalardan tekshiriladi.
    Ruxsatsiz → AppError("orders.order_not_found", 404) (IDOR).
    """
    stmt = (
        select(Order)
        .options(selectinload(Order.lines))
        .where(
            Order.id == order_id,
            Order.deleted_at.is_(None),
        )
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Order.enterprise_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise AppError("orders.order_not_found", status_code=404)

    if user is not None:
        await _check_order_access(db, order, user)

    return order


# ─── list_orders ──────────────────────────────────────────────────────────────


async def list_orders(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Order], int]:
    """
    Paginated buyurtmalar ro'yxati.

    RBAC scope: foydalanuvchi roliga qarab filtr qo'llaniladi.
    - agent: faqat o'z do'konlari buyurtmalari.
    - store: faqat o'z do'koni buyurtmalari.
    - accountant/administrator: barcha (branch_id filtr ixtiyoriy).

    N+1 MUAMMOSI YO'Q: selectinload(Order.lines) orqali (MEDIUM #7).
    """
    conditions = [Order.deleted_at.is_(None)]

    # MT2: Enterprise izolyatsiyasi
    from sqlalchemy import and_ as _and
    if enterprise_id is not None:
        conditions.append(Order.enterprise_id == enterprise_id)

    # RBAC scope
    if user is not None:
        role = user.role

        if role == "agent":
            allowed_subq = (
                select(AgentStore.store_id)
                .where(AgentStore.agent_id == user.id)
                .scalar_subquery()
            )
            conditions.append(
                or_(
                    Order.store_id.in_(
                        select(Store.id).where(Store.agent_id == user.id)
                    ),
                    Order.store_id.in_(allowed_subq),
                )
            )

        elif role == "store":
            store_subq = (
                select(Store.id)
                .where(Store.user_id == user.id)
                .scalar_subquery()
            )
            conditions.append(Order.store_id.in_(store_subq))

        elif role in ("administrator", "accountant"):
            if user.branch_id is not None:
                conditions.append(
                    or_(
                        Order.branch_id == user.branch_id,
                        Order.branch_id.is_(None),
                    )
                )

    # Filtrlar
    if store_id is not None:
        conditions.append(Order.store_id == store_id)
    if agent_id is not None:
        conditions.append(Order.agent_id == agent_id)
    if status is not None:
        conditions.append(Order.status == status)
    if date_from is not None:
        conditions.append(Order.ordered_at >= date_from)
    if date_to is not None:
        conditions.append(Order.ordered_at <= date_to)

    # Count
    count_stmt = select(func.count()).select_from(Order)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List — selectinload bilan N+1 oldini olish (MEDIUM #7)
    stmt = (
        select(Order)
        .options(selectinload(Order.lines))
        .order_by(Order.ordered_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── T12: Shablon servisi ─────────────────────────────────────────────────────


async def _check_template_access(
    db: AsyncSession,
    template: OrderTemplate,
    user: AppUser,
) -> None:
    """
    IDOR himoya: foydalanuvchi berilgan shablonga kirish huquqini tekshiradi.

    - administrator/accountant: barcha shablonlar.
    - agent: faqat o'z do'konlari shablonlari.
    - store: faqat o'z do'koni shablonlari.
    - Ruxsatsiz → AppError("orders.template_not_found", 404).
    """
    role = user.role

    if role in ("administrator", "accountant"):
        if user.branch_id is not None and template.branch_id is not None:
            if template.branch_id != user.branch_id:
                raise AppError("orders.template_not_found", status_code=404)
        return

    if role == "agent":
        allowed_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        stmt = select(Store.id).where(
            Store.id == template.store_id,
            Store.deleted_at.is_(None),
            or_(
                Store.agent_id == user.id,
                Store.id.in_(allowed_subq),
            ),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("orders.template_not_found", status_code=404)
        return

    if role == "store":
        stmt = select(Store.id).where(
            Store.id == template.store_id,
            Store.user_id == user.id,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("orders.template_not_found", status_code=404)
        return

    raise AppError("orders.template_not_found", status_code=404)


async def create_template(
    db: AsyncSession,
    data: OrderTemplateCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> OrderTemplate:
    """
    Yangi buyurtma shabloni yaratadi.

    MUHIM: shablonda narx saqlanmaydi — faqat product_id + qty.
    Narx apply_template() paytida katalogdan olinadi (server-avtoritar).

    RBAC scope: agent o'z do'konlari uchun shablon yaratadi.
    """
    # Bo'sh lines tekshiruvi
    if not data.lines:
        raise AppError("orders.empty_template", status_code=422)

    # Do'kon mavjudligi (enterprise filtr bilan)
    store_stmt = select(Store).where(
        Store.id == data.store_id,
        Store.deleted_at.is_(None),
    )
    store_stmt = apply_enterprise_filter(store_stmt, enterprise_id, Store.enterprise_id)
    store_result = await db.execute(store_stmt)
    store = store_result.scalar_one_or_none()
    if store is None:
        raise AppError("customers.store_not_found", status_code=404)

    # RBAC scope: foydalanuvchi bu do'kon uchun shablon yarata oladimi?
    if user is not None:
        await _check_store_access_for_create(db, data.store_id, user)

    template = OrderTemplate(
        store_id=data.store_id,
        name=data.name,
        created_by=actor_id,
        branch_id=store.branch_id,
        enterprise_id=enterprise_id,  # MT2: server-authoritative
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(template)
    await db.flush()

    for line_in in data.lines:
        tl = OrderTemplateLine(
            template_id=template.id,
            product_id=line_in.product_id,
            qty=line_in.qty,
        )
        db.add(tl)
    await db.flush()

    # Audit + Outbox
    after_payload = {
        "id": str(template.id),
        "store_id": str(data.store_id),
        "name": data.name,
        "lines_count": len(data.lines),
    }
    await _write_audit(
        db, actor_id, "create", "order_template", str(template.id), after=after_payload,
    )
    await _write_outbox(
        db, "order_template", str(template.id), "order_template.created", after_payload,
    )

    await db.refresh(template, ["lines"])
    return template


async def list_templates(
    db: AsyncSession,
    *,
    store_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[OrderTemplate], int]:
    """
    Paginated shablonlar ro'yxati.

    RBAC scope: foydalanuvchi roliga qarab filtr qo'llaniladi.
    Soft delete filtrlangan (deleted_at IS NULL).
    """
    conditions = [OrderTemplate.deleted_at.is_(None)]

    # MT2: Enterprise izolyatsiyasi
    if enterprise_id is not None:
        conditions.append(OrderTemplate.enterprise_id == enterprise_id)

    if user is not None:
        role = user.role

        if role == "agent":
            allowed_subq = (
                select(AgentStore.store_id)
                .where(AgentStore.agent_id == user.id)
                .scalar_subquery()
            )
            conditions.append(
                or_(
                    OrderTemplate.store_id.in_(
                        select(Store.id).where(Store.agent_id == user.id)
                    ),
                    OrderTemplate.store_id.in_(allowed_subq),
                )
            )

        elif role == "store":
            store_subq = (
                select(Store.id)
                .where(Store.user_id == user.id)
                .scalar_subquery()
            )
            conditions.append(OrderTemplate.store_id.in_(store_subq))

        elif role in ("administrator", "accountant"):
            if user.branch_id is not None:
                conditions.append(
                    or_(
                        OrderTemplate.branch_id == user.branch_id,
                        OrderTemplate.branch_id.is_(None),
                    )
                )

    if store_id is not None:
        conditions.append(OrderTemplate.store_id == store_id)

    count_stmt = select(func.count()).select_from(OrderTemplate)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = (
        select(OrderTemplate)
        .options(selectinload(OrderTemplate.lines))
        .order_by(OrderTemplate.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def get_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> OrderTemplate:
    """
    Bitta shablonni qaytaradi.

    RBAC scope: foydalanuvchi ruxsatli shablonlardan tekshiriladi.
    Ruxsatsiz → AppError("orders.template_not_found", 404) (IDOR).
    """
    stmt = (
        select(OrderTemplate)
        .options(selectinload(OrderTemplate.lines))
        .where(
            OrderTemplate.id == template_id,
            OrderTemplate.deleted_at.is_(None),
        )
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, OrderTemplate.enterprise_id)
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise AppError("orders.template_not_found", status_code=404)

    if user is not None:
        await _check_template_access(db, template, user)

    return template


async def delete_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    user: AppUser | None = None,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """
    Shablonni soft delete qiladi.

    RBAC scope: foydalanuvchi ruxsatli shablonlardan tekshiriladi.
    """
    stmt = (
        select(OrderTemplate)
        .where(
            OrderTemplate.id == template_id,
            OrderTemplate.deleted_at.is_(None),
        )
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, OrderTemplate.enterprise_id)
    result = await db.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise AppError("orders.template_not_found", status_code=404)

    if user is not None:
        await _check_template_access(db, template, user)

    before_payload = {"id": str(template.id), "deleted_at": None}
    template.deleted_at = _now()
    await db.flush()

    await _write_audit(
        db, actor_id, "delete", "order_template", str(template.id), before=before_payload,
    )
    await _write_outbox(
        db, "order_template", str(template.id), "order_template.deleted",
        {"id": str(template.id)},
    )


async def apply_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    apply_data: ApplyTemplateIn,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> Order:
    """
    Shablon qatorlaridan yangi buyurtma yaratadi.

    MUHIM — NARX XAVFSIZLIGI:
      Bu funksiya mavjud create_order() ni QAYTA ISHLATADI.
      Narx server-avtoritar + atomik ombor/qarz ta'minoti create_order() ichida.
      Shablonda narx YO'Q — narx faqat create_order() ichida katalogdan olinadi.
      Shablon O'ZGARMAYDI — faqat yangi buyurtma yaratiladi.

    Jarayon:
      1. Shablonni RBAC scope bilan topadi.
      2. Shablon qatorlaridan OrderCreate yasaydi.
      3. Mavjud create_order() ni chaqiradi (barcha atomiklik, idempotentlik, narx
         xavfsizligi create_order() da ta'minlangan — dublikat qilinmaydi).
      4. Yangi buyurtmani qaytaradi.

    Raises:
        AppError("orders.template_not_found", 404): shablon topilmasa.
        AppError("orders.empty_template", 422): shablon qatorlari bo'sh.
        (create_order() xatolari: orders.insufficient_stock, orders.no_price va h.k.)
    """
    # 1. Shablonni topish (RBAC scope + enterprise bilan)
    template_stmt = (
        select(OrderTemplate)
        .options(selectinload(OrderTemplate.lines))
        .where(
            OrderTemplate.id == template_id,
            OrderTemplate.deleted_at.is_(None),
        )
    )
    template_stmt = apply_enterprise_filter(template_stmt, enterprise_id, OrderTemplate.enterprise_id)
    result = await db.execute(template_stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise AppError("orders.template_not_found", status_code=404)

    # RBAC scope tekshiruvi
    if user is not None:
        await _check_template_access(db, template, user)

    # 2. Bo'sh qatorlar tekshiruvi
    if not template.lines:
        raise AppError("orders.empty_template", status_code=422)

    # 3. Shablon qatorlaridan OrderCreate yasash
    order_lines = [
        OrderLineIn(product_id=line.product_id, qty=line.qty)
        for line in template.lines
    ]

    order_data = OrderCreate(
        store_id=template.store_id,
        mode=apply_data.mode,
        lines=order_lines,
        client_uuid=apply_data.client_uuid,
        currency=apply_data.currency,
    )

    # 4. Mavjud create_order() ni QAYTA ISHLATISH
    # Narx server-avtoritar, atomik ombor/qarz, idempotentlik — hammasi create_order() da.
    # Shablon O'ZGARMAYDI.
    order = await create_order(
        db=db,
        data=order_data,
        actor_id=actor_id,
        user=user,
        redis=redis,
        enterprise_id=enterprise_id,
    )

    # Audit: shablon orqali buyurtma yaratilgani haqida
    await _write_audit(
        db, actor_id, "apply_template", "order_template", str(template.id),
        after={"order_id": str(order.id), "template_id": str(template.id)},
    )

    return order
