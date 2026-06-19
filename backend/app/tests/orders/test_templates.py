"""
Buyurtma shabloni testlari — T12.

Test kategoriyalari:
  1.  create_template: shablon + qatorlar saqlanadi (narxsiz).
  2.  apply: shablondan yangi buyurtma yaratiladi — narx katalogdan (server),
      ombor chiqadi, qarz yoziladi. Shablon o'zgarmaydi.
  3.  apply yetarli qoldiq bo'lmasa → create_order kabi xato (atomik rollback).
  4.  RBAC/scope: agent o'z do'koni shabloni; boshqa do'kon shabloni → 404.
  5.  list_templates / get_template / delete_template (soft).
  6.  Bo'sh shablon → orders.empty_template xatosi.
  7.  Idempotentlik: apply client_uuid → bir buyurtma.
  8.  i18n: shablon xabarlari uz/ru.
  9.  HTTP endpoint testlari (orders_client orqali).
  10. Mavjud T11 testlari regressiyaga uchramasligi (import sanity).

Infrasiz: aiosqlite + fakeredis.

MUHIM INVARIANT:
  - Shablonda unit_price YO'Q — faqat product_id + qty.
  - apply create_order() ni qayta ishlatadi (narx server-avtoritar + atomik).
  - Shablon apply dan keyin O'ZGARMAYDI.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.finance import AccountBalance, LedgerEntry
from app.models.order import Order, OrderLine, OrderTemplate, OrderTemplateLine
from app.models.stock import StockBalance, StockMovement
from app.modules.orders import service
from app.modules.orders.schemas import (
    ApplyTemplateIn,
    OrderTemplateCreate,
    TemplateLineIn,
)
from app.tests.orders.conftest import DEFAULT_WAREHOUSE, get_token


# ─── Yordamchi: segmentli do'kon + mahsulot + narx + stock yaratish ──────────


async def _setup(
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    db_session,
    price: Decimal = Decimal("1000.00"),
    qty: Decimal = Decimal("100"),
    store_kwargs: dict | None = None,
):
    """
    Standart test ma'lumotlari: segment + mahsulot + do'kon + stock.
    Returns: (store, product, segment)
    """
    segment = await make_price_segment()
    product = await make_product(price=price, segment_id=segment.id)
    kwargs = store_kwargs or {}
    store = await make_store(segment_id=segment.id, **kwargs)
    await seed_stock(product.id, qty=qty)
    await db_session.commit()
    return store, product, segment


# ─── 1. create_template: shablon + qatorlar, narx YO'Q ───────────────────────


@pytest.mark.asyncio
async def test_create_template_saves_lines_without_price(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    create_template: shablon + qatorlar saqlanadi.
    OrderTemplateLine da unit_price ustuni YO'Q — faqat product_id + qty.
    """
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("500.00"), qty=Decimal("50"),
    )

    data = OrderTemplateCreate(
        store_id=store.id,
        name="Kunlik shablon",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("5"))],
    )

    template = await service.create_template(
        db=db_session, data=data, actor_id=admin_user.id, user=admin_user,
    )
    await db_session.commit()

    # DB dan tekshirish
    stmt = select(OrderTemplate).where(OrderTemplate.id == template.id)
    result = await db_session.execute(stmt)
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.name == "Kunlik shablon"
    assert saved.store_id == store.id
    assert saved.deleted_at is None

    # Qatorlar tekshiruvi — narx YO'Q
    line_stmt = select(OrderTemplateLine).where(
        OrderTemplateLine.template_id == template.id
    )
    line_result = await db_session.execute(line_stmt)
    lines = line_result.scalars().all()
    assert len(lines) == 1
    assert lines[0].product_id == product.id
    assert lines[0].qty == Decimal("5")

    # OrderTemplateLine da unit_price atributi YO'Q (model darajasida)
    assert not hasattr(lines[0], "unit_price"), (
        "OrderTemplateLine da unit_price bo'lmasligi kerak (server-avtoritar invariant)"
    )


