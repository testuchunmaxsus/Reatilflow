"""
RBAC testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis) — T1 conftest uslubida.

Fixtures:
  engine       — aiosqlite in-memory async engine
  db_session   — har test uchun yangi async session (rollback bilan)
  fake_redis   — fakeredis async klient
  rbac_client  — app dependency override qilingan AsyncClient
  make_user    — har rol uchun AppUser yaratish factory
  admin_user, agent_user, courier_user, accountant_user, store_user — tayyor foydalanuvchilar
  agent_token, admin_token, ...  — login qilingan tokenlar
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
from app.models.store import AgentStore, Store
from app.models.user import AppUser

TEST_PASSWORD = "TestPassword123!"


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


@pytest.fixture
async def fake_redis():
    """Har test uchun yangi fakeredis."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Foydalanuvchi factory ────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession):
    """
    Factory fixture: berilgan rol bilan AppUser yaratadi va DB ga qo'shadi.

    Foydalanish:
        user = await make_user("agent")
        user = await make_user("admin", branch_id=some_uuid)
    """
    async def _factory(
        role: str,
        phone: str | None = None,
        branch_id: uuid.UUID | None = None,
        is_active: bool = True,
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


# ─── Tayyor foydalanuvchilar ─────────────────────────────────────────────────


@pytest.fixture
async def admin_user(make_user) -> AppUser:
    return await make_user("administrator")


@pytest.fixture
async def agent_user(make_user) -> AppUser:
    return await make_user("agent")


@pytest.fixture
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


@pytest.fixture
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def store_user(make_user) -> AppUser:
    return await make_user("store")


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def rbac_client(db_session: AsyncSession, fake_redis):
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


# ─── Token olish yordamchisi ──────────────────────────────────────────────────


async def get_token_for_user(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi (login orqali)."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
