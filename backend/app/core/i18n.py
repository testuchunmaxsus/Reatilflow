"""
i18n (Internationalization) qatlami — uz/ru ikki tilli qo'llab-quvvatlash.

Asosiy elementlar:
  SUPPORTED_LOCALES  — qo'llab-quvvatlanadigan til kodlari
  DEFAULT_LOCALE     — standart til (Accept-Language yo'q bo'lganda)
  current_locale     — ContextVar: har request uchun joriy til
  parse_accept_language() — Accept-Language headeridan til ajratish
  translate()        — message_key + locale → lokalizatsiyalangan matn
  localized_name()   — ORM obyektidan name_uz/name_ru ajratish (T4 uchun)
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

# ─── Til konstantalari ───────────────────────────────────────────────────────

SUPPORTED_LOCALES: tuple[str, ...] = ("uz", "ru")
DEFAULT_LOCALE: str = "uz"

# ContextVar — async kontekstda (per-request) joriy tilni saqlaydi.
# servis qatlami request ob'ektsiz ham current_locale.get() orqali tilni oladi.
current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)


# ─── Accept-Language parser ──────────────────────────────────────────────────

# "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,uz;q=0.6" kabi headerlarni ajratadi.
_LANG_TAG_RE = re.compile(r"([a-zA-Z]{1,8})(?:-[a-zA-Z0-9]{1,8})*(?:;q=([\d.]+))?")


def parse_accept_language(header: str | None) -> str:
    """
    Accept-Language headeridan qo'llab-quvvatlanadigan tilni ajratadi.

    Algoritm:
      1. Header yo'q yoki bo'sh → DEFAULT_LOCALE.
      2. Barcha til teglarini q-faktor bilan ajratadi (standart q=1.0).
      3. q bo'yicha kamayish tartibida saralab, birinchi mos SUPPORTED_LOCALES
         tilini qaytaradi.
      4. Hech qaysi mos kelmasa → DEFAULT_LOCALE.

    Misollar:
      "ru"                    → "ru"
      "uz"                    → "uz"
      "en"                    → "uz"  (DEFAULT_LOCALE)
      "ru-RU,ru;q=0.9"       → "ru"
      ""                      → "uz"
      None                    → "uz"
      "ru;q=0.5,uz;q=0.8"    → "uz"  (uz q=0.8 > ru q=0.5)

    Args:
        header: HTTP Accept-Language header qiymati yoki None.

    Returns:
        Til kodi: "uz" yoki "ru".
    """
    if not header:
        return DEFAULT_LOCALE

    # MEDIUM (Security/SRE): DoS oldini olish — 256 belgidan uzun header rad etiladi
    if len(header) > 256:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, str]] = []

    for match in _LANG_TAG_RE.finditer(header):
        lang_code = match.group(1).lower()
        q_str = match.group(2)
        try:
            q = float(q_str) if q_str else 1.0
        except ValueError:
            q = 1.0

        # Faqat asosiy til kodini tekshirish (masalan, "ru-RU" → "ru")
        if lang_code in SUPPORTED_LOCALES:
            candidates.append((q, lang_code))

    if not candidates:
        return DEFAULT_LOCALE

    # Eng yuqori q-faktorli tilni tanlash
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ─── localized_name yordamchisi ──────────────────────────────────────────────

def localized_name(obj: Any, locale: str | None = None) -> str:
    """
    ORM obyektidan joriy tilga mos nom qaytaradi.

    `name_uz` va `name_ru` ustunlari bo'lgan istalgan ORM modelida ishlaydi
    (Category, Product, PriceSegment, Promo va boshqalar).

    Fallback zanjiri:
      1. `name_{locale}` atribyuti mavjud va bo'sh bo'lmasa → qaytaradi.
      2. `name_uz` ga fallback qiladi.
      3. Hech nima yo'q bo'lsa → bo'sh string.

    Args:
        obj: name_uz/name_ru atribyutlari bo'lgan ORM obyekti.
        locale: Til kodi ("uz" yoki "ru"). None bo'lsa current_locale ishlatiladi.

    Returns:
        Lokalizatsiyalangan nom string.
    """
    if locale is None:
        locale = current_locale.get()

    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE

    # Asosiy til
    value = getattr(obj, f"name_{locale}", None)
    if value:
        return str(value)

    # Fallback: har doim uz
    fallback = getattr(obj, "name_uz", None)
    if fallback:
        return str(fallback)

    return ""
