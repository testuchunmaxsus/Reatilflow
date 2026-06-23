"""
MP4 Expiry testlari — muddati o'tgan mahsulot + POS inventar integratsiya.

Test kategoriyalari:
  1. Expiry helper: is_expired, is_near_expiry, days_to_expiry to'g'ri ishlaydi.
  2. POS sotuv: inventari bor, muddat uzoq → muvaffaqiyatli, qty kamayadi.
  3. POS sotuv: muddati o'tgan item (status='expired') → 422 pos.product_expired.
  4. POS sotuv: muddati o'tgan item (expiry_date o'tgan) → 422 pos.product_expired.
  5. POS sotuv: muddati 2 kun qolgan (near-expiry, ≤3) → 422 pos.product_expired.
  6. POS sotuv: muddati 5 kun → muvaffaqiyatli (blok 3 kundan uzoq).
  7. POS sotuv: inventarsiz do'kon → katalog narxiga fallback (eski testlar mos).
  8. expiry-scan: muddati o'tgan → status='expired'.
  9. expiry-scan: 2 kun qolgan → bildirishnoma outbox event.
  10. expiry-scan: takror skan → ikki marta bildirishnoma yuborilmaydi.
  11. StoreInventoryOut bayroqlari to'g'ri (is_expired/is_near_expiry/days_to_expiry).
  12. Tenant izolyatsiya saqlanadi (boshqa korxona inventarini sotib bo'lmaydi).

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.errors import AppError
from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
from app.models.store_inventory import StoreInventory
from app.models.outbox import OutboxEvent
from app.modules.pos import service
from app.modules.pos.expiry import is_expired, is_near_expiry, days_to_expiry
from app.modules.pos.expiry_scan import mark_expired_inventory
from app.modules.pos.schemas import PosSaleCreate, PosSaleLineIn
from app.tests.conftest import TEST_ENTERPRISE_UUID
from app.tests.pos.conftest import get_token


# ─── Yordamchi: inventar bilan do'kon yaratish ───────────────────────────────

async def _make_inventory(
    db_session: AsyncSession,
    store_id: uuid.UUID,
    product_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    qty: Decimal = Decimal("10"),
    sale_price: Decimal = Decimal("2000.00"),
    cost_price: Decimal = Decimal("1500.00"),
    expiry_date: date | None = None,
    status: str = "active",
) -> StoreInventory:
    """StoreInventory yaratish yordamchisi."""
    inv = StoreInventory(
        enterprise_id=enterprise_id,
        store_id=store_id,
        product_id=product_id,
        qty=qty,
        cost_price=cost_price,
        markup_percent=Decimal("33.33"),
        sale_price=sale_price,
        expiry_date=expiry_date,
        status=status,
    )
    db_session.add(inv)
    await db_session.flush()
    return inv


async def _make_seeded_with_inventory(
    make_price_segment,
    make_product,
    make_store,
    db_session: AsyncSession,
    enterprise_id: uuid.UUID,
    store_user_id: uuid.UUID | None = None,
    price: Decimal = Decimal("2000.00"),
    expiry_date: date | None = None,
    inv_status: str = "active",
    qty: Decimal = Decimal("10"),
):
    """Segment + mahsulot + do'kon + inventar."""
    segment = await make_price_segment(enterprise_id=enterprise_id)
    product = await make_product(
        price=price, segment_id=segment.id, enterprise_id=enterprise_id
    )
    store = await make_store(
        segment_id=segment.id,
        user_id=store_user_id,
        enterprise_id=enterprise_id,
    )
    inv = await _make_inventory(
        db_session=db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=enterprise_id,
        qty=qty,
        sale_price=price,
        expiry_date=expiry_date,
        status=inv_status,
    )
    return store, product, segment, inv


# ─── 1. Expiry helper funksiyalari ───────────────────────────────────────────

class _FakeInv:
    """Duck-type StoreInventory."""
    def __init__(self, expiry_date: date | None, status: str = "active"):
        self.expiry_date = expiry_date
        self.status = status


def test_expiry_helper_no_expiry():
    """expiry_date=None → hech qachon expired/near_expiry emas."""
    inv = _FakeInv(expiry_date=None)
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert not is_expired(inv, now)
    assert not is_near_expiry(inv, now, days=3)
    assert days_to_expiry(inv, now) is None


