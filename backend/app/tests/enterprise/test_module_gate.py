"""
MT3 — Module gating testlari.

Test stsenariyalar:
  1. Module enabled  → endpoint 200 (default korxona — barcha modul yoqilgan).
  2. Module DISABLED → 403 enterprise.module_disabled (promo o'chirilgan korxona).
  3. GET /enterprise/me → enabled_modules ro'yxati qaytadi.
  4. superadmin → gate bypass (403 bermaydi).
  5. GET /enterprise/me superadmin uchun → 404 (superadmin korxonasiz).

Testlar aiosqlite in-memory + fakeredis bilan — haqiqiy infra kerak emas.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.enterprise.conftest import get_token

pytestmark = pytest.mark.anyio


# ─── 1. Module enabled → 200 ──────────────────────────────────────────────────


async def test_promo_enabled_returns_200(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
):
    """
    Default korxona barcha modulni yoqqan → /promos endpointi 200 qaytaradi.
    Mavjud testlar buzilmasligi uchun asosiy shartni tekshiradi.
    """
    assert "promo" in (default_enterprise.enabled_modules or [])

    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.get(
        "/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 yoki 403-dan boshqa (masalan, 422/404 biznes logika — module gate emas)
    assert resp.status_code != 403, (
        f"promo yoqilgan bo'lsa gate 403 bermasligi kerak, lekin: {resp.text}"
    )


async def test_catalog_enabled_returns_not_403(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
):
    """catalog moduli yoqilgan → /catalog/categories 403 bermaydi."""
    assert "catalog" in (default_enterprise.enabled_modules or [])

    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.get(
        "/catalog/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code != 403, (
        f"catalog yoqilgan bo'lsa gate 403 bermasligi kerak: {resp.text}"
    )


# ─── 2. Module DISABLED → 403 ─────────────────────────────────────────────────


async def test_promo_disabled_returns_403(
    enterprise_client: AsyncClient,
    admin_user_no_promo: AppUser,
    disabled_promo_enterprise: Enterprise,
):
    """
    promo o'chirilgan korxona foydalanuvchisi /promos ga murojaat qilsa → 403.
    message_key = "enterprise.module_disabled".
    """
    assert "promo" not in (disabled_promo_enterprise.enabled_modules or [])

    token = await get_token(enterprise_client, admin_user_no_promo)
    resp = await enterprise_client.get(
        "/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"promo o'chirilgan korxona uchun 403 kutilgan, lekin: {resp.status_code} {resp.text}"
    )
    data = resp.json()
    assert data.get("message_key") == "enterprise.module_disabled", (
        f"Noto'g'ri message_key: {data}"
    )


async def test_promo_disabled_post_returns_403(
    enterprise_client: AsyncClient,
    admin_user_no_promo: AppUser,
):
    """promo o'chirilgan korxona — POST /promos ham 403."""
    token = await get_token(enterprise_client, admin_user_no_promo)
    resp = await enterprise_client.post(
        "/promos",
        headers={"Authorization": f"Bearer {token}"},
        json={"name_uz": "test", "name_ru": "test", "promo_type": "discount"},
    )
    assert resp.status_code == 403
    assert resp.json().get("message_key") == "enterprise.module_disabled"


# ─── 3. GET /enterprise/me ────────────────────────────────────────────────────


async def test_enterprise_me_returns_enabled_modules(
    enterprise_client: AsyncClient,
    admin_user: AppUser,
    default_enterprise: Enterprise,
):
    """GET /enterprise/me → korxona ma'lumotlari + enabled_modules qaytadi."""
    token = await get_token(enterprise_client, admin_user)
    resp = await enterprise_client.get(
        "/enterprise/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"200 kutilgan: {resp.text}"
    data = resp.json()

    assert "id" in data
    assert "name" in data
    assert "status" in data
    assert "enabled_modules" in data

    # Default korxona barcha modulni yoqqan
    assert set(data["enabled_modules"]) == set(ALL_MODULE_KEYS), (
        f"Barcha modullar kutilgan, lekin: {data['enabled_modules']}"
    )


async def test_enterprise_me_disabled_promo_shows_in_list(
    enterprise_client: AsyncClient,
    admin_user_no_promo: AppUser,
    disabled_promo_enterprise: Enterprise,
):
    """promo o'chirilgan korxona — /enterprise/me promo'siz ro'yxat qaytaradi."""
    token = await get_token(enterprise_client, admin_user_no_promo)
    resp = await enterprise_client.get(
        "/enterprise/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "promo" not in data["enabled_modules"], (
        f"promo o'chirilgan bo'lishi kerak: {data['enabled_modules']}"
    )
    # Boshqa modullar mavjud bo'lishi kerak
    assert "catalog" in data["enabled_modules"]


async def test_enterprise_me_requires_auth(
    enterprise_client: AsyncClient,
):
    """GET /enterprise/me — autentifikatsiyasiz 401."""
    resp = await enterprise_client.get("/enterprise/me")
    assert resp.status_code == 401


# ─── 4. superadmin bypass ─────────────────────────────────────────────────────


async def test_superadmin_bypasses_module_gate(
    enterprise_client: AsyncClient,
    superadmin_user: AppUser,
    disabled_promo_enterprise: Enterprise,
):
    """
    superadmin (enterprise_id=None) → gate bypass — promo o'chirilgan bo'lsa ham 403 bermaydi.

    Eslatma: superadmin'ning o'z enterprise yo'q — disabled_promo_enterprise fixture
    DB da mavjud bo'lsa ham, superadmin unga tegishli emas.
    Gate 403 bermasligi tekshiriladi (biznes logika xatosi boshqa status berishi mumkin).
    """
    assert superadmin_user.enterprise_id is None

    token = await get_token(enterprise_client, superadmin_user)
    resp = await enterprise_client.get(
        "/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Gate bypass: 403 bo'lmasligi kerak (boshqa status — biznes logika)
    assert resp.status_code != 403, (
        f"superadmin gate bypass bo'lishi kerak, 403 bermaydi: {resp.text}"
    )


# ─── 5. superadmin /enterprise/me → 404 ──────────────────────────────────────


async def test_superadmin_enterprise_me_returns_404(
    enterprise_client: AsyncClient,
    superadmin_user: AppUser,
):
    """superadmin (enterprise_id=None) → GET /enterprise/me 404 qaytaradi."""
    token = await get_token(enterprise_client, superadmin_user)
    resp = await enterprise_client.get(
        "/enterprise/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, (
        f"superadmin uchun 404 kutilgan: {resp.status_code} {resp.text}"
    )


# ─── 6. Qo'shimcha tekshiruvlar ────────────────────────────────────────────────


async def test_module_disabled_message_bilingual(
    enterprise_client: AsyncClient,
    admin_user_no_promo: AppUser,
):
    """enterprise.module_disabled xabari uz tilida qaytadi."""
    token = await get_token(enterprise_client, admin_user_no_promo)
    resp = await enterprise_client.get(
        "/promos",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "uz",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    # message_key to'g'ri
    assert data["message_key"] == "enterprise.module_disabled"
    # xabar matni bo'sh emas
    assert data["message"]
    # 'promo' modul nomi xabarda aks etadi
    assert "promo" in data["message"]


async def test_module_disabled_message_russian(
    enterprise_client: AsyncClient,
    admin_user_no_promo: AppUser,
):
    """enterprise.module_disabled xabari ru tilida qaytadi."""
    token = await get_token(enterprise_client, admin_user_no_promo)
    resp = await enterprise_client.get(
        "/promos",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "enterprise.module_disabled"
    assert "promo" in data["message"]
