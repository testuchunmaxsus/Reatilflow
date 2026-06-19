"""
GPS Ingest router — T17.

Endpointlar:
  POST /gps/ingest              — batch GPS nuqtalarni yuklash (agent/courier)
  GET  /gps/track/{delivery_id} — yetkazish marshrutini ko'rish (scope)
  GET  /gps/track               — foydalanuvchi+sana bo'yicha marshrut (scope)

RBAC:
  POST ingest:       gps:create (agent, courier)
  GET  track:        gps:view   (agent, courier, administrator)

IDOR himoya:
  - agent/courier: FAQAT o'z nuqtalarini ingest/ko'radi.
    Boshqa user_id yoki boshqa delivery → 403 (mavjudlik oshkor bo'lmaydi).
  - administrator: barchasi.

Rate-limit (Redis):
  POST /gps/ingest: 600 so'rov/daqiqa — yuqori chastota uchun moslangan.
    (Batch bo'lgani uchun 600 so'rov/min: har 100ms da 1 ta batch — qurilma uchun yetarli)
  GET  /gps/track:  120 so'rov/daqiqa — ko'rish uchun.

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).

ADR §3.7:
  - recorded_at: QURILMA vaqti (klientdan keladi).
  - ingested_at: SERVER vaqti.
  - GPS sync'ga tushmaydi — outbox YO'Q.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db, get_timescale_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.gps import service
from app.modules.gps.schemas import (
    GpsBatchIngest,
    GpsTrackOut,
    IngestResult,
    PaginatedTrack,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gps"])

# ─── Rate-limit konstantalari ─────────────────────────────────────────────────

_INGEST_RATE_LIMIT  = 600   # batch ingest: yuqori chastota
_INGEST_RATE_WINDOW = 60    # sekund oyna

_TRACK_RATE_LIMIT   = 120   # ko'rish: standart
_TRACK_RATE_WINDOW  = 60


# ─── Rate-limit yordamchisi ───────────────────────────────────────────────────


async def _check_rate_limit(
    redis: Redis,
    user_id: str,
    endpoint: str,
    limit: int,
    window: int,
) -> None:
    """
    Redis INCR+EXPIRE orqali sodda rate-limit.

    Kalit: rate:gps:{endpoint}:{user_id}
    Oshsa: AppError("sync.rate_limited", 429).
    Redis xato bo'lsa — graceful degradation (o'tkazib yuboriladi).
    """
    key = f"rate:gps:{endpoint}:{user_id}"
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window)
        if current > limit:
            raise AppError("sync.rate_limited", status_code=429)
    except AppError:
        raise
    except Exception as exc:
        logger.warning(
            "gps: rate-limit tekshiruvi muvaffaqiyatsiz (user_id=%s endpoint=%s): %r",
            user_id, endpoint, exc,
        )


# ─── POST /gps/ingest ─────────────────────────────────────────────────────────


@router.post(
    "/ingest",
    response_model=IngestResult,
    status_code=200,
    summary="Batch GPS nuqtalarni yuklash",
    description=(
        "Qurilmadan batch GPS nuqtalarni yuklaydi. "
        "user_id SERVER'dan olinadi (klient boshqa nomidan ingest qila olmaydi). "
        "recorded_at — QURILMA vaqti (offline yozilgan). "
        "ingested_at — SERVER qabul qilgan vaqt. "
        "ADR §3.7: GPS faqat aktiv ish sessiyasida (check_in → check_out) saqlanadi. "
        "Ish vaqtidan tashqari nuqtalar jim tashlab yuboriladi. "
        "Batch limit: 500 nuqta. "
        "Rate-limit: 600 so'rov/daqiqa. "
        "Idempotentlik: (user_id, recorded_at) takror → e'tiborsiz."
    ),
)
async def ingest_gps(
    body: GpsBatchIngest,
    current_user: AppUser = require_permission(Module.GPS, Action.CREATE),
    db: AsyncSession = Depends(get_timescale_db),
    oltp_db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> IngestResult:
    """
    POST /gps/ingest

    RBAC: gps:create (agent, courier).
    IDOR: user_id server'dan (klientdan OLINMAYDI).
    Rate-limit: 600 batch/daqiqa.
    ADR §3.7: attendance aktiv sessiyasi tekshiriladi (oltp_db orqali).
    """
    await _check_rate_limit(
        redis,
        str(current_user.id),
        "ingest",
        _INGEST_RATE_LIMIT,
        _INGEST_RATE_WINDOW,
    )

    return await service.ingest(
        user=current_user,
        batch=body,
        db=db,
        oltp_db=oltp_db,
    )


# ─── GET /gps/track/{delivery_id} ────────────────────────────────────────────


@router.get(
    "/track/{delivery_id}",
    response_model=PaginatedTrack,
    status_code=200,
    summary="Yetkazish marshrutini ko'rish",
    description=(
        "delivery_id bo'yicha GPS marshrut nuqtalari. "
        "agent/courier: faqat o'z yetkazishining marshrutini ko'radi. "
        "administrator: barchasi. "
        "Rate-limit: 120 so'rov/daqiqa."
    ),
)
async def get_track_by_delivery(
    delivery_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000, description="Sahifa hajmi"),
    offset: int = Query(default=0, ge=0, description="Sahifa ofset"),
    current_user: AppUser = require_permission(Module.GPS, Action.VIEW),
    db: AsyncSession = Depends(get_timescale_db),
    redis: Redis = Depends(get_redis),
) -> PaginatedTrack:
    """
    GET /gps/track/{delivery_id}

    RBAC: gps:view (agent, courier, administrator).
    IDOR: agent/courier boshqa delivery → 403/404.
    """
    await _check_rate_limit(
        redis,
        str(current_user.id),
        "track",
        _TRACK_RATE_LIMIT,
        _TRACK_RATE_WINDOW,
    )

    items, total = await service.get_track(
        db=db,
        user=current_user,
        delivery_id=delivery_id,
        limit=limit,
        offset=offset,
    )

    return PaginatedTrack(
        items=[GpsTrackOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /gps/track ───────────────────────────────────────────────────────────


@router.get(
    "/track",
    response_model=PaginatedTrack,
    status_code=200,
    summary="Foydalanuvchi+sana bo'yicha marshrut",
    description=(
        "user_id va/yoki sana bo'yicha GPS marshrut nuqtalari. "
        "agent/courier: ?user_id= boshqa ID bo'lsa → 403. "
        "administrator: istalgan user_id. "
        "?date= (YYYY-MM-DD) — recorded_at kuni bo'yicha filtr. "
        "Rate-limit: 120 so'rov/daqiqa."
    ),
)
async def get_track_by_user(
    filter_user_id: uuid.UUID | None = Query(
        default=None,
        alias="user_id",
        description=(
            "Foydalanuvchi ID bo'yicha filtr. "
            "agent/courier uchun: faqat o'z ID'si ruxsatli (boshqasi → 403). "
            "administrator uchun: ixtiyoriy."
        ),
    ),
    filter_date: date | None = Query(
        default=None,
        alias="date",
        description="Sana bo'yicha filtr — recorded_at kuni (YYYY-MM-DD)",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Sahifa hajmi"),
    offset: int = Query(default=0, ge=0, description="Sahifa ofset"),
    current_user: AppUser = require_permission(Module.GPS, Action.VIEW),
    db: AsyncSession = Depends(get_timescale_db),
    redis: Redis = Depends(get_redis),
) -> PaginatedTrack:
    """
    GET /gps/track?user_id=&date=

    RBAC: gps:view (agent, courier, administrator).
    IDOR: agent/courier boshqa user_id so'rasa → 403.
    """
    await _check_rate_limit(
        redis,
        str(current_user.id),
        "track",
        _TRACK_RATE_LIMIT,
        _TRACK_RATE_WINDOW,
    )

    items, total = await service.get_track(
        db=db,
        user=current_user,
        delivery_id=None,
        filter_user_id=filter_user_id,
        filter_date=filter_date,
        limit=limit,
        offset=offset,
    )

    return PaginatedTrack(
        items=[GpsTrackOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )
