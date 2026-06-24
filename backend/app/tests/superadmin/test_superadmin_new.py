"""
Yangi superadmin endpointlari testlari — MT4 kengaytmasi.

Scenariylar:
  1.  GET /superadmin/stats — to'g'ri hisob-kitob
  2.  GET /superadmin/stats — enterprises_new_7d sanash
  3.  GET /superadmin/enterprises?search — name bo'yicha qidiruv
  4.  GET /superadmin/enterprises?search — INN bo'yicha qidiruv
  5.  GET /superadmin/enterprises?status — filtrlash
  6.  DELETE /superadmin/enterprises/{id} — soft-delete 204
  7.  DELETE /superadmin/enterprises/{id} — o'chirilgan keyin 404
  8.  DELETE /superadmin/enterprises/DEFAULT — 422 cannot_delete_default
  9.  GET /superadmin/enterprises/{id} — detail: user_count + admins
  10. GET /superadmin/enterprises/{id} — topilmasa 404
  11. POST /superadmin/enterprises/{id}/reset-admin-password — parol tiklash (explicit)
  12. POST /superadmin/enterprises/{id}/reset-admin-password — null → generatsiya
  13. POST /superadmin/enterprises/{id}/reset-admin-password — boshqa korxona user → 404
  14. GET /superadmin/users — barcha users
  15. GET /superadmin/users?enterprise_id — filtr
  16. GET /superadmin/users?role — rol filtri
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import hash_password
from app.models.enterprise import DEFAULT_ENTERPRISE_UUID, Enterprise
from app.models.user import AppUser
from app.tests.conftest import TEST_ENTERPRISE_UUID
from app.tests.superadmin.conftest import (
    ADMIN_PHONE,
    TEST_PASSWORD,
)


# ─── Yordamchi: ikkinchi korxona yaratish ─────────────────────────────────────


async def _make_enterprise(
    db: AsyncSession,
    name: str = "Ikkinchi Korxona",
    inn: str | None = "555666777",
    status: str = "active",
) -> Enterprise:
    ent = Enterprise(
        id=uuid.uuid4(),
        name=name,
        inn=inn,
        status=status,
        enabled_modules=["catalog"],
        version=1,
    )
    db.add(ent)
    await db.flush()
    return ent


async def _make_user(
    db: AsyncSession,
    enterprise: Enterprise,
    role: str = "agent",
    phone: str | None = None,
) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Test User",
        phone=phone or f"+9989{uuid.uuid4().int % 900000000 + 100000000:09d}",
        role=role,
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    await db.flush()
    return user


# ─── 1. GET /superadmin/stats — to'g'ri hisob-kitob ─────────────────────────


@pytest.mark.asyncio
async def test_stats_basic_counts(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
) -> None:
    """stats: enterprises_total >= 1, users_total >= 1."""
    resp = await superadmin_client.get("/superadmin/stats")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "enterprises_total" in data
    assert "enterprises_active" in data
    assert "enterprises_suspended" in data
    assert "users_total" in data
    assert "enterprises_new_7d" in data

    assert data["enterprises_total"] >= 1
    assert data["users_total"] >= 1  # admin_user enterprise ga bog'liq


@pytest.mark.asyncio
async def test_stats_suspended_count(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """stats: suspended korxona suspended hisobga olinadi."""
    # Suspended korxona qo'shish
    susp = await _make_enterprise(db_session, name="Susp Ent", status="suspended")

    resp = await superadmin_client.get("/superadmin/stats")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["enterprises_suspended"] >= 1


# ─── 2. stats enterprises_new_7d ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_new_7d_counts_recent(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """stats: default_enterprise yangi (hozirgina yaratilgan) → new_7d >= 1."""
    resp = await superadmin_client.get("/superadmin/stats")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["enterprises_new_7d"] >= 1


# ─── 3. GET /superadmin/enterprises?search (name) ─────────────────────────────


@pytest.mark.asyncio
async def test_enterprises_search_by_name(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """search=TestKorxona name bo'yicha topadi."""
    # default_enterprise nomi "Test Korxona"
    resp = await superadmin_client.get("/superadmin/enterprises?search=Test+Korxona")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    ids = [e["id"] for e in data["items"]]
    assert str(default_enterprise.id) in ids


