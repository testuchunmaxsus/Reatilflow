"""
StoreInventory modeli — do'kon POS inventari (MP3 natijasi).

Jadval:
  store_inventory — marketplace yetkazilgan buyurtma do'kon inventariga tushadi.

DIZAYN:
  - Har marketplace buyurtma qatori (MarketplaceOrderLine) → bitta StoreInventory yozuvi.
  - cost_price = buyurtmadagi unit_price (server-avtoritar, o'zgartirib bo'lmaydi).
  - sale_price = cost_price * (1 + markup_percent / 100) — server tomonida hisoblanadi.
  - expiry_date — muddat (MP4: muddati o'tgan tahlil va bildirishnoma uchun asos).
  - enterprise_id = buyer korxona (tenant-scoped, MT1 pattern).
  - source_order_id — manbasi (qaysi marketplace buyurtmadan kelgani).

XAVFSIZLIK:
  - enterprise_id NOT NULL — tenant izolyatsiyasi (MT1).
  - Boshqa korxona bu inventarni ko'ra olmaydi (enterprise_id filtrlanadi).
  - cost_price faqat serverda o'rnatiladi (buyurtma unit_price dan).

MP4 uchun asos:
  - expiry_date: muddati o'tgan → status="expired" (cron/worker tomonida).
  - expiry_date <= now+2d → bildirishnoma (MP4 implements).
  - POS sotuv: qty deduksiya (MP4/POS modul).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise
    from app.models.store import Store
    from app.models.catalog import Product
    from app.models.marketplace import MarketplaceOrder
    from app.models.delivery import Delivery


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── Inventar holatlari ───────────────────────────────────────────────────────

STORE_INVENTORY_STATUSES = frozenset({"active", "expired"})


class StoreInventory(Base):
    """
    Do'kon POS inventar partiyasi.

    Marketplace orqali qabul qilingan mahsulotlar shu jadvalga tushadi.
    Har qabul qilingan buyurtma qatori → bitta StoreInventory yozuvi.

    TENANT IZOLYATSIYASI:
      - enterprise_id NOT NULL — faqat shu korxona ko'radi.
      - store_id — qaysi do'konda saqlanmoqda.

    NARX MANTIQI (server-avtoritar):
      cost_price  = buyurtma unit_price (o'zgartirilmaydi).
      sale_price  = cost_price * (1 + markup_percent / 100).
      markup_percent = do'kon qabul qilganda beradi (default 0).

    EXPIRY (MP4 tayanchisi):
      expiry_date — NULL bo'lishi mumkin (abadiy saqlash).
      Muddati o'tganda status='expired' bo'ladi (MP4 cron/worker).
    """

    __tablename__ = "store_inventory"
    __table_args__ = (
        # Tenant bo'yicha tez so'rovlar
        Index("ix_store_inv_enterprise", "enterprise_id"),
        # Do'kon + mahsulot bo'yicha inventar qidiruvi (POS uchun)
        Index("ix_store_inv_store_product", "store_id", "product_id"),
        # Expiry monitoring (MP4 cron/bildirishnoma uchun)
        Index("ix_store_inv_expiry", "expiry_date"),
        # Yetkazish manbasi bo'yicha qidiruv + idempotentlik
        Index("ix_store_inv_source_delivery", "source_delivery_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    # ─── Tenant izolyatsiyasi (MT1) ──────────────────────────────────────────

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Korxona FK → enterprise (MT1 tenant izolyatsiyasi, buyer korxona)",
    )

    # ─── Joylashuv ──────────────────────────────────────────────────────────

    store_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Do'kon FK → store (qaysi do'konda saqlanmoqda)",
    )

    # ─── Mahsulot ────────────────────────────────────────────────────────────

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    # ─── Miqdor ─────────────────────────────────────────────────────────────

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Inventardagi miqdor (Decimal, musbat)",
    )

    # ─── Narx (server-avtoritar) ─────────────────────────────────────────────

    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Tan narx (buyurtma unit_price — server-avtoritar, o'zgartirilmaydi)",
    )

    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0"),
        comment="Ustama foizi (do'kon qabul qilganda belgilaydi, default=0)",
    )

    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Sotuv narxi: cost_price * (1 + markup_percent/100) — server hisoblanadi",
    )

    # ─── Muddat ─────────────────────────────────────────────────────────────

    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Yaroqlilik muddati (NULL = cheksiz; MP4: muddati o'tganda expired)",
    )

    # ─── Holat ──────────────────────────────────────────────────────────────

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Holat: active | expired (MP4: muddat o'tganda expired bo'ladi)",
    )

    # ─── Manba (tracability) ─────────────────────────────────────────────────

    source_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("marketplace_order.id", ondelete="SET NULL"),
        nullable=True,
        comment="Manba buyurtma FK → marketplace_order (qaysi buyurtmadan kelgani)",
    )

    source_delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("delivery.id", ondelete="SET NULL"),
        nullable=True,
        comment="Manba yetkazish FK → delivery (agent buyurtmasi yetkazilganda yaratiladi)",
    )

    # ─── Vaqt ────────────────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    enterprise: Mapped["Enterprise"] = relationship(
        "Enterprise",
        foreign_keys="[StoreInventory.enterprise_id]",
        lazy="select",
    )

    store: Mapped["Store"] = relationship(
        "Store",
        foreign_keys="[StoreInventory.store_id]",
        lazy="select",
    )

    product: Mapped["Product"] = relationship(
        "Product",
        foreign_keys="[StoreInventory.product_id]",
        lazy="select",
    )

    source_order: Mapped["MarketplaceOrder | None"] = relationship(
        "MarketplaceOrder",
        foreign_keys="[StoreInventory.source_order_id]",
        lazy="select",
    )

    source_delivery: Mapped["Delivery | None"] = relationship(
        "Delivery",
        foreign_keys="[StoreInventory.source_delivery_id]",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<StoreInventory id={self.id} store={self.store_id} "
            f"product={self.product_id} qty={self.qty} "
            f"cost={self.cost_price} sale={self.sale_price} "
            f"status={self.status!r}>"
        )
