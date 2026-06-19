"""
Demo ma'lumotlar (seed) skripti — RETAIL tizimi.

Foydalanish:
    cd backend
    python -m scripts.seed

Idempotent: qayta ishga tushirilsa dublikat yaratmaydi.
  - Har bir yozuv "mavjudmi?" tekshiruvi orqali o'tkaziladi.
  - Mavjud bo'lsa: o'tkazib yuboriladi.
  - Yo'q bo'lsa: yaratiladi.

Parol manbai:
    SEED_ADMIN_PASSWORD  — muhit o'zgaruvchisi (tavsiya etiladi).
    Agar o'rnatilmagan bo'lsa — DEV_DEFAULT parol ishlatiladi va
    konsol'da aniq ogohlantirish chiqariladi.
    HECH QACHON production da default parol bilan ishlatmang.

Yaratiladi:
    - 1 ta administrator (branch=None)
    - 2 ta filial (branch UUID-lari sabit, idempotentlik uchun)
    - 4 ta kategoriya (2 ildiz, 2 farzand)
    - 2 ta narx segmenti (chakana, ulgurji)
    - 8 ta mahsulot (MXIK + barcode bilan)
    - 3 ta do'kon (har biriga segment)
    - 1 ta agent + agent-do'kon biriktirishlari (2 do'kon)
    - 1 ta kuryer
    - 1 ta buxgalter
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

# backend/ papkasidan import qilish uchun path ni sozlash
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.core.db import AsyncSessionPrimary
from app.core.jwt import hash_password
from app.models.catalog import Category, PriceSegment, Product, ProductPrice
from app.models.store import AgentStore, Store
from app.models.user import AppUser

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("seed")

# ─── Sabit UUIDlar (idempotentlik uchun) ─────────────────────────────────────
# Bu UUIDlar o'zgartirilmaydi — qayta ishga tushirilganda bir xil yozuvlar.

_BRANCH_1_ID = uuid.UUID("10000000-0000-7000-8000-000000000001")
_BRANCH_2_ID = uuid.UUID("10000000-0000-7000-8000-000000000002")

_ADMIN_PHONE  = "+998901000001"
_AGENT_PHONE  = "+998901000002"
_COURIER_PHONE = "+998901000003"
_ACCOUNTANT_PHONE = "+998901000004"

_CAT_FOOD_ID     = uuid.UUID("20000000-0000-7000-8000-000000000001")
_CAT_DRINK_ID    = uuid.UUID("20000000-0000-7000-8000-000000000002")
_CAT_DAIRY_ID    = uuid.UUID("20000000-0000-7000-8000-000000000003")
_CAT_JUICE_ID    = uuid.UUID("20000000-0000-7000-8000-000000000004")

_SEG_RETAIL_ID   = uuid.UUID("30000000-0000-7000-8000-000000000001")
_SEG_WHOLESALE_ID = uuid.UUID("30000000-0000-7000-8000-000000000002")

_STORE_1_ID = uuid.UUID("40000000-0000-7000-8000-000000000001")
_STORE_2_ID = uuid.UUID("40000000-0000-7000-8000-000000000002")
_STORE_3_ID = uuid.UUID("40000000-0000-7000-8000-000000000003")

# ─── Parol mantig'i ────────────────────────────────────────────────────────────

_DEV_DEFAULT_PASSWORD = "dev_seed_pass_2026"
_DEV_DEFAULT_WARNING  = (
    "\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
    "OGOHLANTIRISH: SEED_ADMIN_PASSWORD muhit o'zgaruvchisi\n"
    "o'rnatilmagan. DEV-ONLY standart parol ishlatilmoqda.\n"
    "BU PAROLNI PRODUCTION DA HECH QACHON ISHLATING!\n"
    "  export SEED_ADMIN_PASSWORD='<kuchli_parol>'\n"
    "  export SEED_AGENT_PASSWORD='<kuchli_parol>'\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
)


def _get_password(env_var: str, label: str) -> str:
    """Muhit o'zgaruvchisidan parolni oladi yoki dev-default ishlatadi."""
    val = os.environ.get(env_var, "").strip()
    if val:
        return val
    logger.warning(
        "%s uchun %s o'rnatilmagan — dev-default parol ishlatilmoqda.", label, env_var
    )
    return _DEV_DEFAULT_PASSWORD


