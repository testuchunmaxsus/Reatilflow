"""
Buyurtma moduli testlari — T11 Buyurtma yadrosi.

Test kategoriyalari:
  1.  ATOMIKLIK (eng muhim): yetarli qoldiq → order+stock+ledger yoziladi.
  2.  ATOMIKLIK rollback: qoldiq yetmasa → AppError, order YO'Q, stock_movement YO'Q,
      ledger_entry YO'Q (to'liq rollback — DB da tekshiriladi).
  3.  total_amount qatorlardan to'g'ri hisoblanadi (Decimal).
  4.  Idempotentlik: client_uuid → bir order; IntegrityError graceful.
  5.  Holat mashinasi:
      - qonuniy o'tishlar ishlaydi.
      - noqonuniy o'tish → 422 invalid_transition.
      - delivered → hech qaerga (terminal).
  6.  RBAC/scope:
      - agent o'z buyurtmalari (boshqasi 404).
      - store o'ziniki.
      - admin barchasi.
  7.  Bo'sh lines → xato (422).
  8.  Noma'lum product → 404.
  9.  Noma'lum store → 404.
  10. i18n: uz/ru xabarlar.
  11. version optimistik lock: noto'g'ri version → 409.
  12. NARX MANIPULYATSIYASI YOPILGANI: unit_price/discount/segment_id rad etiladi.
  13. KOMPENSATSIYA: confirmed/packed/delivering → canceled → ombor/ledger qaytadi.
  14. Idempotentlik doirasi: boshqa aktor bir xil client_uuid → 409 (DoS yo'q).
  15. Buxgalter PATCH /status → 403.
  16. GET /orders HTTP endpoint.

Infrasiz: aiosqlite + fakeredis.

MUHIM O'ZGARISH (narx xavfsizligi tuzatishidan so'ng):
  - Barcha testlar do'konga segment_id berib, mahsulotga o'sha segment narxini qo'shadi.
  - unit_price/discount/segment_id schema darajasida yo'q — testlar faqat product_id + qty yuboradi.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import AccountBalance, LedgerEntry
from app.models.order import Order, OrderLine
from app.models.stock import StockBalance, StockMovement
from app.models.store import AgentStore
from app.modules.orders import service
from app.modules.orders.schemas import OrderCreate, OrderLineIn, OrderStatusUpdate
from app.tests.orders.conftest import DEFAULT_WAREHOUSE, get_token


# ─── Yordamchi: segmentli do'kon + mahsulot + narx yaratish ─────────────────


async def _make_seeded_store_and_product(
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    price: Decimal = Decimal("1000.00"),
    qty: Decimal = Decimal("100"),
    store_kwargs: dict | None = None,
):
    """
    Segmentli do'kon + mahsulot + narx + stock seed.

    Returns: (store, product, segment)
    """
    segment = await make_price_segment()
    product = await make_product(price=price, segment_id=segment.id)
    kwargs = store_kwargs or {}
    store = await make_store(segment_id=segment.id, **kwargs)
    await seed_stock(product.id, qty=qty)
    return store, product, segment


# ─── 1. ATOMIKLIK: yetarli qoldiq → hammasi yoziladi ─────────────────────────


@pytest.mark.asyncio
async def test_atomicity_success(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    ATOMIKLIK testi (muvaffaqiyatli):
      Yetarli qoldiq bor → order, stock_movement, ledger_entry — hammasi yoziladi.
      StockMovement ham tekshiriladi (oldingi versiyada yo'q edi).
    """
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("50"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("3"))],
    )

    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Order yozilganini tekshirish
    order_stmt = select(Order).where(Order.id == order.id)
    result = await db_session.execute(order_stmt)
    saved_order = result.scalar_one_or_none()
    assert saved_order is not None
    assert saved_order.status == "confirmed"
    assert saved_order.total_amount == Decimal("3000.00")

    # stock_movement yozilganini tekshirish (MUHIM: avval tekshirilmagan edi)
    sm_stmt = select(StockMovement).where(
        StockMovement.ref_id == order.id,
        StockMovement.type == "out",
    )
    sm_result = await db_session.execute(sm_stmt)
    movements = sm_result.scalars().all()
    assert len(movements) == 1, "StockMovement yozilishi kerak"
    assert movements[0].qty == Decimal("3")

    # ledger_entry yozilganini tekshirish
    le_stmt = select(LedgerEntry).where(
        LedgerEntry.ref_id == order.id,
        LedgerEntry.type == "debit",
    )
    le_result = await db_session.execute(le_stmt)
    entries = le_result.scalars().all()
    assert len(entries) == 1
    assert entries[0].amount == Decimal("3000.00")

    # stock_balance kamayganini tekshirish
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    balance = sb_result.scalar_one_or_none()
    assert balance is not None
    assert balance.qty_on_hand == Decimal("47")  # 50 - 3


