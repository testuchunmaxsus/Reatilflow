"""
Sync testlari uchun fixtures — T13.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL, Redis kerak emas.

Fixtures:
  engine        — aiosqlite in-memory async engine
  db_session    — har test uchun yangi async session
  fake_redis    — fakeredis async klient
  sync_client   — app dependency override qilingan AsyncClient
  make_user     — AppUser yaratish factory
  make_store    — Store yaratish factory
  make_price_segment — PriceSegment yaratish factory
  make_product  — Product + narx factory
  seed_stock    — StockBalance boshlang'ich qoldiq
  admin_user, agent_user, store_user — tayyor foydalanuvchilar
  get_token     — foydalanuvchi uchun access token olish
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.catalog import Category, PriceSegment, Product, ProductPrice
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.stock import service as stock_service
from app.modules.stock.schemas import StockMovementCreate
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"
DEFAULT_WAREHOUSE = uuid.UUID("ffffcccc-0000-7000-8000-aaaaaaaaaaaa")


# ─── Engine ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def engine():
    """Har test uchun yangi aiosqlite in-memory engine."""
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
    """Har test uchun yangi async session."""
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


# ─── Fake Redis ──────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Default Enterprise ─────────────────────────────────────────────────────


@pytest.fixture
async def default_enterprise(db_session: AsyncSession) -> Enterprise:
    """MT1: Default test korxonasi."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Test Korxona",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture(autouse=True)
def _tenant_context(default_enterprise: Enterprise):
    """
    MT2: so'rov kontekstini default korxonaga o'rnatadi.

    Sync testlari outbox hodisalarini to'g'ridan-to'g'ri (OutboxEvent(...)) yaratadi.
    Prod'da bu hodisalar so'rov kontekstida (ContextVar o'rnatilgan) yaratiladi va
    enterprise_id'ni avtomatik oladi. Bu fixture shu kontekstni taqlid qiladi —
    inline OutboxEvent'lar default orqali enterprise_id = default_enterprise oladi.
    """
    from app.core.tenant_context import set_current_enterprise

    set_current_enterprise(default_enterprise.id)
    yield
    set_current_enterprise(None)


# ─── Foydalanuvchi factory ────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        role: str,
        phone: str | None = None,
        is_active: bool = True,
        branch_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> AppUser:
        user_id = uuid.uuid4()
        user = AppUser(
            id=user_id,
            full_name=f"Test {role.capitalize()}",
            phone=phone or f"+99890{str(abs(hash(str(user_id))))[:7]}",
            role=role,
            branch_id=branch_id,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=is_active,
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
async def agent_user(make_user) -> AppUser:
    return await make_user("agent")


@pytest.fixture
async def store_user(make_user) -> AppUser:
    return await make_user("store")


@pytest.fixture
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


# ─── PriceSegment factory ─────────────────────────────────────────────────────


@pytest.fixture
def make_price_segment(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name: str = "Standart",
        enterprise_id: uuid.UUID | None = None,
    ) -> PriceSegment:
        seg = PriceSegment(
            name=f"{name}-{uuid.uuid4().hex[:6]}",
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(seg)
        await db_session.flush()
        return seg

    return _factory


# ─── Product + narx factory ───────────────────────────────────────────────────


@pytest.fixture
def make_product(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name_uz: str = "Test mahsulot",
        name_ru: str = "Test tovar",
        sku: str | None = None,
        is_active: bool = True,
        price: Decimal | None = None,
        segment_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Product:
        from datetime import datetime, timezone

        eid = enterprise_id if enterprise_id is not None else default_enterprise.id
        prod_id = uuid.uuid4()
        sku = sku or f"SKU-{str(prod_id)[:8]}"
        prod = Product(
            id=prod_id,
            name_uz=name_uz,
            name_ru=name_ru,
            sku=sku,
            unit="dona",
            is_active=is_active,
            version=1,
            enterprise_id=eid,
        )
        db_session.add(prod)
        await db_session.flush()

        if price is not None:
            if segment_id is None:
                seg = PriceSegment(
                    name=f"Seg-{uuid.uuid4().hex[:8]}",
                    enterprise_id=eid,
                )
                db_session.add(seg)
                await db_session.flush()
                segment_id = seg.id

            pp = ProductPrice(
                product_id=prod_id,
                segment_id=segment_id,
                price=price,
                currency="UZS",
                valid_from=datetime.now(timezone.utc),
                valid_to=None,
                enterprise_id=eid,
            )
            db_session.add(pp)
            await db_session.flush()

        return prod

    return _factory


# ─── Store factory ────────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name: str = "Test Do'kon",
        user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        segment_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            user_id=user_id,
            agent_id=agent_id,
            branch_id=branch_id,
            segment_id=segment_id,
            version=1,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── Stock seed fixture ───────────────────────────────────────────────────────


@pytest.fixture
def seed_stock(db_session: AsyncSession):
    async def _factory(
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID = DEFAULT_WAREHOUSE,
        qty: Decimal = Decimal("100"),
    ) -> None:
        data = StockMovementCreate(
            product_id=product_id,
            warehouse_id=warehouse_id,
            type="in",
            qty=qty,
        )
        await stock_service.record_movement(db_session, data, actor_id=None, redis=None)

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def sync_client(
    db_session: AsyncSession,
    fake_redis,
):
    """
    Dependency override qilingan AsyncClient (sync testlari uchun).

    get_db()    → db_session (aiosqlite in-memory)
    get_redis() → fake_redis (fakeredis)
    """

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ─── Token yordamchisi ────────────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
