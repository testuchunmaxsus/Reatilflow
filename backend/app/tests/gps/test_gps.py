"""
GPS Ingest testlari — T17.

Qamrov:
  1.  Ingest batch → nuqtalar saqlanadi (user_id server'dan, ingested_at server).
  2.  Batch limit oshsa → 422 gps.batch_too_large.
  3.  recorded_at validatsiya — juda kelajak → rad etiladi (rejected++).
  4.  recorded_at validatsiya — juda eski → rad etiladi (rejected++).
  5.  recorded_at validatsiya — to'g'ri oraliq → qabul qilinadi.
  6.  IDOR/scope: agent o'z trekini ingest qiladi; user_id klientdan o'zgartirib bo'lmaydi.
  7.  IDOR: agent boshqa user_id track'ini ko'rishga urinish → 403.
  8.  Admin barcha trekni ko'radi (user_id filtr bilan).
  9.  get_track delivery_id bo'yicha.
  10. get_track user_id + sana bo'yicha.
  11. get_track paginated.
  12. Rate-limit: ingest oshsa → 429.
  13. Decimal (lat/lng/speed) aniqligi.
  14. GPS oraliq validatsiya — noto'g'ri lat/lng → 422.
  15. recorded_at qurilma vaqti, ingested_at server vaqti (ikkalasi farqli).
  16. i18n uz/ru — xato xabarlar.
  17. Auth: token yo'q → 401.
  18. RBAC: store roli GPS ingest qila olmaydi.
  19. Courier ingest va ko'rish qila oladi.
  20. Idempotentlik: bir xil (user_id, recorded_at) → takror ingest e'tiborsiz.
  21. delivery_id ixtiyoriy — berilmasa NULL saqlanadi.
  22. speed ixtiyoriy — berilmasa NULL.
  23. Mavjud 483 test regressiyaga uchramasin (GPS modul mustaqil).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.user import AppUser
from app.tests.gps.conftest import get_token

# ─── Test konstantalari ───────────────────────────────────────────────────────

GPS_LAT = Decimal("41.29954200")
GPS_LNG = Decimal("69.24012700")
GPS_LAT2 = Decimal("41.30010000")
GPS_LNG2 = Decimal("69.24120000")

_NOW = datetime.now(timezone.utc)


def _recorded_at(delta_minutes: int = -1) -> str:
    """recorded_at qiymati: now + delta_minutes daqiqa."""
    dt = _NOW + timedelta(minutes=delta_minutes)
    return dt.isoformat()


def _make_point(
    lat: str = str(GPS_LAT),
    lng: str = str(GPS_LNG),
    recorded_at: str | None = None,
    speed: str | None = "5.5",
    delivery_id: str | None = None,
) -> dict:
    p: dict = {
        "lat": lat,
        "lng": lng,
        "recorded_at": recorded_at or _recorded_at(-1),
    }
    if speed is not None:
        p["speed"] = speed
    if delivery_id is not None:
        p["delivery_id"] = delivery_id
    return p


def _batch(points: list[dict]) -> dict:
    return {"points": points}


# ─── 1. Ingest batch → nuqtalar saqlanadi ────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_success(gps_client: AsyncClient, agent_user: AppUser):
    """Batch ingest → accepted nuqtalar."""
    token = await get_token(gps_client, agent_user)
    before = datetime.now(timezone.utc)

    points = [
        _make_point(recorded_at=_recorded_at(-i)) for i in range(1, 4)
    ]
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch(points),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 3
    assert data["rejected"] == 0


# ─── 2. Batch limit oshsa → 422 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_batch_too_large(gps_client: AsyncClient, agent_user: AppUser):
    """501 ta nuqta → 422 gps.batch_too_large."""
    token = await get_token(gps_client, agent_user)

    # har biri farqli recorded_at (soniyalar farqi)
    points = [
        _make_point(recorded_at=_recorded_at(-(i + 1)))
        for i in range(501)
    ]
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch(points),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422, resp.text
    data = resp.json()
    assert data["message_key"] == "gps.batch_too_large"


# ─── 3. recorded_at — juda kelajak ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_future_recorded_at_rejected(
    gps_client: AsyncClient, agent_user: AppUser
):
    """recorded_at > now + 5 daqiqa → rejected."""
    token = await get_token(gps_client, agent_user)

    future_point = _make_point(recorded_at=_recorded_at(delta_minutes=10))
    valid_point = _make_point(recorded_at=_recorded_at(-1))

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([future_point, valid_point]),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 1
    assert data["rejected"] == 1


# ─── 4. recorded_at — juda eski ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_old_recorded_at_rejected(
    gps_client: AsyncClient, agent_user: AppUser
):
    """recorded_at > 30 kun eski → rejected."""
    token = await get_token(gps_client, agent_user)

    old_dt = (_NOW - timedelta(days=31)).isoformat()
    old_point = _make_point(recorded_at=old_dt)
    valid_point = _make_point(recorded_at=_recorded_at(-1))

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([old_point, valid_point]),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 1
    assert data["rejected"] == 1


# ─── 5. recorded_at — to'g'ri oraliq ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_valid_recorded_at(gps_client: AsyncClient, agent_user: AppUser):
    """Chegaraga yaqin lekin to'g'ri vaqt → accepted."""
    token = await get_token(gps_client, agent_user)

    # 29 kun eski (max 30 kun)
    edge_past = (_NOW - timedelta(days=29)).isoformat()
    # 4 daqiqa kelajak (max 5 daqiqa)
    edge_future = (_NOW + timedelta(minutes=4)).isoformat()

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([
            _make_point(recorded_at=edge_past),
            _make_point(recorded_at=edge_future),
        ]),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 2
    assert data["rejected"] == 0


# ─── 6. IDOR: user_id server'dan (klientdan o'zgartirish imkonsiz) ────────────


@pytest.mark.asyncio
async def test_ingest_user_id_from_server(
    gps_client: AsyncClient, agent_user: AppUser, make_user
):
    """
    Ingest: user_id klientdan OLINMAYDI — server current_user.id ishlatadi.
    Batch sxemasida user_id maydoni yo'q — faqat server belgilaydi.
    """
    token = await get_token(gps_client, agent_user)

    # Sxemada user_id yo'q — klient yuborsa ham e'tiborsiz
    # Biz ingest qilamiz va track'da o'z ID'mizni ko'ramiz
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Track so'rash — o'z user_id bilan
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    items = track_resp.json()["items"]
    assert len(items) >= 1
    # Barcha nuqtalar agent_user.id bilan saqlanganligini tekshiramiz
    for item in items:
        assert item["user_id"] == str(agent_user.id)


# ─── 7. IDOR: agent boshqa user track'ini ko'rish → 403 ─────────────────────


@pytest.mark.asyncio
async def test_get_track_idor_forbidden(
    gps_client: AsyncClient, agent_user: AppUser, make_user
):
    """Agent boshqa user_id track'ini so'rasa → 403."""
    token = await get_token(gps_client, agent_user)
    other_user = await make_user("agent")

    resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(other_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403, resp.text
    data = resp.json()
    assert data["message_key"] == "gps.forbidden_track"


# ─── 8. Admin barcha trekni ko'radi ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_see_all_tracks(
    gps_client: AsyncClient, agent_user: AppUser, admin_user: AppUser
):
    """Administrator barcha foydalanuvchi trekini ko'radi."""
    # Agent ingest qilsin
    agent_token = await get_token(gps_client, agent_user)
    await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    # Admin agent user_id bilan track so'rash
    admin_token = await get_token(gps_client, admin_user)
    resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1


