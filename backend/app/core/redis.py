"""
Markaziy async Redis klient.

Barcha modullarda shu dependency orqali foydalaniladi (DRY).
main.py readiness ham shu klientni ishlatadi.

Foydalanish:
    from app.core.redis import get_redis

    async def my_endpoint(redis: Redis = Depends(get_redis)):
        await redis.set("key", "value")
"""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings

# ─── Global klient singletoni ────────────────────────────────────────────────
# Ilova startup'ida bir marta yaratiladi, shutdown'da yopiladi.
# None = hali yaratilmagan yoki yopilgan.

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """
    Global Redis klientini qaytaradi.

    Agar klient hali yaratilmagan bo'lsa, yangi yaratadi (lazy init).
    Barcha modullarda bitta pool ishlatiladi.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8",
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            retry_on_timeout=False,  # sekin Redis'da RBAC cho'zilmasin; graceful degradatsiya ishlaydi
        )
    return _redis_client


async def close_redis() -> None:
    """
    Redis ulanishini yopish — ilova shutdown da chaqiriladi.

    main.py lifespan ichida chaqirish tavsiya etiladi.
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    FastAPI dependency: Redis klientini yield qiladi.

    Har so'rovda yangi ulanish ochmaydi — bitta connection pool ishlatiladi.

    Foydalanish:
        async def endpoint(redis: Redis = Depends(get_redis)):
            ...
    """
    yield get_redis_client()
