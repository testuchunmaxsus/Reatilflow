"""
#15 SAVEPOINT dizayni — REAL tranzaksiya chegarasi testi (TEST-GAP tuzatish).

MUAMMO: mavjud sync/contracts/catalog testlari get_db()'ni override qilib
raw db_session beradi va sessiyaning REAL session.commit()/rollback()'ini
HECH QACHON chaqirmaydi (fixture faqat test oxirida rollback qiladi).
SAVEPOINT dizayni ("muvaffaqiyat holatida SAVEPOINT ochiq qoldiriladi, keyingi
ROOT commit/rollback hal qiladi") ana shu REAL commit/rollback chegarasiga
tayanadi — lekin bu chegara avtomatik testda hech qachon sinalmagan edi.

Bu fayl sync push orqali [op1 applied, op2 IntegrityError-fail, op3 applied]
ssenariysini REAL db.commit() dan o'tkazadi, so'ng YANGI (tozalangan) sessiya
bilan qayta so'rov qilib op1/op3 SAQLANGANini va op2 YO'Qligini tasdiqlaydi.

order.create tanlangan sabab: Order.__table_args__ da
UniqueConstraint("store_id", "client_uuid") ORM darajasida e'lon qilingan
(migr emas) — shuning uchun aiosqlite test muhitida ham HAQIQIY IntegrityError
zanjiri (flush → IntegrityError → SAVEPOINT rollback) reproduktsiya qilinadi.
Katalog/shartnoma unique cheklovlari (uix_product_ent_sku, uq_contract_store_
number) faqat Alembic raw-SQL migratsiyada yaratiladi — Base.metadata.create_all()
bilan quriladigan aiosqlite test bazasida mavjud emas, shu sabab shu yerda
ishlatilmaydi.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.order import Order
from app.models.outbox import reset_seq_counter
from app.modules.sync import service as sync_service
from app.modules.sync.schemas import SyncOp


@pytest.fixture(autouse=True)
def _reset_outbox_seq():
    reset_seq_counter()
    yield
    reset_seq_counter()


async def _setup(make_price_segment, make_product, make_store, seed_stock, agent_user):
    """Segment + mahsulot + agentga tegishli do'kon + stock."""
    segment = await make_price_segment()
    product = await make_product(price=Decimal("1000.00"), segment_id=segment.id)
    store = await make_store(agent_id=agent_user.id, segment_id=segment.id)
    await seed_stock(product.id, qty=Decimal("100"))
    return store, product, segment


@pytest.mark.asyncio
async def test_savepoint_survives_real_commit_boundary(
    engine,
    db_session: AsyncSession,
    fake_redis,
    make_price_segment,
    make_product,
    make_store,
    seed_stock,
    agent_user,
    admin_user,
) -> None:
    """
    [op1 applied, op2 IntegrityError-fail, op3 applied] → REAL db.commit()
    dan o'tgach, YANGI sessiyada op1&op3 SAQLANGAN, op2 YO'Q ekanini tekshiradi.

    Bu test #15 SAVEPOINT dizayni (muvaffaqiyat holatida SAVEPOINT ochiq
    qoldiriladi, ROOT commit/rollback keyinroq hal qiladi) HAQIQIY sessiya
    commit() chegarasidan xavfsiz o'tishini isbotlaydi — mavjud test
    infratuzilmasi (get_db override, hech qachon commit() chaqirmaydi) buni
    tekshirmaydi.
    """
    store, product, _ = await _setup(
        make_price_segment, make_product, make_store, seed_stock, agent_user
    )

    op1_uuid = str(uuid.uuid4())
    op3_uuid = str(uuid.uuid4())

    op1 = SyncOp(
        op_type="order.create",
        client_uuid=op1_uuid,
        payload={
            "store_id": str(store.id),
            "lines": [{"product_id": str(product.id), "qty": "2"}],
            "mode": "bozor",
            "currency": "UZS",
        },
    )
    op3 = SyncOp(
        op_type="order.create",
        client_uuid=op3_uuid,
        payload={
            "store_id": str(store.id),
            "lines": [{"product_id": str(product.id), "qty": "3"}],
            "mode": "bozor",
            "currency": "UZS",
        },
    )

    # ── 1-chaqiruv: op1 va op3 — ikkalasi ham applied ────────────────────────
    results_1 = await sync_service.push(
        ops=[op1, op3],
        actor_id=agent_user.id,
        user=agent_user,
        db=db_session,
        redis=fake_redis,
    )
    assert len(results_1) == 2
    res1 = next(r for r in results_1 if r.client_uuid == op1_uuid)
    res3 = next(r for r in results_1 if r.client_uuid == op3_uuid)
    assert res1.status == "applied", res1
    assert res3.status == "applied", res3
    assert res1.server_id is not None
    assert res3.server_id is not None

    # ── 2-chaqiruv: op2 — bir xil (store_id, client_uuid)=op1, LEKIN boshqa
    # aktor (admin, agent_user emas) → create_order() ichida IntegrityError
    # ushlanadi (uq_order_store_client_uuid), o'z SAVEPOINT'i rollback qilinadi,
    # keyin mavjud buyurtma agent_id mos kelmagani uchun
    # "orders.idempotency_conflict" (409) qaytaradi — HAQIQIY IntegrityError
    # yo'li, oldindan tekshiruv (pre-check) emas.
    op2 = SyncOp(
        op_type="order.create",
        client_uuid=op1_uuid,  # op1 bilan bir xil client_uuid — dublikat
        payload={
            "store_id": str(store.id),
            "lines": [{"product_id": str(product.id), "qty": "5"}],
            "mode": "bozor",
            "currency": "UZS",
        },
    )
    results_2 = await sync_service.push(
        ops=[op2],
        actor_id=admin_user.id,
        user=admin_user,
        db=db_session,
        redis=fake_redis,
    )
    assert len(results_2) == 1
    res2 = results_2[0]
    assert res2.status == "conflict", res2
    assert res2.message_key == "orders.idempotency_conflict"

    # ── REAL tranzaksiya chegarasidan o'tish ────────────────────────────────
    # get_db() production'da shu yerda `await session.commit()` chaqiradi.
    # Test infratuzilmasi buni HECH QACHON chaqirmaydi — shu yerda ATAYLAB
    # qo'lda bajaramiz (MASALA 3 tuzatishi).
    await db_session.commit()

    # ── YANGI (tozalangan) sessiyada qayta so'rov ───────────────────────────
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as fresh_session:
        count_stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.store_id == store.id)
        )
        total = (await fresh_session.execute(count_stmt)).scalar_one()
        # Faqat op1 va op3 saqlangan — op2 (IntegrityError-fail) YO'Q.
        assert total == 2, f"Kutilgan 2 ta buyurtma, topilgan {total}"

        uuid_stmt = select(Order.client_uuid).where(Order.store_id == store.id)
        persisted_uuids = {
            str(u) for u in (await fresh_session.execute(uuid_stmt)).scalars().all()
        }
        assert persisted_uuids == {op1_uuid, op3_uuid}
