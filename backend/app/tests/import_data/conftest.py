"""
Import data moduli testlari uchun fixtures.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL/Redis kerak emas.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

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
from app.models.store import Store
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"


# ─── Engine / Session ─────────────────────────────────────────────────────────


@pytest.fixture
async def engine():
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
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


# ─── Enterprise ───────────────────────────────────────────────────────────────


@pytest.fixture
async def default_enterprise(db_session: AsyncSession) -> Enterprise:
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


# ─── Users ────────────────────────────────────────────────────────────────────


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        role: str,
        enterprise_id: uuid.UUID | None = None,
    ) -> AppUser:
        user_id = uuid.uuid4()
        user = AppUser(
            id=user_id,
            full_name=f"Test {role.capitalize()}",
            phone=f"+9989{str(abs(hash(str(user_id))))[:8]}",
            role=role,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
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
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def store_user(make_user, db_session: AsyncSession, default_enterprise: Enterprise) -> AppUser:
    """Store roli foydalanuvchi + bog'liq Store yaratiladi."""
    user = await make_user("store")

    # Do'kon yaratish va user_id bilan bog'lash
    store = Store(
        name="Test Do'kon",
        enterprise_id=default_enterprise.id,
        user_id=user.id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    return user


# ─── HTTP klient ──────────────────────────────────────────────────────────────


@pytest.fixture
async def import_client(
    db_session: AsyncSession,
    fake_redis,
):
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


# ─── Token yordamchisi ────────────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]


# ─── Excel fayl factory ───────────────────────────────────────────────────────


def make_xlsx_bytes(rows: list[list]) -> bytes:
    """
    In-memory xlsx fayl yaratadi.
    rows[0] — header, qolganlar ma'lumot.
    """
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl o'rnatilmagan")

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