# ─── 2. apply: shablondan buyurtma yaratiladi, narx katalogdan ───────────────


@pytest.mark.asyncio
async def test_apply_template_creates_order_with_catalog_price(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    apply: shablondan yangi buyurtma yaratiladi.
    - Narx katalogdan (server tomonida) olinadi — shablondagi narx YO'Q.
    - Ombor chiqadi, qarz yoziladi (create_order() qayta ishlatilgani uchun atomik).
    - Shablon O'ZGARMAYDI.
    """
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("2000.00"), qty=Decimal("30"),
    )

    # Shablon yaratish
    tpl_data = OrderTemplateCreate(
        store_id=store.id,
        name="Haftalik zakaz",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("4"))],
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
    )
    await db_session.commit()

    # Apply
    apply_data = ApplyTemplateIn()
    order = await service.apply_template(
        db=db_session,
        template_id=template.id,
        apply_data=apply_data,
        actor_id=admin_user.id,
        user=admin_user,
        redis=fake_redis,
    )
    await db_session.commit()

    # Buyurtma yaratilganini tekshirish
    assert order is not None
    assert order.status == "confirmed"
    assert order.store_id == store.id

    # Narx server tomonidan (katalogdan): 2000 * 4 = 8000
    assert order.total_amount == Decimal("8000.00"), (
        f"Narx katalogdan olinishi kerak: 2000 * 4 = 8000, got {order.total_amount}"
    )
    assert len(order.lines) == 1
    assert order.lines[0].unit_price == Decimal("2000.00"), (
        "unit_price katalogdan olinishi kerak"
    )
    assert order.lines[0].qty == Decimal("4")

    # Ombor chiqganini tekshirish (create_order() atomik chaqirilgani uchun)
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    bal = sb_result.scalar_one_or_none()
    assert bal is not None
    assert bal.qty_on_hand == Decimal("26"), "30 - 4 = 26 bo'lishi kerak"

    # Qarz yozilganini tekshirish
    le_stmt = select(LedgerEntry).where(
        LedgerEntry.ref_id == order.id,
        LedgerEntry.type == "debit",
    )
    le_result = await db_session.execute(le_stmt)
    entries = le_result.scalars().all()
    assert len(entries) == 1
    assert entries[0].amount == Decimal("8000.00")

    # MUHIM: Shablon o'zgarmagan
    tpl_stmt = select(OrderTemplate).where(OrderTemplate.id == template.id)
    tpl_result = await db_session.execute(tpl_stmt)
    saved_tpl = tpl_result.scalar_one()
    assert saved_tpl.deleted_at is None, "Shablon o'chmasligi kerak"
    assert saved_tpl.name == "Haftalik zakaz", "Shablon nomi o'zgarmasligi kerak"

    # Shablon qatorlari o'zgarmagan
    line_stmt = select(OrderTemplateLine).where(
        OrderTemplateLine.template_id == template.id
    )
    line_result = await db_session.execute(line_stmt)
    tpl_lines = line_result.scalars().all()
    assert len(tpl_lines) == 1, "Shablon qatorlari o'zgarmasligi kerak"


# ─── 3. apply — yetarli qoldiq yo'q → create_order xatosi ───────────────────


@pytest.mark.asyncio
async def test_apply_template_insufficient_stock_rolls_back(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    apply: qoldiq yetmasa → AppError (create_order() kabi xato).
    Atomik rollback: order, stock_movement, ledger_entry — hech narsa yozilmaydi.
    Shablon o'zgarmaydi.
    """
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("100.00"), qty=Decimal("2"),  # faqat 2 ta bor
    )

    # ID lar rollback dan oldin saqlab olinadi
    store_id = store.id
    product_id = product.id

    tpl_data = OrderTemplateCreate(
        store_id=store_id,
        name="Katta zakaz",
        lines=[TemplateLineIn(product_id=product_id, qty=Decimal("10"))],  # 10 ta kerak
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
    )
    template_id = template.id
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await service.apply_template(
            db=db_session,
            template_id=template_id,
            apply_data=ApplyTemplateIn(),
            actor_id=admin_user.id,
            user=admin_user,
            redis=fake_redis,
        )
    assert exc_info.value.message_key == "orders.insufficient_stock"
    assert exc_info.value.status_code == 409

    await db_session.rollback()

    # Order YO'Q
    order_stmt = select(Order).where(Order.store_id == store_id)
    order_result = await db_session.execute(order_stmt)
    orders = order_result.scalars().all()
    assert len(orders) == 0, "Rollback: order yozilmagan bo'lishi kerak"

    # StockMovement YO'Q
    sm_stmt = select(StockMovement).where(
        StockMovement.product_id == product_id,
        StockMovement.type == "out",
    )
    sm_result = await db_session.execute(sm_stmt)
    movements = sm_result.scalars().all()
    assert len(movements) == 0, "Rollback: stock_movement yozilmagan bo'lishi kerak"

    # Shablon o'zgarmagan (DB dan to'g'ridan-to'g'ri tekshirish)
    tpl_stmt = select(OrderTemplate).where(OrderTemplate.id == template_id)
    tpl_result = await db_session.execute(tpl_stmt)
    saved_tpl = tpl_result.scalar_one()
    assert saved_tpl.deleted_at is None, "Shablon rollback dan ta'sirlanmasligi kerak"


