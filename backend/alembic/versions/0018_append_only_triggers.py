"""Append-only triggerlar — moliyaviy invariant DB darajasida.

ledger_entry va stock_movement jadvallariga UPDATE/DELETE ni DB darajasida
BLOKLOVCHI triggerlar qo'shiladi. Ilova kodi xato qilsa ham yoki to'g'ridan-to'g'ri
SQL bajarilsa ham moliyaviy yaxlitlik saqlanadi (defence-in-depth).

Migration 0006 da PostgreSQL RULE lar mavjud edi (DO INSTEAD NOTHING — jim yutar edi).
Bu migratsiya ularni o'chirib, XATO QAYTARADIGAN triggerlar bilan almashtiradi:
  - PostgreSQL: plpgsql RAISE EXCEPTION — tranzaksiyani butunlay bekor qiladi
  - SQLite: RAISE(ABORT, ...) — test muhitida ham bloklanadi

Mutable jadvallar (account_balance, stock_balance) — TEGMA.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Nom konstantalari ─────────────────────────────────────────────────────────

_APPEND_ONLY_TABLES = ("ledger_entry", "stock_movement")

# PostgreSQL: eski RULE nomlar (0006 dan — o'chiriladi)
_OLD_PG_RULES = [
    ("stock_movement_no_update", "stock_movement"),
    ("stock_movement_no_delete", "stock_movement"),
    ("ledger_entry_no_update",   "ledger_entry"),
    ("ledger_entry_no_delete",   "ledger_entry"),
]

# ─── PostgreSQL DDL ────────────────────────────────────────────────────────────

_PG_FUNCTION = """\
CREATE OR REPLACE FUNCTION reject_append_only_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % forbidden', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

# DIQQAT: asyncpg bitta prepared statement'da bir nechta buyruqni qabul qilmaydi
# ("cannot insert multiple commands into a prepared statement"). Shu sabab DROP va
# CREATE ALOHIDA bajariladi (upgrade ichida ketma-ket).
_PG_TRIGGER_CREATE = """\
CREATE TRIGGER trg_{tbl}_append_only
    BEFORE UPDATE OR DELETE ON {tbl}
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
"""

_PG_TRIGGER_DROP = """\
DROP TRIGGER IF EXISTS trg_{tbl}_append_only ON {tbl};
"""

# ─── SQLite DDL ───────────────────────────────────────────────────────────────

_SQLITE_TRIGGER_UPDATE = """\
CREATE TRIGGER IF NOT EXISTS trg_{tbl}_no_update
    BEFORE UPDATE ON {tbl}
BEGIN
    SELECT RAISE(ABORT, '{tbl} is append-only: UPDATE forbidden');
END;
"""

_SQLITE_TRIGGER_DELETE = """\
CREATE TRIGGER IF NOT EXISTS trg_{tbl}_no_delete
    BEFORE DELETE ON {tbl}
BEGIN
    SELECT RAISE(ABORT, '{tbl} is append-only: DELETE forbidden');
END;
"""

_SQLITE_TRIGGER_UPDATE_DROP = "DROP TRIGGER IF EXISTS trg_{tbl}_no_update;"
_SQLITE_TRIGGER_DELETE_DROP = "DROP TRIGGER IF EXISTS trg_{tbl}_no_delete;"


# ─── upgrade ──────────────────────────────────────────────────────────────────


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # 1. Eski RULE larni o'chirish (0006 dan — jim yutar edi, endi trigger ishlatamiz).
        for rule_name, table_name in _OLD_PG_RULES:
            try:
                bind.execute(sa.text(
                    f"DROP RULE IF EXISTS {rule_name} ON {table_name}"
                ))
            except Exception:
                pass   # RULE mavjud bo'lmasa — o'tkazib yuborish

        # 2. plpgsql funksiya (CREATE OR REPLACE — idempotent).
        bind.execute(sa.text(_PG_FUNCTION))

        # 3. Har jadval uchun BEFORE UPDATE OR DELETE trigger.
        #    DROP va CREATE alohida — asyncpg multi-command prepared statement'ni rad etadi.
        for tbl in _APPEND_ONLY_TABLES:
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{tbl}_append_only ON {tbl}"))
            bind.execute(sa.text(_PG_TRIGGER_CREATE.format(tbl=tbl)))

    elif dialect == "sqlite":
        # SQLite: BEFORE UPDATE/DELETE triggerlar.
        for tbl in _APPEND_ONLY_TABLES:
            bind.execute(sa.text(_SQLITE_TRIGGER_UPDATE.format(tbl=tbl)))
            bind.execute(sa.text(_SQLITE_TRIGGER_DELETE.format(tbl=tbl)))


# ─── downgrade ────────────────────────────────────────────────────────────────


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # 1. Triggerlarni o'chirish.
        for tbl in _APPEND_ONLY_TABLES:
            try:
                bind.execute(sa.text(_PG_TRIGGER_DROP.format(tbl=tbl)))
            except Exception:
                pass

        # 2. plpgsql funksiyani o'chirish (boshqa trigger ishlatmasa).
        try:
            bind.execute(sa.text(
                "DROP FUNCTION IF EXISTS reject_append_only_mutation() CASCADE"
            ))
        except Exception:
            pass

        # 3. Eski RULE larni tiklash (0006 ga qaytish — ixtiyoriy, lekin paritet uchun).
        #    DO INSTEAD NOTHING — jim yutar, lekin kamida himoya mavjud bo'ladi.
        for rule_sql in (
            "CREATE RULE stock_movement_no_update AS ON UPDATE TO stock_movement DO INSTEAD NOTHING",
            "CREATE RULE stock_movement_no_delete AS ON DELETE TO stock_movement DO INSTEAD NOTHING",
            "CREATE RULE ledger_entry_no_update AS ON UPDATE TO ledger_entry DO INSTEAD NOTHING",
            "CREATE RULE ledger_entry_no_delete AS ON DELETE TO ledger_entry DO INSTEAD NOTHING",
        ):
            try:
                bind.execute(sa.text(rule_sql))
            except Exception:
                pass

    elif dialect == "sqlite":
        # SQLite triggerlarni o'chirish.
        for tbl in _APPEND_ONLY_TABLES:
            try:
                bind.execute(sa.text(_SQLITE_TRIGGER_UPDATE_DROP.format(tbl=tbl)))
                bind.execute(sa.text(_SQLITE_TRIGGER_DELETE_DROP.format(tbl=tbl)))
            except Exception:
                pass
