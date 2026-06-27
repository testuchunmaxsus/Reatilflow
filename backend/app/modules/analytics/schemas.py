"""
AI Tahlil moduli sxemalari — Faza 4.

Sxemalar:
  OverviewOut          — KPI kartalar javobi
  ContractedStoreItem  — Bitta do'kon holati
  ContractedStoresOut  — Shartnoma qilgan do'konlar ro'yxati
  GeoVelocityItem      — Bitta do'kon geo-sotuv tezligi
  GeoVelocityOut       — Geografik savdo tezligi javobi
  ExpiryItem           — Bitta muddati o'tayotgan partiya
  ExpiryReportOut      — Expiry hisoboti javobi
  ProductRankingItem   — Bitta mahsulot reytingi
  ProductRankingOut    — Top/kam mahsulotlar javobi
  RecommendationItem   — Bitta tavsiya (rule-based)
  RecommendationsOut   — Tavsiyalar javobi
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ─── Overview (KPI kartalar) ──────────────────────────────────────────────────


class ContractStatusCounts(BaseModel):
    """Shartnoma holati bo'yicha soni."""

    model_config = ConfigDict(from_attributes=True)

    active: int = Field(ge=0, description="Faol shartnomalar soni")
    expiring: int = Field(ge=0, description="Tugayotgan shartnomalar soni (≤30 kun)")
    expired: int = Field(ge=0, description="Muddati o'tgan shartnomalar soni")


class OverviewOut(BaseModel):
    """KPI kartalar javobi.

    overview() servis funksiyasi qaytaradi.
    """

    model_config = ConfigDict(from_attributes=True)

    contracted_store_count: int = Field(ge=0, description="Jami shartnomadagi do'konlar soni")
    contract_status: ContractStatusCounts = Field(description="Shartnoma holati bo'yicha soni")
    sold_qty_total: Decimal = Field(description="Tanlangan davrda jami sotilgan miqdor")
    revenue_total: Decimal = Field(description="Tanlangan davrda jami sotuv summasi (Decimal)")
    expiry_risk_count: int = Field(ge=0, description="7 kun ichida muddati o'tayotgan SKU soni")
    period_from: datetime | None = Field(None, description="Boshlanish vaqti (filtrdan)")
    period_to: datetime | None = Field(None, description="Tugash vaqti (filtrdan)")


# ─── Contracted Stores ────────────────────────────────────────────────────────


class ContractedStoreItem(BaseModel):
    """Bitta shartnomadagi do'kon ma'lumoti."""

    model_config = ConfigDict(from_attributes=True)

    store_id: uuid.UUID = Field(description="Do'kon UUID")
    store_name: str = Field(description="Do'kon nomi")
    contract_status: str = Field(description="Shartnoma holati: active | expiring | expired")
    valid_to: date = Field(description="Shartnoma muddati tugash sanasi")
    inventory_qty: Decimal = Field(description="Do'kondagi mening mahsulotlarimning jami miqdori")
    sold_qty_30d: Decimal = Field(description="So'nggi 30 kunda sotilgan miqdor")
    gps_lat: Decimal | None = Field(None, description="Kenglik (GPS)")
    gps_lng: Decimal | None = Field(None, description="Uzunlik (GPS)")
    address: str | None = Field(None, description="Manzil")


class ContractedStoresOut(BaseModel):
    """Shartnoma qilgan do'konlar ro'yxati javobi."""

    model_config = ConfigDict(from_attributes=True)

    stores: list[ContractedStoreItem] = Field(default_factory=list)
    total: int = Field(ge=0, description="Jami do'konlar soni")


# ─── Geo Velocity ─────────────────────────────────────────────────────────────


class GeoVelocityItem(BaseModel):
    """Bitta do'kon geografik sotuv tezligi."""

    model_config = ConfigDict(from_attributes=True)

    store_id: uuid.UUID = Field(description="Do'kon UUID")
    store_name: str = Field(description="Do'kon nomi")
    gps_lat: Decimal | None = Field(None, description="Kenglik koordinatasi")
    gps_lng: Decimal | None = Field(None, description="Uzunlik koordinatasi")
    address: str | None = Field(None, description="Manzil")
    sold_qty: Decimal = Field(description="Tanlangan davrda sotilgan jami miqdor")
    revenue: Decimal = Field(description="Tanlangan davrda sotuv summasi")
    velocity_per_day: Decimal = Field(description="Kunlik sotuv tezligi (qty/kun)")


