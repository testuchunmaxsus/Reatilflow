"""Modul default drift tuzatish + platforma-do'kon marketplace idempotentligi.

BATCH 4A — #26, #27.

#26 [correctness] modul default drift:
  0020 migratsiyasi va model default'i orasidagi tafovut — 0020 DB DEFAULT
  va "Default Korxona" satri 13 modulda qotib qolgan, ORM model
  (app/models/enterprise.py) va superadmin EnterpriseCreate default'i esa
  ALL_MODULE_KEYS = 18 modul. 0020 O'ZI TAHRIRLANMAYDI (prod'da bajarilgan,
  additive-only siyosat). Bu migratsiya:
    1. PostgreSQL: enterprise.enabled_modules DEFAULT'ini 18-modulga o'rnatadi
       (kelajakdagi backfill/legacy tenant uchun).
    2. Faqat 0020 legacy-13 IMZOSIGA AYNAN TENG (jsonb-tenglik — bo'sh joy
       formatlash farqidan mustaqil) satrlarni 18-modulga yangilaydi.
       ATAYLAB "union-add" EMAS: API orqali ongli ravishda kamaytirilgan
       modul-subsetlar (imzosi legacy-13'dan farq qiladi) TEGILMAYDI.
  Idempotent: qayta ishga tushirilganda mos qatordagi enabled_modules
  allaqachon 18-modul bo'lgani uchun WHERE shartga mos kelmaydi.
  Additive: hech qanday modul olib tashlanmaydi.

#27 [data-integrity] platforma-do'kon (buyer_enterprise_id IS NULL, ADR-003)
  marketplace_order idempotentligi:
    Mavjud UniqueConstraint(buyer_enterprise_id, client_uuid) PostgreSQL'da
    NULL != NULL sababli platforma-do'kon buyurtmalari uchun ISHLAMAYDI.
    Qo'shimcha partial-unique: (buyer_store_id, client_uuid)
    WHERE buyer_enterprise_id IS NULL AND client_uuid IS NOT NULL.
    PostgreSQL: haqiqiy partial index. SQLite: model orqali oddiy UNIQUE
    (NULL != NULL allaqachon ekvivalent naqsh beradi — 0037 bilan bir xil).

IDEMPOTENT: sa.inspect bilan ustun/indeks borligini tekshiradi (0029/0037 naqshi).

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ─── #26: modul signaturalari ────────────────────────────────────────────────

# 0020 migratsiyasida yozilgan legacy-13 imzo (aynan shu literal matn —
# bo'sh joysiz, ALL_MODULE_KEYS ning birinchi 13 elementi bilan mos).
_LEGACY_13_JSON = (
    '["catalog","customers","orders","stock","finance",'
    '"delivery","attendance","gps","contracts","tickets",'
    '"promo","stats","push"]'
)

# app/models/enterprise.py ALL_MODULE_KEYS bilan mos — 18 modul (to'liq).
_ALL_18_JSON = (
    '["catalog","customers","orders","stock","finance",'
    '"delivery","attendance","gps","contracts","tickets",'
    '"promo","stats","push","pos","marketplace","analytics",'
    '"import","assistant"]'
)

# ─── #27: marketplace_order partial-unique ───────────────────────────────────

_MP_TABLE = "marketplace_order"
_MP_UQ_PARTIAL = "uq_mp_order_store_client_uuid_partial"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ── #26.1: DB DEFAULT'ni 18-modulga o'rnatish (faqat PostgreSQL) ─────────
    if is_pg:
        op.execute(sa.text(
            f"ALTER TABLE enterprise ALTER COLUMN enabled_modules "
            f"SET DEFAULT '{_ALL_18_JSON}'"
        ))

        # ── #26.2: faqat legacy-13 imzosiga AYNAN TENG satrlarni backfill ────
        # jsonb-tenglik — bo'sh-joy/formatlash farqidan mustaqil qiyoslash,
        # lekin ANIQ-IMZO (superset/union emas) — API orqali ataylab
        # kamaytirilgan modul-subsetlar tegilmaydi.
        op.execute(sa.text(
            "UPDATE enterprise SET enabled_modules = CAST(:new_val AS json) "
            "WHERE enabled_modules::jsonb = CAST(:legacy_val AS jsonb)"
        ).bindparams(new_val=_ALL_18_JSON, legacy_val=_LEGACY_13_JSON))
    else:
        # SQLite: aynan-teng matn solishtirish (jsonb funksiyasi yo'q).
        # Testlarda enterprise fixture'lari odatda to'liq 18-modul bilan
        # yaratiladi (model orqali) — bu tarmoq amaliy ta'sirsiz, faqat
        # PostgreSQL uchun muhim (dizaynga muvofiq).
        op.execute(sa.text(
            "UPDATE enterprise SET enabled_modules = :new_val "
            "WHERE enabled_modules = :legacy_val"
        ).bindparams(new_val=_ALL_18_JSON, legacy_val=_LEGACY_13_JSON))

    # ── #27: marketplace_order platforma-do'kon partial-unique indeks ────────
    insp = sa.inspect(bind)
    indexes = {i["name"] for i in insp.get_indexes(_MP_TABLE)}

    if is_pg:
        if _MP_UQ_PARTIAL not in indexes:
            op.execute(sa.text(
                f"CREATE UNIQUE INDEX {_MP_UQ_PARTIAL} "
                f"ON {_MP_TABLE} (buyer_store_id, client_uuid) "
                f"WHERE buyer_enterprise_id IS NULL AND client_uuid IS NOT NULL"
            ))
    else:
        if _MP_UQ_PARTIAL not in indexes:
            op.create_index(
                _MP_UQ_PARTIAL,
                _MP_TABLE,
                ["buyer_store_id", "client_uuid"],
                unique=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    insp = sa.inspect(bind)

    # ── #27: indeksni olib tashlash ───────────────────────────────────────────
    indexes = {i["name"] for i in insp.get_indexes(_MP_TABLE)}
    if _MP_UQ_PARTIAL in indexes:
        if is_pg:
            op.execute(sa.text(f"DROP INDEX {_MP_UQ_PARTIAL}"))
        else:
            op.drop_index(_MP_UQ_PARTIAL, table_name=_MP_TABLE)

    # ── #26: DEFAULT'ni 0020 legacy-13 qiymatiga qaytarish ────────────────────
    # ESLATMA: backfill qilingan qatorlarni (enabled_modules=18) legacy-13'ga
    # QAYTARISH QILINMAYDI — bu ma'lumot yo'qotish (modul ro'yxatini
    # kamaytirish) bo'lardi. Faqat DB DEFAULT qaytariladi.
    if is_pg:
        op.execute(sa.text(
            f"ALTER TABLE enterprise ALTER COLUMN enabled_modules "
            f"SET DEFAULT '{_LEGACY_13_JSON}'"
        ))