# ─── 2. ATOMIKLIK rollback: qoldiq yetmasa → hech narsa yozilmaydi ───────────


@pytest.mark.asyncio
async def test_atomicity_rollback_on_insufficient_stock(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    ATOMIKLIK testi (rollback):
      Qoldiq yetmasa → AppError → order YO'Q, stock_movement YO'Q, ledger_entry YO'Q.
      Bu eng muhim invariant test. StockMovement ham tekshiriladi.
    """
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("500.00"), qty=Decimal("2"),
    )
    await db_session.commit()

    store_id = store.id
    product_id = product.id

    data = OrderCreate(
        store_id=store_id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product_id, qty=Decimal("10"))],
    )

    from app.core.errors import AppError
    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    assert exc_info.value.message_key == "orders.insufficient_stock"
    assert exc_info.value.status_code == 409

    await db_session.rollback()

    # Order YO'Q
    order_stmt = select(Order).where(Order.store_id == store_id)
    order_result = await db_session.execute(order_stmt)
    orders = order_result.scalars().all()
    assert len(orders) == 0, "Order yozilmagan bo'lishi kerak (rollback)"

    # StockMovement YO'Q (muhim: avval tekshirilmagan edi)
    sm_stmt = select(StockMovement).where(
        StockMovement.product_id == product_id,
        StockMovement.type == "out",
    )
    sm_result = await db_session.execute(sm_stmt)
    movements = sm_result.scalars().all()
    assert len(movements) == 0, "StockMovement yozilmagan bo'lishi kerak (rollback)"

    # ledger_entry YO'Q
    le_stmt = select(LedgerEntry).where(LedgerEntry.store_id == store_id)
    le_result = await db_session.execute(le_stmt)
    entries = le_result.scalars().all()
    assert len(entries) == 0, "LedgerEntry yozilmagan bo'lishi kerak (rollback)"


# ─── 3. total_amount to'g'ri Decimal hisobi ──────────────────────────────────


@pytest.mark.asyncio
async def test_total_amount_decimal_calculation(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """total_amount qatorlardan to'g'ri Decimal bilan hisoblanadi (server narxi)."""
    segment = await make_price_segment()
    prod1 = await make_product(price=Decimal("1500.00"), segment_id=segment.id, sku="P1")
    prod2 = await make_product(price=Decimal("2000.00"), segment_id=segment.id, sku="P2")
    store = await make_store(segment_id=segment.id)
    await seed_stock(prod1.id, qty=Decimal("100"))
    await seed_stock(prod2.id, qty=Decimal("100"))
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="bozor",
        lines=[
            OrderLineIn(product_id=prod1.id, qty=Decimal("2")),
            OrderLineIn(product_id=prod2.id, qty=Decimal("3")),
        ],
    )

    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # line1: 1500 * 2 = 3000 (discount yo'q — server tomonida 0)
    # line2: 2000 * 3 = 6000
    # total = 9000
    assert order.total_amount == Decimal("9000.00")


# ─── 4. Narx manipulyatsiyasi yopilgani ──────────────────────────────────────


@pytest.mark.asyncio
async def test_price_manipulation_unit_price_ignored(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    CRITICAL: unit_price schema darajasida yo'q — klient narx bera olmaydi.
    Total server narxidan (1000.00 * 2 = 2000.00) hisoblanadi.
    """
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("100"),
    )
    await db_session.commit()

    # Klient unit_price yubora olmaydi — schema darajasida qabul qilinmaydi
    # OrderLineIn faqat product_id + qty qabul qiladi
    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("2"))],
    )

    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Server narxi: 1000.00 * 2 = 2000.00 (klient narxi emas)
    assert order.total_amount == Decimal("2000.00")
    assert order.lines[0].unit_price == Decimal("1000.00")
    assert order.lines[0].discount == Decimal("0.00")


@pytest.mark.asyncio
async def test_price_manipulation_schema_rejects_unit_price() -> None:
    """unit_price va discount schema darajasida qabul qilinmaydi (extra field)."""
    from pydantic import ValidationError

    # OrderLineIn faqat product_id + qty oladi; extra field → ValidationError
    try:
        line = OrderLineIn(
            product_id=uuid.uuid4(),
            qty=Decimal("1"),
            unit_price=Decimal("999.00"),  # type: ignore[call-arg]
        )
        # Agar Pydantic extra='ignore' bo'lsa — unit_price e'tiborsiz qolinadi
        # Agar extra='forbid' bo'lsa — ValidationError
        # Har ikkala holda ham unit_price OrderLineIn da mavjud emas
        assert not hasattr(line, "unit_price"), (
            "unit_price OrderLineIn da bo'lmasligi kerak (narx manipulyatsiyasi himoyasi)"
        )
    except (ValidationError, TypeError):
        pass  # Extra field rejected — to'g'ri


