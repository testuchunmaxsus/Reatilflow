"""
Arq worker — push bildirishnomalar davriy ishlov berish — T19.

MUHIM: Bu fayl production uchun arq (async redis queue) worker ta'rifini o'z ichiga oladi.
Sinxron testlash uchun `service.process_pending_pushes(db, provider)` to'g'ridan-to'g'ri ishlating.

Arq konfiguratsiyasi:
  - Broker: Redis (config.redis_url yoki REDIS_DB_QUEUE)
  - Davriy vazifa: har N soniyada push_worker_task() chaqiriladi.
  - cron_jobs yoki on_startup + periodic pattern.

Ishga tushirish (production):
  cd backend && arq app.modules.push.worker.WorkerSettings

Muhim eslatmalar:
  - Arq worker API processga parallel ishlamaydi — alohida jarayon.
  - Worker bir vaqtning o'zida bitta push_worker_task() chaqiradi (default).
  - Concurrency kerak bo'lsa max_jobs > 1 o'rnating.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


# ─── Arq task ────────────────────────────────────────────────────────────────


async def push_worker_task(ctx: dict[str, Any]) -> str:
    """
    Arq davriy vazifasi — push bildirishnomalarni qayta ishlaydi.

    Har ishga tushganda:
      1. DB sessiya ochiladi.
      2. process_pending_pushes() chaqiriladi.
      3. Natija log ga yoziladi.

    Args:
        ctx: Arq context (startup da to'ldiriladi: db_session_factory, provider).

    Returns:
        Natija matni (log uchun).
    """
    from app.modules.push.service import process_pending_pushes

    db_session_factory: async_sessionmaker[AsyncSession] = ctx["db_session_factory"]
    provider = ctx["push_provider"]

    async with db_session_factory() as db:
        try:
            count = await process_pending_pushes(db=db, provider=provider)
            await db.commit()
            logger.info("push_worker_task: %d push qayta ishlandi", count)
            return f"processed={count}"
        except Exception as exc:
            await db.rollback()
            logger.error("push_worker_task: xato", exc_info=exc)
            raise


# ─── Arq WorkerSettings ───────────────────────────────────────────────────────


class WorkerSettings:
    """
    Arq worker konfiguratsiyasi.

    Production da:
      arq app.modules.push.worker.WorkerSettings

    Davriy ishga tushirish intervali: PUSH_POLL_INTERVAL_SECONDS sekund
    (default: 30 soniya).

    Env:
      REDIS_URL — Redis broker URL (app.core.config.settings.redis_url)
      FCM_SERVER_KEY — FCM server kaliti (placeholder, env dan)
      Boshqa push sozlamalari config.py da.
    """

    # Davriy ishga tushirish oraligi (sekunda)
    PUSH_POLL_INTERVAL: int = 30

    @classmethod
    def get_redis_settings(cls) -> Any:
        """Redis sozlamalarini qaytaradi."""
        from arq.connections import RedisSettings  # type: ignore[import]
        from app.core.config import settings
        # Redis URL parsing: redis://:password@host:port/db
        return RedisSettings.from_dsn(settings.redis_url)

    # Arq cron job ta'rifi — alternative yondashuv: cron_jobs ro'yxati
    # (arq >= 0.25 da cron_jobs qo'llab-quvvatlanadi)
    # Biz on_startup + periodic task pattern ishlatamiz:

    @staticmethod
    async def on_startup(ctx: dict[str, Any]) -> None:
        """
        Worker ishga tushganda DB sessiya factory va push provider yaratiladi.
        """
        from app.core.config import settings
        from app.modules.push.provider import get_push_provider

        engine = create_async_engine(settings.database_url, echo=False)
        db_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        ctx["engine"] = engine
        ctx["db_session_factory"] = db_session_factory
        ctx["push_provider"] = get_push_provider()
        logger.info("push worker: startup — DB va provider tayyor")

    @staticmethod
    async def on_shutdown(ctx: dict[str, Any]) -> None:
        """Worker o'chganda resurslarni tozalaydi."""
        engine = ctx.get("engine")
        if engine:
            await engine.dispose()
        logger.info("push worker: shutdown — resurslar tozalandi")

    # Arq funksiyalar ro'yxati
    functions = [push_worker_task]

    # Davriy ishga tushirish (arq >= 0.25 cron_jobs):
    # cron_jobs = [cron(push_worker_task, second={0, 30})]  # har 30 soniya
    # Eslatma: arq versiyasiga qarab cron sintaksisi farq qiladi.
    # Hozir: function qo'lda yoki scheduler (Celery Beat analog) orqali chaqiriladi.
