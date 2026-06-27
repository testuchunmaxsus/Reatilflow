"""
Import data moduli Pydantic v2 sxemalari.

Sxemalar:
  ParsedRow            — parse qilingan bitta satr (Excel yoki Nakladnoy)
  ColumnMapping        — Excel ustun moslash natijasi
  ExcelParseOut        — Excel parse javobi
  NakladnoyParseOut    — Nakladnoy rasm parse javobi
  ConfirmRow           — confirm so'rovdagi bitta satr (client_uuid bilan)
  ImportConfirmIn      — confirm so'rov tanasi
  ImportConfirmOut     — confirm javob
  RowError             — op-darajali xato
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


# ─── Parse natijasi ───────────────────────────────────────────────────────────


class ParsedRow(BaseModel):
    """Parse qilingan bitta mahsulot satri."""

    row_index: int = Field(..., description="Manba fayldagi satr raqami (0-dan)")
    name: str | None = Field(None, description="Mahsulot nomi")
    sku: str | None = Field(None, description="SKU/artikel")
    barcode: str | None = Field(None, description="Shtrix-kod")
    qty: float | None = Field(None, description="Miqdor")
    price: float | None = Field(None, description="Narx")
    currency: str = Field("UZS", description="Valyuta kodi (ISO 4217)")
    expiry_date: date | None = Field(None, description="Yaroqlilik muddati (ixtiyoriy)")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Ishonch darajasi (0-1)")


class ColumnMapping(BaseModel):
    """Excel ustun moslash natijasi."""

    source_header: str = Field(..., description="Excel ustun sarlavhasi")
    mapped_to: str | None = Field(None, description="Moslangan maydon nomi")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Ishonch darajasi")


class ExcelParseOut(BaseModel):
    """Excel parse javobi."""

    parse_id: uuid.UUID = Field(..., description="Client-correlation UUID (DBda saqlanmaydi)")
    columns_detected: list[ColumnMapping] = Field(
        default_factory=list, description="Aniqlanib moslangan ustunlar"
    )
    rows: list[ParsedRow] = Field(default_factory=list, description="Parse qilingan satrlar")
    warnings: list[str] = Field(default_factory=list, description="Ogohlantirishlar")


class NakladnoyParseOut(BaseModel):
    """Nakladnoy rasm parse javobi."""

    parse_id: uuid.UUID = Field(..., description="Client-correlation UUID (DBda saqlanmaydi)")
    rows: list[ParsedRow] = Field(default_factory=list, description="Parse qilingan satrlar")
    raw_text: str | None = Field(None, description="OCR debug matni (ixtiyoriy)")
    warnings: list[str] = Field(default_factory=list, description="Ogohlantirishlar")
    vision_enabled: bool = Field(True, description="Groq Vision ishladimi")


# ─── Confirm ──────────────────────────────────────────────────────────────────


class ConfirmRow(BaseModel):
    """Confirm so'rovdagi bitta mahsulot satri."""

    row_index: int = Field(..., description="Asl satr raqami (xato traceback uchun)")
    name: str = Field(..., min_length=1, max_length=500, description="Mahsulot nomi")
    sku: str | None = Field(None, max_length=100, description="SKU/artikel (ixtiyoriy)")
    barcode: str | None = Field(None, max_length=100, description="Shtrix-kod (ixtiyoriy)")
    qty: float = Field(..., gt=0, description="Miqdor (musbat)")
    price: float = Field(..., gt=0, description="Narx (musbat)")
    currency: str = Field("UZS", min_length=3, max_length=3, description="Valyuta kodi")
    expiry_date: date | None = Field(None, description="Yaroqlilik muddati (ixtiyoriy)")
    client_uuid: uuid.UUID = Field(..., description="Idempotentlik UUID (frontend tomonidan)")


class ImportConfirmIn(BaseModel):
    """Import confirm so'rov tanasi."""

    source: str = Field(
        ..., pattern="^(excel|nakladnoy)$", description="Import manbasi: excel | nakladnoy"
    )
    rows: list[ConfirmRow] = Field(
        ..., min_length=1, max_length=500, description="Tasdiqlash uchun satrlar (max 500)"
    )


class RowError(BaseModel):
    """Op-darajali xato (bitta satr)."""

    row_index: int = Field(..., description="Xatolik sodir bo'lgan satr raqami")
    code: str = Field(..., description="Xato kodi")
    message: str = Field(..., description="Xato matni (o'zbekcha)")


class ImportConfirmOut(BaseModel):
    """Import confirm javobi."""

    created: int = Field(..., description="Muvaffaqiyatli yaratilgan yozuvlar soni")
    skipped: int = Field(..., description="Idempotent skip qilingan yozuvlar soni")
    errors: list[RowError] = Field(default_factory=list, description="Op-darajali xatolar")
    target: str = Field(
        ..., description="Yozish maqsadi: catalog | store_inventory"
    )
