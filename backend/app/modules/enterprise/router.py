"""
Enterprise moduli router — /enterprise prefiksi bilan main.py ga ulanadi.

Endpointlar (MT3):
  GET /enterprise/me — joriy korxona + enabled_modules qaytaradi.
                       Veb/mobil UI yoqilmagan modullarni yashirish uchun.

CORE modul: gate QO'YILMAYDI (auth/rbac/users/sync kabi).
Har autentifikatsiyalangan user korxonasini ko'ra oladi.

superadmin (enterprise_id=None): 404 qaytaradi
  (superadmin korxonaga tegishli emas, biznes ma'lumotiga kirmaydi).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.models.enterprise import Enterprise
from app.models.user import AppUser
from app.modules.auth.router import get_current_user
from app.modules.enterprise.schemas import EnterpriseOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enterprise"])


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
