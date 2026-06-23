"""
POS router — chakana sotuv endpointlari.

Endpointlar:
  POST   /pos/sales           — yangi sotuv (checkout), status 201
  GET    /pos/sales           — sotuvlar ro'yxati (paginated, scope bilan)
  GET    /pos/sales/{id}      — bitta sotuv (kvitansiya)
  GET    /pos/summary?date=   — kunlik statistika

RBAC:
  POST   — store, administrator
  GET    — store, administrator, accountant
  agent/courier ruxsati yo'q (RBAC darajasida bloklangan)

Module gating: "pos" (main.py da require_module("pos") qo'shiladi).

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.user import AppUser
from app.modules.pos import service
from app.modules.pos.schemas import (
    DailySummaryOut,
    PaginatedSales,
    PosSaleCreate,
    PosSaleOut,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Module, Action

router = APIRouter(tags=["pos"])


# ─── POST /pos/sales ──────────────────────────────────────────────────────────


@router.post(
    "/sales",
    response_model=PosSaleOut,
    status_code=201,
    summary="Yangi POS sotuv (checkout)",
    description=(
        "Kassir chakana sotuv bajaradi. "
        "Narx SERVER tomonida katalogdan olinadi (klient narx bermaydi). "
        "client_uuid bilan idempotentlik kafolatlanadi."
    ),
)
async def create_sale(
    body: PosSaleCreate,
    current_user: AppUser = require_permission(Module.POS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> PosSaleOut:
    enterprise_id = get_current_enterprise_id(current_user)
    sale = await service.create_sale(
        db=db,
        data=body,
        cashier_id=current_user.id,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return PosSaleOut.model_validate(sale)


# ─── GET /pos/sales ───────────────────────────────────────────────────────────


@router.get(
    "/sales",
    response_model=PaginatedSales,
    summary="POS sotuvlar ro'yxati (paginated)",
    description=(
        "RBAC scope bilan: store faqat o'z do'koni, "
        "admin/buxgalter korxona ichida hammasi."
    ),
)
async def list_sales(
    store_id: uuid.UUID | None = Query(None, description="Do'kon bo'yicha filtr"),
    date_from: datetime | None = Query(None, description="Boshlanish sanasi (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Tugash sanasi (ISO 8601)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AppUser = require_permission(Module.POS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedSales:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_sales(
        db=db,
        user=current_user,
        enterprise_id=enterprise_id,
        store_id=store_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedSales(
        items=[PosSaleOut.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /pos/sales/{id} ──────────────────────────────────────────────────────


@router.get(
    "/sales/{sale_id}",
    response_model=PosSaleOut,
    summary="Bitta POS sotuv (kvitansiya)",
    description="RBAC scope: store/admin/buxgalter ruxsatiga ko'ra.",
)
async def get_sale(
    sale_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.POS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PosSaleOut:
    enterprise_id = get_current_enterprise_id(current_user)
    sale = await service.get_sale(
        db=db,
        sale_id=sale_id,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return PosSaleOut.model_validate(sale)


# ─── GET /pos/summary ─────────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=DailySummaryOut,
    summary="Kunlik POS statistika",
    description=(
        "Berilgan kun uchun jami sotuv soni, summasi va "
        "to'lov usuli bo'yicha breakdown qaytaradi. "
        "date parametri bo'lmasa bugungi kun ishlatiladi."
    ),
)
async def daily_summary(
    summary_date: date | None = Query(
        None,
        alias="date",
        description="Kun (YYYY-MM-DD formatida, default: bugun)",
    ),
    store_id: uuid.UUID | None = Query(None, description="Do'kon bo'yicha filtr"),
    current_user: AppUser = require_permission(Module.POS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> DailySummaryOut:
    from datetime import timezone as _tz
    if summary_date is None:
        summary_date = datetime.now(_tz.utc).date()

    enterprise_id = get_current_enterprise_id(current_user)
    return await service.daily_summary(
        db=db,
        summary_date=summary_date,
        enterprise_id=enterprise_id,
        store_id=store_id,
        user=current_user,
    )
