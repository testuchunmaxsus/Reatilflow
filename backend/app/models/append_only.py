"""
Append-only jadvallar uchun DB-darajali invariant himoya.

SQLAlchemy DDL event listener orqali create_all paytida triggerlar
o'rnatiladi — test DB (aiosqlite) va prod DB (PostgreSQL) ikkisida ham ishlaydi.

Himoya qilinadigan jadvallar:
  ledger_entry  — buxgalteriya yozuvlari (faqat INSERT)
  stock_movement — ombor harakatlari (faqat INSERT)

TEGMA (mutable) jadvallar:
  account_balance — balans keshi (version bilan yangilanadi)
  stock_balance   — ombor qoldig'i (version bilan yangilanadi)

SQLite:
  BEFORE UPDATE/DELETE triggerlar → RAISE(ABORT, ...) — tranzaksiyani to'xtatadi.

PostgreSQL:
  plpgsql funksiya reject_append_only_mutation() + BEFORE UPDATE OR DELETE trigger
  har jadval uchun. CREATE OR REPLACE funksiya — idempotent (takror xavfsiz).

MUHIM: ushbu modul app/models/__init__.py dan import qilinishi shart —
event'lar ro'yxatdan o'tishi uchun import bo'lishi kerak.
"""

from sqlalchemy import DDL, event

from app.models.finance import LedgerEntry
from app.models.stock import StockMovement

# ─── SQLite triggerlar ────────────────────────────────────────────────────────

_SQLITE_TRIGGER_TEMPLATE = """\
CREATE TRIGGER IF NOT EXISTS trg_{tbl}_no_update
    BEFORE UPDATE ON {tbl}
BEGIN
    SELECT RAISE(ABORT, '{tbl} is append-only: UPDATE forbidden');
END;
"""

_SQLITE_TRIGGER_DELETE_TEMPLATE = """\
CREATE TRIGGER IF NOT EXISTS trg_{tbl}_no_delete
    BEFORE DELETE ON {tbl}
BEGIN
    SELECT RAISE(ABORT, '{tbl} is append-only: DELETE forbidden');
END;
"""

# ─── PostgreSQL triggerlar ─────────────────────────────────────────────────────

# Funksiyani birinchi jadval after_create event'ida yaratamiz (CREATE OR REPLACE —
# idempotent, ikkinchi jadval uchun ham zararli emas).
_PG_FUNCTION_DDL = """\
CREATE OR REPLACE FUNCTION reject_append_only_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % forbidden', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

_PG_TRIGGER_TEMPLATE = """\
DROP TRIGGER IF EXISTS trg_{tbl}_append_only ON {tbl};
CREATE TRIGGER trg_{tbl}_append_only
    BEFORE UPDATE OR DELETE ON {tbl}
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
"""

# ─── Jadvallar ro'yxati ────────────────────────────────────────────────────────

_APPEND_ONLY_TABLES = [
    ("ledger_entry",   LedgerEntry.__table__),
    ("stock_movement", StockMovement.__table__),
]


def _register_sqlite_triggers(table, tbl_name: str) -> None:
    """SQLite BEFORE UPDATE/DELETE trigger lari table after_create event'iga ulaydi."""
    update_ddl = DDL(
        _SQLITE_TRIGGER_TEMPLATE.format(tbl=tbl_name)
    ).execute_if(dialect="sqlite")

    delete_ddl = DDL(
        _SQLITE_TRIGGER_DELETE_TEMPLATE.format(tbl=tbl_name)
    ).execute_if(dialect="sqlite")

    event.listen(table, "after_create", update_ddl)
    event.listen(table, "after_create", delete_ddl)


def _register_pg_triggers(table, tbl_name: str, include_function: bool) -> None:
    """PostgreSQL plpgsql trigger larini table after_create event'iga ulaydi."""
    if include_function:
        # plpgsql funksiyani birinchi jadvalda yaratamiz (CREATE OR REPLACE — idempotent).
        func_ddl = DDL(_PG_FUNCTION_DDL).execute_if(dialect="postgresql")
        event.listen(table, "after_create", func_ddl)

    trigger_ddl = DDL(
        _PG_TRIGGER_TEMPLATE.format(tbl=tbl_name)
    ).execute_if(dialect="postgresql")

    event.listen(table, "after_create", trigger_ddl)


# ─── Ro'yxatga olish ──────────────────────────────────────────────────────────

for _idx, (_tbl_name, _table) in enumerate(_APPEND_ONLY_TABLES):
    _include_pg_function = (_idx == 0)   # Faqat birinchi jadvalda funksiya yaratiladi
    _register_sqlite_triggers(_table, _tbl_name)
    _register_pg_triggers(_table, _tbl_name, include_function=_include_pg_function)
