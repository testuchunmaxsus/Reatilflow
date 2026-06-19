"""store PII ustunlar shifrlash + user_id FK + blind-index ustunlar.

T5 migratsiyasi:
  1. store.inn, inps, owner_name, phone — String→LargeBinary (shifrlangan saqlash).
     Eslatma: bu bosqichda real ochiq-matn ma'lumot yo'q (development/test).
  2. Yangi ustunlar: inn_bi, phone_bi (HMAC blind-index, indekslangan).
     inn_bi uchun partial unique index WHERE deleted_at IS NULL (PostgreSQL).
  3. store.user_id — nullable FK → app_user.id (do'kon egasi, store roli scope).

Dialect yondashuvi:
  - PostgreSQL: partial index WHERE deleted_at IS NULL (inn_bi uchun).
  - SQLite (test): oddiy index, partial WHERE qo'llab-quvvatlanmaydi.
  - Postgres-specific SQL op.execute() bilan is_postgres tekshiruvi orqali o'ralgan.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Indeks nomlari
_IDX_INN_BI = "ix_store_inn_bi"
_IDX_INN_BI_UNIQUE = "uix_store_inn_bi_active"
_IDX_PHONE_BI = "ix_store_phone_bi"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── 0. Postgres: ochiq-matn PII mavjudligi guard ─────────────────────────
    # Agar store jadvalida inn IS NOT NULL qatorlar bo'lsa, ular ochiq-matn matn.
    # Type o'zgartirish (String → BYTEA) ularni buzib, shifrlash imkonini yo'qotadi.
    # Xavfsizlik: bunday holda migratsiya TO'XTATILADI — avval ma'lumotlar
    # application-darajasida shifrlanib, so'ng bu migratsiya ishga tushirilsin.
    if is_postgres:
        result = bind.execute(
            sa.text("SELECT COUNT(*) FROM store WHERE inn IS NOT NULL")
        )
        count = result.scalar()
        if count and count > 0:
            raise RuntimeError(
                f"upgrade() TO'XTATILDI: store jadvalida {count} ta ochiq-matn INN "
                "mavjud (inn IS NOT NULL). "
                "Type String→BYTEA bu qatorlarni buzadi — PII yo'qoladi. "
                "Avval barcha PII maydonlarni ilova darajasida shifrlang, "
                "so'ng bu migratsiyani qayta ishga tushiring."
            )

    # ── 1. PII ustunlarni String → LargeBinary ga o'tkazish ──────────────────
    # Eslatma: real ochiq-matn ma'lumot bo'lmasligi yuqorida tekshirildi.
    # PostgreSQL da USING casting kerak (explicit); SQLite da type shunchaki yangilanadi.

    if is_postgres:
        op.execute("""
            ALTER TABLE store
                ALTER COLUMN inn     TYPE BYTEA USING inn::bytea,
                ALTER COLUMN inps    TYPE BYTEA USING inps::bytea,
                ALTER COLUMN owner_name TYPE BYTEA USING owner_name::bytea,
                ALTER COLUMN phone   TYPE BYTEA USING phone::bytea
        """)
    else:
        # SQLite: ustunlarni qayta yaratish (ALTER COLUMN TYPE yo'q)
        with op.batch_alter_table("store") as batch_op:
            batch_op.alter_column("inn",        type_=sa.LargeBinary(), existing_nullable=True)
            batch_op.alter_column("inps",       type_=sa.LargeBinary(), existing_nullable=True)
            batch_op.alter_column("owner_name", type_=sa.LargeBinary(), existing_nullable=True)
            batch_op.alter_column("phone",      type_=sa.LargeBinary(), existing_nullable=True)

    # ── 2. Blind-index ustunlari qo'shish ────────────────────────────────────
    op.add_column("store", sa.Column("inn_bi",   sa.String(64), nullable=True,
                                    comment="INN HMAC blind-index"))
    op.add_column("store", sa.Column("phone_bi", sa.String(64), nullable=True,
                                    comment="Phone HMAC blind-index"))

    # ── 3. Blind-index indekslar ─────────────────────────────────────────────
    # inn_bi: partial unique (faqat aktiv qatorlar, PostgreSQL)
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {_IDX_INN_BI_UNIQUE}
            ON store (inn_bi)
            WHERE deleted_at IS NULL AND inn_bi IS NOT NULL
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS {_IDX_PHONE_BI}
            ON store (phone_bi)
            WHERE phone_bi IS NOT NULL
        """)
    else:
        # SQLite: oddiy indekslar
        op.create_index(_IDX_INN_BI_UNIQUE, "store", ["inn_bi"], unique=False)
        op.create_index(_IDX_PHONE_BI,      "store", ["phone_bi"], unique=False)

    # ── 4. user_id FK ustuni qo'shish ────────────────────────────────────────
    op.add_column(
        "store",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Do'kon egasi (FK → app_user) — store roli scope (T5)",
        ),
    )

    if is_postgres:
        op.create_index("ix_store_user_id", "store", ["user_id"])
    else:
        op.create_index("ix_store_user_id", "store", ["user_id"])


