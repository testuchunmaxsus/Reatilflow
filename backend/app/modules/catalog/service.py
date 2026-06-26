"""
Katalog servis qatlami — biznes mantiq.

Funksiyalar:
  Kategoriya:
    create_category(db, data, enterprise_id) → Category
    list_categories(db, enterprise_id) → list[Category]

  Narx segmenti:
    create_segment(db, data, enterprise_id) → PriceSegment
    list_segments(db, enterprise_id) → list[PriceSegment]

  Mahsulot:
    create_product(db, data, actor_id, redis, enterprise_id) → Product
    get_product(db, product_id, user, enterprise_id) → Product
    list_products(db, user, enterprise_id, filters...) → (list[Product], total)
    update_product(db, product_id, data, actor_id, user, enterprise_id) → Product
    delete_product(db, product_id, actor_id, user, enterprise_id) → None  (soft-delete)

  Narx:
    set_price(db, product_id, data, actor_id, user, enterprise_id) → ProductPrice
    get_price_history(db, product_id, user, enterprise_id) → list[PriceHistory]

Qoidalar:
  - Har mutatsiyada audit_log va outbox_event yoziladi.
  - price_history faqat INSERT (append-only).
  - version optimistik lock (mos kelmasa catalog.version_conflict).
  - sku/barcode unikalligi — catalog.duplicate_sku / catalog.duplicate_barcode.
  - Idempotentlik: Redis kalit idem:catalog:create:{user_id}:{client_uuid} → product_id, TTL 24s.
    client_uuid hech qachon Product.id ga yozilmaydi — id har doim server uuid7().
  - Branch ko'rinish: administrator/accountant → barchasi;
    boshqa rollar → faqat branch_scope IS NULL yoki == user.branch_id.
    Doiradan tashqari mahsulot uchun get/update/delete → 404 (mavjudlikni oshkor qilmaslik).
  - MT2: enterprise_id server-avtoritar — har query'ga WHERE enterprise_id = ? qo'shiladi.
    enterprise_id=None (superadmin) → filtr qo'llanmaydi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.i18n import localized_name
from app.core.security import mask_pii
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.catalog import (
    Category,
    PriceHistory,
    PriceSegment,
    Product,
    ProductPrice,
)
from app.models.outbox import OutboxEvent
from app.models.user import AppUser
from app.modules.catalog.schemas import (
    CategoryCreate,
    PriceSet,
    ProductCreate,
    ProductUpdate,
    PriceSegmentCreate,
)
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)

# ─── Konstantalar ────────────────────────────────────────────────────────────

# Idempotentlik TTL (soniya): 24 soat
_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:catalog:create"

# Rollar: bu rollar barcha branch_scope larni ko'ra oladi
_BRANCH_ADMIN_ROLES = frozenset({"administrator", "accountant"})


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi (APPEND-ONLY). PII mask_pii() dan o'tkaziladi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=json.dumps(mask_pii(before), default=str) if before else None,
        after_json=json.dumps(mask_pii(after), default=str) if after else None,
    )
    db.add(log)


async def _write_outbox(
    db: AsyncSession,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """outbox_event ga yozuv qo'shadi."""
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


def _apply_branch_visibility(query, user: AppUser):
    """
    Qator-darajali filial ko'rinish filtri.

    Katalog ko'rinish qarorlari:
      - administrator va accountant rollari barcha mahsulotlarni ko'radi (branch_scope ga qaramasdan).
      - Boshqa rollar (agent, courier, store) faqat o'zlari tegishli filialga oid yoki
        global (branch_scope IS NULL) mahsulotlarni ko'radi.

    Bu cheklov cross-branch IDOR hujumlaridan himoya qiladi:
      agent B filialdagi mahsulotni A filial agent ko'ra olmaydi.
    """
    if user.role in _BRANCH_ADMIN_ROLES:
        # Administrator va accountant barcha yozuvlarni ko'radi
        return query

    # Boshqa rollar: faqat global yoki o'z branch_scope'i
    # branch_scope IS NULL → global mahsulot (barcha filiallarga ko'rinadi)
    # branch_scope == user.branch_id → ushbu filialga tegishli mahsulot
    if user.branch_id is not None:
        return query.where(
            or_(
                Product.branch_scope.is_(None),
                Product.branch_scope == str(user.branch_id),
            )
        )
    else:
        # branch_id=None bo'lgan odatiy foydalanuvchi: faqat global mahsulotlar
        return query.where(Product.branch_scope.is_(None))


