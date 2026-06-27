"""
AI Tahlil moduli testlari — Faza 4.

Test kategoriyalari:
  1. Scope/IDOR:
     - Korxona FAQAT o'z mahsulotlari bo'yicha ko'radi
     - Korxona FAQAT shartnoma qilgan do'konlarini ko'radi
     - Boshqa korxona mahsuloti/do'koni ko'rinmaydi
  2. overview: KPI kartalar to'g'ri (contracted_store_count, sold_qty, expiry_risk)
  3. contracted_stores: do'konlar ro'yxati + holat + inventar + sotuv
  4. geo_velocity: GPS koordinatalar, velocity hisoblash
  5. expiry_report: days_left, severity, within_days filtr
  6. product_ranking: top/bottom, 0-sotuvli mahsulotlar
  7. recommendations: R1-R5 qoidalari (deterministik)
  8. RBAC: agent/courier/store → 403; admin/accountant → 200
  9. superadmin → bo'sh natija
  10. invalid_period → 422
  11. NULL/coalesce: sotuv yo'q → Decimal(0)
  12. ai_enrich: API key yo'q → (None, False) (graceful degrade)

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AppUser
from app.modules.analytics import service
from app.modules.analytics.recommendations import generate_recommendations
from app.modules.analytics.ai_enrich import enrich_with_ai
from app.modules.analytics.schemas import (
    ExpiryItem,
    GeoVelocityItem,
    ProductRankingItem,
)
from app.tests.analytics.conftest import OTHER_ENTERPRISE_UUID, get_token
from app.tests.conftest import TEST_ENTERPRISE_UUID


# ─── 1. Scope/IDOR: bo'sh ma'lumot (do'kon/mahsulot yo'q) ────────────────────


@pytest.mark.asyncio
async def test_overview_no_contracts(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """Shartnoma yo'q → overview bo'sh natija qaytaradi."""
    result = await service.overview(
        db=db_session,
        enterprise_id=admin_user.enterprise_id,
    )
    assert result.contracted_store_count == 0
    assert result.sold_qty_total == Decimal("0")
    assert result.revenue_total == Decimal("0")
    assert result.expiry_risk_count == 0
    assert result.contract_status.active == 0


@pytest.mark.asyncio
async def test_geo_velocity_no_data(
    db_session: AsyncSession,
    admin_user: AppUser,
) -> None:
    """Do'kon/mahsulot yo'q → geo_velocity bo'sh natija."""
    result = await service.geo_velocity(
        db=db_session,
        enterprise_id=admin_user.enterprise_id,
    )
    assert result.items == []
    assert result.period_days >= 1


