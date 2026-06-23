"""
MP5 Reklama banner testlari.

Qamrov:
  1. Korxona banner yaratadi → GET /marketplace/banners da ko'rinadi (aktiv+valid).
  2. IDOR: boshqa korxona bannerini tahrirlaydi → 404.
  3. Muddati o'tgan banner ko'rinmaydi.
  4. O'chiq (is_active=False) banner ko'rinmaydi.
  5. Priority tartib: yuqori son birinchi ko'rsatiladi.
  6. Superadmin har qanday bannerni deactivate qiladi (PATCH is_active=False).
  7. Module "marketplace" o'chiq → 403.
  8. Superadmin banner yarata OLMAYDI (enterprise kerak) → 422.
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


async def _create_banner(
    client: AsyncClient,
    token: str,
    title: str = "Test Banner",
    is_active: bool = True,
    priority: int = 0,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> dict:
    """Admin tomonidan banner yaratadi va javobni qaytaradi."""
    vf = valid_from or _yesterday()
    vt = valid_to or _tomorrow()
    resp = await client.post(
        "/marketplace/banners",
        json={
            "title": title,
            "is_active": is_active,
            "priority": priority,
            "valid_from": str(vf),
            "valid_to": str(vt),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


# ─── 1. Banner yaratish → ko'rinadi ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_banner_visible_in_list(
    mp_client: AsyncClient,
    admin_a: AppUser,
    enterprise_a: Enterprise,
) -> None:
    """Korxona banner yaratadi → GET /marketplace/banners da ko'rinadi."""
    token = await get_token(mp_client, admin_a)

    # Banner yaratish
    resp = await _create_banner(mp_client, token, title="A korxona reklama")
    assert resp.status_code == 201, resp.text
    banner_id = resp.json()["id"]
    assert resp.json()["enterprise_id"] == str(enterprise_a.id)

    # Bannerlar ro'yxatini ko'rish
    list_resp = await mp_client.get(
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [b["id"] for b in list_resp.json()]
    assert banner_id in ids


# ─── 2. IDOR: boshqa korxona banneri → 404 ───────────────────────────────────


@pytest.mark.asyncio
async def test_patch_other_enterprise_banner_404(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """A korxona banneri B korxona tomonidan tahrirlana olmaydi → 404."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    # A banner yaratadi
    resp = await _create_banner(mp_client, token_a, title="A reklama")
    assert resp.status_code == 201, resp.text
    banner_id = resp.json()["id"]

    # B o'z tokenida A bannerini tahrirlashga urinadi → 404
    patch_resp = await mp_client.patch(
        f"/marketplace/banners/{banner_id}",
        json={"title": "B hujum"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert patch_resp.status_code == 404, patch_resp.text


# ─── 3. Muddati o'tgan banner ko'rinmaydi ────────────────────────────────────


@pytest.mark.asyncio
async def test_expired_banner_not_visible(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """valid_to = yesterday → GET /marketplace/banners da ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)
    past_date = _today() - timedelta(days=10)

    resp = await _create_banner(
        mp_client, token,
        title="Muddati o'tgan banner",
        valid_from=past_date - timedelta(days=5),
        valid_to=past_date,
    )
    assert resp.status_code == 201, resp.text
    banner_id = resp.json()["id"]

    list_resp = await mp_client.get(
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [b["id"] for b in list_resp.json()]
    assert banner_id not in ids


# ─── 4. O'chiq banner ko'rinmaydi ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inactive_banner_not_visible(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """is_active=False → GET /marketplace/banners da ko'rinmaydi."""
    token = await get_token(mp_client, admin_a)

    resp = await _create_banner(mp_client, token, title="O'chiq banner", is_active=False)
    assert resp.status_code == 201, resp.text
    banner_id = resp.json()["id"]

    list_resp = await mp_client.get(
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [b["id"] for b in list_resp.json()]
    assert banner_id not in ids


# ─── 5. Priority tartibi ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_banners_ordered_by_priority(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """Bannerlar priority kamayish tartibida qaytadi (yuqori son birinchi)."""
    token = await get_token(mp_client, admin_a)

    r1 = await _create_banner(mp_client, token, title="Kam priority", priority=1)
    r2 = await _create_banner(mp_client, token, title="O'rta priority", priority=5)
    r3 = await _create_banner(mp_client, token, title="Yuqori priority", priority=10)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r3.status_code == 201

    id_low = r1.json()["id"]
    id_mid = r2.json()["id"]
    id_high = r3.json()["id"]

    list_resp = await mp_client.get(
        "/marketplace/banners?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    banners = list_resp.json()
    ids_in_order = [b["id"] for b in banners]

    # id_high birinchi bo'lishi shart
    idx_high = ids_in_order.index(id_high)
    idx_mid = ids_in_order.index(id_mid)
    idx_low = ids_in_order.index(id_low)
    assert idx_high < idx_mid < idx_low


# ─── 6. Superadmin har qanday bannerni deactivate qiladi ─────────────────────


@pytest.mark.asyncio
async def test_superadmin_can_deactivate_any_banner(
    mp_client: AsyncClient,
    admin_a: AppUser,
    db_session: AsyncSession,
) -> None:
    """Superadmin A korxona bannerini deactivate qiladi."""
    from app.core.jwt import create_access_token, hash_password
    from app.models.user import AppUser as UserModel

    token_a = await get_token(mp_client, admin_a)

    # A korxona aktiv banner yaratadi
    resp = await _create_banner(mp_client, token_a, title="Superadmin test banneri")
    assert resp.status_code == 201, resp.text
    banner_id = resp.json()["id"]

    # Superadmin user yaratish (enterprise_id=None)
    sa_id = uuid.uuid4()
    superadmin = UserModel(
        id=sa_id,
        full_name="Super Admin",
        phone="+998901234567",
        role="superadmin",
        branch_id=None,
        password_hash=hash_password("SuperPass123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=None,
    )
    db_session.add(superadmin)
    await db_session.flush()

    # Superadmin uchun JWT to'g'ridan-to'g'ri yaratamiz (phone encrypted)
    sa_token = create_access_token(
        sub=str(sa_id),
        role="superadmin",
        branch_id=None,
        enterprise_id=None,
    )

    # Superadmin A bannerini deactivate qiladi
    patch_resp = await mp_client.patch(
        f"/marketplace/banners/{banner_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["is_active"] is False

    # Browse da ko'rinmasligi tekshiruv
    list_resp = await mp_client.get(
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    ids = [b["id"] for b in list_resp.json()]
    assert banner_id not in ids


# ─── 7. Module gating: marketplace o'chiq → 403 ──────────────────────────────


@pytest.mark.asyncio
async def test_banner_module_gating(
    mp_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """marketplace moduli o'chiq → GET /marketplace/banners → 403."""
    from app.core.jwt import hash_password
    from app.models.user import AppUser as UserModel

    # marketplace o'chiq korxona
    ent_no_mp = Enterprise(
        id=uuid.UUID("00000000-0000-7000-8000-000000000077"),
        name="No Marketplace",
        status="active",
        enabled_modules=[m for m in ALL_MODULE_KEYS if m != "marketplace"],
        version=1,
    )
    db_session.add(ent_no_mp)
    await db_session.flush()

    user_no_mp = UserModel(
        id=uuid.uuid4(),
        full_name="No MP User",
        phone="+998907654321",
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
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 8. Superadmin banner yarata olmaydi ─────────────────────────────────────


@pytest.mark.asyncio
async def test_superadmin_cannot_create_banner(
    mp_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin (enterprise_id=None) banner yarata olmaydi → 422."""
    from app.core.jwt import create_access_token, hash_password
    from app.models.user import AppUser as UserModel

    sa_id = uuid.uuid4()
    superadmin = UserModel(
        id=sa_id,
        full_name="Super Admin 2",
        phone="+998909876543",
        role="superadmin",
        branch_id=None,
        password_hash=hash_password("SuperPass123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
        enterprise_id=None,
    )
    db_session.add(superadmin)
    await db_session.flush()

    # Superadmin uchun JWT to'g'ridan-to'g'ri yaratamiz
    sa_token = create_access_token(
        sub=str(sa_id),
        role="superadmin",
        branch_id=None,
        enterprise_id=None,
    )

    resp = await mp_client.post(
        "/marketplace/banners",
        json={
            "title": "SA Banner",
            "is_active": True,
            "priority": 0,
            "valid_from": str(_yesterday()),
            "valid_to": str(_tomorrow()),
        },
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert resp.status_code == 422


# ─── 9. Delete o'z banneri ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_own_banner(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """Korxona O'Z bannerini o'chiradi → bannerlar ro'yxatida yo'q."""
    token = await get_token(mp_client, admin_a)

    resp = await _create_banner(mp_client, token, title="O'chiriladigan banner")
    assert resp.status_code == 201
    banner_id = resp.json()["id"]

    del_resp = await mp_client.delete(
        f"/marketplace/banners/{banner_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Endi browse da topilmasin
    list_resp = await mp_client.get(
        "/marketplace/banners",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    ids = [b["id"] for b in list_resp.json()]
    assert banner_id not in ids


# ─── 10. Delete boshqa korxona banneri → 404 ─────────────────────────────────


@pytest.mark.asyncio
async def test_delete_other_enterprise_banner_404(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    enterprise_b: Enterprise,
) -> None:
    """B korxona A bannerini o'chira olmaydi → 404."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    resp = await _create_banner(mp_client, token_a, title="A reklama 2")
    assert resp.status_code == 201
    banner_id = resp.json()["id"]

    del_resp = await mp_client.delete(
        f"/marketplace/banners/{banner_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == 404
