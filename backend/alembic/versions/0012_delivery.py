"""Yetkazib berish jadvali — T18 Delivery.

Jadval:
  delivery — yetkazish yozuvi (holat mashinasi)
    id              UUID v7 PK
    order_id        UUID FK → order.id (RESTRICT)
    courier_id      UUID FK → app_user.id (RESTRICT)
    status          VARCHAR(20): assigned | started | delivering | delivered | failed
    assigned_at     TIMESTAMPTZ NOT NULL
    started_at      TIMESTAMPTZ NULL — started holatida to'ldiriladi
    start_gps_lat   NUMERIC(11,8) NULL — started holatida GPS
    start_gps_lng   NUMERIC(12,8) NULL — started holatida GPS
    delivered_at    TIMESTAMPTZ NULL — delivered holatida to'ldiriladi
    delivery_gps_lat NUMERIC(11,8) NULL — delivered holatida GPS
    delivery_gps_lng NUMERIC(12,8) NULL — delivered holatida GPS
    proof_photo_url VARCHAR(1024) NULL — yetkazish dalili rasmi (MinIO)
    failure_reason  TEXT NULL — failed holati sababi
    branch_id       UUID NULL
    client_uuid     UUID NULL (idempotentlik: UNIQUE partial IS NOT NULL)
    version         BIGINT (optimistik lock)
    created_at      TIMESTAMPTZ
    updated_at      TIMESTAMPTZ
    deleted_at      TIMESTAMPTZ NULL (soft delete)

MUHIM: delivery_track (GPS) — ALOHIDA TimescaleDB baza.
  Cross-DB FK YO'Q — GpsPoint.delivery_id faqat UUID, FK siz.
  Shu migratsiyada faqat OLTP FK: order, app_user.

Indekslar:
  ix_delivery_order_id   — order_id bo'yicha qidiruv
  ix_delivery_courier_id — courier_id bo'yicha qidiruv
  ix_delivery_status     — status bo'yicha filtr

Idempotentlik:
  PostgreSQL: UNIQUE partial index (client_uuid WHERE client_uuid IS NOT NULL)
  SQLite: oddiy UNIQUE constraint

downgrade guard (Postgres):
  delivery jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-18
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks/constraint nomlari ────────────────────────────────────────────────

_IDX_ORDER_ID        = "ix_delivery_order_id"
_IDX_COURIER_ID      = "ix_delivery_courier_id"
_IDX_STATUS          = "ix_delivery_status"
_UQ_CLIENT_UUID      = "uq_delivery_client_uuid"
_UQ_CLIENT_UUID_PART = "uq_delivery_client_uuid_partial"  # PostgreSQL partial
# Bir buyurtmaga bitta aktiv yetkazish (operatsion yaxlitlik)
# Postgres: partial unique index — DB darajali ikkinchi himoya qatlami (race guard).
# SQLite: partial unique qo'llab-quvvatlanmaydi — servis tekshiruvi yetarli (izoh).
_UQ_ORDER_ACTIVE_PART = "uq_delivery_order_id_active_partial"  # PostgreSQL partial only


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # delivery jadvali
    # ================================================================
    op.create_table(
        "delivery",
        # ── PK ──────────────────────────────────────────────────────
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        # ── FK ──────────────────────────────────────────────────────
        sa.Column(
            "order_id",
            _uuid_col,
            sa.ForeignKey("order.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Buyurtma FK → order (OLTP)",
        ),
        sa.Column(
            "courier_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Kuryer FK → app_user (OLTP)",
        ),
        # ── Holat ───────────────────────────────────────────────────
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="assigned",
            comment="Holat: assigned | started | delivering | delivered | failed",
        ),
        # ── Vaqt ────────────────────────────────────────────────────
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Tayinlangan vaqt (UTC)",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Yo'lga chiqqan vaqt (UTC) — started holatida",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Yetkazilgan vaqt (UTC) — delivered holatida",
        ),
        # ── GPS key nuqtalar ─────────────────────────────────────────
        # To'liq trek: GpsPoint(delivery_id=...) — alohida TimescaleDB, FK yo'q
        sa.Column(
            "start_gps_lat",
            sa.Numeric(precision=11, scale=8),
            nullable=True,
            comment="Boshlash GPS kenglik (started holatida)",
        ),
        sa.Column(
            "start_gps_lng",
            sa.Numeric(precision=12, scale=8),
            nullable=True,
            comment="Boshlash GPS uzunlik (started holatida)",
        ),
        sa.Column(
            "delivery_gps_lat",
            sa.Numeric(precision=11, scale=8),
            nullable=True,
            comment="Yetkazish GPS kenglik (delivered holatida)",
        ),
        sa.Column(
            "delivery_gps_lng",
            sa.Numeric(precision=12, scale=8),
            nullable=True,
            comment="Yetkazish GPS uzunlik (delivered holatida)",
        ),
        # ── Dalil rasm ───────────────────────────────────────────────
        sa.Column(
            "proof_photo_url",
            sa.String(1024),
            nullable=True,
            comment="Yetkazish dalil rasmi URL (MinIO/S3)",
        ),
        # ── Muvaffaqiyatsizlik ───────────────────────────────────────
        sa.Column(
            "failure_reason",
            sa.Text,
            nullable=True,
            comment="Muvaffaqiyatsizlik sababi (failed holati uchun)",
        ),
        # ── Qo'shimcha ───────────────────────────────────────────────
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
            comment="Klient idempotentlik UUID (UNIQUE partial IS NOT NULL)",
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
    op.create_index(_IDX_ORDER_ID, "delivery", ["order_id"])
    op.create_index(_IDX_COURIER_ID, "delivery", ["courier_id"])
    op.create_index(_IDX_STATUS, "delivery", ["status"])

    # ── Idempotentlik: client_uuid UNIQUE (IS NOT NULL) ───────────────────────
    # PostgreSQL: partial unique index (client_uuid WHERE client_uuid IS NOT NULL)
    # SQLite: oddiy UNIQUE index (NULL qatorlar alohida hisoblanadi — SHA'T bor)
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_CLIENT_UUID_PART} "
            f"ON delivery (client_uuid) WHERE client_uuid IS NOT NULL"
        ))
    else:
        # SQLite: unique constraint — SQLite NULL != NULL, shuning uchun partial ni simulatsiya qiladi
        op.create_index(
            _UQ_CLIENT_UUID,
            "delivery",
            ["client_uuid"],
            unique=True,
        )

    # ── Operatsion yaxlitlik: bir buyurtmaga bitta aktiv yetkazish ────────────
    # Aktiv yetkazish = status NOT IN ('delivered', 'failed') AND deleted_at IS NULL.
    # PostgreSQL: partial unique index — DB darajali ikkinchi himoya qatlami (race guard).
    #   Race window: agar ikki parallel so'rov servis tekshiruvini bir vaqtda o'tib ketsа,
    #   Postgres ushbu indeks orqali IntegrityError ko'taradi → servis graceful 409 qaytaradi.
    # SQLite (test muhiti): partial unique WHERE qo'llab-quvvatlanmaydi.
    #   Servis darajasidagi tekshiruv (3c qadami) yetarli — test seriyali ishlaydi.
    if is_postgres:
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_ORDER_ACTIVE_PART} "
            f"ON delivery (order_id) "
            f"WHERE status NOT IN ('delivered', 'failed') AND deleted_at IS NULL"
        ))


def downgrade() -> None:
    """
    OGOHLANTIRISH — delivery jadvali o'chiriladi.

    Postgres guard: agar jadvalda qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text("SELECT COUNT(*) FROM delivery"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: delivery jadvalida {count} ta qator mavjud. "
                    "Jadval o'chirilishi yetkazish ma'lumotlarini yo'q qiladi. "
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
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_ORDER_ACTIVE_PART}"))
        except Exception:
            pass
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_CLIENT_UUID_PART}"))
        except Exception:
            pass

    # Oddiy indekslar
    try:
        op.drop_index(_IDX_STATUS, table_name="delivery")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_COURIER_ID, table_name="delivery")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_ORDER_ID, table_name="delivery")
    except Exception:
        pass

    if not is_postgres:
        try:
            op.drop_index(_UQ_CLIENT_UUID, table_name="delivery")
        except Exception:
            pass

    op.drop_table("delivery")
