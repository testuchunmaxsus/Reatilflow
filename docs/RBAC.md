# RBAC moduli — texnik qo'llanma (v0.3.0)

| | |
|---|---|
| **Prefiks** | `/rbac` |
| **Modul** | `backend/app/modules/rbac/` |
| **Versiya** | 0.3.0 |
| **Gate** | PASS (131/131 test) |
| **ADR** | §3.6 — 5 rol × 11 modul ruxsat matritsasi |

---

## 1. Ruxsat matritsasi

`app/modules/rbac/permissions.py` — yagona haqiqat manbai.

Amallar: `view` | `create` | `edit` | `delete` | `approve`

| Modul | administrator | agent | courier | accountant | store |
|---|---|---|---|---|---|
| `catalog` | view, create, edit, delete | view | view | view | view |
| `agent_cabinet` | view | view, edit | — | view | — |
| `attendance` | view | view, create | view, create | view | — |
| `delivery` | view, create, edit | view, create | view, edit | view | view |
| `stock` | view, create, edit, delete | view | view | view | — |
| `finance` | view | view | — | view, create, edit, delete, approve | view |
| `tickets` | view, edit | view, create | view, create | view, edit | view, create |
| `customers` | view, create, edit, delete | view, edit | view | view | view, edit |
| `stats` | view | view | view | view | view |
| `contracts` | view, create, edit, delete | view | — | view, edit | view |
| `promo` | view, create, edit, delete | view | — | view | view |
| `rbac` | view, create, edit, delete | — | — | view | — |

**Eslatmalar:**
- `administrator`: `agent_cabinet` uchun faqat `view` (o'zgartirish yo'q); `tickets` uchun `view + edit` (resolve uchun).
- `accountant`: `finance` uchun to'liq CRUD + `approve`; `rbac` uchun `view` (audit ko'rish).
- `agent` va `courier` uchun qator-darajali scope qo'llaniladi (quyida).

---

## 2. `require_permission` — endpoint himoyalash

`app/modules/rbac/dependency.py` da aniqlangan FastAPI dependency factory.

```python
from app.modules.rbac.dependency import require_permission
from app.modules.rbac.permissions import Module, Action

# Foydalanuvchi faqat autentifikatsiya talab qiluvchi endpoint
@router.get("/catalog")
async def list_products(
    current_user: AppUser = Depends(require_permission(Module.CATALOG, Action.VIEW)),
):
    # current_user — AppUser obyekti (ruxsat tasdiqlangan)
    ...

# Ruxsat va foydalanuvchi alohida kerak bo'lsa
@router.post("/finance/entry")
async def create_entry(
    _: None = Depends(require_permission(Module.FINANCE, Action.CREATE)),
    current_user: AppUser = Depends(get_current_user),
    body: EntryCreate = ...,
):
    ...
```

`require_permission(module, action)` qanday ishlaydi:
1. `get_current_user()` orqali Bearer access tokenni tekshiradi (401 agar yaroqsiz).
2. `get_permissions_for_role(user.role, redis)` — Redis keshdan yoki matritsadan ruxsatlar to'plamini oladi.
3. `module:action` kaliti to'plamda bo'lmasa — HTTP 403 chiqaradi (aniq xabar: modul, amal, rol ko'rsatiladi) va `WARNING` log yozadi.
4. Ruxsat mavjud bo'lsa `AppUser` obyektini qaytaradi.

**403 xabar namunasi:**
```json
{
  "detail": "Ruxsat yo'q: 'finance' modulida 'approve' amali 'agent' roli uchun taqiqlangan."
}
```

---

## 3. `has_permission` — sof sinxron tekshiruv

Redis chaqiriqsiz, matritsadan to'g'ridan-to'g'ri. Middleware yoki tez tekshiruv uchun.

```python
from app.modules.rbac.service import has_permission

allowed = has_permission(current_user, "finance", "approve")
# True yoki False — HTTP chiqarmaydi
```

---

## 4. Qator-darajali scope (`apply_store_scope`, `get_user_store_ids`)

`app/modules/rbac/scope.py` — SQLAlchemy SELECT ga rol asosida WHERE sharti qo'shadi.

### `apply_store_scope(query, user)`

```python
from sqlalchemy import select
from app.modules.rbac.scope import apply_store_scope
from app.models.store import Store

stmt = select(Store)
stmt = apply_store_scope(stmt, current_user)
result = await db.execute(stmt)
stores = result.scalars().all()
```

Har rol qanday ko'radi:

| Rol | Do'konlar ko'rinishi |
|---|---|
| `administrator` | `branch_id` bo'yicha (agar `branch_id=None` — barchasi) |
| `accountant` | `branch_id` bo'yicha (agar `branch_id=None` — barchasi) |
| `agent` | Faqat o'ziga biriktirilgan: `Store.agent_id == user.id` YOKI `AgentStore.agent_id == user.id` — bitta `OR + scalar_subquery` so'rovi |
| `courier` | Barcha do'konlar (faqat manzil ko'rish; delivery scope alohida) |
| `store` | **Vaqtinchalik deny-all** — `Store.id IS NULL` (hech narsa qaytmaydi) |

### `get_user_store_ids(user, db)`

Agent yoki boshqa rol uchun ruxsat etilgan do'kon UUID ro'yxatini qaytaradi. T4/T5 modullari bog'liq filtr uchun ishlatadi.

```python
from app.modules.rbac.scope import get_user_store_ids

store_ids = await get_user_store_ids(current_user, db)
# list[UUID] — bo'sh ro'yxat = hech narsa ruxsat emas
```

### Agent N+1 tuzatish

