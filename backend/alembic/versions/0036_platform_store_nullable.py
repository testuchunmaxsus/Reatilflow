"""Platforma-do'kon POS/accept: store_inventory/pos_sale/pos_sale_line.enterprise_id NULLABLE.

MUAMMO (jonli bug, ADR-036):
  ADR-003 ko'prik bo'yicha platforma-do'konlar `enterprise_id IS NULL`
  (mustaqil, korxonadan bog'liq emas). Lekin:
    - store_inventory.enterprise_id — 0024 da PG+SQLite RAW DDL bilan
      NOT NULL qilib yaratilgan (model esa allaqachon nullable emas edi —
      ADR-036 bilan model ham shu migratsiyada moslashtiriladi).
    - pos_sale.enterprise_id / pos_sale_line.enterprise_id — 0021 da PG+SQLite
      RAW DDL bilan NOT NULL (ORM model esa nullable=True — model/DB drift).
  Natijada platforma-do'konda (enterprise_id=NULL) marketplace accept_order
  StoreInventory INSERT qilganda, yoki POS create_sale PosSale/PosSaleLine
  INSERT qilganda, jonli PG'da NotNullViolationError → 500.

  Testlar ushlamadi: SQLite test bazasi MODEL'dan `create_all` bilan quriladi
  (model allaqachon nullable=True/model shu PR bilan nullable bo'ladi),
  shuning uchun bug faqat jonli PG'da (raw DDL NOT NULL) chiqadi (0027/0035
  naqshi bilan bir xil sabab).

YECHIM (ADR-036 variant C):
  store_inventory.enterprise_id, pos_sale.enterprise_id,
  pos_sale_line.enterprise_id — DROP NOT NULL. Scope endi store_id ga
  tayanadi (do'konga kirish allaqachon get_store_visibility_filter /
  _check_store_access bilan tekshirilgan — yagona ishonchli tenant chegara).
  Oddiy tenant xatti-harakati o'zgarmaydi (real enterprise_id yozilishi
  davom etadi) — bu faqat CHEKLOVni bo'shatadi, ma'lumot yo'qolmaydi.

PG only (RAW DDL ALTER COLUMN ... DROP NOT NULL). SQLite: no-op — model
allaqachon nullable=True bo'lgani uchun `create_all` constraint qo'ymaydi
(0027 naqshi bilan bir xil).

FK va indekslar SAQLANADI — faqat NOT NULL cheklovi olib tashlanadi.
CONCURRENTLY ISHLATILMAYDI (ALTER COLUMN bilan mos kelmaydi, kerak ham emas).

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (jadval, ustun) — platforma-do'kon uchun enterprise_id NULL bo'lishi mumkin
_NULLABLE_COLUMNS = (
    ("store_inventory", "enterprise_id"),
    ("pos_sale", "enterprise_id"),
    ("pos_sale_line", "enterprise_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: NOT NULL cheklovi yo'q (model nullable=True, create_all)

    insp = sa.inspect(bind)
    for table, column in _NULLABLE_COLUMNS:
        cols = {col["name"]: col for col in insp.get_columns(table)}
        col_info = cols.get(column)
        if col_info is None:
            # Ustun mavjud emas (kutilmagan holat) — o'tkazib yuborish
            continue
        if col_info.get("nullable"):
            # Idempotent: allaqachon nullable
            continue
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, column in _NULLABLE_COLUMNS:
        # DIQQAT: NULL qatorlar mavjud bo'lsa SET NOT NULL xato beradi.
        # Production'da downgrade taqiqlangan — avval NULL qatorlarni
        # tozalash/backfill qilish kerak.
        null_count_result = bind.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL')
        )
        null_count = null_count_result.scalar() or 0
        if null_count > 0:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: {table} jadvalida {null_count} ta qator "
                f"{column}=NULL (platforma-do'kon yozuvlari). NOT NULL ga qaytarish "
                "uchun avval bu qatorlarni tozalang."
            )
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET NOT NULL')
