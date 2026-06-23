"""
POS moduli testlari — chakana sotuv yadrosi.

Test kategoriyalari:
  1.  NARX XAVFSIZLIGI: klient narx bermaydi — server katalogdan oladi.
  2.  total_amount to'g'ri hisoblanadi (Decimal).
  3.  Idempotentlik: client_uuid → bir sotuv; IntegrityError graceful.
  4.  RBAC/scope:
      - store faqat o'z do'koni.
      - admin/accountant barchasi.
      - agent/courier → 403.
  5.  Bo'sh lines → 422.
  6.  Noma'lum mahsulot → 404.
  7.  Noma'lum do'kon → 404.
  8.  Segment/narx topilmasa → 422.
  9.  Tenant izolyatsiyasi: korxona A sotuvini korxona B ko'rmaydi.
  10. Module gating: "pos" o'chiq → /pos/* 403.
  11. HTTP endpointlar: POST /pos/sales, GET ro'yxat, GET id, GET /summary.
  12. daily_summary: to'g'ri agregatsiya, payment_method bo'yicha.

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise, ALL_MODULE_KEYS
from app.models.pos import PosSale, PosSaleLine
from app.modules.pos import service
from app.modules.pos.schemas import PosSaleCreate, PosSaleLineIn
from app.tests.conftest import TEST_ENTERPRISE_UUID
from app.tests.pos.conftest import get_token


# ─── Yordamchi: segmentli do'kon + mahsulot yaratish ─────────────────────────

async def _make_seeded_store_product(
    make_price_segment,
    make_product,
    make_store,
    price: Decimal = Decimal("2000.00"),
    store_user_id: uuid.UUID | None = None,
    enterprise_id: uuid.UUID | None = None,
):
    """Segmentli do'kon + mahsulot + narx seed."""
    segment = await make_price_segment()
    product = await make_product(price=price, segment_id=segment.id, enterprise_id=enterprise_id)
    store = await make_store(
        segment_id=segment.id,
        user_id=store_user_id,
        enterprise_id=enterprise_id,
    )
    return store, product, segment


# ─── 1. NARX XAVFSIZLIGI ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_authoritative_price(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """
    Server-avtoritar narx testi:
    Klient unit_price bermaydi — PosSaleLineIn sxemasida unit_price maydoni YO'Q.
    Server narxni katalogdan oladi.
    """
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
        price=Decimal("2500.00"),
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("2"))],
    )

    # PosSaleLineIn da unit_price maydoni YO'QLIGINI tekshirish
    line_fields = set(PosSaleLineIn.model_fields.keys())
    assert "unit_price" not in line_fields, "unit_price sxemada bo'lmasligi kerak (XAVFSIZLIK)"
    assert "discount" not in line_fields, "discount sxemada bo'lmasligi kerak (XAVFSIZLIK)"

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    # Narx server tomonidan to'g'ri olinganini tekshirish
    assert sale.total_amount == Decimal("5000.00")  # 2500 * 2
    assert len(sale.lines) == 1
    assert sale.lines[0].unit_price == Decimal("2500.00")


# ─── 2. total_amount to'g'ri ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_total_amount_correct(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """Bir nechta qator uchun total_amount to'g'ri hisoblanadi."""
    segment = await make_price_segment()
    prod1 = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    prod2 = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="card",
        lines=[
            PosSaleLineIn(product_id=prod1.id, qty=Decimal("3")),  # 3000
            PosSaleLineIn(product_id=prod2.id, qty=Decimal("2")),  # 1000
        ],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale.total_amount == Decimal("4000.00")
    assert len(sale.lines) == 2

    # Qator jamilarini ham tekshirish
    totals = {str(l.product_id): l.line_total for l in sale.lines}
    assert totals[str(prod1.id)] == Decimal("3000.00")
    assert totals[str(prod2.id)] == Decimal("1000.00")


# ─── 3. Idempotentlik ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotency_client_uuid(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """Bir xil client_uuid → bir xil sotuv qaytariladi (ikki marta INSERT emas)."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )
    idem_uuid = uuid.uuid4()

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=idem_uuid,
    )

    sale1 = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )
    # Commit — ikkinchi create_sale IntegrityError ishlatishi uchun
    await db_session.commit()

    # Ikkinchi marta — bir xil ID qaytishi kerak
    sale2 = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    assert sale1.id == sale2.id, "Idempotentlik: bir xil client_uuid → bir xil sotuv"

    # DB da bitta sotuv
    result = await db_session.execute(
        select(PosSale).where(PosSale.client_uuid == idem_uuid)
    )
    rows = result.scalars().all()
    assert len(rows) == 1


