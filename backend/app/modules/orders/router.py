"""
Buyurtma router — T11, T12.

Endpointlar (T11):
  POST   /orders              — yangi buyurtma yaratish (orders:create)
  GET    /orders              — buyurtmalar ro'yxati (orders:view, paginated)
  GET    /orders/{id}         — bitta buyurtma (orders:view)
  PATCH  /orders/{id}/status  — holat o'zgartirish (orders:edit)

Endpointlar (T12 — Shablon):
  POST   /orders/templates                — shablon yaratish (orders:create)
  GET    /orders/templates                — shablonlar ro'yxati (orders:view, paginated)
  GET    /orders/templates/{id}           — bitta shablon (orders:view)
  DELETE /orders/templates/{id}           — shablonni o'chirish (orders:edit)
  POST   /orders/templates/{id}/apply     — shablondan buyurtma yaratish (orders:create) → 201

RBAC:
  POST   — administrator, agent (o'z do'konlari uchun)
  GET    — administrator, agent, accountant, store (scope bilan)
  PATCH  — administrator, agent (o'z buyurtmalari), accountant (faqat view — edit yo'q)
  DELETE — administrator, agent (o'z do'konlari shablonlari)

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).

MUHIM (T12): /orders/templates marshrutlari /orders/{order_id} dan OLDIN ro'yxatga olinishi kerak.
  Aks holda FastAPI "templates" ni order_id sifatida talqin qiladi.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.orders import service
from app.modules.orders.schemas import (
    ApplyTemplateIn,
    OrderCreate,
    OrderOut,
    OrderStatusUpdate,
    OrderTemplateCreate,
    OrderTemplateOut,
    PaginatedOrders,
    PaginatedTemplates,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Module, Action

router = APIRouter(tags=["orders"])


# ─── POST /orders ─────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=OrderOut,
    status_code=201,
    summary="Yangi buyurtma yaratish",
    description=(
        "Atomik tranzaksiyada buyurtma + stock chiqimi + ledger debit yozadi. "
        "Qoldiq yetmasa → 409 (barcha yozuvlar rollback). "
        "client_uuid bilan idempotentlik kafolatlanadi."
    ),
)
async def create_order(
    body: OrderCreate,
    current_user: AppUser = require_permission(Module.ORDERS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> OrderOut:
    enterprise_id = get_current_enterprise_id(current_user)
    order = await service.create_order(
        db=db,
        data=body,
        actor_id=current_user.id,
        user=current_user,
        redis=redis,
        enterprise_id=enterprise_id,
    )
    return OrderOut.model_validate(order)


# ─── GET /orders ──────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedOrders,
    summary="Buyurtmalar ro'yxati (paginated)",
    description=(
        "RBAC scope bilan: agent faqat o'z do'konlari, "
        "store faqat o'z do'koni, admin/buxgalter barchasi."
    ),
)
async def list_orders(
    store_id: uuid.UUID | None = Query(None, description="Do'kon bo'yicha filtr"),
    agent_id: uuid.UUID | None = Query(None, description="Agent bo'yicha filtr"),
    status: str | None = Query(None, description="Holat bo'yicha filtr"),
    date_from: datetime | None = Query(None, description="Boshlanish sanasi (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Tugash sanasi (ISO 8601)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AppUser = require_permission(Module.ORDERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedOrders:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_orders(
        db=db,
        user=current_user,
        enterprise_id=enterprise_id,
        store_id=store_id,
        agent_id=agent_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PaginatedOrders(
        items=[OrderOut.model_validate(o) for o in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── T12: Shablon endpointlari ────────────────────────────────────────────────
# MUHIM: Bu marshrutlar /{order_id} dan OLDIN ro'yxatga olinishi kerak.
# Aks holda FastAPI "templates" ni order_id sifatida talqin qiladi.


@router.post(
    "/templates",
    response_model=OrderTemplateOut,
    status_code=201,
    summary="Yangi shablon yaratish",
    description=(
        "Buyurtma shabloni yaratadi (faqat product_id + qty; NARX SAQLANMAYDI). "
        "Narx apply paytida katalogdan olinadi (server-avtoritar)."
    ),
)
async def create_template(
    body: OrderTemplateCreate,
    current_user: AppUser = require_permission(Module.ORDERS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> OrderTemplateOut:
    enterprise_id = get_current_enterprise_id(current_user)
    template = await service.create_template(
        db=db,
        data=body,
        actor_id=current_user.id,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return OrderTemplateOut.model_validate(template)


@router.get(
    "/templates",
    response_model=PaginatedTemplates,
    summary="Shablonlar ro'yxati (paginated)",
    description=(
        "RBAC scope bilan: agent faqat o'z do'konlari, "
        "store faqat o'z do'koni, admin/buxgalter barchasi."
    ),
)
async def list_templates(
    store_id: uuid.UUID | None = Query(None, description="Do'kon bo'yicha filtr"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AppUser = require_permission(Module.ORDERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTemplates:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_templates(
        db=db,
        store_id=store_id,
        user=current_user,
        enterprise_id=enterprise_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedTemplates(
        items=[OrderTemplateOut.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/templates/{template_id}",
    response_model=OrderTemplateOut,
    summary="Bitta shablon",
    description="RBAC scope: agent/store/accountant/admin ruxsatiga ko'ra.",
)
async def get_template(
    template_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.ORDERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> OrderTemplateOut:
    enterprise_id = get_current_enterprise_id(current_user)
    template = await service.get_template(db=db, template_id=template_id, user=current_user, enterprise_id=enterprise_id)
    return OrderTemplateOut.model_validate(template)


@router.delete(
    "/templates/{template_id}",
    status_code=204,
    summary="Shablonni o'chirish (soft delete)",
    description="Soft delete: deleted_at o'rnatiladi, ma'lumotlar saqlanadi.",
)
async def delete_template(
    template_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.ORDERS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> None:
    enterprise_id = get_current_enterprise_id(current_user)
    await service.delete_template(
        db=db,
        template_id=template_id,
        user=current_user,
        actor_id=current_user.id,
        enterprise_id=enterprise_id,
    )


@router.post(
    "/templates/{template_id}/apply",
    response_model=OrderOut,
    status_code=201,
    summary="Shablon apply — yangi buyurtma yaratish",
    description=(
        "Shablon qatorlaridan yangi buyurtma yaratadi. "
        "Narx SERVER tomonida katalogdan olinadi (server-avtoritar). "
        "Atomik: ombor chiqimi + ledger debit bir tranzaksiyada. "
        "client_uuid bilan idempotentlik kafolatlanadi. "
        "Shablon O'ZGARMAYDI."
    ),
)
async def apply_template(
    template_id: uuid.UUID,
    body: ApplyTemplateIn,
    current_user: AppUser = require_permission(Module.ORDERS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> OrderOut:
    enterprise_id = get_current_enterprise_id(current_user)
    order = await service.apply_template(
        db=db,
        template_id=template_id,
        apply_data=body,
        actor_id=current_user.id,
        user=current_user,
        redis=redis,
        enterprise_id=enterprise_id,
    )
    return OrderOut.model_validate(order)


# ─── GET /orders/{id} ─────────────────────────────────────────────────────────


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Bitta buyurtma",
    description="RBAC scope: agent/store/accountant/admin ruxsatiga ko'ra.",
)
async def get_order(
    order_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.ORDERS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    enterprise_id = get_current_enterprise_id(current_user)
    order = await service.get_order(db=db, order_id=order_id, user=current_user, enterprise_id=enterprise_id)
    return OrderOut.model_validate(order)


# ─── PATCH /orders/{id}/status ────────────────────────────────────────────────


@router.patch(
    "/{order_id}/status",
    response_model=OrderOut,
    summary="Buyurtma holatini o'zgartirish",
    description=(
        "Server-avtoritar holat mashinasi: faqat qonuniy o'tishlar ruxsat. "
        "Noqonuniy → 422 invalid_transition. "
        "version optimistik lock: mos kelmasa → 409."
    ),
)
async def update_status(
    order_id: uuid.UUID,
    body: OrderStatusUpdate,
    current_user: AppUser = require_permission(Module.ORDERS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> OrderOut:
    enterprise_id = get_current_enterprise_id(current_user)
    order = await service.update_status(
        db=db,
        order_id=order_id,
        data=body,
        user=current_user,
        enterprise_id=enterprise_id,
    )
    return OrderOut.model_validate(order)
