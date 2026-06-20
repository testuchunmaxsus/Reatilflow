"""
pytest konfiguratsiya va umumiy fixtures.

asyncio_mode = "auto" pyproject.toml da o'rnatilgan,
shuning uchun har bir async test avtomatik taniladi.

MT1: default_enterprise fixture — barcha test modullari uchun umumiy.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app

# ─── Test uchun default korxona UUID ─────────────────────────────────────────
# Bu UUID testlarda "default test enterprise" sifatida ishlatiladi.
# Migratsiya 0020 dagi DEFAULT_ENTERPRISE_UUID dan farqli (test izolyatsiyasi).
TEST_ENTERPRISE_UUID = uuid.UUID("00000000-0000-7000-8000-000000000099")


@pytest.fixture(scope="session")
def anyio_backend():
    """anyio backend — asyncio."""
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncClient:
    """
    Barcha testlar uchun umumiy async HTTP klient.

    ASGI transport — haqiqiy server kerak emas.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
