"""
Marketplace moduli router — /marketplace prefiksi bilan main.py ga ulanadi.

Endpointlar (MP1):
  GET /marketplace/products                — barcha korxonalar published mahsulotlari
                                             (cross-tenant browse, marketplace_published=True)
  GET /marketplace/products/{id}           — bitta published marketplace mahsuloti
  GET /marketplace/suppliers               — marketplace'da mahsuloti bor korxonalar

Endpointlar (MP2 — Buyurtma):
  POST   /marketplace/orders               — buyurtma yaratish (do'kon/admin → supplier)
  GET    /marketplace/orders/outgoing      — chiquvchi buyurtmalar (buyer korxona)
  GET    /marketplace/orders/incoming      — kiruvchi buyurtmalar (supplier korxona)
  GET    /marketplace/orders/{id}          — bitta buyurtma
  PATCH  /marketplace/orders/{id}/confirm  — tasdiqlash (FAQAT supplier)
  PATCH  /marketplace/orders/{id}/reject   — rad etish (FAQAT supplier)

XAVFSIZLIK (MP1):
  - marketplace_published=True QATTIQ SHART — hech qachon published emas
    mahsulot cross-tenant oqmaydi.
  - enterprise_id filtri bu endpointlarda QILINMAYDI (atayin cross-tenant).
  - RBAC: marketplace:view ruxsati — store/admin/accountant/agent/courier ko'radi.
  - Module gating: "marketplace" moduli yoqilgan bo'lishi shart.

XAVFSIZLIK (MP2):
  - Buyurtma faqat buyer YOKI supplier korxonasiga ko'rinadi.
  - Uchinchi korxona → 404 (mavjudlikni oshkor qilmaslik).
  - confirm/reject: FAQAT supplier korxona (admin/accountant).
  - Server-avtoritar narx: klient narx bera olmaydi.

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
    MarketplaceOrderCreateIn,
    MarketplaceOrderOut,
    MarketplaceOrderRejectIn,
    MarketplaceProductOut,
    MarketplaceSupplierOut,
    PaginatedMarketplace,
    PaginatedMarketplaceOrders,
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


# ─── MP2: Buyurtma endpointlari ───────────────────────────────────────────────


def _build_order_out(order) -> MarketplaceOrderOut:
    """MarketplaceOrder ORM → MarketplaceOrderOut Pydantic sxemasi."""
    lines_out = []
    for line in (order.lines or []):
        from app.modules.marketplace.schemas import MarketplaceOrderLineOut
        lines_out.append(
            MarketplaceOrderLineOut(
                id=line.id,
                product_id=line.product_id,
                qty=line.qty,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        )
    return MarketplaceOrderOut(
        id=order.id,
        buyer_enterprise_id=order.buyer_enterprise_id,
        buyer_store_id=order.buyer_store_id,
        buyer_user_id=order.buyer_user_id,
        supplier_enterprise_id=order.supplier_enterprise_id,
        status=order.status,
        total_amount=order.total_amount,
        reject_reason=order.reject_reason,
        client_uuid=order.client_uuid,
        lines=lines_out,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.post(
    "/orders",
    response_model=MarketplaceOrderOut,
    status_code=201,
    summary="Marketplace buyurtma yaratish",
    description=(
        "Do'kon yoki admin supplier korxona published mahsulotlaridan buyurtma beradi. "
        "Narx SERVER TOMONIDA aniqlanadi (marketplace_price yoki segment). "
        "Bitta so'rovda faqat bitta supplier korxona mahsulotlari qabul qilinadi."
    ),
    responses={
        201: {"description": "Buyurtma muvaffaqiyatli yaratildi"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Mahsulot published emas yoki topilmadi"},
        422: {"description": "Aralash supplier, narx topilmadi yoki bo'sh lines"},
    },
)
async def create_order(
    body: MarketplaceOrderCreateIn,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.CREATE),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Marketplace buyurtma yaratadi.

    XAVFSIZLIK:
      - marketplace_published=True bo'lmagan mahsulot → 404.
      - Narx server tomonida aniqlanadi (klient narx bera olmaydi).
      - Bitta so'rovda faqat bitta supplier korxona mahsulotlari.
      - Idempotentlik: client_uuid bilan qayta yuborishda dublikat yaratilmaydi.
    """
    lines = [
        service.OrderLineInput(
            product_id=line.product_id,
            qty=line.qty,
        )
        for line in body.lines
    ]
    order = await service.create_order(
        db,
        buyer_user=current_user,
        lines=lines,
        client_uuid=body.client_uuid,
    )
    # selectin lines ni eager yuklash uchun refresh
    await db.refresh(order, ["lines"])
    await db.commit()
    return _build_order_out(order)


