"""
Claude AI boyitish qatlami — Faza 4 (ixtiyoriy).

ANTHROPIC_API_KEY muhit o'zgaruvchisi bo'lsa:
  - Rule-based tavsiyalar (faqat raqam/nom, PII YO'Q) Claude'ga yuboriladi.
  - O'zbekcha umumiy xulosa + ustuvorlik tartibi qaytariladi.
  - Xato yoki limit → rule-based fallback (fail-open).

ANTHROPIC_API_KEY bo'lmasa:
  - No-op, (None, False) qaytaradi.

PII himoyasi:
  - Do'kon INN/telefon/egasi HECH QACHON yuborilmaydi.
  - Faqat tavsiya kodi + raqamlar + mahsulot nomi (shifrsiz PII emas).

Push provider FakeProvider naqshi (no-op graceful degrade).
"""

from __future__ import annotations

import logging

from app.modules.analytics.schemas import RecommendationItem

logger = logging.getLogger(__name__)


async def enrich_with_ai(
    recommendations: list[RecommendationItem],
) -> tuple[str | None, bool]:
    """
    Ixtiyoriy Claude AI boyitish.

    Args:
        recommendations: Rule-based tavsiyalar ro'yxati.

    Returns:
        (ai_summary, ai_enabled):
          ai_summary — Claude matni (yoki None)
          ai_enabled — True agar Claude muvaffaqiyatli ishlagan bo'lsa

    Fail-open: Claude xatosida (None, False) qaytaradi.
    """
    try:
        from app.core.config import settings
    except ImportError:
        return None, False

    # Kalit yo'q → no-op (Groq — bepul provayder)
    api_key = getattr(settings, "groq_api_key", None)
    if not api_key:
        logger.debug("ai_enrich: GROQ_API_KEY yo'q — rule-based fallback")
        return None, False

    ai_enabled_flag = getattr(settings, "analytics_ai_enabled", True)
    if not ai_enabled_flag:
        logger.debug("ai_enrich: analytics_ai_enabled=False — rule-based fallback")
        return None, False

    if not recommendations:
        return None, False

    try:
        import httpx

        model = getattr(settings, "groq_model", "llama-3.3-70b-versatile")

        # PII-guard: faqat tavsiya kodi + jiddiylik + raqamlar + mahsulot nomi
        # Do'kon nomi ham yuborilmaydi (anonimlashtirish)
        anon_items = []
        for idx, rec in enumerate(recommendations[:10], start=1):  # Max 10 ta
            metric_str = ", ".join(f"{k}={v}" for k, v in rec.metric.items())
            anon_items.append(
                f"Tavsiya {idx} [{rec.severity.upper()}] {rec.code}: {metric_str}"
            )

        prompt = (
            "Quyidagi retail do'kon savdo tahlili tavsiyalari asosida o'zbekcha "
            "qisqa umumiy xulosa yozing (3-4 gap). Ustuvorlik tartibini belgilang. "
            "Faqat raqamlar va tavsiyalar kodiga tayanib ish yuriting.\n\n"
            + "\n".join(anon_items)
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 400,
                    "temperature": 0.4,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                summary = (choices[0].get("message", {}).get("content") or "").strip()
                if summary:
                    logger.info("ai_enrich: Groq boyitish muvaffaqiyatli")
                    return summary, True

        logger.warning(
            "ai_enrich: Groq noto'g'ri javob",
            extra={"status_code": resp.status_code},
        )
        return None, False

    except Exception as exc:
        logger.warning("ai_enrich: xato (rule-based fallback)", exc_info=exc)
        return None, False
