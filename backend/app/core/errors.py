"""
Standart xato sinflari va xato javob formati.

Xato konverti (envelope):
  {
    "message_key": "auth.invalid_credentials",
    "message":     "Telefon yoki parol noto'g'ri",
    "detail":      null  # yoki qo'shimcha ma'lumot dict
  }

Asosiy sinf: AppError — barcha domenli xatolar shu sinfdan meros oladi.
Sub-sinf: AuthAppError — autentifikatsiya xatolari.
"""

from __future__ import annotations

from typing import Any


# ─── Bazaviy AppError ────────────────────────────────────────────────────────

class AppError(Exception):
    """
    Domenli xato — barcha lokalizatsiyalangan xatolar shu sinfdan.

    Atribyutlar:
      message_key : xabar katalog kaliti (masalan, "auth.invalid_credentials").
      status_code : HTTP status kodi (400, 401, 403, 404 va h.k.).
      params      : translate() ga uzatiladigan format parametrlari.
      detail      : ixtiyoriy qo'shimcha ma'lumot (JSON serializable).
    """

    def __init__(
        self,
        message_key: str,
        status_code: int = 400,
        params: dict[str, Any] | None = None,
        detail: Any = None,
    ) -> None:
        self.message_key = message_key
        self.status_code = status_code
        self.params = params or {}
        self.detail = detail
        super().__init__(message_key)

    def localized_message(self, locale: str | None = None) -> str:
        """
        Joriy locale bo'yicha lokalizatsiyalangan xabar matnini qaytaradi.

        Args:
            locale: Til kodi. None bo'lsa current_locale ContextVar ishlatiladi.

        Returns:
            Lokalizatsiyalangan va formatlanagan xabar matn.
        """
        from app.core.messages import translate
        return translate(self.message_key, locale=locale, **self.params)


# ─── Auth sub-turi ───────────────────────────────────────────────────────────

class AuthAppError(AppError):
    """
    Autentifikatsiya xatosi.

    Standart status kodi 401; bloklangan hisob uchun 403 berilishi mumkin.
    """

    def __init__(
        self,
        message_key: str,
        status_code: int = 401,
        params: dict[str, Any] | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(
            message_key=message_key,
            status_code=status_code,
            params=params,
            detail=detail,
        )


# ─── Xato javob yordamchisi ──────────────────────────────────────────────────

def error_envelope(
    message_key: str,
    message: str,
    detail: Any = None,
) -> dict[str, Any]:
    """
    Standart xato konvertini dict sifatida qaytaradi.

    Foydalanish (exception handler ichida):
        content = error_envelope("auth.invalid_credentials", translated_msg)

    Args:
        message_key: Xabar katalog kaliti.
        message:     Lokalizatsiyalangan xabar matni.
        detail:      Ixtiyoriy qo'shimcha ma'lumot (Pydantic xatolari uchun).

    Returns:
        {"message_key": ..., "message": ..., "detail": ...} dict.
    """
    return {
        "message_key": message_key,
        "message": message,
        "detail": detail,
    }
