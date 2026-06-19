"""
RBAC ruxsat matritsasi testlari.

ADR-001 §3.6 bo'yicha har rol uchun allow/deny scenariylarini tekshiradi.
Infrasiz — aiosqlite + fakeredis.

Test guruhlari:
  1. `has_permission` — sof sinxron, matritsadan
  2. `get_permissions_for_role` — Redis kesh va graceful degradation
  3. Matritsa invariantlari (admin barchaga, store finance:approve → deny, va h.k.)
"""

from __future__ import annotations

import json

import pytest

from app.models.user import AppUser
from app.modules.rbac.permissions import (
    ROLE_PERMISSIONS,
    Action,
    Module,
    ALL_VALID_ROLES,
)
from app.modules.rbac.service import get_permissions_for_role, has_permission


# ─── has_permission — sof sinxron testlar ────────────────────────────────────


class TestHasPermission:
    """has_permission() — matritsadan to'g'ridan-to'g'ri."""

    def _make_user(self, role: str) -> AppUser:
        """
        Minimal AppUser mock (DB kerak emas).

        dataclasses-like obyekt yaratish — SQLAlchemy ORM holat kerak emas,
        has_permission faqat `user.role` ga murojaat qiladi.
        """
        import types
        user = types.SimpleNamespace(role=role)
        return user  # type: ignore[return-value]

    # ─── Administrator ────────────────────────────────────────────────────────

    def test_admin_catalog_create_allow(self):
        """administrator → catalog:create → ruxsat."""
        user = self._make_user("administrator")
        assert has_permission(user, Module.CATALOG, Action.CREATE) is True

    def test_admin_catalog_delete_allow(self):
        """administrator → catalog:delete → ruxsat."""
        user = self._make_user("administrator")
        assert has_permission(user, Module.CATALOG, Action.DELETE) is True

    def test_admin_rbac_crud_allow(self):
        """administrator → rbac:create/delete → ruxsat."""
        user = self._make_user("administrator")
        assert has_permission(user, Module.RBAC, Action.CREATE) is True
        assert has_permission(user, Module.RBAC, Action.DELETE) is True

    def test_admin_finance_approve_deny(self):
        """administrator → finance:approve → taqiqlangan (ADR §3.6 matritsasida yo'q)."""
        user = self._make_user("administrator")
        assert has_permission(user, Module.FINANCE, Action.APPROVE) is False

    # ─── Agent ───────────────────────────────────────────────────────────────

    def test_agent_catalog_view_allow(self):
        """agent → catalog:view → ruxsat."""
        user = self._make_user("agent")
        assert has_permission(user, Module.CATALOG, Action.VIEW) is True

    def test_agent_catalog_create_deny(self):
        """agent → catalog:create → taqiqlangan."""
        user = self._make_user("agent")
        assert has_permission(user, Module.CATALOG, Action.CREATE) is False

    def test_agent_catalog_delete_deny(self):
        """agent → catalog:delete → taqiqlangan."""
        user = self._make_user("agent")
        assert has_permission(user, Module.CATALOG, Action.DELETE) is False

    def test_agent_agent_cabinet_edit_allow(self):
        """agent → agent_cabinet:edit → ruxsat (o'zi uchun, row-level scope bilan)."""
        user = self._make_user("agent")
        assert has_permission(user, Module.AGENT_CABINET, Action.EDIT) is True

    def test_agent_finance_approve_deny(self):
        """agent → finance:approve → taqiqlangan."""
        user = self._make_user("agent")
        assert has_permission(user, Module.FINANCE, Action.APPROVE) is False

    def test_agent_rbac_deny(self):
        """agent → rbac:view → taqiqlangan."""
        user = self._make_user("agent")
        assert has_permission(user, Module.RBAC, Action.VIEW) is False

    def test_agent_stock_view_allow(self):
        """agent → stock:view → ruxsat."""
        user = self._make_user("agent")
        assert has_permission(user, Module.STOCK, Action.VIEW) is True

    def test_agent_stock_create_deny(self):
        """agent → stock:create → taqiqlangan."""
        user = self._make_user("agent")
        assert has_permission(user, Module.STOCK, Action.CREATE) is False

    # ─── Courier ─────────────────────────────────────────────────────────────

    def test_courier_delivery_create_deny(self):
        """courier → delivery:create → taqiqlangan (T18: tayinlash faqat admin/agent)."""
        user = self._make_user("courier")
        assert has_permission(user, Module.DELIVERY, Action.CREATE) is False

    def test_courier_delivery_edit_allow(self):
        """courier → delivery:edit → ruxsat."""
        user = self._make_user("courier")
        assert has_permission(user, Module.DELIVERY, Action.EDIT) is True

    def test_courier_finance_view_deny(self):
        """courier → finance:view → taqiqlangan (ADR §3.6: Kuryer — buxgalteriya yo'q)."""
        user = self._make_user("courier")
        assert has_permission(user, Module.FINANCE, Action.VIEW) is False

    def test_courier_contracts_deny(self):
        """courier → contracts:view → taqiqlangan."""
        user = self._make_user("courier")
        assert has_permission(user, Module.CONTRACTS, Action.VIEW) is False

    def test_courier_promo_deny(self):
        """courier → promo:view → taqiqlangan."""
        user = self._make_user("courier")
        assert has_permission(user, Module.PROMO, Action.VIEW) is False

    def test_courier_agent_cabinet_deny(self):
        """courier → agent_cabinet:view → taqiqlangan."""
        user = self._make_user("courier")
        assert has_permission(user, Module.AGENT_CABINET, Action.VIEW) is False

    # ─── Accountant ──────────────────────────────────────────────────────────

    def test_accountant_finance_approve_allow(self):
        """accountant → finance:approve → ruxsat."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.FINANCE, Action.APPROVE) is True

    def test_accountant_finance_crud_allow(self):
        """accountant → finance:create/edit/delete → ruxsat."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.FINANCE, Action.CREATE) is True
        assert has_permission(user, Module.FINANCE, Action.EDIT) is True
        assert has_permission(user, Module.FINANCE, Action.DELETE) is True

    def test_accountant_rbac_view_allow(self):
        """accountant → rbac:view (audit) → ruxsat."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.RBAC, Action.VIEW) is True

    def test_accountant_rbac_create_deny(self):
        """accountant → rbac:create → taqiqlangan (faqat view)."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.RBAC, Action.CREATE) is False

    def test_accountant_catalog_create_deny(self):
        """accountant → catalog:create → taqiqlangan."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.CATALOG, Action.CREATE) is False

    def test_accountant_contracts_edit_allow(self):
        """accountant → contracts:edit → ruxsat."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.CONTRACTS, Action.EDIT) is True

    def test_accountant_contracts_delete_deny(self):
        """accountant → contracts:delete → taqiqlangan."""
        user = self._make_user("accountant")
        assert has_permission(user, Module.CONTRACTS, Action.DELETE) is False

    # ─── Store (do'kon) ───────────────────────────────────────────────────────

    def test_store_catalog_view_allow(self):
        """store → catalog:view → ruxsat."""
        user = self._make_user("store")
        assert has_permission(user, Module.CATALOG, Action.VIEW) is True

    def test_store_catalog_create_deny(self):
        """store → catalog:create → taqiqlangan."""
        user = self._make_user("store")
        assert has_permission(user, Module.CATALOG, Action.CREATE) is False

    def test_store_finance_approve_deny(self):
        """store → finance:approve → taqiqlangan."""
        user = self._make_user("store")
        assert has_permission(user, Module.FINANCE, Action.APPROVE) is False

    def test_store_finance_view_allow(self):
        """store → finance:view → ruxsat (o'z balansi)."""
        user = self._make_user("store")
        assert has_permission(user, Module.FINANCE, Action.VIEW) is True

    def test_store_attendance_deny(self):
        """store → attendance:view → taqiqlangan."""
        user = self._make_user("store")
        assert has_permission(user, Module.ATTENDANCE, Action.VIEW) is False

    def test_store_rbac_deny(self):
        """store → rbac:view → taqiqlangan."""
        user = self._make_user("store")
        assert has_permission(user, Module.RBAC, Action.VIEW) is False

    def test_store_tickets_create_allow(self):
        """store → tickets:create → ruxsat."""
        user = self._make_user("store")
        assert has_permission(user, Module.TICKETS, Action.CREATE) is True

    def test_store_stock_view_deny(self):
        """store → stock:view → taqiqlangan (ADR §3.6)."""
        user = self._make_user("store")
        assert has_permission(user, Module.STOCK, Action.VIEW) is False

    # ─── Noto'g'ri rol ────────────────────────────────────────────────────────

    def test_unknown_role_denies_all(self):
        """Noma'lum rol → hamma narsa taqiqlangan."""
        user = self._make_user("superadmin_unknown")
        assert has_permission(user, Module.CATALOG, Action.VIEW) is False
        assert has_permission(user, Module.FINANCE, Action.APPROVE) is False

    # ─── Matritsa invariantlari ───────────────────────────────────────────────

    def test_all_roles_have_catalog_view(self):
        """ADR §3.6: barcha rollar catalog:view ga ega (Katalog — umumiy)."""
        for role in ALL_VALID_ROLES:
            user = self._make_user(role)
            assert has_permission(user, Module.CATALOG, Action.VIEW) is True, (
                f"{role} catalog:view ga ega bo'lishi kerak"
            )

    def test_only_accountant_has_finance_approve(self):
        """ADR §3.6: faqat accountant finance:approve ga ega."""
        for role in ALL_VALID_ROLES:
            user = self._make_user(role)
            expected = role == "accountant"
            assert has_permission(user, Module.FINANCE, Action.APPROVE) is expected, (
                f"{role} finance:approve = {expected} bo'lishi kerak"
            )

    def test_only_admin_has_rbac_create(self):
        """ADR §3.6: faqat administrator rbac:create ga ega."""
        for role in ALL_VALID_ROLES:
            user = self._make_user(role)
            expected = role == "administrator"
            assert has_permission(user, Module.RBAC, Action.CREATE) is expected, (
                f"{role} rbac:create = {expected} bo'lishi kerak"
            )

    def test_permissions_are_nonempty_for_all_roles(self):
        """Har rol uchun kamida bitta ruxsat bo'lishi kerak."""
        for role in ALL_VALID_ROLES:
            assert len(ROLE_PERMISSIONS[role]) > 0, (
                f"{role} uchun ruxsatlar to'plami bo'sh"
            )