# ─── 9. get_track delivery_id bo'yicha ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_track_by_delivery_id(
    gps_client: AsyncClient, agent_user: AppUser
):
    """delivery_id bo'yicha track so'rash."""
    token = await get_token(gps_client, agent_user)
    delivery_id = str(uuid.uuid4())

    # Delivery_id bilan ingest
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([
            _make_point(delivery_id=delivery_id, recorded_at=_recorded_at(-2)),
            _make_point(delivery_id=delivery_id, recorded_at=_recorded_at(-1)),
            _make_point(recorded_at=_recorded_at(-3)),  # delivery_id siz
        ]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 3

    # Delivery_id bo'yicha track
    track_resp = await gps_client.get(
        f"/gps/track/{delivery_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    data = track_resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["delivery_id"] == delivery_id


# ─── 10. get_track user_id + sana bo'yicha ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_track_by_date(gps_client: AsyncClient, agent_user: AppUser):
    """user_id + sana bo'yicha track so'rash."""
    token = await get_token(gps_client, agent_user)

    today = datetime.now(timezone.utc).date().isoformat()
    # Bugun nuqta yuklash
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(recorded_at=_recorded_at(-1))]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Bugun bo'yicha filter
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id), "date": today},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    data = track_resp.json()
    assert data["total"] >= 1


