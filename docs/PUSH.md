# Push bildirishnomalar (T19) — Texnik qo'llanma

| | |
|---|---|
| **Versiya** | 0.15.0 |
| **Modul** | `app/modules/push/` |
| **Model** | `app/models/push.py` — `PushLog` |
| **Migratsiya** | `alembic/versions/0013_push_log.py` |
| **Worker** | `app/modules/push/worker.py` — arq |
| **Gate** | PASS (578/578 test) |

---

## 1. Arxitektura — sync'dan izolyatsiya

Push consumer **outbox'dan mustaqil** ishlaydi:

```
outbox_event jadvali
      │
      ├─► GET /sync/pull  (seq kursori, published_at)  ← sync consumer
      │
      └─► process_pending_pushes()  (push_log dedupe)  ← push consumer
```

- Push consumer `outbox.published_at` ga **tegmaydi** — bu field faqat sync uchun.
- Push consumer o'z holatini `push_log` jadvalida saqlaydi.
- `outbox.seq` kursori push bilan **to'qnashmaydi**.

---

## 2. `process_pending_pushes` oqimi

```python
count = await process_pending_pushes(db, provider, limit=100)
await db.commit()
```

### PASS 1 — Yangi hodisalar (NOT EXISTS filtr)

```sql
SELECT outbox_event.*
FROM outbox_event
WHERE outbox_event.event_type IN ('order.status_updated', 'delivery.created', 'delivery.status_updated')
  AND NOT EXISTS (
    SELECT 1 FROM push_log
    WHERE push_log.outbox_event_id = outbox_event.id
  )
ORDER BY outbox_event.seq
LIMIT 100;
```

Har run faqat `push_log` da hech qanday yozuvi yo'q hodisalar olinadi.
Bir hodisa qayta ishlangach `push_log` yozuvi paydo bo'ladi — keyingi runda PASS 1 dan tushib qoladi.
Bu **stall yo'qligini kafolatlaydi**: 100+ hodisa bo'lsa ham har run oldinga suriladi.

### PASS 2 — Retry (alohida pass)

PASS 1 dan **oldin** yig'iladi (shunday qilib shu runda yangi failed yozuvlar aralashmaydi):

```sql
SELECT push_log.*, outbox_event.*
FROM push_log
JOIN outbox_event ON push_log.outbox_event_id = outbox_event.id
WHERE push_log.status = 'failed'
  AND push_log.attempts < 3  -- PUSH_MAX_RETRIES
ORDER BY push_log.attempts, outbox_event.seq
LIMIT 100;
```

---

## 3. Maqsad foydalanuvchilarni aniqlash

