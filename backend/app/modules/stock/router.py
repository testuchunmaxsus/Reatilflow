"""
Ombor moduli router — /stock prefiksi bilan main.py ga ulanadi.

Endpointlar:
  POST /stock/movements           — harakat qayd etish (admin: stock:create)
  GET  /stock/balance             — qoldiq (stock:view)
  GET  /stock/movements           — paginated harakatlar ro'yxati (stock:view)

RBAC:
  - POST: faqat administrator (require_permission stock:create).
  - GET:  barcha ruxsatli rollar (stock:view).

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
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module
from app.modules.stock import service
from app.modules.stock.schemas import (
    PaginatedMovements,
    StockBalanceOut,
    StockMovementCreate,
    StockMovementOut,
)

router = APIRouter(tags=["stock"])


# ─── Harakat qayd etish ───────────────────────────────────────────────────────


@router.post(
    "/movements",
    response_model=StockMovementOut,
    status_code=201,
    summary="Ombor harakatini qayd etish (APPEND-ONLY)",
    description=(
        "Yangi ombor harakatini qayd etadi. Faqat INSERT — harakat hech qachon "
        "o'chirilmaydi yoki yangilanmaydi (APPEND-ONLY ledger). "
        "Faqat administrator. client_uuid idempotentlik uchun (24h)."
    ),
    responses={
        404: {"description": "Mahsulot topilmadi"},
        409: {"description": "Yetarli qoldiq yo'q yoki versiya konflikti"},
    },
)
async def create_movement(
    body: StockMovementCreate,
    current_user: AppUser = require_permission(Module.STOCK, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StockMovementOut:
    enterprise_id = get_current_enterprise_id(current_user)
    movement = await service.record_movement(
        db, body, actor_id=current_user.id, redis=redis, enterprise_id=enterprise_id
    )
    await db.commit()
    await db.refresh(movement)
    return StockMovementOut.model_validate(movement)


# ─── Qoldiq olish ─────────────────────────────────────────────────────────────


@router.get(
    "/balance",
    response_model=StockBalanceOut,
    summary="Mahsulot qoldig'ini olish",
    description=(
        "Mahsulot + ombor bo'yicha joriy qoldiqni qaytaradi. "
        "Primary DB dan o'qiladi (replica kechikishini oldini olish). "
        "Barcha ruxsatli rollar uchun (stock:view)."
    ),
)
async def get_balance(
    product_id: uuid.UUID = Query(..., description="Mahsulot ID"),
    warehouse_id: uuid.UUID = Query(..., description="Ombor ID"),
    current_user: AppUser = require_permission(Module.STOCK, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> StockBalanceOut:
    balance = await service.get_balance(db, product_id, warehouse_id)
    return StockBalanceOut.model_validate(balance)


# ─── Harakatlar ro'yxati ──────────────────────────────────────────────────────


@router.get(
    "/movements",
    response_model=PaginatedMovements,
    summary="Ombor harakatlari ro'yxati (paginated)",
    description=(
        "Paginated ombor harakatlari. "
        "product_id, warehouse_id, type bo'yicha filtr. "
        "Barcha ruxsatli rollar (stock:view)."
    ),
)
async def list_movements(
    product_id: uuid.UUID | None = Query(None, description="Mahsulot filtri"),
    warehouse_id: uuid.UUID | None = Query(None, description="Ombor filtri"),
    movement_type: str | None = Query(None, description="Tur filtri: in | out | transfer | adjust"),
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    current_user: AppUser = require_permission(Module.STOCK, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedMovements:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_movements(
        db,
        enterprise_id=enterprise_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedMovements(
        items=[StockMovementOut.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )
