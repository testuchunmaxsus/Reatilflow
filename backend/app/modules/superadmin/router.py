"""
Superadmin router — /superadmin prefiksi, MT4.

Endpointlar (faqat superadmin roli):
  POST   /superadmin/enterprises          — korxona + birinchi admin yaratish
  GET    /superadmin/enterprises          — barcha korxonalar (paginated)
  GET    /superadmin/enterprises/{id}     — bitta korxona
  PATCH  /superadmin/enterprises/{id}     — name/enabled_modules/status yangilash
  PATCH  /superadmin/enterprises/{id}/suspend  — to'xtatib qo'yish
  PATCH  /superadmin/enterprises/{id}/activate — qayta faollashtirish

CORE modul: module gate YO'Q.
superadmin dependency har endpointda tekshiriladi.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.superadmin.dependency import require_superadmin
from app.modules.superadmin.schemas import (
    EnterpriseAdminOut,
    EnterpriseCreate,
    EnterpriseOut,
    EnterprisePaginated,
    EnterpriseUpdate,
    AdminOut,
)
from app.modules.superadmin.service import (
    activate_enterprise,
    create_enterprise_with_admin,
    get_enterprise,
    list_enterprises,
    suspend_enterprise,
    update_enterprise,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["superadmin"])


# ─── POST /superadmin/enterprises ────────────────────────────────────────────


@router.post(
    "/enterprises",
    response_model=EnterpriseAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Korxona va birinchi admin yaratish",
    description=(
        "Yangi korxona (tenant) va uning birinchi administratorini yaratadi. "
        "Javobda parol QAYTARILMAYDI. "
        "Faqat superadmin."
    ),
    responses={
        201: {"description": "Korxona va admin muvaffaqiyatli yaratildi"},
        403: {"description": "Faqat superadmin"},
        409: {"description": "Telefon raqam allaqachon band"},
    },
)
async def create_enterprise(
    body: EnterpriseCreate,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> EnterpriseAdminOut:
    """Korxona va birinchi administratorni yaratadi."""
    enterprise, admin = await create_enterprise_with_admin(
        db=db,
        data=body,
        actor_id=current_user.id,
        redis=redis,
    )

    return EnterpriseAdminOut(
        enterprise=EnterpriseOut.model_validate(enterprise),
        admin=AdminOut.model_validate(admin),
    )


# ─── GET /superadmin/enterprises ─────────────────────────────────────────────


@router.get(
    "/enterprises",
    response_model=EnterprisePaginated,
    status_code=status.HTTP_200_OK,
    summary="Barcha korxonalar ro'yxati",
    description="Paginated korxonalar ro'yxati. Faqat superadmin.",
    responses={
        200: {"description": "Korxonalar ro'yxati"},
        403: {"description": "Faqat superadmin"},
    },
)
async def get_enterprises(
    limit: int = Query(20, ge=1, le=100, description="Sahifadagi yozuvlar soni"),
    offset: int = Query(0, ge=0, description="Boshlash joyi"),
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePaginated:
    """Barcha korxonalar ro'yxatini qaytaradi."""
    items, total = await list_enterprises(db, limit=limit, offset=offset)
    return EnterprisePaginated(
        items=[EnterpriseOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /superadmin/enterprises/{id} ────────────────────────────────────────


@router.get(
    "/enterprises/{enterprise_id}",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="Bitta korxona ma'lumotlari",
    description="ID bo'yicha korxona ma'lumotlarini qaytaradi. Faqat superadmin.",
    responses={
        200: {"description": "Korxona ma'lumotlari"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Korxona topilmadi"},
    },
)
async def get_single_enterprise(
    enterprise_id: uuid.UUID,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """ID bo'yicha korxona ma'lumotlarini qaytaradi."""
    enterprise = await get_enterprise(db, enterprise_id)
    return EnterpriseOut.model_validate(enterprise)


# ─── PATCH /superadmin/enterprises/{id} ──────────────────────────────────────


@router.patch(
    "/enterprises/{enterprise_id}",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="Korxonani yangilash",
    description=(
        "Korxona name, enabled_modules va/yoki status ni yangilaydi. "
        "Optimistik lock — version talab qilinadi. Faqat superadmin."
    ),
    responses={
        200: {"description": "Yangilangan korxona"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Korxona topilmadi"},
        409: {"description": "Versiya konflikti"},
        422: {"description": "Noto'g'ri status qiymati"},
    },
)
async def patch_enterprise(
    enterprise_id: uuid.UUID,
    body: EnterpriseUpdate,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """Korxona ma'lumotlarini yangilaydi."""
    enterprise = await update_enterprise(db, enterprise_id, body)
    await db.flush()
    return EnterpriseOut.model_validate(enterprise)


# ─── PATCH /superadmin/enterprises/{id}/suspend ──────────────────────────────


@router.patch(
    "/enterprises/{enterprise_id}/suspend",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="Korxonani to'xtatib qo'yish",
    description=(
        "Korxona status='suspended' qilinadi. "
        "Suspended korxona foydalanuvchilari login qila olmaydi. Faqat superadmin."
    ),
    responses={
        200: {"description": "Korxona to'xtatildi"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Korxona topilmadi"},
    },
)
async def suspend_enterprise_endpoint(
    enterprise_id: uuid.UUID,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """Korxonani to'xtatib qo'yadi."""
    enterprise = await suspend_enterprise(db, enterprise_id)
    await db.flush()
    return EnterpriseOut.model_validate(enterprise)


# ─── PATCH /superadmin/enterprises/{id}/activate ─────────────────────────────


@router.patch(
    "/enterprises/{enterprise_id}/activate",
    response_model=EnterpriseOut,
    status_code=status.HTTP_200_OK,
    summary="Korxonani qayta faollashtirish",
    description="Korxona status='active' qilinadi. Faqat superadmin.",
    responses={
        200: {"description": "Korxona faollashtirildi"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Korxona topilmadi"},
    },
)
async def activate_enterprise_endpoint(
    enterprise_id: uuid.UUID,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterpriseOut:
    """Korxonani qayta faollashtiradi."""
    enterprise = await activate_enterprise(db, enterprise_id)
    await db.flush()
    return EnterpriseOut.model_validate(enterprise)
