"""
Qator-darajali himoya (Row-Level Security) — SQLAlchemy filtr yordamchilari.

`apply_store_scope(query, user)`:
  Rolga qarab SQLAlchemy WHERE sharti qo'shiladi (eski enterprise-bitta-tenant mantiq).

`get_store_visibility_filter(user) -> ColumnElement | None`:
  ADR-003 bo'yicha platforma do'konlarini (enterprise_id=NULL) ham qamrab oluvchi
  ko'rinish filtri. Kimga nima ko'rinadi:

  | Rol              | Ko'rinish                                                       |
  |------------------|-----------------------------------------------------------------|
  | superadmin       | Barchasi (filtr yo'q → None qaytaradi)                         |
  | administrator    | O'z korxona do'konlari + shartnoma qilgan platforma do'konlari  |
  | accountant       | O'z korxona do'konlari + shartnoma qilgan platforma do'konlari  |
  | agent            | Store.agent_id == user.id YOKI AgentStore orqali               |
  | store            | Store.user_id == user.id                                        |
  | courier          | Barcha do'konlar (manzil ko'rish — faqat view, filtr yo'q)     |

Eslatma:
  - `apply_store_scope` — eski branch-darajali helper (hali ishlatiladi).
  - `get_store_visibility_filter` — ADR-003 visibility helper (customers moduli).
  - Yetkazish scope'i (courier → o'z deliveries) T4/T5 modullarida
    mos delivery modeliga alohida qo'llaniladi.
  - T4/T5 modullari shu helperdan import qiladi (cross-modul SQL yo'q).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, or_, select
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


# ─── ADR-003: Platforma do'koni ko'rinish filtri ─────────────────────────────


def get_store_visibility_filter(user: AppUser) -> ColumnElement | None:
    """
    ADR-003 §B bo'yicha do'kon ko'rinish filtri.

    Platforma do'konlari (enterprise_id=NULL, is_platform_managed=True) muayyan
    foydalanuvchilarga ko'rinadigan yagona mantiq — SQL WHERE sharti sifatida
    qaytaradi. Qaytarilgan shartni `query.where(...)` ga berib ishlatiladi.

    Kimga nima ko'rinadi:
      - superadmin (enterprise_id IS NULL):
          None qaytaradi — filtr yo'q, barcha do'konlar ko'rinadi.
      - administrator | accountant:
          O'z korxona do'konlari (Store.enterprise_id == user.enterprise_id)
          YOKI shartnoma qilgan platforma do'konlari:
            Store.is_platform_managed=True AND
            Store.id IN (SELECT store_id FROM contract
                         WHERE enterprise_id == user.enterprise_id
                           AND deleted_at IS NULL)
          DIQQAT: contract.enterprise_id hozir buyer/holder korxona.
          BO'LAK C da supplier_enterprise_id qo'shilgach, shart yangilanadi.
      - agent:
          Store.agent_id == user.id
          YOKI Store.id IN (SELECT store_id FROM agent_store WHERE agent_id == user.id)
      - store:
          Store.user_id == user.id
      - courier:
          None qaytaradi — filtr yo'q (view-only, barcha manzillar).
      - Noma'lum rol:
          Deny-all: Store.id.is_(None).

    Args:
        user: Autentifikatsiyalangan AppUser.

    Returns:
        SQLAlchemy ColumnElement (WHERE sharti) yoki None (filtr yo'q).

    Qo'llanish:
        visibility = get_store_visibility_filter(user)
        if visibility is not None:
            stmt = stmt.where(visibility)
    """
    role = user.role

    # superadmin: enterprise_id=None → barcha do'konlar ko'rinadi
    if user.enterprise_id is None:
        return None

    if role in ("administrator", "accountant"):
        from app.models.contract import Contract

        # Shartnoma qilingan platforma do'konlari subquery.
        # ADR-003 Bo'lak C: supplier_enterprise_id ishlatiladi (TODO edi — hozir tuzatildi).
        # Shartnoma: do'kon (store_id) ↔ bu foydalanuvchi korxonasi (supplier_enterprise_id).
        contracted_platform_subq = (
            select(Contract.store_id)
            .where(
                Contract.supplier_enterprise_id == user.enterprise_id,
                Contract.deleted_at.is_(None),
            )
            .scalar_subquery()
        )

        return or_(
            # O'z korxona do'konlari (eski + yangi)
            Store.enterprise_id == user.enterprise_id,
            # Shartnoma qilingan platforma do'konlari
            and_(
                Store.is_platform_managed.is_(True),
                Store.id.in_(contracted_platform_subq),
            ),
        )

    elif role == "agent":
        agent_store_subq = (
            select(AgentStore.store_id)
            .where(AgentStore.agent_id == user.id)
            .scalar_subquery()
        )
        return or_(
            Store.agent_id == user.id,
            Store.id.in_(agent_store_subq),
        )

    elif role == "store":
        return Store.user_id == user.id

    elif role == "courier":
        # Kuryer barcha do'kon manzillarini ko'ra oladi (delivery scope uchun)
        return None

    else:
        # Noma'lum rol → deny-all (hech narsa ko'rinmaydi)
        logger.warning(
            "get_store_visibility_filter: noma'lum rol uchun deny-all qo'llanildi",
            extra={"role": role, "user_id": str(user.id)},
        )
        return Store.id.is_(None)
