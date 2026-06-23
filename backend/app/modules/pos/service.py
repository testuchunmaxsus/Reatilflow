"""
POS servis qatlami — chakana sotuv yadrosi.

Funksiyalar:
  create_sale(...)   — SERVER-AVTORITAR narx bilan sotuv yaratadi.
  list_sales(...)    — paginated sotuvlar ro'yxati (scope + filtr).
  get_sale(...)      — bitta sotuv (kvitansiya).
  daily_summary(...) — kunlik statistika (SQL agregatsiya).

NARX XAVFSIZLIGI (CRITICAL):
  Klient unit_price/discount/segment_id BERMAYDI.
  Narx FAQAT server tomonida katalogdan (do'kon segmenti bo'yicha) olinadi.
  Bu T11 orders moduli bilan izchil yondashuv.

RBAC SCOPE:
  - store: faqat o'z do'koni (Store.user_id == user.id)
  - administrator/accountant: korxona ichida hammasi
  - agent/courier: ruxsati yo'q (403)

IDEMPOTENTLIK:
  client_uuid orqali (store_id, client_uuid) UNIQUE constraint.
  IntegrityError ushlanadi → mavjud sotuv qaytariladi.

OUTBOX:
  Har sotuv pos.sale_created event (aggregate_type="pos_sale") outbox'ga yoziladi.

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ) — stats dialekt qo'rig'iga rioya.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.catalog import Product, ProductPrice
from app.models.outbox import OutboxEvent
from app.models.pos import PosSale, PosSaleLine
from app.models.store import Store
from app.models.user import AppUser
from app.modules.pos.schemas import (
    DailySummaryOut,
    PaymentMethodSummary,
    PosSaleCreate,
)
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Narx qidirish (orders pattern) ──────────────────────────────────────────


async def _get_product_price(
    db: AsyncSession,
    product_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> Decimal | None:
    """
    Mahsulot narxini katalogdan oladi — ANIQ SEGMENT bo'yicha.

    XAVFSIZLIK (HIGH):
      segment_id MAJBURIY — do'kon (Store.segment_id) dan server tomonida olinadi.
      Narx topilmasa → None qaytaradi (caller AppError ko'taradi).
    """
    stmt = (
        select(ProductPrice)
        .where(
            ProductPrice.product_id == product_id,
            ProductPrice.segment_id == segment_id,
            ProductPrice.valid_to.is_(None),
        )
        .order_by(ProductPrice.valid_from.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    price_row = result.scalar_one_or_none()
    return price_row.price if price_row else None


# ─── Outbox yordamchisi ───────────────────────────────────────────────────────


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


# ─── Do'kon scope tekshiruvi ──────────────────────────────────────────────────


async def _check_store_access(
    db: AsyncSession,
    store_id: uuid.UUID,
    user: AppUser,
) -> None:
    """
    RBAC scope: foydalanuvchi berilgan do'konga kirish huquqini tekshiradi.

    - store: faqat o'z do'koni (Store.user_id == user.id)
    - administrator/accountant: har qanday do'kon
    - agent/courier: ruxsati yo'q (403)

    Ruxsatsiz → AppError("rbac.permission_denied", 403)
    """
    role = user.role

    if role in ("administrator", "accountant"):
        return

    if role == "store":
        stmt = select(Store.id).where(
            Store.id == store_id,
            Store.user_id == user.id,
            Store.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError(
                "pos.sale_not_found",
                status_code=404,
            )
        return

    # agent, courier — ruxsati yo'q
    raise AppError(
        "rbac.permission_denied",
        status_code=403,
        params={"module": "pos", "action": "create", "role": role},
    )


async def _check_sale_access(
    db: AsyncSession,
    sale: PosSale,
    user: AppUser,
) -> None:
    """
    IDOR himoya: foydalanuvchi berilgan sotuvga kirish huquqini tekshiradi.

    - store: faqat o'z do'koni sotuvlari
    - administrator/accountant: korxona ichida hammasi
    """
    role = user.role

    if role in ("administrator", "accountant"):
        return

    if role == "store":
        stmt = select(Store.id).where(
            Store.id == sale.store_id,
            Store.user_id == user.id,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("pos.sale_not_found", status_code=404)
        return

    raise AppError("pos.sale_not_found", status_code=404)


# ─── create_sale ─────────────────────────────────────────────────────────────


async def create_sale(
    db: AsyncSession,
    data: PosSaleCreate,
    cashier_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> PosSale:
    """
    Yangi POS sotuv yaratadi.

    NARX XAVFSIZLIGI:
      Klient unit_price/discount BERMAYDI.
      Narx FAQAT do'kon segmenti bo'yicha katalogdan olinadi.
      Segment yo'q → AppError("pos.no_price", 422).

    ATOMIKLIK:
      PosSale + PosSaleLine bir sessiyada (caller get_db() commit qiladi).

    IDEMPOTENTLIK:
      (store_id, client_uuid) UNIQUE constraint.
      IntegrityError → mavjud sotuv qaytariladi.

    Raises:
        AppError("pos.empty_lines", 422): qatorlar bo'sh.
        AppError("customers.store_not_found", 404): do'kon topilmasa.
        AppError("pos.product_not_found", 404): mahsulot topilmasa.
        AppError("pos.no_price", 422): segment narxi topilmasa.
        AppError("pos.idempotency_conflict", 409): boshqa do'kon bir xil client_uuid.
    """
    # ── 1. Bo'sh lines tekshiruvi ─────────────────────────────────────────
    if not data.lines:
        raise AppError("pos.empty_lines", status_code=422)

    # ── 2. Do'kon mavjudligi (enterprise filtr bilan) ─────────────────────
    store_stmt = select(Store).where(
        Store.id == data.store_id,
        Store.deleted_at.is_(None),
    )
    store_stmt = apply_enterprise_filter(store_stmt, enterprise_id, Store.enterprise_id)
    store_result = await db.execute(store_stmt)
    store = store_result.scalar_one_or_none()
    if store is None:
        raise AppError("customers.store_not_found", status_code=404)

    # ── 3. RBAC scope ─────────────────────────────────────────────────────
    if user is not None:
        await _check_store_access(db, data.store_id, user)

    # ── 4. Do'kon segmenti — server tomonidan ─────────────────────────────
    store_segment_id: uuid.UUID | None = store.segment_id

    # ── 5. Har qator uchun mahsulot + narx tekshiruvi ─────────────────────
    # (product, unit_price, line_total)
    resolved_lines: list[tuple] = []

    for line_in in data.lines:
        # Mahsulot mavjudligi
        prod_stmt = select(Product).where(
            Product.id == line_in.product_id,
            Product.is_active.is_(True),
        )
        prod_result = await db.execute(prod_stmt)
        product = prod_result.scalar_one_or_none()
        if product is None:
            raise AppError("pos.product_not_found", status_code=404)

        # Narx: FAQAT server tomonida, do'kon segmenti bo'yicha (CRITICAL)
        if store_segment_id is None:
            raise AppError("pos.no_price", status_code=422)

        cat_price = await _get_product_price(db, line_in.product_id, store_segment_id)
        if cat_price is None:
            raise AppError("pos.no_price", status_code=422)

        unit_price = cat_price
        line_total = (unit_price * line_in.qty).quantize(Decimal("0.01"))
        if line_total < Decimal("0"):
            line_total = Decimal("0.00")

        resolved_lines.append((line_in, unit_price, line_total))

    # ── 6. total_amount hisoblash ─────────────────────────────────────────
    total_amount = Decimal(
        str(sum(lt for _, _, lt in resolved_lines))
    ).quantize(Decimal("0.01"))

    # ── 7. PosSale INSERT ─────────────────────────────────────────────────
    sale_id = uuid7()
    sale = PosSale(
        id=sale_id,
        store_id=data.store_id,
        cashier_id=cashier_id,
        total_amount=total_amount,
        discount_amount=Decimal("0"),
        payment_method=data.payment_method,
        customer_phone=data.customer_phone,
        status="completed",
        client_uuid=data.client_uuid,
        enterprise_id=enterprise_id,
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(sale)

    try:
        await db.flush()
    except IntegrityError as exc:
        # (store_id, client_uuid) dublikati — mavjud sotuvni qaytarish
        await db.rollback()
        if data.client_uuid is not None:
            existing_stmt = (
                select(PosSale)
                .options(selectinload(PosSale.lines))
                .where(
                    PosSale.store_id == data.store_id,
                    PosSale.client_uuid == data.client_uuid,
                )
            )
            existing_result = await db.execute(existing_stmt)
            existing_sale = existing_result.scalar_one_or_none()
            if existing_sale is not None:
                # Bir xil do'kon + client_uuid → idempotent qaytarish
                if (
                    existing_sale.cashier_id == cashier_id
                    or existing_sale.cashier_id is None
                    or cashier_id is None
                ):
                    return existing_sale
                raise AppError("pos.idempotency_conflict", status_code=409) from exc
        raise AppError("pos.idempotency_conflict", status_code=409) from exc

    # ── 8. PosSaleLine INSERT ─────────────────────────────────────────────
    for line_in, unit_price, line_total in resolved_lines:
        sl = PosSaleLine(
            sale_id=sale.id,
            product_id=line_in.product_id,
            qty=line_in.qty,
            unit_price=unit_price,
            line_total=line_total,
            enterprise_id=enterprise_id,
        )
        db.add(sl)
    await db.flush()

    # ── 9. Outbox event ───────────────────────────────────────────────────
    payload = {
        "id": str(sale.id),
        "store_id": str(data.store_id),
        "cashier_id": str(cashier_id) if cashier_id else None,
        "total_amount": str(total_amount),
        "payment_method": data.payment_method,
        "status": "completed",
        "lines_count": len(resolved_lines),
    }
    await _write_outbox(db, "pos_sale", str(sale.id), "pos.sale_created", payload)

    # lines ni yuklab qaytarish (N+1 oldini olish)
    await db.refresh(sale, ["lines"])
    return sale


# ─── list_sales ───────────────────────────────────────────────────────────────


async def list_sales(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[PosSale], int]:
    """
    Paginated POS sotuvlar ro'yxati.

    RBAC scope:
      - store: faqat o'z do'koni sotuvlari.
      - administrator/accountant: korxona ichida hammasi.
      - Boshqa rollar → bo'sh ro'yxat (ruxsat RBAC darajasida tekshiriladi).
    """
    conditions = []

    # MT2: Enterprise izolyatsiyasi
    if enterprise_id is not None:
        conditions.append(PosSale.enterprise_id == enterprise_id)

    # RBAC scope
    if user is not None:
        role = user.role

        if role == "store":
            store_subq = (
                select(Store.id)
                .where(Store.user_id == user.id)
                .scalar_subquery()
            )
            conditions.append(PosSale.store_id.in_(store_subq))

        elif role in ("administrator", "accountant"):
            # Barcha do'konlar — enterprise filtr yetarli
            pass

        else:
            # agent, courier — ruxsati yo'q, bo'sh ro'yxat
            conditions.append(PosSale.id.is_(None))

    # Qo'shimcha filtrlar
    if store_id is not None:
        conditions.append(PosSale.store_id == store_id)
    if date_from is not None:
        conditions.append(PosSale.created_at >= date_from)
    if date_to is not None:
        conditions.append(PosSale.created_at <= date_to)

    # Count
    count_stmt = select(func.count()).select_from(PosSale)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List
    stmt = (
        select(PosSale)
        .options(selectinload(PosSale.lines))
        .order_by(PosSale.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return items, total


# ─── get_sale ─────────────────────────────────────────────────────────────────


async def get_sale(
    db: AsyncSession,
    sale_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> PosSale:
    """
    Bitta sotuvni qaytaradi — kvitansiya ma'lumoti.

    IDOR himoya: foydalanuvchi ruxsatli sotuvlardan tekshiriladi.
    Ruxsatsiz → AppError("pos.sale_not_found", 404).
    """
    stmt = (
        select(PosSale)
        .options(selectinload(PosSale.lines))
        .where(PosSale.id == sale_id)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, PosSale.enterprise_id)
    result = await db.execute(stmt)
    sale = result.scalar_one_or_none()
    if sale is None:
        raise AppError("pos.sale_not_found", status_code=404)

    if user is not None:
        await _check_sale_access(db, sale, user)

    return sale


# ─── daily_summary ────────────────────────────────────────────────────────────


async def daily_summary(
    db: AsyncSession,
    *,
    summary_date: date,
    enterprise_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> DailySummaryOut:
    """
    Kunlik POS statistika — SQL agregatsiya.

    Qaytaradi:
      - total_sales: sotuv soni
      - total_amount: jami summa
      - by_payment: to'lov usuli bo'yicha breakdown

    RBAC scope:
      - store: faqat o'z do'koni.
      - administrator/accountant: korxona ichida hammasi.

    Dialekt-aware sana filtr (SQLite/PostgreSQL).
    """
    from datetime import timedelta

    # Sana chegaralarini hisoblash (kun boshidan oxirigacha UTC)
    date_start = datetime(summary_date.year, summary_date.month, summary_date.day, 0, 0, 0, tzinfo=timezone.utc)
    date_end = date_start + timedelta(days=1)

    # Base conditions
    conditions = [
        PosSale.status == "completed",
        PosSale.created_at >= date_start,
        PosSale.created_at < date_end,
    ]

    # Enterprise filtr
    if enterprise_id is not None:
        conditions.append(PosSale.enterprise_id == enterprise_id)

    # RBAC scope
    if user is not None:
        role = user.role
        if role == "store":
            store_subq = (
                select(Store.id)
                .where(Store.user_id == user.id)
                .scalar_subquery()
            )
            conditions.append(PosSale.store_id.in_(store_subq))
        elif role in ("administrator", "accountant"):
            pass
        else:
            # Boshqa rollar — bo'sh qaytarish
            return DailySummaryOut(
                date=summary_date,
                total_sales=0,
                total_amount=Decimal("0"),
                by_payment=[],
            )

    # store_id filtr (ixtiyoriy)
    if store_id is not None:
        conditions.append(PosSale.store_id == store_id)

    # ── Total hisoblash (bitta SQL) ───────────────────────────────────────
    total_stmt = select(
        func.count(PosSale.id).label("total_sales"),
        func.coalesce(func.sum(PosSale.total_amount), 0).label("total_amount"),
    ).where(*conditions)

    total_result = await db.execute(total_stmt)
    row = total_result.one()
    total_sales = row.total_sales or 0
    total_amount = Decimal(str(row.total_amount or 0)).quantize(Decimal("0.01"))

    # ── To'lov usuli bo'yicha breakdown ───────────────────────────────────
    payment_stmt = select(
        PosSale.payment_method,
        func.count(PosSale.id).label("count"),
        func.coalesce(func.sum(PosSale.total_amount), 0).label("amount"),
    ).where(*conditions).group_by(PosSale.payment_method)

    payment_result = await db.execute(payment_stmt)
    by_payment = [
        PaymentMethodSummary(
            payment_method=r.payment_method,
            count=r.count,
            total_amount=Decimal(str(r.amount or 0)).quantize(Decimal("0.01")),
        )
        for r in payment_result.all()
    ]

    return DailySummaryOut(
        date=summary_date,
        total_sales=total_sales,
        total_amount=total_amount,
        by_payment=by_payment,
    )
