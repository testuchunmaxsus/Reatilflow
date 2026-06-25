"""
Customers moduli Pydantic v2 sxemalari — do'konlar CRUD.

Sxemalar:
  StoreCreate           — yangi do'kon yaratish
  StoreUpdate           — do'kon yangilash (PATCH, optimistik lock)
  StoreOut              — to'liq javob (admin/accountant/agent o'z do'koni uchun)
  StoreLimitedOut       — cheklangan javob (kuryer: faqat manzil/koordinata; PII yo'q)
  AssignAgentRequest    — agentni do'konga biriktirish
  PaginatedStores       — paginated do'konlar ro'yxati

Xavfsizlik:
  - StoreLimitedOut da inn/inps/credit_limit/phone YO'Q (kuryer uchun).
  - credit_limit Decimal (moliyaviy aniqlik uchun float emas).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── StoreCreate ─────────────────────────────────────────────────────────────


class StoreCreate(BaseModel):
    """Yangi do'kon yaratish so'rovi."""

    name: str = Field(..., min_length=1, max_length=255, description="Do'kon nomi")
    inn: str | None = Field(None, max_length=20, description="INN (PII, shifrlanadi)")
    inps: str | None = Field(None, max_length=20, description="INPS (PII, shifrlanadi)")
    owner_name: str | None = Field(None, max_length=255, description="Egasi ismi (PII, shifrlanadi)")
    phone: str | None = Field(None, max_length=20, description="Telefon (PII, shifrlanadi)")
    address: str | None = Field(None, description="Manzil (matnli)")
    gps_lat: Decimal | None = Field(None, description="Kenglik koordinatasi (-90..90)")
    gps_lng: Decimal | None = Field(None, description="Uzunlik koordinatasi (-180..180)")
    segment_id: uuid.UUID | None = Field(None, description="Narx segmenti ID")

    @field_validator("gps_lat")
    @classmethod
    def validate_gps_lat(cls, v: Decimal | None) -> Decimal | None:
        """Kenglik: -90 dan 90 gacha."""
        if v is not None and not (Decimal("-90") <= v <= Decimal("90")):
            raise ValueError("gps_lat -90 va 90 oralig'ida bo'lishi kerak")
        return v

    @field_validator("gps_lng")
    @classmethod
    def validate_gps_lng(cls, v: Decimal | None) -> Decimal | None:
        """Uzunlik: -180 dan 180 gacha."""
        if v is not None and not (Decimal("-180") <= v <= Decimal("180")):
            raise ValueError("gps_lng -180 va 180 oralig'ida bo'lishi kerak")
        return v
    agent_id: uuid.UUID | None = Field(None, description="Asosiy agent ID")
    branch_id: uuid.UUID | None = Field(None, description="Filial ID")
    credit_limit: Decimal | None = Field(None, description="Kredit limiti (so'm)")
    user_id: uuid.UUID | None = Field(None, description="Do'kon egasi (app_user FK)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")


# ─── StoreUpdate ─────────────────────────────────────────────────────────────


class StoreUpdate(BaseModel):
    """Do'kon yangilash so'rovi (PATCH — faqat berilgan maydonlar yangilanadi)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    inn: str | None = Field(None, max_length=20)
    inps: str | None = Field(None, max_length=20)
    owner_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    address: str | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None
    segment_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    credit_limit: Decimal | None = None
    user_id: uuid.UUID | None = None
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "StoreUpdate":
        """version dan tashqari kamida bitta maydon berilishi shart."""
        fields = {
            "name", "inn", "inps", "owner_name", "phone", "address",
            "gps_lat", "gps_lng", "segment_id", "agent_id", "branch_id",
            "credit_limit", "user_id",
        }
        if not any(getattr(self, f) is not None for f in fields):
            raise ValueError("Kamida bitta maydon yangilanishi shart")
        return self


# ─── StoreOut (to'liq) ───────────────────────────────────────────────────────


class StoreOut(BaseModel):
    """
    Do'kon to'liq javob sxemasi.

    Admin, accountant, agent (o'z do'koni) uchun — barcha maydonlar.
    PII maydonlar (inn, inps, owner_name, phone) deshifrlanib qaytadi.
    """

    id: uuid.UUID
    name: str
    inn: str | None
    inps: str | None
    owner_name: str | None
    phone: str | None
    address: str | None
    gps_lat: Decimal | None
    gps_lng: Decimal | None
    segment_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    credit_limit: Decimal | None
    user_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── StoreLimitedOut (kuryer uchun cheklangan) ────────────────────────────────


class StoreLimitedOut(BaseModel):
    """
    Do'kon cheklangan javob sxemasi — kuryer uchun.

    Faqat manzil va koordinata ma'lumotlari.
    PII (inn, inps, owner_name, phone) va moliyaviy (credit_limit) maydonlar YO'Q.

    Xavfsizlik: T2 reviewer topilmasi — kuryer rolida moliyaviy/PII oqib ketmasin.
    """

    id: uuid.UUID
    name: str
    address: str | None
    gps_lat: Decimal | None
    gps_lng: Decimal | None

    model_config = {"from_attributes": True}


# ─── AssignAgentRequest ───────────────────────────────────────────────────────


class AssignAgentRequest(BaseModel):
    """Do'konga agent biriktirish so'rovi."""

    agent_id: uuid.UUID = Field(..., description="Biriktiriladigan agent ID")


# ─── PaginatedStores ─────────────────────────────────────────────────────────


class PaginatedStores(BaseModel):
    """Paginated do'konlar ro'yxati javob sxemasi."""

    items: list[StoreOut]
    total: int = Field(..., description="Jami topilgan do'konlar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
