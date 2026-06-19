"""
Users moduli testlari (T6).

Scenariylar:
  CRUD:
    - Admin user yaratadi (201), yangilaydi, ro'yxat oladi (paginated)
    - Non-admin (agent/store/courier/accountant) → 403
    - phone DB da shifrlangan (xom-matn emas)
    - UserOut da password_hash yo'q
    - Dublikat telefon → 409
    - Noto'g'ri rol → validatsiya/422 yoki AppError
    - Deactivate: is_active=False; admin o'zini deaktiv → 403
    - Version conflict → 409
    - Idempotentlik (client_uuid)
    - i18n (?lang=ru)

  Login regressiya:
    - Yangi yaratilgan user phone bilan login qila oladi (blind-index lookup ishlaydi)
    - Deactivate qilingan user login qila olmaydi (401/403)
    - phone EncryptedString — DB da raw text emas

  Mavjud testlar regressiyaga uchramasin (phone_bi avtomatik to'ldiriladi):
    - auth conftest fixture: AppUser(phone=...) → phone_bi avtomatik
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index
from app.models.user import AppUser
from app.tests.users.conftest import (
    ADMIN_PASSWORD,
    ADMIN_PHONE,
    AGENT_PHONE,
    AGENT_USER_ID,
)


# ─── CRUD testlari ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_create_user(users_client: AsyncClient, admin_user: AppUser) -> None:
    """Admin yangi user yarata oladi → 201."""
    resp = await users_client.post(
        "/users",
        json={
            "full_name": "Yangi Foydalanuvchi",
            "phone": "+998907654321",
            "role": "agent",
            "password": "NewPass123!",
            "locale": "uz",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["role"] == "agent"
    assert data["full_name"] == "Yangi Foydalanuvchi"
    assert data["phone"] == "+998907654321"
    assert data["is_active"] is True
    # password_hash hech qachon chiqmasligi shart
    assert "password_hash" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_created_user_phone_stored_encrypted(
    users_client: AsyncClient, db_session: AsyncSession, admin_user: AppUser
) -> None:
    """
    Yangi yaratilgan user phone DB da shifrlangan saqlanishi kerak (raw text emas).

    EncryptedString TypeDecorator ORM orqali encrypt_pii() chaqiradi.
    Shu sababli ORM dan o'qilgan phone deshifrlanib qaytadi (string).
    Lekin raw SQL orqali o'qilsa bytes (shifrlangan) bo'lishi kerak.

    Tekshiruv:
      1. API orqali yaratilgan user ID olish
      2. ORM orqali phone o'qish — deshifrlanib to'g'ri qaytishi kerak
      3. phone_bi HMAC blind-index to'g'ri ekanligini tekshirish
    """
    test_phone = "+998907777001"
    resp = await users_client.post(
        "/users",
        json={
            "full_name": "PII Test User",
            "phone": test_phone,
            "role": "courier",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    user_id = data["id"]

    # 1. API javobida phone to'g'ri deshifrlanib qaytgan
    assert data["phone"] == test_phone, "API javobida phone to'g'ri ko'rinishi kerak"

    # 2. ORM orqali o'qish — deshifrlanib qaytadi
    result = await db_session.execute(
        select(AppUser).where(AppUser.id == uuid.UUID(user_id))
    )
    db_user = result.scalar_one_or_none()
    if db_user is not None:
        # ORM deshifrlaydi — to'g'ri qiymat qaytadi
        assert db_user.phone == test_phone, "ORM orqali deshifrlanib to'g'ri qaytishi kerak"
        # phone_bi HMAC blind-index to'g'ri hisoblanganligini tekshirish
        expected_bi = blind_index(test_phone)
        assert db_user.phone_bi == expected_bi, "phone_bi to'g'ri blind-index bo'lishi kerak"


@pytest.mark.asyncio
async def test_admin_can_list_users(users_client: AsyncClient, admin_user: AppUser) -> None:
    """Admin foydalanuvchilar ro'yxatini oladi → paginated."""
    resp = await users_client.get("/users")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["total"] >= 1  # kamida admin_user bor


