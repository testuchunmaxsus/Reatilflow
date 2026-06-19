# Katalog moduli — texnik qo'llanma (v0.5.0)

| | |
|---|---|
| **Prefiks** | `/catalog` |
| **Modul** | `backend/app/modules/catalog/` |
| **Versiya** | 0.5.0 |
| **Gate** | PASS (229/229 test) |

---

## 1. Endpointlar

### 1.1 Kategoriyalar

| Metod | Yo'l | RBAC ruxsati | Tavsif |
|---|---|---|---|
| `GET` | `/catalog/categories` | `catalog:view` | Barcha faol kategoriyalar ro'yxati |
| `POST` | `/catalog/categories` | `catalog:create` | Yangi kategoriya yaratish (admin) |

### 1.2 Narx segmentlari

| Metod | Yo'l | RBAC ruxsati | Tavsif |
|---|---|---|---|
| `GET` | `/catalog/price-segments` | `catalog:view` | Barcha narx segmentlar ro'yxati |
| `POST` | `/catalog/price-segments` | `catalog:create` | Yangi narx segmenti yaratish (admin) |

### 1.3 Mahsulotlar

| Metod | Yo'l | RBAC ruxsati | Tavsif |
|---|---|---|---|
| `GET` | `/catalog/products` | `catalog:view` | Paginated ro'yxat (filter, qidiruv, branch ko'rinish) |
| `POST` | `/catalog/products` | `catalog:create` | Yangi mahsulot yaratish (admin) |
| `GET` | `/catalog/products/{id}` | `catalog:view` | Bitta mahsulot (branch visibility) |
| `PATCH` | `/catalog/products/{id}` | `catalog:edit` | Qisman yangilash (optimistik lock) |
| `DELETE` | `/catalog/products/{id}` | `catalog:delete` | Soft-delete (`deleted_at` o'rnatiladi) |
| `POST` | `/catalog/products/{id}/prices` | `catalog:edit` | Narx o'rnatish (append-only tarix) |
| `GET` | `/catalog/products/{id}/price-history` | `catalog:view` | Narx tarixi (yangirog'i birinchi) |
| `POST` | `/catalog/products/{id}/photo` | `catalog:edit` | Rasm yuklash (MinIO, JPEG/PNG/WebP) |

---

## 2. So'rov va javob sxemalari

### 2.1 Kategoriya

**`CategoryCreate`** (POST `/catalog/categories` tanasi):
```json
{
  "name_uz": "Oziq-ovqat",
  "name_ru": "Продукты питания",
  "parent_id": null,
  "is_active": true
}
```

**`CategoryOut`** (javob):
```json
{
  "id": "019012ab-...",
  "name_uz": "Oziq-ovqat",
  "name_ru": "Продукты питания",
  "name": "Oziq-ovqat",
  "parent_id": null,
  "is_active": true,
  "created_at": "2026-06-16T10:00:00Z",
  "updated_at": "2026-06-16T10:00:00Z"
}
```

`name` maydoni joriy til bo'yicha lokalizatsiyalangan nom (`name_uz` yoki `name_ru`). Til aniqlanmasa `name_uz` qaytariladi.

### 2.2 Narx segmenti

**`PriceSegmentCreate`**:
```json
{ "name": "Ulgurji" }
```

**`PriceSegmentOut`**:
```json
{
  "id": "019012ac-...",
  "name": "Ulgurji",
  "created_at": "2026-06-16T10:00:00Z",
  "updated_at": "2026-06-16T10:00:00Z"
}
```

### 2.3 Mahsulot

**`ProductCreate`** (POST `/catalog/products` tanasi):
```json
{
  "name_uz": "Non oq",
  "name_ru": "Хлеб белый",
  "sku": "BREAD-001",
  "barcode": "4600001234567",
  "mxik_code": "01234567",
  "unit": "dona",
  "category_id": "019012ab-...",
  "is_active": true,
  "branch_scope": null,
  "client_uuid": "550e8400-e29b-41d4-a716-446655440000"
}
```

`client_uuid` ixtiyoriy — idempotentlik uchun (§4 ga qarang).
`branch_scope: null` — global mahsulot (barcha filiallarga ko'rinadi).

**`ProductOut`** (javob):
```json
{
  "id": "019012bd-...",
  "name_uz": "Non oq",
  "name_ru": "Хлеб белый",
  "name": "Non oq",
  "sku": "BREAD-001",
  "barcode": "4600001234567",
  "mxik_code": "01234567",
  "unit": "dona",
  "category_id": "019012ab-...",
  "photo_url": null,
  "is_active": true,
  "branch_scope": null,
  "version": 1,
  "created_at": "2026-06-16T10:00:00Z",
  "updated_at": "2026-06-16T10:00:00Z",
  "deleted_at": null
}
```

**`ProductUpdate`** (PATCH tanasi — faqat berilgan maydonlar yangilanadi):
```json
{
  "name_uz": "Non oq premium",
  "is_active": false,
  "version": 1
}
```

`version` majburiy — optimistik lock uchun. Joriy versiya bilan mos kelmasa 409 qaytariladi.

**`PaginatedProducts`** (GET `/catalog/products` javobi):
```json
{
  "items": [ ...ProductOut... ],
  "total": 142,
  "limit": 20,
  "offset": 0
}
```

### 2.4 Narx

**`PriceSet`** (POST `/catalog/products/{id}/prices` tanasi):
```json
{
  "segment_id": "019012ac-...",
  "price": "12500.00",
  "currency": "UZS",
  "valid_from": "2026-06-16T00:00:00Z"
}
```

**`PriceOut`** (javob):
```json
{
  "id": "019012cd-...",
  "product_id": "019012bd-...",
  "segment_id": "019012ac-...",
  "price": "12500.00",
  "currency": "UZS",
  "valid_from": "2026-06-16T00:00:00Z",
  "valid_to": null,
  "created_at": "2026-06-16T10:00:00Z"
}
```

**`PriceHistoryOut`** (GET `.../price-history` elementlari):
```json
{
  "id": "019012de-...",
  "product_id": "019012bd-...",
  "segment_id": "019012ac-...",
  "old_price": "11000.00",
  "new_price": "12500.00",
  "currency": "UZS",
  "changed_by": "019011aa-...",
  "changed_at": "2026-06-16T10:00:00Z"
}
```

---

## 3. Narx tarixi — append-only model

Narx o'zgarishi quyidagi tartibda amalga oshiriladi:

1. `POST /catalog/products/{id}/prices` chaqiriladi.
2. Joriy ochiq narx (`valid_to IS NULL`) `SELECT FOR UPDATE` bilan qulflanadi.
3. Joriy narxning `valid_to` yangi `valid_from` ga o'rnatiladi (yopiladi).
4. `price_history` jadvaliga eski va yangi narx bilan yozuv qo'shiladi (APPEND — hech qachon o'chirmaydi).
5. Yangi `ProductPrice` yozuvi yaratiladi (`valid_to = NULL`).

`uix_product_price_open` partial unique index (`product_id, segment_id WHERE valid_to IS NULL`) bir mahsulot × segment uchun bir vaqtda faqat bitta ochiq narx bo'lishini kafolatlaydi.

`price_history` jadvali faqat INSERT — UPDATE va DELETE yo'q (moliyaviy aniqlik).

---

## 4. Idempotentlik

`POST /catalog/products` da takroriy so'rovlardan himoya:

| | |
|---|---|
| **Kalit** | `idem:catalog:create:{actor_id}:{client_uuid}` (Redis) |
| **TTL** | 86400 soniya (24 soat) |
| **Mexanizm** | Bir xil `(actor_id, client_uuid)` juftligi kelsa — avval yaratilgan mahsulot qaytariladi |
| **Muhim** | `client_uuid` hech qachon `Product.id` ga yozilmaydi; `id` har doim server tomonida `uuid7()` bilan generatsiya qilinadi |
| **Redis o'chsa** | Graceful degradatsiya — idempotentlik o'tkazib yuboriladi, yangi mahsulot yaratiladi; warning log yoziladi |

---

## 5. Branch ko'rinish qoidasi

| Rol | Ko'rish doirasi |
|---|---|
| `administrator` | Barcha mahsulotlar (`branch_scope` ga qaramasdan) |
| `accountant` | Barcha mahsulotlar (`branch_scope` ga qaramasdan) |
| `agent` | `branch_scope IS NULL` (global) yoki `branch_scope == user.branch_id` |
| `courier` | `branch_scope IS NULL` (global) yoki `branch_scope == user.branch_id` |
| `store` | `branch_scope IS NULL` (global) yoki `branch_scope == user.branch_id` |

Doiradan tashqari mahsulotni `GET/PATCH/DELETE` bilan so'raganda ham **404** qaytariladi (mavjudlikni oshkor qilmaslik — cross-branch IDOR himoyasi).

---

## 6. Rasm yuklash

`POST /catalog/products/{id}/photo` — `multipart/form-data`, `file` maydoni.

| Parametr | Qiymat |
|---|---|
| Ruxsat etilgan formatlar | JPEG (`FF D8 FF`), PNG (`89 50 4E 47`), WebP (`52 49 46 46`) |
| Maksimal hajm | 5 MB |
| Rad etilganlar | SVG, HTML va boshqa formatlar |
| Validatsiya | Faylning birinchi baytlari (magic bytes) tekshiriladi; `Content-Type` headeriga ishonilmaydi |
| Saqlash | Prod: MinIO; Test: `FakeStorage` (xotiraga saqlaydi) |
| Javob | Yangilangan `ProductOut` (`photo_url` bilan) |

---

## 7. i18n (lokalizatsiya)

Til aniqlash ustuvorligi: `?lang=` query parametri > `Accept-Language` header > `uz` (default).

`ProductOut.name` va `CategoryOut.name` maydonlari joriy til bo'yicha lokalizatsiyalanadi:
- `lang=uz` → `name_uz` qiymati
- `lang=ru` → `name_ru` qiymati
- Til aniqlanmasa yoki `name_ru` bo'sh bo'lsa → `name_uz` ga fallback

So'rovda `name_uz` va `name_ru` maydonlari ham har doim qaytariladi.

---

## 8. curl misollari

### Mahsulot yaratish

```bash
curl -X POST http://localhost:8000/catalog/products \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name_uz": "Limon",
    "name_ru": "Лимон",
    "sku": "LEMON-001",
    "barcode": "4601234567890",
    "unit": "kg",
    "is_active": true,
    "client_uuid": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

### Mahsulotlar ro'yxati (filter va qidiruv)

```bash
# Kategoriya bo'yicha, faqat faol, o'zbek tilida
curl "http://localhost:8000/catalog/products?category_id=019012ab-...&is_active=true&lang=uz&limit=10&offset=0" \
  -H "Authorization: Bearer <access_token>"

# Nom/SKU/barcode bo'yicha qidiruv
curl "http://localhost:8000/catalog/products?search=limon&lang=ru" \
  -H "Authorization: Bearer <access_token>"
```

### Narx o'rnatish

```bash
curl -X POST http://localhost:8000/catalog/products/019012bd-.../prices \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "segment_id": "019012ac-...",
    "price": "15000.00",
    "currency": "UZS",
    "valid_from": "2026-06-16T00:00:00Z"
  }'
```

### Rasm yuklash

```bash
curl -X POST http://localhost:8000/catalog/products/019012bd-.../photo \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/photo.jpg"
```

### Mahsulot yangilash (PATCH)

```bash
curl -X PATCH http://localhost:8000/catalog/products/019012bd-... \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name_uz": "Limon yashil",
    "is_active": false,
    "version": 1
  }'
