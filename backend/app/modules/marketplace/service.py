"""
Marketplace servis qatlami — MP1 + MP2 + MP3 + MP5.

MP1 funksiyalar:
  browse_products(db, filters...) → (list[ProductWithEnterprise], total)
  get_published_product(db, product_id) → (Product, Enterprise)
  list_suppliers(db) → list[SupplierRow]

MP2 funksiyalar:
  create_order(db, buyer_user, lines, client_uuid) → MarketplaceOrder
  list_outgoing(db, buyer_enterprise_id, ...) → (list[MarketplaceOrder], total)
  list_incoming(db, supplier_enterprise_id, status, ...) → (list[MarketplaceOrder], total)
  get_order(db, order_id, current_user) → MarketplaceOrder
  confirm_order(db, order_id, supplier_user) → MarketplaceOrder
  reject_order(db, order_id, supplier_user, reason) → MarketplaceOrder

MP3 funksiyalar (yetkazish oqimi):
  ship_order(db, order_id, supplier_user, courier_id) → MarketplaceOrder
    confirmed → delivering, kuryer tayinlaydi (supplier korxona kuryeri).
  deliver_order(db, order_id, courier_user, proof_photo_url) → MarketplaceOrder
    delivering → delivered + proof_photo_url + delivered_at.
    Faqat tayinlangan kuryer (courier_id == courier_user.id).
  accept_order(db, order_id, buyer_user, lines_info) → MarketplaceOrder
    delivered → accepted + accepted_at.
    Atomik: har line → StoreInventory yozuvi (cost=unit_price, sale=cost*(1+markup/100)).
    Outbox: marketplace.order_accepted.

MP5 funksiyalar (banner + qaynoq aksiya):
  list_active_banners(db, limit) → list[AdBanner]
    cross-tenant, is_active + valid sana + priority tartib.
  create_banner(db, data, enterprise_id) → AdBanner
    enterprise-scoped yaratish (korxona o'z reklamasi).
  get_banner_for_enterprise(db, banner_id, enterprise_id) → AdBanner
    IDOR-safe: faqat o'z korxonasi banneri.
  patch_banner(db, banner_id, data, enterprise_id, is_superadmin) → AdBanner
    enterprise-scoped tahrirlash; superadmin har qanday bannerni tahrirlaydi.
  delete_banner(db, banner_id, enterprise_id, is_superadmin) → None
    enterprise-scoped o'chirish; superadmin har qanday bannerni o'chiradi.
  update_banner_image(db, banner_id, image_url, enterprise_id, is_superadmin) → AdBanner
    Banner rasm URL yangilash (MinIO yuklash keyin).
  list_marketplace_promos(db, limit) → list[(Promo, Enterprise)]
    cross-tenant: marketplace_featured + is_active + valid sana.
  toggle_promo_featured(db, promo_id, enterprise_id, featured) → Promo
    Korxona O'Z aksiyasini featured qiladi (enterprise-scoped, IDOR-safe).

Xavfsizlik qoidalari (MP1):
  - marketplace_published=True QATTIQ SHART — hech qachon published emas
    mahsulot cross-tenant oqmasligi.
  - enterprise_id filtri bu endpointlarda QILINMAYDI (atayin cross-tenant).
  - Lekin is_active=True va deleted_at IS NULL tekshiriladi.
  - supplier korxona enterprise_id=product.enterprise_id → JOIN orqali.

Xavfsizlik qoidalari (MP2):
  - Buyurtma faqat buyer YOKI supplier korxonasiga ko'rinadi.
  - Uchinchi korxona → 404 (mavjudlikni oshkor qilmaslik).
  - Server-avtoritar narx: klient narx bera olmaydi (marketplace_price yoki segment).
  - Bitta so'rovda faqat bitta supplier korxona mahsulotlari (aralash → xato).
  - confirm/reject: FAQAT supplier korxona admini bajaradi.

Xavfsizlik qoidalari (MP3):
  - ship: FAQAT supplier korxona (admin/accountant). Kuryer ham shu korxona.
  - deliver: FAQAT tayinlangan kuryer (courier_id == current_user.id).
  - accept: FAQAT buyer korxona (admin/store).
  - 3-korxona → 404.

Xavfsizlik qoidalari (MP5 banner):
  - create/patch/delete: FAQAT korxona O'Z banneri (enterprise_id == enterprise_id).
  - Superadmin har qanday bannerni moderatsiya qila oladi (is_active toggle).
  - list_active_banners: cross-tenant (faqat is_active + valid_from<=bugun<=valid_to).
  - IDOR: boshqa korxona banneri → 404 (mavjudlikni oshkor qilmaslik).

Xavfsizlik qoidalari (MP5 promo):
  - toggle_featured: FAQAT korxona O'Z aksiyasi (enterprise_id filtr — IDOR-safe).
  - list_marketplace_promos: cross-tenant, faqat marketplace_featured=True + aktiv + valid.
  - Featured emas aksiyalar oqmaydi (izolyatsiya kafolati).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.ad_banner import AdBanner
from app.models.catalog import Product, ProductPrice
from app.models.enterprise import Enterprise
from app.models.marketplace import MarketplaceOrder, MarketplaceOrderLine, MP_VALID_TRANSITIONS
from app.models.outbox import OutboxEvent
from app.models.promo import Promo
from app.models.store_inventory import StoreInventory
from app.models.user import AppUser


# ─── Browse ──────────────────────────────────────────────────────────────────


async def browse_products(
    db: AsyncSession,
    *,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    supplier_enterprise: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[tuple[Product, Enterprise, Decimal | None]], int]:
    """
    Barcha korxonalar published mahsulotlarini qaytaradi (cross-tenant browse).

    XAVFSIZLIK:
      - marketplace_published=True MAJBURIY filtr.
      - product.deleted_at IS NULL va product.is_active=True tekshiriladi.
      - enterprise filtr QO'LLANMAYDI (atayin cross-tenant — dizayn).
      - Natijada: (Product, Enterprise, effective_price) uchlik qaytariladi.

    Args:
        db:                  AsyncSession
        search:              nom/sku/barcode bo'yicha ILIKE qidiruv
        category_id:         Kategoriya filtri
        supplier_enterprise: Faqat bitta korxona mahsulotlari (ixtiyoriy)
        page:                Sahifa raqami (1-bazali)
        limit:               Sahifa hajmi

    Returns:
        (items, total) — items: (Product, Enterprise, price) uchlik ro'yxati
    """
    offset = (page - 1) * limit

    # Asosiy so'rov: Product JOIN Enterprise
    stmt = (
        select(Product, Enterprise)
        .join(Enterprise, Product.enterprise_id == Enterprise.id)
        .where(
            Product.marketplace_published.is_(True),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Enterprise.deleted_at.is_(None),
            Enterprise.status == "active",
        )
    )

    # ── Ixtiyoriy filtrlar ───────────────────────────────────────────────────
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Product.name_uz.ilike(pattern),
                Product.name_ru.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.barcode.ilike(pattern),
            )
        )

    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)

    if supplier_enterprise is not None:
        stmt = stmt.where(Product.enterprise_id == supplier_enterprise)

    # ── Count ────────────────────────────────────────────────────────────────
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # ── Paginated natijalar ──────────────────────────────────────────────────
    stmt = stmt.order_by(Product.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()  # list of Row(Product, Enterprise)

    # ── Narx hisoblash: marketplace_price yoki birinchi aktiv segment narxi ─
    items: list[tuple[Product, Enterprise, Decimal | None]] = []
    for product, enterprise in rows:
        price = await _resolve_price(db, product)
        items.append((product, enterprise, price))

    return items, total


async def get_published_product(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> tuple[Product, Enterprise, Decimal | None]:
    """
    Bitta published marketplace mahsulotini qaytaradi.

    XAVFSIZLIK:
      - marketplace_published=True bo'lmasa → 404 (boshqa korxona ichki
        mahsulotini oshkor qilmaslik).
      - deleted_at IS NULL va is_active=True tekshiriladi.

    Returns:
        (Product, Enterprise, effective_price) uchlik.

    Raises:
        AppError(404) — mahsulot topilmasa yoki published emas bo'lsa.
    """
    stmt = (
        select(Product, Enterprise)
        .join(Enterprise, Product.enterprise_id == Enterprise.id)
        .where(
            Product.id == product_id,
            Product.marketplace_published.is_(True),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Enterprise.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    row = result.first()

    if row is None:
        # 404 — mavjudlikni oshkor qilmaslik (published emas yoki yo'q — farq yo'q)
        raise AppError(
            message_key="marketplace.product_not_found",
            status_code=404,
        )

    product, enterprise = row
    price = await _resolve_price(db, product)
    return product, enterprise, price


async def list_suppliers(
    db: AsyncSession,
) -> list[dict]:
    """
    Marketplace'da published mahsuloti bor korxonalar ro'yxatini qaytaradi.

    Har korxona uchun: enterprise_id, name, product_count.
    Tartibi: product_count kamayish.
    """
    stmt = (
        select(
            Enterprise.id.label("enterprise_id"),
            Enterprise.name.label("name"),
            func.count(Product.id).label("product_count"),
        )
        .join(Product, Product.enterprise_id == Enterprise.id)
        .where(
            Product.marketplace_published.is_(True),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Enterprise.deleted_at.is_(None),
            Enterprise.status == "active",
        )
        .group_by(Enterprise.id, Enterprise.name)
        .order_by(func.count(Product.id).desc())
    )
    result = await db.execute(stmt)
    return [
        {
            "enterprise_id": row.enterprise_id,
            "name": row.name,
            "product_count": row.product_count,
        }
        for row in result.all()
    ]


# ─── Publish toggle ──────────────────────────────────────────────────────────


async def toggle_marketplace(
    db: AsyncSession,
    product_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    published: bool,
    marketplace_price: Decimal | None,
) -> Product:
    """
    Korxona O'Z mahsulotini marketplace'ga publish/unpublish qiladi.

    XAVFSIZLIK (enterprise-scoped):
      - Faqat product.enterprise_id == enterprise_id bo'lsa ishlaydi.
      - Boshqa korxona mahsuloti → 404 (IDOR himoyasi).

    Args:
        db:               AsyncSession
        product_id:       Mahsulot UUID
        enterprise_id:    Joriy foydalanuvchi korxonasi UUID
        published:        True=publish, False=unpublish
        marketplace_price: Ixtiyoriy narx (None=segment narx)

    Returns:
        Yangilangan Product ORM obyekti.

    Raises:
        AppError(404) — mahsulot topilmasa yoki boshqa korxona mahsuloti.
    """
    stmt = (
        select(Product)
        .where(
            Product.id == product_id,
            Product.enterprise_id == enterprise_id,  # enterprise scope — MAJBURIY
            Product.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    product: Product | None = result.scalar_one_or_none()

    if product is None:
        raise AppError(
            message_key="catalog.product_not_found",
            status_code=404,
        )

    product.marketplace_published = published
    product.marketplace_price = marketplace_price
    await db.flush()
    return product


# ─── Yordamchi ───────────────────────────────────────────────────────────────


async def _resolve_price(
    db: AsyncSession,
    product: Product,
) -> Decimal | None:
    """
    Mahsulot uchun ko'rsatiladigan narxni aniqlaydi.

    Tartib:
      1. marketplace_price mavjud bo'lsa → shu narx.
      2. Aktiv product_price (valid_from ≤ now, valid_to IS NULL yoki > now)
         bo'lsa → birinchi segmentning narxi.
      3. Hech narsa yo'q → None.
    """
    if product.marketplace_price is not None:
        return product.marketplace_price

    # Birinchi aktiv segment narxini olish
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = (
        select(ProductPrice.price)
        .where(
            ProductPrice.product_id == product.id,
            ProductPrice.enterprise_id == product.enterprise_id,
            ProductPrice.valid_from <= now,
            or_(
                ProductPrice.valid_to.is_(None),
                ProductPrice.valid_to > now,
            ),
        )
        .order_by(ProductPrice.valid_from.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    price: Decimal | None = result.scalar_one_or_none()
    return price


# ─── MP2: Buyurtma yaratish ───────────────────────────────────────────────────


class OrderLineInput:
    """Buyurtma qatori kiritish (ichki DTO)."""

    __slots__ = ("product_id", "qty")

    def __init__(self, product_id: uuid.UUID, qty: Decimal) -> None:
        self.product_id = product_id
        self.qty = qty


async def create_order(
    db: AsyncSession,
    buyer_user: AppUser,
    lines: list[OrderLineInput],
    client_uuid: uuid.UUID | None = None,
) -> MarketplaceOrder:
    """
    Marketplace buyurtma yaratadi.

    QOIDALAR:
      - Har mahsulot marketplace_published=True bo'lishi SHART (aks holda 404).
      - Bitta so'rovda FAQAT bitta supplier korxona mahsulotlari
        (aralash supplier → AppError 422).
      - unit_price SERVER TOMONIDA: marketplace_price yoki segment narx.
        Narx topilmasa → AppError 422.
      - buyer_enterprise = buyer_user.enterprise_id.
      - buyer_store = user tomonida boshqariladigan do'kon (agar store roli bo'lsa).
      - Idempotentlik: client_uuid + buyer_enterprise_id UNIQUE.
      - Outbox: marketplace.order_created (supplier_enterprise_id bilan).

    Args:
        db:          AsyncSession
        buyer_user:  Buyurtma bergan foydalanuvchi (buyer korxona foydalanuvchisi)
        lines:       [OrderLineInput(product_id, qty), ...]
        client_uuid: Idempotentlik UUID (ixtiyoriy)

    Returns:
        Yaratilgan MarketplaceOrder (lines bilan yuklangan).

    Raises:
        AppError(404) — mahsulot published emas yoki topilmadi.
        AppError(422) — aralash supplier, narx topilmadi, bo'sh lines, dublikat.
    """
    if not lines:
        raise AppError(
            message_key="marketplace.order_empty_lines",
            status_code=422,
        )

    buyer_enterprise_id = buyer_user.enterprise_id
    if buyer_enterprise_id is None:
        raise AppError(
            message_key="marketplace.order_buyer_no_enterprise",
            status_code=422,
        )

    # ── Idempotentlik tekshiruvi ──────────────────────────────────────────────
    if client_uuid is not None:
        existing_stmt = select(MarketplaceOrder).where(
            MarketplaceOrder.buyer_enterprise_id == buyer_enterprise_id,
            MarketplaceOrder.client_uuid == client_uuid,
        )
        existing_result = await db.execute(existing_stmt)
        existing_order = existing_result.scalar_one_or_none()
        if existing_order is not None:
            return existing_order

    # ── Mahsulotlarni yuklash va narx aniqlash ────────────────────────────────
    product_ids = [line.product_id for line in lines]
    stmt = (
        select(Product)
        .where(
            Product.id.in_(product_ids),
            Product.marketplace_published.is_(True),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
    )
    result = await db.execute(stmt)
    products_found: list[Product] = list(result.scalars().all())

    # Topilmagan mahsulotlar tekshiruvi
    found_ids = {p.id for p in products_found}
    missing_ids = [lid for lid in product_ids if lid not in found_ids]
    if missing_ids:
        raise AppError(
            message_key="marketplace.product_not_found",
            status_code=404,
        )

    # Bitta supplier tekshiruvi
    supplier_enterprises = {p.enterprise_id for p in products_found}
    if len(supplier_enterprises) > 1:
        raise AppError(
            message_key="marketplace.order_mixed_suppliers",
            status_code=422,
        )

    supplier_enterprise_id: uuid.UUID = supplier_enterprises.pop()  # type: ignore[assignment]

    # Supplier == buyer bo'lishi mumkin emas (o'zidan buyurtma)
    if supplier_enterprise_id == buyer_enterprise_id:
        raise AppError(
            message_key="marketplace.order_self_purchase",
            status_code=422,
        )

    # ── Narx hisoblash va qatorlar yaratish ───────────────────────────────────
    product_map: dict[uuid.UUID, Product] = {p.id: p for p in products_found}
    order_lines: list[MarketplaceOrderLine] = []
    total_amount = Decimal("0")

    for line_input in lines:
        product = product_map[line_input.product_id]
        unit_price = await _resolve_price(db, product)
        if unit_price is None:
            raise AppError(
                message_key="marketplace.order_no_price",
                status_code=422,
                params={"product_id": str(line_input.product_id)},
            )

        line_total = unit_price * line_input.qty
        total_amount += line_total

        order_line = MarketplaceOrderLine(
            id=uuid7(),
            product_id=line_input.product_id,
            qty=line_input.qty,
            unit_price=unit_price,
            line_total=line_total,
        )
        order_lines.append(order_line)

    # ── Buyurtma yaratish ─────────────────────────────────────────────────────

    # buyer_store_id: store roli foydalanuvchisi uchun topiladi
    from app.models.store import Store

    buyer_store_id: uuid.UUID | None = None
    if buyer_user.role == "store":
        store_stmt = select(Store.id).where(
            Store.user_id == buyer_user.id,
            Store.enterprise_id == buyer_enterprise_id,
            Store.deleted_at.is_(None),
        ).limit(1)
        store_result = await db.execute(store_stmt)
        buyer_store_id = store_result.scalar_one_or_none()

    order = MarketplaceOrder(
        id=uuid7(),
        buyer_enterprise_id=buyer_enterprise_id,
        buyer_store_id=buyer_store_id,
        buyer_user_id=buyer_user.id,
        supplier_enterprise_id=supplier_enterprise_id,
        status="pending",
        total_amount=total_amount,
        client_uuid=client_uuid,
    )
    db.add(order)
    await db.flush()  # id olish uchun

    # Lines ni order_id bilan bog'lash
    for ol in order_lines:
        ol.order_id = order.id
        db.add(ol)

    # ── Outbox ────────────────────────────────────────────────────────────────
    # supplier_enterprise_id bilan — supplier sync uchun
    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_created",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(buyer_enterprise_id),
            "supplier_enterprise_id": str(supplier_enterprise_id),
            "status": "pending",
            "total_amount": str(total_amount),
        }),
        enterprise_id=supplier_enterprise_id,
    )
    db.add(outbox)

    await db.flush()

    # lines ni order obyektiga bog'laymiz (selectin lazy load o'rniga to'g'ridan-to'g'ri)
    # flush qilingan, demak order.id mavjud va barcha line'lar DB'da
    # ORM relationship'ga assignment o'rniga result'ni construct qilamiz
    return order


# ─── MP2: Buyurtmalar ro'yxati ────────────────────────────────────────────────


async def list_outgoing(
    db: AsyncSession,
    buyer_enterprise_id: uuid.UUID,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[MarketplaceOrder], int]:
    """
    Xaridor korxona chiquvchi buyurtmalari (o'zi jo'natgan).

    ACCESS: faqat buyer_enterprise_id == current_user.enterprise_id bo'lganda chaqiriladi.

    Args:
        db:                  AsyncSession
        buyer_enterprise_id: Xaridor korxona UUID
        status:              Holat filtri (ixtiyoriy)
        page:                Sahifa (1-bazali)
        limit:               Sahifa hajmi

    Returns:
        (orders, total)
    """
    offset = (page - 1) * limit
    base = select(MarketplaceOrder).where(
        MarketplaceOrder.buyer_enterprise_id == buyer_enterprise_id,
    )
    if status:
        base = base.where(MarketplaceOrder.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = (
        base
        .order_by(MarketplaceOrder.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    orders = list(result.scalars().all())
    return orders, total


async def list_incoming(
    db: AsyncSession,
    supplier_enterprise_id: uuid.UUID,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[MarketplaceOrder], int]:
    """
    Supplier korxona kiruvchi buyurtmalari (o'ziga kelgan).

    ACCESS: faqat supplier_enterprise_id == current_user.enterprise_id bo'lganda chaqiriladi.

    Args:
        db:                    AsyncSession
        supplier_enterprise_id: Supplier korxona UUID
        status:                Holat filtri (ixtiyoriy)
        page:                  Sahifa (1-bazali)
        limit:                 Sahifa hajmi

    Returns:
        (orders, total)
    """
    offset = (page - 1) * limit
    base = select(MarketplaceOrder).where(
        MarketplaceOrder.supplier_enterprise_id == supplier_enterprise_id,
    )
    if status:
        base = base.where(MarketplaceOrder.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = (
        base
        .order_by(MarketplaceOrder.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    orders = list(result.scalars().all())
    return orders, total


async def get_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    current_user: AppUser,
) -> MarketplaceOrder:
    """
    Bitta marketplace buyurtmasini qaytaradi.

    XAVFSIZLIK (kritik — 3-tomon izolyatsiya):
      Faqat buyer YOKI supplier korxona foydalanuvchisi ko'radi.
      Uchinchi korxona → 404 (mavjudlikni oshkor qilmaslik).

    Args:
        db:           AsyncSession
        order_id:     Buyurtma UUID
        current_user: Joriy foydalanuvchi (enterprise_id tekshiriladi)

    Returns:
        MarketplaceOrder

    Raises:
        AppError(404) — topilmasa yoki ruxsatsiz.
    """
    user_enterprise = current_user.enterprise_id
    if user_enterprise is None:
        # Superadmin — hamma narsani ko'radi
        stmt = select(MarketplaceOrder).where(MarketplaceOrder.id == order_id)
    else:
        stmt = select(MarketplaceOrder).where(
            MarketplaceOrder.id == order_id,
            or_(
                MarketplaceOrder.buyer_enterprise_id == user_enterprise,
                MarketplaceOrder.supplier_enterprise_id == user_enterprise,
            ),
        )

    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )
    return order


# ─── MP2: Tasdiqlash / Rad etish ─────────────────────────────────────────────


async def confirm_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    supplier_user: AppUser,
) -> MarketplaceOrder:
    """
    Supplier korxona admini buyurtmani tasdiqlaydi: pending → confirmed.

    XAVFSIZLIK:
      - Faqat order.supplier_enterprise_id == supplier_user.enterprise_id bo'lsa ishlaydi.
      - buyer korxona foydalanuvchisi confirm qila OLMAYDI → 403.
      - Faqat pending holat uchun → boshqa holat = 422.

    Args:
        db:            AsyncSession
        order_id:      Buyurtma UUID
        supplier_user: Supplier korxona foydalanuvchisi

    Returns:
        Yangilangan MarketplaceOrder (status=confirmed).

    Raises:
        AppError(404) — buyurtma topilmadi yoki ruxsatsiz.
        AppError(403) — buyer korxona confirm qilmoqchi.
        AppError(422) — noto'g'ri holat o'tishi.
    """
    order = await _get_supplier_order(db, order_id, supplier_user)

    if order.status != "pending":
        raise AppError(
            message_key="marketplace.order_invalid_transition",
            status_code=422,
            params={"from_status": order.status, "to_status": "confirmed"},
        )

    order.status = "confirmed"
    from datetime import datetime, timezone
    order.updated_at = datetime.now(timezone.utc)

    # Outbox: buyer korxona sync uchun
    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_confirmed",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(order.buyer_enterprise_id),
            "supplier_enterprise_id": str(order.supplier_enterprise_id),
            "status": "confirmed",
        }),
        enterprise_id=order.buyer_enterprise_id,
    )
    db.add(outbox)
    await db.flush()
    return order


async def reject_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    supplier_user: AppUser,
    reason: str | None = None,
) -> MarketplaceOrder:
    """
    Supplier korxona admini buyurtmani rad etadi: pending → rejected.

    XAVFSIZLIK:
      - Faqat order.supplier_enterprise_id == supplier_user.enterprise_id bo'lsa ishlaydi.
      - buyer korxona reject qila OLMAYDI → 403.
      - Faqat pending holat uchun.

    Args:
        db:            AsyncSession
        order_id:      Buyurtma UUID
        supplier_user: Supplier korxona foydalanuvchisi
        reason:        Rad etish sababi (ixtiyoriy matn)

    Returns:
        Yangilangan MarketplaceOrder (status=rejected).

    Raises:
        AppError(404) — buyurtma topilmadi yoki ruxsatsiz.
        AppError(403) — buyer korxona reject qilmoqchi.
        AppError(422) — noto'g'ri holat o'tishi.
    """
    order = await _get_supplier_order(db, order_id, supplier_user)

    if order.status != "pending":
        raise AppError(
            message_key="marketplace.order_invalid_transition",
            status_code=422,
            params={"from_status": order.status, "to_status": "rejected"},
        )

    order.status = "rejected"
    order.reject_reason = reason
    from datetime import datetime, timezone
    order.updated_at = datetime.now(timezone.utc)

    # Outbox: buyer korxona sync uchun
    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_rejected",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(order.buyer_enterprise_id),
            "supplier_enterprise_id": str(order.supplier_enterprise_id),
            "status": "rejected",
            "reject_reason": reason,
        }),
        enterprise_id=order.buyer_enterprise_id,
    )
    db.add(outbox)
    await db.flush()
    return order


# ─── MP3: Yetkazish oqimi ────────────────────────────────────────────────────


class AcceptLineInfo:
    """accept_order uchun har line'ga berilgan ma'lumot (ichki DTO)."""

    __slots__ = ("line_id", "expiry_date", "markup_percent")

    def __init__(
        self,
        line_id: uuid.UUID,
        expiry_date: date | None = None,
        markup_percent: Decimal = Decimal("0"),
    ) -> None:
        self.line_id = line_id
        self.expiry_date = expiry_date
        self.markup_percent = markup_percent


async def ship_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    supplier_user: AppUser,
    courier_id: uuid.UUID,
) -> MarketplaceOrder:
    """
    Supplier korxona buyurtmani jo'natadi: confirmed → delivering.
    Kuryer tayinlanadi (courier_id = supplier korxona kuryeri).

    XAVFSIZLIK:
      - Faqat supplier korxona foydalanuvchisi (admin/accountant) bajaradi.
      - Kuryer shu supplier korxonaga tegishli va courier roli bo'lishi kerak.
      - Faqat confirmed holat uchun → boshqa holat = 422.

    Args:
        db:            AsyncSession
        order_id:      Buyurtma UUID
        supplier_user: Supplier korxona foydalanuvchisi
        courier_id:    Tayinlanadigan kuryer FK (app_user.id)

    Returns:
        Yangilangan MarketplaceOrder (status=delivering).

    Raises:
        AppError(404) — buyurtma topilmadi yoki ruxsatsiz.
        AppError(403) — supplier emas.
        AppError(422) — noto'g'ri holat o'tishi yoki kuryer topilmadi.
    """
    order = await _get_supplier_order(db, order_id, supplier_user)

    if order.status not in MP_VALID_TRANSITIONS or "delivering" not in MP_VALID_TRANSITIONS.get(order.status, set()):
        raise AppError(
            message_key="marketplace.order_invalid_transition",
            status_code=422,
            params={"from_status": order.status, "to_status": "delivering"},
        )

    # Kuryer tekshiruvi — shu supplier korxonaniki bo'lishi shart
    from app.models.user import AppUser as UserModel
    courier_stmt = select(UserModel).where(
        UserModel.id == courier_id,
        UserModel.role == "courier",
        UserModel.enterprise_id == order.supplier_enterprise_id,
        UserModel.is_active.is_(True),
    )
    courier_result = await db.execute(courier_stmt)
    courier = courier_result.scalar_one_or_none()
    if courier is None:
        raise AppError(
            message_key="marketplace.courier_not_found",
            status_code=422,
        )

    order.status = "delivering"
    order.courier_id = courier_id
    order.updated_at = datetime.now(timezone.utc)

    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_delivering",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(order.buyer_enterprise_id),
            "supplier_enterprise_id": str(order.supplier_enterprise_id),
            "status": "delivering",
            "courier_id": str(courier_id),
        }),
        enterprise_id=order.buyer_enterprise_id,
    )
    db.add(outbox)
    await db.flush()
    return order


async def deliver_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    courier_user: AppUser,
    proof_photo_url: str | None = None,
) -> MarketplaceOrder:
    """
    Tayinlangan kuryer yetkazib berdi: delivering → delivered.
    proof_photo_url va delivered_at o'rnatiladi.

    XAVFSIZLIK:
      - Faqat tayinlangan kuryer (order.courier_id == courier_user.id) bajaradi.
      - Boshqa kuryer → 403.
      - Faqat delivering holat uchun → boshqa holat = 422.

    Args:
        db:             AsyncSession
        order_id:       Buyurtma UUID
        courier_user:   Joriy kuryer foydalanuvchisi
        proof_photo_url: Isboti rasm URL (ixtiyoriy, lekin tavsiya etiladi)

    Returns:
        Yangilangan MarketplaceOrder (status=delivered).

    Raises:
        AppError(404) — buyurtma topilmadi.
        AppError(403) — bu kuryer tayinlanmagan.
        AppError(422) — noto'g'ri holat o'tishi.
    """
    # Buyurtmani olish (faqat supplier YOKI buyer tomoni — courier ular ichida)
    stmt = select(MarketplaceOrder).where(MarketplaceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )

    # Faqat tayinlangan kuryer deliver qila oladi
    if order.courier_id != courier_user.id:
        raise AppError(
            message_key="marketplace.order_courier_mismatch",
            status_code=403,
        )

    if "delivered" not in MP_VALID_TRANSITIONS.get(order.status, set()):
        raise AppError(
            message_key="marketplace.order_invalid_transition",
            status_code=422,
            params={"from_status": order.status, "to_status": "delivered"},
        )

    now = datetime.now(timezone.utc)
    order.status = "delivered"
    order.delivered_at = now
    order.proof_photo_url = proof_photo_url
    order.updated_at = now

    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_delivered",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(order.buyer_enterprise_id),
            "supplier_enterprise_id": str(order.supplier_enterprise_id),
            "status": "delivered",
            "proof_photo_url": proof_photo_url,
            "delivered_at": now.isoformat(),
        }),
        enterprise_id=order.buyer_enterprise_id,
    )
    db.add(outbox)
    await db.flush()
    return order


async def accept_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    buyer_user: AppUser,
    lines_info: list[AcceptLineInfo],
    store_id: uuid.UUID | None = None,
) -> MarketplaceOrder:
    """
    Buyer do'kon buyurtmani qabul qiladi: delivered → accepted.
    Atomik: har buyurtma qatori → StoreInventory yozuvi.

    XAVFSIZLIK:
      - Faqat buyer korxona (admin yoki store roli) bajaradi.
      - Supplier korxona accept qila OLMAYDI → 403.
      - Faqat delivered holat uchun → boshqa holat = 422.

    BIZNES MANTIQI:
      - Har line uchun StoreInventory yaratiladi:
          cost_price  = line.unit_price (server-avtoritar)
          sale_price  = cost_price * (1 + markup_percent / 100)
          expiry_date = lines_info[line].expiry_date
          qty         = line.qty
          enterprise_id = order.buyer_enterprise_id
          store_id    = buyer_store_id (parametrdan yoki order.buyer_store_id)

    Args:
        db:          AsyncSession
        order_id:    Buyurtma UUID
        buyer_user:  Buyer korxona foydalanuvchisi
        lines_info:  Har line uchun expiry_date + markup_percent ro'yxati
        store_id:    Do'kon UUID (None bo'lsa order.buyer_store_id ishlatiladi)

    Returns:
        Yangilangan MarketplaceOrder (status=accepted).

    Raises:
        AppError(404) — buyurtma topilmadi yoki ruxsatsiz.
        AppError(403) — buyer emas.
        AppError(422) — noto'g'ri holat o'tishi yoki store topilmadi.
    """
    order = await _get_buyer_order(db, order_id, buyer_user)

    if "accepted" not in MP_VALID_TRANSITIONS.get(order.status, set()):
        raise AppError(
            message_key="marketplace.order_invalid_transition",
            status_code=422,
            params={"from_status": order.status, "to_status": "accepted"},
        )

    # Do'kon aniqlash: parametr → order.buyer_store_id → xato
    effective_store_id = store_id or order.buyer_store_id
    if effective_store_id is None:
        raise AppError(
            message_key="marketplace.accept_no_store",
            status_code=422,
        )

    # Do'kon buyer korxonasiga tegishli ekanligini tekshiramiz
    from app.models.store import Store
    store_stmt = select(Store).where(
        Store.id == effective_store_id,
        Store.enterprise_id == order.buyer_enterprise_id,
        Store.deleted_at.is_(None),
    )
    store_result = await db.execute(store_stmt)
    store_obj = store_result.scalar_one_or_none()
    if store_obj is None:
        raise AppError(
            message_key="marketplace.accept_store_not_found",
            status_code=422,
        )

    # lines_info indeksi quramiz
    lines_info_map: dict[uuid.UUID, AcceptLineInfo] = {
        li.line_id: li for li in lines_info
    }

    # Buyurtma line'larini yuklash (selectin bo'lmasa qo'lda)
    from sqlalchemy.orm import selectinload
    order_with_lines_stmt = (
        select(MarketplaceOrder)
        .options(selectinload(MarketplaceOrder.lines))
        .where(MarketplaceOrder.id == order_id)
    )
    ow_result = await db.execute(order_with_lines_stmt)
    order_loaded = ow_result.scalar_one()

    now = datetime.now(timezone.utc)

    # Har line → StoreInventory yozuvi
    for line in order_loaded.lines:
        li = lines_info_map.get(line.id)
        markup_pct = li.markup_percent if li else Decimal("0")
        expiry_dt = li.expiry_date if li else None

        # sale_price server tomonida hisoblanadi
        sale_price = line.unit_price * (1 + markup_pct / Decimal("100"))
        # 2 kasrga yaxlitlash
        sale_price = sale_price.quantize(Decimal("0.01"))

        inv = StoreInventory(
            id=uuid7(),
            enterprise_id=order.buyer_enterprise_id,
            store_id=effective_store_id,
            product_id=line.product_id,
            qty=line.qty,
            cost_price=line.unit_price,
            markup_percent=markup_pct,
            sale_price=sale_price,
            expiry_date=expiry_dt,
            status="active",
            source_order_id=order.id,
            created_at=now,
        )
        db.add(inv)

    # Buyurtma holatini yangilash
    order.status = "accepted"
    order.accepted_at = now
    order.updated_at = now

    outbox = OutboxEvent(
        aggregate_type="marketplace_order",
        aggregate_id=str(order.id),
        event_type="marketplace.order_accepted",
        payload=json.dumps({
            "order_id": str(order.id),
            "buyer_enterprise_id": str(order.buyer_enterprise_id),
            "supplier_enterprise_id": str(order.supplier_enterprise_id),
            "status": "accepted",
            "store_id": str(effective_store_id),
            "accepted_at": now.isoformat(),
        }),
        enterprise_id=order.supplier_enterprise_id,
    )
    db.add(outbox)
    await db.flush()
    return order


# ─── Ichki yordamchilar ───────────────────────────────────────────────────────


async def _get_supplier_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    supplier_user: AppUser,
) -> MarketplaceOrder:
    """
    Supplier foydalanuvchi uchun buyurtmani yuklaydi va tekshiradi.

    XAVFSIZLIK:
      - Buyurtma mavjudligini tekshiradi (404 agar yo'q).
      - supplier_enterprise_id == supplier_user.enterprise_id tekshiradi.
        Agar buyer korxona foydalanuvchisi confirm/reject qilmoqchi bo'lsa → 403.
      - Uchinchi korxona → 404 (supplier ga ham, buyer ga ham tegishli emas).

    Returns:
        MarketplaceOrder

    Raises:
        AppError(404) — buyurtma topilmadi.
        AppError(403) — foydalanuvchi supplier emas (buyer yoki uchinchi korxona).
    """
    user_enterprise = supplier_user.enterprise_id

    # Avval buyurtmani topish (ruxsatsiz access uchun ham 404 — lekin buyer uchun 403)
    stmt = select(MarketplaceOrder).where(MarketplaceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )

    # Superadmin bypass
    if user_enterprise is None:
        return order

    # Buyer korxona foydalanuvchisi confirm/reject qila olmaydi → 403
    if order.buyer_enterprise_id == user_enterprise and order.supplier_enterprise_id != user_enterprise:
        raise AppError(
            message_key="marketplace.order_supplier_only",
            status_code=403,
        )

    # Uchinchi korxona → 404
    if order.supplier_enterprise_id != user_enterprise:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )

    return order


async def _get_buyer_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    buyer_user: AppUser,
) -> MarketplaceOrder:
    """
    Buyer foydalanuvchi uchun buyurtmani yuklaydi va tekshiradi.

    XAVFSIZLIK:
      - Buyurtma mavjudligini tekshiradi (404 agar yo'q).
      - buyer_enterprise_id == buyer_user.enterprise_id tekshiradi.
        Agar supplier korxona foydalanuvchisi accept qilmoqchi bo'lsa → 403.
      - Uchinchi korxona → 404.

    Returns:
        MarketplaceOrder

    Raises:
        AppError(404) — buyurtma topilmadi.
        AppError(403) — foydalanuvchi buyer emas (supplier yoki uchinchi korxona).
    """
    user_enterprise = buyer_user.enterprise_id

    stmt = select(MarketplaceOrder).where(MarketplaceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )

    # Superadmin bypass
    if user_enterprise is None:
        return order

    # Supplier korxona foydalanuvchisi accept qila olmaydi → 403
    if order.supplier_enterprise_id == user_enterprise and order.buyer_enterprise_id != user_enterprise:
        raise AppError(
            message_key="marketplace.order_buyer_only",
            status_code=403,
        )

    # Uchinchi korxona → 404
    if order.buyer_enterprise_id != user_enterprise:
        raise AppError(
            message_key="marketplace.order_not_found",
            status_code=404,
        )

    return order


# ─── StoreInventory o'qish ────────────────────────────────────────────────────


async def list_store_inventory(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
    store_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[StoreInventory], int]:
    """
    Do'kon inventarini ro'yxatini qaytaradi (tenant-scoped).

    XAVFSIZLIK:
      - enterprise_id MAJBURIY — boshqa korxona inventarini ko'ra olmaydi.
      - store_id bo'yicha qo'shimcha filtr (ixtiyoriy).

    Args:
        db:            AsyncSession
        enterprise_id: Joriy korxona UUID (buyer korxona)
        store_id:      Do'kon filtri (ixtiyoriy)
        product_id:    Mahsulot filtri (ixtiyoriy)
        status:        Holat filtri: active | expired (ixtiyoriy)
        page:          Sahifa (1-bazali)
        limit:         Sahifa hajmi

    Returns:
        (inventories, total)
    """
    offset = (page - 1) * limit
    base = select(StoreInventory).where(
        StoreInventory.enterprise_id == enterprise_id,
    )

    if store_id is not None:
        base = base.where(StoreInventory.store_id == store_id)

    if product_id is not None:
        base = base.where(StoreInventory.product_id == product_id)

    if status is not None:
        base = base.where(StoreInventory.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = base.order_by(StoreInventory.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return items, total


# ─── MP5: Reklama banner funksiyalari ─────────────────────────────────────────


async def list_active_banners(
    db: AsyncSession,
    limit: int = 5,
) -> list[AdBanner]:
    """
    Marketplace uchun aktiv bannerlar ro'yxatini qaytaradi (cross-tenant).

    QOIDALAR:
      - is_active=True MAJBURIY.
      - valid_from <= bugun <= valid_to MAJBURIY.
      - priority kamayish tartibida (yuqori son birinchi).
      - limit bilan cheklanadi (halaqit bermaslik uchun, default 5).
      - cross-tenant: enterprise_id filtri qo'llanmaydi.

    Args:
        db:    AsyncSession
        limit: Maksimal bannerlar soni (default 5)

    Returns:
        AdBanner ro'yxati (priority kamayish tartibida).
    """
    today = datetime.now(timezone.utc).date()
    stmt = (
        select(AdBanner)
        .where(
            AdBanner.is_active.is_(True),
            AdBanner.valid_from <= today,
            AdBanner.valid_to >= today,
        )
        .order_by(AdBanner.priority.desc(), AdBanner.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_banner(
    db: AsyncSession,
    data,
    enterprise_id: uuid.UUID,
) -> AdBanner:
    """
    Korxona O'Z reklamasini yaratadi (enterprise-scoped).

    XAVFSIZLIK:
      - enterprise_id = current_user.enterprise_id — server avtoritar.
      - Klient enterprise_id bera OLMAYDI.

    Args:
        db:            AsyncSession
        data:          AdBannerCreate (Pydantic sxema)
        enterprise_id: Korxona UUID (server tomonida o'rnatiladi)

    Returns:
        Yaratilgan AdBanner.

    Raises:
        AppError(422) — valid_to < valid_from bo'lsa.
    """
    if data.valid_to < data.valid_from:
        raise AppError(
            message_key="marketplace.banner_invalid_dates",
            status_code=422,
        )

    banner = AdBanner(
        id=uuid7(),
        enterprise_id=enterprise_id,
        title=data.title,
        image_url=data.image_url,
        target_url=data.target_url,
        target_product_id=data.target_product_id,
        is_active=data.is_active,
        priority=data.priority,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(banner)
    await db.flush()
    return banner


async def _get_banner_scoped(
    db: AsyncSession,
    banner_id: uuid.UUID,
    enterprise_id: uuid.UUID | None,
    is_superadmin: bool = False,
) -> AdBanner:
    """
    Bannerli yuklash — enterprise-scoped yoki superadmin bypass.

    XAVFSIZLIK:
      - enterprise_id berilsa: faqat shu korxona banneri (IDOR-safe).
      - is_superadmin=True: har qanday bannerni oladi.
      - Topilmasa → 404 (mavjudlikni oshkor qilmaslik).

    Returns:
        AdBanner

    Raises:
        AppError(404) — topilmasa yoki boshqa korxona banneri.
    """
    stmt = select(AdBanner).where(AdBanner.id == banner_id)

    if not is_superadmin and enterprise_id is not None:
        stmt = stmt.where(AdBanner.enterprise_id == enterprise_id)

    result = await db.execute(stmt)
    banner = result.scalar_one_or_none()

    if banner is None:
        raise AppError(
            message_key="marketplace.banner_not_found",
            status_code=404,
        )
    return banner


async def get_banner_for_enterprise(
    db: AsyncSession,
    banner_id: uuid.UUID,
    enterprise_id: uuid.UUID,
) -> AdBanner:
    """
    Korxona O'Z bannerini oladi (IDOR-safe).

    Raises:
        AppError(404) — boshqa korxona banneri yoki topilmasa.
    """
    return await _get_banner_scoped(db, banner_id, enterprise_id, is_superadmin=False)


async def patch_banner(
    db: AsyncSession,
    banner_id: uuid.UUID,
    data,
    enterprise_id: uuid.UUID | None,
    is_superadmin: bool = False,
) -> AdBanner:
    """
    Bannerni qisman yangilaydi (PATCH).

    XAVFSIZLIK:
      - enterprise_id bilan: faqat O'Z banneri tahrir (IDOR-safe).
      - is_superadmin=True: superadmin har qanday bannerni tahrirlaydi
        (moderatsiya: is_active toggle).

    Args:
        db:            AsyncSession
        banner_id:     Banner UUID
        data:          AdBannerPatch (Pydantic sxema — faqat berilgan maydonlar)
        enterprise_id: Korxona UUID (None = superadmin)
        is_superadmin: Superadmin belgisi

    Returns:
        Yangilangan AdBanner.

    Raises:
        AppError(404) — topilmasa yoki IDOR.
        AppError(422) — valid_to < valid_from.
    """
    banner = await _get_banner_scoped(db, banner_id, enterprise_id, is_superadmin)

    if data.title is not None:
        banner.title = data.title
    if data.image_url is not None:
        banner.image_url = data.image_url
    if "target_url" in data.model_fields_set:
        banner.target_url = data.target_url
    if "target_product_id" in data.model_fields_set:
        banner.target_product_id = data.target_product_id
    if data.is_active is not None:
        banner.is_active = data.is_active
    if data.priority is not None:
        banner.priority = data.priority
    if data.valid_from is not None:
        banner.valid_from = data.valid_from
    if data.valid_to is not None:
        banner.valid_to = data.valid_to

    # Sana izchilligini tekshirish
    if banner.valid_to < banner.valid_from:
        raise AppError(
            message_key="marketplace.banner_invalid_dates",
            status_code=422,
        )

    banner.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return banner


async def delete_banner(
    db: AsyncSession,
    banner_id: uuid.UUID,
    enterprise_id: uuid.UUID | None,
    is_superadmin: bool = False,
) -> None:
    """
    Bannerni o'chiradi (qattiq o'chirish — ad_banner jadvalidan DELETE).

    XAVFSIZLIK:
      - enterprise_id bilan: faqat O'Z banneri o'chirish (IDOR-safe).
      - is_superadmin=True: superadmin har qanday bannerni o'chiradi.

    Raises:
        AppError(404) — topilmasa yoki IDOR.
    """
    banner = await _get_banner_scoped(db, banner_id, enterprise_id, is_superadmin)
    await db.delete(banner)
    await db.flush()


async def update_banner_image(
    db: AsyncSession,
    banner_id: uuid.UUID,
    image_url: str,
    enterprise_id: uuid.UUID | None,
    is_superadmin: bool = False,
) -> AdBanner:
    """
    Banner rasm URL ni yangilaydi (MinIO upload'dan keyin chaqiriladi).

    XAVFSIZLIK:
      - enterprise_id bilan: faqat O'Z banneri (IDOR-safe).
      - is_superadmin=True: superadmin bypass.

    Args:
        db:          AsyncSession
        banner_id:   Banner UUID
        image_url:   MinIO dan qaytgan URL
        enterprise_id: Korxona UUID (None = superadmin)
        is_superadmin: Superadmin belgisi

    Returns:
        Yangilangan AdBanner.

    Raises:
        AppError(404) — topilmasa yoki IDOR.
    """
    banner = await _get_banner_scoped(db, banner_id, enterprise_id, is_superadmin)
    banner.image_url = image_url
    banner.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return banner


# ─── MP5: Qaynoq aksiya (marketplace promo) funksiyalari ─────────────────────


async def list_marketplace_promos(
    db: AsyncSession,
    limit: int = 20,
) -> list[tuple[Promo, Enterprise]]:
    """
    Marketplace'da ko'rinadigan qaynoq aksiyalar (cross-tenant).

    QOIDALAR:
      - marketplace_featured=True MAJBURIY — izolyatsiya kafolati.
      - is_active=True MAJBURIY.
      - valid_from <= bugun <= valid_to MAJBURIY.
      - deleted_at IS NULL.
      - cross-tenant: enterprise_id filtri qo'llanmaydi.
      - Har aksiya bilan birga supplier korxona nomi qaytadi.
      - Featured EMAS aksiyalar HECH QACHON oqmaydi (izolyatsiya).

    Args:
        db:    AsyncSession
        limit: Maksimal aksiyalar soni (default 20)

    Returns:
        list of (Promo, Enterprise) uchliklar.
    """
    today = datetime.now(timezone.utc).date()
    stmt = (
        select(Promo, Enterprise)
        .join(Enterprise, Promo.enterprise_id == Enterprise.id)
        .where(
            Promo.deleted_at.is_(None),
            Promo.is_active.is_(True),
            Promo.marketplace_featured.is_(True),
            Promo.valid_from <= today,
            Promo.valid_to >= today,
            Enterprise.deleted_at.is_(None),
            Enterprise.status == "active",
        )
        .order_by(Promo.valid_from.asc(), Promo.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def toggle_promo_featured(
    db: AsyncSession,
    promo_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    featured: bool,
) -> Promo:
    """
    Korxona O'Z aksiyasini marketplace'da featured qiladi (opt-in).

    XAVFSIZLIK (KRITIK — IDOR-safe):
      - enterprise_id == promo.enterprise_id tekshiriladi.
      - Boshqa korxona aksiyasini featured qilishga urinish → 404.
      - Server tomonida enterprise_id o'rnatiladi (klient bera olmaydi).

    Args:
        db:            AsyncSession
        promo_id:      Aksiya UUID
        enterprise_id: Joriy korxona UUID (server tomonida)
        featured:      True = marketplace qaynoq, False = olib tashlash

    Returns:
        Yangilangan Promo.

    Raises:
        AppError(404) — aksiya topilmasa yoki boshqa korxona aksiyasi (IDOR).
    """
    stmt = select(Promo).where(
        Promo.id == promo_id,
        Promo.enterprise_id == enterprise_id,  # IDOR himoyasi — MAJBURIY
        Promo.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()

    if promo is None:
        raise AppError(
            message_key="promo.not_found",
            status_code=404,
        )

    promo.marketplace_featured = featured
    promo.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return promo
