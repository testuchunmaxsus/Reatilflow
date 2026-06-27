"""
Sync servis qatlami — T13 Outbox Sync API.

push(ops, actor_id, user, db, redis):
  Har op uchun mos modul servisiga dispatch qiladi.
  Op-darajali xato izolyatsiyasi: bitta op xato bo'lsa qolganlar davom etadi.
  Har op db.begin_nested() (SAVEPOINT) ichida bajariladi — bitta op rollback
  bo'lsa sessiya ifloslanmaydi, qolgan op'lar toza sessiyada davom etadi.
  client_uuid idempotentlik: applied→server_id; duplicate; conflict; error+message_key.
  Batch limit: settings.sync_max_batch (default: 100) — oshsa AppError("sync.batch_too_large").

pull(since_seq, limit, user, db):
  OutboxEvent'dan seq > since_seq hodisalar, foydalanuvchi scope'ida.
  Scope filtr (IDOR):
    - order/store → faqat user_store_ids do'konlariga tegishli hodisalar.
    - product/price/promo/catalog → global read-only, hammaga.
    - boshqa aggregate_type → admin/accountant ko'radi; agent/store ko'rmaydi.
  Har hodisaga joriy entity snapshot qo'shiladi (klient upsert uchun).
  Snapshot'lar aggregate_type bo'yicha batch fetch bilan olinadi (N+1 yo'q).
  next_cursor = SKANERLANGAN oxirgi hodisa seq'i (changes bo'sh bo'lsa ham ilgarilaydi).
  has_more = skanerlangan hodisa soni limit'ga yetganda.

KURSOR MEXANIZMI (server-avtoritar monoton):
  seq — Postgres DB SEQUENCE / SQLite AUTOINCREMENT — klient soatiga ishonmaslik (ADR §3.5).
  created_at wall-clock ISHLATILMAYDI.

OP REGISTRY:
  op_type → handler funksiyasi xaritasi.
  Yangi op turlari uchun kengaytiriladigan dict.

MODUL CHEGARASI:
  sync modul boshqa modul servislarini interfeys orqali chaqiradi.
  To'g'ridan-to'g'ri DB jadvallariga yozilmaydi.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.catalog import Product, ProductPrice
from app.models.finance import AccountBalance
from app.models.order import Order
from app.models.outbox import OutboxEvent
from app.models.store import Store
from app.models.user import AppUser
from app.modules.orders.schemas import OrderCreate, OrderLineIn
from app.modules.orders.service import create_order
from app.modules.rbac.enterprise_scope import apply_enterprise_filter, get_current_enterprise_id
from app.modules.rbac.scope import get_user_store_ids
from app.modules.sync.schemas import ChangeItem, OpResult, SyncOp

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

# Katalog/global aggregate_type'lar — hammaga read-only
_GLOBAL_AGGREGATE_TYPES = frozenset({
    "product",
    "product_price",
    "price",
    "promo",
    "category",
    "price_segment",
    "catalog",
})

# Do'kon/buyurtma aggregate_type'lar — scope filtr kerak
_SCOPED_AGGREGATE_TYPES = frozenset({
    "order",
    "store",
    "order_template",
    "attendance",  # T16: davomat — foydalanuvchi o'z yozuvlarini ko'radi
})


# ─── Op handler'lar ───────────────────────────────────────────────────────────


async def _handle_order_create(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """
    "order.create" operatsiyasini qayta ishlaydi.

    Mavjud create_order() servisini QAYTA ISHLATADI — atomiklik, narx xavfsizligi,
    idempotentlik va RBAC scope create_order() ichida ta'minlangan.
    enterprise_id — server-avtoritar korxona scope (cross-tenant teshigi yo'q).

    payload kutilgan maydonlar:
      store_id   — do'kon UUID (string)
      lines      — [{product_id, qty}] ro'yxati
      mode       — "bozor" | "oddiy" (ixtiyoriy, default "bozor")
      currency   — "UZS" (ixtiyoriy, default "UZS")
    """
    payload = op.payload
    try:
        store_id = uuid.UUID(payload["store_id"])
        raw_lines = payload.get("lines", [])
        lines = [
            OrderLineIn(
                product_id=uuid.UUID(line["product_id"]),
                qty=line["qty"],
            )
            for line in raw_lines
        ]
        order_data = OrderCreate(
            store_id=store_id,
            mode=payload.get("mode", "bozor"),
            lines=lines,
            client_uuid=op.client_uuid,
            currency=payload.get("currency", "UZS"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("order.create payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        order = await create_order(
            db=db,
            data=order_data,
            actor_id=actor_id,
            user=user,
            redis=redis,
            enterprise_id=enterprise_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(order.id),
        )
    except AppError as exc:
        # client_uuid takror (same store+uuid) — mavjud order qaytariladi
        # create_order() mavjud orderni qaytaradi → "applied" sifatida
        # Lekin agar boshqa aktor o'sha uuid ni ishlatgan bo'lsa → conflict
        if exc.message_key == "orders.idempotency_conflict":
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        # Boshqa AppError → moslik + xato
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_attendance_check_in(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"attendance.check_in" — mobil ilova outbox orqali yuborgan kirish operatsiyasi.

    Mobil payload: {biometric_verified, gps_lat, gps_lng, source, client_uuid}.
    attendance.service.check_in() QAYTA ISHLATILADI — biometric tekshiruvi,
    idempotentlik (client_uuid), server vaqti, audit+outbox shu yerda.

    server_id = attendance.id (UUID).
    """
    from app.modules.attendance import service as attendance_service
    from app.modules.attendance.schemas import CheckInRequest

    try:
        data = CheckInRequest.model_validate(op.payload)
        # client_uuid op.client_uuid dan ham olinishi mumkin (payload'da bo'lmasa)
        if data.client_uuid is None and op.client_uuid is not None:
            try:
                data = CheckInRequest.model_validate(
                    {**op.payload, "client_uuid": op.client_uuid}
                )
            except Exception:
                pass
    except Exception as exc:
        logger.debug("attendance.check_in payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        attendance = await attendance_service.check_in(
            user=user,
            data=data,
            db=db,
            redis=redis,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(attendance.id),
        )
    except AppError as exc:
        if exc.message_key in ("attendance.already_checked_in",):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_attendance_check_out(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"attendance.check_out" — mobil ilova outbox orqali yuborgan chiqish operatsiyasi.

    Mobil payload: {gps_lat, gps_lng, client_uuid}.
    attendance.service.check_out() QAYTA ISHLATILADI — ochiq davomat topish,
    server vaqti, idempotentlik, audit+outbox shu yerda.

    server_id = attendance.id (UUID).
    """
    from app.modules.attendance import service as attendance_service
    from app.modules.attendance.schemas import CheckOutRequest

    try:
        data = CheckOutRequest.model_validate(op.payload)
        if data.client_uuid is None and op.client_uuid is not None:
            try:
                data = CheckOutRequest.model_validate(
                    {**op.payload, "client_uuid": op.client_uuid}
                )
            except Exception:
                pass
    except Exception as exc:
        logger.debug("attendance.check_out payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        attendance = await attendance_service.check_out(
            user=user,
            data=data,
            db=db,
            redis=redis,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(attendance.id),
        )
    except AppError as exc:
        if exc.message_key in ("attendance.not_checked_in",):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_delivery_status_update(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"delivery.status_update" — mobil ilova outbox orqali yuborgan yetkazish holat yangilanishi.

    Mobil payload (delivery_repository.dart ~152-158):
      {delivery_id, status, version, gps_lat?, gps_lng?, failure_reason?}.
    delivery.service.update_status() QAYTA ISHLATILADI — holat mashinasi,
    IDOR (kuryer faqat o'zining yetkazishi), optimistik lock, audit+outbox shu yerda.

    server_id = delivery.id (UUID).
    """
    from app.modules.delivery import service as delivery_service
    from app.modules.delivery.schemas import DeliveryStatusUpdate

    payload = op.payload
    try:
        delivery_id = uuid.UUID(payload["delivery_id"])
        data = DeliveryStatusUpdate.model_validate({
            "status": payload["status"],
            "version": payload["version"],
            "gps_lat": payload.get("gps_lat"),
            "gps_lng": payload.get("gps_lng"),
            "failure_reason": payload.get("failure_reason"),
        })
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("delivery.status_update payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        delivery = await delivery_service.update_status(
            db=db,
            delivery_id=delivery_id,
            data=data,
            user=user,
            enterprise_id=enterprise_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(delivery.id),
        )
    except AppError as exc:
        if exc.message_key in ("orders.version_conflict", "delivery.invalid_transition"):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_store_update(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"store.update" — mobil ilova outbox orqali yuborgan do'kon yangilash.

    Mobil payload (store_repository.dart ~97-107):
      {store_id, version, name?, owner_name?, phone?, address?, gps_lat?, gps_lng?}.
    customers.service.update_store() QAYTA ISHLATILADI — optimistik lock,
    IDOR (scope filtri), audit+outbox shu yerda.

    server_id = store.id (UUID).
    """
    from app.modules.customers import service as customers_service
    from app.modules.customers.schemas import StoreUpdate

    payload = op.payload
    try:
        store_id = uuid.UUID(payload["store_id"])
        version = int(payload["version"])
        update_fields: dict[str, Any] = {"version": version}
        for field in ("name", "owner_name", "phone", "address", "gps_lat", "gps_lng"):
            if field in payload and payload[field] is not None:
                update_fields[field] = payload[field]
        data = StoreUpdate.model_validate(update_fields)
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("store.update payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        store = await customers_service.update_store(
            db=db,
            store_id=store_id,
            data=data,
            actor_id=actor_id,
            user=user,
            enterprise_id=enterprise_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(store.id),
        )
    except AppError as exc:
        if exc.message_key in ("customers.version_conflict",):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_store_assign_agent(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"store.assign_agent" — mobil ilova outbox orqali yuborgan agent biriktirish.

    Mobil payload (store_repository.dart ~150-157):
      {store_id, agent_id}.
    customers.service.assign_agent() QAYTA ISHLATILADI — agent mavjudligi,
    enterprise tekshiruvi, idempotent (allaqachon biriktirilgan → mavjudni qaytaradi),
    audit+outbox shu yerda.

    server_id = store.id (UUID).
    """
    from app.modules.customers import service as customers_service

    payload = op.payload
    try:
        store_id = uuid.UUID(payload["store_id"])
        agent_id = uuid.UUID(payload["agent_id"])
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("store.assign_agent payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        await customers_service.assign_agent(
            db=db,
            store_id=store_id,
            agent_id=agent_id,
            actor_id=actor_id,
            user=user,
            enterprise_id=enterprise_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(store_id),
        )
    except AppError as exc:
        if exc.message_key in ("customers.store_not_found", "customers.agent_not_found"):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_contract_create(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"contract.create" — mobil ilova outbox orqali yuborgan shartnoma yaratish.

    Mobil payload (contract_repository.dart ~34-38 + contract_models.dart ~106-113):
      {client_uuid, store_id, number, valid_from, valid_to}.
    supplier_enterprise_id SERVER-AVTORITAR: user.enterprise_id dan olinadi.
    contracts.service.create_contract() QAYTA ISHLATILADI — (store_id, number)
    unikalligi, Redis idempotentlik (client_uuid), scope (agent o'z do'konlari),
    audit+outbox shu yerda.

    server_id = contract.id (UUID).
    """
    from app.modules.contracts import service as contracts_service
    from app.modules.contracts.schemas import ContractCreate

    payload = op.payload
    try:
        # client_uuid: op.client_uuid yoki payload'dan
        client_uuid_val = op.client_uuid
        if client_uuid_val is None and "client_uuid" in payload:
            try:
                client_uuid_val = str(uuid.UUID(payload["client_uuid"]))
            except (ValueError, TypeError):
                pass

        data = ContractCreate.model_validate({
            "store_id": payload["store_id"],
            "number": payload["number"],
            "valid_from": payload["valid_from"],
            "valid_to": payload["valid_to"],
            "client_uuid": client_uuid_val,
        })
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("contract.create payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        contract = await contracts_service.create_contract(
            db=db,
            data=data,
            actor_id=actor_id,
            user=user,
            redis=redis,
            enterprise_id=enterprise_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(contract.id),
        )
    except AppError as exc:
        if exc.message_key in ("contracts.duplicate_number",):
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_marketplace_order_create(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"marketplace_order.create" — mobil ilova outbox orqali yuborgan marketplace buyurtma.

    Mobil payload (onetime_order_providers.dart ~57-64):
      {client_uuid, product_id, qty, store_id, is_onetime}.
    marketplace.service.create_order() QAYTA ISHLATILADI — Shartnoma-Gate
    (activ shartnoma → is_onetime=False; agent bypass → is_onetime=True; yo'q → 409),
    server-avtoritar narx, idempotentlik (client_uuid), audit+outbox shu yerda.

    Shartnoma-Gate 409 → OpResult status="conflict" + message_key="marketplace.contract_required".
    server_id = marketplace_order.id (UUID).
    """
    from decimal import Decimal as _Decimal
    from app.modules.marketplace import service as marketplace_service
    from app.modules.marketplace.service import OrderLineInput

    payload = op.payload
    try:
        product_id = uuid.UUID(payload["product_id"])
        qty = _Decimal(str(payload["qty"]))
        store_id = uuid.UUID(payload["store_id"])
        # client_uuid: op.client_uuid yoki payload'dan
        client_uuid_val: uuid.UUID | None = None
        if op.client_uuid is not None:
            try:
                client_uuid_val = uuid.UUID(op.client_uuid)
            except (ValueError, TypeError):
                pass
        if client_uuid_val is None and "client_uuid" in payload:
            try:
                client_uuid_val = uuid.UUID(str(payload["client_uuid"]))
            except (ValueError, TypeError):
                pass
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("marketplace_order.create payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        order = await marketplace_service.create_order(
            db=db,
            buyer_user=user,
            lines=[OrderLineInput(product_id=product_id, qty=qty)],
            client_uuid=client_uuid_val,
            buyer_store_id=store_id,
        )
        return OpResult(
            client_uuid=op.client_uuid,
            status="applied",
            server_id=str(order.id),
        )
    except AppError as exc:
        if exc.message_key == "marketplace.contract_required":
            return OpResult(
                client_uuid=op.client_uuid,
                status="conflict",
                message_key=exc.message_key,
            )
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


async def _handle_gps_ingest(
    op: SyncOp,
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> OpResult:
    """"gps.ingest" — mobil ilova outbox orqali yuborgan GPS nuqtalari.

    Mobil ilova check-in'dan keyin davriy joylashuvni outbox 'gps.ingest' op sifatida
    yuboradi (payload: {points: [{lat, lng, recorded_at, speed?, delivery_id?}]}).
    Bu handler gps modulining ingest() servisini QAYTA ISHLATADI — ish-soati filtri
    (aktiv attendance) + idempotentlik (user_id, recorded_at UNIQUE) shu yerda.

    db — asosiy OLTP session: gps_point 0011/0029 da asosiy bazada (timescale_url
    DATABASE_URL'ga fallback), attendance ham shu yerda → oltp_db=db.
    """
    from app.modules.gps import service as gps_service
    from app.modules.gps.schemas import GpsBatchIngest

    try:
        batch = GpsBatchIngest.model_validate(op.payload)
    except Exception as exc:  # noqa: BLE001 — payload validatsiyasi
        logger.debug("gps.ingest payload xatosi: %r", exc)
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key="common.validation_error",
        )

    try:
        await gps_service.ingest(user=user, batch=batch, db=db, oltp_db=db)
        return OpResult(client_uuid=op.client_uuid, status="applied")
    except AppError as exc:
        return OpResult(
            client_uuid=op.client_uuid,
            status="error",
            message_key=exc.message_key,
        )


# ─── Op registry ─────────────────────────────────────────────────────────────

# Kengaytiriladigan registry: yangi op turi uchun handler qo'shing
_OP_REGISTRY: dict[
    str,
    Any  # (op, actor_id, user, db, redis) -> OpResult
] = {
    "order.create": _handle_order_create,
    "attendance.check_in": _handle_attendance_check_in,
    "attendance.check_out": _handle_attendance_check_out,
    "delivery.status_update": _handle_delivery_status_update,
    "gps.ingest": _handle_gps_ingest,
    # Ko'prik (bridge) op'lar — T-bridge
    "store.update": _handle_store_update,
    "store.assign_agent": _handle_store_assign_agent,
    "contract.create": _handle_contract_create,
    "marketplace_order.create": _handle_marketplace_order_create,
}


# ─── push ─────────────────────────────────────────────────────────────────────


async def push(
    ops: list[SyncOp],
    actor_id: uuid.UUID,
    user: AppUser,
    db: AsyncSession,
    redis: Any,
    enterprise_id: uuid.UUID | None = None,
) -> list[OpResult]:
    """
    Push batch — har op uchun dispatch + op-darajali xato izolyatsiyasi.

    BATCH LIMIT: settings.sync_max_batch (default: 100).
    OP REGISTRY: op_type → handler.
    IDEMPOTENTLIK: client_uuid — mavjud create_order() mexanizmi ishlatiladi.

    SAVEPOINT IZOLYATSIYA:
      Har op db.begin_nested() (SAVEPOINT) ichida bajariladi.
      Bitta op rollback bo'lsa sessiya ifloslanmaydi — qolgan op'lar
      toza sessiyada davom etadi.
    """
    max_batch = getattr(settings, "sync_max_batch", 100)
    if len(ops) > max_batch:
        raise AppError(
            "sync.batch_too_large",
            status_code=422,
            params={"max": str(max_batch), "given": str(len(ops))},
        )

    results: list[OpResult] = []

    for op in ops:
        handler = _OP_REGISTRY.get(op.op_type)
        if handler is None:
            results.append(
                OpResult(
                    client_uuid=op.client_uuid,
                    status="error",
                    message_key="sync.unknown_op",
                )
            )
            continue

        # SAVEPOINT: har op alohida izolyatsiyalangan nested transaction ichida
        # Bitta op rollback bo'lsa sessiya ifloslanmaydi, qolgan op'lar toza sessiyada davom etadi.
        #
        # Muhim: handler AppError ni ichida ushlab, OpResult(error) qaytarishi mumkin.
        # Bunday hollarda ham SAVEPOINT rollback qilinadi — partial flush'lar tozalansin.
        # Faqat "applied"/"duplicate" natijalarda SAVEPOINT commit qilinadi.
        # SAVEPOINT: har op alohida izolyatsiyalangan nested transaction ichida
        # Bitta op rollback bo'lsa sessiya ifloslanmaydi, qolgan op'lar toza sessiyada davom etadi.
        #
        # Muhim: handler AppError ni ichida ushlab, OpResult(error) qaytarishi mumkin.
        # Bunday hollarda ham SAVEPOINT rollback qilinadi — partial flush'lar tozalansin.
        # Faqat "applied"/"duplicate" natijalarda SAVEPOINT commit qilinadi.
        #
        # Cheklov: create_order() IntegrityError da db.rollback() chaqiradi (idempotentlik).
        # Bu full-session rollback bo'lib SAVEPOINT'ni ham bekor qiladi.
        # Bunday hollarda sp.rollback() xato chiqaradi — qo'shimcha try/except bilan himoya.
        sp = await db.begin_nested()
        try:
            result = await handler(op, actor_id, user, db, redis, enterprise_id=enterprise_id)
            if result.status in ("applied", "duplicate"):
                # Muvaffaqiyatli — SAVEPOINT commit (RELEASE SAVEPOINT)
                try:
                    await sp.commit()
                except Exception:
                    pass  # Allaqachon committed yoki xato — davom etamiz
            else:
                # Op xato/conflict — SAVEPOINT rollback (partial flush'larni tozalash)
                try:
                    await sp.rollback()
                except Exception:
                    pass  # Allaqachon rolled back (masalan, db.rollback() chaqirilgan)
            results.append(result)
        except AppError as exc:
            # AppError handler'dan chiqdi — SAVEPOINT rollback, sessiya toza
            try:
                await sp.rollback()
            except Exception:
                pass
            logger.debug(
                "sync.push: AppError op_type=%s client_uuid=%s key=%s",
                op.op_type,
                op.client_uuid,
                exc.message_key,
            )
            results.append(
                OpResult(
                    client_uuid=op.client_uuid,
                    status="error",
                    message_key=exc.message_key,
                )
            )
        except Exception as exc:
            # Kutilmagan xato — SAVEPOINT rollback, op-darajali (batch davom etadi)
            try:
                await sp.rollback()
            except Exception:
                pass
            logger.exception(
                "sync.push: kutilmagan xato op_type=%s client_uuid=%s",
                op.op_type,
                op.client_uuid,
                exc_info=exc,
            )
            results.append(
                OpResult(
                    client_uuid=op.client_uuid,
                    status="error",
                    message_key="common.internal_error",
                )
            )

    return results


# ─── Snapshot yordamchilari ───────────────────────────────────────────────────


async def _batch_fetch_orders(
    db: AsyncSession, entity_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Order snapshot'larini batch fetch qiladi (N+1 oldini olish).

    WHERE id IN (...) — bitta so'rov, N ta hodisa emas.
    Topilmagan ID uchun {"id": ..., "_deleted": True} qaytaradi.
    """
    uuids: list[uuid.UUID] = []
    invalid: set[str] = set()
    for eid in entity_ids:
        try:
            uuids.append(uuid.UUID(eid))
        except ValueError:
            invalid.add(eid)

    result_map: dict[str, dict[str, Any]] = {}

    # Noto'g'ri UUID lar
    for eid in invalid:
        result_map[eid] = {"id": eid}

    if uuids:
        stmt = select(Order).where(Order.id.in_(uuids))
        result = await db.execute(stmt)
        orders = result.scalars().all()
        found_ids = set()
        for order in orders:
            found_ids.add(order.id)
            result_map[str(order.id)] = {
                "id": str(order.id),
                "store_id": str(order.store_id) if order.store_id else None,
                "agent_id": str(order.agent_id) if order.agent_id else None,
                "mode": order.mode,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "currency": order.currency,
                "ordered_at": order.ordered_at.isoformat() if order.ordered_at else None,
                "client_uuid": order.client_uuid,
                "version": order.version,
                "deleted_at": order.deleted_at.isoformat() if order.deleted_at else None,
            }
        # Topilmagan UUID lar — deleted
        for u in uuids:
            if u not in found_ids:
                result_map[str(u)] = {"id": str(u), "_deleted": True}

    return result_map


async def _batch_fetch_stores(
    db: AsyncSession, entity_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Store snapshot'larini batch fetch qiladi."""
    uuids: list[uuid.UUID] = []
    invalid: set[str] = set()
    for eid in entity_ids:
        try:
            uuids.append(uuid.UUID(eid))
        except ValueError:
            invalid.add(eid)

    result_map: dict[str, dict[str, Any]] = {}
    for eid in invalid:
        result_map[eid] = {"id": eid}

    if uuids:
        stmt = select(Store).where(Store.id.in_(uuids))
        result = await db.execute(stmt)
        stores = result.scalars().all()
        found_ids = set()
        for store in stores:
            found_ids.add(store.id)
            result_map[str(store.id)] = {
                "id": str(store.id),
                "name": store.name,
                "segment_id": str(store.segment_id) if store.segment_id else None,
                "agent_id": str(store.agent_id) if store.agent_id else None,
                "branch_id": str(store.branch_id) if store.branch_id else None,
                "version": store.version,
                "deleted_at": store.deleted_at.isoformat() if store.deleted_at else None,
            }
        for u in uuids:
            if u not in found_ids:
                result_map[str(u)] = {"id": str(u), "_deleted": True}

    return result_map


async def _batch_fetch_products(
    db: AsyncSession, entity_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Product snapshot'larini batch fetch qiladi."""
    uuids: list[uuid.UUID] = []
    invalid: set[str] = set()
    for eid in entity_ids:
        try:
            uuids.append(uuid.UUID(eid))
        except ValueError:
            invalid.add(eid)

    result_map: dict[str, dict[str, Any]] = {}
    for eid in invalid:
        result_map[eid] = {"id": eid}

    if uuids:
        stmt = select(Product).where(Product.id.in_(uuids))
        result = await db.execute(stmt)
        products = result.scalars().all()
        found_ids = set()
        for product in products:
            found_ids.add(product.id)
            result_map[str(product.id)] = {
                "id": str(product.id),
                "name_uz": product.name_uz,
                "name_ru": product.name_ru,
                "sku": product.sku,
                "barcode": product.barcode,
                "unit": product.unit,
                "is_active": product.is_active,
                "version": product.version,
            }
        for u in uuids:
            if u not in found_ids:
                result_map[str(u)] = {"id": str(u), "_deleted": True}

    return result_map


def _generic_snapshot_from_payload(
    entity_id: str, payload_str: str
) -> dict[str, Any]:
    """Umumiy snapshot — maxsus modeli bo'lmagan aggregate_type uchun. Outbox payload'ini qaytaradi."""
    try:
        return json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return {"id": entity_id}


# Batch fetch handler'lari: aggregate_type → batch fetch funksiyasi
_BATCH_SNAPSHOT_HANDLERS: dict[
    str,
    Any  # (db, entity_ids) -> dict[str, dict]
] = {
    "order": _batch_fetch_orders,
    "order_template": _batch_fetch_orders,  # stub — to'liq T14 da kengaytiriladi
    "store": _batch_fetch_stores,
    "product": _batch_fetch_products,
}


# ─── pull ─────────────────────────────────────────────────────────────────────


async def pull(
    since_seq: int,
    limit: int,
    user: AppUser,
    db: AsyncSession,
    enterprise_id: uuid.UUID | None = None,
) -> tuple[list[ChangeItem], int, bool]:
    """
    Delta pull — foydalanuvchi scope'idagi hodisalar, seq > since_seq.

    KURSOR: seq (server-avtoritar monoton) — created_at ishlatilmaydi.
    SCOPE (IDOR himoya):
      - product/price/promo/catalog → global, hammaga.
      - order/store/order_template → faqat user_store_ids.
      - boshqa → admin/accountant ko'radi; agent/store ko'rmaydi.

    N+1 YECHIMI (batch fetch):
      Hodisalar aggregate_type bo'yicha guruhlanadi.
      Har tur uchun BITTA batch so'rov (WHERE id IN (...)).
      200 hodisa = bir nechta so'rov (tur soni), N+1 emas.

    KURSOR PROGRESS:
      next_cursor = skanerlangan oxirgi hodisa seq'i (events[-1].seq).
      changes bo'sh bo'lsa ham kursor ilgarilaydi — cheksiz bo'sh pull yo'q.
      has_more = skanerlangan hodisa soni limit'ga yetganda.

    Returns:
      (changes, next_cursor, has_more)
      next_cursor = skanerlangan oxirgi seq (0 agar hech qanday hodisa yo'q).
      has_more = True agar limit'ga yetilgan.
    """
    effective_limit = min(limit, getattr(settings, "sync_pull_limit", 200))

    # Foydalanuvchi roli uchun ruxsat etilgan do'kon ID lari
    user_store_ids: list | None = None
    role = user.role

    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.seq > since_seq)
        .order_by(OutboxEvent.seq.asc())
        .limit(effective_limit)
    )
    # MT2: faqat joriy korxona outbox hodisalarini qaytarish (cross-tenant sync teshigi yo'q)
    stmt = apply_enterprise_filter(stmt, enterprise_id, OutboxEvent.enterprise_id)
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    if not events:
        return [], since_seq, False

    # Scope uchun store_ids — faqat bir marta oliladi (lazy)
    def _needs_scope_check(agg_type: str) -> bool:
        return agg_type in _SCOPED_AGGREGATE_TYPES

    # Store IDs ni olish (agar kerak bo'lsa)
    if any(_needs_scope_check(e.aggregate_type) for e in events):
        user_store_ids = await get_user_store_ids(user, db)

    # ── Scope filtr: qaysi hodisalar ko'rinadi ───────────────────────────────
    visible_events: list[OutboxEvent] = []
    for event in events:
        if event.aggregate_type in _GLOBAL_AGGREGATE_TYPES:
            visible_events.append(event)
        elif event.aggregate_type in _SCOPED_AGGREGATE_TYPES:
            if _can_see_scoped_event(event, user, user_store_ids or []):
                visible_events.append(event)
        else:
            # Noma'lum aggregate_type — faqat admin/accountant
            if role in ("administrator", "accountant"):
                visible_events.append(event)

    # KURSOR PROGRESS: skanerlangan oxirgi hodisa seq'i
    # changes bo'sh bo'lsa ham kursor ilgarilaydi (cheksiz bo'sh pull oldini olish)
    last_scanned_seq = events[-1].seq
    has_more = len(events) >= effective_limit

    if not visible_events:
        return [], last_scanned_seq, has_more

    # ── Batch fetch: aggregate_type bo'yicha guruhla → har tur uchun bir so'rov ─
    # N+1 muammosini bartaraf etadi: 200 hodisa = bir nechta so'rov (tur soni).
    from collections import defaultdict

    # aggregate_type → [(aggregate_id, event), ...]
    type_to_events: dict[str, list[OutboxEvent]] = defaultdict(list)
    for event in visible_events:
        type_to_events[event.aggregate_type].append(event)

    # Har aggregate_type uchun batch fetch
    # aggregate_type:entity_id → snapshot dict
    snapshot_cache: dict[str, dict[str, Any]] = {}

    for agg_type, agg_events in type_to_events.items():
        batch_handler = _BATCH_SNAPSHOT_HANDLERS.get(agg_type)
        if batch_handler is not None:
            entity_ids = [e.aggregate_id for e in agg_events]
            batch_result = await batch_handler(db, entity_ids)
            for eid, snap in batch_result.items():
                snapshot_cache[f"{agg_type}:{eid}"] = snap
        else:
            # Generic: payload'dan snapshot olish (DB so'rovi yo'q)
            for event in agg_events:
                key = f"{agg_type}:{event.aggregate_id}"
                snapshot_cache[key] = _generic_snapshot_from_payload(
                    event.aggregate_id, event.payload
                )

    # ── ChangeItem ro'yxatini yasash ────────────────────────────────────────
    changes: list[ChangeItem] = []
    for event in visible_events:
        key = f"{event.aggregate_type}:{event.aggregate_id}"
        snapshot = snapshot_cache.get(key, {"id": event.aggregate_id})
        changes.append(
            ChangeItem(
                entity_type=event.aggregate_type,
                entity_id=event.aggregate_id,
                event_type=event.event_type,
                seq=event.seq,
                snapshot=snapshot,
            )
        )

    return changes, last_scanned_seq, has_more


def _can_see_scoped_event(
    event: OutboxEvent,
    user: AppUser,
    user_store_ids: list,
) -> bool:
    """
    Foydalanuvchi berilgan scope'd hodisani ko'ra oladimi?

    Qoida:
      - admin/accountant → barcha hodisalar.
      - agent/store → faqat o'z do'konlariga tegishli.
      - store_id payload'da bo'lmasa → fail-safe deny (ruxsat berilmaydi).
        (store_id endi order.status_updated payload'ida ham mavjud — HIGH #4 tuzatildi.)
      - courier → faqat order_template ko'rmaydi, lekin orderlarni ko'radi
        (yetkazish uchun). Bu soddalashtirilgan qoida — T18 da kengaytiriladi.
    """
    role = user.role
    agg_type = event.aggregate_type

    if role in ("administrator", "accountant"):
        return True

    if agg_type == "store":
        # Do'kon hodisasi: store_id == aggregate_id
        try:
            store_uuid = uuid.UUID(event.aggregate_id)
            return store_uuid in user_store_ids
        except ValueError:
            return False

    if agg_type in ("order", "order_template"):
        # Buyurtma hodisasi: payload'dan store_id ajratish
        # store_id payload'da bo'lmasa → fail-safe deny
        # (order.status_updated endi store_id o'z ichiga oladi — HIGH #4)
        try:
            payload_data = json.loads(event.payload)
            store_id_str = payload_data.get("store_id")
            if store_id_str is None:
                # store_id payload'da yo'q — fail-safe: ruxsat berilmaydi
                return False
            store_uuid = uuid.UUID(store_id_str)
            return store_uuid in user_store_ids
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    if agg_type == "attendance":
        # Davomat hodisasi: payload'dan user_id ajratish
        # Foydalanuvchi faqat o'z davomatini ko'radi (T16 IDOR himoya)
        # Administrator/accountant yuqorida allaqachon True qaytarildi
        try:
            payload_data = json.loads(event.payload)
            user_id_str = payload_data.get("user_id")
            if user_id_str is None:
                return False
            event_user_id = uuid.UUID(user_id_str)
            return event_user_id == user.id
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    return False
