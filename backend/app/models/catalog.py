"""
Katalog modellari.

Jadvallar:
  category       — mahsulot kategoriyasi (ierarxik, self-referential)
  price_segment  — narx segmenti (VIP, ulgurji, chakana, ...)
  product        — asosiy mahsulot (barcode, mxik, sku indekslangan)
  product_price  — segment × mahsulot narxi (valid_from/valid_to bilan)
  price_history  — narx tarixi (APPEND-ONLY — o'chirish/yangilash taqiqlangan)
  product_note   — mahsulot izohi/baholash (faqat yozish)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class Category(TimestampMixin, Base):
    """Mahsulot kategoriyasi (ierarxik daraxt)."""

    __tablename__ = "category"

    name_uz: Mapped[str] = mapped_column(String(255), nullable=False, comment="Nomi (UZ)")
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False, comment="Nomi (RU)")

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category.id", ondelete="SET NULL"),
        nullable=True,
        comment="Yuqori kategoriya (NULL = ildiz)",
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ─── Relationships ───────────────────────────────────────
    children: Mapped[list["Category"]] = relationship(
        "Category",
        back_populates="parent",
        lazy="select",
    )
    parent: Mapped["Category | None"] = relationship(
        "Category",
        back_populates="children",
        remote_side="Category.id",
        lazy="select",
    )
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="category",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name_uz={self.name_uz!r}>"


class PriceSegment(TimestampMixin, Base):
    """Narx segmenti (VIP, ulgurji, chakana, ...)."""

    __tablename__ = "price_segment"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Segment nomi",
    )

    def __repr__(self) -> str:
        return f"<PriceSegment id={self.id} name={self.name!r}>"


class Product(TimestampMixin, Base):
    """
    Mahsulot.

    Indekslar (Alembic migratsiyada):
      - barcode  — shtrix-kod skaneri orqali tezkor qidiruv
      - mxik_code — MXIK fiskal kod
      - sku      — ichki artikel
    """

    __tablename__ = "product"

    name_uz: Mapped[str] = mapped_column(String(500), nullable=False, comment="Nomi (UZ)")
    name_ru: Mapped[str] = mapped_column(String(500), nullable=False, comment="Nomi (RU)")

    sku: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        comment="Ichki artikel (SKU)",
    )

    barcode: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Shtrix-kod (EAN/UPC) — indekslangan",
    )

    mxik_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="MXIK fiskal kod — indekslangan",
    )

    unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="dona",
        comment="O'lchov birligi: dona | kg | litr | ...",
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kategoriya FK",
    )

    photo_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="MinIO/S3 URL",
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    branch_scope: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON: filiallar ro'yxati (NULL = barcha filiallar)",
    )

    # ─── Relationships ───────────────────────────────────────
    category: Mapped["Category | None"] = relationship(
        "Category",
        back_populates="products",
        lazy="select",
    )
    prices: Mapped[list["ProductPrice"]] = relationship(
        "ProductPrice",
        back_populates="product",
        lazy="select",
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="product",
        lazy="select",
    )
    notes: Mapped[list["ProductNote"]] = relationship(
        "ProductNote",
        back_populates="product",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r} name_uz={self.name_uz!r}>"


class ProductPrice(TimestampMixin, Base):
    """
    Mahsulot narxi — segment va muddatga bog'liq.

    Bir vaqtda bitta mahsulot + segment uchun faqat bitta aktiv narx bo'ladi
    (valid_from ≤ now ≤ valid_to, yoki valid_to IS NULL = ochiq muddat).
    """

    __tablename__ = "product_price"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "segment_id", "valid_from",
            name="uq_product_price_segment_from",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_segment.id", ondelete="CASCADE"),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Narx (so'm)",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="UZS",
        nullable=False,
        comment="Valyuta kodi (ISO 4217)",
    )

    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Narx amal qilish boshlanishi",
    )

    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Narx tugash vaqti (NULL = ochiq)",
    )

    # ─── Relationships ───────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="prices",
        lazy="select",
    )
    segment: Mapped["PriceSegment"] = relationship("PriceSegment", lazy="select")


class PriceHistory(Base):
    """
    Narx tarixi — APPEND-ONLY.

    Bu jadvalga faqat INSERT qilinadi; UPDATE/DELETE taqiqlangan.
    Audit va moliyaviy hisobot uchun kerak.
    """

    __tablename__ = "price_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID birlamchi kalit",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_segment.id", ondelete="CASCADE"),
        nullable=False,
    )

    old_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)

    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kim o'zgartirdi (FK → app_user)",
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ─── Relationships ───────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="price_history",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<PriceHistory product={self.product_id} "
            f"{self.old_price}→{self.new_price} at={self.changed_at}>"
        )


class ProductNote(Base):
    """
    Mahsulot izohi / baholash — faqat yozish.

    Agent yoki do'kon qoldirgan izohlar; o'chirish/tahrirlash yo'q.
    """

    __tablename__ = "product_note"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID birlamchi kalit",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Muallif (FK → app_user)",
    )

    rating: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Baho (1–5, ixtiyoriy)",
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Matnli izoh",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ─── Relationships ───────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="notes",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<ProductNote product={self.product_id} rating={self.rating}>"
