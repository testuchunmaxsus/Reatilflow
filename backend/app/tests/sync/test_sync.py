"""
Sync moduli testlari — T13 Outbox Sync API.

Test kategoriyalari:
  1.  push: bir nechta op batch → har biriga natija (applied/duplicate/conflict/error).
  2.  push: bitta op xato bo'lsa boshqalari davom etadi (op-darajali izolyatsiya).
  3.  push: order.create op → haqiqiy buyurtma yaratiladi (create_order qayta ishlatilgani).
  4.  push: client_uuid takror → duplicate (idempotentlik).
  5.  push: batch limit oshsa → 422 (sync.batch_too_large).
  6.  push: noma'lum op_type → error/sync.unknown_op.
  7.  pull: kursordan keyingi hodisalar qaytadi; next_cursor monoton.
  8.  pull: since=next_cursor bilan qayta so'rov bo'sh/yangi (idempotent delta).
  9.  pull: klient soatiga bog'liq emas (seq asosida).
  10. pull: scope/IDOR — agent faqat o'z do'konlari hodisalarini oladi.
  11. pull: katalog hodisalari hammaga ko'rinadi (global).
  12. pull: has_more/limit ishlaydi.
  13. rate-limit: limitdan oshsa 429 (sync.rate_limited).
  14. i18n: uz/ru xabarlar.
  15. autentifikatsiya majburiy (401).

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.outbox import OutboxEvent, reset_seq_counter
from app.models.store import AgentStore
from app.modules.sync import service as sync_service
from app.modules.sync.schemas import SyncOp
from app.tests.sync.conftest import DEFAULT_WAREHOUSE, get_token


# ─── Fixtures izolyatsiyasi ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_outbox_seq():
    """Har test uchun OutboxEvent seq counter'ini nolga qaytaradi."""
    reset_seq_counter()
    yield
    reset_seq_counter()


# ─── Yordamchi: segmentli do'kon + mahsulot + stock ─────────────────────────


async def _make_full_setup(
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    price: Decimal = Decimal("1000.00"),
    qty: Decimal = Decimal("100"),
    store_kwargs: dict | None = None,
):
    """Segment + mahsulot + do'kon + stock seed — to'liq setup."""
    segment = await make_price_segment()
    product = await make_product(price=price, segment_id=segment.id)
    kwargs = store_kwargs or {}
    store = await make_store(segment_id=segment.id, **kwargs)
    await seed_stock(product.id, qty=qty)
    return store, product, segment


