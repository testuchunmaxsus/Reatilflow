"""
JWT token yaratish va tekshirish yordamchilari.

Xavfsizlik qarorlari:
  - PyJWT ishlatiladi (python-jose o'rniga) — CVE/algorithm confusion xataridan himoya.
  - algorithms=["HS256"] qat'iy allowlist — boshqa algoritmlar rad etiladi.
  - jti (JWT ID) har token uchun unikal UUID — denylist va rotatsiyada ishlatiladi.
  - Parol: bcrypt to'g'ridan-to'g'ri (passlib bcrypt>=4 bilan mos kelmaydi), rounds=12.

Token tuzilishi:
  access  : sub, role, branch_id, type="access",   jti, exp, iat
  refresh : sub,                  type="refresh",   jti, exp, iat
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings

# ─── Parol yordamchilari ──────────────────────────────────────────────────────
# bcrypt to'g'ridan-to'g'ri ishlatiladi (passlib bcrypt>=4.x bilan mos kelmaydi).

_BCRYPT_ROUNDS = 12


def hash_password(plain_password: str) -> str:
    """
    Parolni bcrypt bilan hashlaydi (rounds=12).

    Tekis parol hech qachon saqlanmaydi.
    Returns: bcrypt hash string (prefix $2b$).
    """
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Tekis parolni bcrypt hash bilan solishtiradi.

    Constant-time solishtirish (timing attack xavfini kamaytiradi).
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ─── Algoritm allowlist (algorithm confusion oldini olish) ───────────────────

_ALGORITHM_ALLOWLIST: list[str] = ["HS256"]


# ─── Token yaratish ──────────────────────────────────────────────────────────

def _build_token(extra_claims: dict[str, Any], expire_delta: timedelta) -> str:
    """
    Ichki yordamchi: JWT token yaratadi.

    Args:
        extra_claims: Token turiga xos qo'shimcha claimlar.
        expire_delta: Token amal qilish muddati.

    Returns:
        Imzolangan JWT string.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iat": now,
        "exp": now + expire_delta,
        "jti": str(uuid.uuid4()),
        **extra_claims,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(
    sub: str,
    role: str,
    branch_id: str | None,
) -> str:
    """
    Access token yaratadi (15 daqiqa amal qiladi).

    Claims: sub, role, branch_id, type="access", jti, exp, iat.

    Args:
        sub: Foydalanuvchi ID (UUID string).
        role: Foydalanuvchi roli (administrator | agent | courier | accountant | store).
        branch_id: Filial ID yoki None (administrator uchun).

    Returns:
        Imzolangan JWT access token.
    """
    return _build_token(
        extra_claims={
            "sub": sub,
            "role": role,
            "branch_id": str(branch_id) if branch_id is not None else None,
            "type": "access",
        },
        expire_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(sub: str) -> str:
    """
    Refresh token yaratadi (30 kun amal qiladi).

    Claims: sub, type="refresh", jti, exp, iat.

    Args:
        sub: Foydalanuvchi ID (UUID string).

    Returns:
        Imzolangan JWT refresh token.
    """
    return _build_token(
        extra_claims={
            "sub": sub,
            "type": "refresh",
        },
        expire_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
    )


# ─── Token tekshirish ────────────────────────────────────────────────────────

class TokenError(Exception):
    """Token yaroqsiz yoki muddati o'tgan."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class TokenExpiredError(TokenError):
    """Token muddati tugagan."""


def decode_token(token: str) -> dict[str, Any]:
    """
    JWT tokenni tekshirib, payload qaytaradi.

    Xavfsizlik:
      - algorithms qat'iy allowlist ["HS256"] — algorithm confusion oldini olish.
      - Muddati o'tgan token → TokenExpiredError.
      - Imzo/format xatosi → TokenError.

    Args:
        token: JWT string.

    Returns:
        Decoded payload dict (sub, role, branch_id, type, jti, exp, iat ...).

    Raises:
        TokenExpiredError: Token muddati tugagan.
        TokenError: Token yaroqsiz (imzo xatosi, format xatosi va h.k.).
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=_ALGORITHM_ALLOWLIST,  # qat'iy allowlist
        )
    except ExpiredSignatureError:
        raise TokenExpiredError("Token muddati tugagan")
    except InvalidTokenError as exc:
        raise TokenError(f"Token yaroqsiz: {exc}") from exc

    return payload