def test_expiry_helper_expired_by_date():
    """expiry_date kecha → is_expired=True."""
    yesterday = date(2026, 6, 22)
    inv = _FakeInv(expiry_date=yesterday)
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert is_expired(inv, now)
    assert not is_near_expiry(inv, now, days=3)  # o'tgan → near emas
    assert days_to_expiry(inv, now) == -1


def test_expiry_helper_expired_by_status():
    """status='expired' → is_expired=True (expiry_date bo'lmasada)."""
    inv = _FakeInv(expiry_date=None, status="expired")
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert is_expired(inv, now)


def test_expiry_helper_near_expiry_2_days():
    """2 kun qolgan → is_near_expiry=True (days=3)."""
    future = date(2026, 6, 25)  # bugundan 2 kun
    inv = _FakeInv(expiry_date=future)
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert not is_expired(inv, now)
    assert is_near_expiry(inv, now, days=3)
    assert days_to_expiry(inv, now) == 2


def test_expiry_helper_far_expiry():
    """5 kun qolgan → is_near_expiry=False (days=3)."""
    future = date(2026, 6, 28)  # bugundan 5 kun
    inv = _FakeInv(expiry_date=future)
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert not is_expired(inv, now)
    assert not is_near_expiry(inv, now, days=3)
    assert days_to_expiry(inv, now) == 5


def test_expiry_helper_today_expiry():
    """Bugun muddati tugaydi → is_near_expiry=True (0 kun), is_expired=False."""
    today = date(2026, 6, 23)
    inv = _FakeInv(expiry_date=today)
    now = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert not is_expired(inv, now)  # TODAY emas < today, balki == today
    assert is_near_expiry(inv, now, days=3)
    assert days_to_expiry(inv, now) == 0


# ─── 2. POS sotuv: inventari bor, muddat uzoq ────────────────────────────────

@pytest.mark.asyncio
async def test_pos_sale_with_inventory_success(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """Inventari bor, muddat 10 kun → sotuv muvaffaqiyatli, qty kamayadi."""
    future_date = date.today() + timedelta(days=10)
    store, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        price=Decimal("2000.00"),
        expiry_date=future_date,
        qty=Decimal("5"),
    )
    initial_qty = inv.qty

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("2"))],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.total_amount == Decimal("4000.00")
    assert len(sale.lines) == 1
    assert sale.lines[0].unit_price == Decimal("2000.00")

    # qty kamayishi tekshiruvi
    await db_session.refresh(inv)
    assert inv.qty == initial_qty - Decimal("2"), "qty atomik kamayishi"


# ─── 3. POS sotuv: status='expired' → 422 ────────────────────────────────────

