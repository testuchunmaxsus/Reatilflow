"""
AI Tahlil servis qatlami — Faza 4.

Funksiyalar:
  overview(db, enterprise_id, from_dt, to_dt)            → OverviewOut
  contracted_stores(db, enterprise_id)                   → ContractedStoresOut
  geo_velocity(db, enterprise_id, from_dt, to_dt)        → GeoVelocityOut
  expiry_report(db, enterprise_id, within_days)          → ExpiryReportOut
  product_ranking(db, enterprise_id, from_dt, to_dt, order, limit) → ProductRankingOut
  recommendations(db, enterprise_id, from_dt, to_dt)    → RecommendationsOut

MT (xavfsizlik yadrosi, har funksiyada majburiy):
  1. Mahsulot filtri: Product.enterprise_id == enterprise_id
  2. Do'kon filtri:   Contract.supplier_enterprise_id == enterprise_id
                     AND valid_to >= today

MUHIM QOIDALAR:
  - Barcha funksiyalar read-only (SELECT faqat) — yozuv TAQIQLANGAN.
  - Moliyaviy emas → read replica sessiyasi (non-financial, ADR §3.4).
  - Decimal moliyaviy aniqlik (float emas).
  - SQL agregatsiya DB darajasida: func.sum, func.count, func.coalesce.
  - superadmin (enterprise_id=None) → bo'sh natija qaytaradi (korxona-egasi paneli).
  - CONTRACT_EXPIRING_DAYS konstantasi import qilinadi (30 kun — yagona manba).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.catalog import Product
from app.models.contract import CONTRACT_EXPIRING_DAYS, Contract
from app.models.pos import PosSale, PosSaleLine
from app.models.store import Store
from app.models.store_inventory import StoreInventory
from app.modules.analytics.schemas import (
    ContractStatusCounts,
    ContractedStoreItem,
    ContractedStoresOut,
    ExpiryItem,
    ExpiryReportOut,
    GeoVelocityItem,
    GeoVelocityOut,
    OverviewOut,
    ProductRankingItem,
    ProductRankingOut,
    RecommendationItem,
    RecommendationsOut,
)

logger = logging.getLogger(__name__)

# Default davr (kunlar) — from/to berilmasa
DEFAULT_PERIOD_DAYS: int = 30

# Expiry jiddiy chegarasi (kunlar)
EXPIRY_URGENT_DAYS: int = 7

# Reytinglash default chegarasi
DEFAULT_RANKING_LIMIT: int = 10


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now_utc().date()


def _default_period(
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> tuple[datetime, datetime]:
    """from/to berilmasa oxirgi DEFAULT_PERIOD_DAYS kunni qaytaradi."""
    now = _now_utc()
    if to_dt is None:
        to_dt = now
    if from_dt is None:
        from_dt = now - timedelta(days=DEFAULT_PERIOD_DAYS)
    return from_dt, to_dt


def _period_days(from_dt: datetime, to_dt: datetime) -> int:
    """Davr davomiyligi (kun, minimal 1)."""
    delta = (to_dt - from_dt).days
    return max(delta, 1)


async def _get_contracted_store_ids(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
    today: date | None = None,
) -> list[uuid.UUID]:
    """
    Korxona bilan shartnoma qilgan do'konlar IDs (aktiv + tugayotgan).

    Shartnoma mezonlari:
      Contract.supplier_enterprise_id == enterprise_id
      AND Contract.valid_to >= today

    stats._get_agent_store_ids naqshi.
    """
    if today is None:
        today = _today()

    stmt = (
        select(Contract.store_id)
        .where(
            Contract.supplier_enterprise_id == enterprise_id,
            Contract.valid_to >= today,
        )
        .distinct()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_own_product_ids(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Korxonaning o'z mahsulotlari IDs (Product.enterprise_id == me)."""
    stmt = select(Product.id).where(Product.enterprise_id == enterprise_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_all_contracted_store_data(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
    today: date | None = None,
) -> list:
    """
    Shartnomadagi do'konlar: store_id, valid_to (status hisoblash uchun).

    (store_id, valid_to) juftliklari ro'yxati qaytaradi.
    Har do'kon uchun ENG UZOQ valid_to olinadi (bir do'konda bir nechta shartnoma bo'lishi mumkin).
    """
    if today is None:
        today = _today()

    stmt = (
        select(
            Contract.store_id,
            func.max(Contract.valid_to).label("valid_to"),
        )
        .where(
            Contract.supplier_enterprise_id == enterprise_id,
            Contract.valid_to >= today,
        )
        .group_by(Contract.store_id)
    )
    result = await db.execute(stmt)
    return list(result.all())


def _contract_status(valid_to: date, today: date) -> str:
    """valid_to dan shartnoma statusini hisoblaydi (CONTRACT_EXPIRING_DAYS dan foydalanadi)."""
    if valid_to < today:
        return "expired"
    delta = (valid_to - today).days
    if delta <= CONTRACT_EXPIRING_DAYS:
        return "expiring"
    return "active"


def _expiry_severity(days_left: int) -> str:
    """Expiry jiddiligi: muddati o'tgan, shoshilinch, ogohlantirish."""
    if days_left < 0:
        return "expired"
    if days_left <= EXPIRY_URGENT_DAYS:
        return "urgent"
    return "warning"


def _to_decimal(val) -> Decimal:
    """DB dan kelgan qiymatni Decimal ga aylantiradi (NULL → 0)."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


# ─── 1. Overview (KPI kartalar) ───────────────────────────────────────────────


async def overview(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> OverviewOut:
    """
    Korxona uchun KPI kartalar.

    superadmin (enterprise_id=None) → bo'sh natija.
    """
    if enterprise_id is None:
        return OverviewOut(
            contracted_store_count=0,
            contract_status=ContractStatusCounts(active=0, expiring=0, expired=0),
            sold_qty_total=Decimal("0"),
            revenue_total=Decimal("0"),
            expiry_risk_count=0,
            period_from=from_dt,
            period_to=to_dt,
        )

    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="analytics.invalid_period", status_code=422)

    from_dt, to_dt = _default_period(from_dt, to_dt)
    today = _today()

    # 1. Shartnomadagi do'konlar soni + holat
    contract_rows = await _get_all_contracted_store_data(db, enterprise_id, today)
    store_ids = [row.store_id for row in contract_rows]

    contracted_store_count = len(store_ids)
    status_active = status_expiring = status_expired = 0
    for row in contract_rows:
        st = _contract_status(row.valid_to, today)
        if st == "active":
            status_active += 1
        elif st == "expiring":
            status_expiring += 1
        else:
            status_expired += 1

    if not store_ids:
        return OverviewOut(
            contracted_store_count=0,
            contract_status=ContractStatusCounts(
                active=status_active,
                expiring=status_expiring,
                expired=status_expired,
            ),
            sold_qty_total=Decimal("0"),
            revenue_total=Decimal("0"),
            expiry_risk_count=0,
            period_from=from_dt,
            period_to=to_dt,
        )

    # 2. Mahsulot IDs
    product_ids = await _get_own_product_ids(db, enterprise_id)
    if not product_ids:
        return OverviewOut(
            contracted_store_count=contracted_store_count,
            contract_status=ContractStatusCounts(
                active=status_active,
                expiring=status_expiring,
                expired=status_expired,
            ),
            sold_qty_total=Decimal("0"),
            revenue_total=Decimal("0"),
            expiry_risk_count=0,
            period_from=from_dt,
            period_to=to_dt,
        )

    # 3. Jami sotuv (PosSaleLine × PosSale)
    sales_stmt = (
        select(
            func.coalesce(func.sum(PosSaleLine.qty), Decimal("0")).label("sold_qty"),
            func.coalesce(func.sum(PosSaleLine.line_total), Decimal("0")).label("revenue"),
        )
        .join(PosSale, PosSale.id == PosSaleLine.sale_id)
        .where(
            PosSale.status == "completed",
            PosSale.store_id.in_(store_ids),
            PosSaleLine.product_id.in_(product_ids),
            PosSale.created_at >= from_dt,
            PosSale.created_at <= to_dt,
        )
    )
    sales_result = await db.execute(sales_stmt)
    sales_row = sales_result.one()
    sold_qty_total = _to_decimal(sales_row.sold_qty)
    revenue_total = _to_decimal(sales_row.revenue)

    # 4. Expiry risk (7 kun ichida, qty>0)
    expiry_deadline = today + timedelta(days=EXPIRY_URGENT_DAYS)
    expiry_stmt = (
        select(func.count().label("cnt"))
        .where(
            StoreInventory.store_id.in_(store_ids),
            StoreInventory.product_id.in_(product_ids),
            StoreInventory.qty > 0,
            StoreInventory.expiry_date.isnot(None),
            StoreInventory.expiry_date <= expiry_deadline,
        )
    )
    expiry_result = await db.execute(expiry_stmt)
    expiry_risk_count = expiry_result.scalar() or 0

    return OverviewOut(
        contracted_store_count=contracted_store_count,
        contract_status=ContractStatusCounts(
            active=status_active,
            expiring=status_expiring,
            expired=status_expired,
        ),
        sold_qty_total=sold_qty_total,
        revenue_total=revenue_total,
        expiry_risk_count=expiry_risk_count,
        period_from=from_dt,
        period_to=to_dt,
    )


# ─── 2. Contracted Stores ─────────────────────────────────────────────────────


async def contracted_stores(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
) -> ContractedStoresOut:
    """
    Shartnoma qilgan do'konlar ro'yxati + holat + inventar + sotuv.

    superadmin (enterprise_id=None) → bo'sh ro'yxat.
    """
    if enterprise_id is None:
        return ContractedStoresOut(stores=[], total=0)

    today = _today()
    now = _now_utc()
    from_30d = now - timedelta(days=30)

    # Do'konlar + shartnoma
    contract_rows = await _get_all_contracted_store_data(db, enterprise_id, today)
    store_ids = [row.store_id for row in contract_rows]
    valid_to_map = {row.store_id: row.valid_to for row in contract_rows}

    if not store_ids:
        return ContractedStoresOut(stores=[], total=0)

    # Mahsulot IDs
    product_ids = await _get_own_product_ids(db, enterprise_id)

    # Do'kon ma'lumotlari (GPS, manzil, nom)
    store_stmt = (
        select(
            Store.id,
            Store.name,
            Store.gps_lat,
            Store.gps_lng,
            Store.address,
        )
        .where(Store.id.in_(store_ids))
    )
    store_result = await db.execute(store_stmt)
    store_map = {
        row.id: row for row in store_result.all()
    }

    # Inventar qoldig'i (mening mahsulotlarim)
    if product_ids:
        inv_stmt = (
            select(
                StoreInventory.store_id,
                func.coalesce(func.sum(StoreInventory.qty), Decimal("0")).label("inv_qty"),
            )
            .where(
                StoreInventory.store_id.in_(store_ids),
                StoreInventory.product_id.in_(product_ids),
                StoreInventory.qty > 0,
            )
            .group_by(StoreInventory.store_id)
        )
        inv_result = await db.execute(inv_stmt)
        inv_map: dict[uuid.UUID, Decimal] = {
            row.store_id: _to_decimal(row.inv_qty)
            for row in inv_result.all()
        }

        # So'nggi 30 kun sotilgan miqdor
        sold_stmt = (
            select(
                PosSale.store_id,
                func.coalesce(func.sum(PosSaleLine.qty), Decimal("0")).label("sold_qty"),
            )
            .join(PosSaleLine, PosSale.id == PosSaleLine.sale_id)
            .where(
                PosSale.status == "completed",
                PosSale.store_id.in_(store_ids),
                PosSaleLine.product_id.in_(product_ids),
                PosSale.created_at >= from_30d,
            )
            .group_by(PosSale.store_id)
        )
        sold_result = await db.execute(sold_stmt)
        sold_map: dict[uuid.UUID, Decimal] = {
            row.store_id: _to_decimal(row.sold_qty)
            for row in sold_result.all()
        }
    else:
        inv_map = {}
        sold_map = {}

    # Natija yig'ish
    items: list[ContractedStoreItem] = []
    for sid in store_ids:
        store_row = store_map.get(sid)
        if store_row is None:
            continue
        vt = valid_to_map[sid]
        items.append(
            ContractedStoreItem(
                store_id=sid,
                store_name=store_row.name,
                contract_status=_contract_status(vt, today),
                valid_to=vt,
                inventory_qty=inv_map.get(sid, Decimal("0")),
                sold_qty_30d=sold_map.get(sid, Decimal("0")),
                gps_lat=_to_decimal(store_row.gps_lat) if store_row.gps_lat is not None else None,
                gps_lng=_to_decimal(store_row.gps_lng) if store_row.gps_lng is not None else None,
                address=store_row.address,
            )
        )

    return ContractedStoresOut(stores=items, total=len(items))


# ─── 3. Geo Velocity ──────────────────────────────────────────────────────────


async def geo_velocity(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> GeoVelocityOut:
    """
    Geografik savdo tezligi: do'kon bo'yicha mening mahsulotlarimni sotuv tezligi.

    velocity_per_day = sold_qty / period_days.

    superadmin (enterprise_id=None) → bo'sh natija.
    """
    if enterprise_id is None:
        from_dt, to_dt = _default_period(from_dt, to_dt)
        return GeoVelocityOut(items=[], period_from=from_dt, period_to=to_dt, period_days=DEFAULT_PERIOD_DAYS)

    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="analytics.invalid_period", status_code=422)

    from_dt, to_dt = _default_period(from_dt, to_dt)
    period_days = _period_days(from_dt, to_dt)

    store_ids = await _get_contracted_store_ids(db, enterprise_id)
    if not store_ids:
        return GeoVelocityOut(items=[], period_from=from_dt, period_to=to_dt, period_days=period_days)

    product_ids = await _get_own_product_ids(db, enterprise_id)
    if not product_ids:
        return GeoVelocityOut(items=[], period_from=from_dt, period_to=to_dt, period_days=period_days)

    stmt = (
        select(
            PosSale.store_id,
            Store.name.label("store_name"),
            Store.gps_lat,
            Store.gps_lng,
            Store.address,
            func.coalesce(func.sum(PosSaleLine.qty), Decimal("0")).label("sold_qty"),
            func.coalesce(func.sum(PosSaleLine.line_total), Decimal("0")).label("revenue"),
        )
        .join(PosSaleLine, PosSale.id == PosSaleLine.sale_id)
        .join(Store, Store.id == PosSale.store_id)
        .where(
            PosSale.status == "completed",
            PosSale.store_id.in_(store_ids),
            PosSaleLine.product_id.in_(product_ids),
            PosSale.created_at >= from_dt,
            PosSale.created_at <= to_dt,
        )
        .group_by(
            PosSale.store_id,
            Store.name,
            Store.gps_lat,
            Store.gps_lng,
            Store.address,
        )
        .order_by(func.sum(PosSaleLine.qty).desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    items: list[GeoVelocityItem] = []
    for row in rows:
        sold_qty = _to_decimal(row.sold_qty)
        velocity = sold_qty / Decimal(str(period_days))
        items.append(
            GeoVelocityItem(
                store_id=row.store_id,
                store_name=row.store_name,
                gps_lat=_to_decimal(row.gps_lat) if row.gps_lat is not None else None,
                gps_lng=_to_decimal(row.gps_lng) if row.gps_lng is not None else None,
                address=row.address,
                sold_qty=sold_qty,
                revenue=_to_decimal(row.revenue),
                velocity_per_day=velocity.quantize(Decimal("0.0001")),
            )
        )

    return GeoVelocityOut(items=items, period_from=from_dt, period_to=to_dt, period_days=period_days)


# ─── 4. Expiry Report ─────────────────────────────────────────────────────────


async def expiry_report(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    within_days: int = DEFAULT_PERIOD_DAYS,
) -> ExpiryReportOut:
    """
    Muddati o'tgan/o'tayotgan inventar partiyalari.

    within_days: Bu kun ichida muddati o'tayotgan partiyalar (default 30).
    Muddati allaqachon o'tganlar ham kiritiladi (days_left < 0).

    superadmin (enterprise_id=None) → bo'sh natija.
    """
    if enterprise_id is None:
        return ExpiryReportOut(items=[], total=0, within_days=within_days)

    today = _today()
    deadline = today + timedelta(days=within_days)

    store_ids = await _get_contracted_store_ids(db, enterprise_id)
    if not store_ids:
        return ExpiryReportOut(items=[], total=0, within_days=within_days)

    product_ids = await _get_own_product_ids(db, enterprise_id)
    if not product_ids:
        return ExpiryReportOut(items=[], total=0, within_days=within_days)

    stmt = (
        select(
            StoreInventory.id.label("inventory_id"),
            StoreInventory.store_id,
            Store.name.label("store_name"),
            StoreInventory.product_id,
            Product.name_uz.label("product_name"),
            StoreInventory.qty,
            StoreInventory.expiry_date,
        )
        .join(Store, Store.id == StoreInventory.store_id)
        .join(Product, Product.id == StoreInventory.product_id)
        .where(
            StoreInventory.store_id.in_(store_ids),
            StoreInventory.product_id.in_(product_ids),
            StoreInventory.qty > 0,
            StoreInventory.expiry_date.isnot(None),
            StoreInventory.expiry_date <= deadline,
        )
        .order_by(StoreInventory.expiry_date.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    items: list[ExpiryItem] = []
    for row in rows:
        days_left = (row.expiry_date - today).days
        items.append(
            ExpiryItem(
                inventory_id=row.inventory_id,
                store_id=row.store_id,
                store_name=row.store_name,
                product_id=row.product_id,
                product_name=row.product_name,
                qty=_to_decimal(row.qty),
                expiry_date=row.expiry_date,
                days_left=days_left,
                severity=_expiry_severity(days_left),
            )
        )

    return ExpiryReportOut(items=items, total=len(items), within_days=within_days)


# ─── 5. Product Ranking ───────────────────────────────────────────────────────


async def product_ranking(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    order: str = "top",
    limit: int = DEFAULT_RANKING_LIMIT,
) -> ProductRankingOut:
    """
    Eng ko'p/kam sotiladigan mahsulotlar.

    order='top'    → sold_qty DESC (eng ko'p)
    order='bottom' → sold_qty ASC (eng kam; 0-sotuvli ham kiritiladi)

    superadmin (enterprise_id=None) → bo'sh natija.
    """
    if enterprise_id is None:
        from_dt, to_dt = _default_period(from_dt, to_dt)
        return ProductRankingOut(items=[], order=order, period_from=from_dt, period_to=to_dt)

    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="analytics.invalid_period", status_code=422)

    if order not in ("top", "bottom"):
        raise AppError(message_key="analytics.invalid_order", status_code=422)

    from_dt, to_dt = _default_period(from_dt, to_dt)

    store_ids = await _get_contracted_store_ids(db, enterprise_id)
    product_ids = await _get_own_product_ids(db, enterprise_id)

    if not product_ids:
        return ProductRankingOut(items=[], order=order, period_from=from_dt, period_to=to_dt)

    if store_ids:
        # Sotilgan mahsulotlar (PosSaleLine orqali)
        stmt = (
            select(
                PosSaleLine.product_id,
                Product.name_uz.label("product_name"),
                func.coalesce(func.sum(PosSaleLine.qty), Decimal("0")).label("sold_qty"),
                func.coalesce(func.sum(PosSaleLine.line_total), Decimal("0")).label("revenue"),
                func.count(PosSale.store_id.distinct()).label("store_count"),
            )
            .join(PosSale, PosSale.id == PosSaleLine.sale_id)
            .join(Product, Product.id == PosSaleLine.product_id)
            .where(
                PosSale.status == "completed",
                PosSale.store_id.in_(store_ids),
                PosSaleLine.product_id.in_(product_ids),
                PosSale.created_at >= from_dt,
                PosSale.created_at <= to_dt,
            )
            .group_by(PosSaleLine.product_id, Product.name_uz)
        )

        if order == "top":
            stmt = stmt.order_by(func.sum(PosSaleLine.qty).desc())
        else:
            stmt = stmt.order_by(func.sum(PosSaleLine.qty).asc())

        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        sold_rows = result.all()

        # bottom uchun 0-sotuvli mahsulotlarni qo'shish
        # (bazada sotuv bo'lmagan mahsulotlar JOIN orqali tushib qoladi)
        if order == "bottom":
            sold_product_ids = {row.product_id for row in sold_rows}
            zero_product_ids = [pid for pid in product_ids if pid not in sold_product_ids]
            # Ularga 0 sotuv bilan maxsus qo'shish
            zero_rows: list = []
            if zero_product_ids:
                zero_stmt = (
                    select(Product.id.label("product_id"), Product.name_uz.label("product_name"))
                    .where(Product.id.in_(zero_product_ids))
                    .limit(max(0, limit - len(sold_rows)))
                )
                zero_result = await db.execute(zero_stmt)
                zero_rows = list(zero_result.all())

            # Birlashtirish: avval 0-sotuvlilar, keyin eng kam sotilganlar
            combined_rows = [
                (r.product_id, r.product_name, Decimal("0"), Decimal("0"), 0)
                for r in zero_rows
            ] + [
                (r.product_id, r.product_name, _to_decimal(r.sold_qty), _to_decimal(r.revenue), r.store_count)
                for r in sold_rows
            ]
            combined_rows = combined_rows[:limit]
        else:
            combined_rows = [
                (r.product_id, r.product_name, _to_decimal(r.sold_qty), _to_decimal(r.revenue), r.store_count)
                for r in sold_rows
            ]
    else:
        # Do'kon yo'q — faqat mahsulot nomlarini 0 sotuv bilan qaytarish
        if order == "bottom":
            zero_stmt = (
                select(Product.id.label("product_id"), Product.name_uz.label("product_name"))
                .where(Product.id.in_(product_ids))
                .limit(limit)
            )
            zero_result = await db.execute(zero_stmt)
            combined_rows = [
                (r.product_id, r.product_name, Decimal("0"), Decimal("0"), 0)
                for r in zero_result.all()
            ]
        else:
            combined_rows = []

    items: list[ProductRankingItem] = []
    for rank_idx, row_data in enumerate(combined_rows, start=1):
        product_id, product_name, sold_qty, revenue, store_count = row_data
        items.append(
            ProductRankingItem(
                product_id=product_id,
                product_name=product_name,
                sold_qty=sold_qty,
                revenue=revenue,
                store_count=int(store_count),
                rank=rank_idx,
            )
        )

    return ProductRankingOut(
        items=items,
        order=order,
        period_from=from_dt,
        period_to=to_dt,
    )


# ─── 6. Recommendations ───────────────────────────────────────────────────────


async def recommendations(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> RecommendationsOut:
    """
    AI tavsiyalar: rule-based + ixtiyoriy Claude-boyitilgan.

    Barcha agregatsiya natijalari yig'ilib recommendations.py ga uzatiladi,
    u R1-R5 qoidalari asosida tavsiyalar ro'yxati qaytaradi.
    ai_enrich.py ixtiyoriy Claude boyitish qo'shadi (ANTHROPIC_API_KEY bo'lsa).

    superadmin (enterprise_id=None) → bo'sh tavsiyalar.
    """
    from app.modules.analytics.recommendations import generate_recommendations
    from app.modules.analytics.ai_enrich import enrich_with_ai

    now = _now_utc()

    if enterprise_id is None:
        return RecommendationsOut(
            recommendations=[],
            ai_summary=None,
            ai_enabled=False,
            generated_at=now,
        )

    from_dt, to_dt = _default_period(from_dt, to_dt)

    # Barcha agregatsiyani yig'amiz
    geo_data = await geo_velocity(db, enterprise_id, from_dt, to_dt)
    expiry_data = await expiry_report(db, enterprise_id, within_days=DEFAULT_PERIOD_DAYS)
    products_top = await product_ranking(db, enterprise_id, from_dt, to_dt, order="top", limit=20)
    products_bottom = await product_ranking(db, enterprise_id, from_dt, to_dt, order="bottom", limit=20)

    # Rule-based tavsiyalar
    rec_items = generate_recommendations(
        geo_items=geo_data.items,
        expiry_items=expiry_data.items,
        top_products=products_top.items,
        bottom_products=products_bottom.items,
    )

    # Ixtiyoriy Claude boyitish
    ai_summary, ai_enabled = await enrich_with_ai(rec_items)

    return RecommendationsOut(
        recommendations=rec_items,
        ai_summary=ai_summary,
        ai_enabled=ai_enabled,
        generated_at=now,
    )
