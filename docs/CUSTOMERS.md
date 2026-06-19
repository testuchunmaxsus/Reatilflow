# Mijoz bazasi moduli — texnik qo'llanma (v0.6.0)

| | |
|---|---|
| **Prefiks** | `/customers` |
| **Modul** | `backend/app/modules/customers/` |
| **Versiya** | 0.6.0 |
| **Gate** | PASS (278/278 test) |

---

## 1. Endpointlar

| Metod | Yo'l | RBAC ruxsati | Tavsif |
|---|---|---|---|
| `GET` | `/customers/stores` | `customers:view` | Paginated do'konlar ro'yxati (filter, blind-index qidiruv) |
| `POST` | `/customers/stores` | `customers:create` | Yangi do'kon yaratish (admin yoki agent) |
| `GET` | `/customers/stores/{id}` | `customers:view` | Bitta do'kon (RBAC scope; kuryer `StoreLimitedOut` oladi) |
| `PATCH` | `/customers/stores/{id}` | `customers:edit` | Qisman yangilash (optimistik lock) |
| `DELETE` | `/customers/stores/{id}` | `customers:delete` | Soft-delete (`deleted_at` o'rnatiladi) |
| `POST` | `/customers/stores/{id}/assign-agent` | `customers:edit` + admin check | Do'konga agent biriktirish (faqat administrator) |

---

## 2. PII shifrlash modeli

### 2.1 Shifrlangan maydonlar

| Ustun | Turi | Shifrlash | Blind-index |
|---|---|---|---|
| `inn` | `BYTEA` | AES-256-GCM | `inn_bi` (HMAC-SHA256, partial unique) |
| `inps` | `BYTEA` | AES-256-GCM | yo'q |
| `owner_name` | `BYTEA` | AES-256-GCM | yo'q |
| `phone` | `BYTEA` | AES-256-GCM | `phone_bi` (HMAC-SHA256, indekslangan) |

Qolgan ustunlar (`name`, `address`, `gps_lat`, `gps_lng`, `credit_limit`) ochiq-matn saqlanadi.

### 2.2 AES-256-GCM shifrlash

Shifrlash `app/core/crypto.py` da amalga oshiriladi. DB da saqlanadigan format:

```
| iv (12 bayt) | gcm_tag (16 bayt) | ciphertext |
```

- Har `encrypt_pii()` chaqiruvida yangi `os.urandom(12)` IV — bir xil matn har safar boshqacha ciferlangan.
- Authentication tag (`gcm_tag`) ma'lumot yaxlitligini tekshiradi.
- Kalit qiymati hech qachon loglarga tushirilmaydi.

### 2.3 EncryptedString (shaffof TypeDecorator)

`EncryptedString` SQLAlchemy `TypeDecorator` sifatida ORM modelida ishlatiladi. Dasturchi oddiy `str` bilan ishlaydi — shifrlash/deshifrlash avtomatik:

```python
# app/models/store.py
class Store(Base):
    inn:        Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    inps:       Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    phone:      Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
```

Yozishda: `str → encrypt_pii() → bytes` (DB ga `BYTEA`).
O'qishda: `bytes → decrypt_pii() → str` (Python kodiga oddiy `str`).

---

## 3. Blind-index qidiruv

### 3.1 Nima uchun blind-index

PII shifrlangan saqlanadi, shuning uchun `WHERE inn LIKE '%...'` ishlamaydi. Aniq-moslik (`exact match`) qidiruv uchun HMAC-SHA256 blind-index ishlatiladi.

- So'rovdagi qiymat `blind_index()` orqali o'tkaziladi.
- DB da `inn_bi == blind_index(search_inn)` solishtirish.
- **Ochiq-matn `LIKE` yo'q** — DB operator shifrlangan ma'lumotni ko'rmaydi.

### 3.2 blind_index() ishlash tartibi

```python
# app/core/crypto.py
def blind_index(value: str) -> str:
    normalized = value.strip().lower()          # normalize
    mac = hmac.new(key, normalized.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")
```

- Normalize: `strip()` + `lower()` — `" 123456789 "` va `"123456789"` bir xil indeks beradi.
- Kalit: `BLIND_INDEX_KEY` (64-hex, env dan).
- Natija: URL-safe base64, padding yo'q (44 belgi).

### 3.3 Qidiruv so'rovlari

`GET /customers/stores?search_inn=123456789` — INN bo'yicha aniq-moslik.
`GET /customers/stores?search_phone=998901234567` — telefon bo'yicha aniq-moslik.
`GET /customers/stores?search_name=Do'kon` — nom bo'yicha `ILIKE` (ochiq-matn, PII emas).

---

## 4. Kalitlar va konfiguratsiya

### 4.1 Muhit o'zgaruvchilari

| O'zgaruvchi | Format | Tavsif |
|---|---|---|
| `PII_ENCRYPTION_KEY` | 64-belgili hex | AES-256-GCM kaliti (32 bayt) |
| `BLIND_INDEX_KEY` | 64-belgili hex | HMAC-SHA256 kaliti (32 bayt) |

Kalitlarni yaratish:

```bash
openssl rand -hex 32   # PII_ENCRYPTION_KEY uchun
openssl rand -hex 32   # BLIND_INDEX_KEY uchun
```

`.env` fayliga qo'shish:

```
PII_ENCRYPTION_KEY=<64-belgili-hex>
BLIND_INDEX_KEY=<64-belgili-hex>
```

### 4.2 Format validatsiya

Faqat 64-belgili hex string qabul qilinadi. SHA-256 fallback ataylab olib tashlangan — noto'g'ri format yashirin o'tib ketmaydi:

```
PII_ENCRYPTION_KEY noto'g'ri format: kutilgan 64 belgili hex, olingan 32 belgi.
openssl rand -hex 32 bilan yangi kalit yarating.
```

### 4.3 Startup probe

Ilova ishga tushganda `verify_crypto_keys()` avtomatik chaqiriladi (`main.py` lifespan). Encrypt→decrypt round-trip muvaffaqiyatsiz bo'lsa ilova **boshlanmaydi**:

```
RuntimeError: Crypto startup probe FAILED (decrypt): ...
PII_ENCRYPTION_KEY to'g'ri ekanini tekshiring.
```

---

## 5. RBAC va scope

### 5.1 Kim nimani ko'radi

| Rol | Ko'rinadigan do'konlar | Javob sxemasi |
|---|---|---|
| `administrator` | Barcha (branch filtri ixtiyoriy) | `StoreOut` (to'liq PII) |
| `accountant` | Barcha (branch filtri ixtiyoriy) | `StoreOut` (to'liq PII) |
| `agent` | O'zi biriktirgan do'konlar | `StoreOut` (to'liq PII) |
| `store` | Faqat o'zi (`Store.user_id == user.id`) | `StoreOut` (to'liq PII) |
| `courier` | Branch doirasidagi do'konlar | `StoreLimitedOut` (PII yo'q) |

### 5.2 StoreLimitedOut — kuryer uchun cheklangan javob

`StoreLimitedOut` da faqat quyidagi maydonlar qaytadi:

```json
{
  "id": "019012ab-cdef-7000-8000-123456789abc",
  "name": "Sarvar do'koni",
  "address": "Toshkent, Chilonzor 5",
  "gps_lat": "41.299496",
  "gps_lng": "69.240073"
}
```

`inn`, `inps`, `owner_name`, `phone`, `credit_limit` — kuryer javobida **mavjud emas**.

### 5.3 assign-agent va scope-fields — admin-only

`POST /customers/stores/{id}/assign-agent` faqat `administrator` roli uchun. `users_id`, `agent_id`, `branch_id` maydonlarini `PATCH` orqali o'zgartirish ham faqat administrator tomonidan amalga oshirilishi kerak — servis qatlamida rol tekshiruvi mavjud.

---

## 6. So'rov va javob sxemalari

### 6.1 StoreCreate

`POST /customers/stores` tanasi:

```json
{
  "name": "Namuna do'koni",
  "inn": "123456789",
  "inps": "12345678901234",
  "owner_name": "Alisher Karimov",
  "phone": "998901234567",
  "address": "Toshkent sh., Yunusobod t., 1-uy",
  "gps_lat": "41.299496",
  "gps_lng": "69.240073",
  "segment_id": null,
  "agent_id": null,
  "branch_id": null,
  "credit_limit": "5000000.00",
  "user_id": null,
  "client_uuid": "019012ab-cdef-7000-8000-000000000001"
}
```

`client_uuid` ixtiyoriy — idempotentlik uchun (Redis orqali). `inn` unikalligi `inn_bi` partial unique index orqali ta'minlanadi.

### 6.2 StoreOut

```json
{
  "id": "019012ab-cdef-7000-8000-123456789abc",
  "name": "Namuna do'koni",
  "inn": "123456789",
  "inps": "12345678901234",
  "owner_name": "Alisher Karimov",
  "phone": "998901234567",
  "address": "Toshkent sh., Yunusobod t., 1-uy",
  "gps_lat": "41.299496",
  "gps_lng": "69.240073",
  "segment_id": null,
  "agent_id": "019012ab-0000-7000-8000-aaaaaaaaaaaa",
  "branch_id": null,
  "credit_limit": "5000000.00",
  "user_id": null,
  "version": 1,
  "created_at": "2026-06-16T10:00:00Z",
  "updated_at": "2026-06-16T10:00:00Z",
  "deleted_at": null
}
```

`inn`, `inps`, `owner_name`, `phone` — DB dan `BYTEA` sifatida o'qilib, `EncryptedString` tomonidan avtomatik deshifrlangan holda qaytariladi.

### 6.3 StoreUpdate

`PATCH /customers/stores/{id}` tanasi — faqat berilgan maydonlar yangilanadi:

```json
{
  "address": "Toshkent sh., Chilonzor t., 5-uy",
  "credit_limit": "7500000.00",
  "version": 1
}
```

`version` majburiy. Serverda saqlangan versiyadan farq qilsa `409 Conflict`.

### 6.4 AssignAgentRequest

`POST /customers/stores/{id}/assign-agent` tanasi:

```json
{
  "agent_id": "019012ab-0000-7000-8000-aaaaaaaaaaaa"
}
```

Javob:

```json
{
  "store_id": "019012ab-cdef-7000-8000-123456789abc",
  "agent_id": "019012ab-0000-7000-8000-aaaaaaaaaaaa",
  "assigned_at": "2026-06-16T10:05:00Z"
}
```

---

## 7. curl misollari

Quyidagi misollarda `$TOKEN` — Bearer access token, `$BASE` — `http://localhost:8000`.

### Do'kon yaratish

```bash
curl -X POST "$BASE/customers/stores" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Namuna do'\''koni",
    "inn": "123456789",
    "phone": "998901234567",
    "address": "Toshkent, Yunusobod"
  }'
```

### Do'konlar ro'yxati (INN bo'yicha qidiruv)

```bash
curl "$BASE/customers/stores?search_inn=123456789&limit=20&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

### Bitta do'kon

```bash
curl "$BASE/customers/stores/019012ab-cdef-7000-8000-123456789abc" \
  -H "Authorization: Bearer $TOKEN"
```

### Do'konni yangilash

```bash
curl -X PATCH "$BASE/customers/stores/019012ab-cdef-7000-8000-123456789abc" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "address": "Toshkent, Chilonzor 5",
    "version": 1
  }'
```

### Agent biriktirish (faqat administrator)

```bash
curl -X POST "$BASE/customers/stores/019012ab-cdef-7000-8000-123456789abc/assign-agent" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "019012ab-0000-7000-8000-aaaaaaaaaaaa"}'
```

### Do'konni o'chirish (soft-delete)

```bash
curl -X DELETE "$BASE/customers/stores/019012ab-cdef-7000-8000-123456789abc" \
  -H "Authorization: Bearer $TOKEN"
