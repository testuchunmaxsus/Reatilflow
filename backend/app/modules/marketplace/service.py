"""
Marketplace servis qatlami — MP1.

Funksiyalar:
  browse_products(db, filters...) → (list[ProductWithEnterprise], total)
  get_published_product(db, product_id) → (Product, Enterprise)
  list_suppliers(db) → list[SupplierRow]

Xavfsizlik qoidalari:
  - marketplace_published=True QATTIQ SHART — hech qachon published emas
    mahsulot cross-tenant oqmasligi.
  - enterprise_id filtri bu endpointlarda QILINMAYDI (atayin cross-tenant).
  - Lekin is_active=True va deleted_at IS NULL tekshiriladi.
  - supplier korxona enterprise_id=product.enterprise_id → JOIN orqali.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.catalog import Product, ProductPrice
from app.models.enterprise import Enterprise


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
