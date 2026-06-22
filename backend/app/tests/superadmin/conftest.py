"""
Superadmin testlari uchun fixtures — MT4.

Infrasiz (aiosqlite + fakeredis).

Fixtures:
  engine           — aiosqlite in-memory async engine
  db_session       — har test uchun yangi async session (rollback bilan)
  fake_redis       — fakeredis async klient
  default_enterprise  — barcha modul yoqilgan, aktiv korxona
  suspended_enterprise — status='suspended' korxona
  superadmin_user  — role='superadmin', enterprise_id=None
  admin_user       — role='administrator', default_enterprise ga bog'liq
  agent_user       — role='agent', default_enterprise ga bog'liq
  superadmin_client — superadmin token bilan AsyncClient
  admin_client     — administrator token bilan AsyncClient
  no_auth_client   — tokensiz AsyncClient
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

TEST_PASSWORD = "SuperPass123!"

SUSPENDED_ENTERPRISE_UUID = uuid.UUID("00000000-0000-7000-8000-000000000097")
SUPERADMIN_PHONE = "+998900000001"
ADMIN_PHONE = "+998900000002"
AGENT_PHONE = "+998900000003"
SUSPENDED_ADMIN_PHONE = "+998900000004"


# ─── Engine + DB ──────────────────────────────────────────────────────────────


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
async def db_session(engine) -> AsyncSession:
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


# ─── Fake Redis ───────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
    """Har test uchun yangi fakeredis."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Enterprise fixtures ───────────────────────────────────────────────────────


@pytest.fixture
async def default_enterprise(db_session: AsyncSession) -> Enterprise:
    """Barcha modul yoqilgan, aktiv korxona."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Test Korxona",
        inn="123456789",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def suspended_enterprise(db_session: AsyncSession) -> Enterprise:
    """status='suspended' korxona — login testi uchun."""
    ent = Enterprise(
        id=SUSPENDED_ENTERPRISE_UUID,
        name="To'xtatilgan Korxona",
        inn="987654321",
        status="suspended",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


# ─── User fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
async def superadmin_user(db_session: AsyncSession) -> AppUser:
    """superadmin — enterprise_id=None."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Superadmin",
        phone=SUPERADMIN_PHONE,
        role="superadmin",
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=None,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """administrator — default_enterprise."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Test Admin",
        phone=ADMIN_PHONE,
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
async def agent_user(db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """agent — default_enterprise."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Test Agent",
        phone=AGENT_PHONE,
        role="agent",
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
async def suspended_admin_user(
    db_session: AsyncSession, suspended_enterprise: Enterprise
) -> AppUser:
    """administrator — suspended korxona."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Suspended Admin",
        phone=SUSPENDED_ADMIN_PHONE,
        role="administrator",
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=suspended_enterprise.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ─── HTTP klientlar ────────────────────────────────────────────────────────────


@pytest.fixture
async def superadmin_client(
    db_session: AsyncSession,
    fake_redis,
    superadmin_user: AppUser,
):
    """superadmin token bilan AsyncClient."""

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    access_token = create_access_token(
        sub=str(superadmin_user.id),
        role=superadmin_user.role,
        branch_id=None,
        enterprise_id=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(
    db_session: AsyncSession,
    fake_redis,
    admin_user: AppUser,
    default_enterprise: Enterprise,
):
    """administrator token bilan AsyncClient."""

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    access_token = create_access_token(
        sub=str(admin_user.id),
        role=admin_user.role,
        branch_id=None,
        enterprise_id=str(admin_user.enterprise_id),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def no_auth_client(
    db_session: AsyncSession,
    fake_redis,
):
    """Tokensiz AsyncClient."""

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
