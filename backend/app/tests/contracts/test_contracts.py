"""
Contracts moduli testlari — T23.

Test kategoriyalari:
  1. CRUD: admin/buxgalter yaratadi/yangilaydi; paginated, filter
  2. status hisoblash: valid_to o'tgan→expired, yaqin→expiring, uzoq→active
  3. Dublikat number → 409; valid_to < valid_from → 422
  4. File upload: PDF magic-byte OK; noto'g'ri (exe) → 422
  5. IDOR/scope: agent o'z do'koni; boshqa do'kon→404; do'kon o'ziniki; admin barchasi
  6. RBAC: agent/do'kon yaratolmaydi (faqat view)
  7. version conflict, idempotentlik, i18n
  8. list_expiring (muddati tugayotganlar)

Infrasiz: aiosqlite + fakeredis + FakeStorage.
"""

from __future__ import annotations

import io
import struct
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.contract import CONTRACT_EXPIRING_DAYS, Contract
from app.modules.contracts import service
from app.tests.contracts.conftest import get_token


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ─── PDF magic bytes helper ───────────────────────────────────────────────────


def _make_pdf_bytes() -> bytes:
    """Minimal valid PDF magic bytes (faqat header)."""
    return b"%PDF-1.4\n%test content\n"


def _make_jpeg_bytes() -> bytes:
    """Minimal JPEG magic bytes."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _make_exe_bytes() -> bytes:
    """MZ header (Windows PE) — ruxsat berilmagan."""
    return b"MZ" + b"\x00" * 100


# ─── 1. CRUD testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_create_contract(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Admin yangi shartnoma yaratadi — 201 javob."""
    store = await make_store(name="Test Do'kon")
    token = await get_token(contracts_client, admin_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "CT-2026-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=60)).isoformat(),
            "contract_type": "trade",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["number"] == "CT-2026-001"
    assert data["store_id"] == str(store.id)
    assert data["status"] == "active"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_accountant_can_view_contract(
    contracts_client: AsyncClient,
    accountant_user,
    make_store,
    make_contract,
) -> None:
    """Buxgalter shartnomani ko'ra oladi (view ruxsati bor)."""
    store = await make_store()
    contract = await make_contract(store_id=store.id, number="BX-VIEW-001")
    token = await get_token(contracts_client, accountant_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["number"] == "BX-VIEW-001"


@pytest.mark.asyncio
async def test_admin_get_contract(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Admin shartnomani ID bo'yicha oladi."""
    store = await make_store()
    contract = await make_contract(store_id=store.id, number="CT-GET-001")
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(contract.id)
    assert data["number"] == "CT-GET-001"


@pytest.mark.asyncio
async def test_admin_update_contract(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Admin shartnomani PATCH bilan yangilaydi."""
    store = await make_store()
    today = _today()
    contract = await make_contract(
        store_id=store.id,
        number="OLD-001",
        valid_from=today,
        valid_to=today + timedelta(days=60),
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.patch(
        f"/contracts/{contract.id}",
        json={"number": "NEW-001", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["number"] == "NEW-001"
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_admin_delete_contract(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Admin shartnomani soft-delete qiladi."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.delete(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204, resp.text

    # Qayta olish → 404
    resp2 = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_list_contracts_paginated(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Paginated ro'yxat — limit/offset ishlaydi."""
    store = await make_store()
    today = _today()
    for i in range(5):
        await make_contract(
            store_id=store.id,
            number=f"CT-PAG-{i:03d}",
            valid_from=today,
            valid_to=today + timedelta(days=60),
        )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        "/contracts?limit=3&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_contracts_filter_store(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """store_id filtri — faqat o'sha do'kon shartnomalarini qaytaradi."""
    store_a = await make_store(name="A")
    store_b = await make_store(name="B")
    today = _today()
    await make_contract(store_id=store_a.id, number="A-001")
    await make_contract(store_id=store_b.id, number="B-001")

    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        f"/contracts?store_id={store_a.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["store_id"] == str(store_a.id)


# ─── 2. Status hisoblash ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_expired(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """valid_to o'tgan → status=expired."""
    store = await make_store()
    today = _today()
    contract = await make_contract(
        store_id=store.id,
        number="EXP-001",
        valid_from=today - timedelta(days=60),
        valid_to=today - timedelta(days=1),  # kecha tugagan
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_status_expiring(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """valid_to yaqin (30 kun ichida) → status=expiring."""
    store = await make_store()
    today = _today()
    contract = await make_contract(
        store_id=store.id,
        number="EXPIRING-001",
        valid_from=today,
        valid_to=today + timedelta(days=15),  # 15 kundan keyin tugaydi
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "expiring"


@pytest.mark.asyncio
async def test_status_active(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """valid_to uzoq kelajakda → status=active."""
    store = await make_store()
    today = _today()
    contract = await make_contract(
        store_id=store.id,
        number="ACT-001",
        valid_from=today,
        valid_to=today + timedelta(days=90),  # 90 kundan keyin
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_status_filter_expired(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """status=expired filtri faqat o'tgan shartnomalarni qaytaradi."""
    store = await make_store()
    today = _today()
    await make_contract(
        store_id=store.id, number="E-001",
        valid_from=today - timedelta(days=60), valid_to=today - timedelta(days=1),
    )
    await make_contract(
        store_id=store.id, number="A-002",
        valid_from=today, valid_to=today + timedelta(days=90),
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        "/contracts?status=expired",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "expired"


@pytest.mark.asyncio
async def test_status_filter_active(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """status=active filtri faqat aktiv shartnomalarni qaytaradi."""
    store = await make_store()
    today = _today()
    await make_contract(
        store_id=store.id, number="A-001",
        valid_from=today, valid_to=today + timedelta(days=90),
    )
    await make_contract(
        store_id=store.id, number="EXP-002",
        valid_from=today - timedelta(days=60), valid_to=today - timedelta(days=1),
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        "/contracts?status=active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["status"] == "active" for item in data["items"])


# ─── 3. Validatsiya xatolari ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_number_returns_409(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Bir xil store_id+number → 409."""
    store = await make_store()
    await make_contract(store_id=store.id, number="DUP-001")
    token = await get_token(contracts_client, admin_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "DUP-001",  # dublikat
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["message_key"] == "contracts.duplicate_number"


@pytest.mark.asyncio
async def test_same_number_different_store_ok(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Turli do'konlarda bir xil number → ruxsat."""
    store_a = await make_store(name="A")
    store_b = await make_store(name="B")
    await make_contract(store_id=store_a.id, number="SHARED-001")
    token = await get_token(contracts_client, admin_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store_b.id),
            "number": "SHARED-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_valid_to_before_valid_from_returns_422(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """valid_to < valid_from → 422."""
    store = await make_store()
    token = await get_token(contracts_client, admin_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "INVALID-DATE",
            "valid_from": (today + timedelta(days=10)).isoformat(),
            "valid_to": today.isoformat(),  # to'g'ri emas
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_update_valid_to_before_valid_from_returns_422(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Update: yangi valid_to < valid_from → 422."""
    store = await make_store()
    today = _today()
    contract = await make_contract(
        store_id=store.id,
        valid_from=today,
        valid_to=today + timedelta(days=60),
    )
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.patch(
        f"/contracts/{contract.id}",
        json={
            "valid_to": (today - timedelta(days=1)).isoformat(),
            "version": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text


# ─── 4. File upload ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_pdf_ok(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """PDF fayl yuklash — 200 javob, file_url yangilanadi."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)

    pdf_content = _make_pdf_bytes()
    resp = await contracts_client.post(
        f"/contracts/{contract.id}/file",
        files={"file": ("contract.pdf", io.BytesIO(pdf_content), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["file_url"] is not None
    assert "contracts/" in data["file_url"]
    assert data["file_url"].endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_jpeg_ok(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """JPEG rasm yuklash shartnoma uchun ham ruxsat."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)

    jpeg_content = _make_jpeg_bytes()
    resp = await contracts_client.post(
        f"/contracts/{contract.id}/file",
        files={"file": ("scan.jpg", io.BytesIO(jpeg_content), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_upload_invalid_file_returns_422(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Noto'g'ri fayl (exe magic) → 422."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)

    exe_content = _make_exe_bytes()
    resp = await contracts_client.post(
        f"/contracts/{contract.id}/file",
        files={"file": ("virus.exe", io.BytesIO(exe_content), "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["message_key"] == "contracts.invalid_file"


@pytest.mark.asyncio
async def test_upload_empty_file_returns_422(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Bo'sh fayl → 422."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)

    resp = await contracts_client.post(
        f"/contracts/{contract.id}/file",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text


# ─── 5. IDOR / Scope testlari ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_sees_own_store_contract(
    contracts_client: AsyncClient,
    agent_user,
    make_store,
    make_contract,
) -> None:
    """Agent o'z do'koni shartnomalarini ko'radi."""
    store = await make_store(agent_id=agent_user.id)
    contract = await make_contract(store_id=store.id, number="AGENT-OWN-001")
    token = await get_token(contracts_client, agent_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["number"] == "AGENT-OWN-001"


@pytest.mark.asyncio
async def test_agent_cannot_see_other_store_contract(
    contracts_client: AsyncClient,
    agent_user,
    make_user,
    make_store,
    make_contract,
) -> None:
    """Agent boshqa agent do'konining shartnomalarini ko'ra olmaydi → 404."""
    other_agent = await make_user("agent")
    other_store = await make_store(agent_id=other_agent.id)
    contract = await make_contract(store_id=other_store.id, number="OTHER-001")

    token = await get_token(contracts_client, agent_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_store_user_sees_own_contract(
    contracts_client: AsyncClient,
    store_user,
    make_store,
    make_contract,
) -> None:
    """Store foydalanuvchi o'z do'konining shartnomalarini ko'radi."""
    store = await make_store(user_id=store_user.id)
    contract = await make_contract(store_id=store.id, number="STORE-OWN-001")
    token = await get_token(contracts_client, store_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_store_user_cannot_see_other_store_contract(
    contracts_client: AsyncClient,
    store_user,
    make_user,
    make_store,
    make_contract,
) -> None:
    """Store foydalanuvchi boshqa do'kon shartnomalarini ko'ra olmaydi → 404."""
    other_user = await make_user("store")
    other_store = await make_store(user_id=other_user.id)
    contract = await make_contract(store_id=other_store.id)

    token = await get_token(contracts_client, store_user)
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_admin_sees_all_contracts(
    contracts_client: AsyncClient,
    admin_user,
    make_user,
    make_store,
    make_contract,
) -> None:
    """Admin barchaning shartnomalarini ko'radi."""
    agent_a = await make_user("agent")
    agent_b = await make_user("agent")
    store_a = await make_store(agent_id=agent_a.id)
    store_b = await make_store(agent_id=agent_b.id)
    await make_contract(store_id=store_a.id, number="A-001")
    await make_contract(store_id=store_b.id, number="B-001")

    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.get(
        "/contracts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_agent_create_contract_for_own_store(
    contracts_client: AsyncClient,
    agent_user,
    make_store,
) -> None:
    """Agent o'z do'koni uchun shartnoma yaratadi (ADR-003: contracts:create ruxsati bor) → 201."""
    store = await make_store(agent_id=agent_user.id)
    token = await get_token(contracts_client, agent_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "AGENT-CREATE-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["store_id"] == str(store.id)
    assert data["number"] == "AGENT-CREATE-001"


@pytest.mark.asyncio
async def test_store_user_create_contract_not_allowed(
    contracts_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """Do'kon foydalanuvchisi shartnoma yarata olmaydi → 403."""
    store = await make_store(user_id=store_user.id)
    token = await get_token(contracts_client, store_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "STORE-CREATE-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_cannot_delete_contract(
    contracts_client: AsyncClient,
    agent_user,
    make_store,
    make_contract,
) -> None:
    """Agent shartnoma o'chira olmaydi (RBAC: contracts:delete yo'q) → 403."""
    store = await make_store(agent_id=agent_user.id)
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, agent_user)
    resp = await contracts_client.delete(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_list_only_own_contracts(
    contracts_client: AsyncClient,
    agent_user,
    make_user,
    make_store,
    make_contract,
) -> None:
    """Agent list da faqat o'z do'konlari shartnomalarini ko'radi."""
    other_agent = await make_user("agent")
    own_store = await make_store(agent_id=agent_user.id)
    other_store = await make_store(agent_id=other_agent.id)

    await make_contract(store_id=own_store.id, number="OWN-001")
    await make_contract(store_id=own_store.id, number="OWN-002")
    await make_contract(store_id=other_store.id, number="OTHER-001")

    token = await get_token(contracts_client, agent_user)
    resp = await contracts_client.get(
        "/contracts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["store_id"] == str(own_store.id)


# ─── 6. RBAC testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_courier_cannot_access_contracts(
    contracts_client: AsyncClient,
    courier_user,
) -> None:
    """Kuryer (courier roli) shartnomalar ro'yxatiga kira olmaydi → 403."""
    token = await get_token(contracts_client, courier_user)
    resp = await contracts_client.get(
        "/contracts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_accountant_can_view_and_edit_but_not_delete(
    contracts_client: AsyncClient,
    accountant_user,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Buxgalter ko'radi va tahrirlaydi, lekin o'chira olmaydi va yarata olmaydi."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, accountant_user)
    admin_token = await get_token(contracts_client, admin_user)
    today = _today()

    # view OK
    resp = await contracts_client.get(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # edit OK
    resp_edit = await contracts_client.patch(
        f"/contracts/{contract.id}",
        json={"number": "BX-EDITED", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_edit.status_code == 200

    # delete → 403
    resp_del = await contracts_client.delete(
        f"/contracts/{contract.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_del.status_code == 403

    # create → 403 (accountant contracts:create yo'q)
    resp_create = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "BX-CREATE-DENIED",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_create.status_code == 403


# ─── 7. Version conflict va idempotentlik ────────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict_returns_409(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Noto'g'ri version → 409."""
    store = await make_store()
    contract = await make_contract(store_id=store.id)
    token = await get_token(contracts_client, admin_user)
    resp = await contracts_client.patch(
        f"/contracts/{contract.id}",
        json={"number": "NEW-VER", "version": 999},  # noto'g'ri version
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["message_key"] == "contracts.version_conflict"


@pytest.mark.asyncio
async def test_idempotent_create(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
) -> None:
    """Bir xil client_uuid bilan ikki marta POST → bitta shartnoma qaytadi."""
    store = await make_store()
    token = await get_token(contracts_client, admin_user)
    today = _today()
    client_uuid = str(uuid.uuid4())

    payload = {
        "store_id": str(store.id),
        "number": "IDEM-001",
        "valid_from": today.isoformat(),
        "valid_to": (today + timedelta(days=30)).isoformat(),
        "client_uuid": client_uuid,
    }

    resp1 = await contracts_client.post(
        "/contracts",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201, resp1.text

    resp2 = await contracts_client.post(
        "/contracts",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    # Ikkinchi so'rovda ham 201 (yoki 200) — bir xil ID qaytadi
    assert resp2.status_code in (200, 201), resp2.text
    assert resp1.json()["id"] == resp2.json()["id"]


# ─── 8. list_expiring ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_expiring_service(
    db_session,
    make_store,
    make_contract,
) -> None:
    """list_expiring servis funksiyasi muddati tugayotganlarni qaytaradi."""
    store = await make_store()
    today = _today()

    # Expiring: 15 kun qoldi
    c_expiring = await make_contract(
        store_id=store.id, number="EXP-15",
        valid_from=today, valid_to=today + timedelta(days=15),
    )
    # Active: 90 kun qoldi
    await make_contract(
        store_id=store.id, number="ACT-90",
        valid_from=today, valid_to=today + timedelta(days=90),
    )
    # Expired: kecha tugagan
    await make_contract(
        store_id=store.id, number="PAST-1",
        valid_from=today - timedelta(days=60), valid_to=today - timedelta(days=1),
    )

    result = await service.list_expiring(db_session)
    ids = [c.id for c in result]
    assert c_expiring.id in ids
    # Active va expired bo'lmasligi kerak
    for c in result:
        assert c.number not in ("ACT-90", "PAST-1")


@pytest.mark.asyncio
async def test_list_expiring_agent_scope(
    db_session,
    make_user,
    make_store,
    make_contract,
) -> None:
    """list_expiring agent scope'ini hurmat qiladi."""
    agent_a = await make_user("agent")
    agent_b = await make_user("agent")
    store_a = await make_store(agent_id=agent_a.id)
    store_b = await make_store(agent_id=agent_b.id)
    today = _today()

    c_a = await make_contract(
        store_id=store_a.id, number="EXPIRING-A",
        valid_from=today, valid_to=today + timedelta(days=10),
    )
    c_b = await make_contract(
        store_id=store_b.id, number="EXPIRING-B",
        valid_from=today, valid_to=today + timedelta(days=10),
    )

    result_a = await service.list_expiring(db_session, user=agent_a)
    result_b = await service.list_expiring(db_session, user=agent_b)

    assert c_a.id in [c.id for c in result_a]
    assert c_b.id not in [c.id for c in result_a]
    assert c_b.id in [c.id for c in result_b]
    assert c_a.id not in [c.id for c in result_b]


# ─── 9. i18n ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_i18n_not_found_uz(
    contracts_client: AsyncClient,
    admin_user,
) -> None:
    """Mavjud bo'lmagan shartnoma → 404 + uz xabar."""
    token = await get_token(contracts_client, admin_user)
    fake_id = uuid.uuid4()
    resp = await contracts_client.get(
        f"/contracts/{fake_id}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "contracts.not_found"
    assert "topilmadi" in data["message"].lower()


@pytest.mark.asyncio
async def test_i18n_not_found_ru(
    contracts_client: AsyncClient,
    admin_user,
) -> None:
    """Mavjud bo'lmagan shartnoma → 404 + ru xabar."""
    token = await get_token(contracts_client, admin_user)
    fake_id = uuid.uuid4()
    resp = await contracts_client.get(
        f"/contracts/{fake_id}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "contracts.not_found"
    assert "не найден" in data["message"].lower()


@pytest.mark.asyncio
async def test_i18n_duplicate_number_uz(
    contracts_client: AsyncClient,
    admin_user,
    make_store,
    make_contract,
) -> None:
    """Dublikat number → 409 + uz xabar."""
    store = await make_store()
    await make_contract(store_id=store.id, number="DUP-I18N")
    token = await get_token(contracts_client, admin_user)
    today = _today()
    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "DUP-I18N",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["message_key"] == "contracts.duplicate_number"
    assert "allaqachon mavjud" in data["message"].lower()


# ─── 10. Contract model status property ──────────────────────────────────────


def test_contract_status_property_expired() -> None:
    """Contract.status — expired."""
    today = _today()
    c = Contract(
        store_id=uuid.uuid4(),
        number="TEST",
        valid_from=today - timedelta(days=60),
        valid_to=today - timedelta(days=1),
        version=1,
    )
    assert c.status == "expired"


def test_contract_status_property_expiring() -> None:
    """Contract.status — expiring."""
    today = _today()
    c = Contract(
        store_id=uuid.uuid4(),
        number="TEST",
        valid_from=today,
        valid_to=today + timedelta(days=CONTRACT_EXPIRING_DAYS - 5),
        version=1,
    )
    assert c.status == "expiring"


def test_contract_status_property_active() -> None:
    """Contract.status — active."""
    today = _today()
    c = Contract(
        store_id=uuid.uuid4(),
        number="TEST",
        valid_from=today,
        valid_to=today + timedelta(days=CONTRACT_EXPIRING_DAYS + 10),
        version=1,
    )
    assert c.status == "active"


def test_contract_status_property_expiring_boundary() -> None:
    """Contract.status — valid_to == bugun + 30 kun = expiring chegarasi."""
    today = _today()
    c = Contract(
        store_id=uuid.uuid4(),
        number="TEST",
        valid_from=today,
        valid_to=today + timedelta(days=CONTRACT_EXPIRING_DAYS),  # aniq chegara
        version=1,
    )
    assert c.status == "expiring"


# ─── 11. PDF magic bytes storage validatsiyasi ───────────────────────────────


@pytest.mark.asyncio
async def test_storage_pdf_magic_bytes_accepted(fake_storage) -> None:
    """FakeStorage PDF magic bytes qabul qiladi."""
    from fastapi import UploadFile
    import io

    pdf_bytes = _make_pdf_bytes()
    file = UploadFile(
        filename="contract.pdf",
        file=io.BytesIO(pdf_bytes),
    )
    url = await fake_storage.upload_contract_file(file)
    assert url.endswith(".pdf")
    assert "contracts/" in url


@pytest.mark.asyncio
async def test_storage_exe_magic_bytes_rejected(fake_storage) -> None:
    """FakeStorage EXE magic bytes rad etadi."""
    from fastapi import UploadFile
    from app.core.errors import AppError
    import io

    exe_bytes = _make_exe_bytes()
    file = UploadFile(
        filename="bad.exe",
        file=io.BytesIO(exe_bytes),
    )
    with pytest.raises(AppError) as exc_info:
        await fake_storage.upload_contract_file(file)
    assert exc_info.value.message_key == "contracts.invalid_file"
    assert exc_info.value.status_code == 422


# ─── 12. ADR-003: Agent shartnoma tuzish testlari ────────────────────────────


@pytest.mark.asyncio
async def test_agent_create_contract_supplier_is_agent_enterprise(
    contracts_client: AsyncClient,
    agent_user,
    make_store,
    db_session,
) -> None:
    """
    ADR-003 (a): Agent shartnoma tuzadi — supplier_enterprise_id = agent.enterprise_id.

    Server-avtoritar: klient supplier_enterprise_id bera olmaydi.
    Shartnoma agent biriktirilgan do'kon uchun tuziladi.
    """
    from sqlalchemy import select as sa_select
    from app.models.contract import Contract as _Contract

    store = await make_store(agent_id=agent_user.id)
    token = await get_token(contracts_client, agent_user)
    today = _today()

    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(store.id),
            "number": "AGENT-SUPPLIER-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=60)).isoformat(),
            "contract_type": "trade",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["store_id"] == str(store.id)
    assert data["number"] == "AGENT-SUPPLIER-001"

    # supplier_enterprise_id = agent.enterprise_id (server-avtoritar)
    stmt = sa_select(_Contract).where(_Contract.id == uuid.UUID(data["id"]))
    result = await db_session.execute(stmt)
    contract = result.scalar_one_or_none()
    assert contract is not None
    assert contract.supplier_enterprise_id == agent_user.enterprise_id, (
        f"supplier_enterprise_id={contract.supplier_enterprise_id} != "
        f"agent.enterprise_id={agent_user.enterprise_id}"
    )


@pytest.mark.asyncio
async def test_agent_cannot_create_contract_for_other_store(
    contracts_client: AsyncClient,
    agent_user,
    make_user,
    make_store,
) -> None:
    """
    Agent boshqa agentning do'koni uchun shartnoma tuzib bo'lmaydi (scope) → 404.
    """
    other_agent = await make_user("agent")
    other_store = await make_store(agent_id=other_agent.id)
    token = await get_token(contracts_client, agent_user)
    today = _today()

    resp = await contracts_client.post(
        "/contracts",
        json={
            "store_id": str(other_store.id),
            "number": "AGENT-OTHER-001",
            "valid_from": today.isoformat(),
            "valid_to": (today + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Scope tekshiruvi: boshqa do'kon → 404 (mavjudlikni oshkor qilmaslik)
    assert resp.status_code == 404, resp.text
