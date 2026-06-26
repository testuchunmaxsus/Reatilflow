"""branch jadvali yaratish va app_user/store.branch_id FK qo'shish.

NEGA:
  - app_user.branch_id va store.branch_id ustunlari mavjud, lekin branch jadvali yo'q edi.
  - Filiallar bo'lmagan (NULL qiymatlar) — FK qo'shish xavfsiz.
  - enterprise_id NOT NULL — har filial korxonaga tegishli.

NIMA:
  - `branch` jadvalini yaratadi (id, enterprise_id FK, name, address, phone,
    is_active, version, created_at, updated_at, deleted_at).
  - app_user.branch_id → branch.id FK qo'shadi (ON DELETE SET NULL).
  - store.branch_id → branch.id FK qo'shadi (ON DELETE SET NULL).
  - IDEMPOTENT: sa.inspect bilan jadval/ustun/indeks borligini tekshiradi.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BRANCH_TABLE = "branch"
_BRANCH_IDX_ENTERPRISE = "ix_branch_enterprise_id"
_APP_USER_FK = "fk_app_user_branch_id"
_STORE_FK = "fk_store_branch_id"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # ── 1. branch jadvali yaratish (agar yo'q bo'lsa) ──────────────────────
    if _BRANCH_TABLE not in existing_tables:
        op.create_table(
            _BRANCH_TABLE,
            sa.Column(
                "id",
                uuid_type,
                primary_key=True,
                comment="UUID v7 — vaqt-tartibli birlamchi kalit",
            ),
            sa.Column(
                "enterprise_id",
                uuid_type,
                sa.ForeignKey("enterprise.id", ondelete="RESTRICT"),
                nullable=False,
                comment="Korxona FK → enterprise (NOT NULL)",
            ),
            sa.Column(
                "name",
                sa.String(255),
                nullable=False,
                comment="Filial nomi",
            ),
            sa.Column(
                "address",
                sa.String(500),
                nullable=True,
                comment="Filial manzili",
            ),
            sa.Column(
                "phone",
                sa.String(50),
                nullable=True,
                comment="Filial telefon raqami",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
                comment="Filial faolligi (False = nofaol)",
            ),
            sa.Column(
                "version",
                sa.BigInteger(),
                nullable=False,
                server_default="1",
                comment="Optimistik lock + LWW uchun versiya raqami",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Yaratilgan vaqt (UTC)",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Oxirgi yangilangan vaqt (UTC)",
            ),
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Soft delete vaqti (NULL = aktiv yozuv)",
            ),
        )

    # ── 2. enterprise_id indeksi ─────────────────────────────────────────────
    indexes = {i["name"] for i in insp.get_indexes(_BRANCH_TABLE)} if _BRANCH_TABLE in existing_tables else set()
    # Re-inspect after possible table creation
    insp2 = sa.inspect(bind)
    if _BRANCH_TABLE in insp2.get_table_names():
        indexes = {i["name"] for i in insp2.get_indexes(_BRANCH_TABLE)}
        if _BRANCH_IDX_ENTERPRISE not in indexes:
            op.create_index(_BRANCH_IDX_ENTERPRISE, _BRANCH_TABLE, ["enterprise_id"])

    # ── 3. app_user.branch_id → branch.id FK (ON DELETE SET NULL) ──────────
    # Mavjud app_user.branch_id qiymatlari NULL — xavfsiz FK qo'shish.
    app_user_fks = {fk["name"] for fk in insp2.get_foreign_keys("app_user")}
    if _APP_USER_FK not in app_user_fks:
        op.create_foreign_key(
            _APP_USER_FK,
            "app_user",
            _BRANCH_TABLE,
            ["branch_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ── 4. store.branch_id → branch.id FK (ON DELETE SET NULL) ─────────────
    store_fks = {fk["name"] for fk in insp2.get_foreign_keys("store")}
    if _STORE_FK not in store_fks:
        op.create_foreign_key(
            _STORE_FK,
            "store",
            _BRANCH_TABLE,
            ["branch_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # FK larni olib tashlash
    store_fks = {fk["name"] for fk in insp.get_foreign_keys("store")}
    if _STORE_FK in store_fks:
        op.drop_constraint(_STORE_FK, "store", type_="foreignkey")

    app_user_fks = {fk["name"] for fk in insp.get_foreign_keys("app_user")}
    if _APP_USER_FK in app_user_fks:
        op.drop_constraint(_APP_USER_FK, "app_user", type_="foreignkey")

    # Indeksni olib tashlash
    existing_tables = insp.get_table_names()
    if _BRANCH_TABLE in existing_tables:
        indexes = {i["name"] for i in insp.get_indexes(_BRANCH_TABLE)}
        if _BRANCH_IDX_ENTERPRISE in indexes:
            op.drop_index(_BRANCH_IDX_ENTERPRISE, table_name=_BRANCH_TABLE)

        # Jadvalni olib tashlash
        op.drop_table(_BRANCH_TABLE)
