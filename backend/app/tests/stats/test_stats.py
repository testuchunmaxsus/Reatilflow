"""
Statistika moduli testlari — T22.

Test kategoriyalari:
  1. sales_stats: buyurtmalar → jami count/summa to'g'ri (Decimal); davr guruhlash
  2. delivery_stats: yetkazishlar → status count, o'rtacha vaqt
  3. finance_stats: ledger → qarz/haqdorlik summasi (PRIMARY DB simulatsiya)
  4. Scope/IDOR:
     - agent faqat o'z buyurtmalari statistikasi
     - do'kon (store) o'ziniki
     - admin barchasi
     - kuryer o'z yetkazishlari
  5. RBAC: courier → finance endpoint 403
  6. invalid period (from > to) → 422
  7. Bo'sh natija (0 buyurtma)
  8. Decimal aniqligi
  9. i18n: uz/ru xabarlar
  10. Read replica simulatsiya (stats_client fixture izohida)

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import AgentStore
from app.models.user import AppUser
from app.modules.stats import service
from app.tests.stats.conftest import get_token


# ─── 1. Sales stats: jami count/summa ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_stats_total_count_and_amount(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """Bir nechta buyurtma → jami count va summa to'g'ri (Decimal)."""
    store = await make_store()

    await make_order(store_id=store.id, total_amount=Decimal("100000.00"))
    await make_order(store_id=store.id, total_amount=Decimal("200000.00"))
    await make_order(store_id=store.id, total_amount=Decimal("50000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 3
    # Decimal aniqlik: float yig'ish xatosi yo'q
    assert result.total_amount == Decimal("350000.00")


@pytest.mark.asyncio
async def test_sales_stats_empty_result(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """Buyurtma yo'q → bo'sh natija (0 count, 0 summa)."""
    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 0
    assert result.total_amount == Decimal("0")
    assert result.dynamics == []


# ─── 2. Sales stats: davr guruhlash ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_stats_group_by_day(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """group_by=day: har kun alohida gruppa."""
    store = await make_store()

    day1 = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=day1)
    await make_order(store_id=store.id, total_amount=Decimal("20000.00"), ordered_at=day1)
    await make_order(store_id=store.id, total_amount=Decimal("30000.00"), ordered_at=day2)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="day")

    assert len(result.dynamics) == 2
    assert result.group_by == "day"

    # 1-kun: 2 buyurtma, 30000
    period_map = {item.period: item for item in result.dynamics}
    assert "2026-06-01" in period_map
    assert period_map["2026-06-01"].order_count == 2
    assert period_map["2026-06-01"].total_amount == Decimal("30000.00")

    # 2-kun: 1 buyurtma, 30000
    assert "2026-06-02" in period_map
    assert period_map["2026-06-02"].order_count == 1
    assert period_map["2026-06-02"].total_amount == Decimal("30000.00")


@pytest.mark.asyncio
async def test_sales_stats_group_by_month(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """group_by=month: oy bo'yicha guruhlash."""
    store = await make_store()

    june = datetime(2026, 6, 15, tzinfo=timezone.utc)
    july = datetime(2026, 7, 5, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("50000.00"), ordered_at=june)
    await make_order(store_id=store.id, total_amount=Decimal("70000.00"), ordered_at=july)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="month")

    assert len(result.dynamics) == 2
    period_map = {item.period: item for item in result.dynamics}
    assert "2026-06" in period_map
    assert "2026-07" in period_map
    assert period_map["2026-06"].total_amount == Decimal("50000.00")
    assert period_map["2026-07"].total_amount == Decimal("70000.00")


# ─── 3. Delivery stats: status count ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_stats_status_counts(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
    make_delivery,
    courier_user: AppUser,
) -> None:
    """Yetkazishlar → delivered, failed, in_progress count to'g'ri."""
    store = await make_store()
    order1 = await make_order(store_id=store.id)
    order2 = await make_order(store_id=store.id)
    order3 = await make_order(store_id=store.id)
    order4 = await make_order(store_id=store.id)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    # 2 ta delivered
    await make_delivery(
        order_id=order1.id,
        courier_id=courier_user.id,
        status="delivered",
        started_at=now - timedelta(hours=2),
        delivered_at=now - timedelta(hours=1),
    )
    await make_delivery(
        order_id=order2.id,
        courier_id=courier_user.id,
        status="delivered",
        started_at=now - timedelta(hours=4),
        delivered_at=now - timedelta(hours=3),
    )
    # 1 ta failed
    await make_delivery(
        order_id=order3.id,
        courier_id=courier_user.id,
        status="failed",
    )
    # 1 ta in_progress (assigned)
    await make_delivery(
        order_id=order4.id,
        courier_id=courier_user.id,
        status="assigned",
    )
    await db_session.commit()

    result = await service.delivery_stats(db=db_session, user=admin_user)

    assert result.total_deliveries == 4
    assert result.delivered_count == 2
    assert result.failed_count == 1
    assert result.in_progress_count == 1


