"""
Import data moduli router — /import prefiksi bilan main.py ga ulanadi.

Endpointlar:
  POST /import/excel/parse     — Excel (.xlsx) faylni parse qiladi (parse-only, DBga yozMAYDI)
  POST /import/nakladnoy/parse — Nakladnoy rasmini Groq Vision bilan parse qiladi
  POST /import/confirm         — Preview satrlarini DBga yozadi (katalog yoki StoreInventory)

RBAC: Module.IMPORT, Action.CREATE — administrator, accountant, store.
Rolga qarab target serverda aniqlanadi (server-avtoritar).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.import_data import service
from app.modules.import_data.excel import parse_excel
from app.modules.import_data.schemas import (
    ExcelParseOut,
    ImportConfirmIn,
    ImportConfirmOut,
    NakladnoyParseOut,
)
from app.modules.import_data.vision import parse_nakladnoy
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.enterprise_scope import get_current_enterprise_id
from app.modules.rbac.permissions import Action, Module

logger = logging.getLogger(__name__)

router = APIRouter(tags=["import"])


# ─── Excel parse ──────────────────────────────────────────────────────────────


@router.post(
    "/excel/parse",
    response_model=ExcelParseOut,
    summary="Excel faylni parse qilish",
    description=(
        "Excel (.xlsx) faylni parse qiladi. DBga YOZMAYDI. "
        "Ustun moslash: heuristika + Groq AI (fail-open). "
        "Javob: columns_detected, rows (preview), warnings. "
        "Keyin /import/confirm ga yuboring."
    ),
    responses={
        422: {"description": "Noto'g'ri fayl (magic bytes, hajm yoki format xatosi)"},
    },
)
async def excel_parse(
    file: UploadFile = File(..., description="Excel fayl (.xlsx, max 5MB)"),
    current_user: AppUser = require_permission(Module.IMPORT, Action.CREATE),
    _eid=None,
) -> ExcelParseOut:
    get_current_enterprise_id(current_user)  # ContextVar o'rnatish

    try:
        result = await parse_excel(file)
    except ValueError as exc:
        raise AppError(
            message_key="import.invalid_file",
            status_code=422,
            params={"detail": str(exc)},
        ) from exc

    return result


# ─── Nakladnoy rasm parse ─────────────────────────────────────────────────────


@router.post(
    "/nakladnoy/parse",
    response_model=NakladnoyParseOut,
    summary="Nakladnoy rasmini parse qilish (Vision AI)",
    description=(
        "Nakladnoy yoki hisob rasmini Groq Llama 4 Vision bilan parse qiladi. "
        "DBga YOZMAYDI. Aniqlik kafolatlanmaydi — preview'da tahrirlang. "
        "Vision ishlamasa 503 qaytaradi (graceful — Excel alternativasi mavjud)."
    ),
    responses={
        422: {"description": "Noto'g'ri rasm (faqat JPEG/PNG/WebP)"},
        503: {"description": "Vision AI ishlamayapti (Groq unavailable)"},
    },
)
async def nakladnoy_parse(
    file: UploadFile = File(..., description="Nakladnoy rasmi (JPEG/PNG/WebP, max 8MB)"),
    current_user: AppUser = require_permission(Module.IMPORT, Action.CREATE),
) -> NakladnoyParseOut:
    get_current_enterprise_id(current_user)  # ContextVar o'rnatish

    try:
        result = await parse_nakladnoy(file)
    except ValueError as exc:
        raise AppError(
            message_key="import.invalid_file",
            status_code=422,
            params={"detail": str(exc)},
        ) from exc
    # AppError(503) vision_unavailable — yuqoriga ko'tariladi (FastAPI handler)

    return result


# ─── Confirm ──────────────────────────────────────────────────────────────────


@router.post(
    "/confirm",
    response_model=ImportConfirmOut,
    summary="Import tasdiqlash (DBga yozish)",
    description=(
        "Preview satrlarini DBga yozadi. "
        "Rol bo'yicha target aniqlanadi: korxona rollari → katalog, "
        "store roli → StoreInventory. "
        "Op-darajali xato izolyatsiyasi: bitta xato batchni yiqitmaydi. "
        "client_uuid idempotentlik kafolatlaydi."
    ),
    responses={
        404: {"description": "Do'kon topilmadi (store roli uchun)"},
        403: {"description": "Ruxsat yo'q"},
    },
)
async def confirm_import(
    body: ImportConfirmIn,
    current_user: AppUser = require_permission(Module.IMPORT, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> ImportConfirmOut:
    get_current_enterprise_id(current_user)  # ContextVar o'rnatish

    result = await service.confirm_import(
        db=db,
        body=body,
        current_user=current_user,
        redis=redis,
    )
    return result
