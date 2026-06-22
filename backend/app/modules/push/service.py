"""
Push bildirishnoma servis qatlami — T19 Push Worker.

ASOSIY FUNKSIYA:
  process_pending_pushes(db, provider, limit=100)

Bu funksiya outbox_event jadvalidan push'ga tegishli hodisalarni o'qiydi va
tegishli foydalanuvchilarga FCM/APNs orqali push bildirishnoma yuboradi.

SYNC DAN IZOLYATSIYA (MUHIM):
  - Push ALOHIDA consumer — outbox.published_at ga TEGMAYDI.
  - Sync (GET /sync/pull) outbox.seq kursori bo'yicha ishlaydi.
  - Push push_log (unique outbox_event_id + user_id) orqali dedupe qiladi.
  - Bu ikki consumer bir-birining holatini buzmaydi.

MAQSAD FOYDALANUVCHILAR:
  order.status_updated  → order.store.user_id (do'kon egasi) + order.agent_id (agent)
  delivery.created      → order.store.user_id (do'kon) + delivery.courier_id (kuryer)
  delivery.status_updated → order.store.user_id (do'kon) + delivery.courier_id (kuryer)

IDEMPOTENTLIK:
  push_log.unique(outbox_event_id, user_id) — bir hodisa + bir foydalanuvchi = bir push.
  IntegrityError → o'tkazib yuboriladi (idempotent).

RETRY:
  status=failed va attempts < PUSH_MAX_RETRIES → keyingi run retry qiladi.
  3 urinishdan keyin status=failed qoladi (manual investigation kerak).
  Backoff: attempts bo'yicha eksponensial (hozir: worker davriy ishlaganda amalga oshadi).

DEVICE_ID:
  AppUser.device_id — FCM token. NULL bo'lsa → skip (log).
  Kanal aniqlanishi: hozir 'fcm' default; kelajakda device_id prefix bo'yicha.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models.delivery import Delivery
from app.models.order import Order
from app.models.outbox import OutboxEvent
from app.models.push import PushLog
from app.models.store import Store
from app.models.user import AppUser
from app.modules.push.messages import push_text
from app.modules.push.provider import PushProvider, PushResult

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

# Push'ga tegishli outbox hodisa turlari
_PUSH_EVENT_TYPES = frozenset({
    "order.status_updated",
    "delivery.created",
    "delivery.status_updated",
})

# Maksimal retry urinishlari — config dan (default 3)
_MAX_RETRIES: int = getattr(settings, "push_max_retries", 3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short_id(uid: uuid.UUID | str | None) -> str:
    """UUID ning qisqa ko'rinishi — push matnda ko'rsatish uchun."""
    if uid is None:
        return "?"
    s = str(uid)
    return s[:8]


# ─── Maqsad foydalanuvchilarni aniqlash ──────────────────────────────────────


async def _get_targets_for_order_event(
    db: AsyncSession,
    payload: dict,
) -> list[uuid.UUID]:
    """
    order.status_updated → do'kon egasi (store.user_id) + agent (order.agent_id).

    payload da order_id bo'lishi kutiladi.
    """
    order_id_str = payload.get("order_id") or payload.get("id")
    if not order_id_str:
        logger.warning("push: order hodisada order_id topilmadi, payload=%s", payload)
        return []

    try:
        order_id = uuid.UUID(str(order_id_str))
    except (ValueError, AttributeError):
        logger.warning("push: order_id UUID emas: %s", order_id_str)
        return []

    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .where(Order.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        logger.debug("push: order topilmadi id=%s", order_id)
        return []

    targets: list[uuid.UUID] = []

    # Do'kon egasi
    store_stmt = select(Store).where(Store.id == order.store_id)
    store_res = await db.execute(store_stmt)
    store = store_res.scalar_one_or_none()
    if store and store.user_id:
        targets.append(store.user_id)

    # Agent
    if order.agent_id:
        targets.append(order.agent_id)

    return list(set(targets))  # dedupe


async def _get_targets_for_delivery_event(
    db: AsyncSession,
    payload: dict,
) -> list[uuid.UUID]:
    """
    delivery.created / delivery.status_updated → do'kon egasi + kuryer.

    payload da delivery_id bo'lishi kutiladi.
    """
    delivery_id_str = payload.get("delivery_id") or payload.get("id")
    if not delivery_id_str:
        logger.warning("push: delivery hodisada delivery_id topilmadi, payload=%s", payload)
        return []

    try:
        delivery_id = uuid.UUID(str(delivery_id_str))
    except (ValueError, AttributeError):
        logger.warning("push: delivery_id UUID emas: %s", delivery_id_str)
        return []

    stmt = (
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .where(Delivery.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()
    if delivery is None:
        logger.debug("push: delivery topilmadi id=%s", delivery_id)
        return []

    targets: list[uuid.UUID] = []

    # Kuryer
    targets.append(delivery.courier_id)

    # Do'kon egasi (order → store → user_id)
    order_stmt = select(Order).where(Order.id == delivery.order_id)
    order_res = await db.execute(order_stmt)
    order = order_res.scalar_one_or_none()
    if order:
        store_stmt = select(Store).where(Store.id == order.store_id)
        store_res = await db.execute(store_stmt)
        store = store_res.scalar_one_or_none()
        if store and store.user_id:
            targets.append(store.user_id)

    return list(set(targets))


# ─── Push matn generatsiya ────────────────────────────────────────────────────


def _build_push_text(
    event_type: str,
    payload: dict,
    locale: str,
) -> tuple[str, str]:
    """
    Hodisa turi va payload asosida push title + body matnini qaytaradi.

    Returns:
        (title, body)
    """
    if event_type == "order.status_updated":
        order_id_str = payload.get("order_id") or payload.get("id") or ""
        status = payload.get("status") or payload.get("new_status") or "?"
        return push_text(
            "push.order_status_updated",
            locale=locale,
            order_id_short=_short_id(order_id_str),
            status=status,
        )

    elif event_type == "delivery.created":
        # Delivery payload da order_id bo'lishi mumkin
        order_id_str = payload.get("order_id") or ""
        return push_text(
            "push.delivery_created",
            locale=locale,
            order_id_short=_short_id(order_id_str),
        )

    elif event_type == "delivery.status_updated":
        order_id_str = payload.get("order_id") or ""
        status = payload.get("status") or payload.get("new_status") or "?"
        return push_text(
            "push.delivery_status_updated",
            locale=locale,
            order_id_short=_short_id(order_id_str),
            status=status,
        )

    else:
        return push_text("push.general", locale=locale)


# ─── Asosiy funksiya ──────────────────────────────────────────────────────────


async def process_pending_pushes(
    db: AsyncSession,
    provider: PushProvider,
    limit: int = 100,
) -> int:
    """
    Kutilayotgan push bildirishnomalarni qayta ishlaydi.

    Bu funksiya sinxron testlash uchun qulay (FakePushProvider bilan).
    Arq worker production da davriy chaqiradi.

    Qadamlar:
      1-PASS (yangi hodisalar): push_log da UMUMAN yo'q outbox hodisalari —
          NOT EXISTS subquery orqali filtrlanadi. Har run yangi hodisalar
          oldinga suriladi (progress kafolatlanadi — stall yo'q).
      2-PASS (retry): status=failed AND attempts < MAX_RETRIES bo'lgan
          push_log yozuvlari — alohida so'rov bilan olinib retry qilinadi.

    Args:
        db:       Async DB sessiyasi.
        provider: Push provider (FcmProvider/FakePushProvider).
        limit:    Bir ishlovda max hodisalar soni (har pass uchun alohida).

    Returns:
        Qayta ishlangan push_log yozuvlari soni.

    DIQQAT:
        outbox.published_at ga TEGMAYDI — sync seq kursori bilan to'qnashmaydi.
    """
    processed = 0

    # ── PASS 2 kandidatlari oldindan yig'iladi (PASS 1 dan oldin) ────────────
    #
    # Muhim: retry so'rovini PASS 1 dan OLDIN bajaramiz.
    # Shunday qilib PASS 1 da yangi yozilgan failed loglar shu runda DARHOL
    # retry qilinmaydi — keyingi runda retry bo'ladi (to'g'ri xulq).
    retry_logs_stmt = (
        select(PushLog, OutboxEvent)
        .join(OutboxEvent, PushLog.outbox_event_id == OutboxEvent.id)
        .where(PushLog.status == "failed")
        .where(PushLog.attempts < _MAX_RETRIES)
        .order_by(PushLog.attempts, OutboxEvent.seq)
        .limit(limit)
    )
    retry_result = await db.execute(retry_logs_stmt)
    # Natijalarni xotirada saqlash — keyingi qayta ishlovda yangi yozuvlar aralashmasin
    retry_rows = retry_result.all()

    # ── PASS 1: Yangi hodisalar — push_log da hech qanday yozuvi YO'Q ────────
    #
    # NOT EXISTS filtr: bu outbox hodisa uchun birorta ham push_log yozuvi
    # bo'lmagan hodisalarni oladi. Shu tarzda har run yangi hodisalar
    # seq bo'yicha oldinga suriladi — 100+ hodisa bo'lsa ham hamma
    # oxir-oqibat qayta ishlanadi (stall yo'q).
    #
    # MUHIM: published_at ni O'QIMAYMIZ — push consumer o'z holatini
    # push_log orqali boshqaradi; sync seq kursori bilan to'qnashmaydi.
    pl_alias = aliased(PushLog)
    new_events_stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.event_type.in_(_PUSH_EVENT_TYPES))
        .where(
            ~select(pl_alias)
            .where(pl_alias.outbox_event_id == OutboxEvent.id)
            .correlate(OutboxEvent)
            .exists()
        )
        .order_by(OutboxEvent.seq)
        .limit(limit)
    )
    new_events_result = await db.execute(new_events_stmt)
    new_events = new_events_result.scalars().all()

    for event in new_events:
        try:
            payload: dict = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
        except (json.JSONDecodeError, TypeError):
            logger.warning("push: payload JSON parse xatosi event_id=%s", event.id)
            payload = {}

        if event.event_type == "order.status_updated":
            target_ids = await _get_targets_for_order_event(db, payload)
        elif event.event_type in ("delivery.created", "delivery.status_updated"):
            target_ids = await _get_targets_for_delivery_event(db, payload)
        else:
            target_ids = []

        if not target_ids:
            logger.debug(
                "push: hodisa uchun maqsad topilmadi event_id=%s type=%s",
                event.id, event.event_type,
            )
            continue

        for user_id in target_ids:
            processed += await _process_one_push(
                db=db,
                provider=provider,
                event=event,
                payload=payload,
                user_id=user_id,
            )

    # ── PASS 2: Retry — oldindan yig'ilgan failed loglar qayta uriniladi ──────
    #
    # retry_rows PASS 1 dan oldin yig'ilgan → shu runda yangi yozilgan
    # failed loglar aralashmaydi (keyingi runda retry bo'ladi).
    for push_log_row, event in retry_rows:
        try:
            payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
        except (json.JSONDecodeError, TypeError):
            logger.warning("push: retry payload JSON parse xatosi event_id=%s", event.id)
            payload = {}

        # _process_one_push mavjud failed log'ni topib retry qiladi
        processed += await _process_one_push(
            db=db,
            provider=provider,
            event=event,
            payload=payload,
            user_id=push_log_row.user_id,
        )

    if not new_events and not retry_rows:
        logger.debug("process_pending_pushes: push hodisalar topilmadi")

    return processed


async def _process_one_push(
    db: AsyncSession,
    provider: PushProvider,
    event: OutboxEvent,
    payload: dict,
    user_id: uuid.UUID,
) -> int:
    """
    Bir foydalanuvchi uchun push yozuvi yaratadi yoki retry qiladi.

    Returns:
        1 — qayta ishlandi; 0 — o'tkazib yuborildi.
    """
    # Mavjud push_log yozuvini tekshirish
    log_stmt = (
        select(PushLog)
        .where(PushLog.outbox_event_id == event.id)
        .where(PushLog.user_id == user_id)
    )
    log_res = await db.execute(log_stmt)
    existing_log = log_res.scalar_one_or_none()

    # Idempotentlik: sent bo'lsa o'tkazib yuborish
    if existing_log is not None and existing_log.status == "sent":
        logger.debug(
            "push: allaqachon yuborilgan, skip. event_id=%s user_id=%s",
            event.id, user_id,
        )
        return 0

    # Retry: failed + max retries yetdi → skip
    if existing_log is not None and existing_log.status == "failed":
        if existing_log.attempts >= _MAX_RETRIES:
            logger.debug(
                "push: max retry yetdi (%d), skip. event_id=%s user_id=%s",
                _MAX_RETRIES, event.id, user_id,
            )
            return 0

    # Foydalanuvchi ma'lumotlarini olish (device_id, locale)
    user_stmt = select(AppUser).where(AppUser.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if user is None:
        logger.warning("push: foydalanuvchi topilmadi user_id=%s", user_id)
        return 0

    # device_id yo'q → skip
    if not user.device_id:
        logger.info(
            "push: device_id yo'q, skip. user_id=%s event_id=%s",
            user_id, event.id,
        )
        return 0

    # ── Kanal aniqlash ────────────────────────────────────────────────────────
    # device_id prefix bo'yicha: "apns:<token>" → apns, boshqasi → fcm.
    # Kelajakda AppUser.push_channel maydoni qo'shilishi mumkin.
    raw_device_id = user.device_id
    if raw_device_id and raw_device_id.startswith("apns:"):
        channel = "apns"
        actual_device_token = raw_device_id[len("apns:"):]
    else:
        channel = "fcm"
        actual_device_token = raw_device_id  # type: ignore[assignment]

    # Xabar matnini generatsiya qilish
    locale = user.locale or "uz"
    title, body = _build_push_text(event.event_type, payload, locale)

    # Push_log yozuvi (mavjud bo'lmasa yangi, bo'lsa retry uchun update)
    if existing_log is None:
        push_log = PushLog(
            outbox_event_id=event.id,
            user_id=user_id,
            device_id=raw_device_id,
            channel=channel,
            title=title,
            body=body,
            status="pending",
            attempts=0,
            # MT2: korxona izchilligi — push_log target user korxonasiga tegishli
            enterprise_id=getattr(user, "enterprise_id", None),
        )
        db.add(push_log)
        try:
            # SAVEPOINT (begin_nested) — faqat shu push_log INSERT uchun.
            # IntegrityError (race/duplicate) → faqat ushbu savepoint rollback
            # bo'ladi; butun sessiya va batch'dagi boshqa push_log yozuvlari
            # saqlanadi. T13/T18 naqshi.
            async with db.begin_nested():
                await db.flush()
        except IntegrityError:
            # Race condition: parallel worker bir xil hodisani qayta ishlaydi.
            # Savepoint rollback bo'ldi — sessiya hali tirik (ifloslanmagan).
            logger.debug(
                "push: IntegrityError (race/duplicate), skip. event_id=%s user_id=%s",
                event.id, user_id,
            )
            return 0
    else:
        # Retry: mavjud failed yozuv
        push_log = existing_log
        # device_id yangilash (foydalanuvchi token yangilagan bo'lishi mumkin)
        push_log.device_id = raw_device_id

    # ── Push yuborish (platform bo'yicha yo'naltirish) ───────────────────────
    #
    # channel="apns" → ApnsProvider, "fcm" → FcmProvider (yoki berilgan provider).
    # Hozirda provider factory dan keladi — agar PushProvider interfeysi bo'lsa,
    # xuddi shunday chaqiriladi (test/prod uchun).
    #
    # APNs provider alohida yaratiladi (service.py da inject qilinmagan).
    # Kelajakda: _get_provider(channel) → dependency injection ga o'tish mumkin.
    push_log.attempts += 1
    result: PushResult
    try:
        if channel == "apns":
            # APNs uchun alohida provider (config asosida, no-op bo'lishi mumkin)
            from app.modules.push.provider import get_apns_provider
            apns_provider = get_apns_provider()
            result = await apns_provider.send(
                device_token=actual_device_token,
                title=title,
                body=body,
            )
        else:
            # FCM (default) — berilgan provider orqali (FakeProvider test uchun)
            # Mavjud provider PushProvider interfeysi → async send() chaqiriladi
            result = await provider.send(
                device_token=actual_device_token,
                title=title,
                body=body,
            )
    except Exception as exc:
        logger.error(
            "push: provider.send() exception: %s event_id=%s user_id=%s",
            exc, event.id, user_id,
        )
        result = PushResult(ok=False, error=str(exc)[:500])
        push_log.last_error = str(exc)[:500]

    # ── Token invalidatsiya ───────────────────────────────────────────────────
    # FCM 404/UNREGISTERED yoki APNs 410/BadDeviceToken →
    # device_token ni NULL qilish (qayta yuborilmasin).
    # Append-only qoida: push_log.last_error da sabab saqlanadi,
    # push_log yozuvi o'chirilmaydi (audit trail).
    if result.invalid_token:
        logger.warning(
            "push: token eskirgan/noto'g'ri — device_id NULL qilinadi. "
            "user_id=%s error=%s",
            user_id, result.error,
        )
        # AppUser.device_id = None → keyingi push skip bo'ladi
        user.device_id = None
        db.add(user)
        push_log.last_error = f"token_invalidated: {result.error or 'invalid_token'}"
        push_log.status = "failed"
        await db.flush()
        return 1

    if result.ok:
        push_log.status = "sent"
        push_log.sent_at = _now()
        push_log.last_error = None
        logger.info(
            "push: muvaffaqiyatli yuborildi. event_id=%s user_id=%s channel=%s",
            event.id, user_id, channel,
        )
    else:
        push_log.status = "failed"
        if not push_log.last_error:
            push_log.last_error = result.error or "provider.send() failed"
        logger.warning(
            "push: yuborishda xato. event_id=%s user_id=%s attempts=%d max=%d error=%s",
            event.id, user_id, push_log.attempts, _MAX_RETRIES, result.error,
        )

    await db.flush()
    return 1
