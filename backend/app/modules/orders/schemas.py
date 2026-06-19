"""
Buyurtma moduli Pydantic v2 sxemalari — T11, T12.

Sxemalar:
  OrderLineIn        — buyurtma qatori kiritish (POST so'rovi ichida)
  OrderCreate        — yangi buyurtma yaratish so'rovi
  OrderLineOut       — qator javob
  OrderOut           — buyurtma javob (to'liq)
  OrderStatusUpdate  — holat o'zgartirish so'rovi
  PaginatedOrders    — paginated buyurtmalar ro'yxati
  TemplateLineIn     — shablon qatori kiritish (product_id + qty, narx YO'Q)
  OrderTemplateCreate — yangi shablon yaratish so'rovi
  OrderTemplateOut   — shablon javob (to'liq)
  PaginatedTemplates — paginated shablonlar ro'yxati
  ApplyTemplateIn    — shablon apply so'rovi (client_uuid ixtiyoriy)

Xavfsizlik qarorlari:
  - unit_price OLIB TASHLANDI: narx faqat server tomonda katalogdan olinadi.
  - segment_id OLIB TASHLANDI: segment do'kon (Store.segment_id) dan server tomonida olinadi.
  - discount OLIB TASHLANDI: narx manipulyatsiyasi yo'li yopildi; kelajakda T25 promo logikasi.
  - T12: shablonda narx SAQLANMAYDI — faqat product_id + qty.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# ─── Ruxsat etilgan qiymatlar ────────────────────────────────────────────────

VALID_MODES = frozenset({"bozor", "oddiy"})
VALID_STATUSES = frozenset({
    "draft", "confirmed", "packed", "delivering", "delivered", "canceled",
})


# ─── OrderLineIn ─────────────────────────────────────────────────────────────


class OrderLineIn(BaseModel):
    """
    Buyurtma qatori — POST /orders so'rovi ichida.

    Xavfsizlik (CRITICAL):
      - unit_price YO'Q: klient narx bera olmaydi. Narx FAQAT server tomonida
        katalogdan (do'kon segmenti bo'yicha) olinadi.
      - segment_id YO'Q: segment do'kon (Store.segment_id) dan olinadi.
      - discount YO'Q: chegirma klient tomonidan belgilanmaydi (T25 da promo logikasi).
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


# ─── OrderCreate ─────────────────────────────────────────────────────────────


class OrderCreate(BaseModel):
    """Yangi buyurtma yaratish so'rovi."""

    store_id: uuid.UUID = Field(..., description="Do'kon ID (FK → store)")
    mode: str = Field("oddiy", description="Rejim: bozor | oddiy")
    lines: list[OrderLineIn] = Field(
        ...,
        min_length=1,
        description="Buyurtma qatorlari (kamida bitta bo'lishi shart)",
    )
    client_uuid: uuid.UUID | None = Field(
        None,
        description="Idempotentlik UUID (ixtiyoriy, offline retry uchun)",
    )
    currency: str = Field("UZS", max_length=3, description="Valyuta kodi (ISO 4217)")
    warehouse_id: uuid.UUID | None = Field(
        None,
        description="Ombor ID — stock chiqimi uchun (berilmasa DEFAULT_WAREHOUSE ishlatiladi)",
    )

    @field_validator("mode")
    @classmethod
    def mode_valid(cls, v: str) -> str:
        if v not in VALID_MODES:
            raise ValueError(f"mode qiymati noto'g'ri: {v!r}; ruxsat etilgan: bozor | oddiy")
        return v

    @field_validator("lines")
    @classmethod
    def lines_not_empty(cls, v: list[OrderLineIn]) -> list[OrderLineIn]:
        if not v:
            raise ValueError("lines bo'sh bo'lishi mumkin emas")
        return v


# ─── OrderLineOut ─────────────────────────────────────────────────────────────


class OrderLineOut(BaseModel):
    """Buyurtma qatori javob sxemasi."""

    id: uuid.UUID
    order_id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal
    unit_price: Decimal
    segment_id: uuid.UUID | None
    discount: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


