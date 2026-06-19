"""Buyurtma shablonlari — T12 (order_template, order_template_line).

Jadvallar:
  order_template      — buyurtma shabloni (product+qty faqat, NARX YO'Q)
  order_template_line — shablon qatorlari (product_id, qty; narx apply paytida katalogdan)

NARX XAVFSIZLIGI (CRITICAL):
  order_template_line jadvalida unit_price ustuni YO'Q.
  Narx faqat apply_template() paytida do'kon segmenti bo'yicha katalogdan olinadi.
  Bu server-avtoritar narx xavfsizligini ta'minlaydi.

Indekslar:
  ix_order_template_store_id        — store_id bo'yicha qidiruv
  ix_order_template_created_by      — created_by bo'yicha qidiruv
  ix_order_template_line_template_id — template_id bo'yicha qatorlar

downgrade guard:
  Postgres: agar jadvallarda qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks nomlari ──────────────────────────────────────────────────────────

_IDX_TPL_STORE   = "ix_order_template_store_id"
_IDX_TPL_CREATOR = "ix_order_template_created_by"
_IDX_TPL_LINE    = "ix_order_template_line_template_id"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # order_template — buyurtma shabloni
    # ================================================================
    op.create_table(
        "order_template",
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        sa.Column(
            "store_id",
            _uuid_col,
            sa.ForeignKey("store.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Do'kon FK → store",
        ),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="Shablon nomi",
        ),
        sa.Column(
            "created_by",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Yaratuvchi FK → app_user",
        ),
        sa.Column(
            "branch_id",
            _uuid_col,
            nullable=True,
            comment="Filial ID (ixtiyoriy)",
        ),
        # TimestampMixin ustunlari
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
            comment="Optimistik lock versiyasi",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Oxirgi yangilangan vaqt (UTC)",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft delete vaqti (NULL = aktiv)",
        ),
    )

    op.create_index(_IDX_TPL_STORE,   "order_template", ["store_id"],    unique=False)
    op.create_index(_IDX_TPL_CREATOR, "order_template", ["created_by"],  unique=False)

    # ================================================================
    # order_template_line — shablon qatorlari
    # MUHIM: unit_price YO'Q — narx apply paytida katalogdan olinadi
    # ================================================================
    op.create_table(
        "order_template_line",
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — birlamchi kalit",
        ),
        sa.Column(
            "template_id",
            _uuid_col,
            sa.ForeignKey("order_template.id", ondelete="CASCADE"),
            nullable=False,
            comment="Shablon FK → order_template",
        ),
        sa.Column(
            "product_id",
            _uuid_col,
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mahsulot FK → product",
        ),
        sa.Column(
            "qty",
            sa.Numeric(18, 4),
            nullable=False,
            comment="Miqdor (Decimal, musbat) — narx YO'Q (server-avtoritar apply paytida)",
        ),
        # unit_price QASDDAN YO'Q — narx server-avtoritar invarianti
    )

    op.create_index(_IDX_TPL_LINE, "order_template_line", ["template_id"], unique=False)


def downgrade() -> None:
    """
    OGOHLANTIRISH — Shablon ma'lumotlari yo'qoladi.

    Postgres guard: agar jadvallarda qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table_name in ("order_template_line", "order_template"):
            try:
                result = bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"'))
                count = result.scalar() or 0
                if count > 0:
                    raise RuntimeError(
                        f"downgrade() BLOKLANDI: {table_name} jadvalida {count} ta qator mavjud. "
                        "Downgrade qilish barcha shablon ma'lumotlarini yo'q qiladi. "
                        "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                    )
            except Exception as exc:
                if "downgrade() BLOKLANDI" in str(exc):
                    raise

    # Teskari tartib
    try:
        op.drop_index(_IDX_TPL_LINE, table_name="order_template_line")
    except Exception:
        pass
    op.drop_table("order_template_line")

    for idx in (_IDX_TPL_CREATOR, _IDX_TPL_STORE):
        try:
            op.drop_index(idx, table_name="order_template")
        except Exception:
            pass

    op.drop_table("order_template")
