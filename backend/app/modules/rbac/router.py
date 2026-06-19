"""
RBAC router — /rbac prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET /rbac/my-permissions   — joriy foydalanuvchi ruxsatlari (autentifikatsiya talab)
  GET /rbac/check            — aniq modul:amal tekshiruvi (query params)

Bu router T4/T5 ga `require_permission` dependency qanday ishlashini ko'rsatadi.
Haqiqiy CRUD endpointlar T4/T5/T6 da implement qilinadi.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.auth.router import get_current_user
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import ALL_VALID_ACTIONS, ALL_VALID_MODULES, Module, Action
from app.modules.rbac.service import get_permissions_for_role, has_permission

router = APIRouter(tags=["rbac"])


# ─── Javob sxemalari ──────────────────────────────────────────────────────────


class MyPermissionsResponse(BaseModel):
    """Foydalanuvchi ruxsatlari javobi."""

    role: str
    permissions: list[str]
    total: int


class PermissionCheckResponse(BaseModel):
    """Aniq ruxsat tekshiruvi javobi."""

    module: str
    action: str
    allowed: bool
    role: str


# ─── Endpointlar ──────────────────────────────────────────────────────────────


@router.get(
    "/my-permissions",
    response_model=MyPermissionsResponse,
    summary="Mening ruxsatlarim",
    description=(
        "Joriy foydalanuvchining barcha ruxsatlarini qaytaradi. "
        "Redis kesh orqali (5 daqiqa TTL). "
        "Autentifikatsiya talab qilinadi."
    ),
)
async def my_permissions(
    current_user: AppUser = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> MyPermissionsResponse:
    """Joriy autentifikatsiyalangan foydalanuvchi ruxsatlarini qaytaradi."""
    perms = await get_permissions_for_role(current_user.role, redis)
    sorted_perms = sorted(perms)
    return MyPermissionsResponse(
        role=current_user.role,
        permissions=sorted_perms,
        total=len(sorted_perms),
    )


@router.get(
    "/check",
    response_model=PermissionCheckResponse,
    summary="Ruxsat tekshiruvi",
    description=(
        "Joriy foydalanuvchining berilgan modul:amalga ruxsatini tekshiradi. "
        "403 emas — faqat `allowed: true/false` qaytaradi (UI uchun qulay). "
        "Autentifikatsiya talab qilinadi."
    ),
)
async def check_permission(
    module: str = Query(..., description="Modul nomi (masalan: catalog, finance)"),
    action: str = Query(..., description="Amal nomi (masalan: view, create, approve)"),
    current_user: AppUser = Depends(get_current_user),
) -> PermissionCheckResponse:
    """Foydalanuvchining aniq modul:amal ruxsatini tekshiradi (403 chiqarmaydi)."""
    allowed = has_permission(current_user, module, action)
    return PermissionCheckResponse(
        module=module,
        action=action,
        allowed=allowed,
        role=current_user.role,
    )


@router.get(
    "/catalog-demo",
    summary="Namuna: catalog:view himoyalangan endpoint",
    description=(
        "Bu endpoint `require_permission(Module.CATALOG, Action.VIEW)` dependency'sini ishlatadi. "
        "catalog:view ruxsatsiz rol (masalan, agent_cabinet faqat) → 403. "
        "Haqiqiy katalog CRUD T4 da implement qilinadi."
    ),
    response_model=dict,
)
async def catalog_demo(
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
) -> dict:
    """
    Namuna himoyalangan endpoint — require_permission ishlashini ko'rsatadi.

    Barcha rollar catalog:view ga ega (ADR §3.6 bo'yicha),
    shuning uchun bu endpoint barcha autentifikatsiyalangan
    foydalanuvchilarga ochiq.
    """
    return {
        "message": "Katalog ko'rish ruxsati tasdiqlandi",
        "user_role": current_user.role,
        "user_id": str(current_user.id),
    }
