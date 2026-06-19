"""
Ombor moduli Pydantic v2 sxemalari.

Sxemalar:
  StockMovementCreate  — yangi harakatni qayd etish
  StockMovementOut     — harakat javob sxemasi
  StockBalanceOut      — qoldiq javob sxemasi
  PaginatedMovements   — paginated harakatlar ro'yxati

Xavfsizlik:
  - qty — Decimal (float emas; moliyaviy aniqlik).
  - type — faqat to'g'ri qiymatlar (in | out | transfer | adjust).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# ─── Ruxsat etilgan harakat turlari ──────────────────────────────────────────

VALID_MOVEMENT_TYPES = frozenset({"in", "out", "transfer", "adjust"})


# ─── StockMovementCreate ──────────────────────────────────────────────────────


class StockMovementCreate(BaseModel):
    """Yangi ombor harakatini qayd etish so'rovi."""

    product_id: uuid.UUID = Field(..., description="Mahsulot ID (FK → product)")
    warehouse_id: uuid.UUID = Field(..., description="Ombor/sklad ID")
    type: str = Field(..., description="Harakat turi: in | out | transfer | adjust")
    qty: Decimal = Field(
        ...,
        description=(
            "Miqdor (Decimal, musbat). "
            "adjust turi FAQAT OSHIRADI (delta += qty). "
            "Kamaytirish uchun 'out' turini ishlating."
        ),
    )
    ref_type: str | None = Field(None, max_length=100, description="Havola turi (ixtiyoriy)")
    ref_id: uuid.UUID | None = Field(None, description="Havola ID (ixtiyoriy)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_MOVEMENT_TYPES:
            raise ValueError(f"Harakat turi noto'g'ri: faqat {sorted(VALID_MOVEMENT_TYPES)} qabul qilinadi")
        return v

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("qty noldan katta bo'lishi shart")
        return v


# ─── StockMovementOut ─────────────────────────────────────────────────────────


class StockMovementOut(BaseModel):
    """Ombor harakati javob sxemasi."""

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    type: str
    qty: Decimal
    ref_type: str | None
    ref_id: uuid.UUID | None
    moved_by: uuid.UUID | None
    moved_at: datetime
    client_uuid: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── StockBalanceOut ──────────────────────────────────────────────────────────


class StockBalanceOut(BaseModel):
    """Ombor qoldig'i javob sxemasi."""

    id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    qty_on_hand: Decimal
    qty_reserved: Decimal
    version: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── PaginatedMovements ───────────────────────────────────────────────────────


class PaginatedMovements(BaseModel):
    """Paginated ombor harakatlari ro'yxati javob sxemasi."""

    items: list[StockMovementOut]
    total: int = Field(..., description="Jami topilgan harakatlar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
