"""
Superadmin servis qatlami — MT4.

Funksiyalar:
  create_enterprise_with_admin  — korxona + birinchi admin yaratish
  list_enterprises              — barcha korxonalar (paginated)
  get_enterprise                — bitta korxona
  update_enterprise             — name/enabled_modules/status yangilash
  suspend_enterprise            — status='suspended'
  activate_enterprise           — status='active'

Qoidalar:
  - superadmin enterprise_id=NULL.
  - Birinchi admin yangi korxona enterprise_id'siga ega.
  - Parol hech qachon javobda/logda.
  - Optimistik lock (version) PATCH da tekshiriladi.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.modules.superadmin.schemas import EnterpriseCreate, EnterpriseUpdate
from app.modules.users.schemas import UserCreate
from app.modules.users.service import create_user

logger = logging.getLogger(__name__)


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
) -> tuple[list[Enterprise], int]:
    """
    Barcha aktiv korxonalar (soft-delete filtrlangan), paginated.

    Returns:
        (items, total)
    """
    base = select(Enterprise).where(Enterprise.deleted_at.is_(None))

    count_stmt = select(func.count()).select_from(
        base.subquery()
    )
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
