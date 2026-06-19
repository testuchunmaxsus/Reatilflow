"""
Contracts moduli Pydantic v2 sxemalari — shartnoma CRUD.

Sxemalar:
  ContractCreate    — yangi shartnoma yaratish
  ContractUpdate    — shartnoma yangilash (PATCH, optimistik lock)
  ContractOut       — javob sxemasi (status DERIVED)
  PaginatedContracts — paginated shartnomalar ro'yxati

status DERIVED:
  valid_to ga qarab hisoblanadi:
    expired  : valid_to < bugun
    expiring : valid_to - bugun <= 30 kun
    active   : boshqa
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


# ─── ContractCreate ──────────────────────────────────────────────────────────


class ContractCreate(BaseModel):
    """Yangi shartnoma yaratish so'rovi."""

    store_id: uuid.UUID = Field(..., description="Do'kon ID (FK → store)")
    number: str = Field(..., min_length=1, max_length=100, description="Shartnoma raqami")
    valid_from: date = Field(..., description="Amal boshlanishi (YYYY-MM-DD)")
    valid_to: date = Field(..., description="Amal tugashi (YYYY-MM-DD)")
    signed_at: datetime | None = Field(None, description="Imzolangan vaqt (UTC, ixtiyoriy)")
    contract_type: str | None = Field(
        None,
        max_length=50,
        description="Turi: trade | employment | service | other",
    )
    branch_id: uuid.UUID | None = Field(None, description="Filial ID (ixtiyoriy)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    @model_validator(mode="after")
    def valid_to_after_valid_from(self) -> "ContractCreate":
        """valid_to >= valid_from bo'lishi shart."""
        if self.valid_to < self.valid_from:
            raise ValueError(
                "valid_to valid_from dan oldin bo'lishi mumkin emas"
            )
        return self


# ─── ContractUpdate ──────────────────────────────────────────────────────────


class ContractUpdate(BaseModel):
    """Shartnoma yangilash so'rovi (PATCH — faqat berilgan maydonlar)."""

    number: str | None = Field(None, min_length=1, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    signed_at: datetime | None = None
    contract_type: str | None = Field(None, max_length=50)
    branch_id: uuid.UUID | None = None
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ContractUpdate":
        """version dan tashqari kamida bitta maydon berilishi shart."""
        fields = {"number", "valid_from", "valid_to", "signed_at", "contract_type", "branch_id"}
        if not any(getattr(self, f) is not None for f in fields):
            raise ValueError("Kamida bitta maydon yangilanishi shart")
        return self


# ─── ContractOut ─────────────────────────────────────────────────────────────


class ContractOut(BaseModel):
    """Shartnoma javob sxemasi (status DERIVED)."""

    id: uuid.UUID
    store_id: uuid.UUID
    number: str
    file_url: str | None
    signed_at: datetime | None
    valid_from: date
    valid_to: date
    contract_type: str | None
    branch_id: uuid.UUID | None
    client_uuid: uuid.UUID | None
    status: str  # "active" | "expiring" | "expired" — DERIVED from valid_to
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── PaginatedContracts ───────────────────────────────────────────────────────


class PaginatedContracts(BaseModel):
    """Paginated shartnomalar ro'yxati javob sxemasi."""

    items: list[ContractOut]
    total: int = Field(..., description="Jami topilgan shartnomalar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