# ─── Category ────────────────────────────────────────────────────────────────


async def create_category(
    db: AsyncSession,
    data: CategoryCreate,
    enterprise_id: uuid.UUID | None = None,
) -> Category:
    """Yangi kategoriya yaratadi. enterprise_id server tomonidan o'rnatiladi."""
    cat = Category(
        name_uz=data.name_uz,
        name_ru=data.name_ru,
        parent_id=data.parent_id,
        is_active=data.is_active,
        enterprise_id=enterprise_id,
    )
    db.add(cat)
    await db.flush()

    await _write_audit(
        db, None, "create", "category", str(cat.id),
        after={"name_uz": cat.name_uz, "name_ru": cat.name_ru},
    )
    await _write_outbox(
        db, "category", str(cat.id), "category.created",
        {"id": str(cat.id), "name_uz": cat.name_uz},
    )
    return cat


async def list_categories(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None = None,
) -> list[Category]:
    """Barcha faol kategoriyalar ro'yxati. MT2: enterprise_id bo'yicha filtrlanadi."""
    stmt = select(Category).where(Category.deleted_at.is_(None)).order_by(Category.created_at)
    stmt = apply_enterprise_filter(stmt, enterprise_id, Category.enterprise_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    enterprise_id: uuid.UUID | None = None,
) -> Category:
    """ID bo'yicha kategoriya oladi. MT2: enterprise_id filtr. Topilmasa AppError."""
    stmt = select(Category).where(
        Category.id == category_id, Category.deleted_at.is_(None)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Category.enterprise_id)
    result = await db.execute(stmt)
    cat = result.scalar_one_or_none()
    if cat is None:
        raise AppError("catalog.category_not_found", status_code=404)
    return cat


# ─── PriceSegment ────────────────────────────────────────────────────────────


async def create_segment(
    db: AsyncSession,
    data: PriceSegmentCreate,
    enterprise_id: uuid.UUID | None = None,
) -> PriceSegment:
    """Yangi narx segmenti yaratadi. enterprise_id server tomonidan o'rnatiladi."""
    # MT izolyatsiya: nom KORXONA ICHIDA unique (uix_segment_ent_name, migr 0032).
    # Boshqa korxonadagi (yoki o'chirilgan) bir xil nom bloklamaydi → toza 409.
    dup_stmt = select(PriceSegment.id).where(
        PriceSegment.name == data.name, PriceSegment.deleted_at.is_(None)
    )
    dup_stmt = apply_enterprise_filter(dup_stmt, enterprise_id, PriceSegment.enterprise_id)
    if (await db.execute(dup_stmt)).scalar_one_or_none() is not None:
        raise AppError("catalog.duplicate_segment", status_code=409)

    seg = PriceSegment(name=data.name, enterprise_id=enterprise_id)
    db.add(seg)
    await db.flush()

    await _write_audit(db, None, "create", "price_segment", str(seg.id), after={"name": seg.name})
    await _write_outbox(
        db, "price_segment", str(seg.id), "price_segment.created", {"id": str(seg.id), "name": seg.name}
    )
    return seg


