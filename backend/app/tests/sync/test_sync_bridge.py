"""
Sync ko'prik handler'lari testlari — store.update, store.assign_agent,
contract.create, marketplace_order.create.

Har handler uchun:
  - applied (normal oqim)
  - idempotentlik (takror client_uuid)
  - conflict (mos xato holati)
  - payload validatsiya xatosi → error

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.marketplace import MarketplaceOrder
from app.models.outbox import OutboxEvent, reset_seq_counter
from app.models.store import AgentStore, Store
from app.modules.sync import service as sync_service
from app.modules.sync.schemas import SyncOp
from app.tests.sync.conftest import DEFAULT_WAREHOUSE


# ─── Fixtures izolyatsiyasi ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_outbox_seq():
    """Har test uchun OutboxEvent seq counter'ini nolga qaytaradi."""
    reset_seq_counter()
    yield
    reset_seq_counter()


# ─── Yordamchilar ────────────────────────────────────────────────────────────


def _valid_date_range():
    today = date.today()
    return today.isoformat(), (today + timedelta(days=365)).isoformat()


# ─── store.update ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_update_applied(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
    make_store,
) -> None:
    """
    store.update → applied: do'kon nomi yangilanadi, server_id qaytadi.
    """
    store = await make_store(name="Eski nom", agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    op = SyncOp(
        op_type="store.update",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "version": store.version,
            "name": "Yangi nom",
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
    result = results[0]
    assert result.status == "applied", f"Kutilgan 'applied', topilgan: {result}"
    assert result.server_id == str(store.id)

    # DB da yangilangan nom tekshirish
    refreshed = await db_session.get(Store, store.id)
    assert refreshed is not None
    assert refreshed.name == "Yangi nom"


@pytest.mark.asyncio
async def test_store_update_version_conflict(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
    make_store,
) -> None:
    """
    store.update versiya mos kelmasa → conflict (customers.version_conflict).
    """
    store = await make_store(name="Do'kon", agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    op = SyncOp(
        op_type="store.update",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "version": store.version + 99,  # eskirgan versiya
            "name": "Yangi nom",
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "conflict"
    assert results[0].message_key == "customers.version_conflict"


@pytest.mark.asyncio
async def test_store_update_bad_payload(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
) -> None:
    """
    store.update payload'da store_id yo'q → error (common.validation_error).
    """
    op = SyncOp(
        op_type="store.update",
        client_uuid=str(uuid.uuid4()),
        payload={"name": "Nom"},  # store_id va version yo'q
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "error"
    assert results[0].message_key == "common.validation_error"


# ─── store.assign_agent ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_assign_agent_applied(
    db_session: AsyncSession,
    fake_redis,
    admin_user,
    make_user,
    make_store,
) -> None:
    """
    store.assign_agent → applied: agent do'konga birikadi, AgentStore yoziladi.
    """
    agent = await make_user("agent")
    store = await make_store()

    op = SyncOp(
        op_type="store.assign_agent",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "agent_id": str(agent.id),
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=admin_user.id,
        user=admin_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "applied"
    assert results[0].server_id == str(store.id)

    # AgentStore yozilganligini tekshirish
    stmt = select(AgentStore).where(
        AgentStore.agent_id == agent.id,
        AgentStore.store_id == store.id,
    )
    result = await db_session.execute(stmt)
    link = result.scalar_one_or_none()
    assert link is not None, "AgentStore yozuvi bo'lishi kerak"


@pytest.mark.asyncio
async def test_store_assign_agent_idempotent(
    db_session: AsyncSession,
    fake_redis,
    admin_user,
    make_user,
    make_store,
) -> None:
    """
    store.assign_agent idempotent: bir xil op ikki marta → ikkisi ham applied.
    """
    agent = await make_user("agent")
    store = await make_store()

    payload = {
        "store_id": str(store.id),
        "agent_id": str(agent.id),
    }

    # Birinchi
    op1 = SyncOp(
        op_type="store.assign_agent",
        client_uuid=str(uuid.uuid4()),
        payload=payload,
    )
    results1 = await sync_service.push(
        ops=[op1],
        actor_id=admin_user.id,
        user=admin_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results1[0].status == "applied"

    # Ikkinchi (bir xil store+agent, boshqa client_uuid)
    op2 = SyncOp(
        op_type="store.assign_agent",
        client_uuid=str(uuid.uuid4()),
        payload=payload,
    )
    results2 = await sync_service.push(
        ops=[op2],
        actor_id=admin_user.id,
        user=admin_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results2[0].status == "applied"

    # Faqat bitta AgentStore bo'lishi kerak (idempotent)
    stmt = select(AgentStore).where(
        AgentStore.agent_id == agent.id,
        AgentStore.store_id == store.id,
    )
    result = await db_session.execute(stmt)
    links = result.scalars().all()
    assert len(links) == 1, "Takror biriktirishda bitta AgentStore bo'lishi kerak"


@pytest.mark.asyncio
async def test_store_assign_agent_not_found(
    db_session: AsyncSession,
    fake_redis,
    admin_user,
    make_store,
) -> None:
    """
    store.assign_agent: mavjud bo'lmagan agent_id → conflict.
    """
    store = await make_store()

    op = SyncOp(
        op_type="store.assign_agent",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "agent_id": str(uuid.uuid4()),  # yo'q agent
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=admin_user.id,
        user=admin_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "conflict"
    assert results[0].message_key == "customers.agent_not_found"


@pytest.mark.asyncio
async def test_store_assign_agent_bad_payload(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
) -> None:
    """
    store.assign_agent payload'da agent_id yo'q → error.
    """
    op = SyncOp(
        op_type="store.assign_agent",
        client_uuid=str(uuid.uuid4()),
        payload={"store_id": str(uuid.uuid4())},  # agent_id yo'q
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "error"
    assert results[0].message_key == "common.validation_error"


# ─── contract.create ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contract_create_applied(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
    make_store,
) -> None:
    """
    contract.create → applied: shartnoma DB da yaratiladi, server_id qaytadi.
    """
    store = await make_store(agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    valid_from, valid_to = _valid_date_range()
    client_uuid = str(uuid.uuid4())

    op = SyncOp(
        op_type="contract.create",
        client_uuid=client_uuid,
        payload={
            "client_uuid": client_uuid,
            "store_id": str(store.id),
            "number": "2026-001",
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "applied", f"Kutilgan 'applied', topilgan: {results[0]}"
    assert results[0].server_id is not None

    # DB da shartnoma tekshirish
    contract_id = uuid.UUID(results[0].server_id)
    stmt = select(Contract).where(Contract.id == contract_id)
    result = await db_session.execute(stmt)
    contract = result.scalar_one_or_none()
    assert contract is not None
    assert contract.number == "2026-001"
    assert str(contract.store_id) == str(store.id)
    # supplier_enterprise_id server-avtoritar = agent.enterprise_id
    assert contract.supplier_enterprise_id == agent_user.enterprise_id


@pytest.mark.asyncio
async def test_contract_create_idempotent(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
    make_store,
) -> None:
    """
    contract.create client_uuid takror → ikkinchisi ham applied (idempotent),
    bir xil server_id qaytadi.
    """
    store = await make_store(agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    valid_from, valid_to = _valid_date_range()
    client_uuid = str(uuid.uuid4())

    op_body = {
        "client_uuid": client_uuid,
        "store_id": str(store.id),
        "number": "2026-IDEM",
        "valid_from": valid_from,
        "valid_to": valid_to,
    }

    op1 = SyncOp(op_type="contract.create", client_uuid=client_uuid, payload=op_body)
    results1 = await sync_service.push(
        ops=[op1],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results1[0].status == "applied"
    server_id_1 = results1[0].server_id

    op2 = SyncOp(op_type="contract.create", client_uuid=client_uuid, payload=op_body)
    results2 = await sync_service.push(
        ops=[op2],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results2[0].status == "applied"
    # Bir xil server_id qaytishi kerak (idempotent)
    assert results2[0].server_id == server_id_1


@pytest.mark.asyncio
async def test_contract_create_duplicate_number_conflict(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
    make_store,
) -> None:
    """
    contract.create bir xil (store_id, number) → conflict (contracts.duplicate_number).
    """
    store = await make_store(agent_id=agent_user.id)
    as_ = AgentStore(agent_id=agent_user.id, store_id=store.id)
    db_session.add(as_)
    await db_session.flush()

    valid_from, valid_to = _valid_date_range()
    number = "2026-DUP"

    op1 = SyncOp(
        op_type="contract.create",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "number": number,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )
    results1 = await sync_service.push(
        ops=[op1],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results1[0].status == "applied"

    # Boshqa client_uuid bilan bir xil number
    op2 = SyncOp(
        op_type="contract.create",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(store.id),
            "number": number,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )
    results2 = await sync_service.push(
        ops=[op2],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )
    assert results2[0].status == "conflict"
    assert results2[0].message_key == "contracts.duplicate_number"


@pytest.mark.asyncio
async def test_contract_create_bad_payload(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
) -> None:
    """
    contract.create payload'da number yo'q → error (common.validation_error).
    """
    op = SyncOp(
        op_type="contract.create",
        client_uuid=str(uuid.uuid4()),
        payload={
            "store_id": str(uuid.uuid4()),
            # number yo'q
            "valid_from": date.today().isoformat(),
            "valid_to": (date.today() + timedelta(days=30)).isoformat(),
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "error"
    assert results[0].message_key == "common.validation_error"


# ─── marketplace_order.create ─────────────────────────────────────────────────


async def _setup_mp_agent_bypass(
    db_session: AsyncSession,
    make_user,
    make_store,
    make_product,
    default_enterprise,
):
    """
    Agent bypass uchun to'liq setup:
      - Supplier korxona (alohida enterprise)
      - Supplier agent (shu korxona)
      - Buyer do'kon (default_enterprise, agent_id = supplier agent)
      - Published mahsulot (supplier korxonasiga tegishli)

    Agent bypass shartlari (service.py ~416-441):
      a. actor.role == "agent"
      b. actor.enterprise_id == supplier_enterprise_id
      c. Agent buyer_store ga biriktirilgan (Store.agent_id == actor.id)

    Buyer do'koni default_enterprise'da — supplier != buyer (self-purchase yo'q).
    """
    from app.models.catalog import Product
    from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
    from sqlalchemy import update as sa_update

    # Supplier korxona
    supplier_enterprise = Enterprise(
        id=uuid.uuid4(),
        name=f"Supplier Korxona {uuid.uuid4().hex[:6]}",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(supplier_enterprise)
    await db_session.flush()

    # Supplier agent
    supplier_agent = await make_user("agent", enterprise_id=supplier_enterprise.id)

    # Buyer do'kon — default_enterprise'da, supplier_agent ga biriktirilgan
    buyer_store = await make_store(agent_id=supplier_agent.id)
    as_ = AgentStore(agent_id=supplier_agent.id, store_id=buyer_store.id)
    db_session.add(as_)

    # Mahsulot — supplier korxonasiga tegishli, published
    product = await make_product(
        name_uz=f"MP mahsulot {uuid.uuid4().hex[:6]}",
        price=Decimal("4000"),
        enterprise_id=supplier_enterprise.id,
    )
    await db_session.execute(
        sa_update(Product)
        .where(Product.id == product.id)
        .values(marketplace_published=True)
    )
    await db_session.flush()

    return supplier_agent, buyer_store, product


@pytest.mark.asyncio
async def test_marketplace_order_create_applied(
    db_session: AsyncSession,
    fake_redis,
    make_user,
    make_store,
    make_product,
    default_enterprise,
) -> None:
    """
    marketplace_order.create (is_onetime=True, agent bypass) → applied.
    Supplier agent o'z korxonasining published mahsulotini buyer do'kon nomidan
    buyurtma qiladi (shartnoma yo'q, agent bypass ishlaydi).
    """
    supplier_agent, buyer_store, product = await _setup_mp_agent_bypass(
        db_session, make_user, make_store, make_product, default_enterprise
    )

    client_uuid = str(uuid.uuid4())
    op = SyncOp(
        op_type="marketplace_order.create",
        client_uuid=client_uuid,
        payload={
            "client_uuid": client_uuid,
            "product_id": str(product.id),
            "qty": "2",
            "store_id": str(buyer_store.id),
            "is_onetime": True,
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=supplier_agent.id,
        user=supplier_agent,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "applied", f"Kutilgan 'applied', topilgan: {results[0]}"
    assert results[0].server_id is not None

    # DB da marketplace buyurtma tekshirish
    mp_id = uuid.UUID(results[0].server_id)
    stmt = select(MarketplaceOrder).where(MarketplaceOrder.id == mp_id)
    result = await db_session.execute(stmt)
    mp_order = result.scalar_one_or_none()
    assert mp_order is not None
    assert mp_order.is_onetime is True
    assert mp_order.buyer_store_id == buyer_store.id


@pytest.mark.asyncio
async def test_marketplace_order_create_idempotent(
    db_session: AsyncSession,
    fake_redis,
    make_user,
    make_store,
    make_product,
    default_enterprise,
) -> None:
    """
    marketplace_order.create client_uuid takror → ikkinchisi ham applied (idempotent),
    bir xil server_id qaytadi.

    Shartnoma mavjud holat ishlatiladi (contract_required yo'q, agent bypass yo'q)
    — bu holda buyer_enterprise_id o'zgarmaydi va idempotentlik to'g'ri ishlaydi.
    """
    from app.models.catalog import Product
    from app.models.contract import Contract
    from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
    from sqlalchemy import update as sa_update

    # Supplier korxona
    supplier_ent = Enterprise(
        id=uuid.uuid4(),
        name=f"Supplier IDEM {uuid.uuid4().hex[:6]}",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(supplier_ent)

    # Buyer admin (default_enterprise)
    buyer_admin = await make_user("administrator")

    # Buyer do'kon (default_enterprise)
    buyer_store = await make_store()

    # Mahsulot — supplier korxonasiga tegishli, published
    product = await make_product(
        name_uz="MP Idem mahsulot shartnomali",
        price=Decimal("3000"),
        enterprise_id=supplier_ent.id,
    )
    await db_session.execute(
        sa_update(Product)
        .where(Product.id == product.id)
        .values(marketplace_published=True)
    )

    # Shartnoma — buyer_store ↔ supplier_ent
    today = date.today()
    contract = Contract(
        store_id=buyer_store.id,
        number=f"IDEM-{uuid.uuid4().hex[:8]}",
        valid_from=today,
        valid_to=today + timedelta(days=365),
        supplier_enterprise_id=supplier_ent.id,
        enterprise_id=default_enterprise.id,
    )
    db_session.add(contract)
    await db_session.flush()

    client_uuid = str(uuid.uuid4())
    payload = {
        "client_uuid": client_uuid,
        "product_id": str(product.id),
        "qty": "1",
        "store_id": str(buyer_store.id),
        "is_onetime": False,
    }

    op1 = SyncOp(op_type="marketplace_order.create", client_uuid=client_uuid, payload=payload)
    results1 = await sync_service.push(
        ops=[op1],
        actor_id=buyer_admin.id,
        user=buyer_admin,
        db=db_session,
        redis=fake_redis,
    )
    assert results1[0].status == "applied", f"1-natija: {results1[0]}"
    server_id_1 = results1[0].server_id

    op2 = SyncOp(op_type="marketplace_order.create", client_uuid=client_uuid, payload=payload)
    results2 = await sync_service.push(
        ops=[op2],
        actor_id=buyer_admin.id,
        user=buyer_admin,
        db=db_session,
        redis=fake_redis,
    )
    assert results2[0].status == "applied", f"2-natija (idempotent bo'lishi kerak): {results2[0]}"
    assert results2[0].server_id == server_id_1, "Bir xil server_id qaytishi kerak"


@pytest.mark.asyncio
async def test_marketplace_order_create_contract_required_conflict(
    db_session: AsyncSession,
    fake_redis,
    make_user,
    make_store,
    make_product,
    default_enterprise,
) -> None:
    """
    marketplace_order.create: shartnoma yo'q, agent bypass ham mumkin emas
    (buyer agent — boshqa korxona) → conflict (marketplace.contract_required).
    """
    from app.models.catalog import Product
    from sqlalchemy import update as sa_update
    from app.tests.conftest import TEST_ENTERPRISE_UUID
    from app.models.enterprise import Enterprise, ALL_MODULE_KEYS

    # Supplier korxona (alohida)
    supplier_enterprise = Enterprise(
        id=uuid.uuid4(),
        name="Supplier Korxona",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(supplier_enterprise)
    await db_session.flush()

    # Buyer agent — default korxona (supplier bilan farqli)
    buyer_agent = await make_user("agent")  # enterprise_id = default_enterprise

    # Buyer do'kon
    buyer_store = await make_store(agent_id=buyer_agent.id)
    as_ = AgentStore(agent_id=buyer_agent.id, store_id=buyer_store.id)
    db_session.add(as_)

    # Mahsulot — supplier korxonasiga tegishli, published
    product = await make_product(
        name_uz="Supplier mahsulot",
        price=Decimal("2000"),
        enterprise_id=supplier_enterprise.id,
    )
    await db_session.execute(
        sa_update(Product)
        .where(Product.id == product.id)
        .values(marketplace_published=True)
    )
    await db_session.flush()

    # Shartnoma yo'q, buyer agent supplier korxonasiga tegishli emas → bypass imkonsiz
    op = SyncOp(
        op_type="marketplace_order.create",
        client_uuid=str(uuid.uuid4()),
        payload={
            "product_id": str(product.id),
            "qty": "1",
            "store_id": str(buyer_store.id),
            "is_onetime": True,
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=buyer_agent.id,
        user=buyer_agent,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "conflict"
    assert results[0].message_key == "marketplace.contract_required"


@pytest.mark.asyncio
async def test_marketplace_order_create_bad_payload(
    db_session: AsyncSession,
    fake_redis,
    agent_user,
) -> None:
    """
    marketplace_order.create payload'da product_id yo'q → error.
    """
    op = SyncOp(
        op_type="marketplace_order.create",
        client_uuid=str(uuid.uuid4()),
        payload={
            "qty": "1",
            "store_id": str(uuid.uuid4()),
            # product_id yo'q
        },
    )

    results = await sync_service.push(
        ops=[op],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )

    assert results[0].status == "error"
    assert results[0].message_key == "common.validation_error"
