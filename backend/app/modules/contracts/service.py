"""
Contracts servis qatlami — shartnoma biznes mantiq.

Funksiyalar:
  create_contract(db, data, actor_id, user, redis) → Contract
  get_contract(db, contract_id, user) → Contract
  list_contracts(db, user, filters...) → (list[Contract], total)
  update_contract(db, contract_id, data, actor_id, user) → Contract
  delete_contract(db, contract_id, actor_id, user) → None  (soft-delete)
  update_contract_file(db, contract_id, file_url, actor_id, user) → Contract
  list_expiring(db, user, days) → list[Contract]

Qoidalar:
  - number unikalligi (store_id, number) juftligi bo'yicha tekshiriladi.
  - version optimistik lock.
  - client_uuid Redis idempotentlik.
  - Har mutatsiyada audit_log + outbox_event yoziladi.
  - status DERIVED: valid_to ga qarab Contract.status property'da hisoblanadi.
  - Scope/IDOR: agent → o'z do'konlari; store → o'ziniki; admin/buxgalter → barchasi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.audit import AuditLog
from app.models.contract import Contract
from app.models.outbox import OutboxEvent
from app.models.user import AppUser
from app.modules.contracts.schemas import ContractCreate, ContractUpdate
from app.modules.rbac.scope import get_user_store_ids

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:contracts:create"

_BRANCH_ADMIN_ROLES = frozenset({"administrator", "accountant"})

DEFAULT_EXPIRING_DAYS = 30


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
    """audit_log ga yozuv qo'shadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="contract",
        entity_id=entity_id,
        before_json=json.dumps(before, default=str) if before else None,
        after_json=json.dumps(after, default=str) if after else None,
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
        aggregate_type="contract",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


async def _get_allowed_store_ids(
    db: AsyncSession,
    user: AppUser | None,
) -> list[uuid.UUID] | None:
    """
    Foydalanuvchiga ruxsat etilgan do'kon ID larini qaytaradi.

    None qaytarsa — barcha do'konlarga ruxsat (admin/buxgalter).
    Bo'sh ro'yxat — hech narsa ko'rinmaydi.
    """
    if user is None:
        return None
    if user.role in _BRANCH_ADMIN_ROLES:
        return None  # filtr yo'q — barchasi
    return await get_user_store_ids(user, db)