# ─── 11. get_track paginated ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_track_paginated(gps_client: AsyncClient, agent_user: AppUser):
    """Paginated track — limit/offset ishlaydi."""
    token = await get_token(gps_client, agent_user)

    # 5 ta nuqta yuklash
    points = [_make_point(recorded_at=_recorded_at(-(i + 1))) for i in range(5)]
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch(points),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 5

    # limit=2, offset=0 → 2 ta nuqta
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id), "limit": 2, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    data = track_resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 0

    # limit=2, offset=4 → 1 ta nuqta
    track_resp2 = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id), "limit": 2, "offset": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp2.status_code == 200
    data2 = track_resp2.json()
    assert len(data2["items"]) == 1


# ─── 12. Rate-limit: oshsa → 429 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_rate_limit(gps_client: AsyncClient, agent_user: AppUser):
    """600 dan ortiq so'rov → 429 sync.rate_limited."""
    token = await get_token(gps_client, agent_user)

    # 600 ta muvaffaqiyatli so'rov (har biri farqli recorded_at)
    hit_limit = False
    for i in range(605):
        recorded_at = (
            datetime.now(timezone.utc) - timedelta(seconds=i + 1)
        ).isoformat()
        resp = await gps_client.post(
            "/gps/ingest",
            json=_batch([_make_point(recorded_at=recorded_at)]),
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 429:
            hit_limit = True
            assert resp.json()["message_key"] == "sync.rate_limited"
            break

    assert hit_limit, "Rate-limit 605 so'rovdan keyin ham ishlamadi"


# ─── 13. Decimal aniqligi ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decimal_precision(gps_client: AsyncClient, agent_user: AppUser):
    """lat/lng/speed Decimal aniqligi to'g'ri saqlanadi."""
    token = await get_token(gps_client, agent_user)

    precise_lat = "41.29954321"
    precise_lng = "69.24012678"
    precise_speed = "12.345"

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(
            lat=precise_lat,
            lng=precise_lng,
            speed=precise_speed,
        )]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Track'dan tekshirish
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    items = track_resp.json()["items"]
    assert len(items) >= 1

    # Eng so'nggi nuqta topish (lat bo'yicha)
    matching = [i for i in items if i["lat"].startswith("41.29954321")]
    assert len(matching) >= 1
    item = matching[0]
    assert Decimal(item["lat"]) == Decimal(precise_lat)
    assert Decimal(item["lng"]) == Decimal(precise_lng)
    assert Decimal(item["speed"]) == Decimal(precise_speed)


# ─── 14. GPS oraliq validatsiya ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gps_range_validation(gps_client: AsyncClient, agent_user: AppUser):
    """Noto'g'ri lat/lng → 422."""
    token = await get_token(gps_client, agent_user)

    # lat > 90
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(lat="91.0", lng="69.0")]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

    # lng > 180
    resp2 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(lat="41.0", lng="181.0")]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422

    # lat < -90
    resp3 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(lat="-91.0", lng="69.0")]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 422


