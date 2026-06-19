"""
Davomat servis qatlami — T16.

check_in(user, data, db, redis):
  Yangi davomat ochadi.
  - Shu kun ochiq davomat bo'lsa → AppError("attendance.already_checked_in", 409).
  - biometric_verified=False → AppError("attendance.biometric_required", 403).
    QAROR: biometric_verified=False kelsa QAT'IY RAD ETILADI.
    Sabab: davomat tizimining asosiy maqsadi qurilma biometriyasi orqali
    identifikatsiyani tasdiqlash. False bo'lsa tizim yaxlitligi buziladi
    (birovning telefoni bilan check-in imkoniyati ochiladi).
    Agar kelajakda "bio'siz check-in" kerak bo'lsa — alohida
    `source="admin_override"` bilan administrator uchun endpoint.
  - client_uuid idempotentlik: Redis + DB unique partial.
  - check_in_at SERVER vaqti (klient soatiga ISHONMASLIK — ADR §3.5).
  - GPS server tomonda yoziladi.
  - Audit + Outbox (user_id payload'da — sync scope uchun).

check_out(user, data, db, redis):
  Shu kunning ochiq davomatini yopadi.
  - Ochiq davomat yo'q bo'lsa → AppError("attendance.not_checked_in", 404).
  - check_out_at SERVER vaqti.
  - client_uuid idempotentlik (check_out uchun alohida Redis kalit).
  - Audit + Outbox.

list_attendance(filter, db, user):
  Paginated ro'yxat.
  RBAC scope:
    - agent/courier: FAQAT O'Z davomati (user_id == current_user.id).
    - administrator/accountant: barchasi (ixtiyoriy user_id filtr).
    - IDOR YO'Q: agent/courier boshqa user_id so'rasa → faqat o'ziniki.

GPS: Decimal (7 kasrga aniqlik).
Server vaqti: datetime.now(timezone.utc).
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
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.outbox import OutboxEvent
from app.models.user import AppUser
from app.modules.attendance.schemas import CheckInRequest, CheckOutRequest

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400  # 24 soat
_IDEM_PREFIX_IN   = "idem:attendance:check_in"
_IDEM_PREFIX_OUT  = "idem:attendance:check_out"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> date:
    return _now().date()


# ─── Audit / Outbox yordamchilari ─────────────────────────────────────────────


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    after: dict | None = None,
    before: dict | None = None,
) -> None:
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="attendance",
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
    event = OutboxEvent(
        aggregate_type="attendance",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


# ─── check_in ─────────────────────────────────────────────────────────────────


async def check_in(
    user: AppUser,
    data: CheckInRequest,
    db: AsyncSession,
    redis=None,
) -> Attendance:
    """
    Yangi davomat ochadi.

    BIZNES QOIDASI — biometric_verified:
      False bo'lsa → AppError("attendance.biometric_required", 403).
      Sabab: davomat tizimi qurilma biometriyasiga tayanadi.
      False → birov boshqasining qurilmasidan check-in qilishi mumkin.
      Kelajak kengaytirish: administrator uchun `source="admin_override"` endpoint.

    SERVER VAQTI:
      check_in_at = SERVER vaqti (klient bergan vaqtga ISHONMASLIK — ADR §3.5).
      work_date   = SERVER vaqtidan olinadi.

    IDEMPOTENTLIK:
      client_uuid berilsa → Redis kalit + DB partial unique tekshiruvi.
      Takror so'rovda mavjud davomat qaytariladi.

    OCHIQ DAVOMAT TEKSHIRUVI:
      Shu kun (work_date) uchun ochiq davomat bo'lsa → already_checked_in.
      "Ochiq davomat" = check_out_at IS NULL AND deleted_at IS NULL.

    Raises:
        AppError("attendance.biometric_required", 403): biometric_verified=False.
        AppError("attendance.already_checked_in", 409): shu kun ochiq davomat bor.
    """
    actor_id = user.id

    # ── 1. biometric_verified tekshiruvi (KRITIK BIZNES QOIDASI) ─────────────
    if not data.biometric_verified:
        raise AppError("attendance.biometric_required", status_code=403)

    # ── 2. client_uuid idempotentlik (Redis) ──────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX_IN}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Attendance).where(
                    Attendance.id == uuid.UUID(cached_id),
                    Attendance.deleted_at.is_(None),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "check_in: idem_key=%s yozuv topilmadi, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "check_in: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r).",
                idem_key, exc,
            )
            idem_key = None

    # ── 3. DB darajasida client_uuid idempotentlik ────────────────────────────
    if data.client_uuid is not None:
        existing_stmt = select(Attendance).where(
            Attendance.client_uuid == data.client_uuid,
            Attendance.user_id == actor_id,
            Attendance.deleted_at.is_(None),
        )
        existing_result = await db.execute(existing_stmt)
        existing_att = existing_result.scalar_one_or_none()
        if existing_att is not None:
            return existing_att

    # ── 4. Shu kun ochiq davomat tekshiruvi ───────────────────────────────────
    today = _today_utc()
    open_stmt = select(Attendance).where(
        Attendance.user_id == actor_id,
        Attendance.work_date == today,
        Attendance.check_out_at.is_(None),
        Attendance.deleted_at.is_(None),
    )
    open_result = await db.execute(open_stmt)
    open_att = open_result.scalar_one_or_none()
    if open_att is not None:
        raise AppError("attendance.already_checked_in", status_code=409)

    # ── 5. Yangi davomat yaratish ─────────────────────────────────────────────
    now = _now()
    att = Attendance(
        id=uuid7(),
        user_id=actor_id,
        work_date=today,
        check_in_at=now,
        check_in_gps_lat=data.gps_lat,
        check_in_gps_lng=data.gps_lng,
        check_out_at=None,
        check_out_gps_lat=None,
        check_out_gps_lng=None,
        biometric_verified=data.biometric_verified,
        source=data.source,
        client_uuid=data.client_uuid,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(att)
    try:
        await db.flush()
    except IntegrityError:
        # Parallel ikki check-in: Postgres partial unique (user_id, work_date)
        # yoki client_uuid unique indeksi xato berdi → 409 (boshqa modullar naqshi).
        await db.rollback()
        logger.warning("check_in: race conflict, user_id=%s", actor_id)
        raise AppError("attendance.already_checked_in", status_code=409)

    # ── 6. Audit + Outbox ─────────────────────────────────────────────────────
    after_payload = {
        "id": str(att.id),
        "user_id": str(actor_id),
        "work_date": str(today),
        "check_in_at": str(now),
        "biometric_verified": data.biometric_verified,
        "source": data.source,
    }
    await _write_audit(db, actor_id, "check_in", str(att.id), after=after_payload)
    await _write_outbox(db, str(att.id), "attendance.checked_in", after_payload)

    # ── 7. Redis idempotentlik kaliti saqlash ─────────────────────────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(att.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "check_in: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return att


# ─── check_out ────────────────────────────────────────────────────────────────


async def check_out(
    user: AppUser,
    data: CheckOutRequest,
    db: AsyncSession,
    redis=None,
) -> Attendance:
    """
    Shu kunning ochiq davomatini yopadi.

    OCHIQ DAVOMAT:
      check_out_at IS NULL AND deleted_at IS NULL AND work_date == today.

    SERVER VAQTI:
      check_out_at = SERVER vaqti (klient bergan vaqtga ISHONMASLIK).

    IDEMPOTENTLIK (check_out uchun):
      client_uuid berilsa va shu davomat allaqachon yopilgan bo'lsa → mavjudini qaytaradi.
      Redis kalit: idem:attendance:check_out:{user_id}:{client_uuid}.

    Raises:
        AppError("attendance.not_checked_in", 404): ochiq davomat yo'q.
    """
    actor_id = user.id

    # ── 1. client_uuid idempotentlik (Redis) ──────────────────────────────────
    idem_key: str | None = None
    if data.client_uuid is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX_OUT}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(Attendance).where(
                    Attendance.id == uuid.UUID(cached_id),
                    Attendance.deleted_at.is_(None),
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
        except Exception as exc:
            logger.warning(
                "check_out: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r).",
                idem_key, exc,
            )
            idem_key = None

    # ── 2. Ochiq davomatni topish ─────────────────────────────────────────────
    today = _today_utc()
    open_stmt = select(Attendance).where(
        Attendance.user_id == actor_id,
        Attendance.work_date == today,
        Attendance.check_out_at.is_(None),
        Attendance.deleted_at.is_(None),
    )
    open_result = await db.execute(open_stmt)
    att = open_result.scalar_one_or_none()

    if att is None:
        raise AppError("attendance.not_checked_in", status_code=404)

    # ── 3. check_out vaqti va GPS yozish ──────────────────────────────────────
    now = _now()
    before_payload = {
        "id": str(att.id),
        "check_out_at": None,
    }

    att.check_out_at = now
    att.check_out_gps_lat = data.gps_lat
    att.check_out_gps_lng = data.gps_lng
    att.version = att.version + 1
    att.updated_at = now
    await db.flush()

    # ── 4. Audit + Outbox ─────────────────────────────────────────────────────
    # IZOH: gps_lat/gps_lng hozir majburiy (schema darajasida NOT NULL).
    # Kelajakda optional bo'lsa str(None) → "None" xavfi bor.
    # O'sha vaqtda: str(data.gps_lat) ni f"{data.gps_lat!r}" yoki None-guard bilan almashtir.
    after_payload = {
        "id": str(att.id),
        "user_id": str(actor_id),
        "work_date": str(today),
        "check_out_at": str(now),
        "check_out_gps_lat": str(data.gps_lat),
        "check_out_gps_lng": str(data.gps_lng),
    }
    await _write_audit(
        db, actor_id, "check_out", str(att.id),
        before=before_payload, after=after_payload,
    )
    await _write_outbox(db, str(att.id), "attendance.checked_out", after_payload)

    # ── 5. Redis idempotentlik kaliti saqlash (check_out uchun) ───────────────
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(att.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "check_out: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return att


# ─── list_attendance ───────────────────────────────────────────────────────────


async def list_attendance(
    db: AsyncSession,
    *,
    user: AppUser,
    filter_user_id: uuid.UUID | None = None,
    filter_date: date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Attendance], int]:
    """
    Paginated davomat ro'yxati.

    RBAC scope (IDOR himoya):
      - agent/courier: FAQAT O'Z davomati.
        Boshqa user_id so'rasa → 403 forbidden_user (enumeration yo'q).
      - administrator/accountant: barchasi (filter_user_id ixtiyoriy).

    filter_date: ixtiyoriy sana filtri.
    """
    role = user.role

    # RBAC scope: agent/courier faqat o'z davomati
    if role in ("agent", "courier"):
        # IDOR himoya: boshqa user_id so'ralsa — 403 (enumeration oldini olish)
        if filter_user_id is not None and filter_user_id != user.id:
            logger.warning(
                "attendance: forbidden user_id so'rovi, actor=%s", user.id
            )
            raise AppError("attendance.forbidden_user", status_code=403)
        # O'z davomat ID'si bilan filtr
        scope_user_id = user.id
    elif role in ("administrator", "accountant"):
        scope_user_id = filter_user_id  # None = barchasi
    else:
        # Boshqa rollar (store) — o'z davomat yo'q (RBAC darajasida rad etiladi)
        raise AppError(
            "rbac.permission_denied",
            status_code=403,
            params={"module": "attendance", "action": "view", "role": role},
        )

    # Shartlar
    conditions = [Attendance.deleted_at.is_(None)]

    if scope_user_id is not None:
        conditions.append(Attendance.user_id == scope_user_id)

    if filter_date is not None:
        conditions.append(Attendance.work_date == filter_date)

    # Count
    count_stmt = select(func.count()).select_from(Attendance).where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List — vaqt bo'yicha teskari tartiblash
    stmt = (
        select(Attendance)
        .where(*conditions)
        .order_by(Attendance.check_in_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total
