"""
POS moduli Pydantic v2 sxemalari.

Sxemalar:
  PosSaleLineIn   — sotuv qatori kiritish (product_id + qty; narx YO'Q)
  PosSaleCreate   — yangi sotuv yaratish so'rovi (checkout)
  PosSaleLineOut  — qator javob
  PosSaleOut      — sotuv javob (to'liq, kvitansiya uchun)
  PaginatedSales  — paginated sotuvlar ro'yxati
  DailySummaryOut — kunlik statistika

Xavfsizlik qarorlari (T11 pattern):
  - unit_price YO'Q: klient narx bera olmaydi. Narx FAQAT server tomonida
    katalogdan (do'kon segmenti bo'yicha) olinadi.
  - discount YO'Q: klient chegirma bera olmaydi; server hisoblaydi.
  - enterprise_id YO'Q: server'dan (user.enterprise_id) olinadi.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.pos import POS_PAYMENT_METHODS

# ─── PosSaleLineIn ────────────────────────────────────────────────────────────


class PosSaleLineIn(BaseModel):
    """
    Sotuv qatori — POST /pos/sales so'rovi ichida.

    XAVFSIZLIK (CRITICAL):
      - unit_price YO'Q: narx server tomonida katalogdan olinadi.
      - discount YO'Q: chegirma klient tomonidan belgilanmaydi.
    """

    product_id: uuid.UUID = Field(..., description="Mahsulot ID (FK → product)")
    qty: Decimal = Field(
        ...,
        gt=Decimal("0"),
        description="Miqdor (Decimal, musbat, 0 dan katta)",
    )

    @field_validator("qty")
    @classmethod
    def qty_positive(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("qty musbat bo'lishi kerak")
        return v


# ─── PosSaleCreate ────────────────────────────────────────────────────────────


class PosSaleCreate(BaseModel):
    """Yangi POS sotuvi yaratish so'rovi (checkout)."""

    store_id: uuid.UUID = Field(..., description="Do'kon ID (FK → store)")
    payment_method: str = Field(
        ...,
        description="To'lov usuli: cash | card",
    )
    lines: list[PosSaleLineIn] = Field(
        ...,
        min_length=1,
        description="Sotuv qatorlari (kamida bitta bo'lishi shart)",
    )
    customer_phone: str | None = Field(
        None,
        max_length=50,
        description="Xaridor telefon raqami (ixtiyoriy)",
    )
    client_uuid: uuid.UUID | None = Field(
        None,
        description="Idempotentlik UUID (ixtiyoriy) — bir xil UUID → bir xil sotuv",
    )

    @field_validator("payment_method")
    @classmethod
    def payment_method_valid(cls, v: str) -> str:
        if v not in POS_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method '{v}' noto'g'ri: faqat {sorted(POS_PAYMENT_METHODS)} qabul qilinadi"
            )
        return v


# ─── PosSaleLineOut ───────────────────────────────────────────────────────────


class PosSaleLineOut(BaseModel):
    """Sotuv qatori javob sxemasi."""

    id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


# ─── PosSaleOut ───────────────────────────────────────────────────────────────


class PosSaleOut(BaseModel):
    """
    Sotuv javob sxemasi — kvitansiya ma'lumoti.

    lines — selectin loader orqali yuklanadi (N+1 yo'q).
    """

    id: uuid.UUID
    store_id: uuid.UUID
    cashier_id: uuid.UUID | None
    enterprise_id: uuid.UUID | None
    total_amount: Decimal
    discount_amount: Decimal
    payment_method: str
    customer_phone: str | None
    status: str
    client_uuid: uuid.UUID | None
    created_at: datetime
    lines: list[PosSaleLineOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ─── PaginatedSales ───────────────────────────────────────────────────────────


class PaginatedSales(BaseModel):
    """Paginated POS sotuvlar ro'yxati."""

    items: list[PosSaleOut]
    total: int
    limit: int
    offset: int


# ─── DailySummaryOut ──────────────────────────────────────────────────────────


class PaymentMethodSummary(BaseModel):
    """To'lov usuli bo'yicha kunlik statistika."""

    payment_method: str
    count: int
    total_amount: Decimal


class DailySummaryOut(BaseModel):
    """
    Kunlik POS statistika.

    total_sales    — umumiy sotuv soni
    total_amount   — umumiy sotuv summasi
    by_payment     — to'lov usuli bo'yicha breakdown
    """

    date: date
    total_sales: int
    total_amount: Decimal
    by_payment: list[PaymentMethodSummary] = Field(default_factory=list)
