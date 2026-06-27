"""
Excel ustun moslash — heuristika + Groq AI fallback.

Oqim:
  1. Heuristika (regex/sinonim lug'at) bilan ustunlarni moslashtiradi.
  2. Heuristika ishonchsiz bo'lsa (confidence < 0.6) → Groq llama-3.3 ga
     faqat header + 3 namuna satr yuboriladi (PII yo'q).
  3. Groq xato bo'lsa → heuristika natijasi (fail-open).

PII-guard: Excel ma'lumotlardan faqat header satri va 3 namuna qiymat yuboriladi.
Mahsulot nomlari ham PII emas (generik), shuning uchun yuborish mumkin.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ─── Sinonim lug'at ────────────────────────────────────────────────────────────
# Har maydon uchun regex pattern (case-insensitive)

_FIELD_PATTERNS: dict[str, re.Pattern] = {
    "name": re.compile(
        r"(nom|name|товар|наимен|nomina|наз|product|item|mahsulot)",
        re.IGNORECASE,
    ),
    "sku": re.compile(
        r"(артикул|sku|код|code|article|artikel|шифр)",
        re.IGNORECASE,
    ),
    "barcode": re.compile(
        r"(штрих|barcode|шк|ean|upc|barcod|bar.?code)",
        re.IGNORECASE,
    ),
    "qty": re.compile(
        r"(кол|miqdor|qty|количество|count|amount|son|dona|unit)",
        re.IGNORECASE,
    ),
    "price": re.compile(
        r"(narx|price|цена|нарх|cost|сумма|sum|summa)",
        re.IGNORECASE,
    ),
    "currency": re.compile(
        r"(valyuta|currency|валюта|curr)",
        re.IGNORECASE,
    ),
    "expiry_date": re.compile(
        r"(muddat|expir|годн|срок|date|sana|sanasi)",
        re.IGNORECASE,
    ),
}


def _heuristic_map(headers: list[str]) -> dict[str, tuple[str | None, float]]:
    """
    Heuristika bilan ustun moslashtiradi.

    Returns:
        {header: (mapped_field, confidence)}
    """
    result: dict[str, tuple[str | None, float]] = {}
    for header in headers:
        best_field: str | None = None
        best_conf = 0.0
        for field, pattern in _FIELD_PATTERNS.items():
            if pattern.search(header):
                # Qisqaroq mos kelsa, ishonch balandroq
                conf = 0.85 if re.search(rf"^{pattern.pattern}$", header, re.IGNORECASE) else 0.75
                if conf > best_conf:
                    best_conf = conf
                    best_field = field
        result[header] = (best_field, best_conf if best_field else 0.0)
    return result


async def map_columns(
    headers: list[str],
    sample_rows: list[list[Any]],
) -> dict[str, tuple[str | None, float]]:
    """
    Ustun moslash: heuristika → Groq fallback.

    Args:
        headers:     Excel ustun sarlavhalari.
        sample_rows: Max 3 ta namuna satr (heuristika tekshiruvi uchun).

    Returns:
        {header: (mapped_field, confidence)}
        mapped_field None bo'lsa — noma'lum ustun.
    """
    mapping = _heuristic_map(headers)

    # Ishonchsiz ustunlar bormi?
    uncertain = [h for h, (_, conf) in mapping.items() if conf < 0.6]
    if not uncertain:
        return mapping

    # Groq ga faqat header + namuna yuboriladi (PII yo'q)
    try:
        mapping = await _groq_enhance(headers, sample_rows, mapping)
    except Exception as exc:
        logger.warning("column_mapping: Groq xato, heuristika natijasi ishlatiladi: %r", exc)

    return mapping


async def _groq_enhance(
    headers: list[str],
    sample_rows: list[list[Any]],
    current_mapping: dict[str, tuple[str | None, float]],
) -> dict[str, tuple[str | None, float]]:
    """
    Groq llama-3.3 bilan ustun moslashni yaxshilaydi.

    Fail-open: xato bo'lsa current_mapping qaytariladi.
    """
    import httpx

    from app.core.config import settings

    api_key = getattr(settings, "groq_api_key", None)
    if not api_key:
        return current_mapping

    # Namuna ma'lumotlar (max 3 satr, max 10 ustun)
    sample_text = " | ".join(str(h) for h in headers[:10])
    rows_text = ""
    for row in sample_rows[:3]:
        rows_text += "\n  " + " | ".join(str(v)[:30] for v in row[:10])

    valid_fields = ["name", "sku", "barcode", "qty", "price", "currency", "expiry_date"]
    prompt = (
        f"Excel ustunlarini mahsulot maydonlariga moslashtir.\n"
        f"Ustunlar: {sample_text}\n"
        f"Namuna qatorlar:{rows_text}\n\n"
        f"Faqat JSON qaytar, boshqa matn yo'q:\n"
        f"{{\"mapping\": {{\"<ustun_nomi>\": \"<maydon_nomi_yoki_null>\"}}}}\n"
        f"Mumkin bo'lgan maydonlar: {valid_fields}\n"
        f"Mos kelmasa null."
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": getattr(settings, "groq_model", "llama-3.3-70b-versatile"),
                    "max_tokens": 200,
                    "temperature": 0.0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if resp.status_code != 200:
            logger.warning("column_mapping Groq status=%s", resp.status_code)
            return current_mapping

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return current_mapping

        content = (choices[0].get("message", {}).get("content") or "").strip()
        # JSON ajratib olish (markdown fence bo'lishi mumkin)
        content = _extract_json(content)
        parsed = json.loads(content)
        ai_mapping: dict[str, Any] = parsed.get("mapping", {})

        # AI natijasini current_mapping bilan birlashtirish
        updated = dict(current_mapping)
        for header, field in ai_mapping.items():
            if header in updated:
                if field in valid_fields:
                    updated[header] = (field, 0.8)
                elif field is None:
                    # AI ham topa olmadi — confidence 0
                    updated[header] = (None, 0.0)
        return updated

    except Exception as exc:
        logger.warning("column_mapping Groq enhance xato: %r", exc)
        return current_mapping


def _extract_json(text: str) -> str:
    """Markdown code fence dan JSON ajratib oladi."""
    # ```json ... ``` yoki ``` ... ``` ni tozalaydi
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()
