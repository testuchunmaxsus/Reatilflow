"""
Katalog moduli router — /catalog prefiksi bilan main.py ga ulanadi.

Endpointlar:
  GET    /catalog/categories                — kategoriyalar ro'yxati
  POST   /catalog/categories                — yangi kategoriya (admin)
  GET    /catalog/price-segments            — narx segmentlar ro'yxati
  POST   /catalog/price-segments            — yangi narx segmenti (admin)

  GET    /catalog/products                  — paginated ro'yxat (filter, search)
  POST   /catalog/products                  — yangi mahsulot (admin)
  GET    /catalog/products/{id}             — mahsulot (view)
  PATCH  /catalog/products/{id}             — yangilash (admin/edit)
  DELETE /catalog/products/{id}             — soft-delete (admin)

  POST   /catalog/products/{id}/prices      — narx o'rnatish (edit)
  GET    /catalog/products/{id}/price-history — narx tarixi (view)

  POST   /catalog/products/{id}/photo       — rasm yuklash (edit)

RBAC: require_permission(Module.CATALOG, Action.*) orqali himoyalangan.
i18n: ?lang= query parametri yoki Accept-Language headeridan til aniqlanadi.
Branch ko'rinish: _apply_branch_visibility() servis funksiyasida qo'llaniladi.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, File
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.i18n import current_locale, localized_name
from app.core.redis import get_redis
from app.core.storage import StorageBackend, get_storage
from app.models.user import AppUser
from app.modules.catalog import service
from app.modules.catalog.schemas import (
    CategoryCreate,
    CategoryOut,
    PaginatedProducts,
    PriceHistoryOut,
    PriceOut,
    PriceSegmentCreate,
    PriceSegmentOut,
    PriceSet,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["catalog"])


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _product_out(product, lang: str | None = None) -> ProductOut:
    """Product ORM → ProductOut (lokalizatsiyalangan name bilan)."""
    locale = lang or current_locale.get()
    out = ProductOut.model_validate(product)
    out.name = localized_name(product, locale)
    return out


def _category_out(cat, lang: str | None = None) -> CategoryOut:
    """Category ORM → CategoryOut (lokalizatsiyalangan name bilan)."""
    locale = lang or current_locale.get()
    out = CategoryOut.model_validate(cat)
    out.name = localized_name(cat, locale)
    return out


# ─── Categories ──────────────────────────────────────────────────────────────


@router.get(
    "/categories",
    response_model=list[CategoryOut],
    summary="Kategoriyalar ro'yxati",
    description="Barcha faol kategoriyalar ro'yxati.",
)
async def list_categories(
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryOut]:
    cats = await service.list_categories(db)
    return [_category_out(c, lang) for c in cats]


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=201,
    summary="Yangi kategoriya yaratish",
    description="Administrator: yangi mahsulot kategoriyasini yaratadi.",
)
async def create_category(
    body: CategoryCreate,
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> CategoryOut:
    cat = await service.create_category(db, body)
    await db.commit()
    await db.refresh(cat)
    return _category_out(cat, lang)


# ─── Price Segments ───────────────────────────────────────────────────────────


@router.get(
    "/price-segments",
    response_model=list[PriceSegmentOut],
    summary="Narx segmentlar ro'yxati",
)
async def list_segments(
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[PriceSegmentOut]:
    segs = await service.list_segments(db)
    return [PriceSegmentOut.model_validate(s) for s in segs]


@router.post(
    "/price-segments",
    response_model=PriceSegmentOut,
    status_code=201,
    summary="Yangi narx segmenti yaratish",
)
async def create_segment(
    body: PriceSegmentCreate,
    current_user: AppUser = require_permission(Module.CATALOG, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> PriceSegmentOut:
    seg = await service.create_segment(db, body)
    await db.commit()
    await db.refresh(seg)
    return PriceSegmentOut.model_validate(seg)


# ─── Products ────────────────────────────────────────────────────────────────


@router.get(
    "/products",
    response_model=PaginatedProducts,
    summary="Mahsulotlar ro'yxati (paginated)",
    description=(
        "Paginated mahsulotlar ro'yxati. "
        "Branch ko'rinish avtomatik qo'llaniladi: "
        "administrator/accountant barcha mahsulotlarni, "
        "boshqa rollar faqat o'z filiali yoki global mahsulotlarni ko'radi."
    ),
)
async def list_products(
    limit: int = Query(20, ge=1, le=200, description="Sahifa hajmi"),
    offset: int = Query(0, ge=0, description="O'tkazib yuborish"),
    category_id: uuid.UUID | None = Query(None, description="Kategoriya filtri"),
    is_active: bool | None = Query(None, description="Faollik filtri"),
    search: str | None = Query(None, max_length=100, description="Qidiruv (nom/sku/barcode)"),
    branch_scope: str | None = Query(None, description="Filial scope filtri"),
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedProducts:
    items, total = await service.list_products(
        db,
        user=current_user,
        limit=limit,
        offset=offset,
        category_id=category_id,
        is_active=is_active,
        search=search,
        branch_scope=branch_scope,
    )
    return PaginatedProducts(
        items=[_product_out(p, lang) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products",
    response_model=ProductOut,
    status_code=201,
    summary="Yangi mahsulot yaratish",
    description="Faqat administrator. SKU va barcode unikal bo'lishi shart.",
    responses={
        409: {"description": "Dublikat SKU yoki barcode"},
    },
)
async def create_product(
    body: ProductCreate,
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ProductOut:
    product = await service.create_product(
        db, body, actor_id=current_user.id, redis=redis
    )
    await db.commit()
    await db.refresh(product)
    return _product_out(product, lang)


@router.get(
    "/products/{product_id}",
    response_model=ProductOut,
    summary="Mahsulot",
    responses={
        404: {"description": "Mahsulot topilmadi (yoki filial doirasidan tashqari)"},
    },
)
async def get_product(
    product_id: uuid.UUID,
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    product = await service.get_product(db, product_id, user=current_user)
    return _product_out(product, lang)


@router.patch(
    "/products/{product_id}",
    response_model=ProductOut,
    summary="Mahsulotni yangilash (PATCH)",
    description="Faqat berilgan maydonlar yangilanadi. version optimistik lock uchun majburiy.",
    responses={
        404: {"description": "Mahsulot topilmadi (yoki filial doirasidan tashqari)"},
        409: {"description": "Versiya konflikti yoki dublikat SKU/barcode"},
    },
)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    product = await service.update_product(
        db, product_id, body, actor_id=current_user.id, user=current_user
    )
    await db.commit()
    await db.refresh(product)
    return _product_out(product, lang)


@router.delete(
    "/products/{product_id}",
    status_code=204,
    summary="Mahsulotni o'chirish (soft-delete)",
    description="deleted_at o'rnatiladi — DB da qoladi, ro'yxatda ko'rinmaydi.",
    responses={
        404: {"description": "Mahsulot topilmadi (yoki filial doirasidan tashqari)"},
    },
)
async def delete_product(
    product_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CATALOG, Action.DELETE),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_product(
        db, product_id, actor_id=current_user.id, user=current_user
    )
    await db.commit()


# ─── Prices ──────────────────────────────────────────────────────────────────


@router.post(
    "/products/{product_id}/prices",
    response_model=PriceOut,
    status_code=201,
    summary="Narx o'rnatish",
    description=(
        "Mahsulot uchun yangi narx o'rnatadi. "
        "Avvalgi narx price_history ga APPEND qilinadi (hech qachon o'chirmaydi). "
        "SELECT FOR UPDATE orqali race condition oldini oladi."
    ),
    responses={
        404: {"description": "Mahsulot yoki segment topilmadi"},
    },
)
async def set_price(
    product_id: uuid.UUID,
    body: PriceSet,
    current_user: AppUser = require_permission(Module.CATALOG, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> PriceOut:
    price = await service.set_price(
        db, product_id, body, actor_id=current_user.id, user=current_user
    )
    await db.commit()
    await db.refresh(price)
    return PriceOut.model_validate(price)


@router.get(
    "/products/{product_id}/price-history",
    response_model=list[PriceHistoryOut],
    summary="Narx tarixi",
    description="Mahsulot narx tarixi (yangirog'i birinchi). APPEND-ONLY — o'chirilmaydi.",
    responses={
        404: {"description": "Mahsulot topilmadi"},
    },
)
async def get_price_history(
    product_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.CATALOG, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[PriceHistoryOut]:
    history = await service.get_price_history(db, product_id, user=current_user)
    return [PriceHistoryOut.model_validate(h) for h in history]


# ─── Photo upload ─────────────────────────────────────────────────────────────


@router.post(
    "/products/{product_id}/photo",
    response_model=ProductOut,
    summary="Mahsulot rasmini yuklash",
    description=(
        "Faqat JPEG/PNG/WebP rasmlari (magic bytes tekshiriladi) va 5 MB gacha. "
        "photo_url yangilanadi. "
        "Test muhitida FakeStorage ishlatiladi."
    ),
    responses={
        404: {"description": "Mahsulot topilmadi"},
        422: {"description": "Noto'g'ri fayl: magic bytes yoki hajm"},
    },
)
async def upload_photo(
    product_id: uuid.UUID,
    file: UploadFile = File(..., description="Rasm fayli (JPEG/PNG/WebP, max 5MB)"),
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.CATALOG, Action.EDIT),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> ProductOut:
    photo_url = await storage.upload_product_photo(file)
    product = await service.update_photo_url(
        db, product_id, photo_url, actor_id=current_user.id, user=current_user
    )
    await db.commit()
    await db.refresh(product)
    return _product_out(product, lang)
