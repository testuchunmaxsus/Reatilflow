"""
Davomat sxemalari — T16.

Pydantic v2 sxemalari:
  CheckInRequest  — kirish so'rovi (klient → server)
  CheckOutRequest — chiqish so'rovi (klient → server)
  AttendanceOut   — davomat javob sxemasi (server → klient)
  PaginatedAttendance — paginated ro'yxat

GPS: Decimal (7 kasrga aniqlik, ±90/±180 oralig'i).
biometric_verified: qurilma biometriyasi bayrog'i (YUZNI HECH QACHON YUBORMANG).
source: 'device_faceid' | 'device_fingerprint'.
check_in_at / check_out_at: serverda belgilanadi (klient berganiga ishonilmaydi).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─── Ruxsat etilgan source qiymatlari ─────────────────────────────────────────

AttendanceSource = Literal["device_faceid", "device_fingerprint"]


# ─── CheckInRequest ───────────────────────────────────────────────────────────


class CheckInRequest(BaseModel):
    """
    Kirish so'rovi.

    MUHIM:
      - biometric_verified: qurilmadan kelgan boolean bayroq.
        YUZNI HECH QACHON serverga YUBORMANG.
        false bo'lsa → attendance.biometric_required xato (servis darajasida).
      - gps_lat / gps_lng: klientdan GPS koordinatasi (server yozadi).
      - source: qurilma biometriya turi.
      - client_uuid: idempotentlik uchun (ixtiyoriy).
    """

    biometric_verified: bool = Field(
        ...,
        description=(
            "Qurilma biometriyasi muvaffaqiyatli o'tganmi. "
            "YUZNI serverga HECH QACHON YUBORMANG — faqat bu boolean flag."
        ),
    )

    gps_lat: Decimal = Field(
        ...,
        ge=Decimal("-90"),
        le=Decimal("90"),
        decimal_places=7,
        description="GPS kenglik (±90.0000000)",
    )

    gps_lng: Decimal = Field(
        ...,
        ge=Decimal("-180"),
        le=Decimal("180"),
        decimal_places=7,
        description="GPS uzunlik (±180.0000000)",
    )

    source: AttendanceSource = Field(
        ...,
        description="Biometriya turi: 'device_faceid' | 'device_fingerprint'",
    )

    client_uuid: uuid.UUID | None = Field(
        default=None,
        description="Idempotentlik UUID (ixtiyoriy)",
    )


# ─── CheckOutRequest ──────────────────────────────────────────────────────────


class CheckOutRequest(BaseModel):
    """
    Chiqish so'rovi.

    gps_lat / gps_lng: chiqish joyi (server yozadi).
    client_uuid: idempotentlik uchun (ixtiyoriy).
    """

    gps_lat: Decimal = Field(
        ...,
        ge=Decimal("-90"),
        le=Decimal("90"),
        decimal_places=7,
        description="GPS kenglik (±90.0000000)",
    )

    gps_lng: Decimal = Field(
        ...,
        ge=Decimal("-180"),
        le=Decimal("180"),
        decimal_places=7,
        description="GPS uzunlik (±180.0000000)",
    )

    client_uuid: uuid.UUID | None = Field(
        default=None,
        description="Idempotentlik UUID (ixtiyoriy)",
    )


# ─── AttendanceOut ────────────────────────────────────────────────────────────


class AttendanceOut(BaseModel):
    """Davomat javob sxemasi."""

    id: uuid.UUID
    user_id: uuid.UUID
    work_date: date
    check_in_at: datetime
    check_in_gps_lat: Decimal
    check_in_gps_lng: Decimal
    check_out_at: datetime | None
    check_out_gps_lat: Decimal | None
    check_out_gps_lng: Decimal | None
    biometric_verified: bool
    source: str
    client_uuid: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


# ─── PaginatedAttendance ──────────────────────────────────────────────────────


class PaginatedAttendance(BaseModel):
    """Paginated davomat ro'yxati."""

    items: list[AttendanceOut]
    total: int
    limit: int
    offset: int
