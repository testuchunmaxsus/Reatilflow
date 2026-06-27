"""
Assistant moduli router — /assistant prefiksi bilan main.py ga ulanadi.

Endpointlar:
  POST /assistant/chat  — AI yordamchi chat (o'zbekcha qadam-baqadam)

RBAC: Module.ASSISTANT, Action.VIEW — barcha tenant rollari.
PII-guard: enterprise_id, store_id, INN Groq'ga YUBORILMAYDI.
Fail-open: Groq ishlamasa statik o'zbekcha javob qaytariladi.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.user import AppUser
from app.modules.assistant import service
from app.modules.assistant.schemas import ChatIn, ChatOut
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistant"])


@router.post(
    "/chat",
    response_model=ChatOut,
    summary="AI yordamchi chat",
    description=(
        "RetailFlowAI tizimidan foydalanish bo'yicha o'zbekcha yordamchi. "
        "Groq llama-3.3 bilan ishlaydi (fail-open: ishlamasa statik javob). "
        "Tarix: max so'nggi 6 ta xabar ishlatiladi. "
        "PII: enterprise/store ma'lumotlari Groq'ga YUBORILMAYDI."
    ),
    responses={
        200: {"description": "AI javobi (ai_enabled=false bo'lsa statik fallback)"},
    },
)
async def assistant_chat(
    body: ChatIn,
    current_user: AppUser = require_permission(Module.ASSISTANT, Action.VIEW),
) -> ChatOut:
    get_current_enterprise_id(current_user)  # ContextVar o'rnatish

    result = await service.chat(body=body, current_user=current_user)
    return result
