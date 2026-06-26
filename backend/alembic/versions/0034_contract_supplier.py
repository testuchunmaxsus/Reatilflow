"""Shartnomaga supplier_enterprise_id qo'shish — Shartnoma-Gate (ADR-003 Bo'lak C).

O'zgarishlar:
  1. contract.supplier_enterprise_id — yangi nullable FK → enterprise.id.
     Shartnoma endi "do'kon ↔ supplier korxona" munosabatini ifodalaydi.
     Mavjud enterprise_id ustuni saqlanadi (legacy/buyer-holder MT1).
  2. ix_contract_supplier_enterprise_id — indeks tez so'rovlar uchun.

Idempotent: ustun va indeks mavjud bo'lsa o'tkazib yuboriladi.

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        insp = sa.inspect(bind)
        existing_cols = {col["name"] for col in insp.get_columns("contract")}

        # ── 1. supplier_enterprise_id ustunini qo'shish (idempotent) ───────────
        if "supplier_enterprise_id" not in existing_cols:
            op.execute(
                "ALTER TABLE contract "
                "ADD COLUMN supplier_enterprise_id uuid "
                "REFERENCES enterprise(id) ON DELETE RESTRICT"
            )

        # ── 2. Indeks qo'shish (idempotent) ─────────────────────────────────────
        existing_indexes = {idx["name"] for idx in insp.get_indexes("contract")}
        if "ix_contract_supplier_enterprise_id" not in existing_indexes:
            # DIQQAT: CONCURRENTLY ISHLATMA — alembic tranzaksiyasi ichida ishlamaydi
            # (PG xato: "CREATE INDEX CONCURRENTLY cannot run inside a transaction block").
            # Contract jadvali kichik → oddiy CREATE INDEX yetarli (tranzaksiya-xavfsiz).
            op.execute(
                "CREATE INDEX IF NOT EXISTS "
                "ix_contract_supplier_enterprise_id "
                "ON contract(supplier_enterprise_id)"
            )
    else:
        # SQLite: test muhiti — add_column orqali
        try:
            op.add_column(
                "contract",
                sa.Column(
                    "supplier_enterprise_id",
                    sa.Uuid(as_uuid=True),
                    nullable=True,
                ),
            )
        except Exception:
            # Ustun allaqachon mavjud — idempotent
            pass


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        insp = sa.inspect(bind)

        # ── Indeksni o'chirish ────────────────────────────────────────────────
        existing_indexes = {idx["name"] for idx in insp.get_indexes("contract")}
        if "ix_contract_supplier_enterprise_id" in existing_indexes:
            op.execute(
                "DROP INDEX IF EXISTS ix_contract_supplier_enterprise_id"
            )

        # ── Ustunni o'chirish ─────────────────────────────────────────────────
        existing_cols = {col["name"] for col in insp.get_columns("contract")}
        if "supplier_enterprise_id" in existing_cols:
            op.execute(
                "ALTER TABLE contract DROP COLUMN supplier_enterprise_id"
            )
    else:
        # SQLite: batch_alter_table orqali xavfsiz olib tashlash
        try:
            with op.batch_alter_table("contract") as batch_op:
                batch_op.drop_column("supplier_enterprise_id")
        except Exception:
            pass
