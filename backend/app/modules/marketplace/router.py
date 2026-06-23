"""
Marketplace moduli router — /marketplace prefiksi bilan main.py ga ulanadi.

Endpointlar (MP1):
  GET /marketplace/products                — barcha korxonalar published mahsulotlari
  GET /marketplace/products/{id}           — bitta published marketplace mahsuloti
  GET /marketplace/suppliers               — marketplace'da mahsuloti bor korxonalar

Endpointlar (MP2 — Buyurtma):
  POST   /marketplace/orders               — buyurtma yaratish
  GET    /marketplace/orders/outgoing      — chiquvchi buyurtmalar (buyer korxona)
  GET    /marketplace/orders/incoming      — kiruvchi buyurtmalar (supplier korxona)
  GET    /marketplace/orders/{id}          — bitta buyurtma
  PATCH  /marketplace/orders/{id}/confirm  — tasdiqlash (FAQAT supplier)
  PATCH  /marketplace/orders/{id}/reject   — rad etish (FAQAT supplier)

Endpointlar (MP3 — Yetkazish):
  PATCH  /marketplace/orders/{id}/ship     — jo'natish (supplier admin, kuryer tayinlash)
  PATCH  /marketplace/orders/{id}/deliver  — yetkazildi (tayinlangan kuryer + proof_photo)
  PATCH  /marketplace/orders/{id}/accept   — qabul (buyer do'kon/admin, inventar yaratiladi)
  GET    /marketplace/inventory            — do'kon inventari (buyer korxona, tenant-scoped)

Endpointlar (MP5 — Banner + Qaynoq aksiyalar):
  GET    /marketplace/banners              — aktiv bannerlar (cross-tenant browse, limit=5)
  POST   /marketplace/banners             — banner yaratish (korxona admin)
  PATCH  /marketplace/banners/{id}        — banner tahrirlash (o'z korxona yoki superadmin)
  DELETE /marketplace/banners/{id}        — banner o'chirish (o'z korxona yoki superadmin)
  POST   /marketplace/banners/{id}/image  — banner rasm yuklash (MinIO)
  GET    /marketplace/promos              — qaynoq aksiyalar (cross-tenant, featured)

XAVFSIZLIK (MP3):
  - ship: FAQAT supplier korxona (admin/accountant) — marketplace:edit.
  - deliver: FAQAT tayinlangan kuryer — marketplace:edit (courier roli).
  - accept: FAQAT buyer korxona (admin/store) — marketplace:edit.
  - inventory: buyer korxona foydalanuvchisi — marketplace:view.
  - 3-korxona → 404.

XAVFSIZLIK (MP5):
  - banner browse: barcha (marketplace:view) — cross-tenant, faqat aktiv+valid.
  - banner CRUD: administrator (marketplace:edit) — faqat O'Z korxonasi.
  - superadmin: har qanday bannerni moderatsiya qiladi.
  - promo featured: administrator (marketplace:edit + promo module) — IDOR-safe.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.i18n import current_locale, localized_name
from app.core.storage import StorageBackend, get_storage
from app.models.user import AppUser
from app.modules.marketplace import service
from app.modules.marketplace.schemas import (
    AdBannerCreate,
    AdBannerOut,
    AdBannerPatch,
    MarketplaceAcceptIn,
    MarketplaceDeliverIn,
    MarketplaceOrderCreateIn,
    MarketplaceOrderOut,
    MarketplaceOrderRejectIn,
    MarketplaceProductOut,
    MarketplacePromoOut,
    MarketplaceShipIn,
    MarketplaceSupplierOut,
    PaginatedMarketplace,
    PaginatedMarketplaceOrders,
    PaginatedStoreInventory,
    StoreInventoryOut,
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
    """MarketplaceOrder ORM → MarketplaceOrderOut Pydantic sxemasi (MP2 + MP3)."""
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
        # MP3 maydonlari
        courier_id=getattr(order, "courier_id", None),
        delivered_at=getattr(order, "delivered_at", None),
        proof_photo_url=getattr(order, "proof_photo_url", None),
        accepted_at=getattr(order, "accepted_at", None),
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


# ─── MP3: Yetkazish endpointlari ─────────────────────────────────────────────


@router.patch(
    "/orders/{order_id}/ship",
    response_model=MarketplaceOrderOut,
    summary="Buyurtmani jo'natish (FAQAT supplier)",
    description=(
        "Supplier korxona admini/accountant'i confirmed buyurtmani jo'natadi. "
        "courier_id: shu supplier korxona kuryeri tayinlanadi. "
        "Status: confirmed → delivering."
    ),
    responses={
        200: {"description": "Buyurtma jo'natildi (delivering)"},
        403: {"description": "Foydalanuvchi supplier emas yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi"},
        422: {"description": "Noto'g'ri holat o'tishi yoki kuryer topilmadi"},
    },
)
async def ship_order(
    order_id: uuid.UUID,
    body: MarketplaceShipIn,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Buyurtmani jo'natish — FAQAT supplier korxona.

    XAVFSIZLIK:
      - supplier_enterprise_id == current_user.enterprise_id tekshiriladi.
      - Kuryer ham supplier korxonasiga tegishli bo'lishi shart.
    """
    order = await service.ship_order(
        db,
        order_id=order_id,
        supplier_user=current_user,
        courier_id=body.courier_id,
    )
    await db.commit()
    return _build_order_out(order)


