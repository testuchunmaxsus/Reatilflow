"""
Superadmin audit-logs va banners endpointlari testlari.

Scenariylar — audit-logs:
  1.  GET /superadmin/audit-logs — bo'sh natija (log yo'q)
  2.  GET /superadmin/audit-logs — loglar mavjud, to'g'ri maydonlar
  3.  GET /superadmin/audit-logs?action — action filtri
  4.  GET /superadmin/audit-logs?entity_type — entity_type filtri
  5.  GET /superadmin/audit-logs?enterprise_id — enterprise_id filtri
  6.  GET /superadmin/audit-logs?entity_id — entity_id filtri
  7.  GET /superadmin/audit-logs — tartib at DESC
  8.  GET /superadmin/audit-logs — pagination (limit/offset)
  9.  GET /superadmin/audit-logs — 403 superadmin emas (administrator)
  10. GET /superadmin/audit-logs — 401 autentifikatsiya yo'q

Scenariylar — banners:
  11. GET /superadmin/banners — bo'sh natija
  12. GET /superadmin/banners — barcha holatlar (aktiv + nofaol) ro'yxati
  13. GET /superadmin/banners — enterprise_name to'g'ri qo'shilgan
  14. GET /superadmin/banners?is_active=true — faqat aktiv bannerlar
  15. GET /superadmin/banners?is_active=false — faqat nofaol bannerlar
  16. GET /superadmin/banners?enterprise_id — korxona filtri
  17. GET /superadmin/banners — tartib priority DESC, created_at DESC
  18. GET /superadmin/banners — 403 superadmin emas (administrator)
  19. GET /superadmin/banners — 401 autentifikatsiya yo'q
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ad_banner import AdBanner
from app.models.audit import AuditLog
from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.tests.conftest import TEST_ENTERPRISE_UUID


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def _make_enterprise(
    db: AsyncSession,
    name: str = "Test Ent",
    status: str = "active",
) -> Enterprise:
    ent = Enterprise(
        id=uuid.uuid4(),
        name=name,
        inn=None,
        status=status,
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db.add(ent)
    await db.flush()
    return ent


async def _make_audit_log(
    db: AsyncSession,
    action: str = "create",
    entity_type: str = "app_user",
    entity_id: str | None = None,
    enterprise_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    ip: str | None = "127.0.0.1",
    at: datetime | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id or str(uuid.uuid4()),
        before_json=None,
        after_json='{"field": "value"}',
        ip=ip,
        enterprise_id=enterprise_id,
    )
    if at is not None:
        log.at = at
    db.add(log)
    await db.flush()
    return log


async def _make_banner(
    db: AsyncSession,
    enterprise: Enterprise,
    title: str = "Test Banner",
    is_active: bool = True,
    priority: int = 0,
) -> AdBanner:
    today = _today()
    banner = AdBanner(
        enterprise_id=enterprise.id,
        title=title,
        image_url=None,
        target_url="https://example.com",
        target_product_id=None,
        is_active=is_active,
        priority=priority,
        valid_from=today,
        valid_to=date(today.year + 1, today.month, today.day),
    )
    db.add(banner)
    await db.flush()
    return banner


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOGS
# ═══════════════════════════════════════════════════════════════════════════════


# ─── 1. Bo'sh natija ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_empty(
    superadmin_client: AsyncClient,
) -> None:
    """Hech qanday log yo'q → bo'sh items, total=0."""
    resp = await superadmin_client.get("/superadmin/audit-logs")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["limit"] == 50
    assert data["offset"] == 0


# ─── 2. Loglar mavjud, to'g'ri maydonlar ─────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_structure(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """Mavjud log to'g'ri maydonlar bilan qaytadi."""
    actor_id = uuid.uuid4()
    log = await _make_audit_log(
        db_session,
        action="login",
        entity_type="app_user",
        entity_id="some-entity-id",
        enterprise_id=default_enterprise.id,
        actor_id=actor_id,
        ip="192.168.1.1",
    )

    resp = await superadmin_client.get("/superadmin/audit-logs")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["id"] == str(log.id)
    assert item["actor_id"] == str(actor_id)
    assert item["action"] == "login"
    assert item["entity_type"] == "app_user"
    assert item["entity_id"] == "some-entity-id"
    assert item["ip"] == "192.168.1.1"
    assert item["enterprise_id"] == str(default_enterprise.id)
    assert item["after_json"] == '{"field": "value"}'
    assert item["before_json"] is None
    assert "at" in item


# ─── 3. action filtri ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """action=create filtri faqat create loglarni qaytaradi."""
    await _make_audit_log(db_session, action="create", enterprise_id=default_enterprise.id)
    await _make_audit_log(db_session, action="delete", enterprise_id=default_enterprise.id)
    await _make_audit_log(db_session, action="login", enterprise_id=default_enterprise.id)

    resp = await superadmin_client.get("/superadmin/audit-logs?action=create")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    for item in data["items"]:
        assert item["action"] == "create"


# ─── 4. entity_type filtri ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_filter_by_entity_type(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """entity_type=enterprise filtri ishlaydi."""
    await _make_audit_log(db_session, entity_type="enterprise", enterprise_id=default_enterprise.id)
    await _make_audit_log(db_session, entity_type="app_user", enterprise_id=default_enterprise.id)
    await _make_audit_log(db_session, entity_type="product", enterprise_id=default_enterprise.id)

    resp = await superadmin_client.get("/superadmin/audit-logs?entity_type=enterprise")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["entity_type"] == "enterprise"


# ─── 5. enterprise_id filtri ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_filter_by_enterprise_id(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """enterprise_id filtri cross-tenant izolyatsiyani ta'minlaydi."""
    other_ent = await _make_enterprise(db_session, name="Boshqa Ent Audit")

    await _make_audit_log(db_session, enterprise_id=default_enterprise.id, action="create")
    await _make_audit_log(db_session, enterprise_id=other_ent.id, action="update")
    await _make_audit_log(db_session, enterprise_id=None, action="login")  # system log

    resp = await superadmin_client.get(
        f"/superadmin/audit-logs?enterprise_id={default_enterprise.id}"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["enterprise_id"] == str(default_enterprise.id)


# ─── 6. entity_id filtri ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_filter_by_entity_id(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """entity_id filtri aniq yozuvga yo'naltiradi."""
    target_id = str(uuid.uuid4())
    await _make_audit_log(db_session, entity_id=target_id)
    await _make_audit_log(db_session, entity_id=str(uuid.uuid4()))

    resp = await superadmin_client.get(f"/superadmin/audit-logs?entity_id={target_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["entity_id"] == target_id


# ─── 7. Tartib at DESC ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_order_by_at_desc(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Loglar at DESC tartibida qaytadi (eng yangi birinchi)."""
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    t3 = datetime(2025, 1, 1, tzinfo=timezone.utc)

    await _make_audit_log(db_session, action="create", at=t1)
    await _make_audit_log(db_session, action="update", at=t2)
    await _make_audit_log(db_session, action="delete", at=t3)

    resp = await superadmin_client.get("/superadmin/audit-logs")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 3

    # Birinchi element eng katta at qiymatiga ega bo'lishi shart
    ats = [item["at"] for item in items]
    assert ats == sorted(ats, reverse=True)


# ─── 8. Pagination limit/offset ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_pagination(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """limit/offset pagination to'g'ri ishlaydi."""
    for i in range(5):
        await _make_audit_log(
            db_session,
            action=f"action_{i}",
            entity_type="product",
            enterprise_id=default_enterprise.id,
        )

    # limit=2, offset=0 → 2 ta element
    resp = await superadmin_client.get("/superadmin/audit-logs?limit=2&offset=0")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    # limit=2, offset=4 → 1 ta element
    resp2 = await superadmin_client.get("/superadmin/audit-logs?limit=2&offset=4")
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert len(data2["items"]) == 1


# ─── 9. 403 administrator ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_requires_superadmin(
    admin_client: AsyncClient,
) -> None:
    """administrator /superadmin/audit-logs → 403."""
    resp = await admin_client.get("/superadmin/audit-logs")
    assert resp.status_code == 403, resp.text


# ─── 10. 401 autentifikatsiya yo'q ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_logs_requires_auth(
    no_auth_client: AsyncClient,
) -> None:
    """Tokensiz /superadmin/audit-logs → 401."""
    resp = await no_auth_client.get("/superadmin/audit-logs")
    assert resp.status_code == 401, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# BANNERS
