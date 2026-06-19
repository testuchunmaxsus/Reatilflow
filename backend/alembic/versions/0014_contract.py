"""contract jadvali — T23 Shartnoma moduli.

Jadval:
  contract — shartnoma hujjati
    id              UUID v7 PK
    store_id        UUID FK → store.id (RESTRICT)
    number          VARCHAR(100) NOT NULL — shartnoma raqami
    file_url        VARCHAR(1024) NULL — PDF URL (MinIO)
    signed_at       TIMESTAMPTZ NULL — imzolangan vaqt
    valid_from      DATE NOT NULL — amal boshlanishi
    valid_to        DATE NOT NULL — amal tugashi
    contract_type   VARCHAR(50) NULL — trade | employment | service | other
    branch_id       UUID NULL — filial ID
    client_uuid     UUID NULL — idempotentlik (partial unique IS NOT NULL)
    version         BIGINT (optimistik lock)
    created_at      TIMESTAMPTZ
    updated_at      TIMESTAMPTZ
    deleted_at      TIMESTAMPTZ NULL (soft delete)

status DERIVED: Python da valid_to ga qarab hisoblanadi (saqlanmaydi).

Indekslar:
  ix_contract_store_id   — store_id bo'yicha qidiruv
  ix_contract_valid_to   — valid_to bo'yicha expiring/expired filtr
  ix_contract_number     — number bo'yicha qidiruv

Idempotentlik:
  PostgreSQL: UNIQUE partial index (client_uuid WHERE client_uuid IS NOT NULL)
  SQLite: oddiy UNIQUE constraint (NULL != NULL — partial simulatsiyasi)

Unikalligi:
  (store_id, number, deleted_at IS NULL) — store ichida raqam unikal.
  PostgreSQL: partial unique index.
  SQLite: service darajasida tekshiriladi.

downgrade guard (Postgres):
  contract jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-18
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nom konstantalari ────────────────────────────────────────────────────────

_TABLE               = "contract"
_IDX_STORE_ID        = "ix_contract_store_id"
_IDX_VALID_TO        = "ix_contract_valid_to"
_IDX_NUMBER          = "ix_contract_number"
_UQ_CLIENT_UUID      = "uq_contract_client_uuid"
_UQ_CLIENT_UUID_PART = "uq_contract_client_uuid_partial"
_UQ_STORE_NUMBER_PART = "uq_contract_store_number_active"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # contract jadvali
    # ================================================================
    op.create_table(
        _TABLE,
        # ── PK ──────────────────────────────────────────────────────
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        # ── FK ──────────────────────────────────────────────────────
        sa.Column(
            "store_id",
            _uuid_col,
            sa.ForeignKey("store.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Do'kon FK → store (RESTRICT)",
        ),
        # ── Asosiy maydonlar ─────────────────────────────────────────
        sa.Column(
            "number",
            sa.String(100),
            nullable=False,
            comment="Shartnoma raqami",
        ),
        sa.Column(
            "file_url",
            sa.String(1024),
            nullable=True,
            comment="PDF fayl URL (MinIO/S3)",
        ),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Imzolangan vaqt (UTC)",
        ),
        sa.Column(
            "valid_from",
            sa.Date,
            nullable=False,
            comment="Amal boshlanishi (sana)",
        ),
        sa.Column(
            "valid_to",
            sa.Date,
            nullable=False,
            comment="Amal tugashi (sana) — status hisoblash uchun",
        ),
        sa.Column(
            "contract_type",
            sa.String(50),
            nullable=True,
            comment="Turi: trade | employment | service | other",
        ),
        sa.Column(
            "branch_id",
            _uuid_col,
            nullable=True,
            comment="Filial ID (ixtiyoriy)",
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
    op.create_index(_IDX_STORE_ID, _TABLE, ["store_id"])
    op.create_index(_IDX_VALID_TO, _TABLE, ["valid_to"])
    op.create_index(_IDX_NUMBER,   _TABLE, ["number"])

    # ── Idempotentlik: client_uuid UNIQUE (IS NOT NULL) ───────────────────────
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_CLIENT_UUID_PART} "
            f"ON {_TABLE} (client_uuid) WHERE client_uuid IS NOT NULL"
        ))
    else:
        op.create_index(
            _UQ_CLIENT_UUID,
            _TABLE,
            ["client_uuid"],
            unique=True,
        )

    # ── Store+number unikalligi — aktiv shartnomalar uchun ────────────────────
    # PostgreSQL: partial unique index (deleted_at IS NULL)
    # SQLite: servis darajasida tekshiriladi (partial WHERE qo'llab-quvvatlanmaydi)
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_STORE_NUMBER_PART} "
            f"ON {_TABLE} (store_id, number) "
            f"WHERE deleted_at IS NULL"
        ))


def downgrade() -> None:
    """
    OGOHLANTIRISH — contract jadvali o'chiriladi.

    Postgres guard: agar jadvalda qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: {_TABLE} jadvalida {count} ta qator mavjud. "
                    "Jadval o'chirilishi shartnoma ma'lumotlarini yo'q qiladi. "
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
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_STORE_NUMBER_PART}"))
        except Exception:
            pass
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_CLIENT_UUID_PART}"))
        except Exception:
            pass

    # Oddiy indekslar
    for idx, tbl in [
        (_IDX_NUMBER, _TABLE),
        (_IDX_VALID_TO, _TABLE),
        (_IDX_STORE_ID, _TABLE),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass

    if not is_postgres:
        try:
            op.drop_index(_UQ_CLIENT_UUID, table_name=_TABLE)
        except Exception:
            pass

    op.drop_table(_TABLE)
