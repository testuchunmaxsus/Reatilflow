"""GPS gps_point jadvali + TimescaleDB hypertable + retention policy.

TimescaleDB alohida migratsiya — OLTP zanjiridan MUSTAQIL.
TIMESCALE_URL ga qarshi ishga tushiriladi:
  cd backend
  alembic -c alembic_timescale.ini upgrade head

Farq (0011_gps.py dan):
  - Bu migratsiya faqat TIMESCALE_URL ga ulanadi.
  - OLTP zanjirida down_revision yo'q — alohida alembic_version_timescale jadvali.
  - timescaledb extension MAJBURIY — yo'q bo'lsa xato chiqariladi (ogohlantirish emas).
  - gps_point jadvali bu yerda yaratiladi; OLTP da create_all() orqali ham bor
    (testlar uchun — modellar o'zgarmagan).

Revision ID: ts0001
Revises: (hech narsa — alohida zanjir boshi)
Create Date: 2026-06-19
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import settings

logger = logging.getLogger(__name__)

revision: str = "ts0001"
down_revision: Union[str, None] = None   # alohida zanjir — OLTP ga bog'liq emas
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks nomlari ──────────────────────────────────────────────────────────

_IDX_USER_RECORDED     = "ix_gps_point_user_recorded"
_IDX_DELIVERY_RECORDED = "ix_gps_point_delivery_recorded"
_UQ_USER_RECORDED      = "uq_gps_point_user_recorded"


def upgrade() -> None:
    """
    gps_point jadvali, hypertable va retention policy yaratadi.

    TimescaleDB extension mavjud bo'lmasa — migratsiya xato bilan to'xtaydi.
    TIMESCALE_URL ga ulanib ishga tushirish zarur (OLTP URL ga emas).
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ── gps_point jadvali ─────────────────────────────────────────────────────
    # Agar jadval mavjud bo'lsa — o'tkazib yuboriladi (idempotent).
    from sqlalchemy import text as _text

    if is_postgres:
        exists_result = bind.execute(
            _text("SELECT to_regclass('public.gps_point') IS NOT NULL AS ex")
        )
        table_exists = exists_result.scalar()
    else:
        table_exists = False

    if not table_exists:
        op.create_table(
            "gps_point",
            sa.Column(
                "id",
                _uuid_col,
                primary_key=True,
                comment="UUID v7 — vaqt-tartibli birlamchi kalit",
            ),
            sa.Column(
                "user_id",
                _uuid_col,
                nullable=False,
                comment="Foydalanuvchi ID — SERVER dan olinadi (klientga ISHONMASLIK)",
            ),
            sa.Column(
                "delivery_id",
                _uuid_col,
                nullable=True,
                comment="Yetkazish UUID (ixtiyoriy; T18 da FK qo'shiladi)",
            ),
            sa.Column(
                "lat",
                sa.Numeric(precision=11, scale=8),
                nullable=False,
                comment="GPS kenglik",
            ),
            sa.Column(
                "lng",
                sa.Numeric(precision=12, scale=8),
                nullable=False,
                comment="GPS uzunlik",
            ),
            sa.Column(
                "recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                comment="QURILMA vaqti — TimescaleDB hypertable partitsiya ustuni",
            ),
            sa.Column(
                "speed",
                sa.Numeric(precision=8, scale=3),
                nullable=True,
                comment="Tezlik m/s (ixtiyoriy)",
            ),
            sa.Column(
                "ingested_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="SERVER qabul qilgan vaqt (UTC)",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Yaratilgan vaqt",
            ),
        )
        logger.info("gps_point jadvali yaratildi.")
    else:
        logger.info("gps_point jadvali allaqachon mavjud — o'tkazib yuborildi.")

    # ── Indekslar (mavjud bo'lmasa) ───────────────────────────────────────────
    if is_postgres:
        # (user_id, recorded_at) indeks
        bind.execute(_text(
            f"CREATE INDEX IF NOT EXISTS {_IDX_USER_RECORDED} "
            f"ON gps_point (user_id, recorded_at)"
        ))
        # (delivery_id, recorded_at) indeks
        bind.execute(_text(
            f"CREATE INDEX IF NOT EXISTS {_IDX_DELIVERY_RECORDED} "
            f"ON gps_point (delivery_id, recorded_at)"
        ))
        # UNIQUE (user_id, recorded_at) — idempotentlik
        # TimescaleDB hypertable + UNIQUE: partitsiya ustuni (recorded_at) kirishi SHART.
        bind.execute(_text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {_UQ_USER_RECORDED} "
            f"ON gps_point (user_id, recorded_at)"
        ))
        logger.info("Indekslar yaratildi/tekshirildi.")
    else:
        # SQLite (agar kerak bo'lsa)
        op.create_index(_IDX_USER_RECORDED, "gps_point", ["user_id", "recorded_at"])
        op.create_index(_IDX_DELIVERY_RECORDED, "gps_point", ["delivery_id", "recorded_at"])
        op.create_index(_UQ_USER_RECORDED, "gps_point", ["user_id", "recorded_at"], unique=True)

    # ── TimescaleDB hypertable ────────────────────────────────────────────────
    if is_postgres:
        # Extension tekshiruvi — MAJBURIY
        ts_result = bind.execute(_text(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'"
        ))
        ts_count = ts_result.scalar() or 0

        if ts_count == 0:
            raise RuntimeError(
                "TimescaleDB extension topilmadi!\n"
                "TIMESCALE_URL ga ulanib, avval extension o'rnating:\n"
                "  CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;\n"
                "Keyin migratsiyani qayta ishga tushiring:\n"
                "  alembic -c alembic_timescale.ini upgrade head"
            )

        # Hypertable yaratish (mavjud bo'lsa — if_not_exists => TRUE)
        bind.execute(_text(
            "SELECT create_hypertable("
            "  'gps_point', 'recorded_at',"
            "  if_not_exists => TRUE,"
            "  migrate_data => TRUE"
            ")"
        ))
        logger.info("TimescaleDB hypertable yaratildi: gps_point[recorded_at]")

        # Retention policy — settings.gps_retention_days kundan eski ma'lumotlar o'chiriladi
        retention_days = settings.gps_retention_days
        bind.execute(_text(
            f"SELECT add_retention_policy("
            f"  'gps_point',"
            f"  INTERVAL '{retention_days} days',"
            f"  if_not_exists => TRUE"
            f")"
        ))
        logger.info(
            "TimescaleDB retention policy: %d kun (gps_point).", retention_days
        )


