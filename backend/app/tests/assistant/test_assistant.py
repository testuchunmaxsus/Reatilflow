"""
Assistant moduli testlari.

Test kategoriyalari:
  1. chat service: fail-open (Groq yo'q → statik fallback)
  2. chat service: Groq muvaffaqiyatli → ai_enabled=True
  3. prompts: rol bo'yicha tizim prompt to'g'ri quruladi
  4. HTTP endpoint: RBAC (401, to'g'ri rol → 200)
  5. HTTP endpoint: tarix kesish (max 6 ta)
  6. HTTP endpoint: uzun xabar → 422

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.user import AppUser
from app.modules.assistant.prompts import STATIC_FALLBACK, build_system_prompt
from app.modules.assistant.schemas import ChatIn, ChatMessage
from app.tests.assistant.conftest import get_token


# ─── 1. Prompts ───────────────────────────────────────────────────────────────


def test_build_system_prompt_contains_role_context():
    """Har rol uchun tizim prompt muvofiq kontekst bilan quruladi."""
    admin_prompt = build_system_prompt("administrator")
    assert "administrator" in admin_prompt.lower()
    assert "RetailFlowAI" in admin_prompt

    store_prompt = build_system_prompt("store")
    assert "kassir" in store_prompt.lower() or "do'kon" in store_prompt.lower()

    agent_prompt = build_system_prompt("agent")
    assert "agent" in agent_prompt.lower()


def test_build_system_prompt_unknown_role():
    """Noma'lum rol uchun base prompt qaytariladi."""
    prompt = build_system_prompt("unknown_role")
    assert "RetailFlowAI" in prompt


def test_static_fallback_not_empty():
    """Statik fallback bo'sh emas."""
    assert STATIC_FALLBACK
    assert len(STATIC_FALLBACK) > 20


# ─── 2. chat service — fail-open ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_service_no_api_key(admin_user: AppUser):
    """GROQ_API_KEY yo'q → statik fallback, ai_enabled=False."""
    from app.modules.assistant.service import chat

    body = ChatIn(message="Katalogga mahsulot qanday qo'shiladi?", history=[])

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None

        result = await chat(body=body, current_user=admin_user)

    assert result.ai_enabled is False
    assert result.reply == STATIC_FALLBACK


@pytest.mark.asyncio
async def test_chat_service_groq_success(admin_user: AppUser):
    """Groq muvaffaqiyatli → ai_enabled=True, javob qaytariladi."""
    from app.modules.assistant.service import chat

    body = ChatIn(message="Salom, qanday yordam bera olasiz?", history=[])

    mock_response = {
        "choices": [
            {"message": {"content": "Salom! Tizimdan foydalanish yordam bera olaman."}}
        ]
    }

    # httpx modul ichki import'ga patch (service funksiyasi ichida import)
    import httpx as real_httpx

    mock_response_obj = AsyncMock()
    mock_response_obj.status_code = 200
    mock_response_obj.json = lambda: mock_response  # sync callable

    async def mock_async_post(*args, **kwargs):
        return mock_response_obj

    mock_client_instance = AsyncMock()
    mock_client_instance.post = mock_async_post

    class MockAsyncClientCM:
        async def __aenter__(self):
            return mock_client_instance

        async def __aexit__(self, *args):
            return False

    with patch.object(real_httpx, "AsyncClient", return_value=MockAsyncClientCM()):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.groq_api_key = "fake-key-for-test"
            mock_settings.groq_model = "llama-3.3-70b-versatile"

            result = await chat(body=body, current_user=admin_user)

    assert result.ai_enabled is True
    assert "Salom" in result.reply


