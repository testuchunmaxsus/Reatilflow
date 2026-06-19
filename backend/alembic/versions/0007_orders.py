"""Buyurtma jadvallari — T11 (order, order_line).

Jadvallar:
  order       — buyurtma bosh yozuvi (status mashinasi)
  order_line  — buyurtma qatorlari

Indekslar:
  ix_order_store_id        — store_id bo'yicha qidiruv
  ix_order_agent_id        — agent_id bo'yicha qidiruv
  ix_order_status          — status bo'yicha filtr
  ix_order_ordered_at      — vaqt bo'yicha tartiblash
  uq_order_client_uuid     — client_uuid UNIQUE partial (IS NOT NULL) — idempotentlik
  ix_order_line_order_id   — order_id bo'yicha qatorlar

downgrade guard:
  Postgres: agar jadvallarda qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks nomlari ──────────────────────────────────────────────────────────

_IDX_ORDER_STORE    = "ix_order_store_id"
_IDX_ORDER_AGENT    = "ix_order_agent_id"
_IDX_ORDER_STATUS   = "ix_order_status"
_IDX_ORDER_DATE     = "ix_order_ordered_at"
# Idempotentlik: (store_id, client_uuid) — aktor-mahalliy doira
# Sabab: faqat client_uuid global unique bo'lsa, boshqa aktor bir xil UUID bilan
# boshqa do'konning client_uuid makonini egallab DoS hujumi qilishi mumkin.
# store_id ni qo'shish bu xavfni yo'q qiladi va har do'kon o'z makoniga ega bo'ladi.
_IDX_ORDER_CLIENT   = "uq_order_store_client_uuid"
_IDX_LINE_ORDER     = "ix_order_line_order_id"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # order — buyurtma bosh yozuvi
    # ================================================================
    op.create_table(
        "order",
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
            "agent_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Agent FK → app_user (RETAIL BOZOR rejimida)",
        ),
        sa.Column(
            "mode",
            sa.String(20),
            nullable=False,
            server_default="oddiy",
            comment="Rejim: bozor | oddiy",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="confirmed",
            comment="Holat: draft | confirmed | packed | delivering | delivered | canceled",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
            comment="Jami summa (Decimal)",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="UZS",
            comment="Valyuta kodi (ISO 4217)",
        ),
        sa.Column(
            "ordered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Buyurtma vaqti (UTC)",
        ),
        sa.Column(
            "client_uuid",
            _uuid_col,
            nullable=True,
            comment="Klient idempotentlik UUID",
        ),
        sa.Column(
            "branch_id",
            _uuid_col,
            nullable=True,
            comment="Filial ID",
        ),
        sa.Column(
            "warehouse_id",
            _uuid_col,
            nullable=True,
            comment="Ombor ID — stock chiqimi/qaytimi uchun (kompensatsiya to'g'ri omborga boradi)",
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

    # Indekslar
    op.create_index(_IDX_ORDER_STORE,  "order", ["store_id"],   unique=False)
    op.create_index(_IDX_ORDER_AGENT,  "order", ["agent_id"],   unique=False)
    op.create_index(_IDX_ORDER_STATUS, "order", ["status"],     unique=False)
    op.create_index(_IDX_ORDER_DATE,   "order", ["ordered_at"], unique=False)

    # (store_id, client_uuid) UNIQUE partial index — idempotentlik (DoS himoyasi)
    # Sabab: faqat client_uuid global unique bo'lsa → boshqa aktor begona UUID egallab DoS.
    # store_id qo'shilganda — har do'kon o'z client_uuid makonida ishlaydi.
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX {_IDX_ORDER_CLIENT}
            ON "order" (store_id, client_uuid)
            WHERE client_uuid IS NOT NULL
        """)
    else:
        # SQLite: partial WHERE qo'llab-quvvatlanmaydi
        op.create_index(_IDX_ORDER_CLIENT, "order", ["store_id", "client_uuid"], unique=True)

    # ================================================================
    # order_line — buyurtma qatorlari
    # ================================================================
    op.create_table(
        "order_line",
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — birlamchi kalit",
        ),
        sa.Column(
            "order_id",
            _uuid_col,
            sa.ForeignKey("order.id", ondelete="CASCADE"),
            nullable=False,
            comment="Buyurtma FK → order",
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
            comment="Miqdor (Decimal, musbat)",
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(18, 2),
            nullable=False,
            comment="Birlik narxi (Decimal)",
        ),
        sa.Column(
            "segment_id",
            _uuid_col,
            sa.ForeignKey("price_segment.id", ondelete="SET NULL"),
            nullable=True,
            comment="Narx segmenti FK → price_segment (ixtiyoriy)",
        ),
        sa.Column(
            "discount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
            comment="Chegirma summasi (Decimal, default=0)",
        ),
        sa.Column(
            "line_total",
            sa.Numeric(18, 2),
            nullable=False,
            comment="Qator jami: unit_price * qty - discount",
        ),
    )

    # order_line indeksi
    op.create_index(_IDX_LINE_ORDER, "order_line", ["order_id"], unique=False)


def downgrade() -> None:
    """
    OGOHLANTIRISH — Buyurtma ma'lumotlari yo'qoladi.

    Postgres guard: agar jadvallarda qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table_name in ("order_line", "order"):
            try:
                result = bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"'))
                count = result.scalar() or 0
                if count > 0:
                    raise RuntimeError(
                        f"downgrade() BLOKLANDI: {table_name} jadvalida {count} ta qator mavjud. "
                        "Downgrade qilish barcha buyurtma ma'lumotlarini yo'q qiladi. "
                        "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                    )
            except Exception as exc:
                if "downgrade() BLOKLANDI" in str(exc):
                    raise

    # Teskari tartib
    try:
        op.drop_index(_IDX_LINE_ORDER, table_name="order_line")
    except Exception:
        pass
    op.drop_table("order_line")

    try:
        if is_postgres:
            op.execute(f'DROP INDEX IF EXISTS {_IDX_ORDER_CLIENT}')
        else:
            op.drop_index(_IDX_ORDER_CLIENT, table_name="order")
    except Exception:
        pass

    for idx in (_IDX_ORDER_DATE, _IDX_ORDER_STATUS, _IDX_ORDER_AGENT, _IDX_ORDER_STORE):
        try:
            op.drop_index(idx, table_name="order")
        except Exception:
            pass

    op.drop_table("order")
