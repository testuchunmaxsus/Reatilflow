# RETAIL — Railway'ga Deploy Qo'llanmasi

Bu hujjat RETAIL platformasini [Railway](https://railway.app) (PaaS) ga deploy qilish
ketma-ketligini tushuntiradi. Railway GitHub repodan avtomatik build + deploy qiladi.

> **Repo:** `https://github.com/testuchunmaxsus/Reatilflow`
> **Versiya:** v0.33.0 (production-ready)

---

## 1. Arxitektura (Railway servislari)

Bitta Railway **project** ichida quyidagi servislar bo'ladi:

| Servis | Manba | Vazifa | Majburiymi |
|---|---|---|---|
| **backend** | `backend/` (Dockerfile) | FastAPI API | ✅ Ha |
| **web** | `web/` (Nixpacks) | React admin SPA (statik) | ✅ Ha |
| **Postgres** | Railway plugin | Asosiy OLTP DB | ✅ Ha |
| **Redis** | Railway plugin | Sessiya/cache/queue | ✅ Ha |
| **TimescaleDB** | Docker image `timescale/timescaledb-ha:pg16` | GPS time-series | ⬜ GPS uchun |
| **MinIO** | Docker image `minio/minio` (yoki tashqi S3/R2) | Fayl/rasm saqlash | ⬜ Fayl yuklash uchun |

> Backend faqat **Postgres + Redis** bilan ham ishga tushadi. TimescaleDB va MinIO
> keyin qo'shilishi mumkin — GPS trekking va fayl yuklash o'shanda yoqiladi.

---

## 2. Tayyorgarlik — sirlarni generatsiya qilish

Deploy'dan oldin 3 ta kalit generatsiya qiling (lokal terminalda):

```bash
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 32   # PII_ENCRYPTION_KEY
openssl rand -hex 32   # BLIND_INDEX_KEY
```

> ⚠️ Bu kalitlarni saqlang. `PII_ENCRYPTION_KEY` yo'qolsa shifrlangan PII (telefon
> raqamlar) ochib bo'lmaydi. Dev-default kalitlar `app_env=production` da **rad etiladi**.

---

## 3. Backend servisi

1. Railway'da yangi **Project** yarating → **Deploy from GitHub repo** → `Reatilflow` ni tanlang.
2. Birinchi servis sozlamalarida **Root Directory** = `backend` qiling.
   - Railway `backend/railway.json` ni o'qiydi: Dockerfile bilan build, start = `alembic upgrade head && uvicorn ... --port $PORT`, healthcheck = `/health`.
3. **Postgres** plugin qo'shing: project → **+ New** → **Database** → **PostgreSQL**.
4. **Redis** plugin qo'shing: **+ New** → **Database** → **Redis**.
5. Backend servisining **Variables** bo'limiga quyidagilarni qo'shing:

| O'zgaruvchi | Qiymat |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (reference) |
| `JWT_SECRET_KEY` | (generatsiya qilingan hex) |
| `PII_ENCRYPTION_KEY` | (generatsiya qilingan hex) |
| `BLIND_INDEX_KEY` | (generatsiya qilingan hex) |
| `CORS_ORIGINS` | web servis URL'i (5-bo'limdan keyin, masalan `https://reatilflow-web.up.railway.app`) |
| `LOG_LEVEL` | `INFO` |

> **Sxema avtomatik:** Railway `DATABASE_URL` ni `postgresql://...` ko'rinishida beradi.
> Ilova `config.py` da uni avtomatik `postgresql+asyncpg://` ga aylantiradi
> (`normalize_async_pg_urls`) — qo'lda o'zgartirish SHART EMAS.

6. Deploy avtomatik boshlanadi. Start buyrug'i `alembic upgrade head` ni ishga tushiradi —
   migratsiyalar avtomatik qo'llanadi. `/health` 200 qaytarsa servis tayyor.
7. Backend uchun **public domain** generatsiya qiling (Settings → Networking → Generate Domain).

---

## 4. Demo ma'lumot (seed)

Backend birinchi deploy bo'lgach, demo ma'lumotni yuklang (admin + katalog + do'kon):

- Railway backend servisida **one-off command** (yoki lokal `railway run`):
  ```bash
  python -m scripts.seed
  ```
- Yoki `SEED_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` env'larini oldindan o'rnating
  (aks holda dev-default parol + WARNING ishlatiladi).

> Skript idempotent — qayta ishga tushirsa dublikat yaratmaydi.

---

## 5. Web servisi

1. Project'da **+ New** → **GitHub Repo** → `Reatilflow` (yana) → **Root Directory** = `web`.
   - Railway `web/railway.json` ni o'qiydi: Nixpacks build (`npm ci && npm run build`),
     start = `npm run start` (statik `serve -s dist -l $PORT`).
2. Web servisining **Variables**:

| O'zgaruvchi | Qiymat |
|---|---|
| `VITE_API_BASE_URL` | backend public URL (3.7-qadam), masalan `https://reatilflow-backend.up.railway.app` |

   > ⚠️ `VITE_API_BASE_URL` **build vaqtida** o'qiladi (Vite uni bundle'ga yozadi).
   > O'zgartirsangiz — qayta deploy (rebuild) kerak.
3. Web uchun **public domain** generatsiya qiling.
4. Backend `CORS_ORIGINS` ga shu web URL'ini qo'shing (3.5-jadval) va backend'ni qayta deploy qiling.

---

## 6. (Ixtiyoriy) TimescaleDB — GPS trekking

