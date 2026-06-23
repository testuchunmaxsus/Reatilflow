"""
GPS Ingest testlari uchun fixtures — T17.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL, Redis, TimescaleDB kerak emas.

Fixtures:
  engine               — aiosqlite in-memory async engine
  db_session           — har test uchun yangi async session
  fake_redis           — fakeredis async klient
  gps_client           — app dependency override qilingan AsyncClient
                         (ish-soati filtri O'CHIRILGAN — mavjud testlar uchun backward-compat)
  make_user            — har rol uchun AppUser yaratish factory
  agent_user           — tayyor agent foydalanuvchi
  courier_user         — tayyor courier foydalanuvchi
  admin_user           — tayyor administrator foydalanuvchi
  store_user           — tayyor store foydalanuvchi (GPS ruxsati yo'q)
  make_attendance      — Attendance sessiyasi yaratish factory (ish-soati testlar uchun)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import get_db, get_timescale_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.core.uuid7 import uuid7
from app.main import app
from app.models.attendance import Attendance  # noqa: F401 — meta import (create_all uchun)
from app.models.base import Base
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.gps import GpsPoint  # noqa: F401 — meta import (create_all uchun)
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"


# ─── Test izolyatsiyasi: GPS ish-soati filtri sozlamasi ───────────────────────


@pytest.fixture(autouse=True)
def _reset_gps_work_hours_filter():
    """
    Har GPS test'dan oldingi `gps_work_hours_filter_enabled` qiymatini saqlab,
    teardown'da TIKLAYDI (test yiqilsa ham — failure-safe).

    Muammo: ba'zi testlar (work_hours, gps_client) global `settings`ni
    `object.__setattr__` bilan o'zgartirib qo'lда restore qiladi — assertion
    yiqilsa restore ishlamaydi → sozlama keyingi testga LEAK bo'ladi (flaky).
    Bu autouse teardown leak'ni butunlay yo'q qiladi.
    """
    original = settings.gps_work_hours_filter_enabled
    yield
    object.__setattr__(settings, "gps_work_hours_filter_enabled", original)


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


# ─── Fake Redis ───────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis():
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
            biometric_enrolled=True,
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
async def agent_user(make_user) -> AppUser:
    return await make_user("agent")


@pytest.fixture
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


@pytest.fixture
async def admin_user(make_user) -> AppUser:
    return await make_user("administrator")


@pytest.fixture
async def store_user(make_user) -> AppUser:
    return await make_user("store")


# ─── Attendance sessiyasi factory ────────────────────────────────────────────


@pytest.fixture
def make_attendance(db_session: AsyncSession):
    """
    Test uchun aktiv Attendance sessiyasi yaratuvchi factory.

    Parametrlar:
      user_id  — foydalanuvchi UUID
      open     — True (default): check_out_at=None (sessiya ochiq)
               — False: check_out_at = check_in_at + 1 soat (yopiq)

    Qaytaradi: Attendance ob'ekti (db_session ga qo'shilgan, flush qilingan).
    """
    async def _factory(
        user_id: uuid.UUID,
        *,
        open: bool = True,
        check_in_offset_seconds: int = -60,
    ) -> Attendance:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        check_in_at = now + timedelta(seconds=check_in_offset_seconds)
        check_out_at = None if open else (check_in_at + timedelta(hours=1))

        att = Attendance(
            id=uuid7(),
            user_id=user_id,
            work_date=check_in_at.date(),
            check_in_at=check_in_at,
            check_in_gps_lat="41.2995420",
            check_in_gps_lng="69.2401270",
            check_out_at=check_out_at,
            check_out_gps_lat=None,
            check_out_gps_lng=None,
            biometric_verified=True,
            source="device_faceid",
            client_uuid=None,
            version=1,
        )
        db_session.add(att)
        await db_session.flush()
        return att

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def gps_client(
    db_session: AsyncSession,
    fake_redis,
):
    """
    Dependency override qilingan AsyncClient.

    ISH-SOATI FILTRI: mavjud testlar uchun backward-compat —
    settings.gps_work_hours_filter_enabled = False qilinadi.
    Ish-soati filtri testlari uchun test_work_hours_filter.py dagi
    work_hours_gps_client fixture'ini ishlating.
    """
    # Mavjud testlar filtr o'chirilgan holatda ishlaydi (backward-compat)
    original_filter = settings.gps_work_hours_filter_enabled
    object.__setattr__(settings, "gps_work_hours_filter_enabled", False)

    async def _get_test_db():
        yield db_session

    async def _get_test_timescale_db():
        # GPS TimescaleDB sessiyasi ham xuddi shu test sessiyasiga yo'naltiriladi.
        # Test muhitida aiosqlite in-memory DB ishlatilgani uchun ikkalasi bir sessiya.
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_timescale_db] = _get_test_timescale_db
    app.dependency_overrides[get_redis] = _get_test_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    object.__setattr__(settings, "gps_work_hours_filter_enabled", original_filter)


# ─── Token yordamchisi ────────────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
