"""
PATCH /enterprise/me/modules testlari — MT5 (A qism).

Stsenariylar:
  1. administrator o'z modullarini yangilaydi → 200 + yangi ro'yxat
  2. administrator bo'sh ro'yxat yuboradi → 200 (barcha o'chiriladi)
  3. Noma'lum modul kalitlari olib tashlanadi
  4. administrator bo'lmagan rol (agent) → 403
  5. superadmin (enterprise_id=None) → 404
  6. Autentifikatsiyasiz → 401
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token, hash_password
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.enterprise.conftest import (
    DISABLED_PROMO_ENTERPRISE_UUID,
    get_token,
    TEST_PASSWORD,
)
from app.tests.conftest import TEST_ENTERPRISE_UUID

pytestmark = pytest.mark.anyio


# ─── 1. Administrator modullarni yangilaydi ───────────────────────────────────


async def test_update_my_modules_success(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
) -> None:
    """administrator o'z enabled_modules'ni yangilaydi → 200."""
    new_modules = ["catalog", "orders", "customers"]

    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": new_modules},
    )
    assert resp.status_code == 200, f"200 kutilgan: {resp.text}"
    data = resp.json()

    assert "enabled_modules" in data
    assert set(data["enabled_modules"]) == set(new_modules), (
        f"Yangilangan ro'yxat kutilgan {new_modules}, lekin: {data['enabled_modules']}"
    )


# ─── 2. Bo'sh ro'yxat (barcha modullar o'chiriladi) ──────────────────────────


async def test_update_my_modules_empty_list(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
) -> None:
    """administrator bo'sh ro'yxat yuboradi → 200, hamma modul o'chiriladi."""
    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": []},
    )
    assert resp.status_code == 200, f"200 kutilgan: {resp.text}"
    data = resp.json()
    assert data["enabled_modules"] == []


# ─── 3. Noma'lum modul kalitlari olib tashlanadi ─────────────────────────────


async def test_update_my_modules_unknown_keys_filtered(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
) -> None:
    """Noma'lum modul kalitlari olib tashlanadi, to'g'rilar saqlanadi."""
    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": ["catalog", "UNKNOWN_MODULE", "promo", "invalid"]},
    )
    assert resp.status_code == 200, f"200 kutilgan: {resp.text}"
    data = resp.json()
    # Faqat to'g'ri kalitlar saqlanishi kerak
    assert set(data["enabled_modules"]) == {"catalog", "promo"}


# ─── 4. Agent roli → 403 ─────────────────────────────────────────────────────


async def test_update_my_modules_agent_forbidden(
    enterprise_client: AsyncClient,
    make_user,
    default_enterprise: Enterprise,
) -> None:
    """agent roli → 403 (faqat administrator)."""
    agent = await make_user("agent")
    token = await get_token(enterprise_client, agent)
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": ["catalog"]},
    )
    assert resp.status_code == 403, f"403 kutilgan: {resp.status_code} {resp.text}"


# ─── 5. superadmin (enterprise_id=None) → 404 ────────────────────────────────


async def test_update_my_modules_superadmin_404(
    enterprise_client: AsyncClient,
    superadmin_user: AppUser,
) -> None:
    """superadmin enterprise_id=None → 404."""
    token = await get_token(enterprise_client, superadmin_user)
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": ["catalog"]},
    )
    assert resp.status_code == 404, f"404 kutilgan: {resp.status_code} {resp.text}"


# ─── 6. Autentifikatsiyasiz → 401 ────────────────────────────────────────────


async def test_update_my_modules_no_auth(
    enterprise_client: AsyncClient,
) -> None:
    """Token yo'q → 401."""
    resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        json={"enabled_modules": ["catalog"]},
    )
    assert resp.status_code == 401, f"401 kutilgan: {resp.status_code} {resp.text}"


# ─── 7. Yangilangan ma'lumot GET /enterprise/me da aks etadi ─────────────────


async def test_update_my_modules_reflects_in_get(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
) -> None:
    """PATCH dan keyin GET /enterprise/me yangilangan modullarni qaytaradi."""
    new_modules = ["catalog", "finance"]
    token = await get_token(enterprise_client, admin_user)

    # Yangilash
    patch_resp = await enterprise_client.patch(
        "/enterprise/me/modules",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_modules": new_modules},
    )
    assert patch_resp.status_code == 200

    # GET bilan tekshirish
    get_resp = await enterprise_client.get(
        "/enterprise/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert set(data["enabled_modules"]) == set(new_modules), (
        f"GET /enterprise/me yangilangan ro'yxatni qaytarishi kerak: {data['enabled_modules']}"
    )