async def list_segments(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None = None,
) -> list[PriceSegment]:
    """Barcha narx segmentlar ro'yxati. MT2: enterprise_id filtr."""
    stmt = select(PriceSegment).where(PriceSegment.deleted_at.is_(None)).order_by(PriceSegment.created_at)
    stmt = apply_enterprise_filter(stmt, enterprise_id, PriceSegment.enterprise_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_segment(
    db: AsyncSession,
    segment_id: uuid.UUID,
    enterprise_id: uuid.UUID | None = None,
) -> PriceSegment:
    """ID bo'yicha narx segmenti oladi. MT2: enterprise_id filtr. Topilmasa AppError."""
    stmt = select(PriceSegment).where(
        PriceSegment.id == segment_id, PriceSegment.deleted_at.is_(None)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, PriceSegment.enterprise_id)
    result = await db.execute(stmt)
    seg = result.scalar_one_or_none()
    if seg is None:
        raise AppError("catalog.segment_not_found", status_code=404)
    return seg


# ─── Product CRUD ────────────────────────────────────────────────────────────


async def _check_sku_unique(
    db: AsyncSession,
    sku: str | None,
    exclude_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """SKU unikalligi tekshiradi. MT2: enterprise bo'yicha. Dublikat bo'lsa AppError."""
    if not sku:
        return
    stmt = select(Product.id).where(
        Product.sku == sku, Product.deleted_at.is_(None)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise AppError("catalog.duplicate_sku", status_code=409)


async def _check_barcode_unique(
    db: AsyncSession,
    barcode: str | None,
    exclude_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """Barcode unikalligi tekshiradi. MT2: enterprise bo'yicha. Dublikat bo'lsa AppError."""
    if not barcode:
        return
    stmt = select(Product.id).where(
        Product.barcode == barcode, Product.deleted_at.is_(None)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise AppError("catalog.duplicate_barcode", status_code=409)


async def create_product(
    db: AsyncSession,
    data: ProductCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> Product:
    """
    Yangi mahsulot yaratadi.

    CRITICAL FIX: id har doim server tomonida uuid7() bilan generatsiya qilinadi.
    client_uuid hech qachon Product.id ga yozilmaydi.

    Idempotentlik (Redis orqali):
      Kalit: idem:catalog:create:{actor_id}:{client_uuid} → saqlangan product_id
      TTL: 86400 soniya (24 soat).
      Bir xil (actor_id, client_uuid) kelsa — saqlangan product_id bo'yicha
      mavjud (deleted_at IS NULL) mahsulotni qaytaradi.
      Redis o'chsa — idempotentlik o'tkazib yuboriladi (yangi yaratiladi), log yoziladi.
    """
    # ── Redis idempotentlik tekshiruvi ──────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                # Avvalgi yaratilgan product_id ni qaytaramiz
                stmt = select(Product).where(
                    Product.id == uuid.UUID(cached_id),
                    Product.deleted_at.is_(None),
                )
                stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                # Agar mahsulot o'chirilgan bo'lsa — yangi yaratamiz (idem_key yangilanadi)
                logger.warning(
                    "create_product: idem_key=%s product_id=%s o'chirilgan, yangi yaratilmoqda",
                    idem_key, cached_id,
                )
        except Exception as exc:
            # Redis o'chgan holat — log yozib davom etamiz (graceful degradatsiya)
            logger.warning(
                "create_product: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi mahsulot yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None  # Redis kalidini saqlash ham amalga oshmaydi

    # ── Unikallık tekshiruv (enterprise bo'yicha) ──────────────────────────
    await _check_sku_unique(db, data.sku, enterprise_id=enterprise_id)
    await _check_barcode_unique(db, data.barcode, enterprise_id=enterprise_id)

    # ── Mahsulot yaratish — id HER DOIM server uuid7() ────────────────────
    # client_uuid hech qachon id ga yozilmaydi (IDOR oldini olish)
    # enterprise_id SERVER tomonidan o'rnatiladi (klient bera olmaydi)
    product = Product(
        name_uz=data.name_uz,
        name_ru=data.name_ru,
        sku=data.sku,
        barcode=data.barcode,
        mxik_code=data.mxik_code,
        unit=data.unit,
        category_id=data.category_id,
        photo_url=data.photo_url,
        is_active=data.is_active,
        branch_scope=data.branch_scope,
        enterprise_id=enterprise_id,
    )

    db.add(product)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "sku" in exc_str:
            raise AppError("catalog.duplicate_sku", status_code=409) from exc
        if "barcode" in exc_str:
            raise AppError("catalog.duplicate_barcode", status_code=409) from exc
        raise

    after = {
        "id": str(product.id),
        "name_uz": product.name_uz,
        "sku": product.sku,
        "barcode": product.barcode,
    }
    await _write_audit(db, actor_id, "create", "product", str(product.id), after=after)
    await _write_outbox(db, "product", str(product.id), "product.created", after)

    # ── Redis idempotentlik kalitini saqlash ────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(product.id), ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_product: Redis idempotentlik kalitini saqlash muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Idempotentlik keyingi so'rovda ishlamaydi.",
                idem_key, exc,
            )

    return product


async def get_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Product:
    """
    ID bo'yicha mahsulot oladi (soft-delete qilinmagan).

    MT2: enterprise_id filtr — boshqa korxona mahsuloti 404 qaytaradi.
    Branch ko'rinish filtri qo'llaniladi (user berilsa).
    Mavjudlikni oshkor qilmaslik: doiradan tashqari mahsulot ham 404 qaytaradi.

    Raises:
        AppError("catalog.product_not_found"): mahsulot topilmasa yoki doiradan tashqari.
    """
    stmt = select(Product).where(
        Product.id == product_id, Product.deleted_at.is_(None)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
    if user is not None:
        stmt = _apply_branch_visibility(stmt, user)

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise AppError("catalog.product_not_found", status_code=404)
    return product


async def list_products(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    branch_scope: str | None = None,
) -> tuple[list[Product], int]:
    """
    Paginated mahsulotlar ro'yxati.

    Branch ko'rinish filtri avtomatik qo'llaniladi (user berilsa):
      - administrator/accountant: barcha mahsulotlar
      - boshqa rollar: faqat global (branch_scope=NULL) yoki o'z filiallari

    Qo'shimcha filtrlar:
      - category_id, is_active, search, branch_scope (qo'shimcha filtr)
    """
    base_where = [Product.deleted_at.is_(None)]

    if category_id is not None:
        base_where.append(Product.category_id == category_id)

    if is_active is not None:
        base_where.append(Product.is_active == is_active)

    if search:
        # SQLite LIKE (test) va PostgreSQL ILIKE (prod) uchun moslashtirilgan
        pattern = f"%{search}%"
        base_where.append(
            or_(
                Product.name_uz.ilike(pattern),
                Product.name_ru.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.barcode.ilike(pattern),
            )
        )

    if branch_scope is not None:
        base_where.append(Product.branch_scope.ilike(f"%{branch_scope}%"))

    # MT2: enterprise filtr
    count_stmt = select(func.count()).select_from(Product).where(*base_where)
    count_stmt = apply_enterprise_filter(count_stmt, enterprise_id, Product.enterprise_id)
    if user is not None:
        count_stmt = _apply_branch_visibility(count_stmt, user)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Ro'yxat (enterprise + branch visibility filtri bilan)
    stmt = (
        select(Product)
        .where(*base_where)
        .order_by(Product.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
    if user is not None:
        stmt = _apply_branch_visibility(stmt, user)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def update_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: ProductUpdate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Product:
    """
    Mahsulotni yangilaydi (PATCH — faqat berilgan maydonlar).

    Branch ko'rinish filtri: user.branch_id doiradan tashqari mahsulot → 404.
    Optimistik lock: data.version joriy version bilan mos kelmasa → version_conflict.

    Raises:
        AppError("catalog.product_not_found"): mahsulot topilmasa yoki doiradan tashqari.
        AppError("catalog.version_conflict"): version mos kelmasa.
        AppError("catalog.duplicate_sku"/"catalog.duplicate_barcode"): dublikat.
    """
    product = await get_product(db, product_id, user=user, enterprise_id=enterprise_id)

    # Optimistik lock tekshiruvi
    if product.version != data.version:
        raise AppError("catalog.version_conflict", status_code=409)

    before = {
        "name_uz": product.name_uz,
        "sku": product.sku,
        "version": product.version,
    }

    # Unikallık tekshiruvlar (enterprise bo'yicha)
    if data.sku is not None and data.sku != product.sku:
        await _check_sku_unique(db, data.sku, exclude_id=product_id, enterprise_id=enterprise_id)
    if data.barcode is not None and data.barcode != product.barcode:
        await _check_barcode_unique(db, data.barcode, exclude_id=product_id, enterprise_id=enterprise_id)

    # Maydonlarni yangilash
    if data.name_uz is not None:
        product.name_uz = data.name_uz
    if data.name_ru is not None:
        product.name_ru = data.name_ru
    if data.sku is not None:
        product.sku = data.sku
    if data.barcode is not None:
        product.barcode = data.barcode
    if data.mxik_code is not None:
        product.mxik_code = data.mxik_code
    if data.unit is not None:
        product.unit = data.unit
    if data.category_id is not None:
        product.category_id = data.category_id
    if data.photo_url is not None:
        product.photo_url = data.photo_url
    if data.is_active is not None:
        product.is_active = data.is_active
    if data.branch_scope is not None:
        product.branch_scope = data.branch_scope

    # Versiyani oshirish
    product.version = product.version + 1
    product.updated_at = _now()

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "sku" in exc_str:
            raise AppError("catalog.duplicate_sku", status_code=409) from exc
        if "barcode" in exc_str:
            raise AppError("catalog.duplicate_barcode", status_code=409) from exc
        raise

    after = {
        "name_uz": product.name_uz,
        "sku": product.sku,
        "version": product.version,
    }
    await _write_audit(db, actor_id, "update", "product", str(product.id), before=before, after=after)
    await _write_outbox(db, "product", str(product.id), "product.updated", after)

    return product


async def delete_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """
    Mahsulotni soft-delete qiladi (deleted_at ni o'rnatadi).

    MT2: enterprise_id filtr — boshqa korxona mahsuloti 404 qaytaradi.
    Branch ko'rinish filtri: doiradan tashqari mahsulot → 404.

    Raises:
        AppError("catalog.product_not_found"): mahsulot topilmasa yoki doiradan tashqari.
    """
    product = await get_product(db, product_id, user=user, enterprise_id=enterprise_id)

    product.deleted_at = _now()
    product.updated_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "delete", "product", str(product.id))
    await _write_outbox(
        db, "product", str(product.id), "product.deleted", {"id": str(product.id)}
    )


# ─── Narx ────────────────────────────────────────────────────────────────────


async def set_price(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: PriceSet,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> ProductPrice:
    """
    Mahsulot uchun narx o'rnatadi.

    Algoritm:
      1. Mahsulot va segment mavjudligini tekshiradi (branch visibility bilan).
      2. Joriy ProductPrice (valid_to=None) ni SELECT FOR UPDATE bilan qulflab topadi (race oldini olish).
      3. Eski narx bilan yangi narxni PriceHistory ga APPEND qiladi.
      4. Yangi ProductPrice yozuvi yaratadi.

    PriceHistory faqat INSERT (append-only) — hech qachon o'chirmaydi.
    """
    # Mahsulot tekshiruvi (enterprise + branch visibility bilan)
    product = await get_product(db, product_id, user=user, enterprise_id=enterprise_id)

    # Segment tekshiruvi (enterprise bo'yicha)
    await get_segment(db, data.segment_id, enterprise_id=enterprise_id)

    # Joriy narxni SELECT FOR UPDATE bilan qulflab topish (race oldini olish)
    stmt = (
        select(ProductPrice)
        .where(
            ProductPrice.product_id == product_id,
            ProductPrice.segment_id == data.segment_id,
            ProductPrice.valid_to.is_(None),
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    current_price = result.scalar_one_or_none()

    old_price_value = current_price.price if current_price else Decimal("0")

    # Eski narxni yopish (valid_to o'rnatish)
    if current_price is not None:
        current_price.valid_to = data.valid_from

    # Narx tarixiga qo'shish (APPEND-ONLY)
    history = PriceHistory(
        product_id=product_id,
        segment_id=data.segment_id,
        old_price=old_price_value,
        new_price=data.price,
        currency=data.currency,
        changed_by=actor_id,
        changed_at=_now(),
        enterprise_id=product.enterprise_id,
    )
    db.add(history)

    # Yangi ProductPrice yaratish
    new_price = ProductPrice(
        product_id=product_id,
        segment_id=data.segment_id,
        price=data.price,
        currency=data.currency,
        valid_from=data.valid_from,
        valid_to=None,
        enterprise_id=product.enterprise_id,
    )
    db.add(new_price)
    await db.flush()

    # Audit + Outbox
    await _write_audit(
        db, actor_id, "price_set", "product", str(product_id),
        before={"old_price": str(old_price_value)},
        after={"new_price": str(data.price), "segment_id": str(data.segment_id)},
    )
    await _write_outbox(
        db, "product", str(product_id), "product.price_changed",
        {
            "product_id": str(product_id),
            "segment_id": str(data.segment_id),
            "new_price": str(data.price),
            "currency": data.currency,
        },
    )

    return new_price


async def get_price_history(
    db: AsyncSession,
    product_id: uuid.UUID,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> list[PriceHistory]:
    """
    Mahsulot narx tarixini qaytaradi (yangirog'i birinchi).

    Branch ko'rinish filtri: mahsulot mavjudligini tekshirishda qo'llaniladi.

    Raises:
        AppError("catalog.product_not_found"): mahsulot topilmasa yoki doiradan tashqari.
    """
    # Mahsulot mavjudligini tekshirish (enterprise + branch visibility bilan)
    await get_product(db, product_id, user=user, enterprise_id=enterprise_id)

    stmt = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.changed_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ─── Photo URL yangilash ──────────────────────────────────────────────────────


async def update_photo_url(
    db: AsyncSession,
    product_id: uuid.UUID,
    photo_url: str,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Product:
    """Mahsulot rasm URL sini yangilaydi. MT2: enterprise + branch visibility tekshiriladi."""
    product = await get_product(db, product_id, user=user, enterprise_id=enterprise_id)

    before_url = product.photo_url
    product.photo_url = photo_url
    product.updated_at = _now()
    await db.flush()

    await _write_audit(
        db, actor_id, "photo_update", "product", str(product_id),
        before={"photo_url": before_url},
        after={"photo_url": photo_url},
    )

    return product
