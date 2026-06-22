"""
Statistika servis qatlami — T22.

Funksiyalar:
  sales_stats(db, user, from_dt, to_dt, branch_id, group_by) → SalesStatsOut
  delivery_stats(db, user, from_dt, to_dt, courier_id) → DeliveryStatsOut
  finance_stats(db, user, from_dt, to_dt, branch_id) → FinanceStatsOut

MUHIM QOIDALAR (ADR §3.4, §3.8):
  - sales_stats, delivery_stats → read replica (db_replica parametri)
  - finance_stats → PRIMARY DB (db parametri) — replikatsiya kechikishidan qochish
  - Barcha funksiyalar faqat SELECT (read-only) — yangi yozuv TAQIQLANGAN
  - Decimal moliyaviy aniqlik (float emas)

Scope/IDOR:
  - agent: faqat o'z do'konlari/buyurtmalari
  - courier: faqat o'z yetkazishlari
  - store: faqat o'z buyurtmalari va balansi
  - accountant/administrator: barchasi (branch_id bo'yicha filter ixtiyoriy)

SQL agregatsiya (T22 hardening):
  - Barcha hisoblashlar DB darajasida: func.sum, func.count, func.coalesce
  - Sana guruhlash: SQLite → func.strftime; PostgreSQL → func.to_char
    (dialekt db.get_bind().dialect.name orqali aniqlanadi)
  - NULL summalar coalesce(..., 0) bilan 0 ga aylantiriladi
  - Barcha qatorlarni xotiraga yuklash BARTARAF etildi
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.delivery import Delivery
from app.models.finance import AccountBalance, LedgerEntry
from app.models.order import Order
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.rbac.enterprise_scope import apply_enterprise_filter
from app.modules.stats.schemas import (
    DeliveryStatsOut,
    FinanceStoreItem,
    FinanceStatsOut,
    SalesPeriodItem,
    SalesStatsOut,
)

logger = logging.getLogger(__name__)

# Qo'llab-quvvatlanadigan group_by qiymatlari
VALID_GROUP_BY: frozenset[str] = frozenset({"day", "week", "month"})


# ─── Scope yordamchi funksiyalari ─────────────────────────────────────────────


async def _get_agent_store_ids(user: AppUser, db: AsyncSession) -> list:
    """Agent uchun ruxsat etilgan do'kon ID larini qaytaradi."""
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


