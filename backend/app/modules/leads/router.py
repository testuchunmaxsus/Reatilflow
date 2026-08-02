"""
Leads moduli — landing page demo so'rovi.

Endpoint (PUBLIC, autentifikatsiyasiz, modul-gate'siz):
  POST /public/demo-request — do'kon yoki korxona demo so'rovi.
    Ma'lumot Telegram'ga (@Ferganasoftuz kanali/guruhi) yuboriladi va logga
    yoziladi (Telegram sozlanmagan bo'lsa ham lead yo'qolmaydi).

Xavfsizlik:
  - Honeypot maydoni (`website`) — bot to'ldirsa jimgina "ok" qaytadi.
  - Maydon uzunliklari pydantic bilan cheklangan.
  - Telegram tokeni FAQAT serverda (config/env), klientga chiqmaydi.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal

from app.core.config import settings

logger = logging.getLogger("leads")

router = APIRouter()


class DemoRequestIn(BaseModel):
    """Landing demo-so'rovi tanasi."""

    type: Literal["dokon", "korxona"] = Field(
        ..., description="Foydalanuvchi turi: do'kon yoki korxona"
    )
    name: str = Field(..., min_length=2, max_length=120, description="Ism / mas'ul shaxs")
    phone: str = Field(..., min_length=7, max_length=32, description="Telefon raqami")
    business_name: str = Field(
        ..., min_length=2, max_length=160, description="Do'kon/korxona nomi"
    )
    region: str | None = Field(None, max_length=120, description="Viloyat/tuman (ixtiyoriy)")
    note: str | None = Field(None, max_length=600, description="Qo'shimcha izoh (ixtiyoriy)")
    # Honeypot — odam ko'rmaydi, bot to'ldiradi. To'lса — jimgina rad.
    website: str | None = Field(None, max_length=200)


class DemoRequestOut(BaseModel):
    ok: bool = True
    message_key: str = "demo.received"


def _fmt_message(data: DemoRequestIn) -> str:
    turi = "🏪 Do'kon" if data.type == "dokon" else "🏭 Korxona"
    lines = [
        "🆕 <b>Yangi demo so'rovi — RetailFlowAI</b>",
        "",
        f"<b>Turi:</b> {turi}",
        f"<b>Nomi:</b> {data.business_name}",
        f"<b>Mas'ul:</b> {data.name}",
        f"<b>Telefon:</b> {data.phone}",
    ]
    if data.region:
        lines.append(f"<b>Hudud:</b> {data.region}")
    if data.note:
        lines.append(f"<b>Izoh:</b> {data.note}")
    lines.append("")
    lines.append("📞 Sotuv bo'limi — bog'laning.")
    return "\n".join(lines)


async def _send_to_telegram(text: str) -> bool:
    """Telegram'ga yuboradi. Sozlanmagan/xato bo'lsa False (lead baribir logda)."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_demo_chat_id
    if not token or not chat_id:
        logger.warning("leads.telegram_not_configured — demo so'rovi faqat logda")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        logger.error("leads.telegram_send_failed status=%s body=%s", resp.status_code, resp.text[:300])
        return False
    except Exception as exc:  # noqa: BLE001 — tashqi xizmat, lead yo'qolmasin
        logger.error("leads.telegram_error %r", exc)
        return False


@router.post(
    "/demo-request",
    response_model=DemoRequestOut,
    status_code=200,
    summary="Landing demo so'rovi (public)",
    description=(
        "Do'kon yoki korxona demo so'rovi. Ma'lumot Telegram'ga yuboriladi. "
        "1 oy tekin sinov — sotuv bo'limi bog'lanadi."
    ),
)
async def create_demo_request(body: DemoRequestIn) -> DemoRequestOut:
    # Honeypot — bot bo'lsa jimgina qabul qilgandek qaytar (spam yozmaymiz).
    if body.website:
        logger.info("leads.honeypot_triggered — jim rad")
        return DemoRequestOut()

    # Lead HAR DOIM logga (Telegram ishlamasa ham yo'qolmasin).
    logger.info(
        "leads.demo_request type=%s business=%s name=%s phone=%s region=%s",
        body.type, body.business_name, body.name, body.phone, body.region or "-",
    )

    await _send_to_telegram(_fmt_message(body))
    # Telegram muvaffaqiyatsiz bo'lsa ham foydalanuvchiga muvaffaqiyat qaytaramiz
    # (lead logda; sotuv bo'limi kuzatadi). UX: "tez orada bog'lanamiz".
    return DemoRequestOut()