async def _check_number_unique(
    db: AsyncSession,
    store_id: uuid.UUID,
    number: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """
    (store_id, number) juftligi bo'yicha unikalligi tekshiradi.

    Dublikat → AppError("contracts.duplicate_number", 409).
    """
    stmt = select(Contract.id).where(
        Contract.store_id == store_id,
        Contract.number == number,
        Contract.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(Contract.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise AppError("contracts.duplicate_number", status_code=409)


# ─── Get (scope/IDOR) ────────────────────────────────────────────────────────


async def get_contract(
    db: AsyncSession,
    contract_id: uuid.UUID,
    user: AppUser | None = None,
) -> Contract:
    """
    ID bo'yicha shartnoma oladi.

    Scope/IDOR: foydalanuvchi doirasidagi shartnomani qaytaradi.
    Boshqasi → 404 (mavjudlikni oshkor qilmaslik).

    Raises:
        AppError("contracts.not_found"): topilmasa yoki IDOR.
    """
    stmt = select(Contract).where(
        Contract.id == contract_id,
        Contract.deleted_at.is_(None),
    )

    if user is not None:
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if allowed_store_ids is not None:
            if not allowed_store_ids:
                raise AppError("contracts.not_found", status_code=404)
            stmt = stmt.where(Contract.store_id.in_(allowed_store_ids))

    result = await db.execute(stmt)
    contract = result.scalar_one_or_none()
    if contract is None:
        raise AppError("contracts.not_found", status_code=404)
    return contract


# ─── List (paginated + filter + scope) ───────────────────────────────────────


async def list_contracts(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    limit: int = 20,
    offset: int = 0,
    store_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    valid_to_before: date | None = None,
    valid_to_after: date | None = None,
) -> tuple[list[Contract], int]:
    """
    Paginated shartnomalar ro'yxati.

    Filtrlar:
      - store_id: do'kon bo'yicha
      - status_filter: "active" | "expiring" | "expired" (today bo'yicha)
      - valid_to_before: valid_to < sana
      - valid_to_after: valid_to > sana

    Scope: admin/buxgalter barchasi; agent/store — o'z do'konlari.

    status filtr DB da sana taqqoslash orqali amalga oshiriladi
    (status property ORM objects da hisoblanadi, lekin count/list uchun DB filtr qo'llaniladi).
    """
    today = _now().date()
    expiring_threshold = today + timedelta(days=DEFAULT_EXPIRING_DAYS)

    base_where = [Contract.deleted_at.is_(None)]

    # Scope/IDOR filtri
    if user is not None:
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if allowed_store_ids is not None:
            if not allowed_store_ids:
                return [], 0
            base_where.append(Contract.store_id.in_(allowed_store_ids))

    if store_id is not None:
        base_where.append(Contract.store_id == store_id)

    # Status filtri (DB sana taqqoslash)
    if status_filter == "expired":
        base_where.append(Contract.valid_to < today)
    elif status_filter == "expiring":
        base_where.append(Contract.valid_to >= today)
        base_where.append(Contract.valid_to <= expiring_threshold)
    elif status_filter == "active":
        base_where.append(Contract.valid_to > expiring_threshold)

    if valid_to_before is not None:
        base_where.append(Contract.valid_to < valid_to_before)
    if valid_to_after is not None:
        base_where.append(Contract.valid_to > valid_to_after)

    # Count
    count_stmt = select(func.count()).select_from(Contract).where(*base_where)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List
    stmt = (
        select(Contract)
        .where(*base_where)
        .order_by(Contract.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Create ───────────────────────────────────────────────────────────────────


async def create_contract(
    db: AsyncSession,
    data: ContractCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
) -> Contract:
    """
    Yangi shartnoma yaratadi.

    Tekshiruvlar:
      - valid_to >= valid_from (sxema darajasida ham tekshiriladi).
      - (store_id, number) unikalligi.
      - Idempotentlik: Redis kalit idem:contracts:create:{actor_id}:{client_uuid}.

    Scope: agent/store faqat ruxsat etilgan do'konlar uchun yarata oladi.
    """
    # ── Scope: agent/store faqat o'z do'konlari uchun ──────────────────────
    if user is not None:
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if allowed_store_ids is not None and data.store_id not in allowed_store_ids:
            raise AppError("contracts.not_found", status_code=404)

    # ── Redis idempotentlik ──────────────────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Contract).where(
                    Contract.id == uuid.UUID(cached_id),
                    Contract.deleted_at.is_(None),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "create_contract: idem_key=%s shartnoma o'chirilgan, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "create_contract: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi shartnoma yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── Number unikalligi ────────────────────────────────────────────────────
    await _check_number_unique(db, data.store_id, data.number)

    # ── Shartnoma yaratish ───────────────────────────────────────────────────
    contract = Contract(
        store_id=data.store_id,
        number=data.number,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        signed_at=data.signed_at,
        contract_type=data.contract_type,
        branch_id=data.branch_id,
        client_uuid=data.client_uuid,
    )

    db.add(contract)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "uq_contract_store_number" in exc_str or "unique" in exc_str:
            raise AppError("contracts.duplicate_number", status_code=409) from exc
        raise

    after = {
        "id": str(contract.id),
        "store_id": str(contract.store_id),
        "number": contract.number,
        "valid_from": str(contract.valid_from),
        "valid_to": str(contract.valid_to),
    }
    await _write_audit(db, actor_id, "create", str(contract.id), after=after)
    await _write_outbox(db, str(contract.id), "contract.created", {
        "id": str(contract.id),
        "store_id": str(contract.store_id),
        "number": contract.number,
        "valid_from": str(contract.valid_from),
        "valid_to": str(contract.valid_to),
    })

    # ── Redis kalit saqlash ──────────────────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(contract.id), ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_contract: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return contract


# ─── Update ──────────────────────────────────────────────────────────────────


async def update_contract(
    db: AsyncSession,
    contract_id: uuid.UUID,
    data: ContractUpdate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> Contract:
    """
    Shartnomani yangilaydi (PATCH — faqat berilgan maydonlar).

    Optimistik lock: data.version mos kelmasa → version_conflict.
    """
    contract = await get_contract(db, contract_id, user=user)

    if contract.version != data.version:
        raise AppError("contracts.version_conflict", status_code=409)

    # valid_from/valid_to tekshiruvi
    new_valid_from = data.valid_from if data.valid_from is not None else contract.valid_from
    new_valid_to = data.valid_to if data.valid_to is not None else contract.valid_to
    if new_valid_to < new_valid_from:
        raise AppError("contracts.invalid_dates", status_code=422)

    before = {
        "number": contract.number,
        "valid_from": str(contract.valid_from),
        "valid_to": str(contract.valid_to),
        "version": contract.version,
    }

    # Number o'zgarganda unikalligi tekshirish
    if data.number is not None and data.number != contract.number:
        await _check_number_unique(db, contract.store_id, data.number, exclude_id=contract_id)

    # Maydonlarni yangilash
    if data.number is not None:
        contract.number = data.number
    if data.valid_from is not None:
        contract.valid_from = data.valid_from
    if data.valid_to is not None:
        contract.valid_to = data.valid_to
    if data.signed_at is not None:
        contract.signed_at = data.signed_at
    if data.contract_type is not None:
        contract.contract_type = data.contract_type
    if data.branch_id is not None:
        contract.branch_id = data.branch_id

    contract.version = contract.version + 1
    contract.updated_at = _now()

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        exc_str = str(exc).lower()
        if "uq_contract_store_number" in exc_str or "unique" in exc_str:
            raise AppError("contracts.duplicate_number", status_code=409) from exc
        raise

    after = {
        "number": contract.number,
        "valid_from": str(contract.valid_from),
        "valid_to": str(contract.valid_to),
        "version": contract.version,
    }
    await _write_audit(db, actor_id, "update", str(contract.id), before=before, after=after)
    await _write_outbox(db, str(contract.id), "contract.updated", {
        "id": str(contract.id),
        "store_id": str(contract.store_id),
        "number": contract.number,
        "version": contract.version,
    })

    return contract


# ─── Delete (soft) ───────────────────────────────────────────────────────────


async def delete_contract(
    db: AsyncSession,
    contract_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> None:
    """
    Shartnomani soft-delete qiladi (deleted_at o'rnatadi).

    Raises:
        AppError("contracts.not_found"): topilmasa yoki doiradan tashqari.
    """
    contract = await get_contract(db, contract_id, user=user)
    contract.deleted_at = _now()
    contract.updated_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "delete", str(contract.id))
    await _write_outbox(db, str(contract.id), "contract.deleted", {"id": str(contract.id)})


# ─── File upload ──────────────────────────────────────────────────────────────


async def update_contract_file(
    db: AsyncSession,
    contract_id: uuid.UUID,
    file_url: str,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> Contract:
    """
    Shartnoma faylini (PDF/rasm URL) yangilaydi.

    Haqiqiy fayl validatsiyasi va storage upload router da bajariladi.
    Bu funksiya faqat file_url ni saqlaydi.
    """
    contract = await get_contract(db, contract_id, user=user)

    before = {"file_url": contract.file_url}
    contract.file_url = file_url
    contract.updated_at = _now()
    await db.flush()

    await _write_audit(
        db, actor_id, "file_upload", str(contract.id),
        before=before, after={"file_url": file_url},
    )
    await _write_outbox(db, str(contract.id), "contract.file_uploaded", {
        "id": str(contract.id),
        "file_url": file_url,
    })

    return contract


# ─── List expiring ────────────────────────────────────────────────────────────


async def list_expiring(
    db: AsyncSession,
    *,
    user: AppUser | None = None,
    days: int = DEFAULT_EXPIRING_DAYS,
) -> list[Contract]:
    """
    Muddati tugayotgan shartnomalar ro'yxati.

    today <= valid_to <= today + days va expired emas (valid_to >= today).
    Worker/push notification uchun ishlatiladi.
    Ixtiyoriy: outbox event `contract.expiring` yozilishi mumkin.

    Returns:
        Muddati tugayotgan (expiring) shartnomalar ro'yxati.
    """
    today = _now().date()
    threshold = today + timedelta(days=days)

    where = [
        Contract.deleted_at.is_(None),
        Contract.valid_to >= today,
        Contract.valid_to <= threshold,
    ]

    # Scope
    if user is not None:
        allowed_store_ids = await _get_allowed_store_ids(db, user)
        if allowed_store_ids is not None:
            if not allowed_store_ids:
                return []
            where.append(Contract.store_id.in_(allowed_store_ids))

    stmt = (
        select(Contract)
        .where(*where)
        .order_by(Contract.valid_to.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
