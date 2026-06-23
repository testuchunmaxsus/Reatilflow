"""
Expiry (muddat) yordamchi funksiyalari — MP4.

Funksiyalar:
  is_expired(inv, now)           — expiry_date < now.date()
  is_near_expiry(inv, now, days) — expiry_date <= now.date() + timedelta(days) va hali o'tmagan.
  days_to_expiry(inv, now)       — nechi kun qolganini qaytaradi (None agar expiry_date yo'q).

StoreInventory modeliga bog'liq emas (duck-typing) — har qanday
`expiry_date: date | None`, `status: str` maydonlari bo'lgan obyektda ishlaydi.

DIZAYN:
  - Solishtirish DATE darajasida (vaqt soati ahamiyatsiz) — expiry_date Date ustun.
  - Barcha solishtiruvlar UTC now.date() ga nisbatan.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


def _today(now: datetime | None = None) -> date:
    """UTC bugungi sanani qaytaradi. now None bo'lsa hozirgi vaqt ishlatiladi."""
    if now is None:
        return datetime.now(timezone.utc).date()
    if now.tzinfo is None:
        # timezone-naive → UTC deb qabul qilinadi
        return now.date()
    return now.astimezone(timezone.utc).date()


def is_expired(inv: Any, now: datetime | None = None) -> bool:
    """
    Inventar partiyasi muddati o'tganini tekshiradi.

    Holat: status == 'expired' YOKI expiry_date < bugun.

    Args:
        inv: StoreInventory yoki expiry_date/status maydonlari bo'lgan obyekt.
        now: Tekshirish vaqti (None = hozir UTC).

    Returns:
        True — muddati o'tgan; False — yo'q yoki expiry_date belgilanmagan.
    """
    # status='expired' — bazada allaqachon belgilangan
    if getattr(inv, "status", None) == "expired":
        return True

    exp: date | None = getattr(inv, "expiry_date", None)
    if exp is None:
        return False

    today = _today(now)
    return exp < today


def is_near_expiry(inv: Any, now: datetime | None = None, days: int = 3) -> bool:
    """
    Inventar partiyasi yaqin orada muddati tugashini tekshiradi.

    Shart: expiry_date <= bugun + days VA hali o'tmagan (expiry_date >= bugun).

    Args:
        inv:  StoreInventory yoki expiry_date maydonli obyekt.
        now:  Tekshirish vaqti (None = hozir UTC).
        days: Chegaradagi kunlar soni (masalan, 3 kun).

    Returns:
        True — yaqinda tugaydi; False — yo'q, expiry_date belgilanmagan yoki uzoq.
    """
    exp: date | None = getattr(inv, "expiry_date", None)
    if exp is None:
        return False

    today = _today(now)
    # Allaqachon o'tgan → near_expiry emas (expired)
    if exp < today:
        return False

    deadline = today + timedelta(days=days)
    return exp <= deadline


def days_to_expiry(inv: Any, now: datetime | None = None) -> int | None:
    """
    Muddatgacha qolgan kunlar sonini qaytaradi.

    Args:
        inv: StoreInventory yoki expiry_date maydonli obyekt.
        now: Tekshirish vaqti (None = hozir UTC).

    Returns:
        Qolgan kunlar (manfiy = o'tgan); None — expiry_date belgilanmagan.
    """
    exp: date | None = getattr(inv, "expiry_date", None)
    if exp is None:
        return None

    today = _today(now)
    return (exp - today).days
