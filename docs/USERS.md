# RETAIL — Foydalanuvchi boshqaruvi moduli (T6)

| | |
|---|---|
| **Versiya** | 0.31.0 |
| **Sana** | 2026-06-19 |
| **Holati** | Yakunlandi — gate PASS (802 test, +2 v0.31.0) |
| **Prefiks** | `/users` |

---

## 1. Endpointlar

Barcha endpointlar **faqat administrator** roliga ruxsat etiladi (ikki qatlamli himoya: `require_permission` + `_admin_only` role check).

| Metod | Yo'l | Faqat admin | Tavsif |
|---|---|---|---|
| `GET` | `/users` | Ha | Paginated ro'yxat (role/branch_id/is_active filtrlari) |
| `POST` | `/users` | Ha | Yangi foydalanuvchi yaratish |
| `GET` | `/users/{id}` | Ha | Bitta foydalanuvchi ma'lumotlari |
| `PATCH` | `/users/{id}` | Ha | Qisman yangilash (optimistik lock) |
| `PATCH` | `/users/{id}/deactivate` | Ha | Deaktivatsiya (bloklash) |
| `PATCH` | `/users/{id}/activate` | Ha | Qayta aktivlashtirish (deaktivatsiya teskarisi) |

---

## 2. So'rov va javob sxemalari

### `UserCreate` (POST /users body)

| Maydon | Tip | Majburiy | Tavsif |
|---|---|---|---|
| `full_name` | `string` (1–255) | Ha | To'liq ismi (PII, shifrlangan) |
| `phone` | `string` (7–20) | Ha | Telefon raqami (login identifikatori, PII, shifrlangan) |
| `role` | `string` | Ha | `administrator \| agent \| courier \| accountant \| store` |
| `password` | `string` (6–128) | Ha | Tekis parol — bcrypt(rounds=12) bilan hash qilinadi |
| `branch_id` | `UUID \| null` | Yo'q | Filial ID (NULL = barcha filiallar) |
| `locale` | `string` | Yo'q | `uz \| ru` (default: `uz`) |
| `biometric_enrolled` | `bool` | Yo'q | Biometrik ro'yxat flagi (default: `false`) |
| `device_id` | `string \| null` | Yo'q | Qurilma ID (maks 255 belgi) |
| `client_uuid` | `UUID \| null` | Yo'q | Idempotentlik UUID (ixtiyoriy, POST ni xavfsiz qayta yuborish uchun) |

### `UserUpdate` (PATCH /users/{id} body)

| Maydon | Tip | Majburiy | Tavsif |
|---|---|---|---|
| `version` | `integer` | Ha | Optimistik lock — joriy versiya; mos kelmasa 409 |
| `full_name` | `string \| null` | Yo'q | — |
| `phone` | `string \| null` | Yo'q | O'zgarsa phone_bi ham yangilanadi |
| `role` | `string \| null` | Yo'q | — |
| `branch_id` | `UUID \| null` | Yo'q | — |
| `locale` | `string \| null` | Yo'q | — |
| `biometric_enrolled` | `bool \| null` | Yo'q | — |
| `device_id` | `string \| null` | Yo'q | — |

`version` dan tashqari kamida bitta maydon berilishi shart; aks holda 422.

### `UserOut` (barcha endpointlar javobi)

```json
{
  "id": "01963b2a-...",
  "full_name": "Alisher Toshmatov",
  "phone": "+998901234567",
  "role": "agent",
  "branch_id": null,
  "locale": "uz",
  "biometric_enrolled": false,
  "device_id": null,
  "is_active": true,
  "version": 1,
  "created_at": "2026-06-16T08:00:00Z",
  "updated_at": "2026-06-16T08:00:00Z"
}
```

`password_hash` hech qachon javobga kirmaydi.

### `PaginatedUsers` (GET /users javobi)

