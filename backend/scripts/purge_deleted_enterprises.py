"""XAVFLI: soft-delete qilingan korxonalarni (deleted_at IS NOT NULL) va ularning
BARCHA bog'liq ma'lumotini (foydalanuvchilar, gps, attendance, buyurtma, store,
catalog va h.k.) butunlay o'chiradi.

AKTIV korxonalar (deleted_at IS NULL — masalan "Ibrat Fayz") va superadmin
(enterprise_id IS NULL) TEGILMAYDI.

Maqsad: diagnostika test korxonalari (_DIAG_*) qoldiqlarini tozalash — superadmin
panelidagi foydalanuvchilar ro'yxatini toza qilish.

XAVFSIZLIK:
  - Faqat CONFIRM_PURGE=yes muhit o'zgaruvchisi bilan ishlaydi.
  - session_replication_role=replica — append-only triggerlar (0018) va FK
    cheklovlarini vaqtincha o'chiradi (faqat shu sessiyada).
  - Faqat enterprise_id ustuni bor jadvallardan, soft-delete korxona id'lari bo'yicha.

Foydalanish (Railway konteyneri ichida):
  CONFIRM_PURGE=yes python -m scripts.purge_deleted_enterprises
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.db import AsyncSessionPrimary

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("purge_deleted")

# Soft-delete korxonalar (deleted_at IS NOT NULL) — qayta ishlatiladigan subquery
_DELETED_SUBQ = "(SELECT id FROM enterprise WHERE deleted_at IS NOT NULL)"


async def main() -> None:
    if os.environ.get("CONFIRM_PURGE", "").strip().lower() != "yes":
        logger.error("CONFIRM_PURGE=yes o'rnatilmagan — to'xtatildi (xavfsizlik).")
        sys.exit(1)

    async with AsyncSessionPrimary() as session:
        bind = await session.connection()
        if bind.dialect.name != "postgresql":
            logger.error("Faqat PostgreSQL uchun.")
            sys.exit(1)

        count = (
            await session.execute(
                text("SELECT count(*) FROM enterprise WHERE deleted_at IS NOT NULL")
            )
        ).scalar_one()
        if not count:
            logger.info("Soft-delete qilingan korxona yo'q — tozalashga hojat yo'q.")
            return
        logger.warning("Purge: %d soft-delete korxona va ularning ma'lumoti...", count)

        # FK + append-only triggerlarni shu sessiyada o'chirib turamiz
        await session.execute(text("SET session_replication_role = replica"))

        # enterprise_id ustuni bor barcha public jadvallar
        tables = (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE column_name = 'enterprise_id' AND table_schema = 'public'"
                )
            )
        ).scalars().all()

        total_rows = 0
        for tbl in tables:
            result = await session.execute(
                text(f'DELETE FROM "{tbl}" WHERE enterprise_id IN {_DELETED_SUBQ}')
            )
            deleted = result.rowcount or 0
            if deleted:
                logger.info("  %s: %d qator", tbl, deleted)
            total_rows += deleted

        # Korxonalarning o'zi (oxirida)
        ent_result = await session.execute(
            text("DELETE FROM enterprise WHERE deleted_at IS NOT NULL")
        )

        await session.execute(text("SET session_replication_role = origin"))
        await session.commit()
        logger.info(
            "Tugadi: %d bog'liq qator + %d korxona o'chirildi.",
            total_rows,
            ent_result.rowcount or 0,
        )


if __name__ == "__main__":
    asyncio.run(main())