@pytest.mark.asyncio
async def test_price_manipulation_segment_from_store(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    HIGH: segment do'kondan (Store.segment_id) olinadi, klientdan emas.
    Do'kon segmenti narxi ishlatiladi.
    """
    segment = await make_price_segment("VIP")
    product = await make_product(price=Decimal("5000.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Do'kon VIP segmenti narxi (5000.00) ishlatildi
    assert order.total_amount == Decimal("5000.00")
    assert order.lines[0].unit_price == Decimal("5000.00")
    assert order.lines[0].segment_id == segment.id


@pytest.mark.asyncio
async def test_price_manipulation_no_segment_raises_no_price(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    HIGH: Do'konda segment_id yo'q → orders.no_price 422 (deterministik).
    Fallback narx yo'q.
    """
    from app.core.errors import AppError

    # Do'konda segment yo'q
    product = await make_product(price=Decimal("1000.00"))
    store = await make_store()  # segment_id=None
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    assert exc_info.value.message_key == "orders.no_price"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_price_manipulation_wrong_segment_raises_no_price(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    HIGH: Do'kon segmenti mahsulot narxida yo'q → orders.no_price 422.
    Boshqa segment narxi ishlatilmaydi — deterministik.
    """
    from app.core.errors import AppError

    seg_a = await make_price_segment("A")
    seg_b = await make_price_segment("B")
    # Mahsulot narxi faqat seg_a da
    product = await make_product(price=Decimal("1000.00"), segment_id=seg_a.id)
    # Do'kon seg_b ga biriktirilgan
    store = await make_store(segment_id=seg_b.id)
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    assert exc_info.value.message_key == "orders.no_price"
    assert exc_info.value.status_code == 422


# ─── 5. Idempotentlik: client_uuid → bir order ───────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_client_uuid(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """Bir xil client_uuid bilan ikki marta so'rov → bitta order qaytadi."""
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("100"),
    )
    await db_session.commit()

    client_uuid = uuid.uuid4()
    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=client_uuid,
    )

    # Birinchi so'rov
    order1 = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Ikkinchi so'rov (bir xil client_uuid)
    order2 = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    assert order1.id == order2.id, "Bir xil client_uuid → bitta order bo'lishi kerak"

    # DB da bitta order
    order_stmt = select(Order).where(Order.store_id == store.id)
    result = await db_session.execute(order_stmt)
    orders = result.scalars().all()
    assert len(orders) == 1


# ─── 6. Holat mashinasi — qonuniy o'tishlar ──────────────────────────────────


@pytest.mark.asyncio
async def test_state_machine_valid_transitions(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """Qonuniy o'tishlar: confirmed → packed → delivering → delivered."""
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    assert order.status == "confirmed"
    assert order.version == 1

    # confirmed → packed
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="packed", version=1),
    )
    await db_session.commit()
    assert order.status == "packed"
    assert order.version == 2

    # packed → delivering
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="delivering", version=2),
    )
    await db_session.commit()
    assert order.status == "delivering"

    # delivering → delivered
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="delivered", version=3),
    )
    await db_session.commit()
    assert order.status == "delivered"


@pytest.mark.asyncio
async def test_state_machine_cancel_from_any_non_terminal(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """Confirmed → canceled qonuniy."""
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="canceled", version=1),
    )
    await db_session.commit()
    assert order.status == "canceled"


