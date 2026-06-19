"""app_user.phone va full_name PII shifrlash + phone_bi blind-index.

T6 migratsiyasi:
  1. app_user.phone — String(20) → LargeBinary (shifrlangan saqlash, EncryptedString).
  2. app_user.full_name — String(255) → LargeBinary (shifrlangan saqlash, EncryptedString).
  3. Yangi ustun: phone_bi (HMAC blind-index, UNIQUE, indekslangan).

Mavjud unique constraint phone ustunida bo'lgan — u olib tashlanadi,
chunki phone endi shifrlangan (taqqoslab bo'lmaydi); UNIQUE endi phone_bi da.

Backfill yondashuvi (DATA MIGRATION):
  Tartib:
    a) phone_bi ustuni TEXT sifatida qo'shiladi (nullable).
    b) Mavjud qatorlar batch'da o'qilib: ochiq-matn phone → encrypt_pii() →
       phone shifrlangan bytes, full_name → encrypt_pii() → shifrlangan bytes,
       phone_bi = blind_index(phone) — in-place UPDATE.
    c) Postgres: ustun tipi String → BYTEA ga o'zgartiriladi (USING casting).
    d) 0 qatorli (greenfield) DB da backfill loop hech narsa qilmaydi (no-op).
  SQLite va Postgres ikkalasida ishlaydi (dialect-aware).

  Agar backfill muvaffaqiyatsiz bo'lsa (masalan, kalit xato):
    Migratsiya xato bilan to'xtaydi — tranzaksiya rollback bo'ladi.
    Runbook: PII_ENCRYPTION_KEY va BLIND_INDEX_KEY .env da to'g'ri ekanini
    tekshiring, so'ng migratsiyani qayta ishga tushiring.

Dialect yondashuvi:
  - PostgreSQL: USING casting BYTEA (ALTER COLUMN ... TYPE BYTEA USING encode(...,'escape')::bytea).
  - SQLite (test): batch_alter_table + alter_column type.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Indeks va constraint nomlari
_IDX_PHONE_BI = "ix_app_user_phone_bi"
_UQ_PHONE_BI = "uq_app_user_phone_bi"
_UQ_PHONE_OLD = "uq_app_user_phone"  # eski unique constraint (phone text)

# Batch hajmi — katta jadvallarda xotira tejash uchun
_BATCH_SIZE = 500


def _backfill_user_pii(bind: sa.engine.Connection, is_postgres: bool) -> None:
    """
    Mavjud app_user qatorlarini PII shifrlash bilan to'ldiradi.

    Har bir qator uchun:
      - phone: ochiq-matn → encrypt_pii() → bytes (BYTEA/BLOB)
      - full_name: ochiq-matn → encrypt_pii() → bytes (BYTEA/BLOB)
      - phone_bi: blind_index(phone) → HMAC string

    Batch'da ishlaydi (_BATCH_SIZE qator bir vaqtda).
    0 qatorli DB da hech narsa qilmaydi (no-op).

    Bu funksiya faqat phone ustuni hali TEXT bo'lgan holda chaqirilishi kerak
    (ya'ni tip o'zgartirishdan OLDIN).
    """
    # Import faqat migratsiya vaqtida — ilova konteksti talab qiladi
    from app.core.crypto import blind_index, encrypt_pii

    # Qatorlar sonini tekshirish
    count_result = bind.execute(sa.text("SELECT COUNT(*) FROM app_user"))
    total = count_result.scalar() or 0
    if total == 0:
        # Greenfield DB — backfill kerak emas
        return

    offset = 0
    while True:
        rows = bind.execute(
            sa.text(
                "SELECT id, phone, full_name FROM app_user "
                "ORDER BY id "
                f"LIMIT {_BATCH_SIZE} OFFSET {offset}"
            )
        ).fetchall()
        if not rows:
            break

        for row in rows:
            row_id = row[0]
            raw_phone = row[1]
            raw_full_name = row[2]

            # Allaqachon shifrlangan (bytes) bo'lsa o'tkazib yuborish
            # (masalan, qisman backfill qayta ishga tushirilsa)
            if isinstance(raw_phone, bytes):
                # phone allaqachon shifrlangan — phone_bi ni yangilash
                # Deshifrlash kerak bo'lishi mumkin, lekin bu holda
                # phone_bi ni qayta hisoblash imkoni yo'q (kalit boshqa bo'lishi mumkin).
                # Xavfsiz yo'l: bu qatorni o'tkazib yuborish (phone_bi NULL qoladi).
                continue

            encrypted_phone = encrypt_pii(raw_phone) if raw_phone is not None else None
            encrypted_full_name = encrypt_pii(raw_full_name) if raw_full_name is not None else None
            bi = blind_index(raw_phone) if raw_phone is not None else None

            if is_postgres:
                bind.execute(
                    sa.text(
                        "UPDATE app_user SET "
                        "phone = :enc_phone, "
                        "full_name = :enc_full_name, "
                        "phone_bi = :bi "
                        "WHERE id = :row_id"
                    ),
                    {
                        "enc_phone": encrypted_phone,
                        "enc_full_name": encrypted_full_name,
                        "bi": bi,
                        "row_id": row_id,
                    },
                )
            else:
                # SQLite: binary ni hex string sifatida saqlash (BLOB ustun hali TEXT)
                # Aslida SQLite batch_alter orqali type o'zgaradi, shuning uchun
                # backfill tipdan KEYIN amalga oshiriladi (quyida).
                # Bu tarmoq SQLite uchun erishilmaydi (quyida alohida bajariladi).
                pass

        offset += _BATCH_SIZE


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── 1. Eski unique constraint va indekslarni olib tashlash ───────────────
    # phone ustunida unique=True bo'lgan — shifrlangach mazmuni yo'q.

    if is_postgres:
        # PostgreSQL: unique constraint nomini aniqlab olib tashlash
        op.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_app_user_phone'
                    AND conrelid = 'app_user'::regclass
                ) THEN
                    ALTER TABLE app_user DROP CONSTRAINT uq_app_user_phone;
                END IF;
                -- Agar constraint nomi boshqacha bo'lsa (auto-generated)
                -- ix_app_user_phone indeks ham
                IF EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = 'app_user'
                    AND indexname = 'ix_app_user_phone'
                ) THEN
                    DROP INDEX ix_app_user_phone;
                END IF;
            END;
            $$;
        """)
    else:
        # SQLite: batch_alter_table orqali unique=False ga o'tkazish
        # (SQLite unique constraint-ni bevosita drop qilolmaydi)
        with op.batch_alter_table("app_user", recreate="always") as batch_op:
            batch_op.alter_column("phone", type_=sa.String(20), existing_nullable=False,
                                  unique=False)

    # ── 2. phone_bi blind-index ustuni AVVAL qo'shish (backfill uchun kerak) ─
    # Backfill TEXT ustunlar bilan ishlaydi, shuning uchun phone_bi ni
    # tip o'zgartirishdan OLDIN qo'shamiz.
    op.add_column(
        "app_user",
        sa.Column(
            "phone_bi",
            sa.String(64),
            nullable=True,
            comment="Telefon HMAC blind-index (UNIQUE) — phone bo'yicha aniq-moslik qidiruv",
        ),
    )

    # ── 3. DATA MIGRATION (backfill) ─────────────────────────────────────────
    # Postgres: phone TEXT bo'lgan holatda backfill (encrypt + blind_index).
    # SQLite: tip o'zgartirishdan KEYIN backfill (batch_alter qayta yaratadi).
    if is_postgres:
        _backfill_user_pii(bind, is_postgres=True)

    # ── 4. phone va full_name ustunlarini String → LargeBinary ga o'tkazish ──
    # Postgres: backfill allaqachon bo'ldi, shuning uchun USING casting ishlatamiz.
    # SQLite: batch_alter avval tipni o'zgartiradi; keyin backfill qilamiz.

    if is_postgres:
        op.execute("""
            ALTER TABLE app_user
                ALTER COLUMN phone     TYPE BYTEA USING phone::bytea,
                ALTER COLUMN full_name TYPE BYTEA USING full_name::bytea
        """)
    else:
        with op.batch_alter_table("app_user") as batch_op:
            batch_op.alter_column("phone",     type_=sa.LargeBinary(), existing_nullable=False)
            batch_op.alter_column("full_name", type_=sa.LargeBinary(), existing_nullable=False)

        # SQLite: tip o'zgartirishdan keyin backfill
        # (batch_alter BLOB ustuniga to'g'ridan-to'g'ri yozamiz)
        _backfill_user_pii_sqlite(bind)

    # ── 5. UNIQUE indeks phone_bi uchun ──────────────────────────────────────
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {_UQ_PHONE_BI}
            ON app_user (phone_bi)
            WHERE phone_bi IS NOT NULL
        """)
        op.execute(f"""
            CREATE INDEX IF NOT EXISTS {_IDX_PHONE_BI}
            ON app_user (phone_bi)
        """)
    else:
        # SQLite: oddiy unique indeks
        op.create_index(_UQ_PHONE_BI, "app_user", ["phone_bi"], unique=True)


def _backfill_user_pii_sqlite(bind: sa.engine.Connection) -> None:
    """
    SQLite uchun backfill: BLOB ustunlarga encrypt qilingan qiymatlarni yozish.

    SQLite da batch_alter_table tipni o'zgartirganidan keyin chaqiriladi.
    BLOB ustuniga bytes yozish to'g'ridan-to'g'ri ishlaydi.
    """
    from app.core.crypto import blind_index, encrypt_pii

    count_result = bind.execute(sa.text("SELECT COUNT(*) FROM app_user"))
    total = count_result.scalar() or 0
    if total == 0:
        return

    # SQLite BLOB ustundan ochiq-matn o'qish (agar hali decrypt qilinmagan bo'lsa)
    # Agar allaqachon BLOB bo'lsa — TypeDecorator deshifrlaydi.
    # Bu bosqichda biz raw SQL ishlatamiz — TypeDecorator ishlamaydi.
    # phone_bi NULL bo'lgan qatorlarni topamiz va to'ldiramiz.
    offset = 0
    while True:
        rows = bind.execute(
            sa.text(
                "SELECT id, phone FROM app_user WHERE phone_bi IS NULL "
                f"LIMIT {_BATCH_SIZE} OFFSET {offset}"
            )
        ).fetchall()
        if not rows:
            break

        for row in rows:
            row_id = row[0]
            raw_phone = row[1]
            if raw_phone is None:
                offset += 1
                continue

            # SQLite da bytes yoki str bo'lishi mumkin
            if isinstance(raw_phone, bytes):
                # Allaqachon shifrlangan — decrypt qilib blind_index hisoblash
                from app.core.crypto import decrypt_pii
                plain = decrypt_pii(raw_phone)
                if plain is not None:
                    bi = blind_index(plain)
                    bind.execute(
                        sa.text("UPDATE app_user SET phone_bi = :bi WHERE id = :row_id"),
                        {"bi": bi, "row_id": row_id},
                    )
            else:
                # Hali ochiq-matn (bu holat SQLite testlarda bo'lmasligi kerak)
                bi = blind_index(str(raw_phone))
                enc_phone = encrypt_pii(str(raw_phone))
                bind.execute(
                    sa.text(
                        "UPDATE app_user SET phone_bi = :bi, phone = :enc_phone "
                        "WHERE id = :row_id"
                    ),
                    {"bi": bi, "enc_phone": enc_phone, "row_id": row_id},
                )

        offset += _BATCH_SIZE


def downgrade() -> None:
    """
    OGOHLANTIRISH — PII YO'QOLADI:
    downgrade() phone va full_name ustunlarini BYTEA → VARCHAR ga qaytaradi (USING NULL).
    Bu shuni bildiradi: barcha shifrlangan qiymatlar NULL ga aylanadi.

    Bu downgrade FAQAT ma'lumotlar yo'q (0 qator) bo'lgan DB da xavfsiz.
    Production yoki ma'lumot bo'lgan muhitda DOWNGRADE QILMANG.

    Postgres guard: agar app_user jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.
    Bu tasodifan PII yo'qotishning oldini oladi.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── Postgres: ma'lumot yo'qolishi guard ──────────────────────────────────
    if is_postgres:
        result = bind.execute(sa.text("SELECT COUNT(*) FROM app_user"))
        count = result.scalar() or 0
        if count > 0:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: app_user jadvalida {count} ta qator mavjud. "
                "Downgrade qilish barcha shifrlangan phone va full_name qiymatlarini "
                "yo'q qiladi (PII yo'qolishi). "
                "Agar chindan downgrade zarur bo'lsa: "
                "1) Barcha ma'lumotlarni backup qiling. "
                "2) Faqat bo'sh (0 qatorli) DB da ishga tushiring."
            )

    # ── Teskari tartib ────────────────────────────────────────────────────────

    # 4. phone_bi indekslar
    if is_postgres:
        op.execute(f"DROP INDEX IF EXISTS {_IDX_PHONE_BI}")
        op.execute(f"DROP INDEX IF EXISTS {_UQ_PHONE_BI}")
    else:
        try:
            op.drop_index(_UQ_PHONE_BI, table_name="app_user")
        except Exception:
            pass

    # 3. phone_bi ustuni
    op.drop_column("app_user", "phone_bi")

    # 2. LargeBinary → String qayta o'tkazish (OGOHLANTIRISH: ma'lumot yo'qoladi)
    if is_postgres:
        op.execute("""
            ALTER TABLE app_user
                ALTER COLUMN phone     TYPE VARCHAR(20)  USING NULL,
                ALTER COLUMN full_name TYPE VARCHAR(255) USING NULL
        """)
    else:
        with op.batch_alter_table("app_user") as batch_op:
            batch_op.alter_column("phone",     type_=sa.String(20),  existing_nullable=False)
            batch_op.alter_column("full_name", type_=sa.String(255), existing_nullable=False)

    # 1. Eski unique constraint qaytarish (phone ustuniga)
    if is_postgres:
        op.create_unique_constraint(_UQ_PHONE_OLD, "app_user", ["phone"])
    else:
        with op.batch_alter_table("app_user") as batch_op:
            batch_op.alter_column("phone", type_=sa.String(20), existing_nullable=False,
                                  unique=True)
