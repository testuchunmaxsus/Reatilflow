"""
Superadmin servis qatlami — MT4.

Funksiyalar:
  create_enterprise_with_admin  — korxona + birinchi admin yaratish
  list_enterprises              — barcha korxonalar (paginated, search/filter)
  get_enterprise                — bitta korxona
  get_enterprise_detail         — korxona + user_count + admins
  update_enterprise             — name/enabled_modules/status yangilash
  suspend_enterprise            — status='suspended'
  activate_enterprise           — status='active'
  delete_enterprise             — soft-delete (deleted_at=now, status='suspended')
  get_platform_stats            — platforma statistikasi (cross-tenant)
  reset_admin_password          — foydalanuvchi parolini tiklash
  list_superadmin_users         — cross-tenant foydalanuvchilar ro'yxati

Qoidalar:
  - superadmin enterprise_id=NULL.
  - Birinchi admin yangi korxona enterprise_id'siga ega.
  - Parol hech qachon javobda/logda.
  - Optimistik lock (version) PATCH da tekshiriladi.
"""

from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.jwt import hash_password
from app.models.enterprise import ALL_MODULE_KEYS, DEFAULT_ENTERPRISE_UUID, Enterprise
from app.models.user import AppUser
from app.modules.superadmin.schemas import (
    EnterpriseCreate,
    EnterpriseUpdate,
    StatsOut,
)
from app.modules.users.schemas import UserCreate
from app.modules.users.service import create_user

logger = logging.getLogger(__name__)

_DEFAULT_ENT_UUID = uuid.UUID(DEFAULT_ENTERPRISE_UUID)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Yordamchilar ─────────────────────────────────────────────────────────────


def _validate_modules(modules: list[str]) -> list[str]:
    """
    enabled_modules ro'yxatini tekshiradi va tozalaydi.

    Noma'lum modul kalitlari olib tashlanadi (xato o'rniga — kelajak mos kelish).
    Hech qachon None qaytarmaydi — bo'sh ro'yxat ruxsat etilmaydi emas, hamma yoki ba'zi modul.
    """
    valid = set(ALL_MODULE_KEYS)
    cleaned = [m for m in modules if m in valid]
    return cleaned


