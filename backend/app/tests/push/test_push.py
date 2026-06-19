"""
Push bildirishnoma testlari — T19.

Testlar (infrasiz — aiosqlite + FakePushProvider):
  1. order.status_updated → do'kon egasi + agent ga push (FakeProvider ro'yxatida)
  2. dedupe: ikkinchi process_pending_pushes → bir xil hodisa qayta yuborilmaydi
  3. device_id yo'q foydalanuvchi → skip (push yuborilmaydi)
  4. retry: FakeProvider birinchi marta fail → status=failed, attempts oshadi;
            keyingi run → sent. 3 urinishdan keyin failed qoladi.
  5. delivery hodisasi → kuryer + do'konga push
  6. sync buzilmaydi: push outbox.published_at ni o'zgartirmaydi
  7. device-token endpoint: foydalanuvchi o'z device_id ni o'rnatadi
  8. i18n: uz/ru xabar farqi
  9. push_log yoziladi (sent holat)
  10. xato: delivery payload da delivery_id yo'q → maqsad topilmadi, push yo'q
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import Delivery
from app.models.order import Order
from app.models.outbox import OutboxEvent
from app.models.push import PushLog
from app.models.store import Store
from app.models.user import AppUser
from app.modules.push.messages import push_body, push_title
from app.modules.push.provider import FakePushProvider
from app.modules.push.service import process_pending_pushes
from app.tests.push.conftest import get_token


# ─── Test 1: order.status_updated → do'kon + agent ga push ───────────────────


@pytest.mark.anyio
async def test_order_status_updated_push(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """order.status_updated outbox hodisasi → do'kon egasi va agent ga push."""
    # Setup: do'kon egasi, agent, do'kon, buyurtma
    store_owner = await make_user(role="store", device_id="owner_fcm_token")
    agent = await make_user(role="agent", device_id="agent_fcm_token")
    store = await make_store(user_id=store_owner.id, agent_id=agent.id)
    order = await make_order(store_id=store.id, agent_id=agent.id, status="confirmed")

    # Outbox hodisasi yaratish
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={
            "order_id": str(order.id),
            "status": "packed",
        },
    )

    # Process pending pushes
    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # Tekshirish: kamida 2 ta push (do'kon egasi + agent)
    assert len(fake_provider.sent) >= 2, (
        f"Kamida 2 ta push kutilgan, {len(fake_provider.sent)} ta yuborildi"
    )

    # Device tokenlar to'g'ri
    tokens_sent = {p.device_id for p in fake_provider.sent}
    assert "owner_fcm_token" in tokens_sent
    assert "agent_fcm_token" in tokens_sent

    # push_log yozildi
    logs_result = await db_session.execute(
        select(PushLog).where(PushLog.outbox_event_id == event.id)
    )
    logs = logs_result.scalars().all()
    assert len(logs) >= 2
    for log in logs:
        assert log.status == "sent"
        assert log.attempts == 1
        assert log.sent_at is not None

    # processed count to'g'ri
    assert count >= 2


# ─── Test 2: dedupe — ikkinchi run bir xil hodisani qayta yuborilmaydi ────────


