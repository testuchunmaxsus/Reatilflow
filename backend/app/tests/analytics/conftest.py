"""
AI Tahlil testlari uchun fixtures — Faza 4.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL/Redis kerak emas.

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session
  fake_redis      — fakeredis async klient
  analytics_client — app dependency override qilingan AsyncClient
  default_enterprise — test korxonasi (analytics moduli yoqilgan)
  other_enterprise   — boshqa korxona (IDOR test uchun)
  make_user          — AppUser factory
  admin_user, accountant_user, agent_user, store_user_obj
  make_store         — Store factory
  make_product       — Product factory (enterprise_id bilan)
  make_contract      — Contract factory (supplier_enterprise_id bilan)
  make_pos_sale      — PosSale + PosSaleLine factory
  make_inventory     — StoreInventory factory
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db, get_db_replica
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.catalog import Product
from app.models.contract import Contract
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.pos import PosSale, PosSaleLine
from app.models.store import Store
from app.models.store_inventory import StoreInventory
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"
OTHER_ENTERPRISE_UUID = uuid.UUID("00000000-0000-7000-8000-000000000088")


# ─── Engine ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def engine():
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
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Enterprises ─────────────────────────────────────────────────────────────


@pytest.fixture
async def default_enterprise(db_session: AsyncSession) -> Enterprise:
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Test Korxona (Supplier)",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def other_enterprise(db_session: AsyncSession) -> Enterprise:
    """Boshqa korxona — IDOR testlari uchun."""
    ent = Enterprise(
        id=OTHER_ENTERPRISE_UUID,
        name="Boshqa Korxona",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


# ─── Users ────────────────────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        role: str,
        enterprise_id: uuid.UUID | None = None,
    ) -> AppUser:
        user_id = uuid.uuid4()
        user = AppUser(
            id=user_id,
            full_name=f"Test {role.capitalize()}",
            phone=f"+9989{str(abs(hash(str(user_id))))[:8]}",
            role=role,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
            biometric_enrolled=False,
            locale="uz",
            device_id=None,
            version=1,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _factory


@pytest.fixture
async def admin_user(make_user) -> AppUser:
    return await make_user("administrator")


@pytest.fixture
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def agent_user(make_user) -> AppUser:
    return await make_user("agent")


@pytest.fixture
async def store_user_obj(make_user) -> AppUser:
    return await make_user("store")


# ─── Stores ───────────────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name: str = "Test Do'kon",
        enterprise_id: uuid.UUID | None = None,
        gps_lat: Decimal | None = None,
        gps_lng: Decimal | None = None,
        address: str | None = None,
    ) -> Store:
        store = Store(
            name=name,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            address=address,
            version=1,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── Products ─────────────────────────────────────────────────────────────────


@pytest.fixture
def make_product(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name_uz: str = "Test Mahsulot",
        enterprise_id: uuid.UUID | None = None,
    ) -> Product:
        from app.core.uuid7 import uuid7

        product = Product(
            id=uuid7(),
            name_uz=name_uz,
            name_ru=name_uz,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
            is_active=True,
            version=1,
        )
        db_session.add(product)
        await db_session.flush()
        return product

    return _factory


# ─── Contracts ────────────────────────────────────────────────────────────────


@pytest.fixture
def make_contract(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        store_id: uuid.UUID,
        supplier_enterprise_id: uuid.UUID | None = None,
        valid_to: date | None = None,
        valid_from: date | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Contract:
        from app.core.uuid7 import uuid7

        today = datetime.now(timezone.utc).date()
        contract = Contract(
            id=uuid7(),
            store_id=store_id,
            number=f"CTR-{str(uuid.uuid4())[:8]}",
            valid_from=valid_from or today,
            valid_to=valid_to or (today + timedelta(days=90)),
            supplier_enterprise_id=supplier_enterprise_id or default_enterprise.id,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
            version=1,
        )
        db_session.add(contract)
        await db_session.flush()
        return contract

    return _factory


# ─── POS Sale + Lines ─────────────────────────────────────────────────────────


@pytest.fixture
def make_pos_sale(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        store_id: uuid.UUID,
        lines: list[tuple[uuid.UUID, Decimal, Decimal]],  # (product_id, qty, unit_price)
        status: str = "completed",
        created_at: datetime | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> PosSale:
        from app.core.uuid7 import uuid7

        eid = enterprise_id if enterprise_id is not None else default_enterprise.id
        now = created_at or datetime.now(timezone.utc)

        total = sum(qty * unit_price for _, qty, unit_price in lines)
        sale = PosSale(
            id=uuid7(),
            store_id=store_id,
            total_amount=total,
            discount_amount=Decimal("0"),
            payment_method="cash",
            status=status,
            enterprise_id=eid,
            created_at=now,
            updated_at=now,
        )
        db_session.add(sale)
        await db_session.flush()

        for product_id, qty, unit_price in lines:
            line = PosSaleLine(
                id=uuid7(),
                sale_id=sale.id,
                product_id=product_id,
                qty=qty,
                unit_price=unit_price,
                line_total=qty * unit_price,
                enterprise_id=eid,
            )
            db_session.add(line)

        await db_session.flush()
        return sale

    return _factory


# ─── StoreInventory ───────────────────────────────────────────────────────────


@pytest.fixture
def make_inventory(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        store_id: uuid.UUID,
        product_id: uuid.UUID,
        qty: Decimal = Decimal("100"),
        cost_price: Decimal = Decimal("10000"),
        sale_price: Decimal = Decimal("12000"),
        expiry_date: date | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> StoreInventory:
        from app.core.uuid7 import uuid7

        eid = enterprise_id if enterprise_id is not None else default_enterprise.id
        inv = StoreInventory(
            id=uuid7(),
            enterprise_id=eid,
            store_id=store_id,
            product_id=product_id,
            qty=qty,
            cost_price=cost_price,
            sale_price=sale_price,
            markup_percent=Decimal("20"),
            expiry_date=expiry_date,
            status="active",
        )
        db_session.add(inv)
        await db_session.flush()
        return inv

    return _factory


# ─── HTTP klient ─────────────────────────────────────────────────────────────


@pytest.fixture
async def analytics_client(
    db_session: AsyncSession,
    fake_redis,
):
    async def _get_test_db():
        yield db_session

    async def _get_test_db_replica():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_db_replica] = _get_test_db_replica
    app.dependency_overrides[get_redis] = _get_test_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


async def get_token(client: AsyncClient, user: AppUser) -> str:
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
