"""
Nakladnoy rasm OCR — Groq Llama 4 Vision.

Oqim:
  1. Magic bytes tekshiruvi (JPEG/PNG/WebP).
  2. Base64 kodlash.
  3. Groq meta-llama/llama-4-scout-17b-16e-instruct ga image_url (base64) yuborish.
  4. Strict JSON parse ({\"items\": [{...}]}).
  5. Muvaffaqiyatsiz → AppError 503 vision_unavailable (graceful, aniq xato).

PII-guard: Rasm faqat Groq Vision APIga yuboriladi. Hech qanday metadata qo'shilmaydi.
Biznes ma'lumot: nakladnoy odatda PII emas (mahsulot nomlari).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid

from fastapi import UploadFile

from app.core.errors import AppError
from app.modules.import_data.schemas import NakladnoyParseOut, ParsedRow

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB

# Magic bytes
_MAGIC_JPEG = b"\xFF\xD8"
_MAGIC_PNG = b"\x89PNG"
_MAGIC_WEBP_RIFF = b"RIFF"
_MAGIC_WEBP_MARKER = b"WEBP"

# Strict prompt — faqat JSON qaytarish
_VISION_PROMPT = (
    "Ushbu nakladnoy/hisob rasmidan mahsulotlar ro'yxatini ajratib ol. "
    "Faqat JSON qaytar, boshqa matn yo'q:\n"
    "{\"items\": [{\"name\": \"mahsulot nomi\", \"qty\": 1.0, \"price\": 0.0}]}\n"
    "Agar hech narsa topilmasa: {\"items\": []}\n"
    "qty va price raqam bo'lishi shart (topilmasa 0 qo'y)."
)


# ─── Vision parse ─────────────────────────────────────────────────────────────


async def parse_nakladnoy(file: UploadFile) -> NakladnoyParseOut:
    """
    Nakladnoy rasmini Groq Vision bilan parse qiladi.

    Args:
        file: FastAPI UploadFile (JPEG/PNG/WebP, max 8MB).

    Returns:
        NakladnoyParseOut.

    Raises:
        ValueError: Noto'g'ri rasm (magic bytes yoki hajm).
        AppError(503): Vision API ishlamayapti (graceful xato).
    """
    warnings: list[str] = []

    # 1. Fayl o'qish
    content = await file.read()

    # 2. Hajm tekshiruvi
    if len(content) > _MAX_FILE_SIZE:
        raise ValueError(f"Rasm hajmi {_MAX_FILE_SIZE // (1024*1024)} MB dan oshmasin")

    # 3. Magic bytes va MIME type
    mime_type = _detect_mime(content)
    if mime_type is None:
        raise ValueError("Faqat JPEG, PNG yoki WebP rasmlari qabul qilinadi")

    # 4. Groq Vision API
    from app.core.config import settings

    api_key = getattr(settings, "groq_api_key", None)
    if not api_key:
        raise AppError(
            message_key="import.vision_unavailable",
            status_code=503,
        )

    # 5. Base64 kodlash
    b64 = base64.b64encode(content).decode("ascii")
    image_url = f"data:{mime_type};base64,{b64}"

    vision_model = getattr(settings, "groq_vision_model", "meta-llama/llama-4-scout-17b-16e-instruct")

    rows, raw_text = await _call_groq_vision(api_key, vision_model, image_url, warnings)

    return NakladnoyParseOut(
        parse_id=uuid.uuid4(),
        rows=rows,
        raw_text=raw_text,
        warnings=warnings,
        vision_enabled=True,
    )


async def _call_groq_vision(
    api_key: str,
    model: str,
    image_url: str,
    warnings: list[str],
) -> tuple[list[ParsedRow], str | None]:
    """
    Groq Vision API ga so'rov yuboradi va ParsedRow ro'yxati qaytaradi.

    Raises:
        AppError(503): Vision API ishlamayapti.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "temperature": 0.0,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": _VISION_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url},
                                },
                            ],
                        }
                    ],
                },
            )
    except Exception as exc:
        logger.error("vision: Groq Vision so'rov xatosi: %r", exc)
        raise AppError(
            message_key="import.vision_unavailable",
            status_code=503,
        ) from exc

    if resp.status_code != 200:
        logger.error("vision: Groq Vision noto'g'ri javob status=%s", resp.status_code)
        raise AppError(
            message_key="import.vision_unavailable",
            status_code=503,
        )

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise AppError(message_key="import.vision_unavailable", status_code=503)

    raw_text = (choices[0].get("message", {}).get("content") or "").strip()
    if not raw_text:
        raise AppError(message_key="import.vision_unavailable", status_code=503)

    # JSON parse
    rows = _parse_vision_json(raw_text, warnings)
    return rows, raw_text


def _parse_vision_json(text: str, warnings: list[str]) -> list[ParsedRow]:
    """
    Vision javobidan JSON parse qiladi.

    Strategiya:
      1. To'g'ridan-to'g'ri json.loads.
      2. Markdown fence tozalab qayta urinish.
      3. re bilan {...} ajratib qayta urinish.
      4. Baribir muvaffaqiyatsiz → AppError 503.
    """
    # 1. To'g'ridan-to'g'ri
    try:
        parsed = json.loads(text)
        return _items_to_rows(parsed.get("items", []), warnings)
    except json.JSONDecodeError:
        pass

    # 2. Markdown fence tozalash
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        parsed = json.loads(cleaned)
        return _items_to_rows(parsed.get("items", []), warnings)
    except json.JSONDecodeError:
        pass

    # 3. re bilan {...} ajratib olish
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return _items_to_rows(parsed.get("items", []), warnings)
        except json.JSONDecodeError:
            pass

    # 4. Baribir muvaffaqiyatsiz
    logger.error("vision: JSON parse muvaffaqiyatsiz. raw_text=%r", text[:200])
    raise AppError(
        message_key="import.vision_unavailable",
        status_code=503,
    )


def _items_to_rows(items: list, warnings: list[str]) -> list[ParsedRow]:
    """Vision items ro'yxatini ParsedRow ro'yxatiga o'tkazadi."""
    rows: list[ParsedRow] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or None
        qty = _safe_float(item.get("qty"))
        price = _safe_float(item.get("price"))

        # Agar qty/price 0 bo'lsa — confidence past
        confidence = 0.7
        if qty is None or qty == 0:
            confidence = 0.5
            warnings.append(f"Satr {idx + 1}: miqdor aniqlanmadi")
        if price is None or price == 0:
            confidence = min(confidence, 0.5)
            warnings.append(f"Satr {idx + 1}: narx aniqlanmadi")

        rows.append(
            ParsedRow(
                row_index=idx,
                name=name,
                qty=qty or 0.0,
                price=price or 0.0,
                confidence=confidence,
            )
        )

    return rows


def _detect_mime(content: bytes) -> str | None:
    """Magic bytes bo'yicha MIME type aniqlanadi."""
    if content[:2] == _MAGIC_JPEG:
        return "image/jpeg"
    if content[:4] == _MAGIC_PNG:
        return "image/png"
    if content[:4] == _MAGIC_WEBP_RIFF and len(content) >= 12 and content[8:12] == _MAGIC_WEBP_MARKER:
        return "image/webp"
    return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
