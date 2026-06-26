"""
Qator-darajali himoya (row-level scope) testlari.

`apply_store_scope` va `get_user_store_ids` funksiyalari:
  - agent faqat o'z do'konlarini ko'radi (agent_id yoki AgentStore orqali)
  - courier barcha do'konlarni ko'radi (manzil uchun)
  - administrator barcha do'konlarni ko'radi (branch_id=None holda)
  - administrator branch_id bilan faqat o'z filialini ko'radi
  - store roli → Store.user_id == user.id (T5 da DENY-ALL tuzatildi)

`get_store_visibility_filter` funksiyasi (ADR-003):
  - superadmin → None (filtr yo'q)
  - administrator/accountant → o'z korxona do'konlari + shartnoma qilgan platforma do'konlari
  - agent → agent_id yoki AgentStore orqali biriktirilgan do'konlar
  - store → user_id bo'yicha o'z do'koni
  - courier → None (filtr yo'q, barcha manzillar)
  - noma'lum rol → deny-all

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

from app.models.contract import Contract
from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.rbac.scope import apply_store_scope, get_store_visibility_filter, get_user_store_ids
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


# ─── get_store_visibility_filter testlari (ADR-003) ──────────────────────────


async def create_store_with_enterprise(
    db_session: AsyncSession,
    name: str,
    enterprise_id: uuid.UUID | None = None,
    is_platform_managed: bool = False,
    agent_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Store:
    """ADR-003 uchun enterprise_id va is_platform_managed bilan do'kon yaratadi."""
    store = Store(
        id=uuid.uuid4(),
        name=name,
        enterprise_id=enterprise_id,
        is_platform_managed=is_platform_managed,
        agent_id=agent_id,
        user_id=user_id,
        version=1,
    )
    db_session.add(store)
    await db_session.flush()
    return store


