"""
Alembic muhit konfiguratsiyasi.

Async engine (asyncpg) bilan ishlaydi.
DB URL .env faylidan (app.core.config.settings) o'qiladi.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Barcha modellarni import qilish — Base.metadata to'liq bo'lishi uchun
from app.core.config import settings
from app.models import Base  # noqa: F401 — barcha modellari ro'yxatga oladi

# Alembic Config obyekti
config = context.config

# Logging sozlamasi
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata — Alembic --autogenerate uchun
target_metadata = Base.metadata

# .env dan DB URL ni o'rnatish
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """
    Offline rejim — haqiqiy DB ulanishsiz SQL skript generatsiya.

    `alembic upgrade head --sql` buyrug'i uchun.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
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
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async engine bilan migratsiyalarni bajarish."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Online rejim — haqiqiy DB ulanish bilan."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
