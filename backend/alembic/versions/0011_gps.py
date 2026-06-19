"""GPS trekking jadvali — T17 GPS Ingest.

Jadval:
  gps_point — yuqori chastotali GPS trekking nuqtalari (time-series)
    id           UUID v7 PK
    user_id      UUID NOT NULL (server'dan; klientga ISHONMASLIK)
    delivery_id  UUID NULL (T18 da FK bo'ladi; hozir faqat UUID)
    lat          NUMERIC(11,8) NOT NULL — GPS kenglik
    lng          NUMERIC(12,8) NOT NULL — GPS uzunlik
    recorded_at  TIMESTAMPTZ NOT NULL — QURILMA vaqti (offline yozilgan)
    speed        NUMERIC(8,3) NULL — tezlik m/s
    ingested_at  TIMESTAMPTZ NOT NULL — SERVER qabul qilgan vaqt
    created_at   TIMESTAMPTZ NOT NULL

Indekslar:
  ix_gps_point_user_recorded   — (user_id, recorded_at) — trekking qidiruv
  ix_gps_point_delivery_recorded — (delivery_id, recorded_at) — yetkazish bo'yicha

Idempotentlik:
  uq_gps_point_user_recorded — UNIQUE (user_id, recorded_at)
  → bir qurilma bir vaqtda bir nuqta yozadi; takror ingest e'tiborsiz (ON CONFLICT DO NOTHING)
  ESLATMA: TimescaleDB hypertable bilan UNIQUE constraint partitsiya ustunini o'z ichiga olishi shart.
  recorded_at partitsiya ustuni — (user_id, recorded_at) UNIQUE to'g'ri.

PostgreSQL — TimescaleDB hypertable:
  SELECT create_hypertable('gps_point', 'recorded_at', if_not_exists => TRUE)
  Agar timescaledb extension mavjud bo'lmasa — oddiy jadval (SKIP).

Retention policy (90 kun):
  TODO: add_retention_policy('gps_point', INTERVAL '90 days')
  Bu funksiya timescaledb extension talab qiladi.
  Production da: SELECT add_retention_policy('gps_point', INTERVAL '90 days');
  Alternativa (standart Postgres): pg_cron + DELETE FROM gps_point WHERE recorded_at < NOW() - INTERVAL '90 days'
  Hozir faqat izoh — scheduled job yoki migration kengaytirish kerak.

SQLite (test): oddiy jadval, UUID String(36), UNIQUE indeks.

Dialect-aware: PostgreSQL UUID + TimescaleDB; SQLite oddiy jadval.

downgrade guard (Postgres):
  Agar gps_point jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-17
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import settings

logger = logging.getLogger(__name__)

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks nomlari ──────────────────────────────────────────────────────────

_IDX_USER_RECORDED      = "ix_gps_point_user_recorded"
_IDX_DELIVERY_RECORDED  = "ix_gps_point_delivery_recorded"
_UQ_USER_RECORDED       = "uq_gps_point_user_recorded"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # gps_point jadvali
    # ================================================================
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
            comment="Foydalanuvchi ID — SERVER'dan olinadi (klientga ISHONMASLIK)",
        ),
        sa.Column(
            "delivery_id",
            _uuid_col,
            nullable=True,
            comment="Yetkazish UUID (ixtiyoriy; T18 da FK qo'shiladi — hozir faqat UUID)",
        ),
        sa.Column(
            "lat",
            sa.Numeric(precision=11, scale=8),
            nullable=False,
            comment="GPS kenglik (±90.00000000, 8 kasrga aniqlik)",
        ),
        sa.Column(
            "lng",
            sa.Numeric(precision=12, scale=8),
            nullable=False,
            comment="GPS uzunlik (±180.00000000, 8 kasrga aniqlik)",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=(
                "QURILMA vaqti — offline yozilgan (klientdan keladi). "
                "TimescaleDB hypertable partitsiya ustuni. "
                "ADR §3.7: klient soatiga ishonilmaydi — faqat trekking uchun."
            ),
        ),
        sa.Column(
            "speed",
            sa.Numeric(precision=8, scale=3),
            nullable=True,
            comment="Tezlik m/s (ixtiyoriy — qurilmadan keladi)",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="SERVER qabul qilgan vaqt (UTC, server clock) — ADR §3.7",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (ingested_at bilan teng — server clock)",
        ),
    )

    # ── Indekslar ─────────────────────────────────────────────────────────────
    # (user_id, recorded_at) — trekking qidiruv + idempotentlik
    op.create_index(
        _IDX_USER_RECORDED,
        "gps_point",
        ["user_id", "recorded_at"],
    )

    # (delivery_id, recorded_at) — yetkazish marshrutini ko'rish
    op.create_index(
        _IDX_DELIVERY_RECORDED,
        "gps_point",
        ["delivery_id", "recorded_at"],
    )

    # ── Idempotentlik: UNIQUE (user_id, recorded_at) ──────────────────────────
    # TimescaleDB hypertable bilan UNIQUE faqat partitsiya ustunini o'z ichiga olishi shart.
    # recorded_at partitsiya ustuni — (user_id, recorded_at) UNIQUE to'g'ri.
    # SQLite: oddiy UNIQUE indeks.
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_USER_RECORDED} "
            f"ON gps_point (user_id, recorded_at)"
        ))
    else:
        op.create_index(
            _UQ_USER_RECORDED,
            "gps_point",
            ["user_id", "recorded_at"],
            unique=True,
        )

    # ── TimescaleDB hypertable (faqat PostgreSQL) ─────────────────────────────
    if is_postgres:
        # timescaledb extension mavjudligini tekshiramiz.
        # Mavjud bo'lsa — hypertable + retention policy yaratamiz.
        # Bo'lmasa — oddiy Postgres jadvali bo'lib qoladi; OGOHLANTIRISH chiqariladi.
        try:
            result = bind.execute(sa.text(
                "SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'"
            ))
            ts_count = result.scalar() or 0
            if ts_count > 0:
                bind.execute(sa.text(
                    "SELECT create_hypertable("
                    "  'gps_point', 'recorded_at',"
                    "  if_not_exists => TRUE,"
                    "  migrate_data => TRUE"
                    ")"
                ))
                # Retention policy — settings.gps_retention_days kundan eski ma'lumotlar
                # avtomatik o'chiriladi (TimescaleDB >= 2.x).
                retention_days = settings.gps_retention_days
                bind.execute(sa.text(
                    f"SELECT add_retention_policy("
                    f"  'gps_point',"
                    f"  INTERVAL '{retention_days} days',"
                    f"  if_not_exists => TRUE"
                    f")"
                ))
                logger.info(
                    "TimescaleDB: gps_point hypertable yaratildi, "
                    "retention policy = %d kun.",
                    retention_days,
                )
            else:
                # timescaledb extension topilmadi — oddiy Postgres jadvali saqlanadi.
                # Production da timescaledb SHART — GPS time-series ishlashi uchun.
                # DEPLOY RUNBOOK:
                #   1. TimescaleDB extension o'rnating:
                #      CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
                #   2. Migratsiyani TIMESCALE_URL da ishga tushiring:
                #      TIMESCALE_URL=<ts_url> alembic upgrade 0011
                #   3. Yoki qo'lda:
                #      SELECT create_hypertable('gps_point', 'recorded_at', if_not_exists => TRUE);
                #      SELECT add_retention_policy('gps_point', INTERVAL '90 days', if_not_exists => TRUE);
                logger.warning(
                    "TimescaleDB extension topilmadi — gps_point oddiy jadval bo'lib qoldi. "
                    "PRODUCTION DA timescaledb extension O'RNATILISHI SHART! "
                    "GPS time-series ishlashi va chunk pruning uchun zarur. "
                    "Deploy runbook: CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE; "
                    "keyin ushbu migratsiyani qayta ishga tushiring."
                )
        except Exception as exc:
            # Kutilmagan xato — oddiy jadval sifatida qoladi, lekin jim o'tmaymiz.
            logger.warning(
                "TimescaleDB hypertable/retention yaratishda xato: %r — "
                "gps_point oddiy jadval bo'lib qoldi. "
                "PRODUCTION DA timescaledb extension tekshirilsin!",
                exc,
            )


def downgrade() -> None:
    """
    OGOHLANTIRISH — gps_point jadvali o'chiriladi.

    Postgres guard: agar jadvalda qatorlar bo'lsa — downgrade BLOKLANADI.
    GPS time-series ma'lumotlari qimmatli — o'chirishdan avval zaxira oling.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text("SELECT COUNT(*) FROM gps_point"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: gps_point jadvalida {count} ta qator mavjud. "
                    "Jadval o'chirilishi GPS trekking ma'lumotlarini yo'q qiladi. "
                    "Faqat bo'sh (0 qatorli) DB da ishga tushiring yoki avval ma'lumotlarni eksport qiling."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: COUNT xato — xavfsiz emas ({exc})"
            ) from exc

        # Partial/unique indekslarni olib tashlash
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_USER_RECORDED}"))
        except Exception:
            pass

    # Oddiy indekslar
    try:
        op.drop_index(_IDX_DELIVERY_RECORDED, table_name="gps_point")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_USER_RECORDED, table_name="gps_point")
    except Exception:
        pass
    if not is_postgres:
        try:
            op.drop_index(_UQ_USER_RECORDED, table_name="gps_point")
        except Exception:
            pass

    op.drop_table("gps_point")
