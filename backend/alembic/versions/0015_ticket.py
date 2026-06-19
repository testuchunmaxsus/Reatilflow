"""ticket va ticket_message jadvallari — T24 Murojaat moduli.

Jadvallar:
  ticket — murojaat (taklif / e'tiroz)
    id              UUID v7 PK
    store_id        UUID FK → store.id (SET NULL), nullable — NULL=xodim murojaati
    author_id       UUID FK → app_user.id (SET NULL), nullable
    ticket_type     VARCHAR(20) NOT NULL — taklif | etiroz
    subject         VARCHAR(255) NOT NULL
    body            TEXT NOT NULL
    status          VARCHAR(20) NOT NULL DEFAULT 'new' — new|in_progress|resolved|closed
    assigned_to     UUID FK → app_user.id (SET NULL), nullable
    branch_id       UUID NULL — filial ID
    client_uuid     UUID NULL — idempotentlik (partial unique IS NOT NULL)
    version         BIGINT (optimistik lock)
    created_at      TIMESTAMPTZ
    updated_at      TIMESTAMPTZ
    deleted_at      TIMESTAMPTZ NULL (soft delete)

  ticket_message — murojaatga qo'shilgan xabar (append-only)
    id              UUID v7 PK
    ticket_id       UUID FK → ticket.id (CASCADE)
    author_id       UUID FK → app_user.id (SET NULL), nullable
    body            TEXT NOT NULL
    attachment_url  VARCHAR(1024) NULL
    created_at      TIMESTAMPTZ

Indekslar:
  ix_ticket_store_id    — store_id bo'yicha qidiruv
  ix_ticket_author_id   — author_id bo'yicha qidiruv
  ix_ticket_status      — status bo'yicha filtr
  ix_ticket_message_ticket_id — ticket_id bo'yicha join

Idempotentlik:
  PostgreSQL: UNIQUE partial index (client_uuid WHERE client_uuid IS NOT NULL)
  SQLite: oddiy UNIQUE constraint (NULL != NULL — partial simulatsiyasi)

downgrade guard (Postgres):
  ticket jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-18
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nom konstantalari ────────────────────────────────────────────────────────

_TABLE_TICKET         = "ticket"
_TABLE_MESSAGE        = "ticket_message"

_IDX_STORE_ID         = "ix_ticket_store_id"
_IDX_AUTHOR_ID        = "ix_ticket_author_id"
_IDX_STATUS           = "ix_ticket_status"
_IDX_MSG_TICKET_ID    = "ix_ticket_message_ticket_id"

_UQ_CLIENT_UUID       = "uq_ticket_client_uuid"
_UQ_CLIENT_UUID_PART  = "uq_ticket_client_uuid_partial"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # ticket jadvali
    # ================================================================
    op.create_table(
        _TABLE_TICKET,
        # ── PK ──────────────────────────────────────────────────────
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        # ── FK maydonlar ─────────────────────────────────────────────
        sa.Column(
            "store_id",
            _uuid_col,
            sa.ForeignKey("store.id", ondelete="SET NULL"),
            nullable=True,
            comment="Do'kon FK → store (NULL = xodim murojaati)",
        ),
        sa.Column(
            "author_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Muallif FK → app_user",
        ),
        sa.Column(
            "assigned_to",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Mas'ul xodim FK → app_user",
        ),
        # ── Asosiy maydonlar ─────────────────────────────────────────
        sa.Column(
            "ticket_type",
            sa.String(20),
            nullable=False,
            comment="Murojaat turi: taklif | etiroz",
        ),
        sa.Column(
            "subject",
            sa.String(255),
            nullable=False,
            comment="Murojaat mavzusi",
        ),
        sa.Column(
            "body",
            sa.Text,
            nullable=False,
            comment="Murojaat matni",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="new",
            comment="Holat: new | in_progress | resolved | closed",
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
    op.create_index(_IDX_STORE_ID,  _TABLE_TICKET, ["store_id"])
    op.create_index(_IDX_AUTHOR_ID, _TABLE_TICKET, ["author_id"])
    op.create_index(_IDX_STATUS,    _TABLE_TICKET, ["status"])

    # ── Idempotentlik: client_uuid UNIQUE (IS NOT NULL) ───────────────────────
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_CLIENT_UUID_PART} "
            f"ON {_TABLE_TICKET} (client_uuid) WHERE client_uuid IS NOT NULL"
        ))
    else:
        op.create_index(
            _UQ_CLIENT_UUID,
            _TABLE_TICKET,
            ["client_uuid"],
            unique=True,
        )

    # ================================================================
    # ticket_message jadvali
    # ================================================================
    op.create_table(
        _TABLE_MESSAGE,
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — birlamchi kalit",
        ),
        sa.Column(
            "ticket_id",
            _uuid_col,
            sa.ForeignKey("ticket.id", ondelete="CASCADE"),
            nullable=False,
            comment="Murojaat FK → ticket",
        ),
        sa.Column(
            "author_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Xabar muallifi FK → app_user",
        ),
        sa.Column(
            "body",
            sa.Text,
            nullable=False,
            comment="Xabar matni",
        ),
        sa.Column(
            "attachment_url",
            sa.String(1024),
            nullable=True,
            comment="Fayl URL (MinIO/S3; NULL = fayl yo'q)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (UTC)",
        ),
    )

    # ── Indekslar ─────────────────────────────────────────────────────────────
    op.create_index(_IDX_MSG_TICKET_ID, _TABLE_MESSAGE, ["ticket_id"])


def downgrade() -> None:
    """
    OGOHLANTIRISH — ticket va ticket_message jadvallari o'chiriladi.

    Postgres guard: agar ticket jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE_TICKET}"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: {_TABLE_TICKET} jadvalida {count} ta qator mavjud. "
                    "Jadvallarni o'chirish murojaat ma'lumotlarini yo'q qiladi. "
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

    # ticket_message indekslari va jadvali
    try:
        op.drop_index(_IDX_MSG_TICKET_ID, table_name=_TABLE_MESSAGE)
    except Exception:
        pass
    op.drop_table(_TABLE_MESSAGE)

    # ticket indekslari
    for idx in [_IDX_STATUS, _IDX_AUTHOR_ID, _IDX_STORE_ID]:
        try:
            op.drop_index(idx, table_name=_TABLE_TICKET)
        except Exception:
            pass

    if not is_postgres:
        try:
            op.drop_index(_UQ_CLIENT_UUID, table_name=_TABLE_TICKET)
        except Exception:
            pass

    op.drop_table(_TABLE_TICKET)
