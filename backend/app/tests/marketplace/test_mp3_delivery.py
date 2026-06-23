"""
Marketplace MP3 testlari — yetkazish → do'kon qabul → POS inventar.

Qamrov:
  1. To'liq oqim: confirm → ship(courier) → deliver(proof) → accept → StoreInventory.
  2. Noto'g'ri holat o'tishlari rad (masalan, accept delivered emas holat).
  3. ship: faqat supplier korxona bajaradi.
  4. deliver: faqat tayinlangan kuryer bajaradi.
  5. accept: faqat buyer do'kon/admin bajaradi.
  6. StoreInventory tenant-scoped (boshqa korxona ko'rmaydi).
  7. sale_price = cost * (1 + markup/100) to'g'ri hisoblanadi.
  8. expiry_date StoreInventoryda saqlanadi.
  9. Supplier accept qila olmaydi → 403.
  10. deliver tayinlanmagan kuryer tomonidan → 403.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import hash_password
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.store import Store
from app.models.user import AppUser
from app.tests.marketplace.conftest import TEST_PASSWORD, TEST_ENTERPRISE_B_UUID, get_token
from app.tests.conftest import TEST_ENTERPRISE_UUID


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


def _make_user(role: str, enterprise_id: uuid.UUID, suffix: str = "") -> AppUser:
    """Sinov foydalanuvchisi yaratadi."""
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix + "mp3"))
    return AppUser(
        id=user_id,
        full_name=f"MP3 {role.capitalize()} {suffix}",
        phone=f"+99892{str(phone_hash)[:7]}",
        role=role,
        branch_id=None,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=enterprise_id,
    )


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def courier_b(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Korxona B kuryeri."""
    user = _make_user("courier", enterprise_b.id, "courierB")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def courier_b2(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Korxona B ikkinchi kuryeri (tayinlanmagan kuryer testi uchun)."""
    user = _make_user("courier", enterprise_b.id, "courierB2")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def store_a(
    db_session: AsyncSession,
    enterprise_a: Enterprise,
    store_user_a: AppUser,
) -> Store:
    """Korxona A do'koni."""
    store = Store(
        id=uuid.uuid4(),
        name="Do'kon A",
        enterprise_id=enterprise_a.id,
        user_id=store_user_a.id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()
    return store


# ─── Yordamchi HTTP funksiyalar ───────────────────────────────────────────────


async def _create_and_confirm_order(
    client: AsyncClient,
    admin_b_token: str,
    store_a_token: str,
    store_a_id: str,
    sku: str = "MP3-TEST-001",
    marketplace_price: str = "20000.00",
) -> tuple[str, str]:
    """
    Mahsulot yaratadi, publish qiladi, buyurtma beradi va tasdiqlaydi.
    Returns: (order_id, product_id)
    """
    # B korxona mahsulot yaratadi
    create_resp = await client.post(
        "/catalog/products",
        json={"name_uz": "MP3 mahsulot", "name_ru": "MP3 товар", "unit": "dona", "sku": sku},
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert create_resp.status_code == 201, f"Mahsulot yaratilmadi: {create_resp.text}"
    product_id = create_resp.json()["id"]

    # Publish
    pub = await client.patch(
        f"/catalog/products/{product_id}/marketplace",
        json={"marketplace_published": True, "marketplace_price": marketplace_price},
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert pub.status_code == 200

    # A korxona do'koni buyurtma beradi
    order_resp = await client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": product_id, "qty": "5"}],
            "store_id": store_a_id,
        },
        headers={"Authorization": f"Bearer {store_a_token}"},
    )
    assert order_resp.status_code == 201, f"Buyurtma yaratilmadi: {order_resp.text}"
    order_id = order_resp.json()["id"]

    # B korxona tasdiqlaydi
    confirm = await client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert confirm.status_code == 200, f"Confirm muvaffaqiyatsiz: {confirm.text}"
    assert confirm.json()["status"] == "confirmed"

    return order_id, product_id


# ─── 1. To'liq oqim testi ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_delivery_flow(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """
    To'liq oqim:
    confirm → ship(courier_b) → deliver(proof_url) → accept(markup=20%) →
    StoreInventory yozuvi: cost=20000, markup=20, sale=24000, expiry saqlangan.
    """
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)
    token_courier_b = await get_token(mp_client, courier_b)

    order_id, product_id = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-FULL-001",
        marketplace_price="20000.00",
    )

    # ── ship: supplier B admin kuryer tayinlaydi ────────────────────────────
    ship_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert ship_resp.status_code == 200, f"Ship muvaffaqiyatsiz: {ship_resp.text}"
    ship_data = ship_resp.json()
    assert ship_data["status"] == "delivering"
    assert ship_data["courier_id"] == str(courier_b.id)

    # ── deliver: kuryer B yetkazdi + proof_photo ────────────────────────────
    proof_url = "https://storage.example.com/proof/order-abc.jpg"
    deliver_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": proof_url},
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert deliver_resp.status_code == 200, f"Deliver muvaffaqiyatsiz: {deliver_resp.text}"
    deliver_data = deliver_resp.json()
    assert deliver_data["status"] == "delivered"
    assert deliver_data["proof_photo_url"] == proof_url
    assert deliver_data["delivered_at"] is not None

    # ── accept: A korxona admin qabul qiladi (markup=20%, expiry=2027-12-31) ─
    expiry_str = "2027-12-31"
    # line_id ni olish kerak
    order_detail = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert order_detail.status_code == 200
    lines = order_detail.json()["lines"]
    assert len(lines) == 1
    line_id = lines[0]["id"]

    accept_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={
            "store_id": str(store_a.id),
            "lines": [
                {
                    "line_id": line_id,
                    "expiry_date": expiry_str,
                    "markup_percent": "20.00",
                }
            ],
        },
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert accept_resp.status_code == 200, f"Accept muvaffaqiyatsiz: {accept_resp.text}"
    accept_data = accept_resp.json()
    assert accept_data["status"] == "accepted"
    assert accept_data["accepted_at"] is not None

    # ── inventar tekshiruvi ─────────────────────────────────────────────────
    inv_resp = await mp_client.get(
        f"/marketplace/inventory?store_id={store_a.id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert inv_resp.status_code == 200, f"Inventar so'rovi muvaffaqiyatsiz: {inv_resp.text}"
    inv_data = inv_resp.json()
    assert inv_data["total"] >= 1, "Inventar yozuvi yaratilishi kerak"

    inv_item = inv_data["items"][0]
    # cost_price = buyurtma unit_price (20000)
    assert Decimal(inv_item["cost_price"]) == Decimal("20000.00"), (
        f"cost_price noto'g'ri: {inv_item['cost_price']}"
    )
    # sale_price = 20000 * (1 + 20/100) = 24000
    assert Decimal(inv_item["sale_price"]) == Decimal("24000.00"), (
        f"sale_price noto'g'ri: {inv_item['sale_price']}"
    )
    assert inv_item["markup_percent"] == "20.0000"
    assert inv_item["expiry_date"] == expiry_str
    assert inv_item["status"] == "active"
    assert inv_item["product_id"] == product_id
    assert inv_item["store_id"] == str(store_a.id)
    assert inv_item["enterprise_id"] == str(enterprise_a.id)
    assert inv_item["source_order_id"] == order_id


# ─── 2. Noto'g'ri holat o'tishi testlari ─────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_accept_without_deliver(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """delivered emas buyurtmani accept qilib bo'lmaydi → 422."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-NOACCEPT-001",
    )

    # ship qilmasdan (confirmed holat) accept qilmoqchi → 422
    accept_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={"store_id": str(store_a.id), "lines": []},
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert accept_resp.status_code == 422, (
        f"confirmed holat accept bo'lmasligi kerak: {accept_resp.text}"
    )


@pytest.mark.asyncio
async def test_cannot_deliver_without_ship(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """delivering emas buyurtmani deliver qilib bo'lmaydi → 422."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b = await get_token(mp_client, courier_b)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-NODELIVER-001",
    )

    # confirmed holat — deliver → 422
    deliver_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert deliver_resp.status_code in (403, 422), (
        f"confirmed holat deliver bo'lmasligi kerak: {deliver_resp.text}"
    )


# ─── 3. Access nazorati testlari ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_buyer_cannot_ship(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """Buyer korxona ship qila olmaydi → 403."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-BUYERSHIP-001",
    )

    # A korxona (buyer) ship qilmoqchi → 403
    ship_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert ship_resp.status_code == 403, (
        f"Buyer ship qila olmaydi (xavfsizlik buzildi!): {ship_resp.text}"
    )


@pytest.mark.asyncio
async def test_wrong_courier_cannot_deliver(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    courier_b2: AppUser,
    store_a: Store,
) -> None:
    """Tayinlanmagan kuryer deliver qila olmaydi → 403."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b2 = await get_token(mp_client, courier_b2)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-WRONGCOURIER-001",
    )

    # ship: courier_b tayinlanadi
    ship_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert ship_resp.status_code == 200

    # courier_b2 (tayinlanmagan) deliver qilmoqchi → 403
    deliver_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier_b2}"},
    )
    assert deliver_resp.status_code == 403, (
        f"Tayinlanmagan kuryer deliver qila olmaydi (xavfsizlik buzildi!): {deliver_resp.text}"
    )


@pytest.mark.asyncio
async def test_supplier_cannot_accept(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """Supplier korxona accept qila olmaydi → 403."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b = await get_token(mp_client, courier_b)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-SUPPACCEPT-001",
    )

    # ship
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )

    # deliver
    token_courier = await get_token(mp_client, courier_b)
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier}"},
    )

    # B korxona (supplier) accept qilmoqchi → 403
    accept_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={"store_id": str(store_a.id), "lines": []},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert accept_resp.status_code == 403, (
        f"Supplier accept qila olmaydi (xavfsizlik buzildi!): {accept_resp.text}"
    )


