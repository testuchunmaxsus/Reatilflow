"""gps_point.enterprise_id ustunini qo'shish (asosiy OLTP baza).

NEGA:
  - 0011 `gps_point`'ni enterprise_id'SIZ yaratgan (MT1'dan oldin).
  - 0020 (multitenancy) gps_point'ni SKIP qilgan ("TimescaleDB alohida baza" deb).
  - Ammo PROD'da alohida TimescaleDB YO'Q — gps_point asosiy OLTP bazada
    (settings.timescale_url endi DATABASE_URL'ga fallback qiladi).
  - `GpsPoint` modeli `enterprise_id` (nullable, indexed) ustuniga ega va GPS ingest
    uni yozadi → ustun bo'lmasa `UndefinedColumnError` → 500.
  Bu drift (model'da bor, migratsiyada yo'q) SQLite testlarda yashiringan edi
  (test sxemasi modeldan create_all bilan quriladi).

NIMA:
  - gps_point'ga `enterprise_id` (UUID, NULLABLE — TimescaleDB'da cross-DB FK yo'q)
    ustunini qo'shadi + `ix_gps_point_enterprise_id` indeksini yaratadi.
  - Idempotent: ustun/indeks allaqachon bo'lsa (create_all yoki qayta yurgizish) — skip.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDX = "ix_gps_point_enterprise_id"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    insp = sa.inspect(bind)
    columns = {c["name"] for c in insp.get_columns("gps_point")}
    if "enterprise_id" not in columns:
        op.add_column(
            "gps_point",
            sa.Column("enterprise_id", uuid_type, nullable=True),
        )

    indexes = {i["name"] for i in insp.get_indexes("gps_point")}
    if _IDX not in indexes:
        op.create_index(_IDX, "gps_point", ["enterprise_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    indexes = {i["name"] for i in insp.get_indexes("gps_point")}
    if _IDX in indexes:
        op.drop_index(_IDX, table_name="gps_point")

    columns = {c["name"] for c in insp.get_columns("gps_point")}
    if "enterprise_id" in columns:
        op.drop_column("gps_point", "enterprise_id")