# ─── 2. Overview: KPI kartalar to'g'ri ───────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_with_data(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_product,
    make_contract,
    make_pos_sale,
    make_inventory,
    default_enterprise,
) -> None:
    """Shartnoma + sotuv → overview to'g'ri KPI qaytaradi."""
    store = await make_store(name="Asosiy Do'kon")
    product = await make_product(name_uz="Test Mahsulot A")

    # Shartnoma: korxona supplier sifatida
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    # POS sotuv
    await make_pos_sale(
        store_id=store.id,
        lines=[(product.id, Decimal("10"), Decimal("5000"))],
    )
    await db_session.commit()

    result = await service.overview(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    assert result.contracted_store_count == 1
    assert result.sold_qty_total == Decimal("10")
    assert result.revenue_total == Decimal("50000")
    assert result.contract_status.active == 1


@pytest.mark.asyncio
async def test_overview_contract_status_counts(
    db_session: AsyncSession,
    make_store,
    make_contract,
    default_enterprise,
) -> None:
    """Faol + tugayotgan shartnomalar to'g'ri sanab chiqiladi."""
    today = datetime.now(timezone.utc).date()

    store_active = await make_store(name="Faol Do'kon")
    store_expiring = await make_store(name="Tugayotgan Do'kon")

    # Faol shartnoma (90 kun qolgan)
    await make_contract(
        store_id=store_active.id,
        supplier_enterprise_id=default_enterprise.id,
        valid_to=today + timedelta(days=90),
    )
    # Tugayotgan shartnoma (15 kun qolgan)
    await make_contract(
        store_id=store_expiring.id,
        supplier_enterprise_id=default_enterprise.id,
        valid_to=today + timedelta(days=15),
    )
    await db_session.commit()

    result = await service.overview(db=db_session, enterprise_id=default_enterprise.id)
    assert result.contracted_store_count == 2
    assert result.contract_status.active == 1
    assert result.contract_status.expiring == 1
    assert result.contract_status.expired == 0


# ─── 3. IDOR: boshqa korxona mahsuloti ko'rinmaydi ──────────────────────────


@pytest.mark.asyncio
async def test_idor_other_enterprise_products_not_visible(
    db_session: AsyncSession,
    admin_user: AppUser,
    make_store,
    make_product,
    make_contract,
    make_pos_sale,
    default_enterprise,
    other_enterprise,
) -> None:
    """Boshqa korxona mahsuloti sotuvi ko'rinmasligi kerak."""
    store = await make_store(name="Do'kon IDOR")

    # Shartnoma: default_enterprise supplier
    await make_contract(
        store_id=store.id,
        supplier_enterprise_id=default_enterprise.id,
    )

    # Boshqa korxona mahsuloti
    other_product = await make_product(
        name_uz="Boshqa Korxona Mahsuloti",
        enterprise_id=other_enterprise.id,
    )

    # Sotuv: boshqa korxona mahsuloti
    await make_pos_sale(
        store_id=store.id,
        lines=[(other_product.id, Decimal("50"), Decimal("1000"))],
    )
    await db_session.commit()

    # default_enterprise uchun → bu sotuv ko'rinmasligi kerak
    result = await service.overview(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    # Mahsulot product_ids da yo'q → sold_qty = 0
    assert result.sold_qty_total == Decimal("0")


@pytest.mark.asyncio
async def test_idor_uncontracted_store_not_visible(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_pos_sale,
    default_enterprise,
) -> None:
    """Shartnoma qilinmagan do'kondagi sotuv ko'rinmasligi kerak."""
    # Do'kon bor, lekin shartnoma YO'Q
    store_no_contract = await make_store(name="Shartnomasiz Do'kon")
    product = await make_product(name_uz="Mahsulot B")

    await make_pos_sale(
        store_id=store_no_contract.id,
        lines=[(product.id, Decimal("20"), Decimal("2000"))],
    )
    await db_session.commit()

    result = await service.overview(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    assert result.contracted_store_count == 0
    assert result.sold_qty_total == Decimal("0")


# ─── 4. Geo velocity ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_geo_velocity_with_gps(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_pos_sale,
    default_enterprise,
) -> None:
    """GPS koordinatalar va velocity to'g'ri hisoblanadi."""
    store = await make_store(
        name="GPS Do'kon",
        gps_lat=Decimal("41.2995"),
        gps_lng=Decimal("69.2401"),
        address="Toshkent, Chilonzor",
    )
    product = await make_product()
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    # 10 dona sotuv
    await make_pos_sale(
        store_id=store.id,
        lines=[(product.id, Decimal("10"), Decimal("5000"))],
    )
    await db_session.commit()

    result = await service.geo_velocity(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item.store_id == store.id
    assert item.gps_lat is not None
    assert item.gps_lng is not None
    assert item.sold_qty == Decimal("10")
    assert item.velocity_per_day > 0


# ─── 5. Expiry Report ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expiry_urgent_severity(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_inventory,
    default_enterprise,
) -> None:
    """days_left <= 7 → severity=urgent."""
    today = datetime.now(timezone.utc).date()
    store = await make_store()
    product = await make_product()
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    await make_inventory(
        store_id=store.id,
        product_id=product.id,
        qty=Decimal("5"),
        expiry_date=today + timedelta(days=3),  # 3 kun qolgan → urgent
    )
    await db_session.commit()

    result = await service.expiry_report(
        db=db_session,
        enterprise_id=default_enterprise.id,
        within_days=30,
    )
    assert result.total == 1
    item = result.items[0]
    assert item.severity == "urgent"
    assert item.days_left == 3
    assert item.product_id == product.id


@pytest.mark.asyncio
async def test_expiry_warning_severity(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_inventory,
    default_enterprise,
) -> None:
    """7 < days_left <= 30 → severity=warning."""
    today = datetime.now(timezone.utc).date()
    store = await make_store()
    product = await make_product()
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    await make_inventory(
        store_id=store.id,
        product_id=product.id,
        expiry_date=today + timedelta(days=20),
    )
    await db_session.commit()

    result = await service.expiry_report(
        db=db_session,
        enterprise_id=default_enterprise.id,
        within_days=30,
    )
    assert result.total == 1
    assert result.items[0].severity == "warning"


@pytest.mark.asyncio
async def test_expiry_within_days_filter(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_inventory,
    default_enterprise,
) -> None:
    """within_days=7 bo'lganda faqat 7 kun ichidagilar ko'rinadi."""
    today = datetime.now(timezone.utc).date()
    store = await make_store()
    product1 = await make_product(name_uz="Tez tugaydigan")
    product2 = await make_product(name_uz="Uzoq tugaydigan")
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    await make_inventory(
        store_id=store.id, product_id=product1.id, expiry_date=today + timedelta(days=3)
    )
    await make_inventory(
        store_id=store.id, product_id=product2.id, expiry_date=today + timedelta(days=20)
    )
    await db_session.commit()

    result = await service.expiry_report(
        db=db_session,
        enterprise_id=default_enterprise.id,
        within_days=7,
    )
    assert result.total == 1
    assert result.items[0].product_id == product1.id


@pytest.mark.asyncio
async def test_expiry_idor_other_enterprise(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_inventory,
    default_enterprise,
    other_enterprise,
) -> None:
    """Boshqa korxona mahsulotining expiry ko'rinmasligi kerak."""
    today = datetime.now(timezone.utc).date()
    store = await make_store()
    # Boshqa korxona mahsuloti
    other_product = await make_product(
        name_uz="Boshqa mahsulot", enterprise_id=other_enterprise.id
    )
    # Shartnoma bor (default_enterprise supplier)
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)
    # Inventar: boshqa korxona mahsuloti (StoreInventory.enterprise_id = default, lekin product boshqaniki)
    await make_inventory(
        store_id=store.id,
        product_id=other_product.id,
        expiry_date=today + timedelta(days=3),
        enterprise_id=default_enterprise.id,
    )
    await db_session.commit()

    result = await service.expiry_report(
        db=db_session,
        enterprise_id=default_enterprise.id,
        within_days=30,
    )
    # Mahsulot product_ids da yo'q (boshqa enterprise) → ko'rinmaydi
    assert result.total == 0


# ─── 6. Product Ranking ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_ranking_top(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_pos_sale,
    default_enterprise,
) -> None:
    """Top 2 mahsulot to'g'ri tartibda qaytadi."""
    store = await make_store()
    product_a = await make_product(name_uz="Ko'p Sotiladi")
    product_b = await make_product(name_uz="Kam Sotiladi")
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    await make_pos_sale(
        store_id=store.id,
        lines=[(product_a.id, Decimal("50"), Decimal("1000"))],  # 50 dona
    )
    await make_pos_sale(
        store_id=store.id,
        lines=[(product_b.id, Decimal("5"), Decimal("1000"))],   # 5 dona
    )
    await db_session.commit()

    result = await service.product_ranking(
        db=db_session,
        enterprise_id=default_enterprise.id,
        order="top",
        limit=5,
    )
    assert len(result.items) == 2
    assert result.items[0].product_id == product_a.id
    assert result.items[0].sold_qty == Decimal("50")
    assert result.items[1].product_id == product_b.id
    assert result.items[0].rank == 1
    assert result.items[1].rank == 2


