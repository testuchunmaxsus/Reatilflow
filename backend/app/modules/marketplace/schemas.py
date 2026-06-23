"""
Marketplace moduli Pydantic v2 sxemalari — MP1 + MP2.

MP1 sxemalar:
  MarketplaceProductOut     — browse ro'yxat va bitta mahsulot javobi
  MarketplaceSupplierOut    — supplier (korxona) javobi
  MarketplacePublishRequest — PATCH /catalog/products/{id}/marketplace tanasi
  PaginatedMarketplace      — paginated browse ro'yxat

MP2 sxemalar:
  MarketplaceOrderLineIn    — buyurtma yaratish: bitta qator kiritish
  MarketplaceOrderCreateIn  — buyurtma yaratish so'rovi tanasi
  MarketplaceOrderLineOut   — buyurtma qatori javobi
  MarketplaceOrderOut       — buyurtma javobi (lines bilan)
  PaginatedMarketplaceOrders — paginated buyurtmalar ro'yxati
  MarketplaceOrderRejectIn  — reject so'rovi tanasi (reason)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ─── Marketplace mahsulot ────────────────────────────────────────────────────


class MarketplaceProductOut(BaseModel):
    """
    Marketplace browse javobi — bitta mahsulot.

    price = marketplace_price yoki segment narxi (server tomonidan aniqlanadi).
    supplier_* = mahsulot egasi korxona ma'lumotlari.
    """

    id: uuid.UUID
    name_uz: str
    name_ru: str
    name: str = Field("", description="Lokalizatsiyalangan nom (joriy til)")
    sku: str | None
    barcode: str | None
    unit: str
    category_id: uuid.UUID | None
    photo_url: str | None
    is_active: bool
    marketplace_published: bool
    marketplace_price: Decimal | None = Field(
        None,
        description="Marketplace ulgurji narxi (None bo'lsa segment narx ishlatiladi)",
    )
    price: Decimal | None = Field(
        None,
        description="Ko'rsatiladigan narx: marketplace_price yoki segment narxi",
    )

    # Supplier (mahsulot egasi korxona)
    supplier_enterprise_id: uuid.UUID = Field(
        ...,
        description="Mahsulot egasi korxona ID",
    )
    supplier_name: str = Field(
        ...,
        description="Mahsulot egasi korxona nomi",
    )

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Supplier ro'yxat ────────────────────────────────────────────────────────


class MarketplaceSupplierOut(BaseModel):
    """
    Marketplace supplier (korxona) javobi.

    Faqat marketplace'da published mahsuloti bor korxonalar.
    """

    enterprise_id: uuid.UUID = Field(..., description="Korxona ID")
    name: str = Field(..., description="Korxona nomi")
    product_count: int = Field(..., description="Published mahsulotlar soni")

    model_config = {"from_attributes": True}


# ─── Paginated browse ────────────────────────────────────────────────────────


class PaginatedMarketplace(BaseModel):
    """Paginated marketplace browse ro'yxati javobi."""

    items: list[MarketplaceProductOut]
    total: int = Field(..., description="Jami topilgan published mahsulotlar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")


# ─── Publish toggle ──────────────────────────────────────────────────────────


class MarketplacePublishRequest(BaseModel):
    """
    PATCH /catalog/products/{id}/marketplace tanasi.

    marketplace_published = True → marketplace'ga qo'yish.
    marketplace_published = False → marketplace'dan olish.
    marketplace_price = None → segment narxidan foydalanish.
    """

    marketplace_published: bool = Field(
        ...,
        description="Marketplace'da ko'rinadimi (True=publish, False=unpublish)",
    )
    marketplace_price: Decimal | None = Field(
        None,
        description="Marketplace ulgurji narxi (None bo'lsa segment narx ishlatiladi)",
        ge=Decimal("0"),
    )


# ─── MP2: Buyurtma yaratish ──────────────────────────────────────────────────


class MarketplaceOrderLineIn(BaseModel):
    """
    Buyurtma qatori kiritish — bitta mahsulot.

    product_id: published marketplace mahsulot UUID.
    qty: miqdor (musbat).
    unit_price BERILMAYDI — server tomonida aniqlanadi (server-avtoritar narx).
    """

    product_id: uuid.UUID = Field(..., description="Marketplace mahsulot UUID")
    qty: Decimal = Field(..., gt=Decimal("0"), description="Miqdor (musbat)")


class MarketplaceOrderCreateIn(BaseModel):
    """
    POST /marketplace/orders tanasi.

    lines: bitta yoki ko'p qator (BARCHA bir supplierdan bo'lishi shart).
    client_uuid: idempotentlik UUID (ixtiyoriy — qayta yuborishda dublikat oldini oladi).
    """

    lines: list[MarketplaceOrderLineIn] = Field(
        ...,
        min_length=1,
        description="Buyurtma qatorlari (min 1, barcha bir supplierdan)",
    )
    client_uuid: uuid.UUID | None = Field(
        None,
        description="Idempotentlik UUID — qayta yuborishda dublikat yaratilmaydi",
    )


class MarketplaceOrderRejectIn(BaseModel):
    """
    PATCH /marketplace/orders/{id}/reject tanasi.

    reason: rad etish sababi (ixtiyoriy matn).
    """

    reason: str | None = Field(
        None,
        max_length=500,
        description="Rad etish sababi (ixtiyoriy)",
    )


# ─── MP2: Buyurtma javobi ────────────────────────────────────────────────────


class MarketplaceOrderLineOut(BaseModel):
    """Buyurtma qatori javobi."""

    id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal
    unit_price: Decimal = Field(..., description="Server-avtoritar narx")
    line_total: Decimal

    model_config = {"from_attributes": True}


class MarketplaceOrderOut(BaseModel):
    """
    Marketplace buyurtma javobi.

    Ikkita korxona uchun: buyer va supplier ma'lumotlari.
    """

    id: uuid.UUID
    buyer_enterprise_id: uuid.UUID
    buyer_store_id: uuid.UUID | None
    buyer_user_id: uuid.UUID
    supplier_enterprise_id: uuid.UUID
    status: str
    total_amount: Decimal
    reject_reason: str | None
    client_uuid: uuid.UUID | None
    lines: list[MarketplaceOrderLineOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedMarketplaceOrders(BaseModel):
    """Paginated marketplace buyurtmalar ro'yxati javobi."""

    items: list[MarketplaceOrderOut]
    total: int = Field(..., description="Jami buyurtmalar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
