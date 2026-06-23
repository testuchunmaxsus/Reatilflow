"""
Push bildirishnoma xabar kalitlari va i18n matnlari — T19.

Katalog: PUSH_MESSAGES[key][locale] = (title_template, body_template)

Qo'llab-quvvatlanadigan kalidlar:
  push.order_status_updated   — buyurtma holati o'zgardi
  push.delivery_created       — yetkazish yaratildi (tayinlandi)
  push.delivery_status_updated — yetkazish holati o'zgardi

Parametrlar {param} bilan belgilanadi.
`push_title()` va `push_body()` funksiyalari foydalanuvchi locale asosida
lokalizatsiyalangan matn qaytaradi.
"""

from __future__ import annotations

_DEFAULT_LOCALE = "uz"
_SUPPORTED_LOCALES = frozenset({"uz", "ru"})

# ─── Xabar katalogi ───────────────────────────────────────────────────────────
# Har kalit: (title_template, body_template)

PUSH_MESSAGES: dict[str, dict[str, tuple[str, str]]] = {
    # Buyurtma holati o'zgardi
    "push.order_status_updated": {
        "uz": (
            "Buyurtma holati",
            "Buyurtma #{order_id_short}: holat '{status}' ga o'zgardi",
        ),
        "ru": (
            "Статус заказа",
            "Заказ #{order_id_short}: статус изменён на '{status}'",
        ),
    },

    # Yetkazish yaratildi (kuryer tayinlandi)
    "push.delivery_created": {
        "uz": (
            "Yetkazish tayinlandi",
            "Buyurtma #{order_id_short} uchun kuryer tayinlandi",
        ),
        "ru": (
            "Назначена доставка",
            "Для заказа #{order_id_short} назначен курьер",
        ),
    },

    # Yetkazish holati o'zgardi
    "push.delivery_status_updated": {
        "uz": (
            "Yetkazish holati",
            "Buyurtma #{order_id_short} yetkazish holati: '{status}'",
        ),
        "ru": (
            "Статус доставки",
            "Статус доставки заказа #{order_id_short}: '{status}'",
        ),
    },

    # Inventar muddati yaqinlashmoqda (MP4)
    "push.inventory_expiring_soon": {
        "uz": (
            "Inventar muddati",
            "{product_name}: {days} kun qoldi ({store_name})",
        ),
        "ru": (
            "Срок годности",
            "{product_name}: осталось {days} дн. ({store_name})",
        ),
    },

    # Umumiy bildirishnoma (fallback)
    "push.general": {
        "uz": (
            "RETAIL",
            "Yangi bildirishnoma",
        ),
        "ru": (
            "RETAIL",
            "Новое уведомление",
        ),
    },
}


# ─── Foydalanuvchi locale bo'yicha matn olish ────────────────────────────────


def _resolve_locale(locale: str | None) -> str:
    """Locale ni normallashtiradi: qo'llab-quvvatlanmaydigan → default (uz)."""
    if locale and locale in _SUPPORTED_LOCALES:
        return locale
    return _DEFAULT_LOCALE


def push_title(key: str, locale: str | None = None, **params: object) -> str:
    """
    Push sarlavhasini lokalizatsiyalangan tarzda qaytaradi.

    Args:
        key:    Xabar kaliti (masalan, 'push.order_status_updated').
        locale: Foydalanuvchi tili ('uz' yoki 'ru').
        **params: Shablon parametrlari.

    Returns:
        Lokalizatsiyalangan va formatlanagan sarlavha matni.
    """
    loc = _resolve_locale(locale)
    catalog = PUSH_MESSAGES.get(key) or PUSH_MESSAGES.get("push.general", {})
    title_tmpl, _ = catalog.get(loc) or catalog.get(_DEFAULT_LOCALE) or ("RETAIL", "")
    if params:
        try:
            return title_tmpl.format(**params)
        except (KeyError, ValueError):
            pass
    return title_tmpl


def push_body(key: str, locale: str | None = None, **params: object) -> str:
    """
    Push matni (body) ni lokalizatsiyalangan tarzda qaytaradi.

    Args:
        key:    Xabar kaliti.
        locale: Foydalanuvchi tili ('uz' yoki 'ru').
        **params: Shablon parametrlari.

    Returns:
        Lokalizatsiyalangan va formatlanagan matn.
    """
    loc = _resolve_locale(locale)
    catalog = PUSH_MESSAGES.get(key) or PUSH_MESSAGES.get("push.general", {})
    _, body_tmpl = catalog.get(loc) or catalog.get(_DEFAULT_LOCALE) or ("", "Yangi bildirishnoma")
    if params:
        try:
            return body_tmpl.format(**params)
        except (KeyError, ValueError):
            pass
    return body_tmpl


def push_text(key: str, locale: str | None = None, **params: object) -> tuple[str, str]:
    """
    (title, body) juftligini qaytaradi — qulay wrapper.

    Returns:
        (title, body) — lokalizatsiyalangan matnlar.
    """
    return push_title(key, locale, **params), push_body(key, locale, **params)
