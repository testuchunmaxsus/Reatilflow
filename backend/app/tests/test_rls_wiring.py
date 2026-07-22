"""
BATCH 3B (ADR-013 Variant B) — RLS session-variable setter testlari.

Tekshiriladi:
  1. `_set_rls_var` SQLite'da no-op (xato tashlamaydi, dialekt-guard ishlaydi).
  2. `_set_rls_var` PostgreSQL yo'lida `set_config(..., true)` ni BIND parametr
     bilan chaqiradi — `SET LOCAL ... = :bind` EMAS (asyncpg bind bermaydi).
  3. `app.modules.rbac.enterprise_scope.set_rls_enterprise_var` endi mustaqil
     f-string SQL qurmaydi — yagona setterga (`app.core.db._set_rls_var`)
     delegatsiya qiladi (drift yo'q, SQL-injection shakli yo'q).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import db as dbmod
from app.modules.rbac import enterprise_scope as scope_mod


@pytest.fixture
async def _sqlite_engine():
    """Yengil aiosqlite in-memory engine — faqat dialekt-guard sinovi uchun."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(_sqlite_engine):
    """SQLite session — jadval yaratish shart emas (faqat dialekt tekshiriladi)."""
    session_factory = async_sessionmaker(
        bind=_sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session


class _FakePostgresDialect:
    name = "postgresql"


class _FakePostgresConnection:
    dialect = _FakePostgresDialect()


class _FakePostgresSession:
    """`_set_rls_var` uchun minimal soxta PostgreSQL session."""

    def __init__(self) -> None:
        self.executed: list = []

    async def connection(self):
        return _FakePostgresConnection()

    async def execute(self, stmt):
        self.executed.append(stmt)
        return None


# ─── 1. SQLite no-op ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_rls_var_noop_on_sqlite(db_session: AsyncSession):
    """SQLite session'da _set_rls_var xato tashlamaydi va hech narsa bajarmaydi."""
    # UUID enterprise_id bilan
    await dbmod._set_rls_var(db_session, uuid.uuid4())
    # None (superadmin) bilan ham
    await dbmod._set_rls_var(db_session, None)
    # Hech qanday exception ko'tarilmasligi kerak — dialekt-guard ishladi.


@pytest.mark.asyncio
async def test_set_rls_var_exception_is_swallowed(monkeypatch):
    """Ichki xato bo'lsa ham funksiya ko'tarilmaydi (request to'xtamaydi)."""

    class _BoomSession:
        async def connection(self):
            raise RuntimeError("boom")

    # Xato bo'lsa ham exception chiqmasligi kerak (log qilinadi, no-op).
    await dbmod._set_rls_var(_BoomSession(), uuid.uuid4())


# ─── 2. PostgreSQL yo'lida set_config(..., true) BIND bilan ─────────────────


@pytest.mark.asyncio
async def test_set_rls_var_uses_set_config_bind_not_set_local():
    """
    PostgreSQL yo'lida `SELECT set_config('app.current_enterprise_id', :eid, true)`
    ishlatiladi — `SET LOCAL app.current_enterprise_id = :eid` EMAS.

    asyncpg SET LOCAL kabi utility buyruqlarga bind bermaydi — shu sabab
    set_config() (oddiy funksiya, bind qabul qiladi) ishlatilishi shart.
    """
    fake_session = _FakePostgresSession()
    eid = uuid.uuid4()

    await dbmod._set_rls_var(fake_session, eid)

    assert len(fake_session.executed) == 1
    stmt = fake_session.executed[0]
    sql_text = str(stmt)

    assert "set_config" in sql_text
    assert "SET LOCAL" not in sql_text

    compiled = stmt.compile()
    assert compiled.params == {"eid": str(eid)}
    # is_local=true — tranzaksiya-lokal (pool sizishisiz)
    assert ", true)" in sql_text


@pytest.mark.asyncio
async def test_set_rls_var_superadmin_empty_string():
    """enterprise_id=None (superadmin) uchun bo'sh string bind qilinadi."""
    fake_session = _FakePostgresSession()

    await dbmod._set_rls_var(fake_session, None)

    assert len(fake_session.executed) == 1
    stmt = fake_session.executed[0]
    compiled = stmt.compile()
    assert compiled.params == {"eid": ""}


# ─── 3. enterprise_scope — bitta setter, f-string SQL yo'q ──────────────────


def test_enterprise_scope_no_fstring_sql_injection():
    """
    enterprise_scope.set_rls_enterprise_var manba kodida f-string orqali
    enterprise_id qiymatini SQL ichiga to'g'ridan-to'g'ri qo'shish YO'Q
    (SQL-injection shakli). Bind/set_config ishlatilishi kerak.
    """
    import inspect

    source = inspect.getsource(scope_mod.set_rls_enterprise_var)
    assert "f\"SET LOCAL" not in source
    assert "f'SET LOCAL" not in source
    assert "{enterprise_id}" not in source


@pytest.mark.asyncio
async def test_enterprise_scope_delegates_to_single_setter(monkeypatch):
    """set_rls_enterprise_var endi app.core.db._set_rls_var ga delegatsiya qiladi."""
    calls = []

    async def _fake_set_rls_var(session, enterprise_id):
        calls.append((session, enterprise_id))

    monkeypatch.setattr(dbmod, "_set_rls_var", _fake_set_rls_var)

    fake_session = object()
    eid = uuid.uuid4()
    await scope_mod.set_rls_enterprise_var(fake_session, eid)

    assert calls == [(fake_session, eid)]
