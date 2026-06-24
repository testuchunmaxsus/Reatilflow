"""
Push moduli router — T19.

Endpointlar:
  PATCH /push/device-token — foydalanuvchi o'z FCM/APNs device_id ni ro'yxatdan o'tkazadi.

RBAC:
  - push:create ruxsati talab qilinadi (barcha autentifikatsiyalangan rollar uchun bor).
  - Boshqa foydalanuvchi device_id ni yangilash taqiqlangan (IDOR himoyasi).

Eslatma:
  Bu endpoint /push prefixiga main.py da ulanadi.
  require_permission(Module.PUSH, Action.CREATE) orqali himoyalangan.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.user import AppUser
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["push"])


# ─── Sxemalar ─────────────────────────────────────────────────────────────────


class DeviceTokenUpdate(BaseModel):
    """Qurilma FCM/APNs tokenini yangilash so'rovi."""

    device_id: str | None = Field(
        ...,
        max_length=512,
        description="FCM registration token yoki APNs device token. NULL = o'chirish",
    )
    channel: str = Field(
        "fcm",
        description="Push kanali: fcm | apns",
    )


class DeviceTokenResponse(BaseModel):
    """Device token yangilash javobi."""

    user_id: str
    device_id: str | None
    channel: str
    message: str


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.patch(
    "/device-token",
    response_model=DeviceTokenResponse,
    summary="FCM/APNs device token ro'yxatdan o'tkazish",
    description=(
        "Joriy foydalanuvchi (JWT token asosida) o'z qurilmasining FCM registration "
        "token yoki APNs device token'ini yangilaydi. "
        "NULL yuborish token'ni o'chiradi (push bildirishnomalar to'xtatiladi). "
        "Barcha autentifikatsiyalangan rollar uchun ruxsat etilgan."
    ),
    responses={
        200: {"description": "Device token muvaffaqiyatli yangilandi"},
        401: {"description": "Autentifikatsiya talab qilinadi"},
        422: {"description": "Noto'g'ri token format"},
    },
)
async def update_device_token(
    body: DeviceTokenUpdate,
    current_user: AppUser = require_permission(Module.PUSH, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> DeviceTokenResponse:
    """
    Foydalanuvchi o'z FCM/APNs tokenini yangilaydi.

    RBAC: push:create ruxsati — barcha autentifikatsiyalangan rollar (administrator, agent,
    courier, accountant, store) uchun mavjud. require_permission(Module.PUSH, Action.CREATE)
    dependency orqali tekshiriladi.
    IDOR himoyasi: faqat joriy foydalanuvchi (current_user.id) yangilanadi — boshqasi emas.
    """
    # IDOR himoyasi: faqat joriy foydalanuvchi o'z device_id ni o'zgartiradi
    # (current_user dependency dan keladi — JWT dan extract qilingan)
    current_user.device_id = body.device_id
    db.add(current_user)
    await db.flush()
    await db.commit()

    return DeviceTokenResponse(
        user_id=str(current_user.id),
        device_id=body.device_id,
        channel=body.channel,
        message="Device token yangilandi" if body.device_id else "Device token o'chirildi",
    )
