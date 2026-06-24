"""
Superadmin moduli Pydantic sxemalari — MT4.

Sxemalar:
  EnterpriseCreate          — POST /superadmin/enterprises so'rovi
  FirstAdminCreate          — birinchi administrator ma'lumoti (EnterpriseCreate ichida)
  EnterpriseUpdate          — PATCH /superadmin/enterprises/{id} so'rovi
  EnterpriseAdminOut        — POST javob: korxona + admin (parolsiz)
  EnterprisePaginated       — GET ro'yxat javob
  AdminOut                  — birinchi admin javob sxemasi (parol QAYTARILMAYDI)
  StatsOut                  — GET /superadmin/stats javob
  EnterpriseAdminListItem   — admins[] ichidagi element
  EnterpriseDetailOut       — GET /superadmin/enterprises/{id} kengaytirilgan javob
  ResetPasswordIn           — POST reset-admin-password so'rovi
  ResetPasswordOut          — POST reset-admin-password javob
  SuperadminUserOut         — cross-tenant users elementi
  PaginatedSuperadminUsers  — GET /superadmin/users paginated javob
  AuditLogOut               — GET /superadmin/audit-logs elementi
  PaginatedAuditLogs        — GET /superadmin/audit-logs paginated javob
  SuperadminBannerOut       — GET /superadmin/banners elementi (enterprise_name bilan)
  PaginatedSuperadminBanners — GET /superadmin/banners paginated javob
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enterprise import ALL_MODULE_KEYS


# ─── Ichki yordamchi ─────────────────────────────────────────────────────────


class FirstAdminCreate(BaseModel):
    """Yangi korxonaning birinchi administratori uchun ma'lumotlar."""

    full_name: str = Field(..., min_length=1, max_length=255, description="To'liq ismi")
    phone: str = Field(..., min_length=7, max_length=20, description="Telefon (login, PII)")
    password: str = Field(..., min_length=6, max_length=128, description="Parol (hash qilinadi)")
    locale: str = Field("uz", min_length=2, max_length=5, description="Til: uz | ru")


# ─── EnterpriseCreate ────────────────────────────────────────────────────────


class EnterpriseCreate(BaseModel):
    """POST /superadmin/enterprises so'rovi."""

    name: str = Field(..., min_length=1, max_length=255, description="Korxona nomi")
    inn: str | None = Field(None, max_length=20, description="Soliq raqami (ixtiyoriy)")
    enabled_modules: list[str] = Field(
        default_factory=lambda: list(ALL_MODULE_KEYS),
        description="Yoqilgan modul kalitlari (default: hammasi)",
    )
    first_admin: FirstAdminCreate = Field(..., description="Birinchi administrator ma'lumotlari")


# ─── EnterpriseUpdate ────────────────────────────────────────────────────────


class EnterpriseUpdate(BaseModel):
    """PATCH /superadmin/enterprises/{id} so'rovi."""

    name: str | None = Field(None, min_length=1, max_length=255)
    enabled_modules: list[str] | None = None
    status: str | None = Field(None, description="active | suspended")
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")


# ─── Javob sxemalari ─────────────────────────────────────────────────────────


class AdminOut(BaseModel):
    """Birinchi admin javob sxemasi — parol HECH QACHON chiqarilmaydi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone: str
    role: str
    locale: str
    is_active: bool
    enterprise_id: uuid.UUID | None
    created_at: datetime


class EnterpriseOut(BaseModel):
    """Korxona javob sxemasi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    inn: str | None = None
    status: str
    enabled_modules: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class EnterpriseAdminOut(BaseModel):
    """POST /superadmin/enterprises javob: korxona + admin (parolsiz)."""

    enterprise: EnterpriseOut
    admin: AdminOut


class EnterprisePaginated(BaseModel):
    """GET /superadmin/enterprises paginated javob."""

    items: list[EnterpriseOut]
    total: int
    limit: int
    offset: int


# ─── Stats ───────────────────────────────────────────────────────────────────


class StatsOut(BaseModel):
    """GET /superadmin/stats javob."""

    model_config = ConfigDict(from_attributes=True)

    enterprises_total: int
    enterprises_active: int
    enterprises_suspended: int
    users_total: int
    enterprises_new_7d: int


# ─── Enterprise Detail ────────────────────────────────────────────────────────


class EnterpriseAdminListItem(BaseModel):
    """admins[] ro'yxatidagi administrator elementi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone: str
    role: str
    is_active: bool
    created_at: datetime


class EnterpriseDetailOut(EnterpriseOut):
    """
    GET /superadmin/enterprises/{id} kengaytirilgan javob.

    EnterpriseOut barcha maydonlari + user_count + admins.
    """

    user_count: int
    admins: list[EnterpriseAdminListItem]


# ─── Reset Admin Password ─────────────────────────────────────────────────────


class ResetPasswordIn(BaseModel):
    """POST /superadmin/enterprises/{id}/reset-admin-password so'rovi."""

    user_id: uuid.UUID = Field(..., description="Paroli tiklanadigian foydalanuvchi ID")
    new_password: str | None = Field(
        None,
        min_length=12,
        description="Yangi parol (null bo'lsa server kuchli parol generatsiya qiladi)",
    )


class ResetPasswordOut(BaseModel):
    """POST /superadmin/enterprises/{id}/reset-admin-password javob."""

    user_id: uuid.UUID
    new_password: str = Field(..., description="Yangi parol (faqat shu javobda bir marta ko'rsatiladi)")


# ─── Cross-tenant Users ───────────────────────────────────────────────────────


class SuperadminUserOut(BaseModel):
    """GET /superadmin/users — bitta foydalanuvchi elementi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone: str
    role: str
    is_active: bool
    enterprise_id: uuid.UUID | None
    enterprise_name: str | None
    created_at: datetime


class PaginatedSuperadminUsers(BaseModel):
    """GET /superadmin/users paginated javob."""

    items: list[SuperadminUserOut]
    total: int
    limit: int
    offset: int


# ─── Audit Logs ───────────────────────────────────────────────────────────────


class AuditLogOut(BaseModel):
    """GET /superadmin/audit-logs — bitta audit yozuvi elementi."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    before_json: str | None
    after_json: str | None
    ip: str | None
    at: datetime
    enterprise_id: uuid.UUID | None


class PaginatedAuditLogs(BaseModel):
    """GET /superadmin/audit-logs paginated javob."""

    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int


# ─── Superadmin Banners ───────────────────────────────────────────────────────


class SuperadminBannerOut(BaseModel):
    """GET /superadmin/banners — bitta banner elementi (enterprise_name bilan)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    enterprise_id: uuid.UUID
    enterprise_name: str | None
    title: str
    image_url: str | None
    target_url: str | None
    target_product_id: uuid.UUID | None
    is_active: bool
    priority: int
    valid_from: date
    valid_to: date
    created_at: datetime
    updated_at: datetime


class PaginatedSuperadminBanners(BaseModel):
    """GET /superadmin/banners paginated javob."""

    items: list[SuperadminBannerOut]
    total: int
    limit: int
    offset: int