# ─── 7. KOMPENSATSIYA testlari ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compensation_confirmed_to_canceled(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    KOMPENSATSIYA: confirmed → canceled
    - stock qaytadi (type=in movement)
    - ledger credit yoziladi
    - balans 0 ga qaytadi
    """
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("10"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("3"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Yaratishdan keyin qoldiq: 10 - 3 = 7
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    bal_after_create = sb_result.scalar_one()
    assert bal_after_create.qty_on_hand == Decimal("7")

    # AccountBalance: 3000 debit
    acct_stmt = select(AccountBalance).where(AccountBalance.store_id == store.id)
    acct_result = await db_session.execute(acct_stmt)
    acct_after_create = acct_result.scalar_one()
    assert acct_after_create.balance == Decimal("3000.00")

    # confirmed → canceled (kompensatsiya)
    await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="canceled", version=1),
    )
    await db_session.commit()

    # Stock qaytdi: 7 + 3 = 10
    sb_result2 = await db_session.execute(sb_stmt)
    bal_after_cancel = sb_result2.scalar_one()
    assert bal_after_cancel.qty_on_hand == Decimal("10"), (
        "Ombor qoldig'i canceled da qaytishi kerak"
    )

    # Ledger credit yozildi
    credit_stmt = select(LedgerEntry).where(
        LedgerEntry.ref_id == order.id,
        LedgerEntry.type == "credit",
    )
    cr_result = await db_session.execute(credit_stmt)
    credits = cr_result.scalars().all()
    assert len(credits) == 1, "Credit yozuvi bo'lishi kerak"
    assert credits[0].amount == Decimal("3000.00")

    # AccountBalance: 3000 - 3000 = 0
    acct_result2 = await db_session.execute(acct_stmt)
    acct_after_cancel = acct_result2.scalar_one()
    assert acct_after_cancel.balance == Decimal("0.00"), (
        "Account balans canceled da 0 ga qaytishi kerak"
    )

    # StockMovement: in harakat yozildi
    in_stmt = select(StockMovement).where(
        StockMovement.ref_id == order.id,
        StockMovement.type == "in",
    )
    in_result = await db_session.execute(in_stmt)
    in_movements = in_result.scalars().all()
    assert len(in_movements) == 1, "Qaytim StockMovement yozilishi kerak"
    assert in_movements[0].qty == Decimal("3")


@pytest.mark.asyncio
async def test_compensation_packed_to_canceled(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """KOMPENSATSIYA: packed → canceled — qaytim bajariladi."""
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("500.00"), qty=Decimal("5"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("2"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # confirmed → packed
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="packed", version=1),
    )
    await db_session.commit()

    # packed → canceled (kompensatsiya)
    await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="canceled", version=2),
    )
    await db_session.commit()

    # Qoldiq qaytdi: 5 - 2 + 2 = 5
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    bal = sb_result.scalar_one()
    assert bal.qty_on_hand == Decimal("5"), "packed → canceled da stock qaytishi kerak"


@pytest.mark.asyncio
async def test_compensation_delivering_to_canceled(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """KOMPENSATSIYA: delivering → canceled — qaytim bajariladi."""
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("200.00"), qty=Decimal("10"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("4"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # confirmed → packed → delivering
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="packed", version=1),
    )
    await db_session.commit()
    order = await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="delivering", version=2),
    )
    await db_session.commit()

    # delivering → canceled
    await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="canceled", version=3),
    )
    await db_session.commit()

    # Qoldiq qaytdi: 10 - 4 + 4 = 10
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    bal = sb_result.scalar_one()
    assert bal.qty_on_hand == Decimal("10"), "delivering → canceled da stock qaytishi kerak"

    # Balans 0 ga qaytdi
    acct_stmt = select(AccountBalance).where(AccountBalance.store_id == store.id)
    acct_result = await db_session.execute(acct_stmt)
    acct = acct_result.scalar_one()
    assert acct.balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_compensation_delivered_no_rollback(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """delivered terminal holat — canceled ga o'tish mumkin emas (kompensatsiya ham yo'q)."""
    from app.core.errors import AppError

    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="packed", version=1))
    await db_session.commit()
    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="delivering", version=2))
    await db_session.commit()
    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="delivered", version=3))
    await db_session.commit()

    # delivered → canceled → noqonuniy (terminal)
    with pytest.raises(AppError) as exc_info:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="canceled", version=4),
        )
    assert exc_info.value.message_key == "orders.invalid_transition"


# ─── 8. Holat mashinasi — noqonuniy o'tish ───────────────────────────────────


@pytest.mark.asyncio
async def test_state_machine_invalid_transition(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """Noqonuniy o'tish → AppError invalid_transition 422."""
    from app.core.errors import AppError

    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # confirmed → delivering (packing ni o'tkazib ketish — noqonuniy)
    with pytest.raises(AppError) as exc_info:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="delivering", version=1),
        )
    assert exc_info.value.message_key == "orders.invalid_transition"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_state_machine_delivered_is_terminal(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """delivered → istalgan holat → noqonuniy (terminal holat)."""
    from app.core.errors import AppError

    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="packed", version=1))
    await db_session.commit()
    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="delivering", version=2))
    await db_session.commit()
    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="delivered", version=3))
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="canceled", version=4),
        )
    assert exc_info.value.message_key == "orders.invalid_transition"

    with pytest.raises(AppError) as exc_info2:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="draft", version=4),
        )
    assert exc_info2.value.message_key == "orders.invalid_transition"


@pytest.mark.asyncio
async def test_state_machine_canceled_is_terminal(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """canceled → istalgan holat → noqonuniy."""
    from app.core.errors import AppError

    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    order = await service.update_status(db_session, order.id, OrderStatusUpdate(status="canceled", version=1))
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="confirmed", version=2),
        )
    assert exc_info.value.message_key == "orders.invalid_transition"


