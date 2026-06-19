"""
Qator-darajali himoya (Row-Level Security) — SQLAlchemy filtr yordamchilari.

`scope_filter(user, query)` yoki `apply_store_scope(query, user)`:
  Rolga qarab SQLAlchemy WHERE sharti qo'shiladi:

  | Rol           | Do'kon filtrasi                                    |
  |---------------|----------------------------------------------------|
  | administrator | branch_id bo'yicha (yoki barchasi, agar None)      |
  | accountant    | branch_id bo'yicha (yoki barchasi, agar None)      |
  | agent         | Store.agent_id == user.id YOKI AgentStore orqali   |
  | store         | Store.id == user's store (user.id bilan bog'liq)   |
  | courier       | manzil ko'rish uchun barcha do'konlar (faqat view) |

Eslatma:
  - Bu helper faqat `Store` modeliga bog'liq filtr qaytaradi.
  - Yetkazish scope'i (courier → o'z deliveries) T4/T5 modullarida
    mos delivery modeliga alohida qo'llaniladi.
  - T4/T5 modullari shu helperdan import qiladi (cross-modul SQL yo'q).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import AgentStore, Store
from app.models.user import AppUser

logger = logging.getLogger(__name__)


def apply_store_scope(query: Select, user: AppUser) -> Select:
    """
    Berilgan SQLAlchemy SELECT so'roviga rol asosida WHERE sharti qo'shadi.

    Args:
        query: `select(Store)` yoki Store ustunlarini o'z ichiga olgan so'rov.
        user:  Joriy autentifikatsiyalangan foydalanuvchi.

    Returns:
        Filtr qo'shilgan yangi SELECT (iммutabel — asl so'rov o'zgartirilmaydi).

    Qo'llanish:
        stmt = select(Store)
        stmt = apply_store_scope(stmt, current_user)
        result = await db.execute(stmt)
    """
    role = user.role

    if role == "administrator":
        # Branch_id cheklovi — agar admin bitta filialga biriktirilgan bo'lsa
        if user.branch_id is not None:
            query = query.where(Store.branch_id == user.branch_id)
        # branch_id=None → barcha filiallar, filtr qo'shilmaydi

    elif role == "accountant":
        # Buxgalter ham branch_id bo'yicha
        if user.branch_id is not None:
            query = query.where(Store.branch_id == user.branch_id)

    elif role == "agent":
        # Agent faqat o'ziga biriktirilgan do'konlarni ko'radi — BITTA so'rov:
        #   Store.agent_id == user.id  (asosiy biriktirish)
        #   yoki AgentStore.agent_id == user.id (qo'shimcha ko'p-ko'p)
        # N+1 muammo: avval 2 ta alohida DB so'rov bo'lgan — endi OR+subquery bilan birlashtirildi.
        agent_store_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        query = query.where(
            or_(
                Store.agent_id == user.id,
                Store.id.in_(agent_store_subq),
            )
        )

    elif role == "store":
        # T5: Store.user_id FK qo'shildi — store egasi faqat o'z do'konini ko'radi.
        # Avvalgi DENY-ALL (IDOR xavfi sabab) T5 da tuzatildi.
        query = query.where(Store.user_id == user.id)

    elif role == "courier":
        # Kuryer do'kon manzilini ko'rish uchun barcha do'konlarga ega
        # (faqat view ruxsati — delivery scope alohida qo'llaniladi)
        pass  # filtr yo'q — barcha do'kon manzillarini ko'ra oladi

    else:
        # Noma'lum rol — hech narsani ko'rsatma (deny-by-default)
        logger.warning(
            "RBAC scope: noma'lum rol uchun deny-all qo'llanildi",
            extra={"role": role, "user_id": str(user.id)},
        )
        query = query.where(Store.id.is_(None))  # hech narsa qaytmaydi

    return query


async def get_user_store_ids(user: AppUser, db: AsyncSession) -> list[Any]:
    """
    Agent yoki store roli uchun foydalanuvchiga ruxsat etilgan
    do'kon ID larini qaytaradi.

    T4/T5 modullari bog'liq filtr uchun shu helperdan foydalanadi.

    Returns:
        UUID ro'yxati — bo'sh ro'yxat = hech narsa ruxsat emas.
    """
    role = user.role

    if role in ("administrator", "accountant"):
        # Barcha do'konlar (branch_id filtrini apply_store_scope da qo'llash)
        stmt = select(Store.id)
        if user.branch_id is not None:
            stmt = stmt.where(Store.branch_id == user.branch_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    elif role == "agent":
        # N+1 tuzatildi: ikkita alohida so'rov o'rniga OR+scalar_subquery bilan BITTA so'rov.
        agent_store_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        stmt = select(Store.id).where(
            or_(
                Store.agent_id == user.id,
                Store.id.in_(agent_store_subq),
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    elif role == "store":
        # T5: Store.user_id FK qo'shildi — store egasi faqat o'z do'kon ID sini oladi.
        # Avvalgi DENY-ALL (IDOR xavfi sabab) T5 da tuzatildi.
        stmt = select(Store.id).where(Store.user_id == user.id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    elif role == "courier":
        # Kuryer barcha do'kon manzillarini ko'ra oladi
        stmt = select(Store.id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    return []
