"""
Marketplace buyurtma modellari — MP2 + MP3.

Jadvallar:
  marketplace_order      — cross-tenant buyurtma (buyer ↔ supplier ikki korxona)
  marketplace_order_line — buyurtma qatorlari (mahsulot, miqdor, server-narx)

XAVFSIZLIK va ARXITEKTURA IZOHI:
  Bu jadvallar ATAYLAB ikkita korxonaga tegishli (cross-tenant).
  Shuning uchun:
    - enterprise_id TEKIS USTUN YO'Q (boshqa jadvallardagidek tenant RLS yo'q).
    - Buning o'rniga buyer_enterprise_id va supplier_enterprise_id alohida FK.
    - Access nazorati SERVICE QATLAMIDA amalga oshiriladi:
        (buyer_enterprise_id == me OR supplier_enterprise_id == me)
      Uchinchi korxona → 404 (mavjudlikni oshkor qilmaslik).
    - Migratsiyada oddiy tenant-RLS QO'YILMAYDI — bu istisno, service nazorat qiladi.

Status mashinasi (MP3):
  pending → confirmed → delivering → delivered → accepted
  pending → rejected   (terminal)

Outbox:
  marketplace.order_created    — supplier_enterprise_id bilan (supplier sync uchun)
  marketplace.order_confirmed  — buyer_enterprise_id bilan (buyer sync uchun)
  marketplace.order_rejected   — buyer_enterprise_id bilan (buyer sync uchun)
  marketplace.order_delivering — buyer_enterprise_id bilan (MP3)
  marketplace.order_delivered  — buyer_enterprise_id bilan (MP3)
  marketplace.order_accepted   — supplier_enterprise_id bilan (MP3)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.enterprise import Enterprise
    from app.models.store import Store
    from app.models.user import AppUser
    from app.models.store_inventory import StoreInventory


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── Status konstantalari ──────────────────────────────────────────────────────

MP_ORDER_STATUSES = frozenset({
    "pending",
    "confirmed",
    "rejected",
    "delivering",
    "delivered",
    "accepted",
})

# Server-avtoritar qonuniy o'tishlar (MP2 uchun pending/confirmed/rejected):
MP_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":    {"confirmed", "rejected"},
    "confirmed":  {"delivering"},        # MP3 da kengaytiriladi
    "rejected":   set(),                 # terminal
    "delivering": {"delivered"},         # MP3
    "delivered":  {"accepted"},          # MP3
    "accepted":   set(),                 # terminal
}


class MarketplaceOrder(Base):
    """
    Marketplace cross-tenant buyurtmasi.

    DIZAYN ISTISNO:
      - enterprise_id ustuni YO'Q — jadval ikkita korxonaga tegishli.
      - buyer_enterprise_id:  xaridor korxona (do'kon tomonida).
      - supplier_enterprise_id: sotuvchi korxona (mahsulot egasi).
      - Tenant-RLS bu jadvalga QILINMAYDI — service nazorat qiladi.

    Idempotentlik:
      client_uuid — UNIQUE(buyer_enterprise_id, client_uuid) partial index.
      Bir xil so'rovni qayta jo'natsa dublikat yaratilmaydi.
    """

    __tablename__ = "marketplace_order"
    __table_args__ = (
        # Tez so'rovlar uchun indekslar
        Index("ix_mp_order_buyer_enterprise", "buyer_enterprise_id"),
        Index("ix_mp_order_supplier_enterprise_status", "supplier_enterprise_id", "status"),
        # Idempotentlik: bir xil client_uuid + buyer korxonada faqat bitta
        UniqueConstraint(
            "buyer_enterprise_id",
            "client_uuid",
            name="uq_mp_order_buyer_client_uuid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    # ─── Xaridor (buyer) ─────────────────────────────────────────────────────

    buyer_enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,  # 0035: DROP NOT NULL — mustaqil do'kon korxonaga ega emas
        comment="Xaridor korxona FK → enterprise (buyer side; NULL=mustaqil do'kon, 0035)",
    )

    buyer_store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store.id", ondelete="SET NULL"),
        nullable=True,
        comment="Xaridor do'kon FK → store (NULL bo'lishi mumkin — admin buyurtma bersa)",
    )

    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Buyurtma bergan foydalanuvchi FK → app_user",
    )

    # ─── Sotuvchi (supplier) ──────────────────────────────────────────────────

    supplier_enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Sotuvchi korxona FK → enterprise (supplier side)",
    )

    # ─── Holat va miqdor ─────────────────────────────────────────────────────

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Holat: pending | confirmed | rejected | delivering | delivered | accepted",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Jami summa (Decimal) — qatorlardan server hisoblanadi",
    )

    reject_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Rad etish sababi (faqat rejected holat uchun)",
    )

    # ─── MP3: Yetkazish maydonlari ────────────────────────────────────────────

    courier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Tayinlangan kuryer FK → app_user (MP3: ship bosqichida o'rnatiladi)",
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Yetkazilgan vaqt (MP3: delivered holat, UTC)",
    )

    proof_photo_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Yetkazish isboti rasm URL (MP3: delivered holat, do'kon oldida)",
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Do'kon qabul qilgan vaqt (MP3: accepted holat, UTC)",
    )

    # ─── Idempotentlik ────────────────────────────────────────────────────────

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Klient idempotentlik UUID — UNIQUE(buyer_enterprise_id, client_uuid)",
    )

    # ─── Shartnoma-Gate (0035) ────────────────────────────────────────────────

    is_onetime: Mapped[bool] = mapped_column(
        __import__("sqlalchemy").Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Bir martalik buyurtma: agent bypass orqali (shartnoma yo'q holat, 0035)",
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Bir martalik buyurtmani bergan agent FK → app_user (0035)",
    )

    # ─── Vaqt ────────────────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
        nullable=False,
        comment="Oxirgi yangilangan vaqt (UTC)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    lines: Mapped[list["MarketplaceOrderLine"]] = relationship(
        "MarketplaceOrderLine",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    buyer_enterprise: Mapped["Enterprise"] = relationship(
        "Enterprise",
        foreign_keys="[MarketplaceOrder.buyer_enterprise_id]",
        lazy="select",
    )

    supplier_enterprise: Mapped["Enterprise"] = relationship(
        "Enterprise",
        foreign_keys="[MarketplaceOrder.supplier_enterprise_id]",
        lazy="select",
    )

    buyer_store: Mapped["Store | None"] = relationship(
        "Store",
        foreign_keys="[MarketplaceOrder.buyer_store_id]",
        lazy="select",
    )

    buyer_user: Mapped["AppUser"] = relationship(
        "AppUser",
        foreign_keys="[MarketplaceOrder.buyer_user_id]",
        lazy="select",
    )

    courier: Mapped["AppUser | None"] = relationship(
        "AppUser",
        foreign_keys="[MarketplaceOrder.courier_id]",
        lazy="select",
    )

    agent: Mapped["AppUser | None"] = relationship(
        "AppUser",
        foreign_keys="[MarketplaceOrder.agent_id]",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<MarketplaceOrder id={self.id} "
            f"buyer={self.buyer_enterprise_id} "
            f"supplier={self.supplier_enterprise_id} "
            f"status={self.status!r}>"
        )


class MarketplaceOrderLine(Base):
    """
    Marketplace buyurtma qatori — bitta mahsulot.

    unit_price: SERVER TOMONIDAN aniqlanadi (product.marketplace_price
    yoki birinchi aktiv segment narxi). Klient narx bera olmaydi.
    line_total = unit_price * qty.

    XAVFSIZLIK:
      - enterprise_id YO'Q (cross-tenant jadval — order bilan birga nazorat qilinadi).
    """

    __tablename__ = "marketplace_order_line"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_order.id", ondelete="CASCADE"),
        nullable=False,
        comment="Buyurtma FK → marketplace_order",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
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
        comment="Birlik narxi (SERVER-AVTORITAR — marketplace_price yoki segment narx)",
    )

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Qator jami: unit_price * qty",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    order: Mapped["MarketplaceOrder"] = relationship(
        "MarketplaceOrder",
        back_populates="lines",
        lazy="select",
    )

    product: Mapped["Product"] = relationship(
        "Product",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<MarketplaceOrderLine order={self.order_id} "
            f"product={self.product_id} qty={self.qty} total={self.line_total}>"
        )
