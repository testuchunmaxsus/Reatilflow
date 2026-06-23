"""Multi-tenant poydevori — MT1 Foundation.

ADR-002 §2.8 bo'yicha:
  1. CREATE TABLE enterprise (id uuid7 PK, name, inn, status, enabled_modules, timestamps).
  2. "Default Korxona" INSERT: fixed UUID 00000000-0000-7000-8000-000000000001.
  3. Har jadvalga enterprise_id ADD (nullable) → backfill → NOT NULL + FK + index.
     app_user enterprise_id NULLABLE qoladi (superadmin uchun NULL).
  4. PostgreSQL: RLS ENABLE + siyosat har jadval.
     SQLite: RLS skip.

XAVFSIZLIK ESLATMALARI:
  - NON-DESTRUCTIVE: mavjud ma'lumot default korxonaga backfill qilinadi.
  - app_user.enterprise_id NULLABLE: superadmin NULL bo'ladi.
  - RLS BYPASSRLS: migratsiya foydalanuvchisi (db admin) BYPASSRLS
    rolida ishlaydi — bu yig'ilgan DDL uchun talab qilinadi.
  - current_setting('app.current_enterprise_id', true): 2-argument TRUE
    → sozlama yo'q bo'lsa NULL qaytaradi (xato bermaydi).
    NULL::uuid != har qanday UUID → superadmin uchun bypass BYPASSRLS rol.

ASYNCPG cheklov:
  Har sa.text() bitta buyruq (ko'p-statement TAQIQ).
  Shu sabab har ALTER, CREATE, UPDATE alohida execute qilinadi.

ZAXIRALANGAN SO'Z (reserved word) cheklov:
  Jadval nomi RAW SQL ga f-string bilan qo'yilganda MAJBURIY qo'shtirnoqlanadi
  (_qi). PostgreSQL'da "order" zaxiralangan so'z — qo'shtirnoqsiz
  `ALTER TABLE order ...` sintaksis xatosi beradi. Double-quote ham PG, ham
  SQLite uchun amal qiladi. (op.create_table avto-quote qiladi, lekin bu yerda
  RAW SQL ishlatiladi — shuning uchun qo'lda quote shart.)

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Konstantalar ─────────────────────────────────────────────────────────────

# Default korxona UUID — jonli ma'lumot backfill uchun (fixed)
_DEFAULT_ENTERPRISE_UUID = "00000000-0000-7000-8000-000000000001"

# Barcha modul kalitlari (ADR-002 §2.2)
_ALL_MODULES_JSON = (
    '["catalog","customers","orders","stock","finance",'
    '"delivery","attendance","gps","contracts","tickets",'
    '"promo","stats","push"]'
)

# Tenant-scoped jadvallar (enterprise_id NOT NULL bo'ladi)
# Tartib: FK bog'lanishlarga ko'ra (parent → child)
_TENANT_TABLES_NOT_NULL = [
    "category",
    "price_segment",
    "product",
    "product_price",
    "price_history",
    "product_note",
    "store",
    "agent_store",
    "order",
    "order_line",
    "order_template",
    "order_template_line",
    "stock_movement",
    "stock_balance",
    "ledger_entry",
    "account_balance",
    "delivery",
    "attendance",
    "contract",
    "ticket",
    "ticket_message",
    "promo",
    "push_log",
    "outbox_event",
    "audit_log",
]

# app_user — NULLABLE (superadmin uchun NULL)
# gps_point — TimescaleDB alohida baza, bu migratsiyada skip

# Barcha tenant jadvallari (app_user ham, lekin nullable)
_ALL_TENANT_TABLES = _TENANT_TABLES_NOT_NULL + ["app_user"]


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _is_sqlite(bind) -> bool:
    return bind.dialect.name == "sqlite"


def _qi(identifier: str) -> str:
    """SQL identifikatorni (jadval nomi) qo'shtirnoq bilan o'raydi.

    PostgreSQL'da "order" kabi zaxiralangan so'zlar ALTER/CREATE/RLS RAW SQL
    da MAJBURIY qo'shtirnoqlanishi kerak — aks holda sintaksis xatosi.
    Double-quote ("...") ham PostgreSQL, ham SQLite uchun amal qiladi.

    FK/index NOMLARI (ix_order_..., fk_order_...) zaxiralangan emas — ular
    quote QILINMAYDI (faqat bare jadval nomi quote qilinadi).
    """
    return '"' + identifier.replace('"', '""') + '"'


# ─── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)
    is_sq = _is_sqlite(bind)

    # ── 1. Enterprise jadvali yaratish ──────────────────────────────────────────
    # Idempotent: CREATE TABLE IF NOT EXISTS ekvivalenti — avval mavjudligini tekshirish.
    # SQLAlchemy op.create_table() xato beradi agar mavjud bo'lsa.
    # Shu sabab tekshirib, keyin yaratamiz.

    if is_pg:
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS enterprise ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  version BIGINT NOT NULL DEFAULT 1,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  deleted_at TIMESTAMPTZ,"
            "  name VARCHAR(255) NOT NULL,"
            "  inn VARCHAR(20),"
            "  status VARCHAR(20) NOT NULL DEFAULT 'active',"
            "  enabled_modules JSON NOT NULL DEFAULT '" + _ALL_MODULES_JSON + "'"
            ")"
        ))
    else:
        # SQLite — BOOLEAN/UUID ekvivalenti
        bind.execute(sa.text(
            "CREATE TABLE IF NOT EXISTS enterprise ("
            "  id TEXT PRIMARY KEY,"
            "  version INTEGER NOT NULL DEFAULT 1,"
            "  created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "  updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "  deleted_at TEXT,"
            "  name TEXT NOT NULL,"
            "  inn TEXT,"
            "  status TEXT NOT NULL DEFAULT 'active',"
            "  enabled_modules TEXT NOT NULL DEFAULT '" + _ALL_MODULES_JSON + "'"
            ")"
        ))

    # ── 2. Default Korxona INSERT ───────────────────────────────────────────────
    # ON CONFLICT DO NOTHING — idempotent.

    if is_pg:
        bind.execute(sa.text(
            "INSERT INTO enterprise (id, name, inn, status, enabled_modules, version) "
            "VALUES "
            "('" + _DEFAULT_ENTERPRISE_UUID + "', "
            "'Default Korxona', NULL, 'active', '" + _ALL_MODULES_JSON + "', 1) "
            "ON CONFLICT (id) DO NOTHING"
        ))
    else:
        # SQLite: INSERT OR IGNORE
        bind.execute(sa.text(
            "INSERT OR IGNORE INTO enterprise (id, name, inn, status, enabled_modules, version) "
            "VALUES "
            "('" + _DEFAULT_ENTERPRISE_UUID + "', "
            "'Default Korxona', NULL, 'active', '" + _ALL_MODULES_JSON + "', 1)"
        ))

    # ── 3. Har jadvallga enterprise_id qo'shish ────────────────────────────────
    # NOT NULL jadvallar:
    for table in _TENANT_TABLES_NOT_NULL:
        _add_enterprise_id_not_null(bind, table, is_pg, is_sq)

    # app_user — NULLABLE (superadmin uchun NULL)
    _add_enterprise_id_nullable(bind, "app_user", is_pg, is_sq)

    # ── 4. PostgreSQL RLS ──────────────────────────────────────────────────────
    if is_pg:
        _setup_rls_postgresql(bind)


def _column_exists(bind, table: str, column: str) -> bool:
    """Ustun mavjudligini tekshiradi (idempotent qo'shish uchun)."""
    if bind.dialect.name == "postgresql":
        result = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ).bindparams(t=table, c=column))
        return result.fetchone() is not None
    else:
        # SQLite: PRAGMA table_info — jadval nomi quote qilinadi ("order" uchun)
        result = bind.execute(sa.text(f"PRAGMA table_info({_qi(table)})"))
        rows = result.fetchall()
        return any(row[1] == column for row in rows)


