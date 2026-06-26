"""Marketplace buyurtmaga is_onetime + agent_id qo'shish va buyer_enterprise_id nullable (ADR-003 Bo'lak C).

O'zgarishlar:
  1. marketplace_order.is_onetime — Boolean NOT NULL DEFAULT false.
     Bir martalik (agent bypass) buyurtmani belgilaydi.
  2. marketplace_order.agent_id — nullable FK → app_user.id.
     is_onetime=True bo'lganda shartnomasi yo'q holat uchun agent ID.
  3. marketplace_order.buyer_enterprise_id — NOT NULL → nullable.
     Mustaqil do'kon (enterprise_id=NULL) ham buyurtma bera oladi;
     bunday holda buyurtma egasi buyer_store_id asosida aniqlanadi.

Idempotent: har ustun mavjudligi tekshiriladi.
Zanjir: 0033 → 0034 → 0035 (bitta head).

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        insp = sa.inspect(bind)
        existing_cols = {col["name"] for col in insp.get_columns("marketplace_order")}

        # ── 1. is_onetime ustuni qo'shish (idempotent) ──────────────────────────
        if "is_onetime" not in existing_cols:
            op.execute(
                "ALTER TABLE marketplace_order "
                "ADD COLUMN is_onetime boolean NOT NULL DEFAULT false"
            )

        # ── 2. agent_id ustuni qo'shish (idempotent) ─────────────────────────
        if "agent_id" not in existing_cols:
            op.execute(
                "ALTER TABLE marketplace_order "
                "ADD COLUMN agent_id uuid "
                "REFERENCES app_user(id) ON DELETE SET NULL"
            )

        # ── 3. buyer_enterprise_id NOT NULL → nullable ───────────────────────
        # FK saqlanadi, faqat NOT NULL cheklov olib tashlanadi.
        op.execute(
            "ALTER TABLE marketplace_order "
            "ALTER COLUMN buyer_enterprise_id DROP NOT NULL"
        )
    else:
        # SQLite: test muhiti
        try:
            op.add_column(
                "marketplace_order",
                sa.Column(
                    "is_onetime",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                ),
            )
        except Exception:
            pass

        try:
            op.add_column(
                "marketplace_order",
                sa.Column(
                    "agent_id",
                    sa.Uuid(as_uuid=True),
                    nullable=True,
                ),
            )
        except Exception:
            pass

        # SQLite: buyer_enterprise_id allaqachon nullable=True (model), shuning uchun
        # alohida ALTER TABLE shart emas — create_all model'dan to'g'ri DDL quradi.


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        insp = sa.inspect(bind)
        existing_cols = {col["name"] for col in insp.get_columns("marketplace_order")}

        # ── 3. buyer_enterprise_id nullable → NOT NULL tiklash ───────────────
        # OGOHLANTIRISH: NULL bo'lgan qatorlar mavjud bo'lsa bu amal muvaffaqiyatsiz.
        null_count_result = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM marketplace_order "
                "WHERE buyer_enterprise_id IS NULL"
            )
        )
        null_count = null_count_result.scalar() or 0
        if null_count > 0:
            raise RuntimeError(
                f"downgrade() BLOKLANDI: marketplace_order jadvalida {null_count} ta qator "
                "buyer_enterprise_id=NULL. "
                "NOT NULL ga qaytarish uchun avval bu qatorlarni tozalang."
            )
        op.execute(
            "ALTER TABLE marketplace_order "
            "ALTER COLUMN buyer_enterprise_id SET NOT NULL"
        )

        # ── 2. agent_id ustunini o'chirish ────────────────────────────────────
        if "agent_id" in existing_cols:
            op.execute("ALTER TABLE marketplace_order DROP COLUMN agent_id")

        # ── 1. is_onetime ustunini o'chirish ──────────────────────────────────
        if "is_onetime" in existing_cols:
            op.execute("ALTER TABLE marketplace_order DROP COLUMN is_onetime")
    else:
        try:
            with op.batch_alter_table("marketplace_order") as batch_op:
                batch_op.drop_column("agent_id")
                batch_op.drop_column("is_onetime")
        except Exception:
            pass
