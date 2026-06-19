"""
Buxgalteriya servis qatlami — ledger yozuvlari va balans biznes mantiq.

Funksiyalar:
  record_entry(db, data, actor_id, redis) → LedgerEntry
  get_balance(db, store_id, user) → AccountBalance
  list_entries(db, store_id, user, ...) → (list[LedgerEntry], int)

MUHIM QOIDALAR (ADR §3.4, §3.5):
  - ledger_entry APPEND-ONLY: faqat INSERT. UPDATE/DELETE TAQIQLANGAN.
  - Moliyaviy balans o'qish FAQAT primary DB dan (replica kechikishini oldini olish).
    IZOH: get_balance() va record_entry() doim primary sessiya (db parametri) bilan
    chaqirilishi shart. FastAPI get_db() (primary) dependency ishlatiladi.
  - amount — Decimal (float emas; moliyaviy aniqlik).
  - client_uuid Redis idempotentlik (24h TTL).
  - Har yozuvda audit_log + outbox_event qo'shiladi.
  - IDOR himoya: store roli faqat o'z store_id ini ko'ra oladi (scope.py orqali).

Balans ishorasi kelishuvi:
  debit  → balance += amount (mijoz qarz oshdi)
  credit → balance -= amount (qarz kamaydi, to'lov)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.audit import AuditLog
from app.models.finance import AccountBalance, LedgerEntry
from app.models.outbox import OutboxEvent
from app.models.store import Store
from app.models.user import AppUser
from app.modules.finance.schemas import LedgerEntryCreate
from app.modules.rbac.scope import get_user_store_ids

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_IDEM_TTL_SECONDS = 86400       # 24 soat
_IDEM_PREFIX = "idem:finance:entry"


# ─── Yordamchi ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    entity_id: str,
    after: dict | None = None,
) -> None:
    """audit_log ga yozuv qo'shadi."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="ledger_entry",
        entity_id=entity_id,
        before_json=None,
        after_json=json.dumps(after, default=str) if after else None,
    )
    db.add(log)


