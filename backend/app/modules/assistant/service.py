"""
Assistant servis qatlami — Groq llama-3.3 chat.

Oqim:
  1. System prompt (tizim qo'llanmasi + rol konteksti) qurish.
  2. Tarix: max so'nggi 6 ta xabar (server kesadi).
  3. Groq llama-3.3-70b-versatile ga so'rov yuborish.
  4. Muvaffaqiyatsiz → statik o'zbekcha fallback (fail-open).

PII-guard:
  - History va message matni yuboriladi (foydalanuvchi o'zi yozsa).
  - Groq'ga enterprise_id, store_id, INN, telefon YUBORILMAYDI.
  - Faqat rol nomi (nomi yo'q, ID yo'q) system prompt'da ishlatiladi.
"""

from __future__ import annotations

import logging

from app.modules.assistant.prompts import STATIC_FALLBACK, build_system_prompt
from app.modules.assistant.schemas import ChatIn, ChatMessage, ChatOut
from app.models.user import AppUser

logger = logging.getLogger(__name__)

# Suhbat tarixidagi max xabarlar soni
_MAX_HISTORY = 6


async def chat(body: ChatIn, current_user: AppUser) -> ChatOut:
    """
    AI chat: foydalanuvchi savoliga o'zbekcha javob qaytaradi.

    Fail-open: Groq ishlamasa statik fallback javobi qaytaradi.
    """
    # Tarixni kesish (max _MAX_HISTORY ta)
    trimmed_history = body.history[-_MAX_HISTORY:]

    # Groq ga urinib ko'rish
    try:
        reply = await _call_groq(body.message, trimmed_history, current_user.role)
        if reply:
            return ChatOut(reply=reply, ai_enabled=True)
    except Exception as exc:
        logger.warning("assistant: Groq chat xato (statik fallback): %r", exc)

    return ChatOut(reply=STATIC_FALLBACK, ai_enabled=False)


async def _call_groq(
    message: str,
    history: list[ChatMessage],
    role: str,
) -> str | None:
    """
    Groq llama-3.3 ga chat so'rovi yuboradi.

    Returns:
        AI javobi matni yoki None (ishlamasa).
    """
    import httpx

    from app.core.config import settings

    api_key = getattr(settings, "groq_api_key", None)
    if not api_key:
        logger.debug("assistant: GROQ_API_KEY yo'q — statik fallback")
        return None

    # System prompt
    system_prompt = build_system_prompt(role)

    # Xabarlar ro'yxati
    messages = [{"role": "system", "content": system_prompt}]

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": message})

    model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 800,
                    "temperature": 0.4,
                    "messages": messages,
                },
            )

        if resp.status_code != 200:
            logger.warning("assistant: Groq status=%s", resp.status_code)
            return None

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return None

        content = (choices[0].get("message", {}).get("content") or "").strip()
        return content if content else None

    except Exception as exc:
        logger.warning("assistant: Groq so'rov xato: %r", exc)
        return None
