"""Marketplace yetkazish maydonlari + store_inventory jadvali — MP3.

O'zgarishlar:
  marketplace_order   — courier_id, delivered_at, proof_photo_url, accepted_at qo'shildi
  store_inventory     — yangi jadval (buyer korxona POS inventari)

DIZAYN IZOHI:
  store_inventory.enterprise_id NOT NULL + FK → tenant izolyatsiyasi (MT1).
  Migratsiyada tenant-RLS (row-level security) qo'yilmaydi — service qatlamida
  enterprise_id filtri orqali nazorat qilinadi (marketplace pattern).

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ — `;` bilan ajratilgan buyruq yo'q).

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # ── 1. marketplace_order: courier_id ustuni qo'shish ───────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order "
            "ADD COLUMN IF NOT EXISTS courier_id UUID "
            "REFERENCES app_user(id) ON DELETE SET NULL"
        ))
    else:
        # SQLite — IF NOT EXISTS yo'q, pragma bilan tekshiramiz
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order ADD COLUMN courier_id TEXT"
        ))

    # ── 2. marketplace_order: delivered_at ustuni ──────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order "
            "ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ"
        ))
    else:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order ADD COLUMN delivered_at DATETIME"
        ))

    # ── 3. marketplace_order: proof_photo_url ustuni ──────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order "
            "ADD COLUMN IF NOT EXISTS proof_photo_url TEXT"
        ))
    else:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order ADD COLUMN proof_photo_url TEXT"
        ))

    # ── 4. marketplace_order: accepted_at ustuni ──────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order "
            "ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ"
        ))
    else:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order ADD COLUMN accepted_at DATETIME"
        ))

    # ── 5. store_inventory jadvali yaratish ────────────────────────────────

    if is_pg:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS store_inventory (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                enterprise_id   UUID NOT NULL
                    REFERENCES enterprise(id) ON DELETE RESTRICT,
                store_id        UUID NOT NULL
                    REFERENCES store(id) ON DELETE RESTRICT,
                product_id      UUID NOT NULL
                    REFERENCES product(id) ON DELETE RESTRICT,
                qty             NUMERIC(18,4) NOT NULL,
                cost_price      NUMERIC(18,2) NOT NULL,
                markup_percent  NUMERIC(10,4) NOT NULL DEFAULT 0,
                sale_price      NUMERIC(18,2) NOT NULL,
                expiry_date     DATE,
                status          VARCHAR(20) NOT NULL DEFAULT 'active',
                source_order_id UUID
                    REFERENCES marketplace_order(id) ON DELETE SET NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
    else:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS store_inventory (
                id              TEXT PRIMARY KEY,
                enterprise_id   TEXT NOT NULL,
                store_id        TEXT NOT NULL,
                product_id      TEXT NOT NULL,
                qty             NUMERIC NOT NULL,
                cost_price      NUMERIC NOT NULL,
                markup_percent  NUMERIC NOT NULL DEFAULT 0,
                sale_price      NUMERIC NOT NULL,
                expiry_date     DATE,
                status          TEXT NOT NULL DEFAULT 'active',
                source_order_id TEXT,
                created_at      DATETIME NOT NULL
            )
        """))

    # ── 6. Indeks: store_inventory.enterprise_id ───────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_enterprise "
            "ON store_inventory (enterprise_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_enterprise "
            "ON store_inventory (enterprise_id)"
        ))

    # ── 7. Indeks: store_inventory (store_id, product_id) ─────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_store_product "
            "ON store_inventory (store_id, product_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_store_product "
            "ON store_inventory (store_id, product_id)"
        ))

    # ── 8. Indeks: store_inventory.expiry_date (MP4 cron uchun) ───────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_expiry "
            "ON store_inventory (expiry_date)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_store_inv_expiry "
            "ON store_inventory (expiry_date)"
        ))

    # ── 9. Indeks: marketplace_order.courier_id (tez qidiruv) ─────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_courier "
            "ON marketplace_order (courier_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_courier "
            "ON marketplace_order (courier_id)"
        ))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    MP3 o'zgarishlarini qaytaradi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      Faqat dev/staging muhitida ishlatilsin.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # store_inventory indekslarini o'chirish
    if is_pg:
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_store_inv_expiry"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_store_inv_store_product"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_store_inv_enterprise"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_mp_order_courier"))
        bind.execute(sa.text("DROP TABLE IF EXISTS store_inventory"))

    # marketplace_order ustunlarini olib tashlash (faqat PostgreSQL)
    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order DROP COLUMN IF EXISTS accepted_at"
        ))
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order DROP COLUMN IF EXISTS proof_photo_url"
        ))
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order DROP COLUMN IF EXISTS delivered_at"
        ))
        bind.execute(sa.text(
            "ALTER TABLE marketplace_order DROP COLUMN IF EXISTS courier_id"
        ))
    else:
        # SQLite ustun o'chirish qo'llab-quvvatlanmaydi
        bind.execute(sa.text("DROP TABLE IF EXISTS store_inventory"))
