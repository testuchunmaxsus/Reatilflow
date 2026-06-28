"""
DB transient-connect retry testlari.

Railway Postgres qayta ishga tushganda `CannotConnectNowError: the database
system is starting up` qaytaradi → `_acquire_connected_session` qisqa backoff
bilan qayta urinadi (login va boshqa endpointlar 500 bermasligi uchun).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.core import db as dbmod


def _factory_raising(fail_times: int, exc: BaseException):
    """fail_times marta `exc` ko'taradi, keyin ulanadigan mock-session qaytaradi."""
    state = {"n": 0}

    def factory():
        state["n"] += 1
        s = MagicMock()
        if state["n"] <= fail_times:
            s.connection = AsyncMock(side_effect=exc)
        else:
            s.connection = AsyncMock(return_value=MagicMock())
        s.close = AsyncMock()
        return s

    factory.state = state  # type: ignore[attr-defined]
    return factory


def _op_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("the database system is starting up"))


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient(monkeypatch):
    """2 ta transient xato → 3-urinishda ulanadi (500 bermaydi)."""
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_MAX_DELAY", 0.001)
    factory = _factory_raising(2, _op_error())
    session = await dbmod._acquire_connected_session(factory)
    assert session is not None
    assert factory.state["n"] == 3  # 2 fail + 1 success


@pytest.mark.asyncio
async def test_retry_exhausts_and_raises(monkeypatch):
    """Doimiy xato → barcha urinishlardan keyin xato qayta ko'tariladi."""
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_MAX_DELAY", 0.001)
    factory = _factory_raising(999, _op_error())
    with pytest.raises(OperationalError):
        await dbmod._acquire_connected_session(factory)
    assert factory.state["n"] == dbmod._CONNECT_RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_no_retry_on_success(monkeypatch):
    """Birinchi urinishda ulansa — qayta urinmaydi."""
    factory = _factory_raising(0, _op_error())
    session = await dbmod._acquire_connected_session(factory)
    assert session is not None
    assert factory.state["n"] == 1


def test_cannotconnectnow_is_transient():
    """asyncpg CannotConnectNowError transient ro'yxatda (prod muhitida)."""
    try:
        from asyncpg.exceptions import CannotConnectNowError
    except Exception:
        pytest.skip("asyncpg o'rnatilmagan")
    assert CannotConnectNowError in dbmod._TRANSIENT_CONNECT_ERRORS
