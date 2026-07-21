"""
ADR-036 marketplace testlari — platforma-do'kon accept_order + concurrency.

Test kategoriyalari:
  1. [#11] Platforma-do'kon (mustaqil, buyer_enterprise_id=NULL) o'z
     buyurtmasini qabul qiladi — StoreInventory.enterprise_id=NULL yoziladi
     (0036 migratsiyagacha PG'da NOT NULL bilan 500 berardi).
  2. [#11] Tenant admin (real enterprise_id) shartnoma orqali platforma-do'kon
     nomidan qabul qiladi (order.buyer_enterprise_id=REAL, lekin
     store.enterprise_id=NULL) — StoreInventory.enterprise_id STORE'ning
     enterprise_id'siga (NULL) teng bo'lishi kerak, buyer_enterprise_id'ga EMAS.
  3. [#8] Ikki marta ketma-ket accept (race simulyatsiyasi, finance modulidagi
     naqsh bilan bir xil) — ikkinchisi 422 marketplace.order_invalid_transition
     bilan bloklanishi kerak.

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.jwt import hash_password
from app.models.contract import Contract
from app.models.catalog import Product
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.marketplace import MarketplaceOrder, MarketplaceOrderLine
from app.models.store import Store
from app.models.store_inventory import StoreInventory
from app.models.user import AppUser
from app.modules.marketplace.service import AcceptLineInfo, accept_order
from app.tests.marketplace.conftest import TEST_PASSWORD


def _make_user(role: str, enterprise_id: uuid.UUID | None, suffix: str = "") -> AppUser:
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix + "adr036"))
    return AppUser(
        id=user_id,
        full_name=f"ADR036 {role.capitalize()} {suffix}",
        phone=f"+99897{str(phone_hash)[:7]}",
        role=role,
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=enterprise_id,
    )


async def _make_supplier_product(
    db_session: AsyncSession,
    supplier_enterprise_id: uuid.UUID,
    price: Decimal = Decimal("20000.00"),
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name_uz="ADR036 mahsulot",
        name_ru="ADR036 товар",
        sku=f"ADR036-{uuid.uuid4().hex[:8]}",
        unit="dona",
        is_active=True,
        marketplace_published=True,
        marketplace_price=price,
        version=1,
        enterprise_id=supplier_enterprise_id,
    )
    db_session.add(product)
    await db_session.flush()
    return product


async def _make_delivered_order(
    db_session: AsyncSession,
    *,
    buyer_enterprise_id: uuid.UUID | None,
    buyer_store_id: uuid.UUID,
    buyer_user_id: uuid.UUID,
    supplier_enterprise_id: uuid.UUID,
    product: Product,
    qty: Decimal = Decimal("5"),
) -> MarketplaceOrder:
    """Delivered holatdagi MarketplaceOrder + bitta line — accept uchun tayyor."""
    now = datetime.now(timezone.utc)
    order = MarketplaceOrder(
        id=uuid.uuid4(),
        buyer_enterprise_id=buyer_enterprise_id,
        buyer_store_id=buyer_store_id,
        buyer_user_id=buyer_user_id,
        supplier_enterprise_id=supplier_enterprise_id,
        status="delivered",
        total_amount=product.marketplace_price * qty,
        delivered_at=now,
    )
    db_session.add(order)
    await db_session.flush()

    line = MarketplaceOrderLine(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        qty=qty,
        unit_price=product.marketplace_price,
        line_total=product.marketplace_price * qty,
    )
    db_session.add(line)
    await db_session.flush()
    await db_session.refresh(order, ["lines"])
    return order


# ─── 1. Platforma-do'kon (mustaqil) o'z buyurtmasini qabul qiladi ────────────


@pytest.mark.asyncio
async def test_accept_order_platform_store_inventory_enterprise_null(
    db_session: AsyncSession,
) -> None:
    """
    Mustaqil platforma-do'kon (buyer_enterprise_id=NULL, store.enterprise_id=NULL)
    o'z buyurtmasini qabul qiladi — StoreInventory.enterprise_id=NULL yoziladi,
    500 XATOLIK BERMASLIGI kerak (0036 migratsiya PG'da NOT NULL olib tashlaydi).
    """
    supplier_ent = Enterprise(
        id=uuid.uuid4(), name="ADR036 Supplier", status="active",
        enabled_modules=list(ALL_MODULE_KEYS), version=1,
    )
    db_session.add(supplier_ent)
    await db_session.flush()

    buyer_user = _make_user("store", enterprise_id=None, suffix="buyer1")
    db_session.add(buyer_user)
    await db_session.flush()

    store = Store(
        id=uuid.uuid4(),
        name="Mustaqil Platforma Do'kon",
        user_id=buyer_user.id,
        enterprise_id=None,
        is_platform_managed=True,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    product = await _make_supplier_product(db_session, supplier_ent.id)

    order = await _make_delivered_order(
        db_session,
        buyer_enterprise_id=None,
        buyer_store_id=store.id,
        buyer_user_id=buyer_user.id,
        supplier_enterprise_id=supplier_ent.id,
        product=product,
        qty=Decimal("5"),
    )
    line_id = order.lines[0].id

    result = await accept_order(
        db_session,
        order_id=order.id,
        buyer_user=buyer_user,
        lines_info=[AcceptLineInfo(line_id=line_id, expiry_date=None, markup_percent=Decimal("20"))],
        store_id=store.id,
    )

    assert result.status == "accepted"

    inv_stmt = select(StoreInventory).where(StoreInventory.source_order_id == order.id)
    inv_result = await db_session.execute(inv_stmt)
    inv = inv_result.scalar_one()

    assert inv.enterprise_id is None, "Platforma-do'kon inventari enterprise_id=NULL bo'lishi kerak"
    assert inv.store_id == store.id
    assert inv.cost_price == Decimal("20000.00")
    assert inv.sale_price == Decimal("24000.00")


# ─── 2. [#11] StoreInventory.enterprise_id = store.enterprise_id, buyer EMAS ──


@pytest.mark.asyncio
async def test_accept_order_uses_store_enterprise_not_buyer_enterprise(
    db_session: AsyncSession,
) -> None:
    """
    order.buyer_enterprise_id = REAL tenant (masalan tenant admin platforma-
    do'kon nomidan shartnoma orqali accept qiladi), lekin store.enterprise_id
    = NULL (platforma-do'kon). StoreInventory.enterprise_id STORE'ning
    enterprise_id'si (NULL) bo'lishi kerak — order.buyer_enterprise_id (real
    UUID) EMAS. Bu #11 buzuqligini to'g'ridan-to'g'ri tekshiradi.
    """
    supplier_ent = Enterprise(
        id=uuid.uuid4(), name="ADR036 Supplier2", status="active",
        enabled_modules=list(ALL_MODULE_KEYS), version=1,
    )
    buyer_ent = Enterprise(
        id=uuid.uuid4(), name="ADR036 Buyer Tenant", status="active",
        enabled_modules=list(ALL_MODULE_KEYS), version=1,
    )
    db_session.add_all([supplier_ent, buyer_ent])
    await db_session.flush()

    admin_user = _make_user("administrator", enterprise_id=buyer_ent.id, suffix="admin2")
    db_session.add(admin_user)
    await db_session.flush()

    # Platforma-do'kon — hech qanday korxonaga tegishli emas
    store = Store(
        id=uuid.uuid4(),
        name="Shartnomali Platforma Do'kon",
        enterprise_id=None,
        is_platform_managed=True,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    # Shartnoma — admin_user korxonasi (buyer_ent) bu do'konni ko'rishi uchun
    contract = Contract(
        store_id=store.id,
        number="ADR036-ACCEPT-CONTRACT",
        valid_from=date.today() - timedelta(days=10),
        valid_to=date.today() + timedelta(days=365),
        contract_type="trade",
        supplier_enterprise_id=buyer_ent.id,
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()

    product = await _make_supplier_product(db_session, supplier_ent.id)

    # DIQQAT: buyer_enterprise_id=buyer_ent.id (REAL) — store.enterprise_id (None) bilan MOS EMAS
    order = await _make_delivered_order(
        db_session,
        buyer_enterprise_id=buyer_ent.id,
        buyer_store_id=store.id,
        buyer_user_id=admin_user.id,
        supplier_enterprise_id=supplier_ent.id,
        product=product,
        qty=Decimal("3"),
    )
    line_id = order.lines[0].id

    result = await accept_order(
        db_session,
        order_id=order.id,
        buyer_user=admin_user,
        lines_info=[AcceptLineInfo(line_id=line_id, expiry_date=None, markup_percent=Decimal("0"))],
        store_id=store.id,
    )
    assert result.status == "accepted"

    inv_stmt = select(StoreInventory).where(StoreInventory.source_order_id == order.id)
    inv_result = await db_session.execute(inv_stmt)
    inv = inv_result.scalar_one()

    assert inv.enterprise_id is None, (
        "Inventar STORE enterprise_id'siga (NULL) teng bo'lishi kerak, "
        f"buyer_enterprise_id ({buyer_ent.id}) ga EMAS"
    )


# ─── 3. [#8] Ketma-ket ikki marta accept — ikkinchisi bloklanadi ─────────────


@pytest.mark.asyncio
async def test_accept_order_sequential_double_accept_blocked(
    db_session: AsyncSession,
) -> None:
    """
    Race simulyatsiyasi (finance test_approve_entry_race naqshi bilan bir xil
    uslub — SQLite bir oqim, chin parallel bloklanish PG'da with_for_update()
    orqali sinaladi): birinchi accept muvaffaqiyatli, ikkinchisi (xuddi shu
    buyurtma, xuddi shu holatda) 422 marketplace.order_invalid_transition
    bilan bloklanishi SHART — buyurtma ikki marta qabul qilinib, StoreInventory
    ikki marta yaratilib qolmasligi kerak.
    """
    supplier_ent = Enterprise(
        id=uuid.uuid4(), name="ADR036 Supplier3", status="active",
        enabled_modules=list(ALL_MODULE_KEYS), version=1,
    )
    db_session.add(supplier_ent)
    await db_session.flush()

    buyer_user = _make_user("store", enterprise_id=None, suffix="buyer3")
    db_session.add(buyer_user)
    await db_session.flush()

    store = Store(
        id=uuid.uuid4(),
        name="Double Accept Do'kon",
        user_id=buyer_user.id,
        enterprise_id=None,
        is_platform_managed=True,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    product = await _make_supplier_product(db_session, supplier_ent.id)

    order = await _make_delivered_order(
        db_session,
        buyer_enterprise_id=None,
        buyer_store_id=store.id,
        buyer_user_id=buyer_user.id,
        supplier_enterprise_id=supplier_ent.id,
        product=product,
        qty=Decimal("4"),
    )
    line_id = order.lines[0].id
    lines_info = [AcceptLineInfo(line_id=line_id, expiry_date=None, markup_percent=Decimal("0"))]

    # 1-chaqiruv — muvaffaqiyatli
    result1 = await accept_order(
        db_session, order_id=order.id, buyer_user=buyer_user,
        lines_info=lines_info, store_id=store.id,
    )
    assert result1.status == "accepted"

    # 2-chaqiruv — xuddi shu buyurtma, endi status='accepted' → 422
    with pytest.raises(AppError) as exc_info:
        await accept_order(
            db_session, order_id=order.id, buyer_user=buyer_user,
            lines_info=lines_info, store_id=store.id,
        )
    assert exc_info.value.message_key == "marketplace.order_invalid_transition"
    assert exc_info.value.status_code == 422

    # Faqat BITTA StoreInventory yozuvi yaratilgan bo'lishi kerak
    inv_stmt = select(StoreInventory).where(StoreInventory.source_order_id == order.id)
    inv_result = await db_session.execute(inv_stmt)
    invs = inv_result.scalars().all()
    assert len(invs) == 1, "Ikkinchi accept StoreInventory qayta yaratmasligi kerak"