# ─── 4. Bo'sh lines → 422 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_lines_rejected(
    db_session: AsyncSession,
    make_store,
    admin_user,
) -> None:
    """Bo'sh qatorlar → AppError (422)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PosSaleCreate(
            store_id=uuid.uuid4(),
            payment_method="cash",
            lines=[],
        )


# ─── 5. Noma'lum mahsulot → 404 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_product_rejected(
    db_session: AsyncSession,
    make_price_segment,
    make_store,
    admin_user,
) -> None:
    """Mavjud bo'lmagan mahsulot → AppError("pos.product_not_found", 404)."""
    from app.core.errors import AppError

    segment = await make_price_segment()
    store = await make_store(segment_id=segment.id)

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=uuid.uuid4(), qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.product_not_found"
    assert exc_info.value.status_code == 404


# ─── 6. Noma'lum do'kon → 404 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_store_rejected(
    db_session: AsyncSession,
    make_product,
    make_price_segment,
    admin_user,
) -> None:
    """Mavjud bo'lmagan do'kon → AppError("customers.store_not_found", 404)."""
    from app.core.errors import AppError

    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)

    data = PosSaleCreate(
        store_id=uuid.uuid4(),
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "customers.store_not_found"


# ─── 7. Segment/narx yo'q → 422 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_price_segment_rejected(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """Do'konda segment yo'q → AppError("pos.no_price", 422)."""
    from app.core.errors import AppError

    product = await make_product()  # narxsiz mahsulot
    store = await make_store(segment_id=None)  # segmentsiz do'kon

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_sale(
            db=db_session,
            data=data,
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )
    assert exc_info.value.message_key == "pos.no_price"


# ─── 8. Tenant izolyatsiyasi ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    default_enterprise: Enterprise,
) -> None:
    """
    Korxona A sotuvini korxona B ko'rmasligi kerak.
    get_sale() enterprise filtr bilan ishlaydi.
    """
    from app.core.errors import AppError

    # Korxona B yaratish
    enterprise_b_id = uuid.UUID("00000000-0000-7000-8000-000000000088")
    enterprise_b = Enterprise(
        id=enterprise_b_id,
        name="Korxona B",
        status="active",
        enabled_modules=list(ALL_MODULE_KEYS),
        version=1,
    )
    db_session.add(enterprise_b)
    await db_session.flush()

    # Korxona A (default) uchun sotuv yaratish
    store_a, product_a, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
        enterprise_id=default_enterprise.id,
    )
    admin_a = await make_user("administrator", enterprise_id=default_enterprise.id)

    data = PosSaleCreate(
        store_id=store_a.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product_a.id, qty=Decimal("1"))],
    )
    sale_a = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_a.id,
        user=admin_a,
        enterprise_id=default_enterprise.id,
    )

    # Korxona B admin — A sotuvini ko'ra olmaydi
    admin_b = await make_user("administrator", enterprise_id=enterprise_b_id)
    with pytest.raises(AppError) as exc_info:
        await service.get_sale(
            db=db_session,
            sale_id=sale_a.id,
            user=admin_b,
            enterprise_id=enterprise_b_id,
        )
    assert exc_info.value.status_code == 404


# ─── 9. Store roli o'z do'koni ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_role_own_store_only(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    default_enterprise: Enterprise,
) -> None:
    """store roli faqat o'z do'koniga sotuv yaratadi."""
    store_user = await make_user("store")
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
        store_user_id=store_user.id,
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=store_user.id,
        user=store_user,
        enterprise_id=store_user.enterprise_id,
    )
    assert sale is not None
    assert sale.store_id == store.id


@pytest.mark.asyncio
async def test_store_role_cannot_access_other_store_sale(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    make_user,
) -> None:
    """store roli boshqa do'kon sotuvini ko'ra olmaydi (404 IDOR himoya)."""
    from app.core.errors import AppError

    admin = await make_user("administrator")
    store_user_other = await make_user("store")  # boshqa kassir
    store_user_me = await make_user("store")

    # Admin do'kon yaratadi
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="cash",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin.id,
        user=admin,
        enterprise_id=admin.enterprise_id,
    )

    # store_user_me shu do'konga biriktirilmagan → 404
    with pytest.raises(AppError) as exc_info:
        await service.get_sale(
            db=db_session,
            sale_id=sale.id,
            user=store_user_me,
            enterprise_id=store_user_me.enterprise_id,
        )
    assert exc_info.value.status_code == 404


