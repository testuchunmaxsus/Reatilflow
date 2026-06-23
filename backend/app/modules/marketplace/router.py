"""
Marketplace moduli router — /marketplace prefiksi bilan main.py ga ulanadi.

Endpointlar (MP1):
  GET /marketplace/products                — barcha korxonalar published mahsulotlari
                                             (cross-tenant browse, marketplace_published=True)
  GET /marketplace/products/{id}           — bitta published marketplace mahsuloti
  GET /marketplace/suppliers               — marketplace'da mahsuloti bor korxonalar

XAVFSIZLIK:
  - marketplace_published=True QATTIQ SHART — hech qachon published emas
    mahsulot cross-tenant oqmaydi.
  - enterprise_id filtri bu endpointlarda QILINMAYDI (atayin cross-tenant).
  - RBAC: marketplace:view ruxsati — store/admin/accountant/agent/courier ko'radi.
  - Module gating: "marketplace" moduli yoqilgan bo'lishi shart.

Publish toggle endpoint:
  PATCH /catalog/products/{id}/marketplace — catalog router'da (catalog modul gate).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.i18n import current_locale, localized_name
from app.models.user import AppUser
from app.modules.marketplace import service
from app.modules.marketplace.schemas import (
    MarketplaceProductOut,
    MarketplaceSupplierOut,
    PaginatedMarketplace,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

router = APIRouter(tags=["marketplace"])


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _build_product_out(
    product,
    enterprise,
    effective_price,
    lang: str | None = None,
) -> MarketplaceProductOut:
    """Product + Enterprise → MarketplaceProductOut (lokalizatsiyalangan)."""
    locale = lang or current_locale.get()
    out = MarketplaceProductOut(
        id=product.id,
        name_uz=product.name_uz,
        name_ru=product.name_ru,
        name=localized_name(product, locale),
        sku=product.sku,
        barcode=product.barcode,
        unit=product.unit,
        category_id=product.category_id,
        photo_url=product.photo_url,
        is_active=product.is_active,
        marketplace_published=product.marketplace_published,
        marketplace_price=product.marketplace_price,
        price=effective_price,
        supplier_enterprise_id=enterprise.id,
        supplier_name=enterprise.name,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
    return out


# ─── Browse ──────────────────────────────────────────────────────────────────


@router.get(
    "/products",
    response_model=PaginatedMarketplace,
    summary="Marketplace mahsulotlar ro'yxati (cross-tenant browse)",
    description=(
        "Barcha korxonalar published mahsulotlarini qaytaradi. "
        "Bu endpoint ATAYIN cross-tenant — korxona filtri qo'llanmaydi. "
        "LEKIN faqat marketplace_published=True mahsulotlar ko'rinadi. "
        "Har natijada supplier korxona nomi va ID qaytadi."
    ),
    responses={
        200: {"description": "Published mahsulotlar ro'yxati (paginated)"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def browse_marketplace(
    search: str | None = Query(None, max_length=100, description="Qidiruv (nom/sku/barcode)"),
    category: uuid.UUID | None = Query(None, description="Kategoriya filtri"),
    supplier_enterprise: uuid.UUID | None = Query(None, description="Supplier korxona UUID filtri"),
    page: int = Query(1, ge=1, description="Sahifa raqami (1-bazali)"),
    limit: int = Query(20, ge=1, le=100, description="Sahifa hajmi"),
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedMarketplace:
    """
    Marketplace browse — barcha korxonalar published mahsulotlari.

    enterprise_id filtri QO'LLANMAYDI — bu cross-tenant endpoint.
    marketplace_published=True MAJBURIY — izolyatsiya kafolati.
    """
    items, total = await service.browse_products(
        db,
        search=search,
        category_id=category,
        supplier_enterprise=supplier_enterprise,
        page=page,
        limit=limit,
    )
    return PaginatedMarketplace(
        items=[_build_product_out(p, e, price, lang) for p, e, price in items],
        total=total,
        limit=limit,
        offset=(page - 1) * limit,
    )


@router.get(
    "/products/{product_id}",
    response_model=MarketplaceProductOut,
    summary="Marketplace mahsulot (bitta)",
    description=(
        "Bitta published marketplace mahsulotini qaytaradi. "
        "published bo'lmasa → 404 (boshqa korxona ichki mahsuloti oshkor qilinmaydi)."
    ),
    responses={
        200: {"description": "Published marketplace mahsuloti"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Mahsulot topilmadi yoki published emas"},
    },
)
async def get_marketplace_product(
    product_id: uuid.UUID,
    lang: str | None = Query(None, description="Til: uz | ru"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceProductOut:
    """
    Bitta published marketplace mahsuloti.

    XAVFSIZLIK: marketplace_published=False bo'lsa yoki boshqa korxona
    ichki mahsuloti bo'lsa — 404 qaytadi (mavjudlikni oshkor qilmaslik).
    """
    product, enterprise, price = await service.get_published_product(db, product_id)
    return _build_product_out(product, enterprise, price, lang)


# ─── Suppliers ───────────────────────────────────────────────────────────────


@router.get(
    "/suppliers",
    response_model=list[MarketplaceSupplierOut],
    summary="Marketplace supplierlar ro'yxati",
    description=(
        "Marketplace'da published mahsuloti bor korxonalar ro'yxatini qaytaradi. "
        "Har korxona uchun: enterprise_id, name, product_count."
    ),
    responses={
        200: {"description": "Supplierlar ro'yxati"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_suppliers(
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[MarketplaceSupplierOut]:
    """Marketplace'da mahsuloti bor korxonalar."""
    suppliers = await service.list_suppliers(db)
    return [
        MarketplaceSupplierOut(
            enterprise_id=s["enterprise_id"],
            name=s["name"],
            product_count=s["product_count"],
        )
        for s in suppliers
    ]