def _add_enterprise_id_not_null(bind, table: str, is_pg: bool, is_sq: bool) -> None:
    """
    Jadvallga enterprise_id qo'shadi (NOT NULL, backfill, FK, index).

    Bosqichlar:
      1. ADD COLUMN enterprise_id (nullable) — agar mavjud bo'lmasa.
      2. UPDATE SET enterprise_id = default — mavjud qatorlar backfill.
      3. NOT NULL constraint.
      4. FK constraint (PostgreSQL) yoki skip (SQLite — FK constraints).
      5. Index.

    qt — quote qilingan jadval nomi (RAW SQL identifikatori uchun).
    """
    qt = _qi(table)

    if _column_exists(bind, table, "enterprise_id"):
        # Ustun allaqachon bor — faqat FK/index missing bo'lishi mumkin
        # Backfill qilamiz (idempotent — DEFAULT qayta yozilmaydi)
        bind.execute(sa.text(
            f"UPDATE {qt} SET enterprise_id = '{_DEFAULT_ENTERPRISE_UUID}' "
            f"WHERE enterprise_id IS NULL"
        ))
        return

    # 1. ADD COLUMN (nullable)
    if is_pg:
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD COLUMN enterprise_id UUID"
        ))
    else:
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD COLUMN enterprise_id TEXT"
        ))

    # 2. Backfill
    bind.execute(sa.text(
        f"UPDATE {qt} SET enterprise_id = '{_DEFAULT_ENTERPRISE_UUID}'"
    ))

    # 3. NOT NULL
    if is_pg:
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ALTER COLUMN enterprise_id SET NOT NULL"
        ))
    # SQLite'da NOT NULL — ADD COLUMN bilan birga bo'ladi, lekin mavjud ustun uchun
    # alter qilib bo'lmaydi. Backfill etilgan bo'lgani uchun amalda NULL yo'q.

    # 4. FK (PostgreSQL only — SQLite FK support cheklangan)
    if is_pg:
        fk_name = f"fk_{table}_enterprise_id"
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD CONSTRAINT {fk_name} "
            f"FOREIGN KEY (enterprise_id) REFERENCES enterprise(id) "
            f"ON DELETE RESTRICT"
        ))

    # 5. Index
    idx_name = f"ix_{table}_enterprise_id"
    if is_pg:
        bind.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qt} (enterprise_id)"
        ))
    else:
        # SQLite: CREATE INDEX IF NOT EXISTS
        bind.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qt} (enterprise_id)"
        ))


