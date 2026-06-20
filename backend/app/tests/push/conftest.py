"""
Push testlari uchun fixtures — T19.

Infrasiz (aiosqlite + FakePushProvider) — haqiqiy infra kerak emas.

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session
  fake_provider   — FakePushProvider (yuborilganlarni ro'yxatga oladi)
  make_user       — AppUser yaratish factory (device_id bilan)
  make_store      — Store yaratish factory
  make_order      — Order yaratish factory
  make_delivery   — Delivery yaratish factory
  make_outbox     — OutboxEvent yaratish factory
  push_client     — PATCH /push/device-token uchun AsyncClient
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import hash_password
from app.main import app
from app.models.base import Base
from app.models.delivery import Delivery
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.order import Order
from app.models.outbox import OutboxEvent
from app.models.push import PushLog
from app.models.store import Store
from app.models.user import AppUser
from app.modules.push.provider import FakePushProvider
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"


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


# ─── Fake Provider ─────────────────────────────────────────────────────────────


@pytest.fixture
def fake_provider() -> FakePushProvider:
    """FakePushProvider — har test uchun yangi instance."""
    return FakePushProvider()


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
        role: str = "agent",
        device_id: str | None = "fake_fcm_token_abc123",
        locale: str = "uz",
        phone: str | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> AppUser:
        uid = uuid.uuid4()
        user = AppUser(
            id=uid,
            full_name=f"Test {role.capitalize()}",
            phone=phone or f"+99890{str(abs(hash(str(uid))))[:7]}",
            role=role,
            branch_id=None,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
            biometric_enrolled=False,
            locale=locale,
            device_id=device_id,
            version=1,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _factory


# ─── Store factory ────────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name: str = "Test Do'kon",
        user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            user_id=user_id,
            agent_id=agent_id,
            version=1,
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(store)
        await db_session.flush()
        return store

    return _factory


# ─── Order factory ────────────────────────────────────────────────────────────


@pytest.fixture
def make_order(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        store_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
        status: str = "confirmed",
        enterprise_id: uuid.UUID | None = None,
    ) -> Order:
        from app.core.uuid7 import uuid7

        order = Order(
            id=uuid7(),
            store_id=store_id,
            agent_id=agent_id,
            mode="bozor",
            status=status,
            total_amount=Decimal("50000.00"),
            currency="UZS",
            ordered_at=datetime.now(timezone.utc),
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(order)
        await db_session.flush()
        return order

    return _factory


# ─── Delivery factory ─────────────────────────────────────────────────────────


@pytest.fixture
def make_delivery(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
        status: str = "assigned",
        enterprise_id: uuid.UUID | None = None,
    ) -> Delivery:
        from app.core.uuid7 import uuid7

        delivery = Delivery(
            id=uuid7(),
            order_id=order_id,
            courier_id=courier_id,
            status=status,
            assigned_at=datetime.now(timezone.utc),
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(delivery)
        await db_session.flush()
        return delivery

    return _factory


# ─── OutboxEvent factory ──────────────────────────────────────────────────────


@pytest.fixture
def make_outbox(db_session: AsyncSession):
    async def _factory(
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        published_at: datetime | None = None,
    ) -> OutboxEvent:
        from app.core.uuid7 import uuid7

        event = OutboxEvent(
            id=uuid7(),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=json.dumps(payload),
            created_at=datetime.now(timezone.utc),
            published_at=published_at,
        )
        db_session.add(event)
        await db_session.flush()
        return event

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def push_client(db_session: AsyncSession):
    """Dependency override qilingan AsyncClient (device-token endpoint uchun)."""

    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ─── Token yordamchisi ────────────────────────────────────────────────────────


async def get_token(client: AsyncClient, user: AppUser) -> str:
    """Foydalanuvchi uchun access token qaytaradi."""
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]