# ─── 9. Version optimistik lock ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """Noto'g'ri version → AppError version_conflict 409."""
    from app.core.errors import AppError

    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await service.update_status(
            db_session, order.id, OrderStatusUpdate(status="packed", version=99),
        )
    assert exc_info.value.message_key == "orders.version_conflict"
    assert exc_info.value.status_code == 409


# ─── 10. RBAC/scope testlari ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rbac_agent_own_store_visible(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    seed_stock,
) -> None:
    """Agent o'z do'koni buyurtmasini ko'radi."""
    agent = await make_user("agent")
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("100"),
        store_kwargs={"agent_id": agent.id},
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="bozor",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=agent.id, user=agent, redis=fake_redis)
    await db_session.commit()

    fetched = await service.get_order(db_session, order.id, user=agent)
    assert fetched.id == order.id


@pytest.mark.asyncio
async def test_rbac_agent_other_store_invisible(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    admin_user,
    seed_stock,
) -> None:
    """Agent boshqa do'kon buyurtmasini ko'ra olmaydi → 404."""
    from app.core.errors import AppError

    agent = await make_user("agent")
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"), qty=Decimal("100"),
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await service.get_order(db_session, order.id, user=agent)
    assert exc_info.value.message_key == "orders.order_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_rbac_store_user_own_order_visible(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    seed_stock,
) -> None:
    """Do'kon roli o'z do'koni buyurtmasini ko'radi."""
    store_user = await make_user("store")
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("1000.00"), qty=Decimal("100"),
        store_kwargs={"user_id": store_user.id},
    )
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=store_user.id, redis=fake_redis)
    await db_session.commit()

    fetched = await service.get_order(db_session, order.id, user=store_user)
    assert fetched.id == order.id


@pytest.mark.asyncio
async def test_rbac_admin_all_orders(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    make_user,
    seed_stock,
) -> None:
    """Administrator barcha do'konlar buyurtmalarini ko'radi."""
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store1 = await make_store(segment_id=segment.id)
    store2 = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    for s in [store1, store2]:
        data = OrderCreate(
            store_id=s.id,
            mode="oddiy",
            lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        )
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    orders, total = await service.list_orders(db_session, user=admin_user)
    assert total == 2


# ─── 11. Bo'sh lines → xato ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_lines_raises_error(
    db_session: AsyncSession,
    fake_redis,
    make_store,
    admin_user,
) -> None:
    """Bo'sh lines → Pydantic validatsiya xatosi."""
    from pydantic import ValidationError

    store = await make_store()
    await db_session.commit()

    with pytest.raises(ValidationError):
        OrderCreate(
            store_id=store.id,
            mode="oddiy",
            lines=[],
        )


# ─── 12. Noma'lum product → 404 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_product_raises_404(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_store,
    admin_user,
) -> None:
    """Mavjud bo'lmagan mahsulot → AppError 404."""
    from app.core.errors import AppError

    segment = await make_price_segment()
    store = await make_store(segment_id=segment.id)
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(
            product_id=uuid.uuid4(),  # mavjud emas
            qty=Decimal("1"),
        )],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    assert exc_info.value.status_code == 404


