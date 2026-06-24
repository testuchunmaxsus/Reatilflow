"""
Superadmin router — /superadmin prefiksi, MT4.

Endpointlar (faqat superadmin roli):
  POST   /superadmin/enterprises                          — korxona + birinchi admin yaratish
  GET    /superadmin/enterprises                          — barcha korxonalar (search/filter, paginated)
  GET    /superadmin/enterprises/{id}                     — bitta korxona (kengaytirilgan)
  PATCH  /superadmin/enterprises/{id}                     — name/enabled_modules/status yangilash
  DELETE /superadmin/enterprises/{id}                     — soft-delete
  PATCH  /superadmin/enterprises/{id}/suspend             — to'xtatib qo'yish
  PATCH  /superadmin/enterprises/{id}/activate            — qayta faollashtirish
  POST   /superadmin/enterprises/{id}/reset-admin-password — admin parolini tiklash
  GET    /superadmin/stats                                — platforma statistikasi
  GET    /superadmin/users                                — cross-tenant foydalanuvchilar

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
    AdminOut,
    EnterpriseAdminListItem,
    EnterpriseAdminOut,
    EnterpriseCreate,
    EnterpriseDetailOut,
    EnterpriseOut,
    EnterprisePaginated,
    EnterpriseUpdate,
    PaginatedSuperadminUsers,
    ResetPasswordIn,
    ResetPasswordOut,
    StatsOut,
    SuperadminUserOut,
)
from app.modules.superadmin.service import (
    activate_enterprise,
    create_enterprise_with_admin,
    delete_enterprise,
    get_enterprise_detail,
    get_platform_stats,
    list_enterprises,
    list_superadmin_users,
    reset_admin_password,
    suspend_enterprise,
    update_enterprise,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["superadmin"])


# ─── GET /superadmin/stats ────────────────────────────────────────────────────


@router.get(
    "/stats",
    response_model=StatsOut,
    status_code=status.HTTP_200_OK,
    summary="Platforma statistikasi",
    description="Cross-tenant platforma statistikasi. Faqat superadmin.",
    responses={
        200: {"description": "Platforma statistikasi"},
        403: {"description": "Faqat superadmin"},
    },
)
async def get_stats(
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> StatsOut:
    """Platforma statistikasini qaytaradi."""
    return await get_platform_stats(db)


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
    description=(
        "Paginated korxonalar ro'yxati. "
        "search — name yoki INN bo'yicha case-insensitive qidiruv. "
        "status — active | suspended filtri. "
        "Faqat superadmin."
    ),
    responses={
        200: {"description": "Korxonalar ro'yxati"},
        403: {"description": "Faqat superadmin"},
    },
)
async def get_enterprises(
    limit: int = Query(20, ge=1, le=100, description="Sahifadagi yozuvlar soni"),
    offset: int = Query(0, ge=0, description="Boshlash joyi"),
    search: str | None = Query(None, description="Name yoki INN bo'yicha qidiruv"),
    status: str | None = Query(None, description="active | suspended filtri"),
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePaginated:
    """Barcha korxonalar ro'yxatini qaytaradi."""
    items, total = await list_enterprises(
        db,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
    )
    return EnterprisePaginated(
        items=[EnterpriseOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /superadmin/enterprises/{id} ────────────────────────────────────────


@router.get(
    "/enterprises/{enterprise_id}",
    response_model=EnterpriseDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Bitta korxona ma'lumotlari (kengaytirilgan)",
    description=(
        "ID bo'yicha korxona ma'lumotlarini qaytaradi. "
        "user_count (barcha foydalanuvchilar soni) va admins (administrator ro'yxati) qo'shilgan. "
        "Faqat superadmin."
    ),
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
) -> EnterpriseDetailOut:
    """ID bo'yicha korxona ma'lumotlarini (kengaytirilgan) qaytaradi."""
    enterprise, user_count, admins = await get_enterprise_detail(db, enterprise_id)
    return EnterpriseDetailOut(
        **EnterpriseOut.model_validate(enterprise).model_dump(),
        user_count=user_count,
        admins=[EnterpriseAdminListItem.model_validate(a) for a in admins],
    )


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


# ─── DELETE /superadmin/enterprises/{id} ─────────────────────────────────────


@router.delete(
    "/enterprises/{enterprise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Korxonani o'chirish (soft-delete)",
    description=(
        "Korxonani soft-delete qiladi: deleted_at=now(), status='suspended'. "
        "Default korxona (00000000-0000-7000-8000-000000000001) o'chirilmaydi. "
        "Faqat superadmin."
    ),
    responses={
        204: {"description": "Korxona o'chirildi"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Korxona topilmadi"},
        422: {"description": "Default korxonani o'chirib bo'lmaydi"},
    },
)
async def delete_enterprise_endpoint(
    enterprise_id: uuid.UUID,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Korxonani soft-delete qiladi."""
    await delete_enterprise(db, enterprise_id)


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


# ─── POST /superadmin/enterprises/{id}/reset-admin-password ──────────────────


@router.post(
    "/enterprises/{enterprise_id}/reset-admin-password",
    response_model=ResetPasswordOut,
    status_code=status.HTTP_200_OK,
    summary="Administrator parolini tiklash",
    description=(
        "Foydalanuvchi parolini tiklaydi. "
        "new_password null bo'lsa — server kuchli parol generatsiya qiladi (12+ belgi). "
        "Foydalanuvchi shu korxonaga tegishli bo'lishi shart. "
        "Parol FAQAT shu javobda bir marta ko'rsatiladi. "
        "Faqat superadmin."
    ),
    responses={
        200: {"description": "Parol tiklandi — yangi parol faqat shu javobda"},
        403: {"description": "Faqat superadmin"},
        404: {"description": "Foydalanuvchi topilmadi yoki boshqa korxona"},
    },
)
async def reset_admin_password_endpoint(
    enterprise_id: uuid.UUID,
    body: ResetPasswordIn,
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordOut:
    """Administrator parolini tiklaydi."""
    user_id, plain_password = await reset_admin_password(
        db=db,
        enterprise_id=enterprise_id,
        user_id=body.user_id,
        new_password=body.new_password,
    )
    return ResetPasswordOut(user_id=user_id, new_password=plain_password)


# ─── GET /superadmin/users ────────────────────────────────────────────────────


@router.get(
    "/users",
    response_model=PaginatedSuperadminUsers,
    status_code=status.HTTP_200_OK,
    summary="Cross-tenant foydalanuvchilar ro'yxati",
    description=(
        "Barcha korxona foydalanuvchilari (superadminlar yo'q). "
        "enterprise_id va role bo'yicha filtr qilish mumkin. "
        "Faqat superadmin."
    ),
    responses={
        200: {"description": "Foydalanuvchilar ro'yxati"},
        403: {"description": "Faqat superadmin"},
    },
)
async def get_all_users(
    enterprise_id: uuid.UUID | None = Query(None, description="Korxona ID bo'yicha filtr"),
    role: str | None = Query(None, description="Rol bo'yicha filtr"),
    limit: int = Query(20, ge=1, le=100, description="Sahifadagi yozuvlar soni"),
    offset: int = Query(0, ge=0, description="Boshlash joyi"),
    current_user: AppUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedSuperadminUsers:
    """Cross-tenant foydalanuvchilar ro'yxatini qaytaradi."""
    items, total = await list_superadmin_users(
        db,
        enterprise_id=enterprise_id,
        role=role,
        limit=limit,
        offset=offset,
    )

    user_items = [
        SuperadminUserOut(
            id=user.id,
            full_name=user.full_name,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
            enterprise_id=user.enterprise_id,
            enterprise_name=ent_name,
            created_at=user.created_at,
        )
        for user, ent_name in items
    ]

    return PaginatedSuperadminUsers(
        items=user_items,
        total=total,
        limit=limit,
        offset=offset,
    )