def _generate_strong_password(length: int = 14) -> str:
    """
    Kuchli parol generatsiya qiladi (secrets moduli bilan).

    Tarkibi: katta/kichik harflar + raqamlar + maxsus belgilar.
    Minimal talablar: har guruhdan kamida 1 ta belgi.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        # Kamida bir katta harf, kichik harf, raqam va maxsus belgi bo'lsin
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*" for c in password)
        if has_upper and has_lower and has_digit and has_special:
            return password


# ─── Korxona olish ────────────────────────────────────────────────────────────


async def get_enterprise(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> Enterprise:
    """
    ID bo'yicha korxona oladi.

    Raises:
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
    """
    stmt = select(Enterprise).where(
        Enterprise.id == enterprise_id,
        Enterprise.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    enterprise = result.scalar_one_or_none()
    if enterprise is None:
        raise AppError("superadmin.enterprise_not_found", status_code=404)
    return enterprise


# ─── Korxona + birinchi admin yaratish ───────────────────────────────────────


async def create_enterprise_with_admin(
    db: AsyncSession,
    data: EnterpriseCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
) -> tuple[Enterprise, AppUser]:
    """
    Korxona va birinchi administratorni birgalikda yaratadi.

    Bosqichlar:
      1. enabled_modules tekshirish + tozalash.
      2. Enterprise obyekti yaratish va flush.
      3. UserCreate sxemasi orqali create_user() chaqirish (enterprise_id bilan).

    Raises:
        AppError("users.duplicate_phone", 409): telefon allaqachon band.
    """
    modules = _validate_modules(data.enabled_modules)

    # Korxona yaratish
    enterprise = Enterprise(
        name=data.name,
        inn=data.inn,
        status="active",
        enabled_modules=modules,
    )
    db.add(enterprise)
    await db.flush()  # ID olish uchun

    logger.info(
        "superadmin.enterprise_created id=%s name=%s actor=%s",
        str(enterprise.id),
        enterprise.name,
        str(actor_id) if actor_id else "system",
    )

    # Birinchi admin yaratish — users.service.create_user qayta ishlatiladi
    admin_data = UserCreate(
        full_name=data.first_admin.full_name,
        phone=data.first_admin.phone,
        role="administrator",
        locale=data.first_admin.locale,
        password=data.first_admin.password,
        biometric_enrolled=False,
        device_id=None,
        client_uuid=None,
        branch_id=None,
    )

    admin = await create_user(
        db=db,
        data=admin_data,
        actor_id=actor_id,
        redis=redis,
        enterprise_id=enterprise.id,
    )

    logger.info(
        "superadmin.first_admin_created user_id=%s enterprise_id=%s",
        str(admin.id),
        str(enterprise.id),
    )

    return enterprise, admin


# ─── Korxonalar ro'yxati ──────────────────────────────────────────────────────


async def list_enterprises(
    db: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    status: str | None = None,
) -> tuple[list[Enterprise], int]:
    """
    Barcha aktiv korxonalar (soft-delete filtrlangan), paginated.

    Ixtiyoriy filterlar:
      search — name YOKI inn bo'yicha case-insensitive qidiruv (LIKE).
      status — 'active' | 'suspended'.

    Returns:
        (items, total)
    """
    base = select(Enterprise).where(Enterprise.deleted_at.is_(None))

    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(
                Enterprise.name.ilike(pattern),
                Enterprise.inn.ilike(pattern),
            )
        )

    if status is not None:
        base = base.where(Enterprise.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    list_stmt = (
        base.order_by(Enterprise.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(list_stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Korxona yangilash ────────────────────────────────────────────────────────


async def update_enterprise(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
    data: EnterpriseUpdate,
) -> Enterprise:
    """
    Korxonani yangilaydi (PATCH — faqat berilgan maydonlar).

    Optimistik lock: data.version mos kelmasa → version_conflict.

    Raises:
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
        AppError("superadmin.version_conflict", 409): versiya mos kelmasa.
        AppError("superadmin.invalid_status", 422): noto'g'ri status.
    """
    enterprise = await get_enterprise(db, enterprise_id)

    if enterprise.version != data.version:
        raise AppError("superadmin.version_conflict", status_code=409)

    if data.name is not None:
        enterprise.name = data.name

    if data.enabled_modules is not None:
        enterprise.enabled_modules = _validate_modules(data.enabled_modules)

    if data.status is not None:
        if data.status not in ("active", "suspended"):
            raise AppError("superadmin.invalid_status", status_code=422)
        enterprise.status = data.status

    enterprise.version = enterprise.version + 1
    enterprise.updated_at = _now()

    await db.flush()

    logger.info(
        "superadmin.enterprise_updated id=%s",
        str(enterprise.id),
    )

    return enterprise


# ─── Suspend / Activate ───────────────────────────────────────────────────────


async def suspend_enterprise(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> Enterprise:
    """
    Korxonani to'xtatib qo'yadi (status='suspended').

    Raises:
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
    """
    enterprise = await get_enterprise(db, enterprise_id)
    enterprise.status = "suspended"
    enterprise.version = enterprise.version + 1
    enterprise.updated_at = _now()
    await db.flush()

    logger.info("superadmin.enterprise_suspended id=%s", str(enterprise.id))
    return enterprise


async def activate_enterprise(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> Enterprise:
    """
    Korxonani qayta faollashtiradi (status='active').

    Raises:
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
    """
    enterprise = await get_enterprise(db, enterprise_id)
    enterprise.status = "active"
    enterprise.version = enterprise.version + 1
    enterprise.updated_at = _now()
    await db.flush()

    logger.info("superadmin.enterprise_activated id=%s", str(enterprise.id))
    return enterprise


# ─── Soft-delete ──────────────────────────────────────────────────────────────


async def delete_enterprise(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> None:
    """
    Korxonani soft-delete qiladi: deleted_at=now(), status='suspended'.

    Default korxona (00000000-0000-7000-8000-000000000001) o'chirilmaydi.

    Raises:
        AppError("superadmin.cannot_delete_default", 422): default korxona.
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
    """
    if enterprise_id == _DEFAULT_ENT_UUID:
        raise AppError("superadmin.cannot_delete_default", status_code=422)

    enterprise = await get_enterprise(db, enterprise_id)
    enterprise.deleted_at = _now()
    enterprise.status = "suspended"
    enterprise.updated_at = _now()
    await db.flush()

    logger.info("superadmin.enterprise_deleted id=%s", str(enterprise.id))


# ─── Platforma statistikasi ───────────────────────────────────────────────────


async def get_platform_stats(db: AsyncSession) -> StatsOut:
    """
    Platforma bo'yicha umumiy statistika (cross-tenant).

    Returns:
        StatsOut — enterprises_total, enterprises_active, enterprises_suspended,
                   users_total, enterprises_new_7d.
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Korxonalar soni (deleted emas)
    ent_total_stmt = select(func.count()).select_from(Enterprise).where(
        Enterprise.deleted_at.is_(None)
    )
    ent_total = (await db.execute(ent_total_stmt)).scalar_one()

    # Aktiv korxonalar
    ent_active_stmt = select(func.count()).select_from(Enterprise).where(
        Enterprise.deleted_at.is_(None),
        Enterprise.status == "active",
    )
    ent_active = (await db.execute(ent_active_stmt)).scalar_one()

    # Suspended korxonalar
    ent_suspended_stmt = select(func.count()).select_from(Enterprise).where(
        Enterprise.deleted_at.is_(None),
        Enterprise.status == "suspended",
    )
    ent_suspended = (await db.execute(ent_suspended_stmt)).scalar_one()

    # Tenant foydalanuvchilari (enterprise_id IS NOT NULL — superadminlar yo'q)
    users_total_stmt = select(func.count()).select_from(AppUser).where(
        AppUser.enterprise_id.is_not(None)
    )
    users_total = (await db.execute(users_total_stmt)).scalar_one()

    # Yangi korxonalar (oxirgi 7 kun)
    ent_new_7d_stmt = select(func.count()).select_from(Enterprise).where(
        Enterprise.deleted_at.is_(None),
        Enterprise.created_at >= seven_days_ago,
    )
    ent_new_7d = (await db.execute(ent_new_7d_stmt)).scalar_one()

    return StatsOut(
        enterprises_total=ent_total,
        enterprises_active=ent_active,
        enterprises_suspended=ent_suspended,
        users_total=users_total,
        enterprises_new_7d=ent_new_7d,
    )


