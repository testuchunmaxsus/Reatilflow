"""
Marketplace moduli Pydantic v2 sxemalari — MP1.

Sxemalar:
  MarketplaceProductOut     — browse ro'yxat va bitta mahsulot javobi
  MarketplaceSupplierOut    — supplier (korxona) javobi
  MarketplacePublishRequest — PATCH /catalog/products/{id}/marketplace tanasi
  PaginatedMarketplace      — paginated browse ro'yxat
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
