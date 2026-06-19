# PROMO — Aksiya moduli texnik qo'llanmasi (T25, v0.18.0)

| | |
|---|---|
| **Versiya** | 0.18.0 |
| **Migratsiya** | `alembic/versions/0016_promo.py` |
| **Prefix** | `/promos` |
| **Test soni** | 701 (jami) |

---

## Endpointlar va RBAC

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `GET` | `/promos` | `promo:view` (barcha rollar) | Paginated ro'yxat; filtrlash mumkin |
| `GET` | `/promos/active` | `promo:view` (barcha rollar) | Hozir amal qilayotgan aksiyalar |
| `POST` | `/promos` | `promo:create` (administrator) | Yangi aksiya yaratish |
| `GET` | `/promos/{id}` | `promo:view` (barcha rollar) | Bitta aksiya |
| `PATCH` | `/promos/{id}` | `promo:edit` (administrator) | Qisman yangilash |
| `POST` | `/promos/{id}/banner` | `promo:edit` (administrator) | Banner rasm yuklash |
| `DELETE` | `/promos/{id}` | `promo:delete` (administrator) | Soft-delete |

**Rollar**: `administrator` — to'liq CRUD; `accountant`, `agent`, `store`, `courier` — faqat `GET` (`promo:view`).

---

## rule_json formati

`rule_json` — aksiya qoidasini ifodalovchi JSON ob'ekti. Faqat `discount` tipidagi aksiyalarda server chegirma hisoblaydi.

### Maydonlar

