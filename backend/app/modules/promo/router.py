"""
Promo (Aksiya) moduli router — /promos prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /promos           — paginated ro'yxat (filter, hamma rol view)
  GET    /promos/active    — hozir amal qiladigan aksiyalar (hamma rol)
  POST   /promos           — yangi aksiya (faqat administrator)
  GET    /promos/{id}      — bitta aksiya (hamma rol)
  PATCH  /promos/{id}      — aksiyani yangilash (faqat administrator)
  POST   /promos/{id}/banner — banner yuklash (faqat administrator)
  DELETE /promos/{id}      — soft-delete (faqat administrator)

RBAC (ADR §3.6 §11 Aksiya qatori):
  GET:    barcha rollar (view)
  POST:   faqat administrator (create)
  PATCH:  faqat administrator (edit)
  DELETE: faqat administrator (delete)
  banner: faqat administrator (edit)

SERVER-AVTORITAR: chegirma server tomonda hisoblanadi, klient discount bera olmaydi.
i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.core.storage import StorageBackend, get_storage
from app.models.user import AppUser
from app.modules.promo import service
from app.modules.marketplace.schemas import PromoMarketplaceToggle
from app.modules.promo.schemas import (
    PaginatedPromos,
    PromoCreate,
    PromoOut,
    PromoUpdate,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["promo"])


# ─── Active list (hamma rol — /active endpoint birinchi bo'lishi shart) ───────


@router.get(
    "/active",
    response_model=list[PromoOut],
    summary="Hozir amal qiladigan aksiyalar",
    description=(
        "is_active=True va bugungi sana valid_from..valid_to oralig'ida bo'lgan aksiyalar. "
        "Barcha autentifikatsiyalangan rollar ko'ra oladi. "
        "Sync pull da global — Flutter klientlarga ham uzatiladi."
    ),
)
async def get_active_promos(
    at_date: date | None = Query(None, description="Tekshirish sanasi (default: bugun, YYYY-MM-DD)"),
    current_user: AppUser = require_permission(Module.PROMO, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[PromoOut]:
    enterprise_id = get_current_enterprise_id(current_user)
    promos = await service.list_active_promos(db, at_date=at_date, enterprise_id=enterprise_id)
    return [PromoOut.model_validate(p) for p in promos]


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedPromos,
    summary="Aksiyalar ro'yxati (paginated)",
    description=(
        "Paginated aksiyalar ro'yxati. "
        "Barcha autentifikatsiyalangan rollar ko'ra oladi. "
        "Filtrlar: is_active, target_segment_id, target_product_id, promo_type."
    ),
)
async def list_promos(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    is_active: bool | None = Query(None, description="Aktiv filtri"),
    target_segment_id: uuid.UUID | None = Query(None, description="Segment filtri"),
    target_product_id: uuid.UUID | None = Query(None, description="Mahsulot filtri"),
    promo_type: str | None = Query(None, description="Tur filtri: discount | bonus | gift"),
    current_user: AppUser = require_permission(Module.PROMO, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedPromos:
    enterprise_id = get_current_enterprise_id(current_user)
    items, total = await service.list_promos(
        db,
        is_active=is_active,
        target_segment_id=target_segment_id,
        target_product_id=target_product_id,
        promo_type=promo_type,
        limit=limit,
        offset=offset,
        enterprise_id=enterprise_id,
    )
    return PaginatedPromos(
        items=[PromoOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=PromoOut,
    status_code=201,
    summary="Yangi aksiya yaratish (faqat administrator)",
    description=(
        "Yangi savdo aksiyasi yaratadi. "
        "valid_to >= valid_from bo'lishi shart. "
        "rule_json: {discount_percent} yoki {discount_amount}, ixtiyoriy min_qty."
    ),
    responses={
        403: {"description": "Ruxsat yo'q (faqat administrator)"},
        422: {"description": "Noto'g'ri sanalar yoki rule_json"},
    },
)
async def create_promo(
    body: PromoCreate,
    current_user: AppUser = require_permission(Module.PROMO, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> PromoOut:
    enterprise_id = get_current_enterprise_id(current_user)
    promo = await service.create_promo(
        db, body, actor_id=current_user.id, user=current_user, redis=redis,
        enterprise_id=enterprise_id,
    )
    await db.commit()
    await db.refresh(promo)
    return PromoOut.model_validate(promo)


# ─── Get ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{promo_id}",
    response_model=PromoOut,
    summary="Aksiya ma'lumotlari",
    description="Barcha autentifikatsiyalangan rollar ko'ra oladi.",
    responses={
        404: {"description": "Aksiya topilmadi"},
    },
)
async def get_promo(
    promo_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.PROMO, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PromoOut:
    enterprise_id = get_current_enterprise_id(current_user)
    promo = await service.get_promo(db, promo_id, user=current_user, enterprise_id=enterprise_id)
    return PromoOut.model_validate(promo)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/{promo_id}",
    response_model=PromoOut,
    summary="Aksiyani yangilash (PATCH, faqat administrator)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy.",
    responses={
        403: {"description": "Ruxsat yo'q"},
        404: {"description": "Aksiya topilmadi"},
        409: {"description": "Versiya konflikti"},
        422: {"description": "Noto'g'ri sanalar yoki rule_json"},
    },
)
async def update_promo(
    promo_id: uuid.UUID,
    body: PromoUpdate,
    current_user: AppUser = require_permission(Module.PROMO, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> PromoOut:
    enterprise_id = get_current_enterprise_id(current_user)
    promo = await service.update_promo(
        db, promo_id, body, actor_id=current_user.id, user=current_user,
        enterprise_id=enterprise_id,
    )
    await db.commit()
    await db.refresh(promo)
    return PromoOut.model_validate(promo)


# ─── Banner upload ────────────────────────────────────────────────────────────


@router.post(
    "/{promo_id}/banner",
    response_model=PromoOut,
    summary="Aksiya banneri yuklash (faqat administrator)",
    description=(
        "JPEG, PNG yoki WebP formatdagi banner rasmini yuklaydi. "
        "Magic bytes validatsiya: JPEG/PNG/WebP, max 5MB. "
        "Content-Type ga ishonilmaydi."
    ),
    responses={
        403: {"description": "Ruxsat yo'q"},
        404: {"description": "Aksiya topilmadi"},
        422: {"description": "Noto'g'ri rasm formati yoki hajmi"},
    },
)
async def upload_banner(
    promo_id: uuid.UUID,
    file: UploadFile,
    current_user: AppUser = require_permission(Module.PROMO, Action.EDIT),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> PromoOut:
    enterprise_id = get_current_enterprise_id(current_user)
    # Magic-byte validatsiya storage ichida
    banner_url = await storage.upload_product_photo(file)

    promo = await service.update_banner(
        db, promo_id, banner_url, actor_id=current_user.id, user=current_user,
        enterprise_id=enterprise_id,
    )
    await db.commit()
    await db.refresh(promo)
    return PromoOut.model_validate(promo)


# ─── Delete (soft) ────────────────────────────────────────────────────────────


@router.delete(
    "/{promo_id}",
    status_code=204,
    summary="Aksiyani o'chirish (soft-delete, faqat administrator)",
    description="deleted_at o'rnatiladi — DB da qoladi, ro'yxatda ko'rinmaydi.",
    responses={
        403: {"description": "Ruxsat yo'q"},
        404: {"description": "Aksiya topilmadi"},
    },
)
async def delete_promo(
    promo_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.PROMO, Action.DELETE),
    db: AsyncSession = Depends(get_db),
) -> None:
    enterprise_id = get_current_enterprise_id(current_user)
    await service.delete_promo(
        db, promo_id, actor_id=current_user.id, user=current_user,
        enterprise_id=enterprise_id,
    )
    await db.commit()


# ─── MP5: Marketplace featured toggle ────────────────────────────────────────


@router.patch(
    "/{promo_id}/marketplace-featured",
    response_model=PromoOut,
    summary="Aksiyani marketplace'da featured qilish (administrator)",
    description=(
        "Korxona O'Z aksiyasini marketplace'da 'qaynoq' sifatida ko'rsatadi. "
        "featured=True → GET /marketplace/promos da ko'rinadi (cross-tenant). "
        "featured=False → marketplace'dan olib tashlanadi. "
        "IDOR-safe: faqat O'Z korxonasi aksiyasi (boshqasi → 404)."
    ),
    responses={
        200: {"description": "Aksiya marketplace featured holati yangilandi"},
        403: {"description": "Ruxsat yo'q (faqat administrator)"},
        404: {"description": "Aksiya topilmadi yoki boshqa korxona aksiyasi (IDOR)"},
    },
)
async def toggle_marketplace_featured(
    promo_id: uuid.UUID,
    body: PromoMarketplaceToggle,
    current_user: AppUser = require_permission(Module.PROMO, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> PromoOut:
    """
    Aksiyani marketplace'da featured qilish/olib tashlash.

    XAVFSIZLIK (IDOR-safe):
      - enterprise_id = current_user.enterprise_id — server tomonida.
      - Boshqa korxona aksiyasini featured qilishga urinish → 404.
      - Superadmin uchun: enterprise_id=None → bazaga enterprise_id filtri yo'q
        (superadmin ham faqat O'Z korxonasi aksiyasini emas, ammо bu holat
        superadmin uchun enterprise_id bo'lmasligi tufayli 404 bo'ladi —
        superadmin promo yarata OLMAYDI, enterprise kerak).
    """
    from app.modules.marketplace import service as mp_service

    enterprise_id = get_current_enterprise_id(current_user)
    if enterprise_id is None:
        from app.core.errors import AppError
        raise AppError(
            message_key="promo.not_found",
            status_code=404,
        )

    promo = await mp_service.toggle_promo_featured(
        db,
        promo_id=promo_id,
        enterprise_id=enterprise_id,
        featured=body.featured,
    )
    await db.commit()
    await db.refresh(promo)
    return PromoOut.model_validate(promo)
