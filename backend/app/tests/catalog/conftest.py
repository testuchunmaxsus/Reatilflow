"""
Katalog testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis + FakeStorage) — haqiqiy PostgreSQL, Redis, MinIO kerak emas.

Fixtures:
  engine        — aiosqlite in-memory async engine
  db_session    — har test uchun yangi async session (rollback bilan)
  fake_redis    — fakeredis async klient
  fake_storage  — in-memory storage (MinIO o'rniga)
  catalog_client — app dependency override qilingan AsyncClient
  make_user     — har rol uchun AppUser yaratish factory
  admin_user, agent_user, store_user — tayyor foydalanuvchilar
  agent_user_branch_a, agent_user_branch_b — branch_id bilan agentlar
  make_category, make_segment        — test ma'lumotlari factory

Token olish: get_token_for_user() yordamchisi.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

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
from app.models.catalog import Category, PriceSegment
from app.models.user import AppUser

TEST_PASSWORD = "TestPassword123!"

_BRANCH_A_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_BRANCH_B_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


# ─── aiosqlite in-memory engine ─────────────────────────────────────────────


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
    """Har test uchun yangi async session (rollback bilan)."""
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


# ─── fakeredis ───────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
    """Har test uchun yangi fakeredis."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── FakeStorage ─────────────────────────────────────────────────────────────


@pytest.fixture
def fake_storage() -> FakeStorage:
    """In-memory FakeStorage — MinIO o'rniga."""
    return FakeStorage()


# ─── Foydalanuvchi factory ────────────────────────────────────────────────────


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
async def agent_user_branch_a(make_user) -> AppUser:
    """Agent foydalanuvchi — branch A ga tegishli."""
    return await make_user("agent", branch_id=_BRANCH_A_ID)


@pytest.fixture
async def agent_user_branch_b(make_user) -> AppUser:
    """Agent foydalanuvchi — branch B ga tegishli."""
    return await make_user("agent", branch_id=_BRANCH_B_ID)


# ─── Katalog ma'lumotlari factory ────────────────────────────────────────────


@pytest.fixture
def make_category(db_session: AsyncSession):
    """Factory: Category yaratadi."""

    async def _factory(
        name_uz: str = "Test Kategoriya",
        name_ru: str = "Тестовая Категория",
        is_active: bool = True,
    ) -> Category:
        cat = Category(
            name_uz=name_uz,
            name_ru=name_ru,
            is_active=is_active,
        )
        db_session.add(cat)
        await db_session.flush()
        return cat

    return _factory


@pytest.fixture
def make_segment(db_session: AsyncSession):
    """Factory: PriceSegment yaratadi."""

    async def _factory(name: str = "Chakana") -> PriceSegment:
        seg = PriceSegment(name=name)
        db_session.add(seg)
        await db_session.flush()
        return seg

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def catalog_client(
    db_session: AsyncSession,
    fake_redis,
    fake_storage: FakeStorage,
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

    def _get_test_storage():
        return fake_storage

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis
    app.dependency_overrides[get_storage] = _get_test_storage

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


# ─── Branch ID konstantalari (testlar uchun) ─────────────────────────────────

BRANCH_A_ID = _BRANCH_A_ID
BRANCH_B_ID = _BRANCH_B_ID