@pytest.mark.asyncio
async def test_product_ranking_bottom_includes_zero(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_pos_sale,
    default_enterprise,
) -> None:
    """Bottom tartibda 0-sotuvli mahsulotlar ham ko'rinadi."""
    store = await make_store()
    product_sold = await make_product(name_uz="Sotilgan")
    product_zero = await make_product(name_uz="Sotilmagan")
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)

    await make_pos_sale(
        store_id=store.id,
        lines=[(product_sold.id, Decimal("3"), Decimal("1000"))],
    )
    await db_session.commit()

    result = await service.product_ranking(
        db=db_session,
        enterprise_id=default_enterprise.id,
        order="bottom",
        limit=10,
    )
    # Ikkala mahsulot ham ko'rinishi kerak
    product_ids = {item.product_id for item in result.items}
    assert product_zero.id in product_ids
    # 0-sotuvli birinchi bo'lishi kerak (bottom)
    zero_item = next((i for i in result.items if i.product_id == product_zero.id), None)
    assert zero_item is not None
    assert zero_item.sold_qty == Decimal("0")


# ─── 7. Recommendations: R1-R5 deterministik ────────────────────────────────


def _make_expiry_item(days_left: int, severity: str) -> ExpiryItem:
    today = datetime.now(timezone.utc).date()
    return ExpiryItem(
        inventory_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        store_name="Do'kon X",
        product_id=uuid.uuid4(),
        product_name="Mahsulot Y",
        qty=Decimal("10"),
        expiry_date=today + timedelta(days=days_left),
        days_left=days_left,
        severity=severity,
    )


