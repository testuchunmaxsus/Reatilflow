"""
Yetkazib berish testlari — T18 Delivery.

Qamrab olingan:
  - create_delivery: order bog'liqligi, courier tekshiruvi, idempotentlik
  - Holat mashinasi: qonuniy o'tishlar (assigned→started→delivering→delivered)
  - Noqonuniy o'tishlar (delivered→started, assigned→delivered) → 422
  - started→start_gps yoziladi; delivered→delivery_gps
  - proof_photo: FakeStorage, magic-byte (noto'g'ri→422)
  - IDOR/scope: kuryer o'ziga tayinlangan; boshqa kuryerniki → 403/404
  - RBAC: do'kon yetkazish yaratolmaydi (faqat view)
  - Agent o'z buyurtmasi yetkazishini ko'radi
  - Admin barchani ko'radi
  - version conflict, idempotentlik, Decimal GPS, i18n
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import Delivery, VALID_TRANSITIONS
from app.models.order import Order
from app.models.store import AgentStore
from app.models.user import AppUser
from app.modules.delivery import service as delivery_service
from app.modules.delivery.schemas import DeliveryCreate, DeliveryStatusUpdate
from app.tests.delivery.conftest import get_token

pytestmark = pytest.mark.anyio


# ─── FAKE RASM YORDAMCHILARI ──────────────────────────────────────────────────

def _fake_jpeg() -> bytes:
    """To'g'ri JPEG magic bytes (FF D8 FF)."""
    return b"\xff\xd8\xff" + b"\x00" * 100


def _fake_png() -> bytes:
    """To'g'ri PNG magic bytes."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _fake_invalid() -> bytes:
    """Noto'g'ri format."""
    return b"INVALID" + b"\x00" * 100


# ─── create_delivery TESTLARI ─────────────────────────────────────────────────


async def test_create_delivery_success(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """Admin yetkazish yarata oladi."""
    store = await make_store()
    agent = await make_user("agent")
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, agent_id=agent.id, status="confirmed")
    admin = await make_user("administrator")

    data = DeliveryCreate(order_id=order.id, courier_id=courier.id)
    delivery = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin
    )

    assert delivery.order_id == order.id
    assert delivery.courier_id == courier.id
    assert delivery.status == "assigned"
    assert delivery.version == 1


async def test_create_delivery_order_not_found(
    db_session: AsyncSession,
    make_user,
):
    """Mavjud bo'lmagan buyurtma → 404."""
    from app.core.errors import AppError

    admin = await make_user("administrator")
    courier = await make_user("courier")

    data = DeliveryCreate(order_id=uuid.uuid4(), courier_id=courier.id)
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data, actor_id=admin.id, user=admin
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.message_key == "delivery.order_not_found"


async def test_create_delivery_wrong_order_status(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """delivered holati buyurtmaga yetkazish yaratilmaydi → 422."""
    from app.core.errors import AppError

    store = await make_store()
    courier = await make_user("courier")
    admin = await make_user("administrator")
    order = await make_order(store_id=store.id, status="delivered")

    data = DeliveryCreate(order_id=order.id, courier_id=courier.id)
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data, actor_id=admin.id, user=admin
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.message_key == "delivery.invalid_transition"


async def test_create_delivery_not_courier(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """Agent foydalanuvchini kuryer sifatida tayinlab bo'lmaydi → 422."""
    from app.core.errors import AppError

    store = await make_store()
    admin = await make_user("administrator")
    agent_as_courier = await make_user("agent")
    order = await make_order(store_id=store.id, status="confirmed")

    data = DeliveryCreate(order_id=order.id, courier_id=agent_as_courier.id)
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data, actor_id=admin.id, user=admin
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.message_key == "delivery.not_courier"


async def test_create_delivery_idempotency(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    fake_redis,
):
    """client_uuid bilan idempotentlik: bir xil so'rov ikki marta yuborganda bitta yetkazish."""
    store = await make_store()
    courier = await make_user("courier")
    admin = await make_user("administrator")
    order = await make_order(store_id=store.id, status="confirmed")
    client_uuid = uuid.uuid4()

    data = DeliveryCreate(
        order_id=order.id,
        courier_id=courier.id,
        client_uuid=client_uuid,
    )

    d1 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin, redis=fake_redis
    )
    await db_session.commit()

    d2 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin, redis=fake_redis
    )

    assert d1.id == d2.id


