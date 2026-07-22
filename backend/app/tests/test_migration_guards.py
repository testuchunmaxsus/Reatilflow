"""
Migratsiya dialekt-guard testlari (#46, #47).

#46: 0031_branch_table.py upgrade() — SQLite'da `op.create_foreign_key`
     (ALTER TABLE ADD CONSTRAINT) NotImplementedError beradi. Fix: FK
     bloklarini `if is_postgres:` bilan o'rash.
#47: 0033_store_decouple.py downgrade() — guard so'rovi soft-delete
     (deleted_at IS NOT NULL) qatorlarni sanamasdi, keyingi ALTER COLUMN
     esa BARCHA qatorlarga qo'llanadi. Fix: guard `deleted_at` shartisiz sanaydi.

Ikkala migratsiya ham `alembic.op` ni to'g'ridan-to'g'ri chaqiradi — bu modul
faqat migration paytida mavjud bo'lgani uchun import vaqtida mock qilinadi
(app/tests/test_t6_fixes.py'dagi `_load_migration_0005` bilan bir xil naqsh).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest


def _load_migration(filename: str, module_name: str):
    """Berilgan alembic migratsiya faylini `alembic.op` mock qilib yuklaydi."""
    migration_path = (
        pathlib.Path(__file__).parent.parent.parent / "alembic" / "versions" / filename
    )

    alembic_mock = types.ModuleType("alembic")
    alembic_mock.op = MagicMock()
    original_alembic = sys.modules.get("alembic")
    sys.modules["alembic"] = alembic_mock

    try:
        spec = importlib.util.spec_from_file_location(module_name, migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if original_alembic is not None:
            sys.modules["alembic"] = original_alembic
        elif "alembic" in sys.modules:
            del sys.modules["alembic"]

    return module


# ─── #46: 0031 upgrade() SQLite'da FK yaratmasligi kerak ────────────────────


def test_0031_upgrade_skips_fk_on_sqlite(monkeypatch):
    """
    SQLite dialektida `op.create_foreign_key` UMUMAN chaqirilmasligi kerak
    (NotImplementedError oldini olish) — faqat PostgreSQL'da chaqiriladi.
    """
    module = _load_migration("0031_branch_table.py", "migration_0031")

    fake_bind = MagicMock()
    fake_bind.dialect.name = "sqlite"
    module.op.get_bind.return_value = fake_bind

    fake_insp = MagicMock()
    # branch jadvali hali yo'q — create_table chaqirilishi kerak
    fake_insp.get_table_names.return_value = ["app_user", "store"]
    fake_insp.get_indexes.return_value = []
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_insp)

    module.upgrade()

    module.op.create_foreign_key.assert_not_called()
    module.op.create_table.assert_called_once()


def test_0031_upgrade_creates_fk_on_postgres(monkeypatch):
    """PostgreSQL dialektida FK'lar (app_user, store) yaratilishi kerak."""
    module = _load_migration("0031_branch_table.py", "migration_0031_pg")

    fake_bind = MagicMock()
    fake_bind.dialect.name = "postgresql"
    module.op.get_bind.return_value = fake_bind

    fake_insp = MagicMock()
    fake_insp.get_table_names.return_value = ["app_user", "store", "branch"]
    fake_insp.get_indexes.return_value = [{"name": "ix_branch_enterprise_id"}]
    fake_insp.get_foreign_keys.return_value = []
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_insp)

    module.upgrade()

    assert module.op.create_foreign_key.call_count == 2
    created_names = {c.args[0] for c in module.op.create_foreign_key.call_args_list}
    assert created_names == {module._APP_USER_FK, module._STORE_FK}


# ─── #47: 0033 downgrade() soft-delete qatorlarni ham sanashi kerak ─────────


def test_0033_downgrade_counts_soft_deleted_rows(monkeypatch):
    """
    Guard so'rovi soft-delete (deleted_at IS NOT NULL) qatorlarni ham
    sanashi kerak — aks holda ALTER COLUMN SET NOT NULL o'rtada crash bo'lardi.
    """
    module = _load_migration("0033_store_decouple.py", "migration_0033")

    fake_bind = MagicMock()
    fake_bind.dialect.name = "postgresql"
    module.op.get_bind.return_value = fake_bind

    fake_insp = MagicMock()
    fake_insp.get_columns.return_value = [{"name": "is_platform_managed"}]
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_insp)

    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 3  # 3 ta soft-delete NULL qator
    fake_bind.execute.return_value = scalar_result

    with pytest.raises(RuntimeError, match="3 ta qator"):
        module.downgrade()

    # Guard so'rovida `deleted_at` sharti BO'LMASLIGI kerak
    executed_sql = str(fake_bind.execute.call_args_list[0].args[0])
    assert "deleted_at" not in executed_sql
    assert "enterprise_id IS NULL" in executed_sql

    # ALTER COLUMN SET NOT NULL chaqirilmasligi kerak (guard bloklagan)
    for call in module.op.execute.call_args_list:
        assert "SET NOT NULL" not in str(call.args[0])


def test_0033_downgrade_proceeds_when_no_null_rows(monkeypatch):
    """NULL qator yo'q bo'lsa — ALTER COLUMN SET NOT NULL bajariladi."""
    module = _load_migration("0033_store_decouple.py", "migration_0033_ok")

    fake_bind = MagicMock()
    fake_bind.dialect.name = "postgresql"
    module.op.get_bind.return_value = fake_bind

    fake_insp = MagicMock()
    fake_insp.get_columns.return_value = [{"name": "is_platform_managed"}]
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_insp)

    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 0
    fake_bind.execute.return_value = scalar_result

    module.downgrade()

    assert any(
        "SET NOT NULL" in str(call.args[0]) for call in module.op.execute.call_args_list
    )