def _make_geo_item(velocity: float, sold_qty: float = 30.0) -> GeoVelocityItem:
    return GeoVelocityItem(
        store_id=uuid.uuid4(),
        store_name="GPS Do'kon",
        gps_lat=Decimal("41.3"),
        gps_lng=Decimal("69.2"),
        address="Toshkent",
        sold_qty=Decimal(str(sold_qty)),
        revenue=Decimal("100000"),
        velocity_per_day=Decimal(str(velocity)),
    )


def _make_product_item(sold_qty: float, rank: int = 1) -> ProductRankingItem:
    return ProductRankingItem(
        product_id=uuid.uuid4(),
        product_name="Mahsulot Z",
        sold_qty=Decimal(str(sold_qty)),
        revenue=Decimal("50000"),
        store_count=1,
        rank=rank,
    )


def test_recommendations_r1_expiry_urgent() -> None:
    """R1: days_left <= 7 → severity=high, kod=R1_expiry_urgent."""
    expiry_urgent = [_make_expiry_item(3, "urgent")]
    recs = generate_recommendations(
        geo_items=[],
        expiry_items=expiry_urgent,
        top_products=[],
        bottom_products=[],
    )
    high_recs = [r for r in recs if r.code == "R1_expiry_urgent"]
    assert len(high_recs) == 1
    assert high_recs[0].severity == "high"


def test_recommendations_r2_expiry_warn() -> None:
    """R2: 7 < days_left <= 30 → severity=medium, kod=R2_expiry_warn."""
    expiry_warn = [_make_expiry_item(20, "warning")]
    recs = generate_recommendations(
        geo_items=[],
        expiry_items=expiry_warn,
        top_products=[],
        bottom_products=[],
    )
    med_recs = [r for r in recs if r.code == "R2_expiry_warn"]
    assert len(med_recs) == 1
    assert med_recs[0].severity == "medium"


def test_recommendations_r4_slow_mover() -> None:
    """R4: sold_qty=0 → R4_slow_mover tavsiyasi."""
    zero_products = [_make_product_item(0.0)]
    recs = generate_recommendations(
        geo_items=[],
        expiry_items=[],
        top_products=[],
        bottom_products=zero_products,
    )
    slow_recs = [r for r in recs if r.code == "R4_slow_mover"]
    assert len(slow_recs) == 1
    assert slow_recs[0].severity == "medium"


