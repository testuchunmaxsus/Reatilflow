"""
Marketplace testlari uchun fixtures.

Multi-tenant test sozlamasi:
  - enterprise_a (TEST_ENTERPRISE_UUID): asosiy korxona
  - enterprise_b: ikkinchi korxona (cross-tenant tekshiruv uchun)
  - admin_a: enterprise_a administratori
  - admin_b: enterprise_b administratori
  - store_user_a: enterprise_a do'kon foydalanuvchisi (browse testlari uchun)

Infrasiz: aiosqlite + fakeredis.
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
from app.main import app
from app.models.base import Base
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"

# Ikkinchi korxona UUID (cross-tenant test uchun)
TEST_ENTERPRISE_B_UUID = uuid.UUID("00000000-0000-7000-8000-000000000088")


# ─── Engine / Session ────────────────────────────────────────────────────────


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


# ─── Redis ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Enterprise fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def enterprise_a(db_session: AsyncSession) -> Enterprise:
    """Asosiy test korxonasi (enterprise A)."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Korxona A",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def enterprise_b(db_session: AsyncSession) -> Enterprise:
    """Ikkinchi test korxonasi (enterprise B) — cross-tenant tekshiruv."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_B_UUID,
        name="Korxona B",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


# ─── User fixtures ───────────────────────────────────────────────────────────


def _make_app_user(
    role: str,
    enterprise_id: uuid.UUID,
    suffix: str = "",
) -> AppUser:
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix))
    return AppUser(
        id=user_id,
        full_name=f"Test {role.capitalize()} {suffix}",
        phone=f"+99890{str(phone_hash)[:7]}",
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


@pytest.fixture
async def admin_a(db_session: AsyncSession, enterprise_a: Enterprise) -> AppUser:
    """Enterprise A administratori."""
    user = _make_app_user("administrator", enterprise_a.id, "A")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin_b(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Enterprise B administratori."""
    user = _make_app_user("administrator", enterprise_b.id, "B")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def store_user_a(db_session: AsyncSession, enterprise_a: Enterprise) -> AppUser:
    """Enterprise A do'kon foydalanuvchisi (marketplace browse uchun)."""
    user = _make_app_user("store", enterprise_a.id, "storeA")
    db_session.add(user)
    await db_session.flush()
    return user


# ─── HTTP klient ─────────────────────────────────────────────────────────────


@pytest.fixture
async def mp_client(
    db_session: AsyncSession,
    fake_redis,
):
    """Marketplace testlari uchun AsyncClient."""

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


# ─── Token yordamchisi ───────────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
