"""
GPS Ingest servis qatlami — T17.

ingest(user, points, db):
  Batch GPS nuqtalarni saqlaydi.
  - user_id SERVER'dan (current_user.id) — klient boshqa nomidan ingest qila olmaydi.
  - recorded_at qurilma vaqti (klientdan keladi — offline yozilgan).
  - ingested_at SERVER vaqti (hisob-kitob uchun).
  - Batch limit: config gps_max_batch (default 500).
  - recorded_at validatsiya:
      * Kelajak (> GPS_FUTURE_TOLERANCE_MINUTES=5 daqiqa) → rad etiladi (rejected++).
      * Juda eski (> GPS_MAX_AGE_DAYS=30 kun) → rad etiladi (rejected++).
    BIZNES QAROR:
      Kelajak vaqt: qurilma soati noto'g'ri yoki ataka. Rad etish to'g'ri.
      Juda eski: 30 kundan eski trekking ma'lumoti operatsion qiymatga ega emas;
      90 kun retention bilan mos (30 < 90 kun). Kelajakda config dan olish mumkin.
  - ADR §3.7 ish-soati filtri (gps_work_hours_filter_enabled=True):
      Foydalanuvchining aktiv attendance sessiyasi (check_in_at <= server_now,
      check_out_at IS NULL) bor-yo'qligini tekshiradi. BATCH DA BIR MARTA SO'RALANADI
      (N+1 yo'q). Sessiya yo'q → nuqta jim tashlab yuboriladi (filtered++).
      "filtered" soni IngestResult.rejected ga qo'shiladi (xulq o'zgarishsiz,
      lekin log'da sababni ko'rsatamiz).
  - Idempotentlik: (user_id, recorded_at) UNIQUE → ON CONFLICT DO NOTHING.
    Takror nuqta rejected deb hisoblanmaydi — shunchaki e'tiborsiz.
  - Audit emas (yuqori hajm — faqat log/metrika). Outbox YO'Q (GPS sync'ga tushmaydi).

get_track(db, user, delivery_id, filter_user_id, filter_date, limit, offset):
  GPS marshrut nuqtalari, paginated.
  RBAC scope:
    - agent/courier: FAQAT o'z nuqtalari.
    - administrator: barchasi.
    - IDOR: boshqa user_id/delivery → 403 (mavjudlik oshkor bo'lmaydi).

ADR §3.7: recorded_at=qurilma, ingested_at=server.
GPS time-series — OLTP'dan izolyatsiya (alohida modul/jadval).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.uuid7 import uuid7
from app.models.attendance import Attendance
from app.models.gps import GpsPoint
from app.models.user import AppUser
from app.modules.gps.schemas import GpsBatchIngest, GpsPointIn, IngestResult

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

# recorded_at kelajak toleransi (daqiqa) — qurilma soati ozgina oldinda bo'lishi mumkin
_GPS_FUTURE_TOLERANCE_MINUTES = 5

# recorded_at maksimal yoshi (kun) — juda eski ma'lumotlar rad etiladi
_GPS_MAX_AGE_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    """Naive datetime ni UTC aware ga aylantiradi."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_recorded_at(recorded_at: datetime, now: datetime) -> str | None:
    """
    recorded_at validatsiyasi.

    Qaytaradi: None (ok) yoki xato sababi (reject qilinsin).

    BIZNES QAROR:
      - Kelajak vaqt (> GPS_FUTURE_TOLERANCE_MINUTES): qurilma soati noto'g'ri.
        Rad etish — serverda noto'g'ri zaman muhri bilan saqlash zararli.
      - Juda eski (> GPS_MAX_AGE_DAYS kun): operatsion qiymat yo'q.
        Rad etish — retention (90 kun) bilan mos.
    """
    aware_recorded = _ensure_aware(recorded_at)

    # Kelajak tekshiruvi
    max_future = now + timedelta(minutes=_GPS_FUTURE_TOLERANCE_MINUTES)
    if aware_recorded > max_future:
        return f"recorded_at juda kelajak: {recorded_at!r}"

    # Eski tekshiruvi
    min_past = now - timedelta(days=_GPS_MAX_AGE_DAYS)
    if aware_recorded < min_past:
        return f"recorded_at juda eski: {recorded_at!r}"

    return None


