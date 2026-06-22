"""
Superadmin endpointlari testlari — MT4.

Scenariylar:
  1. superadmin korxona + birinchi-admin yaratadi → admin login qila oladi
  2. non-superadmin (administrator/agent) /superadmin/* → 403
  3. tokensiz /superadmin/* → 401
  4. GET /superadmin/enterprises — ro'yxat qaytaradi
  5. GET /superadmin/enterprises/{id} — bitta korxona
  6. PATCH /superadmin/enterprises/{id} — yangilash
  7. suspend → o'sha korxona useri login → 403 enterprise.suspended
  8. activate → yana ishlaydi
  9. enabled_modules PATCH → /enterprise/me yangi ro'yxat
  10. version conflict → 409
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.superadmin.conftest import (
    SUSPENDED_ADMIN_PHONE,
    TEST_PASSWORD,
)


# ─── 1. superadmin korxona + admin yaratadi ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_enterprise_success(
    superadmin_client: AsyncClient,
) -> None:
    """superadmin korxona + birinchi admin yaratadi → 201."""
    resp = await superadmin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Yangi Korxona",
            "inn": "111222333",
            "enabled_modules": list(ALL_MODULE_KEYS),
            "first_admin": {
                "full_name": "Yangi Admin",
                "phone": "+998901111234",
                "password": "AdminPass123!",
                "locale": "uz",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "enterprise" in data
    assert "admin" in data
    assert data["enterprise"]["name"] == "Yangi Korxona"
    assert data["enterprise"]["inn"] == "111222333"
    assert data["enterprise"]["status"] == "active"
    assert data["admin"]["role"] == "administrator"
    assert data["admin"]["phone"] == "+998901111234"
    # Parol javobda bo'lmasligi shart
    assert "password" not in data["admin"]
    assert "password_hash" not in data["admin"]


@pytest.mark.asyncio
async def test_create_enterprise_admin_has_correct_enterprise_id(
    superadmin_client: AsyncClient,
) -> None:
    """Yaratilgan adminning enterprise_id yangi korxona ID'siga mos kelishi shart."""
    resp = await superadmin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Scoped Test Korxona",
            "first_admin": {
                "full_name": "Scoped Admin",
                "phone": "+998901111235",
                "password": "ScopedPass123!",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["admin"]["enterprise_id"] == data["enterprise"]["id"]


@pytest.mark.asyncio
async def test_create_enterprise_default_modules(
    superadmin_client: AsyncClient,
) -> None:
    """enabled_modules berilmasa default (hammasi) qo'llaniladi."""
    resp = await superadmin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Default Modules Korxona",
            "first_admin": {
                "full_name": "Admin",
                "phone": "+998901111236",
                "password": "Pass123!",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # Default: hamma modul
    assert set(data["enterprise"]["enabled_modules"]) == set(ALL_MODULE_KEYS)


# ─── 2. non-superadmin /superadmin/* → 403 ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_enterprise_as_admin_returns_403(
    admin_client: AsyncClient,
) -> None:
    """administrator /superadmin/enterprises ga so'rov → 403."""
    resp = await admin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Test",
            "first_admin": {
                "full_name": "Test",
                "phone": "+998901111237",
                "password": "Pass123!",
            },
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_list_enterprises_as_admin_returns_403(
    admin_client: AsyncClient,
) -> None:
    """administrator GET /superadmin/enterprises → 403."""
    resp = await admin_client.get("/superadmin/enterprises")
    assert resp.status_code == 403, resp.text


# ─── 3. tokensiz → 401 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_enterprises_no_auth_returns_401(
    no_auth_client: AsyncClient,
) -> None:
    """Tokensiz GET /superadmin/enterprises → 401."""
    resp = await no_auth_client.get("/superadmin/enterprises")
    assert resp.status_code == 401, resp.text


# ─── 4. GET ro'yxat ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_enterprises_returns_200(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """superadmin barcha korxonalarni ko'ra oladi."""
    resp = await superadmin_client.get("/superadmin/enterprises")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    ids = [e["id"] for e in data["items"]]
    assert str(default_enterprise.id) in ids


@pytest.mark.asyncio
async def test_list_enterprises_pagination(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """limit/offset parametrlari ishlaydi."""
    resp = await superadmin_client.get("/superadmin/enterprises?limit=1&offset=0")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) <= 1


# ─── 5. GET bitta korxona ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_single_enterprise_returns_200(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """superadmin bitta korxonani ko'ra oladi."""
    resp = await superadmin_client.get(f"/superadmin/enterprises/{default_enterprise.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(default_enterprise.id)
    assert data["name"] == default_enterprise.name


@pytest.mark.asyncio
async def test_get_nonexistent_enterprise_returns_404(
    superadmin_client: AsyncClient,
) -> None:
    """Mavjud bo'lmagan ID → 404."""
    resp = await superadmin_client.get(f"/superadmin/enterprises/{uuid.uuid4()}")
    assert resp.status_code == 404, resp.text


# ─── 6. PATCH yangilash ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_enterprise_name(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """PATCH — name yangilash ishlaydi."""
    current_version = default_enterprise.version
    resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}",
        json={"name": "Yangilangan Korxona", "version": current_version},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Yangilangan Korxona"
    assert data["version"] == current_version + 1