# ─── 15. recorded_at qurilma, ingested_at server (farqli) ────────────────────


@pytest.mark.asyncio
async def test_recorded_at_device_ingested_at_server(
    gps_client: AsyncClient, agent_user: AppUser
):
    """recorded_at qurilma vaqti, ingested_at server vaqti — ikkalasi farqli bo'lishi mumkin."""
    token = await get_token(gps_client, agent_user)

    # 10 daqiqa oldin yozilgan qurilma vaqti
    device_time = (_NOW - timedelta(minutes=10)).isoformat()

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(recorded_at=device_time)]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Track'dan tekshirish
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    items = track_resp.json()["items"]
    assert len(items) >= 1

    # Eng so'nggi nuqta
    item = items[-1]
    recorded = datetime.fromisoformat(item["recorded_at"].replace("Z", "+00:00"))
    ingested = datetime.fromisoformat(item["ingested_at"].replace("Z", "+00:00"))

    # ingested_at > recorded_at (server so'ngiroq qabul qildi)
    assert ingested > recorded, (
        f"ingested_at ({ingested}) > recorded_at ({recorded}) bo'lishi kerak"
    )


# ─── 16. i18n — xato xabarlar ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_i18n_uz(gps_client: AsyncClient, agent_user: AppUser, make_user):
    """uz tilida xato xabari."""
    token = await get_token(gps_client, agent_user)
    other = await make_user("agent")

    resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(other.id)},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert "taqiqlangan" in data["message"].lower() or "forbidden" in data["message"].lower()


@pytest.mark.asyncio
async def test_i18n_ru(gps_client: AsyncClient, agent_user: AppUser, make_user):
    """ru tilida xato xabari."""
    token = await get_token(gps_client, agent_user)
    other = await make_user("agent")

    resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(other.id)},
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 403
    data = resp.json()
    # Ru tilida xabar bo'lishi kerak
    assert data["message_key"] == "gps.forbidden_track"


# ─── 17. Auth: token yo'q → 401 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_no_auth(gps_client: AsyncClient):
    """Token yo'q → 401."""
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_track_no_auth(gps_client: AsyncClient):
    """Token yo'q → 401."""
    resp = await gps_client.get("/gps/track")
    assert resp.status_code == 401


# ─── 18. RBAC: store roli GPS ingest qila olmaydi ────────────────────────────


@pytest.mark.asyncio
async def test_rbac_store_cannot_ingest(gps_client: AsyncClient, store_user: AppUser):
    """store roli GPS ingest qila olmaydi → 403."""
    token = await get_token(gps_client, store_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    data = resp.json()
    assert data["message_key"] == "rbac.permission_denied"


@pytest.mark.asyncio
async def test_rbac_store_cannot_view_track(gps_client: AsyncClient, store_user: AppUser):
    """store roli GPS trek ko'ra olmaydi → 403."""
    token = await get_token(gps_client, store_user)

    resp = await gps_client.get(
        "/gps/track",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 19. Courier ingest va ko'rish ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_courier_can_ingest_and_view(
    gps_client: AsyncClient, courier_user: AppUser
):
    """Courier o'z trekini ingest qiladi va ko'radi."""
    token = await get_token(gps_client, courier_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(courier_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    assert track_resp.json()["total"] >= 1


# ─── 20. Idempotentlik: takror ingest e'tiborsiz ─────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_ingest(gps_client: AsyncClient, agent_user: AppUser):
    """Bir xil recorded_at bilan ikki marta ingest → ikkinchisi e'tiborsiz."""
    token = await get_token(gps_client, agent_user)

    fixed_time = _recorded_at(-5)

    # Birinchi marta
    resp1 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(recorded_at=fixed_time)]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Ikkinchi marta (bir xil recorded_at)
    resp2 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(recorded_at=fixed_time)]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200

    # Track'da faqat 1 ta nuqta bo'lishi kerak (takror e'tiborsiz)
    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    data = track_resp.json()
    # recorded_at bo'yicha tekshirish
    matching_times = [
        i for i in data["items"]
        if fixed_time[:19] in i["recorded_at"]  # saniyagacha solishtirish
    ]
    assert len(matching_times) == 1, (
        f"Bir xil recorded_at bilan {len(matching_times)} ta nuqta saqlangan, 1 ta kutilgan"
    )


# ─── 21. delivery_id ixtiyoriy — NULL saqlanadi ─────────────────────────────


@pytest.mark.asyncio
async def test_delivery_id_optional_null(gps_client: AsyncClient, agent_user: AppUser):
    """delivery_id berilmasa → NULL saqlanadi."""
    token = await get_token(gps_client, agent_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(delivery_id=None)]),  # delivery_id yo'q
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    items = track_resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["delivery_id"] is None