```json
{
  "items": [ /* UserOut ro'yxati */ ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

## 3. PII shifrlash va phone_bi (blind-index)

### Shifrlash arxitekturasi

`app_user.phone` va `app_user.full_name` ustunlari DB da `BYTEA` tipida saqlanadi. Yozish va o'qishda `EncryptedString` SQLAlchemy TypeDecorator avtomatik `encrypt_pii()` / `decrypt_pii()` chaqiradi — ORM foydalanuvchisi shifrlashni ko'rmaydi.

| Ustun | DB tipi | Shifrlash | Maqsad |
|---|---|---|---|
| `phone` | `BYTEA` | AES-256-GCM | Saqlash |
| `full_name` | `BYTEA` | AES-256-GCM | Saqlash |
| `phone_bi` | `VARCHAR(64)` | HMAC-SHA256 | Qidiruv (unique) |

`phone_bi = blind_index(phone)` — telefon raqami normalizatsiya (strip + lowercase) qilinib HMAC hisoblanadi, `base64url` sifatida saqlanadi. Partial unique index: `(phone_bi) WHERE phone_bi IS NOT NULL`.

### Nima uchun blind-index

Shifrlangan `BYTEA` ustunida `WHERE phone = :val` ishlamaydi — har xil IV bilan shifrlanadi, har safar boshqa bayt ketma-ketligi. `phone_bi` aniq-moslik (exact-match) qidiruvni taqdim etadi:

```python
stmt = select(AppUser).where(AppUser.phone_bi == blind_index(phone))
```

**Auth login ham shu orqali ishlaydi** (`app/modules/auth/service.py → login()`).

### Muhit o'zgaruvchilari

```bash
# 64 belgili hex — openssl rand -hex 32 bilan generatsiya
PII_ENCRYPTION_KEY=<64-belgili-hex>
BLIND_INDEX_KEY=<64-belgili-hex>
```

Barcha muhitlarda faqat 64-belgili hex qabul qilinadi. Production/staging da:
- `CHANGE_ME` taqiqlangan
- Dev-default qiymatlar (source code da ma'lum) **denylist** orqali bloklanadi — `.env` o'rnatilmasa ilova ishga tushmaydi

---

## 4. RBAC va xavfsizlik

### Ikki qatlamli admin himoyasi

Har bir endpoint:
1. `require_permission(Module.RBAC, Action.CREATE/VIEW/EDIT)` — JWT token va rol tekshiruvi
2. `_admin_only(current_user)` — `role != "administrator"` bo'lsa 403

Bitta qatlam aylanib o'tilsa ikkinchisi bloklaydi.

### Self-deactivation himoyasi

`PATCH /users/{id}/deactivate` — agar `id` === joriy admin `id` bo'lsa:

```json
HTTP 403
{ "message_key": "users.cannot_deactivate_self", ... }
```

Administrator o'zini bloklash yo'li bilan tizimni boshqaruvchisiz qoldira olmaydi.

### Xato kodlari

| HTTP kod | `message_key` | Sabab |
|---|---|---|
| 401 | `auth.authentication_required` | Token yo'q yoki yaroqsiz |
| 403 | `rbac.permission_denied` | Administrator emas |
| 403 | `users.cannot_deactivate_self` | Admin o'zini deaktiv qilmoqchi (`/deactivate` da) |
| 404 | `users.user_not_found` | ID bo'yicha topilmadi |
| 409 | `users.duplicate_phone` | Telefon raqam band |
| 409 | `users.version_conflict` | Optimistik lock — versiya mos kelmadi |
| 422 | `users.invalid_role` | Noto'g'ri rol qiymati |

---

## 5. `curl` misollari

Quyidagi misollarda `TOKEN` o'rniga admin `access_token` qo'ying.  
Telefon va ism — namuna qiymatlari (real PII ishlatmang).

### Yangi foydalanuvchi yaratish

```bash
curl -X POST http://localhost:8000/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Alisher Toshmatov",
    "phone": "+998901234567",
    "role": "agent",
    "password": "SecurePass123",
    "locale": "uz"
  }'
```

Javob: `HTTP 201` + `UserOut`

### Login (phone blind-index orqali)

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+998901234567",
    "password": "SecurePass123"
  }'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

Login ichida `blind_index(phone)` hisoblanib, `phone_bi` ustunida qidiriladi.

### Foydalanuvchilar ro'yxati (filtrlash bilan)

```bash
# Barcha agentlar
curl "http://localhost:8000/users?role=agent&limit=20&offset=0" \
  -H "Authorization: Bearer $TOKEN"

# Faqat aktiv foydalanuvchilar
curl "http://localhost:8000/users?is_active=true" \
  -H "Authorization: Bearer $TOKEN"
```

### Foydalanuvchini yangilash (optimistik lock)

```bash
curl -X PATCH http://localhost:8000/users/01963b2a-0000-7000-8000-000000000001 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Alisher Toshmatov (yangilangan)",
    "version": 1
  }'
```

`version` mos kelmasa: `HTTP 409 users.version_conflict`

### Foydalanuvchini deaktivatsiya qilish

```bash
curl -X PATCH \
  http://localhost:8000/users/01963b2a-0000-7000-8000-000000000002/deactivate \
  -H "Authorization: Bearer $TOKEN"
```

Javob: `HTTP 200` + `UserOut` (`is_active: false`)

### Foydalanuvchini qayta aktivlashtirish

```bash
curl -X PATCH \
  http://localhost:8000/users/01963b2a-0000-7000-8000-000000000002/activate \
  -H "Authorization: Bearer $TOKEN"
