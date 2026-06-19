"""
TimescaleDB Alembic muhit konfiguratsiyasi.

OLTP env.py dan MUSTAQIL — settings.timescale_url ga ulanadi.
Faqat GPS/time-series migratsiyalari (alembic_timescale/versions/) bu yerdan o'tadi.

Qoidalar:
  - OLTP (alembic/) migratsiyalar bilan HECH QANDAY bog'liqlik yo'q.
  - OLTP migratsiya zanjiriga (down_revision) ulanish taqiqlangan.
  - Base.metadata ishlatilmaydi — faqat alembic_timescale/versions/ ichidagi
    migratsiyalar qo'llanadi.

Foydalanish:
  cd backend
  alembic -c alembic_timescale.ini upgrade head
  alembic -c alembic_timescale.ini current
  alembic -c alembic_timescale.ini history
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings

# Alembic Config obyekti
config = context.config

# Logging sozlamasi
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# TimescaleDB uchun metadata — faqat GPS modeli.
# OLTP Base.metadata ISHLATILMAYDI (izolyatsiya uchun).
# target_metadata=None: autogenerate o'chirilgan (DDL qo'lda yoziladi).
target_metadata = None

# TIMESCALE_URL ni alembic ga o'rnatish
config.set_main_option("sqlalchemy.url", settings.timescale_url)


def run_migrations_offline() -> None:
    """
    Offline rejim — SQL skript generatsiya.

    alembic -c alembic_timescale.ini upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        # TimescaleDB uchun alohida alembic_version jadval nomi —
        # OLTP alembic_version bilan to'qnashuv yo'q.
        version_table="alembic_version_timescale",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sinxron ulanish bilan migratsiyalarni bajarish."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # TimescaleDB uchun alohida alembic_version jadval nomi —
        # OLTP alembic_version bilan to'qnashuv yo'q.
        version_table="alembic_version_timescale",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async engine bilan TimescaleDB migratsiyalarini bajarish."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Online rejim — haqiqiy TimescaleDB ulanish bilan."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
