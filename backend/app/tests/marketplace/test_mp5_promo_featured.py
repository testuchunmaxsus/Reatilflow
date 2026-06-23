"""
MP5 Qaynoq aksiyalar (marketplace promo featured) testlari.

Qamrov:
  1. Korxona aksiyani featured qiladi → GET /marketplace/promos da ko'rinadi.
  2. Featured EMAS aksiya GET /marketplace/promos da ko'rinmaydi (izolyatsiya).
  3. IDOR: boshqa korxona aksiyasini featured qila olmaydi → 404.
  4. Muddati o'tgan/o'chiq aksiya featured bo'lsa ham ko'rinmaydi.
  5. Featured toggle: featured=False → marketplace'dan olib tashlanadi.
  6. Module "marketplace" o'chiq → 403 (GET /marketplace/promos).
  7. Promo moduli tekshiruvi: /promos/{id}/marketplace-featured.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import ALL_MODULE_KEYS, Enterprise
from app.models.user import AppUser
from app.tests.marketplace.conftest import TEST_ENTERPRISE_B_UUID, get_token


# ─── Yordamchi ───────────────────────────────────────────────────────────────


def _today() -> date:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()


def _yesterday() -> date:
    return _today() - timedelta(days=1)


def _tomorrow() -> date:
    return _today() + timedelta(days=1)


async def _create_promo(
    client: AsyncClient,
    token: str,
    name_uz: str = "Test aksiya",
    name_ru: str = "Test акция",
    is_active: bool = True,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> dict:
    """Admin tomonidan aksiya yaratadi va javobni qaytaradi."""
    vf = valid_from or _yesterday()
    vt = valid_to or _tomorrow()
    resp = await client.post(
        "/promos",
        json={
            "name_uz": name_uz,
            "name_ru": name_ru,
            "promo_type": "discount",
            "rule_json": {"discount_percent": 10},
            "valid_from": str(vf),
            "valid_to": str(vt),
            "is_active": is_active,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


async def _set_featured(
    client: AsyncClient,
    token: str,
    promo_id: str,
    featured: bool,
) -> dict:
    """Aksiyani featured qiladi."""
    resp = await client.patch(
        f"/promos/{promo_id}/marketplace-featured",
        json={"featured": featured},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


# ─── 1. Featured → ko'rinadi ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_featured_promo_visible_in_marketplace(
    mp_client: AsyncClient,
    admin_a: AppUser,
    enterprise_a: Enterprise,
) -> None:
    """Korxona aksiyani featured qiladi → GET /marketplace/promos da ko'rinadi."""
    token = await get_token(mp_client, admin_a)

    # Aksiya yaratish
    resp = await _create_promo(mp_client, token, name_uz="Qaynoq aksiya A")
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # Featured qilish
    feat_resp = await _set_featured(mp_client, token, promo_id, True)
    assert feat_resp.status_code == 200, feat_resp.text
    assert feat_resp.json()["marketplace_featured"] is True

    # Marketplace promos ro'yxatida ko'rinadi
    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id in ids

    # enterprise_id va supplier_name qaytadi
    found = next(p for p in list_resp.json() if p["id"] == promo_id)
    assert found["enterprise_id"] == str(enterprise_a.id)
    assert found["supplier_name"] == enterprise_a.name


# ─── 2. Featured emas → ko'rinmaydi (izolyatsiya) ────────────────────────────