# ─── 22. speed ixtiyoriy — NULL ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_speed_optional_null(gps_client: AsyncClient, agent_user: AppUser):
    """speed berilmasa → NULL saqlanadi."""
    token = await get_token(gps_client, agent_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(speed=None)]),  # speed yo'q
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    track_resp = await gps_client.get(
        "/gps/track",
        params={"user_id": str(agent_user.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert track_resp.status_code == 200
    items = track_resp.json()["items"]
    assert len(items) >= 1

    # NULL speed
    null_speed_items = [i for i in items if i["speed"] is None]
    assert len(null_speed_items) >= 1


# ─── Batch hajmi chegarasi — aniq limit ──────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_exactly_max_batch(gps_client: AsyncClient, agent_user: AppUser):
    """Aniq 500 ta nuqta → qabul qilinadi (limit emas)."""
    token = await get_token(gps_client, agent_user)

    points = [
        _make_point(recorded_at=(_NOW - timedelta(seconds=i + 1)).isoformat())
        for i in range(500)
    ]
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch(points),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 500


# ─── Yagona nuqta — minimal batch ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_single_point(gps_client: AsyncClient, agent_user: AppUser):
    """1 ta nuqta → accepted=1."""
    token = await get_token(gps_client, agent_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
    assert resp.json()["rejected"] == 0


# ─── Bo'sh nuqtalar ro'yxati — 422 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_empty_points_422(gps_client: AsyncClient, agent_user: AppUser):
    """Bo'sh nuqtalar ro'yxati → 422."""
    token = await get_token(gps_client, agent_user)

    resp = await gps_client.post(
        "/gps/ingest",
        json={"points": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ─── Admin barcha nuqtalar, filtr yo'q ───────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_track_no_filter(
    gps_client: AsyncClient, agent_user: AppUser, admin_user: AppUser
):
    """Administrator user_id filtrsiz barcha nuqtalarni ko'radi."""
    # Agent ingest
    agent_token = await get_token(gps_client, agent_user)
    await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point()]),
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    # Admin filtrsiz
    admin_token = await get_token(gps_client, admin_user)
    resp = await gps_client.get(
        "/gps/track",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


# ─── speed yuqori chegara (le=150 m/s) validatsiya ───────────────────────────


@pytest.mark.asyncio
async def test_speed_max_limit_validation(gps_client: AsyncClient, agent_user: AppUser):
    """speed > 150 m/s → 422 (data-quality chegarasi)."""
    token = await get_token(gps_client, agent_user)

    # 150.001 m/s — chegaradan yuqori
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(speed="150.001")]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text

    # Aynan 150.0 — chegara qiymati, qabul qilinishi kerak
    resp2 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(speed="150.0", recorded_at=_recorded_at(-2))]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["accepted"] == 1

    # Manfiy tezlik — ham 422
    resp3 = await gps_client.post(
        "/gps/ingest",
        json=_batch([_make_point(speed="-1.0")]),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 422, resp3.text