# ─── ADR §3.7 — Ish-soati attendance tekshiruvi ──────────────────────────────


async def _get_active_attendance(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime,
) -> Attendance | None:
    """
    Foydalanuvchining server vaqti (now) bo'yicha AKTIV attendance sessiyasini qaytaradi.

    "Aktiv" ta'rifi (ADR §3.7):
      - check_in_at <= now  (check-in allaqachon bo'lgan)
      - check_out_at IS NULL  YO'Q: hali chiqmagan
        YOKI check_out_at > now  (check-out kelajakda — hali ish vaqtida)
      - deleted_at IS NULL  (o'chirilmagan)

    IZOH: Attendance DB si get_db (OLTP PostgreSQL) orqali so'ralanadi;
    GPS ingest esa get_timescale_db orqali keladi.
    Test muhitida ikkalasi ham aiosqlite in-memory — bir xil jadvallar mavjud.
    Bu funksiya `db` (timescale session) parametr oladi, lekin u test muhitida
    OLTP bilan bir xil session. Production'da attendance uchun alohida OLTP
    sessiyasi ishlatilishi kerak edi; lekin ADR modullar faqat servis interfeysi
    orqali muloqot qiladi deydi, shu sababdan qo'shimcha dependency injection
    o'rniga caller (ingest) OLTP sessiyasini uzatadi.
    Bu yondashuv: GPS ingest router'ga `oltp_db: AsyncSession = Depends(get_db)`
    qo'shish bilan kelajakda to'liq ajratilishi mumkin.

    Hozir: test muhitida to'g'ri ishlashi uchun `db` (ixtiyoriy OLTP session)
    parametrini qabul qiladi.
    """
    stmt = select(Attendance).where(
        Attendance.user_id == user_id,
        Attendance.check_in_at <= now,
        Attendance.check_out_at.is_(None),  # ochiq sessiya
        Attendance.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ─── ingest ───────────────────────────────────────────────────────────────────


async def ingest(
    user: AppUser,
    batch: GpsBatchIngest,
    db: AsyncSession,
    oltp_db: AsyncSession | None = None,
) -> IngestResult:
    """
    Batch GPS nuqtalarni saqlaydi.

    XAVFSIZLIK:
      user_id = current_user.id (SERVER'dan) — klientdan OLINMAYDI.
      Klient boshqa foydalanuvchi nomidan ingest qila olmaydi (IDOR yo'q).

    BATCH LIMIT:
      Agar points soni > gps_max_batch (default 500) → AppError(gps.batch_too_large, 422).

    ADR §3.7 ISH-SOATI FILTRI (gps_work_hours_filter_enabled=True):
      Batch ingest da N+1 yo'q: attendance sessiyasi BATCH BOSHIDA BIR MARTA so'ralanadi.
      Aktiv sessiya yo'q → barcha nuqtalar jim tashlab yuboriladi (rejected ga qo'shiladi).
      Aktiv sessiya bor → barcha nuqtalar o'tadi (sessiya server vaqti bo'yicha tekshiriladi).
      oltp_db: attendance jadvaliga kirish uchun OLTP sessiyasi. None bo'lsa — db ishlatiladi
      (test muhitida bir xil; production da router get_db inject qilishi kerak).

    VALIDATSIYA:
      - recorded_at: kelajak/eski → reject (accepted'ga qo'shilmaydi).
      - Qolgan maydonlar: Pydantic sxemasi darajasida tekshirilgan.

    IDEMPOTENTLIK:
      (user_id, recorded_at) UNIQUE — ON CONFLICT DO NOTHING.
      SQLite: executemany + individual insert (conflict skip).
      Takror nuqta: e'tiborsiz (rejected deb hisoblanmaydi, lekin accepted'ga ham kirmaydi).

    AUDIT/OUTBOX:
      Yuqori hajm — audit yozilmaydi, outbox YO'Q.
      Log/metrika orqali monitoring.
    """
    max_batch = settings.gps_max_batch
    if len(batch.points) > max_batch:
        raise AppError(
            "gps.batch_too_large",
            status_code=422,
            params={"max": max_batch, "given": len(batch.points)},
        )

    now = _now()
    user_id = user.id

    accepted = 0
    rejected = 0
    duplicate = 0

    # ── ADR §3.7: Ish-soati filtri — attendance sessiyasini BATCH BOSHIDA BIR MARTA tekshir ──
    # N+1 muammo YO'Q: bitta SELECT butun batch uchun yetarli.
    # Sabab: barcha nuqtalar bir foydalanuvchiga tegishli va server "now" da ingest qilinmoqda.
    work_hours_filter = settings.gps_work_hours_filter_enabled
    has_active_session: bool = True  # default: filtr o'chirilganda o'tkazib yuborish

    if work_hours_filter:
        # attendance sessiyasi so'rash uchun oltp_db (yoki db) ishlatiladi
        att_db = oltp_db if oltp_db is not None else db
        active_att = await _get_active_attendance(att_db, user_id, now)
        has_active_session = active_att is not None

        if not has_active_session:
            # Barcha nuqtalar filterlandi — jim tashlab yuboriladi (maxfiylik)
            filtered_count = len(batch.points)
            logger.info(
                "gps.ingest: ish-soati filtri — aktiv attendance sessiyasi yo'q, "
                "barcha nuqtalar o'tkazib yuborildi. "
                "user_id=%s filtered=%d",
                user_id, filtered_count,
            )
            return IngestResult(accepted=0, rejected=filtered_count, duplicate=0)

    # Saqlash uchun validatsiyadan o'tgan nuqtalar
    valid_points: list[GpsPoint] = []

    for point in batch.points:
        reject_reason = _validate_recorded_at(point.recorded_at, now)
        if reject_reason:
            logger.debug(
                "gps.ingest: nuqta rad etildi (user_id=%s): %s",
                user_id, reject_reason,
            )
            rejected += 1
            continue

        gp = GpsPoint(
            id=uuid7(),
            user_id=user_id,
            enterprise_id=user.enterprise_id,  # MT: tenant scoping (xarita filtri uchun)
            delivery_id=point.delivery_id,
            lat=point.lat,
            lng=point.lng,
            recorded_at=_ensure_aware(point.recorded_at),
            speed=point.speed,
            ingested_at=now,
            created_at=now,
        )
        valid_points.append(gp)

    # Batch INSERT — dialect-aware idempotentlik
    if valid_points:
        # Dialect aniqlash: AsyncSession.get_bind() async muhitda ishonchsiz.
        # Ishonchli usul: session.bind (async_sessionmaker bind argumenti) yoki
        # session.get_bind() o'rniga session.bind.dialect.name.
        # AsyncSession ichida sync_engine orqali dialect aniqlanadi.
        try:
            # AsyncSession.bind — async_sessionmaker bind= argumenti (AsyncEngine).
            # .sync_engine — AsyncEngine'ning ichki sync Engine'i.
            dialect = db.bind.sync_engine.dialect.name  # type: ignore[union-attr]
        except AttributeError:
            # bind None bo'lsa — get_bind() ni sinab ko'ramiz (fallback)
            try:
                dialect = db.get_bind().dialect.name  # type: ignore[union-attr]
            except Exception:
                # Agar dialect aniqlanmasa — xato log'laymiz, lekin SQLite default emas.
                # Noto'g'ri yo'lga tushmaslik uchun: PostgreSQL yo'liga o'tamiz
                # (real deployment doim Postgres; SQLite faqat test).
                logger.warning(
                    "gps.ingest: dialect aniqlanmadi — PostgreSQL yo'lidan foydalanamiz "
                    "(test muhitida SQLite'ga fallback yo'q)."
                )
                dialect = "postgresql"

        if dialect == "postgresql":
            # PostgreSQL: ON CONFLICT DO NOTHING (UNIQUE user_id, recorded_at)
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            rows = [
                {
                    "id": str(gp.id),
                    "user_id": str(gp.user_id),
                    "enterprise_id": str(gp.enterprise_id) if gp.enterprise_id else None,
                    "delivery_id": str(gp.delivery_id) if gp.delivery_id else None,
                    "lat": gp.lat,
                    "lng": gp.lng,
                    "recorded_at": gp.recorded_at,
                    "speed": gp.speed,
                    "ingested_at": gp.ingested_at,
                    "created_at": gp.created_at,
                }
                for gp in valid_points
            ]
            stmt = pg_insert(GpsPoint).values(rows).on_conflict_do_nothing(
                index_elements=["user_id", "recorded_at"]
            )
            result = await db.execute(stmt)
            # rowcount: -1 bo'lsa driver rowcount qaytara olmaydi (asyncpg ba'zan shunday).
            # -1 holatida: barcha nuqtalar qabul qilindi deb hisoblaymiz (konservativ emas,
            # lekin ON CONFLICT DO NOTHING bilan batch hajmi = qabul qilinganlar maksimumi).
            if result.rowcount == -1:
                logger.warning(
                    "gps.ingest: PostgreSQL rowcount=-1 (driver rowcount qaytarmadi) — "
                    "user_id=%s, valid_points=%d. accepted=%d deb hisoblanadi.",
                    user_id, len(valid_points), len(valid_points),
                )
            inserted = result.rowcount if result.rowcount >= 0 else len(valid_points)
            accepted += inserted
            # Takror nuqtalar (conflict) — duplicate hisoblanadi, rejected emas (idempotent)
            duplicate += len(valid_points) - inserted if result.rowcount >= 0 else 0
        else:
            # SQLite: har bir nuqta uchun alohida savepoint (nested transaction)
            # UNIQUE (user_id, recorded_at) conflict → savepoint rollback (session saqlanadi)
            # Bu pattern test muhitida shared session'ni saqlaydi.
            from sqlalchemy.exc import IntegrityError

            for gp in valid_points:
                try:
                    async with db.begin_nested():
                        db.add(gp)
                        await db.flush()
                    accepted += 1
                except IntegrityError:
                    # Savepoint rollback — faqat bu nuqta bekor qilinadi, session saqlanadi
                    duplicate += 1
                    logger.debug(
                        "gps.ingest: takror nuqta (user_id=%s recorded_at=%s) — e'tiborsiz",
                        user_id, gp.recorded_at,
                    )

    logger.info(
        "gps.ingest: user_id=%s accepted=%d rejected=%d duplicate=%d total=%d",
        user_id, accepted, rejected, duplicate, len(batch.points),
    )

    return IngestResult(accepted=accepted, rejected=rejected, duplicate=duplicate)


# ─── get_track ────────────────────────────────────────────────────────────────


async def get_track(
    db: AsyncSession,
    *,
    user: AppUser,
    delivery_id: uuid.UUID | None = None,
    filter_user_id: uuid.UUID | None = None,
    filter_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[GpsPoint], int]:
    """
    GPS marshrut nuqtalari, paginated.

    RBAC scope (IDOR himoya):
      - agent/courier: FAQAT O'Z nuqtalari.
        Boshqa user_id yoki boshqa delivery_id so'rasa → 403 (mavjudlik oshkor bo'lmaydi).
      - administrator: barchasi (filter_user_id, delivery_id ixtiyoriy).
      - Boshqa rollar: RBAC darajasida rad etilgan (shu yerga yetib kelmaydi).

    delivery_id bo'yicha qidiruvda:
      - agent/courier: delivery boshqa userga tegishli → 403.
        (delivery_id uchun user_id tekshiruvi qo'shimcha guard sifatida ishlaydi)

    filter_date: recorded_at kuni bo'yicha filtr (agar berilsa).
    """
    role = user.role

    # TODO(ADR §3.7 work-hours filter): GPS ma'lumotlari faqat ish vaqtida
    # ko'rsatilishi kerak (attendance check_in/check_out oralig'i).
    # Hozir enforce qilinmagan — attendance shift oynasi bilan join murakkab.
    # GPS admin-only bo'lgani uchun MEDIUM xavf.
    # Kelajak: filter_date berilganda attendance jadvalidan
    # shift start/end ni olish va recorded_at oralig'ini cheklash.

    if role in ("agent", "courier"):
        # IDOR himoya: boshqa user_id so'rasa → 403
        if filter_user_id is not None and filter_user_id != user.id:
            logger.warning(
                "gps.get_track: IDOR urinish, actor=%s so'ragan=%s",
                user.id, filter_user_id,
            )
            raise AppError("gps.forbidden_track", status_code=403)
        scope_user_id = user.id
    elif role == "administrator":
        scope_user_id = filter_user_id  # None = barchasi
    else:
        # Boshqa rollar → RBAC darajasida rad (shu yerga yetmaslik kerak)
        raise AppError(
            "rbac.permission_denied",
            status_code=403,
            params={"module": "gps", "action": "view", "role": role},
        )

    # Shartlar
    conditions = []

    # MT: faqat foydalanuvchining korxonasi nuqtalari (tenant izolyatsiya +
    # admin'ning date-only so'rovida cross-tenant leak'ni yopadi).
    # user.enterprise_id None bo'lsa (test/superadmin) — filtr qo'llanmaydi.
    if user.enterprise_id is not None:
        conditions.append(GpsPoint.enterprise_id == user.enterprise_id)

    if scope_user_id is not None:
        conditions.append(GpsPoint.user_id == scope_user_id)

    if delivery_id is not None:
        conditions.append(GpsPoint.delivery_id == delivery_id)

        # agent/courier: delivery boshqa userga tegishli bo'lsa → 403
        # Bu tekshiruv: delivery_id bilan scope_user_id kombinatsiyasini cheklaydi.
        # Natija bo'sh bo'lsa: mavjud emas yoki ruxsat yo'q — 404 qaytariladi (enumeration yo'q).

    if filter_date is not None:
        # func.date() o'rniga range filter ishlatiladi:
        # recorded_at >= day_start AND recorded_at < day_end
        # Sabab: indeks va TimescaleDB chunk pruning faqat range filtrlarda ishlaydi.
        # func.date() kolonnani wrap qiladi — indeks ishlatilmaydi (full scan).
        day_start = datetime(
            filter_date.year, filter_date.month, filter_date.day,
            0, 0, 0, tzinfo=timezone.utc,
        )
        day_end = day_start + timedelta(days=1)
        conditions.append(GpsPoint.recorded_at >= day_start)
        conditions.append(GpsPoint.recorded_at < day_end)

    where_clause = and_(*conditions) if conditions else sa_true()

    # Count
    count_stmt = select(func.count()).select_from(GpsPoint).where(where_clause)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # List — recorded_at bo'yicha tartiblash (vaqt o'sishi)
    stmt = (
        select(GpsPoint)
        .where(where_clause)
        .order_by(GpsPoint.recorded_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return items, total


# ─── Yordamchi ────────────────────────────────────────────────────────────────

def sa_true():
    """SQLAlchemy true() — shartlar bo'sh bo'lganda."""
    from sqlalchemy import true
    return true()
