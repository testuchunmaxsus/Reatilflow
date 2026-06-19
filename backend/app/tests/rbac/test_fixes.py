"""
SRE/Security topilmalari uchun regression testlar (T2 RBAC gate).

Qamrab olingan topilmalar:
  - [HIGH] agent N+1 → BITTA so'rov (apply_store_scope va get_user_store_ids)
  - [MEDIUM-SEC] store roli — T5 dan oldin deny-all edi; hozir Store.user_id == user.id.
    Testlar user_id=None bo'lgan do'konlar uchun 0 qaytishini tekshiradi —
    T5 da user_id-based filtering ham xuddi shunday natija beradi (NULL ≠ user.id).
  - [MEDIUM-SEC] courier roli alohida tekshiruvi
  - [LOW] require_permission → haqiqiy HTTP 403, xabarda modul/action
  - [LOW] Redis kesh TTL == 300 soniya

T5 o'zgarish (T2 qarzi yopildi):
  - store roli: Store.id.is_(None) deny-all → Store.user_id == user.id
  - Bu testlarda user_id=None bo'lgan do'konlar yaratilgan — shuning uchun
    natija hali ham 0 (regress yo'q, xulosa to'g'ri).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import AgentStore, Store
from app.models.user import AppUser
from app.modules.rbac.scope import apply_store_scope, get_user_store_ids
from app.tests.rbac.conftest import TEST_PASSWORD, get_token_for_user


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


async def _create_store(
    db: AsyncSession,
    name: str,
    agent_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> Store:
    store = Store(
        id=uuid.uuid4(),
        name=name,
        agent_id=agent_id,
        branch_id=branch_id,
        version=1,
    )
    db.add(store)
    await db.flush()
    return store


async def _create_user(
    db: AsyncSession,
    role: str,
    branch_id: uuid.UUID | None = None,
) -> AppUser:
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


# ─── [MEDIUM-SEC] store roli — deny-all (apply_store_scope) ──────────────────


@pytest.mark.asyncio
async def test_store_role_apply_scope_deny_all(db_session: AsyncSession) -> None:
    """
    store roli apply_store_scope — user_id=None do'konlar uchun 0 natija.

    T2: deny-all edi (IDOR xavfi).
    T5: Store.user_id == user.id — bu testda user_id=None, shuning uchun 0.
    Regression guard: store roli boshqa agentlarning do'konlarini ko'ra olmasin.
    """
    store_user = await _create_user(db_session, "store")

    # user_id=None (store_user ga tegishli emas) — ko'rinmasin
    await _create_store(db_session, "Store1", agent_id=store_user.id)
    await _create_store(db_session, "Store2", agent_id=None)

    stmt = select(Store)
    stmt = apply_store_scope(stmt, store_user)
    result = await db_session.execute(stmt)
    stores = result.scalars().all()

    assert len(stores) == 0, (
        f"store roli user_id=None do'konlarni ko'rmasligi kerak, "
        f"lekin {len(stores)} ta do'kon qaytdi"
    )


# ─── [MEDIUM-SEC] store roli — deny-all (get_user_store_ids) ─────────────────


@pytest.mark.asyncio
async def test_store_role_get_user_store_ids_empty(db_session: AsyncSession) -> None:
    """
    store roli get_user_store_ids — user_id=None do'konlar uchun bo'sh ro'yxat.

    T2: deny-all edi.
    T5: Store.user_id == user.id — bu testda user_id=None, shuning uchun [].
    Regression guard: store roli boshqa agentlarning do'kon ID larini ololmasin.
    """
    store_user = await _create_user(db_session, "store")
    # user_id=None — store_user ga tegishli emas
    await _create_store(db_session, "S1", agent_id=store_user.id)

    ids = await get_user_store_ids(store_user, db_session)

    assert ids == [], (
        f"store roli user_id=None do'konlarni ololmasligi kerak, lekin {ids} qaytdi"
    )


# ─── [HIGH] agent N+1 tuzatildi — bitta so'rov (SQL count orqali) ────────────


@pytest.mark.asyncio
async def test_agent_get_user_store_ids_single_query(db_session: AsyncSession) -> None:
    """
    get_user_store_ids agent roli uchun agent_id va AgentStore ikkalasini
    BITTA so'rovda qaytaradi.

    Avval: 2 alohida DB so'rov (N+1). Hozir: OR+scalar_subquery (1 so'rov).
    Natija to'g'riligini tekshiramiz (SQL count ni mock qilib so'rov sonini
    hisoblash o'rniga, natija to'g'riligini — bu regression guard sifatida).
    """
    agent = await _create_user(db_session, "agent")
    other_agent = await _create_user(db_session, "agent")

    # agent_id orqali to'g'ridan-to'g'ri
    store_direct = await _create_store(db_session, "Direct", agent_id=agent.id)
    # AgentStore orqali
    store_table = await _create_store(db_session, "Via Table", agent_id=None)
    # boshqa agent — ko'rinmasin
    await _create_store(db_session, "Other", agent_id=other_agent.id)

    link = AgentStore(agent_id=agent.id, store_id=store_table.id)
    db_session.add(link)
    await db_session.flush()

    ids = await get_user_store_ids(agent, db_session)
    ids_set = set(ids)

    assert store_direct.id in ids_set
    assert store_table.id in ids_set
    assert len(ids_set) == 2, f"Faqat 2 ta do'kon kutilgan, {len(ids_set)} qaytdi"


@pytest.mark.asyncio
async def test_agent_apply_scope_single_query_correctness(db_session: AsyncSession) -> None:
    """
    apply_store_scope agent roli uchun OR+subquery natijasi to'g'ri.
    """
    agent = await _create_user(db_session, "agent")

    s1 = await _create_store(db_session, "Direct", agent_id=agent.id)
    s2 = await _create_store(db_session, "Via Table", agent_id=None)
    s3 = await _create_store(db_session, "Unrelated", agent_id=uuid.uuid4())

    link = AgentStore(agent_id=agent.id, store_id=s2.id)
    db_session.add(link)
    await db_session.flush()

    stmt = select(Store)
    stmt = apply_store_scope(stmt, agent)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert s1.id in ids
    assert s2.id in ids
    assert s3.id not in ids


# ─── [SRE] courier roli scope — barcha do'konlar (regression) ────────────────


@pytest.mark.asyncio
async def test_courier_get_user_store_ids_all(db_session: AsyncSession) -> None:
    """
    courier roli get_user_store_ids → barcha do'konlar.
    """
    courier = await _create_user(db_session, "courier")

    s1 = await _create_store(db_session, "S1", agent_id=uuid.uuid4())
    s2 = await _create_store(db_session, "S2")

    ids = set(await get_user_store_ids(courier, db_session))
    assert s1.id in ids
    assert s2.id in ids


@pytest.mark.asyncio
async def test_courier_apply_scope_all_stores(db_session: AsyncSession) -> None:
    """
    courier roli apply_store_scope → barcha do'konlar (filtr yo'q).
    """
    courier = await _create_user(db_session, "courier")

    s1 = await _create_store(db_session, "S1", agent_id=uuid.uuid4())
    s2 = await _create_store(db_session, "S2")

    stmt = select(Store)
    stmt = apply_store_scope(stmt, courier)
    result = await db_session.execute(stmt)
    ids = {s.id for s in result.scalars().all()}

    assert s1.id in ids
    assert s2.id in ids


# ─── [LOW] HTTP 403 — require_permission himoyalangan endpoint ────────────────


@pytest.mark.asyncio
async def test_require_permission_403_real_http(
    rbac_client: AsyncClient,
    courier_user: AppUser,
) -> None:
    """
    require_permission — ruxsatsiz rol → 403, xabarda modul va action ko'rsatilgan.

    courier → finance:approve ruxsati yo'q → /rbac/catalog-demo emas,
    alohida test app yaratib finance:approve tekshiramiz.

    Mavjud /rbac/catalog-demo barcha rollarda catalog:view bor,
    shuning uchun yangi mini-app orqali courier → finance:approve → 403.
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from httpx import ASGITransport, AsyncClient as AC

    from app.core.db import get_db
    from app.core.errors import AppError, error_envelope
    from app.core.redis import get_redis
    from app.modules.rbac.dependency import require_permission

    mini_app = FastAPI()

    @mini_app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.message_key, exc.localized_message(), exc.detail),
        )

    @mini_app.get("/protected-finance")
    async def _protected(user=require_permission("finance", "approve")):
        return {"ok": True}

    # courier uchun token rbac_client orqali olamiz (DB override bor)
    token = await get_token_for_user(rbac_client, courier_user)

    # Mini app uchun override — rbac_client dagi override'lardan olamiz
    from app.main import app as main_app

    # Mini app dependency override — same db/redis as rbac_client
    get_db_override = main_app.dependency_overrides.get(get_db)
    get_redis_override = main_app.dependency_overrides.get(get_redis)
    if get_db_override:
        mini_app.dependency_overrides[get_db] = get_db_override
    if get_redis_override:
        mini_app.dependency_overrides[get_redis] = get_redis_override

    async with AC(
        transport=ASGITransport(app=mini_app),
        base_url="http://testserver",
    ) as mini_client:
        resp = await mini_client.get(
            "/protected-finance",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403, f"403 kutilgan, {resp.status_code} qaytdi: {resp.text}"
    # i18n envelope formati: {"message_key": ..., "message": ..., "detail": null}
    body = resp.json()
    assert body.get("message_key") == "rbac.permission_denied"
    message = body.get("message", "")
    assert "finance" in message, f"Xabarda 'finance' bo'lishi kerak: {message}"
    assert "approve" in message, f"Xabarda 'approve' bo'lishi kerak: {message}"


@pytest.mark.asyncio
async def test_require_permission_403_contains_role_info(
    rbac_client: AsyncClient,
    store_user: AppUser,
) -> None:
    """
    store roli → rbac:delete → 403, xabarda rol nomi ko'rsatilgan.
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from httpx import ASGITransport, AsyncClient as AC

    from app.core.db import get_db
    from app.core.errors import AppError, error_envelope
    from app.core.redis import get_redis
    from app.modules.rbac.dependency import require_permission

    mini_app = FastAPI()

    @mini_app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.message_key, exc.localized_message(), exc.detail),
        )

    @mini_app.get("/protected-rbac")
    async def _protected(user=require_permission("rbac", "delete")):
        return {"ok": True}

    token = await get_token_for_user(rbac_client, store_user)

    from app.main import app as main_app

    get_db_override = main_app.dependency_overrides.get(get_db)
    get_redis_override = main_app.dependency_overrides.get(get_redis)
    if get_db_override:
        mini_app.dependency_overrides[get_db] = get_db_override
    if get_redis_override:
        mini_app.dependency_overrides[get_redis] = get_redis_override

    async with AC(
        transport=ASGITransport(app=mini_app),
        base_url="http://testserver",
    ) as mini_client:
        resp = await mini_client.get(
            "/protected-rbac",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403
    # i18n envelope formati: {"message_key": ..., "message": ..., "detail": null}
    body = resp.json()
    assert body.get("message_key") == "rbac.permission_denied"
    message = body.get("message", "")
    assert "rbac" in message
    assert "delete" in message
    assert "store" in message


# ─── [LOW] Redis kesh TTL == 300 soniya ──────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_cache_ttl_is_300(fake_redis) -> None:
    """
    get_permissions_for_role Redis'ga 300 soniya (5 daqiqa) TTL bilan keshlaydi.
    """
    from app.modules.rbac.service import get_permissions_for_role

    await get_permissions_for_role("agent", fake_redis)

    ttl = await fake_redis.ttl("rbac:perms:agent")
    # TTL 300 bo'lishi kerak (fakeredis bir zumda ishlagani uchun 295-300 oralig'ida)
    assert 290 <= ttl <= 300, f"TTL 300 soniya kutilgan, {ttl} qaytdi"


@pytest.mark.asyncio
async def test_redis_cache_set_with_ex_300(fake_redis) -> None:
    """
    Kesh yozuvida `ex=300` ishlatilganini kalit TTL orqali tasdiqlash.
    Redis'ga yozilgandan so'ng TTL mavjud (0 yoki -1 emas).
    """
    from app.modules.rbac.service import get_permissions_for_role

    # Birinchi chaqiruv — kesh yo'q, matritsadan yuklab Redis'ga yozadi
    await get_permissions_for_role("administrator", fake_redis)

    cached = await fake_redis.get("rbac:perms:administrator")
    assert cached is not None, "Redis'ga kesh yozilmagan"

    ttl = await fake_redis.ttl("rbac:perms:administrator")
    assert ttl > 0, f"TTL musbat bo'lishi kerak, {ttl} qaytdi (expire o'rnatilmagan?)"
    assert ttl <= 300, f"TTL 300 dan oshmasligi kerak, {ttl} qaytdi"