def test_recommendations_r5_geo_hotspot() -> None:
    """R5: velocity > 0 → R5_geo_hotspot tavsiyasi (eng yuqori)."""
    geo_items = [_make_geo_item(2.5)]
    recs = generate_recommendations(
        geo_items=geo_items,
        expiry_items=[],
        top_products=[],
        bottom_products=[],
    )
    hotspot_recs = [r for r in recs if r.code == "R5_geo_hotspot"]
    assert len(hotspot_recs) == 1
    assert hotspot_recs[0].severity == "info"


def test_recommendations_severity_ordering() -> None:
    """Tavsiyalar jiddiylik bo'yicha tartiblanadi: high → medium → info."""
    recs = generate_recommendations(
        geo_items=[_make_geo_item(1.0)],
        expiry_items=[
            _make_expiry_item(3, "urgent"),
            _make_expiry_item(20, "warning"),
        ],
        top_products=[],
        bottom_products=[_make_product_item(0.0)],
    )
    severities = [r.severity for r in recs]
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    orders = [severity_order.get(s, 4) for s in severities]
    assert orders == sorted(orders), f"Tartib noto'g'ri: {severities}"


def test_recommendations_empty_data() -> None:
    """Hech qanday ma'lumot yo'q → bo'sh tavsiyalar."""
    recs = generate_recommendations(
        geo_items=[],
        expiry_items=[],
        top_products=[],
        bottom_products=[],
    )
    assert recs == []


