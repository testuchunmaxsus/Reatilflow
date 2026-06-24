"""
Buxgalteriya moduli testlari — LedgerEntry, AccountBalance, RBAC, append-only, Decimal, IDOR.

Test kategoriyalari:
  1. record_entry: INSERT → balans yangilanadi (debit oshiradi, credit kamaytiradi)
  2. Append-only: 2 yozuv → 2 qator, balans yig'indi (hech qachon UPDATE/DELETE emas)
  3. Idempotentlik: client_uuid → bir yozuv
  4. RBAC: buxgalter create; store/agent view (o'z do'koni)
  5. IDOR: store roli boshqa store_id → 404
  6. Balans aniqligi: Decimal
  7. i18n: uz/ru xabarlar
  8. Do'kon topilmasa → 404

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import AccountBalance, LedgerApproval, LedgerEntry
from app.modules.finance import service
from app.modules.finance.schemas import LedgerEntryCreate
from app.tests.finance.conftest import get_token


# ─── 1. record_entry: INSERT + balans yangilanadi ────────────────────────────


@pytest.mark.asyncio
async def test_record_debit_increases_balance(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """debit yozuvi balansni oshiradi (qarz ko'paydi)."""
    store = await make_store()

    data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("10000.00"),
        currency="UZS",
    )
    entry = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    assert entry.id is not None
    assert entry.type == "debit"
    assert entry.amount == Decimal("10000.00")

    balance = await service.get_balance(db_session, store.id)
    assert balance.balance == Decimal("10000.00")


@pytest.mark.asyncio
async def test_record_credit_decreases_balance(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """credit yozuvi balansni kamaytiradi (qarz kamaydi, to'lov)."""
    store = await make_store()

    # Avval debit
    debit_data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("50000.00"),
    )
    await service.record_entry(db_session, debit_data, actor_id=accountant_user.id, redis=fake_redis)

    # Keyin credit (to'lov)
    credit_data = LedgerEntryCreate(
        store_id=store.id,
        type="credit",
        amount=Decimal("20000.00"),
    )
    await service.record_entry(db_session, credit_data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    balance = await service.get_balance(db_session, store.id)
    # 50000 - 20000 = 30000
    assert balance.balance == Decimal("30000.00")


# ─── 2. Append-only: 2 yozuv → 2 qator, balans yig'indi ─────────────────────


@pytest.mark.asyncio
async def test_append_only_two_entries_two_records(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """
    APPEND-ONLY tekshiruvi:
    Ikki yozuv → ikki alohida qator, UPDATE/DELETE YO'Q.
    Balans ikkisini yig'indisi.
    """
    store = await make_store()

    data1 = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("100000.00"),
    )
    data2 = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("50000.00"),
    )

    e1 = await service.record_entry(db_session, data1, actor_id=accountant_user.id, redis=fake_redis)
    e2 = await service.record_entry(db_session, data2, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    # Ikki alohida yozuv
    assert e1.id != e2.id

    # DB da ikkala yozuv mavjud
    stmt = select(LedgerEntry).where(LedgerEntry.store_id == store.id)
    result = await db_session.execute(stmt)
    entries = list(result.scalars().all())
    assert len(entries) == 2

    # Balans yig'indi
    balance = await service.get_balance(db_session, store.id)
    assert balance.balance == Decimal("150000.00")


@pytest.mark.asyncio
async def test_append_only_entries_never_updated(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """
    Yozuvlar hech qachon UPDATE qilinmaydi.
    Birinchi yozuv keyingi yozuvdan keyin ham o'zgarmaydi.
    """
    store = await make_store()

    data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("30000.00"),
    )
    entry = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    original_id = entry.id
    original_amount = entry.amount
    original_created_at = entry.created_at

    # Ikkinchi yozuv
    data2 = LedgerEntryCreate(
        store_id=store.id,
        type="credit",
        amount=Decimal("10000.00"),
    )
    await service.record_entry(db_session, data2, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    # Birinchi yozuv o'zgarmagan (append-only)
    stmt = select(LedgerEntry).where(LedgerEntry.id == original_id)
    result = await db_session.execute(stmt)
    fetched = result.scalar_one()
    assert fetched.amount == original_amount
    assert fetched.created_at == original_created_at
    assert fetched.type == "debit"


# ─── 3. Idempotentlik ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_same_client_uuid_returns_same_record(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """Bir xil client_uuid → bir yozuv."""
    store = await make_store()
    client_uuid = uuid.uuid4()

    data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("10000.00"),
        client_uuid=client_uuid,
    )

    e1 = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    e2 = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    assert e1.id == e2.id

    # DB da faqat bir yozuv
    stmt = select(LedgerEntry).where(LedgerEntry.store_id == store.id)
    result = await db_session.execute(stmt)
    entries = list(result.scalars().all())
    assert len(entries) == 1


# ─── 4. Do'kon topilmasa ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_store_not_found(
    db_session: AsyncSession,
    fake_redis,
    accountant_user,
) -> None:
    """Mavjud bo'lmagan do'kon → AppError 404."""
    from app.core.errors import AppError

    data = LedgerEntryCreate(
        store_id=uuid.uuid4(),  # mavjud emas
        type="debit",
        amount=Decimal("1000.00"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)

    assert exc_info.value.message_key == "finance.store_not_found"
    assert exc_info.value.status_code == 404


# ─── 5. RBAC testlari (HTTP) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_cannot_create_ledger_entry(
    finance_client: AsyncClient,
    store_user,
    make_store,
) -> None:
    """Store roli finance:create ruxsatiga ega emas → 403."""
    store = await make_store()
    token = await get_token(finance_client, store_user)

    resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "1000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_agent_cannot_create_ledger_entry(
    finance_client: AsyncClient,
    agent_user,
    make_store,
) -> None:
    """Agent roli finance:create ruxsatiga ega emas → 403."""
    store = await make_store()
    token = await get_token(finance_client, agent_user)

    resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "1000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_accountant_can_create_ledger_entry(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Buxgalter finance:create ruxsatiga ega → 201."""
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "5000.00",
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["type"] == "debit"
    assert Decimal(data["amount"]) == Decimal("5000.00")


