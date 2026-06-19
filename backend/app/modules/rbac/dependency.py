"""
RBAC FastAPI dependency'lari.

`require_permission(module, action)`:
  - FastAPI dependency factory — endpoint dekoratorida ishlatiladi.
  - `get_current_user` (T1) dan foydalanuvchini oladi (kengaytirish, almashtirish emas).
  - Ruxsat yo'q bo'lsa → HTTP 403 (aniq xabar: modul va amal ko'rsatiladi).
  - Redis keshi orqali tezkor tekshiruv (graceful degradation mavjud).

Misol:
    @router.get("/catalog")
    async def list_products(
        _: None = Depends(require_permission(Module.CATALOG, Action.VIEW)),
        current_user: AppUser = Depends(get_current_user),
    ):
        ...

    # Yoki qisqaroq — user ham kerak bo'lsa:
    @router.post("/catalog")
    async def create_product(
        current_user: AppUser = Depends(require_permission(Module.CATALOG, Action.CREATE)),
    ):
        ...
    # Bu holda require_permission AppUser qaytaradi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends
from redis.asyncio import Redis

from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.auth.router import get_current_user
from app.modules.rbac.service import get_permissions_for_role

logger = logging.getLogger(__name__)


def require_permission(module: str, action: str) -> Callable:
    """
    FastAPI dependency factory: modul + amal bo'yicha ruxsatni tekshiradi.

    Foydalanuvchi ruxsatga ega bo'lsa AppUser obyektini qaytaradi,
    aks holda HTTP 403 chiqaradi.

    Args:
        module: Modul nomi (masalan, "catalog", "finance").
        action: Amal nomi (masalan, "view", "create", "approve").

    Returns:
        FastAPI Depends() uchun yaroqli async callable.
    """
    perm_key = f"{module}:{action}"

    async def _check_permission(
        current_user: AppUser = Depends(get_current_user),
        redis: Redis = Depends(get_redis),
    ) -> AppUser:
        """
        Haqiqiy tekshiruv:
          1. Redis keshidan yoki matritsadan ruxsatlar to'plamini oladi.
          2. `module:action` kalitini tekshiradi.
          3. Ruxsat yo'q → 403 (aniq xabar).
        """
        perms = await get_permissions_for_role(current_user.role, redis)

        if perm_key not in perms:
            logger.warning(
                "RBAC: ruxsat rad etildi",
                extra={
                    "user_id": str(current_user.id),
                    "role": current_user.role,
                    "perm_module": module,   # 'module' LogRecord da band — perm_module ishlatiladi
                    "action": action,
                },
            )
            raise AppError(
                message_key="rbac.permission_denied",
                status_code=403,
                params={
                    "module": module,
                    "action": action,
                    "role": current_user.role,
                },
            )

        return current_user

    # Dependency introspection uchun aniq nom
    _check_permission.__name__ = f"require_{module}_{action}"

    return Depends(_check_permission)
