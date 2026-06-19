"""Ombor va Buxgalteriya jadvallari — T9/T10 (APPEND-ONLY event-sourced ledger).

Jadvallar:
  stock_movement   — ombor harakatlari (APPEND-ONLY)
  stock_balance    — harakatlardan derivatsiyalangan qoldiq (kesh)
  ledger_entry     — buxgalteriya yozuvlari (APPEND-ONLY)
  account_balance  — ledger dan derivatsiyalangan balans (kesh)

Indekslar:
  ix_stock_movement_product_warehouse  — product_id + warehouse_id (asosiy qidiruv)
  ix_stock_movement_product_id         — product bo'yicha filtr
  ix_stock_balance_product_warehouse   — UNIQUE (product_id, warehouse_id)
  ix_ledger_entry_store_id             — store bo'yicha filtr
  uq_ledger_entry_client_uuid          — client_uuid UNIQUE (idempotentlik, partial: IS NOT NULL)
  uq_stock_movement_client_uuid        — client_uuid UNIQUE (idempotentlik, partial: IS NOT NULL)

downgrade guard:
  Postgres: agar jadvalda qatorlar bo'lsa — downgrade BLOKLANADI (T5 naqshi).
  Ma'lumot yo'qolishini oldini olish.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── Indeks va constraint nomlari ────────────────────────────────────────────

_IDX_SM_PROD_WH = "ix_stock_movement_product_warehouse"
_IDX_SM_PROD = "ix_stock_movement_product_id"
_IDX_SM_CLIENT_UUID = "uq_stock_movement_client_uuid"

_IDX_SB_PROD_WH = "uq_stock_balance_product_warehouse"

_IDX_LE_STORE = "ix_ledger_entry_store_id"
_IDX_LE_CLIENT_UUID = "uq_ledger_entry_client_uuid"

_IDX_AB_STORE = "uq_account_balance_store_id"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ================================================================
    # stock_movement — APPEND-ONLY ombor harakatlari
    # ================================================================
    op.create_table(
        "stock_movement",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mahsulot FK → product",
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=False,
            comment="Ombor ID",
        ),
        sa.Column(
            "type",
            sa.String(20),
            nullable=False,
            comment="in | out | transfer | adjust",
        ),
        sa.Column(
            "qty",
            sa.Numeric(18, 4),
            nullable=False,
            comment="Miqdor (Decimal, out uchun manfiy bo'lishi mumkin)",
        ),
        sa.Column(
            "ref_type",
            sa.String(100),
            nullable=True,
            comment="Havola turi (ixtiyoriy)",
        ),
        sa.Column(
            "ref_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=True,
            comment="Havola ID (ixtiyoriy)",
        ),
        sa.Column(
            "moved_by",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Kim bajardi (FK → app_user)",
        ),
        sa.Column(
            "moved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Harakat vaqti (UTC)",
        ),
        sa.Column(
            "client_uuid",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=True,
            comment="Klient idempotentlik UUID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (UTC) — APPEND-ONLY",
        ),
    )

    # Indekslar: product+warehouse (asosiy qidiruv), product (filtr)
    op.create_index(
        _IDX_SM_PROD_WH,
        "stock_movement",
        ["product_id", "warehouse_id"],
        unique=False,
    )
    op.create_index(
        _IDX_SM_PROD,
        "stock_movement",
        ["product_id"],
        unique=False,
    )

    # client_uuid UNIQUE partial index — idempotentlik
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX {_IDX_SM_CLIENT_UUID}
            ON stock_movement (client_uuid)
            WHERE client_uuid IS NOT NULL
        """)
    else:
        # SQLite: oddiy unique indeks (partial WHERE qo'llab-quvvatlanmaydi)
        op.create_index(
            _IDX_SM_CLIENT_UUID,
            "stock_movement",
            ["client_uuid"],
            unique=True,
        )

    # ================================================================
    # stock_balance — harakatlardan derivatsiyalangan qoldiq (kesh)
    # ================================================================
    op.create_table(
        "stock_balance",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            primary_key=True,
            comment="UUID v7 — birlamchi kalit",
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mahsulot FK → product",
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=False,
            comment="Ombor ID",
        ),
        sa.Column(
            "qty_on_hand",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
            comment="Qo'ldagi miqdor (Decimal)",
        ),
        sa.Column(
            "qty_reserved",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
            comment="Band qilingan miqdor (Decimal)",
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
            comment="Optimistik lock versiyasi",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Oxirgi yangilangan vaqt (UTC)",
        ),
    )

    # UNIQUE: har (product, warehouse) juftligi uchun bitta qoldiq yozuvi
    op.create_index(
        _IDX_SB_PROD_WH,
        "stock_balance",
        ["product_id", "warehouse_id"],
        unique=True,
    )

    # ================================================================
    # ledger_entry — APPEND-ONLY buxgalteriya yozuvlari
    # ================================================================
    op.create_table(
        "ledger_entry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("store.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Do'kon FK → store",
        ),
        sa.Column(
            "type",
            sa.String(20),
            nullable=False,
            comment="debit | credit",
        ),
        sa.Column(
            "amount",
            sa.Numeric(18, 2),
            nullable=False,
            comment="Miqdor (Decimal, musbat)",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="UZS",
            comment="Valyuta kodi (ISO 4217)",
        ),
        sa.Column(
            "ref_type",
            sa.String(100),
            nullable=True,
            comment="Havola turi (ixtiyoriy)",
        ),
        sa.Column(
            "ref_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=True,
            comment="Havola ID (ixtiyoriy)",
        ),
        sa.Column(
            "entry_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yozuv sanasi (hujjat vaqti, UTC)",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
            comment="Kim yaratdi (FK → app_user)",
        ),
        sa.Column(
            "client_uuid",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            nullable=True,
            comment="Klient idempotentlik UUID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Yaratilgan vaqt (UTC) — APPEND-ONLY",
        ),
    )

    # store_id bo'yicha indeks
    op.create_index(
        _IDX_LE_STORE,
        "ledger_entry",
        ["store_id"],
        unique=False,
    )

    # client_uuid UNIQUE partial index — idempotentlik
    if is_postgres:
        op.execute(f"""
            CREATE UNIQUE INDEX {_IDX_LE_CLIENT_UUID}
            ON ledger_entry (client_uuid)
            WHERE client_uuid IS NOT NULL
        """)
    else:
        op.create_index(
            _IDX_LE_CLIENT_UUID,
            "ledger_entry",
            ["client_uuid"],
            unique=True,
        )

    # ================================================================
    # account_balance — ledger dan derivatsiyalangan balans (kesh)
    # ================================================================
    op.create_table(
        "account_balance",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            primary_key=True,
            comment="UUID v7 — birlamchi kalit",
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("store.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Do'kon FK → store",
        ),
        sa.Column(
            "balance",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
            comment="Joriy balans (>0 = qarz, <0 = ortiqcha kredit)",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="UZS",
            comment="Valyuta kodi (ISO 4217)",
        ),
        sa.Column(
            "last_recalc_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Oxirgi qayta hisoblangan vaqt",
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
            comment="Optimistik lock versiyasi",
        ),
    )

    # UNIQUE: har do'kon uchun bitta balans yozuvi
    op.create_index(
        _IDX_AB_STORE,
        "account_balance",
        ["store_id"],
        unique=True,
    )

    # ================================================================
    # DB-darajali APPEND-ONLY himoya (defence-in-depth)
    # Faqat Postgres; SQLite da o'tkazib yuboriladi (izoh pastda).
    # ================================================================
    if is_postgres:
        # stock_movement: UPDATE va DELETE ni bloklash
        op.execute("""
            CREATE RULE stock_movement_no_update AS
                ON UPDATE TO stock_movement
                DO INSTEAD NOTHING
        """)
        op.execute("""
            CREATE RULE stock_movement_no_delete AS
                ON DELETE TO stock_movement
                DO INSTEAD NOTHING
        """)

        # ledger_entry: UPDATE va DELETE ni bloklash
        op.execute("""
            CREATE RULE ledger_entry_no_update AS
                ON UPDATE TO ledger_entry
                DO INSTEAD NOTHING
        """)
        op.execute("""
            CREATE RULE ledger_entry_no_delete AS
                ON DELETE TO ledger_entry
                DO INSTEAD NOTHING
        """)
    # SQLite: RULE qo'llab-quvvatlanmaydi — test muhitida o'tkazib yuboriladi.
    # Ishlab chiqarish (Postgres) da yuqoridagi RULE lar ishlab turadi.


