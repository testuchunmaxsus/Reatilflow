"""
AI Tahlil moduli router — Faza 4.

Endpointlar (prefix /analytics):
  GET /analytics/overview         — KPI kartalar
  GET /analytics/stores           — Shartnoma qilgan do'konlar
  GET /analytics/geo-velocity     — Geografik savdo tezligi
  GET /analytics/expiry           — Muddati o'tayotgan partiyalar
  GET /analytics/products         — Top/kam mahsulotlar
  GET /analytics/recommendations  — AI tavsiyalar

RBAC:
  - Barchasi: analytics:view ruxsati (administrator + accountant)
  - agent/courier/store → 403 (korxona-egasi paneli)

ADR §3.4:
  - Barcha endpointlar → replica DB (non-financial, read-only)

MT:
  - enterprise_id JWT'dan (server-avtoritar)
  - superadmin → bo'sh natija (korxona-egasi paneli, platforma emas)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_replica
from app.models.user import AppUser
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    ContractedStoresOut,
    ExpiryReportOut,
    GeoVelocityOut,
    OverviewOut,
    ProductRankingOut,
    RecommendationsOut,
)

router = APIRouter(tags=["analytics"])


# ─── Overview ─────────────────────────────────────────────────────────────────


@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="AI Tahlil: KPI kartalar",
    description=(
        "Korxona uchun asosiy KPI ko'rsatkichlari. "
        "Shartnomadagi do'konlar soni, shartnoma holati (active/expiring/expired), "
        "jami sotilgan va sotuv summasi, expiry-risk SKU soni. "
        "Read replica ishlatiladi. "
        "Faqat administrator va accountant ko'ra oladi. "
        "superadmin → bo'sh natija (korxona-egasi paneli)."
    ),
    responses={
        403: {"description": "Ruxsat yo'q"},
        422: {"description": "Noto'g'ri davr (from > to)"},
    },
)
async def get_overview(
    from_dt: datetime | None = Query(
        None, alias="from", description="Boshlanish vaqti (ISO 8601, default: 30 kun oldin)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to", description="Tugash vaqti (ISO 8601, default: hozir)"
    ),
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> OverviewOut:
    return await service.overview(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
        from_dt=from_dt,
        to_dt=to_dt,
    )


# ─── Contracted Stores ────────────────────────────────────────────────────────


@router.get(
    "/stores",
    response_model=ContractedStoresOut,
    summary="AI Tahlil: Shartnoma qilgan do'konlar",
    description=(
        "Korxona bilan shartnoma qilgan do'konlar ro'yxati. "
        "Har do'kon uchun: shartnoma holati (active/expiring/expired), "
        "joriy inventar qoldig'i va so'nggi 30 kun sotilgan miqdor. "
        "GPS koordinatalari (leaflet xarita uchun) qaytariladi. "
        "Read replica ishlatiladi."
    ),
    responses={403: {"description": "Ruxsat yo'q"}},
)
async def get_contracted_stores(
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> ContractedStoresOut:
    return await service.contracted_stores(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
    )


# ─── Geo Velocity ─────────────────────────────────────────────────────────────


@router.get(
    "/geo-velocity",
    response_model=GeoVelocityOut,
    summary="AI Tahlil: Geografik savdo tezligi",
    description=(
        "Do'kon joylashuvi bo'yicha mening mahsulotlarimni sotuv tezligi (qty/kun). "
        "Leaflet xarita uchun GPS koordinatalari qaytariladi. "
        "Marker o'lchami/rangi velocity_per_day bo'yicha skalanadi. "
        "Read replica ishlatiladi."
    ),
    responses={
        403: {"description": "Ruxsat yo'q"},
        422: {"description": "Noto'g'ri davr (from > to)"},
    },
)
async def get_geo_velocity(
    from_dt: datetime | None = Query(
        None, alias="from", description="Boshlanish vaqti (ISO 8601)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to", description="Tugash vaqti (ISO 8601)"
    ),
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> GeoVelocityOut:
    return await service.geo_velocity(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
        from_dt=from_dt,
        to_dt=to_dt,
    )


# ─── Expiry Report ────────────────────────────────────────────────────────────


@router.get(
    "/expiry",
    response_model=ExpiryReportOut,
    summary="AI Tahlil: Muddati o'tayotgan inventar",
    description=(
        "Muddati o'tgan va within_days kun ichida muddati tugaydigan partiyalar. "
        "Har partiya: do'kon, mahsulot, miqdor, expiry_date, days_left, severity. "
        "severity: expired (muddati o'tgan) | urgent (≤7 kun) | warning (≤30 kun). "
        "Natija expiry_date ASC tartibida. "
        "Read replica ishlatiladi (ix_store_inv_expiry indeksidan foydalanadi)."
    ),
    responses={403: {"description": "Ruxsat yo'q"}},
)
async def get_expiry(
    within_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Filtr: N kun ichida muddati tugaydigan partiyalar (default 30)"
    ),
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> ExpiryReportOut:
    return await service.expiry_report(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
        within_days=within_days,
    )


# ─── Product Ranking ──────────────────────────────────────────────────────────


@router.get(
    "/products",
    response_model=ProductRankingOut,
    summary="AI Tahlil: Mahsulot reytingi",
    description=(
        "Eng ko'p (order=top) yoki eng kam (order=bottom) sotiladigan mahsulotlar. "
        "'bottom' so'rovida 0-sotuvli mahsulotlar ham kiritiladi. "
        "Read replica ishlatiladi."
    ),
    responses={
        403: {"description": "Ruxsat yo'q"},
        422: {"description": "Noto'g'ri davr yoki order qiymati"},
    },
)
async def get_products(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    order: str = Query("top", description="Tartib: top | bottom"),
    limit: int = Query(10, ge=1, le=100, description="Natija soni (default 10, max 100)"),
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> ProductRankingOut:
    return await service.product_ranking(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
        from_dt=from_dt,
        to_dt=to_dt,
        order=order,
        limit=limit,
    )


# ─── Recommendations ─────────────────────────────────────────────────────────


@router.get(
    "/recommendations",
    response_model=RecommendationsOut,
    summary="AI Tahlil: Tavsiyalar",
    description=(
        "Rule-based (R1-R5) + ixtiyoriy Claude AI boyitilgan tavsiyalar. "
        "R1: expiry shoshilinch (≤7 kun, HIGH). "
        "R2: expiry ogohlantirish (≤30 kun, MEDIUM). "
        "R3: qayta to'ldirish kerak (tez sotuv, MEDIUM-HIGH). "
        "R4: sekin harakat (0 sotuv, MEDIUM). "
        "R5: geo hotspot (eng tez sotuv nuqtasi, INFO). "
        "ANTHROPIC_API_KEY bo'lsa ai_summary matn qaytadi, bo'lmasa null. "
        "Read replica ishlatiladi."
    ),
    responses={403: {"description": "Ruxsat yo'q"}},
)
async def get_recommendations(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    current_user: AppUser = require_permission(Module.ANALYTICS, Action.VIEW),
    db: AsyncSession = Depends(get_db_replica),
) -> RecommendationsOut:
    return await service.recommendations(
        db=db,
        enterprise_id=get_current_enterprise_id(current_user),
        from_dt=from_dt,
        to_dt=to_dt,
    )
