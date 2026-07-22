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
# Yechim: ulanish o'rnatishni qisqa eksponensial backoff bilan qayta urinish.
try:
    from asyncpg.exceptions import CannotConnectNowError as _CannotConnectNow
    _ASYNCPG_TRANSIENT: tuple[type[BaseException], ...] = (_CannotConnectNow,)
except Exception:  # asyncpg yo'q (sof SQLite test muhiti)
    _ASYNCPG_TRANSIENT = ()

from sqlalchemy.exc import InterfaceError as _SAInterfaceError
from sqlalchemy.exc import OperationalError as _SAOperationalError

# Faqat ulanish-darajasidagi vaqtinchalik xatolar (so'rov xatolari emas)
_TRANSIENT_CONNECT_ERRORS: tuple[type[BaseException], ...] = (
    *_ASYNCPG_TRANSIENT,
    _SAOperationalError,
    _SAInterfaceError,
    ConnectionError,
    OSError,
)
_CONNECT_RETRY_ATTEMPTS = 5
_CONNECT_RETRY_BASE_DELAY = 0.3
_CONNECT_RETRY_MAX_DELAY = 1.5


async def _acquire_connected_session(
    factory: "async_sessionmaker[AsyncSession]",
) -> AsyncSession:
    """
    Sessiya ochib, ulanishni MAJBURIY o'rnatadi — transient connect xatosida retry.

    `await session.connection()` pool'dan ulanish oladi (+ pool_pre_ping SELECT 1).
    DB qayta ishga tushayotgan bo'lsa (CannotConnectNowError) qisqa backoff bilan
    qayta urinadi. Barcha urinishlar tugasa — oxirgi xatoni qayta ko'taradi.
    SQLite (test) — birinchi urinishda ulanadi, retry ishlamaydi.
    """
    last_exc: BaseException | None = None
    for attempt in range(_CONNECT_RETRY_ATTEMPTS):
        session = factory()
        try:
            await session.connection()
            return session
        except _TRANSIENT_CONNECT_ERRORS as exc:
            last_exc = exc
            await session.close()
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
    faqat `echo` uzatiladi; PostgreSQL/prod uchun to'liq pool sozlamalari.
    """
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=settings.sql_echo)
    return create_async_engine(url, **_POOL_KWARGS)


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
    Uso'age:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
    """
    session = await _acquire_connected_session(AsyncSessionPrimary)
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
    """
    session = await _acquire_connected_session(AsyncSessionReplica)
    try:
        yield session
    finally:
        await session.close()


async def get_timescale_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: TimescaleDB sessiyasi — GPS time-series uchun.

    GPS endpointlari faqat shu dependency'dan foydalanadi (ADR §3.2).
    OLTP primary engine dan to'liq izolyatsiya.
    Uso'age:
        async def my_endpoint(db: AsyncSession = Depends(get_timescale_db)):
    """
    session = await _acquire_connected_session(AsyncSessionTimescale)
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