# ═══════════════════════════════════════════════════════════════════════════════


# ─── 11. Bo'sh natija ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_empty(
    superadmin_client: AsyncClient,
) -> None:
    """Banner yo'q → bo'sh items, total=0."""
    resp = await superadmin_client.get("/superadmin/banners")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["limit"] == 50
    assert data["offset"] == 0


# ─── 12. Barcha holatlar ro'yxati (aktiv + nofaol) ───────────────────────────


@pytest.mark.asyncio
async def test_banners_all_statuses_returned(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """Superadmin aktiv ham, nofaol ham bannerlarni ko'radi."""
    await _make_banner(db_session, default_enterprise, title="Aktiv Banner", is_active=True)
    await _make_banner(db_session, default_enterprise, title="Nofaol Banner", is_active=False)

    resp = await superadmin_client.get("/superadmin/banners")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2

    active_flags = {item["is_active"] for item in data["items"]}
    assert True in active_flags
    assert False in active_flags


# ─── 13. enterprise_name to'g'ri qo'shilgan ──────────────────────────────────


@pytest.mark.asyncio
async def test_banners_enterprise_name_included(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """Javobda enterprise_name korxona nomiga mos bo'lishi shart."""
    await _make_banner(db_session, default_enterprise, title="Banner With Name")

    resp = await superadmin_client.get("/superadmin/banners")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1

    item = items[0]
    assert "enterprise_name" in item
    assert item["enterprise_name"] == default_enterprise.name
    assert item["enterprise_id"] == str(default_enterprise.id)


# ─── 14. is_active=true filtri ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_filter_is_active_true(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """is_active=true faqat aktiv bannerlarni qaytaradi."""
    await _make_banner(db_session, default_enterprise, title="Aktiv 1", is_active=True)
    await _make_banner(db_session, default_enterprise, title="Nofaol 1", is_active=False)
    await _make_banner(db_session, default_enterprise, title="Aktiv 2", is_active=True)

    resp = await superadmin_client.get("/superadmin/banners?is_active=true")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["is_active"] is True


# ─── 15. is_active=false filtri ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_filter_is_active_false(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """is_active=false faqat nofaol bannerlarni qaytaradi."""
    await _make_banner(db_session, default_enterprise, title="Aktiv X", is_active=True)
    await _make_banner(db_session, default_enterprise, title="Nofaol X", is_active=False)

    resp = await superadmin_client.get("/superadmin/banners?is_active=false")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["is_active"] is False


# ─── 16. enterprise_id filtri ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_filter_by_enterprise_id(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """enterprise_id filtri faqat o'sha korxona bannerlarini qaytaradi."""
    other_ent = await _make_enterprise(db_session, name="Boshqa Ent Banner")

    await _make_banner(db_session, default_enterprise, title="Banner 1")
    await _make_banner(db_session, other_ent, title="Banner Other")

    resp = await superadmin_client.get(
        f"/superadmin/banners?enterprise_id={default_enterprise.id}"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["enterprise_id"] == str(default_enterprise.id)
    assert data["items"][0]["title"] == "Banner 1"


# ─── 17. Tartib priority DESC, created_at DESC ────────────────────────────────


@pytest.mark.asyncio
async def test_banners_order_by_priority_desc(
    superadmin_client: AsyncClient,
    default_enterprise: Enterprise,
    db_session: AsyncSession,
) -> None:
    """Bannerlar priority DESC tartibida qaytadi."""
    await _make_banner(db_session, default_enterprise, title="Low Prio", priority=1)
    await _make_banner(db_session, default_enterprise, title="High Prio", priority=100)
    await _make_banner(db_session, default_enterprise, title="Mid Prio", priority=50)

    resp = await superadmin_client.get("/superadmin/banners")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 3

    priorities = [item["priority"] for item in items]
    assert priorities == sorted(priorities, reverse=True)


# ─── 18. 403 administrator ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_requires_superadmin(
    admin_client: AsyncClient,
) -> None:
    """administrator /superadmin/banners → 403."""
    resp = await admin_client.get("/superadmin/banners")
    assert resp.status_code == 403, resp.text


# ─── 19. 401 autentifikatsiya yo'q ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_requires_auth(
    no_auth_client: AsyncClient,
) -> None:
    """Tokensiz /superadmin/banners → 401."""
    resp = await no_auth_client.get("/superadmin/banners")
    assert resp.status_code == 401, resp.text
