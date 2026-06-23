"""
Marketplace moduli Pydantic v2 sxemalari — MP1 + MP2 + MP3 + MP5.

MP1 sxemalar:
  MarketplaceProductOut     — browse ro'yxat va bitta mahsulot javobi
  MarketplaceSupplierOut    — supplier (korxona) javobi
  MarketplacePublishRequest — PATCH /catalog/products/{id}/marketplace tanasi
  PaginatedMarketplace      — paginated browse ro'yxat

MP2 sxemalar:
  MarketplaceOrderLineIn    — buyurtma yaratish: bitta qator kiritish
  MarketplaceOrderCreateIn  — buyurtma yaratish so'rovi tanasi
  MarketplaceOrderLineOut   — buyurtma qatori javobi (product_name bilan)
  MarketplaceOrderOut       — buyurtma javobi (lines + nom maydonlar bilan)
  PaginatedMarketplaceOrders — paginated buyurtmalar ro'yxati
  MarketplaceOrderRejectIn  — reject so'rovi tanasi (reason)

MP3 sxemalar:
  MarketplaceShipIn         — ship so'rovi tanasi (courier_id)
  MarketplaceDeliverIn      — deliver so'rovi tanasi (proof_photo_url)
  MarketplaceAcceptLineIn   — accept: bitta line uchun expiry+markup
  MarketplaceAcceptIn       — accept so'rovi tanasi (lines_info, store_id)
  StoreInventoryOut         — inventar partiyasi javobi
  PaginatedStoreInventory   — paginated inventar ro'yxati

MP5 sxemalar:
  AdBannerCreate            — banner yaratish so'rovi tanasi
  AdBannerPatch             — banner tahrirlash (PATCH) tanasi
  AdBannerOut               — banner javobi
  PaginatedBanners          — paginated banner ro'yxati (admin /banners/mine uchun)
  MarketplacePromoOut       — qaynoq aksiya javobi (cross-tenant, featured)
  PromoMarketplaceToggle    — PATCH /promos/{id}/marketplace-featured tanasi
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
    """
    Buyurtma qatori javobi.

    product_name — faqat list_incoming/list_outgoing'da populate qilinadi (enrich=True).
    Mutatsiya endpointlari (confirm/reject/ship/deliver/accept) da None qaytadi.
    """

    id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal
    unit_price: Decimal = Field(..., description="Server-avtoritar narx")
    line_total: Decimal
    product_name: str | None = Field(
        None,
        description="Mahsulot nomi (faqat ro'yxat endpointlarida: list_incoming/outgoing)",
    )

    model_config = {"from_attributes": True}


class MarketplaceOrderOut(BaseModel):
    """
    Marketplace buyurtma javobi.

    Ikkita korxona uchun: buyer va supplier ma'lumotlari.
    MP3 maydonlari: courier_id, delivered_at, proof_photo_url, accepted_at.

    Nom maydonlari (faqat list_incoming/list_outgoing da, enrich=True):
      buyer_store_name  — buyer do'kon nomi (buyer_store.name)
      supplier_name     — supplier korxona nomi (supplier_enterprise.name)
      courier_name      — kuryer to'liq ismi (courier.full_name)
    Mutatsiya endpointlari (confirm/reject/ship/deliver/accept) da bular None.
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
    # Nom maydonlari (enrich=True bo'lganda populate qilinadi)
    buyer_store_name: str | None = Field(
        None,
        description="Buyer do'kon nomi (faqat ro'yxat endpointlarida populate qilinadi)",
    )
    supplier_name: str | None = Field(
        None,
        description="Supplier korxona nomi (faqat ro'yxat endpointlarida populate qilinadi)",
    )
    courier_name: str | None = Field(
        None,
        description="Kuryer to'liq ismi (faqat ro'yxat endpointlarida populate qilinadi)",
    )

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


# ─── MP5: Reklama banner sxemalari ───────────────────────────────────────────


