"""
Append-only DB invariant testlari — ledger_entry va stock_movement.

DB-darajali triggerlar (SQLite RAISE(ABORT), PostgreSQL RAISE EXCEPTION) orqali
UPDATE va DELETE operatsiyalari bloklanishini tekshiradi.

Test rejasi:
  (a) ledger_entry INSERT → muvaffaqiyatli
  (b) ledger_entry UPDATE → DatabaseError ko'taradi
  (c) ledger_entry DELETE → DatabaseError ko'taradi
  (d) stock_movement INSERT → muvaffaqiyatli
  (e) stock_movement UPDATE → DatabaseError ko'taradi
  (f) stock_movement DELETE → DatabaseError ko'taradi
  (g) REGRESSIYA: account_balance UPDATE → hali ham ruxsat (mutable jadval)
  (h) REGRESSIYA: stock_balance UPDATE → hali ham ruxsat (mutable jadval)

MUHIM: ORM orqali UPDATE/DELETE sinovdan o'tkaziladi (haqiqiy ilova yo'lini aks ettiradi).
Xatodan keyin session.rollback() chaqiriladi — keyingi test uchun session tozalanadi.

Infrasiz: aiosqlite in-memory (create_all → triggerlar avtomatik o'rnatiladi).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.jwt import hash_password
from app.core.uuid7 import uuid7
from app.models.base import Base
from app.models.catalog import Category, Product
from app.models.finance import AccountBalance, LedgerEntry
from app.models.stock import StockBalance, StockMovement
from app.models.store import Store
from app.models.user import AppUser

# append_only modulini import qilish shart — event'lar ro'yxatdan o'tishi uchun
import app.models.append_only  # noqa: F401


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def ao_engine():
    """
    Append-only testlari uchun yangi aiosqlite in-memory engine.
    create_all → DDL event listeners → SQLite triggerlar avtomatik o'rnatiladi.
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def ao_session(ao_engine) -> AsyncGenerator[AsyncSession, None]:
    """Har test uchun yangi async session (rollback bilan tozalanadi)."""
    session_factory = async_sessionmaker(
        bind=ao_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def ao_store(ao_session: AsyncSession) -> Store:
    """Test uchun Store yozuvi."""
    store = Store(
        id=uuid7(),
        name="Append-Only Test Do'kon",
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    ao_session.add(store)
    await ao_session.flush()
    return store


@pytest.fixture
async def ao_product(ao_session: AsyncSession) -> Product:
    """Test uchun Product yozuvi."""
    cat = Category(
        id=uuid7(),
        name_uz="Test Cat",
        name_ru="Test Cat",
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    ao_session.add(cat)
    await ao_session.flush()

    prod = Product(
        id=uuid7(),
        name_uz="Test mahsulot",
        name_ru="Test tovar",
        sku=f"SKU-AO-{uuid.uuid4().hex[:8]}",
        unit="dona",
        is_active=True,
        category_id=cat.id,
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    ao_session.add(prod)
    await ao_session.flush()
    return prod


@pytest.fixture
async def ao_ledger_entry(ao_session: AsyncSession, ao_store: Store) -> LedgerEntry:
    """Test uchun LedgerEntry yozuvi (committed)."""
    entry = LedgerEntry(
        id=uuid7(),
        store_id=ao_store.id,
        type="debit",
        amount=Decimal("5000.00"),
        currency="UZS",
        entry_date=_now(),
        created_at=_now(),
    )
    ao_session.add(entry)
    await ao_session.commit()
    return entry


@pytest.fixture
async def ao_stock_movement(ao_session: AsyncSession, ao_product: Product) -> StockMovement:
    """Test uchun StockMovement yozuvi (committed)."""
    movement = StockMovement(
        id=uuid7(),
        product_id=ao_product.id,
        warehouse_id=uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001"),
        type="in",
        qty=Decimal("10.0000"),
        moved_at=_now(),
        created_at=_now(),
    )
    ao_session.add(movement)
    await ao_session.commit()
    return movement


# ─── (a) ledger_entry INSERT → muvaffaqiyatli ─────────────────────────────────


@pytest.mark.asyncio
async def test_ledger_entry_insert_allowed(
    ao_session: AsyncSession,
    ao_store: Store,
) -> None:
    """(a) ledger_entry INSERT → trigger bloklamaydi, yozuv DB ga saqlanadi."""
    entry = LedgerEntry(
        id=uuid7(),
        store_id=ao_store.id,
        type="credit",
        amount=Decimal("1000.00"),
        currency="UZS",
        entry_date=_now(),
        created_at=_now(),
    )
    ao_session.add(entry)
    await ao_session.flush()

    result = await ao_session.execute(
        select(LedgerEntry).where(LedgerEntry.id == entry.id)
    )
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.amount == Decimal("1000.00")


# ─── (b) ledger_entry UPDATE → trigger bloklaydiledi ─────────────────────────


@pytest.mark.asyncio
async def test_ledger_entry_update_blocked(
    ao_session: AsyncSession,
    ao_ledger_entry: LedgerEntry,
) -> None:
    """(b) ledger_entry UPDATE → DatabaseError (RAISE ABORT / EXCEPTION)."""
    # Yozuvni session ga yuklash
    result = await ao_session.execute(
        select(LedgerEntry).where(LedgerEntry.id == ao_ledger_entry.id)
    )
    entry = result.scalar_one()

    # ORM orqali maydonni o'zgartirishga urinish
    entry.amount = Decimal("99999.00")

    with pytest.raises(sqlalchemy.exc.DatabaseError):
        await ao_session.flush()

    # Session rollback — keyingi test uchun tozalaymiz
    await ao_session.rollback()


# ─── (c) ledger_entry DELETE → trigger bloklaydiledi ─────────────────────────


@pytest.mark.asyncio
async def test_ledger_entry_delete_blocked(
    ao_session: AsyncSession,
    ao_ledger_entry: LedgerEntry,
) -> None:
    """(c) ledger_entry DELETE → DatabaseError (RAISE ABORT / EXCEPTION)."""
    result = await ao_session.execute(
        select(LedgerEntry).where(LedgerEntry.id == ao_ledger_entry.id)
    )
    entry = result.scalar_one()

    # ORM orqali o'chirishga urinish
    await ao_session.delete(entry)

    with pytest.raises(sqlalchemy.exc.DatabaseError):
        await ao_session.flush()

    await ao_session.rollback()


# ─── (d) stock_movement INSERT → muvaffaqiyatli ───────────────────────────────


@pytest.mark.asyncio
async def test_stock_movement_insert_allowed(
    ao_session: AsyncSession,
    ao_product: Product,
) -> None:
    """(d) stock_movement INSERT → trigger bloklamaydi, yozuv DB ga saqlanadi."""
    wh_id = uuid.UUID("bbbbbbbb-2222-0000-0000-000000000002")
    movement = StockMovement(
        id=uuid7(),
        product_id=ao_product.id,
        warehouse_id=wh_id,
        type="in",
        qty=Decimal("25.0000"),
        moved_at=_now(),
        created_at=_now(),
    )
    ao_session.add(movement)
    await ao_session.flush()

    result = await ao_session.execute(
        select(StockMovement).where(StockMovement.id == movement.id)
    )
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.qty == Decimal("25.0000")


# ─── (e) stock_movement UPDATE → trigger bloklaydiledi ───────────────────────


@pytest.mark.asyncio
async def test_stock_movement_update_blocked(
    ao_session: AsyncSession,
    ao_stock_movement: StockMovement,
) -> None:
    """(e) stock_movement UPDATE → DatabaseError (RAISE ABORT / EXCEPTION)."""
    result = await ao_session.execute(
        select(StockMovement).where(StockMovement.id == ao_stock_movement.id)
    )
    movement = result.scalar_one()

    # ORM orqali maydonni o'zgartirishga urinish
    movement.qty = Decimal("999.0000")

    with pytest.raises(sqlalchemy.exc.DatabaseError):
        await ao_session.flush()

    await ao_session.rollback()


# ─── (f) stock_movement DELETE → trigger bloklaydiledi ───────────────────────


@pytest.mark.asyncio
async def test_stock_movement_delete_blocked(
    ao_session: AsyncSession,
    ao_stock_movement: StockMovement,
) -> None:
    """(f) stock_movement DELETE → DatabaseError (RAISE ABORT / EXCEPTION)."""
    result = await ao_session.execute(
        select(StockMovement).where(StockMovement.id == ao_stock_movement.id)
    )
    movement = result.scalar_one()

    # ORM orqali o'chirishga urinish
    await ao_session.delete(movement)

    with pytest.raises(sqlalchemy.exc.DatabaseError):
        await ao_session.flush()

    await ao_session.rollback()


# ─── (g) REGRESSIYA: account_balance UPDATE → hali ham ruxsat ────────────────


@pytest.mark.asyncio
async def test_account_balance_update_still_allowed(
    ao_session: AsyncSession,
    ao_store: Store,
) -> None:
    """
    (g) REGRESSIYA: account_balance (mutable jadval) — triggerga ega emas.
    UPDATE hali ham ruxsat berilgan. Balanslar yangilanishi kerak.
    """
    # AccountBalance yaratish
    balance = AccountBalance(
        id=uuid7(),
        store_id=ao_store.id,
        balance=Decimal("0.00"),
        currency="UZS",
        last_recalc_at=_now(),
        version=1,
    )
    ao_session.add(balance)
    await ao_session.flush()
    await ao_session.commit()

    # ORM orqali yangilash — trigger yo'q, muvaffaqiyatli bo'lishi kerak
    result = await ao_session.execute(
        select(AccountBalance).where(AccountBalance.store_id == ao_store.id)
    )
    bal = result.scalar_one()
    bal.balance = Decimal("12345.00")
    bal.version = bal.version + 1

    # Xato BOLMASLIGI KERAK
    await ao_session.flush()
    await ao_session.commit()

    # Tekshirish
    result2 = await ao_session.execute(
        select(AccountBalance).where(AccountBalance.store_id == ao_store.id)
    )
    updated = result2.scalar_one()
    assert updated.balance == Decimal("12345.00")
    assert updated.version == 2


# ─── (h) REGRESSIYA: stock_balance UPDATE → hali ham ruxsat ──────────────────


@pytest.mark.asyncio
async def test_stock_balance_update_still_allowed(
    ao_session: AsyncSession,
    ao_product: Product,
) -> None:
    """
    (h) REGRESSIYA: stock_balance (mutable jadval) — triggerga ega emas.
    UPDATE hali ham ruxsat berilgan. Ombor qoldig'i yangilanishi kerak.
    """
    wh_id = uuid.UUID("cccccccc-3333-0000-0000-000000000003")

    # StockBalance yaratish
    balance = StockBalance(
        id=uuid7(),
        product_id=ao_product.id,
        warehouse_id=wh_id,
        qty_on_hand=Decimal("0.0000"),
        qty_reserved=Decimal("0.0000"),
        version=1,
        updated_at=_now(),
    )
    ao_session.add(balance)
    await ao_session.flush()
    await ao_session.commit()

    # ORM orqali yangilash — trigger yo'q, muvaffaqiyatli bo'lishi kerak
    result = await ao_session.execute(
        select(StockBalance).where(
            StockBalance.product_id == ao_product.id,
            StockBalance.warehouse_id == wh_id,
        )
    )
    bal = result.scalar_one()
    bal.qty_on_hand = Decimal("50.0000")
    bal.version = bal.version + 1
    bal.updated_at = _now()

    # Xato BOLMASLIGI KERAK
    await ao_session.flush()
    await ao_session.commit()

    # Tekshirish
    result2 = await ao_session.execute(
        select(StockBalance).where(
            StockBalance.product_id == ao_product.id,
            StockBalance.warehouse_id == wh_id,
        )
    )
    updated = result2.scalar_one()
    assert updated.qty_on_hand == Decimal("50.0000")
    assert updated.version == 2
