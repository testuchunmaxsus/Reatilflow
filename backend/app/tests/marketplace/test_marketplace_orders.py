"""
Marketplace buyurtma testlari — MP2.

Qamrov (xavfsizlik-kritik):
  1. do'kon (korxona A) supplier (korxona B) published mahsulotini buyurtma qiladi
     → MarketplaceOrder (buyer=A, supplier=B, pending).
  2. B korxona admini incoming'da ko'radi → confirm → confirmed.
  3. A korxona outgoing'da ko'radi.
  4. Uchinchi korxona C bu buyurtmani KO'RMAYDI (get → 404, incoming/outgoing'da yo'q).
  5. A korxona buyurtmani confirm qila OLMAYDI (faqat supplier B).
  6. published EMAS mahsulotni buyurtma → 404.
  7. Server narx: buyer narx bermaydi, server marketplace_price ishlatadi.
  8. Supplier korxona kiruvchi buyurtmani rad etadi (reject).
  9. Aralash supplier mahsulotlari → 422.
  10. Idempotentlik: bir xil client_uuid → bitta buyurtma.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product
from app.models.enterprise import Enterprise
from app.models.user import AppUser
from app.tests.marketplace.conftest import TEST_ENTERPRISE_B_UUID, get_token

# ─── Test uchun uchinchi korxona UUID ────────────────────────────────────────

TEST_ENTERPRISE_C_UUID = uuid.UUID("00000000-0000-7000-8000-000000000099")
# Har test uchun alohida UUID ishlatiladi (fixture'lar orqali)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_user(role: str, enterprise_id: uuid.UUID, suffix: str = "") -> AppUser:
    """Sinov foydalanuvchisi yaratadi."""
    from app.core.jwt import hash_password
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix))
    return AppUser(
        id=user_id,
        full_name=f"Test {role.capitalize()} {suffix}",
        phone=f"+99891{str(phone_hash)[:7]}",
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


@pytest.fixture
async def enterprise_c(db_session: AsyncSession) -> Enterprise:
    """Uchinchi korxona — kirish tekshiruvi uchun. Har test uchun yangi random UUID."""
    from app.models.enterprise import ALL_MODULE_KEYS
    ent = Enterprise(
        id=uuid.uuid4(),  # Har test uchun yangi UUID — UNIQUE conflict yo'q
        name="Korxona C",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def admin_c(db_session: AsyncSession, enterprise_c: Enterprise) -> AppUser:
    """Korxona C administratori."""
    user = _make_user("administrator", enterprise_c.id, "C")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def store_user_b(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Korxona B do'kon foydalanuvchisi."""
    user = _make_user("store", enterprise_b.id, "storeB")
    db_session.add(user)
    await db_session.flush()
    return user


# ─── Yordamchilar ─────────────────────────────────────────────────────────────


