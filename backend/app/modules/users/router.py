"""
Users moduli router — /users prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /users              — paginated ro'yxat (filter: role, branch, is_active)
  POST   /users              — yangi foydalanuvchi yaratish (admin only)
  GET    /users/{id}         — foydalanuvchi ma'lumotlari
  PATCH  /users/{id}         — yangilash (PATCH, optimistik lock)
  PATCH  /users/{id}/deactivate — deaktivatsiya (is_active=False)
  PATCH  /users/{id}/activate   — qayta aktivlashtirish (is_active=True)

RBAC:
  - Barcha endpointlar faqat administrator uchun.
  - require_permission(Module.RBAC, Action.CREATE/VIEW/EDIT) + role != administrator → 403.

i18n: ?lang= query parametri yoki Accept-Language headeridan.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module
from app.modules.users import service
from app.modules.users.schemas import (
    PaginatedUsers,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(tags=["users"])


def _admin_only(current_user: AppUser) -> None:
    """Faqat administrator ruxsat beriladi. Boshqa rollar → 403."""
    if current_user.role != "administrator":
        raise AppError("rbac.permission_denied", status_code=403, params={
            "module": "users",
            "action": "manage",
            "role": current_user.role,
        })


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedUsers,
    summary="Foydalanuvchilar ro'yxati (paginated)",
    description=(
        "Paginated foydalanuvchilar ro'yxati. Faqat administrator. "
        "Filtrlar: role, branch_id, is_active."
    ),
)
async def list_users(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    role: str | None = Query(None, description="Rol bo'yicha filtrlash"),
    branch_id: uuid.UUID | None = Query(None, description="Filial filtri"),
    is_active: bool | None = Query(None, description="Aktiv/bloklangan filtri"),
    current_user: AppUser = require_permission(Module.RBAC, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedUsers:
    _admin_only(current_user)
    items, total = await service.list_users(
        db,
        limit=limit,
        offset=offset,
        role=role,
        branch_id=branch_id,
        is_active=is_active,
    )
    return PaginatedUsers(
        items=[UserOut.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Yangi foydalanuvchi yaratish",
    description="Faqat administrator. Telefon unikal bo'lishi shart.",
    responses={
        409: {"description": "Dublikat telefon raqam"},
        422: {"description": "Noto'g'ri rol yoki validatsiya xatosi"},
    },
)
async def create_user(
    body: UserCreate,
    current_user: AppUser = require_permission(Module.RBAC, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> UserOut:
    _admin_only(current_user)
    user = await service.create_user(db, body, actor_id=current_user.id, redis=redis)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Foydalanuvchi",
    description="Foydalanuvchi ma'lumotlari. Faqat administrator.",
    responses={
        404: {"description": "Foydalanuvchi topilmadi"},
    },
)
async def get_user(
    user_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.RBAC, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    _admin_only(current_user)
    user = await service.get_user(db, user_id)
    return UserOut.model_validate(user)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Foydalanuvchini yangilash (PATCH)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy. Faqat administrator.",
    responses={
        404: {"description": "Foydalanuvchi topilmadi"},
        409: {"description": "Versiya konflikti yoki dublikat telefon"},
        422: {"description": "Noto'g'ri rol"},
    },
)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: AppUser = require_permission(Module.RBAC, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    _admin_only(current_user)
    user = await service.update_user(db, user_id, body, actor_id=current_user.id)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ─── Deactivate ───────────────────────────────────────────────────────────────


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserOut,
    summary="Foydalanuvchini deaktivatsiya qilish",
    description=(
        "is_active=False o'rnatiladi — hisob bloklanadi. "
        "Admin o'zini deaktiv qila olmaydi. Faqat administrator."
    ),
    responses={
        403: {"description": "Admin o'zini deaktiv qila olmaydi"},
        404: {"description": "Foydalanuvchi topilmadi"},
    },
)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.RBAC, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    _admin_only(current_user)
    user = await service.deactivate_user(
        db, user_id, actor_id=current_user.id, current_user=current_user
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


# ─── Activate ─────────────────────────────────────────────────────────────────


@router.patch(
    "/{user_id}/activate",
    response_model=UserOut,
    summary="Foydalanuvchini qayta aktivlashtirish",
    description=(
        "is_active=True o'rnatiladi — bloklangan hisob qaytariladi. "
        "Deaktivatsiyaning teskarisi. Faqat administrator."
    ),
    responses={
        404: {"description": "Foydalanuvchi topilmadi"},
    },
)
async def activate_user(
    user_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.RBAC, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    _admin_only(current_user)
    user = await service.activate_user(db, user_id, actor_id=current_user.id)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)
