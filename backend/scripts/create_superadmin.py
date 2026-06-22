"""
Superadmin bootstrap skripti — MT4.

Foydalanish:
    cd backend
    python -m scripts.create_superadmin

Muhit o'zgaruvchilari:
    SUPERADMIN_PHONE    — superadmin telefon raqami (MAJBURIY)
    SUPERADMIN_PASSWORD — superadmin paroli (MAJBURIY)

Idempotent: mavjud bo'lsa yangilamaydi, faqat xabar beradi.

Qoidalar:
  - superadmin enterprise_id=NULL (korxonaga tegishli emas).
  - Parol HECH QACHON kodga hardcode qilinmaydi.
  - Migratsiyada parol hardcode QILINMAYDI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# backend/ papkasidan import qilish uchun path ni sozlash
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.core.db import AsyncSessionPrimary
from app.core.jwt import hash_password
from app.models.user import AppUser

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("create_superadmin")


async def create_superadmin(db: AsyncSession) -> None:
    """
    Superadmin foydalanuvchini idempotent tarzda yaratadi.

    Muhit o'zgaruvchilari:
      SUPERADMIN_PHONE    — telefon raqami
      SUPERADMIN_PASSWORD — parol

    Raises:
        SystemExit: agar muhit o'zgaruvchilari o'rnatilmagan bo'lsa.
    """
    phone = os.environ.get("SUPERADMIN_PHONE", "").strip()
    password = os.environ.get("SUPERADMIN_PASSWORD", "").strip()

    if not phone:
        logger.error(
            "SUPERADMIN_PHONE muhit o'zgaruvchisi o'rnatilmagan!\n"
            "  export SUPERADMIN_PHONE='+998XXXXXXXXX'\n"
            "  export SUPERADMIN_PASSWORD='<kuchli_parol>'"
        )
        sys.exit(1)

    if not password:
        logger.error(
            "SUPERADMIN_PASSWORD muhit o'zgaruvchisi o'rnatilmagan!\n"
            "  export SUPERADMIN_PASSWORD='<kuchli_parol>'"
        )
        sys.exit(1)

    if len(password) < 8:
        logger.error(
            "SUPERADMIN_PASSWORD kamida 8 ta belgidan iborat bo'lishi shart!"
        )
        sys.exit(1)

    # Mavjudligini tekshirish (idempotent)
    bi = blind_index(phone)
    stmt = select(AppUser).where(AppUser.phone_bi == bi)
    result = await db.execute(stmt)
    existing: AppUser | None = result.scalar_one_or_none()

    if existing is not None:
        if existing.role == "superadmin":
            logger.info(
                "Superadmin allaqachon mavjud: phone=%s id=%s — hech narsa o'zgarmadi.",
                phone[:4] + "***",
                str(existing.id),
            )
        else:
            logger.warning(
                "Bu telefon raqam allaqachon boshqa rol bilan ro'yxatdan o'tgan: "
                "phone=%s role=%s id=%s — o'zgartirilmadi.",
                phone[:4] + "***",
                existing.role,
                str(existing.id),
            )
        return

    # Superadmin yaratish
    superadmin = AppUser(
        full_name="Superadmin",
        phone=phone,
        role="superadmin",
        branch_id=None,
        locale="uz",
        password_hash=hash_password(password),
        biometric_enrolled=False,
        is_active=True,
        enterprise_id=None,  # superadmin korxonasiz
    )
    # phone_bi event listener (before_insert) orqali avtomatik to'ldiriladi
    db.add(superadmin)
    await db.flush()

    logger.info(
        "Superadmin muvaffaqiyatli yaratildi: id=%s phone=%s enterprise_id=NULL",
        str(superadmin.id),
        phone[:4] + "***",
    )


async def main() -> None:
    """Skriptni ishga tushiradi."""
    logger.info("Superadmin bootstrap skripti boshlanmoqda...")
    async with AsyncSessionPrimary() as session:
        try:
            await create_superadmin(session)
            await session.commit()
            logger.info("Commit: o'zgarishlar saqlandi.")
        except SystemExit:
            raise
        except Exception as exc:
            await session.rollback()
            logger.error("Xato: %r — rollback qilindi.", exc)
            raise


if __name__ == "__main__":
    asyncio.run(main())
