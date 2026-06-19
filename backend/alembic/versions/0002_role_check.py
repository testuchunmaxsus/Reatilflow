"""app_user.role ustuniga CHECK constraint qo'shish.

Faqat 5 qonuniy rol qiymatiga ruxsat beradi:
  administrator | agent | courier | accountant | store

Texnik qarz (T2 da yopiladi):
  0001_initial.py da role String(20) — hech qanday constraint yo'q.
  Bu migratsiya eski yozuvlarni tekshiradi va constraint qo'shadi.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

Not: PostgreSQL ENUM o'rniga CHECK ishlatildi — soddaroq va
  migratsiyada reverse-compatible (yangi rol qo'shish uchun faqat
  ALTER TABLE CHECK o'zgartirish kifoya, TYPE RENAME kerak emas).

Kelajak: `role_permission` jadvali (admin boshqaruvi uchun DB seed) —
  T2 doirasida faqat Python matritsa + Redis kesh ishlatiladi.
  Admin UI orqali rol/ruxsat boshqaruvi talab etilganda qo'shiladi.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Qonuniy rol qiymatlari
_VALID_ROLES = ("administrator", "agent", "courier", "accountant", "store")
_CHECK_NAME = "ck_app_user_role_valid"
_ROLES_CSV = ", ".join(f"'{r}'" for r in _VALID_ROLES)


def upgrade() -> None:
    # ─── Proaktiv tekshiruv (faqat PostgreSQL) ─────────────────────────────
    # CHECK qo'shishdan OLDIN noto'g'ri rol qiymatlari borligini aniqlaymiz.
    # Migratsiya o'rta yo'lda yiqilmasin — aniq RuntimeError ko'tariladi.
    # SQLite'da (test muhiti) bu tekshiruv e'tiborsiz qoldiriladi.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        roles_in = ", ".join(f"'{r}'" for r in _VALID_ROLES)
        result = bind.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                f"SELECT COUNT(*) FROM app_user WHERE role NOT IN ({roles_in})"
            )
        )
        invalid_count = result.scalar()
        if invalid_count and invalid_count > 0:
            raise RuntimeError(
                f"Migratsiya to'xtatildi: app_user jadvalida {invalid_count} ta "
                f"noto'g'ri rol qiymati mavjud. "
                f"Avval ularni quyidagi qiymatlarga keltiring: {list(_VALID_ROLES)}"
            )

    # ─── CHECK constraint qo'shish ─────────────────────────────────────────
    op.execute(f"""
        ALTER TABLE app_user
        ADD CONSTRAINT {_CHECK_NAME}
        CHECK (role IN ({_ROLES_CSV}))
    """)


def downgrade() -> None:
    op.execute(f"""
        ALTER TABLE app_user
        DROP CONSTRAINT IF EXISTS {_CHECK_NAME}
    """)
