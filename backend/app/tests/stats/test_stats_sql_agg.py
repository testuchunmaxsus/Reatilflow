"""
SQL agregatsiya testlari — T22 hardening.

Bu testlar Python-tomon agregatsiyadan SQL-tomon o'tkazilganini tekshiradi:
  (a) Bir nechta filial/agent/sana bo'yicha to'g'ri yig'indi (multi-entity sums)
  (b) Bo'sh ma'lumotda 0 qaytishi (NULL emas) — coalesce kafolati
  (c) Dinamika (dynamics) tartibi to'g'ri (ORDER BY period ASC)
  (d) RBAC scope / IDOR — boshqa filial/agent ma'lumoti oqib chiqmaydi

Infrasiz: aiosqlite + fakeredis (stats conftest dan fixtures import).
SQLite dialektida ishlaydi (prod PG uchun mantiq bir xil, dialekt tanlanadi).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import AgentStore
from app.models.user import AppUser
from app.modules.stats import service


# ─── (a) Ko'p agent/do'kon yig'indisi to'g'ri ─────────────────────────────────


@pytest.mark.asyncio
async def test_sql_agg_multi_agent_total_sum(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    Ikki do'kon, har birida bir nechta buyurtma.
    Jami COUNT va SUM SQL GROUP BY siz to'g'ri.
    """
    store_a = await make_store(name="Do'kon A")
    store_b = await make_store(name="Do'kon B")

    await make_order(store_id=store_a.id, total_amount=Decimal("111000.00"))
    await make_order(store_id=store_a.id, total_amount=Decimal("222000.00"))
    await make_order(store_id=store_b.id, total_amount=Decimal("333000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 3
    assert result.total_amount == Decimal("666000.00")


@pytest.mark.asyncio
async def test_sql_agg_multi_agent_scope_sum(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """
    Ikkita agent, har birining do'konlari bor.
    Agent1 faqat o'z ikki do'konining summasi → boshqa agent ko'rinmaydi.
    """
    agent1 = await make_user("agent")
    agent2 = await make_user("agent")

    store_a1 = await make_store(agent_id=agent1.id)
    store_a2 = await make_store(agent_id=agent1.id)
    store_b = await make_store(agent_id=agent2.id)

    # Agent1 ning do'konlari
    await make_order(store_id=store_a1.id, total_amount=Decimal("100000.00"))
    await make_order(store_id=store_a2.id, total_amount=Decimal("200000.00"))
    # Agent2 ning do'koni — ko'rinmasligi kerak
    await make_order(store_id=store_b.id, total_amount=Decimal("999999.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=agent1)

    assert result.total_orders == 2
    assert result.total_amount == Decimal("300000.00")


@pytest.mark.asyncio
async def test_sql_agg_finance_multi_store_sum(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_ledger,
) -> None:
    """
    Uch do'kon, har birida ledger yozuvlari.
    Jami debit/credit SQL GROUP BY orqali to'g'ri.
    """
    store1 = await make_store(name="Meva Do'koni")
    store2 = await make_store(name="Sabzavot Do'koni")
    store3 = await make_store(name="Non Do'koni")

    await make_ledger(store_id=store1.id, entry_type="debit", amount=Decimal("100000.00"))
    await make_ledger(store_id=store1.id, entry_type="credit", amount=Decimal("50000.00"))
    await make_ledger(store_id=store2.id, entry_type="debit", amount=Decimal("200000.00"))
    await make_ledger(store_id=store3.id, entry_type="debit", amount=Decimal("300000.00"))
    await make_ledger(store_id=store3.id, entry_type="credit", amount=Decimal("100000.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    # Jami: debit=600k, credit=150k
    assert result.total_debit == Decimal("600000.00")
    assert result.total_credit == Decimal("150000.00")
    assert result.net_balance == Decimal("450000.00")

    # Har bir do'kon alohida to'g'ri
    store_map = {str(s.store_id): s for s in result.stores}
    s1 = store_map[str(store1.id)]
    assert s1.total_debit == Decimal("100000.00")
    assert s1.total_credit == Decimal("50000.00")

    s3 = store_map[str(store3.id)]
    assert s3.total_debit == Decimal("300000.00")
    assert s3.total_credit == Decimal("100000.00")


# ─── (b) Bo'sh ma'lumotda 0 (NULL emas) — coalesce kafolati ──────────────────


@pytest.mark.asyncio
async def test_sql_agg_empty_sales_returns_zero_not_null(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """
    Hech qanday buyurtma yo'q → total_amount = Decimal('0'), NULL emas.
    SQL SUM(NULL) → NULL bo'lishi mumkin; COALESCE(..., 0) ni tekshiradi.
    """
    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 0
    assert result.total_amount is not None
    assert result.total_amount == Decimal("0")
    assert isinstance(result.total_amount, Decimal)
    assert result.dynamics == []


@pytest.mark.asyncio
async def test_sql_agg_empty_finance_returns_zero_not_null(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
) -> None:
    """
    Do'kon bor lekin ledger yozuvlari yo'q → 0, NULL emas.
    """
    await make_store(name="Bo'sh Do'kon")
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    assert result.total_debit == Decimal("0")
    assert result.total_credit == Decimal("0")
    assert result.net_balance == Decimal("0")
    # Do'kon ro'yxatida 0 li yozuvlar
    for s in result.stores:
        assert s.total_debit == Decimal("0")
        assert s.total_credit == Decimal("0")
        assert isinstance(s.total_debit, Decimal)


@pytest.mark.asyncio
async def test_sql_agg_empty_delivery_returns_zero_not_null(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """
    Hech qanday yetkazish yo'q → barcha count=0, avg=None.
    """
    result = await service.delivery_stats(db=db_session, user=admin_user)

    assert result.total_deliveries == 0
    assert result.delivered_count == 0
    assert result.failed_count == 0
    assert result.in_progress_count == 0
    # Bo'sh bo'lganda avg None bo'lishi kerak
    assert result.avg_delivery_minutes is None


@pytest.mark.asyncio
async def test_sql_agg_sales_group_by_day_empty_zero(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """
    Buyurtma yo'q + group_by=day → dynamics bo'sh ro'yxat, 0 count.
    """
    result = await service.sales_stats(db=db_session, user=admin_user, group_by="day")

    assert result.total_orders == 0
    assert result.total_amount == Decimal("0")
    assert result.dynamics == []


# ─── (c) Dinamika tartibi to'g'ri (ORDER BY period ASC) ──────────────────────


@pytest.mark.asyncio
async def test_sql_agg_dynamics_sorted_by_period_asc(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    group_by=day: dinamika ORDER BY period ASC tartiblangan bo'lishi kerak.
    Buyurtmalar tartibsiz kiritilsa ham natija sanalari o'sish tartibida.
    """
    store = await make_store()

    # Tartibsiz qo'shish
    d3 = datetime(2026, 6, 20, tzinfo=timezone.utc)
    d1 = datetime(2026, 6, 10, tzinfo=timezone.utc)
    d2 = datetime(2026, 6, 15, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("30000.00"), ordered_at=d3)
    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=d1)
    await make_order(store_id=store.id, total_amount=Decimal("20000.00"), ordered_at=d2)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="day")

    assert len(result.dynamics) == 3
    periods = [item.period for item in result.dynamics]
    # Tartiblangan bo'lishi kerak (ASC)
    assert periods == sorted(periods), f"Dinamika tartiblangan emas: {periods}"
    # Birinchi element eng kichik sana
    assert periods[0] == "2026-06-10"
    assert periods[1] == "2026-06-15"
    assert periods[2] == "2026-06-20"


@pytest.mark.asyncio
async def test_sql_agg_dynamics_month_sorted(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    group_by=month: oylar tartiblangan bo'lishi kerak.
    Har oy uchun summa to'g'ri.
    """
    store = await make_store()

    # 3 ta oy (tartibsiz qo'shish)
    aug = datetime(2026, 8, 5, tzinfo=timezone.utc)
    apr = datetime(2026, 4, 20, tzinfo=timezone.utc)
    jun = datetime(2026, 6, 10, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("80000.00"), ordered_at=aug)
    await make_order(store_id=store.id, total_amount=Decimal("40000.00"), ordered_at=apr)
    await make_order(store_id=store.id, total_amount=Decimal("60000.00"), ordered_at=jun)
    # Xuddi iyun oyida yana bir buyurtma
    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=jun)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="month")

    assert len(result.dynamics) == 3
    periods = [item.period for item in result.dynamics]
    assert periods == sorted(periods)
    assert periods[0] == "2026-04"
    assert periods[1] == "2026-06"
    assert periods[2] == "2026-08"

    period_map = {item.period: item for item in result.dynamics}
    # Iyunda 2 ta buyurtma
    assert period_map["2026-06"].order_count == 2
    assert period_map["2026-06"].total_amount == Decimal("70000.00")
    # Avgust va aprelda 1 tadan
    assert period_map["2026-08"].total_amount == Decimal("80000.00")
    assert period_map["2026-04"].total_amount == Decimal("40000.00")


# ─── (d) RBAC scope / IDOR — boshqa filial ma'lumoti oqib chiqmasin ──────────


@pytest.mark.asyncio
async def test_sql_agg_idor_agent_cannot_see_other_branch(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """
    Agent1 filiali A, agent2 filiali B.
    Agent1 faqat o'z filialidagi do'kon buyurtmalarini ko'radi.
    Filial B buyurtmalari ko'rinmaydi (IDOR himoya).
    """
    branch_a = uuid.uuid4()
    branch_b = uuid.uuid4()

    agent1 = await make_user("agent", branch_id=branch_a)
    agent2 = await make_user("agent", branch_id=branch_b)

    store_a = await make_store(agent_id=agent1.id, branch_id=branch_a)
    store_b = await make_store(agent_id=agent2.id, branch_id=branch_b)

    await make_order(store_id=store_a.id, total_amount=Decimal("100000.00"), branch_id=branch_a)
    await make_order(store_id=store_b.id, total_amount=Decimal("999999.00"), branch_id=branch_b)
    await db_session.commit()

    result_agent1 = await service.sales_stats(db=db_session, user=agent1)
    result_agent2 = await service.sales_stats(db=db_session, user=agent2)

    # Agent1 faqat o'z filialini ko'radi
    assert result_agent1.total_orders == 1
    assert result_agent1.total_amount == Decimal("100000.00")

    # Agent2 faqat o'z filialini ko'radi
    assert result_agent2.total_orders == 1
    assert result_agent2.total_amount == Decimal("999999.00")


@pytest.mark.asyncio
async def test_sql_agg_idor_finance_agent_branch_isolation(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_ledger,
) -> None:
    """
    Finance stats: agent o'z do'konlarining ledger ma'lumotini ko'radi.
    Boshqa agentning do'koni ledger yozuvlari OQMAYDI (IDOR).
    """
    agent1 = await make_user("agent")
    agent2 = await make_user("agent")

    store_a = await make_store(agent_id=agent1.id)
    store_b = await make_store(agent_id=agent2.id)

    await make_ledger(store_id=store_a.id, entry_type="debit", amount=Decimal("500000.00"))
    await make_ledger(store_id=store_b.id, entry_type="debit", amount=Decimal("888888.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=agent1)

    # Faqat agent1 ning do'koni ko'rinadi
    assert len(result.stores) == 1
    assert result.stores[0].store_id == store_a.id
    assert result.total_debit == Decimal("500000.00")
    # Agent2 ma'lumoti yo'q
    store_ids = [s.store_id for s in result.stores]
    assert store_b.id not in store_ids


@pytest.mark.asyncio
async def test_sql_agg_idor_store_user_branch_isolation(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """
    Store foydalanuvchisi faqat o'z do'konini ko'radi.
    Boshqa do'kon buyurtmalari OQMAYDI — IDOR himoya.
    """
    store_user = await make_user("store")
    own_store = await make_store(user_id=store_user.id)
    # Boshqa do'kon (boshqa foydalanuvchiga tegishli)
    other_store = await make_store()

    await make_order(store_id=own_store.id, total_amount=Decimal("50000.00"))
    await make_order(store_id=own_store.id, total_amount=Decimal("75000.00"))
    await make_order(store_id=other_store.id, total_amount=Decimal("1000000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=store_user)

    assert result.total_orders == 2
    assert result.total_amount == Decimal("125000.00")
    # 1000000 summa ko'rinmaydi
    assert result.total_amount < Decimal("200000.00")


@pytest.mark.asyncio
async def test_sql_agg_idor_delivery_courier_isolation(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
    make_delivery,
) -> None:
    """
    Kuryer faqat o'z yetkazishlarini ko'radi.
    Boshqa kuryerning yetkazishlari ko'rinmaydi (IDOR).
    """
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")
    store = await make_store()

    order1 = await make_order(store_id=store.id)
    order2 = await make_order(store_id=store.id)
    order3 = await make_order(store_id=store.id)
    await db_session.commit()

    from datetime import timedelta
    now = datetime.now(timezone.utc)

    await make_delivery(
        order_id=order1.id,
        courier_id=courier1.id,
        status="delivered",
        started_at=now - timedelta(hours=2),
        delivered_at=now - timedelta(hours=1),
    )
    await make_delivery(
        order_id=order2.id,
        courier_id=courier1.id,
        status="failed",
    )
    # Kuryer2 ning yetkazishi — courier1 ko'rmasligi kerak
    await make_delivery(
        order_id=order3.id,
        courier_id=courier2.id,
        status="delivered",
    )
    await db_session.commit()

    result = await service.delivery_stats(db=db_session, user=courier1)

    # Faqat courier1 ning 2 ta yetkazishi
    assert result.total_deliveries == 2
    assert result.delivered_count == 1
    assert result.failed_count == 1
    # courier2 ning yetkazishi ko'rinmaydi


@pytest.mark.asyncio
async def test_sql_agg_admin_branch_filter_idor(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    Admin branch_id filtri: faqat ko'rsatilgan filialdagi buyurtmalar ko'rinadi.
    Boshqa filial buyurtmalari oqib chiqmaydi.
    """
    branch_x = uuid.uuid4()
    branch_y = uuid.uuid4()

    store_x = await make_store(branch_id=branch_x)
    store_y = await make_store(branch_id=branch_y)

    await make_order(store_id=store_x.id, total_amount=Decimal("100000.00"), branch_id=branch_x)
    await make_order(store_id=store_x.id, total_amount=Decimal("200000.00"), branch_id=branch_x)
    await make_order(store_id=store_y.id, total_amount=Decimal("999000.00"), branch_id=branch_y)
    await db_session.commit()

    # Faqat filial X ni ko'rish
    result = await service.sales_stats(
        db=db_session,
        user=admin_user,
        branch_id=str(branch_x),
    )

    assert result.total_orders == 2
    assert result.total_amount == Decimal("300000.00")
    # Filial Y ko'rinmaydi
    assert result.total_amount < Decimal("999000.00")


# ─── Qo'shimcha: group_by=week bo'sh natija ──────────────────────────────────


@pytest.mark.asyncio
async def test_sql_agg_group_by_week_correct_grouping(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    group_by=week: bir hafta ichidagi buyurtmalar bir gruppaga tushadi.
    Har bir hafta yig'indisi to'g'ri.
    """
    store = await make_store()

    # Hafta 23 (2026-06-08 dushanba → 2026-06-14 yakshanba)
    w23_mon = datetime(2026, 6, 8, tzinfo=timezone.utc)
    w23_fri = datetime(2026, 6, 12, tzinfo=timezone.utc)
    # Hafta 24
    w24_tue = datetime(2026, 6, 16, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=w23_mon)
    await make_order(store_id=store.id, total_amount=Decimal("20000.00"), ordered_at=w23_fri)
    await make_order(store_id=store.id, total_amount=Decimal("30000.00"), ordered_at=w24_tue)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="week")

    assert len(result.dynamics) == 2
    # Hafta 23: 2 buyurtma, 30000
    # Hafta 24: 1 buyurtma, 30000
    period_map = {item.period: item for item in result.dynamics}

    # Periods tartiblangan bo'lishi kerak
    periods = list(period_map.keys())
    assert periods == sorted(periods)

    # Har bir hafta uchun summa to'g'ri
    w23_key = result.dynamics[0].period
    w24_key = result.dynamics[1].period
    assert result.dynamics[0].order_count == 2
    assert result.dynamics[0].total_amount == Decimal("30000.00")
    assert result.dynamics[1].order_count == 1
    assert result.dynamics[1].total_amount == Decimal("30000.00")


# ─── Decimal aniqlik: SQL SUM ham Decimal qaytarishi kerak ────────────────────


@pytest.mark.asyncio
async def test_sql_agg_decimal_precision_in_sql_sum(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """
    SQL SUM Numeric(18,2) ustunida Decimal aniqligini saqlaydi.
    1000 ta 0.01 → 10.00 (float'da emas Decimal'da).
    """
    store = await make_store()

    for _ in range(1000):
        await make_order(store_id=store.id, total_amount=Decimal("0.01"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 1000
    # Float: 1000 * 0.01 = 9.999999... bo'lishi mumkin
    # Decimal: aniq 10.00
    assert result.total_amount == Decimal("10.00")
    assert isinstance(result.total_amount, Decimal)


@pytest.mark.asyncio
async def test_sql_agg_finance_decimal_precision(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_ledger,
) -> None:
    """
    Finance SQL SUM: 100 ta 0.01 → 1.00 aniq (float xatosiz).
    """
    store = await make_store()

    for _ in range(100):
        await make_ledger(
            store_id=store.id,
            entry_type="debit",
            amount=Decimal("0.01"),
        )
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    assert result.total_debit == Decimal("1.00")
    assert isinstance(result.total_debit, Decimal)


# ─── AgentStore orqali biriktirilgan do'kon ham ko'rinadi ────────────────────


@pytest.mark.asyncio
async def test_sql_agg_agent_store_table_scope_with_group_by(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """
    Agent AgentStore orqali biriktirilgan do'konga ham group_by ishlatilsa,
    barcha buyurtmalar to'g'ri guruhlarda ko'rinadi.
    """
    agent = await make_user("agent")
    store = await make_store()  # agent_id yo'q

    # AgentStore orqali biriktirish
    agent_store = AgentStore(
        agent_id=agent.id,
        store_id=store.id,
        assigned_at=datetime.now(timezone.utc),
    )
    db_session.add(agent_store)
    await db_session.flush()

    day1 = datetime(2026, 5, 1, tzinfo=timezone.utc)
    day2 = datetime(2026, 6, 1, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=day1)
    await make_order(store_id=store.id, total_amount=Decimal("20000.00"), ordered_at=day2)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=agent, group_by="month")

    assert result.total_orders == 2
    assert result.total_amount == Decimal("30000.00")
    assert len(result.dynamics) == 2

    period_map = {item.period: item for item in result.dynamics}
    assert "2026-05" in period_map
    assert "2026-06" in period_map
    assert period_map["2026-05"].total_amount == Decimal("10000.00")
    assert period_map["2026-06"].total_amount == Decimal("20000.00")