# ─── 4. RBAC/scope: agent o'z do'koni shabloni ───────────────────────────────


@pytest.mark.asyncio
async def test_rbac_agent_own_store_template_accessible(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    seed_stock,
) -> None:
    """Agent o'z do'koni shablonini ko'radi va apply qila oladi."""
    agent = await make_user("agent")
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("500.00"), qty=Decimal("20"),
        store_kwargs={"agent_id": agent.id},
    )

    tpl_data = OrderTemplateCreate(
        store_id=store.id,
        name="Agent shabloni",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=agent.id, user=agent,
    )
    await db_session.commit()

    # get_template — agent o'z shablonini ko'radi
    fetched = await service.get_template(db=db_session, template_id=template.id, user=agent)
    assert fetched.id == template.id

    # apply — agent o'z do'koni shablonini apply qila oladi
    order = await service.apply_template(
        db=db_session,
        template_id=template.id,
        apply_data=ApplyTemplateIn(),
        actor_id=agent.id,
        user=agent,
        redis=fake_redis,
    )
    await db_session.commit()
    assert order is not None
    assert order.store_id == store.id


@pytest.mark.asyncio
async def test_rbac_agent_other_store_template_returns_404(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    admin_user,
    seed_stock,
) -> None:
    """Agent boshqa do'kon shablonini ko'ra olmaydi → 404 (IDOR himoya)."""
    agent = await make_user("agent")
    # Do'kon agent ga tegishli emas
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("100.00"), qty=Decimal("20"),
    )

    tpl_data = OrderTemplateCreate(
        store_id=store.id,
        name="Boshqa do'kon shabloni",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
    )
    await db_session.commit()

    # Agent boshqa do'kon shablonini ko'ra olmaydi
    with pytest.raises(AppError) as exc_info:
        await service.get_template(db=db_session, template_id=template.id, user=agent)
    assert exc_info.value.message_key == "orders.template_not_found"
    assert exc_info.value.status_code == 404

    # Agent boshqa do'kon shablonini apply qila olmaydi
    with pytest.raises(AppError) as exc_info2:
        await service.apply_template(
            db=db_session,
            template_id=template.id,
            apply_data=ApplyTemplateIn(),
            actor_id=agent.id,
            user=agent,
            redis=fake_redis,
        )
    assert exc_info2.value.message_key == "orders.template_not_found"
    assert exc_info2.value.status_code == 404


# ─── 5. list_templates / get_template / delete_template ──────────────────────


@pytest.mark.asyncio
async def test_list_templates_paginated(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """list_templates paginated ro'yxat qaytaradi."""
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("100.00"), qty=Decimal("100"),
    )

    # 3 ta shablon yaratish
    for i in range(3):
        tpl_data = OrderTemplateCreate(
            store_id=store.id,
            name=f"Shablon {i}",
            lines=[TemplateLineIn(product_id=product.id, qty=Decimal("1"))],
        )
        await service.create_template(
            db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
        )
    await db_session.commit()

    items, total = await service.list_templates(
        db=db_session,
        store_id=store.id,
        user=admin_user,
    )
    assert total == 3
    assert len(items) == 3

    # Paginated: limit=2
    items2, total2 = await service.list_templates(
        db=db_session,
        store_id=store.id,
        user=admin_user,
        limit=2,
        offset=0,
    )
    assert total2 == 3
    assert len(items2) == 2


@pytest.mark.asyncio
async def test_delete_template_soft_delete(
    db_session: AsyncSession,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """delete_template: soft delete — deleted_at o'rnatiladi, DB dan o'chirmaydi."""
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("100.00"), qty=Decimal("10"),
    )

    tpl_data = OrderTemplateCreate(
        store_id=store.id,
        name="O'chiriladigan shablon",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
    )
    await db_session.commit()

    # O'chirish
    await service.delete_template(
        db=db_session,
        template_id=template.id,
        user=admin_user,
        actor_id=admin_user.id,
    )
    await db_session.commit()

    # DB da yozuv mavjud lekin deleted_at o'rnatilgan
    stmt = select(OrderTemplate).where(OrderTemplate.id == template.id)
    result = await db_session.execute(stmt)
    saved = result.scalar_one_or_none()
    assert saved is not None, "Soft delete: yozuv DB da qolishi kerak"
    assert saved.deleted_at is not None, "Soft delete: deleted_at o'rnatilishi kerak"

    # get_template endi 404 qaytaradi
    with pytest.raises(AppError) as exc_info:
        await service.get_template(db=db_session, template_id=template.id, user=admin_user)
    assert exc_info.value.message_key == "orders.template_not_found"

    # list_templates da ko'rinmaydi
    items, total = await service.list_templates(
        db=db_session, store_id=store.id, user=admin_user,
    )
    assert total == 0, "O'chirilgan shablon ro'yxatda ko'rinmasligi kerak"


@pytest.mark.asyncio
async def test_delete_template_not_found(
    db_session: AsyncSession,
    admin_user,
) -> None:
    """Mavjud bo'lmagan shablon o'chirish → 404."""
    with pytest.raises(AppError) as exc_info:
        await service.delete_template(
            db=db_session,
            template_id=uuid.uuid4(),
            user=admin_user,
            actor_id=admin_user.id,
        )
    assert exc_info.value.message_key == "orders.template_not_found"
    assert exc_info.value.status_code == 404


# ─── 6. Bo'sh shablon → xato ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_template_lines_raises_validation_error(
    db_session: AsyncSession,
    make_store,
    admin_user,
) -> None:
    """Bo'sh lines → Pydantic validatsiya xatosi."""
    from pydantic import ValidationError

    store = await make_store()
    await db_session.commit()

    with pytest.raises(ValidationError):
        OrderTemplateCreate(
            store_id=store.id,
            name="Bo'sh shablon",
            lines=[],
        )


# ─── 7. Idempotentlik: apply client_uuid → bir buyurtma ─────────────────────