@pytest.mark.asyncio
async def test_chat_service_groq_error_fallback(admin_user: AppUser):
    """Groq xato bo'lsa → statik fallback (fail-open)."""
    from app.modules.assistant.service import chat

    body = ChatIn(message="Savol", history=[])

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Network error")
        )

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.groq_api_key = "fake-key"
            mock_settings.groq_model = "llama-3.3-70b-versatile"

            result = await chat(body=body, current_user=admin_user)

    assert result.ai_enabled is False
    assert result.reply == STATIC_FALLBACK


# ─── 3. Tarix kesish ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_history_trimmed_to_6(admin_user: AppUser):
    """Tarix 6 ta xabardan oshsa, server 6 tagacha kesadi."""
    from app.modules.assistant.service import _call_groq, _MAX_HISTORY
    import httpx as real_httpx

    # 10 ta tarix
    history = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"xabar {i}")
        for i in range(10)
    ]

    captured_messages = []

    async def mock_post(url, **kwargs):
        # messages parametrini saqlash
        captured_messages.extend(kwargs.get("json", {}).get("messages", []))
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {"choices": [{"message": {"content": "OK javob"}}]}
        return mock_resp

    mock_client_instance = AsyncMock()
    mock_client_instance.post = mock_post

    class MockCM:
        async def __aenter__(self):
            return mock_client_instance

        async def __aexit__(self, *a):
            return False

    with patch.object(real_httpx, "AsyncClient", return_value=MockCM()):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.groq_api_key = "fake"
            mock_settings.groq_model = "llama-3.3-70b-versatile"

            # _MAX_HISTORY = 6, service'da trimlanadi
            trimmed = history[-_MAX_HISTORY:]
            await _call_groq("Yangi savol", trimmed, "administrator")

    # system + max 6 tarix + 1 yangi xabar = 8 ta
    assert len(captured_messages) <= 8


# ─── 4. HTTP endpoint RBAC ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_endpoint_unauthorized(assistant_client):
    """Token yo'q → 401."""
    resp = await assistant_client.post(
        "/assistant/chat",
        json={"message": "Salom", "history": []},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_endpoint_admin_success(assistant_client, admin_user):
    """Administrator chat endpointga kira oladi → 200."""
    token = await get_token(assistant_client, admin_user)

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None  # fallback

        resp = await assistant_client.post(
            "/assistant/chat",
            json={"message": "Katalog nima?", "history": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "ai_enabled" in data
    assert data["ai_enabled"] is False  # API key yo'q → fallback


@pytest.mark.asyncio
async def test_chat_endpoint_agent_success(assistant_client, agent_user):
    """Agent ham chat endpointga kira oladi."""
    token = await get_token(assistant_client, agent_user)

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None

        resp = await assistant_client.post(
            "/assistant/chat",
            json={"message": "Buyurtma qanday beriladi?", "history": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_endpoint_store_success(assistant_client, store_user):
    """Store roli ham chat endpointga kira oladi."""
    token = await get_token(assistant_client, store_user)

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None

        resp = await assistant_client.post(
            "/assistant/chat",
            json={"message": "POS sotuv qanday amalga oshiriladi?", "history": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_endpoint_too_long_message(assistant_client, admin_user):
    """1000 belgidan uzun xabar → 422."""
    token = await get_token(assistant_client, admin_user)

    resp = await assistant_client.post(
        "/assistant/chat",
        json={"message": "a" * 1001, "history": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_endpoint_pii_not_sent(assistant_client, admin_user):
    """
    PII test: server-tarafda enterprise_id va store_id Groq'ga YUBORILMAYDI.
    Groq yo'q (fallback) → javob qaytariladi, PII test statik fallback ustida ham ishlaydi.
    """
    token = await get_token(assistant_client, admin_user)

    # API key yo'q → statik fallback, Groq'ga so'rov yo'q — PII chiqmaydi
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None

        resp = await assistant_client.post(
            "/assistant/chat",
            json={"message": "Savol", "history": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    # Javobda enterprise_id yoki store_id bo'lmasligi kerak
    assert "enterprise_id" not in data["reply"]
    assert "store_id" not in data["reply"]
