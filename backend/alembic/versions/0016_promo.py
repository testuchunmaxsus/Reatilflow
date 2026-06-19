"""promo jadvali — T25 Aksiya moduli.

Jadval:
  promo — savdo aksiyalari (chegirma/bonus/sovg'a)
    id                UUID v7 PK
    name_uz           VARCHAR(255) NOT NULL
    name_ru           VARCHAR(255) NOT NULL
    promo_type        VARCHAR(20) NOT NULL DEFAULT 'discount'
    rule_json         JSON NOT NULL — {discount_percent?, discount_amount?, min_qty?}
    banner_url        TEXT NULL
    valid_from        DATE NOT NULL
    valid_to          DATE NOT NULL
    target_segment_id UUID FK → price_segment (SET NULL), nullable
    target_product_id UUID FK → product (SET NULL), nullable
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
    branch_id         UUID NULL
    client_uuid       UUID NULL — idempotentlik (partial unique IS NOT NULL)
    version           BIGINT (optimistik lock)
    created_at        TIMESTAMPTZ
    updated_at        TIMESTAMPTZ
    deleted_at        TIMESTAMPTZ NULL (soft delete)

Indekslar:
  ix_promo_is_active       — aktiv aksiyalar filtri
  ix_promo_valid_from      — sana bo'yicha qidiruv
  ix_promo_valid_to        — sana bo'yicha qidiruv
  ix_promo_target_segment  — segment bo'yicha qidiruv
  ix_promo_target_product  — mahsulot bo'yicha qidiruv

Idempotentlik:
  PostgreSQL: UNIQUE partial index (client_uuid WHERE client_uuid IS NOT NULL)
  SQLite: oddiy UNIQUE constraint (NULL != NULL simulatsiyasi)

downgrade guard (Postgres):
  promo jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-18
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nom konstantalari ────────────────────────────────────────────────────────

_TABLE_PROMO           = "promo"

_IDX_IS_ACTIVE         = "ix_promo_is_active"
_IDX_VALID_FROM        = "ix_promo_valid_from"
_IDX_VALID_TO          = "ix_promo_valid_to"
_IDX_TARGET_SEGMENT    = "ix_promo_target_segment"
_IDX_TARGET_PRODUCT    = "ix_promo_target_product"

_UQ_CLIENT_UUID        = "uq_promo_client_uuid"
_UQ_CLIENT_UUID_PART   = "uq_promo_client_uuid_partial"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # promo jadvali
    # ================================================================
    op.create_table(
        _TABLE_PROMO,
        # ── PK ──────────────────────────────────────────────────────
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        # ── Nom maydonlari ────────────────────────────────────────────
        sa.Column(
            "name_uz",
            sa.String(255),
            nullable=False,
            comment="Aksiya nomi (UZ)",
        ),
        sa.Column(
            "name_ru",
            sa.String(255),
            nullable=False,
            comment="Aksiya nomi (RU)",
        ),
        # ── Aksiya turi ───────────────────────────────────────────────
        sa.Column(
            "promo_type",
            sa.String(20),
            nullable=False,
            server_default="discount",
            comment="Aksiya turi: discount | bonus | gift",
        ),
        # ── Qoidalar (JSON) ───────────────────────────────────────────
        sa.Column(
            "rule_json",
            sa.JSON,
            nullable=False,
            comment="Chegirma qoidalari: {discount_percent?, discount_amount?, min_qty?}",
        ),
        # ── Banner ────────────────────────────────────────────────────
        sa.Column(
            "banner_url",
            sa.Text,
            nullable=True,
            comment="Banner URL (MinIO/S3, ixtiyoriy)",
        ),
        # ── Muddat ────────────────────────────────────────────────────
        sa.Column(
            "valid_from",
            sa.Date,
            nullable=False,
            comment="Aksiya boshlanish sanasi",
        ),
        sa.Column(
            "valid_to",
            sa.Date,
            nullable=False,
            comment="Aksiya tugash sanasi",
        ),
        # ── FK maydonlar ─────────────────────────────────────────────
        sa.Column(
            "target_segment_id",
            _uuid_col,
            sa.ForeignKey("price_segment.id", ondelete="SET NULL"),
            nullable=True,
            comment="Narx segmenti FK → price_segment (NULL = barchasi)",
        ),
        sa.Column(
            "target_product_id",
            _uuid_col,
            sa.ForeignKey("product.id", ondelete="SET NULL"),
            nullable=True,
            comment="Mahsulot FK → product (NULL = barchasi)",
        ),
        # ── Holat ────────────────────────────────────────────────────
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Aktiv holat",
        ),
        sa.Column(
            "branch_id",
            _uuid_col,
            nullable=True,
            comment="Filial ID (NULL = global)",
        ),
        sa.Column(
            "client_uuid",
            _uuid_col,
            nullable=True,
            comment="Idempotentlik UUID (partial unique IS NOT NULL)",
        ),
        # ── TimestampMixin ───────────────────────────────────────────
        sa.Column(
            "version",
            sa.BigInteger,
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

    # ── Indekslar ─────────────────────────────────────────────────────────────
    op.create_index(_IDX_IS_ACTIVE,       _TABLE_PROMO, ["is_active"])
    op.create_index(_IDX_VALID_FROM,      _TABLE_PROMO, ["valid_from"])
    op.create_index(_IDX_VALID_TO,        _TABLE_PROMO, ["valid_to"])
    op.create_index(_IDX_TARGET_SEGMENT,  _TABLE_PROMO, ["target_segment_id"])
    op.create_index(_IDX_TARGET_PRODUCT,  _TABLE_PROMO, ["target_product_id"])

    # ── Idempotentlik: client_uuid UNIQUE (IS NOT NULL) ───────────────────────
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_CLIENT_UUID_PART} "
            f"ON {_TABLE_PROMO} (client_uuid) WHERE client_uuid IS NOT NULL"
        ))
    else:
        op.create_index(
            _UQ_CLIENT_UUID,
            _TABLE_PROMO,
            ["client_uuid"],
            unique=True,
        )


def downgrade() -> None:
    """
    OGOHLANTIRISH — promo jadvali o'chiriladi.

    Postgres guard: agar promo jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE_PROMO}"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: {_TABLE_PROMO} jadvalida {count} ta qator mavjud. "
                    "Jadval o'chirish aksiya ma'lumotlarini yo'q qiladi. "
                    "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: COUNT xato — xavfsiz emas ({exc})"
            ) from exc

        # PostgreSQL partial indekslarni olib tashlash
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_CLIENT_UUID_PART}"))
        except Exception:
            pass

    # Indekslarni olib tashlash
    for idx, tbl in [
        (_IDX_TARGET_PRODUCT,  _TABLE_PROMO),
        (_IDX_TARGET_SEGMENT,  _TABLE_PROMO),
        (_IDX_VALID_TO,        _TABLE_PROMO),
        (_IDX_VALID_FROM,      _TABLE_PROMO),
        (_IDX_IS_ACTIVE,       _TABLE_PROMO),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass

    if not is_postgres:
        try:
            op.drop_index(_UQ_CLIENT_UUID, table_name=_TABLE_PROMO)
        except Exception:
            pass

    op.drop_table(_TABLE_PROMO)
