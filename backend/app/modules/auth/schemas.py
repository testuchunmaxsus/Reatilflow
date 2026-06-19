"""
Auth moduli Pydantic sxemalari.

LoginRequest     — telefon + parol bilan kirish
TokenPair        — access + refresh token javob
RefreshRequest   — refresh token bilan yangilash
LogoutRequest    — refresh token bilan chiqish
MeResponse       — joriy foydalanuvchi ma'lumotlari
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Telefon + parol bilan kirish so'rovi."""

    phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        examples=["+998901234567"],
        description="Foydalanuvchi telefon raqami (login)",
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="Foydalanuvchi paroli (tekis matn — HTTPS orqali)",
    )


class TokenPair(BaseModel):
    """
    Muvaffaqiyatli login yoki refresh javob sxemasi.

    access_token  — 15 daqiqa amal qiladi
    refresh_token — 30 kun amal qiladi (rotatsiyali)
    token_type    — har doim "bearer"
    """

    access_token: str = Field(..., description="JWT access token (Bearer)")
    refresh_token: str = Field(..., description="JWT refresh token (rotatsiyali)")
    token_type: str = Field(default="bearer", description="Token turi")


class RefreshRequest(BaseModel):
    """Refresh token bilan yangi token juft olish so'rovi."""

    refresh_token: str = Field(..., description="Amal qilayotgan refresh token")


class LogoutRequest(BaseModel):
    """Chiqish — refresh tokenni denylist ga qo'shish."""

    refresh_token: str = Field(..., description="Denylist ga qo'shiladigan refresh token")


class MeResponse(BaseModel):
    """Joriy autentifikatsiyalangan foydalanuvchi ma'lumotlari."""

    id: uuid.UUID = Field(..., description="Foydalanuvchi UUID")
    phone: str = Field(..., description="Telefon raqami")
    full_name: str = Field(..., description="To'liq ismi")
    role: str = Field(..., description="Rol: administrator | agent | courier | accountant | store")
    branch_id: uuid.UUID | None = Field(None, description="Filial ID (None = barcha filiallar)")
    locale: str = Field(..., description="Til: uz | ru")
    is_active: bool = Field(..., description="Hisob holati")
    biometric_enrolled: bool = Field(..., description="Biometrik ro'yxatga olinganmi")
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Rolning ruxsatlari ro'yxati ('module:action' formatida). "
            "T2 RBAC tomonidan to'ldiriladi."
        ),
    )

    model_config = {"from_attributes": True}