@router.patch(
    "/orders/{order_id}/deliver",
    response_model=MarketplaceOrderOut,
    summary="Buyurtma yetkazildi (FAQAT tayinlangan kuryer)",
    description=(
        "Tayinlangan kuryer buyurtmani yetkazib berganini tasdiqlaydi. "
        "proof_photo_url: do'kon oldidagi fotosurat URL (ixtiyoriy). "
        "Status: delivering → delivered."
    ),
    responses={
        200: {"description": "Buyurtma yetkazildi (delivered)"},
        403: {"description": "Kuryer tayinlanmagan yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi"},
        422: {"description": "Noto'g'ri holat o'tishi"},
    },
)
async def deliver_order(
    order_id: uuid.UUID,
    body: MarketplaceDeliverIn | None = None,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Buyurtma yetkazildi — FAQAT tayinlangan kuryer.

    XAVFSIZLIK:
      - order.courier_id == current_user.id tekshiriladi.
      - Boshqa kuryer → 403.
    """
    proof_url = body.proof_photo_url if body else None
    order = await service.deliver_order(
        db,
        order_id=order_id,
        courier_user=current_user,
        proof_photo_url=proof_url,
    )
    await db.commit()
    return _build_order_out(order)


@router.patch(
    "/orders/{order_id}/accept",
    response_model=MarketplaceOrderOut,
    summary="Buyurtmani qabul qilish (FAQAT buyer do'kon/admin)",
    description=(
        "Buyer do'kon/admin delivered buyurtmani qabul qiladi. "
        "Har buyurtma qatori uchun expiry_date va markup_percent beriladi. "
        "Atomik: qabul = StoreInventory yozuvlari yaratiladi. "
        "Status: delivered → accepted. sale_price = cost * (1 + markup/100)."
    ),
    responses={
        200: {"description": "Buyurtma qabul qilindi (accepted), inventar yaratildi"},
        403: {"description": "Foydalanuvchi buyer emas yoki ruxsat yo'q"},
        404: {"description": "Buyurtma topilmadi"},
        422: {"description": "Noto'g'ri holat o'tishi yoki do'kon topilmadi"},
    },
)
async def accept_order(
    order_id: uuid.UUID,
    body: MarketplaceAcceptIn | None = None,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceOrderOut:
    """
    Buyurtmani qabul qilish — FAQAT buyer korxona.

    XAVFSIZLIK:
      - buyer_enterprise_id == current_user.enterprise_id tekshiriladi.
      - supplier korxona accept qilishga urinsa → 403.

    Atomik: har line → StoreInventory yozuvi.
    sale_price server tomonida: cost_price * (1 + markup_percent/100).
    """
    from app.modules.marketplace.service import AcceptLineInfo
    from decimal import Decimal

    lines_info: list[AcceptLineInfo] = []
    store_id = None

    if body:
        store_id = body.store_id
        for li in body.lines:
            lines_info.append(AcceptLineInfo(
                line_id=li.line_id,
                expiry_date=li.expiry_date,
                markup_percent=li.markup_percent,
            ))

    order = await service.accept_order(
        db,
        order_id=order_id,
        buyer_user=current_user,
        lines_info=lines_info,
        store_id=store_id,
    )
    await db.commit()
    return _build_order_out(order)


# ─── MP3: Do'kon inventari endpointi ─────────────────────────────────────────


def _build_inventory_out(inv) -> StoreInventoryOut:
    """
    StoreInventory ORM → StoreInventoryOut Pydantic sxemasi.

    MP4: is_expired, is_near_expiry, days_to_expiry bayroqlari hisoblanadi.
    """
    from app.core.config import settings
    from app.modules.pos.expiry import is_expired, is_near_expiry, days_to_expiry

    _expired = is_expired(inv)
    _near = is_near_expiry(inv, days=settings.pos_expiry_block_days)
    _days = days_to_expiry(inv)

    return StoreInventoryOut(
        id=inv.id,
        enterprise_id=inv.enterprise_id,
        store_id=inv.store_id,
        product_id=inv.product_id,
        qty=inv.qty,
        cost_price=inv.cost_price,
        markup_percent=inv.markup_percent,
        sale_price=inv.sale_price,
        expiry_date=inv.expiry_date,
        status=inv.status,
        source_order_id=inv.source_order_id,
        created_at=inv.created_at,
        is_expired=_expired,
        is_near_expiry=_near,
        days_to_expiry=_days,
    )


@router.get(
    "/inventory",
    response_model=PaginatedStoreInventory,
    summary="Do'kon inventari (buyer korxona, tenant-scoped)",
    description=(
        "Marketplace orqali qabul qilingan mahsulotlar inventarini ko'radi. "
        "Faqat joriy korxona inventari (enterprise_id filtr). "
        "store_id bo'yicha filtr: bitta do'kon inventari."
    ),
    responses={
        200: {"description": "Inventar ro'yxati (paginated)"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_inventory(
    store_id: uuid.UUID | None = Query(None, description="Do'kon UUID filtri"),
    product_id: uuid.UUID | None = Query(None, description="Mahsulot UUID filtri"),
    status: str | None = Query(None, description="Holat filtri: active | expired"),
    page: int = Query(1, ge=1, description="Sahifa raqami (1-bazali)"),
    limit: int = Query(50, ge=1, le=200, description="Sahifa hajmi"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedStoreInventory:
    """
    Buyer korxona do'kon inventarini qaytaradi (tenant-scoped).

    XAVFSIZLIK: enterprise_id = current_user.enterprise_id — boshqa korxona
    inventarini ko'ra olmaydi.
    """
    if current_user.enterprise_id is None:
        return PaginatedStoreInventory(items=[], total=0, limit=limit, offset=0)

    items, total = await service.list_store_inventory(
        db,
        enterprise_id=current_user.enterprise_id,
        store_id=store_id,
        product_id=product_id,
        status=status,
        page=page,
        limit=limit,
    )
    return PaginatedStoreInventory(
        items=[_build_inventory_out(inv) for inv in items],
        total=total,
        limit=limit,
        offset=(page - 1) * limit,
    )


# ─── MP5: Reklama banner endpointlari ────────────────────────────────────────


def _build_banner_out(banner) -> AdBannerOut:
    """AdBanner ORM → AdBannerOut Pydantic sxemasi."""
    return AdBannerOut(
        id=banner.id,
        enterprise_id=banner.enterprise_id,
        title=banner.title,
        image_url=banner.image_url,
        target_url=banner.target_url,
        target_product_id=banner.target_product_id,
        is_active=banner.is_active,
        priority=banner.priority,
        valid_from=banner.valid_from,
        valid_to=banner.valid_to,
        created_at=banner.created_at,
        updated_at=banner.updated_at,
    )


@router.get(
    "/banners",
    response_model=list[AdBannerOut],
    summary="Marketplace aktiv bannerlari (cross-tenant browse)",
    description=(
        "Barcha korxonalarning aktiv bannerlarini qaytaradi. "
        "Bu endpoint ATAYIN cross-tenant — korxona filtri qo'llanmaydi. "
        "Halaqit bermaslik: faqat aktiv + valid sana + limit (default 5). "
        "priority kamayish tartibida (yuqori birinchi). "
        "Muddati o'tgan yoki o'chiq bannerlar ko'rinmaydi."
    ),
    responses={
        200: {"description": "Aktiv bannerlar ro'yxati"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_banners(
    limit: int = Query(5, ge=1, le=20, description="Maksimal bannerlar soni (halaqit bermaslik uchun, max 20)"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[AdBannerOut]:
    """
    Marketplace aktiv bannerlari — cross-tenant browse.

    XAVFSIZLIK: faqat is_active=True + valid_from<=bugun<=valid_to bannerlar.
    Nofaol yoki muddati o'tgan bannerlar HECH QACHON ko'rinmaydi.
    """
    banners = await service.list_active_banners(db, limit=limit)
    return [_build_banner_out(b) for b in banners]


@router.post(
    "/banners",
    response_model=AdBannerOut,
    status_code=201,
    summary="Banner yaratish (korxona admini)",
    description=(
        "Korxona O'Z reklamasini yaratadi. "
        "enterprise_id SERVER TOMONIDA o'rnatiladi (klient bera olmaydi). "
        "Rasm keyinchalik POST /marketplace/banners/{id}/image orqali yuklanadi."
    ),
    responses={
        201: {"description": "Banner muvaffaqiyatli yaratildi"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        422: {"description": "Noto'g'ri sanalar (valid_to < valid_from)"},
    },
)
async def create_banner(
    body: AdBannerCreate,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> AdBannerOut:
    """
    Banner yaratish — FAQAT administrator.

    XAVFSIZLIK:
      - enterprise_id = current_user.enterprise_id (server avtoritar).
      - Superadmin (enterprise_id=None) banner yarata OLMAYDI (korxona kerak).
    """
    if current_user.enterprise_id is None:
        from app.core.errors import AppError
        raise AppError(
            message_key="marketplace.banner_no_enterprise",
            status_code=422,
        )
    banner = await service.create_banner(db, body, current_user.enterprise_id)
    await db.commit()
    return _build_banner_out(banner)


@router.patch(
    "/banners/{banner_id}",
    response_model=AdBannerOut,
    summary="Banner tahrirlash (o'z korxona yoki superadmin)",
    description=(
        "Bannerni qisman yangilaydi. "
        "Korxona faqat O'Z bannerini tahrirlaydi (IDOR-safe). "
        "Superadmin har qanday bannerni tahrirlaydi (moderatsiya: is_active toggle)."
    ),
    responses={
        200: {"description": "Banner yangilandi"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Banner topilmadi yoki boshqa korxona banneri (IDOR)"},
        422: {"description": "Noto'g'ri sanalar"},
    },
)
async def patch_banner(
    banner_id: uuid.UUID,
    body: AdBannerPatch,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> AdBannerOut:
    """
    Banner tahrirlash — korxona O'Z banneri yoki superadmin.

    XAVFSIZLIK:
      - enterprise_id bilan: faqat O'Z korxonasi banneri (IDOR himoyasi).
      - Superadmin (enterprise_id=None): har qanday bannerni tahrirlaydi.
    """
    is_superadmin = current_user.enterprise_id is None
    banner = await service.patch_banner(
        db,
        banner_id=banner_id,
        data=body,
        enterprise_id=current_user.enterprise_id,
        is_superadmin=is_superadmin,
    )
    await db.commit()
    return _build_banner_out(banner)


@router.delete(
    "/banners/{banner_id}",
    status_code=204,
    summary="Banner o'chirish (o'z korxona yoki superadmin)",
    description=(
        "Bannerni o'chiradi (qattiq o'chirish). "
        "Korxona faqat O'Z bannerini o'chiradi. "
        "Superadmin har qanday bannerni o'chiradi."
    ),
    responses={
        204: {"description": "Banner o'chirildi"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Banner topilmadi yoki boshqa korxona banneri (IDOR)"},
    },
)
async def delete_banner(
    banner_id: uuid.UUID,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Banner o'chirish — korxona O'Z banneri yoki superadmin.

    XAVFSIZLIK: enterprise_id bilan IDOR himoyasi.
    """
    is_superadmin = current_user.enterprise_id is None
    await service.delete_banner(
        db,
        banner_id=banner_id,
        enterprise_id=current_user.enterprise_id,
        is_superadmin=is_superadmin,
    )
    await db.commit()


@router.post(
    "/banners/{banner_id}/image",
    response_model=AdBannerOut,
    summary="Banner rasmi yuklash (MinIO)",
    description=(
        "Banner rasmi yuklash (JPEG/PNG/WebP, max 5MB). "
        "Magic bytes validatsiya: faqat rasm formatlari. "
        "Korxona faqat O'Z banneriga rasm yuklaydi. "
        "Superadmin har qanday bannerga rasm yuklay oladi."
    ),
    responses={
        200: {"description": "Rasm yuklandi, banner yangilandi"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
        404: {"description": "Banner topilmadi yoki boshqa korxona banneri (IDOR)"},
        422: {"description": "Noto'g'ri rasm formati yoki hajmi"},
    },
)
async def upload_banner_image(
    banner_id: uuid.UUID,
    file: UploadFile,
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.EDIT),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> AdBannerOut:
    """
    Banner rasmi yuklash — korxona O'Z banneri yoki superadmin.

    Magic-byte validatsiya storage ichida (JPEG/PNG/WebP, 5MB).
    """
    image_url = await storage.upload_product_photo(file)
    is_superadmin = current_user.enterprise_id is None
    banner = await service.update_banner_image(
        db,
        banner_id=banner_id,
        image_url=image_url,
        enterprise_id=current_user.enterprise_id,
        is_superadmin=is_superadmin,
    )
    await db.commit()
    return _build_banner_out(banner)


# ─── MP5: Qaynoq aksiyalar endpointi ─────────────────────────────────────────


@router.get(
    "/promos",
    response_model=list[MarketplacePromoOut],
    summary="Marketplace qaynoq aksiyalar (cross-tenant, featured)",
    description=(
        "Barcha korxonalarning marketplace'da ko'rinadigan qaynoq aksiyalarini qaytaradi. "
        "Bu endpoint ATAYIN cross-tenant — korxona filtri qo'llanmaydi. "
        "Faqat: marketplace_featured=True + is_active=True + valid sana. "
        "Har aksiyada supplier korxona nomi (supplier_name) qaytadi. "
        "Featured EMAS aksiyalar HECH QACHON ko'rinmaydi (izolyatsiya kafolati)."
    ),
    responses={
        200: {"description": "Qaynoq aksiyalar ro'yxati"},
        403: {"description": "marketplace moduli yoqilmagan yoki ruxsat yo'q"},
    },
)
async def list_marketplace_promos(
    limit: int = Query(20, ge=1, le=50, description="Maksimal aksiyalar soni (max 50)"),
    current_user: AppUser = require_permission(Module.MARKETPLACE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> list[MarketplacePromoOut]:
    """
    Marketplace qaynoq aksiyalari — cross-tenant browse.

    XAVFSIZLIK: faqat marketplace_featured=True + aktiv + valid sana.
    Featured emas aksiyalar HECH QACHON oqmaydi (izolyatsiya).
    """
    items = await service.list_marketplace_promos(db, limit=limit)
    result = []
    for promo, enterprise in items:
        result.append(
            MarketplacePromoOut(
                id=promo.id,
                name_uz=promo.name_uz,
                name_ru=promo.name_ru,
                promo_type=promo.promo_type,
                rule_json=promo.rule_json,
                banner_url=promo.banner_url,
                valid_from=promo.valid_from,
                valid_to=promo.valid_to,
                is_active=promo.is_active,
                marketplace_featured=promo.marketplace_featured,
                enterprise_id=enterprise.id,
                supplier_name=enterprise.name,
            )
        )
    return result
