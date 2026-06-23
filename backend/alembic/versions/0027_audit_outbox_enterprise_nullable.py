"""audit_log + outbox_event: enterprise_id NULLABLE (superadmin/tizim hodisalari).

MUAMMO (jonli bug):
  0020 _TENANT_TABLES_NOT_NULL ga audit_log va outbox_event ni ham kiritib,
  enterprise_id NOT NULL qildi. LEKIN model'larda enterprise_id nullable=True
  (MT1 dizayni — AuditLog.actor_id ham "NULL = tizim/cron"). Superadmin
  (enterprise_id=NULL) korxona yaratganda create_user audit_log + outbox_event
  yozadi; ularning enterprise_id'si tenant-context ContextVar'idan keladi = NULL
  (superadminda korxona yo'q) → NotNullViolationError get_db commit'da →
  butun tranzaksiya rollback → korxona UMUMAN saqlanmaydi.

  Klient 201 oladi (BaseHTTPMiddleware status'ni commit'dan oldin yuboradi),
  lekin ma'lumot yo'q — ya'ni "yaratilgan korxona ko'rinmaydi".

  Testlar ushlamadi: SQLite test bazasi MODEL'dan quriladi (nullable=True),
  shuning uchun superadmin yozuvi o'tadi. Faqat jonli PG'da (0020 NOT NULL) buziladi.

YECHIM:
  audit_log.enterprise_id va outbox_event.enterprise_id DROP NOT NULL — DB'ni
  model bilan moslashtirish. Superadmin/tizim hodisalari korxonaga tegishli emas
  → NULL to'g'ri (app_user.enterprise_id kabi). Tenant amallari hamon
  context'dan enterprise_id oladi (non-null) — RLS o'zgarmaydi.

PG only. SQLite no-op (constraint allaqachon yo'q — model nullable=True).

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cross-cutting jadvallar — superadmin/tizim hodisalari uchun enterprise_id NULL bo'lishi mumkin
_NULLABLE_TABLES = ("audit_log", "outbox_event")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: NOT NULL constraint yo'q (model nullable=True)
    for table in _NULLABLE_TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN enterprise_id DROP NOT NULL')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # DIQQAT: NULL qatorlar mavjud bo'lsa SET NOT NULL xato beradi (avval
    # backfill/o'chirish kerak). Production'da downgrade taqiqlangan.
    for table in _NULLABLE_TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN enterprise_id SET NOT NULL')
