"""
Qator-darajali himoya (row-level scope) testlari.

`apply_store_scope` va `get_user_store_ids` funksiyalari:
  - agent faqat o'z do'konlarini ko'radi (agent_id yoki AgentStore orqali)
  - courier barcha do'konlarni ko'radi (manzil uchun)
  - administrator barcha do'konlarni ko'radi (branch_id=None holda)
  - administrator branch_id bilan faqat o'z filialini ko'radi
  - store roli → Store.user_id == user.id (T5 da DENY-ALL tuzatildi)

Infrasiz: aiosqlite in-memory.

T5 o'zgarish:
  - store roli endi DENY-ALL emas — Store.user_id == user.id bo'lsa ko'radi.
  - test_store_role_deny_all → test_store_role_sees_own_store_via_user_id (nom o'zgardi).
  - T2 dagi TODO(T5) yopildi.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.rbac.scope import apply_store_scope, get_user_store_ids
from app.tests.rbac.conftest import TEST_PASSWORD


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


async def create_store(
    db: AsyncSession,
    name: str,
    agent_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Store:
    """Test do'koni yaratadi."""
    store = Store(
        id=uuid.uuid4(),
        name=name,
        agent_id=agent_id,
        branch_id=branch_id,
        user_id=user_id,
        version=1,
    )
    db.add(store)
    await db.flush()
    return store


async def create_user(
    db: AsyncSession,
    role: str,
    branch_id: uuid.UUID | None = None,
) -> AppUser:
    """Test foydalanuvchisi yaratadi."""
    from app.core.jwt import hash_password
    user = AppUser(
        id=uuid.uuid4(),
        full_name=f"Test {role}",
        phone=f"+99890{str(abs(hash(role + str(uuid.uuid4()))))[:7]}",
        role=role,
        branch_id=branch_id,
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    db.add(user)
    await db.flush()
    return user


# ─── apply_store_scope testlari ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_sees_only_own_stores_via_agent_id(db_session: AsyncSession) -> None:
    """
    Agent faqat Store.agent_id == user.id do'konlarini ko'radi.
    Boshqa agentning do'konlari ko'rinmaydi.
    """
    agent = await create_user(db_session, "agent")
    other_agent = await create_user(db_session, "agent")

    # agent's stores
    store1 = await create_store(db_session, "Agent Store 1", agent_id=agent.id)
    store2 = await create_store(db_session, "Agent Store 2", agent_id=agent.id)
    # other agent's store
    _other_store = await create_store(db_session, "Other Store", agent_id=other_agent.id)
    # no agent store
    _no_agent = await create_store(db_session, "No Agent Store", agent_id=None)

    stmt = select(Store)
    stmt = apply_store_scope(stmt, agent)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    store_ids = {s.id for s in stores}
    assert store1.id in store_ids
    assert store2.id in store_ids
    assert _other_store.id not in store_ids
    assert _no_agent.id not in store_ids


@pytest.mark.asyncio
async def test_agent_sees_stores_via_agent_store_table(db_session: AsyncSession) -> None:
    """
    Agent AgentStore jadvali orqali biriktirilgan do'konlarni ham ko'radi.
    """
    agent = await create_user(db_session, "agent")

    # Do'kon agent_id=None (to'g'ridan-to'g'ri emas) — faqat AgentStore orqali
    store_via_table = await create_store(db_session, "Linked via AgentStore", agent_id=None)
    # Store agent_id orqali
    store_via_agent_id = await create_store(db_session, "Direct agent_id", agent_id=agent.id)
    # Boshqa do'kon
    unrelated = await create_store(db_session, "Unrelated", agent_id=None)

    # AgentStore yozuvi
    link = AgentStore(agent_id=agent.id, store_id=store_via_table.id)
    db_session.add(link)
    await db_session.flush()

    stmt = select(Store)
    stmt = apply_store_scope(stmt, agent)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    store_ids = {s.id for s in stores}
    assert store_via_table.id in store_ids
    assert store_via_agent_id.id in store_ids
    assert unrelated.id not in store_ids


@pytest.mark.asyncio
async def test_admin_without_branch_sees_all_stores(db_session: AsyncSession) -> None:
    """Administrator branch_id=None → barcha do'konlarni ko'radi."""
    admin = await create_user(db_session, "administrator", branch_id=None)

    branch_a = uuid.uuid4()
    branch_b = uuid.uuid4()
    store1 = await create_store(db_session, "Store A", branch_id=branch_a)
    store2 = await create_store(db_session, "Store B", branch_id=branch_b)
    store3 = await create_store(db_session, "Store C")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, admin)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    store_ids = {s.id for s in stores}
    assert store1.id in store_ids
    assert store2.id in store_ids
    assert store3.id in store_ids


@pytest.mark.asyncio
async def test_admin_with_branch_sees_only_own_branch(db_session: AsyncSession) -> None:
    """Administrator branch_id bilan → faqat o'z filialini ko'radi."""
    branch_a = uuid.uuid4()
    branch_b = uuid.uuid4()
    admin = await create_user(db_session, "administrator", branch_id=branch_a)

    store_a = await create_store(db_session, "Store A", branch_id=branch_a)
    store_b = await create_store(db_session, "Store B", branch_id=branch_b)
    store_none = await create_store(db_session, "Store None")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, admin)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    store_ids = {s.id for s in stores}
    assert store_a.id in store_ids
    assert store_b.id not in store_ids
    assert store_none.id not in store_ids


