"""
pytest konfiguratsiya va umumiy fixtures.

asyncio_mode = "auto" pyproject.toml da o'rnatilgan,
shuning uchun har bir async test avtomatik taniladi.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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
