"""
RBAC servis qatlami — ruxsatlar tekshiruvi va Redis keshi.

`get_permissions_for_role(role, redis)`:
  - Redis'dan `rbac:perms:{role}` kalitini o'qiydi (5 daqiqa TTL).
  - Yo'q bo'lsa matritsadan yuklab keshlaydi.
  - Redis o'chsa (ConnectionError) → matritsadan to'g'ridan-to'g'ri (fail-closed, matritsa zaxira manbai, log yoziladi).

`has_permission(user, module, action)`:
  - Sof sinxron yordamchi (Redis chaqirmaydi).
  - Matritsadan foydalanadi — past kechikish uchun.
"""

from __future__ import annotations

import json
import logging

from redis.asyncio import Redis

from app.models.user import AppUser
from app.modules.rbac.permissions import ROLE_PERMISSIONS

logger = logging.getLogger(__name__)

# Redis kesh kaliti prefiksi va TTL (soniyada)
_CACHE_KEY_PREFIX = "rbac:perms:"
_CACHE_TTL_SECONDS = 5 * 60  # 5 daqiqa


# ─── Redis keshli ruxsatlar olish ────────────────────────────────────────────


async def get_permissions_for_role(role: str, redis: Redis) -> set[str]:
    """
    Berilgan rol uchun ruxsatlar to'plamini qaytaradi.

    1. Redis'dan `rbac:perms:{role}` o'qiydi (JSON massiv sifatida saqlangan).
    2. Yo'q bo'lsa → matritsadan yuklaydi va Redis'ga 5 daqiqaga keshlaydi.
    3. Redis o'chsa → WARNING log va matritsadan to'g'ridan-to'g'ri qaytaradi (fail-closed, matritsa zaxira manbai).

    Noto'g'ri rol berilsa bo'sh to'plam qaytaradi (hech narsa ruxsat yo'q).
    """
    cache_key = f"{_CACHE_KEY_PREFIX}{role}"

    # ─── 1. Redis'dan o'qishga harakat ──────────────────────────────────────
    try:
        cached = await redis.get(cache_key)
        if cached is not None:
            return set(json.loads(cached))
    except Exception as exc:
        logger.warning(
            "RBAC: Redis'dan ruxsatlar o'qib bo'lmadi — matritsadan yuklanmoqda",
            extra={"role": role, "error": str(exc)},
        )

    # ─── 2. Matritsadan yuklash ──────────────────────────────────────────────
    perms: set[str] = ROLE_PERMISSIONS.get(role, set())

    # ─── 3. Redis'ga keshlashga harakat ─────────────────────────────────────
    try:
        await redis.set(
            cache_key,
            json.dumps(sorted(perms)),  # sorted → deterministik JSON
            ex=_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "RBAC: Redis'ga ruxsatlar keshlab bo'lmadi — matritsa ishlatilmoqda",
            extra={"role": role, "error": str(exc)},
        )

    return perms


# ─── Sof sinxron tekshiruv yordamchisi ───────────────────────────────────────


def has_permission(user: AppUser, module: str, action: str) -> bool:
    """
    Foydalanuvchining berilgan modul:amalga ruxsati borligini tekshiradi.

    Redis chaqiriqsiz — matritsadan to'g'ridan-to'g'ri.
    Tezkor (HTTP middleware darajasida ishlatish uchun mos).

    Args:
        user:   Autentifikatsiyalangan AppUser obyekti.
        module: Modul nomi (Module enum yoki string, masalan "catalog").
        action: Amal nomi (Action enum yoki string, masalan "view").

    Returns:
        True — ruxsat mavjud; False — ruxsat yo'q.
    """
    perm_key = f"{module}:{action}"
    role_perms = ROLE_PERMISSIONS.get(user.role, set())
    return perm_key in role_perms
