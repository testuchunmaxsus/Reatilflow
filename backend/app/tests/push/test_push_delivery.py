"""
HTTP orqali push yetkazish testlari — T19 Push Delivery.

Bu testlar haqiqiy FCM/APNs serveri CHAQIRMAYDI.
httpx.AsyncClient.send yoki transport mock orqali HTTP javoblar simulatsiya qilinadi.

Holatlar:
  (a) FCM v1 muvaffaqiyat    → push_log status=sent
  (b) FCM v1 404 UNREGISTERED → token invalidatsiya (device_id=None, status=failed)
  (c) FCM legacy muvaffaqiyat → push_log status=sent
  (d) FCM legacy NotRegistered → token invalidatsiya
  (e) APNs muvaffaqiyat       → push_log status=sent
  (f) APNs 410                → token invalidatsiya
  (g) APNs BadDeviceToken     → token invalidatsiya
  (h) Config yo'q → no-op (PushResult ok=False), istisno yo'q
  (i) Platform routing: "apns:<token>" → ApnsProvider
  (j) APNs JWT kesh: ikkinchi send JWT qayta yaratmaydi (muddati o'tmagan)
  (k) FCM tarmoq xatosi → PushResult(ok=False), retry uchun failed
  (l) service.py end-to-end: FcmProvider mock → push_log sent/failed/invalidated
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push import PushLog
from app.models.user import AppUser
from app.modules.push.provider import (
    ApnsProvider,
    FakePushProvider,
    FcmProvider,
    PushResult,
    get_apns_provider,
    get_push_provider,
)
from app.modules.push.service import process_pending_pushes
from app.tests.push.conftest import TEST_PASSWORD


# ─── Yordamchi: httpx mock transport ─────────────────────────────────────────


def _mock_response(status_code: int, body: dict | str = "") -> httpx.Response:
    """Oddiy httpx.Response mock yaratadi."""
    if isinstance(body, dict):
        content = json.dumps(body).encode()
        headers = {"content-type": "application/json"}
    else:
        content = body.encode() if body else b""
        headers = {}
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers,
    )


class _MockTransport(httpx.AsyncBaseTransport):
    """httpx AsyncBaseTransport mock — haqiqiy tarmoqni bloklaydi."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Request ni saqlash (tekshirish uchun)
        self.last_request = request
        return self._response


