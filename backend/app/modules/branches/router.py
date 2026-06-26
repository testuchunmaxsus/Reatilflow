"""
Branches moduli router — /branches prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /branches              — paginated ro'yxat (filter: is_active)
  POST   /branches              — yangi filial yaratish (admin only)
  GET    /branches/{id}         — filial ma'lumotlari (admin only)
  PATCH  /branches/{id}         — yangilash (PATCH, optimistik lock, admin only)
  DELETE /branches/{id}         — soft-delete (admin only)

RBAC:
  - GET ro'yxat: Module.RBAC, Action.VIEW  (users moduli naqshi)
  - POST/PATCH/DELETE: faqat administrator roli (Module.RBAC + Action.CREATE/EDIT/DELETE)
  - _admin_only() qo'shimcha rol tekshiruvi — non-admin 403 oladi.

i18n: ?lang= query parametri yoki Accept-Language headeridan.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.models.user import AppUser
from app.modules.branches import service
from app.modules.branches.schemas import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    PaginatedBranches,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["branches"])


def _admin_only(current_user: AppUser) -> None:
    """Faqat administrator ruxsat beriladi. Boshqa rollar → 403."""
    if current_user.role != "administrator":
        raise AppError("rbac.permission_denied", status_code=403, params={
            "module": "branches",
            "action": "manage",
            "role": current_user.role,
        })


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedBranches,
    summary="Filiallar ro'yxati (paginated)",
    description=(
        "Paginated filiallar ro'yxati. "
        "Faqat administrator. "
        "Filtrlar: is_active."
    ),
)
async def list_branches(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    is_active: bool | None = Query(None, description="Faol/nofaol filtri"),
    current_user: AppUser = require_permission(Module.RBAC, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedBranches:
    _admin_only(current_user)
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_branches(
        db,
        enterprise_id=enterprise_id,
        limit=limit,
        offset=offset,
        is_active=is_active,
    )
    return PaginatedBranches(
        items=[BranchOut.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=BranchOut,
    status_code=201,
    summary="Yangi filial yaratish",
    description="Faqat administrator.",
    responses={
        403: {"description": "Administrator huquqi kerak"},
    },
)
async def create_branch(
    body: BranchCreate,
    current_user: AppUser = require_permission(Module.RBAC, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> BranchOut:
    _admin_only(current_user)
    enterprise_id = get_current_enterprise_id(current_user)
    branch = await service.create_branch(
        db, body, actor_id=current_user.id, enterprise_id=enterprise_id
    )
    await db.commit()
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{branch_id}",
    response_model=BranchOut,
    summary="Filial",
    description="Filial ma'lumotlari. Faqat administrator.",
    responses={
        404: {"description": "Filial topilmadi"},
    },
)
async def get_branch(
    branch_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.RBAC, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> BranchOut:
    _admin_only(current_user)
    enterprise_id = get_current_enterprise_id(current_user)
    branch = await service.get_branch(db, branch_id, enterprise_id=enterprise_id)
    return BranchOut.model_validate(branch)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/{branch_id}",
    response_model=BranchOut,
    summary="Filialni yangilash (PATCH)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy. Faqat administrator.",
    responses={
        404: {"description": "Filial topilmadi"},
        409: {"description": "Versiya konflikti"},
    },
)
async def update_branch(
    branch_id: uuid.UUID,
    body: BranchUpdate,
    current_user: AppUser = require_permission(Module.RBAC, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> BranchOut:
    _admin_only(current_user)
    enterprise_id = get_current_enterprise_id(current_user)
    branch = await service.update_branch(
        db, branch_id, body, actor_id=current_user.id, enterprise_id=enterprise_id
    )
    await db.commit()
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


# ─── Delete (soft) ────────────────────────────────────────────────────────────


@router.delete(
    "/{branch_id}",
    status_code=204,
    summary="Filialni o'chirish (soft-delete)",
    description="deleted_at o'rnatiladi — DB da qoladi, ro'yxatda ko'rinmaydi. Faqat administrator.",
    responses={
        404: {"description": "Filial topilmadi"},
    },
)
async def delete_branch(
    branch_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.RBAC, Action.DELETE),
    db: AsyncSession = Depends(get_db),
) -> None:
    _admin_only(current_user)
    enterprise_id = get_current_enterprise_id(current_user)
    await service.delete_branch(
        db, branch_id, actor_id=current_user.id, enterprise_id=enterprise_id
    )
    await db.commit()
