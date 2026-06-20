"""
Auth testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL va Redis talab qilinmaydi.

Fixtures:
  engine       — aiosqlite in-memory async engine
  db_session   — har test uchun yangi async session (rollback bilan)
  fake_redis   — fakeredis async klient
  test_user    — bcrypt parol bilan yaratilgan AppUser
  auth_client  — app dependency override qilingan AsyncClient
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

# ─── Parol konstantasi (testlarda ishlatiladi) ───────────────────────────────

TEST_PHONE = "+998901234567"
TEST_PASSWORD = "TestPassword123!"
TEST_USER_ID = uuid.uuid4()


# ─── aiosqlite in-memory engine ─────────────────────────────────────────────
# Har test uchun yangi engine — session-scoped loop muammosini hal qiladi.

@pytest.fixture
async def engine():
    """
    Har test uchun aiosqlite in-memory engine.

    Jadvallar yaratiladi va test tugagach o'chiriladi.
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
async def db_session(engine):
    """
    Har test uchun yangi async session.

    Test tugagach rollback — DB holati tozalanadi.
    """
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
    """Har test uchun yangi fakeredis (in-memory, haqiqiy Redis kerak emas)."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Default Enterprise ───────────────────────────────────────────────────────

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


# ─── Test foydalanuvchi ───────────────────────────────────────────────────────

@pytest.fixture
async def test_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """
    Bcrypt parol bilan yaratilgan test foydalanuvchi.

    Har test uchun bir xil ID ishlatiladi (session scope emas — har test
    o'z rollback ga ega).
    MT1: enterprise_id qo'shildi.
    """
    user = AppUser(
        id=TEST_USER_ID,
        full_name="Test Foydalanuvchi",
        phone=TEST_PHONE,
        role="administrator",
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=default_enterprise.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def inactive_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """is_active=False foydalanuvchi (bloklangan)."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Bloklangan Foydalanuvchi",
        phone="+998909999999",
        role="agent",
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=False,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=default_enterprise.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ─── HTTP klient (dependency override) ───────────────────────────────────────

@pytest.fixture
async def auth_client(db_session: AsyncSession, fake_redis):
    """
    Dependency override qilingan AsyncClient.

    get_db() → db_session (aiosqlite in-memory)
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