@pytest.mark.asyncio
async def test_apply_template_idempotency_client_uuid(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    apply client_uuid bilan — ikki marta chaqirilsa bitta buyurtma qaytadi.
    create_order() idempotentlik mexanizmi ishlatiladi.
    """
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("1000.00"), qty=Decimal("100"),
    )

    tpl_data = OrderTemplateCreate(
        store_id=store.id,
        name="Idem shablon",
        lines=[TemplateLineIn(product_id=product.id, qty=Decimal("2"))],
    )
    template = await service.create_template(
        db=db_session, data=tpl_data, actor_id=admin_user.id, user=admin_user,
    )
    await db_session.commit()

    client_uuid = uuid.uuid4()
    apply_data = ApplyTemplateIn(client_uuid=client_uuid)

    # Birinchi apply
    order1 = await service.apply_template(
        db=db_session,
        template_id=template.id,
        apply_data=apply_data,
        actor_id=admin_user.id,
        user=admin_user,
        redis=fake_redis,
    )
    await db_session.commit()

    # Ikkinchi apply (bir xil client_uuid)
    order2 = await service.apply_template(
        db=db_session,
        template_id=template.id,
        apply_data=apply_data,
        actor_id=admin_user.id,
        user=admin_user,
        redis=fake_redis,
    )

    assert order1.id == order2.id, (
        "Bir xil client_uuid → bitta buyurtma qaytishi kerak (idempotentlik)"
    )

    # DB da bitta buyurtma
    order_stmt = select(Order).where(Order.store_id == store.id)
    result = await db_session.execute(order_stmt)
    orders = result.scalars().all()
    assert len(orders) == 1, "Idempotentlik: DB da bitta buyurtma bo'lishi kerak"


# ─── 8. i18n: shablon xabarlari ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_not_found_i18n_uz(
    orders_client: AsyncClient,
    admin_user,
) -> None:
    """orders.template_not_found xabari o'zbek tilida."""
    token = await get_token(orders_client, admin_user)
    fake_id = uuid.uuid4()
    resp = await orders_client.get(
        f"/orders/templates/{fake_id}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "shablon" in data["message"].lower() or "topilmadi" in data["message"].lower()


@pytest.mark.asyncio
async def test_template_not_found_i18n_ru(
    orders_client: AsyncClient,
    admin_user,
) -> None:
    """orders.template_not_found xabari rus tilida."""
    token = await get_token(orders_client, admin_user)
    fake_id = uuid.uuid4()
    resp = await orders_client.get(
        f"/orders/templates/{fake_id}",
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "шаблон" in data["message"].lower() or "найден" in data["message"].lower()


# ─── 9. HTTP endpoint testlari ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_create_template_success(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """POST /orders/templates → 201 muvaffaqiyatli shablon."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    body = {
        "store_id": str(store.id),
        "name": "HTTP shablon",
        "lines": [
            {"product_id": str(product.id), "qty": "3"},
        ],
    }
    resp = await orders_client.post(
        "/orders/templates",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "HTTP shablon"
    assert len(data["lines"]) == 1
    assert Decimal(data["lines"][0]["qty"]) == Decimal("3")
    # Narx YO'Q shablon javobida
    assert "unit_price" not in data["lines"][0], (
        "Shablon qatorida unit_price bo'lmasligi kerak"
    )


@pytest.mark.asyncio
async def test_http_apply_template_creates_order(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """POST /orders/templates/{id}/apply → 201 yangi buyurtma."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    # Shablon yaratish
    tpl_body = {
        "store_id": str(store.id),
        "name": "Apply test shabloni",
        "lines": [{"product_id": str(product.id), "qty": "2"}],
    }
    tpl_resp = await orders_client.post(
        "/orders/templates",
        json=tpl_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert tpl_resp.status_code == 201, tpl_resp.text
    template_id = tpl_resp.json()["id"]

    # Apply
    apply_body = {"mode": "oddiy", "currency": "UZS"}
    resp = await orders_client.post(
        f"/orders/templates/{template_id}/apply",
        json=apply_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "confirmed"
    # Server narxi: 1000 * 2 = 2000
    assert Decimal(data["total_amount"]) == Decimal("2000.00"), (
        "Narx katalogdan olinishi kerak: 1000 * 2 = 2000"
    )
    assert len(data["lines"]) == 1
    assert Decimal(data["lines"][0]["unit_price"]) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_http_get_templates_list(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """GET /orders/templates → paginated ro'yxat."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    # 2 ta shablon yaratish
    body = {
        "store_id": str(store.id),
        "name": "Shablon",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    await orders_client.post("/orders/templates", json=body, headers={"Authorization": f"Bearer {token}"})
    await orders_client.post("/orders/templates", json=body, headers={"Authorization": f"Bearer {token}"})

    resp = await orders_client.get(
        "/orders/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_http_get_template_by_id(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """GET /orders/templates/{id} — mavjud shablon."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("10"))

    tpl_body = {
        "store_id": str(store.id),
        "name": "ID test shabloni",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    tpl_resp = await orders_client.post(
        "/orders/templates",
        json=tpl_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = tpl_resp.json()["id"]

    resp = await orders_client.get(
        f"/orders/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == template_id
    assert data["name"] == "ID test shabloni"


@pytest.mark.asyncio
async def test_http_delete_template(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """DELETE /orders/templates/{id} → 204; keyin GET → 404."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("10"))

    tpl_body = {
        "store_id": str(store.id),
        "name": "O'chiriladigan",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    tpl_resp = await orders_client.post(
        "/orders/templates",
        json=tpl_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = tpl_resp.json()["id"]

    # O'chirish
    del_resp = await orders_client.delete(
        f"/orders/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Endi 404
    get_resp = await orders_client.get(
        f"/orders/templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_http_template_not_found(
    orders_client: AsyncClient,
    admin_user,
) -> None:
    """GET /orders/templates/{id} — mavjud bo'lmagan ID → 404."""
    token = await get_token(orders_client, admin_user)
    resp = await orders_client.get(
        f"/orders/templates/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["message_key"] == "orders.template_not_found"


@pytest.mark.asyncio
async def test_http_apply_template_not_found(
    orders_client: AsyncClient,
    admin_user,
) -> None:
    """POST /orders/templates/{id}/apply — mavjud bo'lmagan ID → 404."""
    token = await get_token(orders_client, admin_user)
    resp = await orders_client.post(
        f"/orders/templates/{uuid.uuid4()}/apply",
        json={"mode": "oddiy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["message_key"] == "orders.template_not_found"


@pytest.mark.asyncio
async def test_http_apply_template_insufficient_stock(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """POST /orders/templates/{id}/apply — qoldiq yetmasa → 409."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("1"))  # faqat 1 ta

    tpl_body = {
        "store_id": str(store.id),
        "name": "Katta zakaz shabloni",
        "lines": [{"product_id": str(product.id), "qty": "100"}],  # 100 ta kerak
    }
    tpl_resp = await orders_client.post(
        "/orders/templates",
        json=tpl_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert tpl_resp.status_code == 201
    template_id = tpl_resp.json()["id"]

    apply_resp = await orders_client.post(
        f"/orders/templates/{template_id}/apply",
        json={"mode": "oddiy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert apply_resp.status_code == 409
    assert apply_resp.json()["message_key"] == "orders.insufficient_stock"


@pytest.mark.asyncio
async def test_http_unauthenticated_templates(
    orders_client: AsyncClient,
) -> None:
    """Token yo'q → 401 (template endpointlari uchun)."""
    resp = await orders_client.get("/orders/templates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_http_accountant_cannot_create_template(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    accountant_user,
    seed_stock,
) -> None:
    """Buxgalter orders:create ruxsatiga ega emas → 403."""
    token = await get_token(orders_client, accountant_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("10"))

    body = {
        "store_id": str(store.id),
        "name": "Buxgalter shabloni",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    resp = await orders_client.post(
        "/orders/templates",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 10. T11 testlari regressiyaga uchramasin (sanity import) ────────────────


@pytest.mark.asyncio
async def test_t11_regression_create_order_still_works(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    T11 regressiya: create_order() shablonlar qo'shilgandan keyin ham ishlaydi.
    Bu eng muhim invariant — T12 T11 ning create_order() ni buzmaydi.
    """
    from app.modules.orders.schemas import OrderCreate, OrderLineIn

    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, db_session,
        price=Decimal("100.00"), qty=Decimal("50"),
    )

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("3"))],
    )
    order = await service.create_order(
        db_session, data, actor_id=admin_user.id, redis=fake_redis
    )
    await db_session.commit()

    assert order is not None
    assert order.status == "confirmed"
    assert order.total_amount == Decimal("300.00")
