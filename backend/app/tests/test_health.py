"""
Health endpoint testlari.

Testlar httpx.AsyncClient orqali ASGI transport ishlatadi —
haqiqiy server kerak emas, DB ham ulanishi shart emas.

Ishlatish:
    cd backend
    pytest app/tests/test_health.py -v
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """
    Test klienti — ASGI transport orqali (haqiqiy server kerak emas).
    AsyncClient async context manager sifatida ishlatiladi.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ─── /health testlari ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """/health 200 qaytarishi kerak."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_ok_status(client: AsyncClient) -> None:
    """/health javobida status='ok' bo'lishi kerak."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_service_name(client: AsyncClient) -> None:
    """/health javobida service='retail-api' bo'lishi kerak."""
    response = await client.get("/health")
    data = response.json()
    assert data["service"] == "retail-api"


@pytest.mark.asyncio
async def test_health_is_json(client: AsyncClient) -> None:
    """/health Content-Type application/json bo'lishi kerak."""
    response = await client.get("/health")
    assert "application/json" in response.headers["content-type"]


# ─── /openapi.json testlari ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openapi_returns_200(client: AsyncClient) -> None:
    """/openapi.json 200 qaytarishi kerak."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_has_info(client: AsyncClient) -> None:
    """/openapi.json da info.title bo'lishi kerak."""
    response = await client.get("/openapi.json")
    data = response.json()
    assert "info" in data
    assert data["info"]["title"] == "RETAIL API"


@pytest.mark.asyncio
async def test_openapi_has_paths(client: AsyncClient) -> None:
    """/openapi.json da /health yo'li bo'lishi kerak."""
    response = await client.get("/openapi.json")
    data = response.json()
    assert "/health" in data.get("paths", {})
