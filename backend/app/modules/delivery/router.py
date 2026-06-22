"""
Yetkazib berish router — T18 Delivery.

Endpointlar:
  POST   /delivery                  — kuryer tayinlash (delivery:create — admin/agent)
  PATCH  /delivery/{id}/status      — holat o'zgartirish (delivery:edit — courier)
  POST   /delivery/{id}/proof-photo — dalil rasmi yuklash (delivery:edit — courier)
  GET    /delivery                  — ro'yxat (delivery:view, paginated, RBAC scope)
  GET    /delivery/{id}             — bitta yetkazish (delivery:view, + GPS trek havolasi)

RBAC:
  POST   /delivery:          administrator, agent (orders:create ruxsati bilan)
  PATCH  /delivery/{id}/status: courier (faqat o'ziga tayinlangan), administrator
  POST   /delivery/{id}/proof-photo: courier (faqat o'ziga tayinlangan), administrator
  GET    /delivery:          administrator, agent, accountant, store, courier (scope bilan)
  GET    /delivery/{id}:     administrator, agent, accountant, store, courier (scope bilan)

GPS TREK HAVOLASI:
  GET /delivery/{id} javobi gps_track_url ni qaytaradi:
  GET /gps/track/{delivery_id} — alohida GPS moduli orqali (cross-DB FK yo'q).

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.core.storage import FakeStorage, StorageBackend, get_storage
from app.models.user import AppUser
from app.modules.delivery import service
from app.modules.delivery.schemas import (
    DeliveryCreate,
    DeliveryOut,
    DeliveryStatusUpdate,
    PaginatedDeliveries,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["delivery"])


def _delivery_to_out(delivery, request: Request | None = None) -> DeliveryOut:
    """
    Delivery modelini DeliveryOut sxemasiga aylantiradi.

    gps_track_url — GPS trek havolasi (alohida GPS moduli).
    Havola: /gps/track/{delivery_id}?delivery_id=... formatida (query param).
    Cross-DB FK yo'q — faqat URL reference.
    """
    out = DeliveryOut.model_validate(delivery)
    # GPS trek havolasi — alohida GPS moduli (TimescaleDB, cross-DB FK yo'q)
    # Havola ixtiyoriy — trek GPS moduli orqali o'qiladi
    if request is not None:
        base = str(request.base_url).rstrip("/")
        out.gps_track_url = f"{base}/gps/track?delivery_id={delivery.id}"
    else:
        out.gps_track_url = f"/gps/track?delivery_id={delivery.id}"
    return out


# ─── POST /delivery ───────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=DeliveryOut,
    status_code=201,
    summary="Kuryer tayinlash (yangi yetkazish yaratish)",
    description=(
        "Buyurtmaga kuryer tayinlaydi. "
        "Faqat administrator yoki agent (delivery:create + orders:create). "
        "client_uuid bilan idempotentlik kafolatlanadi."
    ),
)
async def create_delivery(
    body: DeliveryCreate,
    request: Request,
    current_user: AppUser = require_permission(Module.DELIVERY, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> DeliveryOut:
    # Do'kon (store roli) yetkazish yaratolmaydi — faqat view
    if current_user.role == "store":
        raise AppError(
            "rbac.permission_denied",
            status_code=403,
            params={
                "module": "delivery",
                "action": "create",
                "role": current_user.role,
            },
        )

    enterprise_id = get_current_enterprise_id(current_user)
    delivery = await service.create_delivery(
        db=db,
        data=body,
        actor_id=current_user.id,
        user=current_user,
        redis=redis,
        enterprise_id=enterprise_id,
    )
    return _delivery_to_out(delivery, request)


# ─── PATCH /delivery/{id}/status ─────────────────────────────────────────────


@router.patch(
    "/{delivery_id}/status",
    response_model=DeliveryOut,
    summary="Yetkazish holatini o'zgartirish",
    description=(
        "Kuryer o'z yetkazishini holat mashinasi bo'yicha o'zgartiradi. "
        "Noqonuniy o'tish → 422. "
        "IDOR: kuryer faqat o'ziga tayinlangan yetkazishni o'zgartiradi."
    ),
)
async def update_delivery_status(
    delivery_id: uuid.UUID,
    body: DeliveryStatusUpdate,
    request: Request,
    current_user: AppUser = require_permission(Module.DELIVERY, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> DeliveryOut:
    enterprise_id = get_current_enterprise_id(current_user)
    delivery = await service.update_status(
        db=db,
        delivery_id=delivery_id,
        data=body,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return _delivery_to_out(delivery, request)


# ─── POST /delivery/{id}/proof-photo ─────────────────────────────────────────


@router.post(
    "/{delivery_id}/proof-photo",
    response_model=DeliveryOut,
    summary="Yetkazish dalil rasmi yuklash",
    description=(
        "Kuryer yetkazish dalili rasmini yuklaydi (JPEG/PNG/WebP, 5MB gacha). "
        "Magic-bytes validatsiya. "
        "IDOR: kuryer faqat o'ziga tayinlangan yetkazish rasmi yuklaydi."
    ),
)
async def upload_proof_photo(
    delivery_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    current_user: AppUser = require_permission(Module.DELIVERY, Action.EDIT),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> DeliveryOut:
    # Rasmni storage'ga yuklash (magic-byte validatsiya storage qatlamida)
    # storage.upload_product_photo — mavjud validatsiya logikasini qayta ishlatish
    try:
        photo_url = await storage.upload_product_photo(file)
    except AppError as exc:
        # catalog.invalid_photo → delivery.invalid_photo ga qayta mapping
        if exc.message_key == "catalog.invalid_photo":
            raise AppError("delivery.invalid_photo", status_code=422) from exc
        # catalog.storage_error → delivery.storage_error (503)
        if exc.message_key == "catalog.storage_error":
            raise AppError("delivery.storage_error", status_code=503) from exc
        raise

    delivery = await service.set_proof_photo(
        db=db,
        delivery_id=delivery_id,
        photo_url=photo_url,
        user=current_user,
    )
    return _delivery_to_out(delivery, request)


# ─── GET /delivery ────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedDeliveries,
    summary="Yetkazishlar ro'yxati (paginated)",
    description=(
        "RBAC scope bilan: kuryer o'ziga tayinlangan, "
        "agent o'z buyurtmalari, do'kon o'z buyurtmalari, admin/buxgalter barchasi."
    ),
)
async def list_deliveries(
    request: Request,
    status: Optional[str] = Query(None, description="Holat bo'yicha filtr"),
    courier_id: Optional[uuid.UUID] = Query(None, description="Kuryer bo'yicha filtr"),
    order_id: Optional[uuid.UUID] = Query(None, description="Buyurtma bo'yicha filtr"),
    date_from: Optional[datetime] = Query(None, description="Boshlanish sanasi (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Tugash sanasi (ISO 8601)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AppUser = require_permission(Module.DELIVERY, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedDeliveries:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_deliveries(
        db=db,
        user=current_user,
        enterprise_id=enterprise_id,
        status=status,
        courier_id=courier_id,
        order_id=order_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedDeliveries(
        items=[_delivery_to_out(d, request) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /delivery/{id} ───────────────────────────────────────────────────────


@router.get(
    "/{delivery_id}",
    response_model=DeliveryOut,
    summary="Bitta yetkazish (+ GPS trek havolasi)",
    description=(
        "RBAC scope bilan. "
        "gps_track_url: GPS trek havolasi (GET /gps/track?delivery_id=...). "
        "GPS trek alohida TimescaleDB da — cross-DB FK yo'q."
    ),
)
async def get_delivery(
    delivery_id: uuid.UUID,
    request: Request,
    current_user: AppUser = require_permission(Module.DELIVERY, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> DeliveryOut:
    enterprise_id = get_current_enterprise_id(current_user)
    delivery = await service.get_delivery(
        db=db,
        delivery_id=delivery_id,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return _delivery_to_out(delivery, request)
