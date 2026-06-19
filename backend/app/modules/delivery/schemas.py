"""
Yetkazib berish sxemalari — T18 Delivery.

Sxemalar:
  DeliveryCreate       — yangi yetkazish yaratish (kuryer tayinlash)
  DeliveryStatusUpdate — holat o'zgartirish (kuryer)
  DeliveryOut          — javob sxemasi
  PaginatedDeliveries  — paginated ro'yxat
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class DeliveryCreate(BaseModel):
    """
    Yangi yetkazish yaratish — kuryer tayinlash.

    order_id:    Yetkazilishi kerak bo'lgan buyurtma.
    courier_id:  Tayinlanadigan kuryer (app_user, role=courier).
    client_uuid: Ixtiyoriy idempotentlik UUID (takroriy so'rovdan himoya).
    """

    order_id: uuid.UUID = Field(..., description="Buyurtma ID (FK → order)")
    courier_id: uuid.UUID = Field(..., description="Kuryer ID (FK → app_user, role=courier)")
    client_uuid: Optional[uuid.UUID] = Field(
        default=None,
        description="Klient idempotentlik UUID (ixtiyoriy)",
    )


class DeliveryStatusUpdate(BaseModel):
    """
    Yetkazish holat o'zgartirish.

    status:         Yangi holat (server holat mashinasi tekshiradi).
    version:        Joriy versiya (optimistik lock).
    gps_lat/lng:    GPS koordinatalar (started va delivered holatlari uchun).
    failure_reason: Muvaffaqiyatsizlik sababi (failed holati uchun).
    """

    status: str = Field(
        ...,
        description="Yangi holat: started | delivering | delivered | failed",
    )
    version: int = Field(..., description="Joriy versiya (optimistik lock uchun)")
    gps_lat: Optional[Decimal] = Field(
        default=None,
        description="GPS kenglik (started/delivered holatlarida ixtiyoriy)",
    )
    gps_lng: Optional[Decimal] = Field(
        default=None,
        description="GPS uzunlik (started/delivered holatlarida ixtiyoriy)",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        description="Muvaffaqiyatsizlik sababi (failed holati uchun ixtiyoriy)",
    )


class DeliveryOut(BaseModel):
    """
    Yetkazish javob sxemasi.

    gps_track_url: GPS trek havolasi — GET /gps/track/{delivery_id}
                   (alohida GPS moduli, TimescaleDB'dan o'qiladi; cross-DB FK yo'q).
    """

    id: uuid.UUID
    order_id: uuid.UUID
    courier_id: uuid.UUID
    status: str
    assigned_at: datetime
    started_at: Optional[datetime] = None
    start_gps_lat: Optional[Decimal] = None
    start_gps_lng: Optional[Decimal] = None
    delivered_at: Optional[datetime] = None
    delivery_gps_lat: Optional[Decimal] = None
    delivery_gps_lng: Optional[Decimal] = None
    proof_photo_url: Optional[str] = None
    failure_reason: Optional[str] = None
    branch_id: Optional[uuid.UUID] = None
    client_uuid: Optional[uuid.UUID] = None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    # GPS trek havola — alohida GPS moduli orqali (cross-DB FK yo'q)
    gps_track_url: Optional[str] = None

    model_config = {"from_attributes": True}


class PaginatedDeliveries(BaseModel):
    """Paginated yetkazishlar ro'yxati."""

    items: list[DeliveryOut]
    total: int
    limit: int
    offset: int