def downgrade() -> None:
    """
    OGOHLANTIRISH — gps_point jadvali o'chiriladi.

    Postgres guard: jadvalda qatorlar bo'lsa BLOKLANADI.
    GPS time-series ma'lumotlari qimmatli — avval eksport qiling.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        from sqlalchemy import text as _text
        try:
            result = bind.execute(_text("SELECT COUNT(*) FROM gps_point"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: gps_point da {count} ta qator mavjud. "
                    "GPS ma'lumotlarini avval eksport qiling yoki bo'sh DB da ishlating."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: COUNT xato — xavfsiz emas ({exc})"
            ) from exc

        # Indekslarni tozalash
        try:
            bind.execute(_text(f"DROP INDEX IF EXISTS {_UQ_USER_RECORDED}"))
            bind.execute(_text(f"DROP INDEX IF EXISTS {_IDX_USER_RECORDED}"))
            bind.execute(_text(f"DROP INDEX IF EXISTS {_IDX_DELIVERY_RECORDED}"))
        except Exception:
            pass  # Hypertable bilan birga tushadi
    else:
        try:
            op.drop_index(_IDX_DELIVERY_RECORDED, table_name="gps_point")
            op.drop_index(_IDX_USER_RECORDED, table_name="gps_point")
            op.drop_index(_UQ_USER_RECORDED, table_name="gps_point")
        except Exception:
            pass

    op.drop_table("gps_point")
    logger.info("gps_point jadvali o'chirildi.")
