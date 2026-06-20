"""
Auth servisi — biznes mantiq.

login()   — telefon+parol tekshirish, token juft yaratish
refresh() — refresh tokenni rotatsiya qilish (eski jti denylist ga, yangi juft ber)
logout()  — refresh jti ni denylist ga qo'shish

Denylist mantiqi:
  Redis kalit: denylist:refresh:{jti}
  TTL: token qolgan amal muddati (sekundda)
  Refresh va logout shu yerga yozadi; decode'dan oldin tekshiriladi.

Dizayn: fail-closed by design — Redis mavjud bo'lmasa token ishlamaydi.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime

import jwt as _jwt
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.core.errors import AuthAppError
from app.core.jwt import (
    TokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import AppUser
from app.modules.auth.schemas import TokenPair

logger = logging.getLogger(__name__)

# ─── Redis kalit prefiksi ────────────────────────────────────────────────────

_DENYLIST_PREFIX = "denylist:refresh:"


def _denylist_key(jti: str) -> str:
    return f"{_DENYLIST_PREFIX}{jti}"


def _mask_phone(phone: str) -> str:
    """Telefon raqamning faqat birinchi 4 belgisini ko'rsatadi."""
    return phone[:4] + "***" if len(phone) >= 4 else "***"


# ─── Denylist yordamchilari ──────────────────────────────────────────────────

async def _is_denylisted(redis: Redis, jti: str) -> bool:
    """
    Tokenning jti si denylist da borligini tekshiradi.

    Fail-closed by design: Redis o'chsa yoki vaqt tugasa xato qaytariladi —
    tekshirilmagan token qabul qilinmaydi.
    """
    try:
        return bool(await redis.exists(_denylist_key(jti)))
    except (RedisConnectionError, RedisTimeoutError) as exc:
        logger.error("denylist.check.redis_error jti=%s error=%r", jti, exc)
        raise


async def _add_to_denylist(redis: Redis, jti: str, exp: int) -> None:
    """
    jti ni denylist ga TTL bilan qo'shadi.

    TTL = token qolgan amal muddati (soniya). Muddati o'tgan bo'lsa TTL=1 (tezda tozalanadi).

    Fail-closed by design: Redis o'chsa yoki vaqt tugasa xato qaytariladi.
    """
    now_ts = int(datetime.now(UTC).timestamp())
    ttl = max(exp - now_ts, 1)
    try:
        await redis.setex(_denylist_key(jti), ttl, "1")
    except (RedisConnectionError, RedisTimeoutError) as exc:
        logger.error("denylist.add.redis_error jti=%s error=%r", jti, exc)
        raise


# ─── Login ───────────────────────────────────────────────────────────────────


async def login(
    phone: str,
    password: str,
    db: AsyncSession,
) -> TokenPair:
    """
    Telefon + parol bilan kirish.

    Tekshiruvlar:
      1. Telefon bo'yicha foydalanuvchi topish.
      2. is_active=True tekshirish.
      3. Parol solishtirish (bcrypt).

    Returns:
        TokenPair — access + refresh token juft.

    Raises:
        AuthError: Hisob topilmasa, bloklangan bo'lsa yoki parol noto'g'ri bo'lsa.
    """
    # Foydalanuvchini telefon bo'yicha topish.
    # phone EncryptedString (shifrlangan) — to'g'ridan-to'g'ri taqqoslab bo'lmaydi.
    # Blind-index orqali: blind_index(phone) == phone_bi (HMAC UNIQUE ustun).
    stmt = select(AppUser).where(AppUser.phone_bi == blind_index(phone))
    result = await db.execute(stmt)
    user: AppUser | None = result.scalar_one_or_none()

    # Vaqt hujumini (timing attack) kamaytirish uchun parol har doim tekshiriladi
    # (foydalanuvchi topilmagan holatda ham).
    # bcrypt format: $2b$12$ + 22 belgilik salt + 31 belgilik hash = jami 60 belgi.
    # Bu statik dummy hash — foydalanuvchi topilmagan holda ham bcrypt.checkpw()
    # chaqiriladi va taxminan bir xil vaqt ketadi (user enumeration himoyasi).
    # Yaratilgan: bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=12))
    dummy_hash = "$2b$12$Wf0AWCIf8MpSBNYxzLX/LuuudL6ZzMDuMdyNXzy9pyW6/.zCONapG"
    stored_hash = user.password_hash if user is not None else dummy_hash

    password_ok = verify_password(password, stored_hash)

    if user is None:
        logger.info("login.failed phone=%s reason=user_not_found", _mask_phone(phone))
        raise AuthAppError("auth.invalid_credentials", status_code=401)

    if not user.is_active:
        logger.info("login.failed phone=%s reason=account_blocked", _mask_phone(phone))
        raise AuthAppError("auth.inactive_user", status_code=403)

    if not password_ok:
        logger.info("login.failed phone=%s reason=wrong_password", _mask_phone(phone))
        raise AuthAppError("auth.invalid_credentials", status_code=401)

    logger.info("login.success phone=%s user_id=%s", _mask_phone(phone), user.id)
    return _generate_token_pair(user)


