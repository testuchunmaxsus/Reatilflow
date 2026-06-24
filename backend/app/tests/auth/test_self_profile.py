"""
PATCH /auth/me — self-service profil yangilash testlari.

Har qanday autentifikatsiyalangan rol O'Z full_name/locale ni yangilay oladi
(alohida RBAC ruxsati kerak emas). phone/role/enterprise_id O'ZGARMAYDI.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import AppUser
from app.tests.auth.conftest import TEST_PASSWORD, TEST_PHONE


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_patch_me_updates_name_and_locale(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    token = await _login(auth_client)
    resp = await auth_client.patch(
        "/auth/me",
        json={"full_name": "Yangilangan Ism", "locale": "ru"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Yangilangan Ism"
    assert body["locale"] == "ru"
    # phone (login) o'zgarmaydi
    assert body["phone"] == TEST_PHONE


@pytest.mark.asyncio
async def test_patch_me_requires_auth(auth_client: AsyncClient, test_user: AppUser) -> None:
    resp = await auth_client.patch("/auth/me", json={"full_name": "X"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_me_ignores_protected_fields(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """role/phone kabi himoyalangan maydonlar SelfProfileUpdate da yo'q — e'tiborsiz."""
    token = await _login(auth_client)
    resp = await auth_client.patch(
        "/auth/me",
        json={
            "full_name": "Faqat Ism",
            "role": "superadmin",            # e'tiborsiz qoldirilishi kerak
            "phone": "+998900000000",        # e'tiborsiz qoldirilishi kerak
            "is_active": False,              # e'tiborsiz qoldirilishi kerak
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Faqat Ism"
    assert body["role"] == "administrator"   # o'zgarmadi
    assert body["phone"] == TEST_PHONE       # o'zgarmadi
    assert body["is_active"] is True         # o'zgarmadi


@pytest.mark.asyncio
async def test_patch_me_invalid_locale_rejected(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    token = await _login(auth_client)
    resp = await auth_client.patch(
        "/auth/me",
        json={"locale": "en"},  # faqat uz|ru ruxsat
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
