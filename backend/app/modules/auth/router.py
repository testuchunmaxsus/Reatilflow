"""
Auth router — /auth prefiksi bilan main.py ga ulanadi.

Endpointlar:
  POST /auth/login    — telefon + parol, token juft qaytaradi
  POST /auth/refresh  — refresh token rotatsiyasi
  POST /auth/logout   — refresh tokenni denylist ga qo'shish
  GET  /auth/me       — joriy foydalanuvchi ma'lumotlari (access token)

Dependency:
  get_current_user() — Bearer access tokenni decode qilib foydalanuvchini yuklaydi.
  Bu dependency T2 (RBAC) da kengaytiriladi (has_permission bilan).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AuthAppError
from app.core.jwt import TokenError, TokenExpiredError, decode_token
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
)
from app.modules.auth.service import login, logout, refresh_tokens
from app.modules.rbac.service import get_permissions_for_role

router = APIRouter(tags=["auth"])

# HTTPBearer — Authorization: Bearer <token> headerini o'qiydi
_bearer = HTTPBearer(auto_error=False)


# ─── get_current_user dependency ─────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AppUser:
    """
    FastAPI dependency: access tokenni tekshirib, joriy foydalanuvchini qaytaradi.

    T2 (RBAC) da bu dependency kengaytiriladi — has_permission() shu yerdan foydalanadi.

    Raises:
        HTTPException 401: Token yo'q, yaroqsiz yoki muddati tugagan.
        HTTPException 403: Hisob bloklangan.
    """
    if credentials is None:
        raise AuthAppError(
            "auth.authentication_required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise AuthAppError("auth.token_expired", status_code=status.HTTP_401_UNAUTHORIZED)
    except TokenError:
        raise AuthAppError("auth.token_invalid", status_code=status.HTTP_401_UNAUTHORIZED)

    # Token turi tekshirish — faqat access token
    if payload.get("type") != "access":
        raise AuthAppError(
            "auth.token_wrong_type",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    sub: str = payload.get("sub", "")
    if not sub:
        raise AuthAppError("auth.token_invalid", status_code=status.HTTP_401_UNAUTHORIZED)

    # Foydalanuvchini DB dan yuklash
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise AuthAppError("auth.token_invalid", status_code=status.HTTP_401_UNAUTHORIZED)

    stmt = select(AppUser).where(AppUser.id == user_id)
    result = await db.execute(stmt)
    user: AppUser | None = result.scalar_one_or_none()

    if user is None:
        raise AuthAppError("auth.user_not_found", status_code=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        raise AuthAppError("auth.inactive_user", status_code=status.HTTP_403_FORBIDDEN)

    return user


# ─── Endpointlar ─────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Tizimga kirish",
    description=(
        "Telefon raqam va parol bilan kirish. "
        "Muvaffaqiyatli bo'lsa access token (15 daqiqa) va "
        "refresh token (30 kun, rotatsiyali) qaytaradi."
    ),
    responses={
        200: {"description": "Muvaffaqiyatli kirish — token juft qaytadi"},
        401: {"description": "Noto'g'ri telefon yoki parol"},
        403: {"description": "Hisob bloklangan"},
    },
)
async def auth_login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Telefon + parol bilan kirish, token juft qaytaradi."""
    return await login(phone=body.phone, password=body.password, db=db)


@router.post(
    "/refresh",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Token yangilash (rotatsiya)",
    description=(
        "Refresh token bilan yangi token juft olish. "
        "Eski refresh token denylist ga qo'shiladi (bir martalik). "
        "Yangi access (15 daqiqa) va refresh (30 kun) token qaytariladi."
    ),
    responses={
        200: {"description": "Yangi token juft"},
        401: {"description": "Refresh token yaroqsiz, muddati o'tgan yoki allaqachon ishlatilgan"},
        403: {"description": "Hisob bloklangan"},
    },
)
async def auth_refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    """Refresh token rotatsiyasi — eski token bekor qilinadi, yangi juft qaytaradi."""
    return await refresh_tokens(
        refresh_token=body.refresh_token,
        db=db,
        redis=redis,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Tizimdan chiqish",
    description=(
        "Refresh tokenni denylist ga qo'shib, sessiyani yakunlaydi. "
        "Klient tomonida access token ham o'chirilishi kerak."
    ),
    responses={
        204: {"description": "Muvaffaqiyatli chiqish"},
        400: {"description": "Refresh token format xatosi"},
    },
)
async def auth_logout(
    body: LogoutRequest,
    redis: Redis = Depends(get_redis),
) -> None:
    """Refresh tokenni denylist ga qo'shib sessiyani yakunlaydi."""
    await logout(refresh_token=body.refresh_token, redis=redis)


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    summary="Joriy foydalanuvchi",
    description=(
        "Access token (Bearer) dan joriy foydalanuvchi ma'lumotlarini qaytaradi. "
        "Token yaroqsiz yoki muddati o'tgan bo'lsa 401 qaytaradi. "
        "T2 RBAC: javobda rolning barcha ruxsatlari (`permissions`) ham qaytariladi."
    ),
    responses={
        200: {"description": "Joriy foydalanuvchi ma'lumotlari (ruxsatlar bilan)"},
        401: {"description": "Token yaroqsiz yoki yo'q"},
        403: {"description": "Hisob bloklangan"},
    },
)
async def auth_me(
    current_user: AppUser = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> MeResponse:
    """
    Joriy autentifikatsiyalangan foydalanuvchi profilini qaytaradi.

    T2 kengaytmasi: `permissions` maydoni rolning barcha ruxsatlarini o'z ichiga oladi
    (Redis kesh orqali, graceful degradation mavjud).
    """
    perms = await get_permissions_for_role(current_user.role, redis)
    data = MeResponse.model_validate(current_user)
    data.permissions = sorted(perms)
    return data
