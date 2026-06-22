"""
Users servis qatlami — foydalanuvchilar biznes mantiq.

Funksiyalar:
  create_user(db, data, actor_id, redis) → AppUser
  get_user(db, user_id) → AppUser
  list_users(db, filters...) → (list[AppUser], total)
  update_user(db, user_id, data, actor_id) → AppUser
  deactivate_user(db, user_id, actor_id, current_user) → AppUser

Qoidalar:
  - PII (phone, full_name) EncryptedString orqali shifrlangan saqlanadi.
  - phone qidiruv faqat blind_index() orqali (ochiq-matn LIKE taqiqlangan).
  - phone_bi partial unique: dublikat telefon → 409.
  - version optimistik lock.
  - client_uuid Redis idempotentlik.
  - Har mutatsiyada audit_log + outbox_event yoziladi (PII mask_pii() bilan).
  - Admin o'zini deaktiv qila olmaydi.
  - password_hash hech qachon loglanmaydi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.core.errors import AppError
from app.core.jwt import hash_password
from app.core.security import mask_pii
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.outbox import OutboxEvent
from app.models.user import AppUser
from app.modules.rbac.enterprise_scope import apply_enterprise_filter
from app.modules.users.schemas import VALID_ROLES, UserCreate, UserUpdate

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:users:create"


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi. PII mask_pii() orqali maskalanadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="app_user",
        entity_id=entity_id,
        before_json=json.dumps(mask_pii(before), default=str) if before else None,
        after_json=json.dumps(mask_pii(after), default=str) if after else None,
    )
    db.add(log)


async def _write_outbox(
    db: AsyncSession,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """outbox_event ga yozuv qo'shadi."""
    event = OutboxEvent(
        aggregate_type="app_user",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


async def _check_phone_unique(
    db: AsyncSession,
    phone: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Telefon unikalligi blind-index orqali tekshiradi. Dublikat → AppError 409."""
    bi = blind_index(phone)
    stmt = select(AppUser.id).where(AppUser.phone_bi == bi)
    if exclude_id is not None:
        stmt = stmt.where(AppUser.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise AppError("users.duplicate_phone", status_code=409)


# ─── Get ──────────────────────────────────────────────────────────────────────


async def get_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """
    ID bo'yicha foydalanuvchi oladi.

    enterprise_id: server-authoritative (JWT dan). None = superadmin (filtr yo'q).

    Raises:
        AppError("users.user_not_found"): topilmasa yoki boshqa korxonaga tegishli.
    """
    stmt = select(AppUser).where(AppUser.id == user_id)
    stmt = apply_enterprise_filter(stmt, enterprise_id, AppUser.enterprise_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError("users.user_not_found", status_code=404)
    return user


# ─── List ─────────────────────────────────────────────────────────────────────


async def list_users(
    db: AsyncSession,
    *,
    enterprise_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    role: str | None = None,
    branch_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> tuple[list[AppUser], int]:
    """
    Paginated foydalanuvchilar ro'yxati.

    Filtrlar:
      - role: rol bo'yicha filtrlash
      - branch_id: filial bo'yicha filtrlash
      - is_active: aktiv/bloklangan bo'yicha filtrlash
    """
    base_where = []

    if role is not None:
        base_where.append(AppUser.role == role)

    if branch_id is not None:
        base_where.append(AppUser.branch_id == branch_id)

    if is_active is not None:
        base_where.append(AppUser.is_active == is_active)

    # Enterprise filtr
    count_base = select(func.count()).select_from(AppUser)
    count_base = apply_enterprise_filter(count_base, enterprise_id, AppUser.enterprise_id)
    if base_where:
        count_base = count_base.where(*base_where)
    count_result = await db.execute(count_base)
    total = count_result.scalar_one()

    # List
    list_stmt = select(AppUser).order_by(AppUser.created_at.desc()).limit(limit).offset(offset)
    list_stmt = apply_enterprise_filter(list_stmt, enterprise_id, AppUser.enterprise_id)
    if base_where:
        list_stmt = list_stmt.where(*base_where)

    result = await db.execute(list_stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Create ───────────────────────────────────────────────────────────────────


async def create_user(
    db: AsyncSession,
    data: UserCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """
    Yangi foydalanuvchi yaratadi (faqat administrator).

    PII (phone, full_name) EncryptedString orqali shifrlangan saqlanadi.
    phone_bi blind-index avtomatik to'ldiriladi (event listener orqali).
    Idempotentlik: Redis kalit idem:users:create:{actor_id}:{client_uuid}.
    """
    # Rol tekshiruvi
    if data.role not in VALID_ROLES:
        raise AppError("users.invalid_role", status_code=422)

    # ── Redis idempotentlik ──────────────────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(AppUser).where(AppUser.id == uuid.UUID(cached_id))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_user: idem_key=%s user o'chirilgan, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_user: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi user yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── Telefon unikalligi ───────────────────────────────────────────────────
    await _check_phone_unique(db, data.phone)

    # ── Foydalanuvchi yaratish ───────────────────────────────────────────────
    # phone va full_name EncryptedString TypeDecorator orqali shifrlangan saqlanadi.
    # phone_bi event listener (before_insert) orqali avtomatik to'ldiriladi.
    user = AppUser(
        full_name=data.full_name,
        phone=data.phone,
        role=data.role,
        branch_id=data.branch_id,
        locale=data.locale,
        password_hash=hash_password(data.password),
        biometric_enrolled=data.biometric_enrolled,
        device_id=data.device_id,
        is_active=True,
        enterprise_id=enterprise_id,  # MT2: server-authoritative
    )

    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "phone_bi" in exc_str or "uq_app_user_phone_bi" in exc_str or "unique" in exc_str:
            raise AppError("users.duplicate_phone", status_code=409) from exc
        raise

    after = {
        "id": str(user.id),
        "full_name": user.full_name,  # mask_pii da maskalanadi
        "phone": user.phone,
        "role": user.role,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "is_active": user.is_active,
    }
    await _write_audit(db, actor_id, "create", str(user.id), after=after)
    await _write_outbox(db, str(user.id), "user.created", {
        "id": str(user.id),
        "role": user.role,
        "branch_id": str(user.branch_id) if user.branch_id else None,
    })

    # ── Redis kalit saqlash ──────────────────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(user.id), ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_user: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return user


# ─── Update ───────────────────────────────────────────────────────────────────


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: UserUpdate,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """
    Foydalanuvchini yangilaydi (PATCH — faqat berilgan maydonlar).

    Optimistik lock: data.version mos kelmasa → version_conflict.
    phone yangilanganda phone_bi ham yangilanadi (event listener orqali).

    Raises:
        AppError("users.user_not_found"): topilmasa.
        AppError("users.version_conflict"): versiya mos kelmasa.
        AppError("users.duplicate_phone"): dublikat telefon.
        AppError("users.invalid_role"): noto'g'ri rol.
    """
    user = await get_user(db, user_id, enterprise_id=enterprise_id)

    if user.version != data.version:
        raise AppError("users.version_conflict", status_code=409)

    before = {
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "version": user.version,
        "is_active": user.is_active,
    }

    # Rol tekshiruvi
    if data.role is not None and data.role not in VALID_ROLES:
        raise AppError("users.invalid_role", status_code=422)

    # Telefon o'zgarganda unikalligi tekshirish
    if data.phone is not None and data.phone != user.phone:
        await _check_phone_unique(db, data.phone, exclude_id=user_id)

    # Maydonlarni yangilash
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone
        # phone_bi event listener (before_update) orqali avtomatik yangilanadi
    if data.role is not None:
        user.role = data.role
    if data.branch_id is not None:
        user.branch_id = data.branch_id
    if data.locale is not None:
        user.locale = data.locale
    if data.biometric_enrolled is not None:
        user.biometric_enrolled = data.biometric_enrolled
    if data.device_id is not None:
        user.device_id = data.device_id

    user.version = user.version + 1
    user.updated_at = _now()

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "phone_bi" in exc_str or "unique" in exc_str:
            raise AppError("users.duplicate_phone", status_code=409) from exc
        raise

    after = {
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "version": user.version,
        "is_active": user.is_active,
    }
    await _write_audit(db, actor_id, "update", str(user.id), before=before, after=after)
    await _write_outbox(db, str(user.id), "user.updated", {
        "id": str(user.id),
        "role": user.role,
        "version": user.version,
    })

    return user


# ─── Deactivate ───────────────────────────────────────────────────────────────


async def deactivate_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    current_user: AppUser | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """
    Foydalanuvchini deaktivatsiya qiladi (is_active=False).

    Admin o'zini deaktiv qila olmaydi.

    Raises:
        AppError("users.user_not_found"): topilmasa.
        AppError("users.cannot_deactivate_self"): admin o'zini deaktiv qilmoqchi.
    """
    # Admin o'zini deaktiv qila olmaydi
    if current_user is not None and current_user.id == user_id:
        raise AppError("users.cannot_deactivate_self", status_code=403)

    user = await get_user(db, user_id, enterprise_id=enterprise_id)

    before = {"is_active": user.is_active}

    user.is_active = False
    user.updated_at = _now()
    await db.flush()

    after = {"is_active": user.is_active}
    await _write_audit(db, actor_id, "deactivate", str(user.id), before=before, after=after)
    await _write_outbox(db, str(user.id), "user.deactivated", {"id": str(user.id)})

    return user


async def activate_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """
    Foydalanuvchini qayta aktivlashtiradi (is_active=True).

    Deaktivatsiyaning simmetrik teskarisi — bloklangan hisobni qaytaradi.

    Raises:
        AppError("users.user_not_found"): topilmasa.
    """
    user = await get_user(db, user_id, enterprise_id=enterprise_id)

    before = {"is_active": user.is_active}

    user.is_active = True
    user.updated_at = _now()
    await db.flush()

    after = {"is_active": user.is_active}
    await _write_audit(db, actor_id, "activate", str(user.id), before=before, after=after)
    await _write_outbox(db, str(user.id), "user.activated", {"id": str(user.id)})

    return user
