"""ledger_approval jadvali — finance ledger tasdiqlash (APPEND-ONLY, event-sourcing).

MUAMMO/SABAB:
  ledger_entry APPEND-ONLY (0018 trigger). Shu sabab tasdiqlash holatini
  to'g'ridan-to'g'ri UPDATE qilib bo'lmaydi. LedgerApproval modeli (models/finance.py)
  alohida jadval sifatida qo'shildi — har tasdiqlash mustaqil APPEND yozuvi.
  Testlar SQLite create_all bilan jadvalni avtomatik yaratadi; jonli Postgres
  uchun bu migratsiya ZARUR (aks holda POST /finance/ledger/{id}/approve 500 beradi).

Jadval:
  ledger_approval (id PK, entry_id UNIQUE FK→ledger_entry, approved_by FK→app_user,
                   approved_at, enterprise_id FK→enterprise NULLABLE)
  - entry_id UNIQUE: bitta ledger_entry — bitta tasdiqlash (qayta urinish → 409/DB conflict).
  - enterprise_id NULLABLE (MT1 — model bilan mos; superadmin/tizim holati uchun ham xavfsiz).

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()

    if _is_pg(bind):
        # Bitta CREATE TABLE (inline FK/UNIQUE) — asyncpg uchun bitta statement.
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS ledger_approval ("
            "  id UUID PRIMARY KEY,"
            "  entry_id UUID NOT NULL UNIQUE REFERENCES ledger_entry(id) ON DELETE RESTRICT,"
            "  approved_by UUID NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,"
            "  approved_at TIMESTAMPTZ NOT NULL,"
            "  enterprise_id UUID REFERENCES enterprise(id) ON DELETE RESTRICT"
            ")"
        ))
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ledger_approval_enterprise_id "
            "ON ledger_approval (enterprise_id)"
        ))
    else:
        # SQLite (dev/seed migratsiya yo'li — testlar create_all ishlatadi)
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS ledger_approval ("
            "  id TEXT PRIMARY KEY,"
            "  entry_id TEXT NOT NULL UNIQUE REFERENCES ledger_entry(id) ON DELETE RESTRICT,"
            "  approved_by TEXT NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,"
            "  approved_at TEXT NOT NULL,"
            "  enterprise_id TEXT REFERENCES enterprise(id) ON DELETE RESTRICT"
            ")"
        ))
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ledger_approval_enterprise_id "
            "ON ledger_approval (enterprise_id)"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    if _is_pg(bind):
        bind.execute(sa.text("DROP TABLE IF EXISTS ledger_approval CASCADE"))
    else:
        bind.execute(sa.text("DROP TABLE IF EXISTS ledger_approval"))
