"""
Marketplace servis qatlami — MP1 + MP2.

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
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.catalog import Product, ProductPrice
from app.models.enterprise import Enterprise
from app.models.marketplace import MarketplaceOrder, MarketplaceOrderLine
from app.models.outbox import OutboxEvent
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