async def _get_store_id_for_store_user(user: AppUser, db: AsyncSession):
    """Store roli uchun foydalanuvchiga tegishli bitta do'kon ID sini qaytaradi.

    Topilmasa None qaytaradi (bo'sh statistika).
    """
    stmt = select(Store.id).where(Store.user_id == user.id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ─── Dialekt yordamchi funksiyasi ─────────────────────────────────────────────


def _get_dialect(db: AsyncSession) -> str:
    """
    Sessiyaning DB dialektini qaytaradi: 'sqlite' yoki 'postgresql'.

    db.get_bind().dialect.name ishlatiladi — sync proxy orqali.
    Bu function faqat read-only (dialect aniqlanadi, yozuv bo'lmaydi).
    """
    try:
        return db.get_bind().dialect.name
    except Exception:
        # Fallback: agar get_bind() ishlamasa (ba'zi test o'ramlar) 'sqlite' deb ol
        return "sqlite"


def _period_label_expr(group_by: str, dialect: str):
    """
    Sana bo'yicha guruhlash uchun SQL expression qaytaradi.

    SQLite: func.strftime(format, column)
    PostgreSQL: func.to_char(column, format)

    Qaytaruvchi qiymat:
      day   → '2026-06-01'
      week  → '2026-W23'   (SQLite: '%Y-W%W'; PG: 'IYYY-"W"IW')
      month → '2026-06'
    """
    col = Order.ordered_at
    if dialect == "postgresql":
        if group_by == "day":
            return func.to_char(col, "YYYY-MM-DD")
        elif group_by == "week":
            # ISO hafta: 'IYYY-"W"IW' → '2026-W23'
            return func.to_char(col, 'IYYY-"W"IW')
        else:  # month
            return func.to_char(col, "YYYY-MM")
    else:
        # SQLite: strftime
        if group_by == "day":
            return func.strftime("%Y-%m-%d", col)
        elif group_by == "week":
            return func.strftime("%Y-W%W", col)
        else:  # month
            return func.strftime("%Y-%m", col)


def _format_period(dt: datetime, group_by: str) -> str:
    """datetime ni davr labeliga aylantiradi (Python tomonda fallback uchun)."""
    if group_by == "day":
        return dt.strftime("%Y-%m-%d")
    elif group_by == "week":
        return dt.strftime("%Y-W%W")
    elif group_by == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


# ─── 1. Savdo statistikasi ────────────────────────────────────────────────────


async def sales_stats(
    db: AsyncSession,
    user: AppUser,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    branch_id: str | None = None,
    group_by: str | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> SalesStatsOut:
    """
    Buyurtmalar bo'yicha savdo statistikasi.

    SQL agregatsiya: DB darajasida COUNT(*), SUM(total_amount), GROUP BY period.
    Barcha qatorlarni xotiraga yuklash bartaraf etildi.

    Parametrlar:
        db       — read replica sessiyasi (non-financial, ADR §3.4)
        user     — joriy foydalanuvchi (RBAC scope uchun)
        from_dt  — boshlanish vaqti (ixtiyoriy)
        to_dt    — tugash vaqti (ixtiyoriy)
        branch_id — filial filtrasi (admin/accountant uchun)
        group_by  — 'day' | 'week' | 'month' (dinamika guruhlash)

    Scope (IDOR himoya):
        - administrator/accountant: barchasi (branch_id bo'yicha ixtiyoriy filtr)
        - agent: faqat o'z do'konlari buyurtmalari
        - store: faqat o'z do'konining buyurtmalari
        - courier: bo'sh (savdo statistikasi kuryerga tegishli emas)

    Raises:
        AppError(stats.invalid_period, 422) — from_dt > to_dt
        AppError(stats.invalid_group_by, 422) — yaroqsiz group_by qiymati
    """
    # Validatsiya
    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="stats.invalid_period", status_code=422)
    if group_by and group_by not in VALID_GROUP_BY:
        raise AppError(message_key="stats.invalid_group_by", status_code=422)

    # RBAC scope: courier bo'sh qaytaradi
    role = user.role
    if role == "courier":
        return SalesStatsOut(
            total_orders=0,
            total_amount=Decimal("0"),
            period_from=from_dt,
            period_to=to_dt,
            group_by=group_by,
            dynamics=[],
        )

    # Jami aggregatsiya so'rovi (SQL darajasida COUNT + SUM)
    total_stmt = select(
        func.count().label("total_orders"),
        func.coalesce(func.sum(Order.total_amount), Decimal("0")).label("total_amount"),
    ).where(Order.deleted_at.is_(None))
    # MT2: korxona filtr
    total_stmt = apply_enterprise_filter(total_stmt, enterprise_id, Order.enterprise_id)

    # RBAC scope filtri
    if role == "administrator" or role == "accountant":
        if branch_id is not None:
            import uuid as _uuid
            try:
                bid = _uuid.UUID(str(branch_id))
                total_stmt = total_stmt.where(Order.branch_id == bid)
            except ValueError:
                pass
    elif role == "agent":
        store_ids = await _get_agent_store_ids(user, db)
        if not store_ids:
            return SalesStatsOut(
                total_orders=0,
                total_amount=Decimal("0"),
                period_from=from_dt,
                period_to=to_dt,
                group_by=group_by,
                dynamics=[],
            )
        total_stmt = total_stmt.where(Order.store_id.in_(store_ids))
    elif role == "store":
        store_id = await _get_store_id_for_store_user(user, db)
        if store_id is None:
            return SalesStatsOut(
                total_orders=0,
                total_amount=Decimal("0"),
                period_from=from_dt,
                period_to=to_dt,
                group_by=group_by,
                dynamics=[],
            )
        total_stmt = total_stmt.where(Order.store_id == store_id)

    # Vaqt filtri
    if from_dt:
        total_stmt = total_stmt.where(Order.ordered_at >= from_dt)
    if to_dt:
        total_stmt = total_stmt.where(Order.ordered_at <= to_dt)

    # Jami hisob (bitta DB so'rovi)
    total_result = await db.execute(total_stmt)
    total_row = total_result.one()
    total_orders = total_row.total_orders or 0
    # SQL SUM Decimal bo'lishi kerak; coalesce bilan NULL→0 kafolatlangan
    raw_total = total_row.total_amount
    if raw_total is None:
        total_amount = Decimal("0")
    elif isinstance(raw_total, Decimal):
        total_amount = raw_total
    else:
        total_amount = Decimal(str(raw_total))

    # Dinamika guruhlash (ixtiyoriy, faqat group_by berilganda)
    dynamics: list[SalesPeriodItem] = []
    if group_by and total_orders > 0:
        dialect = _get_dialect(db)
        period_expr = _period_label_expr(group_by, dialect)

        # GROUP BY period_expr SQL darajasida
        # Scope where klozlari jami so'rovdan nusxalanadi
        dynamics_stmt = (
            select(
                period_expr.label("period"),
                func.count().label("order_count"),
                func.coalesce(func.sum(Order.total_amount), Decimal("0")).label("total_amount"),
            )
            .where(Order.deleted_at.is_(None))
            .group_by(period_expr)
            .order_by(period_expr)
        )
        # MT2: korxona filtr (dinamika ham)
        dynamics_stmt = apply_enterprise_filter(dynamics_stmt, enterprise_id, Order.enterprise_id)

        # Xuddi o'sha scope filtrlarini qo'shish
        if role == "administrator" or role == "accountant":
            if branch_id is not None:
                import uuid as _uuid
                try:
                    bid = _uuid.UUID(str(branch_id))
                    dynamics_stmt = dynamics_stmt.where(Order.branch_id == bid)
                except ValueError:
                    pass
        elif role == "agent":
            # store_ids allaqachon yuqorida aniqlangan
            dynamics_stmt = dynamics_stmt.where(Order.store_id.in_(store_ids))
        elif role == "store":
            # store_id allaqachon yuqorida aniqlangan
            dynamics_stmt = dynamics_stmt.where(Order.store_id == store_id)

        if from_dt:
            dynamics_stmt = dynamics_stmt.where(Order.ordered_at >= from_dt)
        if to_dt:
            dynamics_stmt = dynamics_stmt.where(Order.ordered_at <= to_dt)

        dyn_result = await db.execute(dynamics_stmt)
        dyn_rows = dyn_result.all()

        for row in dyn_rows:
            raw_amt = row.total_amount
            if raw_amt is None:
                amt = Decimal("0")
            elif isinstance(raw_amt, Decimal):
                amt = raw_amt
            else:
                amt = Decimal(str(raw_amt))
            dynamics.append(
                SalesPeriodItem(
                    period=row.period,
                    order_count=row.order_count,
                    total_amount=amt,
                )
            )

    return SalesStatsOut(
        total_orders=total_orders,
        total_amount=total_amount,
        period_from=from_dt,
        period_to=to_dt,
        group_by=group_by,
        dynamics=dynamics,
    )


# ─── 2. Yetkazish statistikasi ─────────────────────────────────────────────────


async def delivery_stats(
    db: AsyncSession,
    user: AppUser,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    courier_id: str | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> DeliveryStatsOut:
    """
    Yetkazishlar bo'yicha statistika.

    SQL agregatsiya: status bo'yicha COUNT (CASE WHEN), avg_delivery_minutes
    ham DB darajasida dialekt-agnostik tarzda hisoblanadi.

    Parametrlar:
        db         — read replica sessiyasi (non-financial, ADR §3.4)
        user       — joriy foydalanuvchi
        from_dt    — boshlanish vaqti
        to_dt      — tugash vaqti
        courier_id — kuryer filtri (administrator uchun)

    Scope:
        - administrator/accountant/agent: barchasi ko'rish mumkin
          (agent o'z do'konlarining yetkazishlari)
        - courier: faqat o'z yetkazishlari
        - store: faqat o'z do'konining buyurtmalarining yetkazishlari

    avg_delivery_minutes:
        SQLite: (julianday(delivered_at) - julianday(started_at)) * 24 * 60
        PostgreSQL: EXTRACT(EPOCH FROM (delivered_at - started_at)) / 60
        Ikkala holat uchun dialekt aniqlanadi va mos SQL ishlatiladi.
        None — hech qanday yetkazilgan yozuv yo'q.

    Raises:
        AppError(stats.invalid_period, 422) — from_dt > to_dt
    """
    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="stats.invalid_period", status_code=422)

    role = user.role
    dialect = _get_dialect(db)

    # Base filtrlar (scope + vaqt) uchun where sharti ro'yxati
    # Ular STATUS COUNT va AVG uchun qayta ishlatiladi
    base_where = [Delivery.deleted_at.is_(None)]
    # MT2: korxona filtr
    if enterprise_id is not None:
        base_where.append(Delivery.enterprise_id == enterprise_id)

    # RBAC scope
    _needs_order_join = False
    _order_store_ids: list | None = None
    _order_store_id = None

    if role == "courier":
        base_where.append(Delivery.courier_id == user.id)
    elif role == "store":
        store_id = await _get_store_id_for_store_user(user, db)
        if store_id is None:
            return DeliveryStatsOut(
                total_deliveries=0,
                delivered_count=0,
                failed_count=0,
                in_progress_count=0,
                avg_delivery_minutes=None,
                period_from=from_dt,
                period_to=to_dt,
            )
        _needs_order_join = True
        _order_store_id = store_id
    elif role == "agent":
        store_ids = await _get_agent_store_ids(user, db)
        if not store_ids:
            return DeliveryStatsOut(
                total_deliveries=0,
                delivered_count=0,
                failed_count=0,
                in_progress_count=0,
                avg_delivery_minutes=None,
                period_from=from_dt,
                period_to=to_dt,
            )
        _needs_order_join = True
        _order_store_ids = store_ids
    # administrator/accountant — barcha yetkazishlar, qo'shimcha filtr yo'q

    # courier_id filtri (administrator/accountant uchun)
    if courier_id is not None and role in ("administrator", "accountant"):
        import uuid as _uuid
        try:
            cid = _uuid.UUID(str(courier_id))
            base_where.append(Delivery.courier_id == cid)
        except ValueError:
            pass

    # Vaqt filtri (assigned_at bo'yicha)
    if from_dt:
        base_where.append(Delivery.assigned_at >= from_dt)
    if to_dt:
        base_where.append(Delivery.assigned_at <= to_dt)

    # avg_delivery_minutes SQL ifodasi (dialekt-agnostik)
    # Faqat "delivered" holat uchun, started_at va delivered_at NOT NULL bo'lganda
    if dialect == "postgresql":
        # EXTRACT(EPOCH FROM (delivered_at - started_at)) / 60.0
        avg_minutes_expr = func.avg(
            case(
                (
                    (
                        Delivery.status == "delivered"
                    ) & (
                        Delivery.started_at.isnot(None)
                    ) & (
                        Delivery.delivered_at.isnot(None)
                    ),
                    # EPOCH seconds → minutes
                    func.extract(
                        "epoch",
                        Delivery.delivered_at - Delivery.started_at
                    ) / 60.0,
                ),
                else_=None,
            )
        )
    else:
        # SQLite: (julianday(delivered_at) - julianday(started_at)) * 24 * 60
        avg_minutes_expr = func.avg(
            case(
                (
                    (
                        Delivery.status == "delivered"
                    ) & (
                        Delivery.started_at.isnot(None)
                    ) & (
                        Delivery.delivered_at.isnot(None)
                    ),
                    (
                        func.julianday(Delivery.delivered_at)
                        - func.julianday(Delivery.started_at)
                    ) * 24 * 60,
                ),
                else_=None,
            )
        )

    # Agregatsiya so'rovi: bitta SELECT — barcha status count va avg
    agg_stmt = select(
        func.count().label("total"),
        func.sum(
            case((Delivery.status == "delivered", 1), else_=0)
        ).label("delivered_count"),
        func.sum(
            case((Delivery.status == "failed", 1), else_=0)
        ).label("failed_count"),
        func.sum(
            case(
                (Delivery.status.notin_(("delivered", "failed")), 1),
                else_=0,
            )
        ).label("in_progress_count"),
        avg_minutes_expr.label("avg_minutes"),
    ).where(*base_where)

    # Join kerak bo'lsa (store/agent scope)
    if _needs_order_join:
        agg_stmt = agg_stmt.join(Order, Delivery.order_id == Order.id)
        if _order_store_id is not None:
            agg_stmt = agg_stmt.where(Order.store_id == _order_store_id)
        elif _order_store_ids is not None:
            agg_stmt = agg_stmt.where(Order.store_id.in_(_order_store_ids))

    result = await db.execute(agg_stmt)
    row = result.one()

    total = row.total or 0
    delivered_count = row.delivered_count or 0
    failed_count = row.failed_count or 0
    in_progress = row.in_progress_count or 0

    # avg_minutes: SQL AVG NULL → None; aks holda Decimal ga aylantirish
    avg_minutes: Decimal | None = None
    if row.avg_minutes is not None:
        avg_minutes = Decimal(str(round(float(row.avg_minutes), 2)))

    return DeliveryStatsOut(
        total_deliveries=total,
        delivered_count=delivered_count,
        failed_count=failed_count,
        in_progress_count=in_progress,
        avg_delivery_minutes=avg_minutes,
        period_from=from_dt,
        period_to=to_dt,
    )


# ─── 3. Moliyaviy statistika ──────────────────────────────────────────────────


async def finance_stats(
    db: AsyncSession,
    user: AppUser,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    branch_id: str | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> FinanceStatsOut:
    """
    Do'kon bo'yicha qarz/haqdorlik va jami debit/credit statistikasi.

    SQL agregatsiya: LedgerEntry GROUP BY (store_id, type) — DB darajasida SUM.
    AccountBalance alohida so'rovda (kumulativ, period filtrisisiz).

    MUHIM: bu funksiya PRIMARY DB sessiyasida chaqirilishi shart (ADR §3.8).
    Moliyaviy o'qish replikadan emas, asosiy bazadan.

    Parametrlar:
        db       — PRIMARY DB sessiyasi (get_db dependency, ADR §3.8)
        user     — joriy foydalanuvchi
        from_dt  — boshlanish vaqti (ledger_entry.entry_date bo'yicha)
        to_dt    — tugash vaqti
        branch_id — filial filtrasi

    Scope:
        - administrator/accountant: barchasi ko'rishi mumkin
        - agent: faqat o'z do'konlari
        - store: faqat o'z balansi (bitta do'kon)
        - courier: moliyaviy hisobot ko'ra olmaydi (403 router darajasida)

    Raises:
        AppError(stats.invalid_period, 422) — from_dt > to_dt
    """
    if from_dt and to_dt and from_dt > to_dt:
        raise AppError(message_key="stats.invalid_period", status_code=422)

    role = user.role

    # Store ro'yxatini aniqlash (scope bo'yicha)
    if role in ("administrator", "accountant"):
        stmt = select(Store.id, Store.name)
        # MT2: korxona filtr — admin faqat o'z korxonasi do'konlarini ko'radi
        stmt = apply_enterprise_filter(stmt, enterprise_id, Store.enterprise_id)
        if branch_id is not None:
            import uuid as _uuid
            try:
                bid = _uuid.UUID(str(branch_id))
                stmt = stmt.where(Store.branch_id == bid)
            except ValueError:
                pass
        result = await db.execute(stmt)
        store_rows = list(result.all())
    elif role == "agent":
        store_ids = await _get_agent_store_ids(user, db)
        if not store_ids:
            return FinanceStatsOut(
                total_debit=Decimal("0"),
                total_credit=Decimal("0"),
                net_balance=Decimal("0"),
                stores=[],
                period_from=from_dt,
                period_to=to_dt,
            )
        stmt = select(Store.id, Store.name).where(Store.id.in_(store_ids))
        result = await db.execute(stmt)
        store_rows = list(result.all())
    elif role == "store":
        store_id = await _get_store_id_for_store_user(user, db)
        if store_id is None:
            return FinanceStatsOut(
                total_debit=Decimal("0"),
                total_credit=Decimal("0"),
                net_balance=Decimal("0"),
                stores=[],
                period_from=from_dt,
                period_to=to_dt,
            )
        stmt = select(Store.id, Store.name).where(Store.id == store_id)
        result = await db.execute(stmt)
        store_rows = list(result.all())
    else:
        # courier va boshqa rollar uchun bo'sh qaytarish
        return FinanceStatsOut(
            total_debit=Decimal("0"),
            total_credit=Decimal("0"),
            net_balance=Decimal("0"),
            stores=[],
            period_from=from_dt,
            period_to=to_dt,
        )

    store_id_list = [row[0] for row in store_rows]
    store_name_map = {row[0]: row[1] for row in store_rows}

    if not store_id_list:
        return FinanceStatsOut(
            total_debit=Decimal("0"),
            total_credit=Decimal("0"),
            net_balance=Decimal("0"),
            stores=[],
            period_from=from_dt,
            period_to=to_dt,
        )

    # Ledger agregatsiyasi: GROUP BY store_id, type → SUM(amount) DB darajasida
    # Bitta so'rov — barcha store_id larni qamrab oladi
    ledger_agg_stmt = (
        select(
            LedgerEntry.store_id,
            LedgerEntry.type,
            func.coalesce(func.sum(LedgerEntry.amount), Decimal("0")).label("total"),
            # Valyutani olish uchun (har do'kon uchun birinchi topilgan)
            # Aggregate func.max currency tartib bo'yicha tanlab oladi (yetarli)
            func.max(LedgerEntry.currency).label("currency"),
        )
        .where(LedgerEntry.store_id.in_(store_id_list))
        .group_by(LedgerEntry.store_id, LedgerEntry.type)
    )
    # MT2: korxona filtr (do'kon ro'yxati allaqachon scoped — defense-in-depth)
    ledger_agg_stmt = apply_enterprise_filter(ledger_agg_stmt, enterprise_id, LedgerEntry.enterprise_id)
    if from_dt:
        ledger_agg_stmt = ledger_agg_stmt.where(LedgerEntry.entry_date >= from_dt)
    if to_dt:
        ledger_agg_stmt = ledger_agg_stmt.where(LedgerEntry.entry_date <= to_dt)

    ledger_result = await db.execute(ledger_agg_stmt)
    ledger_rows = ledger_result.all()

    # Store bo'yicha debit/credit yig'ish (Python darajasida — lekin faqat N ta guruhlovchi satr)
    store_debit: dict = {}
    store_credit: dict = {}
    store_currency: dict = {}

    for sid in store_id_list:
        store_debit[sid] = Decimal("0")
        store_credit[sid] = Decimal("0")

    for row in ledger_rows:
        sid = row.store_id
        raw_total = row.total
        if raw_total is None:
            total_val = Decimal("0")
        elif isinstance(raw_total, Decimal):
            total_val = raw_total
        else:
            total_val = Decimal(str(raw_total))

        if row.type == "debit":
            store_debit[sid] = total_val
        elif row.type == "credit":
            store_credit[sid] = total_val

        if row.currency:
            store_currency[sid] = row.currency

    # Account balance (joriy balans — period filtrisiz, kumulativ)
    balance_stmt = select(AccountBalance).where(
        AccountBalance.store_id.in_(store_id_list)
    )
    balance_result = await db.execute(balance_stmt)
    balances = list(balance_result.scalars().all())
    balance_map: dict = {b.store_id: b for b in balances}

    # Jami
    total_debit = sum(store_debit.values(), Decimal("0"))
    total_credit = sum(store_credit.values(), Decimal("0"))
    net_balance = total_debit - total_credit

    # Do'kon ro'yxati
    store_items: list[FinanceStoreItem] = []
    for sid in store_id_list:
        debit = store_debit[sid]
        credit = store_credit[sid]
        bal_obj = balance_map.get(sid)
        balance_val = bal_obj.balance if bal_obj is not None else (debit - credit)
        currency = store_currency.get(sid) or (bal_obj.currency if bal_obj else "UZS")

        store_items.append(FinanceStoreItem(
            store_id=sid,
            store_name=store_name_map.get(sid, ""),
            total_debit=debit,
            total_credit=credit,
            balance=balance_val,
            currency=currency,
        ))

    return FinanceStatsOut(
        total_debit=total_debit,
        total_credit=total_credit,
        net_balance=net_balance,
        stores=store_items,
        period_from=from_dt,
        period_to=to_dt,
    )
