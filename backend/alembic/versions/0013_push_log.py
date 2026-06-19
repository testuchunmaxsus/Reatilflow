"""push_log jadvali — T19 Push Worker.

Jadval:
  push_log — push bildirishnoma log yozuvi (idempotent dedupe)
    id              UUID v7 PK
    outbox_event_id UUID FK → outbox_event.id (CASCADE)
    user_id         UUID FK → app_user.id (CASCADE)
    device_id       VARCHAR(512) NULL — FCM token yoki APNs device token
    channel         VARCHAR(10) NOT NULL — fcm | apns
    title           VARCHAR(255) NOT NULL
    body            TEXT NOT NULL
    status          VARCHAR(20) NOT NULL DEFAULT 'pending' — pending | sent | failed
    attempts        INTEGER NOT NULL DEFAULT 0
    last_error      TEXT NULL
    created_at      TIMESTAMPTZ NOT NULL
    sent_at         TIMESTAMPTZ NULL

Idempotentlik:
  UNIQUE (outbox_event_id, user_id) — bir hodisa + bir foydalanuvchi = bir push.

DIQQAT:
  outbox.published_at ga TEGMAYDI — sync seq kursori bilan to'qnashmaydi.
  Push o'z holatini push_log.status orqali boshqaradi.

Indekslar:
  ix_push_log_outbox_event_id — event_id bo'yicha tez qidiruv
  ix_push_log_user_id         — user_id bo'yicha tez qidiruv
  ix_push_log_status          — status bo'yicha filtr (pending retry uchun)
  uq_push_log_event_user      — UNIQUE constraint (idempotentlik)

Downgrade guard (Postgres):
  push_log jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-18
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nomlar ───────────────────────────────────────────────────────────────────

_TABLE = "push_log"
_IDX_EVENT_ID  = "ix_push_log_outbox_event_id"
_IDX_USER_ID   = "ix_push_log_user_id"
_IDX_STATUS    = "ix_push_log_status"
_UQ_EVENT_USER = "uq_push_log_event_user"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # push_log jadvali
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
            "outbox_event_id",
            _uuid_col,
            sa.ForeignKey("outbox_event.id", ondelete="CASCADE"),
            nullable=False,
            comment="OutboxEvent FK — qaysi hodisa uchun push",
        ),
        sa.Column(
            "user_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
            comment="AppUser FK — kimga push yuboriladi",
        ),
        # ── Kanal / Token ────────────────────────────────────────────
        sa.Column(
            "device_id",
            sa.String(512),
            nullable=True,
            comment="FCM registration token yoki APNs device token",
        ),
        sa.Column(
            "channel",
            sa.String(10),
            nullable=False,
            server_default="fcm",
            comment="Push kanali: fcm | apns",
        ),
        # ── Matn ────────────────────────────────────────────────────
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            comment="Push bildirishnoma sarlavhasi",
        ),
        sa.Column(
            "body",
            sa.Text,
            nullable=False,
            comment="Push bildirishnoma matni",
        ),
        # ── Holat ───────────────────────────────────────────────────
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="Holat: pending | sent | failed",
        ),
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Yuborish urinishlari soni",
        ),
        sa.Column(
            "last_error",
            sa.Text,
            nullable=True,
            comment="Oxirgi xato xabari (failed holat uchun)",
        ),
        # ── Vaqt damllari ────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (UTC)",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Muvaffaqiyatli yuborilgan vaqt (UTC)",
        ),
    )

    # ── Indekslar ─────────────────────────────────────────────────────────────
    op.create_index(_IDX_EVENT_ID, _TABLE, ["outbox_event_id"])
    op.create_index(_IDX_USER_ID,  _TABLE, ["user_id"])
    op.create_index(_IDX_STATUS,   _TABLE, ["status"])

    # ── Idempotentlik: UNIQUE (outbox_event_id, user_id) ─────────────────────
    # Bir hodisa + bir foydalanuvchi = bir push (duplicate yuborishdan himoya).
    # outbox.published_at ga TEGMAYDI — sync seq kursori bilan to'qnashmaydi.
    op.create_unique_constraint(_UQ_EVENT_USER, _TABLE, ["outbox_event_id", "user_id"])


def downgrade() -> None:
    """
    OGOHLANTIRISH — push_log jadvali o'chiriladi.

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
                    "Jadval o'chirilishi push log ma'lumotlarini yo'q qiladi. "
                    "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: COUNT xato — xavfsiz emas ({exc})"
            ) from exc

    # Indekslar va constraintlarni olib tashlash
    try:
        op.drop_constraint(_UQ_EVENT_USER, _TABLE, type_="unique")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_STATUS, table_name=_TABLE)
    except Exception:
        pass
    try:
        op.drop_index(_IDX_USER_ID, table_name=_TABLE)
    except Exception:
        pass
    try:
        op.drop_index(_IDX_EVENT_ID, table_name=_TABLE)
    except Exception:
        pass

    op.drop_table(_TABLE)
