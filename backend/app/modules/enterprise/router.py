"""
Enterprise moduli router — /enterprise prefiksi bilan main.py ga ulanadi.

Endpointlar (MT3):
  GET   /enterprise/me         — joriy korxona + enabled_modules qaytaradi.
                                  Veb/mobil UI yoqilmagan modullarni yashirish uchun.
  PATCH /enterprise/me/modules — administrator o'z korxonasi enabled_modules'ni yangilaydi.
                                  Body: {enabled_modules: [...]}.

CORE modul: gate QO'YILMAYDI (auth/rbac/users/sync kabi).
Har autentifikatsiyalangan user korxonasini ko'ra oladi.

superadmin (enterprise_id=None): 404 qaytaradi
  (superadmin korxonaga tegishli emas, biznes ma'lumotiga kirmaydi).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.modules.auth.router import get_current_user
from app.modules.enterprise.schemas import EnterpriseOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enterprise"])


# ─── Sxemalar ────────────────────────────────────────────────────────────────


class UpdateModulesRequest(BaseModel):
    """PATCH /enterprise/me/modules so'rovi."""

    enabled_modules: list[str] = Field(
        ...,
        description="Yoqilgan modul kalitlari ro'yxati",
    )


@router.get(
    "/me",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="Joriy korxona ma'lumotlari",
    description=(
        "Autentifikatsiyalangan foydalanuvchining korxonasini qaytaradi. "
        "`enabled_modules` — yoqilgan modul kalitlari ro'yxati. "
        "Veb/mobil UI yoqilmagan modullarni yashirish uchun ishlatiladi. "
        "superadmin (enterprise_id=None) uchun 404 qaytaradi."
    ),
    responses={
        200: {"description": "Joriy korxona ma'lumotlari + enabled_modules"},
        401: {"description": "Autentifikatsiya talab qilinadi"},
        404: {"description": "Korxona topilmadi (superadmin uchun)"},
    },
)
async def get_my_enterprise(
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """
    Joriy foydalanuvchi korxonasini qaytaradi.

    superadmin enterprise_id=None bilan ishlaydi — korxonaga tegishli emas,
    shuning uchun 404 qaytariladi (ADR-002 §2.4: superadmin biznes ma'lumotiga kirmaydi).

    Oddiy foydalanuvchi uchun:
      - enterprise_id dan Enterprise yuklanadi.
      - enabled_modules ro'yxati qaytariladi.
    """
    if current_user.enterprise_id is None:
        # superadmin — korxonasiz
        raise AppError(
            message_key="common.not_found",
            status_code=404,
        )

    stmt = select(Enterprise).where(
        Enterprise.id == current_user.enterprise_id,
        Enterprise.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    enterprise: Enterprise | None = result.scalar_one_or_none()

    if enterprise is None:
        logger.warning(
            "enterprise/me: korxona topilmadi",
            extra={
                "user_id": str(current_user.id),
                "enterprise_id": str(current_user.enterprise_id),
            },
        )
        raise AppError(
            message_key="common.not_found",
            status_code=404,
        )

    return EnterpriseOut.model_validate(enterprise)


# ─── PATCH /enterprise/me/modules ────────────────────────────────────────────


@router.patch(
    "/me/modules",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="O'z korxonasi modullarini yangilash",
    description=(
        "Administrator o'z korxonasining enabled_modules ro'yxatini yangilaydi. "
        "Faqat 'administrator' roli. Noma'lum modul kalitlari olib tashlanadi. "
        "superadmin (enterprise_id=None) uchun 404 qaytaradi."
    ),
    responses={
        200: {"description": "Yangilangan korxona"},
        401: {"description": "Autentifikatsiya talab qilinadi"},
        403: {"description": "Faqat administrator roli"},
        404: {"description": "Korxona topilmadi (superadmin uchun)"},
    },
)
async def update_my_modules(
    body: UpdateModulesRequest,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """
    Korxona-administrator o'z korxonasining enabled_modules'ni yangilaydi.

    Tekshiruvlar:
      - Faqat 'administrator' roli (boshqa rollar 403).
      - superadmin (enterprise_id=None) 404 qaytaradi.
      - Noma'lum modul kalitlari olib tashlanadi (kelajak moslik uchun).
    """
    # Faqat administrator
    if current_user.role != "administrator":
        raise AppError("rbac.permission_denied", status_code=403)

    # superadmin korxonasiz
    if current_user.enterprise_id is None:
        raise AppError("common.not_found", status_code=404)

    stmt = select(Enterprise).where(
        Enterprise.id == current_user.enterprise_id,
        Enterprise.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    enterprise: Enterprise | None = result.scalar_one_or_none()

    if enterprise is None:
        logger.warning(
            "enterprise/me/modules: korxona topilmadi",
            extra={
                "user_id": str(current_user.id),
                "enterprise_id": str(current_user.enterprise_id),
            },
        )
        raise AppError("common.not_found", status_code=404)

    # Noma'lum kalitlarni olib tashlash
    valid = set(ALL_MODULE_KEYS)
    cleaned = [m for m in body.enabled_modules if m in valid]

    enterprise.enabled_modules = cleaned
    enterprise.updated_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "enterprise.modules_updated enterprise_id=%s modules=%s actor=%s",
        str(enterprise.id),
        cleaned,
        str(current_user.id),
    )

    return EnterpriseOut.model_validate(enterprise)