```

---

## 9. Xato kodlari

| HTTP | `message_key` | Sabab |
|---|---|---|
| 404 | `catalog.product_not_found` | Mahsulot topilmadi yoki branch doirasidan tashqari |
| 404 | `catalog.category_not_found` | Kategoriya topilmadi |
| 404 | `catalog.segment_not_found` | Narx segmenti topilmadi |
| 409 | `catalog.duplicate_sku` | Bir xil SKU bilan faol mahsulot mavjud |
| 409 | `catalog.duplicate_barcode` | Bir xil barcode bilan faol mahsulot mavjud |
| 409 | `catalog.version_conflict` | Optimistik lock — `version` mos kelmadi |
| 422 | `common.validation_error` | Noto'g'ri so'rov formati (magic byte, hajm, maydon validatsiyasi) |
| 401 | `auth.authentication_required` | Token yo'q yoki yaroqsiz |
| 403 | `rbac.permission_denied` | Ruxsat yo'q |

---

## 10. Migratsiya 0003 — deploy runbook

`alembic upgrade 0003` dan **oldin** barcode dublikatlarini tekshiring:

```sql
-- Faol mahsulotlar orasida takroriy barcode bor-yo'qligini tekshirish
SELECT barcode, COUNT(*) AS cnt
FROM product
WHERE deleted_at IS NULL
  AND barcode IS NOT NULL
GROUP BY barcode
HAVING COUNT(*) > 1;
```

Natija bo'sh bo'lishi kerak. Agar dublikat topilsa — birorta mahsulotni soft-delete qilib yoki barcodeini tuzatib, so'ng migratsiyani ishga tushiring:

```bash
cd backend
alembic upgrade 0003
```

Migratsiya faqat PostgreSQL da partial unique index yaratadi. SQLite test muhitida oddiy unique index ishlatiladi.

**Rollback** (agar kerak bo'lsa):
```bash
alembic downgrade 0002
```
