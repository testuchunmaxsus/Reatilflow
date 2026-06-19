# Yetkazib berish moduli texnik qo'llanmasi (T18)

| | |
|---|---|
| **Versiya** | 0.14.0 |
| **Holati** | Yakunlandi — gate PASS (554 test) |
| **Prefix** | `/delivery` |
| **Migratsiya** | `0012_delivery.py` |
| **DB** | OLTP primary (PostgreSQL) |

---

## Endpointlar

| Metod | Yo'l | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/delivery` | `delivery:create` | Kuryer tayinlash (yangi yetkazish) |
| `PATCH` | `/delivery/{id}/status` | `delivery:edit` | Holat o'zgartirish |
| `POST` | `/delivery/{id}/proof-photo` | `delivery:edit` | Dalil rasmi yuklash |
| `GET` | `/delivery` | `delivery:view` | Paginated ro'yxat |
| `GET` | `/delivery/{id}` | `delivery:view` | Bitta yetkazish |

### RBAC jadvali

| Rol | yaratish | holat/foto | ko'rish |
|---|---|---|---|
| `administrator` | ✅ | ✅ | ✅ (barchasi) |
| `agent` | ✅ (o'z do'konlari) | ✗ | ✅ (o'z buyurtmalari) |
| `courier` | ✗ | ✅ (faqat o'ziniki) | ✅ (faqat o'ziniki) |
| `accountant` | ✗ | ✗ | ✅ (barchasi) |
| `store` | ✗ | ✗ | ✅ (o'z buyurtmalari) |

---

## Holat mashinasi

Holat o'tishlari server-avtoritar: klient faqat maqsad holatni (`status`) yuboradi; serverda `VALID_TRANSITIONS` diktati qo'llaniladi. Noto'g'ri o'tish → **422** (`delivery.invalid_transition`).

```
assigned ──────► started ──────► delivering ──────► delivered
    │               │                 │                (terminal)
    └──► failed ◄───┘                 └──► failed
         (terminal)
```

| Joriy holat | Mumkin o'tishlar |
|---|---|
| `assigned` | `started`, `failed` |
| `started` | `delivering`, `failed` |
| `delivering` | `delivered`, `failed` |
| `delivered` | — (terminal) |
| `failed` | — (terminal) |

Terminal holatdan (`delivered`, `failed`) hech qanday o'tish yo'q. Terminal holatdan keyin bir xil buyurtmaga yangi yetkazish tayinlash mumkin (aktiv yetkazish tekshiruvi terminal holatlarni hisobga olmaydi).

---

## GPS bog'lanishi

Delivery moduli ikkita GPS qatlamiga bog'liq:

### Key nuqtalar (delivery jadvali)

`delivery` jadvalida faqat ikki muhim GPS koordinat juftligi saqlanadi:

| Maydon | Holat | Tavsif |
|---|---|---|
| `start_gps_lat` / `start_gps_lng` | `started` | Kuryer yo'lga chiqqan joy |
| `delivery_gps_lat` / `delivery_gps_lng` | `delivered` | Yetkazib berilgan joy |

Bu koordinatlar `PATCH /delivery/{id}/status` so'rovida `gps_lat`/`gps_lng` ixtiyoriy maydonlar orqali yoziladi.

### To'liq GPS trek (TimescaleDB)

Kuryer marshrutining to'liq koordinat ketma-ketligi `gps_point` jadvalida (TimescaleDB, alohida baza) saqlanadi. Delivery jadvalidan cross-DB FK yo'q — bog'lanish faqat `GpsPoint.delivery_id` UUID reference orqali.

Trek o'qish endpointi:

```
GET /gps/track?delivery_id={delivery_id}
```

`DeliveryOut.gps_track_url` maydoni ushbu URL ni avtomatik qaytaradi.

---

## RBAC va IDOR

### Yaratish (`POST /delivery`)

- `administrator`: istalgan buyurtmaga kuryer tayinlay oladi.
- `agent`: faqat **o'z do'konlariga** tegishli buyurtmalarga kuryer tayinlay oladi. Boshqa do'kon buyurtmasi → **404** (`delivery.order_not_found`).
- `store`, `courier`, `accountant`: ruxsat yo'q → **403**.

Yaratishda buyurtma holati `confirmed`, `packed`, yoki `delivering` bo'lishi shart. Boshqa holat → **422** (`delivery.invalid_transition`).

Tayinlanadigan foydalanuvchi `role=courier` va `is_active=true` bo'lishi shart. Aks holda → **422** (`delivery.not_courier`).

### Holat va foto o'zgartirish (`PATCH`, `POST /proof-photo`)

- `courier`: FAQAT o'ziga (`courier_id == current_user.id`) tayinlangan yetkazishni o'zgartiradi. Boshqa kuryerning yetkazishi → **403** (`delivery.forbidden`).
- `administrator`: istalgan yetkazishni o'zgartiradi.

### Ko'rish (`GET /delivery`, `GET /delivery/{id}`)

| Rol | Qamrov |
|---|---|
| `administrator` | Barchasi; `branch_id` bo'yicha ixtiyoriy filtr |
| `accountant` | Barchasi; `branch_id` bo'yicha ixtiyoriy filtr |
| `agent` | Faqat o'z do'konlari buyurtmalarining yetkazishlari |
| `store` | Faqat o'z buyurtmalarining yetkazishlari |
| `courier` | Faqat o'ziga tayinlangan yetkazishlar |

Ruxsatsiz kirish `GET /delivery/{id}` uchun **404** qaytaradi (mavjudlikni oshkor qilmaslik).

---

## Bir buyurtmaga bitta aktiv yetkazish

Bir vaqtning o'zida bir buyurtmada faqat bitta aktiv (terminal bo'lmagan) yetkazish bo'lishi mumkin.

**Aktiv** — `status NOT IN ('delivered', 'failed') AND deleted_at IS NULL`.

Himoya ikki qatlamli:

1. **Servis tekshiruvi** (`create_delivery()` qadam 3c): `INSERT` dan oldin aktiv yetkazish mavjudligi tekshiriladi → **409** (`delivery.already_assigned`).
2. **Postgres partial unique index** (`uq_delivery_order_id_active_partial`): `CREATE UNIQUE INDEX ... ON delivery (order_id) WHERE status NOT IN ('delivered', 'failed') AND deleted_at IS NULL` — servis tekshiruvi race window da o'tib ketsa, DB `IntegrityError` ko'taradi → servis **409** qaytaradi.

SQLite (test muhiti) partial unique `WHERE` shartini qo'llab-quvvatlamaydi; servis tekshiruvi yetarli (testlar seriyali ishlaydi).

Terminal holatdan keyin (masalan, `failed`) bir xil buyurtmaga yangi `POST /delivery` chaqirilishi mumkin — eski terminal yetkazish aktiv hisoblanmaydi.

---

## proof_photo

`POST /delivery/{id}/proof-photo` so'rovi `multipart/form-data` formatida fayl qabul qiladi.

- **Ruxsat etilgan formatlar**: JPEG (`FF D8 FF`), PNG (`89 50 4E 47`), WebP (`52 49 46 46`) — magic-byte orqali tekshiriladi.
- **Maksimal hajm**: 5 MB.
- **SVG va HTML**: rad etiladi.
- Kontent-type headeriga ishonilmaydi; faylning birinchi baytlari tekshiriladi.
- Yuklash muvaffaqiyatli bo'lsa `proof_photo_url` (MinIO/S3 URL) `delivery` yozuviga saqlanadi.
- Xato holatlari: **422** (`delivery.invalid_photo`) noto'g'ri format; **503** (`delivery.storage_error`) storage xatosi.

Idempotentlik: bir xil yetkazishga foto bir necha marta yuklanishi mumkin — har safar URL yangilanadi.

---

## Idempotentlik va version lock

### client_uuid idempotentlik

`POST /delivery` da `client_uuid` (ixtiyoriy UUID) taqdim etilsa:

1. Redis `SET NX` kaliti `idem:delivery:create:{actor_id}:{client_uuid}` (TTL 24 soat) — mavjud bo'lsa keshdan qaytariladi.
2. Postgres partial unique index `uq_delivery_client_uuid_partial` — DB darajali kafolat.
3. `IntegrityError` → mavjud `client_uuid` bilan yetkazish qaytariladi (graceful).

### version optimistik lock

`PATCH /delivery/{id}/status` so'rovida `version` maydoni joriy versiyaga mos kelishi shart. Mos kelmasa → **409** (`orders.version_conflict`).

`SELECT ... FOR UPDATE` (Postgres) `update_status()` da parallel holat yangilanishlarini seriallashtiradi.

---

## So'rov / javob sxemalari

### `POST /delivery`

**So'rov:**
```json
{
  "order_id": "01940000-0000-7000-0000-000000000010",
  "courier_id": "01900000-0000-7000-0000-000000000042",
  "client_uuid": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Javob (201):**
```json
{
  "id": "01950000-0000-7000-0000-000000000001",
  "order_id": "01940000-0000-7000-0000-000000000010",
  "courier_id": "01900000-0000-7000-0000-000000000042",
  "status": "assigned",
  "assigned_at": "2026-06-18T07:00:00+00:00",
  "started_at": null,
  "start_gps_lat": null,
  "start_gps_lng": null,
  "delivered_at": null,
  "delivery_gps_lat": null,
  "delivery_gps_lng": null,
  "proof_photo_url": null,
  "failure_reason": null,
  "branch_id": null,
  "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "version": 1,
  "created_at": "2026-06-18T07:00:00+00:00",
  "updated_at": "2026-06-18T07:00:00+00:00",
  "deleted_at": null,
  "gps_track_url": "/gps/track?delivery_id=01950000-0000-7000-0000-000000000001"
}
```

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 404 | `delivery.order_not_found` | Buyurtma topilmadi yoki agent scope da emas |
| 409 | `delivery.already_assigned` | Buyurtmada aktiv yetkazish mavjud |
| 422 | `delivery.invalid_transition` | Buyurtma holati ruxsat etilmagan |
| 422 | `delivery.not_courier` | Tayinlanadigan foydalanuvchi kuryer emas yoki nofaol |
| 403 | `rbac.permission_denied` | Ruxsatsiz rol |

---

### `PATCH /delivery/{id}/status`

**So'rov (assigned → started, GPS bilan):**
```json
{
  "status": "started",
  "version": 1,
  "gps_lat": "41.29950000",
  "gps_lng": "69.24010000"
}
```

**So'rov (delivering → delivered, GPS va foto ko'rsatgichi bilan):**
```json
{
  "status": "delivered",
  "version": 3,
  "gps_lat": "41.30100000",
  "gps_lng": "69.24200000"
}
```

**So'rov (istalgan holat → failed):**
```json
{
  "status": "failed",
  "version": 2,
  "failure_reason": "Mijoz uyda yo'q edi"
}
```

**Xato holatlari:**

| HTTP | `message_key` | Sabab |
|---|---|---|
| 404 | `delivery.not_found` | Yetkazish topilmadi |
| 403 | `delivery.forbidden` | IDOR: boshqa kuryerning yetkazishi |
| 409 | `orders.version_conflict` | `version` mos kelmaydi |
| 422 | `delivery.invalid_transition` | Noqonuniy holat o'tishi |

---

### `POST /delivery/{id}/proof-photo`

**So'rov**: `multipart/form-data`, maydon nomi `file`.

```bash
curl -X POST http://localhost:8000/delivery/{id}/proof-photo \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "file=@/path/to/photo.jpg"
```

**Javob (200)**: yangilangan `DeliveryOut` (`proof_photo_url` to'ldirilgan holda).

---

### `GET /delivery`

**Query parametrlar:**

| Parametr | Turi | Default | Tavsif |
|---|---|---|---|
| `status` | string \| null | null | Holat bo'yicha filtr |
| `courier_id` | UUID \| null | null | Kuryer bo'yicha filtr |
| `order_id` | UUID \| null | null | Buyurtma bo'yicha filtr |
| `date_from` | ISO 8601 \| null | null | `assigned_at >=` filtr |
| `date_to` | ISO 8601 \| null | null | `assigned_at <=` filtr |
| `limit` | int [1..100] | 20 | Sahifa hajmi |
| `offset` | int ≥0 | 0 | Sahifa ofset |

**Javob (200):**
```json
{
  "items": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

## curl misollari

```bash
# 1. Kuryer tayinlash (agent yoki admin)
curl -X POST http://localhost:8000/delivery \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "01940000-0000-7000-0000-000000000010",
    "courier_id": "01900000-0000-7000-0000-000000000042",
    "client_uuid": "550e8400-e29b-41d4-a716-446655440000"
  }'
# Javob: 201 DeliveryOut, status="assigned"

# 2. Kuryer yo'lga chiqdi (started, GPS bilan)
curl -X PATCH http://localhost:8000/delivery/01950000-0000-7000-0000-000000000001/status \
  -H "Authorization: Bearer <COURIER_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status": "started", "version": 1, "gps_lat": "41.29950000", "gps_lng": "69.24010000"}'

# 3. Yetkazildi (delivered, GPS bilan)
curl -X PATCH http://localhost:8000/delivery/01950000-0000-7000-0000-000000000001/status \
  -H "Authorization: Bearer <COURIER_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered", "version": 3, "gps_lat": "41.30100000", "gps_lng": "69.24200000"}'

# 4. Dalil rasmi yuklash
curl -X POST http://localhost:8000/delivery/01950000-0000-7000-0000-000000000001/proof-photo \
  -H "Authorization: Bearer <COURIER_ACCESS_TOKEN>" \
  -F "file=@/path/to/photo.jpg"

# 5. Ro'yxat — faqat "assigned" holatdagilar (admin)
curl "http://localhost:8000/delivery?status=assigned&limit=50" \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>"

# 6. GPS trek havolasini olish (GET /delivery/{id} dan gps_track_url)
curl http://localhost:8000/delivery/01950000-0000-7000-0000-000000000001 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
# Javob ichida: "gps_track_url": "/gps/track?delivery_id=01950000-..."
# Trodni o'qish:
curl "http://localhost:8000/gps/track?delivery_id=01950000-0000-7000-0000-000000000001" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## Migratsiya runbook (0012)

```bash
# Standart OLTP URL orqali (TimescaleDB shart emas — delivery OLTP da)
cd backend
alembic upgrade 0012

# Tekshiruv
psql $DATABASE_URL -c "SELECT COUNT(*) FROM delivery;"
psql $DATABASE_URL -c "\d delivery"

# Indekslarni tekshirish (PostgreSQL)
psql $DATABASE_URL -c "
  SELECT indexname, indexdef
  FROM pg_indexes
  WHERE tablename = 'delivery'
  ORDER BY indexname;"

# Partial unique indekslar tekshiruvi
# uq_delivery_order_id_active_partial — bir buyurtmaga bitta aktiv yetkazish
# uq_delivery_client_uuid_partial     — idempotentlik

# Downgrade (FAQAT bo'sh DB da)
alembic downgrade 0011
# Agar jadvalda qatorlar bo'lsa — RuntimeError bilan bloklaydi.
```

---

## Ma'lum cheklovlar va texnik qarz

| Cheklov | Ustuvorlik | Rejalashtirilgan |
|---|---|---|
| `failure_reason` validatsiyasi yo'q — istalgan matn qabul qilinadi; uzunlik cheklovi qo'shilmagan | LOW | Kelajak |
| `check_out` `IntegrityError` ushlash yo'q (davomat modulidan meros) — parallel `set_proof_photo` race holati teorik | LOW | Kuzatish |
| Dalil foto majburiy emas `delivered` holatida — biznes jarayoni foto talab qilmasligi mumkin; agar majburiy bo'lsa, `update_status()` da tekshiruv qo'shish kerak | — | Biznes qaror |
| Sync outbox payload `delivery` aggregate_type uchun pull scope filtri belgilanmagan — `pull()` `delivery` hodisalarini qaysi roldagi foydalanuvchilarga berishi aniq emas | MEDIUM | T19/Sync kengaytma |
