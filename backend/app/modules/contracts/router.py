"""
Contracts moduli router — /contracts prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /contracts                  — paginated ro'yxat (filter, scope)
  POST   /contracts                  — yangi shartnoma (admin/buxgalter)
  GET    /contracts/{id}             — shartnoma (scope bilan)
  PATCH  /contracts/{id}             — yangilash (admin/buxgalter)
  POST   /contracts/{id}/file        — PDF yuklash (admin/buxgalter)
  DELETE /contracts/{id}             — soft-delete (admin)

RBAC:
  GET    /contracts:          administrator, accountant, agent (view o'z do'konlari), store (o'ziniki)
  POST   /contracts:          administrator, accountant (CREATE)
  PATCH  /contracts/{id}:     administrator, accountant (EDIT)
  POST   /contracts/{id}/file: administrator, accountant (EDIT)
  DELETE /contracts/{id}:     administrator (DELETE)

Scope/IDOR:
  - agent → faqat o'z do'konlari shartnomasi
  - store → faqat o'ziniki
  - admin/buxgalter → barchasi

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.core.storage import StorageBackend, get_storage
from app.models.user import AppUser
from app.modules.contracts import service
from app.modules.contracts.schemas import (
    ContractCreate,
    ContractOut,
    ContractUpdate,
    PaginatedContracts,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["contracts"])


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedContracts,
    summary="Shartnomalar ro'yxati (paginated)",
    description=(
        "Paginated shartnomalar ro'yxati. "
        "RBAC + scope: agent → o'z do'konlari, store → o'ziniki, "
        "admin/buxgalter → barchasi. "
        "status filtr: active | expiring | expired."
    ),
)
async def list_contracts(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    store_id: uuid.UUID | None = Query(None, description="Do'kon filtri"),
    status: str | None = Query(None, description="Status filtri: active | expiring | expired"),
    valid_to_before: date | None = Query(None, description="valid_to < sana"),
    valid_to_after: date | None = Query(None, description="valid_to > sana"),
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedContracts:
    items, total = await service.list_contracts(
        db,
        user=current_user,
        limit=limit,
        offset=offset,
        store_id=store_id,
        status_filter=status,
        valid_to_before=valid_to_before,
        valid_to_after=valid_to_after,
    )
    return PaginatedContracts(
        items=[ContractOut.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ContractOut,
    status_code=201,
    summary="Yangi shartnoma yaratish",
    description="Administrator yoki buxgalter. Shartnoma raqami (store ichida) unikal bo'lishi shart.",
    responses={
        409: {"description": "Dublikat shartnoma raqami"},
        422: {"description": "valid_to < valid_from"},
    },
)
async def create_contract(
    body: ContractCreate,
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ContractOut:
    contract = await service.create_contract(
        db, body, actor_id=current_user.id, user=current_user, redis=redis,
    )
    await db.commit()
    await db.refresh(contract)
    return ContractOut.model_validate(contract)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{contract_id}",
    response_model=ContractOut,
    summary="Shartnoma",
    description=(
        "Shartnoma ma'lumotlari. RBAC + scope qo'llaniladi. "
        "Scope tashqarisidagi shartnoma → 404."
    ),
    responses={
        404: {"description": "Shartnoma topilmadi yoki doiradan tashqari"},
    },
)
async def get_contract(
    contract_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> ContractOut:
    contract = await service.get_contract(db, contract_id, user=current_user)
    return ContractOut.model_validate(contract)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/{contract_id}",
    response_model=ContractOut,
    summary="Shartnomani yangilash (PATCH)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy.",
    responses={
        404: {"description": "Shartnoma topilmadi yoki doiradan tashqari"},
        409: {"description": "Versiya konflikti yoki dublikat raqam"},
        422: {"description": "valid_to < valid_from"},
    },
)
async def update_contract(
    contract_id: uuid.UUID,
    body: ContractUpdate,
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> ContractOut:
    contract = await service.update_contract(
        db, contract_id, body, actor_id=current_user.id, user=current_user,
    )
    await db.commit()
    await db.refresh(contract)
    return ContractOut.model_validate(contract)


# ─── File upload ──────────────────────────────────────────────────────────────


@router.post(
    "/{contract_id}/file",
    response_model=ContractOut,
    summary="Shartnoma faylini yuklash",
    description=(
        "PDF yoki rasm faylini yuklaydi va file_url ni yangilaydi. "
        "Magic bytes validatsiya: PDF, JPEG, PNG, WebP. "
        "Maksimal hajm: 20 MB."
    ),
    responses={
        404: {"description": "Shartnoma topilmadi"},
        422: {"description": "Noto'g'ri fayl formati yoki hajmi"},
    },
)
async def upload_contract_file(
    contract_id: uuid.UUID,
    file: UploadFile,
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> ContractOut:
    # Storage upload (validatsiya storage ichida)
    file_url = await storage.upload_contract_file(file)

    contract = await service.update_contract_file(
        db, contract_id, file_url, actor_id=current_user.id, user=current_user,
    )
    await db.commit()
    await db.refresh(contract)
    return ContractOut.model_validate(contract)


# ─── Delete (soft) ────────────────────────────────────────────────────────────


@router.delete(
    "/{contract_id}",
    status_code=204,
    summary="Shartnomani o'chirish (soft-delete)",
    description="deleted_at o'rnatiladi — DB da qoladi, ro'yxatda ko'rinmaydi.",
    responses={
        404: {"description": "Shartnoma topilmadi yoki doiradan tashqari"},
    },
)
async def delete_contract(
    contract_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CONTRACTS, Action.DELETE),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_contract(
        db, contract_id, actor_id=current_user.id, user=current_user,
    )
    await db.commit()
