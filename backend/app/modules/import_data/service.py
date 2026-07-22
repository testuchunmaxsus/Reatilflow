"""
Import confirm servis qatlami.

Maqsad:
  - preview satrlarini tasdiqlash → DB ga yozish.
  - Rol bo'yicha target aniqlash (server-avtoritar):
      * Korxona roli (administrator/accountant) → katalog (Product + narx).
      * Do'kon roli (store) → StoreInventory (qoldiq).
  - Op-darajali xato izolyatsiyasi: bitta satr xatosi batchni yiqitmaydi.
  - Idempotentlik: client_uuid takror → skip (skipped++).

DIZAYN:
  - StoreInventory idempotentlik (#16): client_uuid DB-darajali UNIQUE
    (uq_store_inv_client_uuid, migratsiya 0037) — ASOSIY backstop. Redis
    faqat tez-yo'l optimizatsiyasi (GET, SETNX EMAS) — commit'dan OLDIN kalit
    qo'yilmaydi, shuning uchun commit muvaffaqiyatsiz bo'lganda dublikat
    noto'g'ri "band" bo'lib qolmaydi. Redis kalitlari faqat commit
    MUVAFFAQIYATLI bo'lgandan KEYIN o'rnatiladi.
  - Katalog idempotentlik: mavjud create_product client_uuid Redis keshi.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.catalog import PriceSegment, Product, ProductPrice
from app.models.store import Store
from app.models.store_inventory import StoreInventory
from app.models.user import AppUser
from app.modules.catalog.schemas import ProductCreate, PriceSet
from app.modules.catalog import service as catalog_service
from app.modules.import_data.schemas import (
    ConfirmRow,
    ImportConfirmIn,
    ImportConfirmOut,
    RowError,
)
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)

# Korxona rollari (katalogga yozadi)
_ENTERPRISE_ROLES = frozenset({"administrator", "accountant"})
# Do'kon roli (StoreInventory ga yozadi)
_STORE_ROLE = "store"

# Redis idempotentlik prefiksi (StoreInventory uchun)
_IDEM_STORE_INV_PREFIX = "idem:import:store_inv"
_IDEM_TTL = 86400  # 24 soat


async def confirm_import(
    db: AsyncSession,
    body: ImportConfirmIn,
    current_user: AppUser,
    redis=None,
) -> ImportConfirmOut:
    """
    Import confirm: preview satrlarini DB ga yozadi.

    Target rol bo'yicha server-avtoritar aniqlanadi.
    Op-darajali xato izolyatsiyasi: bitta satr xatosi batchni yiqitmaydi.
    """
    enterprise_id = current_user.enterprise_id
    role = current_user.role

    # Target aniqlash
    if role in _ENTERPRISE_ROLES:
        target = "catalog"
    elif role == _STORE_ROLE:
        target = "store_inventory"
    else:
        # Boshqa rollar (agent) import qila olmaydi
        raise AppError("rbac.permission_denied", status_code=403)

    created = 0
    skipped = 0
    errors: list[RowError] = []
    created_uuids: list[uuid.UUID] = []

    if target == "catalog":
        created, skipped, errors = await _confirm_catalog(
            db, body.rows, current_user, enterprise_id, redis
        )
    else:
        store_id = await _get_store_id(db, current_user)
        if store_id is None:
            raise AppError("import.store_not_found", status_code=404)
        created, skipped, errors, created_uuids = await _confirm_store_inventory(
            db, body.rows, enterprise_id, store_id, redis
        )

    # Commit
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("confirm_import: commit xato: %r", exc)
        raise AppError("common.internal_error", status_code=500) from exc

    # ── Redis kalit (#16): faqat commit MUVAFFAQIYATLI bo'lgandan KEYIN
    # o'rnatiladi — tez-yo'l optimizatsiyasi, DB unikalligi asosiy backstop.
    if target == "store_inventory" and redis is not None and created_uuids:
        for cu in created_uuids:
            idem_key = f"{_IDEM_STORE_INV_PREFIX}:{cu}"
            try:
                await redis.set(idem_key, "1", ex=_IDEM_TTL)
            except Exception as exc:
                logger.warning(
                    "confirm_import: Redis kalit saqlash muvaffaqiyatsiz "
                    "(kalit=%s, xato=%r)", idem_key, exc,
                )

    return ImportConfirmOut(
        created=created,
        skipped=skipped,
        errors=errors,
        target=target,
    )


# ─── Katalog import ────────────────────────────────────────────────────────────


async def _confirm_catalog(
    db: AsyncSession,
    rows: list[ConfirmRow],
    actor: AppUser,
    enterprise_id: uuid.UUID | None,
    redis=None,
) -> tuple[int, int, list[RowError]]:
    """Satrlarni katalogga yozadi (Product + narx)."""
    created = 0
    skipped = 0
    errors: list[RowError] = []

    # Default segment
    default_segment = await _get_or_create_default_segment(db, enterprise_id, actor.id)

    for row in rows:
        try:
            result = await _create_catalog_row(
                db, row, actor, enterprise_id, default_segment, redis
            )
            if result == "skipped":
                skipped += 1
            else:
                created += 1
        except AppError as exc:
            errors.append(
                RowError(
                    row_index=row.row_index,
                    code=exc.message_key,
                    message=_map_error_message(exc.message_key),
                )
            )
        except Exception as exc:
            logger.error("catalog import row=%d xato: %r", row.row_index, exc)
            errors.append(
                RowError(
                    row_index=row.row_index,
                    code="import.row_error",
                    message="Satrni yozishda xato yuz berdi",
                )
            )

    return created, skipped, errors


async def _create_catalog_row(
    db: AsyncSession,
    row: ConfirmRow,
    actor: AppUser,
    enterprise_id: uuid.UUID | None,
    default_segment: PriceSegment | None,
    redis=None,
) -> str:
    """
    Bitta satrni katalogga yozadi.

    Returns:
        "created" yoki "skipped".
    """
    data = ProductCreate(
        name_uz=row.name,
        name_ru=row.name,  # import da faqat bitta nom — ikkisiga ham
        sku=row.sku or None,
        barcode=row.barcode or None,
        unit="dona",
        is_active=True,
        client_uuid=row.client_uuid,
    )

    # create_product idempotentlikni Redis orqali boshqaradi
    product = await catalog_service.create_product(
        db,
        data,
        actor_id=actor.id,
        redis=redis,
        enterprise_id=enterprise_id,
    )

    # Narx o'rnatish (segment bo'lsa)
    if default_segment is not None and row.price > 0:
        price_set = PriceSet(
            segment_id=default_segment.id,
            price=_to_decimal(row.price),
            currency=row.currency,
            valid_from=datetime.now(timezone.utc),
            client_uuid=row.client_uuid,
        )
        try:
            await catalog_service.set_price(
                db,
                product.id,
                price_set,
                actor_id=actor.id,
                user=actor,
                enterprise_id=enterprise_id,
            )
        except AppError as exc:
            # Narx xatosi — mahsulot yaratildi, faqat narx yo'q (warning emas, davom etamiz)
            logger.warning(
                "catalog import: narx o'rnatishda xato product_id=%s: %s",
                product.id, exc.message_key,
            )

    return "created"


async def _get_or_create_default_segment(
    db: AsyncSession,
    enterprise_id: uuid.UUID | None,
    actor_id: uuid.UUID,
) -> PriceSegment | None:
    """
    Korxona uchun default narx segmentini qaytaradi yoki yaratadi.

    Segment topilmasa → "Standart" segmenti yaratiladi.
    enterprise_id None bo'lsa → None qaytaradi.
    """
    if enterprise_id is None:
        return None

    stmt = (
        select(PriceSegment)
        .where(PriceSegment.deleted_at.is_(None))
        .order_by(PriceSegment.created_at)
        .limit(1)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, PriceSegment.enterprise_id)
    result = await db.execute(stmt)
    seg = result.scalar_one_or_none()

    if seg is not None:
        return seg

    # Yangi "Standart" segment yaratish
    from app.modules.catalog.schemas import PriceSegmentCreate
    try:
        seg = await catalog_service.create_segment(
            db,
            PriceSegmentCreate(name="Standart"),
            enterprise_id=enterprise_id,
        )
        logger.info("import: 'Standart' narx segmenti yaratildi enterprise=%s", enterprise_id)
        return seg
    except AppError:
        # Parallel yaratish — mavjud segment topiladi
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# ─── StoreInventory import ─────────────────────────────────────────────────────


async def _confirm_store_inventory(
    db: AsyncSession,
    rows: list[ConfirmRow],
    enterprise_id: uuid.UUID | None,
    store_id: uuid.UUID,
    redis=None,
) -> tuple[int, int, list[RowError], list[uuid.UUID]]:
    """
    Satrlarni StoreInventory ga yozadi.

    Idempotentlik qatlamlari (#16):
      1. In-batch set (bitta so'rov ichida takror client_uuid).
      2. Redis GET — tez-yo'l optimizatsiyasi (SETNX EMAS — kalit faqat
         commit muvaffaqiyatli bo'lgandan keyin qo'yiladi, confirm_import da).
      3. DB SELECT (client_uuid bo'yicha) — asosiy tekshiruv.
      4. DB UNIQUE + SAVEPOINT — race-guard backstop (#15 pattern).

    Returns:
        (created, skipped, errors, created_uuids) — created_uuids commit'dan
        keyin Redis kalit o'rnatish uchun ishlatiladi.
    """
    created = 0
    skipped = 0
    errors: list[RowError] = []
    created_uuids: list[uuid.UUID] = []

    # In-batch idempotentlik seti (client_uuid → True)
    seen_uuids: set[uuid.UUID] = set()

    for row in rows:
        try:
            # In-batch dedup
            if row.client_uuid in seen_uuids:
                skipped += 1
                continue
            seen_uuids.add(row.client_uuid)

            # Redis tez-yo'l optimizatsiyasi (GET — backstop emas)
            if redis is not None:
                idem_key = f"{_IDEM_STORE_INV_PREFIX}:{row.client_uuid}"
                try:
                    if await redis.get(idem_key) is not None:
                        skipped += 1
                        continue
                except Exception as exc:
                    logger.warning("store_inv import: Redis dedup xato: %r", exc)

            # DB-darajali idempotentlik (asosiy tekshiruv)
            existing_stmt = select(StoreInventory.id).where(
                StoreInventory.client_uuid == row.client_uuid
            )
            existing_result = await db.execute(existing_stmt)
            if existing_result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            # Mahsulotni topish (sku/barcode bo'yicha) yoki yaratish
            product = await _find_or_create_product_for_store(
                db, row, enterprise_id
            )

            cost_price = _to_decimal(row.price)
            markup = Decimal("0")
            sale_price = cost_price * (1 + markup / 100)

            inv = StoreInventory(
                enterprise_id=enterprise_id,
                store_id=store_id,
                product_id=product.id,
                qty=_to_decimal(row.qty),
                cost_price=cost_price,
                markup_percent=markup,
                sale_price=sale_price,
                expiry_date=row.expiry_date,
                status="active",
                source_order_id=None,
                source_delivery_id=None,
                client_uuid=row.client_uuid,
            )

            # SAVEPOINT (#15): db.add() dan OLDIN ochiladi — aks holda
            # begin_nested() ichki avtoflush-snapshot mexanizmi pending
            # `inv`ni allaqachon flush qilib, IntegrityError'ni try/except'dan
            # TASHQARIDA chiqarib yuborishi mumkin edi. DB UNIQUE (client_uuid)
            # race-guard — parallel so'rov bir xil satrni bir vaqtda yozsa
            # faqat shu qator bekor qilinadi, ROOT tranzaksiya buzilmaydi.
            #
            # MUHIM: muvaffaqiyat holatida sp.commit() ATAYLAB chaqirilmaydi —
            # SAVEPOINT ochiq qoldiriladi (empirik tekshirilgan: release
            # qilingan SAVEPOINT keyinroq shu BATCH ichida (masalan
            # confirm_import'ning yakuniy db.commit()'i yiqilib db.rollback()
            # chaqirilganda) noto'g'ri "omon qolishi" mumkin edi — orders/
            # service.py create_order() dagi batafsil izohga qarang).
            sp = await db.begin_nested()
            db.add(inv)
            try:
                await db.flush()
            except IntegrityError:
                await sp.rollback()
                skipped += 1
                continue

            created += 1
            created_uuids.append(row.client_uuid)

        except AppError as exc:
            errors.append(
                RowError(
                    row_index=row.row_index,
                    code=exc.message_key,
                    message=_map_error_message(exc.message_key),
                )
            )
        except Exception as exc:
            logger.error("store_inv import row=%d xato: %r", row.row_index, exc)
            errors.append(
                RowError(
                    row_index=row.row_index,
                    code="import.row_error",
                    message="Satrni yozishda xato yuz berdi",
                )
            )

    return created, skipped, errors, created_uuids


async def _find_or_create_product_for_store(
    db: AsyncSession,
    row: ConfirmRow,
    enterprise_id: uuid.UUID | None,
) -> Product:
    """
    Sku/barcode bo'yicha mahsulotni topadi, topilmasa yaratadi.

    Do'kon import uchun — mavjud katalog mahsulotiga bog'lash.
    """
    from sqlalchemy import or_

    # Avval sku/barcode bo'yicha qidirish
    if row.sku or row.barcode:
        conditions = []
        if row.sku:
            conditions.append(Product.sku == row.sku)
        if row.barcode:
            conditions.append(Product.barcode == row.barcode)

        # #33: bir nechta mos yozuv (sku VA barcode alohida mos kelishi
        # mumkin — MultipleResultsFound xavfi) — .limit(1) + .scalars().first()
        # deterministik birinchi natijani qaytaradi (scalar_one_or_none()
        # ko'p natija bo'lsa 500 bilan qulaydi).
        stmt = select(Product).where(
            or_(*conditions), Product.deleted_at.is_(None)
        ).limit(1)
        stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
        result = await db.execute(stmt)
        product = result.scalars().first()
        if product is not None:
            return product

    # Nom bo'yicha qidirish (taxminiy — birinchi mos)
    if row.name:
        # #33: ILIKE ko'p natija qaytarishi mumkin — .limit(1) + .scalars().first().
        stmt = select(Product).where(
            Product.name_uz.ilike(f"%{row.name}%"),
            Product.deleted_at.is_(None),
        ).limit(1)
        stmt = apply_enterprise_filter(stmt, enterprise_id, Product.enterprise_id)
        result = await db.execute(stmt)
        product = result.scalars().first()
        if product is not None:
            return product

    # Topilmadi — yangi mahsulot yaratamiz (do'kon uchun minimal katalog entry)
    product = Product(
        name_uz=row.name,
        name_ru=row.name,
        sku=row.sku,
        barcode=row.barcode,
        unit="dona",
        is_active=True,
        enterprise_id=enterprise_id,
    )
    db.add(product)
    await db.flush()
    return product


# ─── Yordamchi ────────────────────────────────────────────────────────────────


async def _get_store_id(db: AsyncSession, user: AppUser) -> uuid.UUID | None:
    """Store roli uchun foydalanuvchiga tegishli do'kon ID sini qaytaradi.

    #33: bitta foydalanuvchi bir nechta do'konga user_id orqali bog'langan
    (yoki o'chirilgan do'kon qolgan) holatda scalar_one_or_none() ko'p
    natija bilan MultipleResultsFound (500) beradi. Deterministik: faqat
    aktiv (deleted_at IS NULL) do'konlar, eng eskisi (created_at) birinchi,
    .limit(1) + .scalars().first().
    """
    stmt = (
        select(Store.id)
        .where(Store.user_id == user.id, Store.deleted_at.is_(None))
        .order_by(Store.created_at)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


def _to_decimal(val: float) -> Decimal:
    """float → Decimal (xavfsiz)."""
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0")


def _map_error_message(key: str) -> str:
    """Xato kalitini o'zbekcha xabarga aylantiradi."""
    _MESSAGES: dict[str, str] = {
        "catalog.duplicate_sku": "Bu SKU allaqachon mavjud",
        "catalog.duplicate_barcode": "Bu barcode allaqachon mavjud",
        "catalog.segment_not_found": "Narx segmenti topilmadi",
        "import.store_not_found": "Do'kon topilmadi",
        "import.row_error": "Satrni yozishda xato",
        "rbac.permission_denied": "Ruxsat yo'q",
    }
    return _MESSAGES.get(key, key)
