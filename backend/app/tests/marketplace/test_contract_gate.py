"""
Marketplace Shartnoma-Gate testlari — ADR-003 Bo'lak C.

Qamrov (majburiy 4 test):
  a. Shartnoma bor → buyurtma o'tadi (is_onetime=False).
  b. Shartnoma yo'q → 409 contract_required.
  c. Agent bir martalik bypass → is_onetime=True.
  d. IDOR: boshqa do'kon buyurtmasini ko'rib/o'zgartirib bo'lmaydi.

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import hash_password
from app.models.catalog import Product
from app.models.contract import Contract
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.tests.marketplace.conftest import (
    TEST_PASSWORD,
    TEST_ENTERPRISE_B_UUID,
    get_token,
)
from app.tests.conftest import TEST_ENTERPRISE_UUID

# Uchinchi korxona UUID — IDOR testi uchun (enterprise_a ham, enterprise_b ham emas)
TEST_ENTERPRISE_C_UUID = uuid.UUID("00000000-0000-7000-8000-0000000000cc")


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _make_user(role: str, enterprise_id: uuid.UUID | None, suffix: str = "") -> AppUser:
    user_id = uuid.uuid4()
    phone_hash = abs(hash(str(user_id) + suffix + "gate"))
    return AppUser(
        id=user_id,
        full_name=f"Gate {role.capitalize()} {suffix}",
        phone=f"+99894{str(phone_hash)[:7]}",
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
async def enterprise_a(db_session: AsyncSession) -> Enterprise:
    """Asosiy test korxonasi (buyer)."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_UUID,
        name="Gate Korxona A",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def enterprise_b(db_session: AsyncSession) -> Enterprise:
    """Supplier korxona B."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_B_UUID,
        name="Gate Korxona B",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def admin_b(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Enterprise B administratori."""
    user = _make_user("administrator", enterprise_b.id, "adminB")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def store_user_a(db_session: AsyncSession, enterprise_a: Enterprise) -> AppUser:
    """Enterprise A do'kon foydalanuvchisi."""
    user = _make_user("store", enterprise_a.id, "storeA")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def agent_b(db_session: AsyncSession, enterprise_b: Enterprise) -> AppUser:
    """Enterprise B agenti (supplier korxona agenti)."""
    user = _make_user("agent", enterprise_b.id, "agentB")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def agent_other(db_session: AsyncSession, enterprise_a: Enterprise) -> AppUser:
    """Enterprise A agenti (supplier emas — gate uchun bypass yo'q)."""
    user = _make_user("agent", enterprise_a.id, "agentOther")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def store_a(
    db_session: AsyncSession,
    enterprise_a: Enterprise,
    store_user_a: AppUser,
) -> Store:
    """Enterprise A do'koni."""
    store = Store(
        id=uuid.uuid4(),
        name="Gate Do'kon A",
        enterprise_id=enterprise_a.id,
        user_id=store_user_a.id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()
    return store


@pytest.fixture
async def enterprise_c(db_session: AsyncSession) -> Enterprise:
    """Uchinchi korxona — IDOR testi uchun (supplier ham, buyer ham emas)."""
    ent = Enterprise(
        id=TEST_ENTERPRISE_C_UUID,
        name="Gate Korxona C (IDOR)",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(ent)
    await db_session.flush()
    return ent


@pytest.fixture
async def store_other(
    db_session: AsyncSession,
    enterprise_c: Enterprise,
) -> Store:
    """Enterprise C do'koni — IDOR testi uchun (enterprise_a buyurtmalarini ko'ra OLMAYDI)."""
    other_user = _make_user("store", enterprise_c.id, "storeC")
    db_session.add(other_user)
    await db_session.flush()

    store = Store(
        id=uuid.uuid4(),
        name="Gate C Do'kon (IDOR)",
        enterprise_id=enterprise_c.id,
        user_id=other_user.id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()
    return store


async def _create_published_product(
    client: AsyncClient,
    admin_token: str,
    sku: str,
    price: str = "10000.00",
) -> str:
    """B korxona mahsulot yaratadi va publish qiladi."""
    resp = await client.post(
        "/catalog/products",
        json={
            "name_uz": f"Gate mahsulot {sku}",
            "name_ru": f"Gate товар {sku}",
            "unit": "dona",
            "sku": sku,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, f"Mahsulot yaratilmadi: {resp.text}"
    pid = resp.json()["id"]

    pub = await client.patch(
        f"/catalog/products/{pid}/marketplace",
        json={"marketplace_published": True, "marketplace_price": price},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub.status_code == 200, f"Publish muvaffaqiyatsiz: {pub.text}"
    return pid


# ─── a. Shartnoma bor → buyurtma o'tadi (is_onetime=False) ───────────────────


@pytest.mark.asyncio
async def test_gate_with_active_contract_order_passes(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    store_a: Store,
    enterprise_b: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    Shartnoma-Gate: aktiv Contract(store_a, supplier=enterprise_b) mavjud →
    buyurtma 201 bilan yaratiladi, is_onetime=False.
    """
    # Aktiv shartnoma yaratish
    contract = Contract(
        store_id=store_a.id,
        number="GATE-CONTRACT-001",
        valid_from=_today() - timedelta(days=10),
        valid_to=_today() + timedelta(days=365),
        contract_type="trade",
        supplier_enterprise_id=enterprise_b.id,
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()

    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    pid = await _create_published_product(
        mp_client, token_b_admin, "GATE-SKU-A01"
    )

    resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": pid, "qty": "2"}],
            "store_id": str(store_a.id),
        },
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert resp.status_code == 201, f"Buyurtma yaratilmadi (shartnoma bor): {resp.text}"
    order = resp.json()
    assert order["is_onetime"] is False, "Shartnoma bor buyurtma is_onetime=False bo'lishi kerak"
    assert order["agent_id"] is None, "Shartnoma bor buyurtmada agent_id None bo'lishi kerak"


# ─── b. Shartnoma yo'q → 409 contract_required ───────────────────────────────


@pytest.mark.asyncio
async def test_gate_no_contract_returns_409(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    store_a: Store,
) -> None:
    """
    Shartnoma-Gate: aktiv shartnoma yo'q va actor agent emas →
    409 marketplace.contract_required qaytadi.
    """
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    pid = await _create_published_product(
        mp_client, token_b_admin, "GATE-SKU-B01"
    )

    resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": pid, "qty": "1"}],
            "store_id": str(store_a.id),
        },
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert resp.status_code == 409, f"Kutilgan 409, olindi: {resp.status_code} — {resp.text}"
    data = resp.json()
    assert data["message_key"] == "marketplace.contract_required", (
        f"Xato xabar kaliti: {data['message_key']!r}"
    )


# ─── c. Agent bir martalik bypass → is_onetime=True ──────────────────────────


@pytest.mark.asyncio
async def test_gate_agent_bypass_onetime_order(
    mp_client: AsyncClient,
    admin_b: AppUser,
    agent_b: AppUser,
    store_a: Store,
    enterprise_b: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    Shartnoma-Gate: shartnoma yo'q LEKIN actor=agent (supplier B agenti)
    va agent store_a ga biriktirilgan →
    buyurtma 201, is_onetime=True, agent_id=actor.id.
    """
    # Agent store_a ga biriktirish (AgentStore)
    link = AgentStore(
        agent_id=agent_b.id,
        store_id=store_a.id,
    )
    db_session.add(link)
    await db_session.flush()

    token_b_admin = await get_token(mp_client, admin_b)
    token_agent_b = await get_token(mp_client, agent_b)

    pid = await _create_published_product(
        mp_client, token_b_admin, "GATE-SKU-C01"
    )

    resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": pid, "qty": "3"}],
            "store_id": str(store_a.id),
        },
        headers={"Authorization": f"Bearer {token_agent_b}"},
    )
    assert resp.status_code == 201, f"Agent bypass buyurtma yaratilmadi: {resp.text}"
    order = resp.json()
    assert order["is_onetime"] is True, "Agent bypass buyurtma is_onetime=True bo'lishi kerak"
    assert order["agent_id"] == str(agent_b.id), (
        f"agent_id noto'g'ri: {order['agent_id']!r}, kutilgan: {agent_b.id}"
    )


# ─── c2. Agent Store.agent_id orqali biriktirilgan bo'lsa ham bypass ─────────


@pytest.mark.asyncio
async def test_gate_agent_bypass_via_store_agent_id(
    mp_client: AsyncClient,
    admin_b: AppUser,
    agent_b: AppUser,
    enterprise_b: Enterprise,
    enterprise_a: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    Shartnoma-Gate: agent Store.agent_id orqali biriktirish (AgentStore emas) →
    bypass ishlaydi, is_onetime=True.
    """
    # Store.agent_id bilan do'kon yaratish
    store = Store(
        id=uuid.uuid4(),
        name="Agent Direct Store",
        enterprise_id=enterprise_a.id,
        agent_id=agent_b.id,  # to'g'ridan-to'g'ri agent_id FK
        version=1,
    )
    db_session.add(store)
    await db_session.flush()

    # Shartnoma YO'Q — bypass tekshiruvi uchun

    token_b_admin = await get_token(mp_client, admin_b)
    token_agent_b = await get_token(mp_client, agent_b)

    pid = await _create_published_product(
        mp_client, token_b_admin, "GATE-SKU-C02"
    )

    resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": pid, "qty": "1"}],
            "store_id": str(store.id),
        },
        headers={"Authorization": f"Bearer {token_agent_b}"},
    )
    assert resp.status_code == 201, f"Agent direct bypass buyurtma yaratilmadi: {resp.text}"
    order = resp.json()
    assert order["is_onetime"] is True
    assert order["agent_id"] == str(agent_b.id)


# ─── d. IDOR: boshqa do'kon buyurtmasini ko'rib/o'zgartirib bo'lmaydi ────────


@pytest.mark.asyncio
async def test_gate_idor_other_store_cannot_see_order(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    store_a: Store,
    store_other: Store,
    enterprise_b: Enterprise,
    db_session: AsyncSession,
) -> None:
    """
    IDOR: store_a ning buyurtmasini store_other (boshqa do'kon egasi) ko'ra OLMAYDI.

    store_a → B korxona mahsuloti buyurtmasi (shartnoma bilan).
    store_other foydalanuvchisi GET /marketplace/orders/{id} → 404.
    store_other outgoing'da ham ko'rinmaydi.
    """
    # Shartnoma store_a ↔ enterprise_b
    contract = Contract(
        store_id=store_a.id,
        number="GATE-IDOR-CONTRACT",
        valid_from=_today() - timedelta(days=5),
        valid_to=_today() + timedelta(days=365),
        contract_type="trade",
        supplier_enterprise_id=enterprise_b.id,
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()

    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    # store_other egasini topish
    other_user_stmt = __import__("sqlalchemy").select(AppUser).where(
        AppUser.id == store_other.user_id,
    )
    other_user_result = await db_session.execute(other_user_stmt)
    other_store_user = other_user_result.scalar_one()
    token_other_store = await get_token(mp_client, other_store_user)

    pid = await _create_published_product(
        mp_client, token_b_admin, "GATE-SKU-D01"
    )

    # store_a buyurtma beradi
    create_resp = await mp_client.post(
        "/marketplace/orders",
        json={
            "lines": [{"product_id": pid, "qty": "1"}],
            "store_id": str(store_a.id),
        },
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert create_resp.status_code == 201, f"Buyurtma yaratilmadi: {create_resp.text}"
    order_id = create_resp.json()["id"]

    # store_other bu buyurtmani ko'ra OLMAYDI → 404
    get_resp = await mp_client.get(
        f"/marketplace/orders/{order_id}",
        headers={"Authorization": f"Bearer {token_other_store}"},
    )
    assert get_resp.status_code == 404, (
        f"Boshqa do'kon buyurtmani ko'rmasligi kerak, ammo: {get_resp.status_code}"
    )

    # store_other outgoing'da ko'rinmaydi
    outgoing_resp = await mp_client.get(
        "/marketplace/orders/outgoing",
        headers={"Authorization": f"Bearer {token_other_store}"},
    )
    assert outgoing_resp.status_code == 200
    other_ids = [o["id"] for o in outgoing_resp.json()["items"]]
    assert order_id not in other_ids, "Boshqa do'kon buyurtmani outgoing'da ko'rmasligi kerak"
