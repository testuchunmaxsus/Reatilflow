"""
ADR §3.7 — GPS Ish-soati Filtri Testlari.

Qamrov:
  (a) Aktiv ish sessiyasi bor → nuqta saqlanadi.
  (b) Ish sessiyasi yo'q (hech qachon check-in qilinmagan) → nuqta saqlanmaydi.
  (c) Check-out qilingan (yopiq sessiya) → nuqta saqlanmaydi.
  (d) Batch: bir qismi ish vaqtida, bir qismi tashqarida →
      ish vaqtidagilari saqlanadi (bu holatda server "now" bir xil,
      shuning uchun yaxlit batch: aktiv sessiya bor → hammasi qabul, yo'q → hammasi rad).
      Batch ichidagi "ish vaqtidan tashqari" holat faqat recorded_at validatsiya orqali
      aniqlanadi (server_now bilan sessiya oynasi tekshiriladi).
  (e) Filtr o'chirilgan (gps_work_hours_filter_enabled=False) → hamma nuqta saqlanadi.
  (f) Batch: filtr yoqilgan + aktiv sessiya → hammasi saqlanadi.
  (g) Courier uchun ham filtr ishlaydi.

ISH-SOATI FILTRI MANTIQ (ADR §3.7):
  - server_now (ingest vaqti) bo'yicha tekshiriladi.
  - Aktiv sessiya: check_in_at <= server_now AND check_out_at IS NULL AND deleted_at IS NULL.
  - Batch da N+1 yo'q: bir marta SELECT attendance WHERE user_id=X.
  - Filtr o'chirilganda: attendance so'rovlanmaydi, hamma nuqta o'tadi.

Fixtures (conftest.py dan):
  work_hours_gps_client — ish-soati filtri YOQILGAN holat uchun client
  make_attendance        — test uchun attendance sessiyasi yaratuvchi factory
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db, get_timescale_db
from app.core.redis import get_redis
from app.main import app
from app.models.user import AppUser
from app.tests.gps.conftest import TEST_PASSWORD, get_token, make_attendance  # noqa

# ─── Test konstantalari ───────────────────────────────────────────────────────

GPS_LAT = "41.29954200"
GPS_LNG = "69.24012700"

_NOW = datetime.now(timezone.utc)


def _recorded_at(delta_minutes: int = -1) -> str:
    return (_NOW + timedelta(minutes=delta_minutes)).isoformat()


def _point(recorded_at: str | None = None) -> dict:
    return {
        "lat": GPS_LAT,
        "lng": GPS_LNG,
        "recorded_at": recorded_at or _recorded_at(-1),
    }


def _batch(*points: dict) -> dict:
    return {"points": list(points)}


# ─── work_hours_gps_client — filtr YOQILGAN holat uchun client ───────────────


@pytest.fixture
async def work_hours_gps_client(db_session: AsyncSession, fake_redis):
    """
    GPS HTTP klient — ish-soati filtri YOQILGAN holda.

    gps_client (mavjud testlar uchun) filtrni O'CHIRADI.
    Bu fixture esa filtrni YOQADI — ADR §3.7 xulqini sinash uchun.
    """
    original_filter = settings.gps_work_hours_filter_enabled
    object.__setattr__(settings, "gps_work_hours_filter_enabled", True)

    async def _get_test_db():
        yield db_session

    async def _get_test_timescale_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_timescale_db] = _get_test_timescale_db
    app.dependency_overrides[get_redis] = _get_test_redis

    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    object.__setattr__(settings, "gps_work_hours_filter_enabled", original_filter)


# ─── (a) Aktiv ish sessiyasi bor → nuqta saqlanadi ───────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_with_active_session(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
    make_attendance,
):
    """
    (a) Aktiv attendance sessiyasi mavjud → GPS nuqtasi saqlanadi.

    Holat:
      - agent check-in qilgan (sessiya ochiq).
      - GPS ingest → accepted=1, rejected=0.
    """
    # Aktiv attendance sessiyasi yaratish
    await make_attendance(agent_user.id, open=True)

    token = await get_token(work_hours_gps_client, agent_user)
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(_point()),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 1, f"Kutilgan accepted=1, olingan: {data}"
    assert data["rejected"] == 0


# ─── (b) Sessiya yo'q → nuqta saqlanmaydi ────────────────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_no_session(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
):
    """
    (b) Hech qachon check-in qilinmagan → GPS nuqtasi saqlanmaydi.

    Holat:
      - attendance sessiyasi YO'Q.
      - GPS ingest → accepted=0, rejected=1 (jim tashlab yuboriladi).
    """
    token = await get_token(work_hours_gps_client, agent_user)
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(_point()),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 0, f"Kutilgan accepted=0, olingan: {data}"
    assert data["rejected"] == 1


# ─── (c) Check-out qilingan (yopiq sessiya) → nuqta saqlanmaydi ──────────────


@pytest.mark.asyncio
async def test_work_hours_filter_checked_out_session(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
    make_attendance,
):
    """
    (c) Check-out qilingan (check_out_at IS NOT NULL) → GPS nuqtasi saqlanmaydi.

    Holat:
      - Agent check-in va check-out qilgan (sessiya YOPIQ).
      - GPS ingest → accepted=0, rejected=1.
    """
    # Yopiq (check_out qilingan) sessiya
    await make_attendance(agent_user.id, open=False)

    token = await get_token(work_hours_gps_client, agent_user)
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(_point()),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 0, f"Kutilgan accepted=0 (yopiq sessiya), olingan: {data}"
    assert data["rejected"] == 1


# ─── (d) Batch: aktiv sessiya → hammasi saqlanadi ────────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_batch_all_accepted(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
    make_attendance,
):
    """
    (d-1) Batch ingest, aktiv sessiya mavjud → barcha nuqtalar saqlanadi.

    ADR §3.7 batch mantiqi:
      N+1 yo'q — attendance bir marta tekshiriladi.
      Sessiya bor → batch'dagi barcha to'g'ri nuqtalar qabul qilinadi.
    """
    await make_attendance(agent_user.id, open=True)

    token = await get_token(work_hours_gps_client, agent_user)
    points = [_point(recorded_at=_recorded_at(-(i + 1))) for i in range(5)]
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(*points),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 5, f"Kutilgan accepted=5, olingan: {data}"
    assert data["rejected"] == 0


@pytest.mark.asyncio
async def test_work_hours_filter_batch_all_rejected(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
):
    """
    (d-2) Batch ingest, sessiya YO'Q → barcha nuqtalar saqlanmaydi.

    Sessiya yo'q holatida accepted=0, rejected=batch hajmi.
    """
    token = await get_token(work_hours_gps_client, agent_user)
    points = [_point(recorded_at=_recorded_at(-(i + 1))) for i in range(3)]
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(*points),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 0, f"Kutilgan accepted=0, olingan: {data}"
    assert data["rejected"] == 3


# ─── (e) Filtr o'chirilgan → hamma nuqta saqlanadi ───────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_disabled(
    gps_client: AsyncClient,
    agent_user: AppUser,
):
    """
    (e) gps_work_hours_filter_enabled=False → attendance tekshirilmaydi,
    barcha nuqtalar saqlanadi (eski xulq).

    gps_client fixture filtrni O'CHIRADI (backward-compat uchun).
    """
    # Attendance YO'Q — lekin filtr o'chirilganligi sababli nuqtalar saqlanishi kerak
    token = await get_token(gps_client, agent_user)
    resp = await gps_client.post(
        "/gps/ingest",
        json=_batch(
            _point(recorded_at=_recorded_at(-1)),
            _point(recorded_at=_recorded_at(-2)),
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 2, f"Filtr o'chirilgan: accepted=2 kutilgan, olingan: {data}"
    assert data["rejected"] == 0


# ─── (f) Courier uchun filtr ishlaydi ────────────────────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_courier_with_session(
    work_hours_gps_client: AsyncClient,
    courier_user: AppUser,
    make_attendance,
):
    """
    (f-1) Courier + aktiv sessiya → nuqta saqlanadi.

    Filtr agent va courier uchun bir xil ishlaydi.
    """
    await make_attendance(courier_user.id, open=True)

    token = await get_token(work_hours_gps_client, courier_user)
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(_point()),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 1
    assert data["rejected"] == 0


@pytest.mark.asyncio
async def test_work_hours_filter_courier_no_session(
    work_hours_gps_client: AsyncClient,
    courier_user: AppUser,
):
    """
    (f-2) Courier + sessiya yo'q → nuqta saqlanmaydi.
    """
    token = await get_token(work_hours_gps_client, courier_user)
    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(_point()),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] == 0
    assert data["rejected"] == 1


# ─── (g) accepted+rejected+duplicate = jami nuqtalar ─────────────────────────


@pytest.mark.asyncio
async def test_work_hours_filter_count_consistency(
    work_hours_gps_client: AsyncClient,
    agent_user: AppUser,
    make_attendance,
):
    """
    (g) accepted + rejected + duplicate = jami yuborilgan nuqtalar.

    Aktiv sessiya bor, lekin ba'zi nuqtalar vaqt validatsiyadan o'tmaydi.
    accepted + rejected (vaqt sababi) + duplicate = total.
    """
    await make_attendance(agent_user.id, open=True)

    token = await get_token(work_hours_gps_client, agent_user)

    # 2 ta to'g'ri, 1 ta juda kelajak (rad etiladi)
    future_point = _point(recorded_at=_recorded_at(delta_minutes=10))
    valid_point1 = _point(recorded_at=_recorded_at(-1))
    valid_point2 = _point(recorded_at=_recorded_at(-2))

    resp = await work_hours_gps_client.post(
        "/gps/ingest",
        json=_batch(future_point, valid_point1, valid_point2),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    total_sent = 3
    assert data["accepted"] + data["rejected"] + data["duplicate"] == total_sent, (
        f"accepted({data['accepted']}) + rejected({data['rejected']}) "
        f"+ duplicate({data['duplicate']}) != {total_sent}"
    )
    assert data["accepted"] == 2
    assert data["rejected"] == 1  # kelajak vaqt sababi