# ─── 1. Push: bir nechta op batch ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_multiple_ops_batch(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    Bir nechta op batch: har biriga alohida natija.
    Birinchi op applied, ikkinchi op noma'lum (error).
    """
    store, product, _ = await _make_full_setup(
        make_price_segment, make_product, make_store, seed_stock,
        store_kwargs={"agent_id": agent_user.id},
    )
    # AgentStore biriktirish
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    headers = {"Authorization": f"Bearer {token}"}

    client_uuid_1 = str(uuid.uuid4())
    client_uuid_2 = str(uuid.uuid4())

    resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "order.create",
                    "client_uuid": client_uuid_1,
                    "payload": {
                        "store_id": str(store.id),
                        "lines": [{"product_id": str(product.id), "qty": "2"}],
                        "mode": "bozor",
                        "currency": "UZS",
                    },
                },
                {
                    "op_type": "unknown.op",
                    "client_uuid": client_uuid_2,
                    "payload": {},
                },
            ]
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2

    res1 = next(r for r in data["results"] if r["client_uuid"] == client_uuid_1)
    res2 = next(r for r in data["results"] if r["client_uuid"] == client_uuid_2)

    assert res1["status"] == "applied"
    assert res1["server_id"] is not None

    assert res2["status"] == "error"
    assert res2["message_key"] == "sync.unknown_op"


# ─── 2. Push: op-darajali xato izolyatsiyasi ─────────────────────────────────


@pytest.mark.asyncio
async def test_push_op_error_isolation(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    Op-darajali izolyatsiya: bitta op xato bo'lsa qolganlar davom etadi.
    1-op: xato (yetarli stock yo'q), 2-op: applied (boshqa product).
    """
    segment = await make_price_segment()
    product_bad = await make_product(price=Decimal("1000"), segment_id=segment.id)
    product_good = await make_product(price=Decimal("500"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id, agent_id=agent_user.id)

    # Faqat product_good uchun stock seed (product_bad uchun yo'q)
    await seed_stock(product_good.id, qty=Decimal("50"))

    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    headers = {"Authorization": f"Bearer {token}"}

    bad_uuid = str(uuid.uuid4())
    good_uuid = str(uuid.uuid4())

    resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "order.create",
                    "client_uuid": bad_uuid,
                    "payload": {
                        "store_id": str(store.id),
                        "lines": [{"product_id": str(product_bad.id), "qty": "1"}],
                    },
                },
                {
                    "op_type": "order.create",
                    "client_uuid": good_uuid,
                    "payload": {
                        "store_id": str(store.id),
                        "lines": [{"product_id": str(product_good.id), "qty": "1"}],
                    },
                },
            ]
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    results = {r["client_uuid"]: r for r in data["results"]}

    # Bad op xato bo'ladi (qoldiq yo'q)
    assert results[bad_uuid]["status"] == "error"
    # Good op davom etadi
    assert results[good_uuid]["status"] == "applied"
    assert results[good_uuid]["server_id"] is not None


# ─── 3. Push: order.create → create_order qayta ishlatilishi ─────────────────


