# Davomat moduli texnik qo'llanmasi (T16)

| | |
|---|---|
| **Versiya** | 0.12.0 |
| **Holati** | Yakunlandi — gate PASS (483 test) |
| **Prefix** | `/attendance` |
| **Migratsiya** | `0010_attendance.py` |

---

## Endpointlar

| Metod | Yo'l | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/attendance/check-in` | `attendance:create` | Davomatga kirish qayd etish |
| `POST` | `/attendance/check-out` | `attendance:create` | Davomatdan chiqish qayd etish |
| `GET` | `/attendance` | `attendance:view` | Paginated davomat ro'yxati |

### RBAC jadvali

| Rol | check-in | check-out | list (o'ziniki) | list (barchasi) |
|---|---|---|---|---|
| `agent` | ✅ | ✅ | ✅ | ✗ |
| `courier` | ✅ | ✅ | ✅ | ✗ |
| `administrator` | ✗ | ✗ | — | ✅ |
| `accountant` | ✗ | ✗ | — | ✅ |
| `store` | ✗ | ✗ | ✗ | ✗ |

---

## Qurilma-lokal biometriya modeli (Face ID / Fingerprint)

Tizim qurilma-lokal biometriya ishonch modeliga tayanadi:

1. **Qurilmada**: foydalanuvchi Face ID yoki barmoq izi orqali autentifikatsiya qilinadi. Bu operatsiya faqat qurilmada (iOS Secure Enclave, Android StrongBox) sodir bo'ladi.
2. **Serverga**: foydalanuvchi qiymati, barmoq izi yoki yuz tasviri **hech qachon yuborilmaydi**. Faqat `biometric_verified: true` boolean bayrog'i yuboriladi.
3. **Serverda**: bayroq + GPS faktini yozadi. Biometrik ma'lumot saqlanmaydi.

`biometric_verified=false` kelsa server **403** qaytaradi — bu holat birovning qurilmasidan check-in qilishga urinish deb talqin qilinadi.

Bu yondashuv **Accepted Risk** sifatida hujjatlangan: server klient qurilmasining haqiqiy biometriya natijasini mustaqil tarzda tekshira olmaydi. Agar kelajakda server-tarafli verifikatsiya kerak bo'lsa — `source="admin_override"` bilan alohida administrator endpointi qo'shilishi kerak.

---

## Server-avtoritar vaqt

`check_in_at`, `check_out_at` va `work_date` — klient qiymati qabul qilinmaydi. Ikkala vaqt ham server tomonida `datetime.now(timezone.utc)` bilan belgilanadi (ADR §3.5).

`work_date` UTC bo'yicha hisoblanadi. Ko'p-kunlik timezone muammosi (masalan, UTC+5 da yarim tunda check-in) texnik qarz sifatida qayd etilgan (LOW, kelajak hardening).

---

## RBAC va IDOR himoya

- **agent/courier**: faqat o'z `user_id` bilan davomat ko'ra oladi. `GET /attendance?user_id=<boshqa_id>` → **403** (`attendance.forbidden_user`).
- **administrator/accountant**: istalgan `user_id` bo'yicha filtrlash mumkin.
- `store` roli uchun `attendance:view` ruxsati yo'q — `require_permission` middleware darajasida 403 qaytaradi.

---

## Idempotentlik

`client_uuid` (UUID v4/v7) berilsa:

1. **Redis kalit** (TTL 24 soat): `idem:attendance:check_in:{user_id}:{client_uuid}` — birinchi muvaffaqiyatli yaratishda mavjud davomat ID saqlanadi.
2. **DB darajasi**: `uq_attendance_client_uuid` partial unique index (`client_uuid WHERE IS NOT NULL`, PostgreSQL) — Redis xato bo'lganda ham duplikat oldini oladi.
3. SQLite (test muhiti): partial unique faqat servis darajasida (Postgres'da DB index).

Takroriy so'rovda mavjud davomat yozuvi qaytariladi (yangi yozuv yaratilmaydi).

`check_out` uchun alohida prefix: `idem:attendance:check_out:{user_id}:{client_uuid}`.

---

## GPS koordinatalar

- Format: `Decimal(10, 7)` — 7 kasrga aniqlik (~1 sm darajasida).
- `gps_lat`: `[-90.0000000, 90.0000000]`
- `gps_lng`: `[-180.0000000, 180.0000000]`
- Klient koordinatani yuboradi, server yozadi. Server koordinatani tekshirmaydi (geozone validatsiya kelajak vazifasi).

---

## So'rov/javob sxemalari

### `POST /attendance/check-in`

**So'rov:**
```json
{
  "biometric_verified": true,
  "gps_lat": "41.2995",
  "gps_lng": "69.2401",
  "source": "device_faceid",
  "client_uuid": "01930000-0000-7000-0000-000000000001"
}
```

**Javob (201):**
```json
{
  "id": "01930000-0000-7000-0000-000000000042",
  "user_id": "01900000-0000-7000-0000-000000000007",
  "work_date": "2026-06-17",
  "check_in_at": "2026-06-17T07:00:00+00:00",
  "check_in_gps_lat": "41.2995000",
  "check_in_gps_lng": "69.2401000",
  "check_out_at": null,
  "check_out_gps_lat": null,
  "check_out_gps_lng": null,
  "biometric_verified": true,
  "source": "device_faceid",
  "client_uuid": "01930000-0000-7000-0000-000000000001",
  "version": 1,
  "created_at": "2026-06-17T07:00:00+00:00",
  "updated_at": "2026-06-17T07:00:00+00:00",
  "deleted_at": null
}
```

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 403 | `attendance.biometric_required` | `biometric_verified=false` |
| 409 | `attendance.already_checked_in` | Shu kun ochiq davomat mavjud yoki race |
| 403 | `rbac.permission_denied` | Ruxsatsiz rol |

---

### `POST /attendance/check-out`

**So'rov:**
```json
{
  "gps_lat": "41.2995",
  "gps_lng": "69.2401",
  "client_uuid": "01930000-0000-7000-0000-000000000002"
}
```

**Javob (200):** `AttendanceOut` — `check_out_at` to'ldirilgan holda.

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 404 | `attendance.not_checked_in` | Shu kun ochiq davomat yo'q |

---

### `GET /attendance`

**Query parametrlar:**

| Parametr | Turi | Default | Tavsif |
|---|---|---|---|
| `user_id` | UUID \| null | null | Foydalanuvchi filtri (agent/courier — faqat o'ziniki) |
| `date` | YYYY-MM-DD \| null | null | Sana filtri |
| `limit` | int [1..100] | 20 | Sahifa hajmi |
| `offset` | int ≥0 | 0 | Sahifa ofset |

**Javob (200):**
```json
{
  "items": [ /* AttendanceOut massivi */ ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

---

## curl misollari

```bash
# 1. Davomatga kirish
curl -X POST http://localhost:8000/attendance/check-in \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "biometric_verified": true,
    "gps_lat": "41.2995",
    "gps_lng": "69.2401",
    "source": "device_faceid",
    "client_uuid": "01930000-0000-7000-0000-000000000001"
  }'

# 2. Davomatdan chiqish
curl -X POST http://localhost:8000/attendance/check-out \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "gps_lat": "41.2995",
    "gps_lng": "69.2401",
    "client_uuid": "01930000-0000-7000-0000-000000000002"
  }'

# 3. O'z davomatini ko'rish (agent/courier)
curl "http://localhost:8000/attendance?date=2026-06-17&limit=20" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# 4. Muayyan foydalanuvchi davomati (administrator)
curl "http://localhost:8000/attendance?user_id=01900000-0000-7000-0000-000000000007&date=2026-06-17" \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>"
```

---

## Migratsiya runbook (0010)

```bash
# Upgrade
cd backend
alembic upgrade 0010

# Tekshiruv
psql $DATABASE_URL -c "SELECT COUNT(*) FROM attendance;"
psql $DATABASE_URL -c "\d attendance"

# Downgrade (FAQAT bo'sh DB da)
alembic downgrade 0009
# Agar jadvalda qatorlar bo'lsa — RuntimeError bilan bloklaydi.
```

---

## Ma'lum cheklovlar va texnik qarz

| Cheklov | Ustuvorlik | Rejalashtirilgan |
|---|---|---|
| SQLite (test) da partial unique faqat servis darajasida (`uq_attendance_user_date_open` Postgres'da DB index, SQLite'da yo'q) | LOW | Kelajak hardening |
| `check_out` `IntegrityError` ushlash yo'q (parallel check_out race) — hozir `500` mumkin | LOW | Keyingi sprint |
| GPS decimal_places enforce — Pydantic schema `decimal_places=7` shart, lekin DB `NUMERIC(10,7)` qo'shimcha yumaloqlash qiladi; katta raqam uchun tekshiruv yo'q | LOW | Kuzatish |
| Multi-day timezone: UTC+5 muhitida yarim tunda `work_date` oldingi kun bo'lishi mumkin | LOW | Kelajak hardening |
| Geozone validatsiya (koordinata ma'lum hududda ekanligini tekshirish) | Kelajak | T17+ |