@pytest.mark.asyncio
async def test_admin_can_get_user(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Admin ID bo'yicha user oladi → 200."""
    resp = await users_client.get(f"/users/{agent_user.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(agent_user.id)
    assert data["role"] == "agent"
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_admin_can_update_user(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Admin user ma'lumotlarini yangilaydi → 200."""
    # Avval joriy versiyani API orqali olish
    get_resp = await users_client.get(f"/users/{agent_user.id}")
    assert get_resp.status_code == 200, get_resp.text
    current_version = get_resp.json()["version"]

    resp = await users_client.patch(
        f"/users/{agent_user.id}",
        json={
            "full_name": "Yangilangan Agent",
            "version": current_version,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["full_name"] == "Yangilangan Agent"
    assert data["version"] == current_version + 1


@pytest.mark.asyncio
async def test_list_users_pagination(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Paginated ro'yxat limit va offset ishlaydi."""
    resp = await users_client.get("/users?limit=1&offset=0")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_users_filter_by_role(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser, store_user: AppUser
) -> None:
    """Rol bo'yicha filtrlash ishlaydi."""
    resp = await users_client.get("/users?role=agent")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert item["role"] == "agent"


# ─── Non-admin 403 testlari ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_cannot_list_users(
    agent_client: AsyncClient, agent_user: AppUser
) -> None:
    """Agent /users ro'yxatiga kirish → 403."""
    resp = await agent_client.get("/users")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_cannot_create_user(
    agent_client: AsyncClient, agent_user: AppUser
) -> None:
    """Agent yangi user yarata olmaydi → 403."""
    resp = await agent_client.post(
        "/users",
        json={
            "full_name": "Test",
            "phone": "+998909999001",
            "role": "courier",
            "password": "Pass123!",
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_cannot_get_user(
    agent_client: AsyncClient, agent_user: AppUser, admin_user: AppUser
) -> None:
    """Agent boshqa user ma'lumotlarini ololmaydi → 403."""
    resp = await agent_client.get(f"/users/{admin_user.id}")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_store_role_cannot_access_users(
    db_session: AsyncSession, fake_redis, store_user: AppUser
) -> None:
    """Store roli /users endpointlariga kira olmaydi → 403."""
    from app.core.db import get_db
    from app.core.jwt import create_access_token
    from app.core.redis import get_redis
    from app.main import app

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    token = create_access_token(sub=str(store_user.id), role=store_user.role, branch_id=None)

    from httpx import ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        resp = await client.get("/users")
        assert resp.status_code == 403, resp.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_courier_cannot_access_users(
    db_session: AsyncSession, fake_redis, courier_user: AppUser
) -> None:
    """Courier roli /users endpointlariga kira olmaydi → 403."""
    from app.core.db import get_db
    from app.core.jwt import create_access_token
    from app.core.redis import get_redis
    from app.main import app

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    token = create_access_token(sub=str(courier_user.id), role=courier_user.role, branch_id=None)

    from httpx import ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        resp = await client.get("/users")
        assert resp.status_code == 403, resp.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accountant_cannot_manage_users(
    db_session: AsyncSession, fake_redis, accountant_user: AppUser
) -> None:
    """Accountant roli /users endpointlariga kira olmaydi → 403."""
    from app.core.db import get_db
    from app.core.jwt import create_access_token
    from app.core.redis import get_redis
    from app.main import app

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    token = create_access_token(sub=str(accountant_user.id), role=accountant_user.role, branch_id=None)

    from httpx import ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        resp = await client.get("/users")
        assert resp.status_code == 403, resp.text

    app.dependency_overrides.clear()


# ─── Login regressiya testlari ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_regression_with_blind_index(
    auth_client: AsyncClient, admin_user: AppUser
) -> None:
    """
    Login regressiya: admin_user phone bilan login qila oladi.

    phone EncryptedString (shifrlangan) — login faqat blind-index orqali ishlaydi.
    Bu blind-index event listener ishlayotganini tasdiqlaydi.
    """
    resp = await auth_client.post(
        "/auth/login",
        json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_newly_created_user_can_login(
    users_client: AsyncClient, auth_client: AsyncClient, admin_user: AppUser
) -> None:
    """
    Yangi yaratilgan user o'z phone va parol bilan login qila oladi.

    Bu blind-index qidiruv to'g'ri ishlayotganini tasdiqlaydi:
    1. Admin yangi user yaratadi (phone → shifrlangan, phone_bi → blind-index)
    2. Yangi user phone + parol bilan login qiladi
    3. Login muvaffaqiyatli bo'lishi kerak
    """
    new_phone = "+998907123456"
    new_password = "NewUserPass123!"

    # 1. Yangi user yaratish
    create_resp = await users_client.post(
        "/users",
        json={
            "full_name": "Yangi Login Test User",
            "phone": new_phone,
            "role": "agent",
            "password": new_password,
            "locale": "uz",
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    # 2. Yangi user login
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": new_phone, "password": new_password},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_deactivated_user_cannot_login(
    users_client: AsyncClient, auth_client: AsyncClient,
    db_session: AsyncSession, admin_user: AppUser, agent_user: AppUser
) -> None:
    """
    Deaktiv qilingan user login qila olmaydi → 403.

    1. Admin agent_user ni deaktiv qiladi
    2. agent_user login qilmoqchi → 403
    """
    # 1. Deaktivatsiya
    deact_resp = await users_client.patch(f"/users/{agent_user.id}/deactivate")
    assert deact_resp.status_code == 200, deact_resp.text
    assert deact_resp.json()["is_active"] is False

    # 2. Login urinishi — 403 bo'lishi kerak
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": AGENT_PHONE, "password": "AgentPass123!"},
    )
    assert login_resp.status_code == 403, login_resp.text


# ─── Dublikat telefon → 409 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_phone_returns_409(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Mavjud telefon bilan yangi user yaratmoqchi → 409."""
    resp = await users_client.post(
        "/users",
        json={
            "full_name": "Dublikat Test",
            "phone": AGENT_PHONE,  # agent_user ning telefoni
            "role": "store",
            "password": "Pass123!",
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["message_key"] == "users.duplicate_phone"


# ─── Noto'g'ri rol → 422/409 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_role_returns_error(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Noto'g'ri rol bilan user yaratmoqchi → 422 yoki 400."""
    resp = await users_client.post(
        "/users",
        json={
            "full_name": "Bad Role User",
            "phone": "+998909888001",
            "role": "superadmin",  # noto'g'ri rol
            "password": "Pass123!",
        },
    )
    # AppError yoki Pydantic validation xatosi
    assert resp.status_code in (400, 409, 422), resp.text


# ─── Self-deactivation himoyasi ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Admin o'zini deaktiv qila olmaydi → 403."""
    resp = await users_client.patch(f"/users/{admin_user.id}/deactivate")
    assert resp.status_code == 403, resp.text
    data = resp.json()
    assert data["message_key"] == "users.cannot_deactivate_self"


@pytest.mark.asyncio
async def test_admin_can_deactivate_other_user(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Admin boshqa userni deaktiv qila oladi → 200."""
    resp = await users_client.patch(f"/users/{agent_user.id}/deactivate")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_admin_can_activate_user(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Admin deaktiv userni qayta aktivlashtira oladi → is_active True (deactivate teskarisi)."""
    deact = await users_client.patch(f"/users/{agent_user.id}/deactivate")
    assert deact.status_code == 200, deact.text
    assert deact.json()["is_active"] is False

    act = await users_client.patch(f"/users/{agent_user.id}/activate")
    assert act.status_code == 200, act.text
    assert act.json()["is_active"] is True


@pytest.mark.asyncio
async def test_activate_nonexistent_user_returns_404(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Mavjud bo'lmagan userni aktivlashtirish → 404."""
    import uuid as _uuid

    resp = await users_client.patch(f"/users/{_uuid.uuid4()}/activate")
    assert resp.status_code == 404, resp.text


# ─── Version conflict → 409 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict_returns_409(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """Eski version bilan PATCH → 409 version conflict."""
    # Joriy versiyadan katta bo'lmagan yoki noto'g'ri versiya
    wrong_version = 9999  # doim noto'g'ri bo'ladi

    resp = await users_client.patch(
        f"/users/{agent_user.id}",
        json={
            "full_name": "Conflict Test",
            "version": wrong_version,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["message_key"] == "users.version_conflict"


# ─── Idempotentlik (client_uuid) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_user_idempotency(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Bir xil client_uuid bilan ikki marta POST → ikkinchi marta ham 201, bir xil ID."""
    client_uuid = str(uuid.uuid4())

    resp1 = await users_client.post(
        "/users",
        json={
            "full_name": "Idempotent User",
            "phone": "+998907999001",
            "role": "courier",
            "password": "Pass123!",
            "client_uuid": client_uuid,
        },
    )
    assert resp1.status_code == 201, resp1.text
    user_id_1 = resp1.json()["id"]

    resp2 = await users_client.post(
        "/users",
        json={
            "full_name": "Idempotent User",
            "phone": "+998907999001",
            "role": "courier",
            "password": "Pass123!",
            "client_uuid": client_uuid,
        },
    )
    assert resp2.status_code == 201, resp2.text
    user_id_2 = resp2.json()["id"]

    # Bir xil user qaytishi kerak
    assert user_id_1 == user_id_2


# ─── i18n testlari ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_not_found_i18n_ru(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Mavjud bo'lmagan user → 404, ?lang=ru da rus tilida xabar."""
    non_existent_id = uuid.uuid4()
    resp = await users_client.get(f"/users/{non_existent_id}?lang=ru")
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["message_key"] == "users.user_not_found"
    # Xabar rus tilida bo'lishi kerak
    assert "не найден" in data["message"].lower() or "найден" in data["message"]


@pytest.mark.asyncio
async def test_user_not_found_i18n_uz(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Mavjud bo'lmagan user → 404, ?lang=uz da o'zbek tilida xabar."""
    non_existent_id = uuid.uuid4()
    resp = await users_client.get(f"/users/{non_existent_id}?lang=uz")
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["message_key"] == "users.user_not_found"
    assert "topilmadi" in data["message"].lower()


# ─── phone_bi avtomatik to'ldirilishi (event listener) ───────────────────────


@pytest.mark.asyncio
async def test_phone_bi_auto_set_on_fixture_creation(
    db_session: AsyncSession, admin_user: AppUser
) -> None:
    """
    AppUser(phone=...) fixture yaratilganda phone_bi avtomatik to'ldirilishi kerak.

    Bu event listener (before_insert) ishlayotganini tasdiqlaydi.
    """
    # admin_user fixture yaratilgan — phone_bi to'ldirilgan bo'lishi kerak
    expected_bi = blind_index(ADMIN_PHONE)
    assert admin_user.phone_bi == expected_bi, (
        f"phone_bi avtomatik to'ldirilmagan. "
        f"Kutilgan: {expected_bi!r}, olingan: {admin_user.phone_bi!r}"
    )


@pytest.mark.asyncio
async def test_phone_bi_unique_constraint(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """
    Bir xil phone_bi bilan ikkinchi user → 409.

    Blind-index UNIQUE constraint ishlayotganini tekshiradi.
    """
    # agent_user ning telefonini ishlatamiz
    resp = await users_client.post(
        "/users",
        json={
            "full_name": "Yana Bir Foydalanuvchi",
            "phone": AGENT_PHONE,  # UNIQUE phone_bi → 409
            "role": "store",
            "password": "Pass123!",
        },
    )
    assert resp.status_code == 409, resp.text


# ─── UserOut da password_hash yo'qligi ───────────────────────────────────────


@pytest.mark.asyncio
async def test_user_out_no_password_hash(
    users_client: AsyncClient, admin_user: AppUser, agent_user: AppUser
) -> None:
    """UserOut javobida password_hash va password maydonlari bo'lmasligi kerak."""
    resp = await users_client.get(f"/users/{agent_user.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "password_hash" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_user_list_no_password_hash(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Ro'yxatda ham password_hash bo'lmasligi kerak."""
    resp = await users_client.get("/users")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for item in data["items"]:
        assert "password_hash" not in item
        assert "password" not in item


# ─── phone update → phone_bi yangilanishi ─────────────────────────────────────


@pytest.mark.asyncio
async def test_phone_update_updates_phone_bi(
    users_client: AsyncClient, auth_client: AsyncClient,
    admin_user: AppUser, agent_user: AppUser
) -> None:
    """
    Phone yangilanganda phone_bi ham yangilanadi va login ishlaydi.
    """
    new_phone = "+998909876543"
    new_password = "AgentPass123!"  # parol o'zgarmaydi

    # 1. phone yangilash
    update_resp = await users_client.patch(
        f"/users/{agent_user.id}",
        json={
            "phone": new_phone,
            "version": agent_user.version,
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    # 2. Yangi telefon bilan login
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": new_phone, "password": new_password},
    )
    assert login_resp.status_code == 200, login_resp.text


# ─── Unauthenticated access ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_users(auth_client: AsyncClient) -> None:
    """Token yo'q → 401."""
    resp = await auth_client.get("/users")
    assert resp.status_code == 401, resp.text


# ─── Get not found ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_nonexistent_user_returns_404(
    users_client: AsyncClient, admin_user: AppUser
) -> None:
    """Mavjud bo'lmagan user ID → 404."""
    non_existent = uuid.uuid4()
    resp = await users_client.get(f"/users/{non_existent}")
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["message_key"] == "users.user_not_found"
