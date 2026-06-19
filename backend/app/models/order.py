"""
Buyurtma modellari — T11 Buyurtma yadrosi, T12 Buyurtma shabloni.

Jadvallar:
  order             — buyurtma bosh yozuvi (status mashinasi bilan)
  order_line        — buyurtma qatorlari (mahsulot, miqdor, narx)
  order_template    — buyurtma shabloni (product+qty faqat, narx YO'Q)
  order_template_line — shablon qatorlari (product_id, qty; narx katalogdan apply paytida)

ADR §3.4, §3.5:
  - status: draft → confirmed → packed → delivering → delivered (→ canceled istalgan joydan)
  - server-avtoritar holat mashinasi (klient holat o'tishlarni taklif qiladi, server tasdiqlaydi)
  - client_uuid idempotentlik (UNIQUE partial index)
  - version — optimistik lock + LWW
  - append-only stock_movement + ledger_entry orqali atomik tranzaksiya

T12 Shablon:
  - Shablonda NARX SAQLANMAYDI — narx faqat apply paytida katalogdan olinadi (server-avtoritar).
  - apply_template() mavjud create_order() ni qayta ishlatadi — atomiklik dublikat qilinmaydi.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── Holat konstantalari ─────────────────────────────────────────────────────

ORDER_STATUSES = frozenset({
    "draft",
    "confirmed",
    "packed",
    "delivering",
    "delivered",
    "canceled",
})

ORDER_MODES = frozenset({"bozor", "oddiy"})

# Server-avtoritar qonuniy o'tishlar:
#   draft → confirmed, canceled
#   confirmed → packed, canceled
#   packed → delivering, canceled
#   delivering → delivered, canceled
#   delivered → (hech qaerga: QAYTIB BO'LMAYDI)
#   canceled → (hech qaerga: terminal holat)
VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft":       {"confirmed", "canceled"},
    "confirmed":   {"packed", "canceled"},
    "packed":      {"delivering", "canceled"},
    "delivering":  {"delivered", "canceled"},
    "delivered":   set(),   # terminal holat — orqaga qaytish mumkin emas
    "canceled":    set(),   # terminal holat
}


class Order(TimestampMixin, Base):
    """
    Buyurtma bosh yozuvi.

    Holat mashinasi (ADR §3.5):
      draft → confirmed → packed → delivering → delivered
      istalgan holat → canceled (delivered bundan mustasno: TERMINAL)

    Atomiklik (T11):
      create_order() BITTA DB tranzaksiyasida:
        1. Order + OrderLine INSERT
        2. Har qator uchun stock chiqimi (record_movement type=out)
        3. LedgerEntry debit (do'kon qarzi)
      Agar qoldiq yetmasa → AppError → BUTUN rollback.

    Kompensatsiya:
      canceled holat uchun stock/ledger kompensatsiyasi T12/T13 da (kelajak ish).
      Hozirda status o'zgartirish + izoh (status_comment) yetarli.
    """

    __tablename__ = "order"
    __table_args__ = (
        Index("ix_order_store_id", "store_id"),
        Index("ix_order_agent_id", "agent_id"),
        Index("ix_order_status", "status"),
        Index("ix_order_ordered_at", "ordered_at"),
        # Idempotentlik: (store_id, client_uuid) — DoS himoyasi
        # Partial index (client_uuid IS NOT NULL) migration da yaratiladi.
        # ORM darajasida UniqueConstraint — to'liq unique (SQLite uchun).
        UniqueConstraint("store_id", "client_uuid", name="uq_order_store_client_uuid"),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Do'kon FK → store",
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Agent FK → app_user (RETAIL BOZOR rejimida)",
    )

    mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="oddiy",
        comment="Rejim: bozor | oddiy",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="confirmed",
        comment="Holat: draft | confirmed | packed | delivering | delivered | canceled",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Jami summa (Decimal) — qatorlardan hisoblanadi",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="UZS",
        comment="Valyuta kodi (ISO 4217)",
    )

    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Buyurtma vaqti (UTC)",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Klient idempotentlik UUID — UNIQUE partial index (IS NOT NULL)",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Filial ID",
    )

    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Ombor ID — stock chiqimi/qaytimi uchun (kompensatsiya to'g'ri omborga boradi)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} store={self.store_id} "
            f"status={self.status!r} total={self.total_amount}>"
        )


class OrderLine(Base):
    """
    Buyurtma qatori — bitta mahsulot.

    line_total = unit_price * qty - discount (Decimal)
    Narx katalogdan olinadi (segment_id bo'yicha) yoki kirishdan.
    """

    __tablename__ = "order_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False,
        comment="Buyurtma FK → order",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Miqdor (Decimal, musbat)",
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Birlik narxi (Decimal) — katalogdan yoki kirishdan",
    )

    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_segment.id", ondelete="SET NULL"),
        nullable=True,
        comment="Narx segmenti FK → price_segment (ixtiyoriy)",
    )

    discount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Chegirma summasi (Decimal, default=0)",
    )

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Qator jami: unit_price * qty - discount",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="lines",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderLine order={self.order_id} product={self.product_id} "
            f"qty={self.qty} total={self.line_total}>"
        )


# ─── OrderTemplate (T12) ──────────────────────────────────────────────────────


class OrderTemplate(TimestampMixin, Base):
    """
    Buyurtma shabloni — T12.

    Shablon faqat product_id + qty saqlaydi. NARX YO'Q.
    Narx apply_template() paytida katalogdan (do'kon segmenti bo'yicha) olinadi.
    Bu server-avtoritar narx xavfsizligini ta'minlaydi.

    Soft delete: deleted_at IS NOT NULL → o'chirilgan.
    """

    __tablename__ = "order_template"
    __table_args__ = (
        Index("ix_order_template_store_id", "store_id"),
        Index("ix_order_template_created_by", "created_by"),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Do'kon FK → store",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Shablon nomi",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Yaratuvchi FK → app_user",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Filial ID (ixtiyoriy)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    lines: Mapped[list["OrderTemplateLine"]] = relationship(
        "OrderTemplateLine",
        back_populates="template",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderTemplate id={self.id} store={self.store_id} name={self.name!r}>"
        )


class OrderTemplateLine(Base):
    """
    Buyurtma shabloni qatori — bitta mahsulot.

    MUHIM: unit_price YO'Q — narx FAQAT apply paytida katalogdan olinadi.
    Bu T12 asosiy invarianti: shablon product+qty saqlaydi, narx emas.
    """

    __tablename__ = "order_template_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("order_template.id", ondelete="CASCADE"),
        nullable=False,
        comment="Shablon FK → order_template",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Miqdor (Decimal, musbat) — narx YO'Q",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    template: Mapped["OrderTemplate"] = relationship(
        "OrderTemplate",
        back_populates="lines",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderTemplateLine template={self.template_id} "
            f"product={self.product_id} qty={self.qty}>"
        )
