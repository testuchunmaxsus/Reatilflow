"""
Promo testlari uchun fixtures — T25 Aksiya moduli.

Infrasiz (aiosqlite + fakeredis + FakeStorage) — haqiqiy infra kerak emas.

Fixtures:
  engine         — aiosqlite in-memory async engine
  db_session     — har test uchun yangi async session
  fake_redis     — fakeredis async klient
  fake_storage   — FakeStorage in-memory
  promo_client   — app dependency override qilingan AsyncClient
  make_user      — AppUser factory (har rol)
  make_store     — Store factory (segment_id bilan)
  make_product   — Product factory (narx bilan)
  make_price_segment — PriceSegment factory
  make_promo     — Promo factory (test uchun)
  seed_stock     — StockBalance boshlang'ich qoldig'ini sozlash
  admin_user, agent_user, store_user, accountant_user, courier_user
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

from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.core.storage import FakeStorage, get_storage
from app.main import app
from app.models.base import Base
from app.models.catalog import PriceSegment, Product, ProductPrice
from app.models.promo import Promo
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.stock import service as stock_service
from app.modules.stock.schemas import StockMovementCreate

TEST_PASSWORD = "TestPassword123!"
DEFAULT_WAREHOUSE = uuid.UUID("ffffcccc-0000-7000-8000-aaaaaaaaaaaa")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _yesterday() -> date:
    return _today() - timedelta(days=1)


def _tomorrow() -> date:
    return _today() + timedelta(days=1)


# ─── Engine ──────────────────────────────────────────────────────────────────


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


# ─── Fake Redis ───────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
    """Har test uchun yangi fakeredis."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── FakeStorage ─────────────────────────────────────────────────────────────


@pytest.fixture
def fake_storage():
    """FakeStorage in-memory instance."""
    return FakeStorage()


# ─── Foydalanuvchi factory ─────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession):
    """Factory: berilgan rol bilan AppUser yaratadi."""

    async def _factory(
        role: str,
        phone: str | None = None,
        is_active: bool = True,
        branch_id: uuid.UUID | None = None,
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
def make_price_segment(db_session: AsyncSession):
    """Factory: PriceSegment yaratadi."""

    async def _factory(name: str = "Standart") -> PriceSegment:
        seg = PriceSegment(name=f"{name}-{uuid.uuid4().hex[:6]}")
        db_session.add(seg)
        await db_session.flush()
        return seg

    return _factory


# ─── Product factory ─────────────────────────────────────────────────────────


@pytest.fixture
def make_product(db_session: AsyncSession):
    """Factory: Product va ixtiyoriy narx bilan yaratadi."""

    async def _factory(
        name_uz: str = "Test mahsulot",
        name_ru: str = "Test tovar",
        sku: str | None = None,
        is_active: bool = True,
        price: Decimal | None = None,
        segment_id: uuid.UUID | None = None,
    ) -> Product:
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
        )
        db_session.add(prod)
        await db_session.flush()

        if price is not None:
            if segment_id is None:
                seg = PriceSegment(name=f"Seg-{uuid.uuid4().hex[:8]}")
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
            )
            db_session.add(pp)
            await db_session.flush()

        return prod

    return _factory


# ─── Store factory ───────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession):
    """Factory: Store yaratadi (ixtiyoriy segment_id bilan)."""

    async def _factory(
        name: str = "Test Do'kon",
        user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        segment_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            user_id=user_id,
            agent_id=agent_id,
            branch_id=branch_id,
            segment_id=segment_id,
            version=1,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── Promo factory ───────────────────────────────────────────────────────────


@pytest.fixture
def make_promo(db_session: AsyncSession):
    """Factory: Promo yaratadi."""

    async def _factory(
        name_uz: str = "Test aksiya",
        name_ru: str = "Test акция",
        promo_type: str = "discount",
        rule_json: dict | None = None,
        valid_from: date | None = None,
        valid_to: date | None = None,
        is_active: bool = True,
        target_segment_id: uuid.UUID | None = None,
        target_product_id: uuid.UUID | None = None,
        client_uuid: uuid.UUID | None = None,
    ) -> Promo:
        from app.core.uuid7 import uuid7 as _uuid7

        today = _today()
        promo = Promo(
            id=_uuid7(),
            name_uz=name_uz,
            name_ru=name_ru,
            promo_type=promo_type,
            rule_json=rule_json or {"discount_percent": 10},
            valid_from=valid_from or today,
            valid_to=valid_to or (today + timedelta(days=30)),
            is_active=is_active,
            target_segment_id=target_segment_id,
            target_product_id=target_product_id,
            client_uuid=client_uuid,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(promo)
        await db_session.flush()
        return promo

    return _factory


# ─── Stock boshlang'ich qoldiq sozlash ────────────────────────────────────────


@pytest.fixture
def seed_stock(db_session: AsyncSession):
    """Factory: StockBalance boshlang'ich qoldig'ini sozlaydi."""

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
async def promo_client(
    db_session: AsyncSession,
    fake_redis,
    fake_storage,
):
    """
    Dependency override qilingan AsyncClient.

    get_db()      → db_session (aiosqlite in-memory)
    get_redis()   → fake_redis (fakeredis)
    get_storage() → fake_storage (FakeStorage)
    """

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis
    app.dependency_overrides[get_storage] = lambda: fake_storage

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ─── Token olish yordamchisi ──────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