def downgrade() -> None:
    """
    OGOHLANTIRISH — MOLIYAVIY MA'LUMOTLAR YO'QOLADI.

    downgrade() barcha stock/finance jadvallarini o'chiradi.
    Bu FAQAT ma'lumotlar yo'q (0 qator) bo'lgan DB da xavfsiz.

    Postgres guard: agar jadvallarda qatorlar bo'lsa — downgrade BLOKLANADI.
    Bu tasodifan moliyaviy ma'lumot yo'qotishning oldini oladi (T5 naqshi).
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── Postgres: ma'lumot yo'qolishi guard ──────────────────────────────────
    if is_postgres:
        for table_name in ("stock_movement", "ledger_entry", "account_balance", "stock_balance"):
            try:
                result = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar() or 0
                if count > 0:
                    raise RuntimeError(
                        f"downgrade() BLOKLANDI: {table_name} jadvalida {count} ta qator mavjud. "
                        "Downgrade qilish barcha ombor/buxgalteriya ma'lumotlarini yo'q qiladi. "
                        "Agar chindan downgrade zarur bo'lsa: barcha ma'lumotlarni backup qiling, "
                        "so'ng faqat bo'sh (0 qatorli) DB da ishga tushiring."
                    )
            except Exception as exc:
                if "downgrade() BLOKLANDI" in str(exc):
                    raise
                # Jadval hali mavjud emas — o'tkazib yuborish
                pass

    # ── Postgres: append-only RULE larni o'chirish ──────────────────────────
    if is_postgres:
        op.execute("DROP RULE IF EXISTS stock_movement_no_update ON stock_movement")
        op.execute("DROP RULE IF EXISTS stock_movement_no_delete ON stock_movement")
        op.execute("DROP RULE IF EXISTS ledger_entry_no_update ON ledger_entry")
        op.execute("DROP RULE IF EXISTS ledger_entry_no_delete ON ledger_entry")

    # ── Teskari tartib (indekslar → jadvallar) ───────────────────────────────

    # account_balance
    try:
        op.drop_index(_IDX_AB_STORE, table_name="account_balance")
    except Exception:
        pass
    op.drop_table("account_balance")

    # ledger_entry
    try:
        if is_postgres:
            op.execute(f"DROP INDEX IF EXISTS {_IDX_LE_CLIENT_UUID}")
        else:
            op.drop_index(_IDX_LE_CLIENT_UUID, table_name="ledger_entry")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_LE_STORE, table_name="ledger_entry")
    except Exception:
        pass
    op.drop_table("ledger_entry")

    # stock_balance
    try:
        op.drop_index(_IDX_SB_PROD_WH, table_name="stock_balance")
    except Exception:
        pass
    op.drop_table("stock_balance")

    # stock_movement
    try:
        if is_postgres:
            op.execute(f"DROP INDEX IF EXISTS {_IDX_SM_CLIENT_UUID}")
        else:
            op.drop_index(_IDX_SM_CLIENT_UUID, table_name="stock_movement")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_SM_PROD, table_name="stock_movement")
    except Exception:
        pass
    try:
        op.drop_index(_IDX_SM_PROD_WH, table_name="stock_movement")
    except Exception:
        pass
    op.drop_table("stock_movement")
