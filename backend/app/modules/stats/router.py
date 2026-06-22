"""
Statistika moduli router — T22.

Endpointlar:
  GET /stats/sales?from=&to=&branch_id=&group_by=     — savdo statistikasi
  GET /stats/delivery?from=&to=&courier_id=           — yetkazish statistikasi
  GET /stats/finance?from=&to=&branch_id=             — moliyaviy statistika (PRIMARY DB)

RBAC:
  - Barchasi: stats:view ruxsati (barcha rollar ruxsatli)
  - finance: courier ko'ra olmaydi → 403 (courier finance:view ruxsatiga ega emas)
  - Scope/IDOR:
    * agent: o'z do'konlari/buyurtmalari
    * courier: o'z yetkazishlari (faqat delivery stats)
    * store: o'z do'koni ma'lumoti
    * accountant/administrator: barchasi

ADR §3.4 / §3.8:
  - sales, delivery → replica DB (get_db_replica)
  - finance → primary DB (get_db) — moliyaviy aniqlik
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, get_db_replica
from app.models.user import AppUser
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module
from app.modules.stats import service
from app.modules.stats.schemas import DeliveryStatsOut, FinanceStatsOut, SalesStatsOut

router = APIRouter(tags=["stats"])


# ─── Savdo statistikasi ───────────────────────────────────────────────────────


@router.get(
    "/sales",
    response_model=SalesStatsOut,
    summary="Savdo statistikasi",
    description=(
        "Buyurtmalar bo'yicha savdo statistikasi. "
        "Read replica ishlatiladi (non-financial, ADR §3.4). "
        "RBAC scope: agent — o'z do'konlari; store — o'z buyurtmalari; "
        "admin/accountant — barchasi. "
        "courier — bo'sh (savdo statistikasi kuryerga tegishli emas). "
        "group_by=day|week|month — dinamika guruhlash."
    ),
    responses={
        422: {"description": "Noto'g'ri davr (from > to) yoki noto'g'ri group_by"},
    },
)
async def get_sales_stats(
    from_dt: datetime | None = Query(
        None, alias="from", description="Boshlanish vaqti (ISO 8601)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to", description="Tugash vaqti (ISO 8601)"
    ),
    branch_id: str | None = Query(
        None, description="Filial filtri (UUID, admin/accountant uchun)"
    ),
    group_by: str | None = Query(
        None, description="Dinamika guruhlash: day | week | month"
    ),
    current_user: AppUser = require_permission(Module.STATS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> SalesStatsOut:
    # Read replica ishlatiladi (non-financial, ADR §3.4)
    return await service.sales_stats(
        db=db,
        user=current_user,
        from_dt=from_dt,
        to_dt=to_dt,
        branch_id=branch_id,
        group_by=group_by,
        enterprise_id=get_current_enterprise_id(current_user),
    )


# ─── Yetkazish statistikasi ───────────────────────────────────────────────────


@router.get(
    "/delivery",
    response_model=DeliveryStatsOut,
    summary="Yetkazish statistikasi",
    description=(
        "Yetkazishlar bo'yicha statistika (kuryer samaradorligi). "
        "Read replica ishlatiladi (non-financial, ADR §3.4). "
        "RBAC scope: courier — o'z yetkazishlari; agent — o'z do'konlari; "
        "store — o'z buyurtmalarining yetkazishlari; admin/accountant — barchasi."
    ),
    responses={
        422: {"description": "Noto'g'ri davr (from > to)"},
    },
)
async def get_delivery_stats(
    from_dt: datetime | None = Query(
        None, alias="from", description="Boshlanish vaqti (ISO 8601)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to", description="Tugash vaqti (ISO 8601)"
    ),
    courier_id: str | None = Query(
        None, description="Kuryer filtri (UUID, admin uchun)"
    ),
    current_user: AppUser = require_permission(Module.STATS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> DeliveryStatsOut:
    # Read replica ishlatiladi (non-financial, ADR §3.4)
    return await service.delivery_stats(
        db=db,
        user=current_user,
        from_dt=from_dt,
        to_dt=to_dt,
        courier_id=courier_id,
        enterprise_id=get_current_enterprise_id(current_user),
    )


# ─── Moliyaviy statistika ─────────────────────────────────────────────────────


@router.get(
    "/finance",
    response_model=FinanceStatsOut,
    summary="Moliyaviy statistika (PRIMARY DB)",
    description=(
        "Do'kon bo'yicha qarz/haqdorlik va jami debit/credit statistikasi. "
        "PRIMARY DB ishlatiladi (moliyaviy aniqlik, ADR §3.8 — replica kechikishi xavfi). "
        "RBAC scope: accountant/administrator — barchasi; "
        "agent — o'z do'konlari; store — faqat o'z balansi. "
        "courier bu endpointni ko'ra olmaydi (finance:view ruxsati yo'q)."
    ),
    responses={
        403: {"description": "Ruxsat yo'q (courier va boshqa ruxsatsiz rollar)"},
        422: {"description": "Noto'g'ri davr (from > to)"},
    },
)
async def get_finance_stats(
    from_dt: datetime | None = Query(
        None, alias="from", description="Boshlanish vaqti (ISO 8601, ledger_entry.entry_date)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to", description="Tugash vaqti (ISO 8601)"
    ),
    branch_id: str | None = Query(
        None, description="Filial filtri (UUID, admin/accountant uchun)"
    ),
    # MUHIM: finance:view — courier ruxsatga ega emas → 403
    current_user: AppUser = require_permission(Module.FINANCE, Action.VIEW),
    # MUHIM: PRIMARY DB — moliyaviy o'qish replica emas (ADR §3.8)
    db: AsyncSession = Depends(get_db),
) -> FinanceStatsOut:
    return await service.finance_stats(
        db=db,
        user=current_user,
        from_dt=from_dt,
        to_dt=to_dt,
        branch_id=branch_id,
        enterprise_id=get_current_enterprise_id(current_user),
    )