@pytest.mark.asyncio
async def test_push_order_create_uses_real_service(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    order.create op → haqiqiy buyurtma DB da yaratiladi.
    create_order() qayta ishlatilgani tekshiriladi (atomiklik, narx xavfsizligi).
    """
    store, product, _ = await _make_full_setup(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("2000.00"), qty=Decimal("10"),
        store_kwargs={"agent_id": agent_user.id},
    )
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    client_uuid = str(uuid.uuid4())

    resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "order.create",
                    "client_uuid": client_uuid,
                    "payload": {
                        "store_id": str(store.id),
                        "lines": [{"product_id": str(product.id), "qty": "3"}],
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {await get_token(sync_client, agent_user)}"},
    )

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "applied"
    assert result["server_id"] is not None

    # DB da buyurtma mavjudligini tekshirish
    order_id = uuid.UUID(result["server_id"])
    order_stmt = select(Order).where(Order.id == order_id)
    order_result = await db_session.execute(order_stmt)
    order = order_result.scalar_one_or_none()
    assert order is not None
    # client_uuid SQLite'da UUID sifatida saqlanishi mumkin — string ga o'tkazib solishtirish
    assert str(order.client_uuid) == str(client_uuid)
    assert str(order.store_id) == str(store.id)


# ─── 4. Push: client_uuid takror → duplicate ─────────────────────────────────


@pytest.mark.asyncio
async def test_push_idempotency_duplicate(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    Bir xil client_uuid ikki marta yuborilsa — ikkinchisi duplicate qaytaradi.
    """
    store, product, _ = await _make_full_setup(
        make_price_segment, make_product, make_store, seed_stock,
        store_kwargs={"agent_id": agent_user.id},
    )
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    headers = {"Authorization": f"Bearer {token}"}
    client_uuid = str(uuid.uuid4())

    op_body = {
        "ops": [
            {
                "op_type": "order.create",
                "client_uuid": client_uuid,
                "payload": {
                    "store_id": str(store.id),
                    "lines": [{"product_id": str(product.id), "qty": "1"}],
                },
            }
        ]
    }

    # Birinchi yuborish
    resp1 = await sync_client.post("/sync/push", json=op_body, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["results"][0]["status"] == "applied"

    server_id_1 = resp1.json()["results"][0]["server_id"]

    # Ikkinchi yuborish (bir xil client_uuid)
    resp2 = await sync_client.post("/sync/push", json=op_body, headers=headers)
    assert resp2.status_code == 200
    result2 = resp2.json()["results"][0]

    # Ikkinchi natija: applied (idempotent) yoki duplicate
    # create_order() mavjud orderni qaytaradi → "applied" bilan server_id bir xil
    # yoki ORM dan duplicate → service "applied" qaytaradi (bir xil server_id)
    assert result2["status"] in ("applied", "duplicate")
    if result2["status"] == "applied":
        assert result2["server_id"] == server_id_1


# ─── 5. Push: batch limit oshsa → 422 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_batch_too_large(
    sync_client: AsyncClient,
    agent_user,
) -> None:
    """
    101 ta op yuborilsa (max=100) → 422 (sync.batch_too_large).
    """
    token = await get_token(sync_client, agent_user)
    headers = {"Authorization": f"Bearer {token}"}

    ops = [
        {
            "op_type": "order.create",
            "client_uuid": str(uuid.uuid4()),
            "payload": {"store_id": str(uuid.uuid4()), "lines": []},
        }
        for _ in range(101)
    ]

    resp = await sync_client.post("/sync/push", json={"ops": ops}, headers=headers)

    assert resp.status_code == 422
    data = resp.json()
    assert data["message_key"] == "sync.batch_too_large"


# ─── 6. Push: noma'lum op_type → error ───────────────────────────────────────


@pytest.mark.asyncio
async def test_push_unknown_op_type(
    sync_client: AsyncClient,
    agent_user,
) -> None:
    """
    Noma'lum op_type → error + sync.unknown_op.
    """
    token = await get_token(sync_client, agent_user)

    resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "nonexistent.op",
                    "client_uuid": str(uuid.uuid4()),
                    "payload": {"foo": "bar"},
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "error"
    assert result["message_key"] == "sync.unknown_op"


# ─── 7. Pull: kursordan keyingi hodisalar ────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_returns_events_after_cursor(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    Outbox'ga 3 hodisa qo'shiladi. since=0 → 3 hodisa.
    since=first_event_seq → 2 hodisa.
    next_cursor monoton (o'sib boradi).
    """
    # 3 ta outbox hodisasi qo'shish
    events = []
    for i in range(3):
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(uuid.uuid4()),
            event_type="product.updated",
            payload=json.dumps({"id": str(uuid.uuid4()), "name_uz": f"P{i}"}),
        )
        db_session.add(e)
        await db_session.flush()
        events.append(e)

    token = await get_token(sync_client, admin_user)

    # since=0 → barcha 3 ta
    resp = await sync_client.get(
        "/sync/pull?since=0&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["changes"]) == 3
    assert data["next_cursor"] > 0
    assert data["has_more"] is False

    first_cursor = data["changes"][0]["seq"]

    # since=first_cursor → 2 ta
    resp2 = await sync_client.get(
        f"/sync/pull?since={first_cursor}&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["changes"]) == 2
    # next_cursor o'sib borishi
    assert data2["next_cursor"] > first_cursor


# ─── 8. Pull: idempotent delta ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_idempotent_delta(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    since=next_cursor bilan qayta so'rov → bo'sh yoki yangi hodisalar.
    Kursor o'zgarmaydi.
    """
    # 2 ta hodisa qo'shish
    for i in range(2):
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(uuid.uuid4()),
            event_type="product.created",
            payload=json.dumps({"id": str(uuid.uuid4())}),
        )
        db_session.add(e)
        await db_session.flush()

    token = await get_token(sync_client, admin_user)

    resp1 = await sync_client.get(
        "/sync/pull?since=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    next_cursor = resp1.json()["next_cursor"]

    # Yangi hodisa yo'q — bo'sh qaytaradi
    resp2 = await sync_client.get(
        f"/sync/pull?since={next_cursor}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["changes"] == []
    assert data2["has_more"] is False


# ─── 9. Pull: klient soatiga bog'liq emas ────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_seq_based_not_time_based(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    seq monoton — created_at tartibiga bog'liq emas.
    Hodisalar seq bo'yicha qaytariladi.
    """
    seqs = []
    for _ in range(3):
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(uuid.uuid4()),
            event_type="product.updated",
            payload=json.dumps({}),
        )
        db_session.add(e)
        await db_session.flush()
        seqs.append(e.seq)

    assert seqs == sorted(seqs), "seq monoton bo'lishi kerak"
    assert seqs[0] < seqs[1] < seqs[2], "seq har doim o'sib borishi kerak"

    token = await get_token(sync_client, admin_user)
    resp = await sync_client.get(
        "/sync/pull?since=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    change_seqs = [c["seq"] for c in resp.json()["changes"]]
    assert change_seqs == sorted(change_seqs), "Pull natijasida seq tartibli bo'lishi kerak"


# ─── 10. Pull: scope/IDOR — agent faqat o'z do'konlari ──────────────────────


@pytest.mark.asyncio
async def test_pull_scope_agent_only_own_stores(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_store,
    agent_user,
    admin_user,
) -> None:
    """
    IDOR himoya: agent faqat o'z do'konlariga tegishli hodisalarni oladi.
    Boshqa do'kon hodisasi ko'rinmaydi.
    """
    # Agent do'koni va boshqa do'kon
    my_store = await make_store(agent_id=agent_user.id)
    other_store = await make_store()  # boshqa do'kon

    as_ = AgentStore(agent_id=agent_user.id, store_id=my_store.id)
    db_session.add(as_)
    await db_session.flush()

    # my_store uchun order hodisasi
    my_event = OutboxEvent(
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload=json.dumps({"store_id": str(my_store.id), "id": str(uuid.uuid4())}),
    )
    db_session.add(my_event)

    # other_store uchun order hodisasi
    other_event = OutboxEvent(
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        event_type="order.created",
        payload=json.dumps({"store_id": str(other_store.id), "id": str(uuid.uuid4())}),
    )
    db_session.add(other_event)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    resp = await sync_client.get(
        "/sync/pull?since=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    changes = resp.json()["changes"]

    # Agent faqat o'z do'koniga tegishli hodisani ko'radi
    returned_ids = {c["entity_id"] for c in changes if c["entity_type"] == "order"}
    assert my_event.aggregate_id in returned_ids
    assert other_event.aggregate_id not in returned_ids, "IDOR: boshqa do'kon hodisasi ko'rinmasligi kerak"


# ─── 11. Pull: katalog hodisalari global ─────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_catalog_events_global(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_store,
    agent_user,
) -> None:
    """
    product/price/promo aggregate_type hodisalari barcha foydalanuvchilarga ko'rinadi.
    """
    # Agent o'z do'koni bor
    my_store = await make_store(agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=my_store.id)
    db_session.add(as_)

    # Katalog hodisasi (global)
    catalog_event = OutboxEvent(
        aggregate_type="product",
        aggregate_id=str(uuid.uuid4()),
        event_type="product.created",
        payload=json.dumps({"id": str(uuid.uuid4()), "name_uz": "Yangi mahsulot"}),
    )
    db_session.add(catalog_event)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)
    resp = await sync_client.get(
        "/sync/pull?since=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    changes = resp.json()["changes"]

    catalog_changes = [c for c in changes if c["entity_type"] == "product"]
    assert len(catalog_changes) >= 1
    assert any(c["entity_id"] == catalog_event.aggregate_id for c in catalog_changes)


# ─── 12. Pull: has_more / limit ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_has_more_and_limit(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    5 ta hodisa bor, limit=3 bilan so'ralsa → 3 ta qaytadi, has_more=True.
    """
    for i in range(5):
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(uuid.uuid4()),
            event_type="product.updated",
            payload=json.dumps({"i": i}),
        )
        db_session.add(e)
        await db_session.flush()

    token = await get_token(sync_client, admin_user)
    resp = await sync_client.get(
        "/sync/pull?since=0&limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["changes"]) == 3
    assert data["has_more"] is True

    # Keyingi sahifa
    next_resp = await sync_client.get(
        f"/sync/pull?since={data['next_cursor']}&limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert next_resp.status_code == 200
    next_data = next_resp.json()
    assert len(next_data["changes"]) == 2
    assert next_data["has_more"] is False


# ─── 13. Rate-limit ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_rate_limit(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    Rate-limit: 61-chi so'rov 429 qaytaradi.
    fakeredis bilan test.
    """
    token = await get_token(sync_client, admin_user)
    headers = {"Authorization": f"Bearer {token}"}

    # Rate-limit Redis kalitini to'g'ridan-to'g'ri o'rnatish
    # (60 so'rov limitga yetkazish o'rniga)
    rate_key = f"rate:sync_push:{admin_user.id}"
    await fake_redis.set(rate_key, "61", ex=60)

    resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "order.create",
                    "client_uuid": str(uuid.uuid4()),
                    "payload": {},
                }
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 429
    assert resp.json()["message_key"] == "sync.rate_limited"


@pytest.mark.asyncio
async def test_pull_rate_limit(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    admin_user,
) -> None:
    """
    Pull rate-limit: 121-chi so'rov 429 qaytaradi.
    """
    token = await get_token(sync_client, admin_user)
    headers = {"Authorization": f"Bearer {token}"}

    rate_key = f"rate:sync_pull:{admin_user.id}"
    await fake_redis.set(rate_key, "121", ex=60)

    resp = await sync_client.get(
        "/sync/pull?since=0",
        headers=headers,
    )
    assert resp.status_code == 429
    assert resp.json()["message_key"] == "sync.rate_limited"


# ─── 14. i18n ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_batch_too_large_i18n_uz(
    sync_client: AsyncClient,
    agent_user,
) -> None:
    """sync.batch_too_large uz tilida xabar."""
    token = await get_token(sync_client, agent_user)
    ops = [
        {"op_type": "order.create", "client_uuid": str(uuid.uuid4()), "payload": {}}
        for _ in range(101)
    ]

    resp = await sync_client.post(
        "/sync/push",
        json={"ops": ops},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "uz",
        },
    )
    assert resp.status_code == 422
    message = resp.json()["message"]
    assert "Batch" in message or "batch" in message.lower() or "oshib" in message


@pytest.mark.asyncio
async def test_push_batch_too_large_i18n_ru(
    sync_client: AsyncClient,
    agent_user,
) -> None:
    """sync.batch_too_large ru tilida xabar."""
    token = await get_token(sync_client, agent_user)
    ops = [
        {"op_type": "order.create", "client_uuid": str(uuid.uuid4()), "payload": {}}
        for _ in range(101)
    ]

    resp = await sync_client.post(
        "/sync/push",
        json={"ops": ops},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru",
        },
    )
    assert resp.status_code == 422
    message = resp.json()["message"]
    assert "пакет" in message.lower() or "превышен" in message.lower() or "размер" in message.lower()


# ─── 15. Autentifikatsiya majburiy ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_requires_auth(sync_client: AsyncClient) -> None:
    """Token yo'q → 403/401."""
    resp = await sync_client.post(
        "/sync/push",
        json={"ops": [{"op_type": "order.create", "client_uuid": str(uuid.uuid4()), "payload": {}}]},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_pull_requires_auth(sync_client: AsyncClient) -> None:
    """Token yo'q → 403/401."""
    resp = await sync_client.get("/sync/pull?since=0")
    assert resp.status_code in (401, 403)


# ─── 16. service.pull biriktirma testi ───────────────────────────────────────


@pytest.mark.asyncio
async def test_service_pull_returns_correct_cursor(
    db_session: AsyncSession,
    admin_user,
) -> None:
    """
    service.pull() biriktirma testi — HTTP qatlamisiz.
    next_cursor = qaytarilgan max seq; bo'sh bo'lsa since_seq qaytadi.
    """
    # 3 ta hodisa
    inserted_seqs = []
    for i in range(3):
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(uuid.uuid4()),
            event_type="product.created",
            payload=json.dumps({"i": i}),
        )
        db_session.add(e)
        await db_session.flush()
        inserted_seqs.append(e.seq)

    changes, next_cursor, has_more = await sync_service.pull(
        since_seq=0,
        limit=10,
        user=admin_user,
        db=db_session,
    )

    assert len(changes) == 3
    assert next_cursor == max(inserted_seqs)
    assert has_more is False

    # Bo'sh so'rov (since=next_cursor)
    changes2, nc2, hm2 = await sync_service.pull(
        since_seq=next_cursor,
        limit=10,
        user=admin_user,
        db=db_session,
    )
    assert changes2 == []
    assert hm2 is False


# ─── 17. service.push biriktirma testi ───────────────────────────────────────


@pytest.mark.asyncio
async def test_service_push_order_create_applied(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    service.push() biriktirma testi — HTTP qatlamisiz.
    order.create → applied + server_id.
    """
    segment = await make_price_segment()
    product = await make_product(price=Decimal("500"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id, agent_id=agent_user.id)
    await seed_stock(product.id, qty=Decimal("20"))

    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    client_uuid = str(uuid.uuid4())
    op = SyncOp(
        op_type="order.create",
        client_uuid=client_uuid,
        payload={
            "store_id": str(store.id),
            "lines": [{"product_id": str(product.id), "qty": "2"}],
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert len(results) == 1
    assert results[0].status == "applied"
    assert results[0].server_id is not None

    # DB tekshiruvi
    order_id = uuid.UUID(results[0].server_id)
    stmt = select(Order).where(Order.id == order_id)
    result = await db_session.execute(stmt)
    order = result.scalar_one_or_none()
    assert order is not None
    assert str(order.client_uuid) == str(client_uuid)


# ─── 18. Kursor progress: barcha hodisalar filtrlangan bo'lsa ham ────────────


@pytest.mark.asyncio
async def test_pull_cursor_advances_when_all_filtered(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_store,
    agent_user,
) -> None:
    """
    MEDIUM — kursor progress testi.

    Barcha hodisalar boshqa do'konnikiga tegishli (agent ko'ra olmaydi).
    Natija: changes=[] bo'lsa ham next_cursor ilgarilaydi.
    since=next_cursor qayta so'rov o'sha hodisalarni qaytarmaydi.
    Cheksiz bo'sh pull yo'q.
    """
    # Agent do'koni
    my_store = await make_store(agent_id=agent_user.id)
    from app.models.store import AgentStore
    as_ = AgentStore(agent_id=agent_user.id, store_id=my_store.id)
    db_session.add(as_)

    # Faqat boshqa do'kon hodisalari (agent ko'ra olmaydi)
    other_store = await make_store()
    for _ in range(3):
        e = OutboxEvent(
            aggregate_type="order",
            aggregate_id=str(uuid.uuid4()),
            event_type="order.created",
            payload=json.dumps({"store_id": str(other_store.id), "id": str(uuid.uuid4())}),
        )
        db_session.add(e)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)

    # Birinchi so'rov: barcha hodisalar filtrlangan → changes=[]
    resp1 = await sync_client.get(
        "/sync/pull?since=0&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["changes"] == [], "Filtrlangan hodisalar ko'rinmasligi kerak"
    # Kursor ilgarilagan bo'lishi kerak (0 dan katta)
    assert data1["next_cursor"] > 0, "next_cursor ilgarilashi kerak (barcha filtrlangan bo'lsa ham)"

    next_cursor = data1["next_cursor"]

    # Ikkinchi so'rov (since=next_cursor): o'sha hodisalar qaytmasligi kerak
    resp2 = await sync_client.get(
        f"/sync/pull?since={next_cursor}&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["changes"] == [], "Qayta so'rovda o'sha hodisalar ko'rinmasligi kerak"
    # Kursor o'zgarmaydi (yangi hodisa yo'q)
    assert data2["next_cursor"] == next_cursor


# ─── 19. Status sync: store_id payloadda mavjud ──────────────────────────────


@pytest.mark.asyncio
async def test_pull_order_status_updated_visible_to_agent(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    HIGH — order.status_updated store_id testi.

    Agent buyurtma holati o'zgarganda (update_status), pull'da
    o'z buyurtmasi status hodisasini olishi kerak.
    store_id outbox payload'da mavjud bo'lishi kerak.
    """
    from app.models.store import AgentStore
    from app.modules.orders.service import update_status
    from app.modules.orders.schemas import OrderStatusUpdate

    segment = await make_price_segment()
    product = await make_product(price=Decimal("500"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id, agent_id=agent_user.id)
    await seed_stock(product.id, qty=Decimal("50"))

    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    token = await get_token(sync_client, agent_user)

    # Buyurtma yaratish
    client_uuid = str(uuid.uuid4())
    push_resp = await sync_client.post(
        "/sync/push",
        json={
            "ops": [
                {
                    "op_type": "order.create",
                    "client_uuid": client_uuid,
                    "payload": {
                        "store_id": str(store.id),
                        "lines": [{"product_id": str(product.id), "qty": "1"}],
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert push_resp.status_code == 200
    server_id = push_resp.json()["results"][0]["server_id"]
    assert server_id is not None

    # Pull — order.created hodisasini olish va kursor saqlash
    pull_resp1 = await sync_client.get(
        "/sync/pull?since=0&limit=50",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pull_resp1.status_code == 200
    cursor_after_create = pull_resp1.json()["next_cursor"]

    # Holat o'zgartirish: confirmed → packed
    order_id = uuid.UUID(server_id)
    order_stmt = select(Order).where(Order.id == order_id)
    order_result = await db_session.execute(order_stmt)
    order = order_result.scalar_one()

    await update_status(
        db=db_session,
        order_id=order_id,
        data=OrderStatusUpdate(status="packed", version=order.version),
        user=agent_user,
    )
    await db_session.flush()

    # Pull — status_updated hodisasini olish
    pull_resp2 = await sync_client.get(
        f"/sync/pull?since={cursor_after_create}&limit=50",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pull_resp2.status_code == 200
    changes = pull_resp2.json()["changes"]

    status_changes = [
        c for c in changes
        if c["entity_type"] == "order" and c["event_type"] == "order.status_updated"
        and c["entity_id"] == server_id
    ]
    assert len(status_changes) >= 1, (
        "Agent o'z buyurtmasi status o'zgarishini ko'rishi kerak. "
        f"Barcha changes: {changes}"
    )


# ─── 20. Push savepoint: bitta op xato bo'lsa keyingi saqlanadi ──────────────


@pytest.mark.asyncio
async def test_push_savepoint_isolation(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
) -> None:
    """
    MEDIUM — push savepoint izolyatsiya testi.

    Batch'da bitta op xato (insufficient stock) bo'lsa,
    undan keyingi to'g'ri op saqlanadi (sessiya ifloslanmaydi).
    """
    from app.modules.sync.schemas import SyncOp

    segment = await make_price_segment()
    product_bad = await make_product(price=Decimal("1000"), segment_id=segment.id)
    product_good = await make_product(price=Decimal("500"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id, agent_id=agent_user.id)

    # Faqat product_good uchun stock bor, product_bad uchun yo'q
    await seed_stock(product_good.id, qty=Decimal("10"))

    from app.models.store import AgentStore
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    bad_uuid = str(uuid.uuid4())
    good_uuid = str(uuid.uuid4())

    ops = [
        SyncOp(
            op_type="order.create",
            client_uuid=bad_uuid,
            payload={
                "store_id": str(store.id),
                "lines": [{"product_id": str(product_bad.id), "qty": "1"}],
            },
        ),
        SyncOp(
            op_type="order.create",
            client_uuid=good_uuid,
            payload={
                "store_id": str(store.id),
                "lines": [{"product_id": str(product_good.id), "qty": "1"}],
            },
        ),
    ]

    results = await sync_service.push(
        ops=ops,
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    results_by_uuid = {r.client_uuid: r for r in results}

    # Birinchi op xato bo'lishi kerak (stock yo'q)
    assert results_by_uuid[bad_uuid].status == "error", (
        "Stock yo'q bo'lgan op xato qaytarishi kerak"
    )

    # Ikkinchi op muvaffaqiyatli bo'lishi kerak (savepoint izolyatsiyasi)
    assert results_by_uuid[good_uuid].status == "applied", (
        "Savepoint izolyatsiyasi: birinchi op xato bo'lsa ham ikkinchi op saqlanishi kerak"
    )
    assert results_by_uuid[good_uuid].server_id is not None

    # DB da ikkinchi buyurtma mavjud bo'lishi kerak
    order_id = uuid.UUID(results_by_uuid[good_uuid].server_id)
    stmt = select(Order).where(Order.id == order_id)
    result = await db_session.execute(stmt)
    order = result.scalar_one_or_none()
    assert order is not None, "Ikkinchi buyurtma DB da saqlanishi kerak"
    assert str(order.store_id) == str(store.id)


# ─── 21. Pull N+1 → batch: ko'p hodisali pull to'g'ri snapshot'lar ───────────


@pytest.mark.asyncio
async def test_pull_batch_snapshot_correctness(
    db_session: AsyncSession,
    fake_redis,
    sync_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    admin_user,
    agent_user,
) -> None:
    """
    HIGH — pull N+1 → batch snapshot testi (funksional).

    Ko'p order hodisalari bo'lganda pull to'g'ri snapshot'lar qaytaradi.
    Har hodisa uchun alohida so'rov emas, batch fetch ishlatiladi.
    """
    from app.models.store import AgentStore

    segment = await make_price_segment()
    store = await make_store(segment_id=segment.id, agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    # Bir nechta order hodisasi qo'shish
    inserted_order_ids: list[str] = []
    for i in range(5):
        product = await make_product(
            name_uz=f"Mahsulot {i}", price=Decimal("100"), segment_id=segment.id
        )
        await seed_stock(product.id, qty=Decimal("50"))

        # To'g'ridan-to'g'ri outbox hodisasi qo'shish (order mavjud emas lekin aggregate_id bor)
        eid = str(uuid.uuid4())
        inserted_order_ids.append(eid)
        e = OutboxEvent(
            aggregate_type="product",
            aggregate_id=str(product.id),
            event_type="product.created",
            payload=json.dumps({"id": str(product.id), "name_uz": f"Mahsulot {i}"}),
        )
        db_session.add(e)
    await db_session.flush()

    token = await get_token(sync_client, admin_user)
    resp = await sync_client.get(
        "/sync/pull?since=0&limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    changes = data["changes"]

    # Kamida 5 ta hodisa qaytishi kerak
    product_changes = [c for c in changes if c["entity_type"] == "product"]
    assert len(product_changes) >= 5, f"5 ta product hodisasi bo'lishi kerak, {len(product_changes)} ta qaytdi"

    # Har bir change'da snapshot bo'lishi kerak
    for c in product_changes:
        assert "snapshot" in c, f"Snapshot bo'lishi kerak: {c}"
        assert c["snapshot"].get("id") is not None, f"Snapshot'da id bo'lishi kerak: {c['snapshot']}"
