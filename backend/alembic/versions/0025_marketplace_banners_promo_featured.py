"""Marketplace reklama bannerlari + promo.marketplace_featured — MP5.

O'zgarishlar:
  ad_banner              — yangi jadval (korxona reklama bannerlari)
  promo.marketplace_featured — yangi ustun (qaynoq aksiya opt-in bayrog'i)

DIZAYN IZOHI:
  ad_banner.enterprise_id NOT NULL + FK → korxona-scoped CRUD.
  Lekin GET /marketplace/banners cross-tenant (faqat aktiv + valid).
  promo.marketplace_featured = True → GET /marketplace/promos da ko'rinadi.

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # ── 1. ad_banner jadvali yaratish ──────────────────────────────────────────

    if is_pg:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS ad_banner (
                id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                enterprise_id     UUID NOT NULL
                    REFERENCES enterprise(id) ON DELETE RESTRICT,
                title             VARCHAR(255) NOT NULL,
                image_url         TEXT,
                target_url        TEXT,
                target_product_id UUID
                    REFERENCES product(id) ON DELETE SET NULL,
                is_active         BOOLEAN NOT NULL DEFAULT TRUE,
                priority          INTEGER NOT NULL DEFAULT 0,
                valid_from        DATE NOT NULL,
                valid_to          DATE NOT NULL,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
    else:
        bind.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS ad_banner (
                id                TEXT PRIMARY KEY,
                enterprise_id     TEXT NOT NULL,
                title             VARCHAR(255) NOT NULL,
                image_url         TEXT,
                target_url        TEXT,
                target_product_id TEXT,
                is_active         BOOLEAN NOT NULL DEFAULT 1,
                priority          INTEGER NOT NULL DEFAULT 0,
                valid_from        DATE NOT NULL,
                valid_to          DATE NOT NULL,
                created_at        DATETIME NOT NULL,
                updated_at        DATETIME NOT NULL
            )
        """))

    # ── 2. Indeks: ad_banner.enterprise_id ────────────────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ad_banner_enterprise_id "
            "ON ad_banner (enterprise_id)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ad_banner_enterprise_id "
            "ON ad_banner (enterprise_id)"
        ))

    # ── 3. Indeks: ad_banner (is_active, priority) ─────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ad_banner_active_priority "
            "ON ad_banner (is_active, priority)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ad_banner_active_priority "
            "ON ad_banner (is_active, priority)"
        ))

    # ── 4. promo.marketplace_featured ustuni qo'shish ─────────────────────────

    if is_pg:
        bind.execute(sa.text(
            "ALTER TABLE promo "
            "ADD COLUMN IF NOT EXISTS marketplace_featured BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    else:
        bind.execute(sa.text(
            "ALTER TABLE promo ADD COLUMN marketplace_featured BOOLEAN NOT NULL DEFAULT 0"
        ))

    # ── 5. Indeks: promo.marketplace_featured (tez qidiruv) ───────────────────

    if is_pg:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_promo_marketplace_featured "
            "ON promo (marketplace_featured)"
        ))
    else:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_promo_marketplace_featured "
            "ON promo (marketplace_featured)"
        ))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    MP5 o'zgarishlarini qaytaradi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      Faqat dev/staging muhitida ishlatilsin.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    if is_pg:
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_promo_marketplace_featured"))
        bind.execute(sa.text("ALTER TABLE promo DROP COLUMN IF EXISTS marketplace_featured"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_ad_banner_active_priority"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_ad_banner_enterprise_id"))
        bind.execute(sa.text("DROP TABLE IF EXISTS ad_banner"))
    else:
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_promo_marketplace_featured"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_ad_banner_active_priority"))
        bind.execute(sa.text("DROP INDEX IF EXISTS ix_ad_banner_enterprise_id"))
        bind.execute(sa.text("DROP TABLE IF EXISTS ad_banner"))
