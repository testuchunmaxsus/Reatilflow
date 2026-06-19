"""
Tickets moduli testlari — T24.

Test kategoriyalari:
  1. CRUD: do'kon/xodim murojaati yaratish; ro'yxat; get (messages bilan)
  2. Xabar qo'shish: text + attachment_url; attachment noto'g'ri → 422
  3. Holat mashinasi: qonuniy o'tishlar; noqonuniy → 422; terminal (closed)
  4. RBAC: do'kon/agent create+view; admin/buxgalter resolve (status o'zgartirish);
           do'kon resolve qila olmaydi (faqat o'z murojaati view+message)
  5. IDOR/scope: do'kon o'z murojaati; boshqa do'kon murojaati→404;
                 agent o'z do'konlari; admin barchasi
  6. version conflict, idempotentlik, i18n

Infrasiz: aiosqlite + fakeredis + FakeStorage.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.tests.tickets.conftest import get_token


# ─── 1. CRUD testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_create_ticket(
    tickets_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """Do'kon o'z do'koni uchun murojaat yaratadi — 201 javob."""
    store = await make_store(name="Aloqa Do'kon", user_id=store_user.id)
    token = await get_token(tickets_client, store_user)
    resp = await tickets_client.post(
        "/tickets",
        json={
            "ticket_type": "taklif",
            "subject": "Yangi maxsulot taklifi",
            "body": "Iltimos, yangi maxsulot qo'shing",
            "store_id": str(store.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ticket_type"] == "taklif"
    assert data["status"] == "new"
    assert data["store_id"] == str(store.id)


@pytest.mark.asyncio
async def test_agent_create_ticket_no_store(
    tickets_client: AsyncClient,
    agent_user,
) -> None:
    """Agent store_id siz xodim murojaati yaratadi (NULL store)."""
    token = await get_token(tickets_client, agent_user)
    resp = await tickets_client.post(
        "/tickets",
        json={
            "ticket_type": "etiroz",
            "subject": "Ish sharoiti haqida",
            "body": "Iltimos, ish sharoitini yaxshilang",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["store_id"] is None
    assert data["ticket_type"] == "etiroz"
    assert data["status"] == "new"


@pytest.mark.asyncio
async def test_admin_list_all_tickets(
    tickets_client: AsyncClient,
    admin_user,
    make_store,
    make_ticket,
) -> None:
    """Admin barcha murojaatlarni ko'radi."""
    store = await make_store(name="Filial Do'kon")
    await make_ticket(store_id=store.id, ticket_type="taklif")
    await make_ticket(store_id=None, ticket_type="etiroz")

    token = await get_token(tickets_client, admin_user)
    resp = await tickets_client.get(
        "/tickets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_get_ticket_with_messages(
    tickets_client: AsyncClient,
    admin_user,
    make_store,
    make_ticket,
    db_session,
) -> None:
    """Murojaat GET da xabarlar ham qaytadi."""
    from app.models.ticket import TicketMessage

    store = await make_store()
    ticket = await make_ticket(store_id=store.id)

    msg = TicketMessage(
        ticket_id=ticket.id,
        author_id=admin_user.id,
        body="Test xabari",
    )
    db_session.add(msg)
    await db_session.flush()

    token = await get_token(tickets_client, admin_user)
    resp = await tickets_client.get(
        f"/tickets/{ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(ticket.id)
    assert data["messages"] is not None
    assert len(data["messages"]) == 1
    assert data["messages"][0]["body"] == "Test xabari"


# ─── 2. Xabar qo'shish testlari ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_message_to_ticket(
    tickets_client: AsyncClient,
    admin_user,
    make_store,
    make_ticket,
) -> None:
    """Admin murojaatga xabar qo'shadi."""
    store = await make_store()
    ticket = await make_ticket(store_id=store.id)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.post(
        f"/tickets/{ticket.id}/messages",
        json={"body": "Murojaat ko'rib chiqilmoqda"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["body"] == "Murojaat ko'rib chiqilmoqda"
    assert data["ticket_id"] == str(ticket.id)
    assert data["author_id"] == str(admin_user.id)


@pytest.mark.asyncio
async def test_add_message_with_attachment_url(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Xabarni attachment_url bilan qo'shish."""
    ticket = await make_ticket()
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.post(
        f"/tickets/{ticket.id}/messages",
        json={
            "body": "Fayl yuborildi",
            "attachment_url": "http://fake-storage/tickets/test.jpg",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["attachment_url"] == "http://fake-storage/tickets/test.jpg"


@pytest.mark.asyncio
async def test_store_add_message_to_own_ticket(
    tickets_client: AsyncClient,
    store_user,
    make_store,
    make_ticket,
) -> None:
    """Do'kon o'z murojaatiga xabar qo'sha oladi."""
    store = await make_store(user_id=store_user.id)
    ticket = await make_ticket(store_id=store.id, author_id=store_user.id)
    token = await get_token(tickets_client, store_user)

    resp = await tickets_client.post(
        f"/tickets/{ticket.id}/messages",
        json={"body": "Qo'shimcha ma'lumot"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_store_cannot_add_message_to_other_store_ticket(
    tickets_client: AsyncClient,
    store_user,
    make_store,
    make_ticket,
) -> None:
    """Do'kon boshqa do'kon murojaatiga xabar qo'sha olmaydi — 404."""
    # store_user.id boshqa do'konga egalik qilmaydi
    other_store = await make_store(name="Boshqa Do'kon", user_id=None)
    ticket = await make_ticket(store_id=other_store.id)

    # store_user o'z do'koniga egalik qilishi kerak
    own_store = await make_store(name="O'z Do'koni", user_id=store_user.id)
    token = await get_token(tickets_client, store_user)

    resp = await tickets_client.post(
        f"/tickets/{ticket.id}/messages",
        json={"body": "Xabar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


# ─── 3. Holat mashinasi testlari ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_new_to_in_progress(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """new → in_progress qonuniy o'tish."""
    ticket = await make_ticket(status="new")
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_status_in_progress_to_resolved(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """in_progress → resolved qonuniy o'tish."""
    ticket = await make_ticket(status="in_progress", version=2)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "resolved", "version": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_status_resolved_to_in_progress_reopen(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """resolved → in_progress qayta ochish qonuniy."""
    ticket = await make_ticket(status="resolved", version=3)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_status_resolved_to_closed(
    tickets_client: AsyncClient,
    accountant_user,
    make_ticket,
) -> None:
    """Buxgalter: resolved → closed (terminal)."""
    ticket = await make_ticket(status="resolved", version=3)
    token = await get_token(tickets_client, accountant_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "closed", "version": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_status_closed_to_in_progress_invalid(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """closed → in_progress noqonuniy o'tish → 422."""
    ticket = await make_ticket(status="closed", version=4)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text
    assert "tickets.invalid_transition" in resp.text


@pytest.mark.asyncio
async def test_status_new_to_resolved_invalid(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """new → resolved noqonuniy o'tish (in_progress o'tkazib yuborilgan) → 422."""
    ticket = await make_ticket(status="new")
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "resolved", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text
    assert "tickets.invalid_transition" in resp.text


@pytest.mark.asyncio
async def test_status_new_to_closed_invalid(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """new → closed noqonuniy o'tish → 422."""
    ticket = await make_ticket(status="new")
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "closed", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text


# ─── 4. RBAC testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_cannot_change_status(
    tickets_client: AsyncClient,
    store_user,
    make_store,
    make_ticket,
) -> None:
    """Do'kon holat o'zgartira olmaydi — 403 (tickets:edit ruxsati yo'q)."""
    store = await make_store(user_id=store_user.id)
    ticket = await make_ticket(store_id=store.id, author_id=store_user.id)
    token = await get_token(tickets_client, store_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_cannot_change_status(
    tickets_client: AsyncClient,
    agent_user,
    make_ticket,
) -> None:
    """Agent holat o'zgartira olmaydi — 403."""
    ticket = await make_ticket(author_id=agent_user.id)
    token = await get_token(tickets_client, agent_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_resolve(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Admin murojaatni resolve qila oladi."""
    ticket = await make_ticket(status="in_progress", version=2)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "resolved", "version": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_accountant_can_resolve(
    tickets_client: AsyncClient,
    accountant_user,
    make_ticket,
) -> None:
    """Buxgalter murojaatni resolve qila oladi."""
    ticket = await make_ticket(status="in_progress", version=2)
    token = await get_token(tickets_client, accountant_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "resolved", "version": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_courier_cannot_change_status(
    tickets_client: AsyncClient,
    courier_user,
    make_ticket,
) -> None:
    """Kuryer holat o'zgartira olmaydi — 403."""
    ticket = await make_ticket(author_id=courier_user.id)
    token = await get_token(tickets_client, courier_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


# ─── 5. IDOR/scope testlari ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_sees_only_own_ticket(
    tickets_client: AsyncClient,
    store_user,
    make_store,
    make_ticket,
) -> None:
    """Do'kon faqat o'z do'koni murojaatini ko'radi."""
    own_store = await make_store(user_id=store_user.id)
    other_store = await make_store(name="Boshqa Do'kon")

    own_ticket = await make_ticket(store_id=own_store.id)
    other_ticket = await make_ticket(store_id=other_store.id)

    token = await get_token(tickets_client, store_user)

    # O'z murojaati — 200
    resp = await tickets_client.get(
        f"/tickets/{own_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # Boshqa do'kon murojaati — 404
    resp2 = await tickets_client.get(
        f"/tickets/{other_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404, resp2.text


@pytest.mark.asyncio
async def test_agent_sees_own_store_tickets(
    tickets_client: AsyncClient,
    agent_user,
    make_store,
    make_ticket,
    make_agent_store,
) -> None:
    """Agent o'z do'konlari murojaatlarini ko'ra oladi."""
    own_store = await make_store(agent_id=agent_user.id)
    other_store = await make_store(name="Boshqa Agent Do'koni")

    own_ticket = await make_ticket(store_id=own_store.id)
    other_ticket = await make_ticket(store_id=other_store.id)

    token = await get_token(tickets_client, agent_user)

    # O'z do'koni murojaati — 200
    resp = await tickets_client.get(
        f"/tickets/{own_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # Boshqa do'kon murojaati — 404
    resp2 = await tickets_client.get(
        f"/tickets/{other_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404, resp2.text


@pytest.mark.asyncio
async def test_agent_sees_own_created_ticket(
    tickets_client: AsyncClient,
    agent_user,
    make_ticket,
) -> None:
    """Agent o'zi yaratgan murojaatni ko'ra oladi (store_id yo'q bo'lsa ham)."""
    ticket = await make_ticket(author_id=agent_user.id, store_id=None)
    token = await get_token(tickets_client, agent_user)

    resp = await tickets_client.get(
        f"/tickets/{ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_admin_sees_all_tickets(
    tickets_client: AsyncClient,
    admin_user,
    store_user,
    agent_user,
    make_store,
    make_ticket,
) -> None:
    """Admin barcha murojaatlarni ko'radi (store va agent murojaatlari ham)."""
    store = await make_store(user_id=store_user.id)
    store_ticket = await make_ticket(store_id=store.id)
    agent_ticket = await make_ticket(author_id=agent_user.id)

    token = await get_token(tickets_client, admin_user)

    # Store murojaati
    resp1 = await tickets_client.get(
        f"/tickets/{store_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Agent murojaati
    resp2 = await tickets_client.get(
        f"/tickets/{agent_ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_store_cannot_create_ticket_for_other_store(
    tickets_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """Do'kon boshqa do'kon uchun murojaat yarata olmaydi — 404."""
    other_store = await make_store(name="Boshqa Do'kon")
    # store_user o'z do'koniga egalik qilmaydi (user_id != store_user.id)

    token = await get_token(tickets_client, store_user)
    resp = await tickets_client.post(
        "/tickets",
        json={
            "ticket_type": "taklif",
            "subject": "Test",
            "body": "IDOR urinishi",
            "store_id": str(other_store.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_store_list_shows_only_own_tickets(
    tickets_client: AsyncClient,
    store_user,
    make_store,
    make_ticket,
) -> None:
    """Do'kon ro'yxatida faqat o'z do'koni murojaatlari ko'rinadi."""
    own_store = await make_store(user_id=store_user.id)
    other_store = await make_store(name="Boshqa")

    await make_ticket(store_id=own_store.id)
    await make_ticket(store_id=other_store.id)  # Ko'rinmasin

    token = await get_token(tickets_client, store_user)
    resp = await tickets_client.get(
        "/tickets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Faqat o'z do'koni murojaati ko'rinadi
    for item in data["items"]:
        assert item["store_id"] == str(own_store.id)


# ─── 6. Version conflict testlari ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_version_conflict(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Noto'g'ri version → 409 conflict."""
    ticket = await make_ticket(status="new", version=1)
    token = await get_token(tickets_client, admin_user)

    # Noto'g'ri version (kutilayotgan 1, lekin 5 yuborildi)
    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text


# ─── 7. Idempotentlik testlari ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_ticket_idempotent(
    tickets_client: AsyncClient,
    agent_user,
) -> None:
    """Bir xil client_uuid bilan ikki marta yuborish — birinchisi qaytadi."""
    client_uuid = str(uuid.uuid4())
    token = await get_token(tickets_client, agent_user)
    payload = {
        "ticket_type": "taklif",
        "subject": "Idempotent murojaat",
        "body": "Test",
        "client_uuid": client_uuid,
    }

    resp1 = await tickets_client.post(
        "/tickets", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp1.status_code == 201, resp1.text

    resp2 = await tickets_client.post(
        "/tickets", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp2.status_code == 201, resp2.text

    # Ikki javobi bir xil ID ni qaytarishi kerak
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_create_ticket_client_uuid_integrity_error_idempotent(
    db_session,
    agent_user,
) -> None:
    """
    DB-darajasi IntegrityError simulyatsiyasi (client_uuid race).

    Bir xil client_uuid bilan service.create_ticket ikki marta to'g'ridan-to'g'ri
    chaqiriladi — ikkinchi flush IntegrityError beradi, lekin servis xatoni
    ushlab mavjud ticketni qaytarishi kerak (500 emas).
    """
    from unittest.mock import AsyncMock, patch

    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    from app.modules.tickets.schemas import TicketCreate
    from app.modules.tickets.service import create_ticket

    client_uuid = uuid.uuid4()
    payload = TicketCreate(
        ticket_type="taklif",
        subject="Race murojaat",
        body="Test matni",
        client_uuid=client_uuid,
    )

    # Birinchi yaratish — haqiqiy
    ticket1 = await create_ticket(db_session, payload, actor_id=agent_user.id, user=agent_user)
    await db_session.commit()

    # IntegrityError simulyatsiya: flush() ni chaqirish o'rniga
    # to'g'ridan-to'g'ri IntegrityError ko'taramiz (race holati)
    orig_flush = db_session.flush

    call_count = 0

    async def _patched_flush(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Birinchi flush chaqiruvi IntegrityError beradi (race simulyatsiyasi)
        if call_count == 1:
            raise SAIntegrityError(
                statement=None,
                params=None,
                orig=Exception("UNIQUE constraint failed: ticket.client_uuid"),
            )
        return await orig_flush(*args, **kwargs)

    db_session.flush = _patched_flush  # type: ignore[method-assign]
    try:
        ticket2 = await create_ticket(
            db_session, payload, actor_id=agent_user.id, user=agent_user
        )
    finally:
        db_session.flush = orig_flush  # type: ignore[method-assign]

    # Ikkinchi chaqiruv birinchi ticket ID ni qaytarishi kerak (500 emas)
    assert ticket2.id == ticket1.id, (
        f"Race holatida create_ticket yangi ticket yaratdi yoki xato chiqdi: "
        f"{ticket2.id} != {ticket1.id}"
    )


# ─── 8. i18n testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_transition_uz_message(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Noqonuniy holat o'tishi — uzbek xabar."""
    ticket = await make_ticket(status="closed", version=4)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 4},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "tickets.invalid_transition" in body.get("message_key", "")
    assert "o'tish" in body.get("message", "") or "closed" in body.get("message", "")


@pytest.mark.asyncio
async def test_invalid_transition_ru_message(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Noqonuniy holat o'tishi — russian xabar."""
    ticket = await make_ticket(status="closed", version=4)
    token = await get_token(tickets_client, admin_user)

    resp = await tickets_client.patch(
        f"/tickets/{ticket.id}/status",
        json={"status": "in_progress", "version": 4},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "tickets.invalid_transition" in body.get("message_key", "")
    assert "переход" in body.get("message", "") or "closed" in body.get("message", "")


@pytest.mark.asyncio
async def test_ticket_not_found_returns_404(
    tickets_client: AsyncClient,
    admin_user,
) -> None:
    """Mavjud bo'lmagan murojaat ID — 404."""
    token = await get_token(tickets_client, admin_user)
    resp = await tickets_client.get(
        f"/tickets/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "tickets.not_found" in resp.json().get("message_key", "")


# ─── 9. Filter testlari ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tickets_filter_by_status(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """Status bo'yicha filtr."""
    await make_ticket(status="new")
    await make_ticket(status="resolved", version=3)

    token = await get_token(tickets_client, admin_user)
    resp = await tickets_client.get(
        "/tickets?status=new",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["status"] == "new"


@pytest.mark.asyncio
async def test_list_tickets_filter_by_type(
    tickets_client: AsyncClient,
    admin_user,
    make_ticket,
) -> None:
    """ticket_type bo'yicha filtr."""
    await make_ticket(ticket_type="taklif")
    await make_ticket(ticket_type="etiroz")

    token = await get_token(tickets_client, admin_user)
    resp = await tickets_client.get(
        "/tickets?ticket_type=taklif",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["ticket_type"] == "taklif"


# ─── 10. Agent via AgentStore scope testi ────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_sees_agentstore_linked_ticket(
    tickets_client: AsyncClient,
    agent_user,
    make_store,
    make_ticket,
    make_agent_store,
) -> None:
    """Agent AgentStore orqali biriktirilgan do'kon murojaatini ko'ra oladi."""
    store = await make_store(name="AgentStore orqali biriktirilgan")
    await make_agent_store(agent_id=agent_user.id, store_id=store.id)
    ticket = await make_ticket(store_id=store.id)

    token = await get_token(tickets_client, agent_user)
    resp = await tickets_client.get(
        f"/tickets/{ticket.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


# ─── 11. Courier testi ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_courier_can_create_and_view_own_ticket(
    tickets_client: AsyncClient,
    courier_user,
) -> None:
    """Kuryer o'z murojaatini yaratib ko'ra oladi."""
    token = await get_token(tickets_client, courier_user)

    # Yaratish
    resp = await tickets_client.post(
        "/tickets",
        json={
            "ticket_type": "etiroz",
            "subject": "Yo'l muammosi",
            "body": "Yo'l yopiq edi",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["id"]

    # Ko'rish
    resp2 = await tickets_client.get(
        f"/tickets/{ticket_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
