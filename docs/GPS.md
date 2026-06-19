# GPS Ingest moduli texnik qo'llanmasi (T17)

| | |
|---|---|
| **Versiya** | 0.33.0 |
| **Holati** | Yakunlandi — gate PASS (811 backend test) |
| **Prefix** | `/gps` |
| **Migratsiya** | `0011_gps.py` |
| **DB** | TimescaleDB (alohida `timescale_url`) |

---

## Endpointlar

| Metod | Yo'l | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/gps/ingest` | `gps:create` | Batch GPS nuqtalarni yuklash |
| `GET` | `/gps/track/{delivery_id}` | `gps:view` | Yetkazish marshrutini ko'rish |
| `GET` | `/gps/track` | `gps:view` | Foydalanuvchi + sana bo'yicha marshrut |

### RBAC jadvali

| Rol | ingest | track (o'ziniki) | track (barchasi) |
|---|---|---|---|
| `agent` | ✅ | ✅ | ✗ |
| `courier` | ✅ | ✅ | ✗ |
| `administrator` | ✗ | — | ✅ |
| `accountant` | ✗ | ✗ | ✗ |
| `store` | ✗ | ✗ | ✗ |

---

## TimescaleDB izolyatsiyasi

GPS time-series ma'lumotlari OLTP primary bazadan to'liq ajratilgan (ADR §3.2).

| | OLTP (primary) | GPS (TimescaleDB) |
|---|---|---|
| **URL** | `DATABASE_URL` | `TIMESCALE_URL` |
| **Engine** | `primary_engine` | `timescale_engine` |
| **Session** | `get_db()` | `get_timescale_db()` |
| **Jadval** | `app_user`, `order`, ... | `gps_point` |

`get_timescale_db` — GPS endpointlarining yagona DB dependency'si. OLTP sessiyasi GPS endpointlarida hech qachon ochilmaydi.

### Hypertable va retention

`0011_gps.py` migratsiyasi TimescaleDB extension mavjudligini tekshiradi:

- **Extension mavjud**: `create_hypertable('gps_point', 'recorded_at')` va `add_retention_policy('gps_point', INTERVAL '90 days')` chaqiriladi.
- **Extension yo'q**: `logger.warning` chiqariladi, `gps_point` oddiy Postgres jadvali bo'lib qoladi. Production da timescaledb extension shart.

Migratsiya runbook:

```bash
# TimescaleDB URL orqali ishga tushirish
TIMESCALE_URL=postgresql+asyncpg://user:pass@timescaledb:5432/retail \
  alembic upgrade 0011

# Tekshiruv (timescaledb extension mavjudligida)
psql $TIMESCALE_URL -c "SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'gps_point';"
psql $TIMESCALE_URL -c "SELECT * FROM timescaledb_information.jobs WHERE application_name LIKE '%Retention%';"
```

---

## Ish-soati filtri (ADR §3.7, v0.33.0)

### Qoida

GPS nuqtalar `POST /gps/ingest` orqali qabul qilinadi, lekin **faqat foydalanuvchining aktiv davomat sessiyasi mavjud bo'lganda** TimescaleDB ga saqlanadi. Sessiya yo'q bo'lganda nuqtalar jim tashlab yuboriladi — klientga xato qaytarilmaydi.

Bu qoida xodim ish vaqtidan tashqarida kuzatilishini oldini oladi (maxfiylik kafolati).

### Aktiv sessiya ta'rifi

```sql
SELECT * FROM attendance
WHERE user_id = :user_id
  AND check_in_at <= :server_now
  AND check_out_at IS NULL
  AND deleted_at IS NULL;
```

Yagona natija → aktiv sessiya bor. `None` → sessiya yo'q, barcha nuqtalar filterlandi.

### Config flag

| Parametr | Default | Ta'sir |
|---|---|---|
| `gps_work_hours_filter_enabled` | `True` | `True` — filtr yoqiq; `False` — barcha nuqtalar o'tkaziladi |

`.env` fayliga qo'shish:
```
GPS_WORK_HOURS_FILTER_ENABLED=true
```

### N+1 yo'q (batch boshida bitta SELECT)

Filtr batch darajasida ishlaydi: `ingest()` chaqirilganda barcha nuqtalar bir foydalanuvchiga tegishli bo'lganligi sababli attendance **batch boshida bitta `SELECT`** bilan tekshiriladi. Har nuqta uchun alohida DB so'rovi yo'q.

```python
if work_hours_filter:
    att_db = oltp_db if oltp_db is not None else db
    active_att = await _get_active_attendance(att_db, user_id, now)
    has_active_session = active_att is not None

    if not has_active_session:
        # Barcha nuqtalar jim o'tkazib yuborildi
        return IngestResult(accepted=0, rejected=filtered_count, duplicate=0)
```

### Cross-DB arxitektura

| DB | Maqsad | Session |
|---|---|---|
| OLTP (`oltp_db`, `get_db`) | `attendance` jadvali — sessiya tekshiruvi | `AsyncSessionPrimary` |
| TimescaleDB (`db`, `get_timescale_db`) | `gps_point` jadvali — nuqtalarni saqlash | `AsyncSessionTimescale` |

GPS ingest routeri ikkala sessionni inject qiladi: `oltp_db: AsyncSession = Depends(get_db)` va `db: AsyncSession = Depends(get_timescale_db)`. Test muhitida ikkalasi ham aiosqlite in-memory — bir xil jadvallar mavjud.

### Maxfiylik

Sessiya yo'q bo'lganda:
- Klientga `200 OK` qaytariladi (xato yo'q — shift oynasi oshkor qilinmaydi).
- `IngestResult.rejected` oshadi — klient faqat statistika ko'radi.
- Server log'ida sabab yoziladi: `gps.ingest: ish-soati filtri — aktiv attendance sessiyasi yo'q`.

---

## recorded_at va ingested_at

| Maydon | Manba | Maqsad |
|---|---|---|
| `recorded_at` | Qurilma (klientdan keladi) | GPS nuqtaning haqiqiy vaqti — qurilma oflayn yozgan |
| `ingested_at` | Server (`datetime.now(UTC)`) | Server qabul qilgan vaqt — hisob-kitob uchun |

**Validatsiya qoidalari:**

| Holat | Chegara | Natija |
|---|---|---|
| Kelajak vaqt | `recorded_at > now + 5 daqiqa` | Rad etiladi (`rejected++`) |
| Juda eski | `recorded_at < now - 30 kun` | Rad etiladi (`rejected++`) |
| To'g'ri oraliq | `[now - 30 kun, now + 5 daqiqa]` | Qabul qilinadi (`accepted++`) |

Biznes qaror: 30 kundan eski GPS trek operatsion qiymatga ega emas; 90 kun retention bilan mos (30 < 90 kun). Kelajak vaqt — qurilma soati noto'g'ri yoki ataka belgisi.

---

## IDOR va scope himoyasi

### ingest

`POST /gps/ingest` da `user_id` `current_user.id` dan olinadi — klient so'rovida `user_id` maydoni yo'q. Klient boshqa foydalanuvchi nomidan joylashuv yuklata olmaydi.

### track ko'rish

- **agent/courier**: faqat o'z `user_id` bo'yicha nuqtalarni ko'radi.
  - `GET /gps/track?user_id=<boshqa_id>` → **403** (`gps.forbidden_track`)
  - `GET /gps/track/{delivery_id}` (boshqaning yetkazishi) → **403**
- **administrator**: istalgan `user_id` va `delivery_id` bo'yicha ko'radi.
- **accountant, store**: `gps:view` ruxsati yo'q → **403** (`rbac.permission_denied`).

GPS koordinatalar foydalanuvchiga bog'liq PII. `GpsTrackOut` da `user_id` maydon mavjud — faqat ruxsatli rollar ko'radi.

---

## Idempotentlik

`(user_id, recorded_at)` juftligi `UNIQUE` — bir qurilma bir vaqt muhri bilan faqat bitta nuqta yozadi.

- **PostgreSQL**: `INSERT ... ON CONFLICT (user_id, recorded_at) DO NOTHING` — takror nuqta `duplicate` hisobiga kiritiladi, `rejected` emas.
- **SQLite (test)**: `begin_nested()` savepoint + `IntegrityError` ushlash — sessiya saqlanadi.

`IngestResult.duplicate` ahamiyati: takror so'rovda xato qaytarilmaydi, faqat `duplicate` hisoblagichi oshadi.

---

## Batch va rate-limit

| Chegara | Qiymat | Sabab |
|---|---|---|
| Batch maksimum | 500 nuqta | `settings.gps_max_batch` |
| Batch oshsa | 422 `gps.batch_too_large` | — |
| `POST /gps/ingest` rate-limit | 600 so'rov/daqiqa | Har 100ms da 1 batch — qurilma uchun yetarli |
| `GET /gps/track` rate-limit | 120 so'rov/daqiqa | — |

Rate-limit kaliti: `rate:gps:{endpoint}:{user_id}`. Redis xato bo'lsa graceful degradation (o'tkazib yuboriladi).

---

## So'rov / javob sxemalari

### `POST /gps/ingest`

**So'rov:**
```json
{
  "points": [
    {
      "lat": "41.29950000",
      "lng": "69.24010000",
      "recorded_at": "2026-06-18T08:15:00+05:00",
      "speed": "1.389",
      "delivery_id": null
    },
    {
      "lat": "41.29980000",
      "lng": "69.24050000",
      "recorded_at": "2026-06-18T08:15:10+05:00",
      "speed": "2.100",
      "delivery_id": "01940000-0000-7000-0000-000000000099"
    }
  ]
}
```

**Javob (200):**
```json
{
  "accepted": 2,
  "rejected": 0,
  "duplicate": 0
}
```

`accepted + rejected + duplicate = points` soni.

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 422 | `gps.batch_too_large` | `points` soni > 500 |
| 429 | `sync.rate_limited` | Rate-limit oshdi |
| 403 | `rbac.permission_denied` | Ruxsatsiz rol |

---

### `GET /gps/track/{delivery_id}`

**Query parametrlar:**

| Parametr | Turi | Default | Tavsif |
|---|---|---|---|
| `limit` | int [1..1000] | 100 | Sahifa hajmi |
| `offset` | int ≥0 | 0 | Sahifa ofset |

**Javob (200):**
```json
{
  "items": [
    {
      "id": "01940000-0000-7000-0000-000000000001",
      "user_id": "01900000-0000-7000-0000-000000000007",
      "delivery_id": "01940000-0000-7000-0000-000000000099",
      "lat": "41.29950000",
      "lng": "69.24010000",
      "recorded_at": "2026-06-18T03:15:00+00:00",
      "speed": "1.389",
      "ingested_at": "2026-06-18T03:15:02+00:00",
      "created_at": "2026-06-18T03:15:02+00:00"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 403 | `gps.forbidden_track` | Boshqa foydalanuvchining yetkazishi |
| 429 | `sync.rate_limited` | Rate-limit oshdi |

---

### `GET /gps/track`

**Query parametrlar:**

| Parametr | Turi | Default | Tavsif |
|---|---|---|---|
| `user_id` | UUID \| null | null | Foydalanuvchi filtri (agent/courier — faqat o'ziniki) |
| `date` | YYYY-MM-DD \| null | null | Sana filtri — `recorded_at` kuni |
| `limit` | int [1..1000] | 100 | Sahifa hajmi |
| `offset` | int ≥0 | 0 | Sahifa ofset |

`?date=` filtri `recorded_at >= day_start AND recorded_at < day_end` (range) sifatida bajariladi — `func.date()` wrap ishlatilmaydi (TimescaleDB chunk pruning va indeks uchun).

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 403 | `gps.forbidden_track` | agent/courier boshqa `user_id` so'radi |
| 429 | `sync.rate_limited` | Rate-limit oshdi |

---

## curl misollari

```bash
# 1. Batch GPS ingest (agent/courier)
curl -X POST http://localhost:8000/gps/ingest \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "lat": "41.29950000",
        "lng": "69.24010000",
        "recorded_at": "2026-06-18T08:15:00+05:00",
        "speed": "1.389"
      },
      {
        "lat": "41.29980000",
        "lng": "69.24050000",
        "recorded_at": "2026-06-18T08:15:10+05:00",
        "speed": "2.100"
      }
    ]
  }'
# Javob: {"accepted": 2, "rejected": 0, "duplicate": 0}

# 2. O'z trek tarixi — bugun (agent/courier)
curl "http://localhost:8000/gps/track?date=2026-06-18&limit=200" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# 3. Boshqa foydalanuvchi treki (administrator)
curl "http://localhost:8000/gps/track?user_id=01900000-0000-7000-0000-000000000007&date=2026-06-18" \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>"

# 4. Yetkazish marshrutini ko'rish
curl "http://localhost:8000/gps/track/01940000-0000-7000-0000-000000000099" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## Migratsiya runbook (0011)

```bash
# TimescaleDB URL ko'rsatib upgrade
cd backend
TIMESCALE_URL=postgresql+asyncpg://user:pass@timescaledb:5432/retail \
  alembic upgrade 0011

# Tekshiruv — jadval yaratilganmi
psql $TIMESCALE_URL -c "SELECT COUNT(*) FROM gps_point;"
psql $TIMESCALE_URL -c "\d gps_point"

# TimescaleDB hypertable tekshiruvi (extension mavjud bo'lsa)
psql $TIMESCALE_URL -c \
  "SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name = 'gps_point';"

# Retention policy tekshiruvi
psql $TIMESCALE_URL -c \
  "SELECT * FROM timescaledb_information.jobs WHERE application_name LIKE '%Retention%';"

# Downgrade (FAQAT bo'sh DB da)
alembic downgrade 0010
# Agar jadvalda qatorlar bo'lsa — RuntimeError bilan bloklaydi.
```

**TimescaleDB extension mavjud bo'lmagan holat:** Migratsiya muvaffaqiyatli o'tadi, lekin `gps_point` oddiy Postgres jadvali bo'lib qoladi. Production da qo'lda qo'shish:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
SELECT create_hypertable('gps_point', 'recorded_at', if_not_exists => TRUE);
SELECT add_retention_policy('gps_point', INTERVAL '90 days', if_not_exists => TRUE);
```

---

## Ma'lum cheklovlar va texnik qarz

| Cheklov | Ustuvorlik | Rejalashtirilgan |
|---|---|---|
| `alembic upgrade 0011` — `TIMESCALE_URL` alohida env o'zgaruvchisi kerak; standart `alembic.ini` `DATABASE_URL` ishlatadi. Infra avtomatlashtirish kerak | MEDIUM | Kelajak sprint (infra) |
| ~~ADR §3.7 work-hours GPS filter — agent/courier GPS ma'lumotlari faqat attendance shift oynasida (`check_in_at`–`check_out_at`) ko'rinishi kerak~~ **✅ Hal qilindi (v0.33.0 — `gps_work_hours_filter_enabled`, batch boshida bitta SELECT, cross-DB)** | — | — |
| `delivery_id` T18 da FK bo'ladi — hozir faqat `UUID nullable`, referential integrity yo'q | — | T18 |
| PostgreSQL `rowcount=-1` holati (asyncpg ba'zan rowcount qaytarmaydi) — `accepted` to'liq aniq hisoblana olmaydi; log orqali kuzatiladi | LOW | Kuzatish |
