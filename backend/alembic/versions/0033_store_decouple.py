"""Do'konni korxonadan ajratish — ADR-003 Variant B (Store Decoupling).

O'zgarishlar:
  1. store.enterprise_id — NOT NULL → nullable (platforma do'koni enterprise_id=NULL bo'ladi).
     FK RESTRICT saqlanadi — korxona o'chirilganda bog'langan do'konlar bloklanadi.
  2. store.is_platform_managed — yangi boolean ustun (default false).
     Superadmin tomonidan yaratilgan mustaqil do'kon = true.

Orqaga moslik:
  Mavjud do'konlar (enterprise_id set) o'zgarmaydi — ishlashda davom etadi.
  Yangi NULL enterprise_id faqat platforma do'konlariga tegishli.

Idempotent: sa.inspect() orqali ustun mavjudligi tekshiriladi.

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # ── 1. enterprise_id NOT NULL → nullable ────────────────────────────
        # FK RESTRICT saqlanadi; faqat NOT NULL cheklov olib tashlanadi.
        op.execute(
            "ALTER TABLE store ALTER COLUMN enterprise_id DROP NOT NULL"
        )

        # ── 2. is_platform_managed ustuni qo'shish (idempotent) ─────────────
        insp = sa.inspect(bind)
        existing_cols = {col["name"] for col in insp.get_columns("store")}
        if "is_platform_managed" not in existing_cols:
            op.execute(
                "ALTER TABLE store "
                "ADD COLUMN is_platform_managed boolean NOT NULL DEFAULT false"
            )
    else:
        # SQLite: test muhiti — create_all model'dan jadval quriladi.
        # enterprise_id allaqachon nullable=True (model), shuning uchun
        # faqat is_platform_managed ustunini qo'shamiz.
        try:
            op.add_column(
                "store",
                sa.Column(
                    "is_platform_managed",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                ),
            )
        except Exception:
            # Ustun allaqachon mavjud bo'lsa — idempotent, o'tkazib yuboramiz
            pass


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # ── 1. is_platform_managed ustunini o'chirish ────────────────────────
        insp = sa.inspect(bind)
        existing_cols = {col["name"] for col in insp.get_columns("store")}
        if "is_platform_managed" in existing_cols:
            op.execute("ALTER TABLE store DROP COLUMN is_platform_managed")

        # ── 2. enterprise_id nullable → NOT NULL tiklash ─────────────────────
        # OGOHLANTIRISH: NULL enterprise_id bo'lgan qatorlar mavjud bo'lsa
        # bu amal muvaffaqiyatsiz bo'ladi — NULL qatorlarni avval tozalang.
        null_count_result = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM store "
                "WHERE enterprise_id IS NULL AND deleted_at IS NULL"
            )
        )
        null_count = null_count_result.scalar() or 0
        if null_count > 0:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: store jadvalida {null_count} ta qator "
                "enterprise_id=NULL (faol). "
                "enterprise_id NOT NULL ga qaytarish uchun avval bu qatorlarni "
                "o'chiring yoki enterprise_id belgilang."
            )

        op.execute(
            "ALTER TABLE store "
            "ALTER COLUMN enterprise_id SET NOT NULL"
        )
    else:
        # SQLite: is_platform_managed ustunini o'chirib bo'lmaydi (ALTER TABLE DROP COLUMN
        # SQLite 3.35.0+ dan keyin qo'llab-quvvatlanadi, lekin aiosqlite versiyasiga bog'liq).
        # batch_alter_table orqali xavfsiz olib tashlaymiz.
        try:
            with op.batch_alter_table("store") as batch_op:
                batch_op.drop_column("is_platform_managed")
        except Exception:
            pass