class AdBannerCreate(BaseModel):
    """
    POST /marketplace/banners tanasi.

    Korxona o'z reklamasini yaratadi (enterprise-scoped).
    image_url keyinchalik POST /marketplace/banners/{id}/image orqali yuklanadi.
    """

    title: str = Field(..., min_length=1, max_length=255, description="Banner sarlavhasi")
    image_url: str | None = Field(None, description="Banner rasmi URL (ixtiyoriy, yuklab qo'shiladi)")
    target_url: str | None = Field(
        None,
        max_length=2000,
        description="Bosilganda yo'naltiriladigan URL (tashqi havola)",
    )
    target_product_id: uuid.UUID | None = Field(
        None,
        description="Bosilganda yo'naltiriladigan mahsulot UUID (target_url o'rniga)",
    )
    is_active: bool = Field(True, description="Aktiv holat (default True)")
    priority: int = Field(0, ge=0, description="Ko'rsatish ustuvorligi (yuqori = birinchi, default 0)")
    valid_from: date = Field(..., description="Ko'rsatish boshlanish sanasi (YYYY-MM-DD)")
    valid_to: date = Field(..., description="Ko'rsatish tugash sanasi (YYYY-MM-DD)")


class AdBannerPatch(BaseModel):
    """
    PATCH /marketplace/banners/{id} tanasi.

    Faqat berilgan maydonlar yangilanadi (qisman yangilash).
    Korxona faqat O'Z bannerini tahrirlaydi (enterprise-scoped, IDOR-safe).
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    image_url: str | None = Field(None)
    target_url: str | None = Field(None, max_length=2000)
    target_product_id: uuid.UUID | None = Field(None)
    is_active: bool | None = Field(None)
    priority: int | None = Field(None, ge=0)
    valid_from: date | None = Field(None)
    valid_to: date | None = Field(None)


class AdBannerOut(BaseModel):
    """
    Reklama banner javobi.

    enterprise_id qaytadi (kim reklamasi ekanligini bildirish uchun).
    """

    id: uuid.UUID
    enterprise_id: uuid.UUID
    title: str
    image_url: str | None
    target_url: str | None
    target_product_id: uuid.UUID | None
    is_active: bool
    priority: int
    valid_from: date
    valid_to: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedBanners(BaseModel):
    """
    Paginated banner ro'yxati javobi — GET /marketplace/banners/mine uchun.

    Admin o'z korxona bannerlarini (BARCHA holat: aktiv, nofaol, muddati o'tgan) ko'radi.
    """

    items: list[AdBannerOut]
    total: int = Field(..., description="Jami bannerlar soni (filtersiz)")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset = (page-1)*limit")


# ─── MP5: Qaynoq aksiya sxemalari ────────────────────────────────────────────


class MarketplacePromoOut(BaseModel):
    """
    Qaynoq aksiya javobi — GET /marketplace/promos da qaytadi.

    cross-tenant (barcha korxonalar featured aksiyalari).
    supplier_name: aksiya beruvchi korxona nomi.
    Faqat is_active=True + marketplace_featured=True + valid sana.
    """

    id: uuid.UUID
    name_uz: str
    name_ru: str
    promo_type: str
    rule_json: dict
    banner_url: str | None
    valid_from: date
    valid_to: date
    is_active: bool
    marketplace_featured: bool

    # Supplier korxona ma'lumotlari (cross-tenant ko'rsatish uchun)
    enterprise_id: uuid.UUID = Field(..., description="Aksiya beruvchi korxona ID")
    supplier_name: str = Field(..., description="Aksiya beruvchi korxona nomi")

    model_config = {"from_attributes": True}


class PromoMarketplaceToggle(BaseModel):
    """
    PATCH /promos/{id}/marketplace-featured tanasi.

    featured=True → aksiya marketplace'da qaynoq sifatida ko'rinadi.
    featured=False → marketplace'dan olib tashlanadi.
    """

    featured: bool = Field(..., description="True = marketplace qaynoq aksiya, False = olish")
