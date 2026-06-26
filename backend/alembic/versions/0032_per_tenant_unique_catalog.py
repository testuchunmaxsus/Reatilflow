"""Katalog unique cheklovlarini TENANT bo'yicha qilish (MT izolyatsiya bug-fix).

MUAMMO: price_segment.name, product.sku, product.barcode GLOBAL unique edi —
ya'ni bir korxonadagi qiymat boshqa korxonada qayta ishlatilmasdi (hatto
o'chirilgan korxonaning qoldiqlari ham bloklardi). Bu multi-tenant izolyatsiya
buzilishi.

YECHIM: global cheklovlarni olib tashlab, har birini (enterprise_id, qiymat)
bo'yicha PARTIAL unique index bilan almashtirish (WHERE deleted_at IS NULL —
soft-delete qilinganlar bloklamaydi).

  - uq_price_segment_name           → uix_segment_ent_name (enterprise_id, name)
  - product_sku_key (column unique) → uix_product_ent_sku (enterprise_id, sku)
  - uix_product_barcode_active      → uix_product_ent_barcode (enterprise_id, barcode)

Mavjud ma'lumot xavfsiz: global unique allaqachon majburlangan edi, demak
per-tenant unique avtomatik bajariladi (index yaratish muvaffaqiyatli bo'ladi).

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # ── 1. Eski GLOBAL cheklovlarni olib tashlash ────────────────────────
        # price_segment.name — 0001 da aniq nomlangan
        op.execute("ALTER TABLE price_segment DROP CONSTRAINT IF EXISTS uq_price_segment_name")
        # product.sku — column unique=True (PG default nom: product_sku_key),
        # lekin nom har xil bo'lishi mumkin → pg_constraint dan topib o'chiramiz
        op.execute("""
            DO $$
            DECLARE c text;
            BEGIN
              SELECT conname INTO c
              FROM pg_constraint
              WHERE conrelid = 'product'::regclass
                AND contype = 'u'
                AND conkey = ARRAY[(
                  SELECT attnum FROM pg_attribute
                  WHERE attrelid = 'product'::regclass AND attname = 'sku'
                )]::smallint[];
              IF c IS NOT NULL THEN
                EXECUTE 'ALTER TABLE product DROP CONSTRAINT ' || quote_ident(c);
              END IF;
            END $$;
        """)
        # product.barcode — 0003 dagi global partial unique index
        op.execute("DROP INDEX IF EXISTS uix_product_barcode_active")

        # ── 2. Yangi PER-TENANT partial unique indekslar ─────────────────────
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_segment_ent_name
            ON price_segment (enterprise_id, name)
            WHERE deleted_at IS NULL
        """)
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_product_ent_sku
            ON product (enterprise_id, sku)
            WHERE deleted_at IS NULL AND sku IS NOT NULL
        """)
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_product_ent_barcode
            ON product (enterprise_id, barcode)
            WHERE deleted_at IS NULL AND barcode IS NOT NULL
        """)
    else:
        # SQLite (test muhiti) — partial WHERE yo'q, oddiy (enterprise_id, col) unique.
        # Eski cheklovlar create_all (model) orqali quriladi; model'da unique=True
        # olib tashlangani uchun sku global unique bo'lmaydi. Faqat yangilarini qo'shamiz.
        for name, table, cols in [
            ("uix_segment_ent_name", "price_segment", ["enterprise_id", "name"]),
            ("uix_product_ent_sku", "product", ["enterprise_id", "sku"]),
            ("uix_product_ent_barcode", "product", ["enterprise_id", "barcode"]),
        ]:
            try:
                op.create_index(name, table, cols, unique=True)
            except Exception:
                pass


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("DROP INDEX IF EXISTS uix_product_ent_barcode")
        op.execute("DROP INDEX IF EXISTS uix_product_ent_sku")
        op.execute("DROP INDEX IF EXISTS uix_segment_ent_name")
        # Eski global cheklovlarni tiklash
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_product_barcode_active
            ON product (barcode)
            WHERE deleted_at IS NULL AND barcode IS NOT NULL
        """)
        op.execute("ALTER TABLE product ADD CONSTRAINT product_sku_key UNIQUE (sku)")
        op.execute("ALTER TABLE price_segment ADD CONSTRAINT uq_price_segment_name UNIQUE (name)")
    else:
        for name, table in [
            ("uix_product_ent_barcode", "product"),
            ("uix_product_ent_sku", "product"),
            ("uix_segment_ent_name", "price_segment"),
        ]:
            try:
                op.drop_index(name, table_name=table)
            except Exception:
                pass