def downgrade() -> None:
    """
    OGOHLANTIRISH — PII YO'QOLADI:
    downgrade() PII ustunlarni BYTEA → VARCHAR ga qaytaradi (USING NULL).
    Bu shuni bildiradi: barcha shifrlangan inn, inps, owner_name, phone
    qiymatlari NULL ga aylanadi — ma'lumotlar qayta tiklanmaydi.

    Bu downgrade FAQAT ma'lumotlar yo'q (0 qator) bo'lgan DB da xavfsiz.
    Production yoki ma'lumot bo'lgan muhitda DOWNGRADE QILMANG.

    Postgres guard: agar store jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.
    Bu tasodifan PII yo'qotishning oldini oladi.

    Agar downgrade zarur bo'lsa:
      1. Avval barcha PII qiymatlarni backup oling.
      2. Faqat 0 qatorli (to'liq bo'sh) store jadvalida ishga tushiring.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── Postgres: ma'lumot yo'qolishi guard ──────────────────────────────────
    if is_postgres:
        result = bind.execute(sa.text("SELECT COUNT(*) FROM store"))
        count = result.scalar() or 0
        if count > 0:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: store jadvalida {count} ta qator mavjud. "
                "Downgrade qilish barcha shifrlangan inn, inps, owner_name, phone "
                "qiymatlarini yo'q qiladi (PII yo'qolishi). "
                "Agar chindan downgrade zarur bo'lsa: "
                "1) Barcha ma'lumotlarni backup qiling. "
                "2) Faqat bo'sh (0 qatorli) DB da ishga tushiring."
            )

    # ── Teskari tartib ────────────────────────────────────────────────────────

    # 4. user_id FK indeks va ustun
    try:
        op.drop_index("ix_store_user_id", table_name="store")
    except Exception:
        pass
    op.drop_column("store", "user_id")

    # 3. Blind-index indekslar
    if is_postgres:
        op.execute(f"DROP INDEX IF EXISTS {_IDX_PHONE_BI}")
        op.execute(f"DROP INDEX IF EXISTS {_IDX_INN_BI_UNIQUE}")
    else:
        try:
            op.drop_index(_IDX_PHONE_BI, table_name="store")
        except Exception:
            pass
        try:
            op.drop_index(_IDX_INN_BI_UNIQUE, table_name="store")
        except Exception:
            pass

    # 2. Blind-index ustunlar
    op.drop_column("store", "phone_bi")
    op.drop_column("store", "inn_bi")

    # 1. LargeBinary → String qayta o'tkazish
    if is_postgres:
        op.execute("""
            ALTER TABLE store
                ALTER COLUMN inn        TYPE VARCHAR(20)  USING NULL,
                ALTER COLUMN inps       TYPE VARCHAR(20)  USING NULL,
                ALTER COLUMN owner_name TYPE VARCHAR(255) USING NULL,
                ALTER COLUMN phone      TYPE VARCHAR(20)  USING NULL
        """)
    else:
        with op.batch_alter_table("store") as batch_op:
            batch_op.alter_column("inn",        type_=sa.String(20),  existing_nullable=True)
            batch_op.alter_column("inps",       type_=sa.String(20),  existing_nullable=True)
            batch_op.alter_column("owner_name", type_=sa.String(255), existing_nullable=True)
            batch_op.alter_column("phone",      type_=sa.String(20),  existing_nullable=True)
