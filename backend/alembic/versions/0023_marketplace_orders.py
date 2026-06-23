"""Marketplace buyurtma jadvallari — MP2.

Jadvallar:
  marketplace_order      — cross-tenant buyurtma (buyer ↔ supplier)
  marketplace_order_line — buyurtma qatorlari (server-narx)

DIZAYN IZOHI:
  Bu jadvallar ATAYIN ikki-korxonali (cross-tenant).
  Oddiy tenant-RLS (enterprise_id bo'yicha) QO'YILMAYDI — bu istisno.
  Access nazorati service qatlamida amalga oshiriladi:
    (buyer_enterprise_id == me OR supplier_enterprise_id == me)
  Uchinchi korxona buyurtmani ko'rishi mumkin emas (service tekshiradi → 404).

Status mashinasi (MP2):
  pending → confirmed | rejected
  confirmed → delivering (MP3)
  delivering → delivered → accepted (MP3)

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ).

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # ── 1. marketplace_order jadvali ────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS marketplace_order (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                buyer_enterprise_id  UUID NOT NULL
                    REFERENCES enterprise(id) ON DELETE RESTRICT,
                buyer_store_id       UUID
                    REFERENCES store(id) ON DELETE SET NULL,
                buyer_user_id        UUID NOT NULL
                    REFERENCES app_user(id) ON DELETE RESTRICT,
                supplier_enterprise_id UUID NOT NULL
                    REFERENCES enterprise(id) ON DELETE RESTRICT,
                status               VARCHAR(20) NOT NULL DEFAULT 'pending',
                total_amount         NUMERIC(18,2) NOT NULL DEFAULT 0,
                reject_reason        TEXT,
                client_uuid          UUID,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_mp_order_buyer_client_uuid
                    UNIQUE (buyer_enterprise_id, client_uuid)
            )
        """))
    else:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS marketplace_order (
                id                   TEXT PRIMARY KEY,
                buyer_enterprise_id  TEXT NOT NULL,
                buyer_store_id       TEXT,
                buyer_user_id        TEXT NOT NULL,
                supplier_enterprise_id TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'pending',
                total_amount         NUMERIC NOT NULL DEFAULT 0,
                reject_reason        TEXT,
                client_uuid          TEXT,
                created_at           DATETIME NOT NULL,
                updated_at           DATETIME NOT NULL
            )
        """))

    # ── 2. marketplace_order_line jadvali ───────────────────────────────────

    if is_pg:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS marketplace_order_line (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id    UUID NOT NULL
                    REFERENCES marketplace_order(id) ON DELETE CASCADE,
                product_id  UUID NOT NULL
                    REFERENCES product(id) ON DELETE RESTRICT,
                qty         NUMERIC(18,4) NOT NULL,
                unit_price  NUMERIC(18,2) NOT NULL,
                line_total  NUMERIC(18,2) NOT NULL
            )
        """))
    else:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS marketplace_order_line (
                id          TEXT PRIMARY KEY,
                order_id    TEXT NOT NULL,
                product_id  TEXT NOT NULL,
                qty         NUMERIC NOT NULL,
                unit_price  NUMERIC NOT NULL,
                line_total  NUMERIC NOT NULL
            )
        """))

    # ── 3. Indekslar: buyer_enterprise_id ──────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_buyer_enterprise "
            "ON marketplace_order (buyer_enterprise_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_buyer_enterprise "
            "ON marketplace_order (buyer_enterprise_id)"
        ))

    # ── 4. Indeks: supplier_enterprise_id + status ──────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_supplier_enterprise_status "
            "ON marketplace_order (supplier_enterprise_id, status)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_supplier_enterprise_status "
            "ON marketplace_order (supplier_enterprise_id, status)"
        ))

    # ── 5. Indeks: order_line.order_id ──────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_line_order_id "
            "ON marketplace_order_line (order_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mp_order_line_order_id "
            "ON marketplace_order_line (order_id)"
        ))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    marketplace_order_line va marketplace_order jadvallarini o'chiradi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      Faqat dev/staging muhitida ishlatilsin.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    if is_pg:
        bind.execute(sa.text(
            "DROP INDEX IF EXISTS ix_mp_order_line_order_id"
        ))
        bind.execute(sa.text(
            "DROP INDEX IF EXISTS ix_mp_order_supplier_enterprise_status"
        ))
        bind.execute(sa.text(
            "DROP INDEX IF EXISTS ix_mp_order_buyer_enterprise"
        ))
        bind.execute(sa.text(
            "DROP TABLE IF EXISTS marketplace_order_line"
        ))
        bind.execute(sa.text(
            "DROP TABLE IF EXISTS marketplace_order"
        ))
    else:
        bind.execute(sa.text("DROP TABLE IF EXISTS marketplace_order_line"))
        bind.execute(sa.text("DROP TABLE IF EXISTS marketplace_order"))
