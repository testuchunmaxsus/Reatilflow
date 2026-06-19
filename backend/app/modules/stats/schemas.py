"""
Statistika moduli sxemalari — T22.

Sxemalar:
  SalesPeriodItem    — davr bo'yicha bitta savdo ma'lumoti
  SalesStatsOut      — savdo statistikasi javobi
  DeliveryStatsOut   — yetkazish statistikasi javobi
  FinanceStoreItem   — bitta do'kon moliyaviy ma'lumoti
  FinanceStatsOut    — moliyaviy statistika javobi
  StatsFilter        — umumiy filter parametrlari (from, to, group_by, branch_id)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ─── Sales statistikasi ───────────────────────────────────────────────────────


class SalesPeriodItem(BaseModel):
    """Davr bo'yicha bitta savdo ma'lumoti (kun/hafta/oy gruppalanganda)."""

    model_config = ConfigDict(from_attributes=True)

    period: str = Field(description="Davr labeli: '2026-06-01' (kun), '2026-W23' (hafta), '2026-06' (oy)")
    order_count: int = Field(ge=0, description="Buyurtmalar soni")
    total_amount: Decimal = Field(description="Jami summa (Decimal aniqlik)")


class SalesStatsOut(BaseModel):
    """Savdo statistikasi javobi.

    sales_stats() servis funksiyasi qaytaradi.
    """

    model_config = ConfigDict(from_attributes=True)

    total_orders: int = Field(ge=0, description="Jami buyurtmalar soni (filtr davri)")
    total_amount: Decimal = Field(description="Jami summa (Decimal aniqlik)")
    currency: str = Field(default="UZS", description="Valyuta kodi (ISO 4217)")
    period_from: datetime | None = Field(None, description="Boshlanish vaqti (filtrdan)")
    period_to: datetime | None = Field(None, description="Tugash vaqti (filtrdan)")
    group_by: str | None = Field(None, description="Guruhlash: day | week | month")
    dynamics: list[SalesPeriodItem] = Field(
        default_factory=list,
        description="Davr bo'yicha dinamika (group_by bo'yicha gruppalangan)"
    )


# ─── Delivery statistikasi ────────────────────────────────────────────────────


class DeliveryStatsOut(BaseModel):
    """Yetkazish statistikasi javobi.

    delivery_stats() servis funksiyasi qaytaradi.
    """

    model_config = ConfigDict(from_attributes=True)

    total_deliveries: int = Field(ge=0, description="Jami yetkazishlar soni")
    delivered_count: int = Field(ge=0, description="Muvaffaqiyatli yetkazilganlar soni")
    failed_count: int = Field(ge=0, description="Muvaffaqiyatsiz yetkazishlar soni")
    in_progress_count: int = Field(ge=0, description="Hozirda jarayondagi yetkazishlar (terminal bo'lmagan)")
    avg_delivery_minutes: Decimal | None = Field(
        None,
        description=(
            "O'rtacha yetkazish vaqti (daqiqa): "
            "started_at → delivered_at oraliq. "
            "Faqat delivered holat uchun. None = hech qachon delivered bo'lmagan."
        )
    )
    period_from: datetime | None = Field(None)
    period_to: datetime | None = Field(None)


# ─── Finance statistikasi ─────────────────────────────────────────────────────


class FinanceStoreItem(BaseModel):
    """Bitta do'kon moliyaviy ma'lumoti."""

    model_config = ConfigDict(from_attributes=True)

    store_id: uuid.UUID = Field(description="Do'kon UUID")
    store_name: str = Field(description="Do'kon nomi")
    total_debit: Decimal = Field(description="Jami debit (qarz oshgan miqdor)")
    total_credit: Decimal = Field(description="Jami kredit (to'lov/kamaytirish miqdori)")
    balance: Decimal = Field(description="Joriy balans: >0 qarz, <0 ortiqcha kredit")
    currency: str = Field(default="UZS", description="Valyuta kodi")


class FinanceStatsOut(BaseModel):
    """Moliyaviy statistika javobi.

    finance_stats() servis funksiyasi qaytaradi.
    PRIMARY DB dan o'qiladi (ADR §3.8).
    """

    model_config = ConfigDict(from_attributes=True)

    total_debit: Decimal = Field(description="Jami barcha do'konlar debit summasi")
    total_credit: Decimal = Field(description="Jami barcha do'konlar kredit summasi")
    net_balance: Decimal = Field(description="Sof balans: total_debit - total_credit")
    stores: list[FinanceStoreItem] = Field(
        default_factory=list,
        description="Do'kon bo'yicha batafsil moliyaviy ma'lumot"
    )
    period_from: datetime | None = Field(None)
    period_to: datetime | None = Field(None)
