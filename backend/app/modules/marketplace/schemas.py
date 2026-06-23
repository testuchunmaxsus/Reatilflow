"""
Marketplace moduli Pydantic v2 sxemalari — MP1 + MP2 + MP3.

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

MP3 sxemalar:
  MarketplaceShipIn         — ship so'rovi tanasi (courier_id)
  MarketplaceDeliverIn      — deliver so'rovi tanasi (proof_photo_url)
  MarketplaceAcceptLineIn   — accept: bitta line uchun expiry+markup
  MarketplaceAcceptIn       — accept so'rovi tanasi (lines_info, store_id)
  StoreInventoryOut         — inventar partiyasi javobi
  PaginatedStoreInventory   — paginated inventar ro'yxati
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
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
    MP3 maydonlari: courier_id, delivered_at, proof_photo_url, accepted_at.
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
    # MP3 maydonlari
    courier_id: uuid.UUID | None = None
    delivered_at: datetime | None = None
    proof_photo_url: str | None = None
    accepted_at: datetime | None = None
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


# ─── MP3: Yetkazish sxemalari ────────────────────────────────────────────────


class MarketplaceShipIn(BaseModel):
    """
    PATCH /marketplace/orders/{id}/ship tanasi.

    courier_id: tayinlanadigan kuryer (supplier korxona kuryeri).
    """

    courier_id: uuid.UUID = Field(
        ...,
        description="Tayinlanadigan kuryer UUID (supplier korxona foydalanuvchisi, courier roli)",
    )


class MarketplaceDeliverIn(BaseModel):
    """
    PATCH /marketplace/orders/{id}/deliver tanasi.

    proof_photo_url: yetkazish isboti rasm URL (ixtiyoriy).
    """

    proof_photo_url: str | None = Field(
        None,
        max_length=1000,
        description="Yetkazish isboti rasm URL (do'kon oldidagi fotosurat, ixtiyoriy)",
    )


class MarketplaceAcceptLineIn(BaseModel):
    """
    accept so'rovida bitta buyurtma qatori ma'lumoti.

    line_id:        buyurtma qatori UUID (MarketplaceOrderLine.id).
    expiry_date:    yaroqlilik muddati (NULL = cheksiz).
    markup_percent: ustama foizi (default 0 — sale_price = cost_price).
    """

    line_id: uuid.UUID = Field(..., description="Buyurtma qatori UUID")
    expiry_date: date | None = Field(
        None,
        description="Yaroqlilik muddati (NULL = cheksiz)",
    )
    markup_percent: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Ustama foizi % (default=0; sale_price = cost*(1+markup/100))",
    )


class MarketplaceAcceptIn(BaseModel):
    """
    PATCH /marketplace/orders/{id}/accept tanasi.

    lines: har line uchun expiry_date + markup_percent.
    store_id: qabul qiladigan do'kon (None = order.buyer_store_id).
    """

    lines: list[MarketplaceAcceptLineIn] = Field(
        default_factory=list,
        description="Har qator uchun expiry va markup ma'lumoti (bo'sh = hammasi default)",
    )
    store_id: uuid.UUID | None = Field(
        None,
        description="Do'kon UUID (None = buyurtmadagi buyer_store_id ishlatiladi)",
    )


# ─── MP3: StoreInventory sxemasi ─────────────────────────────────────────────


class StoreInventoryOut(BaseModel):
    """
    Do'kon inventar partiyasi javobi.

    cost_price = buyurtma narxi (tan narx).
    sale_price = cost_price * (1 + markup_percent/100) — serverda hisoblanadi.
    expiry_date = yaroqlilik muddati (MP4 asos).

    MP4 expiry bayroqlari (UI qizil ko'rsatishi uchun):
      is_expired      — muddati o'tgan (sotuv bloklanadi).
      is_near_expiry  — yaqinda tugaydi (konfigdan: pos_expiry_block_days).
      days_to_expiry  — qolgan kun soni (manfiy = o'tgan, None = expiry yo'q).
    """

    id: uuid.UUID
    enterprise_id: uuid.UUID
    store_id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal
    cost_price: Decimal = Field(..., description="Tan narx (buyurtma unit_price)")
    markup_percent: Decimal = Field(..., description="Ustama foizi %")
    sale_price: Decimal = Field(..., description="Sotuv narxi: cost*(1+markup/100)")
    expiry_date: date | None = Field(None, description="Yaroqlilik muddati (MP4 asos)")
    status: str = Field(..., description="active | expired")
    source_order_id: uuid.UUID | None = None
    created_at: datetime

    # MP4: Expiry bayroqlari — UI qizil ko'rsatish uchun
    is_expired: bool = Field(False, description="True — muddati o'tgan (sotuv bloklanadi)")
    is_near_expiry: bool = Field(
        False,
        description="True — yaqinda tugaydi (POS blok chegarasida yoki undan kam)",
    )
    days_to_expiry: int | None = Field(
        None,
        description="Muddatgacha qolgan kunlar (manfiy = o'tgan, None = cheksiz)",
    )

    model_config = {"from_attributes": True}


class PaginatedStoreInventory(BaseModel):
    """Paginated do'kon inventar ro'yxati javobi."""

    items: list[StoreInventoryOut]
    total: int = Field(..., description="Jami yozuvlar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
