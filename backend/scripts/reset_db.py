"""XAVFLI: barcha DATA jadvallarini TRUNCATE qiladi (schema + alembic_version SAQLANADI).

Maqsad: seed/demo ma'lumot va foydalanuvchilarni to'liq tozalash — toza production
boshlanishi uchun. Schema, migratsiya tarixi (alembic_version), RLS, triggerlar qoladi.

XAVFSIZLIK:
  - FAQAT CONFIRM_RESET=yes muhit o'zgaruvchisi bilan ishlaydi (tasodifan ishga
    tushmasligi uchun).
  - Append-only triggerlar (0018) BEFORE UPDATE OR DELETE — TRUNCATE'ga TEGMAYDI.
  - CASCADE FK bog'lanish tartibini hal qiladi.
  - gps_point (TimescaleDB, alohida baza) bu skriptga KIRMAYDI.

Foydalanish (Railway konteyneri ichida):
  CONFIRM_RESET=yes python -m scripts.reset_db
So'ng superadmin'ni qayta yarating:
  SUPERADMIN_PHONE=... SUPERADMIN_PASSWORD=... python -m scripts.create_superadmin
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# backend/ papkasidan import qilish uchun path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.db import AsyncSessionPrimary

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("reset_db")

# public sxemadagi barcha jadvallar (alembic_version'dan tashqari) — RESTART IDENTITY CASCADE
_TRUNCATE_ALL = (
    "DO $$ DECLARE r RECORD; BEGIN "
    "FOR r IN ("
    "  SELECT tablename FROM pg_tables "
    "  WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
    ") LOOP "
    "  EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE'; "
    "END LOOP; END $$;"
)


async def main() -> None:
    if os.environ.get("CONFIRM_RESET", "").strip().lower() != "yes":
        logger.error(
            "CONFIRM_RESET=yes o'rnatilmagan — to'xtatildi (xavfsizlik kafolati)."
        )
        sys.exit(1)

    async with AsyncSessionPrimary() as session:
        bind = await session.connection()
        if bind.dialect.name != "postgresql":
            logger.error("Bu skript faqat PostgreSQL uchun (SQLite emas).")
            sys.exit(1)

        logger.warning("BARCHA data jadvallari TRUNCATE qilinmoqda (schema saqlanadi)...")
        await session.execute(text(_TRUNCATE_ALL))
        await session.commit()
        logger.info(
            "Tugadi: barcha data tozalandi. Schema/migratsiya/RLS/triggerlar saqlandi. "
            "Endi superadmin'ni qayta yarating (scripts.create_superadmin)."
        )


if __name__ == "__main__":
    asyncio.run(main())
