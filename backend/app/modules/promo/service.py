"""
Promo (Aksiya) servis qatlami — T25.

Funksiyalar:
  create_promo(db, data, actor_id, user, redis) → Promo
  get_promo(db, promo_id, user) → Promo
  list_promos(db, filters...) → (list[Promo], total)
  list_active_promos(db, at_date) → list[Promo]
  update_promo(db, promo_id, data, actor_id, user) → Promo
  delete_promo(db, promo_id, actor_id, user) → None  (soft-delete)
  update_banner(db, promo_id, banner_url, actor_id, user) → Promo
  compute_line_discount(db, product_id, segment_id, qty, unit_price) → Decimal

SERVER-AVTORITAR CHEGIRMA (KRITIK — T11 himoyasi):
  compute_line_discount() server tomonda amaldagi promo'ni topib chegirma hisoblaydi.
  Klient hech qachon discount bera olmaydi — bu funksiya buyurtma yaratishda chaqiriladi.
  Mos promo yo'q → Decimal("0") (buyurtma regressiyasi yo'q).

Qoidalar:
  - admin CRUD; boshqalar faqat view (hammaga GET /promos/active).
  - version optimistik lock.
  - client_uuid Redis idempotentlik (IntegrityError → mavjud).
  - Har mutatsiyada audit_log + outbox_event.
  - Sync pull da promo global — barcha autentifikatsiyalangan foydalanuvchilarga.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.audit import AuditLog
from app.models.outbox import OutboxEvent
from app.models.promo import Promo
from app.models.user import AppUser
from app.modules.promo.schemas import PromoCreate, PromoUpdate

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400
_IDEM_PREFIX = "idem:promo:create"

_PROMO_TYPES = frozenset({"discount", "bonus", "gift"})
_ADMIN_ROLES = frozenset({"administrator"})


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(timezone.utc).date()


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
        entity_type="promo",
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
    """outbox_event ga yozuv qo'shadi — sync pull uchun."""
    event = OutboxEvent(
        aggregate_type="promo",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


def _promo_payload(promo: Promo) -> dict:
    """Promo ning JSON-serializable payload'ini qaytaradi."""
    return {
        "id": str(promo.id),
        "name_uz": promo.name_uz,
        "name_ru": promo.name_ru,
        "promo_type": promo.promo_type,
        "is_active": promo.is_active,
        "valid_from": str(promo.valid_from),
        "valid_to": str(promo.valid_to),
        "target_segment_id": str(promo.target_segment_id) if promo.target_segment_id else None,
        "target_product_id": str(promo.target_product_id) if promo.target_product_id else None,
        "version": promo.version,
    }


# ─── Scope tekshiruvi ─────────────────────────────────────────────────────────


def _require_admin(user: AppUser | None) -> None:
    """Faqat administrator CRUD amal qila oladi."""
    if user is None or user.role not in _ADMIN_ROLES:
        raise AppError(
            "rbac.permission_denied",
            status_code=403,
            params={"module": "promo", "action": "create/edit/delete", "role": user.role if user else "anonymous"},
        )


# ─── create_promo ─────────────────────────────────────────────────────────────


async def create_promo(
    db: AsyncSession,
    data: PromoCreate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    redis=None,
) -> Promo:
    """
    Yangi aksiya yaratadi.

    Faqat administrator. version=1, idempotentlik client_uuid orqali.

    Raises:
        AppError("promo.invalid_dates", 422): valid_to < valid_from.
        AppError("promo.invalid_rule", 422): rule_json yaroqsiz.
        AppError("rbac.permission_denied", 403): ruxsat yo'q.
    """
    _require_admin(user)

    # Sana validatsiyasi (sxemada ham tekshiriladi, lekin service darajasida ham)
    if data.valid_to < data.valid_from:
        raise AppError("promo.invalid_dates", status_code=422)

    # promo_type validatsiyasi
    if data.promo_type not in _PROMO_TYPES:
        raise AppError(
            "promo.invalid_rule",
            status_code=422,
            params={},
        )

    # ── Idempotentlik ─────────────────────────────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Promo).where(Promo.id == uuid.UUID(cached_id))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning("create_promo: idem_key=%s yozuv topilmadi", idem_key)
        except Exception as exc:
            logger.warning(
                "create_promo: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r)", idem_key, exc,
            )
            idem_key = None

    # ── Promo yaratish ────────────────────────────────────────────────────────
    promo = Promo(
        id=uuid7(),
        name_uz=data.name_uz,
        name_ru=data.name_ru,
        promo_type=data.promo_type,
        rule_json=data.rule_json,
        banner_url=data.banner_url,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        target_segment_id=data.target_segment_id,
        target_product_id=data.target_product_id,
        is_active=data.is_active,
        branch_id=data.branch_id,
        client_uuid=data.client_uuid,
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(promo)
    try:
        await db.flush()
    except IntegrityError as exc:
        # client_uuid dublikati — mavjud promo qaytarish
        await db.rollback()
        if data.client_uuid is not None:
            existing_stmt = select(Promo).where(
                Promo.client_uuid == data.client_uuid,
                Promo.deleted_at.is_(None),
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                return existing
        raise AppError("promo.not_found", status_code=404) from exc

    # ── Audit + Outbox ────────────────────────────────────────────────────────
    payload = _promo_payload(promo)
    await _write_audit(db, actor_id, "create", str(promo.id), after=payload)
    await _write_outbox(db, str(promo.id), "promo.created", payload)

    # ── Redis idempotentlik kaliti ────────────────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(promo.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "create_promo: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return promo


# ─── get_promo ────────────────────────────────────────────────────────────────


async def get_promo(
    db: AsyncSession,
    promo_id: uuid.UUID,
    user: AppUser | None = None,
) -> Promo:
    """
    Bitta promo'ni qaytaradi.

    Barcha autentifikatsiyalangan rollar ko'ra oladi (ADR §3.6: hamma view).

    Raises:
        AppError("promo.not_found", 404): promo topilmasa yoki o'chirilgan.
    """
    stmt = select(Promo).where(
        Promo.id == promo_id,
        Promo.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if promo is None:
        raise AppError("promo.not_found", status_code=404)
    return promo


# ─── list_promos ──────────────────────────────────────────────────────────────


async def list_promos(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    target_segment_id: uuid.UUID | None = None,
    target_product_id: uuid.UUID | None = None,
    promo_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Promo], int]:
    """
    Paginated promo ro'yxati.

    Barcha autentifikatsiyalangan rollar ko'ra oladi.
    Filtrlar: is_active, target_segment_id, target_product_id, promo_type.
    """
    conditions = [Promo.deleted_at.is_(None)]

    if is_active is not None:
        conditions.append(Promo.is_active == is_active)
    if target_segment_id is not None:
        conditions.append(Promo.target_segment_id == target_segment_id)
    if target_product_id is not None:
        conditions.append(Promo.target_product_id == target_product_id)
    if promo_type is not None:
        conditions.append(Promo.promo_type == promo_type)

    count_stmt = select(func.count()).select_from(Promo).where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = (
        select(Promo)
        .where(*conditions)
        .order_by(Promo.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── list_active_promos ───────────────────────────────────────────────────────


async def list_active_promos(
    db: AsyncSession,
    at_date: date | None = None,
) -> list[Promo]:
    """
    Hozir amal qiladigan aksiyalar ro'yxatini qaytaradi.

    Shartlar: is_active=True AND valid_from<=at_date<=valid_to.
    at_date=None bo'lsa bugungi sana ishlatiladi.

    Sync pull da promo global — barcha autentifikatsiyalangan foydalanuvchilarga.
    """
    check_date = at_date or _today()

    stmt = select(Promo).where(
        Promo.deleted_at.is_(None),
        Promo.is_active.is_(True),
        Promo.valid_from <= check_date,
        Promo.valid_to >= check_date,
    ).order_by(Promo.valid_from.asc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ─── update_promo ─────────────────────────────────────────────────────────────


async def update_promo(
    db: AsyncSession,
    promo_id: uuid.UUID,
    data: PromoUpdate,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> Promo:
    """
    Aksiyani qisman yangilaydi (PATCH).

    Faqat administrator. version optimistik lock.

    Raises:
        AppError("promo.not_found", 404): promo topilmasa.
        AppError("orders.version_conflict", 409): versiya mos kelmasa.
        AppError("promo.invalid_dates", 422): sana xato.
        AppError("promo.invalid_rule", 422): rule_json yaroqsiz.
        AppError("rbac.permission_denied", 403): ruxsat yo'q.
    """
    _require_admin(user)

    stmt = select(Promo).where(
        Promo.id == promo_id,
        Promo.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if promo is None:
        raise AppError("promo.not_found", status_code=404)

    # Version optimistik lock
    if promo.version != data.version:
        raise AppError("promo.version_conflict", status_code=409)

    before_payload = _promo_payload(promo)

    # Maydonlarni yangilash (faqat berilganlar)
    if data.name_uz is not None:
        promo.name_uz = data.name_uz
    if data.name_ru is not None:
        promo.name_ru = data.name_ru
    if data.promo_type is not None:
        if data.promo_type not in _PROMO_TYPES:
            raise AppError("promo.invalid_rule", status_code=422)
        promo.promo_type = data.promo_type
    if data.rule_json is not None:
        promo.rule_json = data.rule_json
    if data.valid_from is not None:
        promo.valid_from = data.valid_from
    if data.valid_to is not None:
        promo.valid_to = data.valid_to
    if data.is_active is not None:
        promo.is_active = data.is_active
    if data.branch_id is not None:
        promo.branch_id = data.branch_id

    # NULL qabul qiladigan maydonlar (ixtiyoriy)
    if "target_segment_id" in data.model_fields_set:
        promo.target_segment_id = data.target_segment_id
    if "target_product_id" in data.model_fields_set:
        promo.target_product_id = data.target_product_id

    # Sana izchilligini tekshirish (yangilangandan keyin)
    if promo.valid_to < promo.valid_from:
        raise AppError("promo.invalid_dates", status_code=422)

    promo.version = promo.version + 1
    promo.updated_at = _now()
    await db.flush()

    after_payload = _promo_payload(promo)
    await _write_audit(db, actor_id, "update", str(promo.id), before=before_payload, after=after_payload)
    await _write_outbox(db, str(promo.id), "promo.updated", after_payload)

    return promo


# ─── delete_promo ─────────────────────────────────────────────────────────────


async def delete_promo(
    db: AsyncSession,
    promo_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> None:
    """
    Aksiyani soft-delete qiladi.

    Faqat administrator.

    Raises:
        AppError("promo.not_found", 404): promo topilmasa.
        AppError("rbac.permission_denied", 403): ruxsat yo'q.
    """
    _require_admin(user)

    stmt = select(Promo).where(
        Promo.id == promo_id,
        Promo.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if promo is None:
        raise AppError("promo.not_found", status_code=404)

    before_payload = {"id": str(promo.id), "deleted_at": None}
    promo.deleted_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "delete", str(promo.id), before=before_payload)
    await _write_outbox(db, str(promo.id), "promo.deleted", {"id": str(promo.id)})


# ─── update_banner ────────────────────────────────────────────────────────────


async def update_banner(
    db: AsyncSession,
    promo_id: uuid.UUID,
    banner_url: str,
    actor_id: uuid.UUID | None = None,
    user: AppUser | None = None,
) -> Promo:
    """
    Promo banner URL ni yangilaydi.

    Faqat administrator. banner URL storage'dan olinadi (magic-byte validatsiya storage'da).

    Raises:
        AppError("promo.not_found", 404): promo topilmasa.
        AppError("rbac.permission_denied", 403): ruxsat yo'q.
    """
    _require_admin(user)

    stmt = select(Promo).where(
        Promo.id == promo_id,
        Promo.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if promo is None:
        raise AppError("promo.not_found", status_code=404)

    before_payload = {"id": str(promo.id), "banner_url": promo.banner_url}
    promo.banner_url = banner_url
    promo.version = promo.version + 1
    promo.updated_at = _now()
    await db.flush()

    after_payload = {"id": str(promo.id), "banner_url": banner_url}
    await _write_audit(db, actor_id, "update_banner", str(promo.id), before=before_payload, after=after_payload)
    await _write_outbox(db, str(promo.id), "promo.banner_updated", after_payload)

    return promo


# ─── compute_line_discount (SERVER-AVTORITAR) ─────────────────────────────────


async def compute_line_discount(
    db: AsyncSession,
    product_id: uuid.UUID,
    segment_id: uuid.UUID | None,
    qty: Decimal,
    unit_price: Decimal,
) -> Decimal:
    """
    Buyurtma qatori uchun SERVER TOMONDA chegirma hisoblaydi.

    SERVER-AVTORITAR (KRITIK — T11 himoya):
      Bu funksiya server tomonida chaqiriladi. Klient HECH QACHON discount bera olmaydi.
      OrderLineIn sxemasida discount maydoni yo'q (schema darajasida himoya).

    Algoritm:
      1. Hozir amal qilayotgan promo'larni qidiradi:
         - is_active=True AND valid_from<=bugun<=valid_to
         - target_product_id mos (NULL = barchasi) AND target_segment_id mos (NULL = barchasi)
      2. Mos promo topilsa — rule_json bo'yicha chegirma hisoblaydi:
         - discount_percent: unit_price * qty * (pct/100)
         - discount_amount: mos miqdor uchun bir marta (qator uchun)
         - min_qty: berilgan miqdor min_qty dan kichik bo'lsa — chegirma yo'q
      3. Mos promo yo'q → Decimal("0") (klient discount bera olmaydi, 0 qoladi).

    Args:
        product_id: Mahsulot UUID.
        segment_id: Do'kon segmenti UUID (Store.segment_id dan server tomonida olinadi).
        qty: Buyurtma miqdori.
        unit_price: Mahsulot narxi (SERVER tomonida katalogdan olinadi).

    Returns:
        Decimal chegirma summasi (0.00 - mos promo yo'q, yoki hisoblangan summa).
    """
    today = _today()

    # Mos promo ni topish:
    # Ustuvorlik: mahsulot + segment mos promo > mahsulot mos > segment mos > global
    # Eng mos promo: target_product_id va target_segment_id ikkisi ham mos (yoki NULL)
    # Eng yangi/birinchi mos promo ishlatiladi (valid_from desc, id bo'yicha)

    conditions = [
        Promo.deleted_at.is_(None),
        Promo.is_active.is_(True),
        Promo.valid_from <= today,
        Promo.valid_to >= today,
        Promo.promo_type == "discount",  # faqat discount tipi hisoblashga mos
    ]

    # Mahsulot filtri: target_product_id NULL (barchasi) yoki mos mahsulot
    product_cond = (
        (Promo.target_product_id.is_(None)) |
        (Promo.target_product_id == product_id)
    )
    conditions.append(product_cond)

    # Segment filtri: target_segment_id NULL (barchasi) yoki mos segment
    if segment_id is not None:
        segment_cond = (
            (Promo.target_segment_id.is_(None)) |
            (Promo.target_segment_id == segment_id)
        )
        conditions.append(segment_cond)
    else:
        # Segment yo'q bo'lsa — faqat global promo'lar (target_segment_id IS NULL)
        conditions.append(Promo.target_segment_id.is_(None))

    stmt = (
        select(Promo)
        .where(*conditions)
        # Ustuvorlik: aniqroq (mahsulot + segment) promo'lar birinchi
        # 1. target_product_id NOT NULL (aniq mahsulot) — yuqori ustuvorlik
        # 2. target_segment_id NOT NULL (aniq segment) — o'rta ustuvorlik
        # 3. valid_from desc — eng yangi promo
        .order_by(
            Promo.target_product_id.is_(None).asc(),   # NOT NULL birinchi
            Promo.target_segment_id.is_(None).asc(),   # NOT NULL birinchi
            Promo.valid_from.desc(),
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()

    if promo is None:
        return Decimal("0")

    # Chegirma hisoblash
    rule = promo.rule_json or {}

    # min_qty tekshiruvi
    min_qty = rule.get("min_qty")
    if min_qty is not None:
        try:
            min_qty_dec = Decimal(str(min_qty))
        except Exception:
            return Decimal("0")
        if qty < min_qty_dec:
            return Decimal("0")

    # discount_percent hisoblash
    if "discount_percent" in rule:
        try:
            pct = Decimal(str(rule["discount_percent"]))
        except Exception:
            return Decimal("0")
        # Chegirma = unit_price * qty * (pct/100), lekin line_gross dan oshmasin
        line_gross = (unit_price * qty).quantize(Decimal("0.01"))
        discount = (unit_price * qty * pct / Decimal("100")).quantize(Decimal("0.01"))
        discount = min(discount, line_gross)   # line_total hech qachon manfiy bo'lmaydi
        return max(Decimal("0"), discount)

    # discount_amount hisoblash
    if "discount_amount" in rule:
        try:
            amt = Decimal(str(rule["discount_amount"]))
        except Exception:
            return Decimal("0")
        # Chegirma = amt (qator uchun bir marta, line_total dan chiqariladi)
        # Llegirma line_total dan oshib ketmasligi shart
        line_gross = (unit_price * qty).quantize(Decimal("0.01"))
        discount = min(amt, line_gross).quantize(Decimal("0.01"))
        return max(Decimal("0"), discount)

    return Decimal("0")
