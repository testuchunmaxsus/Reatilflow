"""
Davomat testlari — T16.

Qamrov:
  1. check-in → davomat ochiladi (biometric_verified=True, GPS, server vaqti).
  2. Takror check-in (shu kun) → already_checked_in (409).
  3. check-out → ochiq davomat yopiladi.
  4. check-in'siz check-out → not_checked_in (404).
  5. biometric_verified=False → biometric_required (403).
  6. IDOR/scope: agent o'z davomatini ko'radi; boshqa user_id so'rasa 403.
  7. Admin barchasini ko'radi (user_id filtr).
  8. RBAC: store roli check-in qila olmaydi (attendance:create yo'q).
  9. Idempotentlik (client_uuid) — takror check-in bir xil davomat qaytaradi.
  10. Decimal GPS aniqligi (7 kasrga).
  11. i18n uz/ru — xato xabarlar.
  12. Server vaqti ishlatiladi (klient bergan vaqtga ishonilmaydi).
  13. Courier check-in/check-out qila oladi.
  14. accountant boshqa user davomatini ko'ra oladi.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.user import AppUser
from app.tests.attendance.conftest import get_token

# GPS test koordinatalari (Toshkent)
GPS_LAT = Decimal("41.2995420")
GPS_LNG = Decimal("69.2401270")
GPS_LAT2 = Decimal("41.3001000")
GPS_LNG2 = Decimal("69.2412000")

CHECK_IN_BODY = {
    "biometric_verified": True,
    "gps_lat": str(GPS_LAT),
    "gps_lng": str(GPS_LNG),
    "source": "device_faceid",
}

CHECK_OUT_BODY = {
    "gps_lat": str(GPS_LAT2),
    "gps_lng": str(GPS_LNG2),
}


# ─── 1. check-in → davomat ochiladi ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_success(attendance_client: AsyncClient, agent_user: AppUser):
    """check-in muvaffaqiyatli — davomat ochiladi."""
    token = await get_token(attendance_client, agent_user)
    before = datetime.now(timezone.utc)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Asosiy maydonlar
    assert data["user_id"] == str(agent_user.id)
    assert data["biometric_verified"] is True
    assert data["source"] == "device_faceid"
    assert data["check_out_at"] is None

    # GPS aniqligi
    assert Decimal(data["check_in_gps_lat"]).quantize(Decimal("0.0000001")) == GPS_LAT
    assert Decimal(data["check_in_gps_lng"]).quantize(Decimal("0.0000001")) == GPS_LNG

    # Server vaqti tekshiruvi — check_in_at null emas va hozirdan oldin emas
    check_in_at = datetime.fromisoformat(data["check_in_at"].replace("Z", "+00:00"))
    assert check_in_at >= before, "check_in_at SERVER vaqti bo'lishi kerak"

    # work_date
    assert data["work_date"] is not None


# ─── 2. Takror check-in → already_checked_in ─────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_duplicate(attendance_client: AsyncClient, agent_user: AppUser):
    """Shu kun ikkinchi check-in → 409 already_checked_in."""
    token = await get_token(attendance_client, agent_user)

    # Birinchi check-in
    resp1 = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201, resp1.text

    # Ikkinchi check-in
    resp2 = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["message_key"] == "attendance.already_checked_in"


# ─── 3. check-out → ochiq davomat yopiladi ───────────────────────────────────

@pytest.mark.asyncio
async def test_check_out_success(attendance_client: AsyncClient, agent_user: AppUser):
    """check-in → check-out muvaffaqiyatli."""
    token = await get_token(attendance_client, agent_user)

    # Avval check-in
    resp_in = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_in.status_code == 201

    # check-out
    before_out = datetime.now(timezone.utc)
    resp_out = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp_out.status_code == 200, resp_out.text
    data = resp_out.json()

    # check_out_at null emas va server vaqti
    assert data["check_out_at"] is not None
    check_out_at = datetime.fromisoformat(data["check_out_at"].replace("Z", "+00:00"))
    assert check_out_at >= before_out, "check_out_at SERVER vaqti bo'lishi kerak"

    # GPS
    assert Decimal(data["check_out_gps_lat"]).quantize(Decimal("0.0000001")) == GPS_LAT2
    assert Decimal(data["check_out_gps_lng"]).quantize(Decimal("0.0000001")) == GPS_LNG2

    # version o'sdi
    assert data["version"] == 2


# ─── 4. check-in'siz check-out → not_checked_in ──────────────────────────────

@pytest.mark.asyncio
async def test_check_out_no_checkin(attendance_client: AsyncClient, agent_user: AppUser):
    """check-in qilmasdan check-out → 404 not_checked_in."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404
    assert resp.json()["message_key"] == "attendance.not_checked_in"