GPS modulini yoqish uchun alohida TimescaleDB servisi kerak (Railway managed Postgres'da
timescaledb extension yo'q).

1. **+ New** → **Docker Image** → `timescale/timescaledb-ha:pg16`.
   - `POSTGRES_PASSWORD`, `POSTGRES_DB=retail_gps`, `POSTGRES_USER` env'larini o'rnating.
2. Backend Variables'ga qo'shing:
   - `TIMESCALE_URL` = TimescaleDB servisining ulanish URL'i (`${{TimescaleDB.DATABASE_URL}}` yoki qo'lda).
3. TimescaleDB migratsiyasini bir marta ishga tushiring (one-off command yoki `railway run`):
   ```bash
   make migrate-timescale
   # yoki: cd backend && TIMESCALE_URL=... alembic -c alembic_timescale.ini upgrade head
   ```
   Bu `gps_point` hypertable + retention'ni yaratadi.

> TimescaleDB sozlanmaguncha backend ishlайveradi; faqat `/gps/*` endpointlar ishlamaydi.

---

## 7. (Ixtiyoriy) MinIO — fayl/rasm saqlash

Mahsulot rasmi, shartnoma fayli, yetkazish proof_photo uchun S3-mos saqlash kerak.

**Variant A — Railway'da MinIO:**
1. **+ New** → **Docker Image** → `minio/minio`, start command: `server /data --console-address ":9001"`.
2. **Volume** qo'shing (`/data` ga mount) — ma'lumot saqlanishi uchun.
3. `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` env o'rnating.
4. Backend Variables: `MINIO_ENDPOINT_URL`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`.
5. Bucket'larni yarating: `bash infra/minio/create-buckets.sh` (yoki MinIO konsolida qo'lda).

**Variant B — tashqi S3/Cloudflare R2:** `MINIO_ENDPOINT_URL` ni R2/S3 endpoint'iga,
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` ni access/secret key'ga o'rnating.

> MinIO sozlanmaguncha login/katalog/buyurtma (rasmsiz) ishlайveradi; fayl yuklash ishlamaydi.

---

## 8. To'liq env o'zgaruvchilar ma'lumotnomasi

### Majburiy (backend)
- `APP_ENV=production`
- `DATABASE_URL` — `${{Postgres.DATABASE_URL}}`
- `REDIS_URL` — `${{Redis.REDIS_URL}}`
- `JWT_SECRET_KEY`, `PII_ENCRYPTION_KEY`, `BLIND_INDEX_KEY` — `openssl rand -hex 32`
- `CORS_ORIGINS` — web public URL

### Ixtiyoriy (backend)
- `TIMESCALE_URL` — GPS (TimescaleDB servisi)
- `MINIO_ENDPOINT_URL`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` — fayl saqlash
- `FCM_PROJECT_ID` + `FCM_CREDENTIALS` (yoki `FCM_CREDENTIALS_FILE`) — push (Android)
- `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, `APNS_PRIVATE_KEY_PEM` — push (iOS)
- `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT` — kuzatuvchanlik (no-op agar bo'sh)
- `LOG_LEVEL` (default `INFO`)

### Web
- `VITE_API_BASE_URL` — backend public URL (build-time)

---

## 9. Migratsiyalar

- **OLTP (asosiy):** backend start buyrug'ida `alembic upgrade head` avtomatik ishlaydi
  (har deploy'da, idempotent).
- **TimescaleDB (GPS):** alohida `alembic_timescale.ini` — `make migrate-timescale` bilan
  qo'lda (6-bo'lim). OLTP zanjiridan mustaqil (`alembic_version_timescale` jadvali).

---

## 10. Tekshirish

1. `https://<backend-domain>/health` → `{"status":"ok"}` (liveness).
2. `https://<backend-domain>/readiness` → Postgres/Redis/MinIO holati (MinIO yo'q bo'lsa `degraded`).
3. `https://<backend-domain>/docs` — `app_env=staging` da ochiq (production'da yopiq).
4. Web URL'ini oching → login sahifasi. Seed admin bilan kiring.

---

## 11. Eslatmalar va muammolar (gotchas)

- **DATABASE_URL sxemasi:** avtomatik `+asyncpg` ga aylanadi (`config.py`). Railway'ning
  **internal** reference o'zgaruvchisini (`${{Postgres.DATABASE_URL}}`) ishlating — u
  `*.railway.internal` host bilan, SSL kerak emas. Public proxy URL (`*.rlwy.net`) SSL talab qiladi.
- **Sirlar:** `app_env=production` da dev-default `PII_ENCRYPTION_KEY`/`BLIND_INDEX_KEY`/
  `JWT_SECRET_KEY` **rad etiladi** (ilova ishga tushmaydi). Albatta yangi kalit bering.
- **Healthcheck `/health`** (DB tekshirmaydi) — shuning uchun MinIO/Timescale sozlanmasa ham
  deploy muvaffaqiyatli bo'ladi. `/readiness` esa to'liq infra holatini ko'rsatadi.
- **`$PORT`:** Railway portni `$PORT` orqali beradi; start buyruqlari uni ishlatadi
  (backend uvicorn, web `serve`). Qo'lda port qo'ymang.
- **Mobil (Flutter):** Railway'ga deploy QILINMAYDI — u app store / APK orqali tarqatiladi.
  Mobil ilova `VITE_API_BASE_URL` o'rniga o'z `apiClient` base URL'ini backend public domeniga
  sozlashi kerak (`mobile/lib/data/remote/`).