# ─── 4. Delivery stats: o'rtacha vaqt ────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_stats_avg_time(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
    make_delivery,
    courier_user: AppUser,
) -> None:
    """O'rtacha yetkazish vaqti to'g'ri hisoblanadi."""
    store = await make_store()
    order1 = await make_order(store_id=store.id)
    order2 = await make_order(store_id=store.id)
    await db_session.commit()

    base = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    # 1-yetkazish: 60 daqiqa
    await make_delivery(
        order_id=order1.id,
        courier_id=courier_user.id,
        status="delivered",
        started_at=base,
        delivered_at=base + timedelta(minutes=60),
    )
    # 2-yetkazish: 120 daqiqa
    await make_delivery(
        order_id=order2.id,
        courier_id=courier_user.id,
        status="delivered",
        started_at=base,
        delivered_at=base + timedelta(minutes=120),
    )
    await db_session.commit()

    result = await service.delivery_stats(db=db_session, user=admin_user)

    assert result.delivered_count == 2
    # O'rtacha: (60 + 120) / 2 = 90 daqiqa
    assert result.avg_delivery_minutes == Decimal("90.0")


@pytest.mark.asyncio
async def test_delivery_stats_avg_time_none_when_no_delivered(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
    make_delivery,
    courier_user: AppUser,
) -> None:
    """delivered holat yo'q bo'lsa avg_delivery_minutes = None."""
    store = await make_store()
    order = await make_order(store_id=store.id)
    await db_session.commit()

    await make_delivery(
        order_id=order.id,
        courier_id=courier_user.id,
        status="failed",
    )
    await db_session.commit()

    result = await service.delivery_stats(db=db_session, user=admin_user)

    assert result.avg_delivery_minutes is None


# ─── 5. Finance stats: ledger yig'indi ───────────────────────────────────────