| Maydon | Turi | Majburiy | Chegaralar | Tavsif |
|---|---|---|---|---|
| `discount_percent` | `float` | Shartli | `(0, 100]` | Foizli chegirma. `discount_amount` bilan birga bo'lishi mumkin emas |
| `discount_amount` | `float` | Shartli | `> 0` | Summaviy chegirma (so'm). `discount_percent` bilan birga bo'lishi mumkin emas |
| `min_qty` | `float` | Ixtiyoriy | `> 0` | Minimal miqdor. Bu miqdordan kam bo'lsa chegirma qo'llanilmaydi |

`discount_percent` yoki `discount_amount` — ikkisidan biri majburiy. Ikkalasi birga bo'lishi mumkin emas.

### Misollar

```json
{"discount_percent": 10}
```
Barcha mos buyurtma qatorlariga 10% chegirma.

```json
{"discount_amount": 5000}
```
Barcha mos qatorlardan 5 000 so'm chegirma.

```json
{"discount_percent": 15, "min_qty": 3}
```
Kamida 3 dona sotib olinganda 15% chegirma.

```json
{"discount_amount": 2000, "min_qty": 2}
```
Kamida 2 dona sotib olinganda 2 000 so'm chegirma.

---

## SERVER-AVTORITAR chegirma: compute_line_discount

Buyurtma yaratilganda (`POST /orders`) har bir qator uchun `compute_line_discount()` chaqiriladi. Klient `OrderLineIn` sxemasida `discount` maydonini bera olmaydi — schema darajasida bloklangan (T11 himoyasi).

### Oqim

```
create_order() da har order_line uchun:
  └── compute_line_discount(db, product_id, segment_id, qty, unit_price)
        │
        ├── 1. Mos promo topish:
        │     is_active=True
        │     AND valid_from <= bugun <= valid_to
        │     AND promo_type = 'discount'
        │     AND (target_product_id IS NULL OR target_product_id = product_id)
        │     AND (target_segment_id IS NULL OR target_segment_id = segment_id)
        │
        ├── 2. Ustuvorlik (ORDER BY):
        │     target_product_id NOT NULL  — yuqori (aniq mahsulot)
        │     target_segment_id NOT NULL  — o'rta (aniq segment)
        │     global (ikkalasi NULL)       — past
        │     valid_from DESC             — eng yangi
        │     LIMIT 1
        │
        ├── 3. min_qty tekshiruvi:
        │     qty < min_qty  → Decimal("0")
        │
        ├── 4. discount_percent:
        │     discount = unit_price × qty × pct / 100
        │     discount = min(discount, line_gross)   ← manfiy qarz imkonsiz
        │
        ├── 5. discount_amount:
        │     discount = min(amt, line_gross)         ← manfiy qarz imkonsiz
        │
        └── 6. Mos promo yo'q → Decimal("0")
```

`line_gross = unit_price × qty`. Cap `min(discount, line_gross)` kafolat beradi: `line_total` hech qachon manfiy bo'lmaydi.

---

## Maqsad (target) filtrlari

| `target_product_id` | `target_segment_id` | Qo'llanish |
|---|---|---|
| `NULL` | `NULL` | Global — barcha mahsulot va segmentlar |
| `NULL` | segment UUID | Faqat mos segmentdagi do'konlar |
| mahsulot UUID | `NULL` | Faqat mos mahsulot, barcha segmentlar |
| mahsulot UUID | segment UUID | Faqat mos mahsulot + mos segment |

---

## Sync va /active endpoint

`GET /promos/active` — Flutter klientlar, agent va do'kon ilovalariga aksiyalar ro'yxatini uzatish uchun. Katalog kabi global: barcha autentifikatsiyalangan foydalanuvchilarga ko'rinadi.

Outbox hodisalari (`promo.created`, `promo.updated`, `promo.deleted`, `promo.banner_updated`) `outbox_event` jadvaliga yoziladi va sync pull da `aggregate_type = 'promo'` orqali global tarqatiladi.

---

## Banner yuklash

`POST /promos/{id}/banner` — multipart/form-data, `file` maydoni.

- Qabul qilinadigan formatlar: JPEG, PNG, WebP
- Tekshiruv: magic-byte (birinchi baytlar) — Content-Type ga ishonilmaydi
  - JPEG: `FF D8 FF`
  - PNG: `89 50 4E 47`
  - WebP: `52 49 46 46`
- Maksimal hajm: 5 MB
- `banner_url` MinIO/S3 da saqlangan URL bilan yangilanadi
- Idempotent: qayta yuklash `banner_url` ni almashtiradi, `version` oshadi

---

## Idempotentlik

`POST /promos` da `client_uuid` ixtiyoriy maydon:

1. Redis `SET NX ex` (TTL 24 soat) — birinchi qatlam
2. DB `uq_promo_client_uuid_partial` partial unique index (`client_uuid WHERE IS NOT NULL`) — ikkinchi qatlam (race condition)
3. `IntegrityError` → rollback + mavjud promo qaytarish (status 200, yangi yaratilmaydi)

---

## Migratsiya runbook

```bash
# Standart migratsiya
cd backend
alembic upgrade head
# yoki faqat 0016 ga:
alembic upgrade 0016
```

Downgrade qo'llab-quvvatlanadi, lekin `promo` jadvalida qatorlar bo'lsa `RuntimeError` bilan blokladi:

```bash
# Faqat bo'sh DB da:
alembic downgrade 0015
```

---

## curl misollari

### Yangi aksiya yaratish

```bash
curl -X POST http://localhost:8000/promos \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name_uz": "Yozgi chegirma",
    "name_ru": "Летняя скидка",
    "promo_type": "discount",
    "rule_json": {"discount_percent": 10, "min_qty": 3},
    "valid_from": "2026-06-01",
    "valid_to": "2026-08-31",
    "is_active": true
  }'
```

### Hozir amal qilayotgan aksiyalarni olish

```bash
curl http://localhost:8000/promos/active \
  -H "Authorization: Bearer <token>"
```

### Ma'lum sanaga tekshirish

```bash
curl "http://localhost:8000/promos/active?at_date=2026-07-15" \
  -H "Authorization: Bearer <token>"
```

### Aksiyani yangilash (PATCH)

```bash
curl -X PATCH http://localhost:8000/promos/<promo_id> \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "version": 1,
    "rule_json": {"discount_percent": 15, "min_qty": 2},
    "valid_to": "2026-09-30"
  }'
```

### Banner yuklash

```bash
curl -X POST http://localhost:8000/promos/<promo_id>/banner \
  -H "Authorization: Bearer <admin_token>" \
  -F "file=@banner.jpg"
```

### Aksiyani o'chirish (soft-delete)

```bash
curl -X DELETE http://localhost:8000/promos/<promo_id> \
  -H "Authorization: Bearer <admin_token>"
# → 204 No Content
```

---

## PromoOut javob sxemasi

```json
{
  "id": "019012ab-...",
  "name_uz": "Yozgi chegirma",
  "name_ru": "Летняя скидка",
  "name": "Yozgi chegirma",
  "promo_type": "discount",
  "rule_json": {"discount_percent": 10, "min_qty": 3},
  "banner_url": "https://minio.example.com/promos/banner.jpg",
  "valid_from": "2026-06-01",
  "valid_to": "2026-08-31",
  "target_segment_id": null,
  "target_product_id": null,
  "is_active": true,
  "branch_id": null,
  "client_uuid": null,
  "version": 1,
  "created_at": "2026-06-18T10:00:00Z",
  "updated_at": "2026-06-18T10:00:00Z",
  "deleted_at": null
}
```

`name` maydoni `Accept-Language` header asosida lokalizatsiyalanadi: `uz` → `name_uz`, `ru` → `name_ru`.

---

## Ma'lum cheklovlar

| Cheklov | Holat |
|---|---|
| `bonus` va `gift` promo_type hozir `compute_line_discount()` da hisoblanmaydi — faqat `discount` tipi | LOW (kelajak sprint) |
| Bir qatorga bir nechta mos promo bo'lsa faqat ustuvor bittasi qo'llaniladi — stacking yo'q | Qasddan (ADR §3.6) |
| `at_date` parametri UTC bo'yicha tekshiriladi — timezone farqi bo'lishi mumkin | LOW (kuzatish) |
