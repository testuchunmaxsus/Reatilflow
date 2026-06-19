"""
Promo (Aksiya) moduli testlari — T25.

Test kategoriyalari:
  1. CRUD testlari (admin yaratadi/yangilaydi, paginated ro'yxat, active ro'yxat)
  2. RBAC testlari (agent/do'kon yaratolmaydi; active hamma uchun)
  3. compute_line_discount testlari (segment/product mos; mos yo'q → 0)
  4. Buyurtma integratsiya testlari:
       - Amaldagi promo bor mahsulot → line_total SERVER chegirma bilan
       - Klient discount yuborsa e'tiborsiz (T11 himoya)
       - Promo yo'q → discount=0 (mavjud order testlari o'tadi)
  5. Validatsiya testlari (valid_to < valid_from; rule_json yaroqsiz; banner magic-byte)
  6. version conflict, idempotentlik, i18n lokalizatsiyalangan nom
"""

from __future__ import annotations

import io
import uuid
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.promo import Promo
from app.modules.promo import service as promo_service
from app.modules.promo.schemas import PromoCreate, PromoUpdate
from app.modules.orders import service as orders_service
from app.modules.orders.schemas import OrderCreate, OrderLineIn

from app.tests.promo.conftest import get_token, DEFAULT_WAREHOUSE


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _tomorrow() -> date:
    return _today() + timedelta(days=1)


def _yesterday() -> date:
    return _today() - timedelta(days=1)


# ─── 1. CRUD testlari ────────────────────────────────────────────────────────


