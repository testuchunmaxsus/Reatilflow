"""Outbox seq ustuni — monoton kursor (T13 Sync API oldinshartı).

Jarayon:
  OutboxEvent jadvaliga `seq` (Postgres: DB SEQUENCE + BIGINT; SQLite: BIGINT) ustuni
  va indeks qo'shiladi.
  Bu global monoton ketma-ketlik — delta sync kursori = oxirgi ko'rilgan seq.
  created_at/wall-clock kursori O'RNIGA ishlatiladi (klient soatiga ishonmaslik — ADR §3.5).

Xavfsiz migratsiya (Postgres):
  1. CREATE SEQUENCE outbox_event_seq (agar mavjud bo'lmasa).
  2. ADD COLUMN seq BIGINT NULL DEFAULT nextval('outbox_event_seq').
     (ADD COLUMN BIGSERIAL NOT NULL to'g'ridan-to'g'ri EMAS — mavjud qatorlarda lock/backfill xavfi).
  3. Backfill: mavjud qatorlar nextval() bilan to'ldiriladi (UPDATE ... WHERE seq IS NULL).
  4. SET NOT NULL — backfill tugagach.
  5. UNIQUE index qo'shiladi.
  Greenfield (bo'sh jadval) uchun ham to'g'ri ishlaydi.

Downgrade guard (Postgres):
  Agar outbox_event jadvalida qatorlar bo'lsa — downgrade BLOKLANADI.
  downgrade: UNIQUE index → DROP COLUMN → DROP SEQUENCE.

Dialect-aware:
  - PostgreSQL: CREATE SEQUENCE + BIGINT NULL DEFAULT nextval + backfill + SET NOT NULL + index.
  - SQLite: faqat BIGINT NULL ustun + unique index (ORM default orqali seq boshqariladi).

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nomlar ──────────────────────────────────────────────────────────────────

_SEQ_NAME = "outbox_event_seq"
_IDX_SEQ = "ix_outbox_event_seq"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        # ── 1. CREATE SEQUENCE (agar mavjud bo'lmasa) ──────────────────────
        # IF NOT EXISTS: greenfield va qayta ishlatishda xavfsiz.
        bind.execute(sa.text(
            f"CREATE SEQUENCE IF NOT EXISTS {_SEQ_NAME}"
        ))

        # ── 2. ADD COLUMN seq BIGINT NULL DEFAULT nextval(seq) ─────────────
        # BIGSERIAL NOT NULL to'g'ridan-to'g'ri EMAS:
        #   - BIGSERIAL = BIGINT + SEQUENCE + NOT NULL — mavjud qatorlarda backfill bo'lmaydi.
        #   - Avval NULL qabul qilib, backfill qilib, keyin NOT NULL qilamiz.
        # ADD COLUMN ... DEFAULT nextval() — Postgres 11+ da faqat metadata lock oladi
        # (table rewrite yo'q), mavjud qatorlar NULL bo'lib qoladi.
        bind.execute(sa.text(
            f"ALTER TABLE outbox_event "
            f"ADD COLUMN IF NOT EXISTS seq BIGINT NULL "
            f"DEFAULT nextval('{_SEQ_NAME}')"
        ))

        # ── 3. Backfill: mavjud NULL qatorlarga nextval() berish ───────────
        # Har qatorga alohida nextval() — monoton ketma-ketlik saqlanadi.
        # Greenfield'da (bo'sh jadval) bu UPDATE 0 ta qatorga ta'sir qiladi.
        bind.execute(sa.text(
            f"UPDATE outbox_event SET seq = nextval('{_SEQ_NAME}') WHERE seq IS NULL"
        ))

        # ── 4. SET NOT NULL — backfill tugagach ────────────────────────────
        bind.execute(sa.text(
            "ALTER TABLE outbox_event ALTER COLUMN seq SET NOT NULL"
        ))

        # ── 5. UNIQUE index ─────────────────────────────────────────────────
        # seq ustuni unique bo'lishi kerak (kursor izchilligi uchun).
        op.create_index(_IDX_SEQ, "outbox_event", ["seq"], unique=True)

    else:
        # SQLite (test muhiti):
        # AUTOINCREMENT faqat INTEGER PRIMARY KEY'da ishlaydi SQLite'da.
        # seq ORM default (_next_seq) orqali boshqariladi testlarda.
        # Nullable — mavjud qatorlar uchun (greenfield testlarda muammo yo'q).
        op.add_column(
            "outbox_event",
            sa.Column(
                "seq",
                sa.BigInteger(),
                nullable=True,
                comment="Monoton kursor (SQLite: ORM counter; Postgres: DB SEQUENCE)",
            ),
        )
        # SQLite'da unique index alohida qo'shiladi
        op.create_index(_IDX_SEQ, "outbox_event", ["seq"], unique=True)


def downgrade() -> None:
    """
    OGOHLANTIRISH — seq ustuni, indeks va sequence olib tashlanadi.

    Postgres guard: agar outbox_event jadvalida qatorlar bo'lsa — BLOKLANADI.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        try:
            result = bind.execute(sa.text("SELECT COUNT(*) FROM outbox_event"))
            count = result.scalar() or 0
            if count > 0:
                raise RuntimeError(
                    f"downgrade() BLOKLANDI: outbox_event jadvalida {count} ta qator mavjud. "
                    "seq ustunini olib tashlash mavjud sync kursor ma'lumotlarini buzadi. "
                    "Faqat bo'sh (0 qatorli) DB da ishga tushiring."
                )
        except Exception as exc:
            if "downgrade() BLOKLANDI" in str(exc):
                raise

    # Indeksni olib tashlash
    try:
        op.drop_index(_IDX_SEQ, table_name="outbox_event")
    except Exception:
        pass

    # Ustunni olib tashlash
    op.drop_column("outbox_event", "seq")

    # Postgres: SEQUENCE ni olib tashlash
    if is_postgres:
        try:
            bind.execute(sa.text(f"DROP SEQUENCE IF EXISTS {_SEQ_NAME}"))
        except Exception:
            pass
