"""app_user.role CHECK constraint'iga 'superadmin' qo'shish (MT1 drift fix).

MUAMMO:
  0002_role_check.py CHECK (role IN administrator/agent/courier/accountant/store)
  yaratdi. MT1 (multi-tenant) da 'superadmin' roli qo'shildi, LEKIN jonli
  PostgreSQL constraint hech qachon yangilanmadi. Natijada superadmin
  foydalanuvchini INSERT qilishda:
    CheckViolationError: violates check constraint "ck_app_user_role_valid"

  Testlar buni ushlamadi: model (app_user) da role uchun SA CheckConstraint
  YO'Q (constraint faqat migratsiyada). SQLite test bazasi modeldan quriladi
  → role CHECK yo'q → superadmin INSERT ishlaydi. Faqat jonli PG'da uchraydi.

YECHIM:
  PostgreSQL'da constraint'ni DROP + qayta ADD (superadmin bilan). Idempotent.
  SQLite'da role CHECK constraint yo'q → skip.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_NAME = "ck_app_user_role_valid"

# MT1 dan keyingi to'liq rol ro'yxati (superadmin bilan)
_VALID_ROLES = (
    "administrator",
    "agent",
    "courier",
    "accountant",
    "store",
    "superadmin",
)
_ROLES_CSV = ", ".join(f"'{r}'" for r in _VALID_ROLES)

# 0002 dagi eski ro'yxat (downgrade uchun)
_OLD_ROLES = ("administrator", "agent", "courier", "accountant", "store")
_OLD_ROLES_CSV = ", ".join(f"'{r}'" for r in _OLD_ROLES)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (test): app_user.role uchun CHECK constraint yo'q — skip.
        return

    # Idempotent: avval eski constraint'ni olib tashlash, keyin yangisini qo'shish.
    op.execute(f"ALTER TABLE app_user DROP CONSTRAINT IF EXISTS {_CHECK_NAME}")
    op.execute(
        f"ALTER TABLE app_user ADD CONSTRAINT {_CHECK_NAME} "
        f"CHECK (role IN ({_ROLES_CSV}))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Eski (superadmin'siz) ro'yxatga qaytarish.
    # DIQQAT: agar superadmin foydalanuvchi mavjud bo'lsa, bu downgrade
    # CheckViolation beradi — avval superadmin'larni o'chirish kerak.
    op.execute(f"ALTER TABLE app_user DROP CONSTRAINT IF EXISTS {_CHECK_NAME}")
    op.execute(
        f"ALTER TABLE app_user ADD CONSTRAINT {_CHECK_NAME} "
        f"CHECK (role IN ({_OLD_ROLES_CSV}))"
    )
