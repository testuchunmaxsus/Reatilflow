"""
DB transient-connect retry testlari (#38).

Railway Postgres qayta ishga tushganda `CannotConnectNowError: the database
system is starting up` qaytaradi. Endi retry ENGINE darajasida —
`_connect_asyncpg_with_retry` (async_creator, `_make_engine`da ulanadi) —
qisqa backoff bilan qayta urinadi (login va boshqa endpointlar 500
bermasligi uchun). `get_db`/`get_db_replica`/`get_timescale_db` esa LAZY —
eager `session.connection()` chaqirilmaydi (pool ulanishni birinchi
haqiqiy so'rovda oladi, DB'siz endpointlar pool'ni band qilmaydi).

Predikat `_is_transient_connect_error` — keng tuple emas, faqat HAQIQIY
"DB hali ko'tarilmagan / TCP tayyor emas" xatolarni True deb topadi
(auth/config xatolari False — qayta URILMAYDI, fail-fast).
"""

from unittest.mock import AsyncMock, patch

import pytest
from asyncpg.exceptions import CannotConnectNowError, ConnectionDoesNotExistError
from sqlalchemy.exc import OperationalError

from app.core import db as dbmod


def _op_error_wrapping(orig: BaseException) -> OperationalError:
    return OperationalError("SELECT 1", {}, orig)


# ─── _is_transient_connect_error predikat testlari ──────────────────────────


def test_predicate_true_for_direct_cannotconnectnow():
    """Haqiqiy asyncpg CannotConnectNowError to'g'ridan-to'g'ri → True."""
    exc = CannotConnectNowError("the database system is starting up")
    assert dbmod._is_transient_connect_error(exc) is True


def test_predicate_true_for_direct_connectiondoesnotexist():
    """Haqiqiy asyncpg ConnectionDoesNotExistError → True."""
    exc = ConnectionDoesNotExistError("connection was closed")
    assert dbmod._is_transient_connect_error(exc) is True


def test_predicate_true_for_wrapped_orig():
    """SQLAlchemy OperationalError.orig = haqiqiy asyncpg xatosi → True."""
    inner = CannotConnectNowError("the database system is starting up")
    exc = _op_error_wrapping(inner)
    assert dbmod._is_transient_connect_error(exc) is True


def test_predicate_true_for_tcp_not_ready():
    """ConnectionRefusedError/TimeoutError (TCP hali tayyor emas) → True."""
    assert dbmod._is_transient_connect_error(ConnectionRefusedError("refused")) is True
    assert dbmod._is_transient_connect_error(TimeoutError("timed out")) is True


def test_predicate_false_for_generic_wrapped_exception():
    """
    `.orig` HAQIQIY asyncpg klass EMAS (oddiy Exception) → False.

    Eski keng-tuple naqsh bunday holatni ham transient deb hisoblardi —
    yangi predikat FAQAT haqiqiy asyncpg/TCP-not-ready klasslariga ishonadi.
    """
    inner = Exception("the database system is starting up")
    exc = _op_error_wrapping(inner)
    assert dbmod._is_transient_connect_error(exc) is False


def test_predicate_false_for_auth_error():
    """Auth/config xatolari (umumiy Exception/OSError farqli klass) → False."""
    assert dbmod._is_transient_connect_error(ValueError("bad config")) is False
    assert dbmod._is_transient_connect_error(Exception("password authentication failed")) is False


# ─── _connect_asyncpg_with_retry testlari (engine-darajasidagi retry) ───────


def _asyncpg_connect_raising(fail_times: int, exc: BaseException):
    """fail_times marta `exc` ko'taradi, keyin fake connection qaytaradi."""
    state = {"n": 0}

    async def _connect(*args, **kwargs):
        state["n"] += 1
        if state["n"] <= fail_times:
            raise exc
        return "fake-connection"

    _connect.state = state  # type: ignore[attr-defined]
    return _connect


@pytest.mark.asyncio
async def test_connect_retry_succeeds_after_transient(monkeypatch):
    """2 ta transient xato → 3-urinishda ulanadi (500 bermaydi)."""
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_MAX_DELAY", 0.001)
    fake_connect = _asyncpg_connect_raising(
        2, CannotConnectNowError("the database system is starting up")
    )
    with patch("asyncpg.connect", fake_connect):
        result = await dbmod._connect_asyncpg_with_retry()
    assert result == "fake-connection"
    assert fake_connect.state["n"] == 3  # 2 fail + 1 success


@pytest.mark.asyncio
async def test_connect_retry_exhausts_and_raises(monkeypatch):
    """Doimiy transient xato → barcha urinishlardan keyin xato qayta ko'tariladi."""
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_BASE_DELAY", 0.001)
    monkeypatch.setattr(dbmod, "_CONNECT_RETRY_MAX_DELAY", 0.001)
    fake_connect = _asyncpg_connect_raising(
        999, CannotConnectNowError("the database system is starting up")
    )
    with patch("asyncpg.connect", fake_connect):
        with pytest.raises(CannotConnectNowError):
            await dbmod._connect_asyncpg_with_retry()
    assert fake_connect.state["n"] == dbmod._CONNECT_RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_connect_no_retry_on_success(monkeypatch):
    """Birinchi urinishda ulansa — qayta urinmaydi."""
    fake_connect = _asyncpg_connect_raising(
        0, CannotConnectNowError("unused")
    )
    with patch("asyncpg.connect", fake_connect):
        result = await dbmod._connect_asyncpg_with_retry()
    assert result == "fake-connection"
    assert fake_connect.state["n"] == 1


@pytest.mark.asyncio
async def test_connect_no_retry_on_non_transient_error():
    """
    Transient bo'lmagan xato (masalan auth) — DARHOL qayta ko'tariladi,
    qayta urinilmaydi (fail-fast, 3.6s isrof yo'q).
    """
    call_count = {"n": 0}

    async def _connect(*args, **kwargs):
        call_count["n"] += 1
        raise ValueError("invalid password")

    with patch("asyncpg.connect", _connect):
        with pytest.raises(ValueError):
            await dbmod._connect_asyncpg_with_retry()
    assert call_count["n"] == 1


def test_cannotconnectnow_is_transient():
    """asyncpg CannotConnectNowError transient ro'yxatda (prod muhitida)."""
    assert CannotConnectNowError in dbmod._TRANSIENT_CONNECT_ERRORS