@pytest.mark.asyncio
async def test_non_featured_promo_not_visible_in_marketplace(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """Featured emas aktiv aksiya GET /marketplace/promos da ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)

    resp = await _create_promo(mp_client, token, name_uz="Oddiy aksiya")
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # Featured QILINMAYDI

    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id not in ids


# ─── 3. IDOR: boshqa korxona aksiyasini featured qila olmaydi ────────────────


@pytest.mark.asyncio
async def test_featured_other_enterprise_promo_404(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """B korxona A aksiyasini featured qila olmaydi → 404."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    # A korxona aksiya yaratadi
    resp = await _create_promo(mp_client, token_a, name_uz="A aksiya")
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # B korxona A aksiyasini featured qilishga urinadi → 404
    feat_resp = await _set_featured(mp_client, token_b, promo_id, True)
    assert feat_resp.status_code == 404, feat_resp.text


# ─── 4. Muddati o'tgan featured aksiya ko'rinmaydi ───────────────────────────


@pytest.mark.asyncio
async def test_expired_featured_promo_not_visible(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """valid_to = yesterday, featured=True → GET /marketplace/promos da ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)

    past = _today() - timedelta(days=10)
    resp = await _create_promo(
        mp_client, token,
        name_uz="Muddati o'tgan featured",
        valid_from=past - timedelta(days=5),
        valid_to=past,
    )
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # Featured qilamiz
    feat_resp = await _set_featured(mp_client, token, promo_id, True)
    assert feat_resp.status_code == 200

    # Lekin browse da ko'rinmaydi (muddati o'tgan)
    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id not in ids


# ─── 5. O'chiq featured aksiya ko'rinmaydi ────────────────────────────────────


@pytest.mark.asyncio
async def test_inactive_featured_promo_not_visible(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """is_active=False, featured=True → GET /marketplace/promos da ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)

    resp = await _create_promo(mp_client, token, name_uz="O'chiq featured", is_active=False)
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # Featured qilamiz (is_active=False bo'lsa ham toggle ishlaydi)
    feat_resp = await _set_featured(mp_client, token, promo_id, True)
    assert feat_resp.status_code == 200

    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id not in ids


# ─── 6. Featured toggle: False → marketplace'dan olib tashlash ───────────────


@pytest.mark.asyncio
async def test_unfeatured_promo_removed_from_marketplace(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """featured=True → ko'rinadi; featured=False → ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)

    resp = await _create_promo(mp_client, token, name_uz="Toggle test aksiya")
    assert resp.status_code == 201, resp.text
    promo_id = resp.json()["id"]

    # Featured qilamiz
    await _set_featured(mp_client, token, promo_id, True)

    # Ko'rinadi
    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id in ids

    # Featured olib tashlaymiz
    await _set_featured(mp_client, token, promo_id, False)

    # Endi ko'rinmaydi
    list_resp2 = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    ids2 = [p["id"] for p in list_resp2.json()]
    assert promo_id not in ids2


# ─── 7. Cross-tenant: B aksiyasi A tomonidan ko'rinadi ───────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_featured_promo_visible(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """B korxona aksiyasi featured → A tomonidan GET /marketplace/promos da ko'rinadi."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    # B aksiya yaratadi va featured qiladi
    resp_b = await _create_promo(mp_client, token_b, name_uz="B qaynoq aksiya")
    assert resp_b.status_code == 201, resp_b.text
    promo_id_b = resp_b.json()["id"]

    feat_resp = await _set_featured(mp_client, token_b, promo_id_b, True)
    assert feat_resp.status_code == 200

    # A foydalanuvchisi ko'radi
    list_resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert promo_id_b in ids

    found = next(p for p in list_resp.json() if p["id"] == promo_id_b)
    assert found["enterprise_id"] == str(enterprise_b.id)
    assert found["supplier_name"] == enterprise_b.name


# ─── 8. Module gating: marketplace o'chiq → 403 ──────────────────────────────


@pytest.mark.asyncio
async def test_marketplace_promos_module_gating(
    mp_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """marketplace moduli o'chiq → GET /marketplace/promos → 403."""
    from app.core.jwt import hash_password
    from app.models.user import AppUser as UserModel

    ent_no_mp = Enterprise(
        id=uuid.UUID("00000000-0000-7000-8000-000000000066"),
        name="No Marketplace Promo",
        status="active",
        enabled_modules=[m for m in ALL_MODULE_KEYS if m != "marketplace"],
        version=1,
    )
    db_session.add(ent_no_mp)
    await db_session.flush()

    user_no_mp = UserModel(
        id=uuid.uuid4(),
        full_name="No MP Promo User",
        phone="+998905551234",
        role="administrator",
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=ent_no_mp.id,
    )
    db_session.add(user_no_mp)
    await db_session.flush()

    token = await get_token(mp_client, user_no_mp)

    resp = await mp_client.get(
        "/marketplace/promos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
