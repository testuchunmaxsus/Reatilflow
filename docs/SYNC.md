# SYNC moduli texnik qo'llanmasi — T13 Outbox Sync API

Versiya: **0.11.0** | Holat: ✅ Yakunlandi (gate PASS, 452/452 test)

Sync API Flutter (va boshqa offline-first) klientlari uchun ikki yo'nalishli sinxronizatsiyani ta'minlaydi:

- **Push** (`POST /sync/push`) — klientdagi offline o'zgarishlarni serverga yuborish.
- **Pull** (`GET /sync/pull`) — serverdan klientga delta hodisalarni olish.

---

## Endpointlar

| Metod | Yo'l | Tavsif |
|---|---|---|
| `POST` | `/sync/push` | Offline operatsiyalar batchi (klient→server) |
| `GET` | `/sync/pull` | Delta hodisalar (server→klient, kursor asosida) |

**Autentifikatsiya**: ikkalasi ham `Authorization: Bearer <access_token>` talab qiladi.

**RBAC**: barcha autentifikatsiyalangan rollar (`agent`, `store`, `courier`, `administrator`, `accountant`) ruxsatli. RBAC scope push da har op uchun aloyida tekshiriladi (mavjud servis orqali).

### Rate-limit

| Endpoint | Limit | Oyna |
|---|---|---|
| `POST /sync/push` | 60 so'rov | 60 sekund |
| `GET /sync/pull` | 120 so'rov | 60 sekund |

Limit oshganda: `429` + `message_key: "sync.rate_limited"`.

Redis xato bo'lsa rate-limit o'tkazib yuboriladi (graceful degradation) — so'rov bloklanmaydi.

---

## Kursor mexanizmi (server-avtoritar monoton seq)

Pull kursori `outbox_event.seq` ustuniga asoslangan. Bu ustun **Postgres Sequence** (`outbox_event_seq`) orqali to'ldiriladi — multi-worker muhitda ham monoton va takrorlanuvchan emas.

**Asosiy qoidalar:**

