"""Katalog qo'shimcha constraint va indekslar.

Qo'shilganlar:
  1. product.barcode uchun partial unique index WHERE deleted_at IS NULL
     (soft-delete bilan barcode dublikatiga yo'l qo'ymaydi).
  2. product.mxik_code uchun oddiy indeks (agar hali yo'q bo'lsa).
  3. product_price.(product_id, segment_id) uchun partial unique index
     WHERE valid_to IS NULL — bir vaqtda faqat bitta ochiq narx (race condition himoyasi).

Izoh:
  - Partial indekslar faqat PostgreSQL da ishlaydi.
  - SQLite (test muhit) da partial WHERE qo'llab-quvvatlanmasligi mumkin —
    bu holat migration'da dialect tekshiruvi orqali o'tkazib yuboriladi.
  - downgrade: barcha yangi indekslar DROP qilinadi.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Indeks nomlari
_IDX_BARCODE_UNIQUE = "uix_product_barcode_active"
_IDX_MXIK_CODE = "ix_product_mxik_code_v2"
_IDX_PRICE_OPEN = "uix_product_price_open"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── 1. product.barcode partial unique index WHERE deleted_at IS NULL ──────
    # Maqsad: bir xil barcode bilan ikki faol mahsulot bo'lmasin.
    # Soft-delete qilingan mahsulotlar cheklovdan ozod.
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {_IDX_BARCODE_UNIQUE}
            ON product (barcode)
            WHERE deleted_at IS NULL AND barcode IS NOT NULL
        """)
    else:
        # SQLite test muhiti: oddiy (non-partial) unique index
        op.create_index(
            _IDX_BARCODE_UNIQUE,
            "product",
            ["barcode"],
            unique=True,
        )

    # ── 2. product.mxik_code indeks ──────────────────────────────────────────
    # 0001 migratsiyasida ix_product_mxik_code partial index bor edi,
    # lekin bu nom bilan yana bir toza indeks qo'shamiz (agar yo'q bo'lsa).
    # PostgreSQL da IF NOT EXISTS ishlatiladi — xavfsiz.
    if is_postgres:
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS {_IDX_MXIK_CODE}
            ON product (mxik_code)
            WHERE mxik_code IS NOT NULL
        """)
    else:
        try:
            op.create_index(_IDX_MXIK_CODE, "product", ["mxik_code"])
        except Exception:
            pass  # Allaqachon mavjud bo'lsa e'tiborsiz qoldir

    # ── 3. product_price.(product_id, segment_id) partial unique WHERE valid_to IS NULL
    # Maqsad: bir mahsulot × segment kombinatsiyasi uchun faqat bitta ochiq narx.
    # valid_to IS NULL = ochiq muddat (joriy narx).
    # Bu constraint set_price() dagi SELECT FOR UPDATE bilan birgalikda ishlaydi.
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {_IDX_PRICE_OPEN}
            ON product_price (product_id, segment_id)
            WHERE valid_to IS NULL
        """)
    else:
        # SQLite uchun oddiy unique constraint
        op.create_index(
            _IDX_PRICE_OPEN,
            "product_price",
            ["product_id", "segment_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(f"DROP INDEX IF EXISTS {_IDX_PRICE_OPEN}")
        op.execute(f"DROP INDEX IF EXISTS {_IDX_MXIK_CODE}")
        op.execute(f"DROP INDEX IF EXISTS {_IDX_BARCODE_UNIQUE}")
    else:
        try:
            op.drop_index(_IDX_PRICE_OPEN, table_name="product_price")
        except Exception:
            pass
        try:
            op.drop_index(_IDX_MXIK_CODE, table_name="product")
        except Exception:
            pass
        try:
            op.drop_index(_IDX_BARCODE_UNIQUE, table_name="product")
        except Exception:
            pass
