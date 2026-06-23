"""POS (Point-of-Sale) jadvallari — chakana sotuv yadrosi.

Jadvallar:
  pos_sale      — sotuv bosh yozuvi (enterprise_id NOT NULL FK, index)
  pos_sale_line — sotuv qatorlari (enterprise_id NOT NULL FK, index)

ADR-002 §2.8 bo'yicha:
  - enterprise_id NOT NULL + FK → enterprise(id) RESTRICT
  - RLS yoqilgan (PostgreSQL) — 0020 pattern bo'yicha
  - Index: ix_pos_sale_enterprise_id, ix_pos_sale_store_created
  - Idempotentlik: uq_pos_sale_store_client_uuid (partial, IS NOT NULL)

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ).

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
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

    # ── 1. pos_sale jadvali ──────────────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS pos_sale ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  version BIGINT NOT NULL DEFAULT 1,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  deleted_at TIMESTAMPTZ,"
            "  store_id UUID NOT NULL,"
            "  cashier_id UUID,"
            "  total_amount NUMERIC(18,2) NOT NULL DEFAULT 0,"
            "  discount_amount NUMERIC(18,2) NOT NULL DEFAULT 0,"
            "  payment_method VARCHAR(20) NOT NULL,"
            "  customer_phone VARCHAR(50),"
            "  status VARCHAR(20) NOT NULL DEFAULT 'completed',"
            "  client_uuid UUID,"
            "  enterprise_id UUID NOT NULL"
            ")"
        ))
    else:
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS pos_sale ("
            "  id TEXT PRIMARY KEY,"
            "  version INTEGER NOT NULL DEFAULT 1,"
            "  created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "  updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "  deleted_at TEXT,"
            "  store_id TEXT NOT NULL,"
            "  cashier_id TEXT,"
            "  total_amount NUMERIC NOT NULL DEFAULT 0,"
            "  discount_amount NUMERIC NOT NULL DEFAULT 0,"
            "  payment_method TEXT NOT NULL,"
            "  customer_phone TEXT,"
            "  status TEXT NOT NULL DEFAULT 'completed',"
            "  client_uuid TEXT,"
            "  enterprise_id TEXT NOT NULL"
            ")"
        ))

    # ── 2. pos_sale FK va indekslar ──────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE pos_sale ADD CONSTRAINT fk_pos_sale_enterprise_id "
            "FOREIGN KEY (enterprise_id) REFERENCES enterprise(id) ON DELETE RESTRICT"
        ))

        bind.execute(sa.text(
            "ALTER TABLE pos_sale ADD CONSTRAINT fk_pos_sale_store_id "
            "FOREIGN KEY (store_id) REFERENCES store(id) ON DELETE RESTRICT"
        ))

        bind.execute(sa.text(
            "ALTER TABLE pos_sale ADD CONSTRAINT fk_pos_sale_cashier_id "
            "FOREIGN KEY (cashier_id) REFERENCES app_user(id) ON DELETE SET NULL"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_enterprise_id ON pos_sale (enterprise_id)"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_store_created ON pos_sale (store_id, created_at)"
        ))

        # Partial unique index — idempotentlik (client_uuid IS NOT NULL)
        bind.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_pos_sale_store_client_uuid "
            "ON pos_sale (store_id, client_uuid) WHERE client_uuid IS NOT NULL"
        ))
    else:
        # SQLite
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_enterprise_id ON pos_sale (enterprise_id)"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_store_created ON pos_sale (store_id, created_at)"
        ))

        # SQLite'da partial unique — qiyin, UNIQUE constraint bilan yetarli
        # (ORM UniqueConstraint fallback sifatida)

    # ── 3. pos_sale_line jadvali ─────────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS pos_sale_line ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  sale_id UUID NOT NULL,"
            "  product_id UUID NOT NULL,"
            "  qty NUMERIC(18,4) NOT NULL,"
            "  unit_price NUMERIC(18,2) NOT NULL,"
            "  line_total NUMERIC(18,2) NOT NULL,"
            "  enterprise_id UUID NOT NULL"
            ")"
        ))
    else:
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS pos_sale_line ("
            "  id TEXT PRIMARY KEY,"
            "  sale_id TEXT NOT NULL,"
            "  product_id TEXT NOT NULL,"
            "  qty NUMERIC NOT NULL,"
            "  unit_price NUMERIC NOT NULL,"
            "  line_total NUMERIC NOT NULL,"
            "  enterprise_id TEXT NOT NULL"
            ")"
        ))

    # ── 4. pos_sale_line FK va indekslar ─────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE pos_sale_line ADD CONSTRAINT fk_pos_sale_line_sale_id "
            "FOREIGN KEY (sale_id) REFERENCES pos_sale(id) ON DELETE CASCADE"
        ))

        bind.execute(sa.text(
            "ALTER TABLE pos_sale_line ADD CONSTRAINT fk_pos_sale_line_product_id "
            "FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE RESTRICT"
        ))

        bind.execute(sa.text(
            "ALTER TABLE pos_sale_line ADD CONSTRAINT fk_pos_sale_line_enterprise_id "
            "FOREIGN KEY (enterprise_id) REFERENCES enterprise(id) ON DELETE RESTRICT"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_line_enterprise_id ON pos_sale_line (enterprise_id)"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_line_sale_id ON pos_sale_line (sale_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_line_enterprise_id ON pos_sale_line (enterprise_id)"
        ))

        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_pos_sale_line_sale_id ON pos_sale_line (sale_id)"
        ))

    # ── 5. PostgreSQL RLS ────────────────────────────────────────────────────

    if is_pg:
        _setup_rls_postgresql(bind)


def _setup_rls_postgresql(bind) -> None:
    """
    PostgreSQL Row-Level Security — pos_sale va pos_sale_line uchun.

    0020 pattern bo'yicha: tenant_isolation siyosati.
    """
    for table in ("pos_sale", "pos_sale_line"):
        bind.execute(sa.text(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
        ))

        bind.execute(sa.text(
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
        ))

        bind.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ("
            f"  enterprise_id = NULLIF("
            f"    current_setting('app.current_enterprise_id', true), '')"
            f"    ::uuid"
            f")"
        ))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    pos_sale_line va pos_sale jadvallarini o'chiradi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      Faqat dev/staging muhitida ishlatilsin.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    if is_pg:
        # RLS bekor qilish
        for table in ("pos_sale_line", "pos_sale"):
            bind.execute(sa.text(
                f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
            ))
            bind.execute(sa.text(
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
            ))

        bind.execute(sa.text("DROP TABLE IF EXISTS pos_sale_line CASCADE"))
        bind.execute(sa.text("DROP TABLE IF EXISTS pos_sale CASCADE"))
    else:
        bind.execute(sa.text("DROP TABLE IF EXISTS pos_sale_line"))
        bind.execute(sa.text("DROP TABLE IF EXISTS pos_sale"))
