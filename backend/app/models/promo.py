"""
Aksiya (Promo) modeli — T25.

Jadval:
  promo — savdo aksiyalari (chegirma/bonus/sovg'a)

  Promo rules (rule_json):
    discount_percent qoida:
      {"discount_percent": 10, "min_qty": 5}  — 5 dan ortiq sotib olganda 10% chegirma
    discount_amount qoida:
      {"discount_amount": 5000}               — har qatordan 5000 so'm chegirma
    Mos promo yo'q → Decimal("0")             — klient bera olmaydi (T11 himoyasi)

ADR §3.4:
  - id UUID v7 (vaqt-tartibli, offline klient generatsiya qiladi)
  - version optimistik lock + LWW
  - deleted_at soft delete
  - audit_log + outbox_event har mutatsiyada
  - SERVER-AVTORITAR narx: klient discount bera olmaydi
"""

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.catalog import PriceSegment, Product
    from app.models.enterprise import Enterprise


class Promo(TimestampMixin, Base):
    """
    Aksiya (promo) — savdo chegirmasi, bonus yoki sovg'a.

    promo_type:
      discount — foizli yoki summaviy chegirma (rule_json ichida)
      bonus    — bonus point yig'ish (kelajak)
      gift     — sovg'a mahsulot (kelajak)

    rule_json:
      {"discount_percent": 10}              — 10% chegirma
      {"discount_amount": 5000}             — 5000 so'm chegirma
      {"discount_percent": 15, "min_qty": 3} — 3 dan ko'p sotib olganda 15%
      {"discount_amount": 2000, "min_qty": 2} — 2 dan ko'p bo'lsa 2000 so'm

    target_segment_id:
      NULL → barcha segmentlar uchun amal qiladi.
      NOT NULL → faqat mos segment uchun.

    target_product_id:
      NULL → barcha mahsulotlar uchun amal qiladi.
      NOT NULL → faqat mos mahsulot uchun.

    is_active + valid_from/valid_to:
      Aktiv aksiya: is_active=True AND valid_from<=bugun<=valid_to
    """

    __tablename__ = "promo"
    __table_args__ = (
        # Tezkor qidiruvlar uchun indekslar
        Index("ix_promo_is_active", "is_active"),
        Index("ix_promo_valid_from", "valid_from"),
        Index("ix_promo_valid_to", "valid_to"),
        Index("ix_promo_target_segment", "target_segment_id"),
        Index("ix_promo_target_product", "target_product_id"),
        # Idempotentlik: client_uuid UNIQUE (partial — SQLite da to'liq unique)
        UniqueConstraint("client_uuid", name="uq_promo_client_uuid"),
    )

    name_uz: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Aksiya nomi (UZ)",
    )
    name_ru: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Aksiya nomi (RU)",
    )

    promo_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="discount",
        comment="Aksiya turi: discount | bonus | gift",
    )

    rule_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Chegirma qoidalari: {discount_percent?, discount_amount?, min_qty?}",
    )

    banner_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Banner URL (MinIO/S3, ixtiyoriy)",
    )

    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Aksiya boshlanish sanasi",
    )

    valid_to: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Aksiya tugash sanasi",
    )

    target_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("price_segment.id", ondelete="SET NULL"),
        nullable=True,
        comment="Narx segmenti FK → price_segment (NULL = barchasi)",
    )

    target_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product.id", ondelete="SET NULL"),
        nullable=True,
        comment="Mahsulot FK → product (NULL = barchasi)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Aktiv holat",
    )

    marketplace_featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Marketplace'da qaynoq aksiya sifatida ko'rsatish (opt-in, MP5)",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Filial ID (NULL = global)",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Idempotentlik UUID (partial unique IS NOT NULL)",
    )

    # ─── MT1: enterprise_id ──────────────────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Korxona FK → enterprise (MT1)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    target_segment: Mapped["PriceSegment | None"] = relationship(
        "PriceSegment",
        lazy="select",
        foreign_keys=[target_segment_id],
    )
    target_product: Mapped["Product | None"] = relationship(
        "Product",
        lazy="select",
        foreign_keys=[target_product_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Promo id={self.id} type={self.promo_type!r} "
            f"from={self.valid_from} to={self.valid_to} active={self.is_active}>"
        )