# ─── (a) FCM v1 muvaffaqiyat ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_fcm_v1_success():
    """
    FcmProvider v1: 200 javob → PushResult(ok=True).
    OAuth2 token olish ham mock qilinadi.
    """
    ok_resp = _mock_response(200, {"name": "projects/test/messages/123"})
    token_resp = _mock_response(200, {"access_token": "fake_bearer_token", "token_type": "Bearer"})

    call_count = 0

    class _MultiMockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # Birinchi chaqiruv: OAuth2 token endpoint
            if "oauth2" in str(request.url) or "googleapis.com/token" in str(request.url):
                return token_resp
            # Ikkinchi: FCM v1 endpoint
            return ok_resp

    provider = FcmProvider(
        project_id="test-project",
        credentials_json=json.dumps({
            "private_key": _FAKE_RSA_KEY,
            "client_email": "test@test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    # _get_oauth2_token patch — google-auth/tarmoq chaqiruvini chetlash
    # (google-auth httpx emas, requests ishlatadi → httpx mock uni ushlamaydi).
    with patch.object(
        FcmProvider, "_get_oauth2_token", new=AsyncMock(return_value="fake_bearer_token")
    ), patch("httpx.AsyncClient", side_effect=_make_client_factory(_MultiMockTransport())):
        result = await provider.send(
            device_token="test_fcm_token_abc",
            title="Test sarlavha",
            body="Test matn",
        )

    assert result.ok is True
    assert result.invalid_token is False
    assert result.error is None


# ─── (b) FCM v1 404 UNREGISTERED → token invalidatsiya ──────────────────────


@pytest.mark.anyio
async def test_fcm_v1_404_unregistered_invalidates_token():
    """
    FcmProvider v1: 404 UNREGISTERED → PushResult(ok=False, invalid_token=True).
    """
    unregistered_body = {
        "error": {
            "code": 404,
            "message": "Requested entity was not found.",
            "status": "NOT_FOUND",
            "details": [
                {
                    "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                    "errorCode": "UNREGISTERED",
                }
            ],
        }
    }
    error_resp = _mock_response(404, unregistered_body)

    provider = FcmProvider(
        project_id="test-project",
        credentials_json=json.dumps({
            "private_key": _FAKE_RSA_KEY,
            "client_email": "test@test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    token_resp = _mock_response(200, {"access_token": "fake_bearer", "token_type": "Bearer"})

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "oauth2" in str(request.url) or "googleapis.com/token" in str(request.url):
                return token_resp
            return error_resp

    with patch.object(
        FcmProvider, "_get_oauth2_token", new=AsyncMock(return_value="fake_bearer")
    ), patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="old_unregistered_token",
            title="Test",
            body="Test matn",
        )

    assert result.ok is False
    assert result.invalid_token is True
    assert "unregistered" in (result.error or "").lower()


# ─── (c) FCM legacy muvaffaqiyat ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_fcm_legacy_success():
    """
    FcmProvider legacy: FCM_SERVER_KEY bilan 200 + success → PushResult(ok=True).

    ESLATMA: FCM legacy API eskirgan — bu test backward-compat uchun.
    """
    legacy_resp = _mock_response(200, {
        "multicast_id": 12345,
        "success": 1,
        "failure": 0,
        "results": [{"message_id": "0:test_msg"}],
    })

    provider = FcmProvider(server_key="test-legacy-server-key")

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return legacy_resp

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="legacy_device_token",
            title="Sarlavha",
            body="Matn",
        )

    assert result.ok is True
    assert result.invalid_token is False


# ─── (d) FCM legacy NotRegistered → token invalidatsiya ─────────────────────


@pytest.mark.anyio
async def test_fcm_legacy_not_registered_invalidates_token():
    """
    FcmProvider legacy: NotRegistered xatosi → PushResult(ok=False, invalid_token=True).
    """
    legacy_error_resp = _mock_response(200, {
        "multicast_id": 99999,
        "success": 0,
        "failure": 1,
        "results": [{"error": "NotRegistered"}],
    })

    provider = FcmProvider(server_key="test-legacy-server-key")

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return legacy_error_resp

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="old_legacy_token",
            title="Test",
            body="Test",
        )

    assert result.ok is False
    assert result.invalid_token is True


# ─── (e) APNs muvaffaqiyat ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_apns_success():
    """
    ApnsProvider: 200 javob → PushResult(ok=True).
    JWT yaratish mock qilinadi.
    """
    ok_resp = _mock_response(200, "")

    provider = ApnsProvider(
        key_id="TEST_KEY_ID",
        team_id="TEST_TEAM_ID",
        bundle_id="com.example.retail",
        private_key_pem=_FAKE_EC_KEY,
        use_sandbox=True,
    )

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return ok_resp

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="apns_device_token_xyz",
            title="APNs sarlavha",
            body="APNs matn",
        )

    assert result.ok is True
    assert result.invalid_token is False


# ─── (f) APNs 410 → token invalidatsiya ──────────────────────────────────────


@pytest.mark.anyio
async def test_apns_410_invalidates_token():
    """
    ApnsProvider: 410 Gone → PushResult(ok=False, invalid_token=True).
    """
    gone_resp = _mock_response(410, {"reason": "Unregistered", "timestamp": 1234567890})

    provider = ApnsProvider(
        key_id="TEST_KEY_ID",
        team_id="TEST_TEAM_ID",
        bundle_id="com.example.retail",
        private_key_pem=_FAKE_EC_KEY,
        use_sandbox=True,
    )

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return gone_resp

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="old_apns_token",
            title="Test",
            body="Test",
        )

    assert result.ok is False
    assert result.invalid_token is True
    assert "apns_gone_410" in (result.error or "")


# ─── (g) APNs BadDeviceToken → token invalidatsiya ───────────────────────────


@pytest.mark.anyio
async def test_apns_bad_device_token_invalidates():
    """
    ApnsProvider: 400 BadDeviceToken → PushResult(ok=False, invalid_token=True).
    """
    bad_resp = _mock_response(400, {"reason": "BadDeviceToken"})

    provider = ApnsProvider(
        key_id="TEST_KEY_ID",
        team_id="TEST_TEAM_ID",
        bundle_id="com.example.retail",
        private_key_pem=_FAKE_EC_KEY,
        use_sandbox=True,
    )

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return bad_resp

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        result = await provider.send(
            device_token="bad_apns_token",
            title="Test",
            body="Test",
        )

    assert result.ok is False
    assert result.invalid_token is True
    assert "BadDeviceToken" in (result.error or "")


# ─── (h) Config yo'q → no-op, istisno yo'q ───────────────────────────────────


@pytest.mark.anyio
async def test_fcm_no_config_noop():
    """
    FcmProvider: hech qanday kredensial yo'q → no-op (ok=False), istisno tashlamaydi.
    """
    provider = FcmProvider()  # hech qanday arg yo'q
    result = await provider.send(
        device_token="some_token",
        title="Test",
        body="Test",
    )
    assert result.ok is False
    assert result.error == "fcm_not_configured"
    assert result.invalid_token is False


@pytest.mark.anyio
async def test_apns_no_config_noop():
    """
    ApnsProvider: hech qanday kredensial yo'q → no-op (ok=False), istisno tashlamaydi.
    """
    provider = ApnsProvider()  # hech qanday arg yo'q
    result = await provider.send(
        device_token="some_apns_token",
        title="Test",
        body="Test",
    )
    assert result.ok is False
    assert result.error == "apns_not_configured"
    assert result.invalid_token is False


# ─── (i) Platform routing: "apns:<token>" → ApnsProvider ─────────────────────


@pytest.mark.anyio
async def test_service_routes_apns_prefix_to_apns_provider(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    device_id = "apns:<token>" → service.py ApnsProvider chaqiradi (no-op bo'lsa ham).
    FCM FakePushProvider dan o'tmaydi — kanal apns.
    """
    # APNs prefixli device_id
    store_owner = await make_user(role="store", device_id="apns:device_token_ios_xyz")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    # ApnsProvider no-op (config yo'q) → failed, lekin fake_provider.sent bo'sh
    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # fake_provider (FCM) ga yuborilmagan — APNs yo'li tanlanadi
    fcm_tokens = [p.device_id for p in fake_provider.sent]
    assert "apns:device_token_ios_xyz" not in fcm_tokens

    # push_log yozilgan (failed — apns no-op)
    logs = (await db_session.execute(select(PushLog))).scalars().all()
    apns_logs = [l for l in logs if l.channel == "apns"]
    assert len(apns_logs) >= 1
    assert apns_logs[0].status == "failed"
    assert apns_logs[0].device_id == "apns:device_token_ios_xyz"


# ─── (j) APNs JWT kesh ────────────────────────────────────────────────────────


def test_apns_jwt_cache():
    """
    ApnsProvider JWT kesh: ikkinchi _make_jwt() bir xil token qaytaradi (muddati o'tmagan).
    """
    provider = ApnsProvider(
        key_id="KID123",
        team_id="TEAM123",
        bundle_id="com.example.retail",
        private_key_pem=_FAKE_EC_KEY,
    )

    jwt1 = provider._make_jwt()
    assert jwt1 is not None

    # Bir zumda ikkinchi chaqiruv — keshdan kelishi kerak
    jwt2 = provider._make_jwt()
    assert jwt2 == jwt1

    # Muddatni oshirib kesh bekor qilish
    provider._jwt_issued_at = time.time() - 3700  # muddati o'tgan
    jwt3 = provider._make_jwt()
    # Yangi JWT — kesh bekor qilindi
    assert jwt3 is not None
    # jwt3 != jwt1 bo'lishi mumkin (iat farq qiladi) — ammo yangi JWT haqiqiy


# ─── (k) FCM tarmoq xatosi → retry uchun failed ──────────────────────────────


@pytest.mark.anyio
async def test_fcm_network_error_returns_failed():
    """
    FcmProvider: httpx tarmoq xatosi → PushResult(ok=False), istisno tashlamaydi.
    """
    provider = FcmProvider(server_key="test-key")

    class _ErrorTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

    with patch("httpx.AsyncClient", side_effect=_make_client_factory(_ErrorTransport())):
        result = await provider.send(
            device_token="any_token",
            title="Test",
            body="Test",
        )

    assert result.ok is False
    assert result.invalid_token is False
    assert result.error is not None
    assert "network" in result.error.lower() or "connect" in result.error.lower()


# ─── (l) service.py end-to-end: FcmProvider mock → push_log ─────────────────


@pytest.mark.anyio
async def test_service_fcm_provider_sent_updates_push_log(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    FcmProvider (mock) muvaffaqiyatli yuborsa → push_log status=sent.
    FakePushProvider emas — haqiqiy FcmProvider mock HTTP bilan.
    """
    from app.modules.push.provider import FcmProvider

    ok_resp = _mock_response(200, {"name": "projects/test/messages/123"})
    token_resp = _mock_response(200, {"access_token": "fake_bearer"})

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "oauth2" in str(request.url) or "googleapis.com/token" in str(request.url):
                return token_resp
            return ok_resp

    provider = FcmProvider(
        project_id="test-project",
        credentials_json=json.dumps({
            "private_key": _FAKE_RSA_KEY,
            "client_email": "svc@test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    store_owner = await make_user(role="store", device_id="fcm_token_e2e_test")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    with patch.object(
        FcmProvider, "_get_oauth2_token", new=AsyncMock(return_value="fake_bearer")
    ), patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        count = await process_pending_pushes(db=db_session, provider=provider)
    await db_session.commit()

    assert count >= 1

    log_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == store_owner.id)
    )
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.status == "sent"
    assert log.sent_at is not None
    assert log.attempts == 1


@pytest.mark.anyio
async def test_service_fcm_unregistered_deactivates_device_token(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    FcmProvider 404 UNREGISTERED → service.py user.device_id=None qiladi.
    Token invalidatsiya: push_log status=failed, user.device_id=None.
    """
    from app.modules.push.provider import FcmProvider

    unregistered_body = {
        "error": {
            "code": 404,
            "message": "Requested entity was not found.",
            "status": "NOT_FOUND",
            "details": [{"@type": "...", "errorCode": "UNREGISTERED"}],
        }
    }
    error_resp = _mock_response(404, unregistered_body)
    token_resp = _mock_response(200, {"access_token": "fake_bearer"})

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "oauth2" in str(request.url) or "googleapis.com/token" in str(request.url):
                return token_resp
            return error_resp

    provider = FcmProvider(
        project_id="test-project",
        credentials_json=json.dumps({
            "private_key": _FAKE_RSA_KEY,
            "client_email": "svc@test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    store_owner = await make_user(role="store", device_id="unregistered_token_xyz")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    with patch.object(
        FcmProvider, "_get_oauth2_token", new=AsyncMock(return_value="fake_bearer")
    ), patch("httpx.AsyncClient", side_effect=_make_client_factory(_Transport())):
        count = await process_pending_pushes(db=db_session, provider=provider)
    await db_session.commit()

    assert count >= 1

    # push_log: status=failed, last_error=token_invalidated
    log_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == store_owner.id)
    )
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.status == "failed"
    assert log.last_error is not None
    assert "token_invalidated" in log.last_error

    # user.device_id = None (qayta yuborilmasligi uchun)
    await db_session.refresh(store_owner)
    assert store_owner.device_id is None, (
        "Token invalidatsiyadan keyin user.device_id=None bo'lishi kerak"
    )


@pytest.mark.anyio
async def test_service_fake_invalid_token_deactivates_device(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    FakePushProvider invalid_token=True → service.py user.device_id=None qiladi.
    FakePushProvider.set_invalid_next() ishlatiladi.
    """
    provider = FakePushProvider()
    provider.set_invalid_next(1)  # birinchi send → invalid_token=True

    store_owner = await make_user(role="store", device_id="invalid_fake_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    count = await process_pending_pushes(db=db_session, provider=provider)
    await db_session.commit()

    assert count >= 1

    # user.device_id = None
    await db_session.refresh(store_owner)
    assert store_owner.device_id is None

    # push_log: status=failed, last_error da token_invalidated
    log_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == store_owner.id)
    )
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.status == "failed"
    assert "token_invalidated" in (log.last_error or "")


# ─── get_push_provider / get_apns_provider factory ───────────────────────────


def test_get_push_provider_returns_fake_in_dev():
    """
    APP_ENV=development, FCM config yo'q → FakePushProvider.

    get_push_provider() chaqirilganda `from app.core.config import settings`
    qiladi — shuning uchun `app.core.config.settings` ni patch qilsak,
    factory patch qilingan settings'ni o'qiydi.
    """
    from app.core.config import Settings
    import app.modules.push.provider as p_mod

    fake_settings = Settings(
        app_env="development",
        fcm_server_key=None,
        fcm_project_id=None,
        fcm_credentials_file=None,
        fcm_credentials=None,
    )

    with patch("app.core.config.settings", fake_settings):
        result = p_mod.get_push_provider()

    assert isinstance(result, FakePushProvider)


def test_get_apns_provider_no_config_noop():
    """
    APNs config yo'q → ApnsProvider._configured=False (no-op).
    """
    from app.core.config import Settings

    fake_settings = Settings(
        app_env="development",
        apns_key_id=None,
        apns_team_id=None,
        apns_bundle_id=None,
        apns_private_key_pem=None,
        apns_key_file=None,
    )
    with patch("app.core.config.settings", fake_settings):
        provider = get_apns_provider()

    assert isinstance(provider, ApnsProvider)
    assert provider._configured is False


# ─── PushResult dataclass ─────────────────────────────────────────────────────


def test_push_result_defaults():
    """PushResult default qiymatlari to'g'ri."""
    r = PushResult(ok=True)
    assert r.ok is True
    assert r.invalid_token is False
    assert r.error is None

    r2 = PushResult(ok=False, invalid_token=True, error="test_error")
    assert r2.ok is False
    assert r2.invalid_token is True
    assert r2.error == "test_error"


# ─── Yordamchi: httpx.AsyncClient factory ─────────────────────────────────────


def _make_client_factory(transport: httpx.AsyncBaseTransport):
    """
    httpx.AsyncClient(...) chaqiruvini berilgan transport bilan qaytaradi.
    patch("httpx.AsyncClient", side_effect=...) uchun.
    """
    original_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        # transport parametrini almashtiramiz
        kwargs.pop("transport", None)
        return original_async_client(*args, transport=transport, **kwargs)

    return _factory


# ─── Test kalitlari (RSA/EC test uchun — haqiqiy deployment da ISHLATILMAYDI) ──
#
# XAVFSIZLIK ESLATMASI:
#   Quyidagi kalitlar FAQAT test muhitida mock uchun.
#   Hech qachon real FCM/APNs konfiguratsiyasida ishlatilmasin.
#   Production da .env.prod da haqiqiy kalit yo'llari beriladi.

# RSA kalit (test uchun — 2048 bit, cryptography bilan generatsiya qilingan).
# FCM v1 testlarida _get_oauth2_token patch qilingani uchun bu kalit aslida
# imzolashga ishlatilmaydi; lekin YAROQLI PEM bo'lishi shart (parse buzilmasin).
_FAKE_RSA_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQC9wNFZugTqFHim
l4ICf9ZtZf/CM2glOdjHVAlLnjB+yP0DryQt7xClN+Qoz5zKoGNOtAuDXBz1l0eD
in1nEOiw26M3ZX5GhPlPis2dAGG0lu6qQtWoH9x+yavjmnhT1mf6eQrMIfRdlzgi
ZsUoVlI9Y3yuxtyV/rL8Pad49Bd0tOHkQCUyD51twCdvxQD7kZScyHxKmGtMjc3Z
BQL92RDE75AbYEe3Jq0GWKKDYXfxXccmX6jM0oMhEpMDsXwQyT+d++SOhlFLqz1Q
sUzUNwdipyGjBcFWs67tF/yTtfw+WOSU6HXujoRj3BzvAGJkhaW8ldOIJ8KImB7o
lYhl74Q5AgMBAAECggEAAIiRfhtWBrNyiGNeJ/Qkje+uuaTL2ujv+VV85jPGZqDZ
h0BfjWqB5TkEQPIeenpbdR3v91lTsoQPnSjPQ/Ip+U9QxOfZ5Ehc7BKTk+irnaab
+qoP8DZQuCGIhG4Lfw7YAX4EIAFLbtTtQTmBPeUKO6ZzNAmWlqxd4/Qna6FiDH+x
cGBi4tRtFVubN2SUkC0LY+nHSUTM6oRtLjy3Wogp6+NWvFNSjZ1ywBDO8vgEro8x
qfHUgIMzOoY14ERrG2HMThGO91rk2Of8EiZRftpA6V7r2vlqiG59j0mAUFGzQikA
TkPMvdxlMNoofEqL506d+JoLF/sJTcLI24hP++i6lQKBgQD4R4yMmkxCBLNJn+sX
yeRmZWbcsKG4pS3Q1GaD22tf7alSle7XOLw2QlPTXPjJy18vu4X+EneSBOW7RZxo
oE36cFdW6TOrdhU2zsDvPO5UkJ5NTTH3fsctjCiUy8Gk/aNSwywmOh84WPV7xjFu
csaHnHaU+6Nbk/qErQt3XsoBLQKBgQDDp11vTgmkp6hgw/nts2/0RFipm+1o66zT
dJxJTBY47ohpwRt21UCfChpTG1bBfgws7zNbv/q8sfgu9Zjl3a7EJdfp0JbLoFO2
bfI/eyZKcQHqXReDMdsmVWNIEvaqHfXgpXmcPy+oyifPbYpA6bqQGdmAg04qzDMl
xpeXJWr+vQKBgGZ7wjxXhJrLreX6KOSM5caOnMMD9f1t0VeeFSLgc5YJWBdK5Gfa
d3Y+MrPQcLF7TTM6yLhzjv+rHdkLhuB5KzbxIFwzrqxb9a3F8kXOdOJbP7zQ3Is4
vabDcAzbfndIax5CifrNiw2LSuloigb5QZHAuAIPTQMENiiF9XG0otWRAoGAdh+C
kqOLwOQUDS/kobUW32OwH95rDFBVTGj3vmz4cbDZnPegbDM9y4ce85Pq4fEGys4z
tK4IZIoSK8/NWuJnFDdAzwJHOHL4d4iTm+3u5TyrCmLfwi6Ef/VHdok0cOqbuuBM
tp+TV5WNSXd548z4/O0OWr9rnv0f2Cu48+D8YwUCgYBJMED8xQgilYGjlaOjMCj/
fZGCbTlYWJEE5ylOpZYvX8u7JkD97WPIyjrCFxsF1KjFuyy28dcFar3Zz0DnrXZd
Ut4yPOgKjzthFCMcD/sZ1LPLwH5Jty3BuCmdcVScDnQUe/uPlwXUn5K26E4hVoJ8
XQ6FCkhjwn2L2WxmXYGB5g==
-----END PRIVATE KEY-----"""

# EC kalit (ES256, APNs JWT uchun — cryptography SECP256R1 bilan generatsiya).
# YAROQLI P-256 PEM — PyJWT ES256 imzolashi uchun zarur (APNs send + JWT kesh testlari).
# Production da haqiqiy .p8 fayl bilan almashtiriladi.
_FAKE_EC_KEY = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgWSanuOzt6XRU+vbx
YLJTQF5YEgHcR2a3Gpxusg9OslKhRANCAASQD2gFv88bAKEbXxhbQwr3LVnxY3He
sdd0AS3favI8mm/+/5aM7upm24SAF+Js2D+MrckdwUgzw5tWKMfeTXMk
-----END PRIVATE KEY-----"""
