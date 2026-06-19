"""Davomat jadvali — T16 Attendance.

Jadval:
  attendance — foydalanuvchi davomat yozuvi
    id               UUID v7 PK
    user_id          UUID FK → app_user (NOT NULL)
    work_date        DATE (NOT NULL) — ish kuni
    check_in_at      TIMESTAMPTZ (NOT NULL) — server vaqti
    check_in_gps_lat NUMERIC(10,7) (NOT NULL)
    check_in_gps_lng NUMERIC(10,7) (NOT NULL)
    check_out_at     TIMESTAMPTZ (NULL — ochiq davomat)
    check_out_gps_lat NUMERIC(10,7) (NULL)
    check_out_gps_lng NUMERIC(10,7) (NULL)
    biometric_verified BOOLEAN NOT NULL DEFAULT false
    source           VARCHAR(30) NOT NULL
    client_uuid      UUID (NULL) — idempotentlik
    version          BIGINT NOT NULL DEFAULT 1
    created_at       TIMESTAMPTZ NOT NULL
    updated_at       TIMESTAMPTZ NOT NULL
    deleted_at       TIMESTAMPTZ NULL

Indekslar:
  ix_attendance_user_id     — user_id bo'yicha qidiruv
  ix_attendance_work_date   — work_date bo'yicha filtr
  ix_attendance_client_uuid — client_uuid bo'yicha qidiruv

Partial unique indekslar (PostgreSQL):
  uq_attendance_user_date_open — (user_id, work_date) WHERE deleted_at IS NULL
    → bir foydalanuvchi bir kun uchun bitta ochiq davomat.
  uq_attendance_client_uuid    — client_uuid WHERE client_uuid IS NOT NULL
    → idempotentlik kafolati.

downgrade guard (Postgres):
  Agar attendance jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.

Dialect-aware: PostgreSQL UUID + partial unique; SQLite String(36) + oddiy index.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks nomlari ──────────────────────────────────────────────────────────

_IDX_USER_ID      = "ix_attendance_user_id"
_IDX_WORK_DATE    = "ix_attendance_work_date"
_IDX_CLIENT_UUID  = "ix_attendance_client_uuid"
_UQ_USER_DATE     = "uq_attendance_user_date_open"
_UQ_CLIENT_UUID   = "uq_attendance_client_uuid"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    _uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    # ================================================================
    # attendance jadvali
    # ================================================================
    op.create_table(
        "attendance",
        sa.Column(
            "id",
            _uuid_col,
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        sa.Column(
            "user_id",
            _uuid_col,
            sa.ForeignKey("app_user.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Foydalanuvchi FK → app_user",
        ),
        sa.Column(
            "work_date",
            sa.Date(),
            nullable=False,
            comment="Ish kuni (UTC server vaqtidan olinadi)",
        ),
        sa.Column(
            "check_in_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Kirish vaqti — SERVER vaqti (klient vaqtiga ISHONMASLIK)",
        ),
        sa.Column(
            "check_in_gps_lat",
            sa.Numeric(precision=10, scale=7),
            nullable=False,
            comment="Kirish GPS kenglik (±90.0000000)",
        ),
        sa.Column(
            "check_in_gps_lng",
            sa.Numeric(precision=10, scale=7),
            nullable=False,
            comment="Kirish GPS uzunlik (±180.0000000)",
        ),
        sa.Column(
            "check_out_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Chiqish vaqti — SERVER vaqti (NULL = hali chiqmagan)",
        ),
        sa.Column(
            "check_out_gps_lat",
            sa.Numeric(precision=10, scale=7),
            nullable=True,
            comment="Chiqish GPS kenglik (NULL = hali chiqmagan)",
        ),
        sa.Column(
            "check_out_gps_lng",
            sa.Numeric(precision=10, scale=7),
            nullable=True,
            comment="Chiqish GPS uzunlik (NULL = hali chiqmagan)",
        ),
        sa.Column(
            "biometric_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment=(
                "Qurilma biometriyasi muvaffaqiyatli o'tganmi (lokal verifikatsiya bayrog'i). "
                "YUZNI serverga HECH QACHON YUBORMA — faqat boolean flag."
            ),
        ),
        sa.Column(
            "source",
            sa.String(30),
            nullable=False,
            comment="Biometriya turi: 'device_faceid' | 'device_fingerprint'",
        ),
        sa.Column(
            "client_uuid",
            _uuid_col,
            nullable=True,
            comment="Klient idempotentlik UUID (ixtiyoriy; partial unique WHERE IS NOT NULL)",
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
            comment="Optimistik lock + LWW uchun versiya raqami",
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
            comment="Soft delete vaqti (NULL = aktiv yozuv)",
        ),
    )

    # ── Oddiy indekslar ───────────────────────────────────────────────────────
    op.create_index(_IDX_USER_ID, "attendance", ["user_id"])
    op.create_index(_IDX_WORK_DATE, "attendance", ["work_date"])
    op.create_index(_IDX_CLIENT_UUID, "attendance", ["client_uuid"])

    # ── Partial unique indekslar (faqat PostgreSQL) ───────────────────────────
    if is_postgres:
        # (user_id, work_date) WHERE deleted_at IS NULL
        # → bir foydalanuvchi bir kun uchun bitta ochiq davomat
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_USER_DATE} "
            f"ON attendance (user_id, work_date) "
            f"WHERE deleted_at IS NULL"
        ))

        # client_uuid WHERE client_uuid IS NOT NULL
        # → idempotentlik kafolati
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {_UQ_CLIENT_UUID} "
            f"ON attendance (client_uuid) "
            f"WHERE client_uuid IS NOT NULL"
        ))


def downgrade() -> None:
    """
    OGOHLANTIRISH — attendance jadvali o'chiriladi.

    Postgres guard: agar jadvalda qatorlar bo'lsa — downgrade BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text("SELECT COUNT(*) FROM attendance"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: attendance jadvalida {count} ta qator mavjud. "
                    "Jadval o'chirilishi davomatlar ma'lumotlarini yo'q qiladi. "
                    "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: COUNT xato — xavfsiz emas ({exc})"
            ) from exc

        # Partial unique indekslarni olib tashlash
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_USER_DATE}"))
        except Exception:
            pass
        try:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {_UQ_CLIENT_UUID}"))
        except Exception:
            pass

    # Oddiy indekslar
    try:
        op.drop_index(_IDX_CLIENT_UUID, table_name="attendance")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_WORK_DATE, table_name="attendance")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_USER_ID, table_name="attendance")
    except Exception:
        pass

    op.drop_table("attendance")