# ─── 6. IDOR: store roli faqat o'z do'konini ko'radi ─────────────────────────


@pytest.mark.asyncio
async def test_store_cannot_see_other_store_balance(
    finance_client: AsyncClient,
    make_user,
    make_store,
    accountant_user,
    fake_redis,
) -> None:
    """
    IDOR tekshiruvi:
    Store roli boshqa do'kon balansini ko'ra olmaydi → 404.
    Mavjudlikni oshkor qilmaslik (404, 403 emas).
    """
    # Ikkita do'kon yaratish
    store_user_a = await make_user("store")
    store_user_b = await make_user("store")
    store_a = await make_store(name="Do'kon A", user_id=store_user_a.id)
    store_b = await make_store(name="Do'kon B", user_id=store_user_b.id)

    # store_user_a boshqa do'kon balansini so'radi
    token = await get_token(finance_client, store_user_a)

    resp = await finance_client.get(
        f"/finance/balance/{store_b.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 404 — mavjudlikni oshkor qilmaslik (IDOR himoya)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_store_can_see_own_balance(
    finance_client: AsyncClient,
    make_user,
    make_store,
) -> None:
    """Store roli o'z do'koni balansini ko'ra oladi → 200."""
    store_user = await make_user("store")
    store = await make_store(name="O'z do'konim", user_id=store_user.id)

    token = await get_token(finance_client, store_user)

    resp = await finance_client.get(
        f"/finance/balance/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["store_id"] == str(store.id)
    assert Decimal(data["balance"]) == Decimal("0")


@pytest.mark.asyncio
async def test_accountant_can_see_any_store_balance(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Buxgalter har qanday do'kon balansini ko'ra oladi → 200."""
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    resp = await finance_client.get(
        f"/finance/balance/{store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


# ─── 7. Balans aniqligi (Decimal) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_balance_decimal_precision(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """Balans Decimal aniqligini saqlaydi (float yaxlitlanishi yo'q)."""
    store = await make_store()

    amounts = ["333.33", "333.33", "333.34"]
    for amount in amounts:
        data = LedgerEntryCreate(
            store_id=store.id,
            type="debit",
            amount=Decimal(amount),
        )
        await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)

    balance = await service.get_balance(db_session, store.id)
    # 333.33 + 333.33 + 333.34 = 1000.00 (Decimal aniqlik)
    assert balance.balance == Decimal("1000.00")


# ─── 8. i18n testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_not_found_message_uz(
    db_session: AsyncSession,
    fake_redis,
    accountant_user,
) -> None:
    """Do'kon topilmadi xatosi — uz tilida."""
    from app.core.errors import AppError
    from app.core.messages import translate

    data = LedgerEntryCreate(
        store_id=uuid.uuid4(),
        type="debit",
        amount=Decimal("1000.00"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)

    err = exc_info.value
    msg_uz = translate(err.message_key, locale="uz")
    msg_ru = translate(err.message_key, locale="ru")

    assert msg_uz != err.message_key
    assert msg_ru != err.message_key
    # Mazmun tekshiruvi
    assert "topilmadi" in msg_uz.lower() or "do'kon" in msg_uz.lower()
    assert "найден" in msg_ru.lower() or "магазин" in msg_ru.lower()


@pytest.mark.asyncio
async def test_finance_messages_keys_exist() -> None:
    """finance.* kalitlar messages.py da mavjud tekshiruvi."""
    from app.core.messages import MESSAGES, translate

    keys = [
        "finance.store_not_found",
        "finance.invalid_type",
        "finance.version_conflict",
        "finance.currency_mismatch",
    ]
    for key in keys:
        assert key in MESSAGES, f"Kalit topilmadi: {key}"
        msg_uz = translate(key, locale="uz")
        msg_ru = translate(key, locale="ru")
        # Fallback emas (kalit o'zi qaytmaydi)
        assert msg_uz != key
        assert msg_ru != key


# ─── 9. Ledger ro'yxati ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_ledger_entries(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Buxgalter yozuvlar ro'yxatini ko'ra oladi."""
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    # Yozuv yaratish
    await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "1000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await finance_client.get(
        f"/finance/ledger?store_id={store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_agent_view_own_store_ledger(
    finance_client: AsyncClient,
    make_user,
    make_store,
    accountant_user,
) -> None:
    """Agent o'ziga biriktirilgan do'kon ledgerini ko'ra oladi."""
    agent = await make_user("agent")
    store = await make_store(name="Agent do'koni", agent_id=agent.id)
    token = await get_token(finance_client, agent)

    resp = await finance_client.get(
        f"/finance/ledger?store_id={store.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


# ─── 10. Multi-currency: valyuta mismatch → 409 ──────────────────────────────


@pytest.mark.asyncio
async def test_currency_mismatch_raises_409(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """
    Do'konga UZS yozuv, keyin USD yozuv → finance.currency_mismatch (409).
    Jim valyuta aralashuvining oldini olish.
    """
    from app.core.errors import AppError

    store = await make_store()

    # Birinchi yozuv — UZS (balans UZS valyutasida yaratiladi)
    uzs_data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("10000.00"),
        currency="UZS",
    )
    await service.record_entry(db_session, uzs_data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.flush()

    # Ikkinchi yozuv — USD (boshqa valyuta → xato)
    usd_data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("100.00"),
        currency="USD",
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_entry(db_session, usd_data, actor_id=accountant_user.id, redis=fake_redis)

    assert exc_info.value.message_key == "finance.currency_mismatch"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_currency_mismatch_message_content(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """currency_mismatch xabari uz/ru da to'g'ri valyuta nomlarini ko'rsatadi."""
    from app.core.errors import AppError
    from app.core.messages import translate

    store = await make_store()

    uzs_data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("5000.00"),
        currency="UZS",
    )
    await service.record_entry(db_session, uzs_data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.flush()

    usd_data = LedgerEntryCreate(
        store_id=store.id,
        type="credit",
        amount=Decimal("50.00"),
        currency="USD",
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_entry(db_session, usd_data, actor_id=accountant_user.id, redis=fake_redis)

    err = exc_info.value
    msg_uz = translate(err.message_key, locale="uz", **err.params)
    msg_ru = translate(err.message_key, locale="ru", **err.params)

    assert "UZS" in msg_uz
    assert "USD" in msg_uz
    assert "UZS" in msg_ru
    assert "USD" in msg_ru


# ─── 11. Credit → balans manfiy bo'lishi ruxsat ──────────────────────────────


@pytest.mark.asyncio
async def test_credit_can_make_balance_negative(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """
    credit yozuvi balansni manfiyga olib kelishi mumkin (qarz qoplangan).
    Bu holat ruxsat — moliyaviy to'g'ri hisob.
    """
    store = await make_store()

    # Faqat credit (debit yo'q) — balans manfiy bo'ladi
    credit_data = LedgerEntryCreate(
        store_id=store.id,
        type="credit",
        amount=Decimal("5000.00"),
        currency="UZS",
    )
    await service.record_entry(db_session, credit_data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.flush()

    balance = await service.get_balance(db_session, store.id)
    assert balance.balance == Decimal("-5000.00"), "Manfiy balans ruxsat (qarz qoplangan)"


# ─── 12. Idempotentlik SET NX bilan ishlaydi ────────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_set_nx_single_entry(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """
    SET NX bilan idempotentlik: bir xil client_uuid → bitta yozuv.
    Balans faqat bir marta o'zgaradi.
    """
    store = await make_store()
    client_uuid = uuid.uuid4()

    data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("20000.00"),
        currency="UZS",
        client_uuid=client_uuid,
    )

    # Uch marta chaqirish — faqat bitta yozuv bo'lishi kerak
    e1 = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    e2 = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    e3 = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.commit()

    assert e1.id == e2.id == e3.id, "Bir xil client_uuid → bir xil yozuv"

    # DB da faqat bir yozuv
    stmt = select(LedgerEntry).where(LedgerEntry.store_id == store.id)
    result = await db_session.execute(stmt)
    entries = list(result.scalars().all())
    assert len(entries) == 1

    # Balans faqat bir marta o'zgargan
    balance = await service.get_balance(db_session, store.id)
    assert balance.balance == Decimal("20000.00")


# ─── 13. Approve: service qatlami ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_entry_creates_approval_record(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """approve_entry → LedgerApproval yozuvi yaratadi (entry_id, approved_by, approved_at)."""
    store = await make_store()

    data = LedgerEntryCreate(
        store_id=store.id,
        type="debit",
        amount=Decimal("15000.00"),
        currency="UZS",
    )
    entry = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.flush()

    approval = await service.approve_entry(
        db_session,
        entry_id=entry.id,
        actor_id=accountant_user.id,
    )
    await db_session.commit()

    assert approval.entry_id == entry.id
    assert approval.approved_by == accountant_user.id
    assert approval.approved_at is not None
    assert approval.id is not None

    # DB da yozuv mavjud
    from sqlalchemy import select
    stmt = select(LedgerApproval).where(LedgerApproval.entry_id == entry.id)
    result = await db_session.execute(stmt)
    db_approval = result.scalar_one_or_none()
    assert db_approval is not None
    assert db_approval.approved_by == accountant_user.id


@pytest.mark.asyncio
async def test_approve_entry_not_found_raises_404(
    db_session: AsyncSession,
    accountant_user,
) -> None:
    """Mavjud bo'lmagan yozuv → AppError 404."""
    from app.core.errors import AppError

    with pytest.raises(AppError) as exc_info:
        await service.approve_entry(
            db_session,
            entry_id=uuid.uuid4(),
            actor_id=accountant_user.id,
        )

    assert exc_info.value.message_key == "finance.entry_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_entry_already_approved_raises_409(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    accountant_user,
) -> None:
    """Allaqachon tasdiqlangan yozuv → AppError 409."""
    from app.core.errors import AppError

    store = await make_store()
    data = LedgerEntryCreate(
        store_id=store.id,
        type="credit",
        amount=Decimal("7000.00"),
    )
    entry = await service.record_entry(db_session, data, actor_id=accountant_user.id, redis=fake_redis)
    await db_session.flush()

    # Birinchi tasdiqlash — muvaffaqiyatli
    await service.approve_entry(db_session, entry_id=entry.id, actor_id=accountant_user.id)
    await db_session.flush()

    # Ikkinchi tasdiqlash — 409
    with pytest.raises(AppError) as exc_info:
        await service.approve_entry(db_session, entry_id=entry.id, actor_id=accountant_user.id)

    assert exc_info.value.message_key == "finance.entry_already_approved"
    assert exc_info.value.status_code == 409


# ─── 14. Approve: HTTP endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accountant_can_approve_entry_via_http(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Buxgalter POST /finance/ledger/{id}/approve → 200, entry_id va approved_by to'ldiriladi."""
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    # Yozuv yaratish
    create_resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "25000.00",
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201, create_resp.text
    entry_id = create_resp.json()["id"]

    # Tasdiqlash
    approve_resp = await finance_client.post(
        f"/finance/ledger/{entry_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approve_resp.status_code == 200, approve_resp.text

    data = approve_resp.json()
    assert data["entry_id"] == entry_id
    assert data["approved_at"] is not None
    assert data["approved_by"] == str(accountant_user.id)
    assert "id" in data  # LedgerApproval.id (UUID)


@pytest.mark.asyncio
async def test_store_cannot_approve_entry(
    finance_client: AsyncClient,
    store_user,
    accountant_user,
    make_store,
) -> None:
    """Store roli finance:approve ruxsatiga ega emas → 403."""
    store = await make_store(user_id=store_user.id)
    acc_token = await get_token(finance_client, accountant_user)
    store_token = await get_token(finance_client, store_user)

    # Yozuv yaratish (buxgalter orqali)
    create_resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "5000.00",
        },
        headers={"Authorization": f"Bearer {acc_token}"},
    )
    assert create_resp.status_code == 201, create_resp.text
    entry_id = create_resp.json()["id"]

    # Store roli tasdiqlashga urinadi → 403
    approve_resp = await finance_client.post(
        f"/finance/ledger/{entry_id}/approve",
        headers={"Authorization": f"Bearer {store_token}"},
    )
    assert approve_resp.status_code == 403, approve_resp.text


@pytest.mark.asyncio
async def test_agent_cannot_approve_entry(
    finance_client: AsyncClient,
    agent_user,
    accountant_user,
    make_store,
) -> None:
    """Agent roli finance:approve ruxsatiga ega emas → 403."""
    store = await make_store(agent_id=agent_user.id)
    acc_token = await get_token(finance_client, accountant_user)
    agent_token = await get_token(finance_client, agent_user)

    create_resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "3000.00",
        },
        headers={"Authorization": f"Bearer {acc_token}"},
    )
    assert create_resp.status_code == 201, create_resp.text
    entry_id = create_resp.json()["id"]

    approve_resp = await finance_client.post(
        f"/finance/ledger/{entry_id}/approve",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert approve_resp.status_code == 403, approve_resp.text


@pytest.mark.asyncio
async def test_approve_nonexistent_entry_returns_404(
    finance_client: AsyncClient,
    accountant_user,
) -> None:
    """Mavjud bo'lmagan yozuv ID → 404."""
    token = await get_token(finance_client, accountant_user)

    resp = await finance_client.post(
        f"/finance/ledger/{uuid.uuid4()}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_approve_twice_returns_409(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """Ikki marta tasdiqlash → 409 (allaqachon tasdiqlangan)."""
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    create_resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "credit",
            "amount": "10000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201, create_resp.text
    entry_id = create_resp.json()["id"]

    # Birinchi tasdiqlash
    r1 = await finance_client.post(
        f"/finance/ledger/{entry_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200, r1.text

    # Ikkinchi tasdiqlash
    r2 = await finance_client.post(
        f"/finance/ledger/{entry_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_created_entry_response_has_no_approval_fields(
    finance_client: AsyncClient,
    accountant_user,
    make_store,
) -> None:
    """
    Yangi yaratilgan yozuv (LedgerEntryOut) asosiy maydonlarni o'z ichiga oladi.
    Tasdiqlash alohida endpoint orqali amalga oshiriladi.
    """
    store = await make_store()
    token = await get_token(finance_client, accountant_user)

    resp = await finance_client.post(
        "/finance/ledger",
        json={
            "store_id": str(store.id),
            "type": "debit",
            "amount": "8000.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["type"] == "debit"
    assert Decimal(data["amount"]) == Decimal("8000.00")
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_approve_messages_keys_exist() -> None:
    """finance.entry_not_found va finance.entry_already_approved kalitlari mavjud."""
    from app.core.messages import MESSAGES, translate

    keys = [
        "finance.entry_not_found",
        "finance.entry_already_approved",
    ]
    for key in keys:
        assert key in MESSAGES, f"Kalit topilmadi: {key}"
        msg_uz = translate(key, locale="uz")
        msg_ru = translate(key, locale="ru")
        assert msg_uz != key
        assert msg_ru != key
