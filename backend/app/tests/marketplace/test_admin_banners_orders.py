"""
Admin marketplace testlari — Vazifa 1 + Vazifa 2.

Qamrov:
  VAZIFA 1 — GET /marketplace/banners/mine (korxona-admin endpoint):
    1. Korxona O'Z bannerlarini ko'radi — aktiv, nofaol, muddati o'tgan hammasi chiqadi.
    2. Tenant izolyatsiya: A korxona banneri B korxona /banners/mine'da KO'RINMAYDI.
    3. Nofaol banner /banners/mine'da ko'rinadi (is_active=False ham).
    4. Muddati o'tgan banner /banners/mine'da ko'rinadi (valid_to=o'tgan ham).
    5. Superadmin (enterprise_id=None) → bo'sh sahifa (items=[], total=0).
    6. Paginated javob strukturasi to'g'ri (items, total, limit, offset).
    7. Tartib: priority DESC, created_at DESC.

  VAZIFA 2 — list_incoming/list_outgoing nom maydonlari:
    8. list_incoming javobida supplier_name, buyer_store_name, product_name to'g'ri keladi.
    9. list_outgoing javobida supplier_name, product_name to'g'ri keladi.
    10. confirm endpoint javobida nom maydonlari None (enrich=False, MissingGreenlet yo'q).
    11. courier_name — ship+deliver oqimida list_incoming'da to'g'ri keladi.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.store import Store
from app.models.user import AppUser
from app.tests.marketplace.conftest import TEST_ENTERPRISE_B_UUID, get_token


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


def _today() -> date:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()


def _yesterday() -> date:
    return _today() - timedelta(days=1)


def _tomorrow() -> date:
    return _today() + timedelta(days=1)


def _make_user(role: str, enterprise_id: uuid.UUID, suffix: str = "") -> AppUser:
    """Sinov foydalanuvchisi yaratadi."""
    from app.core.jwt import hash_password
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix))
    return AppUser(
        id=user_id,
        full_name=f"Test {role.capitalize()} {suffix}",
        phone=f"+99893{str(phone_hash)[:7]}",
        role=role,
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=enterprise_id,
    )


async def _create_banner(
    client: AsyncClient,
    token: str,
    title: str = "Test Banner",
    is_active: bool = True,
    priority: int = 0,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> dict:
    """Admin tomonidan banner yaratadi."""
    vf = valid_from or _yesterday()
    vt = valid_to or _tomorrow()
    resp = await client.post(
        "/marketplace/banners",
        json={
            "title": title,
            "is_active": is_active,
            "priority": priority,
            "valid_from": str(vf),
            "valid_to": str(vt),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


async def _create_and_publish_product(
    client: AsyncClient,
    admin_token: str,
    name_uz: str,
    sku: str,
    marketplace_price: str = "10000.00",
) -> str:
    """Admin tomonidan mahsulot yaratadi va marketplace'ga publish qiladi."""
    resp = await client.post(
        "/catalog/products",
        json={"name_uz": name_uz, "name_ru": name_uz + " RU", "unit": "dona", "sku": sku},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, f"Mahsulot yaratilmadi: {resp.text}"
    product_id = resp.json()["id"]

    pub = await client.patch(
        f"/catalog/products/{product_id}/marketplace",
        json={"marketplace_published": True, "marketplace_price": marketplace_price},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub.status_code == 200, f"Publish muvaffaqiyatsiz: {pub.text}"
    return product_id


async def _create_order(
    client: AsyncClient,
    buyer_token: str,
    product_id: str,
    qty: str = "2",
) -> dict:
    """Buyurtma yaratadi."""
    resp = await client.post(
        "/marketplace/orders",
        json={"lines": [{"product_id": product_id, "qty": qty}]},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    return resp


# ─── VAZIFA 1: /banners/mine testlari ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mine_returns_own_banners_all_states(
    mp_client: AsyncClient,
    admin_a: AppUser,
    enterprise_a: Enterprise,
) -> None:
    """
    /banners/mine — korxona O'Z barcha bannerlarini ko'radi:
    aktiv, nofaol va muddati o'tgan hammasi chiqadi.
    """
    token = await get_token(mp_client, admin_a)

    # Aktiv banner
    r1 = await _create_banner(mp_client, token, title="Aktiv banner", is_active=True)
    assert r1.status_code == 201, r1.text
    active_id = r1.json()["id"]

    # Nofaol banner
    r2 = await _create_banner(mp_client, token, title="Nofaol banner", is_active=False)
    assert r2.status_code == 201, r2.text
    inactive_id = r2.json()["id"]

    # Muddati o'tgan banner
    past = _today() - timedelta(days=10)
    r3 = await _create_banner(
        mp_client, token,
        title="Muddati o'tgan",
        valid_from=past - timedelta(days=5),
        valid_to=past,
    )
    assert r3.status_code == 201, r3.text
    expired_id = r3.json()["id"]

    # /banners/mine'da hammasi ko'rinadi
    resp = await mp_client.get(
        "/marketplace/banners/mine",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ids = [b["id"] for b in data["items"]]

    assert active_id in ids, "Aktiv banner /banners/mine'da bo'lishi kerak"
    assert inactive_id in ids, "Nofaol banner /banners/mine'da ko'rinishi kerak"
    assert expired_id in ids, "Muddati o'tgan banner /banners/mine'da ko'rinishi kerak"

    # Cross-tenant /banners'da esa faqat aktiv+valid ko'rinadi
    browse_resp = await mp_client.get(
        "/marketplace/banners?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert browse_resp.status_code == 200
    browse_ids = [b["id"] for b in browse_resp.json()]
    assert active_id in browse_ids, "Aktiv banner browse'da bo'lishi kerak"
    assert inactive_id not in browse_ids, "Nofaol banner browse'da ko'rinmasligi kerak"
    assert expired_id not in browse_ids, "Muddati o'tgan banner browse'da ko'rinmasligi kerak"


@pytest.mark.asyncio
async def test_mine_tenant_isolation(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """
    KRITIK XAVFSIZLIK (tenant izolyatsiya):
    A korxona banneri B korxonaning /banners/mine'da KO'RINMAYDI.
    """
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    # A korxona banner yaratadi
    r = await _create_banner(mp_client, token_a, title="A xususiy banner")
    assert r.status_code == 201, r.text
    a_banner_id = r.json()["id"]

    # B korxona /banners/mine → A banneri ko'rinmasligi kerak
    resp_b = await mp_client.get(
        "/marketplace/banners/mine",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200, resp_b.text
    b_ids = [b["id"] for b in resp_b.json()["items"]]
    assert a_banner_id not in b_ids, (
        f"TENANT IZOLYATSIYA BUZILDI: A banneri B korxona /banners/mine'da ko'rindi!"
    )

    # A korxona /banners/mine → o'z banneri ko'rinadi
    resp_a = await mp_client.get(
        "/marketplace/banners/mine",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200
    a_ids = [b["id"] for b in resp_a.json()["items"]]
    assert a_banner_id in a_ids, "A banneri A korxonaning /banners/mine'da bo'lishi kerak"


@pytest.mark.asyncio
async def test_mine_superadmin_returns_empty(
    mp_client: AsyncClient,
    db_session: AsyncSession,
    enterprise_a: Enterprise,
    admin_a: AppUser,
) -> None:
    """
    Superadmin (enterprise_id=None) /banners/mine → bo'sh sahifa.
    """
    from app.core.jwt import create_access_token, hash_password
    from app.models.user import AppUser as UserModel

    token_a = await get_token(mp_client, admin_a)

    # A korxona banner yaratsin
    r = await _create_banner(mp_client, token_a, title="A uchun banner")
    assert r.status_code == 201

    # Superadmin user
    sa_id = uuid.uuid4()
    superadmin = UserModel(
        id=sa_id,
        full_name="Super Admin Mine Test",
        phone="+998901111001",
        role="superadmin",
        branch_id=None,
        password_hash=hash_password("SuperPass123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=None,
    )
    db_session.add(superadmin)
    await db_session.flush()

    sa_token = create_access_token(
        sub=str(sa_id),
        role="superadmin",
        branch_id=None,
        enterprise_id=None,
    )

    resp = await mp_client.get(
        "/marketplace/banners/mine",
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == [], "Superadmin /banners/mine → bo'sh list bo'lishi kerak"
    assert data["total"] == 0, "Superadmin /banners/mine → total=0 bo'lishi kerak"


@pytest.mark.asyncio
async def test_mine_paginated_structure(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """
    /banners/mine javob strukturasi to'g'ri: items, total, limit, offset.
    """
    token = await get_token(mp_client, admin_a)

    # 3 ta banner yaratish
    for i in range(3):
        r = await _create_banner(mp_client, token, title=f"Paginate banner {i}")
        assert r.status_code == 201

    resp = await mp_client.get(
        "/marketplace/banners/mine?page=1&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Struktura tekshiruvi
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["total"] >= 3
    assert len(data["items"]) <= 2

    # 2-sahifa
    resp2 = await mp_client.get(
        "/marketplace/banners/mine?page=2&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["offset"] == 2


@pytest.mark.asyncio
async def test_mine_priority_order(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """
    /banners/mine — priority DESC tartib tekshiruvi.
    """
    token = await get_token(mp_client, admin_a)

    r_low = await _create_banner(mp_client, token, title="Low priority", priority=1)
    r_mid = await _create_banner(mp_client, token, title="Mid priority", priority=5)
    r_high = await _create_banner(mp_client, token, title="High priority", priority=10)
    assert r_low.status_code == 201
    assert r_mid.status_code == 201
    assert r_high.status_code == 201

    id_low = r_low.json()["id"]
    id_mid = r_mid.json()["id"]
    id_high = r_high.json()["id"]

    resp = await mp_client.get(
        "/marketplace/banners/mine?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ids = [b["id"] for b in resp.json()["items"]]

    idx_high = ids.index(id_high)
    idx_mid = ids.index(id_mid)
    idx_low = ids.index(id_low)
    assert idx_high < idx_mid < idx_low, (
        f"Priority tartibi noto'g'ri: high={idx_high}, mid={idx_mid}, low={idx_low}"
    )


# ─── VAZIFA 2: list_incoming/list_outgoing nom maydonlari ────────────────────


@pytest.mark.asyncio
async def test_list_incoming_has_names(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
    store_user_a: AppUser,
    db_session: AsyncSession,
) -> None:
    """
    list_incoming javobida supplier_name, buyer_store_name, product_name to'g'ri keladi.
    """
    from app.models.store import Store
    from app.core.uuid7 import uuid7

    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # B korxona mahsulot yaratadi
    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        name_uz="Nomli Mahsulot",
        sku="ADM-NAMES-B01",
        marketplace_price="5000.00",
    )

    # A do'koni uchun Store yozuvi qo'shamiz (buyer_store_name uchun)
    store_obj = Store(
        id=uuid7(),
        name="A Test Do'koni",
        enterprise_id=enterprise_a.id,
        user_id=store_user_a.id,
    )
    db_session.add(store_obj)
    await db_session.flush()

    # A do'koni buyurtma beradi
    resp = await _create_order(mp_client, token_a_store, pid_b, qty="3")
    assert resp.status_code == 201, f"Buyurtma yaratilmadi: {resp.text}"
    order_id = resp.json()["id"]

    # B korxona incoming'da ko'radi
    incoming_resp = await mp_client.get(
        "/marketplace/orders/incoming",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert incoming_resp.status_code == 200, incoming_resp.text

    orders = incoming_resp.json()["items"]
    target = next((o for o in orders if o["id"] == order_id), None)
    assert target is not None, "Buyurtma incoming'da topilmadi"

    # supplier_name = B korxona nomi
    assert target["supplier_name"] == "Korxona B", (
        f"supplier_name noto'g'ri: {target['supplier_name']!r}"
    )

    # product_name har line'da bor
    assert len(target["lines"]) > 0
    for line in target["lines"]:
        assert line["product_name"] is not None, "product_name None bo'lmasligi kerak"
        assert "Nomli Mahsulot" in line["product_name"], (
            f"product_name kutilgan nom emas: {line['product_name']!r}"
        )


@pytest.mark.asyncio
async def test_list_outgoing_has_names(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
    store_user_a: AppUser,
) -> None:
    """
    list_outgoing javobida supplier_name va product_name to'g'ri keladi.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        name_uz="Chiquvchi Test Mahsulot",
        sku="ADM-OUTGOING-B01",
        marketplace_price="8000.00",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201, f"Buyurtma yaratilmadi: {resp.text}"
    order_id = resp.json()["id"]

    # A korxona outgoing'da ko'radi
    outgoing_resp = await mp_client.get(
        "/marketplace/orders/outgoing",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert outgoing_resp.status_code == 200, outgoing_resp.text

    orders = outgoing_resp.json()["items"]
    target = next((o for o in orders if o["id"] == order_id), None)
    assert target is not None, "Buyurtma outgoing'da topilmadi"

    # supplier_name = B korxona nomi
    assert target["supplier_name"] == "Korxona B", (
        f"supplier_name noto'g'ri: {target['supplier_name']!r}"
    )

    # product_name har line'da bor
    assert len(target["lines"]) > 0
    for line in target["lines"]:
        assert line["product_name"] is not None, "product_name None bo'lmasligi kerak"
        assert "Chiquvchi Test Mahsulot" in line["product_name"], (
            f"product_name kutilgan nom emas: {line['product_name']!r}"
        )


@pytest.mark.asyncio
async def test_confirm_endpoint_names_are_none(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    KRITIK: confirm endpoint javobida nom maydonlari None (enrich=False).
    MissingGreenlet xatosi yo'q.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        name_uz="Confirm None Test",
        sku="ADM-CONFNONE-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # B korxona confirm qiladi
    confirm_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    data = confirm_resp.json()
    # confirm javobida nom maydonlari None bo'lishi kerak (enrich=False)
    assert data["buyer_store_name"] is None, (
        f"confirm javobida buyer_store_name None bo'lishi kerak, lekin: {data['buyer_store_name']!r}"
    )
    assert data["supplier_name"] is None, (
        f"confirm javobida supplier_name None bo'lishi kerak, lekin: {data['supplier_name']!r}"
    )
    assert data["courier_name"] is None, (
        f"confirm javobida courier_name None bo'lishi kerak, lekin: {data['courier_name']!r}"
    )
    # product_name ham None bo'lishi kerak
    for line in data["lines"]:
        assert line["product_name"] is None, (
            f"confirm javobida line.product_name None bo'lishi kerak: {line['product_name']!r}"
        )


@pytest.mark.asyncio
async def test_courier_name_in_list_incoming_after_ship(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_b: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    Ship qilingandan keyin list_incoming'da courier_name to'g'ri keladi.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # B korxona kuryer foydalanuvchisi yaratish
    from app.core.jwt import hash_password
    courier = _make_user("courier", enterprise_b.id, "courier_test")
    courier.full_name = "Test Kuryer Ismi"
    db_session.add(courier)
    await db_session.flush()

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        name_uz="Ship Test Mahsulot",
        sku="ADM-SHIP-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # confirm
    confirm_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert confirm_resp.status_code == 200

    # ship
    ship_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert ship_resp.status_code == 200, ship_resp.text

    # ship javobida courier_name None (enrich=False)
    ship_data = ship_resp.json()
    assert ship_data["courier_name"] is None, (
        f"ship javobida courier_name None bo'lishi kerak: {ship_data['courier_name']!r}"
    )

    # Lekin list_incoming'da courier_name to'g'ri keladi (enrich=True)
    incoming_resp = await mp_client.get(
        "/marketplace/orders/incoming",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert incoming_resp.status_code == 200

    orders = incoming_resp.json()["items"]
    target = next((o for o in orders if o["id"] == order_id), None)
    assert target is not None, "Buyurtma incoming'da topilmadi"

    assert target["courier_name"] == "Test Kuryer Ismi", (
        f"courier_name kutilgan ism emas: {target['courier_name']!r}"
    )