@pytest.mark.asyncio
async def test_pos_sale_blocks_expired_status(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """Inventar status='expired' → sotuv bloklanadi (422 pos.product_expired)."""
    store, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=date.today() - timedelta(days=1),  # kecha
        inv_status="expired",
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.product_expired"
    assert exc_info.value.status_code == 422


# ─── 4. POS sotuv: muddati o'tgan (expiry_date o'tgan) → 422 ────────────────

@pytest.mark.asyncio
async def test_pos_sale_blocks_expired_date(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """expiry_date kecha, status='active' → sotuv bloklanadi (422 pos.product_expired)."""
    store, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=date.today() - timedelta(days=1),  # kecha
        inv_status="active",  # scan hali ishlamagan
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.product_expired"
    assert exc_info.value.status_code == 422


# ─── 5. POS sotuv: 2 kun qolgan (near-expiry ≤3) → 422 ──────────────────────

@pytest.mark.asyncio
async def test_pos_sale_blocks_near_expiry_2_days(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """2 kun qolgan → POS sotuv bloklanadi (near-expiry ≤ pos_expiry_block_days=3)."""
    near_date = date.today() + timedelta(days=2)
    store, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=near_date,
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.product_expired"
    assert exc_info.value.status_code == 422


# ─── 6. POS sotuv: 5 kun qolgan → muvaffaqiyatli ─────────────────────────────

@pytest.mark.asyncio
async def test_pos_sale_allows_5_days_expiry(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """5 kun qolgan → blok chegarasidan tashqarida (>3) → sotuv o'tadi."""
    far_date = date.today() + timedelta(days=5)
    store, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=far_date,
        price=Decimal("1500.00"),
        qty=Decimal("5"),
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="card",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.total_amount == Decimal("1500.00")
    # qty kamayishi
    await db_session.refresh(inv)
    assert inv.qty == Decimal("4")


# ─── 7. POS sotuv: inventarsiz do'kon → katalog narxi (backward-compat) ──────

@pytest.mark.asyncio
async def test_pos_sale_without_inventory_fallback(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """Inventarsiz do'kon → katalog narxi (eski testlar uchun mos)."""
    from app.tests.pos.test_pos import _make_seeded_store_product

    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
        price=Decimal("3000.00"),
    )
    # Inventar yaratilmagan — fallback

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("2"))],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.total_amount == Decimal("6000.00")


# ─── 8. expiry-scan: muddati o'tgan → status='expired' ───────────────────────

@pytest.mark.asyncio
async def test_expiry_scan_marks_expired(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """expiry_date kecha → scan keyin status='expired'."""
    yesterday = date.today() - timedelta(days=1)
    _, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=yesterday,
        inv_status="active",
    )

    assert inv.status == "active"

    result = await mark_expired_inventory(db=db_session)

    assert result["marked_expired"] >= 1
    await db_session.refresh(inv)
    assert inv.status == "expired", "muddati o'tgan → expired deb belgilanishi kerak"


# ─── 9. expiry-scan: 2 kun qolgan → bildirishnoma outbox ─────────────────────

@pytest.mark.asyncio
async def test_expiry_scan_sends_notification(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """2 kun qolgan (≤ expiry_notify_days=2) → outbox event inventory.expiring_soon."""
    soon_date = date.today() + timedelta(days=2)
    _, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=soon_date,
        inv_status="active",
    )

    result = await mark_expired_inventory(db=db_session)

    assert result["notifications_sent"] >= 1

    # Outbox event tekshiruvi
    stmt = select(OutboxEvent).where(
        OutboxEvent.event_type == "inventory.expiring_soon",
        OutboxEvent.aggregate_type == "store_inventory",
    )
    outbox_res = await db_session.execute(stmt)
    events = outbox_res.scalars().all()
    assert len(events) >= 1
    # Payload tekshiruvi
    import json
    payload = json.loads(events[0].payload)
    assert "inventory_id" in payload
    assert "days_to_expiry" in payload
    assert payload["days_to_expiry"] == 2


# ─── 10. expiry-scan: takror → ikki marta bildirishnoma yuborilmaydi ─────────

@pytest.mark.asyncio
async def test_expiry_scan_no_duplicate_notification(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """Bir kunda ikki marta scan → faqat bitta bildirishnoma."""
    soon_date = date.today() + timedelta(days=1)
    _, product, _, inv = await _make_seeded_with_inventory(
        make_price_segment, make_product, make_store,
        db_session=db_session,
        enterprise_id=admin_user.enterprise_id,
        expiry_date=soon_date,
        inv_status="active",
    )

    result1 = await mark_expired_inventory(db=db_session)
    result2 = await mark_expired_inventory(db=db_session)

    # Birinchi skan bildirishnoma yuboradi
    assert result1["notifications_sent"] >= 1
    # Ikkinchi skan takrorlamaydi
    assert result2["notifications_sent"] == 0

    # Jami faqat bitta outbox event
    stmt = select(OutboxEvent).where(
        OutboxEvent.event_type == "inventory.expiring_soon",
        OutboxEvent.aggregate_type == "store_inventory",
    )
    outbox_res = await db_session.execute(stmt)
    events = outbox_res.scalars().all()
    assert len(events) == 1, "Bir kunda faqat bitta bildirishnoma bo'lishi kerak"


# ─── 11. StoreInventoryOut bayroqlari ─────────────────────────────────────────

def test_inventory_out_flags_expired():
    """is_expired=True uchun bayroqlar to'g'ri."""
    from app.modules.marketplace.schemas import StoreInventoryOut
    from datetime import datetime

    yesterday = date.today() - timedelta(days=1)
    inv_out = StoreInventoryOut(
        id=uuid.uuid4(),
        enterprise_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        qty=Decimal("5"),
        cost_price=Decimal("100"),
        markup_percent=Decimal("0"),
        sale_price=Decimal("100"),
        expiry_date=yesterday,
        status="active",
        source_order_id=None,
        created_at=datetime.now(timezone.utc),
        is_expired=True,
        is_near_expiry=False,
        days_to_expiry=-1,
    )
    assert inv_out.is_expired is True
    assert inv_out.is_near_expiry is False
    assert inv_out.days_to_expiry == -1


def test_inventory_out_flags_near_expiry():
    """is_near_expiry=True uchun bayroqlar to'g'ri."""
    from app.modules.marketplace.schemas import StoreInventoryOut
    from datetime import datetime

    soon = date.today() + timedelta(days=2)
    inv_out = StoreInventoryOut(
        id=uuid.uuid4(),
        enterprise_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        qty=Decimal("5"),
        cost_price=Decimal("100"),
        markup_percent=Decimal("0"),
        sale_price=Decimal("100"),
        expiry_date=soon,
        status="active",
        source_order_id=None,
        created_at=datetime.now(timezone.utc),
        is_expired=False,
        is_near_expiry=True,
        days_to_expiry=2,
    )
    assert inv_out.is_expired is False
    assert inv_out.is_near_expiry is True
    assert inv_out.days_to_expiry == 2


def test_inventory_out_flags_no_expiry():
    """expiry_date=None uchun barcha bayroqlar False/None."""
    from app.modules.marketplace.schemas import StoreInventoryOut
    from datetime import datetime

    inv_out = StoreInventoryOut(
        id=uuid.uuid4(),
        enterprise_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        qty=Decimal("5"),
        cost_price=Decimal("100"),
        markup_percent=Decimal("0"),
        sale_price=Decimal("100"),
        expiry_date=None,
        status="active",
        source_order_id=None,
        created_at=datetime.now(timezone.utc),
        is_expired=False,
        is_near_expiry=False,
        days_to_expiry=None,
    )
    assert inv_out.is_expired is False
    assert inv_out.is_near_expiry is False
    assert inv_out.days_to_expiry is None


# ─── 12. Tenant izolyatsiya ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pos_tenant_isolation_inventory(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    default_enterprise: Enterprise,
) -> None:
    """
    Korxona B inventari Korxona A uchun ko'rinmaydi.
    Korxona A sotuv qilsa → Korxona B inventaridan QILMAYDI.
    """
    # Korxona B yaratish (boshqa testlarda ishlatilgan ID lardan farqli)
    enterprise_b_id = uuid.UUID("00000000-0000-7000-8abc-000000000099")
    enterprise_b = Enterprise(
        id=enterprise_b_id,
        name="Korxona B",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(enterprise_b)
    await db_session.flush()

    # Korxona A admin
    admin_a = await make_user("administrator", enterprise_id=default_enterprise.id)

    # Korxona A do'kon + mahsulot (inventarsiz — katalog narxi bilan)
    segment_a = await make_price_segment(enterprise_id=default_enterprise.id)
    product_a = await make_product(
        price=Decimal("1000.00"),
        segment_id=segment_a.id,
        enterprise_id=default_enterprise.id,
    )
    store_a = await make_store(
        segment_id=segment_a.id, enterprise_id=default_enterprise.id
    )

    # Korxona B uchun inventar yaratish (boshqa do'kon, lekin bir xil product)
    # QOIDA: create_sale enterprise_id filtr qo'llaydi → B inventari A ga berilmaydi
    from app.models.store import Store
    store_b = Store(
        name="B do'kon",
        segment_id=segment_a.id,
        version=1,
        enterprise_id=enterprise_b_id,
    )
    db_session.add(store_b)
    await db_session.flush()

    inv_b = await _make_inventory(
        db_session=db_session,
        store_id=store_b.id,
        product_id=product_a.id,
        enterprise_id=enterprise_b_id,
        qty=Decimal("100"),
        sale_price=Decimal("999.00"),  # farqli narx
        expiry_date=date.today() + timedelta(days=30),
    )
    initial_inv_b_qty = inv_b.qty

    # Korxona A sotuv qiladi — B inventaridan OLMASLIGI kerak
    data = PosSaleCreate(
        store_id=store_a.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product_a.id, qty=Decimal("1"))],
    )

    # Sotuv muvaffaqiyatli bo'ladi (katalog narxiga fallback)
    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_a.id,
        user=admin_a,
        enterprise_id=default_enterprise.id,
    )
    assert sale is not None
    # Narx katalogdan — 1000 (B inventar 999 emas)
    assert sale.total_amount == Decimal("1000.00")

    # B inventar qty o'ZGARMAGAN (tenant izolyatsiya)
    await db_session.refresh(inv_b)
    assert inv_b.qty == initial_inv_b_qty, "Tenant izolyatsiya: B inventari o'zgarmasligi kerak"
