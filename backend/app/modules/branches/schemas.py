"""
Branches moduli Pydantic v2 sxemalari — filiallar CRUD.

Sxemalar:
  BranchCreate       — yangi filial yaratish
  BranchUpdate       — filial yangilash (PATCH, optimistik lock)
  BranchOut          — to'liq javob
  PaginatedBranches  — paginated filiallar ro'yxati
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


# ─── BranchCreate ─────────────────────────────────────────────────────────────


class BranchCreate(BaseModel):
    """Yangi filial yaratish so'rovi."""

    name: str = Field(..., min_length=1, max_length=255, description="Filial nomi")
    address: str | None = Field(None, max_length=500, description="Filial manzili")
    phone: str | None = Field(None, max_length=50, description="Filial telefon raqami")


# ─── BranchUpdate ─────────────────────────────────────────────────────────────


class BranchUpdate(BaseModel):
    """Filial yangilash so'rovi (PATCH — faqat berilgan maydonlar yangilanadi)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BranchUpdate":
        """version dan tashqari kamida bitta maydon berilishi shart."""
        fields = {"name", "address", "phone", "is_active"}
        if not any(getattr(self, f) is not None for f in fields):
            raise ValueError("Kamida bitta maydon yangilanishi shart")
        return self


# ─── BranchOut ────────────────────────────────────────────────────────────────


class BranchOut(BaseModel):
    """Filial to'liq javob sxemasi."""

    id: uuid.UUID
    enterprise_id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── PaginatedBranches ────────────────────────────────────────────────────────


class PaginatedBranches(BaseModel):
    """Paginated filiallar ro'yxati javob sxemasi."""

    items: list[BranchOut]
    total: int = Field(..., description="Jami topilgan filiallar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
