"""
Davomat router — T16.

Endpointlar:
  POST /attendance/check-in   — kirish qayd etish
  POST /attendance/check-out  — chiqish qayd etish
  GET  /attendance            — paginated ro'yxat (RBAC scope)

RBAC:
  check-in:  attendance:create (agent, courier)
  check-out: attendance:create (agent, courier) — bir xil ruxsat
  list:      attendance:view   (agent, courier, administrator, accountant)

IDOR himoya:
  - agent/courier: ?user_id= boshqa user_id bo'lsa → 403.
  - administrator/accountant: istalgan user_id.

i18n: Accept-Language header va foydalanuvchi locale'i.
GPS: server tomonda yoziladi. Vaqt: server vaqti.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.redis import get_redis
from app.models.user import AppUser
from app.modules.attendance import service
from app.modules.attendance.schemas import (
    AttendanceOut,
    CheckInRequest,
    CheckOutRequest,
    PaginatedAttendance,
)
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Action, Module

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attendance"])


# ─── POST /attendance/check-in ───────────────────────────────────────────────


@router.post(
    "/check-in",
    response_model=AttendanceOut,
    status_code=201,
    summary="Davomatga kirish",
    description=(
        "Qurilma biometriyasini tasdiqlab davomatga kiradi. "
        "biometric_verified=True bo'lishi MAJBURIY. "
        "check_in_at — SERVER vaqti (klient vaqtiga ishonilmaydi). "
        "Bir kunda faqat bitta ochiq davomat bo'lishi mumkin."
    ),
)
async def check_in(
    body: CheckInRequest,
    current_user: AppUser = require_permission(Module.ATTENDANCE, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AttendanceOut:
    """
    POST /attendance/check-in

    RBAC: attendance:create (agent, courier).
    """
    att = await service.check_in(
        user=current_user,
        data=body,
        db=db,
        redis=redis,
    )
    return AttendanceOut.model_validate(att)


# ─── POST /attendance/check-out ──────────────────────────────────────────────


@router.post(
    "/check-out",
    response_model=AttendanceOut,
    status_code=200,
    summary="Davomatdan chiqish",
    description=(
        "Shu kunning ochiq davomatini yopadi. "
        "check_out_at — SERVER vaqti. "
        "Ochiq davomat bo'lmasa → 404 attendance.not_checked_in."
    ),
)
async def check_out(
    body: CheckOutRequest,
    current_user: AppUser = require_permission(Module.ATTENDANCE, Action.CREATE),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AttendanceOut:
    """
    POST /attendance/check-out

    RBAC: attendance:create (agent, courier).
    """
    att = await service.check_out(
        user=current_user,
        data=body,
        db=db,
        redis=redis,
    )
    return AttendanceOut.model_validate(att)


# ─── GET /attendance ──────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedAttendance,
    status_code=200,
    summary="Davomat ro'yxati",
    description=(
        "Paginated davomat ro'yxati. "
        "agent/courier: faqat o'z davomati (?user_id= boshqa ID bo'lsa → 403). "
        "administrator/accountant: istalgan user_id bo'yicha filtrlash. "
        "?date= qo'shimcha sana filtri."
    ),
)
async def list_attendance(
    user_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Foydalanuvchi ID bo'yicha filtr. "
            "agent/courier uchun: faqat o'z ID'si ruxsatli (boshqasi → 403). "
            "administrator/accountant uchun: ixtiyoriy."
        ),
    ),
    filter_date: date | None = Query(
        default=None,
        alias="date",
        description="Sana bo'yicha filtr (YYYY-MM-DD)",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Sahifa hajmi"),
    offset: int = Query(default=0, ge=0, description="Sahifa ofset"),
    current_user: AppUser = require_permission(Module.ATTENDANCE, Action.VIEW),
    db: AsyncSession = Depends(get_db),
) -> PaginatedAttendance:
    """
    GET /attendance

    RBAC: attendance:view (agent, courier, administrator, accountant).
    IDOR: agent/courier boshqa user_id so'rasa → 403.
    """
    items, total = await service.list_attendance(
        db=db,
        user=current_user,
        filter_user_id=user_id,
        filter_date=filter_date,
        limit=limit,
        offset=offset,
    )
    return PaginatedAttendance(
        items=[AttendanceOut.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )
