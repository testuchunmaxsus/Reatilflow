# Ombor (T9) va Buxgalteriya (T10) — Texnik qo'llanma

| | |
|---|---|
| **Versiya** | 0.8.0 |
| **Sana** | 2026-06-16 |
| **Holati** | Yakunlandi — gate PASS (363/363 test) |
| **Modul prefikslari** | `/stock`, `/finance` |

---

## 1. Ombor (T9) — `/stock`

### 1.1 Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/stock/movements` | `stock:create` (administrator) | Ombor harakatini qayd etish (APPEND-ONLY) |
| `GET` | `/stock/balance` | `stock:view` (barcha ruxsatli rollar) | Mahsulot + ombor qoldig'i |
| `GET` | `/stock/movements` | `stock:view` (barcha ruxsatli rollar) | Harakatlar ro'yxati (paginated) |

**RBAC:** `POST` faqat `administrator` rolida. `GET` — `administrator`, `accountant`, `agent`, `store`, `courier` rollari uchun (`stock:view` ruxsati mavjud bo'lsa).

### 1.2 Harakat turlari

| Tur | Ma'nosi | Qoldiqqa ta'siri |
|---|---|---|
| `in` | Kirish (qabul qilish) | `qty_on_hand` oshadi |
| `out` | Chiqish (jo'natish, yechish) | `qty_on_hand` kamayadi |
| `transfer` | Omborlar o'rtasida ko'chirish | Manba omborda kamayadi, manzil omborda oshadi |
| `adjust` | Tuzatish (ixtiyoriy inventarizatsiya) | Faqat oshiradi (`delta += qty`); kamaytirish uchun `out` ishlating |

`qty` har doim musbat Decimal qiymat. `adjust` faqat qoldig'ni oshirish uchun mo'ljallangan; kamaytirish zarur bo'lsa `out` turini ishlating.

### 1.3 So'rov/javob sxemalari

**`POST /stock/movements` so'rovi:**

```json
{
  "product_id": "019012ab-...",
  "warehouse_id": "019012cd-...",
  "type": "in",
  "qty": "150.0000",
  "ref_type": "purchase_order",
  "ref_id": "019012ef-...",
  "client_uuid": "019012gh-..."
}
```

**Javob (201):**

```json
{
  "id": "019012ij-...",
  "product_id": "019012ab-...",
  "warehouse_id": "019012cd-...",
  "type": "in",
  "qty": "150.0000",
  "ref_type": "purchase_order",
  "ref_id": "019012ef-...",
  "moved_by": "019012kl-...",
  "moved_at": "2026-06-16T08:00:00Z",
  "client_uuid": "019012gh-...",
  "created_at": "2026-06-16T08:00:00Z"
}
```

**`GET /stock/balance` javob (200):**

```json
{
  "id": "019012mn-...",
  "product_id": "019012ab-...",
  "warehouse_id": "019012cd-...",
  "qty_on_hand": "150.0000",
  "qty_reserved": "0.0000",
  "version": 1,
  "updated_at": "2026-06-16T08:00:00Z"
}
```

**`GET /stock/movements` javob (200):**

```json
{
  "items": [ /* StockMovementOut ro'yxati */ ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### 1.4 `curl` misollari

```bash
# Harakat qayd etish
curl -X POST http://localhost:8000/stock/movements \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "019012ab-0000-7000-8000-000000000001",
    "warehouse_id": "019012ab-0000-7000-8000-000000000002",
    "type": "in",
    "qty": "100.0000",
    "client_uuid": "019012ab-0000-7000-8000-000000000099"
  }'

# Qoldiqni olish
curl "http://localhost:8000/stock/balance?product_id=019012ab-...&warehouse_id=019012cd-..." \
  -H "Authorization: Bearer <access_token>"

# Harakatlar ro'yxati (filtrlangan)
curl "http://localhost:8000/stock/movements?product_id=019012ab-...&movement_type=in&limit=20&offset=0" \
  -H "Authorization: Bearer <access_token>"
```

---

## 2. Buxgalteriya (T10) — `/finance`

### 2.1 Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `POST` | `/finance/ledger` | `finance:create` (accountant) | Buxgalteriya yozuvini qayd etish (APPEND-ONLY) |
| `GET` | `/finance/balance/{store_id}` | `finance:view` + scope | Do'kon moliyaviy balansi |
| `GET` | `/finance/ledger` | `finance:view` + scope | Yozuvlar ro'yxati (paginated) |

**RBAC:** `POST` faqat `accountant` rolida. `GET` endpointlari `finance:view` ruxsati + qator-darajali scope (pastda).

### 2.2 Debit/kredit semantikasi

| Tur | Ma'nosi | Balansga ta'siri |
|---|---|---|
| `debit` | Qarz (do'kon qarzdor) | `balance` oshadi (qarzdorlik ko'payadi) |
| `credit` | To'lov yoki kredit berish | `balance` kamayadi (qarzdorlik kamayadi) |

`balance > 0` — do'kon qarzdor. `balance < 0` — do'kon ortiqcha to'lov qilgan (kredit qoldiq).

### 2.3 Valyuta

- Bir do'kon uchun yagona valyuta qo'llanadi.
- Yangi yozuv valyutasi (`currency`) do'konning mavjud valyutasiga mos kelishi shart.
- Mos kelmasa → **409 Conflict** (`currency_mismatch`).
- Default valyuta: `UZS` (ISO 4217).

### 2.4 IDOR va scope

| Rol | Ko'ra oladigan balanslar |
|---|---|
| `accountant` | Barcha do'konlar |
| `administrator` | Barcha do'konlar |
| `agent` | Faqat o'z do'konlari (AgentStore orqali) |
| `store` | Faqat o'z `store_id` |
| `courier` | `finance:view` ruxsati yo'q — 403 |

`store` roli boshqa `store_id` ga so'rov yuborganda → **404** (mavjudlikni oshkor qilmaslik).

### 2.5 So'rov/javob sxemalari

**`POST /finance/ledger` so'rovi:**

```json
{
  "store_id": "019012ab-...",
  "type": "debit",
  "amount": "500000.00",
  "currency": "UZS",
  "ref_type": "invoice",
  "ref_id": "019012cd-...",
  "client_uuid": "019012ef-..."
}
```

**Javob (201):**

```json
{
  "id": "019012gh-...",
  "store_id": "019012ab-...",
  "type": "debit",
  "amount": "500000.00",
  "currency": "UZS",
  "ref_type": "invoice",
  "ref_id": "019012cd-...",
  "entry_date": "2026-06-16T08:00:00Z",
  "created_by": "019012kl-...",
  "client_uuid": "019012ef-...",
  "created_at": "2026-06-16T08:00:00Z"
}
```

**`GET /finance/balance/{store_id}` javob (200):**

```json
{
  "id": "019012mn-...",
  "store_id": "019012ab-...",
  "balance": "500000.00",
  "currency": "UZS",
  "last_recalc_at": "2026-06-16T08:00:00Z",
  "version": 1
}
```

**`GET /finance/ledger` javob (200):**

```json
{
  "items": [ /* LedgerEntryOut ro'yxati */ ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

### 2.6 `curl` misollari

```bash
# Yozuv qayd etish (buxgalter)
curl -X POST http://localhost:8000/finance/ledger \
  -H "Authorization: Bearer <accountant_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "019012ab-0000-7000-8000-000000000001",
    "type": "debit",
    "amount": "500000.00",
    "currency": "UZS",
    "client_uuid": "019012ab-0000-7000-8000-000000000099"
  }'

# Balansni olish
curl http://localhost:8000/finance/balance/019012ab-... \
  -H "Authorization: Bearer <access_token>"

# Yozuvlar ro'yxati (do'kon bo'yicha filtrlangan)
curl "http://localhost:8000/finance/ledger?store_id=019012ab-...&entry_type=debit&limit=20" \
  -H "Authorization: Bearer <access_token>"
```

---

## 3. Append-only model

### 3.1 Nima uchun append-only?

Ombor harakatlari (`stock_movement`) va buxgalteriya yozuvlari (`ledger_entry`) hech qachon o'zgartirilmaydi yoki o'chirilmaydi. Bu moliyaviy audit izi uchun asosiy talab.

### 3.2 Ikki qatlamli himoya

| Qatlam | Mexanizm |
|---|---|
| Servis qatlami | `service.py` — faqat `INSERT` operatsiyasi; `UPDATE`/`DELETE` so'rov yo'q |
| DB qatlami (Postgres) | `RULE ... DO INSTEAD NOTHING` — `UPDATE`/`DELETE` so'rovlari jimgina bloklanadi |

SQLite (test muhiti) da faqat servis qatlami himoyasi ishlaydi — Postgres `RULE` qo'llab-quvvatlanmaydi.

### 3.3 Balans derivatsiyasi (kesh)

`stock_balance` va `account_balance` — harakat/yozuvlardan derivatsiyalangan kesh jadvallar. Har yangi harakat/yozuv yozilganda mos balans `UPDATE` qilinadi (servis qatlamida). Bu real-time qoldiq va balansni tez o'qish imkonini beradi.

### 3.4 Primary DB dan o'qish

Moliyaviy balans va ombor qoldig'i faqat primary DB dan o'qiladi — replica kechikishi (replication lag) moliyaviy aniqlikni buzmaydi. Bu ADR §3.4 talabi.

---

## 4. Idempotentlik

Takroriy so'rovlar (tarmoq xatosi, mobil offline-retry) bir xil natija berishi shart.

**Mexanizm (ikki qatlamli):**

1. **Redis SET NX** — `idem:stock:movement:{actor_id}:{client_uuid}` (TTL 24 soat); birinchi so'rovda kalit yaratiladi va saqlangan ID qaytariladi; keyingi so'rov bir xil ID ni qaytaradi.
2. **DB partial unique index** — `uq_stock_movement_client_uuid` / `uq_ledger_entry_client_uuid` — Redis ishlamasa ham DB darajasida dublikat bloklanadi.

`client_uuid` ixtiyoriy. Yuborilmasa — idempotentlik kafolati yo'q (har so'rovda yangi yozuv yaratiladi).

---

## 5. Migratsiya 0006

```bash
# Migratsiya ishlatish
cd backend && alembic upgrade head

# Yoki Make orqali
make migrate
```

**Yaratilgan jadvallar:**

| Jadval | Turi | Asosiy indeks |
|---|---|---|
| `stock_movement` | Append-only | `ix_stock_movement_product_warehouse` (product_id, warehouse_id) |
| `stock_balance` | Kesh | `uq_stock_balance_product_warehouse` (UNIQUE) |
| `ledger_entry` | Append-only | `ix_ledger_entry_store_id` |
| `account_balance` | Kesh | `uq_account_balance_store_id` (UNIQUE) |

**Downgrade ogohlantiruvi:** `alembic downgrade -1` — jadvalda qatorlar bo'lsa `RuntimeError` chiqadi va bloklanadi. Bu moliyaviy ma'lumotlar tasodifan yo'qolishini oldini oladi. Faqat bo'sh (0 qatorli) DB da downgrade xavfsiz.