# ─── Korxona detail (user_count + admins) ────────────────────────────────────


async def get_enterprise_detail(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
) -> tuple[Enterprise, int, list[AppUser]]:
    """
    Korxona detail: korxona obyekti + user_count + administrators ro'yxati.

    Returns:
        (enterprise, user_count, admins)

    Raises:
        AppError("superadmin.enterprise_not_found", 404): topilmasa.
    """
    enterprise = await get_enterprise(db, enterprise_id)

    # user_count — bu korxonadagi barcha foydalanuvchilar
    user_count_stmt = select(func.count()).select_from(AppUser).where(
        AppUser.enterprise_id == enterprise_id
    )
    user_count = (await db.execute(user_count_stmt)).scalar_one()

    # admins — role='administrator' foydalanuvchilar
    admins_stmt = (
        select(AppUser)
        .where(
            AppUser.enterprise_id == enterprise_id,
            AppUser.role == "administrator",
        )
        .order_by(AppUser.created_at)
    )
    admins_result = await db.execute(admins_stmt)
    admins = list(admins_result.scalars().all())

    return enterprise, user_count, admins


# ─── Admin parolini tiklash ───────────────────────────────────────────────────


async def reset_admin_password(
    db: AsyncSession,
    enterprise_id: uuid.UUID,
    user_id: uuid.UUID,
    new_password: str | None,
) -> tuple[uuid.UUID, str]:
    """
    Foydalanuvchi parolini tiklaydi.

    new_password None bo'lsa — kuchli parol generatsiya qilinadi.
    user_id shu enterprise_id ga tegishli bo'lishi shart.

    Returns:
        (user_id, plain_password)

    Raises:
        AppError("superadmin.user_not_found", 404): topilmasa yoki boshqa korxona.
    """
    # Avval korxona mavjudligini tekshirish
    await get_enterprise(db, enterprise_id)

    # Foydalanuvchini topish — enterprise_id mos bo'lishi shart
    user_stmt = select(AppUser).where(
        AppUser.id == user_id,
        AppUser.enterprise_id == enterprise_id,
    )
    result = await db.execute(user_stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError("superadmin.user_not_found", status_code=404)

    # Parol: null bo'lsa generatsiya qil
    plain_password = new_password if new_password is not None else _generate_strong_password()

    user.password_hash = hash_password(plain_password)
    user.updated_at = _now()
    await db.flush()

    logger.info(
        "superadmin.admin_password_reset user_id=%s enterprise_id=%s",
        str(user_id),
        str(enterprise_id),
    )

    return user_id, plain_password


# ─── Cross-tenant foydalanuvchilar ───────────────────────────────────────────


async def list_superadmin_users(
    db: AsyncSession,
    *,
    enterprise_id: uuid.UUID | None = None,
    role: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[AppUser, str | None]], int]:
    """
    Cross-tenant foydalanuvchilar ro'yxati (superadmin uchun).

    Filterlar:
      enterprise_id — ixtiyoriy korxona filtri.
      role          — ixtiyoriy rol filtri.

    Returns:
        ([(user, enterprise_name), ...], total)
    """
    from sqlalchemy.orm import aliased

    EnterpriseAlias = aliased(Enterprise)

    # Bazaviy where shartlar (filter)
    conditions = [AppUser.enterprise_id.is_not(None)]
    if enterprise_id is not None:
        conditions.append(AppUser.enterprise_id == enterprise_id)
    if role is not None:
        conditions.append(AppUser.role == role)

    # Count
    count_stmt = select(func.count()).select_from(AppUser).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    # Items — enterprise nomi join orqali
    list_stmt = (
        select(AppUser, EnterpriseAlias.name.label("enterprise_name"))
        .outerjoin(EnterpriseAlias, AppUser.enterprise_id == EnterpriseAlias.id)
        .where(*conditions)
        .order_by(AppUser.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).all()

    items = [(row[0], row[1]) for row in rows]
    return items, total
