# Auth moduli — texnik qo'llanma (v0.2.0)

| | |
|---|---|
| **Prefiks** | `/auth` |
| **Modul** | `backend/app/modules/auth/` |
| **Versiya** | 0.2.0 |
| **Gate** | PASS (44/44 test) |

---

## 1. Endpointlar

| Metod | Yo'l | Kirish | Chiqish | Status kodlari |
|---|---|---|---|---|
| `POST` | `/auth/login` | `LoginRequest` (JSON) | `TokenPair` (JSON) | 200 · 401 · 403 |
| `POST` | `/auth/refresh` | `RefreshRequest` (JSON) | `TokenPair` (JSON) | 200 · 401 · 403 |
| `POST` | `/auth/logout` | `LogoutRequest` (JSON) | — (bo'sh tanа) | 204 · 400 |
| `GET` | `/auth/me` | `Authorization: Bearer <access_token>` | `MeResponse` (JSON) | 200 · 401 · 403 |

### So'rov / javob sxemalari

**`LoginRequest`**
```json
{
  "phone": "+998901234567",
  "password": "string (6–128 belgi)"
}
```

**`TokenPair`** (login va refresh javobi)
```json
{
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "token_type": "bearer"
}
```

**`RefreshRequest`**
```json
{
  "refresh_token": "<JWT>"
}
```

**`LogoutRequest`**
```json
{
  "refresh_token": "<JWT>"
}
```

**`MeResponse`**
```json
{
  "id": "018f1a2b-...",
  "phone": "+998901234567",
  "full_name": "Alisher Karimov",
  "role": "agent",
  "branch_id": "018f1a2b-..." ,
  "locale": "uz",
  "is_active": true,
  "biometric_enrolled": false
}
```

`role` qiymatlari: `administrator` | `agent` | `courier` | `accountant` | `store`

---

## 2. Token oqimi

```
1. LOGIN
   Klient → POST /auth/login {phone, password}
           ← 200 {access_token, refresh_token}

2. API CHAQIRUV
   Klient → GET /auth/me
            Header: Authorization: Bearer <access_token>
           ← 200 {id, phone, role, ...}

3. TOKEN YANGILASH (access muddati tugaganda — 401 kelganda)
   Klient → POST /auth/refresh {refresh_token}
           ← 200 {yangi access_token, yangi refresh_token}
              (eski refresh_token Redis denylist ga tushadi)

4. LOGOUT
   Klient → POST /auth/logout {refresh_token}
           ← 204
              (refresh_token denylist ga qo'shiladi)
              (klient tomonida access_token ham o'chiriladi)
```

---

## 3. Token claim'lari

### Access token

| Claim | Tur | Tavsif |
|---|---|---|
| `sub` | string (UUID) | Foydalanuvchi ID |
| `role` | string | Foydalanuvchi roli |
| `branch_id` | string (UUID) \| null | Filial ID; `administrator` uchun `null` |
| `type` | string | Har doim `"access"` |
| `jti` | string (UUID) | Unikal token ID (denylist uchun) |
| `exp` | int (Unix) | Muddati tugash vaqti (15 daqiqa) |
| `iat` | int (Unix) | Yaratilish vaqti |

### Refresh token

| Claim | Tur | Tavsif |
|---|---|---|
| `sub` | string (UUID) | Foydalanuvchi ID |
| `type` | string | Har doim `"refresh"` |
| `jti` | string (UUID) | Unikal token ID (denylist uchun) |
| `exp` | int (Unix) | Muddati tugash vaqti (30 kun) |
| `iat` | int (Unix) | Yaratilish vaqti |

---

## 4. Xavfsizlik xususiyatlari

| Xususiyat | Tafsilot |
|---|---|
| **Algoritm allowlist** | `algorithms=["HS256"]` qat'iy — algorithm confusion (CVE) oldini oladi; `python-jose` o'rniga `PyJWT` ishlatiladi |
| **Refresh rotatsiya + denylist** | Har `refresh` da eski token Redis ga denylist sifatida yoziladi; replay attack ishlaMaydi |
| **Fail-closed denylist** | Redis mavjud bo'lmasa `/auth/refresh` so'rovi rad etiladi; xavfli holat ruxsat etilmaydi |
| **Logout imzo tekshiruvi** | Imzosiz yoki muddati o'tgan token denylist ga qo'shilmaydi — `decode_token()` avval chaqiriladi |
| **bcrypt rounds=12** | Parol hashing; tekis parol hech qachon saqlanmaydi |
| **Enumeration/timing himoya** | Foydalanuvchi topilmasa va parol noto'g'ri bo'lsa bir xil 401 javob qaytariladi |
| **PII maskalash** | Barcha auth hodisalari `mask_pii()` orqali o'tib log yoziladi (`phone`, `token`, va boshqa maxfiy kalitlar `"***"`) |

---

## 5. `get_current_user` dependency

`backend/app/modules/auth/router.py` da aniqlangan FastAPI dependency. Barcha himoyalangan endpointlar ushbu dependency orqali joriy foydalanuvchini oladi.

```python
from app.modules.auth.router import get_current_user
from app.models.user import AppUser
from fastapi import Depends

@router.get("/example")
async def example(current_user: AppUser = Depends(get_current_user)):
    return {"user_id": str(current_user.id)}
```

**T2 (RBAC) da kengaytiriladi** — `has_permission()` dependency shu `get_current_user` ustiga quriladi.

---

## 6. Misol `curl` so'rovlari

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone": "+998901234567", "password": "secret123"}'
```

Javob:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Joriy foydalanuvchi ma'lumotlari

```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Javob:
```json
{
  "id": "018f1a2b-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
  "phone": "+998901234567",
  "full_name": "Alisher Karimov",
  "role": "agent",
  "branch_id": "018f1a2b-0000-7000-8000-000000000001",
  "locale": "uz",
  "is_active": true,
  "biometric_enrolled": false
}
```

### Token yangilash

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'
```

### Chiqish

```bash
curl -X POST http://localhost:8000/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'
# 204 No Content
```

---

## 7. Eslatmalar

- **RBAC majburlash** (ruxsat tekshiruvi) T2 da amalga oshiriladi. T1 faqat autentifikatsiyani ta'minlaydi (kim ekanligini aniqlaydi), avtorizatsiyani emas (nima qila olishini).
- `/auth/login` va `/auth/refresh` endpointlari `Authorization` header talab qilmaydi — ochiq endpointlar.
- Klient tomonida access token muddati (15 daqiqa) tugaganda 401 kelganda avtomatik `/auth/refresh` chaqirilishi tavsiya etiladi (silent refresh).
- Token saqlash: veb da `httpOnly` cookie yoki xavfsiz `sessionStorage`; mobilda `FlutterSecureStorage`.
