"""
Contracts testlari uchun fixtures — T23.

Infrasiz (aiosqlite + fakeredis + FakeStorage) — haqiqiy infra kerak emas.

Fixtures:
  engine           — aiosqlite in-memory async engine
  db_session       — har test uchun yangi async session
  fake_redis       — fakeredis async klient
  fake_storage     — FakeStorage in-memory
  contracts_client — app dependency override qilingan AsyncClient
  make_user        — har rol uchun AppUser yaratish factory
  make_store       — Store yaratish factory
  make_contract    — Contract yaratish factory
  admin_user, agent_user, store_user, accountant_user
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone

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
from app.models.contract import Contract
from app.models.store import AgentStore, Store
from app.models.user import AppUser

TEST_PASSWORD = "TestPassword123!"


def _today() -> date:
    return datetime.now(timezone.utc).date()


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


# ─── fakeredis ───────────────────────────────────────────────────────────────


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
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


# ─── Store factory ───────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession):
    """Factory: Store yaratadi."""

    async def _factory(
        name: str = "Test Do'kon",
        agent_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            agent_id=agent_id,
            branch_id=branch_id,
            user_id=user_id,
            version=1,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── AgentStore factory ──────────────────────────────────────────────────────


@pytest.fixture
def make_agent_store(db_session: AsyncSession):
    """Factory: AgentStore (agent↔do'kon) yaratadi."""

    async def _factory(agent_id: uuid.UUID, store_id: uuid.UUID) -> AgentStore:
        link = AgentStore(agent_id=agent_id, store_id=store_id)
        db_session.add(link)
        await db_session.flush()
        return link

    return _factory


# ─── Contract factory ────────────────────────────────────────────────────────


@pytest.fixture
def make_contract(db_session: AsyncSession):
    """Factory: Contract yaratadi."""

    async def _factory(
        store_id: uuid.UUID,
        number: str = "CT-001",
        valid_from: date | None = None,
        valid_to: date | None = None,
        contract_type: str | None = "trade",
        branch_id: uuid.UUID | None = None,
        client_uuid: uuid.UUID | None = None,
        file_url: str | None = None,
    ) -> Contract:
        today = _today()
        contract = Contract(
            store_id=store_id,
            number=number,
            valid_from=valid_from or today,
            valid_to=valid_to or (today + timedelta(days=60)),
            contract_type=contract_type,
            branch_id=branch_id,
            client_uuid=client_uuid,
            file_url=file_url,
            version=1,
        )
        db_session.add(contract)
        await db_session.flush()
        return contract

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def contracts_client(
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