@pytest.mark.asyncio
async def test_enterprises_search_no_match(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """search=XYZ_NOTEXIST → bo'sh ro'yxat."""
    resp = await superadmin_client.get("/superadmin/enterprises?search=XYZ_NOTEXIST_99999")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


# ─── 4. GET /superadmin/enterprises?search (INN) ─────────────────────────────


@pytest.mark.asyncio
async def test_enterprises_search_by_inn(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """search=123456789 INN bo'yicha topadi (default_enterprise.inn='123456789')."""
    resp = await superadmin_client.get("/superadmin/enterprises?search=123456789")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    ids = [e["id"] for e in data["items"]]
    assert str(default_enterprise.id) in ids


# ─── 5. GET /superadmin/enterprises?status ────────────────────────────────────


@pytest.mark.asyncio
async def test_enterprises_filter_by_status_active(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """status=active faqat aktiv korxonalarni qaytaradi."""
    # Suspended korxona yaratish
    await _make_enterprise(db_session, name="Susp For Filter", status="suspended")

    resp = await superadmin_client.get("/superadmin/enterprises?status=active")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert item["status"] == "active"


@pytest.mark.asyncio
async def test_enterprises_filter_by_status_suspended(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """status=suspended faqat suspended korxonalarni qaytaradi."""
    await _make_enterprise(db_session, name="Susp Test 2", status="suspended")

    resp = await superadmin_client.get("/superadmin/enterprises?status=suspended")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["status"] == "suspended"


# ─── 6. DELETE /superadmin/enterprises/{id} — soft-delete 204 ─────────────────


@pytest.mark.asyncio
async def test_delete_enterprise_soft_delete_204(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """DELETE → 204 va deleted_at o'rnatiladi."""
    ent = await _make_enterprise(db_session, name="Delete Me")

    resp = await superadmin_client.delete(f"/superadmin/enterprises/{ent.id}")
    assert resp.status_code == 204, resp.text

    # Keyin GET → 404 (deleted)
    get_resp = await superadmin_client.get(f"/superadmin/enterprises/{ent.id}")
    assert get_resp.status_code == 404


# ─── 7. DELETE o'chirilgan keyin 404 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_nonexistent_enterprise_404(
    superadmin_client: AsyncClient,
) -> None:
    """Mavjud bo'lmagan ID → 404."""
    resp = await superadmin_client.delete(f"/superadmin/enterprises/{uuid.uuid4()}")
    assert resp.status_code == 404, resp.text


# ─── 8. DELETE Default korxona → 422 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_default_enterprise_422(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Default korxona (00000000-0000-7000-8000-000000000001) o'chirib bo'lmaydi → 422."""
    # Default korxona DB da bo'lmasa ham himoya ishlaydi (UUID tekshiruvi service'da)
    # Lekin DB da bo'lsin
    from app.models.enterprise import ALL_MODULE_KEYS
    default_ent = Enterprise(
        id=uuid.UUID(DEFAULT_ENTERPRISE_UUID),
        name="Default Korxona",
        inn=None,
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(default_ent)
    await db_session.flush()

    resp = await superadmin_client.delete(
        f"/superadmin/enterprises/{DEFAULT_ENTERPRISE_UUID}"
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["message_key"] == "superadmin.cannot_delete_default"


# ─── 9. GET /superadmin/enterprises/{id} — detail ────────────────────────────


@pytest.mark.asyncio
async def test_enterprise_detail_user_count_and_admins(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
    db_session: AsyncSession,
) -> None:
    """Detail: user_count va admins to'g'ri qaytadi."""
    # Yana bir agent user qo'shish
    await _make_user(db_session, default_enterprise, role="agent")

    resp = await superadmin_client.get(f"/superadmin/enterprises/{default_enterprise.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "user_count" in data
    assert "admins" in data
    assert data["user_count"] >= 2  # admin_user + agent

    # admins faqat administrator rolni o'z ichiga olishi shart
    for admin in data["admins"]:
        assert admin["role"] == "administrator"

    # admin_user admins ichida bo'lishi shart
    admin_ids = [a["id"] for a in data["admins"]]
    assert str(admin_user.id) in admin_ids


@pytest.mark.asyncio
async def test_enterprise_detail_has_all_enterprise_fields(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
) -> None:
    """Detail: EnterpriseOut maydonlari (id, name, status, ...) mavjud."""
    resp = await superadmin_client.get(f"/superadmin/enterprises/{default_enterprise.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["id"] == str(default_enterprise.id)
    assert data["name"] == default_enterprise.name
    assert data["status"] == "active"
    assert "enabled_modules" in data
    assert "version" in data
    assert "created_at" in data


# ─── 10. Detail topilmasa 404 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enterprise_detail_not_found_404(
    superadmin_client: AsyncClient,
) -> None:
    """Mavjud bo'lmagan ID → 404."""
    resp = await superadmin_client.get(f"/superadmin/enterprises/{uuid.uuid4()}")
    assert resp.status_code == 404, resp.text


# ─── 11. reset-admin-password — explicit parol ────────────────────────────────


@pytest.mark.asyncio
async def test_reset_admin_password_explicit(
    superadmin_client: AsyncClient,
    no_auth_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
) -> None:
    """Explicit parol berilsa — o'sha parol ishlatiladi va login ishlaydi."""
    new_pwd = "NewStrongPass123!"

    resp = await superadmin_client.post(
        f"/superadmin/enterprises/{default_enterprise.id}/reset-admin-password",
        json={"user_id": str(admin_user.id), "new_password": new_pwd},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == str(admin_user.id)
    assert data["new_password"] == new_pwd

    # Yangi parol bilan login
    login_resp = await no_auth_client.post(
        "/auth/login",
        json={"phone": ADMIN_PHONE, "password": new_pwd},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert "access_token" in login_resp.json()


# ─── 12. reset-admin-password — null → generatsiya ──────────────────────────


@pytest.mark.asyncio
async def test_reset_admin_password_generates_when_null(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
) -> None:
    """new_password=null bo'lsa server 12+ belgilik parol generatsiya qiladi."""
    resp = await superadmin_client.post(
        f"/superadmin/enterprises/{default_enterprise.id}/reset-admin-password",
        json={"user_id": str(admin_user.id), "new_password": None},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == str(admin_user.id)
    assert isinstance(data["new_password"], str)
    assert len(data["new_password"]) >= 12


# ─── 13. reset-admin-password — boshqa korxona user → 404 ───────────────────


@pytest.mark.asyncio
async def test_reset_admin_password_wrong_enterprise_404(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """Boshqa korxona useri uchun → 404 (xavfsizlik tekshiruvi)."""
    other_ent = await _make_enterprise(db_session, name="Boshqa Korxona")
    other_user = await _make_user(db_session, other_ent, role="administrator")

    # default_enterprise uchun other_user paroli tiklash → 404
    resp = await superadmin_client.post(
        f"/superadmin/enterprises/{default_enterprise.id}/reset-admin-password",
        json={"user_id": str(other_user.id), "new_password": "AnyStrongPass123!"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["message_key"] == "superadmin.user_not_found"


# ─── 14. GET /superadmin/users — barcha users ────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_users_list_all(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
    db_session: AsyncSession,
) -> None:
    """GET /superadmin/users barcha tenant userlarni qaytaradi."""
    await _make_user(db_session, default_enterprise, role="agent")

    resp = await superadmin_client.get("/superadmin/users")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2  # admin_user + agent

    # Har birida enterprise_name bo'lishi shart
    for item in data["items"]:
        assert "enterprise_name" in item
        assert item["enterprise_id"] is not None


@pytest.mark.asyncio
async def test_superadmin_users_list_structure(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
) -> None:
    """Har element to'g'ri maydonlarga ega."""
    resp = await superadmin_client.get("/superadmin/users")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) >= 1

    item = items[0]
    assert "id" in item
    assert "full_name" in item
    assert "phone" in item
    assert "role" in item
    assert "is_active" in item
    assert "enterprise_id" in item
    assert "enterprise_name" in item
    assert "created_at" in item


# ─── 15. GET /superadmin/users?enterprise_id ─────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_users_filter_by_enterprise(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
    db_session: AsyncSession,
) -> None:
    """enterprise_id filtri faqat o'sha korxona userlarini qaytaradi."""
    other_ent = await _make_enterprise(db_session, name="Boshqa Ent Filter")
    await _make_user(db_session, other_ent, role="agent")

    resp = await superadmin_client.get(
        f"/superadmin/users?enterprise_id={default_enterprise.id}"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert item["enterprise_id"] == str(default_enterprise.id)


# ─── 16. GET /superadmin/users?role ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_users_filter_by_role(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    admin_user: AppUser,
    db_session: AsyncSession,
) -> None:
    """role filtri faqat o'sha roldagi foydalanuvchilarni qaytaradi."""
    await _make_user(db_session, default_enterprise, role="agent")

    resp = await superadmin_client.get("/superadmin/users?role=administrator")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["role"] == "administrator"


# ─── 17. stats → superadmin so'rov (auth tekshiruvi) ─────────────────────────


@pytest.mark.asyncio
async def test_stats_requires_superadmin(
    admin_client: AsyncClient,
) -> None:
    """administrator /superadmin/stats → 403."""
    resp = await admin_client.get("/superadmin/stats")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_stats_requires_auth(
    no_auth_client: AsyncClient,
) -> None:
    """Tokensiz /superadmin/stats → 401."""
    resp = await no_auth_client.get("/superadmin/stats")
    assert resp.status_code == 401, resp.text


# ─── 18. delete — superadmin auth tekshiruvi ─────────────────────────────────


@pytest.mark.asyncio
async def test_delete_enterprise_requires_superadmin(
    admin_client: AsyncClient,
    default_enterprise: Enterprise,
) -> None:
    """administrator DELETE → 403."""
    resp = await admin_client.delete(
        f"/superadmin/enterprises/{default_enterprise.id}"
    )
    assert resp.status_code == 403, resp.text
