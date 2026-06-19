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
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

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

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: primary DB sessiyasi.

    Yozish va moliyaviy o'qishlar uchun ishlatiladi.
    Uso'age:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionPrimary() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_replica() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: replica DB sessiyasi (read-only).

    Katalog, statistika, ro'yxat endpointlar uchun.
    Moliyaviy ma'lumotlar uchun get_db() ishlatilsin.
    """
    async with AsyncSessionReplica() as session:
        try:
            yield session
        except Exception:
            raise
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
    async with AsyncSessionTimescale() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Startup / Shutdown ────────────────────────────────────────────────────

async def close_db_connections() -> None:
    """Ilova o'chganda barcha pool ulanishlarini yopish."""
    await primary_engine.dispose()
    # Replica primary dan farqli bo'lsagina alohida yopiladi
    if replica_engine is not primary_engine:
        await replica_engine.dispose()
    # TimescaleDB engine — primary dan har doim alohida
    await timescale_engine.dispose()
