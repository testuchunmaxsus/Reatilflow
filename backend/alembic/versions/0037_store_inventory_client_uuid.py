"""store_inventory.client_uuid ustunini qo'shish (#16 — import idempotentlik DB-backstop).

MUAMMO (ADR #16):
  import_data.service._confirm_store_inventory faqat Redis SETNX + in-batch
  set'ga tayanardi — StoreInventory modelida client_uuid ustuni/unikallik
  cheklovi UMUMAN YO'Q edi. Redis kaliti flush/commit'dan OLDIN qo'yilgani
  uchun Redis muvaffaqiyatli, keyin commit yiqilgan holatda dublikat 24 soat
  "skipped" bo'lib qolar edi (ma'lumot yo'qolishi).

YECHIM:
  store_inventory jadvaliga `client_uuid` (UUID, NULLABLE) ustuni qo'shiladi +
  UNIQUE partial index (IS NOT NULL) — delivery.py (0012) naqshi bilan bir xil.
  Endi DB unikalligi asosiy backstop, Redis faqat tez-yo'l optimizatsiyasi.

  PostgreSQL: partial unique index (client_uuid WHERE client_uuid IS NOT NULL).
  SQLite: oddiy UNIQUE index (NULL != NULL qoidasi partial'ga ekvivalent;
  model create_all bilan avtomatik quriladi — bu migratsiya faqat PG uchun
  amaliy ta'sir qiladi, SQLite testlarda model orqali allaqachon mavjud).

IDEMPOTENT: sa.inspect bilan ustun/indeks borligini tekshiradi (0029/0030 naqshi).

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "store_inventory"
_COL = "client_uuid"
_UQ_PARTIAL = "uq_store_inv_client_uuid_partial"  # PostgreSQL partial
_UQ_PLAIN = "uq_store_inv_client_uuid"  # SQLite / ORM Index nomi


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    insp = sa.inspect(bind)

    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COL,
                uuid_type,
                nullable=True,
                comment=(
                    "Klient/import idempotentlik UUID — UNIQUE partial index "
                    "(IS NOT NULL)."
                ),
            ),
        )

    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}

    if is_postgres:
        if _UQ_PARTIAL not in indexes:
            op.execute(sa.text(
                f"CREATE UNIQUE INDEX {_UQ_PARTIAL} "
                f"ON {_TABLE} ({_COL}) WHERE {_COL} IS NOT NULL"
            ))
    else:
        if _UQ_PLAIN not in indexes:
            op.create_index(_UQ_PLAIN, _TABLE, [_COL], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    insp = sa.inspect(bind)

    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}
    if is_postgres:
        if _UQ_PARTIAL in indexes:
            op.execute(sa.text(f"DROP INDEX {_UQ_PARTIAL}"))
    else:
        if _UQ_PLAIN in indexes:
            op.drop_index(_UQ_PLAIN, table_name=_TABLE)

    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL in columns:
        op.drop_column(_TABLE, _COL)