# → 204 No Content
```

---

## 8. Migratsiya 0004 — deploy runbook

### 8.1 Deploy oldidan

```bash
# 1. Ma'lumotlar bazasi zaxira nusxasi
pg_dump -Fc -h localhost -U postgres retail_db > retail_backup_pre_0004.dump

# 2. Ochiq-matn PII qatorlar soni tekshiruvi (0 bo'lishi shart)
psql -h localhost -U postgres -d retail_db \
  -c "SELECT COUNT(*) FROM store WHERE inn IS NOT NULL;"
# Natija 0 bo'lmasa migratsiyani ISHGA TUSHURMANG — avval ilovani yangilang
```

Migratsiyada avtomatik guard mavjud: `inn IS NOT NULL` qatorlar topilsa `RuntimeError` ko'tariladi va migratsiya to'xtatiladi. Guard faqat PostgreSQL da ishlaydi.

### 8.2 Migratsiyani ishga tushirish

```bash
cd backend
alembic upgrade 0004
# yoki:
make migrate
```

### 8.3 Yangi env o'zgaruvchilarni o'rnatish

```bash
# .env yoki prod secret manager da:
PII_ENCRYPTION_KEY=<openssl rand -hex 32 natijasi>
BLIND_INDEX_KEY=<openssl rand -hex 32 natijasi>
```

Kalitlarsiz ilova ishga tushmaydi (startup probe).

### 8.4 Downgrade haqida ogohlantirish

`alembic downgrade 0003` — **PII YO'QOLADI**.

Downgrade natijasida `BYTEA → VARCHAR` o'tkazishda barcha shifrlangan `inn`, `inps`, `owner_name`, `phone` qiymatlari `NULL` ga aylanadi. Bu qaytarib bo'lmaydi.

Downgrade faqat `store` jadvalida 0 qator bo'lganda xavfsiz. Production muhitida downgrade qilmang.