def _add_enterprise_id_nullable(bind, table: str, is_pg: bool, is_sq: bool) -> None:
    """
    app_user uchun enterprise_id NULLABLE qo'shadi.

    Mavjud foydalanuvchilar default korxonaga backfill qilinadi.
    superadmin keyinchalik NULL ga qaytariladi (MT4).

    qt — quote qilingan jadval nomi.
    """
    qt = _qi(table)

    if _column_exists(bind, table, "enterprise_id"):
        # Backfill — NULL bo'lganlarni default'ga
        bind.execute(sa.text(
            f"UPDATE {qt} SET enterprise_id = '{_DEFAULT_ENTERPRISE_UUID}' "
            f"WHERE enterprise_id IS NULL"
        ))
        return

    # 1. ADD COLUMN (nullable)
    if is_pg:
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD COLUMN enterprise_id UUID"
        ))
    else:
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD COLUMN enterprise_id TEXT"
        ))

    # 2. Backfill mavjud foydalanuvchilar
    bind.execute(sa.text(
        f"UPDATE {qt} SET enterprise_id = '{_DEFAULT_ENTERPRISE_UUID}'"
    ))

    # 3. FK (PostgreSQL, NULLABLE — SET NULL on delete)
    if is_pg:
        fk_name = f"fk_{table}_enterprise_id"
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ADD CONSTRAINT {fk_name} "
            f"FOREIGN KEY (enterprise_id) REFERENCES enterprise(id) "
            f"ON DELETE RESTRICT"
        ))

    # 4. Index
    idx_name = f"ix_{table}_enterprise_id"
    if is_pg:
        bind.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qt} (enterprise_id)"
        ))
    else:
        bind.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {qt} (enterprise_id)"
        ))


