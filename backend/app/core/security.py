"""
PII va maxfiy ma'lumotlarni maskalash yordamchisi.

Foydalanish:
    from app.core.security import mask_pii

    safe_data = mask_pii(user_dict)

Maskalanuvchi kalitlar (katta-kichik harfsiz):
  inn, inps, phone, password, password_hash, token,
  access_token, refresh_token, owner_name, secret

Audit yozuvchilari before_json / after_json ni shu funksiyadan o'tkazib yozadi.

TODO (T5 — Mijoz bazasi):
  - pgcrypto AES shifrlash integratsiyasi
  - HMAC blind-index qo'shish
"""

from __future__ import annotations

# PII va maxfiy kalit nomlari (kichik harfda — tekshiruvda .lower() ishlatiladi)
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "inn",
        "inps",
        "phone",
        "full_name",       # T6: PII — audit logda ochiq-matn tushmasin
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "owner_name",
        "secret",
        "jwt_secret_key",
    }
)

_MASK = "***"


def mask_pii(data: dict) -> dict:
    """
    Lug'at ichidagi PII va maxfiy maydonlarni maskalashtiradi.

    Faqat yuqori darajadagi kalitlarni tekshiradi (nested emas).
    Asl lug'at o'zgartirilmaydi — yangi nusxa qaytariladi.

    Args:
        data: Asl ma'lumotlar lug'ati.

    Returns:
        Maskalangan yangi lug'at.
    """
    result: dict = {}
    for key, value in data.items():
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            result[key] = _MASK
        else:
            result[key] = value
    return result
