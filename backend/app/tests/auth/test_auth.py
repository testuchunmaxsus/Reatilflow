"""
Auth endpointlari testlari.

Barcha testlar infrasiz ishlaydi: aiosqlite in-memory + fakeredis.

Scenariylar:
  - Login muvaffaqiyat → token juft qaytadi
  - Login noto'g'ri parol → 401
  - Login is_active=False → 403
  - /auth/me access token bilan ishlaydi → 200
  - Muddati o'tgan access token → 401
  - Buzuq token → 401
  - Refresh rotatsiya: eski refresh ikkinchi marta ishlamaydi (denylist)
  - Logout'dan keyin refresh ishlamaydi
  - Refresh token o'rniga access token bilan refresh → 401
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.user import AppUser
from app.tests.auth.conftest import TEST_PASSWORD, TEST_PHONE


# ─── Login testlari ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(auth_client: AsyncClient, test_user: AppUser) -> None:
    """Muvaffaqiyatli login — 200 va token juft qaytarishi kerak."""
    resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20
    assert len(data["refresh_token"]) > 20


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Noto'g'ri parol → 401."""
    resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_phone_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Mavjud bo'lmagan telefon → 401."""
    resp = await auth_client.post(
        "/auth/login",
        json={"phone": "+998900000000", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_403(
    auth_client: AsyncClient, inactive_user: AppUser
) -> None:
    """Bloklangan foydalanuvchi → 403."""
    resp = await auth_client.post(
        "/auth/login",
        json={"phone": inactive_user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 403


# ─── /auth/me testlari ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_with_valid_token(auth_client: AsyncClient, test_user: AppUser) -> None:
    """/auth/me — to'g'ri access token bilan 200 va foydalanuvchi ma'lumotlari."""
    # Avval login
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    # /auth/me
    me_resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    data = me_resp.json()
    assert data["phone"] == TEST_PHONE
    assert data["role"] == "administrator"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_without_token_returns_401(auth_client: AsyncClient) -> None:
    """/auth/me token'siz → 401."""
    resp = await auth_client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Muddati o'tgan access token → 401."""
    # Muddati allaqachon o'tgan token yaratish
    expired_payload = {
        "sub": str(test_user.id),
        "role": test_user.role,
        "branch_id": None,
        "type": "access",
        "jti": "test-jti-expired",
        "iat": datetime.now(UTC) - timedelta(hours=2),
        "exp": datetime.now(UTC) - timedelta(hours=1),  # o'tgan
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(auth_client: AsyncClient) -> None:
    """Buzuq token → 401."""
    resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer thisisnotavalidtoken"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_wrong_signature_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Noto'g'ri imzo bilan token → 401."""
    payload = {
        "sub": str(test_user.id),
        "role": test_user.role,
        "type": "access",
        "jti": "test-jti",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=15),
    }
    bad_token = jwt.encode(payload, "wrong-secret-key-that-is-at-least-32-bytes-long!!", algorithm="HS256")

    resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


# ─── Refresh rotatsiya testlari ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_success(auth_client: AsyncClient, test_user: AppUser) -> None:
    """Muvaffaqiyatli refresh → yangi token juft qaytadi."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200, refresh_resp.text
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Yangi refresh login dan farqli bo'lishi kerak (rotatsiya)
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_old_token_fails_after_rotation(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Eski refresh token rotatsiyadan keyin denylist da — ikkinchi marta ishlamaydi."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    old_refresh = login_resp.json()["refresh_token"]

    # Birinchi refresh — muvaffaqiyat
    first = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert first.status_code == 200

    # Eski token bilan ikkinchi refresh — 401 (denylist)
    second = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Access token bilan refresh → 401 (tur noto'g'ri)."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    resp = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": access_token},  # access token berildi — xato
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_expired_token_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Muddati o'tgan refresh token → 401."""
    expired_payload = {
        "sub": str(test_user.id),
        "type": "refresh",
        "jti": "test-jti-expired-refresh",
        "iat": datetime.now(UTC) - timedelta(days=31),
        "exp": datetime.now(UTC) - timedelta(days=1),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    resp = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": expired_token},
    )
    assert resp.status_code == 401


# ─── Logout testlari ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_success(auth_client: AsyncClient, test_user: AppUser) -> None:
    """Muvaffaqiyatli logout → 204."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await auth_client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 204


@pytest.mark.asyncio
async def test_refresh_after_logout_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Logout'dan keyin eski refresh token bilan refresh → 401."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Logout
    logout_resp = await auth_client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 204

    # Logout qilingan token bilan refresh → 401
    refresh_resp = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


# ─── Token claim testlari ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_access_token_contains_expected_claims(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Access token da sub, role, branch_id, type, jti claimlari bo'lishi kerak."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    # Decode (tekshirish bilan)
    payload = jwt.decode(
        access_token,
        settings.jwt_secret_key,
        algorithms=["HS256"],
    )
    assert payload["type"] == "access"
    assert payload["sub"] == str(test_user.id)
    assert payload["role"] == test_user.role
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload
    assert "branch_id" in payload


@pytest.mark.asyncio
async def test_refresh_token_contains_expected_claims(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Refresh token da sub, type, jti claimlari bo'lishi kerak (role yo'q)."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    refresh_token = login_resp.json()["refresh_token"]

    payload = jwt.decode(
        refresh_token,
        settings.jwt_secret_key,
        algorithms=["HS256"],
    )
    assert payload["type"] == "refresh"
    assert payload["sub"] == str(test_user.id)
    assert "jti" in payload
    # role refresh tokenida bo'lmasligi kerak
    assert "role" not in payload


# ─── Qo'shimcha scenariylar (T2 oldin yopilishi kerak) ───────────────────────

@pytest.mark.asyncio
async def test_refresh_inactive_user_returns_403(
    auth_client: AsyncClient, test_user: AppUser, db_session
) -> None:
    """Login qilingan user DB'da is_active=False qilinib refresh → 403."""
    # Avval login — user active holatida
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Userni bloklash
    test_user.is_active = False
    await db_session.flush()

    # Refresh — endi 403 bo'lishi kerak
    refresh_resp = await auth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 403


@pytest.mark.asyncio
async def test_login_empty_body_returns_422(auth_client: AsyncClient) -> None:
    """Bo'sh body → 422 (Pydantic validation xatosi)."""
    resp = await auth_client.post("/auth/login", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_body_returns_422(auth_client: AsyncClient) -> None:
    """Yaroqsiz body (telefon yo'q) → 422."""
    resp = await auth_client.post("/auth/login", json={"password": "only_password"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_with_refresh_token_returns_401(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """To'g'ri imzoli refresh token /auth/me ga yuborilsa → 401 (type=access talab qilinadi)."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh tokenni /auth/me ga yuborish — 401 bo'lishi kerak
    me_resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_access_token_returns_400(
    auth_client: AsyncClient, test_user: AppUser
) -> None:
    """Access token bilan logout → 400 (faqat refresh token qabul qilinadi)."""
    login_resp = await auth_client.post(
        "/auth/login",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    logout_resp = await auth_client.post(
        "/auth/logout",
        json={"refresh_token": access_token},  # access token berildi — xato
    )
    assert logout_resp.status_code == 400