@router.get(
    "/orders/outgoing",
    response_model=PaginatedMarketplaceOrders,
    summary="Chiquvchi buyurtmalar (buyer korxona)",
    description=(
        "Joriy foydalanuvchi korxonasi jo'natgan buyurtmalar ro'yxati. "
        "Faqat buyer_enterprise_id == current_user.enterprise_id bo'lgan buyurtmalar."
    ),
    responses={
        200: {"description": "Chiquvchi buyurtmalar ro'yxati (paginated)"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_outgoing_orders(
    status: str | None = Query(None, description="Holat filtri: pending|confirmed|rejected|..."),
    page: int = Query(1, ge=1, description="Sahifa raqami"),
    limit: int = Query(20, ge=1, le=100, description="Sahifa hajmi"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedMarketplaceOrders:
    """Joriy korxona chiquvchi buyurtmalari."""
    if current_user.enterprise_id is None:
        return PaginatedMarketplaceOrders(items=[], total=0, limit=limit, offset=0)

    orders, total = await service.list_outgoing(
        db,
        buyer_enterprise_id=current_user.enterprise_id,
        status=status,
        page=page,
        limit=limit,
    )
    return PaginatedMarketplaceOrders(
        items=[_build_order_out(o) for o in orders],
        total=total,
        limit=limit,
        offset=(page - 1) * limit,
    )


@router.get(
    "/orders/incoming",
    response_model=PaginatedMarketplaceOrders,
    summary="Kiruvchi buyurtmalar (supplier korxona)",
    description=(
        "Joriy foydalanuvchi korxonasiga kelgan buyurtmalar ro'yxati. "
        "Faqat supplier_enterprise_id == current_user.enterprise_id bo'lgan buyurtmalar. "
        "Tasdiqlash/rad etish uchun admin yoki accountant."
    ),
    responses={
        200: {"description": "Kiruvchi buyurtmalar ro'yxati (paginated)"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_incoming_orders(
    status: str | None = Query(None, description="Holat filtri: pending|confirmed|rejected|..."),
    page: int = Query(1, ge=1, description="Sahifa raqami"),
    limit: int = Query(20, ge=1, le=100, description="Sahifa hajmi"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedMarketplaceOrders:
    """Joriy korxona kiruvchi buyurtmalari (supplier sifatida)."""
    if current_user.enterprise_id is None:
        return PaginatedMarketplaceOrders(items=[], total=0, limit=limit, offset=0)

    orders, total = await service.list_incoming(
        db,
        supplier_enterprise_id=current_user.enterprise_id,
        status=status,
        page=page,
        limit=limit,
    )
    return PaginatedMarketplaceOrders(
        items=[_build_order_out(o) for o in orders],
        total=total,
        limit=limit,
        offset=(page - 1) * limit,
    )


@router.get(
    "/orders/{order_id}",
    response_model=MarketplaceOrderOut,
    summary="Bitta marketplace buyurtma",
    description=(
        "Bitta marketplace buyurtmasini qaytaradi. "
        "Faqat buyer YOKI supplier korxona foydalanuvchisi ko'radi. "
        "Uchinchi korxona → 404."
    ),
    responses={
        200: {"description": "Marketplace buyurtma"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi yoki kirish taqiqlangan"},
    },
)
async def get_order(
    order_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Bitta marketplace buyurtmasi.

    XAVFSIZLIK: faqat buyer YOKI supplier korxona ko'radi (3-tomon izolyatsiya).
    """
    order = await service.get_order(db, order_id, current_user)
    return _build_order_out(order)


@router.patch(
    "/orders/{order_id}/confirm",
    response_model=MarketplaceOrderOut,
    summary="Buyurtmani tasdiqlash (FAQAT supplier)",
    description=(
        "Supplier korxona admini/accountant'i pending buyurtmani tasdiqlaydi. "
        "Faqat supplier_enterprise_id == current_user.enterprise_id bo'lsa ishlaydi. "
        "Buyer korxona foydalanuvchisi confirm qila OLMAYDI → 403."
    ),
    responses={
        200: {"description": "Buyurtma tasdiqlandi (confirmed)"},
        403: {"description": "Foydalanuvchi supplier emas yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi"},
        422: {"description": "Noto'g'ri holat o'tishi (pending emas)"},
    },
)
async def confirm_order(
    order_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Buyurtmani tasdiqlash — FAQAT supplier korxona.

    XAVFSIZLIK:
      - supplier_enterprise_id == current_user.enterprise_id tekshiriladi.
      - buyer korxona admini confirm qilishga urinsa → 403.
    """
    order = await service.confirm_order(db, order_id, current_user)
    await db.commit()
    return _build_order_out(order)


@router.patch(
    "/orders/{order_id}/reject",
    response_model=MarketplaceOrderOut,
    summary="Buyurtmani rad etish (FAQAT supplier)",
    description=(
        "Supplier korxona admini/accountant'i pending buyurtmani rad etadi. "
        "reason: rad etish sababi (ixtiyoriy). "
        "Faqat supplier_enterprise_id == current_user.enterprise_id bo'lsa ishlaydi."
    ),
    responses={
        200: {"description": "Buyurtma rad etildi (rejected)"},
        403: {"description": "Foydalanuvchi supplier emas yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi"},
        422: {"description": "Noto'g'ri holat o'tishi (pending emas)"},
    },
)
async def reject_order(
    order_id: uuid.UUID,
    body: MarketplaceOrderRejectIn | None = None,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Buyurtmani rad etish — FAQAT supplier korxona.

    XAVFSIZLIK:
      - supplier_enterprise_id == current_user.enterprise_id tekshiriladi.
      - buyer korxona admini reject qilishga urinsa → 403.
    """
    reason = body.reason if body else None
    order = await service.reject_order(db, order_id, current_user, reason)
    await db.commit()
    return _build_order_out(order)