@pytest.mark.asyncio
async def test_patch_enterprise_modules(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """PATCH — enabled_modules yangilash ishlaydi."""
    new_modules = ["catalog", "orders", "stock"]
    resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}",
        json={"enabled_modules": new_modules, "version": default_enterprise.version},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data["enabled_modules"]) == set(new_modules)


@pytest.mark.asyncio
async def test_patch_enterprise_version_conflict(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """Noto'g'ri version → 409."""
    resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}",
        json={"name": "Konflikt Test", "version": 9999},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["message_key"] == "superadmin.version_conflict"


# ─── 7. Suspend → login 403 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suspended_enterprise_user_cannot_login(
    no_auth_client: AsyncClient,
    suspended_admin_user: AppUser,
) -> None:
    """suspended korxona foydalanuvchisi login → 403 enterprise.suspended."""
    resp = await no_auth_client.post(
        "/auth/login",
        json={"phone": SUSPENDED_ADMIN_PHONE, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["message_key"] == "enterprise.suspended"


@pytest.mark.asyncio
async def test_suspend_and_activate_flow(
    superadmin_client: AsyncClient,
    no_auth_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
    db_session: AsyncSession,
) -> None:
    """
    Suspend → login 403 → activate → login 200 oqimi.
    """
    from app.tests.superadmin.conftest import ADMIN_PHONE

    # Avval suspend
    resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}/suspend",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"

    # Suspended bo'lganda login → 403
    resp = await no_auth_client.post(
        "/auth/login",
        json={"phone": ADMIN_PHONE, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["message_key"] == "enterprise.suspended"

    # Activate
    # version endi +1 bo'ldi — yangilangan versiyani olish uchun GET qilamiz
    get_resp = await superadmin_client.get(
        f"/superadmin/enterprises/{default_enterprise.id}"
    )
    assert get_resp.status_code == 200
    # activate versiya talab qilmaydi (alohida endpoint)
    resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}/activate",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"

    # Activate keyin login → 200
    resp = await no_auth_client.post(
        "/auth/login",
        json={"phone": ADMIN_PHONE, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


# ─── 8. enabled_modules PATCH → /enterprise/me yangi ro'yxat ─────────────────


@pytest.mark.asyncio
async def test_patch_modules_reflected_in_enterprise_me(
    superadmin_client: AsyncClient,
    admin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """PATCH enabled_modules → /enterprise/me yangi ro'yxatni qaytaradi."""
    new_modules = ["catalog", "orders"]

    # Modullarni yangilash
    patch_resp = await superadmin_client.patch(
        f"/superadmin/enterprises/{default_enterprise.id}",
        json={"enabled_modules": new_modules, "version": default_enterprise.version},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    # Admin /enterprise/me ni tekshiradi
    me_resp = await admin_client.get("/enterprise/me")
    assert me_resp.status_code == 200, me_resp.text
    me_data = me_resp.json()
    assert set(me_data["enabled_modules"]) == set(new_modules)


# ─── 9. Superadmin enterprise_id=NULL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_enterprise_id_is_null(
    superadmin_user: AppUser,
) -> None:
    """superadmin enterprise_id=None bo'lishi shart."""
    assert superadmin_user.enterprise_id is None
    assert superadmin_user.role == "superadmin"


# ─── 10. Duplicate phone → 409 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_enterprise_duplicate_phone_returns_409(
    superadmin_client: AsyncClient,
) -> None:
    """Bir xil telefon bilan ikkinchi admin yaratishga urinish → 409."""
    phone = "+998901999001"

    # Birinchi korxona + admin
    resp1 = await superadmin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Korxona 1",
            "first_admin": {
                "full_name": "Admin 1",
                "phone": phone,
                "password": "Pass123!",
            },
        },
    )
    assert resp1.status_code == 201, resp1.text

    # Xuddi shu telefon bilan ikkinchi korxona
    resp2 = await superadmin_client.post(
        "/superadmin/enterprises",
        json={
            "name": "Korxona 2",
            "first_admin": {
                "full_name": "Admin 2",
                "phone": phone,
                "password": "Pass123!",
            },
        },
    )
    assert resp2.status_code == 409, resp2.text


# ─── 11. superadmin /enterprise/me → 404 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_enterprise_me_returns_404(
    superadmin_client: AsyncClient,
) -> None:
    """superadmin /enterprise/me ga so'rov → 404 (korxonasiz)."""
    resp = await superadmin_client.get("/enterprise/me")
    assert resp.status_code == 404, resp.text