# ─── Refresh ─────────────────────────────────────────────────────────────────

async def refresh_tokens(
    refresh_token: str,
    db: AsyncSession,
    redis: Redis,
) -> TokenPair:
    """
    Refresh token rotatsiyasi.

    1. Refresh tokenni decode qilish va tip tekshirish.
    2. jti ni denylist da tekshirish (qayta ishlatilgan bo'lsa rad).
    3. Eski jti ni denylist ga qo'shish (TTL bilan).
    4. Foydalanuvchini DB dan yuklash (is_active tekshiruvi).
    5. Yangi token juft yaratish.

    Raises:
        AuthError: Token yaroqsiz, muddati o'tgan, denylist da yoki foydalanuvchi bloklangan.
    """
    # Token decode
    try:
        payload = decode_token(refresh_token)
    except TokenExpiredError:
        raise AuthAppError("auth.token_expired", status_code=401)
    except TokenError:
        raise AuthAppError("auth.token_invalid", status_code=401)

    # Tip tekshirish
    if payload.get("type") != "refresh":
        raise AuthAppError("auth.token_wrong_type", status_code=401)

    jti: str = payload.get("jti", "")
    exp: int = payload.get("exp", 0)
    sub: str = payload.get("sub", "")

    if not jti or not sub:
        raise AuthAppError("auth.token_invalid", status_code=401)

    # Denylist tekshirish (token allaqachon ishlatilganmi yoki logout qilinganmi)
    if await _is_denylisted(redis, jti):
        raise AuthAppError("auth.token_invalid", status_code=401)

    # Eski jti ni denylist ga qo'shish (rotatsiya: bir marta ishlatiladi)
    await _add_to_denylist(redis, jti, exp)

    # Foydalanuvchini yuklash
    stmt = select(AppUser).where(AppUser.id == uuid.UUID(sub))
    result = await db.execute(stmt)
    user: AppUser | None = result.scalar_one_or_none()

    if user is None:
        raise AuthAppError("auth.user_not_found", status_code=401)

    if not user.is_active:
        raise AuthAppError("auth.inactive_user", status_code=403)

    logger.info("refresh.rotated user_id=%s jti=%s", user.id, jti)
    return _generate_token_pair(user)


# ─── Logout ──────────────────────────────────────────────────────────────────

async def logout(
    refresh_token: str,
    redis: Redis,
) -> None:
    """
    Chiqish — refresh tokenni denylist ga qo'shish.

    Token muddati o'tgan bo'lsa ham denylist ga qo'shiladi (oldingi keshlardan himoya).
    Yaroqsiz token formatida xato qaytariladi.
    Faqat refresh turi token qabul qilinadi.

    Fail-closed by design: Redis o'chsa xato qaytariladi.

    Raises:
        AuthError: Token format xatosi yoki noto'g'ri token turi.
    """
    try:
        payload = decode_token(refresh_token)
    except TokenExpiredError:
        # Muddati o'tgan token: imzo TEKSHIRILADI, faqat exp o'tkazib yuboriladi.
        # verify_signature: False ishlatilmaydi — jti denylist poisoning xavfidan himoya.
        from app.core.config import settings as _settings
        try:
            payload = _jwt.decode(
                refresh_token,
                _settings.jwt_secret_key,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
        except Exception:
            raise AuthAppError("auth.token_invalid", status_code=400)
    except TokenError:
        raise AuthAppError("auth.token_invalid", status_code=400)

    # Tip tekshirish — faqat refresh token logout qila oladi
    if payload.get("type") != "refresh":
        raise AuthAppError("auth.token_wrong_type", status_code=400)

    jti: str = payload.get("jti", "")
    exp: int = payload.get("exp", 0)

    if not jti:
        raise AuthAppError("auth.token_invalid", status_code=400)

    # Denylist ga qo'shish (TTL = qolgan muddat yoki 1 son)
    await _add_to_denylist(redis, jti, exp)

    logger.info("logout jti=%s", jti)


# ─── Yordamchi ───────────────────────────────────────────────────────────────

def _generate_token_pair(user: AppUser) -> TokenPair:
    """
    Foydalanuvchi uchun yangi token juft yaratadi.

    MT1: enterprise_id token'ga qo'shildi.
      - Tenant foydalanuvchi: user.enterprise_id (UUID string)
      - superadmin: None (enterprise_id=NULL)
    """
    access = create_access_token(
        sub=str(user.id),
        role=user.role,
        branch_id=str(user.branch_id) if user.branch_id is not None else None,
        enterprise_id=str(user.enterprise_id) if user.enterprise_id is not None else None,
    )
    refresh = create_refresh_token(sub=str(user.id))
    return TokenPair(access_token=access, refresh_token=refresh, token_type="bearer")
