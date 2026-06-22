"""
Module gating dependency — MT3.

`require_module(module_key: str)` FastAPI dependency factory:
  - Joriy user enterprise'ini DB dan yuklaydi (enterprise_id orqali).
  - `module_key in enterprise.enabled_modules` tekshiradi.
  - Yoqilmagan bo'lsa → AppError("enterprise.module_disabled", 403).
  - superadmin (enterprise_id=None) → bypass (har doim o'tadi).

ADR-002 §2.5 bo'yicha.

Ishlatilish:
    router = APIRouter(
        prefix="/promos",
        dependencies=[Depends(require_module("promo"))],
    )

    # Yoki main.py include_router da:
    app.include_router(
        promo_router,
        prefix="/promos",
        dependencies=[Depends(require_module("promo"))],
    )
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.models.enterprise import Enterprise
from app.models.user import AppUser
from app.modules.auth.router import get_current_user

logger = logging.getLogger(__name__)


def require_module(module_key: str) -> Callable:
    """
    FastAPI dependency factory: enterprise modul-gating tekshiruvi.

    Enterprise yoqilmagan modul endpointiga so'rov kelsa → 403.
    superadmin (enterprise_id=None) → bypass.

    Args:
        module_key: Modul kaliti (masalan, "catalog", "promo", "finance").

    Returns:
        FastAPI Depends() uchun yaroqli async callable.

    Ishlash tartibi:
        1. get_current_user orqali autentifikatsiyani tekshiradi.
        2. superadmin bo'lsa → None qaytaradi (bypass).
        3. Enterprise'ni DB dan SELECT qiladi (bitta so'rov).
        4. enabled_modules ichida module_key borligini tekshiradi.
        5. Yo'q bo'lsa → AppError("enterprise.module_disabled", 403).
    """

    async def _check_module(
        current_user: AppUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        # superadmin bypass: enterprise_id=None bo'lsa gate o'tiladi
        if current_user.enterprise_id is None:
            logger.debug(
                "module_gate: superadmin bypass",
                extra={"module_key": module_key},
            )
            return

        # Enterprise'ni DB dan yuklash (bitta SELECT)
        stmt = select(Enterprise).where(
            Enterprise.id == current_user.enterprise_id,
            Enterprise.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        enterprise: Enterprise | None = result.scalar_one_or_none()

        if enterprise is None:
            # Enterprise topilmadi — bu holat odatda bo'lmasligi kerak
            # (user enterprise_id bor, lekin enterprise o'chirilgan)
            logger.warning(
                "module_gate: enterprise topilmadi",
                extra={
                    "user_id": str(current_user.id),
                    "enterprise_id": str(current_user.enterprise_id),
                    "module_key": module_key,
                },
            )
            raise AppError(
                message_key="enterprise.module_disabled",
                status_code=403,
                params={"module": module_key},
            )

        # Modul yoqilganligini tekshirish
        enabled: list = enterprise.enabled_modules or []
        if module_key not in enabled:
            logger.info(
                "module_gate: modul yoqilmagan",
                extra={
                    "user_id": str(current_user.id),
                    "enterprise_id": str(current_user.enterprise_id),
                    "module_key": module_key,
                    "enabled_modules": enabled,
                },
            )
            raise AppError(
                message_key="enterprise.module_disabled",
                status_code=403,
                params={"module": module_key},
            )

        logger.debug(
            "module_gate: modul yoqilgan",
            extra={
                "enterprise_id": str(current_user.enterprise_id),
                "module_key": module_key,
            },
        )

    # Dependency introspection uchun aniq nom
    _check_module.__name__ = f"require_module_{module_key}"

    return Depends(_check_module)
