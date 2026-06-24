"""
S2 xavfsizlik testlari — bosqich 2.

(a) Audit masking: mask_pii sensitiv maydonlarni redact qiladi.
    Qo'shimcha kalit: api_key.
    Audit yozuvida password_hash, api_key, secret va boshqalar "***" bo'lishi kerak.

(b) Push RBAC:
    - Module enum da PUSH qiymati mavjud.
    - Barcha autentifikatsiyalangan rollar push:create ruxsatiga ega.
    - Administrator push:view ruxsatiga ham ega.
    - require_permission(Module.PUSH, Action.CREATE) himoyasi ishlaydi:
        * Token bilan → 200.
        * Tokensiz → 401.
    - Ruxsat yo'q rol yoki noto'g'ri token → 403/401.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.core.security import mask_pii
from app.main import app
from app.models.base import Base
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.modules.rbac.permissions import Action, Module, ROLE_PERMISSIONS
from app.tests.conftest import TEST_ENTERPRISE_UUID

TEST_PASSWORD = "TestPassword123!"

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def engine():
    """Har test uchun aiosqlite in-memory engine."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
async def default_enterprise(db_session: AsyncSession) -> Enterprise:
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Test Korxona",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
def make_user(db_session: AsyncSession, default_enterprise: Enterprise):
    async def _factory(
        role: str = "agent",
        phone: str | None = None,
        is_active: bool = True,
    ) -> AppUser:
        uid = uuid.uuid4()
        user = AppUser(
            id=uid,
            full_name=f"Test {role.capitalize()}",
            phone=phone or f"+99890{str(abs(hash(str(uid))))[:7]}",
            role=role,
            branch_id=None,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=is_active,
            biometric_enrolled=False,
            locale="uz",
            device_id=None,
            version=1,
            enterprise_id=default_enterprise.id,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _factory


@pytest.fixture
async def s2_client(db_session: AsyncSession, fake_redis):
    """Dependency override qilingan AsyncClient."""

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


async def _login(client: AsyncClient, user: AppUser) -> str:
    resp = await client.post(
        "/auth/login",
        json={"phone": user.phone, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login muvaffaqiyatsiz: {resp.text}"
    return resp.json()["access_token"]


# ─── (a) Audit masking testlari ──────────────────────────────────────────────


class TestAuditMaskPii:
    """mask_pii sensitiv maydonlarni redact qilishi kerak."""

    def test_masks_password_hash(self):
        """password_hash → *** maskalanadi."""
        result = mask_pii({"password_hash": "$2b$12$abc..."})
        assert result["password_hash"] == "***"

    def test_masks_password(self):
        """password → *** maskalanadi."""
        result = mask_pii({"password": "secret123"})
        assert result["password"] == "***"

    def test_masks_api_key(self):
        """api_key → *** maskalanadi (S2 qo'shimchasi)."""
        result = mask_pii({"api_key": "sk-live-abc123xyz"})
        assert result["api_key"] == "***"

    def test_masks_api_key_uppercase(self):
        """API_KEY (uppercase) → *** maskalanadi (case-insensitive)."""
        result = mask_pii({"API_KEY": "sk-test-999"})
        assert result["API_KEY"] == "***"

    def test_masks_token(self):
        """token → *** maskalanadi."""
        result = mask_pii({"token": "eyJhbGc.payload.sig"})
        assert result["token"] == "***"

    def test_masks_access_token(self):
        """access_token → *** maskalanadi."""
        result = mask_pii({"access_token": "eyJhbGc.payload.sig"})
        assert result["access_token"] == "***"

    def test_masks_refresh_token(self):
        """refresh_token → *** maskalanadi."""
        result = mask_pii({"refresh_token": "eyJhbGc.payload.sig"})
        assert result["refresh_token"] == "***"

    def test_masks_secret(self):
        """secret → *** maskalanadi."""
        result = mask_pii({"secret": "my_secret_value"})
        assert result["secret"] == "***"

    def test_keeps_safe_fields(self):
        """Xavfsiz maydonlar o'zgartirilmaydi."""
        data = {"id": "abc", "role": "agent", "status": "active"}
        result = mask_pii(data)
        assert result == data

    def test_audit_json_no_password_hash(self):
        """
        Audit yozuvida password_hash ko'rinmaydi.

        Audit oldin/keyin JSON ni mask_pii dan o'tkazganida
        password_hash "***" bo'lishi kerak.
        """
        before = {
            "id": "user-uuid-123",
            "password_hash": "$2b$12$Wf0AWCIf8MpSBNYxzLX/Lu...",
            "role": "agent",
        }
        after = {
            "id": "user-uuid-123",
            "password_hash": "$2b$12$Wf0AWCIf8MpSBNYxzLX/Lu...",
            "role": "administrator",
        }
        before_masked = json.dumps(mask_pii(before))
        after_masked = json.dumps(mask_pii(after))

        # password_hash ochiq-matn ko'rinmasin
        assert "$2b$12$" not in before_masked
        assert "$2b$12$" not in after_masked
        # "***" bor
        assert "***" in before_masked
        assert "***" in after_masked

    def test_audit_json_no_api_key(self):
        """Audit JSON da api_key ko'rinmaydi."""
        payload = {"api_key": "live_key_abc123", "name": "Integration"}
        masked = json.dumps(mask_pii(payload))
        assert "live_key_abc123" not in masked
        assert "***" in masked

    def test_does_not_mutate_original(self):
        """Asl lug'at o'zgartirilmaydi."""
        original = {"password_hash": "$2b$12$abc", "api_key": "key"}
        mask_pii(original)
        assert original["password_hash"] == "$2b$12$abc"
        assert original["api_key"] == "key"

    def test_all_required_sensitive_keys_masked(self):
        """
        Vazifa talabi bo'yicha barcha sensitiv kalit nomlar maskalanadi:
        password_hash, password, token, api_key, secret, refresh_token.
        """
        required_keys = [
            "password_hash",
            "password",
            "token",
            "api_key",
            "secret",
            "refresh_token",
        ]
        for key in required_keys:
            result = mask_pii({key: "some_value"})
            assert result[key] == "***", f"{key!r} maskalanmadi"


# ─── (b) Push RBAC — matritsa testlari ──────────────────────────────────────


class TestPushRbacMatrix:
    """ROLE_PERMISSIONS matritsa testlari — infrasiz."""

    def test_push_module_exists_in_enum(self):
        """Module.PUSH qiymati mavjud."""
        assert Module.PUSH == "push"
        assert hasattr(Module, "PUSH")

    def test_administrator_has_push_view(self):
        """administrator → push:view ruxsati bor."""
        assert "push:view" in ROLE_PERMISSIONS["administrator"]

    def test_administrator_has_push_create(self):
        """administrator → push:create ruxsati bor."""
        assert "push:create" in ROLE_PERMISSIONS["administrator"]

    def test_agent_has_push_create(self):
        """agent → push:create ruxsati bor."""
        assert "push:create" in ROLE_PERMISSIONS["agent"]

    def test_courier_has_push_create(self):
        """courier → push:create ruxsati bor."""
        assert "push:create" in ROLE_PERMISSIONS["courier"]

    def test_accountant_has_push_create(self):
        """accountant → push:create ruxsati bor."""
        assert "push:create" in ROLE_PERMISSIONS["accountant"]

    def test_store_has_push_create(self):
        """store → push:create ruxsati bor."""
        assert "push:create" in ROLE_PERMISSIONS["store"]

    def test_all_tenant_roles_have_push_create(self):
        """Barcha tenant rollari push:create ruxsatiga ega."""
        tenant_roles = ["administrator", "agent", "courier", "accountant", "store"]
        for role in tenant_roles:
            assert "push:create" in ROLE_PERMISSIONS[role], (
                f"{role} push:create ruxsatiga ega bo'lishi kerak"
            )


# ─── (b) Push RBAC — HTTP endpoint testlari ─────────────────────────────────


@pytest.mark.anyio
async def test_device_token_requires_auth_s2(s2_client):
    """Token yo'q → 401."""
    resp = await s2_client.patch(
        "/push/device-token",
        json={"device_id": "fcm_token_xyz", "channel": "fcm"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_device_token_agent_push_create(
    s2_client, make_user, db_session
):
    """agent push:create ruxsati bor → 200."""
    user = await make_user(role="agent")
    await db_session.commit()

    token = await _login(s2_client, user)
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "agent_device_token", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"agent 200 kutildi: {resp.text}"
    data = resp.json()
    assert data["device_id"] == "agent_device_token"
    assert data["user_id"] == str(user.id)


@pytest.mark.anyio
async def test_device_token_courier_push_create(
    s2_client, make_user, db_session
):
    """courier push:create ruxsati bor → 200."""
    user = await make_user(role="courier")
    await db_session.commit()

    token = await _login(s2_client, user)
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "courier_device_token", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"courier 200 kutildi: {resp.text}"


@pytest.mark.anyio
async def test_device_token_store_push_create(
    s2_client, make_user, db_session
):
    """store push:create ruxsati bor → 200."""
    user = await make_user(role="store")
    await db_session.commit()

    token = await _login(s2_client, user)
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "store_device_token", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"store 200 kutildi: {resp.text}"


@pytest.mark.anyio
async def test_device_token_administrator_push_create(
    s2_client, make_user, db_session
):
    """administrator push:create ruxsati bor → 200."""
    user = await make_user(role="administrator")
    await db_session.commit()

    token = await _login(s2_client, user)
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "admin_device_token", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"administrator 200 kutildi: {resp.text}"


@pytest.mark.anyio
async def test_device_token_accountant_push_create(
    s2_client, make_user, db_session
):
    """accountant push:create ruxsati bor → 200."""
    user = await make_user(role="accountant")
    await db_session.commit()

    token = await _login(s2_client, user)
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "accountant_device_token", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"accountant 200 kutildi: {resp.text}"


@pytest.mark.anyio
async def test_device_token_invalid_token_401(s2_client):
    """Noto'g'ri token → 401."""
    resp = await s2_client.patch(
        "/push/device-token",
        headers={"Authorization": "Bearer invalid.token.here"},
        json={"device_id": "some_token", "channel": "fcm"},
    )
    assert resp.status_code == 401