# ─── Idempotent yordamchilar ───────────────────────────────────────────────────


async def _get_or_create_user(
    db: AsyncSession,
    phone: str,
    full_name: str,
    role: str,
    password: str,
    branch_id: uuid.UUID | None = None,
) -> tuple[AppUser, bool]:
    """
    Telefon raqami bo'yicha foydalanuvchini topadi yoki yaratadi.

    Returns:
        (user, created): created=True yangi yaratilgan bo'lsa.
    """
    bi = blind_index(phone)
    stmt = select(AppUser).where(AppUser.phone_bi == bi)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    user = AppUser(
        full_name=full_name,
        phone=phone,
        role=role,
        branch_id=branch_id,
        locale="uz",
        password_hash=hash_password(password),
        biometric_enrolled=False,
        is_active=True,
    )
    # phone_bi event listener (before_insert) orqali avtomatik to'ldiriladi
    db.add(user)
    await db.flush()
    return user, True


async def _get_or_create_category(
    db: AsyncSession,
    cat_id: uuid.UUID,
    name_uz: str,
    name_ru: str,
    parent_id: uuid.UUID | None = None,
) -> tuple[Category, bool]:
    """ID bo'yicha kategoriya topadi yoki yaratadi."""
    result = await db.execute(select(Category).where(Category.id == cat_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    cat = Category(
        id=cat_id,
        name_uz=name_uz,
        name_ru=name_ru,
        parent_id=parent_id,
        is_active=True,
    )
    db.add(cat)
    await db.flush()
    return cat, True


async def _get_or_create_price_segment(
    db: AsyncSession,
    seg_id: uuid.UUID,
    name: str,
) -> tuple[PriceSegment, bool]:
    """ID bo'yicha narx segmentini topadi yoki yaratadi."""
    result = await db.execute(select(PriceSegment).where(PriceSegment.id == seg_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    seg = PriceSegment(id=seg_id, name=name)
    db.add(seg)
    await db.flush()
    return seg, True


async def _get_or_create_product(
    db: AsyncSession,
    sku: str,
    name_uz: str,
    name_ru: str,
    barcode: str | None,
    mxik_code: str | None,
    unit: str,
    category_id: uuid.UUID | None,
) -> tuple[Product, bool]:
    """SKU bo'yicha mahsulotni topadi yoki yaratadi."""
    result = await db.execute(select(Product).where(Product.sku == sku))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    prod = Product(
        name_uz=name_uz,
        name_ru=name_ru,
        sku=sku,
        barcode=barcode,
        mxik_code=mxik_code,
        unit=unit,
        category_id=category_id,
        is_active=True,
    )
    db.add(prod)
    await db.flush()
    return prod, True


async def _get_or_create_product_price(
    db: AsyncSession,
    product_id: uuid.UUID,
    segment_id: uuid.UUID,
    price: Decimal,
    valid_from: datetime,
) -> bool:
    """product_id + segment_id + valid_from bo'yicha narx topadi yoki yaratadi."""
    from sqlalchemy import and_
    from app.models.catalog import ProductPrice

    stmt = select(ProductPrice).where(
        and_(
            ProductPrice.product_id == product_id,
            ProductPrice.segment_id == segment_id,
            ProductPrice.valid_from == valid_from,
        )
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        return False

    pp = ProductPrice(
        product_id=product_id,
        segment_id=segment_id,
        price=price,
        currency="UZS",
        valid_from=valid_from,
        valid_to=None,
    )
    db.add(pp)
    await db.flush()
    return True


async def _get_or_create_store(
    db: AsyncSession,
    store_id: uuid.UUID,
    name: str,
    address: str,
    segment_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    agent_id: uuid.UUID | None,
    gps_lat: Decimal | None = None,
    gps_lng: Decimal | None = None,
) -> tuple[Store, bool]:
    """ID bo'yicha do'konni topadi yoki yaratadi."""
    result = await db.execute(select(Store).where(Store.id == store_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    store = Store(
        id=store_id,
        name=name,
        address=address,
        segment_id=segment_id,
        branch_id=branch_id,
        agent_id=agent_id,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
    )
    db.add(store)
    await db.flush()
    return store, True


async def _get_or_create_agent_store(
    db: AsyncSession,
    agent_id: uuid.UUID,
    store_id: uuid.UUID,
) -> bool:
    """agent_id + store_id juftligini topadi yoki yaratadi."""
    from sqlalchemy import and_

    stmt = select(AgentStore).where(
        and_(AgentStore.agent_id == agent_id, AgentStore.store_id == store_id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        return False

    link = AgentStore(agent_id=agent_id, store_id=store_id)
    db.add(link)
    await db.flush()
    return True


# ─── Asosiy seed mantig'i ─────────────────────────────────────────────────────


async def seed(db: AsyncSession) -> None:
    """
    Barcha demo yozuvlarni idempotent tarzda yaratadi.

    Har qadamda "mavjudmi?" tekshiruvi qilinadi — dublikat yaratilmaydi.
    """
    # Parol o'zgaruvchilari o'rnatilmagan bo'lsa — ogohlantirish
    if not os.environ.get("SEED_ADMIN_PASSWORD", "").strip():
        logger.warning(_DEV_DEFAULT_WARNING)

    admin_password = _get_password("SEED_ADMIN_PASSWORD", "administrator")
    user_password  = _get_password("SEED_USER_PASSWORD", "agent/kuryer/buxgalter")

    _now = datetime.now(timezone.utc)

    # ── 1. Administrator ──────────────────────────────────────────────────────
    admin, created = await _get_or_create_user(
        db,
        phone=_ADMIN_PHONE,
        full_name="Super Administrator",
        role="administrator",
        password=admin_password,
    )
    logger.info("administrator: %s (%s)", _ADMIN_PHONE, "YANGI" if created else "mavjud")

    # ── 2. Kategoriyalar ──────────────────────────────────────────────────────
    cat_food, c = await _get_or_create_category(db, _CAT_FOOD_ID, "Oziq-ovqat", "Продукты")
    logger.info("kategoriya 'Oziq-ovqat': %s", "YANGI" if c else "mavjud")

    cat_drink, c = await _get_or_create_category(db, _CAT_DRINK_ID, "Ichimliklar", "Напитки")
    logger.info("kategoriya 'Ichimliklar': %s", "YANGI" if c else "mavjud")

    cat_dairy, c = await _get_or_create_category(
        db, _CAT_DAIRY_ID, "Sut mahsulotlari", "Молочные продукты",
        parent_id=_CAT_FOOD_ID,
    )
    logger.info("kategoriya 'Sut mahsulotlari': %s", "YANGI" if c else "mavjud")

    cat_juice, c = await _get_or_create_category(
        db, _CAT_JUICE_ID, "Sharbatlar", "Соки",
        parent_id=_CAT_DRINK_ID,
    )
    logger.info("kategoriya 'Sharbatlar': %s", "YANGI" if c else "mavjud")

    # ── 3. Narx segmentlari ───────────────────────────────────────────────────
    seg_retail, c = await _get_or_create_price_segment(db, _SEG_RETAIL_ID, "chakana")
    logger.info("narx segment 'chakana': %s", "YANGI" if c else "mavjud")

    seg_wholesale, c = await _get_or_create_price_segment(db, _SEG_WHOLESALE_ID, "ulgurji")
    logger.info("narx segment 'ulgurji': %s", "YANGI" if c else "mavjud")

    # ── 4. Mahsulotlar ────────────────────────────────────────────────────────
    products_data = [
        # (sku, name_uz, name_ru, barcode, mxik_code, unit, category_id)
        ("MILK-1L",    "Sut 1 litr",          "Молоко 1 л",        "4890001000010", "10001001", "litr",  _CAT_DAIRY_ID),
        ("KEFIR-1L",   "Kefir 1 litr",         "Кефир 1 л",         "4890001000027", "10001002", "litr",  _CAT_DAIRY_ID),
        ("BUTTER-200G", "Sariyog' 200g",        "Масло сл. 200г",    "4890001000034", "10001003", "dona",  _CAT_DAIRY_ID),
        ("YOGURT-200G", "Yogurt 200g",          "Йогурт 200г",       "4890001000041", "10001004", "dona",  _CAT_DAIRY_ID),
        ("JUICE-APL-1L", "Olma sharbati 1L",   "Сок яблочный 1л",   "4890002000010", "10002001", "litr",  _CAT_JUICE_ID),
        ("JUICE-ORG-1L", "Apelsin sharbati 1L","Сок апельс. 1л",    "4890002000027", "10002002", "litr",  _CAT_JUICE_ID),
        ("WATER-05L",    "Suv 0.5L",           "Вода 0.5л",          "4890003000010", "10003001", "litr",  _CAT_DRINK_ID),
        ("WATER-15L",    "Suv 1.5L",           "Вода 1.5л",          "4890003000027", "10003002", "litr",  _CAT_DRINK_ID),
    ]

    created_products: list[Product] = []
    for sku, name_uz, name_ru, barcode, mxik_code, unit, cat_id in products_data:
        prod, c = await _get_or_create_product(
            db, sku, name_uz, name_ru, barcode, mxik_code, unit, cat_id
        )
        logger.info("mahsulot '%s': %s", sku, "YANGI" if c else "mavjud")
        created_products.append(prod)

    # ── 5. Mahsulot narxlari ──────────────────────────────────────────────────
    # Chakana narxlar
    retail_prices = {
        "MILK-1L":      Decimal("12500.00"),
        "KEFIR-1L":     Decimal("11000.00"),
        "BUTTER-200G":  Decimal("28000.00"),
        "YOGURT-200G":  Decimal("9500.00"),
        "JUICE-APL-1L": Decimal("18000.00"),
        "JUICE-ORG-1L": Decimal("19000.00"),
        "WATER-05L":    Decimal("3500.00"),
        "WATER-15L":    Decimal("7000.00"),
    }
    # Ulgurji narxlar (~15% chegirma)
    wholesale_prices = {
        "MILK-1L":      Decimal("10600.00"),
        "KEFIR-1L":     Decimal("9300.00"),
        "BUTTER-200G":  Decimal("23800.00"),
        "YOGURT-200G":  Decimal("8000.00"),
        "JUICE-APL-1L": Decimal("15300.00"),
        "JUICE-ORG-1L": Decimal("16100.00"),
        "WATER-05L":    Decimal("2900.00"),
        "WATER-15L":    Decimal("5900.00"),
    }

    for prod in created_products:
        sku = prod.sku or ""
        if sku in retail_prices:
            created = await _get_or_create_product_price(
                db, prod.id, _SEG_RETAIL_ID, retail_prices[sku], _now
            )
            if created:
                logger.info("narx '%s' chakana: YANGI", sku)

        if sku in wholesale_prices:
            created = await _get_or_create_product_price(
                db, prod.id, _SEG_WHOLESALE_ID, wholesale_prices[sku], _now
            )
            if created:
                logger.info("narx '%s' ulgurji: YANGI", sku)

    # ── 6. Agent (1-filialga biriktirilgan) ───────────────────────────────────
    agent, c = await _get_or_create_user(
        db,
        phone=_AGENT_PHONE,
        full_name="Demo Agent",
        role="agent",
        password=user_password,
        branch_id=_BRANCH_1_ID,
    )
    logger.info("agent: %s (%s)", _AGENT_PHONE, "YANGI" if c else "mavjud")

    # ── 7. Kuryer (2-filialga biriktirilgan) ──────────────────────────────────
    courier, c = await _get_or_create_user(
        db,
        phone=_COURIER_PHONE,
        full_name="Demo Kuryer",
        role="courier",
        password=user_password,
        branch_id=_BRANCH_2_ID,
    )
    logger.info("kuryer: %s (%s)", _COURIER_PHONE, "YANGI" if c else "mavjud")

    # ── 8. Buxgalter (1-filialga biriktirilgan) ───────────────────────────────
    accountant, c = await _get_or_create_user(
        db,
        phone=_ACCOUNTANT_PHONE,
        full_name="Demo Buxgalter",
        role="accountant",
        password=user_password,
        branch_id=_BRANCH_1_ID,
    )
    logger.info("buxgalter: %s (%s)", _ACCOUNTANT_PHONE, "YANGI" if c else "mavjud")

    # ── 9. Do'konlar ──────────────────────────────────────────────────────────
    store1, c = await _get_or_create_store(
        db,
        store_id=_STORE_1_ID,
        name="Baxt Do'koni",
        address="Toshkent sh., Chilonzor t., Bunyodkor ko'chasi 12",
        segment_id=_SEG_RETAIL_ID,
        branch_id=_BRANCH_1_ID,
        agent_id=agent.id,
        gps_lat=Decimal("41.2995"),
        gps_lng=Decimal("69.2401"),
    )
    logger.info("do'kon 'Baxt Do'koni': %s", "YANGI" if c else "mavjud")

    store2, c = await _get_or_create_store(
        db,
        store_id=_STORE_2_ID,
        name="Farovon Bozor",
        address="Toshkent sh., Mirzo Ulug'bek t., Amir Temur ko'chasi 55",
        segment_id=_SEG_RETAIL_ID,
        branch_id=_BRANCH_1_ID,
        agent_id=agent.id,
        gps_lat=Decimal("41.3123"),
        gps_lng=Decimal("69.2789"),
    )
    logger.info("do'kon 'Farovon Bozor': %s", "YANGI" if c else "mavjud")

    store3, c = await _get_or_create_store(
        db,
        store_id=_STORE_3_ID,
        name="Ulgurji Markaz",
        address="Toshkent viloyati, Kibray t., Sanoat ko'chasi 7",
        segment_id=_SEG_WHOLESALE_ID,
        branch_id=_BRANCH_2_ID,
        agent_id=None,
        gps_lat=Decimal("41.3456"),
        gps_lng=Decimal("69.3012"),
    )
    logger.info("do'kon 'Ulgurji Markaz': %s", "YANGI" if c else "mavjud")

    # ── 10. Agent ↔ Do'kon biriktirishlari ────────────────────────────────────
    c = await _get_or_create_agent_store(db, agent.id, store1.id)
    logger.info("agent_store (agent→store1): %s", "YANGI" if c else "mavjud")

    c = await _get_or_create_agent_store(db, agent.id, store2.id)
    logger.info("agent_store (agent→store2): %s", "YANGI" if c else "mavjud")

    logger.info(
        "\nSeed yakunlandi!\n"
        "  administrator : %s\n"
        "  agent         : %s\n"
        "  kuryer        : %s\n"
        "  buxgalter     : %s\n"
        "  do'konlar     : 3 ta\n"
        "  mahsulotlar   : %d ta\n"
        "  narx segmentlari: 2 ta (chakana, ulgurji)\n"
        "  kategoriyalar : 4 ta\n",
        _ADMIN_PHONE,
        _AGENT_PHONE,
        _COURIER_PHONE,
        _ACCOUNTANT_PHONE,
        len(products_data),
    )


# ─── Entry point ───────────────────────────────────────────────────────────────


async def main() -> None:
    """Seed skriptini ishga tushiradi."""
    logger.info("RETAIL seed skripti boshlanmoqda...")
    async with AsyncSessionPrimary() as session:
        try:
            await seed(session)
            await session.commit()
            logger.info("Commit: barcha o'zgarishlar saqlandi.")
        except Exception as exc:
            await session.rollback()
            logger.error("Xato: %r — rollback qilindi.", exc)
            raise


if __name__ == "__main__":
    asyncio.run(main())
