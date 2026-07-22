"""
Async SQLAlchemy engine va session.

Primary/replica routing skeleti:
  - Yozish (DML) va moliyaviy o'qish → primary
  - Umumiy o'qish → replica (hozircha primary ga fallback)

TimescaleDB (GPS time-series):
  - GPS time-series ma'lumotlari OLTP dan izolyatsiya qilingan.
  - timescale_engine — alohida pool, settings.timescale_url ga ulanadi.
  - get_timescale_db — GPS endpointlari uchun FastAPI dependency.
  ADR §3.2: GPS trekking OLTP bilan aralashmaydi.

MT1 / ADR-013 (Variant B): RLS session variable mexanizmi.
  - O'zgaruvchi get_db() da EMAS — auth dependency'da (get_current_user,
    app/modules/auth/router.py) user yuklanib enterprise_id ma'lum bo'lgach
    o'rnatiladi (_set_rls_var). get_db() so'rov autentifikatsiyasidan OLDIN
    ishlaydi — u paytda enterprise_id hali noma'lum.
  - PostgreSQL: joriy tranzaksiyada set_config('app.current_enterprise_id', ..., true)
    chaqiriladi (is_local=true — tranzaksiya-lokal, pool orqali sizib chiqmaydi).
  - SQLite (test): dialekt-guard bilan no-op.
  - RLS siyosatlari (migratsiya 0020/0021) FORCE QILINMAGAN — bu o'zgaruvchi
    hozircha defense-in-depth tayyorgarlik; ASOSIY tenant izolyatsiya ilova-
    qatlamida apply_enterprise_filter() orqali ta'minlanadi (BATCH 1).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Transient connect retry (DB "starting up" / qisqa uzilish) ──────────────
# Railway Postgres qayta ishga tushganda asyncpg `CannotConnectNowError:
# the database system is starting up` qaytaradi. pool_pre_ping mavjud ulanishni
# tekshiradi, lekin DB butunlay rad etganda YANGI ulanish ham yarata olmaydi → 500.
# Yechim (#38): retry FASTAT haqiqiy ulanish o'rnatish nuqtasida — engine
# `async_creator`ida (pastda `_make_engine`) — get_db/get_db_replica/
# get_timescale_db esa LAZY (eager `session.connection()` chaqirilmaydi, pool
# ulanishni birinchi haqiqiy so'rovda oladi va tezda bo'shatadi).
try:
    from asyncpg.exceptions import (
        CannotConnectNowError as _CannotConnectNow,
    )
    from asyncpg.exceptions import (
        ConnectionDoesNotExistError as _ConnectionDoesNotExist,
    )
    _ASYNCPG_TRANSIENT_TYPES: tuple[type[BaseException], ...] = (
        _CannotConnectNow,
        _ConnectionDoesNotExist,
    )
except Exception:  # asyncpg yo'q (sof SQLite test muhiti)
    _ASYNCPG_TRANSIENT_TYPES = ()

# TCP darajasida "DB hali ko'tarilmagan" — port ochilmagan/qabul qilmayapti.
# Auth (masalan InvalidPasswordError — asyncpg.exceptions.InvalidPasswordError
# OSError/InterfaceError EMAS, alohida PostgresError avlodi) yoki boshqa
# config xatolari bu ro'yxatda YO'Q — ular qayta URILMAYDI (fail-fast).
_TCP_NOT_READY_TYPES: tuple[type[BaseException], ...] = (
    ConnectionRefusedError,
    TimeoutError,
)

# Orqaga-moslik: eski nom (test/monkeypatch uchun) — endi faqat predikat
# ma'lumot manbai, retry logikasi bevosita _is_transient_connect_error ishlatadi.
_TRANSIENT_CONNECT_ERRORS: tuple[type[BaseException], ...] = (
    *_ASYNCPG_TRANSIENT_TYPES,
    *_TCP_NOT_READY_TYPES,
)

_CONNECT_RETRY_ATTEMPTS = 5
_CONNECT_RETRY_BASE_DELAY = 0.3
_CONNECT_RETRY_MAX_DELAY = 1.5


def _is_transient_connect_error(exc: BaseException) -> bool:
    """
    Faqat "DB hali ko'tarilmagan / TCP tayyor emas" — HAQIQIY transient
    ulanish xatolarini True deb topadi (predikat, keng tuple emas).

    Tekshiriladi: `exc` o'zi VA (agar bo'lsa) `exc.__cause__`/`exc.orig`
    (SQLAlchemy OperationalError/InterfaceError asyncpg xatosini shu
    atributlarda o'raydi).

    Auth (InvalidPasswordError), konfiguratsiya xatolari va umumiy
    OSError/InterfaceError — False (qayta URILMAYDI, fail-fast).
    """
    candidates: list[BaseException] = [exc]
    orig = getattr(exc, "orig", None)
    if orig is not None:
        candidates.append(orig)
    cause = exc.__cause__
    if cause is not None:
        candidates.append(cause)

    for candidate in candidates:
        if _ASYNCPG_TRANSIENT_TYPES and isinstance(candidate, _ASYNCPG_TRANSIENT_TYPES):
            return True
        if isinstance(candidate, _TCP_NOT_READY_TYPES):
            return True
    return False


async def _connect_asyncpg_with_retry(*args: Any, **kwargs: Any) -> Any:
    """
    `create_async_engine(..., async_creator=...)` uchun asyncpg.connect o'ragichi.

    SQLAlchemy asyncpg dialekti bu funksiyani (arg/kwarg'lar bilan — URL'dan
    olingan host/port/user/password/database) HAR bir yangi jismoniy ulanish
    yaratilganda chaqiradi (pool birinchi so'rovda yoki pool_recycle'dan keyin).
    Transient xato (`_is_transient_connect_error`) bo'lsa qisqa eksponensial
    backoff bilan qayta urinadi; boshqa xatolar (auth, config) darhol qayta
    ko'tariladi (fail-fast).
    """
    import asyncpg

    last_exc: BaseException | None = None
    for attempt in range(_CONNECT_RETRY_ATTEMPTS):
        try:
            return await asyncpg.connect(*args, **kwargs)
        except Exception as exc:
            if not _is_transient_connect_error(exc):
                raise
            last_exc = exc
            if attempt == _CONNECT_RETRY_ATTEMPTS - 1:
                break
            delay = min(
                _CONNECT_RETRY_MAX_DELAY, _CONNECT_RETRY_BASE_DELAY * (2 ** attempt)
            )
            logger.warning(
                "db.connect.transient_retry attempt=%d/%d error=%r delay=%.2fs",
                attempt + 1, _CONNECT_RETRY_ATTEMPTS, exc, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# ─── Engine sozlamalari ─────────────────────────────────────────────────────

# Umumiy pool parametrlari (PostgreSQL/prod uchun)
# echo — SQL_ECHO o'zgaruvchisiga bog'liq (app_debug emas)
_POOL_KWARGS = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,   # uzilib qolgan ulanishlarni avtomatik qayta ulash
    "pool_recycle": 1800,    # 30 daqiqada ulanishni yangilash (pgbouncer-friendly)
    "echo": settings.sql_echo,
}


def _make_engine(url: str) -> AsyncEngine:
    """
    URL dialektiga mos async engine yaratadi.

    SQLite (dev/test/seed-demo) `pool_size`/`max_overflow` ni QO'LLAB-QUVVATLAMAYDI
    (StaticPool/NullPool) — bu argumentlar TypeError beradi. Shu sabab sqlite uchun
    faqat `echo` uzatiladi; PostgreSQL/prod uchun to'liq pool sozlamalari + #38
    `async_creator` (transient-connect retry haqiqiy ulanish nuqtasida).
    """
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=settings.sql_echo)
    return create_async_engine(
        url, **_POOL_KWARGS, async_creator=_connect_asyncpg_with_retry
    )


# Primary engine — barcha yozishlar + moliyaviy o'qishlar
primary_engine: AsyncEngine = _make_engine(settings.database_url)

# Replica engine — umumiy o'qishlar.
# database_replica_url bo'sh bo'lsa — alohida pool ochmay, primary_engine dan foydalanamiz.
if settings.database_replica_url:
    replica_engine: AsyncEngine = _make_engine(settings.database_replica_url)
else:
    # Fallback: replica URL ko'rsatilmagan — primary engine ishlatiladi
    replica_engine = primary_engine

# TimescaleDB engine — GPS time-series ma'lumotlari (ADR §3.2: OLTP izolyatsiya).
# Alohida pool — primary_engine dan mustaqil.
timescale_engine: AsyncEngine = _make_engine(settings.timescale_url)

# ─── Session factories ──────────────────────────────────────────────────────

AsyncSessionPrimary = async_sessionmaker(
    bind=primary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

AsyncSessionReplica = async_sessionmaker(
    bind=replica_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# TimescaleDB session factory — GPS time-series uchun
AsyncSessionTimescale = async_sessionmaker(
    bind=timescale_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─── FastAPI dependency ─────────────────────────────────────────────────────

async def _set_rls_var(session: AsyncSession, enterprise_id: Any) -> None:
    """
    Joriy tranzaksiyada PostgreSQL'ga app.current_enterprise_id o'rnatadi.

    RLS (Row-Level Security) siyosatlari (migratsiya 0020/0021) bu o'zgaruvchiga
    tayanadi, lekin ULAR FORCE QILINMAGAN (ADR-013 Variant B) — ilova jadval-egasi
    rol bilan ulanadi va shu bois RLS'dan ozod. ASOSIY tenant enforcement ilova-
    qatlamida apply_enterprise_filter() orqali amalga oshadi; bu funksiya
    defense-in-depth tayyorgarligi.

    `set_config(..., true)` ishlatiladi — `SET LOCAL ... = :bind` EMAS, chunki
    asyncpg SET LOCAL kabi utility buyruqlarga bind parametr bermaydi
    (natijada har chaqiruv PostgresSyntaxError bergan bo'lardi). set_config
    oddiy SQL funksiya bo'lgani uchun bind parametrni to'g'ri qabul qiladi.
    `is_local=true` — o'zgaruvchi FAQAT joriy tranzaksiya doirasida amal qiladi;
    `false` ISHLATILMAYDI (aks holda pool orqali boshqa so'rovlarga sizib chiqadi).

    Chaqirilishi kerak: mavjud tranzaksiya ICHIDA (masalan get_current_user'da,
    user yuklab olingandan keyin) — is_local=true shuni talab qiladi.

    SQLite'da (dialekt boshqacha) no-op.

    Args:
        session:       AsyncSession (tranzaksiya ichida).
        enterprise_id: UUID yoki None (superadmin/token yo'q → bo'sh string).
    """
    try:
        bind = await session.connection()
        if bind.dialect.name != "postgresql":
            return  # SQLite — no-op

        # superadmin/enterprise_id yo'q — bo'sh string.
        # RLS USING: current_setting('app.current_enterprise_id', true)
        # true = xato bermaslik (NULL qaytaradi) → NULL::uuid hech qanday
        # qatorga mos kelmaydi. superadmin cross-tenant kirishi BYPASSRLS
        # rol orqali ta'minlanadi (migratsiyada), shu setter orqali emas.
        val = str(enterprise_id) if enterprise_id is not None else ""
        await session.execute(
            sa.text(
                "SELECT set_config('app.current_enterprise_id', :eid, true)"
            ).bindparams(eid=val)
        )
    except Exception:
        # RLS set xatosi — log yozamiz, lekin request'ni to'xtatmaymiz
        # (RLS FORCE qilinmagan — bu defense-in-depth prep, muvaffaqiyatsizlik
        # app-qatlamidagi apply_enterprise_filter enforcementga ta'sir qilmaydi).
        logger.warning("RLS enterprise_id set qilishda xato (no-op)", exc_info=True)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: primary DB sessiyasi.

    Yozish va moliyaviy o'qishlar uchun ishlatiladi.
    RLS session variable bu yerda O'RNATILMAYDI — get_db() autentifikatsiyadan
    OLDIN ishlaydi (user/enterprise_id hali noma'lum). O'zgaruvchi keyinroq,
    get_current_user() (app/modules/auth/router.py) ichida, user yuklab
    olingach _set_rls_var() orqali o'rnatiladi (xuddi shu tranzaksiyada).

    #38: LAZY — pool ulanishini bu yerda MAJBURAN olmaydi (eski xatti-harakat
    dependency-resolve paytida `session.connection()` chaqirib pool'dan
    ulanish olar va butun request davomida ushlab turardi — DB'siz/faqat-AI
    endpointlar ham pool'ni band qilardi). Ulanish endi birinchi haqiqiy
    so'rovda (yoki `session.commit()`da) olinadi; transient-connect retry
    endi engine darajasida (`_connect_asyncpg_with_retry`, `_make_engine`).
    Uso'age:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
    """
    session = AsyncSessionPrimary()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_replica() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: replica DB sessiyasi (read-only).

    Katalog, statistika, ro'yxat endpointlar uchun.
    Moliyaviy ma'lumotlar uchun get_db() ishlatilsin.
    #38: LAZY (izoh uchun get_db() docstring'iga qarang).
    """
    session = AsyncSessionReplica()
    try:
        yield session
    finally:
        await session.close()


async def get_timescale_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: TimescaleDB sessiyasi — GPS time-series uchun.

    GPS endpointlari faqat shu dependency'dan foydalanadi (ADR §3.2).
    OLTP primary engine dan to'liq izolyatsiya.
    #38: LAZY (izoh uchun get_db() docstring'iga qarang).
    Uso'age:
        async def my_endpoint(db: AsyncSession = Depends(get_timescale_db)):
    """
    session = AsyncSessionTimescale()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ─── Startup / Shutdown ────────────────────────────────────────────────────

async def close_db_connections() -> None:
    """Ilova o'chganda barcha pool ulanishlarini yopish."""
    await primary_engine.dispose()
    # Replica primary dan farqli bo'lsagina alohida yopiladi
    if replica_engine is not primary_engine:
        await replica_engine.dispose()
    # TimescaleDB engine — primary dan har doim alohida
    await timescale_engine.dispose()
