"""
Buxgalteriya moduli router — /finance prefiksi bilan main.py ga ulanadi.

Endpointlar:
  POST /finance/ledger                — yozuv qayd etish (accountant: finance:create)
  GET  /finance/balance/{store_id}    — balans (finance:view + scope/IDOR)
  GET  /finance/ledger                — paginated yozuvlar ro'yxati (finance:view + scope)

RBAC:
  - POST: faqat accountant (finance:create).
  - GET balance: finance:view — lekin scope bilan:
    * store: faqat o'z store_id
    * agent: o'z do'konlari
    * accountant/administrator: barchasi
  - IDOR: store roli boshqa store_id ga 404 oladi (mavjudlikni oshkor qilmaslik).

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
from app.modules.finance import service
from app.modules.finance.schemas import (
    AccountBalanceOut,
    LedgerEntryCreate,
    LedgerEntryOut,
    PaginatedLedger,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["finance"])


# ─── Yozuv qayd etish ─────────────────────────────────────────────────────────


@router.post(
    "/ledger",
    response_model=LedgerEntryOut,
    status_code=201,
    summary="Buxgalteriya yozuvini qayd etish (APPEND-ONLY)",
    description=(
        "Yangi buxgalteriya yozuvini qayd etadi. Faqat INSERT — yozuv hech qachon "
        "o'chirilmaydi yoki yangilanmaydi (APPEND-ONLY ledger). "
        "Faqat buxgalter (accountant). client_uuid idempotentlik uchun (24h). "
        "Moliyaviy balans primary DB da yangilanadi (ADR §3.4)."
    ),
    responses={
        404: {"description": "Do'kon topilmadi"},
        409: {"description": "Versiya konflikti"},
    },
)
async def create_ledger_entry(
    body: LedgerEntryCreate,
    current_user: AppUser = require_permission(Module.FINANCE, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LedgerEntryOut:
    enterprise_id = get_current_enterprise_id(current_user)
    entry = await service.record_entry(
        db, body, actor_id=current_user.id, redis=redis, enterprise_id=enterprise_id
    )
    await db.commit()
    await db.refresh(entry)
    return LedgerEntryOut.model_validate(entry)


# ─── Balans olish ─────────────────────────────────────────────────────────────


@router.get(
    "/balance/{store_id}",
    response_model=AccountBalanceOut,
    summary="Do'kon moliyaviy balansini olish",
    description=(
        "Do'kon joriy moliyaviy balansini qaytaradi. "
        "PRIMARY DB dan o'qiladi (replica kechikishini oldini olish — ADR §3.4). "
        "RBAC + IDOR: store roli faqat o'z store_id ni ko'radi; "
        "boshqa store_id → 404 (mavjudlikni oshkor qilmaslik). "
        "Agent — o'z do'konlari. Accountant/administrator — barchasi."
    ),
    responses={
        404: {"description": "Do'kon topilmadi yoki ruxsatsiz (IDOR)"},
    },
)
async def get_balance(
    store_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.FINANCE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> AccountBalanceOut:
    # MUHIM: db = primary DB (ADR §3.4 — moliyaviy o'qish replica emas)
    enterprise_id = get_current_enterprise_id(current_user)
    balance = await service.get_balance(db, store_id, user=current_user, enterprise_id=enterprise_id)
    return AccountBalanceOut.model_validate(balance)


# ─── Yozuvlar ro'yxati ────────────────────────────────────────────────────────


@router.get(
    "/ledger",
    response_model=PaginatedLedger,
    summary="Buxgalteriya yozuvlari ro'yxati (paginated)",
    description=(
        "Paginated buxgalteriya yozuvlari. store_id, type bo'yicha filtr. "
        "RBAC + scope: store — faqat o'z do'koni; agent — o'z do'konlari; "
        "accountant/administrator — barchasi."
    ),
)
async def list_ledger(
    store_id: uuid.UUID | None = Query(None, description="Do'kon filtri"),
    entry_type: str | None = Query(None, description="Tur filtri: debit | credit"),
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    current_user: AppUser = require_permission(Module.FINANCE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedLedger:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_entries(
        db,
        store_id=store_id,
        user=current_user,
        enterprise_id=enterprise_id,
        entry_type=entry_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedLedger(
        items=[LedgerEntryOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