- Klient o'z soatiga (`created_at` wall-clock ga) ishonmaydi (ADR §3.5).
- `since=0` birinchi so'rovda — barcha hodisalardan boshlanadi.
- `next_cursor` = skanerlangan oxirgi hodisa `seq` qiymati.
- Filtrlangan (scope da ko'rinmaydigan) hodisalar ham kursorni ilgarilatadi — cheksiz bo'sh pull tsikli bo'lmaydi.
- `has_more=true` bo'lsa yana so'rov yuborish kerak (keyingi sahifa).

```
klient                       server
  |--- GET /sync/pull?since=0 --->|
  |<-- changes[], next_cursor=42 --|
  |--- GET /sync/pull?since=42 -->|
  |<-- changes[], next_cursor=87 --|
  ...
```

---

## POST /sync/push

### So'rov

```json
{
  "ops": [
    {
      "op_type": "order.create",
      "client_uuid": "018f1a2b-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
      "payload": {
        "store_id": "018e1234-0000-7000-8000-000000000001",
        "lines": [
          {"product_id": "018e1234-0000-7000-8000-000000000002", "qty": "2"},
          {"product_id": "018e1234-0000-7000-8000-000000000003", "qty": "1"}
        ],
        "mode": "bozor",
        "currency": "UZS"
      }
    }
  ]
}
```

**Maydonlar:**

| Maydon | Tur | Tavsif |
|---|---|---|
| `ops` | `list[SyncOp]` | Operatsiyalar ro'yxati (min 1, max 100) |
| `ops[].op_type` | `string` | Operatsiya turi (masalan `order.create`) |
| `ops[].client_uuid` | `string` | Klient idempotentlik UUID |
| `ops[].payload` | `dict` | Op turiga qarab farqli tuzilma |

### Javob

```json
{
  "results": [
    {
      "client_uuid": "018f1a2b-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
      "status": "applied",
      "server_id": "018f9999-0000-7000-8000-000000000099",
      "message_key": null
    }
  ]
}
```

**`status` qiymatlari:**

| Holat | Ma'no |
|---|---|
| `applied` | Op muvaffaqiyatli bajarildi; `server_id` to'ldirilgan |
| `duplicate` | Avval yuborilgan `client_uuid` — asl natija qaytarildi |
| `conflict` | Boshqa aktor shu `client_uuid` ni ishlatgan (IDOR bloklandi) |
| `error` | Xato; `message_key` da sabab |

### Op-darajali izolyatsiya (SAVEPOINT)

Har operatsiya `db.begin_nested()` (PostgreSQL `SAVEPOINT`) ichida bajariladi. Bitta op rollback bo'lsa boshqa oplar ta'sirlanmaydi — batch to'liq yiqilmaydi.

**Muhim cheklov:** `create_order()` `IntegrityError` da full-session rollback chaqirishi mumkin, bu SAVEPOINT ni ham bekor qiladi. Tor ssenariy: bir xil `client_uuid` bilan ikki parallel so'rov kelganda batch idempotentlik konflikti yuzaga kelishi mumkin. Bu holat T14 da to'liq hal qilinadi.

### Hozirda qo'llab-quvvatlanadigan op turlari

| `op_type` | Tavsif |
|---|---|
| `order.create` | Do'kon buyurtmasi yaratish — `create_order()` qayta ishlatiladi |

Yangi op turi uchun `service.py` dagi `_OP_REGISTRY` ga handler qo'shing.

#### `order.create` payload

| Maydon | Majburiy | Tavsif |
|---|---|---|
| `store_id` | ha | Do'kon UUID (string) |
| `lines` | ha | `[{"product_id": "...", "qty": "..."}]` ro'yxati |
| `mode` | yo'q | `"bozor"` yoki `"oddiy"` (default: `"bozor"`) |
| `currency` | yo'q | ISO 4217 kod (default: `"UZS"`) |

---

## GET /sync/pull

### So'rov parametrlari

| Parametr | Tur | Default | Tavsif |
|---|---|---|---|
| `since` | `int` | `0` | Oxirgi ko'rilgan `seq` kursor (0 = boshidan) |
| `limit` | `int` | `50` | Bir so'rovda max hodisalar (1–200) |

### Javob

```json
{
  "changes": [
    {
      "entity_type": "order",
      "entity_id": "018f9999-0000-7000-8000-000000000099",
      "event_type": "order.created",
      "seq": 42,
      "snapshot": {
        "id": "018f9999-0000-7000-8000-000000000099",
        "store_id": "018e1234-0000-7000-8000-000000000001",
        "status": "new",
        "total_amount": "150000.00",
        "currency": "UZS",
        "ordered_at": "2026-06-17T10:00:00",
        "version": 1
      }
    }
  ],
  "next_cursor": 42,
  "has_more": false
}
```

**Javob maydonlari:**

| Maydon | Tur | Tavsif |
|---|---|---|
| `changes` | `list[ChangeItem]` | Foydalanuvchi scope'idagi yangi hodisalar |
| `next_cursor` | `int` | Keyingi `since=` qiymati |
| `has_more` | `bool` | `true` bo'lsa yana so'rov kerak |

**`ChangeItem` tuzilmasi:**

| Maydon | Tavsif |
|---|---|
| `entity_type` | Agregat turi: `order`, `store`, `product`, ... |
| `entity_id` | Agregat UUID (string) |
| `event_type` | Hodisa turi: `order.created`, `product.updated`, ... |
| `seq` | Monoton kursor qiymati |
| `snapshot` | Klient `upsert` uchun joriy entity holati |

---

## Pull scope — IDOR himoyasi

Har foydalanuvchi faqat o'z scope'idagi hodisalarni oladi:

| Aggregate type | Kim ko'radi |
|---|---|
| `product`, `product_price`, `price`, `promo`, `category`, `price_segment`, `catalog` | Barcha autentifikatsiyalangan foydalanuvchilar (global read-only) |
| `order`, `order_template` | agent/store — faqat o'z do'konlariga tegishli; administrator/accountant — barchasi |
| `store` | agent — faqat bog'liq do'konlari; store roli — faqat o'zi; administrator/accountant — barchasi |
| Noma'lum tip | Faqat administrator/accountant |

**fail-safe deny:** agar hodisa payload'ida `store_id` bo'lmasa yoki JSON parse xatosi bo'lsa — hodisa ko'rinmaydi (xato chiqarilmaydi, sukunatda o'tkazib yuboriladi). Bu prinsip: ruxsatsiz ma'lumot oqib chiqishi > bo'sh pull natijadan yaxshiroqdir.

---

## Migratsiya 0009 — outbox_event.seq

`outbox_event` jadvaliga `seq` ustuni va `outbox_event_seq` Postgres Sequence qo'shiladi.

**Postgres upgrade bosqichlari:**

```
1. CREATE SEQUENCE IF NOT EXISTS outbox_event_seq
2. ALTER TABLE outbox_event ADD COLUMN IF NOT EXISTS seq BIGINT NULL DEFAULT nextval('outbox_event_seq')
3. UPDATE outbox_event SET seq = nextval('outbox_event_seq') WHERE seq IS NULL  -- backfill
4. ALTER TABLE outbox_event ALTER COLUMN seq SET NOT NULL
5. CREATE UNIQUE INDEX ix_outbox_event_seq ON outbox_event (seq)
```

Downgrade guard: `outbox_event` da qatorlar bo'lsa `RuntimeError` — ishlab turgan DB da downgrade bajarilmaydi.

Ishga tushirish:

```bash
cd backend && alembic upgrade head
```

---

## Offline-first oqimi (Flutter klient)

```
[Flutter klient]
  1. Lokal o'zgarish sodir bo'ladi (masalan, yangi buyurtma)
  2. O'zgarish lokal outbox ga yoziladi (UUID, op_type, payload)
  3. Tarmoq mavjud bo'lganda: POST /sync/push (batch)
  4. Har op uchun natija: applied → server_id saqlash; conflict/error → foydalanuvchiga ko'rsatish
  5. Vaqti-vaqti bilan: GET /sync/pull?since={next_cursor}
  6. changes[] → lokal DB upsert (entity_type + entity_id asosida)
  7. next_cursor saqlash — keyingi so'rov uchun
```

T14 (Flutter offline-first) da to'liq skelet va konflikt yechimi modeli qo'shiladi.

---

## curl misollari

### Push — batch buyurtma yaratish

```bash
curl -X POST http://localhost:8000/sync/push \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ops": [
      {
        "op_type": "order.create",
        "client_uuid": "018f1a2b-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
        "payload": {
          "store_id": "018e1234-0000-7000-8000-000000000001",
          "lines": [
            {"product_id": "018e1234-0000-7000-8000-000000000002", "qty": "3"}
          ],
          "mode": "bozor",
          "currency": "UZS"
        }
      }
    ]
  }'
```

### Pull — kursor asosida delta

```bash
# Birinchi pull (boshidan)
curl "http://localhost:8000/sync/pull?since=0&limit=50" \
  -H "Authorization: Bearer <access_token>"

# Keyingi pull (next_cursor dan)
curl "http://localhost:8000/sync/pull?since=42&limit=50" \
  -H "Authorization: Bearer <access_token>"
```

---

## Ma'lum cheklovlar

| Cheklov | Rejalashtirilgan |
|---|---|
| Push SAVEPOINT + `create_order()` rollback o'zaro ta'siri: parallel bir xil `client_uuid` bilan batch idempotentlik konflikti (Postgres tor ssenariy) | T14 |
| `delete_template` payload'da `store_id` qisqa — scope filtri payload'dan `store_id` oladi, lekin template delete payload'da store_id kichik bo'lishi mumkin | T14 (kichik) |
| Pull snapshot batch hajmi: limit 200 — juda katta to'plamda snapshot fetch sekinlashishi mumkin | T27 (metrika + tuning) |
| Sync metrika (Prometheus): push/pull latency, batch hajmi, rate-limit hiti | T27 |
