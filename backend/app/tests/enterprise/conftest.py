"""
Enterprise testlari uchun fixtures — MT3 module gating.

Infrasiz (aiosqlite + fakeredis) — haqiqiy infra kerak emas.

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session (rollback bilan)
  fake_redis      — fakeredis async klient
  enterprise_client — app dependency override qilingan AsyncClient
  default_enterprise    — barcha modul yoqilgan korxona
  disabled_promo_enterprise — promo o'chirilgan korxona
  make_user       — AppUser factory
  admin_user      — administrator (default_enterprise bilan)
  superadmin_user — superadmin (enterprise_id=None)
  admin_user_no_promo — administrator (disabled_promo_enterprise bilan)
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

# Promo o'chirilgan korxona UUID
DISABLED_PROMO_ENTERPRISE_UUID = uuid.UUID("00000000-0000-7000-8000-000000000098")


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
    """Barcha modullar yoqilgan korxona (mavjud testlar uchun mos)."""
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


@pytest.fixture
async def disabled_promo_enterprise(db_session: AsyncSession) -> Enterprise:
    """promo moduli O'CHIRILGAN korxona — module gating testi uchun."""
    modules_without_promo = [m for m in ALL_MODULE_KEYS if m != "promo"]
    ent = Enterprise(
        id=DISABLED_PROMO_ENTERPRISE_UUID,
        name="Promo O'chirilgan Korxona",
        status="active",
        enabled_modules=modules_without_promo,
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


# ─── Foydalanuvchi factory ─────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    """Factory: berilgan rol va ixtiyoriy enterprise bilan AppUser yaratadi."""

    async def _factory(
        role: str,
        phone: str | None = None,
        is_active: bool = True,
        enterprise_id: uuid.UUID | None = None,
        no_enterprise: bool = False,
    ) -> AppUser:
        user_id = uuid.uuid4()
        eid: uuid.UUID | None
        if no_enterprise:
            eid = None
        elif enterprise_id is not None:
            eid = enterprise_id
        else:
            eid = default_enterprise.id

        user = AppUser(
            id=user_id,
            full_name=f"Test {role.capitalize()}",
            phone=phone or f"+99890{str(abs(hash(str(user_id))))[:7]}",
            role=role,
            branch_id=None,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=is_active,
            biometric_enrolled=False,
            locale="uz",
            device_id=None,
            version=1,
            enterprise_id=eid,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _factory


@pytest.fixture
async def admin_user(make_user) -> AppUser:
    """Administrator — default_enterprise (barcha modul yoqilgan)."""
    return await make_user("administrator")


@pytest.fixture
async def superadmin_user(make_user) -> AppUser:
    """superadmin — enterprise_id=None (bypass gate)."""
    return await make_user("administrator", no_enterprise=True)


@pytest.fixture
async def admin_user_no_promo(
    make_user, disabled_promo_enterprise: Enterprise
) -> AppUser:
    """Administrator — promo moduli o'chirilgan korxona."""
    return await make_user(
        "administrator",
        enterprise_id=disabled_promo_enterprise.id,
    )


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def enterprise_client(
    db_session: AsyncSession,
    fake_redis,
):
    """
    Dependency override qilingan AsyncClient.

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


# ─── Token olish yordamchisi ──────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