```

Javob: `HTTP 200` + `UserOut` (`is_active: true`)

Xato holatlari:

| HTTP kod | `message_key` | Sabab |
|---|---|---|
| 401 | `auth.authentication_required` | Token yo'q yoki yaroqsiz |
| 403 | `rbac.permission_denied` | Administrator emas |
| 404 | `users.user_not_found` | ID bo'yicha topilmadi |

---

## 6. `PATCH /users/{id}/activate` — texnik tavsif

| Xususiyat | Qiymat |
|---|---|
| Metod | `PATCH` |
| Yo'l | `/users/{id}/activate` |
| Maqsad | Ilgari deaktiv qilingan foydalanuvchini qayta faollashtirish |
| RBAC | Faqat administrator — `require_permission(RBAC, EDIT)` + `_admin_only` ikki qatlam |
| Natija | `is_active=True`, audit log yozuvi + outbox event |
| Javob | `HTTP 200` + `UserOut` |
| 404 | Foydalanuvchi topilmasa `users.user_not_found` |

`deactivate` endpointidan farq: self-deactivation himoyasi yo'q (admin o'zini qayta aktivlashtirishi mumkin, bu xavfsiz).

Xizmat funksiyasi: `service.activate_user(db, user_id, actor_id=current_user.id)`.

---

## 7. Migratsiya 0005 — Deploy runbook

### Tavsif

`alembic/versions/0005_user_phone_encrypt.py` — `app_user.phone` va `full_name` ustunlarini `VARCHAR → BYTEA` ga o'tkazadi va mavjud qatorlar uchun in-migration backfill bajaradi.

### Qadamlar

**1. Backup**

```bash
pg_dump -Fc retail > retail_pre_0005_$(date +%Y%m%d_%H%M%S).dump
```

**2. `.env` tekshirish**

`PII_ENCRYPTION_KEY` va `BLIND_INDEX_KEY` to'g'ri 64-belgili hex bo'lishi shart. Kalit noto'g'ri bo'lsa migratsiya xato bilan to'xtaydi va rollback bo'ladi.

**3. Migratsiyani ishga tushirish**

```bash
cd backend
alembic upgrade 0005
# yoki:
alembic upgrade head
```

**4. Nima bo'ladi (in-migration backfill)**

Migratsiya ichida:
- `phone_bi` ustuni nullable TEXT sifatida qo'shiladi
- Postgres: mavjud qatorlar batch'da (500 ta) o'qiladi; `phone` → `encrypt_pii()`, `full_name` → `encrypt_pii()`, `phone_bi = blind_index(phone)` yoziladi
- Ustun tipi `BYTEA` ga o'zgartiriladi (`USING phone::bytea`)
- `uq_app_user_phone_bi` partial unique index, `ix_app_user_phone_bi` indeks yaratiladi
- Eski `uq_app_user_phone` constraint olib tashlanadi

**5. Katta jadval uchun eslatma**

Agar `app_user` jadvalida millionlab qatorlar bo'lsa, in-migration batch backfill (`_BATCH_SIZE=500`) uzoq vaqt olishi mumkin va migration lock `app_user` jadvalini bloklaydi. Bu holat uchun:
- Maintenance window rejalashtiring yoki
- `pg_repack`/online migration yondashuvini ko'rib chiqing (backfill ni alohida skriptda, migratsiya DDL dan alohida)

Hozirgi deployment uchun (bootstrap bosqichi, yuzlab yozuvlar) standart yondashuv yetarli.

**6. Downgrade guard**

`downgrade()` — `app_user` jadvalida qatorlar bo'lsa PostgreSQL da bloklanadi:

```
RuntimeError: downgrade() BLOKLANDI: app_user jadvalida N ta qator mavjud.
Downgrade qilish barcha shifrlangan phone va full_name qiymatlarini yo'q qiladi (PII yo'qolishi).
```

Downgrade faqat bo'sh (0 qatorli) DB da xavfsiz. Production da downgrade qilmang.

---

## 8. Bog'liq fayllar

- `backend/app/modules/users/router.py` — endpoint yo'naltiruvchi
- `backend/app/modules/users/service.py` — biznes mantiq
- `backend/app/modules/users/schemas.py` — Pydantic sxemalar
- `backend/app/models/user.py` — SQLAlchemy ORM modeli
- `backend/app/core/crypto.py` — `EncryptedString`, `encrypt_pii`, `blind_index`
- `backend/alembic/versions/0005_user_phone_encrypt.py` — migratsiya
- `backend/app/tests/users/` — 44 ta test
- [docs/AUTH.md](AUTH.md) — login, token oqimi
- [docs/CUSTOMERS.md](CUSTOMERS.md) — T5, bir xil PII arxitekturasi
