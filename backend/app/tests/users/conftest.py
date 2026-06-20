"""
Users testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL va Redis talab qilinmaydi.

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session (rollback bilan)
  fake_redis      — fakeredis async klient
  admin_user      — administrator roli bilan AppUser
  agent_user      — agent roli bilan AppUser
  store_user      — store roli bilan AppUser
  courier_user    — courier roli bilan AppUser
  accountant_user — accountant roli bilan AppUser
  users_client    — app dependency override qilingan AsyncClient (admin token bilan)
  agent_client    — agent token bilan klient (403 tekshirish uchun)
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import create_access_token, hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

# ─── Test konstantalari ───────────────────────────────────────────────────────

ADMIN_PHONE = "+998901111111"
ADMIN_PASSWORD = "AdminPass123!"
ADMIN_USER_ID = uuid.uuid4()

AGENT_PHONE = "+998902222222"
AGENT_PASSWORD = "AgentPass123!"
AGENT_USER_ID = uuid.uuid4()

STORE_PHONE = "+998903333333"
COURIER_PHONE = "+998904444444"
ACCOUNTANT_PHONE = "+998905555555"


# ─── aiosqlite in-memory engine ─────────────────────────────────────────────


@pytest.fixture
async def engine():
    """Har test uchun aiosqlite in-memory engine."""
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


# ─── Default Enterprise ──────────────────────────────────────────────────────


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


# ─── Test foydalanuvchilar ────────────────────────────────────────────────────


@pytest.fixture
async def admin_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Administrator roli bilan test foydalanuvchi."""
    user = AppUser(
        id=ADMIN_USER_ID,
        full_name="Admin Foydalanuvchi",
        phone=ADMIN_PHONE,
        role="administrator",
        branch_id=None,
        password_hash=hash_password(ADMIN_PASSWORD),
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
async def agent_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Agent roli bilan test foydalanuvchi."""
    user = AppUser(
        id=AGENT_USER_ID,
        full_name="Agent Foydalanuvchi",
        phone=AGENT_PHONE,
        role="agent",
        branch_id=None,
        password_hash=hash_password(AGENT_PASSWORD),
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
async def store_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Store roli bilan test foydalanuvchi."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Store Foydalanuvchi",
        phone=STORE_PHONE,
        role="store",
        branch_id=None,
        password_hash=hash_password("StorePass123!"),
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
async def courier_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Courier roli bilan test foydalanuvchi."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Courier Foydalanuvchi",
        phone=COURIER_PHONE,
        role="courier",
        branch_id=None,
        password_hash=hash_password("CourierPass123!"),
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
async def accountant_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Accountant roli bilan test foydalanuvchi."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Accountant Foydalanuvchi",
        phone=ACCOUNTANT_PHONE,
        role="accountant",
        branch_id=None,
        password_hash=hash_password("AccountPass123!"),
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


# ─── HTTP klientlar ───────────────────────────────────────────────────────────

@pytest.fixture
async def users_client(db_session: AsyncSession, fake_redis, admin_user: AppUser):
    """
    Admin token bilan AsyncClient (dependency override qilingan).

    Barcha /users/* endpointlari uchun ishlatiladi.
    """
    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    # Admin access token yaratish
    access_token = create_access_token(
        sub=str(admin_user.id),
        role=admin_user.role,
        branch_id=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def agent_client(db_session: AsyncSession, fake_redis, agent_user: AppUser):
    """
    Agent token bilan AsyncClient — 403 testlari uchun.
    """
    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    access_token = create_access_token(
        sub=str(agent_user.id),
        role=agent_user.role,
        branch_id=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(db_session: AsyncSession, fake_redis):
    """
    Auth testlari uchun klient (tokensiz — login endpoint uchun).
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
