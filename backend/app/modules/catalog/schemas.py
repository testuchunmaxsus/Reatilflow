"""
Katalog moduli Pydantic v2 sxemalari.

Sxemalar:
  CategoryCreate, CategoryOut          — kategoriya CRUD
  PriceSegmentCreate, PriceSegmentOut  — narx segmenti CRUD
  PriceSet, PriceOut                   — narx o'rnatish / chiqish
  ProductCreate, ProductUpdate, ProductOut — mahsulot CRUD
  PaginatedProducts                    — paginated ro'yxat javob

ProductOut da `name` maydoni joriy locale bo'yicha lokalizatsiya qilingan nom.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


# ─── Category ────────────────────────────────────────────────────────────────


class CategoryCreate(BaseModel):
    """Yangi kategoriya yaratish."""

    name_uz: str = Field(..., min_length=1, max_length=255, description="Nomi (UZ)")
    name_ru: str = Field(..., min_length=1, max_length=255, description="Nomi (RU)")
    parent_id: uuid.UUID | None = Field(None, description="Yuqori kategoriya ID (ildiz=None)")
    is_active: bool = Field(True, description="Kategoriya faolmi")


class CategoryOut(BaseModel):
    """Kategoriya javob sxemasi."""

    id: uuid.UUID
    name_uz: str
    name_ru: str
    name: str = Field("", description="Lokalizatsiyalangan nom (joriy til)")
    parent_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── PriceSegment ────────────────────────────────────────────────────────────


class PriceSegmentCreate(BaseModel):
    """Yangi narx segmenti yaratish."""

    name: str = Field(..., min_length=1, max_length=100, description="Segment nomi (unikal)")


class PriceSegmentOut(BaseModel):
    """Narx segmenti javob sxemasi."""

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Price ───────────────────────────────────────────────────────────────────


class PriceSet(BaseModel):
    """Mahsulot narxini o'rnatish so'rovi."""

    segment_id: uuid.UUID = Field(..., description="Narx segmenti ID")
    price: Decimal = Field(..., gt=Decimal("0"), description="Narx (so'm, musbat)")
    currency: str = Field("UZS", min_length=3, max_length=3, description="Valyuta kodi (ISO 4217)")
    valid_from: datetime = Field(..., description="Narx amal qilish boshlanishi (UTC)")
    client_uuid: uuid.UUID | None = Field(
        None, description="Idempotentlik UUID (ixtiyoriy)"
    )


class PriceOut(BaseModel):
    """Mahsulot narxi javob sxemasi."""

    id: uuid.UUID
    product_id: uuid.UUID
    segment_id: uuid.UUID
    price: Decimal
    currency: str
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PriceHistoryOut(BaseModel):
    """Narx tarixi yozuvi javob sxemasi."""

    id: uuid.UUID
    product_id: uuid.UUID
    segment_id: uuid.UUID
    old_price: Decimal
    new_price: Decimal
    currency: str
    changed_by: uuid.UUID | None
    changed_at: datetime

    model_config = {"from_attributes": True}


# ─── Product ─────────────────────────────────────────────────────────────────


class ProductCreate(BaseModel):
    """Yangi mahsulot yaratish so'rovi."""

    name_uz: str = Field(..., min_length=1, max_length=500, description="Nomi (UZ)")
    name_ru: str = Field(..., min_length=1, max_length=500, description="Nomi (RU)")
    sku: str | None = Field(None, max_length=100, description="Ichki artikel (SKU, unikal)")
    barcode: str | None = Field(None, max_length=100, description="Shtrix-kod (EAN/UPC)")
    mxik_code: str | None = Field(None, max_length=50, description="MXIK fiskal kod")
    unit: str = Field("dona", max_length=20, description="O'lchov birligi")
    category_id: uuid.UUID | None = Field(None, description="Kategoriya ID")
    photo_url: str | None = Field(None, description="MinIO/S3 URL")
    is_active: bool = Field(True, description="Mahsulot faolmi")
    branch_scope: str | None = Field(
        None, description="JSON: filiallar ro'yxati (None=barcha)"
    )
    client_uuid: uuid.UUID | None = Field(
        None, description="Idempotentlik UUID (ixtiyoriy)"
    )


class ProductUpdate(BaseModel):
    """Mahsulot yangilash so'rovi (PATCH — faqat berilgan maydonlar yangilanadi)."""

    name_uz: str | None = Field(None, min_length=1, max_length=500)
    name_ru: str | None = Field(None, min_length=1, max_length=500)
    sku: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    mxik_code: str | None = Field(None, max_length=50)
    unit: str | None = Field(None, max_length=20)
    category_id: uuid.UUID | None = None
    photo_url: str | None = None
    is_active: bool | None = None
    branch_scope: str | None = None
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProductUpdate":
        """version dan tashqari kamida bitta maydon berilishi shart."""
        fields = {
            "name_uz", "name_ru", "sku", "barcode", "mxik_code",
            "unit", "category_id", "photo_url", "is_active", "branch_scope",
        }
        if not any(getattr(self, f) is not None for f in fields):
            raise ValueError("Kamida bitta maydon yangilanishi shart")
        return self


class ProductOut(BaseModel):
    """Mahsulot javob sxemasi."""

    id: uuid.UUID
    name_uz: str
    name_ru: str
    name: str = Field("", description="Lokalizatsiyalangan nom (joriy til bo'yicha)")
    sku: str | None
    barcode: str | None
    mxik_code: str | None
    unit: str
    category_id: uuid.UUID | None
    photo_url: str | None
    is_active: bool
    branch_scope: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── Paginated ───────────────────────────────────────────────────────────────


class PaginatedProducts(BaseModel):
    """Paginated mahsulotlar ro'yxati javob sxemasi."""

    items: list[ProductOut]
    total: int = Field(..., description="Jami topilgan mahsulotlar soni (filter bo'yicha)")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
