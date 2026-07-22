"""
#27 [data-integrity] platforma-do'kon (buyer_enterprise_id IS NULL, ADR-003)
marketplace_order idempotentligi.

Qamrov:
  1. Bitta platforma-do'kon xuddi shu client_uuid bilan qayta so'rov yuborsa —
     dublikat YARATILMAYDI, bir xil buyurtma qaytadi (retry-safe).
  2. Ikki xil platforma-do'kon TASODIFAN bir xil client_uuid ishlatsa —
     bir-birining buyurtmasini OLMAYDI (kross-do'kon leak yo'q) — har biri
     o'z alohida buyurtmasini oladi.
  3. buyer_enterprise_id VA buyer_store_id ikkalasi ham None bo'lganda
     (masalan explicit buyer_store_id berilmagan agent so'rovi) —
     idempotentlik qidiruvi BUTUNLAY o'tkazib yuboriladi (eski kross-tenant
     client_uuid-only fallback OLIB TASHLANGAN) — ikkala chaqiruv HAM
     alohida buyurtma yaratadi (bir-birining o'rniga qaytmaydi).

Infrasiz: aiosqlite (marketplace/conftest.py db_session/engine).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import hash_password
from app.models.catalog import Product
from app.models.contract import Contract
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.marketplace import MarketplaceOrder
from app.models.store import Store
from app.models.user import AppUser
from app.modules.marketplace.service import OrderLineInput, create_order


def _make_user(role: str, enterprise_id: uuid.UUID | None, suffix: str) -> AppUser:
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix + "platidem"))
    return AppUser(
        id=user_id,
        full_name=f"PlatIdem {role.capitalize()} {suffix}",
        phone=f"+99893{str(phone_hash)[:7]}",
        role=role,
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=enterprise_id,
    )


async def _make_supplier(db_session: AsyncSession, suffix: str) -> Enterprise:
    ent = Enterprise(
        id=uuid.uuid4(),
        name=f"PlatIdem Supplier {suffix}",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


async def _make_published_product(
    db_session: AsyncSession, supplier_enterprise_id: uuid.UUID, suffix: str
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name_uz=f"PlatIdem mahsulot {suffix}",
        name_ru=f"PlatIdem tovar {suffix}",
        sku=f"PLATIDEM-{uuid.uuid4().hex[:8]}",
        unit="dona",
        is_active=True,
        marketplace_published=True,
        marketplace_price=Decimal("5000.00"),
        version=1,
        enterprise_id=supplier_enterprise_id,
    )
    db_session.add(product)
    await db_session.flush()
    return product


async def _make_platform_store_with_contract(
    db_session: AsyncSession,
    supplier_enterprise_id: uuid.UUID,
    suffix: str,
) -> tuple[AppUser, Store]:
    """Platforma-do'kon (buyer_enterprise_id/store.enterprise_id=NULL) + aktiv shartnoma."""
    buyer_user = _make_user("store", enterprise_id=None, suffix=suffix)
    db_session.add(buyer_user)
    await db_session.flush()

    store = Store(
        id=uuid.uuid4(),
        name=f"PlatIdem Do'kon {suffix}",
        user_id=buyer_user.id,
        enterprise_id=None,
        is_platform_managed=True,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    contract = Contract(
        store_id=store.id,
        number=f"PLATIDEM-{suffix}-{uuid.uuid4().hex[:6]}",
        valid_from=date.today() - timedelta(days=5),
        valid_to=date.today() + timedelta(days=365),
        contract_type="trade",
        supplier_enterprise_id=supplier_enterprise_id,
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()

    return buyer_user, store


# ─── 1. Bitta platforma-do'kon retry — dublikat yo'q ─────────────────────────


@pytest.mark.asyncio
async def test_platform_store_idempotent_retry_no_duplicate(
    db_session: AsyncSession,
) -> None:
    supplier_ent = await _make_supplier(db_session, "1")
    product = await _make_published_product(db_session, supplier_ent.id, "1")
    buyer_user, store = await _make_platform_store_with_contract(
        db_session, supplier_ent.id, "1"
    )

    client_uuid = uuid.uuid4()
    lines = [OrderLineInput(product_id=product.id, qty=Decimal("2"))]

    order1 = await create_order(
        db_session, buyer_user, lines, client_uuid=client_uuid
    )
    order2 = await create_order(
        db_session, buyer_user, lines, client_uuid=client_uuid
    )

    assert order2.id == order1.id, "Retry bir xil buyurtmani qaytarishi kerak"

    count_stmt = select(func.count()).select_from(
        select(MarketplaceOrder.id)
        .where(MarketplaceOrder.buyer_store_id == store.id)
        .subquery()
    )
    total = (await db_session.execute(count_stmt)).scalar_one()
    assert total == 1, "Faqat bitta buyurtma yaratilishi kerak (dublikat yo'q)"


# ─── 2. Ikki xil platforma-do'kon bir xil client_uuid — kross-do'kon leak yo'q ─


@pytest.mark.asyncio
async def test_platform_store_idempotency_no_cross_store_leak(
    db_session: AsyncSession,
) -> None:
    supplier_ent = await _make_supplier(db_session, "2")
    product = await _make_published_product(db_session, supplier_ent.id, "2")

    buyer_user_x, store_x = await _make_platform_store_with_contract(
        db_session, supplier_ent.id, "X"
    )
    buyer_user_y, store_y = await _make_platform_store_with_contract(
        db_session, supplier_ent.id, "Y"
    )

    # ATAYLAB bir xil client_uuid — ikki mustaqil do'kon tasodifan bir xil
    # UUID generatsiya qilgan holatni simulyatsiya qiladi.
    shared_client_uuid = uuid.uuid4()
    lines = [OrderLineInput(product_id=product.id, qty=Decimal("1"))]

    order_x = await create_order(
        db_session, buyer_user_x, lines, client_uuid=shared_client_uuid
    )
    order_y = await create_order(
        db_session, buyer_user_y, lines, client_uuid=shared_client_uuid
    )

    assert order_x.id != order_y.id, (
        "Ikki xil do'kon buyurtmasi bir-birining o'rniga qaytmasligi kerak "
        "(kross-do'kon idempotentlik leak)"
    )
    assert order_x.buyer_store_id == store_x.id
    assert order_y.buyer_store_id == store_y.id


# ─── 3. buyer_enterprise_id VA buyer_store_id ikkalasi ham None — skip ───────


@pytest.mark.asyncio
async def test_platform_no_store_no_enterprise_idempotency_skipped(
    db_session: AsyncSession,
) -> None:
    """
    #27: eski kod bu holatda `MarketplaceOrder.client_uuid == client_uuid`
    FAQAT filtri bilan qidiruv qilardi — bu boshqa foydalanuvchining bir xil
    client_uuid'li buyurtmasini noto'g'ri qaytarishi mumkin edi (kross-tenant
    data-leak). Endi bu holatda idempotentlik qidiruvi UMUMAN qilinmaydi —
    har chaqiruv alohida buyurtma yaratadi.
    """
    supplier_ent = await _make_supplier(db_session, "3")
    product = await _make_published_product(db_session, supplier_ent.id, "3")

    # enterprise_id=None, role != "store", buyer_store_id EXPLICIT berilmagan
    # → effective_buyer_store_id ham None qoladi (avto-topish faqat "store"
    # rolida ishlaydi; contract-gate effective_buyer_store_id None bo'lgani
    # uchun o'tkazib yuboriladi).
    buyer_user_1 = _make_user("agent", enterprise_id=None, suffix="noctx1")
    buyer_user_2 = _make_user("agent", enterprise_id=None, suffix="noctx2")
    db_session.add_all([buyer_user_1, buyer_user_2])
    await db_session.flush()

    shared_client_uuid = uuid.uuid4()
    lines = [OrderLineInput(product_id=product.id, qty=Decimal("1"))]

    order_1 = await create_order(
        db_session, buyer_user_1, lines, client_uuid=shared_client_uuid
    )
    order_2 = await create_order(
        db_session, buyer_user_2, lines, client_uuid=shared_client_uuid
    )

    assert order_1.id != order_2.id, (
        "buyer_enterprise_id/buyer_store_id ikkalasi ham None bo'lganda "
        "idempotentlik qidiruvi o'tkazib yuborilishi kerak — ikki alohida "
        "buyurtma yaratilishi kerak"
    )
    assert order_1.buyer_user_id == buyer_user_1.id
    assert order_2.buyer_user_id == buyer_user_2.id

    count_stmt = select(func.count()).select_from(
        select(MarketplaceOrder.id)
        .where(MarketplaceOrder.client_uuid == shared_client_uuid)
        .subquery()
    )
    total = (await db_session.execute(count_stmt)).scalar_one()
    assert total == 2, "Ikkala buyurtma ham alohida yozuv sifatida saqlanishi kerak"