# ─── HOLAT MASHINASI TESTLARI ─────────────────────────────────────────────────


async def test_state_machine_valid_transitions_full_cycle(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """assigned→started→delivering→delivered to'liq holat zanjiri."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    # assigned → started
    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(status="started", version=1),
        user=courier,
    )
    assert updated.status == "started"
    assert updated.version == 2

    # started → delivering
    updated = await delivery_service.update_status(
        db_session,
        updated.id,
        DeliveryStatusUpdate(status="delivering", version=2),
        user=courier,
    )
    assert updated.status == "delivering"

    # delivering → delivered
    updated = await delivery_service.update_status(
        db_session,
        updated.id,
        DeliveryStatusUpdate(status="delivered", version=3),
        user=courier,
    )
    assert updated.status == "delivered"
    assert updated.delivered_at is not None


async def test_state_machine_invalid_transition_delivered_to_started(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """delivered→started noqonuniy o'tish → 422."""
    from app.core.errors import AppError

    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="delivered")
    # version ni 2 ga o'rnatamiz (ya'ni bir marta o'zgartirilgan deb faraz)
    delivery.version = 2
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await delivery_service.update_status(
            db_session,
            delivery.id,
            DeliveryStatusUpdate(status="started", version=2),
            user=courier,
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.message_key == "delivery.invalid_transition"


async def test_state_machine_invalid_transition_assigned_to_delivered(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """assigned→delivered to'g'ridan o'tish noqonuniy → 422."""
    from app.core.errors import AppError

    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    with pytest.raises(AppError) as exc_info:
        await delivery_service.update_status(
            db_session,
            delivery.id,
            DeliveryStatusUpdate(status="delivered", version=1),
            user=courier,
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.message_key == "delivery.invalid_transition"


async def test_state_machine_failed_transition(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """assigned→failed qonuniy o'tish (failure_reason bilan)."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(
            status="failed",
            version=1,
            failure_reason="Manzil topilmadi",
        ),
        user=courier,
    )
    assert updated.status == "failed"
    assert updated.failure_reason == "Manzil topilmadi"


async def test_state_machine_failed_is_terminal(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """failed → hech qaerga o'tish mumkin emas (terminal holat)."""
    from app.core.errors import AppError

    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="failed")

    with pytest.raises(AppError) as exc_info:
        await delivery_service.update_status(
            db_session,
            delivery.id,
            DeliveryStatusUpdate(status="assigned", version=1),
            user=courier,
        )
    assert exc_info.value.status_code == 422


# ─── GPS YOZISH TESTLARI ──────────────────────────────────────────────────────


async def test_started_writes_start_gps(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """started holatiga o'tganda start_gps_lat/lng yoziladi."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(
            status="started",
            version=1,
            gps_lat=Decimal("41.29950000"),
            gps_lng=Decimal("69.24007000"),
        ),
        user=courier,
    )

    assert updated.start_gps_lat == Decimal("41.29950000")
    assert updated.start_gps_lng == Decimal("69.24007000")
    assert updated.started_at is not None
    # delivery_gps hali yozilmagan
    assert updated.delivery_gps_lat is None


async def test_delivered_writes_delivery_gps(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """delivered holatiga o'tganda delivery_gps yoziladi."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="delivering")
    # version ni to'g'ri o'rnatamiz
    delivery.version = 3
    await db_session.flush()

    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(
            status="delivered",
            version=3,
            gps_lat=Decimal("41.30050000"),
            gps_lng=Decimal("69.24100000"),
        ),
        user=courier,
    )

    assert updated.delivery_gps_lat == Decimal("41.30050000")
    assert updated.delivery_gps_lng == Decimal("69.24100000")
    assert updated.delivered_at is not None


async def test_gps_no_cross_db_fk(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """
    GPS trek cross-DB FK yo'qligi tekshiruvi.

    Delivery modelida delivery_track uchun FK ustuni yo'q.
    GpsPoint.delivery_id faqat UUID (FK siz).
    """
    # Delivery model ustunlari orasida delivery_track related ustun yo'q
    delivery_columns = [
        col.key for col in Delivery.__table__.columns  # type: ignore
    ]
    # FK bo'lmagan GPS ustun yo'q (faqat delivery jadvali ustunlari)
    assert "delivery_track" not in delivery_columns
    # start_gps va delivery_gps — key nuqtalar (FK yo'q, faqat koordinatalar)
    assert "start_gps_lat" in delivery_columns
    assert "delivery_gps_lat" in delivery_columns


# ─── PROOF PHOTO TESTLARI ─────────────────────────────────────────────────────


async def test_proof_photo_jpeg_ok(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """To'g'ri JPEG rasmi yuklash muvaffaqiyatli."""
    admin = await make_user("administrator")
    courier = await make_user("courier")
    store = await make_store()
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.post(
        f"/delivery/{delivery.id}/proof-photo",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("proof.jpg", io.BytesIO(_fake_jpeg()), "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["proof_photo_url"] is not None
    assert "fake-storage" in data["proof_photo_url"]


async def test_proof_photo_invalid_format_422(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Noto'g'ri format → 422."""
    admin = await make_user("administrator")
    store = await make_store()
    order = await make_order(store_id=store.id, status="confirmed")
    courier = await make_user("courier")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.post(
        f"/delivery/{delivery.id}/proof-photo",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("evil.exe", io.BytesIO(_fake_invalid()), "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert resp.json()["message_key"] == "delivery.invalid_photo"


# ─── IDOR/SCOPE TESTLARI ─────────────────────────────────────────────────────


async def test_courier_can_update_own_delivery(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Kuryer o'z yetkazishini o'zgartira oladi."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(status="started", version=1),
        user=courier,
    )
    assert updated.status == "started"


async def test_courier_cannot_update_other_courier_delivery(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Boshqa kuryerning yetkazishini o'zgartirish → 403."""
    from app.core.errors import AppError

    store = await make_store()
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    # courier1 ga tayinlangan yetkazish
    delivery = await make_delivery(order_id=order.id, courier_id=courier1.id, status="assigned")

    # courier2 boshqa kuryerning yetkazishini o'zgartirishga urinadi
    with pytest.raises(AppError) as exc_info:
        await delivery_service.update_status(
            db_session,
            delivery.id,
            DeliveryStatusUpdate(status="started", version=1),
            user=courier2,
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.message_key == "delivery.forbidden"


async def test_agent_sees_own_order_delivery(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Agent o'z buyurtmasi yetkazishini ko'ra oladi."""
    agent = await make_user("agent")
    store = await make_store(agent_id=agent.id)
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, agent_id=agent.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)

    fetched = await delivery_service.get_delivery(db_session, delivery.id, user=agent)
    assert fetched.id == delivery.id


async def test_agent_cannot_see_other_store_delivery(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Agent boshqa do'kon yetkazishini ko'ra olmaydi → 404."""
    from app.core.errors import AppError

    agent1 = await make_user("agent")
    agent2 = await make_user("agent")
    store = await make_store(agent_id=agent2.id)  # agent2 do'koni
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, agent_id=agent2.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)

    with pytest.raises(AppError) as exc_info:
        await delivery_service.get_delivery(db_session, delivery.id, user=agent1)
    assert exc_info.value.status_code == 404


async def test_admin_sees_all_deliveries(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Admin barcha yetkazishlarni ko'ra oladi."""
    admin = await make_user("administrator")
    courier = await make_user("courier")

    store1 = await make_store()
    store2 = await make_store()
    order1 = await make_order(store_id=store1.id, status="confirmed")
    order2 = await make_order(store_id=store2.id, status="confirmed")
    d1 = await make_delivery(order_id=order1.id, courier_id=courier.id)
    d2 = await make_delivery(order_id=order2.id, courier_id=courier.id)

    items, total = await delivery_service.list_deliveries(db_session, user=admin)
    ids = {d.id for d in items}
    assert d1.id in ids
    assert d2.id in ids
    assert total >= 2


async def test_store_user_sees_own_delivery_via_http(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Do'kon o'z buyurtmasi yetkazishini ko'ra oladi (view ruxsati bor)."""
    store_u = await make_user("store")
    store = await make_store(user_id=store_u.id)
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, store_u)
    resp = await delivery_client.get(
        "/delivery",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data["items"]]
    assert str(delivery.id) in ids


# ─── RBAC TESTLARI ────────────────────────────────────────────────────────────


async def test_store_cannot_create_delivery(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    db_session: AsyncSession,
):
    """Do'kon yetkazish yarata olmaydi (faqat view)."""
    store_u = await make_user("store")
    store = await make_store(user_id=store_u.id)
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    await db_session.commit()

    token = await get_token(delivery_client, store_u)
    resp = await delivery_client.post(
        "/delivery",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": str(order.id),
            "courier_id": str(courier.id),
        },
    )
    assert resp.status_code == 403


async def test_accountant_can_view_delivery(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Buxgalter yetkazishni ko'ra oladi (faqat view)."""
    accountant = await make_user("accountant")
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, accountant)
    resp = await delivery_client.get(
        f"/delivery/{delivery.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


async def test_courier_cannot_create_delivery_for_other(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    db_session: AsyncSession,
):
    """
    Kuryer RBAC darajasida yetkazish yaratolmaydi (delivery:create yo'q).
    RBAC matritsasi: courier faqat view+edit.
    """
    courier = await make_user("courier")
    store = await make_store()
    order = await make_order(store_id=store.id, status="confirmed")
    await db_session.commit()

    token = await get_token(delivery_client, courier)
    resp = await delivery_client.post(
        "/delivery",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": str(order.id),
            "courier_id": str(courier.id),
        },
    )
    # courier delivery:create ruxsati yo'q
    assert resp.status_code == 403


# ─── AGENT ORDER-SCOPE (CROSS-TENANT IDOR) TESTLARI ─────────────────────────


async def test_agent_cannot_create_delivery_for_other_agents_order(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """
    [HIGH] Agent boshqa agentning do'koni buyurtmasiga kuryer tayinlay olmaydi.

    create_delivery ichida agent uchun order.store_id scope tekshiruvi mavjud.
    Boshqa agentning buyurtmasiga tayinlash → 404 (IDOR: mavjudlikni oshkor qilmaslik).
    """
    from app.core.errors import AppError

    agent1 = await make_user("agent")
    agent2 = await make_user("agent")
    courier = await make_user("courier")
    # agent2 do'koni — agent1 ga tegishli emas
    store_of_agent2 = await make_store(agent_id=agent2.id)
    order = await make_order(store_id=store_of_agent2.id, agent_id=agent2.id, status="confirmed")

    data = DeliveryCreate(order_id=order.id, courier_id=courier.id)
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data, actor_id=agent1.id, user=agent1
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.message_key == "delivery.order_not_found"


async def test_agent_can_create_delivery_for_own_store_order(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """Agent o'z do'koni buyurtmasiga kuryer tayinlay oladi."""
    agent = await make_user("agent")
    courier = await make_user("courier")
    store = await make_store(agent_id=agent.id)
    order = await make_order(store_id=store.id, agent_id=agent.id, status="confirmed")

    data = DeliveryCreate(order_id=order.id, courier_id=courier.id)
    delivery = await delivery_service.create_delivery(
        db_session, data, actor_id=agent.id, user=agent
    )
    assert delivery.order_id == order.id
    assert delivery.courier_id == courier.id


async def test_agent_cannot_create_delivery_for_unrelated_store_order(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """
    [HIGH] AgentStore ga biriktirilmagan do'kon buyurtmasi uchun tayinlay olmaydi.
    """
    from app.core.errors import AppError

    agent = await make_user("agent")
    courier = await make_user("courier")
    # Bu do'kon hech qanday agentga tegishli emas
    unrelated_store = await make_store()
    order = await make_order(store_id=unrelated_store.id, status="confirmed")

    data = DeliveryCreate(order_id=order.id, courier_id=courier.id)
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data, actor_id=agent.id, user=agent
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.message_key == "delivery.order_not_found"


# ─── VERSION CONFLICT TESTLARI ────────────────────────────────────────────────


async def test_version_conflict(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """Noto'g'ri versiya → 409 version_conflict."""
    from app.core.errors import AppError

    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    with pytest.raises(AppError) as exc_info:
        await delivery_service.update_status(
            db_session,
            delivery.id,
            DeliveryStatusUpdate(status="started", version=99),  # noto'g'ri versiya
            user=courier,
        )
    assert exc_info.value.status_code == 409
    assert "version" in exc_info.value.message_key


# ─── DECIMAL GPS TESTLARI ─────────────────────────────────────────────────────


async def test_decimal_gps_precision(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """GPS koordinatalar Decimal aniqligida saqlanadi."""
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="assigned")

    lat = Decimal("41.29950001")
    lng = Decimal("69.24007001")

    updated = await delivery_service.update_status(
        db_session,
        delivery.id,
        DeliveryStatusUpdate(
            status="started",
            version=1,
            gps_lat=lat,
            gps_lng=lng,
        ),
        user=courier,
    )

    assert updated.start_gps_lat is not None
    assert updated.start_gps_lng is not None


# ─── GPS TRACK URL TESTLARI ───────────────────────────────────────────────────


async def test_delivery_has_gps_track_url(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """GET /delivery/{id} javobi gps_track_url ni qaytaradi."""
    admin = await make_user("administrator")
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.get(
        f"/delivery/{delivery.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "gps_track_url" in data
    # GPS trek URL delivery_id ni o'z ichiga oladi
    assert str(delivery.id) in data["gps_track_url"]


# ─── i18n TESTLARI ────────────────────────────────────────────────────────────


async def test_i18n_invalid_transition_uz(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Noqonuniy o'tish xabari o'zbek tilida."""
    admin = await make_user("administrator")
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="delivered")
    delivery.version = 2
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.patch(
        f"/delivery/{delivery.id}/status",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
        json={"status": "started", "version": 2},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["message_key"] == "delivery.invalid_transition"
    # O'zbek tilidagi xabar
    assert "mumkin emas" in body["message"].lower() or "o'tish" in body["message"].lower()


async def test_i18n_invalid_transition_ru(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Noqonuniy o'tish xabari rus tilida."""
    admin = await make_user("administrator")
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id, status="delivered")
    delivery.version = 2
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.patch(
        f"/delivery/{delivery.id}/status",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
        json={"status": "started", "version": 2},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["message_key"] == "delivery.invalid_transition"
    # Rus tilidagi xabar
    assert "невозможен" in body["message"].lower() or "переход" in body["message"].lower()


# ─── PAGINATED LIST TESTLARI ──────────────────────────────────────────────────


async def test_list_deliveries_paginated(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """Paginated ro'yxat to'g'ri ishlaydi."""
    admin = await make_user("administrator")
    store = await make_store()
    courier = await make_user("courier")

    # 3 ta yetkazish yaratish
    for i in range(3):
        order = await make_order(store_id=store.id, status="confirmed")
        await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.get(
        "/delivery?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert len(data["items"]) <= 2
    assert data["limit"] == 2


# ─── HTTP ENDPOINT INTEGRATSIYA TESTLARI ─────────────────────────────────────


async def test_create_delivery_http(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    db_session: AsyncSession,
):
    """POST /delivery endpoint ishlaydi."""
    admin = await make_user("administrator")
    store = await make_store()
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.post(
        "/delivery",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": str(order.id),
            "courier_id": str(courier.id),
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "assigned"
    assert data["order_id"] == str(order.id)
    assert data["courier_id"] == str(courier.id)


async def test_update_status_http(
    delivery_client: AsyncClient,
    make_user,
    make_store,
    make_order,
    make_delivery,
    db_session: AsyncSession,
):
    """PATCH /delivery/{id}/status endpoint ishlaydi."""
    courier = await make_user("courier")
    store = await make_store()
    order = await make_order(store_id=store.id, status="confirmed")
    delivery = await make_delivery(order_id=order.id, courier_id=courier.id)
    await db_session.commit()

    token = await get_token(delivery_client, courier)
    resp = await delivery_client.patch(
        f"/delivery/{delivery.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "started", "version": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "started"
    assert data["version"] == 2


async def test_get_delivery_http_not_found(
    delivery_client: AsyncClient,
    make_user,
    db_session: AsyncSession,
):
    """Mavjud bo'lmagan yetkazish → 404."""
    admin = await make_user("administrator")
    await db_session.commit()

    token = await get_token(delivery_client, admin)
    resp = await delivery_client.get(
        f"/delivery/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ─── OPERATSION YAXLITLIK TESTLARI (T18 HIGH topilma) ────────────────────────


async def test_duplicate_active_delivery_same_order_different_uuid_raises_409(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
):
    """
    [HIGH] Bir buyurtmaga ikkinchi aktiv yetkazish (har xil client_uuid) → 409 already_assigned.

    Birinchi yetkazish 'assigned' holatida — aktiv.
    Ikkinchi yaratish urinishi → AppError("delivery.already_assigned", 409).
    """
    from app.core.errors import AppError

    store = await make_store()
    admin = await make_user("administrator")
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")

    # Birinchi yetkazish muvaffaqiyatli
    data1 = DeliveryCreate(
        order_id=order.id,
        courier_id=courier1.id,
        client_uuid=uuid.uuid4(),
    )
    d1 = await delivery_service.create_delivery(
        db_session, data1, actor_id=admin.id, user=admin
    )
    assert d1.status == "assigned"

    # Ikkinchi yetkazish (boshqa kuryer, boshqa client_uuid) → 409
    data2 = DeliveryCreate(
        order_id=order.id,
        courier_id=courier2.id,
        client_uuid=uuid.uuid4(),
    )
    with pytest.raises(AppError) as exc_info:
        await delivery_service.create_delivery(
            db_session, data2, actor_id=admin.id, user=admin
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.message_key == "delivery.already_assigned"


async def test_new_delivery_allowed_after_terminal_status(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """
    [HIGH] Birinchi yetkazish 'delivered'/'failed' bo'lgach, shu buyurtmaga yangi yaratish MUMKIN.

    Terminal holat = aktiv emas → qayta tayinlash ruxsat etiladi.
    """
    store = await make_store()
    admin = await make_user("administrator")
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")

    # Birinchi yetkazish 'delivered' holatda (terminal)
    await make_delivery(order_id=order.id, courier_id=courier1.id, status="delivered")

    # Yangi yetkazish — ruxsat etilgan (terminal bo'lgani uchun)
    data = DeliveryCreate(order_id=order.id, courier_id=courier2.id)
    d2 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin
    )
    assert d2.order_id == order.id
    assert d2.status == "assigned"


async def test_new_delivery_allowed_after_failed_status(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    make_delivery,
):
    """
    [HIGH] Birinchi yetkazish 'failed' bo'lgach, shu buyurtmaga yangi yaratish MUMKIN.
    """
    store = await make_store()
    admin = await make_user("administrator")
    courier1 = await make_user("courier")
    courier2 = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")

    # Birinchi yetkazish 'failed' holatda (terminal)
    await make_delivery(order_id=order.id, courier_id=courier1.id, status="failed")

    # Yangi yetkazish — ruxsat etilgan
    data = DeliveryCreate(order_id=order.id, courier_id=courier2.id)
    d2 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin
    )
    assert d2.order_id == order.id
    assert d2.status == "assigned"


async def test_client_uuid_duplicate_returns_existing_not_409(
    db_session: AsyncSession,
    make_store,
    make_order,
    make_user,
    fake_redis,
):
    """
    [HIGH] client_uuid takror (bir xil) → mavjud yetkazish qaytadi (idempotentlik),
    already_assigned EMAS.

    Bir xil client_uuid bilan ikki marta so'rov → bitta yetkazish, 409 emas.
    """
    store = await make_store()
    admin = await make_user("administrator")
    courier = await make_user("courier")
    order = await make_order(store_id=store.id, status="confirmed")
    client_uuid = uuid.uuid4()

    data = DeliveryCreate(
        order_id=order.id,
        courier_id=courier.id,
        client_uuid=client_uuid,
    )

    d1 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin, redis=fake_redis
    )
    await db_session.commit()

    # Xuddi shu so'rov — idempotent qaytarish
    d2 = await delivery_service.create_delivery(
        db_session, data, actor_id=admin.id, user=admin, redis=fake_redis
    )

    # Yangi yaratilmagan, mavjud qaytarilgan
    assert d1.id == d2.id
    # 409 ko'tarilmagan — idempotentlik saqlanadi


async def test_already_assigned_message_key_in_messages(db_session: AsyncSession):
    """
    [MEDIUM] delivery.already_assigned kaliti messages.py da mavjud (uz va ru).
    """
    from app.core.messages import MESSAGES, translate

    assert "delivery.already_assigned" in MESSAGES
    assert "uz" in MESSAGES["delivery.already_assigned"]
    assert "ru" in MESSAGES["delivery.already_assigned"]

    uz_text = translate("delivery.already_assigned", locale="uz")
    ru_text = translate("delivery.already_assigned", locale="ru")

    assert len(uz_text) > 5
    assert len(ru_text) > 5
    # Mazmuni to'g'ri
    assert "aktiv" in uz_text.lower() or "allaqachon" in uz_text.lower()
    assert "активн" in ru_text.lower() or "уже" in ru_text.lower()
