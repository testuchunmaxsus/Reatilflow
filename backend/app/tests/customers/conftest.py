"""
Customers testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL, Redis kerak emas.

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session (rollback bilan)
  fake_redis      — fakeredis async klient
  customers_client — app dependency override qilingan AsyncClient
  make_user       — har rol uchun AppUser yaratish factory
  make_store      — Store yaratish factory (PII blind-index bilan)
  admin_user, agent_user, store_user, courier_user, accountant_user — tayyor foydalanuvchilar
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.crypto import blind_index
from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

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


# ─── Foydalanuvchi factory ────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    """Factory: berilgan rol bilan AppUser yaratadi."""

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
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


@pytest.fixture
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


# ─── Store factory ───────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession, default_enterprise: Enterprise):
    """Factory: Store yaratadi (PII + blind-index bilan)."""

    async def _factory(
        name: str = "Test Do'kon",
        inn: str | None = None,
        phone: str | None = None,
        inps: str | None = None,
        owner_name: str | None = None,
        address: str | None = None,
        agent_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        credit_limit: Decimal | None = None,
        user_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            inn=inn,
            inps=inps,
            owner_name=owner_name,
            phone=phone,
            address=address,
            agent_id=agent_id,
            branch_id=branch_id,
            credit_limit=credit_limit,
            user_id=user_id,
            inn_bi=blind_index(inn) if inn else None,
            phone_bi=blind_index(phone) if phone else None,
            version=1,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def customers_client(
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


# ─── Konstantalar ────────────────────────────────────────────────────────────

BRANCH_A_ID = _BRANCH_A_ID
BRANCH_B_ID = _BRANCH_B_ID
