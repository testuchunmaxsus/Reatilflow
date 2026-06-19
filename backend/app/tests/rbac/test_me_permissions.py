"""
/auth/me permissions kengaytmasi testlari.

T2 kengaytmasi: /auth/me javobida `permissions: list[str]` maydoni.
Har rol uchun to'g'ri ruxsatlar ro'yxati qaytishini tekshiradi.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import AppUser
from app.tests.rbac.conftest import get_token_for_user, TEST_PASSWORD


# ─── /auth/me — permissions maydoni ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_includes_permissions_field(
    rbac_client: AsyncClient, admin_user: AppUser
) -> None:
    """/auth/me javobi `permissions` maydonini o'z ichiga olishi kerak."""
    token = await get_token_for_user(rbac_client, admin_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "permissions" in data
    assert isinstance(data["permissions"], list)


@pytest.mark.asyncio
async def test_me_admin_permissions(rbac_client: AsyncClient, admin_user: AppUser) -> None:
    """/auth/me administrator → CRUD ruxsatlari va rbac:delete mavjud."""
    token = await get_token_for_user(rbac_client, admin_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert "catalog:create" in perms
    assert "catalog:delete" in perms
    assert "rbac:delete" in perms
    assert "rbac:view" in perms
    # admin finance:approve yo'q (ADR §3.6)
    assert "finance:approve" not in perms


@pytest.mark.asyncio
async def test_me_accountant_permissions(
    rbac_client: AsyncClient, accountant_user: AppUser
) -> None:
    """/auth/me accountant → finance:approve mavjud, catalog:create yo'q."""
    token = await get_token_for_user(rbac_client, accountant_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert "finance:approve" in perms
    assert "rbac:view" in perms
    assert "catalog:create" not in perms
    assert "rbac:create" not in perms


@pytest.mark.asyncio
async def test_me_agent_permissions(rbac_client: AsyncClient, agent_user: AppUser) -> None:
    """/auth/me agent → catalog:view mavjud, catalog:create yo'q."""
    token = await get_token_for_user(rbac_client, agent_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert "catalog:view" in perms
    assert "agent_cabinet:edit" in perms
    assert "catalog:create" not in perms
    assert "finance:approve" not in perms
    assert "rbac:view" not in perms


@pytest.mark.asyncio
async def test_me_courier_permissions(rbac_client: AsyncClient, courier_user: AppUser) -> None:
    """/auth/me courier → delivery:create mavjud, finance:view yo'q."""
    token = await get_token_for_user(rbac_client, courier_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    # T18: courier delivery:create yo'q (tayinlash faqat admin/agent)
    assert "delivery:create" not in perms
    assert "delivery:edit" in perms
    assert "finance:view" not in perms
    assert "contracts:view" not in perms


@pytest.mark.asyncio
async def test_me_store_permissions(rbac_client: AsyncClient, store_user: AppUser) -> None:
    """/auth/me store → catalog:view mavjud, finance:approve yo'q."""
    token = await get_token_for_user(rbac_client, store_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert "catalog:view" in perms
    assert "finance:view" in perms
    assert "finance:approve" not in perms
    assert "stock:view" not in perms
    assert "rbac:view" not in perms


@pytest.mark.asyncio
async def test_me_permissions_sorted(rbac_client: AsyncClient, admin_user: AppUser) -> None:
    """/auth/me permissions ro'yxati saralangan bo'lishi kerak."""
    token = await get_token_for_user(rbac_client, admin_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert perms == sorted(perms), "permissions saralangan bo'lishi kerak"


@pytest.mark.asyncio
async def test_me_permissions_no_duplicates(
    rbac_client: AsyncClient, admin_user: AppUser
) -> None:
    """/auth/me permissions ro'yxatida takrorlanish bo'lmasligi kerak."""
    token = await get_token_for_user(rbac_client, admin_user)
    resp = await rbac_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    perms = resp.json()["permissions"]
    assert len(perms) == len(set(perms)), "permissions ro'yxatida takrorlanish bor"


@pytest.mark.asyncio
async def test_me_without_auth_returns_401(rbac_client: AsyncClient) -> None:
    """/auth/me token'siz → 401 (regression)."""
    resp = await rbac_client.get("/auth/me")
    assert resp.status_code == 401
