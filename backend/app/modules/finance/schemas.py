"""
Buxgalteriya moduli Pydantic v2 sxemalari.

Sxemalar:
  LedgerEntryCreate  — yangi yozuvni qayd etish
  LedgerEntryOut     — yozuv javob sxemasi
  LedgerApproveOut   — tasdiqlash javob sxemasi
  AccountBalanceOut  — balans javob sxemasi
  PaginatedLedger    — paginated yozuvlar ro'yxati

Xavfsizlik:
  - amount — Decimal (float emas; moliyaviy aniqlik).
  - type — faqat to'g'ri qiymatlar (debit | credit).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# ─── Ruxsat etilgan yozuv turlari ────────────────────────────────────────────

VALID_ENTRY_TYPES = frozenset({"debit", "credit"})


# ─── LedgerEntryCreate ────────────────────────────────────────────────────────


class LedgerEntryCreate(BaseModel):
    """Yangi buxgalteriya yozuvini qayd etish so'rovi."""

    store_id: uuid.UUID = Field(..., description="Do'kon ID (FK → store)")
    type: str = Field(..., description="Yozuv turi: debit | credit")
    amount: Decimal = Field(..., description="Miqdor (Decimal, noldan katta, musbat)")
    currency: str = Field("UZS", max_length=3, description="Valyuta kodi (ISO 4217)")
    ref_type: str | None = Field(None, max_length=100, description="Havola turi (ixtiyoriy)")
    ref_id: uuid.UUID | None = Field(None, description="Havola ID (ixtiyoriy)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_ENTRY_TYPES:
            raise ValueError(f"Yozuv turi noto'g'ri: faqat {sorted(VALID_ENTRY_TYPES)} qabul qilinadi")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("amount noldan katta bo'lishi shart")
        return v


# ─── LedgerEntryOut ───────────────────────────────────────────────────────────


class LedgerEntryOut(BaseModel):
    """Buxgalteriya yozuvi javob sxemasi."""

    id: uuid.UUID
    store_id: uuid.UUID
    type: str
    amount: Decimal
    currency: str
    ref_type: str | None
    ref_id: uuid.UUID | None
    entry_date: datetime
    created_by: uuid.UUID | None
    client_uuid: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── LedgerApproveOut ─────────────────────────────────────────────────────────


class LedgerApproveOut(BaseModel):
    """
    Tasdiqlash operatsiyasi javob sxemasi.

    ledger_approval jadvalidan yaratiladi (entry_id bo'yicha).
    ledger_entry APPEND-ONLY bo'lgani uchun holat alohida jadvalda saqlanadi.
    """

    id: uuid.UUID
    entry_id: uuid.UUID
    approved_by: uuid.UUID
    approved_at: datetime

    model_config = {"from_attributes": True}


# ─── AccountBalanceOut ────────────────────────────────────────────────────────


class AccountBalanceOut(BaseModel):
    """Do'kon buxgalteriya balansi javob sxemasi."""

    id: uuid.UUID
    store_id: uuid.UUID
    balance: Decimal
    currency: str
    last_recalc_at: datetime
    version: int

    model_config = {"from_attributes": True}


# ─── PaginatedLedger ─────────────────────────────────────────────────────────


class PaginatedLedger(BaseModel):
    """Paginated buxgalteriya yozuvlari ro'yxati javob sxemasi."""

    items: list[LedgerEntryOut]
    total: int = Field(..., description="Jami topilgan yozuvlar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
