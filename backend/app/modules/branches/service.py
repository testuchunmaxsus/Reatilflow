"""
Branches servis qatlami — filiallar biznes mantiq.

Funksiyalar:
  create_branch(db, data, actor_id, enterprise_id) → Branch
  get_branch(db, branch_id, enterprise_id) → Branch
  list_branches(db, enterprise_id, filters...) → (list[Branch], total)
  update_branch(db, branch_id, data, actor_id, enterprise_id) → Branch
  delete_branch(db, branch_id, actor_id, enterprise_id) → None  (soft-delete)

Qoidalar:
  - enterprise_id ALBATTA INSERT da o'rnatiladi (multi-tenancy bug oldini olish).
  - version optimistik lock.
  - Har mutatsiyada audit_log yoziladi.
  - Soft-delete: deleted_at o'rnatiladi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.modules.branches.schemas import BranchCreate, BranchUpdate
from app.modules.rbac.enterprise_scope import apply_enterprise_filter

logger = logging.getLogger(__name__)


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="branch",
        entity_id=entity_id,
        before_json=json.dumps(before, default=str) if before else None,
        after_json=json.dumps(after, default=str) if after else None,
    )
    db.add(log)


# ─── Get ──────────────────────────────────────────────────────────────────────


async def get_branch(
    db: AsyncSession,
    branch_id: uuid.UUID,
    enterprise_id: uuid.UUID | None = None,
) -> Branch:
    """
    ID bo'yicha filial oladi.

    enterprise_id filtr — boshqa korxona filiali 404 qaytaradi.

    Raises:
        AppError("branches.not_found"): topilmasa yoki doiradan tashqari.
    """
    stmt = select(Branch).where(
        Branch.id == branch_id,
        Branch.deleted_at.is_(None),
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Branch.enterprise_id)

    result = await db.execute(stmt)
    branch = result.scalar_one_or_none()
    if branch is None:
        raise AppError("branches.not_found", status_code=404)
    return branch


# ─── List ─────────────────────────────────────────────────────────────────────


async def list_branches(
    db: AsyncSession,
    *,
    enterprise_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    is_active: bool | None = None,
) -> tuple[list[Branch], int]:
    """
    Paginated filiallar ro'yxati.

    Filtrlar:
      - is_active: faol/nofaol bo'yicha filtrlash
    """
    base_where = [Branch.deleted_at.is_(None)]

    if is_active is not None:
        base_where.append(Branch.is_active == is_active)

    # Jami soni
    count_stmt = select(func.count()).select_from(Branch).where(*base_where)
    count_stmt = apply_enterprise_filter(count_stmt, enterprise_id, Branch.enterprise_id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Ro'yxat
    stmt = (
        select(Branch)
        .where(*base_where)
        .order_by(Branch.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    stmt = apply_enterprise_filter(stmt, enterprise_id, Branch.enterprise_id)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Create ───────────────────────────────────────────────────────────────────


async def create_branch(
    db: AsyncSession,
    data: BranchCreate,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Branch:
    """
    Yangi filial yaratadi.

    enterprise_id SERVER tomonidan o'rnatiladi (klient bera olmaydi).

    Raises:
        AppError: enterprise_id bo'lmasa (superadmin filial yarata olmaydi).
    """
    if enterprise_id is None:
        raise AppError("branches.enterprise_required", status_code=403)

    branch = Branch(
        name=data.name,
        address=data.address,
        phone=data.phone,
        is_active=True,
        enterprise_id=enterprise_id,  # SERVER tomonidan o'rnatiladi
    )

    db.add(branch)
    await db.flush()

    after = {
        "id": str(branch.id),
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "enterprise_id": str(branch.enterprise_id),
    }
    await _write_audit(db, actor_id, "create", str(branch.id), after=after)

    return branch


# ─── Update ───────────────────────────────────────────────────────────────────


async def update_branch(
    db: AsyncSession,
    branch_id: uuid.UUID,
    data: BranchUpdate,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> Branch:
    """
    Filialni yangilaydi (PATCH — faqat berilgan maydonlar).

    Optimistik lock: data.version mos kelmasa → version_conflict.
    """
    branch = await get_branch(db, branch_id, enterprise_id=enterprise_id)

    if branch.version != data.version:
        raise AppError("branches.version_conflict", status_code=409)

    before = {
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "is_active": branch.is_active,
        "version": branch.version,
    }

    if data.name is not None:
        branch.name = data.name
    if data.address is not None:
        branch.address = data.address
    if data.phone is not None:
        branch.phone = data.phone
    if data.is_active is not None:
        branch.is_active = data.is_active

    branch.version = branch.version + 1
    branch.updated_at = _now()

    await db.flush()

    after = {
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "is_active": branch.is_active,
        "version": branch.version,
    }
    await _write_audit(db, actor_id, "update", str(branch.id), before=before, after=after)

    return branch


# ─── Delete (soft) ────────────────────────────────────────────────────────────


async def delete_branch(
    db: AsyncSession,
    branch_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
) -> None:
    """
    Filialni soft-delete qiladi (deleted_at o'rnatadi).

    Raises:
        AppError("branches.not_found"): topilmasa yoki doiradan tashqari.
    """
    branch = await get_branch(db, branch_id, enterprise_id=enterprise_id)
    branch.deleted_at = _now()
    branch.updated_at = _now()
    await db.flush()

    await _write_audit(db, actor_id, "delete", str(branch.id))