# ─── 4. Tenant izolyatsiyasi — inventar ──────────────────────────────────────


@pytest.mark.asyncio
async def test_inventory_tenant_isolated(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
    enterprise_b: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    KRITIK XAVFSIZLIK:
    A korxona inventarini B korxona KO'RA OLMAYDI.
    """
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)
    token_courier = await get_token(mp_client, courier_b)

    order_id, product_id = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-ISOCHECK-001",
        marketplace_price="5000.00",
    )

    # ship → deliver → accept
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier}"},
    )

    order_detail = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    line_id = order_detail.json()["lines"][0]["id"]

    await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={
            "store_id": str(store_a.id),
            "lines": [{"line_id": line_id, "expiry_date": None, "markup_percent": "0"}],
        },
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )

    # A korxona inventarini ko'radi — yozuv bor
    inv_a = await mp_client.get(
        "/marketplace/inventory",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert inv_a.status_code == 200
    assert inv_a.json()["total"] >= 1

    # B korxona (supplier) inventarni ko'radi — A inventari ko'rinmasligi kerak
    inv_b = await mp_client.get(
        "/marketplace/inventory",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert inv_b.status_code == 200
    b_item_ids = [item["id"] for item in inv_b.json()["items"]]
    a_item_ids = [item["id"] for item in inv_a.json()["items"]]
    for a_id in a_item_ids:
        assert a_id not in b_item_ids, (
            f"B korxona A inventarini ko'rmasligi kerak (izolyatsiya buzildi!): {a_id}"
        )


# ─── 5. sale_price hisoblash to'g'riligi ─────────────────────────────────────


@pytest.mark.asyncio
async def test_sale_price_calculation(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """
    sale_price = cost_price * (1 + markup_percent/100) to'g'ri hisoblanadi.
    cost=15000, markup=25% → sale=18750.00
    """
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)
    token_courier = await get_token(mp_client, courier_b)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-SALEPRICE-001",
        marketplace_price="15000.00",
    )

    await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier}"},
    )

    order_detail = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    line_id = order_detail.json()["lines"][0]["id"]

    accept_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={
            "store_id": str(store_a.id),
            "lines": [
                {
                    "line_id": line_id,
                    "expiry_date": "2028-06-01",
                    "markup_percent": "25.00",
                }
            ],
        },
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert accept_resp.status_code == 200

    inv_resp = await mp_client.get(
        "/marketplace/inventory",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert inv_resp.status_code == 200
    items = inv_resp.json()["items"]
    assert len(items) >= 1

    # Oxirgi yozuv
    item = next((i for i in items if i["source_order_id"] == order_id), None)
    assert item is not None, "Inventar yozuvi topilmadi"

    assert Decimal(item["cost_price"]) == Decimal("15000.00")
    # 15000 * 1.25 = 18750.00
    assert Decimal(item["sale_price"]) == Decimal("18750.00"), (
        f"sale_price noto'g'ri: {item['sale_price']} (kutilmoqda 18750.00)"
    )
    assert item["expiry_date"] == "2028-06-01"


# ─── 6. markup=0 bo'lganda sale_price = cost_price ───────────────────────────


@pytest.mark.asyncio
async def test_zero_markup_sale_equals_cost(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """markup=0 bo'lganda sale_price = cost_price."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)
    token_courier = await get_token(mp_client, courier_b)

    order_id, _ = await _create_and_confirm_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        sku="MP3-ZEROM-001",
        marketplace_price="8000.00",
    )

    await mp_client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": str(courier_b.id)},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    await mp_client.patch(
        f"/marketplace/orders/{order_id}/deliver",
        json={"proof_photo_url": None},
        headers={"Authorization": f"Bearer {token_courier}"},
    )

    order_detail = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    line_id = order_detail.json()["lines"][0]["id"]

    await mp_client.patch(
        f"/marketplace/orders/{order_id}/accept",
        json={
            "store_id": str(store_a.id),
            "lines": [
                {"line_id": line_id, "expiry_date": None, "markup_percent": "0"},
            ],
        },
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )

    inv_resp = await mp_client.get(
        "/marketplace/inventory",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    items = inv_resp.json()["items"]
    item = next((i for i in items if i["source_order_id"] == order_id), None)
    assert item is not None

    assert Decimal(item["cost_price"]) == Decimal("8000.00")
    assert Decimal(item["sale_price"]) == Decimal("8000.00"), (
        f"markup=0 bo'lganda sale=cost bo'lishi kerak: {item['sale_price']}"
    )
