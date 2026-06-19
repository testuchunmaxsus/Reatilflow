"""
Customers moduli router — /customers/stores prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /customers/stores            — paginated ro'yxat (filter, blind-index qidiruv)
  POST   /customers/stores            — yangi do'kon (admin/agent)
  GET    /customers/stores/{id}       — do'kon (scope bilan)
  PATCH  /customers/stores/{id}       — yangilash (admin/agent o'z hududi)
  DELETE /customers/stores/{id}       — soft-delete (admin)
  POST   /customers/stores/{id}/assign-agent — agent biriktirish (admin)

RBAC:
  - require_permission(Module.CUSTOMERS, Action.*) orqali himoyalangan.
  - Kuryer → StoreLimitedOut (inn/credit_limit YO'Q).
  - Store roli → faqat o'z do'koni (Store.user_id == user.id).

i18n: ?lang= query parametri yoki Accept-Language headeridan.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.customers import service
from app.modules.customers.schemas import (
    AssignAgentRequest,
    PaginatedStores,
    StoreCreate,
    StoreLimitedOut,
    StoreOut,
    StoreUpdate,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["customers"])


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _store_out(store, user: AppUser) -> StoreOut | StoreLimitedOut:
    """
    Store ORM → javob sxemasi.

    Kuryer → StoreLimitedOut (faqat manzil/koordinata, PII yo'q).
    Boshqalar → StoreOut (to'liq).

    Xavfsizlik: kuryer rolida credit_limit/inn/inps/phone oqib ketmasin.
    """
    if user.role == "courier":
        return StoreLimitedOut.model_validate(store)
    return StoreOut.model_validate(store)


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "/stores",
    summary="Do'konlar ro'yxati (paginated)",
    description=(
        "Paginated do'konlar ro'yxati. "
        "RBAC + scope: agent → o'z do'konlari, store → o'zi, "
        "courier → StoreLimitedOut (PII yo'q), admin/accountant → branch. "
        "inn/phone qidiruv blind-index orqali (ochiq-matn LIKE emas)."
    ),
)
async def list_stores(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    branch_id: uuid.UUID | None = Query(None, description="Filial filtri"),
    search_inn: str | None = Query(None, max_length=20, description="INN bo'yicha qidiruv"),
    search_phone: str | None = Query(None, max_length=20, description="Telefon bo'yicha qidiruv"),
    search_name: str | None = Query(None, max_length=100, description="Nom bo'yicha qidiruv"),
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_stores(
        db,
        user=current_user,
        limit=limit,
        offset=offset,
        branch_id=branch_id,
        search_inn=search_inn,
        search_phone=search_phone,
        search_name=search_name,
    )

    # Kuryer uchun barcha items StoreLimitedOut sifatida
    if current_user.role == "courier":
        limited_items = [StoreLimitedOut.model_validate(s) for s in items]
        return {
            "items": limited_items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    return PaginatedStores(
        items=[StoreOut.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "/stores",
    response_model=StoreOut,
    status_code=201,
    summary="Yangi do'kon yaratish",
    description="Admin yoki agent. INN unikal bo'lishi shart.",
    responses={
        409: {"description": "Dublikat INN"},
    },
)
async def create_store(
    body: StoreCreate,
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StoreOut:
    store = await service.create_store(db, body, actor_id=current_user.id, redis=redis)
    await db.commit()
    await db.refresh(store)
    return StoreOut.model_validate(store)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/stores/{store_id}",
    summary="Do'kon",
    description=(
        "Do'kon ma'lumotlari. RBAC + scope qo'llaniladi. "
        "Kuryer StoreLimitedOut (PII yo'q) oladi."
    ),
    responses={
        404: {"description": "Do'kon topilmadi yoki doiradan tashqari"},
    },
)
async def get_store(
    store_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
):
    store = await service.get_store(db, store_id, user=current_user)
    return _store_out(store, current_user)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/stores/{store_id}",
    response_model=StoreOut,
    summary="Do'konni yangilash (PATCH)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy.",
    responses={
        404: {"description": "Do'kon topilmadi yoki doiradan tashqari"},
        409: {"description": "Versiya konflikti yoki dublikat INN"},
    },
)
async def update_store(
    store_id: uuid.UUID,
    body: StoreUpdate,
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> StoreOut:
    store = await service.update_store(
        db, store_id, body, actor_id=current_user.id, user=current_user
    )
    await db.commit()
    await db.refresh(store)
    return StoreOut.model_validate(store)


# ─── Delete (soft) ────────────────────────────────────────────────────────────


@router.delete(
    "/stores/{store_id}",
    status_code=204,
    summary="Do'konni o'chirish (soft-delete)",
    description="deleted_at o'rnatiladi — DB da qoladi, ro'yxatda ko'rinmaydi.",
    responses={
        404: {"description": "Do'kon topilmadi yoki doiradan tashqari"},
    },
)
async def delete_store(
    store_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.DELETE),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_store(db, store_id, actor_id=current_user.id, user=current_user)
    await db.commit()


# ─── Assign Agent ─────────────────────────────────────────────────────────────


@router.post(
    "/stores/{store_id}/assign-agent",
    status_code=200,
    summary="Do'konga agent biriktirish",
    description="Faqat administrator. AgentStore yozuvi yaratiladi. Idempotent.",
    responses={
        403: {"description": "Faqat administrator bajara oladi"},
        404: {"description": "Do'kon yoki agent topilmadi"},
    },
)
async def assign_agent(
    store_id: uuid.UUID,
    body: AssignAgentRequest,
    current_user: AppUser = require_permission(Module.CUSTOMERS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
):
    # AUTHZ: faqat administrator agent biriktira oladi (agent/store/courier TAQIQLANGAN).
    from app.core.errors import AppError as _AppError
    if current_user.role != "administrator":
        raise _AppError("customers.forbidden", status_code=403)

    link = await service.assign_agent(
        db,
        store_id=store_id,
        agent_id=body.agent_id,
        actor_id=current_user.id,
        user=current_user,
    )
    await db.commit()
    return {
        "store_id": str(store_id),
        "agent_id": str(link.agent_id),
        "assigned_at": link.assigned_at.isoformat(),
    }
