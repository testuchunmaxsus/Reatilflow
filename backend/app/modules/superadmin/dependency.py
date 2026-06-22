"""
Superadmin dependency — MT4.

`require_superadmin`: current_user.role == "superadmin" bo'lmasa 403.

Foydalanish:
    @router.get("/superadmin/enterprises")
    async def list_enterprises(
        current_user: AppUser = Depends(require_superadmin),
        ...
    ):
        ...
"""

from __future__ import annotations

import logging

from fastapi import Depends

from app.core.errors import AppError
from app.models.user import AppUser
from app.modules.auth.router import get_current_user

logger = logging.getLogger(__name__)


async def require_superadmin(
    current_user: AppUser = Depends(get_current_user),
) -> AppUser:
    """
    FastAPI dependency: faqat superadmin roliga ruxsat beradi.

    Raises:
        AppError("superadmin.forbidden", 403): rol superadmin emas.
    """
    if current_user.role != "superadmin":
        logger.warning(
            "superadmin.forbidden: role=%s user_id=%s",
            current_user.role,
            str(current_user.id),
        )
        raise AppError("superadmin.forbidden", status_code=403)

    return current_user
