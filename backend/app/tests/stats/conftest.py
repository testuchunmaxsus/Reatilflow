"""
Statistika testlari uchun fixtures — T22.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL/Redis kerak emas.
Replica = primary (test muhitida bir xil sessiya).

Fixtures:
  engine          — aiosqlite in-memory async engine
  db_session      — har test uchun yangi async session
  fake_redis      — fakeredis async klient
  stats_client    — app dependency override qilingan AsyncClient
                    (get_db, get_db_replica → db_session; get_redis → fake_redis)
  make_user       — AppUser yaratish factory
  make_store      — Store yaratish factory
  make_order      — Order yaratish factory (savdo statistikasi uchun)
  make_delivery   — Delivery yaratish factory (yetkazish statistikasi uchun)
  make_ledger     — LedgerEntry + AccountBalance yaratish factory (moliyaviy)
  admin_user, agent_user, courier_user, accountant_user, store_user
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db, get_db_replica
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.delivery import Delivery
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.finance import AccountBalance, LedgerEntry
from app.models.order import Order
from app.models.store import AgentStore, Store
from app.models.user import AppUser
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
async def courier_user(make_user) -> AppUser:
    return await make_user("courier")


@pytest.fixture
async def accountant_user(make_user) -> AppUser:
    return await make_user("accountant")


@pytest.fixture
async def store_user(make_user) -> AppUser:
    return await make_user("store")


# ─── Store factory ────────────────────────────────────────────────────────────


@pytest.fixture
def make_store(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        name: str = "Test Do'kon",
        user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Store:
        store = Store(
            name=name,
            user_id=user_id,
            agent_id=agent_id,
            branch_id=branch_id,
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
        total_amount: Decimal = Decimal("100000.00"),
        ordered_at: datetime | None = None,
        branch_id: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Order:
        from app.core.uuid7 import uuid7

        order = Order(
            id=uuid7(),
            store_id=store_id,
            agent_id=agent_id,
            mode="oddiy",
            status=status,
            total_amount=total_amount,
            currency="UZS",
            ordered_at=ordered_at or datetime.now(timezone.utc),
            branch_id=branch_id,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(order)
        await db_session.flush()
        return order

    return _factory


# ─── Delivery factory ────────────────────────────────────────────────────────


@pytest.fixture
def make_delivery(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
        status: str = "delivered",
        assigned_at: datetime | None = None,
        started_at: datetime | None = None,
        delivered_at: datetime | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> Delivery:
        from app.core.uuid7 import uuid7

        delivery = Delivery(
            id=uuid7(),
            order_id=order_id,
            courier_id=courier_id,
            status=status,
            assigned_at=assigned_at or datetime.now(timezone.utc),
            started_at=started_at,
            delivered_at=delivered_at,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            enterprise_id=enterprise_id if enterprise_id is not None else default_enterprise.id,
        )
        db_session.add(delivery)
        await db_session.flush()
        return delivery

    return _factory


# ─── LedgerEntry + AccountBalance factory ────────────────────────────────────


@pytest.fixture
def make_ledger(db_session: AsyncSession, default_enterprise: Enterprise):
    """
    LedgerEntry yaratadi va AccountBalance ni yangilaydi.
    """

    async def _factory(
        store_id: uuid.UUID,
        entry_type: str,  # 'debit' | 'credit'
        amount: Decimal,
        currency: str = "UZS",
        entry_date: datetime | None = None,
        created_by: uuid.UUID | None = None,
        enterprise_id: uuid.UUID | None = None,
    ) -> LedgerEntry:
        from app.core.uuid7 import uuid7

        eid = enterprise_id if enterprise_id is not None else default_enterprise.id

        entry = LedgerEntry(
            id=uuid7(),
            store_id=store_id,
            type=entry_type,
            amount=amount,
            currency=currency,
            entry_date=entry_date or datetime.now(timezone.utc),
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            enterprise_id=eid,
        )
        db_session.add(entry)
        await db_session.flush()

        # AccountBalance yangilash yoki yaratish
        from sqlalchemy import select

        stmt = select(AccountBalance).where(AccountBalance.store_id == store_id)
        result = await db_session.execute(stmt)
        balance = result.scalar_one_or_none()

        if balance is None:
            balance_val = amount if entry_type == "debit" else -amount
            balance = AccountBalance(
                id=uuid7(),
                store_id=store_id,
                balance=balance_val,
                currency=currency,
                last_recalc_at=datetime.now(timezone.utc),
                version=1,
                enterprise_id=eid,
            )
            db_session.add(balance)
        else:
            if entry_type == "debit":
                balance.balance += amount
            else:
                balance.balance -= amount
            balance.version += 1
        await db_session.flush()

        return entry

    return _factory


# ─── HTTP klient (dependency override) ───────────────────────────────────────


@pytest.fixture
async def stats_client(
    db_session: AsyncSession,
    fake_redis,
):
    """
    Dependency override qilingan AsyncClient.

    MUHIM: Test muhitida replica = primary (aiosqlite bitta sessiya).
    Bu ADR §3.4 / §3.8 ni test darajasida simulatsiya qiladi —
    haqiqiy produksiyada get_db_replica → alohida replica engine.

    Overrides:
      get_db()         → db_session (primary simulatsiya)
      get_db_replica() → db_session (replica = primary test uchun)
      get_redis()      → fake_redis
    """

    async def _get_test_db():
        yield db_session

    async def _get_test_db_replica():
        # Test muhitida replica = primary (aiosqlite)
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_db_replica] = _get_test_db_replica
    app.dependency_overrides[get_redis] = _get_test_redis

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