# ─── 10. list_sales + get_sale ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_and_get_sale(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """list_sales va get_sale to'g'ri ishlaydi."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )

    data = PosSaleCreate(
        store_id=store.id,
        payment_method="card",
        lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("5"))],
    )
    created_sale = await service.create_sale(
        db=db_session,
        data=data,
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    # list
    items, total = await service.list_sales(
        db=db_session,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )
    assert total >= 1
    assert any(s.id == created_sale.id for s in items)

    # get
    fetched = await service.get_sale(
        db=db_session,
        sale_id=created_sale.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )
    assert fetched.id == created_sale.id
    assert len(fetched.lines) == 1


# ─── 11. daily_summary ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_summary(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """daily_summary to'g'ri jami hisoblaydi, payment_method bo'yicha ajratadi."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store, price=Decimal("1000.00"),
    )

    today = datetime.now(timezone.utc).date()

    # 2 ta cash sotuv
    for _ in range(2):
        await service.create_sale(
            db=db_session,
            data=PosSaleCreate(
                store_id=store.id,
                payment_method="cash",
                lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
            ),
            cashier_id=admin_user.id,
            user=admin_user,
            enterprise_id=admin_user.enterprise_id,
        )

    # 1 ta card sotuv
    await service.create_sale(
        db=db_session,
        data=PosSaleCreate(
            store_id=store.id,
            payment_method="card",
            lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("3"))],
        ),
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    summary = await service.daily_summary(
        db=db_session,
        summary_date=today,
        enterprise_id=admin_user.enterprise_id,
        user=admin_user,
    )

    assert summary.total_sales == 3
    # 2 * 1000 + 1 * 3000 = 5000
    assert summary.total_amount == Decimal("5000.00")

    # by_payment breakdown
    payment_map = {p.payment_method: p for p in summary.by_payment}
    assert "cash" in payment_map
    assert "card" in payment_map
    assert payment_map["cash"].count == 2
    assert payment_map["cash"].total_amount == Decimal("2000.00")
    assert payment_map["card"].count == 1
    assert payment_map["card"].total_amount == Decimal("3000.00")


# ─── 12. HTTP endpointlar ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_http_post_sales(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """POST /pos/sales → 201, PosSaleOut."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
        price=Decimal("750.00"),
    )
    token = await get_token(pos_client, admin_user)

    resp = await pos_client.post(
        "/pos/sales",
        json={
            "store_id": str(store.id),
            "payment_method": "cash",
            "lines": [
                {"product_id": str(product.id), "qty": "2"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_amount"] == "1500.00"
    assert body["payment_method"] == "cash"
    assert body["status"] == "completed"
    assert len(body["lines"]) == 1


@pytest.mark.asyncio
async def test_http_get_sales_list(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """GET /pos/sales → 200, PaginatedSales."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )
    # Bitta sotuv yaratish
    await service.create_sale(
        db=db_session,
        data=PosSaleCreate(
            store_id=store.id,
            payment_method="cash",
            lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
        ),
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    token = await get_token(pos_client, admin_user)
    resp = await pos_client.get(
        "/pos/sales",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_http_get_sale_by_id(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """GET /pos/sales/{id} → 200, kvitansiya."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )
    sale = await service.create_sale(
        db=db_session,
        data=PosSaleCreate(
            store_id=store.id,
            payment_method="card",
            lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("2"))],
        ),
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    token = await get_token(pos_client, admin_user)
    resp = await pos_client.get(
        f"/pos/sales/{sale.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(sale.id)
    assert body["payment_method"] == "card"


@pytest.mark.asyncio
async def test_http_get_daily_summary(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """GET /pos/summary?date=today → 200, DailySummaryOut."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store, price=Decimal("100.00"),
    )
    await service.create_sale(
        db=db_session,
        data=PosSaleCreate(
            store_id=store.id,
            payment_method="cash",
            lines=[PosSaleLineIn(product_id=product.id, qty=Decimal("1"))],
        ),
        cashier_id=admin_user.id,
        user=admin_user,
        enterprise_id=admin_user.enterprise_id,
    )

    today = datetime.now(timezone.utc).date().isoformat()
    token = await get_token(pos_client, admin_user)
    resp = await pos_client.get(
        f"/pos/summary?date={today}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_sales"] >= 1
    assert "by_payment" in body


# ─── 13. Agent/courier → 403 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_cannot_create_pos_sale(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    agent_user,
) -> None:
    """agent roli /pos/sales POST → 403."""
    store, product, _ = await _make_seeded_store_product(
        make_price_segment, make_product, make_store,
    )
    token = await get_token(pos_client, agent_user)
    resp = await pos_client.post(
        "/pos/sales",
        json={
            "store_id": str(store.id),
            "payment_method": "cash",
            "lines": [{"product_id": str(product.id), "qty": "1"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_courier_cannot_view_pos_sales(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    courier_user,
) -> None:
    """courier roli /pos/sales GET → 403."""
    token = await get_token(pos_client, courier_user)
    resp = await pos_client.get(
        "/pos/sales",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


# ─── 14. Module gating ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_module_gating_pos_disabled(
    pos_client: AsyncClient,
    db_session: AsyncSession,
    make_user,
    default_enterprise: Enterprise,
) -> None:
    """
    Korxona "pos" moduli o'chiq → /pos/* → 403 (enterprise.module_disabled).
    """
    # POS moduli o'chirilgan
    default_enterprise.enabled_modules = [m for m in ALL_MODULE_KEYS if m != "pos"]
    await db_session.flush()

    admin = await make_user("administrator")
    token = await get_token(pos_client, admin)

    resp = await pos_client.get(
        "/pos/sales",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("message_key") == "enterprise.module_disabled"

    # Qayta yoqish (fixture uchun)
    default_enterprise.enabled_modules = list(ALL_MODULE_KEYS)
    await db_session.flush()
