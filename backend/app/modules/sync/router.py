"""
Sync router — T13 Outbox Sync API.

Endpointlar:
  POST /sync/push  — offline operatsiyalar batchi (klient→server).
  GET  /sync/pull  — delta hodisalar (server→klient, since= kursor bilan).

Autentifikatsiya:
  Ikkala endpoint ham Bearer token talab qiladi (get_current_user dependency).
  RBAC: agent, courier, store rollari ruxsatli; administrator/accountant ham.

Rate-limit (Redis):
  Redis counter (INCR+EXPIRE) orqali foydalanuvchi+endpoint bo'yicha cheklash.
  Oshsa → 429 ("sync.rate_limited").

i18n: Accept-Language header va ?lang= query param (LocaleMiddleware orqali).

MUHIM:
  Kursor server-avtoritar monoton (seq) — klient soatiga ishonmaslik (ADR §3.5).
  Push op-darajali xato izolyatsiyasi — batch yiqilmaydi.
  Pull scope majburiy (IDOR yo'q).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.auth.router import get_current_user
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.sync import service
from app.modules.sync.schemas import PullResponse, PushRequest, PushResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])

# ─── Rate-limit konstantalari ─────────────────────────────────────────────────

_PUSH_RATE_LIMIT = 60       # max so'rov soni
_PUSH_RATE_WINDOW = 60      # sekund oyna
_PULL_RATE_LIMIT = 120      # pull ko'proq ruxsat etilgan
_PULL_RATE_WINDOW = 60


# ─── Rate-limit yordamchisi ───────────────────────────────────────────────────


async def _check_rate_limit(
    redis: Redis,
    user_id: str,
    endpoint: str,
    limit: int,
    window: int,
) -> None:
    """
    Redis INCR+EXPIRE orqali sodda token-bucket rate-limit.

    Kalit: rate:{endpoint}:{user_id}
    Oshsa: AppError("sync.rate_limited", 429).
    """
    key = f"rate:{endpoint}:{user_id}"
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window)
        if current > limit:
            raise AppError("sync.rate_limited", status_code=429)
    except AppError:
        raise
    except Exception as exc:
        # Redis xato — graceful degradation (rate-limit o'tkazib yuboriladi)
        logger.warning(
            "sync: rate-limit tekshiruvi muvaffaqiyatsiz (user_id=%s endpoint=%s): %r",
            user_id, endpoint, exc,
        )


# ─── POST /sync/push ──────────────────────────────────────────────────────────


@router.post(
    "/push",
    response_model=PushResponse,
    status_code=200,
    summary="Offline operatsiyalar batchi yuborish",
    description=(
        "Klient tomonidagi offline operatsiyalar (outbox) ni serverga yuboradi. "
        "Har op uchun alohida natija: applied|duplicate|conflict|error. "
        "Bitta op xato bo'lsa qolganlar davom etadi. "
        "client_uuid idempotentlik kafolatlanadi. "
        "Batch limit: 100 op."
    ),
)
async def push_sync(
    body: PushRequest,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> PushResponse:
    """
    POST /sync/push — offline batch operatsiyalar.

    Ruxsatli rollar: agent, courier, store, administrator, accountant.
    Rate-limit: 60 so'rov/daqiqa.
    """
    await _check_rate_limit(
        redis,
        str(current_user.id),
        "sync_push",
        _PUSH_RATE_LIMIT,
        _PUSH_RATE_WINDOW,
    )

    enterprise_id = get_current_enterprise_id(current_user)
    results = await service.push(
        ops=body.ops,
        actor_id=current_user.id,
        user=current_user,
        db=db,
        redis=redis,
        enterprise_id=enterprise_id,
    )

    return PushResponse(results=results)


# ─── GET /sync/pull ───────────────────────────────────────────────────────────


@router.get(
    "/pull",
    response_model=PullResponse,
    status_code=200,
    summary="Delta hodisalar (server→klient)",
    description=(
        "since= kursori (oxirgi ko'rilgan seq) dan keyingi hodisalar. "
        "Kursor server-avtoritar monoton (seq) — klient soatiga ishonmaslik. "
        "Faqat foydalanuvchi scope'idagi hodisalar qaytariladi (IDOR yo'q). "
        "next_cursor = yangi kursor (keyingi so'rov uchun since= qiymati). "
        "has_more = True bo'lsa yana so'rov kerak."
    ),
)
async def pull_sync(
    since: int = Query(
        default=0,
        ge=0,
        description="Oxirgi ko'rilgan seq kursor (0 = boshidan).",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Bir so'rovda maksimal hodisalar soni (max: 200).",
    ),
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> PullResponse:
    """
    GET /sync/pull?since=&limit= — delta hodisalar.

    Ruxsatli rollar: barcha autentifikatsiyalangan foydalanuvchilar.
    Rate-limit: 120 so'rov/daqiqa.
    """
    if since < 0:
        raise AppError("sync.invalid_cursor", status_code=422)

    await _check_rate_limit(
        redis,
        str(current_user.id),
        "sync_pull",
        _PULL_RATE_LIMIT,
        _PULL_RATE_WINDOW,
    )

    enterprise_id = get_current_enterprise_id(current_user)
    changes, next_cursor, has_more = await service.pull(
        since_seq=since,
        limit=limit,
        user=current_user,
        db=db,
        enterprise_id=enterprise_id,
    )

    return PullResponse(
        changes=changes,
        next_cursor=next_cursor,
        has_more=has_more,
    )
