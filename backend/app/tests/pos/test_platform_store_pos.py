"""
ADR-036 POS testlari — platforma-do'kon (enterprise_id IS NULL) + concurrency.

Test kategoriyalari:
  1. Platforma-do'kon (do'kon enterprise_id=NULL, inventar enterprise_id=NULL):
     POS sotuv muvaffaqiyatli o'tadi (avval PG'da NOT NULL bilan 500 berardi —
     0036 migratsiya bilan tuzatildi).
  2. [#10] Inventar so'rovi enterprise_id BILAN FILTRLANMAYDI — do'kon
     enterprise_id=NULL bo'lsa-yu, checkout enterprise_id (real tenant, masalan
     shartnoma orqali platforma-do'konda savdo qiluvchi admin) berilsa ham,
     inventar to'g'ri topiladi (avval bu holatda jimgina katalog-fallback'ga
     tushib, deduksiya/expiry o'tkazib yuborilardi).
  3. [#12a] Bir xil mahsulotga ikkita qator (dublikat) — umumiy talab mavjud
     miqdordan oshsa, ikkalasi HAM 422 bilan bloklanishi kerak (avval har
     qator mustaqil tekshirilib, oversell yuz berardi).
  4. [#9] Eng eski partiya allaqachon tugagan (qty=0) va muddati o'tgan bo'lsa,
     u sotuvni bloklamasligi kerak — faqat AYNAN sotiladigan (qty>0) partiya
     tekshiriladi.

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enterprise import Enterprise
from app.models.store import Store
from app.models.store_inventory import StoreInventory
from app.modules.pos import service
from app.modules.pos.schemas import PosSaleCreate, PosSaleLineIn


async def _make_platform_store(
    db_session: AsyncSession,
    user_id: uuid.UUID | None = None,
    segment_id: uuid.UUID | None = None,
    is_platform_managed: bool = False,
) -> Store:
    """ADR-003 ko'prik: platforma-do'kon — enterprise_id IS NULL (mustaqil)."""
    store = Store(
        id=uuid.uuid4(),
        name="Platforma Do'kon",
        user_id=user_id,
        segment_id=segment_id,
        version=1,
        enterprise_id=None,
        is_platform_managed=is_platform_managed,
    )
    db_session.add(store)
    await db_session.flush()
    return store


async def _make_inventory(
    db_session: AsyncSession,
    store_id: uuid.UUID,
    product_id: uuid.UUID,
    enterprise_id: uuid.UUID | None,
    qty: Decimal = Decimal("10"),
    sale_price: Decimal = Decimal("2000.00"),
    cost_price: Decimal = Decimal("1500.00"),
    expiry_date: date | None = None,
    status: str = "active",
    created_at=None,
) -> StoreInventory:
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
    if created_at is not None:
        inv.created_at = created_at
    db_session.add(inv)
    await db_session.flush()
    return inv


# ─── 1. Platforma-do'kon POS sotuv — enterprise_id=NULL to'liq zanjir ────────


@pytest.mark.asyncio
async def test_create_sale_platform_store_enterprise_null(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_user,
) -> None:
    """
    Do'kon enterprise_id=NULL, inventar enterprise_id=NULL, kassir
    enterprise_id=NULL (ADR-003 mustaqil do'kon) — sotuv muvaffaqiyatli
    o'tishi kerak (0036 migratsiyagacha PG'da NOT NULL bilan 500 berardi).
    """
    segment = await make_price_segment()
    product = await make_product(price=Decimal("2500.00"), segment_id=segment.id)
    cashier = await make_user("store", enterprise_id=None)
    store = await _make_platform_store(db_session, user_id=cashier.id, segment_id=segment.id)

    inv = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=None,
        qty=Decimal("10"),
        sale_price=Decimal("2500.00"),
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("3"))],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=cashier.id,
        user=cashier,
        enterprise_id=None,
    )

    assert sale.enterprise_id is None
    assert sale.total_amount == Decimal("7500.00")
    assert sale.lines[0].enterprise_id is None

    await db_session.refresh(inv)
    assert inv.qty == Decimal("7"), "platforma-do'konda ham qty atomik kamayishi kerak"


# ─── 2. [#10] enterprise_id mos kelmasa ham inventar store_id orqali topiladi ─


@pytest.mark.asyncio
async def test_create_sale_inventory_scope_ignores_enterprise_mismatch(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    admin_user,
    default_enterprise: Enterprise,
) -> None:
    """
    Inventar enterprise_id=NULL (platforma-do'kon), lekin checkout qiluvchi
    tenant admin (enterprise_id=REAL TENANT, shartnoma orqali platforma-do'konda
    savdo qiladi). Eski kod `StoreInventory.enterprise_id == enterprise_id`
    filtri bilan bu inventarni HECH QACHON topolmasdi (None != real UUID) —
    jimgina katalog-narxga tushib, deduksiya/expiry o'tkazib yuborilardi.
    Yangi kod faqat store_id bo'yicha izlaydi.
    """
    from app.models.contract import Contract

    segment = await make_price_segment(enterprise_id=default_enterprise.id)
    product = await make_product(
        price=Decimal("9999.00"), segment_id=segment.id, enterprise_id=default_enterprise.id,
    )
    store = await _make_platform_store(db_session, segment_id=segment.id, is_platform_managed=True)

    # Shartnoma — admin_user korxonasi bu platforma-do'konni ko'rishi uchun
    # (get_store_visibility_filter: administrator + is_platform_managed + contract).
    contract = Contract(
        store_id=store.id,
        number="ADR036-CONTRACT-001",
        valid_from=date.today() - timedelta(days=10),
        valid_to=date.today() + timedelta(days=365),
        contract_type="trade",
        supplier_enterprise_id=default_enterprise.id,
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()

    inv = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=None,  # platforma-do'kon inventari
        qty=Decimal("5"),
        sale_price=Decimal("1234.00"),  # katalog narxidan farqli — inventar ishlatilganini isbotlaydi
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="card",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("2"))],
    )

    # admin_user.enterprise_id = default_enterprise.id (REAL tenant) —
    # inventar (enterprise_id=NULL) baribir topilishi va ishlatilishi kerak.
    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.lines[0].unit_price == Decimal("1234.00"), (
        "Inventar narxi ishlatilishi kerak, katalog narxiga fallback bo'lmasligi kerak"
    )
    await db_session.refresh(inv)
    assert inv.qty == Decimal("3"), "Inventar deduksiya qilinishi kerak (fallback emas)"


# ─── 3. [#12a] Dublikat qatorlar — agregatsiya, oversell bloklanadi ──────────


@pytest.mark.asyncio
async def test_create_sale_duplicate_product_lines_oversell_blocked(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """
    Bitta so'rovda bir xil mahsulotga IKKITA qator (masalan klient/duplikat
    skan) — umumiy talab (3+3=6) mavjud qty(5) dan oshadi. Eski kod har
    qatorni MUSTAQIL tekshirardi (3<=5 ikkalasi ham o'tardi) — natijada
    -1 ga qadar salbiy qty (oversell). Yangi kod umumiy talabni bir marta
    tekshiradi → 422 pos.insufficient_inventory.
    """
    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)

    inv = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=admin_user.enterprise_id,
        qty=Decimal("5"),
        sale_price=Decimal("1000.00"),
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[
            PosSaleLineIn(product_id=product.id, qty=Decimal("3")),
            PosSaleLineIn(product_id=product.id, qty=Decimal("3")),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.insufficient_inventory"
    assert exc_info.value.status_code == 422

    # Sotuv rad etilgan — qty o'zgarmagan bo'lishi kerak
    await db_session.refresh(inv)
    assert inv.qty == Decimal("5"), "Rad etilgan sotuv qty ni o'zgartirmasligi kerak"


@pytest.mark.asyncio
async def test_create_sale_duplicate_product_lines_within_stock_succeeds(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """Dublikat qatorlar, lekin umumiy talab qty ichida — sotuv o'tadi."""
    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)

    inv = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=admin_user.enterprise_id,
        qty=Decimal("10"),
        sale_price=Decimal("1000.00"),
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[
            PosSaleLineIn(product_id=product.id, qty=Decimal("3")),
            PosSaleLineIn(product_id=product.id, qty=Decimal("4")),
        ],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.total_amount == Decimal("7000.00")
    await db_session.refresh(inv)
    assert inv.qty == Decimal("3"), "10 - (3+4) = 3"


# ─── 4. [#9] Tugagan (qty=0) va muddati o'tgan eski partiya sotuvni bloklamaydi ─


@pytest.mark.asyncio
async def test_create_sale_depleted_expired_batch_does_not_block_newer_batch(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """
    Eng eski partiya allaqachon TUGAGAN (qty=0) va muddati o'tgan (yoki
    status='expired') — lekin u endi sotuvga aloqasi yo'q. Yangi (qty>0,
    muddati uzoq) partiya mavjud bo'lsa, sotuv shu partiyadan o'tishi kerak.
    Eski ikki-passli mantiq (PASS-1 status/qty filtrisiz) bu holatda eski
    tugagan partiyani ko'rib, sotuvni noto'g'ri bloklardi.
    """
    from datetime import datetime, timezone, timedelta as _td

    segment = await make_price_segment()
    product = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)

    old_depleted = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=admin_user.enterprise_id,
        qty=Decimal("0"),
        sale_price=Decimal("500.00"),
        expiry_date=date.today() - timedelta(days=5),
        status="expired",
        created_at=datetime.now(timezone.utc) - _td(days=10),
    )
    fresh_batch = await _make_inventory(
        db_session,
        store_id=store.id,
        product_id=product.id,
        enterprise_id=admin_user.enterprise_id,
        qty=Decimal("8"),
        sale_price=Decimal("500.00"),
        expiry_date=date.today() + timedelta(days=30),
        status="active",
        created_at=datetime.now(timezone.utc) - _td(days=1),
    )

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

    assert sale.total_amount == Decimal("1000.00")
    await db_session.refresh(fresh_batch)
    await db_session.refresh(old_depleted)
    assert fresh_batch.qty == Decimal("6"), "yangi partiyadan sotilishi kerak"
    assert old_depleted.qty == Decimal("0"), "tugagan partiya o'zgarmasligi kerak"