# ─── OrderOut ─────────────────────────────────────────────────────────────────


class OrderOut(BaseModel):
    """Buyurtma javob sxemasi (to'liq)."""

    id: uuid.UUID
    store_id: uuid.UUID
    agent_id: uuid.UUID | None
    mode: str
    status: str
    total_amount: Decimal
    currency: str
    ordered_at: datetime
    client_uuid: uuid.UUID | None
    branch_id: uuid.UUID | None
    warehouse_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    lines: list[OrderLineOut]

    model_config = {"from_attributes": True}


# ─── OrderStatusUpdate ────────────────────────────────────────────────────────


class OrderStatusUpdate(BaseModel):
    """Buyurtma holatini o'zgartirish so'rovi."""

    status: str = Field(..., description="Yangi holat: confirmed | packed | delivering | delivered | canceled")
    version: int = Field(..., description="Joriy versiya (optimistik lock uchun)")

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"status qiymati noto'g'ri: {v!r}; "
                f"ruxsat etilgan: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v


# ─── PaginatedOrders ─────────────────────────────────────────────────────────


class PaginatedOrders(BaseModel):
    """Paginated buyurtmalar ro'yxati javobi."""

    items: list[OrderOut]
    total: int
    limit: int
    offset: int


# ─── T12: Shablon sxemalari ──────────────────────────────────────────────────


class TemplateLineIn(BaseModel):
    """
    Shablon qatori kiritish.

    MUHIM: narx (unit_price) YO'Q — narx FAQAT apply paytida katalogdan olinadi.
    Shablon faqat product_id va qty saqlaydi.
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


class OrderTemplateCreate(BaseModel):
    """Yangi shablon yaratish so'rovi."""

    store_id: uuid.UUID = Field(..., description="Do'kon ID (FK → store)")
    name: str = Field(..., min_length=1, max_length=255, description="Shablon nomi")
    lines: list[TemplateLineIn] = Field(
        ...,
        min_length=1,
        description="Shablon qatorlari (kamida bitta bo'lishi shart)",
    )

    @field_validator("lines")
    @classmethod
    def lines_not_empty(cls, v: list[TemplateLineIn]) -> list[TemplateLineIn]:
        if not v:
            raise ValueError("lines bo'sh bo'lishi mumkin emas")
        return v


class TemplateLineOut(BaseModel):
    """Shablon qatori javob sxemasi (narx YO'Q)."""

    id: uuid.UUID
    template_id: uuid.UUID
    product_id: uuid.UUID
    qty: Decimal

    model_config = {"from_attributes": True}


class OrderTemplateOut(BaseModel):
    """Shablon javob sxemasi (to'liq)."""

    id: uuid.UUID
    store_id: uuid.UUID
    name: str
    created_by: uuid.UUID | None
    branch_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    lines: list[TemplateLineOut]

    model_config = {"from_attributes": True}


class PaginatedTemplates(BaseModel):
    """Paginated shablonlar ro'yxati javobi."""

    items: list[OrderTemplateOut]
    total: int
    limit: int
    offset: int


class ApplyTemplateIn(BaseModel):
    """
    Shablon apply so'rovi.

    client_uuid — idempotentlik uchun (ixtiyoriy, offline retry).
    mode — buyurtma rejimi (ixtiyoriy, default: "oddiy").
    """

    client_uuid: uuid.UUID | None = Field(
        None,
        description="Idempotentlik UUID (ixtiyoriy, offline retry uchun)",
    )
    mode: str = Field("oddiy", description="Rejim: bozor | oddiy")
    currency: str = Field("UZS", max_length=3, description="Valyuta kodi (ISO 4217)")

    @field_validator("mode")
    @classmethod
    def mode_valid(cls, v: str) -> str:
        if v not in VALID_MODES:
            raise ValueError(f"mode qiymati noto'g'ri: {v!r}; ruxsat etilgan: bozor | oddiy")
        return v
