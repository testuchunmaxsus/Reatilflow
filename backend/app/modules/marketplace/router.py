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

XAVFSIZLIK (MP3):
  - ship: FAQAT supplier korxona (admin/accountant) — marketplace:edit.
  - deliver: FAQAT tayinlangan kuryer — marketplace:edit (courier roli).
  - accept: FAQAT buyer korxona (admin/store) — marketplace:edit.
  - inventory: buyer korxona foydalanuvchisi — marketplace:view.
  - 3-korxona → 404.
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
    MarketplaceAcceptIn,
    MarketplaceDeliverIn,
    MarketplaceOrderCreateIn,
    MarketplaceOrderOut,
    MarketplaceOrderRejectIn,
    MarketplaceProductOut,
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
