"""
Tickets moduli router — /tickets prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /tickets               — paginated ro'yxat (filter, scope)
  POST   /tickets               — yangi murojaat (do'kon/xodim)
  GET    /tickets/{id}          — murojaat (messages bilan, scope)
  POST   /tickets/{id}/messages — murojaatga xabar qo'shish
  PATCH  /tickets/{id}/status   — holat o'zgartirish (admin/buxgalter)

RBAC:
  GET    /tickets:              admin, buxgalter, agent, do'kon, courier (view)
  POST   /tickets:              admin, agent, do'kon, courier (create)
  GET    /tickets/{id}:         admin, buxgalter, agent, do'kon, courier (view)
  POST   /tickets/{id}/messages: barcha view ruxsati borlar (o'z doirasi)
  PATCH  /tickets/{id}/status:  faqat admin, buxgalter (edit)

Scope/IDOR:
  - do'kon → faqat o'z do'koni murojaatlari
  - agent → o'z do'konlari yoki o'zi yaratgan
  - admin/buxgalter → barchasi + holat o'zgartirish

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.tickets import service
from app.modules.tickets.schemas import (
    PaginatedTickets,
    TicketCreate,
    TicketMessageCreate,
    TicketMessageOut,
    TicketOut,
    TicketStatusUpdate,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["tickets"])


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedTickets,
    summary="Murojaat ro'yxati (paginated)",
    description=(
        "Paginated murojaat ro'yxati. "
        "RBAC + scope: do'kon → o'z murojaatlari, agent → o'z do'konlari yoki o'zi yaratgan, "
        "admin/buxgalter → barchasi. "
        "status filtr: new | in_progress | resolved | closed."
    ),
)
async def list_tickets(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    status: str | None = Query(None, description="Holat filtri: new | in_progress | resolved | closed"),
    ticket_type: str | None = Query(None, description="Tur filtri: taklif | etiroz"),
    store_id: uuid.UUID | None = Query(None, description="Do'kon filtri"),
    current_user: AppUser = require_permission(Module.TICKETS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTickets:
    items, total = await service.list_tickets(
        db,
        user=current_user,
        limit=limit,
        offset=offset,
        status_filter=status,
        type_filter=ticket_type,
        store_id=store_id,
    )
    return PaginatedTickets(
        items=[TicketOut.from_orm_no_messages(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=TicketOut,
    status_code=201,
    summary="Yangi murojaat yaratish",
    description=(
        "Do'kon yoki xodim murojaati. "
        "store_id NULL = xodim murojaati. "
        "client_uuid idempotentlik uchun (ixtiyoriy)."
    ),
    responses={
        404: {"description": "Do'kon scope tashqarisi"},
    },
)
async def create_ticket(
    body: TicketCreate,
    current_user: AppUser = require_permission(Module.TICKETS, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TicketOut:
    ticket = await service.create_ticket(
        db, body, actor_id=current_user.id, user=current_user, redis=redis,
    )
    await db.commit()
    await db.refresh(ticket)
    return TicketOut.from_orm_no_messages(ticket)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{ticket_id}",
    response_model=TicketOut,
    summary="Murojaat (xabarlar bilan)",
    description=(
        "Murojaat ma'lumotlari xabarlar bilan. "
        "RBAC + scope qo'llaniladi. "
        "Scope tashqarisidagi murojaat → 404."
    ),
    responses={
        404: {"description": "Murojaat topilmadi yoki scope tashqarisi"},
    },
)
async def get_ticket(
    ticket_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.TICKETS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    ticket = await service.get_ticket(
        db, ticket_id, user=current_user, with_messages=True
    )
    out = TicketOut.model_validate(ticket)
    out.messages = [TicketMessageOut.model_validate(m) for m in ticket.messages]
    return out


# ─── Add Message ──────────────────────────────────────────────────────────────


@router.post(
    "/{ticket_id}/messages",
    response_model=TicketMessageOut,
    status_code=201,
    summary="Murojaatga xabar qo'shish",
    description=(
        "Murojaatga xabar qo'shadi. "
        "Murojaat ishtirokchilari (scope bo'yicha) yoki admin/buxgalter qo'sha oladi. "
        "attachment_url ixtiyoriy — storage'dan olingan URL (magic-byte validatsiya storage'da)."
    ),
    responses={
        404: {"description": "Murojaat topilmadi yoki scope tashqarisi"},
    },
)
async def add_message(
    ticket_id: uuid.UUID,
    body: TicketMessageCreate,
    current_user: AppUser = require_permission(Module.TICKETS, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> TicketMessageOut:
    msg = await service.add_message(
        db, ticket_id, body, actor_id=current_user.id, user=current_user,
    )
    await db.commit()
    await db.refresh(msg)
    return TicketMessageOut.model_validate(msg)


# ─── Update Status ────────────────────────────────────────────────────────────


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketOut,
    summary="Murojaat holatini o'zgartirish",
    description=(
        "Server-avtoritar holat mashinasi. "
        "Faqat administrator va buxgalter. "
        "new→in_progress→resolved→closed; resolved→in_progress (qayta ochish). "
        "Noqonuniy o'tish → 422. version optimistik lock."
    ),
    responses={
        403: {"description": "Faqat admin/buxgalter bajara oladi"},
        404: {"description": "Murojaat topilmadi"},
        409: {"description": "Versiya konflikti"},
        422: {"description": "Noqonuniy holat o'tishi"},
    },
)
async def update_status(
    ticket_id: uuid.UUID,
    body: TicketStatusUpdate,
    current_user: AppUser = require_permission(Module.TICKETS, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    ticket = await service.update_status(
        db, ticket_id, body, actor_id=current_user.id, user=current_user,
    )
    await db.commit()
    await db.refresh(ticket)
    return TicketOut.from_orm_no_messages(ticket)
