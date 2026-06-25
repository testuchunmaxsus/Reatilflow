"""store_inventory.source_delivery_id ustunini qo'shish.

NEGA:
  - Kuryer buyurtmani "delivered" deb belgilaganda → o'sha buyurtmaning
    tovarlari do'konning POS inventariga (StoreInventory) avtomatik tushishi kerak.
  - Zanjir: agent buyurtma → kuryer yetkazish → do'kon ombori → POS chakana sotuv.
  - source_delivery_id: qaysi yetkazishdan kelib chiqqanini kuzatish (tracability)
    va idempotentlik tekshiruvi uchun (SELECT 1 WHERE source_delivery_id = ...).
  - source_order_id marketplace_order FK — oddiy Order uchun ishlatib bo'lmaydi,
    shuning uchun alohida ustun zarur.

NIMA:
  - store_inventory jadvaliga `source_delivery_id` (UUID, NULLABLE,
    FK → delivery.id, ondelete=SET NULL) ustunini qo'shadi.
  - `ix_store_inv_source_delivery` indeksini yaratadi.
  - IDEMPOTENT: sa.inspect bilan ustun/indeks borligini tekshiradi (0029 naqshi).
  - PostgreSQL va SQLite uchun mos (PG UUID type, SQLite String(36)).

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COL = "source_delivery_id"
_IDX = "ix_store_inv_source_delivery"
_TABLE = "store_inventory"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    insp = sa.inspect(bind)

    # Ustun qo'shish (agar yo'q bo'lsa)
    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COL,
                uuid_type,
                sa.ForeignKey("delivery.id", ondelete="SET NULL"),
                nullable=True,
                comment="Manba yetkazish FK → delivery (agent buyurtmasi yetkazilganda yaratiladi)",
            ),
        )

    # Indeks yaratish (agar yo'q bo'lsa)
    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _IDX not in indexes:
        op.create_index(_IDX, _TABLE, [_COL])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _IDX in indexes:
        op.drop_index(_IDX, table_name=_TABLE)

    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COL in columns:
        op.drop_column(_TABLE, _COL)
