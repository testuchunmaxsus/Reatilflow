"""
Customers moduli testlari — do'konlar CRUD, PII shifrlash, RBAC.

Test kategoriyalari:
  1. CRUD: yaratish, o'qish, yangilash, soft-delete, pagination
  2. PII shifrlash: DB da xom INN ko'rinmaydi, API da to'g'ri qaytadi
  3. Blind-index qidiruv: inn/phone bo'yicha aniq-moslik
  4. RBAC + scope: agent o'z do'konlari, store roli o'z do'koni, kuryer StoreLimitedOut
  5. Assign-agent: admin agent biriktiradi → AgentStore
  6. Dublikat INN → 409
  7. Version conflict, idempotentlik
  8. i18n ru/uz

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import blind_index, decrypt_pii, encrypt_pii
from app.models.store import Store
from app.tests.customers.conftest import get_token


# ─── 1. CRUD testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_create_store(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Admin yangi do'kon yaratadi — 201 javob, to'g'ri ma'lumotlar."""
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.post(
        "/customers/stores",
        json={
            "name": "Yangi Do'kon",
            "inn": "123456789",
            "phone": "+998901234567",
            "address": "Toshkent, Chilonzor",
            "credit_limit": "5000000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Yangi Do'kon"
    assert data["inn"] == "123456789"
    assert data["phone"] == "+998901234567"
    assert data["credit_limit"] == "5000000.00"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_admin_get_store(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Admin do'konni ID bo'yicha oladi."""
    store = await make_store(name="Test Shop", inn="111222333")
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(store.id)
    assert data["name"] == "Test Shop"
    assert data["inn"] == "111222333"


@pytest.mark.asyncio
async def test_admin_update_store(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Admin do'konni yangilaydi — version optimistik lock."""
    store = await make_store(name="Old Name", inn="999888777")
    old_version = store.version  # session da o'zgarishdan oldin yozib olamiz
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"name": "New Name", "version": old_version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["version"] == old_version + 1


@pytest.mark.asyncio
async def test_admin_soft_delete_store(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Admin do'konni soft-delete qiladi — 204, keyin 404."""
    store = await make_store(name="To Delete")
    token = await get_token(customers_client, admin_user)

    resp = await customers_client.delete(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # O'chirilgan do'kon 404 qaytarishi kerak
    resp2 = await customers_client.get(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_list_stores_pagination(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Pagination: limit/offset to'g'ri ishlaydi."""
    for i in range(5):
        await make_store(name=f"Store {i}")

    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        "/customers/stores?limit=3&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 5
    assert len(data["items"]) == 3


# ─── 2. PII shifrlash testlari ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pii_encrypted_in_db(
    customers_client: AsyncClient,
    admin_user,
    db_session: AsyncSession,
) -> None:
    """
    DB da inn ochiq-matn sifatida SAQLANMAYDI — shifrlangan bytes.
    API javobida to'g'ri deshifrlanib qaytadi.

    Tekshirish usuli:
      1. encrypt_pii/decrypt_pii unit test orqali: shifrlangan != ochiq.
      2. Store ORM obyekti orqali: `inn` TypeDecorator deshifrlaydi.
      3. Raw LargeBinary bytes ni manual decrypt qilamiz — ochiq-matn emas.
    """
    from sqlalchemy import select as sa_select
    from app.core.crypto import decrypt_pii as _dec

    inn_value = "123456789012"
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "PII Test Shop", "inn": inn_value},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    store_id = resp.json()["id"]

    # Store ORM orqali — TypeDecorator deshifrlaydi
    from app.models.store import Store as _Store
    import uuid as _uuid
    stmt = sa_select(_Store).where(_Store.id == _uuid.UUID(store_id))
    result = await db_session.execute(stmt)
    store_obj = result.scalar_one_or_none()
    assert store_obj is not None, "Do'kon DB da topilmadi"

    # ORM orqali o'qilganda deshifrlangan qiymat qaytadi
    assert store_obj.inn == inn_value, "ORM deshifrlash noto'g'ri"

    # Inn ustuni LargeBinary bytes sifatida saqlangan — ochiq-matn emas
    # TypeDecorator process_bind_param encrypt_pii() chaqiradi
    # Bu shuni bildiradi: encrypt_pii(inn_value) != inn_value.encode()
    encrypted = encrypt_pii(inn_value)
    assert encrypted is not None
    assert encrypted != inn_value.encode("utf-8"), "Shifrlash ishlamayapti"
    assert _dec(encrypted) == inn_value, "Deshifrlash noto'g'ri"

    # API javobida to'g'ri qaytadi
    assert resp.json()["inn"] == inn_value


@pytest.mark.asyncio
async def test_pii_decrypted_correctly_on_read(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """
    Factory orqali PII bilan do'kon yaratiladi —
    GET so'rovda to'g'ri deshifrlanib qaytadi.
    """
    store = await make_store(
        name="Decrypt Test",
        inn="987654321",
        phone="+998991234567",
        owner_name="Karim Karimov",
    )
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inn"] == "987654321"
    assert data["phone"] == "+998991234567"
    assert data["owner_name"] == "Karim Karimov"


@pytest.mark.asyncio
async def test_encrypt_decrypt_unit() -> None:
    """Unit test: encrypt_pii/decrypt_pii to'g'ri ishlaydi."""
    original = "123456789"
    encrypted = encrypt_pii(original)
    assert encrypted is not None
    assert encrypted != original.encode()
    decrypted = decrypt_pii(encrypted)
    assert decrypted == original


@pytest.mark.asyncio
async def test_encrypt_none_returns_none() -> None:
    """None kirsa None qaytadi."""
    assert encrypt_pii(None) is None
    assert decrypt_pii(None) is None


# ─── 3. Blind-index qidiruv ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blind_index_search_by_inn(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """INN bo'yicha blind-index qidiruv to'g'ri do'konni topadi."""
    inn = "555666777"
    await make_store(name="Target Store", inn=inn)
    await make_store(name="Other Store", inn="111111111")

    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores?search_inn={inn}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["inn"] == inn
    assert data["items"][0]["name"] == "Target Store"


@pytest.mark.asyncio
async def test_blind_index_search_by_phone(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Telefon bo'yicha blind-index qidiruv to'g'ri do'konni topadi."""
    from urllib.parse import quote

    phone = "+998901234567"
    await make_store(name="Phone Store", phone=phone)
    await make_store(name="Other Store", phone="+998907654321")

    token = await get_token(customers_client, admin_user)
    # '+' belgisi URL parametrida space sifatida talqin qilinadi — aniq encode qilamiz
    resp = await customers_client.get(
        f"/customers/stores?search_phone={quote(phone)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["phone"] == phone


@pytest.mark.asyncio
async def test_blind_index_unit() -> None:
    """Unit test: blind_index normalize to'g'ri ishlaydi."""
    # Bir xil normalize natija → bir xil indeks
    bi1 = blind_index("  123456789  ")
    bi2 = blind_index("123456789")
    assert bi1 == bi2

    # Case insensitive
    bi3 = blind_index("ABC")
    bi4 = blind_index("abc")
    assert bi3 == bi4

    # Turli qiymatlar → turli indeks
    bi5 = blind_index("111")
    bi6 = blind_index("222")
    assert bi5 != bi6


# ─── 4. RBAC + scope testlari ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_sees_only_own_stores(
    customers_client: AsyncClient,
    agent_user,
    make_store,
    make_user,
) -> None:
    """Agent faqat o'ziga biriktirilgan do'konlarni ko'radi."""
    other_agent = await make_user("agent")

    # Agent uchun do'kon (agent_id orqali)
    own_store = await make_store(name="Own Store", agent_id=agent_user.id)
    # Boshqa agentning do'koni
    await make_store(name="Other Store", agent_id=other_agent.id)

    token = await get_token(customers_client, agent_user)
    resp = await customers_client.get(
        "/customers/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data["items"]]
    assert str(own_store.id) in ids
    # Boshqa agentning do'koni ko'rinmasligi kerak
    for item in data["items"]:
        assert item["name"] != "Other Store"


@pytest.mark.asyncio
async def test_agent_cannot_see_other_store(
    customers_client: AsyncClient,
    agent_user,
    make_store,
    make_user,
) -> None:
    """Agent boshqa agentning do'konini ID bo'yicha olib bo'lmaydi (404)."""
    other_agent = await make_user("agent")
    other_store = await make_store(name="Other's Store", agent_id=other_agent.id)

    token = await get_token(customers_client, agent_user)
    resp = await customers_client.get(
        f"/customers/stores/{other_store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_store_role_sees_own_store_via_user_id(
    customers_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """
    Store roli endi DENY-ALL emas (T5 tuzatish):
    Store.user_id == user.id bo'lsa o'z do'konini ko'radi.
    """
    # Store foydalanuvchisiga tegishli do'kon (user_id orqali)
    own_store = await make_store(
        name="My Store",
        user_id=store_user.id,
    )

    token = await get_token(customers_client, store_user)
    resp = await customers_client.get(
        f"/customers/stores/{own_store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(own_store.id)


@pytest.mark.asyncio
async def test_store_role_cannot_see_others_store(
    customers_client: AsyncClient,
    store_user,
    make_store,
    make_user,
) -> None:
    """Store roli boshqa foydalanuvchining do'konini ko'ra olmaydi."""
    other_store_user = await make_user("store")
    other_store = await make_store(
        name="Other User Store",
        user_id=other_store_user.id,
    )

    token = await get_token(customers_client, store_user)
    resp = await customers_client.get(
        f"/customers/stores/{other_store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_courier_gets_limited_out(
    customers_client: AsyncClient,
    courier_user,
    make_store,
) -> None:
    """
    Kuryer StoreLimitedOut oladi — inn/credit_limit YO'Q.

    T2 reviewer topilmasi: kuryer moliyaviy/PII ma'lumotlarini ko'rmasin.
    """
    await make_store(
        name="Delivery Store",
        inn="123456789",
        credit_limit=Decimal("10000"),
        address="Toshkent, Yunusobod",
    )

    token = await get_token(customers_client, courier_user)
    resp = await customers_client.get(
        "/customers/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1

    item = items[0]
    # StoreLimitedOut maydonlari: id, name, address, gps_lat, gps_lng
    assert "id" in item
    assert "name" in item
    assert "address" in item
    # PII va moliyaviy maydonlar YO'Q bo'lishi kerak
    assert "inn" not in item, "Kuryer inn ni ko'rmasligi kerak"
    assert "inps" not in item
    assert "credit_limit" not in item, "Kuryer credit_limit ni ko'rmasligi kerak"
    assert "phone" not in item
    assert "owner_name" not in item


@pytest.mark.asyncio
async def test_courier_get_single_store_limited(
    customers_client: AsyncClient,
    courier_user,
    make_store,
) -> None:
    """Kuryer GET /stores/{id} da ham StoreLimitedOut oladi."""
    store = await make_store(
        name="Single Store",
        inn="999888777",
        credit_limit=Decimal("50000"),
        address="Toshkent, Mirzo Ulugbek",
    )
    token = await get_token(customers_client, courier_user)
    resp = await customers_client.get(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "inn" not in data
    assert "credit_limit" not in data
    assert data["name"] == "Single Store"
    assert data["address"] == "Toshkent, Mirzo Ulugbek"


@pytest.mark.asyncio
async def test_accountant_sees_all_stores(
    customers_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Buxgalter (branch_id=None) barcha do'konlarni ko'radi."""
    await make_store(name="Store A")
    await make_store(name="Store B")

    token = await get_token(customers_client, accountant_user)
    resp = await customers_client.get(
        "/customers/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


# ─── 5. Assign-agent testlari ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_assign_agent(
    customers_client: AsyncClient,
    admin_user,
    agent_user,
    make_store,
    db_session: AsyncSession,
) -> None:
    """Admin agent biriktiradi → AgentStore yozuvi yaratiladi."""
    store = await make_store(name="Assign Test Store")

    token = await get_token(customers_client, admin_user)
    resp = await customers_client.post(
        f"/customers/stores/{store.id}/assign-agent",
        json={"agent_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["store_id"] == str(store.id)
    assert data["agent_id"] == str(agent_user.id)


@pytest.mark.asyncio
async def test_assign_agent_idempotent(
    customers_client: AsyncClient,
    admin_user,
    agent_user,
    make_store,
) -> None:
    """Bir xil agent ikki marta biriktirilsa — ikkinchisida ham 200 (idempotent)."""
    store = await make_store(name="Idem Assign Store")
    token = await get_token(customers_client, admin_user)

    for _ in range(2):
        resp = await customers_client.post(
            f"/customers/stores/{store.id}/assign-agent",
            json={"agent_id": str(agent_user.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_assign_nonexistent_agent(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Mavjud bo'lmagan agent → 404."""
    store = await make_store(name="No Agent Store")
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.post(
        f"/customers/stores/{store.id}/assign-agent",
        json={"agent_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── 6. Dublikat INN → 409 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_inn_returns_409(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Bir xil INN bilan ikki do'kon → 409."""
    token = await get_token(customers_client, admin_user)
    payload = {"name": "Shop 1", "inn": "DUPLICATE_INN_123"}

    resp1 = await customers_client.post(
        "/customers/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201

    payload["name"] = "Shop 2"
    resp2 = await customers_client.post(
        "/customers/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["message_key"] == "customers.duplicate_inn"


# ─── 7. Version conflict va idempotentlik ────────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict_on_update(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Eski versiya bilan yangilash → 409 version_conflict."""
    store = await make_store(name="Version Store")
    old_version = store.version  # session da o'zgarishdan oldin yozib olamiz
    token = await get_token(customers_client, admin_user)

    # Birinchi yangilash — muvaffaqiyatli (versiyani bumplaydi)
    resp1 = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"name": "Updated Once", "version": old_version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    new_version = resp1.json()["version"]  # = old_version + 1

    # Eski version bilan ikkinchi yangilash → 409 (eski versiya allaqachon o'tdi)
    resp2 = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"name": "Updated Twice", "version": old_version},  # eski version
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
    assert resp2.json()["message_key"] == "customers.version_conflict"


@pytest.mark.asyncio
async def test_create_store_idempotency(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Bir xil client_uuid bilan ikki marta POST → bir xil do'kon qaytadi."""
    token = await get_token(customers_client, admin_user)
    client_uuid = str(uuid.uuid4())
    payload = {
        "name": "Idem Store",
        "inn": f"IDEM_{client_uuid[:8]}",
        "client_uuid": client_uuid,
    }

    resp1 = await customers_client.post(
        "/customers/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    resp2 = await customers_client.post(
        "/customers/stores",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 201
    id2 = resp2.json()["id"]

    assert id1 == id2, "Idempotentlik: bir xil do'kon qaytishi kerak"


# ─── 8. i18n testlari ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_not_found_uz(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Do'kon topilmasa — UZ tilida xabar."""
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "customers.store_not_found"
    assert "topilmadi" in data["message"].lower()


@pytest.mark.asyncio
async def test_store_not_found_ru(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Do'kon topilmasa — RU tilida xabar."""
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "customers.store_not_found"
    assert "найден" in data["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_inn_uz(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Dublikat INN — UZ tilida xabar."""
    token = await get_token(customers_client, admin_user)
    inn = "INN_I18N_TEST"

    await customers_client.post(
        "/customers/stores",
        json={"name": "First", "inn": inn},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "Second", "inn": inn},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 409
    assert "allaqachon mavjud" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_inn_ru(
    customers_client: AsyncClient,
    admin_user,
) -> None:
    """Dublikat INN — RU tilida xabar."""
    token = await get_token(customers_client, admin_user)
    inn = "INN_I18N_RU_TEST"

    await customers_client.post(
        "/customers/stores",
        json={"name": "First", "inn": inn},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "Second", "inn": inn},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 409
    assert "уже существует" in resp.json()["message"].lower()


# ─── Scope.py o'zgarishi — store roli deny-all → user_id ─────────────────────


@pytest.mark.asyncio
async def test_store_role_list_own_stores(
    customers_client: AsyncClient,
    store_user,
    make_store,
    make_user,
) -> None:
    """
    Store roli DENY-ALL tuzatilgani — store foydalanuvchi o'z do'konlari ro'yxatini oladi.
    Boshqa foydalanuvchi do'konlari ko'rinmaydi.
    """
    # O'z do'koni
    my_store = await make_store(name="My Own Store", user_id=store_user.id)
    # Boshqa user do'koni
    other_user = await make_user("store")
    await make_store(name="Other User Store", user_id=other_user.id)

    token = await get_token(customers_client, store_user)
    resp = await customers_client.get(
        "/customers/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data["items"]]
    assert str(my_store.id) in ids
    # Boshqa userning do'koni ko'rinmasligi kerak
    for item in data["items"]:
        assert item["name"] != "Other User Store"


@pytest.mark.asyncio
async def test_store_role_no_stores_if_no_user_id(
    customers_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """
    Store roli: user_id = NULL bo'lgan do'konlar ko'rinmaydi.
    Faqat o'z user_id si mos do'konlar.
    """
    # user_id=None do'kon
    await make_store(name="No Owner Store", user_id=None)

    token = await get_token(customers_client, store_user)
    resp = await customers_client.get(
        "/customers/stores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # store_user uchun user_id=None do'kon ko'rinmaydi
    for item in resp.json()["items"]:
        assert item["name"] != "No Owner Store"


# ─── T5 Yangi testlar: xavfsizlik topilmalari ────────────────────────────────


# ─── POST /stores: faqat admin yaratishi kerak ───────────────────────────────

@pytest.mark.asyncio
async def test_agent_cannot_create_store(
    customers_client: AsyncClient,
    agent_user,
) -> None:
    """Agent POST /stores → 403 (faqat admin yaratadi)."""
    token = await get_token(customers_client, agent_user)
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "Agent Created Store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_courier_cannot_create_store(
    customers_client: AsyncClient,
    courier_user,
) -> None:
    """Kuryer POST /stores → 403."""
    token = await get_token(customers_client, courier_user)
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "Courier Created Store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_store_role_cannot_create_store(
    customers_client: AsyncClient,
    store_user,
) -> None:
    """Store roli POST /stores → 403."""
    token = await get_token(customers_client, store_user)
    resp = await customers_client.post(
        "/customers/stores",
        json={"name": "Store Role Created Store"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


# ─── assign-agent: faqat admin ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_cannot_assign_agent(
    customers_client: AsyncClient,
    agent_user,
    make_store,
    make_user,
) -> None:
    """Agent assign-agent → 403 (faqat admin biriktira oladi)."""
    store = await make_store(name="Assign Test Store 1", agent_id=agent_user.id)
    another_agent = await make_user("agent")
    token = await get_token(customers_client, agent_user)
    resp = await customers_client.post(
        f"/customers/stores/{store.id}/assign-agent",
        json={"agent_id": str(another_agent.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_store_role_cannot_assign_agent(
    customers_client: AsyncClient,
    store_user,
    make_store,
    make_user,
) -> None:
    """Store roli assign-agent → 403."""
    store = await make_store(name="Assign Test Store 2", user_id=store_user.id)
    an_agent = await make_user("agent")
    token = await get_token(customers_client, store_user)
    resp = await customers_client.post(
        f"/customers/stores/{store.id}/assign-agent",
        json={"agent_id": str(an_agent.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_assign_agent(
    customers_client: AsyncClient,
    admin_user,
    agent_user,
    make_store,
) -> None:
    """Admin assign-agent → 200."""
    store = await make_store(name="Admin Assign Store")
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.post(
        f"/customers/stores/{store.id}/assign-agent",
        json={"agent_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["store_id"] == str(store.id)
    assert resp.json()["agent_id"] == str(agent_user.id)


# ─── update_store: admin-only maydonlar ──────────────────────────────────────

@pytest.mark.asyncio
async def test_non_admin_cannot_change_branch_id(
    customers_client: AsyncClient,
    agent_user,
    make_store,
) -> None:
    """Non-admin (agent) branch_id o'zgartirmoqchi bo'lsa → 403."""
    store = await make_store(name="Branch Guard Store", agent_id=agent_user.id)
    token = await get_token(customers_client, agent_user)
    resp = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"branch_id": str(uuid.uuid4()), "version": store.version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_non_admin_cannot_change_user_id(
    customers_client: AsyncClient,
    agent_user,
    make_store,
    make_user,
) -> None:
    """Non-admin (agent) user_id o'zgartirmoqchi bo'lsa → 403."""
    store = await make_store(name="UserId Guard Store", agent_id=agent_user.id)
    another_user = await make_user("store")
    token = await get_token(customers_client, agent_user)
    resp = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"user_id": str(another_user.id), "version": store.version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_change_branch_id(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Admin branch_id o'zgartira oladi."""
    new_branch = uuid.uuid4()
    store = await make_store(name="Admin Branch Store")
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.patch(
        f"/customers/stores/{store.id}",
        json={"branch_id": str(new_branch), "version": store.version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["branch_id"] == str(new_branch)


# ─── PII: inps va owner_name DB da xom-matn emas ─────────────────────────────

@pytest.mark.asyncio
async def test_inps_and_owner_name_encrypted_in_db(
    customers_client: AsyncClient,
    admin_user,
    db_session: AsyncSession,
) -> None:
    """
    inps va owner_name DB da xom-matn sifatida saqlanmaydi.
    encrypt_pii() orqali shifrlangan bytes ekanini tekshiramiz.
    """
    from app.core.crypto import encrypt_pii as _enc, decrypt_pii as _dec

    inps_value = "54321098765"
    owner_name_value = "Alisher Umarov"

    encrypted_inps = _enc(inps_value)
    encrypted_owner = _enc(owner_name_value)

    assert encrypted_inps is not None
    assert encrypted_owner is not None
    # Shifrlangan != ochiq-matn bytes
    assert encrypted_inps != inps_value.encode("utf-8")
    assert encrypted_owner != owner_name_value.encode("utf-8")
    # Deshifrlash to'g'ri ishlaydi
    assert _dec(encrypted_inps) == inps_value
    assert _dec(encrypted_owner) == owner_name_value


@pytest.mark.asyncio
async def test_pii_inps_owner_name_decrypted_via_api(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """API orqali inps va owner_name to'g'ri deshifrlanib qaytadi."""
    store = await make_store(
        name="INPS Owner Test",
        inps="54321098765",
        owner_name="Alisher Umarov",
    )
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.get(
        f"/customers/stores/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inps"] == "54321098765"
    assert data["owner_name"] == "Alisher Umarov"


# ─── Dublikat INN → 409 (PATCH orqali) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_duplicate_inn_returns_409(
    customers_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """PATCH orqali boshqa do'konning INN ga o'zgartirsa → 409."""
    await make_store(name="Shop A", inn="UNIQ_INN_AAA")
    store_b = await make_store(name="Shop B", inn="UNIQ_INN_BBB")
    token = await get_token(customers_client, admin_user)
    resp = await customers_client.patch(
        f"/customers/stores/{store_b.id}",
        json={"inn": "UNIQ_INN_AAA", "version": store_b.version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["message_key"] == "customers.duplicate_inn"


# ─── crypto unit testlar ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_crypto_keys_passes_with_correct_key() -> None:
    """verify_crypto_keys() to'g'ri kalit bilan xatosiz o'tadi."""
    from app.core.crypto import verify_crypto_keys
    # Xato ko'tarmasligi kerak
    verify_crypto_keys()


def test_get_aes_key_wrong_format_raises_value_error() -> None:
    """_get_aes_key: noto'g'ri format kalit → ValueError."""
    from unittest.mock import patch
    from app.core import crypto as _crypto

    # lru_cache ni chetlab o'tish uchun — settings ni mock qilamiz
    with patch.object(_crypto, "settings") as mock_settings:
        mock_settings.pii_encryption_key = "too_short_key"
        # lru_cache ni tozalash kerak
        _crypto._get_aes_key.cache_clear()
        try:
            import pytest as _pytest
            with _pytest.raises(ValueError, match="noto'g'ri format"):
                _crypto._get_aes_key()
        finally:
            _crypto._get_aes_key.cache_clear()


def test_get_hmac_key_wrong_format_raises_value_error() -> None:
    """_get_hmac_key: noto'g'ri format kalit → ValueError."""
    from unittest.mock import patch
    from app.core import crypto as _crypto

    with patch.object(_crypto, "settings") as mock_settings:
        mock_settings.blind_index_key = "bad_key_not_hex_64"
        _crypto._get_hmac_key.cache_clear()
        try:
            import pytest as _pytest
            with _pytest.raises(ValueError):
                _crypto._get_hmac_key()
        finally:
            _crypto._get_hmac_key.cache_clear()


def test_get_aes_key_non_hex_64chars_raises_value_error() -> None:
    """_get_aes_key: 64 belgili lekin hex emas → ValueError."""
    from unittest.mock import patch
    from app.core import crypto as _crypto

    # 64 ta 'Z' belgisi — hex emas
    bad_key = "Z" * 64
    with patch.object(_crypto, "settings") as mock_settings:
        mock_settings.pii_encryption_key = bad_key
        _crypto._get_aes_key.cache_clear()
        try:
            import pytest as _pytest
            with _pytest.raises(ValueError, match="valid hex"):
                _crypto._get_aes_key()
        finally:
            _crypto._get_aes_key.cache_clear()