# ─── get_permissions_for_role — Redis kesh testlari ──────────────────────────


class TestGetPermissionsForRole:
    """get_permissions_for_role() — Redis kesh + graceful degradation."""

    @pytest.mark.asyncio
    async def test_returns_permissions_from_matrix(self, fake_redis):
        """Redis bo'sh — matritsadan yuklanadi."""
        perms = await get_permissions_for_role("accountant", fake_redis)
        assert "finance:approve" in perms
        assert "catalog:view" in perms
        assert "finance:create" in perms

    @pytest.mark.asyncio
    async def test_caches_to_redis(self, fake_redis):
        """Birinchi chaqiruvdan keyin Redis'ga keshlanadi."""
        perms = await get_permissions_for_role("agent", fake_redis)

        # Redis'da kalit bo'lishi kerak
        cached_raw = await fake_redis.get("rbac:perms:agent")
        assert cached_raw is not None
        cached = set(json.loads(cached_raw))
        assert cached == perms

    @pytest.mark.asyncio
    async def test_second_call_reads_from_cache(self, fake_redis):
        """Ikkinchi chaqiruv keshdan o'qiydi (matritsadan emas)."""
        # Birinchi chaqiruv — kesh to'ldiradi
        perms1 = await get_permissions_for_role("courier", fake_redis)

        # Keshni vaqtinchalik o'zgartirish (agar ikkinchi chaqiruv keshdan o'qisa,
        # u o'zgartirilgan qiymatni qaytaradi)
        modified = sorted(perms1) + ["fake:permission"]
        await fake_redis.set("rbac:perms:courier", json.dumps(modified))

        # Ikkinchi chaqiruv — keshdan o'qishi kerak
        perms2 = await get_permissions_for_role("courier", fake_redis)
        assert "fake:permission" in perms2  # keshdan o'qildi

    @pytest.mark.asyncio
    async def test_unknown_role_returns_empty(self, fake_redis):
        """Noma'lum rol → bo'sh to'plam."""
        perms = await get_permissions_for_role("nonexistent_role", fake_redis)
        assert perms == set()

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_redis_error(self, fake_redis):
        """
        Redis o'chsa (ConnectionError simulyatsiya) → matritsadan qaytaradi.

        fakeredis'da ConnectionError ni simulate qilib bo'lmaydi to'g'ridan-to'g'ri,
        shuning uchun broken redis klientini mock qilamiz.
        """
        from unittest.mock import AsyncMock

        broken_redis = AsyncMock()
        broken_redis.get.side_effect = ConnectionError("Redis ulanmadi")
        broken_redis.set.side_effect = ConnectionError("Redis ulanmadi")

        # Xatolikka qaramay matritsadan yuklanishi kerak
        perms = await get_permissions_for_role("administrator", broken_redis)
        assert "catalog:create" in perms
        assert "rbac:delete" in perms

    @pytest.mark.asyncio
    async def test_all_roles_loadable(self, fake_redis):
        """Barcha rollar uchun ruxsatlar yuklanishi kerak."""
        for role in ["administrator", "agent", "courier", "accountant", "store"]:
            perms = await get_permissions_for_role(role, fake_redis)
            assert isinstance(perms, set)
            assert len(perms) > 0