@pytest.mark.asyncio
async def test_finance_stats_debit_credit_sum(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_ledger,
) -> None:
    """Ledger yozuvlaridan qarz/haqdorlik summasi to'g'ri (PRIMARY DB simulatsiya)."""
    store = await make_store()

    await make_ledger(store_id=store.id, entry_type="debit", amount=Decimal("500000.00"))
    await make_ledger(store_id=store.id, entry_type="debit", amount=Decimal("200000.00"))
    await make_ledger(store_id=store.id, entry_type="credit", amount=Decimal("150000.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    assert result.total_debit == Decimal("700000.00")
    assert result.total_credit == Decimal("150000.00")
    assert result.net_balance == Decimal("550000.00")


@pytest.mark.asyncio
async def test_finance_stats_store_details(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_ledger,
) -> None:
    """Do'kon bo'yicha batafsil moliyaviy ma'lumot."""
    store1 = await make_store(name="Do'kon 1")
    store2 = await make_store(name="Do'kon 2")

    await make_ledger(store_id=store1.id, entry_type="debit", amount=Decimal("100000.00"))
    await make_ledger(store_id=store2.id, entry_type="debit", amount=Decimal("200000.00"))
    await make_ledger(store_id=store2.id, entry_type="credit", amount=Decimal("50000.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    store_map = {str(s.store_id): s for s in result.stores}
    assert str(store1.id) in store_map
    assert str(store2.id) in store_map

    s1 = store_map[str(store1.id)]
    assert s1.total_debit == Decimal("100000.00")
    assert s1.total_credit == Decimal("0")

    s2 = store_map[str(store2.id)]
    assert s2.total_debit == Decimal("200000.00")
    assert s2.total_credit == Decimal("50000.00")


# ─── 6. Scope/IDOR: agent faqat o'z buyurtmalari ─────────────────────────────


@pytest.mark.asyncio
async def test_sales_scope_agent_only_own_stores(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """Agent faqat o'z do'konlari buyurtmalarini ko'radi."""
    agent1 = await make_user("agent")
    agent2 = await make_user("agent")

    store1 = await make_store(agent_id=agent1.id)
    store2 = await make_store(agent_id=agent2.id)

    await make_order(store_id=store1.id, total_amount=Decimal("100000.00"))
    await make_order(store_id=store1.id, total_amount=Decimal("50000.00"))
    await make_order(store_id=store2.id, total_amount=Decimal("999999.00"))  # agent2 ning
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=agent1)

    # Agent1 faqat o'z 2 ta buyurtmasini ko'radi (store2 ning buyurtmasi ko'rinmaydi)
    assert result.total_orders == 2
    assert result.total_amount == Decimal("150000.00")


@pytest.mark.asyncio
async def test_sales_scope_agent_agent_store_table(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """Agent AgentStore orqali biriktirilgan do'konlarni ham ko'radi."""
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

    await make_order(store_id=store.id, total_amount=Decimal("77000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=agent)

    assert result.total_orders == 1
    assert result.total_amount == Decimal("77000.00")


@pytest.mark.asyncio
async def test_sales_scope_store_role_own_only(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """Store roli faqat o'z do'konining buyurtmalarini ko'radi."""
    store_user = await make_user("store")
    own_store = await make_store(user_id=store_user.id)
    other_store = await make_store()

    await make_order(store_id=own_store.id, total_amount=Decimal("10000.00"))
    await make_order(store_id=own_store.id, total_amount=Decimal("20000.00"))
    await make_order(store_id=other_store.id, total_amount=Decimal("99999.00"))  # boshqa do'kon
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=store_user)

    assert result.total_orders == 2
    assert result.total_amount == Decimal("30000.00")


@pytest.mark.asyncio
async def test_sales_scope_admin_sees_all(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """Admin barcha do'konlarning buyurtmalarini ko'radi."""
    store1 = await make_store(name="Do'kon A")
    store2 = await make_store(name="Do'kon B")

    await make_order(store_id=store1.id, total_amount=Decimal("100000.00"))
    await make_order(store_id=store2.id, total_amount=Decimal("200000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 2
    assert result.total_amount == Decimal("300000.00")


@pytest.mark.asyncio
async def test_sales_scope_agent_cannot_see_other_agent_data(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
) -> None:
    """Agent boshqa agentning do'koni statistikasini ko'ra olmaydi (IDOR himoya)."""
    agent1 = await make_user("agent")
    agent2 = await make_user("agent")

    store_agent2 = await make_store(agent_id=agent2.id)
    await make_order(store_id=store_agent2.id, total_amount=Decimal("500000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=agent1)

    # Agent1 agent2 ning do'koni ma'lumotini ko'ra olmaydi
    assert result.total_orders == 0
    assert result.total_amount == Decimal("0")


# ─── 7. Scope/IDOR: courier faqat o'z yetkazishlari ─────────────────────────


@pytest.mark.asyncio
async def test_delivery_scope_courier_own_only(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
    make_delivery,
) -> None:
    """Kuryer faqat o'z yetkazishlari statistikasini ko'radi."""
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")

    store = await make_store()
    order1 = await make_order(store_id=store.id)
    order2 = await make_order(store_id=store.id)
    order3 = await make_order(store_id=store.id)
    await db_session.commit()

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
    await make_delivery(
        order_id=order3.id,
        courier_id=courier2.id,  # boshqa kuryer
        status="delivered",
    )
    await db_session.commit()

    result = await service.delivery_stats(db=db_session, user=courier1)

    # courier1 faqat o'z 2 ta yetkazishini ko'radi
    assert result.total_deliveries == 2
    assert result.delivered_count == 1
    assert result.failed_count == 1


# ─── 8. Finance scope: store faqat o'z balansi ───────────────────────────────


@pytest.mark.asyncio
async def test_finance_scope_store_own_only(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_ledger,
) -> None:
    """Do'kon faqat o'z moliyaviy ma'lumotini ko'radi."""
    store_user = await make_user("store")
    own_store = await make_store(user_id=store_user.id)
    other_store = await make_store()

    await make_ledger(store_id=own_store.id, entry_type="debit", amount=Decimal("300000.00"))
    await make_ledger(store_id=other_store.id, entry_type="debit", amount=Decimal("999999.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=store_user)

    # Faqat o'z do'konini ko'radi
    assert len(result.stores) == 1
    assert result.stores[0].store_id == own_store.id
    assert result.total_debit == Decimal("300000.00")


@pytest.mark.asyncio
async def test_finance_scope_agent_own_stores(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_ledger,
) -> None:
    """Agent faqat o'z do'konlarining moliyaviy ma'lumotini ko'radi."""
    agent = await make_user("agent")
    own_store = await make_store(agent_id=agent.id)
    other_store = await make_store()

    await make_ledger(store_id=own_store.id, entry_type="debit", amount=Decimal("100000.00"))
    await make_ledger(store_id=other_store.id, entry_type="debit", amount=Decimal("888888.00"))
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=agent)

    # Agent faqat o'z do'konini ko'radi
    assert len(result.stores) == 1
    assert result.stores[0].store_id == own_store.id
    assert result.total_debit == Decimal("100000.00")


# ─── 9. RBAC: courier → finance stats 403 ────────────────────────────────────


@pytest.mark.asyncio
async def test_finance_endpoint_courier_403(
    stats_client: AsyncClient,
    courier_user: AppUser,
) -> None:
    """Courier finance stats endpointini ko'ra olmaydi → 403."""
    token = await get_token(stats_client, courier_user)
    resp = await stats_client.get(
        "/stats/finance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 10. invalid period → 422 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_invalid_period_422(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """from > to → 422 (stats.invalid_period)."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        params={"from": "2026-06-30T00:00:00Z", "to": "2026-06-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["message_key"] == "stats.invalid_period"


@pytest.mark.asyncio
async def test_delivery_invalid_period_422(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """Delivery: from > to → 422."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/delivery",
        params={"from": "2026-12-31T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["message_key"] == "stats.invalid_period"


@pytest.mark.asyncio
async def test_finance_invalid_period_422(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """Finance: from > to → 422."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/finance",
        params={"from": "2026-12-31T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["message_key"] == "stats.invalid_period"


# ─── 11. invalid group_by → 422 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_invalid_group_by_422(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """Yaroqsiz group_by → 422 (stats.invalid_group_by)."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        params={"group_by": "quarter"},  # noto'g'ri qiymat
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["message_key"] == "stats.invalid_group_by"


# ─── 12. i18n: uz/ru xabarlar ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_period_i18n_uz(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """i18n uz: stats.invalid_period xabar o'zbek tilida."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        params={"from": "2026-12-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "uz",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "boshlanish" in body["message"].lower() or "tugash" in body["message"].lower()


@pytest.mark.asyncio
async def test_invalid_period_i18n_ru(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """i18n ru: stats.invalid_period xabar rus tilida."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        params={"from": "2026-12-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "период" in body["message"].lower() or "дата" in body["message"].lower()


@pytest.mark.asyncio
async def test_invalid_group_by_i18n_uz(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """i18n uz: stats.invalid_group_by xabar o'zbek tilida."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        params={"group_by": "yearly"},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "uz",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["message_key"] == "stats.invalid_group_by"
    assert "day" in body["message"] or "guruhlash" in body["message"].lower()


# ─── 13. Decimal aniqligi ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decimal_precision_sales(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """Decimal: float yig'ish xatosi yo'q (masalan 0.1 + 0.2 = 0.3)."""
    store = await make_store()

    # Ko'p kichik qiymatlar — float'da xato, Decimal'da to'g'ri
    amounts = [Decimal("0.01")] * 100  # 100 × 0.01 = 1.00
    for a in amounts:
        await make_order(store_id=store.id, total_amount=a)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user)

    assert result.total_orders == 100
    assert result.total_amount == Decimal("1.00")


@pytest.mark.asyncio
async def test_decimal_precision_finance(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_ledger,
) -> None:
    """Finance Decimal: kichik qiymatlar to'g'ri yig'iladi."""
    store = await make_store()

    for _ in range(10):
        await make_ledger(
            store_id=store.id,
            entry_type="debit",
            amount=Decimal("0.01"),
        )
    await db_session.commit()

    result = await service.finance_stats(db=db_session, user=admin_user)

    assert result.total_debit == Decimal("0.10")


# ─── 14. HTTP endpoint testlar ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_endpoint_returns_200(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """GET /stats/sales → 200."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/sales",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_orders" in body
    assert "total_amount" in body
    assert "dynamics" in body


@pytest.mark.asyncio
async def test_delivery_endpoint_returns_200(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """GET /stats/delivery → 200."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/delivery",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_deliveries" in body
    assert "delivered_count" in body
    assert "avg_delivery_minutes" in body


@pytest.mark.asyncio
async def test_finance_endpoint_returns_200_admin(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """GET /stats/finance → 200 (admin)."""
    token = await get_token(stats_client, admin_user)
    resp = await stats_client.get(
        "/stats/finance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_debit" in body
    assert "total_credit" in body
    assert "net_balance" in body
    assert "stores" in body


@pytest.mark.asyncio
async def test_sales_endpoint_unauthenticated_401(
    stats_client: AsyncClient,
) -> None:
    """Token yo'q → 401."""
    resp = await stats_client.get("/stats/sales")
    assert resp.status_code == 401


# ─── 15. Read replica izohli test ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replica_vs_primary_dependency_routing(
    stats_client: AsyncClient,
    admin_user: AppUser,
) -> None:
    """
    Test muhitida get_db_replica() va get_db() bir xil sessiyaga ulanadi
    (stats_client fixture override qiladi).

    Haqiqiy produksiyada:
      - GET /stats/sales, /stats/delivery → get_db_replica() → replica engine
      - GET /stats/finance → get_db() → primary engine (ADR §3.8)

    Bu test ikkala endpoint ham ishlashini (200 qaytarishini) tekshiradi.
    Replica vs primary farqi integration testda tekshiriladi.
    """
    token = await get_token(stats_client, admin_user)

    # Non-financial → replica (test'da primary bilan bir xil)
    resp_sales = await stats_client.get(
        "/stats/sales",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_sales.status_code == 200

    # Financial → primary (ADR §3.8)
    resp_finance = await stats_client.get(
        "/stats/finance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_finance.status_code == 200


# ─── 16. Period filtr ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_period_filter(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """Vaqt filtr: faqat belgilangan davrdagi buyurtmalar ko'rinadi."""
    store = await make_store()

    may = datetime(2026, 5, 15, tzinfo=timezone.utc)
    june = datetime(2026, 6, 15, tzinfo=timezone.utc)
    july = datetime(2026, 7, 15, tzinfo=timezone.utc)

    await make_order(store_id=store.id, total_amount=Decimal("100.00"), ordered_at=may)
    await make_order(store_id=store.id, total_amount=Decimal("200.00"), ordered_at=june)
    await make_order(store_id=store.id, total_amount=Decimal("300.00"), ordered_at=july)
    await db_session.commit()

    # Faqat iyun: 1 ta buyurtma
    result = await service.sales_stats(
        db=db_session,
        user=admin_user,
        from_dt=datetime(2026, 6, 1, tzinfo=timezone.utc),
        to_dt=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )

    assert result.total_orders == 1
    assert result.total_amount == Decimal("200.00")


# ─── 17. Courier savdo statistikasida bo'sh qaytarish ─────────────────────────


@pytest.mark.asyncio
async def test_sales_courier_returns_empty(
    db_session: AsyncSession,
    courier_user: AppUser,
    make_store,
    make_order,
) -> None:
    """Courier savdo statistikasini ko'ra olmaydi — bo'sh natija qaytadi."""
    store = await make_store()
    await make_order(store_id=store.id, total_amount=Decimal("100000.00"))
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=courier_user)

    # Courier scope yo'q — bo'sh qaytadi (403 emas, chunki stats:view ruxsati bor)
    assert result.total_orders == 0
    assert result.total_amount == Decimal("0")


# ─── 18. group_by=week ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_group_by_week(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_order,
) -> None:
    """group_by=week: hafta bo'yicha guruhlash to'g'ri."""
    store = await make_store()

    # Bir xil hafta ichidagi ikki kun
    mon = datetime(2026, 6, 8, tzinfo=timezone.utc)   # hafta 23
    wed = datetime(2026, 6, 10, tzinfo=timezone.utc)  # hafta 23
    # Keyingi hafta
    next_mon = datetime(2026, 6, 15, tzinfo=timezone.utc)  # hafta 24

    await make_order(store_id=store.id, total_amount=Decimal("10000.00"), ordered_at=mon)
    await make_order(store_id=store.id, total_amount=Decimal("20000.00"), ordered_at=wed)
    await make_order(store_id=store.id, total_amount=Decimal("30000.00"), ordered_at=next_mon)
    await db_session.commit()

    result = await service.sales_stats(db=db_session, user=admin_user, group_by="week")

    assert len(result.dynamics) == 2
    # Jami summa to'g'ri
    assert result.total_amount == Decimal("60000.00")