def _setup_rls_postgresql(bind) -> None:
    """
    PostgreSQL Row-Level Security siyosatlarini o'rnatadi.

    Har jadval uchun:
      1. ALTER TABLE ... ENABLE ROW LEVEL SECURITY
      2. CREATE POLICY tenant_isolation ON <tbl>
         USING (
           enterprise_id = current_setting('app.current_enterprise_id', true)::uuid
           OR current_setting('app.current_enterprise_id', true) = ''
         )

    'true' (2-argument) → sozlama yo'q bo'lsa NULL qaytaradi (xato bermaydi).
    '' (bo'sh string) → superadmin yoki BYPASSRLS rol uchun bypass.

    BYPASSRLS: DB admin/migrator foydalanuvchisi BYPASSRLS rolga ega bo'lishi kerak —
    aks holda migratsiya va seed script ishlamaydi.
    Ilova foydalanuvchisi (app user) oddiy rol — RLS ishlaydi.

    app_user uchun maxsus siyosat: enterprise_id NULL (superadmin) ham ruxsat.

    Jadval nomi quote qilinadi (_qi) — "order" zaxiralangan so'z uchun.
    """
    # Barcha jadvallar uchun RLS
    rls_tables = _TENANT_TABLES_NOT_NULL + ["app_user"]

    for table in rls_tables:
        qt = _qi(table)

        # 1. RLS yoqish
        bind.execute(sa.text(
            f"ALTER TABLE {qt} ENABLE ROW LEVEL SECURITY"
        ))

        # 2. Eski siyosatni o'chirish (idempotent)
        bind.execute(sa.text(
            f"DROP POLICY IF EXISTS tenant_isolation ON {qt}"
        ))

        # 3. Yangi siyosat
        if table == "app_user":
            # superadmin: enterprise_id IS NULL ham ruxsat
            bind.execute(sa.text(
                f"CREATE POLICY tenant_isolation ON {qt} "
                f"USING ("
                f"  enterprise_id IS NULL OR "
                f"  enterprise_id = NULLIF("
                f"    current_setting('app.current_enterprise_id', true), '')"
                f"    ::uuid"
                f")"
            ))
        else:
            bind.execute(sa.text(
                f"CREATE POLICY tenant_isolation ON {qt} "
                f"USING ("
                f"  enterprise_id = NULLIF("
                f"    current_setting('app.current_enterprise_id', true), '')"
                f"    ::uuid"
                f")"
            ))

        # 4. Force RLS (superuser ham RLS'ga bo'ysunadi, BYPASSRLS bundan mustasno)
        # FORCE qilmaymiz — migratsiya/seed uchun BYPASSRLS ishlashi kerak
        # bind.execute(sa.text(f"ALTER TABLE {qt} FORCE ROW LEVEL SECURITY"))


# ─── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """
    Orqaga qaytarish — enterprise_id ustunlarini olib tashlaydi.

    MA'LUMOT YO'QOLISHI OGOHLANTIRISHI:
      enterprise_id ustunlari DROP qilinadi — bu ma'lumot yo'qolishi.
      Faqat dev/staging muhitida ishlatilsin.
      Production'da downgrade taqiqlangan.
    """
    bind = op.get_bind()
    is_pg = _is_postgresql(bind)

    # RLS siyosatlarini bekor qilish (PostgreSQL)
    if is_pg:
        rls_tables = _TENANT_TABLES_NOT_NULL + ["app_user"]
        for table in rls_tables:
            qt = _qi(table)
            bind.execute(sa.text(
                f"DROP POLICY IF EXISTS tenant_isolation ON {qt}"
            ))
            bind.execute(sa.text(
                f"ALTER TABLE {qt} DISABLE ROW LEVEL SECURITY"
            ))

    # enterprise_id ustunlarini olib tashlash
    all_tables = _TENANT_TABLES_NOT_NULL + ["app_user"]
    for table in all_tables:
        if not _column_exists(bind, table, "enterprise_id"):
            continue

        qt = _qi(table)

        # FK constraint olib tashlash (PostgreSQL)
        if is_pg:
            fk_name = f"fk_{table}_enterprise_id"
            bind.execute(sa.text(
                f"ALTER TABLE {qt} DROP CONSTRAINT IF EXISTS {fk_name}"
            ))

        # Index olib tashlash
        idx_name = f"ix_{table}_enterprise_id"
        if is_pg:
            bind.execute(sa.text(
                f"DROP INDEX IF EXISTS {idx_name}"
            ))
        # SQLite'da DROP INDEX alohida
        else:
            bind.execute(sa.text(
                f"DROP INDEX IF EXISTS {idx_name}"
            ))

        # Ustun olib tashlash (SQLite'da ALTER TABLE DROP COLUMN SQLite 3.35+ da bor)
        if is_pg:
            bind.execute(sa.text(
                f"ALTER TABLE {qt} DROP COLUMN IF EXISTS enterprise_id"
            ))
        # SQLite'da DROP COLUMN ishlatmaymiz (eski versiya muammosi)

    # enterprise jadvalini o'chirish
    if is_pg:
        bind.execute(sa.text("DROP TABLE IF EXISTS enterprise CASCADE"))
    else:
        bind.execute(sa.text("DROP TABLE IF EXISTS enterprise"))
