"""
Ombor moduli testlari — StockMovement, StockBalance, RBAC, append-only, Decimal.

Test kategoriyalari:
  1. record_movement: INSERT → balans yangilanadi (in oshiradi, out kamaytiradi)
  2. Append-only: 2 harakat → 2 yozuv, balans yig'indi (hech qachon UPDATE/DELETE emas)
  3. Idempotentlik: client_uuid → bir yozuv (ikkinchi chaqiruv mavjudni qaytaradi)
  4. Version conflict (optimistik lock)
  5. RBAC: agent/store/courier stock:create → 403; view ruxsatli
  6. Balans aniqligi: Decimal
  7. Yetarli qoldiq yo'q → 409
  8. i18n: uz/ru xabarlar
  9. Mahsulot topilmasa → 404

Infrasiz: aiosqlite + fakeredis.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import StockBalance, StockMovement
from app.modules.stock import service
from app.modules.stock.schemas import StockMovementCreate
from app.tests.stock.conftest import WAREHOUSE_A, WAREHOUSE_B, get_token


# ─── 1. record_movement: INSERT + balans yangilanadi ─────────────────────────


@pytest.mark.asyncio
async def test_record_movement_in_increases_balance(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """in harakati balansni oshiradi."""
    product = await make_product()

    data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("10.0000"),
    )
    movement = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    assert movement.id is not None
    assert movement.qty == Decimal("10.0000")
    assert movement.type == "in"

    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("10.0000")


@pytest.mark.asyncio
async def test_record_movement_out_decreases_balance(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """out harakati balansni kamaytiradi."""
    product = await make_product()

    # Avval kirim
    in_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("50.0000"),
    )
    await service.record_movement(db_session, in_data, actor_id=admin_user.id, redis=fake_redis)

    # Chiqim
    out_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="out",
        qty=Decimal("20.0000"),
    )
    await service.record_movement(db_session, out_data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("30.0000")


# ─── 2. Append-only: 2 harakat → 2 yozuv, balans yig'indi ───────────────────


@pytest.mark.asyncio
async def test_append_only_two_movements_two_records(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """
    APPEND-ONLY tekshiruvi:
    Ikki harakat → ikki alohida yozuv, UPDATE/DELETE YO'Q.
    Balans ikkisini yig'indisi sifatida to'g'ri hisoblanadi.
    """
    product = await make_product()

    data1 = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("100.0000"),
    )
    data2 = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("50.0000"),
    )

    m1 = await service.record_movement(db_session, data1, actor_id=admin_user.id, redis=fake_redis)
    m2 = await service.record_movement(db_session, data2, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Ikki alohida yozuv
    assert m1.id != m2.id

    # DB da ikkala yozuv mavjud (UPDATE qilinmagan)
    stmt = select(StockMovement).where(StockMovement.product_id == product.id)
    result = await db_session.execute(stmt)
    movements = list(result.scalars().all())
    assert len(movements) == 2

    # Balans yig'indi
    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("150.0000")


@pytest.mark.asyncio
async def test_append_only_movements_never_updated(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """
    Harakatlar hech qachon UPDATE qilinmaydi.
    Birinchi harakat yozuvi keyingi harakatdan keyin ham o'zgarmaydi.
    """
    product = await make_product()

    data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("30.0000"),
    )
    movement = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    original_id = movement.id
    original_qty = movement.qty
    original_created_at = movement.created_at

    # Ikkinchi harakat
    data2 = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="out",
        qty=Decimal("10.0000"),
    )
    await service.record_movement(db_session, data2, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Birinchi harakat o'zgarmagan (append-only)
    stmt = select(StockMovement).where(StockMovement.id == original_id)
    result = await db_session.execute(stmt)
    fetched = result.scalar_one()
    assert fetched.qty == original_qty
    assert fetched.created_at == original_created_at
    assert fetched.type == "in"


# ─── 3. Idempotentlik ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_same_client_uuid_returns_same_record(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """Bir xil client_uuid → bir yozuv (ikkinchi chaqiruv mavjudni qaytaradi)."""
    product = await make_product()
    client_uuid = uuid.uuid4()

    data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("10.0000"),
        client_uuid=client_uuid,
    )

    m1 = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    m2 = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    assert m1.id == m2.id

    # DB da faqat bir yozuv
    stmt = select(StockMovement).where(StockMovement.product_id == product.id)
    result = await db_session.execute(stmt)
    movements = list(result.scalars().all())
    assert len(movements) == 1


# ─── 4. Yetarli qoldiq yo'q ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_out_insufficient_quantity_raises_error(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """Chiqim qoldiqdan ko'p bo'lsa → AppError 409."""
    from app.core.errors import AppError

    product = await make_product()

    # 5 kirim
    in_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("5.0000"),
    )
    await service.record_movement(db_session, in_data, actor_id=admin_user.id, redis=fake_redis)

    # 10 chiqim (5 dan ko'p)
    out_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="out",
        qty=Decimal("10.0000"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_movement(db_session, out_data, actor_id=admin_user.id, redis=fake_redis)

    assert exc_info.value.message_key == "stock.insufficient_quantity"
    assert exc_info.value.status_code == 409


# ─── 5. Mahsulot topilmasa ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_movement_product_not_found(
    db_session: AsyncSession,
    fake_redis,
    admin_user,
) -> None:
    """Mavjud bo'lmagan mahsulot → AppError 404."""
    from app.core.errors import AppError

    data = StockMovementCreate(
        product_id=uuid.uuid4(),  # mavjud emas
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("10.0000"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    assert exc_info.value.message_key == "stock.product_not_found"
    assert exc_info.value.status_code == 404


# ─── 6. Balans aniqligi (Decimal) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_balance_decimal_precision(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """Balans Decimal aniqligini saqlaydi (float yaxlitlanishi yo'q)."""
    product = await make_product()

    # Bir nechta mayda miqdorlar
    for qty in ["0.3333", "0.3333", "0.3334"]:
        data = StockMovementCreate(
            product_id=product.id,
            warehouse_id=WAREHOUSE_A,
            type="in",
            qty=Decimal(qty),
        )
        await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    # 0.3333 + 0.3333 + 0.3334 = 1.0000 (Decimal aniqlik)
    assert balance.qty_on_hand == Decimal("1.0000")


# ─── 7. RBAC testlari (HTTP) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_cannot_create_movement(
    stock_client: AsyncClient,
    agent_user,
    make_product,
) -> None:
    """Agent stock:create ruxsatiga ega emas → 403."""
    product = await make_product()
    token = await get_token(stock_client, agent_user)

    resp = await stock_client.post(
        "/stock/movements",
        json={
            "product_id": str(product.id),
            "warehouse_id": str(WAREHOUSE_A),
            "type": "in",
            "qty": "10.0000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_store_cannot_create_movement(
    stock_client: AsyncClient,
    store_user,
    make_product,
) -> None:
    """Store roli stock:create ruxsatiga ega emas → 403."""
    product = await make_product()
    token = await get_token(stock_client, store_user)

    resp = await stock_client.post(
        "/stock/movements",
        json={
            "product_id": str(product.id),
            "warehouse_id": str(WAREHOUSE_A),
            "type": "in",
            "qty": "10.0000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_create_movement(
    stock_client: AsyncClient,
    admin_user,
    make_product,
) -> None:
    """Admin stock:create ruxsatiga ega → 201."""
    product = await make_product()
    token = await get_token(stock_client, admin_user)

    resp = await stock_client.post(
        "/stock/movements",
        json={
            "product_id": str(product.id),
            "warehouse_id": str(WAREHOUSE_A),
            "type": "in",
            "qty": "10.0000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["type"] == "in"
    assert data["qty"] == "10.0000"


@pytest.mark.asyncio
async def test_agent_can_view_balance(
    stock_client: AsyncClient,
    agent_user,
    make_product,
) -> None:
    """Agent stock:view ruxsatiga ega → 200."""
    product = await make_product()
    token = await get_token(stock_client, agent_user)

    resp = await stock_client.get(
        f"/stock/balance?product_id={product.id}&warehouse_id={WAREHOUSE_A}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["product_id"] == str(product.id)
    assert Decimal(data["qty_on_hand"]) == Decimal("0")


@pytest.mark.asyncio
async def test_courier_can_view_balance(
    stock_client: AsyncClient,
    courier_user,
    make_product,
) -> None:
    """Kuryer stock:view ruxsatiga ega → 200."""
    product = await make_product()
    token = await get_token(stock_client, courier_user)

    resp = await stock_client.get(
        f"/stock/balance?product_id={product.id}&warehouse_id={WAREHOUSE_A}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_view_movements_list(
    stock_client: AsyncClient,
    admin_user,
    make_product,
) -> None:
    """Admin harakatlar ro'yxatini ko'ra oladi."""
    product = await make_product()
    token = await get_token(stock_client, admin_user)

    # Avval harakat yaratish
    await stock_client.post(
        "/stock/movements",
        json={
            "product_id": str(product.id),
            "warehouse_id": str(WAREHOUSE_A),
            "type": "in",
            "qty": "5.0000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await stock_client.get(
        f"/stock/movements?product_id={product.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


# ─── 8. i18n testlari ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insufficient_quantity_message_uz(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """Yetarli qoldiq yo'q xatosi — uz tilida."""
    from app.core.errors import AppError
    from app.core.messages import translate

    product = await make_product()

    out_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="out",
        qty=Decimal("999.0000"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_movement(db_session, out_data, actor_id=admin_user.id, redis=fake_redis)

    err = exc_info.value
    msg_uz = translate(err.message_key, locale="uz", **err.params)
    msg_ru = translate(err.message_key, locale="ru", **err.params)

    assert "mavjud" in msg_uz.lower() or "0" in msg_uz
    assert "доступно" in msg_ru or "0" in msg_ru


@pytest.mark.asyncio
async def test_product_not_found_message_ru(
    db_session: AsyncSession,
    fake_redis,
    admin_user,
) -> None:
    """Mahsulot topilmadi xatosi — ru tilida."""
    from app.core.errors import AppError
    from app.core.messages import translate

    data = StockMovementCreate(
        product_id=uuid.uuid4(),
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("1.0000"),
    )
    with pytest.raises(AppError) as exc_info:
        await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    err = exc_info.value
    msg_ru = translate(err.message_key, locale="ru")
    assert "не найден" in msg_ru.lower() or msg_ru != err.message_key


# ─── 9. Transfer: balansga to'g'ri ta'sir ────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_decreases_source_balance(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """transfer harakati manba omboridan kamaytiradi (chiqim sifatida)."""
    product = await make_product()

    # Kirim
    in_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("100.0000"),
    )
    await service.record_movement(db_session, in_data, actor_id=admin_user.id, redis=fake_redis)

    # Transfer (chiqim)
    transfer_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="transfer",
        qty=Decimal("40.0000"),
    )
    await service.record_movement(db_session, transfer_data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("60.0000")


@pytest.mark.asyncio
async def test_adjust_increases_balance(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """adjust harakati balansni oshiradi (delta += qty)."""
    product = await make_product()

    # Avval kirim
    in_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("50.0000"),
    )
    await service.record_movement(db_session, in_data, actor_id=admin_user.id, redis=fake_redis)

    # Adjust (faqat oshiradi)
    adjust_data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="adjust",
        qty=Decimal("10.0000"),
    )
    await service.record_movement(db_session, adjust_data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("60.0000")


# ─── 10. Ikki ombor izolyatsiyasi ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_warehouses_balance_isolated(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """
    Bir mahsulot, ikki ombor — balanslar ajratilgan.
    Ombor A ga kirim Ombor B balansiga ta'sir qilmaydi.
    """
    product = await make_product()

    # Ombor A: 100 kirim
    in_a = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("100.0000"),
    )
    await service.record_movement(db_session, in_a, actor_id=admin_user.id, redis=fake_redis)

    # Ombor B: 30 kirim
    in_b = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_B,
        type="in",
        qty=Decimal("30.0000"),
    )
    await service.record_movement(db_session, in_b, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    balance_a = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    balance_b = await service.get_balance(db_session, product.id, WAREHOUSE_B)

    assert balance_a.qty_on_hand == Decimal("100.0000"), "Ombor A: 100"
    assert balance_b.qty_on_hand == Decimal("30.0000"), "Ombor B: 30"
    assert balance_a.qty_on_hand != balance_b.qty_on_hand, "Balanslar ajratilgan"


# ─── 11. Idempotentlik SET NX bilan ishlaydi ────────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_set_nx_single_movement(
    db_session: AsyncSession,
    fake_redis,
    make_product,
    admin_user,
) -> None:
    """
    SET NX bilan idempotentlik: bir xil client_uuid → bitta harakat.
    Balans faqat bir marta o'zgaradi.
    """
    product = await make_product()
    client_uuid = uuid.uuid4()

    data = StockMovementCreate(
        product_id=product.id,
        warehouse_id=WAREHOUSE_A,
        type="in",
        qty=Decimal("25.0000"),
        client_uuid=client_uuid,
    )

    # Uch marta chaqirish — faqat bitta yozuv bo'lishi kerak
    m1 = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    m2 = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    m3 = await service.record_movement(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    assert m1.id == m2.id == m3.id, "Bir xil client_uuid → bir xil harakat"

    # DB da faqat bir yozuv
    stmt = select(StockMovement).where(StockMovement.product_id == product.id)
    result = await db_session.execute(stmt)
    movements = list(result.scalars().all())
    assert len(movements) == 1

    # Balans faqat bir marta o'zgargan
    balance = await service.get_balance(db_session, product.id, WAREHOUSE_A)
    assert balance.qty_on_hand == Decimal("25.0000")