# ─── 13. Noma'lum store → 404 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_store_raises_404(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    admin_user,
) -> None:
    """Mavjud bo'lmagan do'kon → AppError 404."""
    from app.core.errors import AppError

    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    await db_session.commit()

    data = OrderCreate(
        store_id=uuid.uuid4(),  # mavjud emas
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    assert exc_info.value.status_code == 404


# ─── 14. i18n: uz/ru xabarlar ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_i18n_uz_message(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """insufficient_stock xabari o'zbek tilida."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    # Stock qo'shilmagan — qoldiq nol

    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "5"}],
    }
    resp = await orders_client.post(
        "/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "uz"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "mavjud" in data["message"].lower() or "qoldiq" in data["message"].lower()


@pytest.mark.asyncio
async def test_i18n_ru_message(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
) -> None:
    """insufficient_stock xabari rus tilida."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)

    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "5"}],
    }
    resp = await orders_client.post(
        "/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Accept-Language": "ru"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "остаток" in data["message"].lower() or "доступно" in data["message"].lower()


# ─── 15. HTTP endpoint testlari ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_create_order_success(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """POST /orders → 201 muvaffaqiyatli buyurtma (server narxi)."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [
            {"product_id": str(product.id), "qty": "2"},
        ],
    }
    resp = await orders_client.post(
        "/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "confirmed"
    # Server narxi: 500.00 * 2 = 1000.00
    assert Decimal(data["total_amount"]) == Decimal("1000.00")
    assert len(data["lines"]) == 1
    # Klient narx bera olmaydi — unit_price server tomonida
    assert Decimal(data["lines"][0]["unit_price"]) == Decimal("500.00")
    assert Decimal(data["lines"][0]["discount"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_http_create_order_extra_fields_ignored(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    Klient unit_price/discount/segment_id yuborsa — server narxi ishlatiladi.
    Total server narxidan hisoblanadi (manipulyatsiya mumkin emas).
    """
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    # Klient "arzon" narx yuborishga urinadi
    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [
            {
                "product_id": str(product.id),
                "qty": "2",
                "unit_price": "1.00",      # manipulyatsiya urinishi
                "discount": "99999.00",    # manipulyatsiya urinishi
                "segment_id": str(uuid.uuid4()),  # manipulyatsiya urinishi
            },
        ],
    }
    resp = await orders_client.post(
        "/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # Server narxi ishlatildi: 500.00 * 2 = 1000.00 (klient 1.00 emas)
    assert Decimal(data["total_amount"]) == Decimal("1000.00"), (
        "Klient narxi (unit_price=1.00) e'tiborga olinmasligi kerak — server narxi 500.00"
    )


@pytest.mark.asyncio
async def test_http_get_order_not_found(
    orders_client: AsyncClient,
    admin_user,
) -> None:
    """GET /orders/{id} — mavjud bo'lmagan ID → 404."""
    token = await get_token(orders_client, admin_user)
    fake_id = uuid.uuid4()
    resp = await orders_client.get(
        f"/orders/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_http_get_orders_list(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """GET /orders → paginated ro'yxat."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    # 2 ta buyurtma yaratamiz
    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    await orders_client.post("/orders", json=body, headers={"Authorization": f"Bearer {token}"})
    await orders_client.post("/orders", json=body, headers={"Authorization": f"Bearer {token}"})

    resp = await orders_client.get("/orders", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_http_update_status_invalid_transition(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """PATCH /orders/{id}/status — noqonuniy o'tish → 422."""
    token = await get_token(orders_client, admin_user)
    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    create_body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    create_resp = await orders_client.post(
        "/orders",
        json=create_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201, create_resp.text
    order_id = create_resp.json()["id"]
    version = create_resp.json()["version"]

    patch_resp = await orders_client.patch(
        f"/orders/{order_id}/status",
        json={"status": "delivered", "version": version},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["message_key"] == "orders.invalid_transition"


@pytest.mark.asyncio
async def test_http_accountant_patch_status_forbidden(
    orders_client: AsyncClient,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    accountant_user,
    seed_stock,
) -> None:
    """Buxgalter (accountant) PATCH /orders/{id}/status → 403."""
    admin_token = await get_token(orders_client, admin_user)
    accountant_token = await get_token(orders_client, accountant_user)

    segment = await make_price_segment()
    product = await make_product(price=Decimal("100.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("50"))

    # Admin buyurtma yaratadi
    create_body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    create_resp = await orders_client.post(
        "/orders",
        json=create_body,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    order_id = create_resp.json()["id"]
    version = create_resp.json()["version"]

    # Buxgalter holat o'zgartirishga urinadi → 403
    patch_resp = await orders_client.patch(
        f"/orders/{order_id}/status",
        json={"status": "packed", "version": version},
        headers={"Authorization": f"Bearer {accountant_token}"},
    )
    assert patch_resp.status_code == 403, (
        "Buxgalter orders:edit ruxsatiga ega emas — 403 bo'lishi kerak"
    )


@pytest.mark.asyncio
async def test_http_rbac_forbidden_create(
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
    await seed_stock(product.id, qty=Decimal("50"))

    body = {
        "store_id": str(store.id),
        "mode": "oddiy",
        "lines": [{"product_id": str(product.id), "qty": "1"}],
    }
    resp = await orders_client.post(
        "/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_http_unauthenticated(
    orders_client: AsyncClient,
) -> None:
    """Token yo'q → 401."""
    resp = await orders_client.get("/orders")
    assert resp.status_code == 401


# ─── 16. AgentStore orqali biriktirish ───────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_store_via_agent_store_table(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    seed_stock,
) -> None:
    """Agent AgentStore jadval orqali biriktirilgan do'kon buyurtmasini ko'radi."""
    agent = await make_user("agent")
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("100.00"), qty=Decimal("100"),
    )

    # AgentStore orqali biriktirish
    agent_store = AgentStore(agent_id=agent.id, store_id=store.id)
    db_session.add(agent_store)
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="bozor",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
    )
    order = await service.create_order(db_session, data, actor_id=agent.id, user=agent, redis=fake_redis)
    await db_session.commit()

    fetched = await service.get_order(db_session, order.id, user=agent)
    assert fetched.id == order.id


# ─── 17. Multi-line atomiklik: birinchi qator OK, ikkinchi yetmaydi ──────────


@pytest.mark.asyncio
async def test_multiline_atomicity_partial_stock_fails(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    Multi-line: birinchi mahsulot OK, ikkinchisi yetmaydi.
    Butun tranzaksiya rollback — birinchi mahsulot chiqimi ham YOZILMAYDI.
    StockMovement ham tekshiriladi (muhim invariant).
    """
    from app.core.errors import AppError

    segment = await make_price_segment()
    prod1 = await make_product(price=Decimal("100.00"), segment_id=segment.id, sku="MULTI1")
    prod2 = await make_product(price=Decimal("200.00"), segment_id=segment.id, sku="MULTI2")
    store = await make_store(segment_id=segment.id)
    await seed_stock(prod1.id, qty=Decimal("100"))    # yetarli
    await seed_stock(prod2.id, qty=Decimal("1"))     # yetmaydi (5 talab qilinadi)
    await db_session.commit()

    store_id = store.id
    prod1_id = prod1.id

    data = OrderCreate(
        store_id=store_id,
        mode="oddiy",
        lines=[
            OrderLineIn(product_id=prod1_id, qty=Decimal("2")),
            OrderLineIn(product_id=prod2.id, qty=Decimal("5")),  # yetmaydi
        ],
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    assert exc_info.value.message_key == "orders.insufficient_stock"

    await db_session.rollback()

    # Order ham yo'q
    order_stmt = select(Order).where(Order.store_id == store_id)
    order_result = await db_session.execute(order_stmt)
    orders = order_result.scalars().all()
    assert len(orders) == 0, "Order rollback qilinishi kerak"

    # StockMovement ham yo'q (atomiklik)
    sm_stmt = select(StockMovement).where(
        StockMovement.product_id == prod1_id,
        StockMovement.type == "out",
    )
    sm_result = await db_session.execute(sm_stmt)
    movements = sm_result.scalars().all()
    assert len(movements) == 0, "StockMovement rollback qilinishi kerak"


# ─── 18. IDEMPOTENTLIK REGRESSIYA: cross-store aralashuv YO'Q ────────────────


@pytest.mark.asyncio
async def test_idempotency_same_client_uuid_different_stores_creates_two_orders(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    REGRESSIYA: bir xil aktor + bir xil client_uuid → IKKI XIL do'kon.
    Natija: ikkita ALOHIDA buyurtma (cross-store aralashuv YO'Q).
    """
    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store1 = await make_store(segment_id=segment.id)
    store2 = await make_store(segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    shared_uuid = uuid.uuid4()

    data1 = OrderCreate(
        store_id=store1.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=shared_uuid,
    )
    data2 = OrderCreate(
        store_id=store2.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=shared_uuid,
    )

    order1 = await service.create_order(db_session, data1, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    order2 = await service.create_order(db_session, data2, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    assert order1.id != order2.id, (
        "Ikki xil do'kon → ikki alohida buyurtma bo'lishi kerak (cross-store aralashuv yo'q)"
    )
    assert order1.store_id == store1.id
    assert order2.store_id == store2.id

    # DB da ikkita buyurtma
    stmt = select(Order).where(Order.client_uuid == shared_uuid)
    result = await db_session.execute(stmt)
    all_orders = result.scalars().all()
    assert len(all_orders) == 2, "Ikki xil do'kon uchun ikkita buyurtma bo'lishi kerak"


@pytest.mark.asyncio
async def test_idempotency_same_store_same_client_uuid_returns_same_order(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    REGRESSIYA: bir do'kon + bir xil client_uuid takror so'rov → bir buyurtma qaytadi.
    Redis hit (birinchi qaytarish) va DB IntegrityError (ikkinchi qaytarish) ikkala yo'l tekshiriladi.
    """
    store, product, _ = await _make_seeded_store_and_product(
        make_price_segment, make_product, make_store, seed_stock,
        price=Decimal("500.00"), qty=Decimal("100"),
    )
    await db_session.commit()

    client_uuid = uuid.uuid4()
    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=client_uuid,
    )

    # Birinchi so'rov
    order1 = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # Ikkinchi so'rov — Redis hit orqali
    order2 = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)

    assert order1.id == order2.id, "Bir do'kon + bir xil client_uuid → bitta buyurtma"

    stmt = select(Order).where(
        Order.store_id == store.id,
        Order.client_uuid == client_uuid,
    )
    result = await db_session.execute(stmt)
    orders = result.scalars().all()
    assert len(orders) == 1, "DB da bitta buyurtma bo'lishi kerak"


@pytest.mark.asyncio
async def test_idempotency_different_actor_same_store_client_uuid_raises_409(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    make_user,
    seed_stock,
) -> None:
    """
    DoS himoyasi: boshqa aktor (agent) bir xil store+client_uuid → 409 idempotency_conflict.

    Ikkala agent ham bir xil do'konga AgentStore orqali biriktirilgan.
    agent role uchun order.agent_id = actor_id o'rnatiladi — shuning uchun
    ikki xil agent boshqa actor sifatida aniqlanadi (agent_id != actor_id → 409).
    """
    from app.core.errors import AppError

    agent1 = await make_user("agent")
    agent2 = await make_user("agent")

    segment = await make_price_segment()
    product = await make_product(price=Decimal("500.00"), segment_id=segment.id)
    # Do'kon agent1 ga biriktirilgan
    store = await make_store(segment_id=segment.id, agent_id=agent1.id)
    # agent2 ham shu do'konga AgentStore orqali qo'shiladi (ikkala agent kirish huquqiga ega)
    db_session.add(AgentStore(agent_id=agent2.id, store_id=store.id))
    await seed_stock(product.id, qty=Decimal("100"))
    await db_session.commit()

    client_uuid = uuid.uuid4()

    data1 = OrderCreate(
        store_id=store.id,
        mode="bozor",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=client_uuid,
    )
    # Birinchi agent yaratadi — order.agent_id = agent1.id
    order1 = await service.create_order(
        db_session, data1, actor_id=agent1.id, user=agent1, redis=fake_redis
    )
    await db_session.commit()
    assert order1 is not None
    assert order1.agent_id == agent1.id

    # Ikkinchi agent bir xil store+client_uuid → 409
    data2 = OrderCreate(
        store_id=store.id,
        mode="bozor",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("1"))],
        client_uuid=client_uuid,
    )
    with pytest.raises(AppError) as exc_info:
        # agent2 uchun Redis cache yo'q → DB IntegrityError yo'li
        await service.create_order(
            db_session, data2, actor_id=agent2.id, user=agent2, redis=fake_redis
        )

    assert exc_info.value.message_key == "orders.idempotency_conflict"
    assert exc_info.value.status_code == 409


# ─── 19. KOMPENSATSIYA: to'g'ri ombor (non-default warehouse) ────────────────


@pytest.mark.asyncio
async def test_compensation_uses_order_warehouse_id_not_default(
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    admin_user,
    seed_stock,
) -> None:
    """
    MEDIUM KOMPENSATSIYA: default bo'lmagan warehouse_id bilan yaratilgan buyurtma
    cancel bo'lganda AYNI omborga qaytadi (default ombor emas).
    """
    NON_DEFAULT_WAREHOUSE = uuid.UUID("bbbbbbbb-2222-0000-0000-000000000002")

    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store = await make_store(segment_id=segment.id)
    # Stock non-default omborga qo'shiladi
    await seed_stock(product.id, warehouse_id=NON_DEFAULT_WAREHOUSE, qty=Decimal("20"))
    await db_session.commit()

    data = OrderCreate(
        store_id=store.id,
        mode="oddiy",
        lines=[OrderLineIn(product_id=product.id, qty=Decimal("5"))],
        warehouse_id=NON_DEFAULT_WAREHOUSE,
    )
    order = await service.create_order(db_session, data, actor_id=admin_user.id, redis=fake_redis)
    await db_session.commit()

    # warehouse_id order ga saqlangan
    assert order.warehouse_id == NON_DEFAULT_WAREHOUSE

    # Non-default ombordan 5 ta chiqib ketganini tekshirish
    sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == NON_DEFAULT_WAREHOUSE,
    )
    sb_result = await db_session.execute(sb_stmt)
    bal_before_cancel = sb_result.scalar_one()
    assert bal_before_cancel.qty_on_hand == Decimal("15")  # 20 - 5

    # confirmed → canceled (kompensatsiya)
    await service.update_status(
        db_session, order.id, OrderStatusUpdate(status="canceled", version=1),
    )
    await db_session.commit()

    # Non-default omborga qaytganini tekshirish: 15 + 5 = 20
    sb_result2 = await db_session.execute(sb_stmt)
    bal_after_cancel = sb_result2.scalar_one()
    assert bal_after_cancel.qty_on_hand == Decimal("20"), (
        "Kompensatsiya AYNI omborga (non-default) qaytishi kerak"
    )

    # Default ombor ta'sirlanmaganini tekshirish
    default_sb_stmt = select(StockBalance).where(
        StockBalance.product_id == product.id,
        StockBalance.warehouse_id == DEFAULT_WAREHOUSE,
    )
    default_sb_result = await db_session.execute(default_sb_stmt)
    default_bal = default_sb_result.scalar_one_or_none()
    assert default_bal is None or default_bal.qty_on_hand == Decimal("0"), (
        "Default ombor ta'sirlanmagan bo'lishi kerak"
    )
