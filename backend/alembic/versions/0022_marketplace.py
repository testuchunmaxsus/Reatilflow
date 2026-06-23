"""Marketplace maydonlari — product jadvali (MP1).

Jadval: product
  + marketplace_published  BOOLEAN NOT NULL DEFAULT FALSE
  + marketplace_price      NUMERIC(18,2) NULL

ADR-002 §2.9 bo'yicha:
  - marketplace_published: opt-in bayroq (default=False → hech narsa sızmaydi).
  - marketplace_price: ixtiyoriy ulgurji narx; NULL bo'lsa segment narx ishlatiladi.
  - Backfill KERAK EMAS — yangi ustunlar, default False/NULL.

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ).

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _is_sqlite(bind) -> bool:
    return bind.dialect.name == "sqlite"


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # ── 1. marketplace_published ustuni ─────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS "
            "marketplace_published BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    else:
        # SQLite: ADD COLUMN BOOLEAN DEFAULT 0
        bind.execute(sa.text(
            "ALTER TABLE product ADD COLUMN "
            "marketplace_published INTEGER NOT NULL DEFAULT 0"
        ))

    # ── 2. marketplace_price ustuni ──────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS "
            "marketplace_price NUMERIC(18,2) NULL"
        ))
    else:
        # SQLite: ADD COLUMN NUMERIC NULL
        bind.execute(sa.text(
            "ALTER TABLE product ADD COLUMN "
            "marketplace_price NUMERIC NULL"
        ))

    # ── 3. Indeks: marketplace_published=TRUE bo'lgan mahsulotlar uchun ─────

    if is_pg:
        # Partial index — faqat published mahsulotlar (ozchiligi)
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_marketplace_published "
            "ON product (enterprise_id) WHERE marketplace_published = TRUE"
        ))
    else:
        # SQLite: oddiy indeks
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_marketplace_published "
            "ON product (marketplace_published)"
        ))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    marketplace_published va marketplace_price ustunlarini o'chiradi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      Faqat dev/staging muhitida ishlatilsin.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    if is_pg:
        bind.execute(sa.text(
            "DROP INDEX IF EXISTS ix_product_marketplace_published"
        ))
        bind.execute(sa.text(
            "ALTER TABLE product DROP COLUMN IF EXISTS marketplace_price"
        ))
        bind.execute(sa.text(
            "ALTER TABLE product DROP COLUMN IF EXISTS marketplace_published"
        ))
    else:
        # SQLite: ustun o'chirish to'g'ridan-to'g'ri qo'llab-quvvatlanmaydi
        # (test muhitida rollback yetarli)
        pass
