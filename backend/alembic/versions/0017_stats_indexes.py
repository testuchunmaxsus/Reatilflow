"""Statistika indekslari — T22 SQL agregatsiya hardening.

Statistika moduli Python-tomon agregatsiyadan SQL GROUP BY/agregatga ko'chirildi
(v0.29.0). Yangi GROUP BY/WHERE ustunlari uchun indekslar qo'shiladi — ko'p-filial
masshtabida full-scan o'rniga indeks-scan.

Indekslar:
  ix_ledger_entry_store_date  — ledger_entry (store_id, entry_date)
      finance_stats: store_id IN (...) + entry_date range + GROUP BY store_id,type
  ix_delivery_assigned_at     — delivery (assigned_at)
      delivery_stats: assigned_at bo'yicha vaqt filtri

Eslatma: bu indekslar model __table_args__ ga ham qo'shilgan (finance.py LedgerEntry,
delivery.py Delivery) — test DB (Base.metadata.create_all) avtomatik oladi. Ushbu
migratsiya real PostgreSQL DB paritetini ta'minlaydi.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDX_LEDGER_STORE_DATE = "ix_ledger_entry_store_date"
_IDX_DELIVERY_ASSIGNED = "ix_delivery_assigned_at"


def upgrade() -> None:
    op.create_index(
        _IDX_LEDGER_STORE_DATE,
        "ledger_entry",
        ["store_id", "entry_date"],
    )
    op.create_index(
        _IDX_DELIVERY_ASSIGNED,
        "delivery",
        ["assigned_at"],
    )


def downgrade() -> None:
    op.drop_index(_IDX_DELIVERY_ASSIGNED, table_name="delivery")
    op.drop_index(_IDX_LEDGER_STORE_DATE, table_name="ledger_entry")