@pytest.mark.asyncio
async def test_accountant_without_branch_sees_all_stores(db_session: AsyncSession) -> None:
    """Accountant branch_id=None → barcha do'konlarni ko'radi."""
    accountant = await create_user(db_session, "accountant", branch_id=None)

    store1 = await create_store(db_session, "S1", branch_id=uuid.uuid4())
    store2 = await create_store(db_session, "S2")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, accountant)
    result = await db_session.execute(stmt)
    store_ids = {s.id for s in result.scalars().all()}
    assert store1.id in store_ids
    assert store2.id in store_ids


@pytest.mark.asyncio
async def test_courier_sees_all_stores(db_session: AsyncSession) -> None:
    """Courier manzil uchun barcha do'konlarni ko'radi (row-level yo'q)."""
    courier = await create_user(db_session, "courier")

    store1 = await create_store(db_session, "S1", agent_id=uuid.uuid4())
    store2 = await create_store(db_session, "S2")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, courier)
    result = await db_session.execute(stmt)
    store_ids = {s.id for s in result.scalars().all()}
    assert store1.id in store_ids
    assert store2.id in store_ids


@pytest.mark.asyncio
async def test_store_role_sees_own_store_via_user_id(db_session: AsyncSession) -> None:
    """
    Store roli — T5 DENY-ALL tuzatish:
    Store.user_id == user.id bo'lgan do'konlar ko'rinadi.

    Avvalgi: deny-all (IDOR xavfi, Store.user_id FK yo'q edi).
    Hozir: Store.user_id == user.id (T5 da FK qo'shildi).
    """
    store_owner = await create_user(db_session, "store")
    other_store_user = await create_user(db_session, "store")

    own_store = Store(
        id=uuid.uuid4(),
        name="Owner's Store",
        user_id=store_owner.id,
        version=1,
    )
    other_store = Store(
        id=uuid.uuid4(),
        name="Other Store",
        user_id=other_store_user.id,
        version=1,
    )
    no_owner_store = Store(
        id=uuid.uuid4(),
        name="No Owner Store",
        user_id=None,
        version=1,
    )
    db_session.add_all([own_store, other_store, no_owner_store])
    await db_session.flush()

    stmt = select(Store)
    stmt = apply_store_scope(stmt, store_owner)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    store_ids = {s.id for s in stores}
    assert own_store.id in store_ids, "Store egasi o'z do'konini ko'rishi kerak"
    assert other_store.id not in store_ids, "Boshqa userning do'koni ko'rinmasligi kerak"
    assert no_owner_store.id not in store_ids, "user_id=None do'kon ko'rinmasligi kerak"


@pytest.mark.asyncio
async def test_get_user_store_ids_store_role(db_session: AsyncSession) -> None:
    """
    get_user_store_ids — store roli uchun faqat o'z do'koni.

    T5: DENY-ALL → Store.user_id == user.id.
    """
    store_owner = await create_user(db_session, "store")
    other_store_user = await create_user(db_session, "store")

    own_store = Store(id=uuid.uuid4(), name="Mine", user_id=store_owner.id, version=1)
    other_store = Store(id=uuid.uuid4(), name="Theirs", user_id=other_store_user.id, version=1)
    db_session.add_all([own_store, other_store])
    await db_session.flush()

    ids = await get_user_store_ids(store_owner, db_session)
    ids_set = set(ids)

    assert own_store.id in ids_set
    assert other_store.id not in ids_set


@pytest.mark.asyncio
async def test_unknown_role_sees_nothing(db_session: AsyncSession) -> None:
    """Noma'lum rol → hech narsa ko'rinmaydi (deny-all)."""
    import types
    user = types.SimpleNamespace(id=uuid.uuid4(), role="unknown_role", branch_id=None)

    await create_store(db_session, "Visible Store")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, user)  # type: ignore[arg-type]
    result = await db_session.execute(stmt)
    stores = result.scalars().all()
    assert len(stores) == 0


# ─── get_user_store_ids testlari ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_store_ids_agent_multiple_stores(db_session: AsyncSession) -> None:
    """
    Agent uchun get_user_store_ids — bir nechta do'kon (agent_id + AgentStore).
    """
    agent = await create_user(db_session, "agent")

    store1 = await create_store(db_session, "Direct 1", agent_id=agent.id)
    store2 = await create_store(db_session, "Direct 2", agent_id=agent.id)
    store3 = await create_store(db_session, "Via Table", agent_id=None)
    _other = await create_store(db_session, "Other", agent_id=uuid.uuid4())

    # AgentStore yozuvi
    link = AgentStore(agent_id=agent.id, store_id=store3.id)
    db_session.add(link)
    await db_session.flush()

    ids = await get_user_store_ids(agent, db_session)
    ids_set = set(ids)

    assert store1.id in ids_set
    assert store2.id in ids_set
    assert store3.id in ids_set
    assert _other.id not in ids_set


@pytest.mark.asyncio
async def test_get_user_store_ids_admin_all(db_session: AsyncSession) -> None:
    """Administrator (branch_id=None) → barcha do'kon ID lari."""
    admin = await create_user(db_session, "administrator")

    s1 = await create_store(db_session, "S1")
    s2 = await create_store(db_session, "S2", branch_id=uuid.uuid4())

    ids = set(await get_user_store_ids(admin, db_session))
    assert s1.id in ids
    assert s2.id in ids


@pytest.mark.asyncio
async def test_scope_preserves_original_query(db_session: AsyncSession) -> None:
    """apply_store_scope asl so'rovni o'zgartirmaydi (iммutabel)."""
    agent = await create_user(db_session, "agent")
    original = select(Store)
    filtered = apply_store_scope(original, agent)

    # Asl so'rov o'zgarmagan
    assert original is not filtered
