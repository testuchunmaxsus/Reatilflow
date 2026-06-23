"""
Marketplace V2C testlari — kuryer marketplace yetkazish oqimi.

Qamrov:
  1. Kuryer o'z delivering buyurtmalarini ko'radi (GET /marketplace/orders/deliveries).
  2. Boshqa kuryer yetkazishlarini ko'rmaydi (tenant izolyatsiya emas, ID izolyatsiya).
  3. Kuryer proof-photo yuklaydi → buyurtma delivered holatiga o'tadi.
  4. Boshqa kuryer proof-photo yuklay olmaydi → 403.
  5. delivering emas buyurtma deliveries ro'yxatiga kirmaydi (confirmed, delivered).
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.core.storage import FakeStorage, get_storage
from app.main import app
from app.models.base import Base
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.store import Store
from app.models.user import AppUser
from app.tests.marketplace.conftest import TEST_PASSWORD, get_token
from app.tests.conftest import TEST_ENTERPRISE_UUID


# ─── Storage-aware klient ─────────────────────────────────────────────────────
# mp_client (conftest) storage'ni override qilmaydi.
# Proof-photo testlari uchun FakeStorage bilan klient kerak.


@pytest.fixture
async def storage_client(
    db_session: AsyncSession,
):
    """FakeStorage bilan AsyncClient — proof-photo testlari uchun."""
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    fake_storage = FakeStorage()

    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis
    app.dependency_overrides[get_storage] = lambda: fake_storage

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await fake_redis.aclose()


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _make_user(role: str, enterprise_id: uuid.UUID, suffix: str = "") -> AppUser:
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix + "v2c"))
    return AppUser(
        id=user_id,
        full_name=f"V2C {role.capitalize()} {suffix}",
        phone=f"+99893{str(phone_hash)[:7]}",
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
    """Korxona B kuryeri (v2c)."""
    user = _make_user("courier", enterprise_b.id, "v2c_courier_b")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def courier_b2(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Korxona B ikkinchi kuryeri (boshqa kuryer testi uchun)."""
    user = _make_user("courier", enterprise_b.id, "v2c_courier_b2")
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
        name="V2C Do'kon A",
        enterprise_id=enterprise_a.id,
        user_id=store_user_a.id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()
    return store


# ─── Yordamchi HTTP funksiya ──────────────────────────────────────────────────