Ilgari: agent do'konlarini aniqlash uchun 2 ta alohida DB so'rov (`Store.agent_id` + `AgentStore`).
Hozir: bitta `OR + scalar_subquery`:

```sql
SELECT store.id FROM store
WHERE store.agent_id = :user_id
   OR store.id IN (
       SELECT agent_store.store_id FROM agent_store
       WHERE agent_store.agent_id = :user_id
   )
```

### `store` roli — vaqtinchalik deny-all

`Store.user_id` FK hali mavjud emas (`0001_initial.py` da qo'shilmagan). `Store.agent_id == user.id` bog'liqligi semantik jihatdan noto'g'ri — IDOR (Insecure Direct Object Reference) xavfi. Shu sababli `store` roli uchun hozircha barcha qator so'rovlari bo'sh qaytariladi.

**T5 da tuzatiladi:** `Store.user_id UUID FK` qo'shilgach, `store` roli `Store.user_id == user.id` filtri bilan o'z yozuvini ko'radi.

---

## 5. Redis kesh

`app/modules/rbac/service.py` — kesh kaliti: `rbac:perms:{role}`, TTL: 5 daqiqa.

```
Redis GET rbac:perms:agent
  → mavjud: JSON ni parse → set qaytaradi
  → yo'q:   matritsadan yuklaydi → Redis SET (TTL 300s) → set qaytaradi
  → Redis xato (ConnectionError): WARNING log → matritsadan to'g'ridan-to'g'ri (fail-closed)
```

**Fail-closed:** Redis o'chganda ham tizim ishlaydi — matritsadan to'g'ridan-to'g'ri o'qiydi. Autentifikatsiya bloklashdan farqli (u fail-closed = bloklaydi); RBAC kesh fail-closed = matritsaga tushadi.

---

## 6. Endpointlar

### `GET /rbac/my-permissions`

Joriy foydalanuvchining barcha ruxsatlarini qaytaradi. Autentifikatsiya talab.

**So'rov:**
```bash
curl http://localhost:8000/rbac/my-permissions \
  -H "Authorization: Bearer <access_token>"
```

**Javob (200):**
```json
{
  "role": "agent",
  "permissions": [
    "agent_cabinet:edit",
    "agent_cabinet:view",
    "attendance:create",
    "attendance:view",
    "catalog:view",
    "contracts:view",
    "customers:edit",
    "customers:view",
    "delivery:view",
    "finance:view",
    "promo:view",
    "stats:view",
    "stock:view",
    "tickets:create",
    "tickets:view"
  ],
  "total": 15
}
```

### `GET /rbac/check`

Aniq modul:amal ruxsatini tekshiradi. 403 chiqarmaydi — faqat `allowed: true/false` (UI uchun).

**So'rov:**
```bash
curl "http://localhost:8000/rbac/check?module=finance&action=approve" \
  -H "Authorization: Bearer <access_token>"
```

**Javob (200) — ruxsat yo'q holat:**
```json
{
  "module": "finance",
  "action": "approve",
  "allowed": false,
  "role": "agent"
}
```

**Javob (200) — ruxsat bor holat:**
```json
{
  "module": "catalog",
  "action": "view",
  "allowed": true,
  "role": "agent"
}
```

### `GET /auth/me` — T2 kengaytmasi

T2 dan boshlab `/auth/me` javobi `permissions` maydonini o'z ichiga oladi.

**Javob (200):**
```json
{
  "id": "018f1a2b-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
  "phone": "+998901234567",
  "full_name": "Alisher Karimov",
  "role": "agent",
  "branch_id": "018f1a2b-0000-7000-8000-000000000001",
  "locale": "uz",
  "is_active": true,
  "biometric_enrolled": false,
  "permissions": [
    "agent_cabinet:edit",
    "agent_cabinet:view",
    "catalog:view",
    "..."
  ]
}
```

---

## 7. Alembic 0002 — `role` CHECK constraint

`alembic/versions/0002_role_check.py` — `app_user.role` ustuniga `ck_app_user_role_valid` nomli `CHECK` constraint qo'shadi.

Qabul qilinadigan qiymatlar: `administrator` | `agent` | `courier` | `accountant` | `store`

Migratsiya qo'llash:
```bash
cd backend
alembic upgrade head
# yoki:
make migrate
```

Migratsiya downgrade:
```bash
alembic downgrade 0001
```

PostgreSQL ENUM o'rniga `CHECK` tanlangan sabab: yangi rol qo'shish uchun faqat `ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT` — `ALTER TYPE ... ADD VALUE` kabi tranzaksiya-xavfli DDL kerak emas.

---

## 8. 403 logging

Har bir rad etilgan so'rov quyidagi maydonlar bilan `WARNING` darajasida yoziladi:

| Maydon | Qiymat |
|---|---|
| `user_id` | Foydalanuvchi UUID (string) |
| `role` | Foydalanuvchi roli |
| `perm_module` | So'ralgan modul (`module` LogRecord da band bo'lgani uchun `perm_module`) |
| `action` | So'ralgan amal |

403 hodisalarni monitoring tizimida `perm_module` maydoni bo'yicha filtrlash mumkin.

---

## 9. Ma'lum cheklovlar

| Cheklov | Rejalashtirilgan sprint |
|---|---|
| `store` roli scope deny-all — `Store.user_id` FK yo'q (IDOR oldini olish) | **T5** |
| `role_permission` jadvali (DB da boshqariluvchi ruxsatlar, admin UI) — hozir Python matritsa | **Keyingi faza (B2+)** |
| Delivery, attendance va boshqa modullar uchun alohida qator-darajali scope | **T4, T5** |