# ─── 8. RBAC: analytics:view ruxsati ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_analytics_overview_admin_200(
    analytics_client,
    admin_user: AppUser,
) -> None:
    """Administrator → 200 qaytadi."""
    token = await get_token(analytics_client, admin_user)
    resp = await analytics_client.get(
        "/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_analytics_overview_accountant_200(
    analytics_client,
    accountant_user: AppUser,
) -> None:
    """Accountant → 200 qaytadi."""
    token = await get_token(analytics_client, accountant_user)
    resp = await analytics_client.get(
        "/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_analytics_overview_agent_403(
    analytics_client,
    agent_user: AppUser,
) -> None:
    """Agent → 403 (analytics:view ruxsati yo'q)."""
    token = await get_token(analytics_client, agent_user)
    resp = await analytics_client.get(
        "/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_analytics_overview_store_403(
    analytics_client,
    store_user_obj: AppUser,
) -> None:
    """Store roli → 403."""
    token = await get_token(analytics_client, store_user_obj)
    resp = await analytics_client.get(
        "/analytics/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 9. superadmin → bo'sh natija ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_superadmin_empty() -> None:
    """superadmin (enterprise_id=None) → bo'sh natija."""
    # service funksiyasini to'g'ridan-to'g'ri test qilamiz (DB kerak emas)
    # Qisqa: overview(enterprise_id=None) bo'sh natija qaytarishi kerak
    # Bu sinxron test (asyncio.run bilan ishlaydi — pytest-asyncio auto mode)
    pass  # service.overview(None) → OverviewOut(contracted_store_count=0, ...)


@pytest.mark.asyncio
async def test_overview_superadmin_direct(
    db_session: AsyncSession,
) -> None:
    """superadmin enterprise_id=None → OverviewOut(contracted_store_count=0)."""
    result = await service.overview(db=db_session, enterprise_id=None)
    assert result.contracted_store_count == 0
    assert result.sold_qty_total == Decimal("0")
    assert result.revenue_total == Decimal("0")


@pytest.mark.asyncio
async def test_contracted_stores_superadmin_empty(
    db_session: AsyncSession,
) -> None:
    result = await service.contracted_stores(db=db_session, enterprise_id=None)
    assert result.total == 0
    assert result.stores == []


@pytest.mark.asyncio
async def test_expiry_superadmin_empty(
    db_session: AsyncSession,
) -> None:
    result = await service.expiry_report(db=db_session, enterprise_id=None)
    assert result.total == 0


# ─── 10. invalid_period → 422 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_invalid_period(
    analytics_client,
    admin_user: AppUser,
) -> None:
    """from > to → 422 AppError."""
    token = await get_token(analytics_client, admin_user)
    resp = await analytics_client.get(
        "/analytics/overview",
        params={
            "from": "2026-06-20T00:00:00",
            "to": "2026-06-10T00:00:00",  # from > to
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_geo_velocity_invalid_period(
    analytics_client,
    admin_user: AppUser,
) -> None:
    token = await get_token(analytics_client, admin_user)
    resp = await analytics_client.get(
        "/analytics/geo-velocity",
        params={
            "from": "2026-06-20T00:00:00",
            "to": "2026-06-01T00:00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── 11. NULL/coalesce: sotuv yo'q → Decimal(0) ──────────────────────────────


@pytest.mark.asyncio
async def test_contracted_stores_zero_sales(
    db_session: AsyncSession,
    make_store,
    make_product,
    make_contract,
    make_inventory,
    default_enterprise,
) -> None:
    """Shartnoma bor, inventar bor, sotuv yo'q → sold_qty_30d=0."""
    store = await make_store(name="Sotuvsiz Do'kon")
    product = await make_product()
    await make_contract(store_id=store.id, supplier_enterprise_id=default_enterprise.id)
    await make_inventory(store_id=store.id, product_id=product.id, qty=Decimal("20"))
    await db_session.commit()

    result = await service.contracted_stores(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    assert result.total == 1
    assert result.stores[0].sold_qty_30d == Decimal("0")
    assert result.stores[0].inventory_qty == Decimal("20")


# ─── 12. ai_enrich: graceful degrade (no API key) ────────────────────────────


@pytest.mark.asyncio
async def test_ai_enrich_no_api_key() -> None:
    """ANTHROPIC_API_KEY yo'q → (None, False) qaytadi."""
    from unittest.mock import patch

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.anthropic_api_key = None
        mock_settings.analytics_ai_enabled = True

        summary, enabled = await enrich_with_ai([])
        assert summary is None
        assert enabled is False


@pytest.mark.asyncio
async def test_ai_enrich_disabled_flag() -> None:
    """analytics_ai_enabled=False → (None, False) qaytadi."""
    from unittest.mock import patch

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.anthropic_api_key = "sk-test-fake-key"
        mock_settings.analytics_ai_enabled = False

        summary, enabled = await enrich_with_ai([])
        assert summary is None
        assert enabled is False


# ─── 13. Contracted stores: contract validity strict ─────────────────────────


@pytest.mark.asyncio
async def test_contracted_stores_expired_not_included(
    db_session: AsyncSession,
    make_store,
    make_contract,
    default_enterprise,
) -> None:
    """Muddati o'tgan shartnoma → do'kon ro'yxatga kirmaydi."""
    today = datetime.now(timezone.utc).date()
    store_expired = await make_store(name="Muddati O'tgan Do'kon")

    # O'tgan shartnoma
    await make_contract(
        store_id=store_expired.id,
        supplier_enterprise_id=default_enterprise.id,
        valid_to=today - timedelta(days=1),
    )
    await db_session.commit()

    result = await service.contracted_stores(
        db=db_session,
        enterprise_id=default_enterprise.id,
    )
    # valid_to < today → _get_contracted_store_ids'da chiqib ketadi
    assert result.total == 0


# ─── 14. recommendations endpoint HTTP test ──────────────────────────────────


@pytest.mark.asyncio
async def test_recommendations_endpoint_200(
    analytics_client,
    admin_user: AppUser,
) -> None:
    """Recommendations endpoint admin uchun 200 qaytadi."""
    token = await get_token(analytics_client, admin_user)
    resp = await analytics_client.get(
        "/analytics/recommendations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert "ai_enabled" in data
    assert "generated_at" in data
    # API key yo'q → ai_enabled=False
    assert data["ai_enabled"] is False


# ─── 15. Product ranking: invalid order → 422 ────────────────────────────────


@pytest.mark.asyncio
async def test_product_ranking_invalid_order(
    analytics_client,
    admin_user: AppUser,
) -> None:
    """Noto'g'ri order parametri → 422."""
    token = await get_token(analytics_client, admin_user)
    resp = await analytics_client.get(
        "/analytics/products",
        params={"order": "invalid_value"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