| Hodisa | Push yuboriladi |
|---|---|
| `order.status_updated` | `store.user_id` (do'kon egasi) + `order.agent_id` (agent) |
| `delivery.created` | `delivery.courier_id` (kuryer) + `order → store.user_id` (do'kon) |
| `delivery.status_updated` | `delivery.courier_id` (kuryer) + `order → store.user_id` (do'kon) |

Bir foydalanuvchi ham do'kon egasi, ham agent bo'lsa — `set(targets)` dedupe qiladi.

---

## 4. Idempotentlik

```sql
UNIQUE (outbox_event_id, user_id)  -- uq_push_log_event_user
```

Bir hodisa + bir foydalanuvchi = bitta `push_log` yozuvi.
Parallel worker ikki marta bir xil insert qilsa — `IntegrityError` SAVEPOINT orqali ushlanadi:

```python
async with db.begin_nested():   # SAVEPOINT
    await db.flush()
# IntegrityError → faqat shu savepoint rollback; sessiya tirik
```

---

## 5. Retry mexanizmi

- `attempts` ustuni har urinishda +1.
- `PUSH_MAX_RETRIES = 3` (config dan, default 3).
- 3 dan keyin: `status=failed`, `last_error` to'ldiriladi. Keyingi runlarda PASS 2 ga tushmaydi.
- Backoff: arq worker davriy ishlaganda (`PUSH_POLL_INTERVAL = 30` soniya) amalga oshadi — `next_retry_at` ustuni yo'q, kechikish worker intervali orqali.

---

## 6. Device token endpoint

### `PATCH /push/device-token`

Foydalanuvchi o'z qurilmasining FCM yoki APNs tokenini ro'yxatdan o'tkazadi.

**So'rov:**
```http
PATCH /push/device-token
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "device_id": "fcm-registration-token-here",
  "channel": "fcm"
}
```

**Javob (200):**
```json
{
  "user_id": "0191f3a4-...",
  "device_id": "fcm-registration-token-here",
  "channel": "fcm",
  "message": "Device token yangilandi"
}
```

**Token o'chirish** (`device_id: null`):
```json
{
  "device_id": null,
  "channel": "fcm"
}
```
Javob: `"message": "Device token o'chirildi"` — push bildirishnomalar to'xtatiladi.

**IDOR himoyasi:** Faqat `current_user` (JWT dan) o'zining `device_id` ini o'zgartiradi.
Boshqa foydalanuvchi `device_id` ini o'zgartirish imkonsiz — endpoint boshqa `user_id` qabul qilmaydi.

**RBAC:** Barcha autentifikatsiyalangan rollar (`administrator`, `agent`, `courier`, `accountant`, `store`).

---

## 7. PushProvider abstraktsiyasi

```python
class PushProvider(ABC):
    def send(self, device_id: str, channel: str, title: str, body: str) -> bool:
        ...
```

| Klass | Maqsad |
|---|---|
| `FcmProvider` | Production skelet — FCM v1 API (httpx TODO) |
| `ApnsProvider` | Production skelet — APNs HTTP/2 + ES256 JWT (httpx TODO) |
| `FakePushProvider` | Testlar uchun — tarmoq yo'q, `sent` ro'yxati |

**Factory:**
```python
provider = get_push_provider()
# APP_ENV=development va FCM key yo'q → FakePushProvider
# Production → FcmProvider
```

**FCM production uchun env:**
```
FCM_SERVER_KEY=...      # legacy server key
FCM_CREDENTIALS=...     # service account JSON (tavsiya etiladi)
```

**APNs production uchun env:**
```
APNS_KEY_ID=...
APNS_TEAM_ID=...
APNS_BUNDLE_ID=...
APNS_PRIVATE_KEY_PEM=...
```

---

## 8. i18n push matnlari

Push matnlari foydalanuvchi `locale` (`uz` yoki `ru`) asosida tanlanadi.
`AppUser.locale` NULL bo'lsa `uz` fallback.

| Kalit | uz sarlavha | ru sarlavha |
|---|---|---|
| `push.order_status_updated` | Buyurtma holati | Статус заказа |
| `push.delivery_created` | Yetkazish tayinlandi | Назначена доставка |
| `push.delivery_status_updated` | Yetkazish holati | Статус доставки |
| `push.general` | RETAIL | RETAIL |

**Foydalanish:**
```python
from app.modules.push.messages import push_text

title, body = push_text(
    "push.order_status_updated",
    locale="uz",
    order_id_short="0191f3a4",
    status="confirmed",
)
# title = "Buyurtma holati"
# body  = "Buyurtma #0191f3a4: holat 'confirmed' ga o'zgardi"
```

---

## 9. arq worker (production)

**Ishga tushirish:**
```bash
cd backend
arq app.modules.push.worker.WorkerSettings
```

Worker Redis broker orqali ishga tushiriladi. Har `PUSH_POLL_INTERVAL = 30` soniyada `push_worker_task()` chaqiriladi.

**Lifecycle:**
- `on_startup`: DB sessiya factory + `get_push_provider()` yaratiladi
- `push_worker_task(ctx)`: `process_pending_pushes()` chaqiradi, natijani log ga yozadi
- `on_shutdown`: engine dispose

**Env:**
```
REDIS_URL=redis://:password@localhost:6379/0
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/retail
APP_ENV=production
FCM_SERVER_KEY=...  # yoki FCM_CREDENTIALS
```

---

## 10. push_log jadvali (migratsiya 0013)

```sql
CREATE TABLE push_log (
    id              UUID PRIMARY KEY,
    outbox_event_id UUID NOT NULL REFERENCES outbox_event(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    device_id       VARCHAR(512),
    channel         VARCHAR(10) NOT NULL DEFAULT 'fcm',
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at         TIMESTAMPTZ,
    CONSTRAINT uq_push_log_event_user UNIQUE (outbox_event_id, user_id)
);

CREATE INDEX ix_push_log_outbox_event_id ON push_log (outbox_event_id);
CREATE INDEX ix_push_log_user_id         ON push_log (user_id);
CREATE INDEX ix_push_log_status          ON push_log (status);
```

**Migratsiya runbook:**
```bash
cd backend
alembic upgrade 0013
# yoki:
alembic upgrade head
```

**Downgrade guard:** `push_log` da qatorlar bo'lsa downgrade `RuntimeError` bilan bloklanadi.

---

## 11. HTTP yetkazib berish (provider) — v0.28.0

`app/modules/push/provider.py` — production push yetkazish implementatsiyasi (774 test, gate PASS).

### Provider arxitekturasi

```
PushProvider (ABC)
  ├── FcmProvider      — FCM HTTP v1 (OAuth2) yoki legacy server-key
  ├── ApnsProvider     — APNs JWT ES256, HTTP/2
  └── FakePushProvider — testlar uchun (tarmoq yo'q)

get_push_provider()   → FcmProvider | FakePushProvider  (FCM, default kanal)
get_apns_provider()   → ApnsProvider                    (iOS qurilmalar uchun)
```

Platform routing `service.py` da amalga oshiriladi: `device_id` `apns:` prefiksi bilan boshlanса → `ApnsProvider`, aks holda → `FcmProvider`.

### FCM HTTP v1 (tavsiya)

```
Endpoint: https://fcm.googleapis.com/v1/projects/{project_id}/messages:send
Auth:      OAuth2 Bearer token (service-account JSON asosida)
```

Oauth2 token olish tartibi:
1. `google-auth` paketi mavjud bo'lsa — `service_account.Credentials` orqali.
2. Yo'q bo'lsa — `PyJWT + httpx` orqali RS256 JWT imzolash + `https://oauth2.googleapis.com/token` ga POST.

```python
# Konfiguratsiya (.env.prod)
FCM_PROJECT_ID=your-firebase-project-id
FCM_CREDENTIALS_FILE=/run/secrets/fcm-service-account.json
# yoki
FCM_CREDENTIALS=<base64-encoded-service-account-json>
```

**FCM legacy (eskirgan):** `FCM_SERVER_KEY` bilan ishlaydi — backward-compat uchun saqlangan. Google 2024-yildan FCM legacy API ni o'chirishni e'lon qildi. Yangi va mavjud loyihalar uchun FCM HTTP v1 + service-account ishlatilsin.

```python
# Legacy (faqat eski deployment uchun)
FCM_SERVER_KEY=AAAA...legacy_key
```

### APNs token-based JWT ES256, HTTP/2

```
Prod endpoint:    https://api.push.apple.com/3/device/{token}
Sandbox endpoint: https://api.sandbox.push.apple.com/3/device/{token}
Auth:             Authorization: bearer <ES256-JWT>
Protocol:         HTTP/2 (majburiy — HTTP/1.1 APNs tomonidan rad etiladi)
```

JWT kesh: 45 daqiqa muddatli (Apple talabi: 20–60 daqiqa), 10 daqiqa zaxira bilan qayta yaratiladi.

```python
# Konfiguratsiya (.env.prod)
APNS_KEY_FILE=/run/secrets/AuthKey_XXXXXXX.p8
APNS_KEY_ID=XXXXXXXXXX
APNS_TEAM_ID=YYYYYYYYYY
APNS_BUNDLE_ID=com.example.retail
APNS_USE_SANDBOX=false      # production; staging uchun true
```

**H2 bog'liqligi:** `httpx[http2]` (`h2` paketi) `pyproject.toml` da talab qilinadi. `pip install "httpx[http2]"` yoki `pip install -e ".[dev]"`.

### Token invalidatsiya oqimi

```
send() → PushResult(invalid_token=True)
          ↓
service.py: app_user.device_id = NULL   (DB UPDATE)
            push_log yazuvi saqlandi     (append-only audit)
```

| Signal | Provider | Sabab |
|---|---|---|
| HTTP 404 + `UNREGISTERED`/`NOT_FOUND` | FCM v1 | Token deregistered |
| JSON `results[0].error = NotRegistered` | FCM legacy | Token deregistered |
| HTTP 410 | APNs | Token yangilangan/o'chirilgan |
| JSON `reason = BadDeviceToken` | APNs | Token formati noto'g'ri |
| JSON `reason = Unregistered` | APNs | Token deregistered |
| JSON `reason = DeviceTokenNotForTopic` | APNs | Bundle ID mos kelmaydi |

### No-op xulqi

Kredensial to'liq ko'rsatilmagan bo'lsa:
- `FcmProvider`: `logger.warning` + `PushResult(ok=False, error="fcm_not_configured")` — istisno tashlanmaydi.
- `ApnsProvider`: `logger.warning` + `PushResult(ok=False, error="apns_not_configured")` — istisno tashlanmaydi.
- Development muhitida FCM config yo'q → `FakePushProvider` ishlatiladi (ilova buzilmaydi).

### PII xavfsizligi

- Device token log'ga `token[:8]***` shaklida maskalangan (masalan: `a1b2c3d4***`).
- `title` va `body` real provider log'iga yozilmaydi — faqat `DEBUG` darajasida token maskalangan yozuv.
- Service-account JSON (`FCM_CREDENTIALS_FILE`) faqat fayl tizimida, env satr orqali ham base64 formatlangan holda berilishi mumkin.

### Konfiguratsiya jadvali

| O'zgaruvchi | Maqsad | Talab |
|---|---|---|
| `FCM_PROJECT_ID` | Firebase project ID (v1) | v1 uchun majburiy |
| `FCM_CREDENTIALS_FILE` | Service-account JSON fayl yo'li (v1) | v1 uchun birontasi |
| `FCM_CREDENTIALS` | Service-account JSON base64 yoki raw (v1) | v1 uchun birontasi |
| `FCM_SERVER_KEY` | Legacy FCM server key (eskirgan) | Faqat eski deployment |
| `APNS_KEY_FILE` | `.p8` kalit fayli yo'li | APNs uchun majburiy |
| `APNS_KEY_ID` | 10 belgili Apple Key ID | APNs uchun majburiy |
| `APNS_TEAM_ID` | 10 belgili Apple Team ID | APNs uchun majburiy |
| `APNS_BUNDLE_ID` | iOS ilova Bundle ID | APNs uchun majburiy |
| `APNS_USE_SANDBOX` | `true` = sandbox, `false` = production | Ixtiyoriy (standart `false`) |

---

## 12. Ma'lum cheklovlar

| Cheklov | Rejalashtirilgan |
|---|---|
| Exponential backoff `next_retry_at` ustuni yo'q — backoff worker intervali orqali | Kelajak |
| Postgres savepoint integratsiya testi yozilmagan (parallel worker race holati) | Hardening |
| Kanal aniqlash `device_id` prefix bo'yicha emas — hozir `apns:` prefix va default `fcm` | Kelajak |