async def _create_and_publish_product(
    client: AsyncClient,
    admin_token: str,
    name_uz: str,
    name_ru: str,
    sku: str,
    marketplace_price: str = "10000.00",
) -> str:
    """Admin tomonidan mahsulot yaratadi va marketplace'ga publish qiladi."""
    resp = await client.post(
        "/catalog/products",
        json={"name_uz": name_uz, "name_ru": name_ru, "unit": "dona", "sku": sku},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, f"Mahsulot yaratilmadi: {resp.text}"
    product_id = resp.json()["id"]

    # Publish
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
    qty: str = "5",
    client_uuid: str | None = None,
) -> dict:
    """Buyurtma yaratadi."""
    body: dict = {
        "lines": [{"product_id": product_id, "qty": qty}],
    }
    if client_uuid:
        body["client_uuid"] = client_uuid
    resp = await client.post(
        "/marketplace/orders",
        json=body,
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    return resp


# ─── 1. Asosiy oqim: buyurtma → tasdiqlash ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_and_confirm(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """
    Asosiy oqim:
      A korxona do'koni → B korxona published mahsulotini buyurtma qiladi (pending)
      → B korxona admini incoming'da ko'radi → confirm → confirmed
      → A korxona outgoing'da ko'radi.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # B korxona mahsulot yaratadi va publish qiladi
    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "B mahsulot", "B товар", "MP2-BASIC-B01",
        marketplace_price="15000.00",
    )

    # A korxona do'koni buyurtma beradi
    resp = await _create_order(mp_client, token_a_store, pid_b, qty="3")
    assert resp.status_code == 201, f"Buyurtma yaratilmadi: {resp.text}"
    order = resp.json()
    order_id = order["id"]

    assert order["status"] == "pending"
    assert order["buyer_enterprise_id"] == str(enterprise_a.id)
    assert order["supplier_enterprise_id"] == str(enterprise_b.id)
    # Server narx: 15000 * 3 = 45000
    assert order["total_amount"] == "45000.00"
    assert len(order["lines"]) == 1
    assert order["lines"][0]["unit_price"] == "15000.00"

    # B korxona incoming'da ko'radi
    incoming = await mp_client.get(
        "/marketplace/orders/incoming",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert incoming.status_code == 200
    incoming_ids = [o["id"] for o in incoming.json()["items"]]
    assert order_id in incoming_ids, "B korxona incoming'da buyurtmani ko'rishi kerak"

    # A korxona outgoing'da ko'radi
    outgoing = await mp_client.get(
        "/marketplace/orders/outgoing",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert outgoing.status_code == 200
    outgoing_ids = [o["id"] for o in outgoing.json()["items"]]
    assert order_id in outgoing_ids, "A korxona outgoing'da buyurtmani ko'rishi kerak"

    # B korxona tasdiqlaydi
    confirm_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert confirm_resp.status_code == 200, f"Confirm muvaffaqiyatsiz: {confirm_resp.text}"
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "confirmed"


# ─── 2. Reject oqimi ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_and_reject(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    B korxona admini pending buyurtmani rad etadi.
    reject_reason saqlangan bo'lishi kerak.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "B reject test", "B реджект", "MP2-REJECT-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="2")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # Reject
    reject_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/reject",
        json={"reason": "Mahsulot stokda yo'q"},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert reject_resp.status_code == 200, f"Reject muvaffaqiyatsiz: {reject_resp.text}"
    rejected = reject_resp.json()
    assert rejected["status"] == "rejected"
    assert rejected["reject_reason"] == "Mahsulot stokda yo'q"


# ─── 3. Uchinchi korxona izolyatsiyasi (kritik xavfsizlik) ───────────────────


@pytest.mark.asyncio
async def test_third_enterprise_cannot_see_order(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    admin_c: AppUser,
    store_user_a: AppUser,
    enterprise_c: Enterprise,
) -> None:
    """
    KRITIK XAVFSIZLIK:
    Uchinchi korxona C buyurtmani KO'RA OLMAYDI:
      - GET /marketplace/orders/{id} → 404
      - GET /marketplace/orders/incoming → bo'sh (buyurtma yo'q)
      - GET /marketplace/orders/outgoing → bo'sh (buyurtma yo'q)
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)
    token_c_admin = await get_token(mp_client, admin_c)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "C test product", "C тест товар", "MP2-C-ISOL-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # C korxona GET → 404
    get_resp = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_c_admin}"},
    )
    assert get_resp.status_code == 404, (
        f"C korxona buyurtmani ko'ra olmaydi (izolyatsiya buzildi!): {get_resp.text}"
    )

    # C korxona incoming → bo'sh (buyurtma yo'q)
    inc_resp = await mp_client.get(
        "/marketplace/orders/incoming",
        headers={"Authorization": f"Bearer {token_c_admin}"},
    )
    assert inc_resp.status_code == 200
    c_incoming_ids = [o["id"] for o in inc_resp.json()["items"]]
    assert order_id not in c_incoming_ids, (
        f"Uchinchi korxona C incoming'da buyurtmani ko'rmasligi kerak!"
    )

    # C korxona outgoing → bo'sh
    out_resp = await mp_client.get(
        "/marketplace/orders/outgoing",
        headers={"Authorization": f"Bearer {token_c_admin}"},
    )
    assert out_resp.status_code == 200
    c_outgoing_ids = [o["id"] for o in out_resp.json()["items"]]
    assert order_id not in c_outgoing_ids, (
        f"Uchinchi korxona C outgoing'da buyurtmani ko'rmasligi kerak!"
    )


# ─── 4. Buyer korxona confirm qila olmaydi (kritik xavfsizlik) ───────────────


@pytest.mark.asyncio
async def test_buyer_cannot_confirm_own_order(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    KRITIK XAVFSIZLIK:
    A korxona admini (buyer) o'z buyurtmasini confirm qila OLMAYDI → 403.
    Faqat supplier B tasdiqlaydi.
    """
    token_a_admin = await get_token(mp_client, admin_a)
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Buyer confirm test", "Buyer конфирм", "MP2-BUYERCONF-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # A korxona admini confirm qilishga urinadi → 403
    conf_resp = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert conf_resp.status_code == 403, (
        f"Buyer A korxona confirm qila olmaydi (xavfsizlik buzildi!): {conf_resp.text}"
    )


# ─── 5. Published emas mahsulotni buyurtma → 404 ─────────────────────────────


@pytest.mark.asyncio
async def test_order_unpublished_product_returns_404(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """Published EMAS B mahsulotini A korxona buyurtma qilmoqchi → 404."""
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # B mahsulot yaratadi, lekin publish QILMAYDI
    create_resp = await mp_client.post(
        "/catalog/products",
        json={
            "name_uz": "B yashirin mahsulot",
            "name_ru": "B скрытый товар",
            "unit": "dona",
            "sku": "MP2-HIDDEN-B01",
        },
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert create_resp.status_code == 201
    hidden_pid = create_resp.json()["id"]

    # A buyurtma bermoqchi → 404 (published emas)
    order_resp = await _create_order(mp_client, token_a_store, hidden_pid, qty="1")
    assert order_resp.status_code == 404, (
        f"Published emas mahsulot buyurtmasi 404 qaytarishi kerak: {order_resp.text}"
    )
    assert order_resp.json()["message_key"] == "marketplace.product_not_found"


# ─── 6. Server narx — buyer narx bera olmaydi ────────────────────────────────


@pytest.mark.asyncio
async def test_server_authoritative_price(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    Server narx: buyurtma beruvchi narx ko'rsatmaydi — server marketplace_price ishlatadi.
    Schema darajasida unit_price maydon yo'q; total server tomonida hisoblanadi.
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # marketplace_price = 7500
    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Server narx test", "Сервер цена", "MP2-PRICE-B01",
        marketplace_price="7500.00",
    )

    # Buyurtma berish — faqat product_id va qty
    resp = await _create_order(mp_client, token_a_store, pid_b, qty="4")
    assert resp.status_code == 201, f"Buyurtma yaratilmadi: {resp.text}"
    order = resp.json()

    # unit_price server tomonida 7500 qilingan
    assert order["lines"][0]["unit_price"] == "7500.00"
    # total = 7500 * 4 = 30000
    assert order["total_amount"] == "30000.00"


# ─── 7. Aralash supplier mahsulotlari → 422 ──────────────────────────────────


@pytest.mark.asyncio
async def test_mixed_suppliers_returns_422(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    Bitta buyurtmada ikki xil supplierdan mahsulot → 422.
    A korxona o'z mahsulotini va B mahsulotini bir buyurtmada bermoqchi → 422.
    """
    token_a_admin = await get_token(mp_client, admin_a)
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    # A korxona o'z mahsulotini publish qiladi
    pid_a = await _create_and_publish_product(
        mp_client, token_a_admin,
        "A supplier mahsulot", "A поставщик", "MP2-MIX-A01",
    )

    # B korxona mahsulot publish qiladi
    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "B supplier mahsulot", "B поставщик", "MP2-MIX-B01",
    )

    # A do'koni ikkala mahsulotni bir buyurtmada → 422
    resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [
                {"product_id": pid_a, "qty": "1"},
                {"product_id": pid_b, "qty": "1"},
            ]
        },
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert resp.status_code == 422, (
        f"Aralash supplier buyurtmasi 422 qaytarishi kerak: {resp.text}"
    )
    assert resp.json()["message_key"] == "marketplace.order_mixed_suppliers"


# ─── 8. Idempotentlik — bir xil client_uuid → bitta buyurtma ─────────────────


@pytest.mark.asyncio
async def test_idempotent_order_creation(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    Bir xil client_uuid bilan qayta yuborish → bitta buyurtma (dublikat emas).
    """
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Idempotent test", "Идемпотент", "MP2-IDEM-B01",
    )

    idem_uuid = str(uuid.uuid4())

    # Birinchi so'rov
    resp1 = await _create_order(mp_client, token_a_store, pid_b, qty="1", client_uuid=idem_uuid)
    assert resp1.status_code == 201
    order_id_1 = resp1.json()["id"]

    # Ikkinchi so'rov (bir xil client_uuid)
    resp2 = await _create_order(mp_client, token_a_store, pid_b, qty="1", client_uuid=idem_uuid)
    assert resp2.status_code == 201
    order_id_2 = resp2.json()["id"]

    # Bir xil buyurtma ID qaytishi kerak
    assert order_id_1 == order_id_2, (
        f"Idempotentlik buzildi: ikkita buyurtma yaratildi ({order_id_1} != {order_id_2})"
    )


# ─── 9. Confirmed buyurtmani qayta confirm qila olmaydi ──────────────────────


@pytest.mark.asyncio
async def test_cannot_confirm_already_confirmed(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """Allaqachon confirmed buyurtmani qayta confirm → 422."""
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Double confirm", "Дабл конфирм", "MP2-DBLCONF-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # Birinchi confirm
    c1 = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert c1.status_code == 200

    # Ikkinchi confirm → 422
    c2 = await mp_client.patch(
        f"/marketplace/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert c2.status_code == 422, f"Qayta confirm 422 bo'lishi kerak: {c2.text}"


# ─── 10. GET /marketplace/orders/{id}: buyer va supplier ham ko'ra oladi ─────


@pytest.mark.asyncio
async def test_both_buyer_and_supplier_can_get_order(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """Buyer (A) va supplier (B) ikkalasi ham GET /marketplace/orders/{id} ko'ra oladi."""
    token_a_store = await get_token(mp_client, store_user_a)
    token_a_admin = await get_token(mp_client, admin_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Mutual get test", "Мьючуал гет", "MP2-MUTGET-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="2")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # A (buyer admin) ko'ra oladi
    get_a = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_a_admin}"},
    )
    assert get_a.status_code == 200, f"Buyer A admin ko'ra olmadi: {get_a.text}"

    # B (supplier admin) ko'ra oladi
    get_b = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert get_b.status_code == 200, f"Supplier B admin ko'ra olmadi: {get_b.text}"


# ─── 11. Holat filtri — incoming status filter ishlaydi ─────────────────────


@pytest.mark.asyncio
async def test_incoming_status_filter(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """supplier incoming'da status filtri ishlaydi."""
    token_a_store = await get_token(mp_client, store_user_a)
    token_b_admin = await get_token(mp_client, admin_b)

    pid_b = await _create_and_publish_product(
        mp_client, token_b_admin,
        "Status filter", "Статус фильтр", "MP2-STFILT-B01",
    )

    resp = await _create_order(mp_client, token_a_store, pid_b, qty="1")
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # pending filtri → topiladi
    pending_resp = await mp_client.get(
        "/marketplace/orders/incoming?status=pending",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert pending_resp.status_code == 200
    pending_ids = [o["id"] for o in pending_resp.json()["items"]]
    assert order_id in pending_ids

    # confirmed filtri → topilmaydi (hali pending)
    confirmed_resp = await mp_client.get(
        "/marketplace/orders/incoming?status=confirmed",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert confirmed_resp.status_code == 200
    confirmed_ids = [o["id"] for o in confirmed_resp.json()["items"]]
    assert order_id not in confirmed_ids
