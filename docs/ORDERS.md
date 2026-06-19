# Buyurtma moduli texnik qo'llanmasi (T11–T12)

| | |
|---|---|
| **Versiya** | 0.10.0 |
| **Sana** | 2026-06-16 |
| **Modul prefiksi** | `/orders` |
| **Test soni** | 428 (23 yangi T12) |
| **Gate** | PASS |

---

## 1. Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/orders` | `orders:create` | Yangi buyurtma (ATOMIK) |
| `GET` | `/orders` | `orders:view` | Paginated ro'yxat (RBAC scope) |
| `GET` | `/orders/{id}` | `orders:view` | Bitta buyurtma (RBAC scope) |
| `PATCH` | `/orders/{id}/status` | `orders:edit` | Holat o'zgartirish (server-avtoritar) |

### RBAC — kim nima qila oladi

| Rol | POST | GET (ro'yxat/bitta) | PATCH status |
|---|---|---|---|
| `administrator` | Ha (har qanday do'kon) | Ha (barchasi) | Ha |
| `agent` | Ha (faqat o'z do'konlari) | Ha (faqat o'z do'konlari) | Ha (faqat o'z buyurtmalari) |
| `accountant` | Yo'q | Ha (barchasi) | Yo'q |
| `store` | Yo'q | Ha (faqat o'z do'koni) | Yo'q |
| `courier` | Yo'q | Yo'q | Yo'q |

---

## 2. ATOMIKLIK — POST /orders

`POST /orders` bitta `AsyncSession` tranzaksiyasida quyidagi operatsiyalarni bajaradi:

```
1. Order INSERT
2. OrderLine INSERT (har qator uchun)
3. StockMovement INSERT + StockBalance UPDATE  (LOCK → check → INSERT)
4. LedgerEntry INSERT + AccountBalance UPDATE
```

Barchasi bitta `get_db()` sessiyasida amalga oshiriladi. Router handler qaytganda FastAPI `commit()` chaqiradi. Xato bo'lsa (masalan, ombor yetmasa) `rollback()` chaqiriladi — hech narsa yozilmaydi.

**Bu modular monolitning isboti**: `stock` va `finance` modullari alohida bo'lsa ham, bitta DB tranzaksiyasida birlashtirilishi mumkin. Agar ular alohida mikroservislar bo'lganda bu kafolatni berish uchun 2PC yoki Saga kerak bo'lar edi.

### Ombor yetmasa nima bo'ladi?

`_record_movement_tx()` `StockBalance` ni `SELECT ... FOR UPDATE` bilan qulflaydi. `qty_on_hand < so'ralgan_miqdor` bo'lsa:

```
HTTP 409
{
  "message_key": "orders.insufficient_stock",
  "message": "Omborda mahsulot yetarli emas",
  "detail": {"available": "10.0000", "requested": "15.0000"}
}
```

Shu paytda hali hech narsa DB ga yozilmagan — `rollback()` bajariladi.

---

## 3. Narx server-avtoritar

Klient so'rovida `unit_price`, `segment_id`, `discount` mavjud emas — bu maydonlar `OrderLineIn` sxemasida yo'q:

```python
# OrderLineIn — faqat shu ikkita maydon qabul qilinadi
{
  "product_id": "uuid",
  "qty": "5.0000"
}
```

Server narxni quyidagicha aniqlaydi:

1. `Store.segment_id` — do'konning narx segmenti (server tomonida o'qiladi).
2. `ProductPrice` — `product_id + segment_id + valid_to IS NULL` sharti bilan katalogdan ochiq narx olinadi.
3. Do'konda segment yo'q yoki segment uchun narx topilmasa → `422 orders.no_price`.

`discount` hozirda `0` — chegirma logikasi T25 (promo moduli) da amalga oshiriladi.

---

## 4. Holat mashinasi

Holat o'tishlar server tomonida `VALID_TRANSITIONS` dicts orqali tekshiriladi:

```
draft → confirmed, canceled
confirmed → packed, canceled
packed → delivering, canceled
delivering → delivered, canceled
delivered → (terminal — hech qaerga)
canceled → (terminal — hech qaerga)
```

`POST /orders` yangi buyurtmani `confirmed` holatida yaratadi (stock chiqimi atomik bajarilganligi sababli `draft` kerak emas).

Noqonuniy o'tish (masalan `delivered → confirmed`) so'rovida:

```
HTTP 422
{
  "message_key": "orders.invalid_transition",
  "detail": {"from_status": "delivered", "to_status": "confirmed"}
}
```

---

## 5. Canceled kompensatsiya

`confirmed`, `packed`, yoki `delivering` holatidagi buyurtma `canceled` ga o'tkazilganda, bitta ACID tranzaksiyasida:

1. Har `order_line` uchun `StockMovement (type=in, ref_type=order_cancel)` — ombor qaytadi.
2. `LedgerEntry (type=credit, ref_type=order_cancel)` — do'kon qarzi kamayadi.

`warehouse_id` `order.warehouse_id` dan olinadi — buyurtma yaratilgandagi ombor. Bu kompensatsiyaning to'g'ri omborga borishini kafolatlaydi.

`draft` yoki allaqachon `canceled`/`delivered` holatdagi buyurtmalar `canceled` ga o'tkazilmaydi (holat mashinasi bloki).

---

## 6. Idempotentlik

Bir xil buyurtma ikki marta yuborilmasligi uchun ikki qatlamli himoya:

| Qatlam | Mexanizm |
|---|---|
| DB | `(store_id, client_uuid) WHERE client_uuid IS NOT NULL` partial unique index |
| Redis | `SET NX idem:orders:create:{actor_id}:{store_id}:{client_uuid}` (TTL 24 soat) |

`client_uuid` berilmasa — idempotentlik tekshiruvi o'tkazilmaydi.

`IntegrityError` bo'lsa — mavjud buyurtma (`store_id + client_uuid` bo'yicha) qaytariladi (graceful). Boshqa aktor bir xil `store+client_uuid` kombinatsiyasini ishlatsa → `409 orders.idempotency_conflict`.

---

## 7. Migratsiya 0007

```bash
alembic upgrade 0007
# yoki:
make migrate
```

Ikki jadval yaratiladi:

**`order`** — buyurtma bosh yozuvi:
- `id` UUID v7 PK
- `store_id` FK → `store` (RESTRICT)
- `agent_id` FK → `app_user` (SET NULL, nullable)
- `mode` VARCHAR(20): `bozor | oddiy`
- `status` VARCHAR(20): `draft | confirmed | packed | delivering | delivered | canceled`
- `total_amount` Numeric(18,2)
- `currency` VARCHAR(3), default `UZS`
- `ordered_at` timestamptz
- `client_uuid` UUID nullable
- `branch_id` UUID nullable
- `warehouse_id` UUID nullable
- `version` BIGINT (optimistik lock)
- `created_at`, `updated_at`, `deleted_at`

**`order_line`** — buyurtma qatorlari:
- `id` UUID v7 PK
- `order_id` FK → `order` (CASCADE)
- `product_id` FK → `product` (RESTRICT)
- `qty` Numeric(18,4)
- `unit_price` Numeric(18,2) — server tomonida to'ldiriladi
- `segment_id` FK → `price_segment` (SET NULL, nullable)
- `discount` Numeric(18,2), default `0`
- `line_total` Numeric(18,2)

Downgrade guard: `order` yoki `order_line` da qatorlar bo'lsa `RuntimeError` ko'tariladi.

---

## 8. curl misollari

### Buyurtma yaratish

```bash
curl -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "01900000-0000-7000-8000-000000000001",
    "mode": "oddiy",
    "currency": "UZS",
    "client_uuid": "01900000-0000-7000-8000-000000000099",
    "lines": [
      {
        "product_id": "01900000-0000-7000-8000-000000000010",
        "qty": "5.0000"
      },
      {
        "product_id": "01900000-0000-7000-8000-000000000011",
        "qty": "2.0000"
      }
    ]
  }'
```

Javob (HTTP 201):
```json
{
  "id": "01900000-0000-7000-8000-000000000100",
  "store_id": "01900000-0000-7000-8000-000000000001",
  "agent_id": "01900000-0000-7000-8000-000000000002",
  "mode": "oddiy",
  "status": "confirmed",
  "total_amount": "250000.00",
  "currency": "UZS",
  "ordered_at": "2026-06-16T10:00:00Z",
  "client_uuid": "01900000-0000-7000-8000-000000000099",
  "branch_id": null,
  "warehouse_id": "01900000-0000-7000-8000-000000000050",
  "version": 1,
  "created_at": "2026-06-16T10:00:00Z",
  "updated_at": "2026-06-16T10:00:00Z",
  "deleted_at": null,
  "lines": [
    {
      "id": "01900000-0000-7000-8000-000000000101",
      "order_id": "01900000-0000-7000-8000-000000000100",
      "product_id": "01900000-0000-7000-8000-000000000010",
      "qty": "5.0000",
      "unit_price": "40000.00",
      "segment_id": "01900000-0000-7000-8000-000000000020",
      "discount": "0.00",
      "line_total": "200000.00"
    },
    {
      "id": "01900000-0000-7000-8000-000000000102",
      "order_id": "01900000-0000-7000-8000-000000000100",
      "product_id": "01900000-0000-7000-8000-000000000011",
      "qty": "2.0000",
      "unit_price": "25000.00",
      "segment_id": "01900000-0000-7000-8000-000000000020",
      "discount": "0.00",
      "line_total": "50000.00"
    }
  ]
}
```

### Holat o'zgartirish (confirmed → packed)

```bash
curl -X PATCH http://localhost:8000/orders/01900000-0000-7000-8000-000000000100/status \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "packed",
    "version": 1
  }'
```

Javob (HTTP 200): yangilangan `OrderOut` (`status: "packed"`, `version: 2`).

### Buyurtmalar ro'yxati

```bash
curl "http://localhost:8000/orders?status=confirmed&limit=20&offset=0" \
  -H "Authorization: Bearer <access_token>"
```

Javob (HTTP 200):
```json
{
  "items": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

## 9. Xato kodlari

| `message_key` | HTTP | Sabab |
|---|---|---|
| `orders.empty_lines` | 422 | `lines` bo'sh yoki berilmagan |
| `orders.product_not_found` | 404 | Mahsulot topilmasa yoki `is_active=False` |
| `customers.store_not_found` | 404 | Do'kon topilmasa yoki o'chirilgan |
| `orders.no_price` | 422 | Do'kon segmenti uchun narx topilmasa |
| `orders.insufficient_stock` | 409 | Ombor qoldig'i yetarli emas |
| `orders.idempotency_conflict` | 409 | Boshqa aktor bir xil `store+client_uuid` ishlatdi |
| `orders.order_not_found` | 404 | Buyurtma topilmasa yoki RBAC scope ruxsat bermasa |
| `orders.invalid_transition` | 422 | Noqonuniy holat o'tishi |
| `orders.version_conflict` | 409 | Optimistik lock — versiya mos kelmasa |
| `orders.template_not_found` | 404 | Shablon topilmasa yoki RBAC scope ruxsat bermasa |

---

## 10. Buyurtma shabloni (T12)

Shablon — tez-tez takrorlanadigan buyurtmalar uchun qayta ishlatiluvchi qator ro'yxati. Shablon faqat `product_id` va `qty` saqlaydi. **Narx hech qachon shablon ichida saqlanmaydi.**

### 10.1. Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/orders/templates` | `orders:create` | Yangi shablon |
| `GET` | `/orders/templates` | `orders:view` | Paginated ro'yxat (RBAC scope) |
| `GET` | `/orders/templates/{id}` | `orders:view` | Bitta shablon (RBAC scope) |
| `DELETE` | `/orders/templates/{id}` | `orders:edit` | Soft delete |
| `POST` | `/orders/templates/{id}/apply` | `orders:create` | Shablondan buyurtma yaratish → 201 `OrderOut` |

### 10.2. RBAC

| Rol | POST | GET | DELETE | apply |
|---|---|---|---|---|
| `administrator` | Ha (har qanday do'kon) | Ha (barchasi) | Ha | Ha |
| `agent` | Ha (faqat o'z do'konlari) | Ha (faqat o'z do'konlari) | Ha (o'z do'konlari) | Ha (o'z do'konlari) |
| `accountant` | Yo'q | Ha (barchasi) | Yo'q | Yo'q |
| `store` | Yo'q | Ha (faqat o'z do'koni) | Yo'q | Yo'q |
| `courier` | Yo'q | Yo'q | Yo'q | Yo'q |

### 10.3. Asosiy invariant: narx saqlanmaydi

`order_template_line` jadvalida `unit_price` ustuni mavjud emas. Sxema darajasida ham (`OrderTemplateLineIn`) narx, segment yoki chegirma maydoni yo'q. Narx faqat `apply` paytida `Store.segment_id` + katalog `ProductPrice` dan server tomonida olinadi — bu `create_order` ning odatdagi narx oqimi bilan bir xil.

```
shablon qatori: { product_id, qty }        ← narx YO'Q
apply paytida:  katalog → unit_price       ← server-avtoritar
```

### 10.4. apply oqimi

`POST /orders/templates/{id}/apply` quyidagi ketma-ketlikda ishlaydi:

```
1. Shablon va qatorlar o'qiladi (RBAC scope tekshiruvi)
2. Shablon qatorlaridan OrderCreate tuziladi:
     store_id    ← ApplyTemplateIn.store_id
     mode        ← ApplyTemplateIn.mode
     currency    ← ApplyTemplateIn.currency
     client_uuid ← ApplyTemplateIn.client_uuid
     lines       ← [{ product_id, qty } for line in template.lines]
3. create_order(OrderCreate) chaqiriladi:
     - narx katalogdan (server-avtoritar)
     - ombor chiqimi + ledger debit (atomik, bitta tranzaksiya)
     - idempotentlik (Redis SET NX + DB partial unique)
4. 201 OrderOut qaytariladi
```

Shablon o'zgarmaydi. Bir shablon bilan bir necha marta `apply` chaqirish mumkin — har safar yangi mustaqil buyurtma yaratiladi (idempotentlik `client_uuid` orqali).

> **Eslatma**: hozirda `apply` `ApplyTemplateIn.warehouse_id` ni `create_order` ga uzatadi. Agar `warehouse_id` berilmasa, standart ombor ishlatiladi. Warehouse moduli (kelajak) to'liq jihatda amalga oshirilganda `warehouse_id` passthrough kengaytiriladi.

### 10.5. Migratsiya 0008

```bash
alembic upgrade 0008
# yoki:
make migrate
```

Ikki jadval yaratiladi:

**`order_template`** — shablon bosh yozuvi:
- `id` UUID v7 PK
- `store_id` FK → `store` (RESTRICT)
- `name` VARCHAR(255)
- `created_by` FK → `app_user` (SET NULL, nullable)
- `version` BIGINT (optimistik lock)
- `created_at`, `updated_at`, `deleted_at`

**`order_template_line`** — shablon qatorlari:
- `id` UUID v7 PK
- `template_id` FK → `order_template` (CASCADE)
- `product_id` FK → `product` (RESTRICT)
- `qty` Numeric(18,4)
- **`unit_price` ustuni YO'Q** — shablon narx saqlamaydi

Downgrade guard: jadvallarda qatorlar bo'lsa `RuntimeError` ko'tariladi.

### 10.6. curl misollari

**Shablon yaratish:**

```bash
curl -X POST http://localhost:8000/orders/templates \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "01900000-0000-7000-8000-000000000001",
    "name": "Haftalik standart buyurtma",
    "lines": [
      { "product_id": "01900000-0000-7000-8000-000000000010", "qty": "10.0000" },
      { "product_id": "01900000-0000-7000-8000-000000000011", "qty": "5.0000" }
    ]
  }'
```

Javob (HTTP 201):
```json
{
  "id": "01900000-0000-7000-8000-000000000200",
  "store_id": "01900000-0000-7000-8000-000000000001",
  "name": "Haftalik standart buyurtma",
  "lines": [
    { "product_id": "01900000-0000-7000-8000-000000000010", "qty": "10.0000" },
    { "product_id": "01900000-0000-7000-8000-000000000011", "qty": "5.0000" }
  ],
  "created_at": "2026-06-16T10:00:00Z",
  "deleted_at": null
}
```

**Shablonni buyurtmaga aylantirish (apply):**

```bash
curl -X POST \
  http://localhost:8000/orders/templates/01900000-0000-7000-8000-000000000200/apply \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "01900000-0000-7000-8000-000000000001",
    "mode": "oddiy",
    "currency": "UZS",
    "client_uuid": "01900000-0000-7000-8000-000000000301"
  }'
```

Javob (HTTP 201): to'liq `OrderOut` — narx katalogdan hisoblangan (`unit_price`, `line_total` server tomonida to'ldirilgan); shablon ichida narx yo'q edi.
