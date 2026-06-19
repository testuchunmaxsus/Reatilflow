"""
GPS Ingest sxemalari — T17.

Pydantic v2 sxemalari:
  GpsPointIn     — bitta GPS nuqta (klient → server)
  GpsBatchIngest — batch GPS nuqtalar so'rovi
  IngestResult   — batch ingest natijasi
  GpsTrackOut    — GPS trekking nuqta javob sxemasi (server → klient)
  PaginatedTrack — paginated trekking nuqtalari ro'yxati

ADR §3.7:
  - recorded_at: QURILMA vaqti (klientdan keladi — offline yozilgan).
    Kelajak vaqt (> 5 daqiqa serverdan) → rad etiladi.
    Juda eski (> 30 kun) → rad etiladi (90 kun retention bilan mos).
    BIZNES QAROR: yumshoq chegara — klientga xabar berish, lekin jarayon davom etadi
    (ma'lumot yo'qolmasin). Hozirgi implementatsiya: qat'iy rad etish.
  - ingested_at: SERVER vaqti (klient ko'ra olmaydi — hisob-kitob uchun).
  - lat/lng: Decimal 8 kasrga aniqlik (GPS standart).
  - speed: m/s (ixtiyoriy).
  - delivery_id: kuryer yetkazishda (T18 da FK; hozir UUID nullable).

GPS oraliq validatsiya:
  lat: [-90, 90]
  lng: [-180, 180]
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ─── GpsPointIn ───────────────────────────────────────────────────────────────


class GpsPointIn(BaseModel):
    """
    Bitta GPS nuqta — klientdan keladi.

    recorded_at: QURILMA vaqti (offline yozilgan).
      - Kelajak vaqt (> 5 daqiqa serverdan) → 422 rad etiladi.
      - Juda eski (> 30 kun) → 422 rad etiladi.
      IZOH: 30 kunlik chegara biznes qaror — GPS trek 30 kundan eski bo'lsa
      trekking qiymati yo'q. 90 kun retention bilan mos (30 < 90).
      Kelajakda: sozlamadan (GPS_MAX_AGE_DAYS) olish mumkin.

    lat/lng: GPS koordinatalar (Decimal, 8 kasrga aniqlik).
    speed: m/s, ixtiyoriy.
    delivery_id: kuryer yetkazishda (ixtiyoriy; T18 da FK).
    """

    lat: Decimal = Field(
        ...,
        ge=Decimal("-90"),
        le=Decimal("90"),
        description="GPS kenglik (±90.00000000, 8 kasrga aniqlik)",
    )

    lng: Decimal = Field(
        ...,
        ge=Decimal("-180"),
        le=Decimal("180"),
        description="GPS uzunlik (±180.00000000, 8 kasrga aniqlik)",
    )

    recorded_at: datetime = Field(
        ...,
        description=(
            "QURILMA vaqti (offline yozilgan). "
            "Kelajak (> 5 daqiqa) yoki juda eski (> 30 kun) bo'lsa → 422."
        ),
    )

    speed: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("150"),
        description=(
            "Tezlik m/s (ixtiyoriy, manfiy bo'lmasligi kerak). "
            "Maksimal: 150 m/s (~540 km/h) — data-quality chegarasi. "
            "Haqiqiy GPS qurilmalar uchun mantiqiy maksimum."
        ),
    )

    delivery_id: uuid.UUID | None = Field(
        default=None,
        description="Yetkazish UUID (ixtiyoriy; T18 da FK)",
    )


# ─── GpsBatchIngest ───────────────────────────────────────────────────────────


class GpsBatchIngest(BaseModel):
    """
    Batch GPS nuqtalar so'rovi.

    points: max 500 ta nuqta (config gps_max_batch).
    Limit oshsa → 422 gps.batch_too_large.
    """

    points: list[GpsPointIn] = Field(
        ...,
        min_length=1,
        description="GPS nuqtalar ro'yxati (min 1, max config gps_max_batch=500)",
    )


# ─── IngestResult ─────────────────────────────────────────────────────────────


class IngestResult(BaseModel):
    """
    Batch ingest natijasi.

    accepted:  saqlangan nuqtalar soni.
    rejected:  rad etilgan nuqtalar soni (vaqt validatsiya xatosi).
    duplicate: takror nuqtalar soni (idempotent — ON CONFLICT DO NOTHING;
               accepted+rejected+duplicate = total yuborilgan).
               IZOH: PostgreSQL rowcount=-1 holatida duplicate=0 (driver
               rowcount qaytara olmadi — accepted konservativ baholanadi).
    """

    accepted: int = Field(..., description="Saqlangan nuqtalar soni")
    rejected: int = Field(..., description="Rad etilgan nuqtalar soni (vaqt validatsiyasi)")
    duplicate: int = Field(
        default=0,
        description=(
            "Takror nuqtalar soni (idempotent — ON CONFLICT DO NOTHING). "
            "accepted + rejected + duplicate = jami yuborilgan nuqtalar."
        ),
    )


# ─── GpsTrackOut ─────────────────────────────────────────────────────────────


class GpsTrackOut(BaseModel):
    """GPS trekking nuqta javob sxemasi."""

    id: uuid.UUID
    user_id: uuid.UUID
    delivery_id: uuid.UUID | None
    lat: Decimal
    lng: Decimal
    recorded_at: datetime
    speed: Decimal | None
    ingested_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── PaginatedTrack ───────────────────────────────────────────────────────────


class PaginatedTrack(BaseModel):
    """Paginated GPS trekking nuqtalari ro'yxati."""

    items: list[GpsTrackOut]
    total: int
    limit: int
    offset: int