async def _write_outbox(
    db: AsyncSession,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """outbox_event ga yozuv qo'shadi."""
    event = OutboxEvent(
        aggregate_type="ledger_entry",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=json.dumps(payload, default=str),
    )
    db.add(event)


# ─── record_entry ─────────────────────────────────────────────────────────────


async def record_entry(
    db: AsyncSession,
    data: LedgerEntryCreate,
    actor_id: uuid.UUID | None = None,
    redis=None,
) -> LedgerEntry:
    """
    Yangi buxgalteriya yozuvi qayd etadi — APPEND-ONLY INSERT.

    Jarayon:
      1. Redis idempotentlik tekshiruvi (client_uuid).
      2. Do'kon mavjudligi tekshiruvi.
      3. LedgerEntry INSERT (APPEND-ONLY — hech qachon UPDATE/DELETE qilinmaydi).
      4. AccountBalance yangilash (with_for_update + optimistik version).
         debit  → balance += amount
         credit → balance -= amount
      5. audit_log + outbox_event INSERT.
      6. Redis idempotentlik kalitini saqlash.

    MUHIM: db parametri primary DB sessiyasi bo'lishi shart (ADR §3.4).
    Replica sessiya balans uchun xavfli (kechikish).

    Args:
        db:       Primary DB sessiyasi.
        data:     LedgerEntryCreate sxemasi.
        actor_id: Kim yaratdi (FK → app_user).
        redis:    Redis klient (idempotentlik uchun).

    Returns:
        Yaratilgan LedgerEntry yozuvi.

    Raises:
        AppError("finance.store_not_found", 404): do'kon topilmasa.
        AppError("finance.invalid_type", 400): tip noto'g'ri (sxema tekshiradi).
        AppError("finance.currency_mismatch", 409): yangi yozuv valyutasi mavjud balans valyutasidan farq qilsa.

    Izoh (version_conflict YO'Q):
        Pessimistik qulf (with_for_update) ishlatiladi — optimistik lock kerak emas.
        balance.version += 1 faqat bookkeeping sifatida qoladi (audit izi).
    """
    # ── 1. Redis idempotentlik (atomik SET NX) ─────────────────────────────
    # IZOH: DB `client_uuid` unique partial index — asosiy idempotentlik himoyasi;
    #       Redis NX — tezkor kesh (GET→SET race oynasini yopadi).
    idem_key: str | None = None
    if data.client_uuid is not None and actor_id is not None and redis is not None:
        idem_key = f"{_IDEM_PREFIX}:{actor_id}:{data.client_uuid}"
        try:
            cached_id = await redis.get(idem_key)
            if cached_id is not None:
                stmt = select(LedgerEntry).where(LedgerEntry.id == uuid.UUID(cached_id))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    return existing
                logger.warning(
                    "record_entry: idem_key=%s yozuv topilmadi, yangi yaratilmoqda",
                    idem_key,
                )
        except Exception as exc:
            logger.warning(
                "record_entry: Redis idempotentlik tekshiruvi muvaffaqiyatsiz "
                "(kalit=%s, xato=%r). Yangi yozuv yaratilmoqda.",
                idem_key, exc,
            )
            idem_key = None

    # ── 2. Do'kon mavjudligi tekshiruvi ─────────────────────────────────────
    store_stmt = select(Store.id).where(
        Store.id == data.store_id,
        Store.deleted_at.is_(None),
    )
    store_result = await db.execute(store_stmt)
    if store_result.scalar_one_or_none() is None:
        raise AppError("finance.store_not_found", status_code=404)

    # ── 3. LedgerEntry INSERT — APPEND-ONLY ─────────────────────────────────
    entry = LedgerEntry(
        store_id=data.store_id,
        type=data.type,
        amount=data.amount,
        currency=data.currency,
        ref_type=data.ref_type,
        ref_id=data.ref_id,
        entry_date=_now(),
        created_by=actor_id,
        client_uuid=data.client_uuid,
        created_at=_now(),
    )
    db.add(entry)
    await db.flush()

    # ── 4. AccountBalance yangilash ──────────────────────────────────────────
    # MUHIM: primary DB sessiyasi (ADR §3.4 — replica kechikishidan saqlanish).
    balance = await _get_or_create_account_balance(db, data.store_id, data.currency)

    # Valyuta nomuvofiqligi tekshiruvi: bir do'konda faqat YAGONA valyuta.
    # Retail asosan UZS; boshqa valyuta kelsa — jim aralashuvni oldini olish uchun xato.
    if balance.currency != data.currency:
        raise AppError(
            "finance.currency_mismatch",
            status_code=409,
            params={
                "existing": balance.currency,
                "incoming": data.currency,
            },
        )

    if data.type == "debit":
        new_balance = balance.balance + data.amount
    else:  # credit
        new_balance = balance.balance - data.amount

    balance.balance = new_balance
    balance.version = balance.version + 1
    balance.last_recalc_at = _now()
    await db.flush()

    # ── 5. Audit + Outbox ──────────────────────────────────────────────────
    after_payload = {
        "id": str(entry.id),
        "store_id": str(data.store_id),
        "type": data.type,
        "amount": str(data.amount),
        "currency": data.currency,
        "balance_after": str(new_balance),
    }
    await _write_audit(db, actor_id, "create", str(entry.id), after=after_payload)
    await _write_outbox(db, str(entry.id), "ledger_entry.created", after_payload)

    # ── 6. Redis kalit saqlash (atomik SET NX EX) ────────────────────────
    # SET key val NX EX 86400 — atomic: faqat mavjud bo'lmasa yozadi (race-safe).
    # Asosiy idempotentlik: DB unique index; Redis — tezkor kesh qatlami.
    if idem_key is not None:
        try:
            await redis.set(idem_key, str(entry.id), nx=True, ex=_IDEM_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "record_entry: Redis kalit saqlash muvaffaqiyatsiz (kalit=%s, xato=%r)",
                idem_key, exc,
            )

    return entry


# ─── _get_or_create_account_balance ──────────────────────────────────────────


async def _get_or_create_account_balance(
    db: AsyncSession,
    store_id: uuid.UUID,
    currency: str,
) -> AccountBalance:
    """
    AccountBalance yozuvini oladi yoki yaratadi (with_for_update qulfi bilan).

    MUHIM: Primary DB sessiyasi bilan chaqirilishi shart (ADR §3.4).
    with_for_update() — bir vaqtda bir nechta so'rov race condition dan saqlaydi.

    Izoh: store_id bo'yicha yagona balans qatorini qulflaydi.
    Valyuta nomuvofiqligi tekshiruvi record_entry() da amalga oshiriladi.
    """
    stmt = (
        select(AccountBalance)
        .where(AccountBalance.store_id == store_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    balance = result.scalar_one_or_none()

    if balance is None:
        balance = AccountBalance(
            store_id=store_id,
            balance=Decimal("0"),
            currency=currency,
            last_recalc_at=_now(),
            version=1,
        )
        db.add(balance)
        await db.flush()

    return balance


# ─── get_balance ──────────────────────────────────────────────────────────────


async def get_balance(
    db: AsyncSession,
    store_id: uuid.UUID,
    user: AppUser | None = None,
) -> AccountBalance:
    """
    Do'kon balansini qaytaradi.

    MUHIM (ADR §3.4):
      Bu funksiya FAQAT primary DB sessiyasi bilan chaqirilishi shart.
      Replica DB kechikishi tufayli moliyaviy qaror noto'g'ri bo'lishi mumkin.
      FastAPI get_db() (primary) dependency ishlatish majburiy.

    IDOR himoya:
      - store roli: faqat o'z store_id ini ko'ra oladi.
        Boshqa store_id → 404 (mavjudlikni oshkor qilmaslik).
      - agent: o'ziga biriktirilgan do'konlar.
      - accountant/administrator: barcha do'konlar.

    Raises:
        AppError("finance.store_not_found", 404): topilmasa yoki ruxsatsiz.
    """
    # Scope tekshiruvi (IDOR himoya)
    if user is not None:
        await _check_store_access(db, store_id, user)

    # Do'kon mavjudligi
    store_stmt = select(Store.id).where(
        Store.id == store_id,
        Store.deleted_at.is_(None),
    )
    store_result = await db.execute(store_stmt)
    if store_result.scalar_one_or_none() is None:
        raise AppError("finance.store_not_found", status_code=404)

    stmt = select(AccountBalance).where(AccountBalance.store_id == store_id)
    result = await db.execute(stmt)
    balance = result.scalar_one_or_none()

    if balance is None:
        # Do'kon mavjud lekin yozuv yo'q — nol balans
        from app.core.uuid7 import uuid7
        balance = AccountBalance(
            id=uuid7(),
            store_id=store_id,
            balance=Decimal("0"),
            currency="UZS",
            last_recalc_at=_now(),
            version=0,
        )

    return balance


# ─── _check_store_access ──────────────────────────────────────────────────────


async def _check_store_access(
    db: AsyncSession,
    store_id: uuid.UUID,
    user: AppUser,
) -> None:
    """
    IDOR himoya: foydalanuvchi berilgan store_id ga kirish huquqini tekshiradi.

    - administrator/accountant: barcha do'konlarga kirish.
    - agent: o'ziga biriktirilgan do'konlar.
    - store: faqat o'z do'koni (Store.user_id == user.id).
    - courier: barcha do'konlar (manzil ko'rish).

    Ruxsatsiz bo'lsa 404 qaytaradi (IDOR: mavjudlikni oshkor qilmaslik).
    """
    role = user.role

    if role in ("administrator", "accountant"):
        # Barcha do'konlarga kirish (branch_id filtrlanmaydi bu yerda)
        return

    if role == "courier":
        # Kuryer manzil uchun barcha do'konlarga kirish
        return

    if role == "store":
        # Faqat o'z do'koni
        from app.models.store import Store
        stmt = select(Store.id).where(
            Store.id == store_id,
            Store.user_id == user.id,
            Store.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise AppError("finance.store_not_found", status_code=404)
        return

    if role == "agent":
        # Agent o'ziga biriktirilgan do'konlar
        allowed_ids = await get_user_store_ids(user, db)
        if store_id not in allowed_ids:
            raise AppError("finance.store_not_found", status_code=404)
        return

    # Noma'lum rol — deny-by-default
    raise AppError("finance.store_not_found", status_code=404)


# ─── list_entries ─────────────────────────────────────────────────────────────


async def list_entries(
    db: AsyncSession,
    *,
    store_id: uuid.UUID | None = None,
    user: AppUser | None = None,
    entry_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[LedgerEntry], int]:
    """
    Paginated buxgalteriya yozuvlari ro'yxati.

    Scope tekshiruvi: foydalanuvchi ruxsatli do'konlarga filtr qo'llaniladi.

    MUHIM: primary DB sessiyasi (ADR §3.4).

    Filtrlar:
      - store_id: do'kon bo'yicha
      - entry_type: yozuv turi bo'yicha (debit | credit)
    """
    conditions = []

    # Scope: foydalanuvchi faqat o'z do'konlarini ko'radi
    if user is not None and store_id is not None:
        await _check_store_access(db, store_id, user)
        conditions.append(LedgerEntry.store_id == store_id)
    elif store_id is not None:
        conditions.append(LedgerEntry.store_id == store_id)
    elif user is not None:
        role = user.role
        if role not in ("administrator", "accountant", "courier"):
            allowed_ids = await get_user_store_ids(user, db)
            if not allowed_ids:
                return [], 0
            conditions.append(LedgerEntry.store_id.in_(allowed_ids))

    if entry_type is not None:
        conditions.append(LedgerEntry.type == entry_type)

    # Count
    count_stmt = select(func.count()).select_from(LedgerEntry)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List
    stmt = (
        select(LedgerEntry)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        stmt = stmt.where(*conditions)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total