async def _create_and_ship_order(
    client: AsyncClient,
    admin_b_token: str,
    store_a_token: str,
    store_a_id: str,
    courier_id: str,
    sku: str = "V2C-TEST-001",
    marketplace_price: str = "15000.00",
) -> str:
    """
    Mahsulot yaratadi, publish qiladi, buyurtma beradi, tasdiqlaydi, ship qiladi.
    Returns: order_id
    """
    # B korxona mahsulot yaratadi
    create_resp = await client.post(
        "/catalog/products",
        json={"name_uz": "V2C mahsulot", "name_ru": "V2C товар", "unit": "dona", "sku": sku},
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

    # A do'koni buyurtma beradi
    order_resp = await client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": product_id, "qty": "3"}],
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
    assert confirm.status_code == 200

    # B korxona ship qiladi (kuryer tayinlaydi)
    ship = await client.patch(
        f"/marketplace/orders/{order_id}/ship",
        json={"courier_id": courier_id},
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert ship.status_code == 200, f"Ship muvaffaqiyatsiz: {ship.text}"
    assert ship.json()["status"] == "delivering"

    return order_id


# ─── 1. Kuryer o'z yetkazishlarini ko'radi ───────────────────────────────────


@pytest.mark.asyncio
async def test_courier_sees_own_deliveries(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """Kuryer GET /marketplace/orders/deliveries — o'ziga tayinlangan buyurtmalar."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b = await get_token(mp_client, courier_b)

    order_id = await _create_and_ship_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        courier_id=str(courier_b.id),
        sku="V2C-LIST-001",
    )

    # Kuryer o'z yetkazishlarini ko'radi
    resp = await mp_client.get(
        "/marketplace/orders/deliveries",
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert resp.status_code == 200, f"deliveries so'rovi muvaffaqiyatsiz: {resp.text}"
    data = resp.json()
    assert data["total"] >= 1, "Kuryer o'z yetkazishini ko'rishi kerak"
    order_ids = [o["id"] for o in data["items"]]
    assert order_id in order_ids, "Tayinlangan buyurtma ro'yxatda bo'lishi kerak"

    # Holat delivering ekanligini tekshirish
    item = next(o for o in data["items"] if o["id"] == order_id)
    assert item["status"] == "delivering"
    assert item["courier_id"] == str(courier_b.id)


# ─── 2. Boshqa kuryer o'zganing yetkazishini ko'rmaydi ───────────────────────


@pytest.mark.asyncio
async def test_other_courier_cannot_see_deliveries(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    courier_b2: AppUser,
    store_a: Store,
) -> None:
    """Boshqa kuryer (courier_b2) courier_b'ga tayinlangan buyurtmani ko'rmaydi."""
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b2 = await get_token(mp_client, courier_b2)

    # courier_b'ga tayinlangan buyurtma
    await _create_and_ship_order(
        mp_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        courier_id=str(courier_b.id),
        sku="V2C-OTHERLIST-001",
    )

    # courier_b2 o'z deliveries ro'yxatini oladi — bo'sh bo'lishi kerak
    resp = await mp_client.get(
        "/marketplace/orders/deliveries",
        headers={"Authorization": f"Bearer {token_courier_b2}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # courier_b2 ga hech narsa tayinlanmagan
    assert data["total"] == 0, (
        f"Boshqa kuryer buyurtmani ko'rmasligi kerak (izolyatsiya buzildi!): {data}"
    )


# ─── 3. Delivering bo'lmagan buyurtmalar ko'rinmaydi ─────────────────────────


@pytest.mark.asyncio
async def test_only_delivering_orders_visible(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """
    Confirmed yoki delivered holatdagi buyurtmalar deliveries ro'yxatiga kirmaydi.
    Faqat delivering holat ko'rinadi.
    """
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)
    token_courier_b = await get_token(mp_client, courier_b)

    # confirmed holat — ship qilinmagan (kuryer ID yo'q)
    create_resp = await mp_client.post(
        "/catalog/products",
        json={"name_uz": "V2C holat test", "name_ru": "V2C тест", "unit": "dona", "sku": "V2C-CONFIRMED-001"},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    await mp_client.patch(
        f"/catalog/products/{product_id}/marketplace",
        json={"marketplace_published": True, "marketplace_price": "5000.00"},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )

    order_resp = await mp_client.post(
        "/marketplace/orders",
        json={"lines": [{"product_id": product_id, "qty": "1"}], "store_id": str(store_a.id)},
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    confirmed_order_id = order_resp.json()["id"]

    await mp_client.patch(
        f"/marketplace/orders/{confirmed_order_id}/confirm",
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    # Bu buyurtma confirmed holatda — kuryer deliveries da ko'rinmasligi kerak

    resp = await mp_client.get(
        "/marketplace/orders/deliveries",
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    order_ids = [o["id"] for o in data["items"]]
    assert confirmed_order_id not in order_ids, (
        "Confirmed holat deliveries ro'yxatiga kirmasligi kerak"
    )


# ─── 4. Kuryer proof-photo yuklaydi → delivered ───────────────────────────────


@pytest.mark.asyncio
async def test_courier_proof_photo_delivers_order(
    storage_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    store_a: Store,
) -> None:
    """
    Kuryer POST /marketplace/orders/{id}/proof-photo:
    rasm yuklaydi → buyurtma delivered holatga o'tadi.
    FakeStorage bilan — haqiqiy MinIO kerak emas.
    """
    token_b_admin = await get_token(storage_client, admin_b)
    token_a_store = await get_token(storage_client, store_user_a)
    token_courier_b = await get_token(storage_client, courier_b)

    order_id = await _create_and_ship_order(
        storage_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        courier_id=str(courier_b.id),
        sku="V2C-PROOF-001",
    )

    # JPEG magic bytes bilan minimal sinov rasmi
    # FakeStorage _validate_photo chaqiradi: magic bytes to'g'ri bo'lishi kerak
    # FF D8 FF E0 + 8 bayt bo'sh → toplam 12 bayt, _MAGIC_READ_BYTES ga mos
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 8  # 12 bayt JPEG-like

    resp = await storage_client.post(
        f"/marketplace/orders/{order_id}/proof-photo",
        files={"file": ("proof.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert resp.status_code == 200, f"proof-photo muvaffaqiyatsiz: {resp.text}"
    data = resp.json()
    assert data["status"] == "delivered", f"Status delivered bo'lishi kerak: {data['status']}"
    assert data["proof_photo_url"] is not None, "proof_photo_url bo'lishi kerak"
    assert data["delivered_at"] is not None, "delivered_at bo'lishi kerak"

    # deliveries ro'yxatida endi ko'rinmaydi (delivered holat)
    list_resp = await storage_client.get(
        "/marketplace/orders/deliveries",
        headers={"Authorization": f"Bearer {token_courier_b}"},
    )
    assert list_resp.status_code == 200
    order_ids = [o["id"] for o in list_resp.json()["items"]]
    assert order_id not in order_ids, (
        "Delivered buyurtma deliveries ro'yxatida ko'rinmasligi kerak"
    )


# ─── 5. Boshqa kuryer proof-photo yuklay olmaydi → 403 ───────────────────────


@pytest.mark.asyncio
async def test_wrong_courier_cannot_upload_proof(
    storage_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    courier_b: AppUser,
    courier_b2: AppUser,
    store_a: Store,
) -> None:
    """Tayinlanmagan kuryer proof-photo yuklay olmaydi → 403."""
    token_b_admin = await get_token(storage_client, admin_b)
    token_a_store = await get_token(storage_client, store_user_a)
    token_courier_b2 = await get_token(storage_client, courier_b2)

    order_id = await _create_and_ship_order(
        storage_client,
        admin_b_token=token_b_admin,
        store_a_token=token_a_store,
        store_a_id=str(store_a.id),
        courier_id=str(courier_b.id),  # courier_b tayinlanadi
        sku="V2C-WRONGPROOF-001",
    )

    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 8

    # courier_b2 (tayinlanmagan) proof yuklashga urinadi
    # FakeStorage magic-bytes tekshiradi — rasm validatsiyasi o'tadi,
    # lekin keyin deliver_order 403 qaytaradi (courier_id != current_user.id)
    resp = await storage_client.post(
        f"/marketplace/orders/{order_id}/proof-photo",
        files={"file": ("proof.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        headers={"Authorization": f"Bearer {token_courier_b2}"},
    )
    assert resp.status_code == 403, (
        f"Tayinlanmagan kuryer proof yuklay olmaydi (xavfsizlik buzildi!): {resp.text}"
    )