class TestPromoCRUD:
    """CRUD operatsiyalari: yaratish, olish, ro'yxat, yangilash, o'chirish."""

    async def test_create_promo_admin(self, promo_client: AsyncClient, admin_user, fake_redis, db_session):
        """Admin yangi promo yarata oladi."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "10% chegirma",
                "name_ru": "Скидка 10%",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 10},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name_uz"] == "10% chegirma"
        assert data["name_ru"] == "Скидка 10%"
        assert data["promo_type"] == "discount"
        assert data["is_active"] is True
        assert data["version"] == 1

    async def test_create_promo_returns_localized_name_uz(
        self, promo_client: AsyncClient, admin_user
    ):
        """PromoOut.name — uz tilida."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Arzon narx",
                "name_ru": "Дешево",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Arzon narx"

    async def test_create_promo_returns_localized_name_ru(
        self, promo_client: AsyncClient, admin_user
    ):
        """PromoOut.name — ru tilida."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Arzon narx",
                "name_ru": "Дешево",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Дешево"

    async def test_get_promo(self, promo_client: AsyncClient, admin_user, make_promo):
        """Bitta promo olish."""
        promo = await make_promo(name_uz="Test aksiya")
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.get(
            f"/promos/{promo.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(promo.id)

    async def test_get_promo_not_found(self, promo_client: AsyncClient, admin_user):
        """Mavjud bo'lmagan promo → 404."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.get(
            f"/promos/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["message_key"] == "promo.not_found"

    async def test_list_promos_paginated(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Paginated ro'yxat."""
        for i in range(3):
            await make_promo(name_uz=f"Aksiya {i}")
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.get(
            "/promos?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["limit"] == 2
        assert len(data["items"]) <= 2

    async def test_list_promos_filter_is_active(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """is_active filtri ishlaydi."""
        await make_promo(name_uz="Faol", is_active=True)
        await make_promo(name_uz="Nofaol", is_active=False)
        token = await get_token(promo_client, admin_user)

        resp_active = await promo_client.get(
            "/promos?is_active=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_active.status_code == 200
        items = resp_active.json()["items"]
        assert all(i["is_active"] for i in items)

    async def test_list_active_promos(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """GET /promos/active — hozir amal qiladigan aksiyalar."""
        today = _today()
        await make_promo(
            name_uz="Aktiv aksiya",
            is_active=True,
            valid_from=today - timedelta(days=1),
            valid_to=today + timedelta(days=1),
        )
        await make_promo(
            name_uz="Tugagan aksiya",
            is_active=True,
            valid_from=today - timedelta(days=10),
            valid_to=today - timedelta(days=2),
        )
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.get(
            "/promos/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        # Tugagan aksiya ko'rinmasligi kerak
        names = [i["name_uz"] for i in items]
        assert "Aktiv aksiya" in names
        assert "Tugagan aksiya" not in names

    async def test_update_promo_admin(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Admin promo'ni yangilaydi."""
        promo = await make_promo(name_uz="Eski nom")
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.patch(
            f"/promos/{promo.id}",
            json={"version": 1, "name_uz": "Yangi nom", "is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name_uz"] == "Yangi nom"
        assert data["is_active"] is False
        assert data["version"] == 2

    async def test_delete_promo_admin(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Admin promo'ni soft-delete qiladi."""
        promo = await make_promo(name_uz="O'chiriladigan aksiya")
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.delete(
            f"/promos/{promo.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

        # Endi ko'rinmaydi
        resp2 = await promo_client.get(
            f"/promos/{promo.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 404


# ─── 2. RBAC testlari ────────────────────────────────────────────────────────


class TestPromoRBAC:
    """RBAC: agent/do'kon yaratolmaydi; active hamma uchun."""

    async def test_agent_cannot_create(self, promo_client: AsyncClient, agent_user):
        """Agent promo yarata olmaydi → 403."""
        token = await get_token(promo_client, agent_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Agent aksiya",
                "name_ru": "Agent акция",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_store_user_cannot_create(self, promo_client: AsyncClient, store_user):
        """Do'kon promo yarata olmaydi → 403."""
        token = await get_token(promo_client, store_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Do'kon aksiya",
                "name_ru": "Акция магазина",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_accountant_cannot_create(self, promo_client: AsyncClient, accountant_user):
        """Buxgalter promo yarata olmaydi → 403."""
        token = await get_token(promo_client, accountant_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Buxgalter aksiya",
                "name_ru": "Акция бухгалтера",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_agent_can_view(self, promo_client: AsyncClient, agent_user, make_promo):
        """Agent promo ro'yxatini ko'ra oladi."""
        await make_promo(name_uz="Ko'rinadigan aksiya")
        token = await get_token(promo_client, agent_user)
        resp = await promo_client.get(
            "/promos",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_store_user_can_view_active(
        self, promo_client: AsyncClient, store_user, make_promo
    ):
        """Do'kon aktiv aksiyalarni ko'ra oladi."""
        await make_promo(name_uz="Aktiv aksiya", is_active=True)
        token = await get_token(promo_client, store_user)
        resp = await promo_client.get(
            "/promos/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_courier_cannot_create(self, promo_client: AsyncClient, courier_user):
        """Kuryer promo yarata olmaydi → 403."""
        token = await get_token(promo_client, courier_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Kuryer aksiya",
                "name_ru": "Акция курьера",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # Kuryerda promo:create yo'q → 403
        assert resp.status_code == 403

    async def test_agent_can_view_single(
        self, promo_client: AsyncClient, agent_user, make_promo
    ):
        """Agent bitta promo ko'ra oladi."""
        promo = await make_promo(name_uz="Aksiya")
        token = await get_token(promo_client, agent_user)
        resp = await promo_client.get(
            f"/promos/{promo.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ─── 3. compute_line_discount testlari ───────────────────────────────────────


class TestComputeLineDiscount:
    """SERVER-AVTORITAR chegirma hisoblash testlari."""

    async def test_discount_percent_mos(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Mos promo bor → foizli chegirma hisoblanadi."""
        seg = await make_price_segment("VIP")
        prod = await make_product(price=Decimal("100000"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_percent": 20},
            target_segment_id=seg.id,
            target_product_id=prod.id,
            is_active=True,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("2"),
            unit_price=Decimal("100000"),
        )
        # 100000 * 2 * 20% = 40000
        assert discount == Decimal("40000.00")

    async def test_discount_amount_mos(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Mos promo bor → summaviy chegirma hisoblanadi."""
        seg = await make_price_segment("Ulgurji")
        prod = await make_product(price=Decimal("50000"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_amount": 5000},
            target_segment_id=seg.id,
            is_active=True,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("3"),
            unit_price=Decimal("50000"),
        )
        # 5000 so'm chegirma
        assert discount == Decimal("5000.00")

    async def test_no_matching_promo_returns_zero(
        self, db_session, make_price_segment, make_product
    ):
        """Mos promo yo'q → 0 qaytadi (order regressiyasi yo'q)."""
        seg = await make_price_segment("Chakana")
        prod = await make_product(price=Decimal("30000"), segment_id=seg.id)

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("1"),
            unit_price=Decimal("30000"),
        )
        assert discount == Decimal("0")

    async def test_min_qty_not_met_returns_zero(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """min_qty talabi bajarilmasa → chegirma yo'q."""
        seg = await make_price_segment("Standart")
        prod = await make_product(price=Decimal("20000"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_percent": 15, "min_qty": 5},
            target_product_id=prod.id,
            is_active=True,
        )

        # qty=2 < min_qty=5 → chegirma yo'q
        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("2"),
            unit_price=Decimal("20000"),
        )
        assert discount == Decimal("0")

    async def test_min_qty_met_gives_discount(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """min_qty talabi bajarilsa → chegirma beriladi."""
        seg = await make_price_segment("Ulgurji2")
        prod = await make_product(price=Decimal("20000"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_percent": 15, "min_qty": 5},
            target_product_id=prod.id,
            is_active=True,
        )

        # qty=5 >= min_qty=5 → 15%
        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("5"),
            unit_price=Decimal("20000"),
        )
        # 20000 * 5 * 15% = 15000
        assert discount == Decimal("15000.00")

    async def test_global_promo_applies_to_all_segments(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Global promo (target_segment_id=NULL) barcha segmentlarga amal qiladi."""
        seg = await make_price_segment("IstSegment")
        prod = await make_product(price=Decimal("10000"), segment_id=seg.id)
        # target_segment_id=NULL → global
        await make_promo(
            rule_json={"discount_percent": 5},
            target_segment_id=None,
            is_active=True,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("1"),
            unit_price=Decimal("10000"),
        )
        # 10000 * 1 * 5% = 500
        assert discount == Decimal("500.00")

    async def test_inactive_promo_ignored(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Nofaol promo e'tiborga olinmaydi → 0."""
        seg = await make_price_segment("NofaolSeg")
        prod = await make_product(price=Decimal("10000"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_percent": 50},
            is_active=False,
            target_segment_id=seg.id,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("1"),
            unit_price=Decimal("10000"),
        )
        assert discount == Decimal("0")

    async def test_expired_promo_ignored(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Muddati o'tgan promo e'tiborga olinmaydi → 0."""
        seg = await make_price_segment("EskiSeg")
        prod = await make_product(price=Decimal("10000"), segment_id=seg.id)
        yesterday = _yesterday()
        await make_promo(
            rule_json={"discount_percent": 50},
            is_active=True,
            valid_from=yesterday - timedelta(days=10),
            valid_to=yesterday - timedelta(days=1),  # kecha tugagan
            target_segment_id=seg.id,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("1"),
            unit_price=Decimal("10000"),
        )
        assert discount == Decimal("0")

    async def test_discount_amount_capped_to_line_total(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """Chegirma line_total dan oshib ketmasligi shart."""
        seg = await make_price_segment("CapSeg")
        prod = await make_product(price=Decimal("100"), segment_id=seg.id)
        await make_promo(
            rule_json={"discount_amount": 99999},  # katta chegirma
            target_product_id=prod.id,
            is_active=True,
        )

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=Decimal("1"),
            unit_price=Decimal("100"),
        )
        # Chegirma 100 dan oshib ketmasligi kerak
        assert discount <= Decimal("100.00")
        assert discount >= Decimal("0")

    async def test_discount_percent_over100_capped_to_line_gross(
        self, db_session, make_promo, make_price_segment, make_product
    ):
        """
        T25 gate fix: discount_percent=150 bo'lsa ham chegirma line_gross dan oshmaydi.

        Schema validatsiya API darajasida >100 ni bloklaydi, lekin agar DB da
        bunday qiymat bo'lsa (to'g'ridan-to'g'ri yozilgan) service uni cheklashi kerak.
        line_total hech qachon manfiy bo'lmaydi.
        """
        seg = await make_price_segment("OverPctSeg")
        prod = await make_product(price=Decimal("1000"), segment_id=seg.id)
        # make_promo DB ga to'g'ridan-to'g'ri yozadi — schema bypass
        await make_promo(
            rule_json={"discount_percent": 150},
            target_product_id=prod.id,
            target_segment_id=seg.id,
            is_active=True,
        )

        unit_price = Decimal("1000")
        qty = Decimal("2")
        line_gross = unit_price * qty  # 2000

        discount = await promo_service.compute_line_discount(
            db_session,
            product_id=prod.id,
            segment_id=seg.id,
            qty=qty,
            unit_price=unit_price,
        )
        # Chegirma line_gross (2000) dan oshib ketmasin
        assert discount <= line_gross, (
            f"discount ({discount}) line_gross ({line_gross}) dan katta — manfiy qarz xavfi!"
        )
        # Chegirma manfiy bo'lmasin
        assert discount >= Decimal("0"), f"discount manfiy: {discount}"
        # Aniq: 150% chekilib line_gross ga teng bo'lishi kerak
        assert discount == Decimal("2000.00")

    async def test_discount_percent_over100_order_line_total_not_negative(
        self, db_session, make_promo, make_price_segment, make_product,
        make_store, make_user, seed_stock
    ):
        """
        T25 gate fix (buyurtma integratsiya): discount_percent=150 bilan buyurtmada
        line_total manfiy bo'lmaydi (>= 0).
        """
        from app.modules.orders import service as orders_service
        from app.modules.orders.schemas import OrderCreate, OrderLineIn

        seg = await make_price_segment("NegLineSeg")
        prod = await make_product(price=Decimal("500"), segment_id=seg.id)
        store = await make_store(segment_id=seg.id)
        admin = await make_user("administrator")
        await seed_stock(prod.id, DEFAULT_WAREHOUSE, Decimal("50"))

        # DB ga to'g'ridan-to'g'ri — schema bypass
        await make_promo(
            rule_json={"discount_percent": 150},
            target_segment_id=seg.id,
            is_active=True,
        )

        order_data = OrderCreate(
            store_id=store.id,
            mode="oddiy",
            lines=[OrderLineIn(product_id=prod.id, qty=Decimal("3"))],
        )
        order = await orders_service.create_order(
            db_session,
            order_data,
            actor_id=admin.id,
            user=admin,
        )

        assert len(order.lines) == 1
        line = order.lines[0]
        # line_total hech qachon manfiy bo'lmasligi kerak
        assert line.line_total >= Decimal("0"), (
            f"line_total manfiy: {line.line_total} — manfiy qarz!"
        )


# ─── 4. Buyurtma integratsiya testlari ───────────────────────────────────────


class TestOrderPromoIntegration:
    """Buyurtmaga promo ulash — SERVER-AVTORITAR (T11 himoya)."""

    async def test_order_with_active_promo_applies_server_discount(
        self,
        db_session,
        make_promo,
        make_price_segment,
        make_product,
        make_store,
        make_user,
        seed_stock,
    ):
        """
        Amaldagi promo bor mahsulotga buyurtma → line_total SERVER chegirma bilan.

        SERVER-AVTORITAR: klient discount bera olmaydi.
        Administrator roli ishlatiladi (scope tekshiruvidan o'tish uchun).
        """
        seg = await make_price_segment("IntSeg")
        prod = await make_product(
            price=Decimal("100000"),
            segment_id=seg.id,
        )
        store = await make_store(segment_id=seg.id)
        admin = await make_user("administrator")
        await seed_stock(prod.id, DEFAULT_WAREHOUSE, Decimal("50"))

        # 10% chegirma promo yaratish
        await make_promo(
            rule_json={"discount_percent": 10},
            target_segment_id=seg.id,
            is_active=True,
        )

        order_data = OrderCreate(
            store_id=store.id,
            mode="oddiy",
            lines=[OrderLineIn(product_id=prod.id, qty=Decimal("2"))],
        )
        order = await orders_service.create_order(
            db_session,
            order_data,
            actor_id=admin.id,
            user=admin,
        )

        assert len(order.lines) == 1
        line = order.lines[0]
        # Chegirma: 100000 * 2 * 10% = 20000
        assert line.discount == Decimal("20000.00")
        # line_total = 100000 * 2 - 20000 = 180000
        assert line.line_total == Decimal("180000.00")

    async def test_order_no_promo_discount_is_zero(
        self,
        db_session,
        make_price_segment,
        make_product,
        make_store,
        make_user,
        seed_stock,
    ):
        """
        Promo yo'q → discount=0 (mavjud order testlari buzilmaydi).

        Bu regressiya testi: T25 dan oldin discount=0 bo'lgan.
        Administrator roli ishlatiladi (scope tekshiruvidan o'tish uchun).
        """
        seg = await make_price_segment("NoPromoSeg")
        prod = await make_product(price=Decimal("50000"), segment_id=seg.id)
        store = await make_store(segment_id=seg.id)
        admin = await make_user("administrator")
        await seed_stock(prod.id, DEFAULT_WAREHOUSE, Decimal("50"))

        order_data = OrderCreate(
            store_id=store.id,
            mode="oddiy",
            lines=[OrderLineIn(product_id=prod.id, qty=Decimal("1"))],
        )
        order = await orders_service.create_order(
            db_session,
            order_data,
            actor_id=admin.id,
            user=admin,
        )

        assert len(order.lines) == 1
        line = order.lines[0]
        # Promo yo'q → discount = 0
        assert line.discount == Decimal("0")
        # line_total = 50000 * 1 = 50000
        assert line.line_total == Decimal("50000.00")

    async def test_client_cannot_provide_discount_schema_level(self):
        """
        T11 himoya: OrderLineIn sxemasida discount maydoni yo'q.

        Klient discount bera olmaydi — schema darajasida chiqarib tashlangan.
        """
        from app.modules.orders.schemas import OrderLineIn as OLI
        import pydantic

        # discount maydoni yo'q — extra='ignore' bo'lsa ham servis foydalanmaydi
        line = OLI(product_id=uuid.uuid4(), qty=Decimal("5"))
        # discount maydoni yo'qligi — hasattr bilan tekshiramiz
        assert not hasattr(line, "discount"), "OrderLineIn da discount maydoni bo'lmasligi kerak"

    async def test_order_with_discount_amount_promo(
        self,
        db_session,
        make_promo,
        make_price_segment,
        make_product,
        make_store,
        make_user,
        seed_stock,
    ):
        """discount_amount promo bor mahsulot → line_total dan chegirma chiqariladi."""
        seg = await make_price_segment("AmtSeg")
        prod = await make_product(price=Decimal("80000"), segment_id=seg.id)
        store = await make_store(segment_id=seg.id)
        admin = await make_user("administrator")
        await seed_stock(prod.id, DEFAULT_WAREHOUSE, Decimal("50"))

        await make_promo(
            rule_json={"discount_amount": 5000},
            target_product_id=prod.id,
            is_active=True,
        )

        order_data = OrderCreate(
            store_id=store.id,
            mode="oddiy",
            lines=[OrderLineIn(product_id=prod.id, qty=Decimal("3"))],
        )
        order = await orders_service.create_order(
            db_session,
            order_data,
            actor_id=admin.id,
            user=admin,
        )
        line = order.lines[0]
        assert line.discount == Decimal("5000.00")
        # 80000*3 - 5000 = 235000
        assert line.line_total == Decimal("235000.00")


# ─── 5. Validatsiya testlari ─────────────────────────────────────────────────


class TestPromoValidation:
    """valid_to < valid_from; rule_json yaroqsiz; banner magic-byte."""

    async def test_invalid_dates_create(
        self, promo_client: AsyncClient, admin_user
    ):
        """valid_to < valid_from → 422."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Xato aksiya",
                "name_ru": "Неверная акция",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 10},
                "valid_from": str(_tomorrow()),
                "valid_to": str(_yesterday()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_invalid_rule_json_no_discount_key(
        self, promo_client: AsyncClient, admin_user
    ):
        """rule_json yaroqsiz (hech qanday discount kalit yo'q) → 422."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Yomon qoida",
                "name_ru": "Плохое правило",
                "promo_type": "discount",
                "rule_json": {"some_field": 5},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_invalid_rule_json_both_keys(
        self, promo_client: AsyncClient, admin_user
    ):
        """rule_json ikkita kalit (discount_percent VA discount_amount) → 422."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "Ikkita kalit",
                "name_ru": "Два ключа",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 10, "discount_amount": 5000},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_invalid_rule_json_percent_out_of_range(
        self, promo_client: AsyncClient, admin_user
    ):
        """discount_percent > 100 → 422."""
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.post(
            "/promos",
            json={
                "name_uz": "110%",
                "name_ru": "110%",
                "promo_type": "discount",
                "rule_json": {"discount_percent": 110},
                "valid_from": str(_today()),
                "valid_to": str(_tomorrow()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_banner_bad_magic_bytes(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Banner fayli yaroqsiz magic bytes → 422."""
        promo = await make_promo(name_uz="Banner aksiya")
        token = await get_token(promo_client, admin_user)

        # SVG fayli (yaroqsiz)
        bad_file = io.BytesIO(b"<svg>...</svg>")
        resp = await promo_client.post(
            f"/promos/{promo.id}/banner",
            files={"file": ("banner.svg", bad_file, "image/svg+xml")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_banner_valid_jpeg(
        self, promo_client: AsyncClient, admin_user, make_promo, fake_storage
    ):
        """JPEG banner muvaffaqiyatli yuklanadi."""
        promo = await make_promo(name_uz="Banner JPEG")
        token = await get_token(promo_client, admin_user)

        # To'g'ri JPEG magic bytes
        jpeg_data = b"\xff\xd8\xff" + b"\x00" * 20
        resp = await promo_client.post(
            f"/promos/{promo.id}/banner",
            files={"file": ("banner.jpg", io.BytesIO(jpeg_data), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["banner_url"] is not None

    async def test_update_invalid_dates(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """PATCH da valid_to < valid_from → 422."""
        promo = await make_promo(
            valid_from=_today(),
            valid_to=_tomorrow(),
        )
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.patch(
            f"/promos/{promo.id}",
            json={
                "version": 1,
                "valid_from": str(_tomorrow()),
                "valid_to": str(_yesterday()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ─── 6. Version conflict, idempotentlik, i18n ────────────────────────────────


class TestPromoVersionAndIdempotency:
    """version conflict va idempotentlik testlari."""

    async def test_version_conflict(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Noto'g'ri version → 409."""
        promo = await make_promo(name_uz="Versiya aksiya")
        token = await get_token(promo_client, admin_user)
        resp = await promo_client.patch(
            f"/promos/{promo.id}",
            json={"version": 999, "name_uz": "Yangi nom"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_idempotency_same_client_uuid(
        self, promo_client: AsyncClient, admin_user
    ):
        """Bir xil client_uuid bilan ikki marta POST → birinchi promo qaytariladi."""
        client_uuid = str(uuid.uuid4())
        token = await get_token(promo_client, admin_user)
        payload = {
            "name_uz": "Idempotent aksiya",
            "name_ru": "Идемпотентная акция",
            "promo_type": "discount",
            "rule_json": {"discount_percent": 5},
            "valid_from": str(_today()),
            "valid_to": str(_tomorrow()),
            "client_uuid": client_uuid,
        }

        resp1 = await promo_client.post(
            "/promos", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 201
        first_id = resp1.json()["id"]

        resp2 = await promo_client.post(
            "/promos", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        # Idempotentlik — ikkinchi so'rov ham 201 (yoki 200) va bir xil id
        assert resp2.status_code in (200, 201)
        assert resp2.json()["id"] == first_id

    async def test_service_idempotency_returns_existing(
        self, db_session, make_promo
    ):
        """Service darajasida: bir xil client_uuid → mavjud promo qaytariladi."""
        client_uuid = uuid.uuid4()
        existing = await make_promo(name_uz="Mavjud", client_uuid=client_uuid)

        data = PromoCreate(
            name_uz="Yangi",
            name_ru="Новый",
            promo_type="discount",
            rule_json={"discount_percent": 5},
            valid_from=_today(),
            valid_to=_tomorrow(),
            client_uuid=client_uuid,
        )

        from unittest.mock import AsyncMock
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=str(existing.id))

        class FakeAdmin:
            id = uuid.uuid4()
            role = "administrator"

        admin = FakeAdmin()
        result = await promo_service.create_promo(
            db_session, data, actor_id=admin.id, user=admin, redis=mock_redis,
        )
        assert result.id == existing.id

    async def test_localized_name_in_list(
        self, promo_client: AsyncClient, admin_user, make_promo
    ):
        """Ro'yxatda lokalizatsiyalangan nom ishlaydi."""
        await make_promo(name_uz="O'zbek aksiya", name_ru="Русская акция")
        token = await get_token(promo_client, admin_user)

        resp_uz = await promo_client.get(
            "/promos",
            headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
        )
        assert resp_uz.status_code == 200
        names_uz = [i["name"] for i in resp_uz.json()["items"]]
        assert any("O'zbek aksiya" == n for n in names_uz)

        resp_ru = await promo_client.get(
            "/promos",
            headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
        )
        assert resp_ru.status_code == 200
        names_ru = [i["name"] for i in resp_ru.json()["items"]]
        assert any("Русская акция" == n for n in names_ru)