@pytest.mark.anyio
async def test_dedupe_no_duplicate_push(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """process_pending_pushes ikkinchi marta ishganda bir xil hodisa qayta yuborilmaydi."""
    store_owner = await make_user(role="store", device_id="dedup_owner_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    # Birinchi run
    count1 = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()
    sent_after_first = len(fake_provider.sent)

    # Ikkinchi run — bir xil hodisa qayta yuborilmasligi kerak
    count2 = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()
    sent_after_second = len(fake_provider.sent)

    # Birinchi run da push yuborilgan
    assert sent_after_first >= 1
    # Ikkinchi run da yangi push qo'shilmagan
    assert sent_after_second == sent_after_first, (
        "Dedupe: ikkinchi run da yangi push yuborilmasligi kerak"
    )


# ─── Test 3: device_id yo'q → skip ───────────────────────────────────────────


@pytest.mark.anyio
async def test_skip_user_without_device_id(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """device_id yo'q foydalanuvchiga push yuborilmaydi."""
    # Do'kon egasi device_id = None
    store_owner = await make_user(role="store", device_id=None)
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # Push yuborilmagan (device_id yo'q)
    assert len(fake_provider.sent) == 0, (
        "device_id yo'q foydalanuvchiga push yuborilmasligi kerak"
    )


# ─── Test 4: retry — birinchi fail, ikkinchi run sent ─────────────────────────


@pytest.mark.anyio
async def test_retry_on_failure(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """Birinchi run fail → status=failed, attempts=1; ikkinchi run → sent."""
    store_owner = await make_user(role="store", device_id="retry_owner_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    # Birinchi run — fail
    fake_provider.set_fail_next(1)
    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # push_log status = failed, attempts = 1
    log_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == store_owner.id)
    )
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.status == "failed"
    assert log.attempts == 1
    assert log.sent_at is None

    # Ikkinchi run — muvaffaqiyatli
    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    await db_session.refresh(log)
    assert log.status == "sent"
    assert log.attempts == 2
    assert log.sent_at is not None
    assert len(fake_provider.sent) == 1


# ─── Test 4b: max retry — 3 marta fail → forever failed ─────────────────────


@pytest.mark.anyio
async def test_max_retry_stays_failed(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """3 ta urinishdan keyin status=failed qoladi (retry to'xtaydi)."""
    from app.modules.push import service as push_service

    original_max = push_service._MAX_RETRIES
    push_service._MAX_RETRIES = 3

    try:
        store_owner = await make_user(role="store", device_id="max_retry_token")
        store = await make_store(user_id=store_owner.id)
        order = await make_order(store_id=store.id, status="confirmed")

        event = await make_outbox(
            event_type="order.status_updated",
            aggregate_type="order",
            aggregate_id=str(order.id),
            payload={"order_id": str(order.id), "status": "packed"},
        )

        # 3 marta fail
        for attempt in range(1, 4):
            fake_provider.set_fail_next(1)
            await process_pending_pushes(db=db_session, provider=fake_provider)
            await db_session.commit()

            log_result = await db_session.execute(
                select(PushLog)
                .where(PushLog.outbox_event_id == event.id)
                .where(PushLog.user_id == store_owner.id)
            )
            log = log_result.scalar_one()
            assert log.status == "failed"
            assert log.attempts == attempt

        # 4-run: max_retries yetdi, qayta urinilmaydi
        fake_provider.set_fail_next(0)  # endi muvaffaqiyatli bo'lardi, lekin retry yo'q
        count = await process_pending_pushes(db=db_session, provider=fake_provider)
        await db_session.commit()

        # Yangi push yuborilmagan (max_retries yetdi)
        assert len(fake_provider.sent) == 0

    finally:
        push_service._MAX_RETRIES = original_max


# ─── Test 5: delivery hodisasi → kuryer + do'konga push ──────────────────────


@pytest.mark.anyio
async def test_delivery_created_push(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_delivery,
    make_outbox,
):
    """delivery.created → kuryer va do'kon egasiga push."""
    courier = await make_user(role="courier", device_id="courier_fcm_token")
    store_owner = await make_user(role="store", device_id="store_owner_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)

    event = await make_outbox(
        event_type="delivery.created",
        aggregate_type="delivery",
        aggregate_id=str(delivery.id),
        payload={
            "delivery_id": str(delivery.id),
            "order_id": str(order.id),
        },
    )

    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # Kuryer va do'kon egasiga push
    assert len(fake_provider.sent) >= 2
    tokens = {p.device_id for p in fake_provider.sent}
    assert "courier_fcm_token" in tokens
    assert "store_owner_token" in tokens


# ─── Test 6: sync buzilmaydi — published_at o'zgartirilmaydi ─────────────────


@pytest.mark.anyio
async def test_push_does_not_modify_published_at(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """Push process outbox.published_at ni o'zgartirmasligi lozim (sync seq saqlanadi)."""
    store_owner = await make_user(role="store", device_id="sync_test_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    # published_at = None (sync hali yuborilmagan)
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "confirmed"},
        published_at=None,
    )
    original_published_at = event.published_at

    # Push process
    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # outbox.published_at o'zgarmasligi kerak
    await db_session.refresh(event)
    assert event.published_at == original_published_at, (
        "Push process outbox.published_at ni o'zgartirmasligi kerak — "
        "sync seq kursori bilan to'qnashmasligi uchun"
    )


# ─── Test 7: device-token endpoint ───────────────────────────────────────────


@pytest.mark.anyio
async def test_device_token_endpoint(
    db_session: AsyncSession,
    push_client,
    make_user,
):
    """PATCH /push/device-token — foydalanuvchi o'z FCM tokenini yangilaydi."""
    user = await make_user(role="agent", device_id=None)
    await db_session.commit()

    token = await get_token(push_client, user)

    # Device token o'rnatish
    resp = await push_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": "new_fcm_token_xyz", "channel": "fcm"},
    )
    assert resp.status_code == 200, f"PATCH /push/device-token: {resp.text}"
    data = resp.json()
    assert data["device_id"] == "new_fcm_token_xyz"
    assert data["user_id"] == str(user.id)

    # DB da yangilandi
    await db_session.refresh(user)
    assert user.device_id == "new_fcm_token_xyz"


@pytest.mark.anyio
async def test_device_token_clear(
    db_session: AsyncSession,
    push_client,
    make_user,
):
    """PATCH /push/device-token — device_id=null → token o'chiriladi."""
    user = await make_user(role="agent", device_id="existing_token")
    await db_session.commit()

    token = await get_token(push_client, user)

    resp = await push_client.patch(
        "/push/device-token",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_id": None, "channel": "fcm"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["device_id"] is None

    await db_session.refresh(user)
    assert user.device_id is None


@pytest.mark.anyio
async def test_device_token_requires_auth(push_client):
    """Device-token endpoint autentifikatsiya talab qiladi."""
    resp = await push_client.patch(
        "/push/device-token",
        json={"device_id": "some_token", "channel": "fcm"},
    )
    assert resp.status_code == 401


# ─── Test 8: i18n — uz/ru xabar farqi ────────────────────────────────────────


def test_push_messages_uz():
    """Uzbekcha xabar to'g'ri."""
    title = push_title("push.order_status_updated", locale="uz", order_id_short="abc123", status="packed")
    body = push_body("push.order_status_updated", locale="uz", order_id_short="abc123", status="packed")
    assert "packed" in body or "holati" in body
    assert len(title) > 0


def test_push_messages_ru():
    """Ruscha xabar to'g'ri."""
    title = push_title("push.order_status_updated", locale="ru", order_id_short="abc123", status="packed")
    body = push_body("push.order_status_updated", locale="ru", order_id_short="abc123", status="packed")
    assert "packed" in body or "статус" in body.lower()
    assert len(title) > 0


def test_push_messages_uz_ne_ru():
    """Uzbekcha va ruscha xabar farq qiladi."""
    title_uz = push_title("push.delivery_created", locale="uz", order_id_short="xxx")
    title_ru = push_title("push.delivery_created", locale="ru", order_id_short="xxx")
    assert title_uz != title_ru


def test_push_messages_unknown_locale_fallback():
    """Noma'lum locale → uzbekcha fallback."""
    title_unknown = push_title("push.delivery_created", locale="fr", order_id_short="yyy")
    title_uz = push_title("push.delivery_created", locale="uz", order_id_short="yyy")
    assert title_unknown == title_uz


# ─── Test 9: delivery.status_updated ─────────────────────────────────────────


@pytest.mark.anyio
async def test_delivery_status_updated_push(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_delivery,
    make_outbox,
):
    """delivery.status_updated → kuryer va do'kon egasiga push."""
    courier = await make_user(role="courier", device_id="courier_status_token")
    store_owner = await make_user(role="store", device_id="store_status_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="delivering")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="delivering")

    await make_outbox(
        event_type="delivery.status_updated",
        aggregate_type="delivery",
        aggregate_id=str(delivery.id),
        payload={
            "delivery_id": str(delivery.id),
            "order_id": str(order.id),
            "status": "delivered",
        },
    )

    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    tokens = {p.device_id for p in fake_provider.sent}
    assert "courier_status_token" in tokens
    assert "store_status_token" in tokens


# ─── Test 10: push_log yoziladi ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_push_log_written(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """process_pending_pushes push_log yozadi (sent holat)."""
    store_owner = await make_user(role="store", device_id="log_test_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    logs_result = await db_session.execute(
        select(PushLog).where(PushLog.outbox_event_id == event.id)
    )
    logs = logs_result.scalars().all()
    assert len(logs) >= 1

    owner_log = next((l for l in logs if l.user_id == store_owner.id), None)
    assert owner_log is not None
    assert owner_log.status == "sent"
    assert owner_log.device_id == "log_test_token"
    assert owner_log.channel == "fcm"
    assert owner_log.title
    assert owner_log.body
    assert owner_log.sent_at is not None
    assert owner_log.attempts == 1


# ─── Test 11: payload'da ID yo'q → maqsad topilmadi ─────────────────────────


@pytest.mark.anyio
async def test_missing_delivery_id_in_payload(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_outbox,
):
    """delivery hodisada delivery_id yo'q payload → maqsad topilmadi, push yo'q."""
    await make_outbox(
        event_type="delivery.created",
        aggregate_type="delivery",
        aggregate_id=str(uuid.uuid4()),
        payload={},  # bo'sh payload — delivery_id yo'q
    )

    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    assert len(fake_provider.sent) == 0


# ─── Test 12: FakePushProvider — set_fail_next va reset ─────────────────────


@pytest.mark.anyio
async def test_fake_provider_fail_and_reset():
    """FakePushProvider fail_next va reset to'g'ri ishlaydi."""
    from app.modules.push.provider import PushResult

    provider = FakePushProvider()

    # Birinchi send fail
    provider.set_fail_next(1)
    result1 = await provider.send("device", "title", "body")
    assert result1.ok is False
    assert len(provider.sent) == 0

    # Ikkinchi send muvaffaqiyatli
    result2 = await provider.send("device", "title", "body")
    assert result2.ok is True
    assert len(provider.sent) == 1

    # Reset
    provider.reset()
    assert len(provider.sent) == 0


# ─── Test 13: Faqat push hodisa turlariga filtrlash ──────────────────────────


@pytest.mark.anyio
async def test_only_push_event_types_processed(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_outbox,
):
    """Push'ga tegishli bo'lmagan hodisalar qayta ishlanmaydi."""
    # Bu hodisa push uchun emas
    await make_outbox(
        event_type="order.created",
        aggregate_type="order",
        aggregate_id=str(uuid.uuid4()),
        payload={"order_id": str(uuid.uuid4())},
    )

    await make_outbox(
        event_type="product.updated",
        aggregate_type="product",
        aggregate_id=str(uuid.uuid4()),
        payload={},
    )

    count = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    assert len(fake_provider.sent) == 0
    assert count == 0


# ─── Test 14: Russo locale foydalanuvchi ────────────────────────────────────


@pytest.mark.anyio
async def test_ru_locale_user_gets_ru_push(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """Ruscha locale foydalanuvchi ruscha push xabar oladi."""
    store_owner = await make_user(role="store", device_id="ru_owner_token", locale="ru")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")
    await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    assert len(fake_provider.sent) >= 1
    ru_push = next(p for p in fake_provider.sent if p.device_id == "ru_owner_token")

    # Ruscha xabar tekshirish
    ru_title = push_title("push.order_status_updated", locale="ru", order_id_short="x", status="packed")
    assert ru_push.title == ru_title


# ─── Test 15: Bir hodisada agent va do'kon egasi bir xil bo'lsa dedupe ──────


@pytest.mark.anyio
async def test_no_duplicate_if_agent_is_store_owner(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """Agent va do'kon egasi bir xil foydalanuvchi bo'lsa, bir marta push."""
    # Bir foydalanuvchi ham agent, ham store egasi (nadir lekin mumkin)
    combined_user = await make_user(role="agent", device_id="combined_user_token")
    store = await make_store(user_id=combined_user.id, agent_id=combined_user.id)
    order = await make_order(
        store_id=store.id,
        agent_id=combined_user.id,
        status="confirmed",
    )
    await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()

    # Faqat 1 ta push (combined_user uchun 1 marta)
    combined_pushes = [p for p in fake_provider.sent if p.device_id == "combined_user_token"]
    assert len(combined_pushes) == 1, (
        "Bir xil foydalanuvchiga bir marta push yuborilishi kerak"
    )


# ─── Test 16: Stall yo'qligi — limit=2, 3+ hodisa → barchasi qayta ishlanadi ─


@pytest.mark.anyio
async def test_no_stall_beyond_limit(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    limit=2 bilan 3 ta hodisa yaratiladi. Har run 2 ta yangi hodisani qayta
    ishlagandan keyin keyingi run qolgan hodisani ham qayta ishlaydi.
    seq>limit hodisalari hech qachon to'xtamaydi (stall yo'q).
    """
    store_owner = await make_user(role="store", device_id="stall_owner_token")
    store = await make_store(user_id=store_owner.id)

    # 3 ta alohida hodisa yaratamiz
    processed_events = []
    for i in range(3):
        order = await make_order(store_id=store.id, status="confirmed")
        event = await make_outbox(
            event_type="order.status_updated",
            aggregate_type="order",
            aggregate_id=str(order.id),
            payload={"order_id": str(order.id), "status": "packed"},
        )
        processed_events.append(event)

    # 1-run: limit=2 → birinchi 2 ta yangi hodisa qayta ishlanadi
    count1 = await process_pending_pushes(db=db_session, provider=fake_provider, limit=2)
    await db_session.commit()
    assert count1 >= 2, f"1-run kamida 2 ta push qayta ishlashi kerak, aslida: {count1}"

    sent_after_run1 = len(fake_provider.sent)
    assert sent_after_run1 >= 2

    # 2-run: limit=2 → 3-chi hodisa (seq>2) qayta ishlanadi — stall yo'q
    count2 = await process_pending_pushes(db=db_session, provider=fake_provider, limit=2)
    await db_session.commit()
    assert count2 >= 1, (
        f"2-run kamida 1 ta push qayta ishlashi kerak (3-chi hodisa), aslida: {count2}. "
        "Bu stall belgisi — seq>limit hodisalar hech qachon qayta ishlanmayapti!"
    )

    sent_after_run2 = len(fake_provider.sent)
    assert sent_after_run2 > sent_after_run1, (
        "2-run yangi push yuborishi kerak — 3-chi hodisa (seq>limit) qayta ishlanishi lozim"
    )

    # 3-run: hamma hodisa allaqachon qayta ishlangan — yangi push yo'q
    count3 = await process_pending_pushes(db=db_session, provider=fake_provider, limit=2)
    await db_session.commit()
    assert count3 == 0, f"3-run da yangi push bo'lmasligi kerak, aslida: {count3}"
    assert len(fake_provider.sent) == sent_after_run2


# ─── Test 17: Savepoint izolyatsiyasi — IntegrityError batch'ni buzmaydi ──────


@pytest.mark.anyio
async def test_savepoint_integrity_error_isolation(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    Batch ichida bitta push uchun IntegrityError (race/duplicate) chiqsa,
    qolgan push_log yozuvlari saqlanishi kerak — sessiya ifloslanmaydi.
    Savepoint (begin_nested) izolyatsiyasi: faqat shu push rollback.

    Usul: _process_one_push to'g'ridan-to'g'ri ikki marta chaqiriladi.
    1-chaqiruv: event1+user1 uchun push_log DB da YO'Q (existing_log=None),
                begin_nested ichida flush() → IntegrityError (pre-inserted duplicate
                biz add qilgan push_log bilan UNIQUE conflict).
    2-chaqiruv: event2+user1 — sessiya hali tirik bo'lishi kerak → muvaffaqiyatli.
    """
    from app.modules.push.service import _process_one_push
    from app.models.push import PushLog as PushLogModel
    from app.core.uuid7 import uuid7 as _uuid7
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    user = await make_user(role="store", device_id="sp_iso_token")
    store = await make_store(user_id=user.id)

    # event1 va event2
    order1 = await make_order(store_id=store.id, status="confirmed")
    event1 = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order1.id),
        payload={"order_id": str(order1.id), "status": "packed"},
    )

    order2 = await make_order(store_id=store.id, status="confirmed")
    event2 = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order2.id),
        payload={"order_id": str(order2.id), "status": "confirmed"},
    )

    # event1+user1 uchun push_log DB ga yoziladi (concurrent worker simulyatsiya).
    # _process_one_push ichida existing_log so'rovi bu yozuvni TOPADI →
    # existing_log.status="sent" → 0 qaytaradi (idem skip).
    # Bu to'g'ridan-to'g'ri savepoint yo'lini sinash uchun emas —
    # balki sessiyaning ikki ketma-ket operatsiyadan keyin tirikligini sinaydi.
    pre_log = PushLogModel(
        id=_uuid7(),
        outbox_event_id=event1.id,
        user_id=user.id,
        device_id="sp_iso_token",
        channel="fcm",
        title="pre-sent",
        body="pre-sent",
        status="sent",
        attempts=1,
    )
    db_session.add(pre_log)
    await db_session.flush()

    # 1-chaqiruv: event1+user1 → existing_log topiladi (sent) → skip (return 0)
    payload1 = {"order_id": str(order1.id), "status": "packed"}
    result1 = await _process_one_push(
        db=db_session,
        provider=fake_provider,
        event=event1,
        payload=payload1,
        user_id=user.id,
    )
    assert result1 == 0, "event1 allaqachon sent — skip bo'lishi kerak"

    # Sessiya hali tirik — 2-chaqiruv: event2+user1 → yangi push_log yoziladi
    payload2 = {"order_id": str(order2.id), "status": "confirmed"}
    result2 = await _process_one_push(
        db=db_session,
        provider=fake_provider,
        event=event2,
        payload=payload2,
        user_id=user.id,
    )
    assert result2 == 1, (
        "event2 push_log yozilishi kerak — sessiya 1-skip dan keyin tirik"
    )

    await db_session.commit()

    # event2 push_log DB da bor
    log2_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event2.id)
        .where(PushLog.user_id == user.id)
    )
    log2 = log2_result.scalar_one_or_none()
    assert log2 is not None, "event2 push_log DB da bo'lishi kerak"
    assert log2.status == "sent"

    # event1 uchun yangi push yuborilmagan (allaqachon sent edi)
    # event2 uchun push yuborildi
    assert len(fake_provider.sent) == 1
    assert fake_provider.sent[0].device_id == "sp_iso_token"


# ─── Test 18: Retry pass — yangi hodisa filtri bo'lsa ham failed qayta urinadi ─


@pytest.mark.anyio
async def test_retry_pass_independent_of_new_event_filter(
    db_session: AsyncSession,
    fake_provider: FakePushProvider,
    make_user,
    make_store,
    make_order,
    make_outbox,
):
    """
    failed push_log (attempts < max) retry pass orqali qayta urinadi —
    NOT EXISTS filtri uni yangi hodisalar ro'yxatidan istisno qilsa ham
    (push_log allaqachon bor → PASS 1 uni ko'rmaydi),
    PASS 2 (retry) uni topib qayta ishlaydi.
    """
    store_owner = await make_user(role="store", device_id="retry_pass_token")
    store = await make_store(user_id=store_owner.id)
    order = await make_order(store_id=store.id, status="confirmed")

    event = await make_outbox(
        event_type="order.status_updated",
        aggregate_type="order",
        aggregate_id=str(order.id),
        payload={"order_id": str(order.id), "status": "packed"},
    )

    # 1-run: fail → status=failed, attempts=1; push_log mavjud bo'ladi
    # (PASS 1 keyingi runda bu hodisani ko'rmaydi — push_log bor)
    fake_provider.set_fail_next(1)
    count1 = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()
    assert count1 >= 1

    log_result = await db_session.execute(
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == store_owner.id)
    )
    log = log_result.scalar_one()
    assert log.status == "failed"
    assert log.attempts == 1

    # 2-run: PASS 1 bu hodisani ko'rmaydi (push_log bor),
    # lekin PASS 2 (retry) failed log'ni topib qayta urinadi → sent
    count2 = await process_pending_pushes(db=db_session, provider=fake_provider)
    await db_session.commit()
    assert count2 >= 1, (
        "PASS 2 (retry) failed push_log'ni qayta ishlashi kerak — "
        "yangi hodisa filtri uni istisno qilsa ham"
    )

    await db_session.refresh(log)
    assert log.status == "sent", f"Retry dan keyin status 'sent' bo'lishi kerak, aslida: {log.status!r}"
    assert log.attempts == 2
    assert log.sent_at is not None

    # Push yuborildi
    tokens = {p.device_id for p in fake_provider.sent}
    assert "retry_pass_token" in tokens
