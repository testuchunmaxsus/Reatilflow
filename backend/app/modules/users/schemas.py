"""
Users moduli Pydantic v2 sxemalari — foydalanuvchilar CRUD.

Sxemalar:
  UserCreate      — yangi foydalanuvchi yaratish (admin only)
  UserUpdate      — foydalanuvchi yangilash (PATCH, optimistik lock)
  UserOut         — to'liq javob (phone admin'ga ko'rinadi; password_hash HECH QACHON chiqmaydi)
  PaginatedUsers  — paginated foydalanuvchilar ro'yxati

Xavfsizlik:
  - password_hash hech qachon UserOut'ga kiritilmaydi.
  - phone PII — foydalanuvchiga deshifrlanib ko'rsatiladi.
  - full_name PII — deshifrlanib ko'rsatiladi.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# Tizimda mavjud 5 ta rol
VALID_ROLES: frozenset[str] = frozenset({
    "administrator", "agent", "courier", "accountant", "store"
})


# ─── UserCreate ───────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """Yangi foydalanuvchi yaratish so'rovi (faqat administrator)."""

    full_name: str = Field(..., min_length=1, max_length=255, description="To'liq ismi")
    phone: str = Field(..., min_length=7, max_length=20, description="Telefon raqami (login uchun, PII)")
    role: str = Field(..., description="administrator | agent | courier | accountant | store")
    branch_id: uuid.UUID | None = Field(None, description="Filial ID (NULL = barcha filiallar)")
    locale: str = Field("uz", min_length=2, max_length=5, description="Foydalanuvchi tili: uz | ru")
    password: str = Field(..., min_length=6, max_length=128, description="Tekis parol (hash qilinadi)")
    biometric_enrolled: bool = Field(False, description="Biometrik ro'yxat flagi")
    device_id: str | None = Field(None, max_length=255, description="Qurilma ID (ixtiyoriy)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    @model_validator(mode="after")
    def validate_role(self) -> "UserCreate":
        """Rol faqat qonuniy 5 ta qiymatdan biri bo'lishi shart."""
        if self.role not in VALID_ROLES:
            from app.core.errors import AppError
            raise AppError(
                "users.invalid_role",
                status_code=422,
            )
        return self


# ─── UserUpdate ───────────────────────────────────────────────────────────────


class UserUpdate(BaseModel):
    """Foydalanuvchi yangilash so'rovi (PATCH — faqat berilgan maydonlar yangilanadi)."""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, min_length=7, max_length=20)
    role: str | None = Field(None, description="administrator | agent | courier | accountant | store")
    branch_id: uuid.UUID | None = None
    locale: str | None = Field(None, min_length=2, max_length=5)
    biometric_enrolled: bool | None = None
    device_id: str | None = None
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")

    @model_validator(mode="after")
    def validate_fields(self) -> "UserUpdate":
        """version dan tashqari kamida bitta maydon berilishi shart; rol qonuniy bo'lsin."""
        fields = {"full_name", "phone", "role", "branch_id", "locale", "biometric_enrolled", "device_id"}
        if not any(getattr(self, f) is not None for f in fields):
            raise ValueError("Kamida bitta maydon yangilanishi shart")
        if self.role is not None and self.role not in VALID_ROLES:
            from app.core.errors import AppError
            raise AppError("users.invalid_role", status_code=422)
        return self


# ─── UserOut ──────────────────────────────────────────────────────────────────


class UserOut(BaseModel):
    """
    Foydalanuvchi to'liq javob sxemasi.

    password_hash HECH QACHON chiqarilmaydi.
    phone va full_name deshifrlanib (EncryptedString orqali) qaytadi.
    """

    id: uuid.UUID
    full_name: str
    phone: str
    role: str
    branch_id: uuid.UUID | None
    locale: str
    biometric_enrolled: bool
    device_id: str | None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── PaginatedUsers ───────────────────────────────────────────────────────────


class PaginatedUsers(BaseModel):
    """Paginated foydalanuvchilar ro'yxati javob sxemasi."""

    items: list[UserOut]
    total: int = Field(..., description="Jami topilgan foydalanuvchilar soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