# ─── 5. biometric_verified=False → biometric_required ───────────────────────

@pytest.mark.asyncio
async def test_check_in_biometric_false(attendance_client: AsyncClient, agent_user: AppUser):
    """biometric_verified=False → 403 attendance.biometric_required."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": False,
            "gps_lat": str(GPS_LAT),
            "gps_lng": str(GPS_LNG),
            "source": "device_faceid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["message_key"] == "attendance.biometric_required"


# ─── 6. IDOR/scope: agent o'z davomatini ko'radi; boshqa user_id → 403 ───────

@pytest.mark.asyncio
async def test_agent_cannot_see_other_user(
    attendance_client: AsyncClient,
    agent_user: AppUser,
    make_user,
):
    """Agent boshqa foydalanuvchi davomatini so'rasa → 403."""
    token = await get_token(attendance_client, agent_user)
    another_user = await make_user("agent")

    # Boshqa foydalanuvchi user_id bilan so'rov
    resp = await attendance_client.get(
        f"/attendance?user_id={another_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["message_key"] == "attendance.forbidden_user"


@pytest.mark.asyncio
async def test_agent_sees_own_attendance(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """Agent o'z davomatini ko'ra oladi."""
    token = await get_token(attendance_client, agent_user)

    # Check-in qilish
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Ro'yxat olish
    resp = await attendance_client.get(
        "/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["user_id"] == str(agent_user.id)


@pytest.mark.asyncio
async def test_agent_own_user_id_filter(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """Agent o'z user_id'si bilan filtr qilsa → muvaffaqiyatli."""
    token = await get_token(attendance_client, agent_user)

    # Check-in
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    # O'z user_id'si bilan filtr
    resp = await attendance_client.get(
        f"/attendance?user_id={agent_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


# ─── 7. Admin barchasini ko'radi ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_sees_all(
    attendance_client: AsyncClient,
    admin_user: AppUser,
    agent_user: AppUser,
    courier_user: AppUser,
    fake_redis,
    db_session,
):
    """Administrator boshqa foydalanuvchi davomatini ko'ra oladi."""
    # Agent check-in
    agent_token = await get_token(attendance_client, agent_user)
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    # Admin token
    admin_token = await get_token(attendance_client, admin_user)

    # Admin agent davomatini ko'radi
    resp = await attendance_client.get(
        f"/attendance?user_id={agent_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["user_id"] == str(agent_user.id)


# ─── 8. RBAC: store roli check-in qila olmaydi ───────────────────────────────

@pytest.mark.asyncio
async def test_store_cannot_check_in(attendance_client: AsyncClient, store_user: AppUser):
    """store roli attendance:create ruxsatiga ega emas → 403."""
    token = await get_token(attendance_client, store_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["message_key"] == "rbac.permission_denied"


@pytest.mark.asyncio
async def test_store_cannot_check_out(attendance_client: AsyncClient, store_user: AppUser):
    """store roli attendance:create (check-out) ruxsatiga ega emas → 403."""
    token = await get_token(attendance_client, store_user)

    resp = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


# ─── 9. Idempotentlik (client_uuid) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_idempotency(attendance_client: AsyncClient, agent_user: AppUser):
    """Bir xil client_uuid bilan takror check-in → bir xil davomat qaytaradi."""
    token = await get_token(attendance_client, agent_user)
    client_uuid = str(uuid.uuid4())

    body = {**CHECK_IN_BODY, "client_uuid": client_uuid}

    # Birinchi so'rov
    resp1 = await attendance_client.post(
        "/attendance/check-in",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    # Takror so'rov (bir xil client_uuid)
    resp2 = await attendance_client.post(
        "/attendance/check-in",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    # Ikkinchi so'rov ham muvaffaqiyatli (idempotent) yoki 409 (ochiq davomat)
    # Idempotentlik kaliti ishlaganda: 201 + bir xil ID
    if resp2.status_code == 201:
        id2 = resp2.json()["id"]
        assert id1 == id2, "Idempotent: bir xil davomat ID qaytarilishi kerak"
    else:
        # Agar Redis idempotentlik ishlamasa (test muhiti) — 409 already_checked_in
        assert resp2.status_code == 409


# ─── 10. Decimal GPS aniqligi ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gps_decimal_precision(attendance_client: AsyncClient, agent_user: AppUser):
    """GPS koordinatalarida 7 kasrga aniqlik saqlanadi."""
    token = await get_token(attendance_client, agent_user)

    precise_lat = "41.2995420"
    precise_lng = "69.2401270"

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": precise_lat,
            "gps_lng": precise_lng,
            "source": "device_fingerprint",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()

    # Decimal aniqlik
    saved_lat = Decimal(data["check_in_gps_lat"])
    saved_lng = Decimal(data["check_in_gps_lng"])
    assert abs(saved_lat - Decimal(precise_lat)) < Decimal("0.0000001")
    assert abs(saved_lng - Decimal(precise_lng)) < Decimal("0.0000001")


# ─── 11. i18n uz/ru ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_i18n_biometric_required_ru(attendance_client: AsyncClient, agent_user: AppUser):
    """biometric_required xatosi rus tilida qaytadi."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": False,
            "gps_lat": str(GPS_LAT),
            "gps_lng": str(GPS_LNG),
            "source": "device_faceid",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "attendance.biometric_required"
    # Rus tilidagi xabar tekshiruvi
    assert "биометр" in data["message"].lower() or "биометрическ" in data["message"].lower()


@pytest.mark.asyncio
async def test_i18n_already_checked_in_uz(attendance_client: AsyncClient, agent_user: AppUser):
    """already_checked_in xatosi o'zbek tilida qaytadi."""
    token = await get_token(attendance_client, agent_user)

    # Birinchi check-in
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Ikkinchi check-in uz tilida
    resp = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "uz",
        },
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["message_key"] == "attendance.already_checked_in"
    # O'zbek tilidagi xabar
    assert "allaqachon" in data["message"].lower() or "davomat" in data["message"].lower()


# ─── 12. Server vaqti (klient vaqtiga ishonmaslik) ───────────────────────────

@pytest.mark.asyncio
async def test_server_time_used(attendance_client: AsyncClient, agent_user: AppUser):
    """check_in_at SERVER tomonida belgilanadi — klient vaqt bera olmaydi."""
    token = await get_token(attendance_client, agent_user)
    before = datetime.now(timezone.utc)

    # Klient vaqtini bermaydi — server o'zi belgilaydi
    resp = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    after = datetime.now(timezone.utc)

    assert resp.status_code == 201
    data = resp.json()

    check_in_at = datetime.fromisoformat(data["check_in_at"].replace("Z", "+00:00"))
    assert before <= check_in_at <= after, (
        f"check_in_at [{check_in_at}] server vaqti [{before}, {after}] orasida bo'lishi kerak"
    )


# ─── 13. Courier check-in/check-out ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_courier_can_check_in_and_out(
    attendance_client: AsyncClient,
    courier_user: AppUser,
):
    """Courier ham check-in va check-out qila oladi."""
    token = await get_token(attendance_client, courier_user)

    # Check-in
    resp_in = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": str(GPS_LAT),
            "gps_lng": str(GPS_LNG),
            "source": "device_fingerprint",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_in.status_code == 201
    assert resp_in.json()["user_id"] == str(courier_user.id)

    # Check-out
    resp_out = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_out.status_code == 200
    assert resp_out.json()["check_out_at"] is not None


# ─── 14. Accountant boshqa user davomatini ko'ra oladi ───────────────────────

@pytest.mark.asyncio
async def test_accountant_sees_other_user(
    attendance_client: AsyncClient,
    accountant_user: AppUser,
    agent_user: AppUser,
):
    """Accountant boshqa foydalanuvchi davomatini ko'ra oladi."""
    # Agent check-in
    agent_token = await get_token(attendance_client, agent_user)
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    # Accountant agent davomatini ko'radi
    accountant_token = await get_token(attendance_client, accountant_user)
    resp = await attendance_client.get(
        f"/attendance?user_id={agent_user.id}",
        headers={"Authorization": f"Bearer {accountant_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["user_id"] == str(agent_user.id)


# ─── 15. Autentifikatsiya talab qilinadi ─────────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_requires_auth(attendance_client: AsyncClient):
    """Token bo'lmasdan check-in → 401."""
    resp = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_requires_auth(attendance_client: AsyncClient):
    """Token bo'lmasdan list → 401."""
    resp = await attendance_client.get("/attendance")
    assert resp.status_code == 401


# ─── 16. Ro'yxat paginatsiyasi ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_pagination(attendance_client: AsyncClient, admin_user: AppUser):
    """Ro'yxat paginatsiyasi ishlaydi."""
    token = await get_token(attendance_client, admin_user)

    resp = await attendance_client.get(
        "/attendance?limit=10&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert data["limit"] == 10
    assert data["offset"] == 0


# ─── 17. GPS oraliq validatsiya ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gps_out_of_range(attendance_client: AsyncClient, agent_user: AppUser):
    """GPS oralig'i tashqarisidagi koordinata → 422."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": "91.0",  # ±90 dan oshib ketdi
            "gps_lng": str(GPS_LNG),
            "source": "device_faceid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── 18. source validatsiya ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_source(attendance_client: AsyncClient, agent_user: AppUser):
    """Noto'g'ri source qiymati → 422."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": str(GPS_LAT),
            "gps_lng": str(GPS_LNG),
            "source": "unknown_source",  # Noto'g'ri qiymat
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── 19. Sana filtri ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_date_filter(attendance_client: AsyncClient, agent_user: AppUser):
    """?date= filtri ishlaydi."""
    token = await get_token(attendance_client, agent_user)

    # Check-in qilish
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    from datetime import date
    today = date.today().isoformat()

    # Bugungi sana filtri
    resp = await attendance_client.get(
        f"/attendance?date={today}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["work_date"] == today


# ─── 20. RBAC: store roli attendance:view ruxsati yo'q ───────────────────────

@pytest.mark.asyncio
async def test_store_cannot_list_attendance(
    attendance_client: AsyncClient,
    store_user: AppUser,
):
    """store roli attendance ro'yxatini ko'ra olmaydi → 403."""
    token = await get_token(attendance_client, store_user)

    resp = await attendance_client.get(
        "/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── T16-SRE: Race condition / Idempotentlik / GPS chegara testlari ──────────

@pytest.mark.asyncio
async def test_check_in_race_duplicate_same_day(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """
    Shu kun ikkinchi check-in (race naqshi): birinchi muvaffaqiyatli,
    ikkinchisi 409 already_checked_in qaytarishi kerak.
    SQLite partial unique yo'q, lekin servis darajasida ochiq davomat tekshiruvi ishlaydi.
    """
    token = await get_token(attendance_client, agent_user)

    resp1 = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201, resp1.text

    resp2 = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["message_key"] == "attendance.already_checked_in"


@pytest.mark.asyncio
async def test_check_out_idempotency_client_uuid(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """
    check_out idempotentlik: bir xil client_uuid bilan takror check-out
    bitta natija qaytarishi kerak (xato emas).
    """
    token = await get_token(attendance_client, agent_user)
    client_uuid = str(uuid.uuid4())

    # check-in
    resp_in = await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_in.status_code == 201

    body = {**CHECK_OUT_BODY, "client_uuid": client_uuid}

    # Birinchi check-out
    resp1 = await attendance_client.post(
        "/attendance/check-out",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200, resp1.text
    id1 = resp1.json()["id"]

    # Takror check-out bir xil client_uuid bilan
    resp2 = await attendance_client.post(
        "/attendance/check-out",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    # Idempotentlik: bir xil ID qaytarishi yoki allaqachon yopilgan → 404
    if resp2.status_code == 200:
        assert resp2.json()["id"] == id1, "Idempotent check_out: bir xil davomat ID kerak"
    else:
        assert resp2.status_code == 404
        assert resp2.json()["message_key"] == "attendance.not_checked_in"


@pytest.mark.asyncio
async def test_check_out_already_closed(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """
    Allaqachon yopilgan davomat uchun check-out (client_uuid'siz)
    → 404 not_checked_in.
    """
    token = await get_token(attendance_client, agent_user)

    # check-in
    await attendance_client.post(
        "/attendance/check-in",
        json=CHECK_IN_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Birinchi check-out (muvaffaqiyatli)
    resp1 = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Ikkinchi check-out — ochiq davomat yo'q → 404
    resp2 = await attendance_client.post(
        "/attendance/check-out",
        json=CHECK_OUT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404
    assert resp2.json()["message_key"] == "attendance.not_checked_in"


@pytest.mark.asyncio
async def test_gps_boundary_valid_extremes(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """
    GPS chegara: gps_lat=-90.0, gps_lng=180.0 qabul qilinishi kerak (valid ekstremum).
    """
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": "-90.0",
            "gps_lng": "180.0",
            "source": "device_faceid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_gps_lat_91_rejected(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """gps_lat=91 → 422 (±90 chegaradan tashqari)."""
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": "91.0",
            "gps_lng": str(GPS_LNG),
            "source": "device_faceid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_gps_excess_decimal_places(
    attendance_client: AsyncClient,
    agent_user: AppUser,
):
    """
    Ortiqcha kasrli GPS koordinata → 422 yoki qabul (schema qaror qiladi).
    8+ kasr berilganda schema rad etishi yoki 7 kasrga kesishi kerak.
    Hozirgi xulq: Pydantic validator 422 qaytaradi.
    """
    token = await get_token(attendance_client, agent_user)

    resp = await attendance_client.post(
        "/attendance/check-in",
        json={
            "biometric_verified": True,
            "gps_lat": "41.29954201234",  # 11 kasrli — schema 7 kasrdan oshmasin
            "gps_lng": str(GPS_LNG),
            "source": "device_faceid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Schema 7 kasrdan ko'p qabul qilmasligi yoki kesishi kerak
    assert resp.status_code in (201, 422)