class GeoVelocityOut(BaseModel):
    """Geografik savdo tezligi javobi."""

    model_config = ConfigDict(from_attributes=True)

    items: list[GeoVelocityItem] = Field(default_factory=list)
    period_from: datetime | None = Field(None)
    period_to: datetime | None = Field(None)
    period_days: int = Field(ge=1, description="Davr davomiyligi (kun)")


# ─── Expiry Report ────────────────────────────────────────────────────────────


class ExpiryItem(BaseModel):
    """Bitta muddati o'tayotgan inventar partiyasi."""

    model_config = ConfigDict(from_attributes=True)

    inventory_id: uuid.UUID = Field(description="StoreInventory UUID")
    store_id: uuid.UUID = Field(description="Do'kon UUID")
    store_name: str = Field(description="Do'kon nomi")
    product_id: uuid.UUID = Field(description="Mahsulot UUID")
    product_name: str = Field(description="Mahsulot nomi (uz)")
    qty: Decimal = Field(description="Inventardagi miqdor")
    expiry_date: date = Field(description="Yaroqlilik muddati")
    days_left: int = Field(description="Qolgan kunlar (manfiy = muddati o'tgan)")
    severity: str = Field(description="Jiddilik: expired | urgent | warning")


class ExpiryReportOut(BaseModel):
    """Expiry hisoboti javobi."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ExpiryItem] = Field(default_factory=list)
    total: int = Field(ge=0)
    within_days: int = Field(ge=1, description="Filtr: N kun ichida")


# ─── Product Ranking ──────────────────────────────────────────────────────────


class ProductRankingItem(BaseModel):
    """Bitta mahsulot reytingi."""

    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID = Field(description="Mahsulot UUID")
    product_name: str = Field(description="Mahsulot nomi (uz)")
    sold_qty: Decimal = Field(description="Sotilgan miqdor")
    revenue: Decimal = Field(description="Sotuv summasi")
    store_count: int = Field(ge=0, description="Nechta do'konda sotilgan")
    rank: int = Field(ge=1, description="Tartib raqami")


class ProductRankingOut(BaseModel):
    """Top/kam mahsulotlar javobi."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ProductRankingItem] = Field(default_factory=list)
    order: str = Field(description="Tartib: top | bottom")
    period_from: datetime | None = Field(None)
    period_to: datetime | None = Field(None)


# ─── Recommendations ─────────────────────────────────────────────────────────


class RecommendationItem(BaseModel):
    """Bitta tavsiya (rule-based)."""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(description="Tavsiya kodi: R1_expiry_urgent | R2_expiry_warn | R3_restock | R4_slow_mover | R5_geo_hotspot")
    severity: str = Field(description="Jiddilik: high | medium | low | info")
    title_uz: str = Field(description="Tavsiya sarlavhasi (o'zbekcha)")
    detail_uz: str = Field(description="Batafsil tavsiya matni (o'zbekcha)")
    store_id: uuid.UUID | None = Field(None, description="Tegishli do'kon (ixtiyoriy)")
    product_id: uuid.UUID | None = Field(None, description="Tegishli mahsulot (ixtiyoriy)")
    metric: dict = Field(default_factory=dict, description="Tavsiya uchun asos bo'lgan metrika raqamlari")


class RecommendationsOut(BaseModel):
    """Tavsiyalar javobi (rule-based + ixtiyoriy Claude-boyitilgan)."""

    model_config = ConfigDict(from_attributes=True)

    recommendations: list[RecommendationItem] = Field(default_factory=list)
    ai_summary: str | None = Field(
        None,
        description="Claude AI tomonidan boyitilgan umumiy xulosa (ANTHROPIC_API_KEY bo'lsa; aks holda None)",
    )
    ai_enabled: bool = Field(
        default=False,
        description="True — Claude boyitish ishladi; False — rule-based fallback",
    )
    generated_at: datetime = Field(description="Tavsiya yaratilgan vaqt (UTC)")
