"""Initial schema — B1 jadvallari to'liq DDL.

Jadvallar:
  app_user, store, agent_store,
  category, price_segment, product, product_price, price_history, product_note,
  audit_log, outbox_event

Har jadvalda: id (UUID v7 PK), version, created_at, updated_at, deleted_at
Indekslar: barcode, mxik_code, sku, phone

PII eslatma:
  inn, inps, phone, owner_name — ochiq-matnli saqlanadi (nullable=True).
  To'liq pgcrypto shifrlash + HMAC blind-index → T5 (Mijoz bazasi).
  Bu bosqichda real PII kiritilmaydi.
  ix_store_inn ochiq-matnli indeks olib tashlandi (T5 ga qoldirildi).

Revision ID: 0001
Revises: (boshlang'ich)
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── pgcrypto kengaytmasi (PII shifrlash uchun, T5 da faollashtiriladi) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ================================================================
    # app_user — tizim foydalanuvchisi
    # ================================================================
    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="UUID v7 — vaqt-tartibli birlamchi kalit",
        ),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "phone",
            sa.String(20),
            nullable=False,
            comment="Login telefon raqami — PII (T5 da shifrlash)",
        ),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            comment="administrator | agent | courier | accountant | store",
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "password_hash",
            sa.Text(),
            nullable=False,
            comment="bcrypt hash",
        ),
        sa.Column(
            "biometric_enrolled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Lokal biometrik flag",
        ),
        sa.Column("device_id", sa.String(255), nullable=True),
        sa.Column("locale", sa.String(5), nullable=False, server_default="uz"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("phone", name="uq_app_user_phone"),
    )
    # updated_at ni avtomatik yangilash uchun trigger (PostgreSQL)
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_app_user_updated_at
        BEFORE UPDATE ON app_user
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # Indekslar
    op.create_index("ix_app_user_phone", "app_user", ["phone"])
    op.create_index("ix_app_user_role", "app_user", ["role"])
    op.create_index("ix_app_user_branch_id", "app_user", ["branch_id"])
    # Soft delete uchun qisman indeks — faqat aktiv yozuvlar
    op.create_index(
        "ix_app_user_active",
        "app_user",
        ["is_active"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ================================================================
    # price_segment — narx segmenti
    # ================================================================
    op.create_table(
        "price_segment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", name="uq_price_segment_name"),
    )
    op.execute("""
        CREATE TRIGGER trg_price_segment_updated_at
        BEFORE UPDATE ON price_segment
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ================================================================
    # category — mahsulot kategoriyasi (ierarxik)
    # ================================================================
    op.create_table(
        "category",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name_uz", sa.String(255), nullable=False),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_category_parent_id", "category", ["parent_id"])
    op.execute("""
        CREATE TRIGGER trg_category_updated_at
        BEFORE UPDATE ON category
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ================================================================
    # product — asosiy mahsulot
    # ================================================================
    op.create_table(
        "product",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name_uz", sa.String(500), nullable=False),
        sa.Column("name_ru", sa.String(500), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True, unique=True),
        sa.Column(
            "barcode",
            sa.String(100),
            nullable=True,
            comment="EAN/UPC — shtrix-kod skaner uchun",
        ),
        sa.Column(
            "mxik_code",
            sa.String(50),
            nullable=True,
            comment="MXIK fiskal kod",
        ),
        sa.Column("unit", sa.String(20), nullable=False, server_default="dona"),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("category.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("branch_scope", sa.Text(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Tezkor qidiruv indekslari
    op.create_index(
        "ix_product_barcode",
        "product",
        ["barcode"],
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_index(
        "ix_product_mxik_code",
        "product",
        ["mxik_code"],
        postgresql_where=sa.text("mxik_code IS NOT NULL"),
    )
    op.create_index(
        "ix_product_sku",
        "product",
        ["sku"],
        postgresql_where=sa.text("sku IS NOT NULL"),
    )
    op.create_index("ix_product_category_id", "product", ["category_id"])
    op.create_index(
        "ix_product_active",
        "product",
        ["is_active"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # To'liq matn qidiruvi uchun (T4 da ishlatiladi)
    op.execute("""
        CREATE INDEX ix_product_fts_uz ON product
        USING gin(to_tsvector('simple', coalesce(name_uz, '')));
    """)
    op.execute("""
        CREATE INDEX ix_product_fts_ru ON product
        USING gin(to_tsvector('simple', coalesce(name_ru, '')));
    """)
    op.execute("""
        CREATE TRIGGER trg_product_updated_at
        BEFORE UPDATE ON product
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ================================================================
    # product_price — mahsulot narxi (segment × muddatga bog'liq)
    # ================================================================
    op.create_table(
        "product_price",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_segment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "product_id", "segment_id", "valid_from",
            name="uq_product_price_segment_from",
        ),
    )
    op.create_index("ix_product_price_product_id", "product_price", ["product_id"])
    op.create_index("ix_product_price_segment_id", "product_price", ["segment_id"])
    op.execute("""
        CREATE TRIGGER trg_product_price_updated_at
        BEFORE UPDATE ON product_price
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ================================================================
    # price_history — narx tarixi (APPEND-ONLY)
    # ================================================================
    op.create_table(
        "price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_segment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("new_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_price_history_product_id", "price_history", ["product_id"])
    op.create_index("ix_price_history_changed_at", "price_history", ["changed_at"])

    # ================================================================
    # product_note — mahsulot izohi (faqat yozish)
    # ================================================================
    op.create_table(
        "product_note",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_product_note_product_id", "product_note", ["product_id"])

    # ================================================================
    # store — chakana do'kon / mijoz
    # ================================================================
    op.create_table(
        "store",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "inn",
            sa.String(20),
            nullable=True,
            comment="INN — PII, T5 da pgcrypto bilan shifrlash",
        ),
        sa.Column("inps", sa.String(20), nullable=True, comment="INPS — PII"),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True, comment="Telefon — PII"),
        sa.Column("gps_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("gps_lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_segment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "credit_limit",
            sa.Numeric(18, 2),
            nullable=True,
            comment="Kredit limiti — moliyaviy, primary DB dan o'qing",
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_store_agent_id", "store", ["agent_id"])
    op.create_index("ix_store_branch_id", "store", ["branch_id"])
    op.create_index("ix_store_segment_id", "store", ["segment_id"])
    # ix_store_inn ochiq-matnli indeks qo'shilmadi:
    # PII pgcrypto shifrlash + HMAC blind-index → T5; bu bosqichda real PII kiritilmaydi.
    op.execute("""
        CREATE TRIGGER trg_store_updated_at
        BEFORE UPDATE ON store
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ================================================================
    # agent_store — agent ↔ do'kon ko'p-ko'p
    # ================================================================
    op.create_table(
        "agent_store",
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("store.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("agent_id", "store_id", name="uq_agent_store"),
    )
    op.create_index("ix_agent_store_agent_id", "agent_store", ["agent_id"])
    op.create_index("ix_agent_store_store_id", "agent_store", ["store_id"])

    # ================================================================
    # audit_log — audit yozuvlari (APPEND-ONLY)
    # ================================================================
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column(
            "before_json",
            sa.Text(),
            nullable=True,
            comment="Oldingi holat — PII maskalangan",
        ),
        sa.Column(
            "after_json",
            sa.Text(),
            nullable=True,
            comment="Keyingi holat — PII maskalangan",
        ),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    # action + entity_type birgalikda qidiruv uchun composite indeks
    op.create_index(
        "ix_audit_log_action_entity_type",
        "audit_log",
        ["action", "entity_type"],
    )

    # ================================================================
    # outbox_event — transactional outbox (offline sync uchun)
    # ================================================================
    op.create_table(
        "outbox_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = hali yuborilmagan",
        ),
    )
    # Hali yuborilmagan hodisalarni tezkor olish (background worker uchun)
    op.create_index(
        "ix_outbox_event_unpublished",
        "outbox_event",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_outbox_event_aggregate", "outbox_event", ["aggregate_type", "aggregate_id"])


def downgrade() -> None:
    # Jadvallarni teskari tartibda o'chirish (FK bog'liqliklar hisobga olingan)
    op.drop_table("outbox_event")
    op.drop_table("audit_log")
    op.drop_table("agent_store")

    # Triggerlarni jadval tushirilishidan OLDIN alohida olib tashlash
    op.execute("DROP TRIGGER IF EXISTS trg_store_updated_at ON store")
    op.drop_table("store")

    op.drop_table("product_note")
    op.drop_table("price_history")

    op.execute("DROP TRIGGER IF EXISTS trg_product_price_updated_at ON product_price")
    op.drop_table("product_price")

    op.execute("DROP TRIGGER IF EXISTS trg_product_updated_at ON product")
    op.drop_table("product")

    op.execute("DROP TRIGGER IF EXISTS trg_category_updated_at ON category")
    op.drop_table("category")

    op.execute("DROP TRIGGER IF EXISTS trg_price_segment_updated_at ON price_segment")
    op.drop_table("price_segment")

    op.execute("DROP TRIGGER IF EXISTS trg_app_user_updated_at ON app_user")
    op.drop_table("app_user")

    # Funksiyani eng oxirida o'chirish (CASCADE'siz — triggerlar yuqorida o'chirildi)
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    # Kengaytmalarni olib tashlash (ixtiyoriy — boshqa kengaytmalar ishlatsa xavfli)
    # op.execute("DROP EXTENSION IF EXISTS pgcrypto")
