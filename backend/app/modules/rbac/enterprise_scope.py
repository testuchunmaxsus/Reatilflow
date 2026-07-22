"""
Enterprise (tenant) scope yordamchilari — MT1 Foundation.

ADR-002 §2.6 bo'yicha:
  - enterprise_id JWT token'dan server-avtoritar olinadi (query param'dan EMAS).
  - Har query enterprise bo'yicha filtrlanadi (MT2 da har modulga qo'llanadi).
  - superadmin enterprise_id=None bilan ishlaydi (cross-tenant kirish).

Eksport:
  get_current_enterprise_id(user)      — joriy user enterprise_id qaytaradi
  apply_enterprise_filter(query, user, col) — query'ga enterprise WHERE qo'shadi
  EnterpriseScope                      — FastAPI dependency (MT2 uchun tayyorlangan)

MT1 doirasida:
  - Helper funksiyalar yozildi.
  - Per-modul QO'LLASH MT2 da bo'ladi.
  - Bu faylda faqat helper + namuna.
"""

from __future__ import annotations

import uuid
import logging
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import set_current_enterprise
from app.models.user import AppUser

logger = logging.getLogger(__name__)


# ─── Enterprise ID olish ──────────────────────────────────────────────────────

def get_current_enterprise_id(user: AppUser) -> uuid.UUID | None:
    """
    Joriy foydalanuvchidan enterprise_id qaytaradi VA so'rov kontekstiga o'rnatadi.

    Args:
        user: Autentifikatsiyalangan AppUser (enterprise_id atributi bor).

    Returns:
        UUID yoki None (superadmin uchun).

    Xavfsizlik:
        enterprise_id SERVER'dan (user ob'ektidan) olinadi.
        Yon ta'sir: ContextVar'ga o'rnatiladi — OutboxEvent va boshqa
        avto-yozuvlar shu kontekstdan enterprise_id oladi (MT2).
    """
    eid = user.enterprise_id
    set_current_enterprise(eid)
    return eid


def get_enterprise_id_from_token_payload(payload: dict[str, Any]) -> uuid.UUID | None:
    """
    JWT payload'dan enterprise_id ni UUID sifatida qaytaradi.

    Args:
        payload: Decode qilingan JWT payload dict.

    Returns:
        UUID yoki None (superadmin yoki enterprise_id yo'q bo'lsa).
    """
    raw = payload.get("enterprise_id")
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        logger.warning("JWT enterprise_id UUID formatida emas: %r", raw)
        return None


# ─── Query filtrash yordamchisi ───────────────────────────────────────────────

def apply_enterprise_filter(
    query: Select,
    enterprise_id: uuid.UUID | None,
    column: Any,
) -> Select:
    """
    SQLAlchemy SELECT so'roviga enterprise_id WHERE sharti qo'shadi.

    Args:
        query:         select(...) so'rov.
        enterprise_id: Korxona UUID (None bo'lsa filtr qo'shilmaydi — superadmin).
        column:        Model.enterprise_id ustun referensi.

    Returns:
        enterprise WHERE qo'shilgan so'rov (immutable — asl o'zgarmaydi).

    Qo'llanish (MT2 da har modul service'ida):
        stmt = select(Store)
        stmt = apply_enterprise_filter(stmt, current_user.enterprise_id, Store.enterprise_id)
        result = await db.execute(stmt)

    Superadmin (enterprise_id=None):
        Filtr QO'SHILMAYDI — superadmin barcha korxona ma'lumotini ko'ra oladi.
        (ADR-002 §2.4: superadmin faqat korxona boshqaruvi, biznes ma'lumotiga kirmasligi
         tavsiya etiladi — bu MT2/MT4 da IDOR testlari bilan tekshiriladi.)
    """
    if enterprise_id is None:
        # superadmin — filtr yo'q
        return query
    return query.where(column == enterprise_id)


def require_enterprise_filter(
    query: Select,
    enterprise_id: uuid.UUID | None,
    column: Any,
) -> Select:
    """
    MAJBURIY enterprise filtr — superadmin ham cheklanadi.

    apply_enterprise_filter'dan farqi:
        enterprise_id=None bo'lsa ham filtr qo'shiladi (NULL WHERE).
        Bu superadmin tenant ma'lumotiga kirishini oldini oladi.

    Args:
        query:         select(...) so'rov.
        enterprise_id: Korxona UUID.
        column:        Model.enterprise_id ustun referensi.

    Returns:
        enterprise WHERE qo'shilgan so'rov.
    """
    return query.where(column == enterprise_id)


# ─── RLS session variable o'rnatish ──────────────────────────────────────────

async def set_rls_enterprise_var(
    session: AsyncSession,
    enterprise_id: uuid.UUID | None,
) -> None:
    """
    PostgreSQL session'ga app.current_enterprise_id o'zgaruvchisini o'rnatadi.

    DIQQAT: bu funksiya endi mustaqil setter EMAS — drift bo'lmasligi uchun
    yagona haqiqiy manba app.core.db._set_rls_var() ga delegatsiya qilinadi
    (u yerda set_config(..., true) bind-parametr bilan ishlatiladi; SET LOCAL
    bilan bind berish asyncpg'da PostgresSyntaxError beradi).

    Amaldagi wiring: bu funksiya emas, get_current_user()
    (app/modules/auth/router.py) ichida _set_rls_var() to'g'ridan-to'g'ri
    chaqiriladi. Bu funksiya faqat orqaga moslik (eski chaqiruvchilar) uchun
    saqlanadi.

    Args:
        session:       AsyncSession (primary yoki replica).
        enterprise_id: Joriy korxona UUID yoki None (superadmin).
    """
    from app.core.db import _set_rls_var

    await _set_rls_var(session, enterprise_id)
