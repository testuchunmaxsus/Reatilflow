"""
Expiry scan servisi — MP4.

mark_expired_inventory(db):
  1. expiry_date < today → status='expired' (active → expired).
  2. expiry_date <= today + expiry_notify_days (hali active) →
     - OutboxEvent (inventory.expiring_soon) yoziladi.
     - PushLog (korxona admini) yoziladi (idempotent: notify_sent_date tekshiradi).

TAKROR BILDIRISHNOMA OLDINI OLISH:
  OutboxEvent aggregate_id = "inv:{inventory_id}:notify:{today.isoformat()}"
  Bir kun ichida bir xil aggregate_id → birinchi yozuv; ikkinchi skip (unique partial).
  Yoki select orqali tekshirib, exists bo'lsa o'tkazib yuboramiz.

ASYNCPG: Har sa.text() bitta buyruq.

ATOMIKLIK: Har inventar yozuvi alohida save-point emas — bulk UPDATE + looping
  for bildirishnomalar. Sessiya caller (router/cron) commit qiladi.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.outbox import OutboxEvent
from app.models.push import PushLog
from app.models.store_inventory import StoreInventory
from app.models.store import Store
from app.models.catalog import Product
from app.models.user import AppUser
from app.modules.pos.expiry import is_expired, days_to_expiry

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> date:
    return _now_utc().date()


# ─── Expiry scan ──────────────────────────────────────────────────────────────


async def mark_expired_inventory(
    db: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """
    Expiry scan: muddati o'tgan → 'expired'; yaqinda tugaydi → bildirishnoma.

    Args:
        db:  AsyncSession (caller commit qiladi).
        now: Test uchun vaqtni o'rnatish (None = hozir UTC).

    Returns:
        {
          "marked_expired": int   — 'expired' deb belgilangan soni,
          "notifications_sent": int — bildirishnoma yuborilgan soni,
        }
    """
    today = _today_utc() if now is None else (
        now.date() if now.tzinfo is None else now.astimezone(timezone.utc).date()
    )

    notify_deadline = today + timedelta(days=settings.expiry_notify_days)
    marked_expired = 0
    notifications_sent = 0

    # ── 1. Muddati o'tgan active partiyalar → status='expired' ───────────────
    expired_stmt = (
        select(StoreInventory)
        .where(
            StoreInventory.status == "active",
            StoreInventory.expiry_date.isnot(None),
            StoreInventory.expiry_date < today,
        )
    )
    expired_result = await db.execute(expired_stmt)
    expired_items = expired_result.scalars().all()

    for inv in expired_items:
        inv.status = "expired"
        db.add(inv)
        marked_expired += 1

    if marked_expired:
        logger.info("expiry_scan: %d partiya 'expired' deb belgilandi", marked_expired)

    # Flush: keyingi so'rovlarda yangilangan statuslar ko'rinsin
    await db.flush()

    # ── 2. Yaqin muddatli ACTIVE partiyalar → bildirishnoma ──────────────────
    # expiry_date <= today + notify_deadline va hali active (expired emas)
    near_stmt = (
        select(StoreInventory)
        .where(
            StoreInventory.status == "active",
            StoreInventory.expiry_date.isnot(None),
            StoreInventory.expiry_date >= today,          # hali o'tmagan
            StoreInventory.expiry_date <= notify_deadline, # chegarada yoki undan ichkarida
        )
    )
    near_result = await db.execute(near_stmt)
    near_items = near_result.scalars().all()

    for inv in near_items:
        # Takror bildirishnoma oldini olish:
        # aggregate_id = "inv_expiry:{inv.id}:{today}" — bir kun, bir partiya = bir bildirishnoma
        notify_aggregate_id = f"inv_expiry:{inv.id}:{today.isoformat()}"

        # Mavjud outbox tekshiruvi
        existing_stmt = select(OutboxEvent.id).where(
            OutboxEvent.aggregate_type == "store_inventory",
            OutboxEvent.aggregate_id == notify_aggregate_id,
            OutboxEvent.event_type == "inventory.expiring_soon",
        )
        existing_res = await db.execute(existing_stmt)
        if existing_res.scalar_one_or_none() is not None:
            # Bu kun allaqachon yuborilgan
            continue

        # Mahsulot va do'kon nomini olish (bildirishnoma matni uchun)
        product_name = str(inv.product_id)  # fallback
        store_name = str(inv.store_id)       # fallback
        days_left = (inv.expiry_date - today).days if inv.expiry_date else 0

        prod_stmt = select(Product.name_uz).where(Product.id == inv.product_id)
        prod_res = await db.execute(prod_stmt)
        pname = prod_res.scalar_one_or_none()
        if pname:
            product_name = pname

        store_stmt = select(Store.name).where(Store.id == inv.store_id)
        store_res = await db.execute(store_stmt)
        sname = store_res.scalar_one_or_none()
        if sname:
            store_name = sname

        # Outbox event
        payload = {
            "inventory_id": str(inv.id),
            "enterprise_id": str(inv.enterprise_id),
            "store_id": str(inv.store_id),
            "product_id": str(inv.product_id),
            "product_name": product_name,
            "store_name": store_name,
            "expiry_date": inv.expiry_date.isoformat() if inv.expiry_date else None,
            "days_to_expiry": days_left,
        }
        outbox_event = OutboxEvent(
            aggregate_type="store_inventory",
            aggregate_id=notify_aggregate_id,
            event_type="inventory.expiring_soon",
            payload=json.dumps(payload, default=str),
        )
        db.add(outbox_event)

        # PushLog: korxona adminini topish (role='administrator')
        # MP4 — korxona admini (enterprise_id bo'yicha faqat birinchi admin)
        admin_stmt = (
            select(AppUser)
            .where(
                AppUser.enterprise_id == inv.enterprise_id,
                AppUser.role == "administrator",
                AppUser.is_active.is_(True),
                AppUser.device_id.isnot(None),
            )
            .limit(5)  # bir nechta admin bo'lishi mumkin
        )
        admin_result = await db.execute(admin_stmt)
        admins = admin_result.scalars().all()

        await db.flush()  # outbox_event.id kerak

        for admin in admins:
            # Push log uchun title/body (foydalanuvchi locale bo'yicha)
            locale = getattr(admin, "locale", "uz") or "uz"
            from app.modules.push.messages import push_text
            title, body = push_text(
                "push.inventory_expiring_soon",
                locale=locale,
                product_name=product_name,
                days=days_left,
                store_name=store_name,
            )

            raw_device_id = admin.device_id or ""
            channel = "apns" if raw_device_id.startswith("apns:") else "fcm"
            actual_token = (
                raw_device_id[len("apns:"):] if channel == "apns" else raw_device_id
            )

            push_log = PushLog(
                outbox_event_id=outbox_event.id,
                user_id=admin.id,
                device_id=raw_device_id,
                channel=channel,
                title=title,
                body=body,
                status="pending",
                attempts=0,
                enterprise_id=inv.enterprise_id,
            )
            db.add(push_log)

        notifications_sent += 1

    if notifications_sent:
        logger.info(
            "expiry_scan: %d yaqin muddatli partiya uchun bildirishnoma yuborildi",
            notifications_sent,
        )

    await db.flush()

    return {
        "marked_expired": marked_expired,
        "notifications_sent": notifications_sent,
    }