async def create_user_with_enterprise(
    db_session: AsyncSession,
    role: str,
    enterprise_id: uuid.UUID | None = None,
) -> AppUser:
    """enterprise_id bilan AppUser yaratadi."""
    from app.core.jwt import hash_password
    user = AppUser(
        id=uuid.uuid4(),
        full_name=f"Test {role}",
        phone=f"+99890{str(abs(hash(role + str(uuid.uuid4()))))[:7]}",
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
    db_session.add(user)
    await db_session.flush()
    return user


async def create_contract(
    db_session: AsyncSession,
    store_id: uuid.UUID,
    enterprise_id: uuid.UUID,
) -> Contract:
    """Test shartnomasi yaratadi.

    ADR-003 Bo'lak C: supplier_enterprise_id ham o'rnatiladi
    (get_store_visibility_filter supplier_enterprise_id ishlatadi).
    """
    from datetime import date
    contract = Contract(
        id=uuid.uuid4(),
        store_id=store_id,
        enterprise_id=enterprise_id,           # legacy/MT1
        supplier_enterprise_id=enterprise_id,  # Shartnoma-Gate (Bo'lak C)
        number=f"CNT-{uuid.uuid4().hex[:8]}",
        valid_from=date(2025, 1, 1),
        valid_to=date(2030, 12, 31),
        contract_type="trade",
        version=1,
    )
    db_session.add(contract)
    await db_session.flush()
    return contract


@pytest.mark.asyncio
async def test_visibility_superadmin_no_filter(db_session: AsyncSession) -> None:
    """Superadmin (enterprise_id=None) → filtr yo'q (None qaytadi)."""
    superadmin = await create_user_with_enterprise(db_session, "superadmin", enterprise_id=None)
    result = get_store_visibility_filter(superadmin)
    assert result is None, "Superadmin uchun filtr yo'q bo'lishi kerak"


@pytest.mark.asyncio
async def test_visibility_admin_sees_own_enterprise_stores(db_session: AsyncSession) -> None:
    """Administrator o'z korxona do'konlarini ko'radi."""
    eid = uuid.uuid4()
    other_eid = uuid.uuid4()
    admin = await create_user_with_enterprise(db_session, "administrator", enterprise_id=eid)

    own_store = await create_store_with_enterprise(db_session, "Own Store", enterprise_id=eid)
    other_store = await create_store_with_enterprise(db_session, "Other Corp Store", enterprise_id=other_eid)
    platform_store = await create_store_with_enterprise(
        db_session, "Platform Store", enterprise_id=None, is_platform_managed=True
    )

    visibility = get_store_visibility_filter(admin)
    assert visibility is not None

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert own_store.id in ids, "Admin o'z korxona do'konini ko'rishi kerak"
    assert other_store.id not in ids, "Admin boshqa korxona do'konini ko'rmasligi kerak"
    # Shartnoma yo'q — platforma do'koni ko'rinmasligi kerak
    assert platform_store.id not in ids, "Shartnomasiz platforma do'koni ko'rinmasligi kerak"


@pytest.mark.asyncio
async def test_visibility_admin_sees_contracted_platform_stores(db_session: AsyncSession) -> None:
    """Administrator shartnoma qilgan platforma do'konlarini ham ko'radi."""
    eid = uuid.uuid4()
    admin = await create_user_with_enterprise(db_session, "administrator", enterprise_id=eid)

    # Platforma do'koni (enterprise_id=NULL, is_platform_managed=True)
    platform_store = await create_store_with_enterprise(
        db_session, "Contracted Platform Store", enterprise_id=None, is_platform_managed=True
    )
    # Shartnoma qilmagan platforma do'koni
    uncontracted_platform = await create_store_with_enterprise(
        db_session, "Uncontracted Platform", enterprise_id=None, is_platform_managed=True
    )

    # Shartnoma yaratish — admin korxonasi bilan
    await create_contract(db_session, platform_store.id, eid)

    visibility = get_store_visibility_filter(admin)
    assert visibility is not None

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert platform_store.id in ids, "Shartnoma qilgan platforma do'koni ko'rinishi kerak"
    assert uncontracted_platform.id not in ids, "Shartnoma qilinmagan platforma do'koni ko'rinmasligi kerak"


@pytest.mark.asyncio
async def test_visibility_accountant_same_as_admin(db_session: AsyncSession) -> None:
    """Buxgalter ham admin kabi o'z korxona + shartnoma qilgan platforma do'konlarini ko'radi."""
    eid = uuid.uuid4()
    accountant = await create_user_with_enterprise(db_session, "accountant", enterprise_id=eid)

    own_store = await create_store_with_enterprise(db_session, "Own", enterprise_id=eid)
    platform_store = await create_store_with_enterprise(
        db_session, "Contracted Platform", enterprise_id=None, is_platform_managed=True
    )
    await create_contract(db_session, platform_store.id, eid)

    visibility = get_store_visibility_filter(accountant)
    assert visibility is not None

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert own_store.id in ids
    assert platform_store.id in ids


@pytest.mark.asyncio
async def test_visibility_agent_sees_only_assigned_stores(db_session: AsyncSession) -> None:
    """Agent faqat biriktirilgan do'konlarni ko'radi (agent_id yoki AgentStore)."""
    eid = uuid.uuid4()
    agent = await create_user_with_enterprise(db_session, "agent", enterprise_id=eid)
    other_agent = await create_user_with_enterprise(db_session, "agent", enterprise_id=eid)

    direct_store = await create_store_with_enterprise(
        db_session, "Direct", enterprise_id=eid, agent_id=agent.id
    )
    table_store = await create_store_with_enterprise(
        db_session, "Via Table", enterprise_id=eid, agent_id=None
    )
    other_store = await create_store_with_enterprise(
        db_session, "Other Agent", enterprise_id=eid, agent_id=other_agent.id
    )

    # AgentStore yozuvi
    link = AgentStore(agent_id=agent.id, store_id=table_store.id)
    db_session.add(link)
    await db_session.flush()

    visibility = get_store_visibility_filter(agent)
    assert visibility is not None

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert direct_store.id in ids, "Agent to'g'ridan-to'g'ri biriktirilgan do'konni ko'rishi kerak"
    assert table_store.id in ids, "Agent AgentStore orqali biriktirilgan do'konni ko'rishi kerak"
    assert other_store.id not in ids, "Agent boshqa agentning do'konini ko'rmasligi kerak"


@pytest.mark.asyncio
async def test_visibility_store_role_sees_own_store(db_session: AsyncSession) -> None:
    """Store roli faqat o'z do'konini ko'radi (user_id orqali)."""
    eid = uuid.uuid4()
    store_user = await create_user_with_enterprise(db_session, "store", enterprise_id=eid)
    other_user = await create_user_with_enterprise(db_session, "store", enterprise_id=eid)

    own_store = await create_store_with_enterprise(
        db_session, "Own", enterprise_id=eid, user_id=store_user.id
    )
    other_store = await create_store_with_enterprise(
        db_session, "Other", enterprise_id=eid, user_id=other_user.id
    )
    no_owner = await create_store_with_enterprise(
        db_session, "No Owner", enterprise_id=eid, user_id=None
    )

    visibility = get_store_visibility_filter(store_user)
    assert visibility is not None

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert own_store.id in ids
    assert other_store.id not in ids
    assert no_owner.id not in ids


@pytest.mark.asyncio
async def test_visibility_courier_no_filter(db_session: AsyncSession) -> None:
    """Kuryer → None qaytadi (barcha do'kon manzillari ko'rinadi)."""
    eid = uuid.uuid4()
    courier = await create_user_with_enterprise(db_session, "courier", enterprise_id=eid)
    result = get_store_visibility_filter(courier)
    assert result is None, "Kuryer uchun filtr yo'q bo'lishi kerak"


@pytest.mark.asyncio
async def test_visibility_unknown_role_deny_all(db_session: AsyncSession) -> None:
    """Noma'lum rol → deny-all filtri (Store.id.is_(None))."""
    import types
    eid = uuid.uuid4()
    fake_user = types.SimpleNamespace(id=uuid.uuid4(), role="hacker", enterprise_id=eid)

    await create_store_with_enterprise(db_session, "Any Store", enterprise_id=eid)

    visibility = get_store_visibility_filter(fake_user)  # type: ignore[arg-type]
    assert visibility is not None, "Noma'lum rol uchun deny-all filtri qaytishi kerak"

    stmt = select(Store).where(visibility)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()
    assert len(stores) == 0, "Noma'lum rol hech narsa ko'rmasligi kerak"
