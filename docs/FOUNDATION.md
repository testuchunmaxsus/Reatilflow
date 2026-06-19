# RETAIL — Poydevor texnik xulosasi (v0.1.0)

| | |
|---|---|
| **Versiya** | 0.33.0 |
| **Sana** | 2026-06-19 |
| **Holati** | Yakunlandi — gate PASS |
| **Qamrov** | P1–P5 (Pre sprintlar) + B1 backend (T1–T6) + B2 (T9–T13) + B3 backend (T16–T19) + B4 backend (T22✅ T23✅ T24✅ T25✅) + **Frontend: T7✅ T8✅ Buyurtma/Statistika✅ Foydalanuvchilar✅ Shartnoma/Murojaat/Aksiya✅** + **Mobil: T14✅ T21✅ T20✅** + **T27: Observability✅** + **CI/CD + Deploy✅** + **FCM/APNs push delivery✅** + **Stats SQL agregatsiya✅** + **Append-only DB invariant✅** + **Production-readiness: GPS ish-soati filtri, seed, code-split, native paketlar✅** |

> **BACKEND B1-B4 TO'LIQ YAKUNLANDI (2026-06-18).** B1✅ B2✅ B3✅ B4✅. Jami: 811 test (v0.33.0), 18 migratsiya, ~19 modul. Har vazifa orkestrator gate PASS bilan tasdiqlangan.
>
> **T27 OBSERVABILITY YAKUNLANDI (v0.26.0, 2026-06-18).** Strukturalangan JSON logging (correlation_id, PII maskalash), CorrelationIdMiddleware (X-Request-ID), Prometheus /metrics (http + biznes counterlar), OpenTelemetry tracing (no-op agar endpoint yo'q), Sentry (no-op agar DSN yo'q, send_default_pii=False). Production hardening boshlandi.
>
> **CI/CD + DEPLOY YAKUNLANDI (v0.27.0, 2026-06-18).** GitHub Actions 3 workflow (backend: lint→test→SAST→Trivy→docker-push ghcr.io; web: tsc/eslint/vitest/build; mobile: pub get/build_runner/analyze/test); `docker-compose.prod.yml` (api/gps-ingest/worker + nginx TLS + postgres primary+replica + timescaledb + redis + minio + prometheus/grafana/loki/promtail); `backend/Dockerfile` multi-stage venv, non-root, healthcheck; `infra/` konfiguratsiya fayllari; `.env.prod.example`; `docs/DEPLOY.md` runbook; Makefile ci/deploy targetlari. 2 HIGH build xatosi tuzatildi: `pyproject.toml` build-backend + Dockerfile venv/PATH. Production hardening: Observability✅ CI/CD✅.
>
> **FCM/APNs PUSH DELIVERY YAKUNLANDI (v0.28.0, 2026-06-19).** `FcmProvider` (FCM HTTP v1 OAuth2 service-account; legacy server-key backward-compat), `ApnsProvider` (JWT ES256 HTTP/2, 45-daqiqa kesh), `FakePushProvider` (test), factory `get_push_provider`/`get_apns_provider`. Platform routing (`apns:` prefix→APNs), token invalidatsiya (FCM 404 UNREGISTERED / APNs 410/BadDeviceToken → `device_id=NULL`), PII-safe loglar (token maskalangan). 2 bugfix: APNs `http2=True`, `httpx[http2]`. 18 yangi test (jami 774). Production hardening: Observability✅ CI/CD✅ Push delivery✅.
>
> **STATISTIKA SQL AGREGATSIYA YAKUNLANDI (v0.29.0, 2026-06-19).** `sales_stats`/`delivery_stats`/`finance_stats` Python-tomon yig'ishdan DB darajali `func.count`/`func.sum`/`func.coalesce`/`func.avg` + `GROUP BY` ga ko'chirildi. Dialekt-aware sana guruhlash (SQLite `strftime` / PostgreSQL `to_char`), avg yetkazish vaqti (SQLite `julianday` / PG `EXTRACT(EPOCH)`), `NULL→0` `coalesce`. Indekslar `ix_ledger_entry_store_date` (ledger_entry: store_id, entry_date) va `ix_delivery_assigned_at` (delivery: assigned_at) — migratsiya `0017`. 18 yangi test (jami 792). Production hardening: Observability✅ CI/CD✅ Push delivery✅ Stats SQL agg✅.
>
> **FRONTEND T7✅ T8✅ Buyurtma/Statistika✅ Foydalanuvchilar✅ Shartnoma/Murojaat/Aksiya✅ YAKUNLANDI.** T7 — React+TS+Vite+Mantine+TanStack+i18next+Tauri skeleti (14 test). T8 — Katalog + Mijoz bazasi veb UI (36 test). Buyurtma/Statistika veb UI (69 test). Foydalanuvchilar boshqaruvi veb UI (83 test jami). Shartnoma + Murojaat + Aksiya veb UI (117 test jami, build toza). Veb admin panelining 8 moduli tayyor — barcha backend modullari qoplangan.
>
> **MOBIL: T14✅ T21✅ T20✅ YAKUNLANDI (v0.25.0, 2026-06-18).** T14 — Flutter+Drift+dio+Riverpod+go_router skeleti; 7-jadval; SyncService; OrderRepository; secure_storage auth; connectivity banner (29 test). T21 — Agent ekranlari: dashboard, do'konlar, katalog, offline buyurtma, buyurtma ro'yxati, davomat (BiometricService/GpsService), GPS tracking (71 test). T20 — Kuryer ekranlari: dashboard, yetkazishlar ro'yxati/detali, holat mashinasi (VALID_TRANSITIONS, version lock), GPS tracking (45s, faol yetkazishda), proof_photo (dio multipart, 401-refresh), deliveries Drift jadvali + schemaVersion 2 (128 test).
>
> ---
>
> ## BUTUN RETAIL MAHSULOTI FUNKSIONAL YAKUNLANDI
>
> **Backend B1-B4✅ + Veb admin✅ + Mobil (T14/T21/T20)✅**
>
> | Komponent | Vazifalar | Test soni | Holat |
> |---|---|---|---|
> | Backend B1 — Auth/RBAC/i18n/Katalog/Mijoz/User | T1 T2 T3 T4 T5 T6 | 322 | ✅ |
> | Backend B2 — Ombor/Buxgalteriya/Buyurtma/Shablon/Sync | T9 T10 T11 T12 T13 | 452 | ✅ |
> | Backend B3 — Davomat/GPS/Yetkazish/Push | T16 T17 T18 T19 | 578 | ✅ |
> | Backend B4 — Shartnoma/Murojaat/Aksiya/Statistika | T23 T24 T25 T22 | 736 | ✅ |
> | Backend T27 — Observability (production hardening) | T27 | 756 (jami) | ✅ |
| CI/CD + Deploy — GitHub Actions, Dockerfile, infra | — | — | ✅ (v0.27.0) |
| Push delivery — FCM HTTP v1, APNs JWT ES256 HTTP/2 | — | 774 (jami) | ✅ (v0.28.0) |
| Stats SQL agregatsiya + indekslar (production hardening) | — | 792 (jami) | ✅ (v0.29.0) |
> | Veb — SPA poydevori | T7 | 14 | ✅ |
> | Veb — Katalog + Mijoz UI | T8 | 36 | ✅ |
> | Veb — Buyurtma + Statistika UI | — | 69 (jami) | ✅ |
> | Veb — Foydalanuvchilar boshqaruvi UI | — | 83 (jami) | ✅ (v0.31.0) |
> | Veb — Shartnoma/Murojaat/Aksiya UI | — | 117 (jami) | ✅ (v0.32.0) |
> | Mobil — Flutter offline yadro | T14 | 29 | ✅ |
> | Mobil — Agent ekranlari | T21 | 71 | ✅ |
> | Mobil — Kuryer ekranlari | T20 | 128 (jami) | ✅ |
> | Production-readiness: GPS filtri, seed, code-split, native paketlar | — | 811 backend (jami) | ✅ (v0.33.0) |
>
> **Backend jami: 811 test. Mobil jami: 128 test. Veb jami: 117 test.**

---

## 1. Nima qurildi

### Backend skeleti
- FastAPI 0.1.0 ilovasi — `app/main.py`; async `lifespan`, CORS middleware
- `GET /health` — liveness probe (infra tekshirmasdan)
- `GET /readiness` — PostgreSQL + Redis + MinIO sog'ligini tekshiradi; 503 qaytaradi agar birontasi ishlamasa
- `GET /openapi.json` — OpenAPI 3.x sxemasi; production da `/docs`/`/redoc` yopiq
- `app/core/config.py` — Pydantic Settings, `.env` asosida; production/staging da zaif JWT kalitni ilova ishga tushishida rad etadi
- `app/core/db.py` — async SQLAlchemy 2.0 engine; primary + replica placeholder
- `app/core/uuid7.py` — RFC 9562 UUID v7 generator, thread-safe, monoton
- `app/core/security.py` — `mask_pii()` — PII va maxfiy kalitlarni maskalash

### Ma'lumotlar bazasi sxemasi
Alembic revision `0001` — 11 jadval:

| Jadval | Turi | Eslatma |
|---|---|---|
| `app_user` | Asosiy | 5 rol, `biometric_enrolled` flag, soft-delete |
| `store` | Asosiy | Chakana do'kon/mijoz, `credit_limit` |
| `agent_store` | Ko'p-ko'p | Agent ↔ do'kon biriktirish |
| `category` | Asosiy | Ierarxik (`parent_id` o'z-o'ziga FK) |
| `price_segment` | Asosiy | Narx segmenti |
| `product` | Asosiy | `barcode`, `mxik_code`, `sku`; GIN full-text indeks |
| `product_price` | Asosiy | Segment × muddat, `(product_id, segment_id, valid_from)` unique |
| `price_history` | Append-only | Narx o'zgarishi tarixi; UPDATE/DELETE yo'q |
| `product_note` | Faqat qo'shish | Mahsulot izohi va reyting |
| `audit_log` | Append-only | Kim/nima/qachon/oldin-keyin; PII maskalangan |
| `outbox_event` | Append-only | Transactional outbox; `published_at IS NULL` — kutayotgan |

Har jadvalda standart ustunlar: `id` (UUID v7), `version` (BIGINT), `created_at`, `updated_at`, `deleted_at`.
`set_updated_at()` trigger funksiyasi har `UPDATE` da `updated_at` ni avtomatik yangilaydi.

### Infra (lokal dev)
`docker-compose.yml` — to'rtta servis, barchasi `healthcheck` bilan:
- `postgres` — PostgreSQL 16, port 5432
- `timescaledb` — TimescaleDB 2.x, port 5434 (GPS ingest uchun izolyatsiya)
- `redis` — Redis 7, port 6379
- `minio` — MinIO, port 9000 (API) / 9001 (konsol)

### Kontrakt va klient generatsiya
- `GET /openapi.json` — barcha klient generatsiyaning kirish nuqtasi
- `make gen-client` — TypeScript (`web/src/api/`) va Dart (`mobile/lib/api/`) klientlarini generatsiya qiladi

---

## 2. Ishga tushirish

To'liq ko'rsatmalar: [README.md](../README.md)

Qisqa qadamlar:

```bash
# 1. Muhit o'zgaruvchilari
cp .env.example .env
# .env faylida JWT_SECRET_KEY ni o'zgartiring

# 2. Infra servislarini ishga tushirish
make up
# yoki: docker compose up -d

# 3. Backend o'rnatish
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 4. Migratsiya
make migrate
# yoki: cd backend && alembic upgrade head

# 5. Serverni ishga tushirish
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Testlar
make test

# 7. Klient generatsiya (ixtiyoriy)
make gen-client
```

Tekshiruv:
- `http://localhost:8000/health` → `{"status": "ok", "service": "retail-api"}`
- `http://localhost:8000/readiness` → `{"status": "ok", "checks": {"postgres": "ok", "redis": "ok", "minio": "ok"}}`
- `http://localhost:8000/docs` → Swagger UI (faqat `development` va `staging`)

---

## 3. Muhim texnik qarorlar

**UUID v7 (RFC 9562)** — barcha jadvallar uchun birlamchi kalit.
Vaqt-tartibli bo'lgani uchun B-tree indekslarda insert samaradorligi yuqori; klient offline holatda ham ID generatsiya qila oladi (server bilan to'qnashuvsiz).

**Append-only moliyaviy jadvallar** — `price_history`, `audit_log`, `outbox_event`.
Keyingi sprintlarda `stock_movement` va `ledger_entry` ham shu tamoyil bilan qo'shiladi.
UPDATE/DELETE yo'q — moliyaviy aniqlik uchun; balans/qoldiq hodisalardan qayta hisoblanadi.

**`version` (BIGINT, optimistik lock)** — har jadvalda.
Offline klientlar LWW (Last-Write-Wins) konflikt yechimi uchun `version` + `updated_at` kursori ishlatadi.
Replikatsiya kechikishidan qochish uchun moliyaviy o'qish faqat primary DB dan.

**Primary/replica arxitekturasi** — `database_url` (primary, yozish + moliyaviy o'qish) va `database_replica_url` (o'qish replikasi, statistika/katalog). Replica URL hozir primary ga fallback qiladi; T1 dan keyin ajratiladi.

**Transactional outbox** — `outbox_event` jadvali.
Har mutatsiya biznes yozuvi + outbox yozuvi bitta tranzaksiyada. Background worker `published_at IS NULL` yozuvlarni oladi va tashqi tizimlar / mobil sync uchun tarqatadi.

**`mask_pii()`** — audit log yozuvchilari `before_json`/`after_json` ni shu funksiyadan o'tkazib yozadi. `inn`, `inps`, `phone`, `password_hash`, `token`, `owner_name`, `secret` va boshqa maxfiy kalitlar `"***"` ga almashtiriladi.

---

## 4. Keyingi sprint — B1 vazifalari (T1–T8)

| ID | Vazifa | Bog'liqlik |
|---|---|---|
| **T1** | Auth yadrosi — JWT (access 15min) + refresh (30kun, rotatsiyali) + Redis denylist | P3, P5 |
| **T2** | RBAC — 5 rol × 11 modul matritsasi, `has_permission` dependency, qator-himoya, Redis kesh | T1 |
| **T3** | i18n backend — `message_key`, ikki tilli ustunlar (`name_uz`/`name_ru`), `Accept-Language` | T1 |
| **T4** | Katalog CRUD API — mahsulot/kategoriya/segment/narx, MinIO rasm, narx tarixi | T2, T3, P3 |
| **T5** | Mijoz bazasi CRUD API — store + agent biriktirish, `inn`/`inps` pgcrypto shifrlash | T2, T3, P3 |
| **T6** | Foydalanuvchi boshqaruvi API + biometrik flag | T2, T4, T5 |
| **T7** | Veb SPA + Tauri skeleti (React + TypeScript + TanStack + i18next) | P1, P5 |
| **T8** | Katalog + Mijoz bazasi veb UI — ro'yxat/forma, RBAC-aware, uz/ru | T4, T5, T7 |

**T1 (Auth) — ✅ Yakunlandi (v0.2.0, gate PASS, 44 test).**
**T2 (RBAC) — ✅ Yakunlandi (v0.3.0, gate PASS, 131 test).**
**T3 (i18n) — ✅ Yakunlandi (v0.4.0, gate PASS, 186 test).**
**T4 (Katalog CRUD) — ✅ Yakunlandi (v0.5.0, gate PASS, 229 test).**
**T5 (Mijoz bazasi) — ✅ Yakunlandi (v0.6.0, gate PASS, 278 test).**
**T6 (Foydalanuvchi boshqaruvi) — ✅ Yakunlandi (v0.7.0, gate PASS, 322 test).**
**T7 (Veb SPA poydevori) — ✅ Yakunlandi (v0.20.0, gate PASS, 14 test).**
**T8 (Katalog + Mijoz veb UI) — ✅ Yakunlandi (v0.21.0, gate PASS, 36 test).**
**Buyurtma/Statistika veb UI — ✅ Yakunlandi (v0.22.0, gate PASS, 69 test).**

**Backend B1 (Poydevor) — ✅ YAKUNLANDI.** P1–P5, T1–T6 barcha backend vazifalari gate PASS.
**Frontend T7✅ T8✅ Buyurtma/Statistika✅ Foydalanuvchilar✅ Shartnoma/Murojaat/Aksiya✅ — YAKUNLANDI.** Veb SPA poydevori + Katalog/Mijoz/Buyurtma/Statistika/Foydalanuvchilar/Shartnoma/Murojaat/Aksiya UI (117 test). Veb endi barcha 8 backend modulini qoplaydi.

**T9 (Ombor) — ✅ Yakunlandi (v0.8.0, gate PASS, 363 test).**
**T10 (Buxgalteriya) — ✅ Yakunlandi (v0.8.0, gate PASS, 363 test).**
**T11 (Buyurtma yadrosi) — ✅ Yakunlandi (v0.9.0, gate PASS, 405 test).**
**T12 (Buyurtma shabloni) — ✅ Yakunlandi (v0.10.0, gate PASS, 428 test).**
**T13 (Outbox Sync API) — ✅ Yakunlandi (v0.11.0, gate PASS, 452 test).**

**T14 (Flutter offline-first yadro) — ✅ Yakunlandi (v0.23.0, gate PASS, 29 test).** Flutter+Drift+dio+Riverpod+go_router skeleti; 7-jadval; SyncService; OrderRepository; secure_storage auth; connectivity banner.

**T21 (Agent Flutter ilovasi) — ✅ Yakunlandi (v0.24.0, gate PASS, 71 test).** Agent ekranlari: dashboard, do'konlar ro'yxati/detali (lokal Drift, agent-scope), katalog (offline qidiruv), offline buyurtma yaratish (T11 narx himoyasi), buyurtma ro'yxati (sync holati), davomat (BiometricService/GpsService abstraktsiya, Face ID), GPS tracking (ish vaqtida, ADR §3.7). BottomNavigationBar navigatsiya.

**T20 (Kuryer Flutter ilovasi) — ✅ Yakunlandi (v0.25.0, gate PASS, 128 test).** Kuryer ekranlari: dashboard (faol/yetkazilgan soni), yetkazishlar ro'yxati/detali (lokal Drift, holat badge), holat mashinasi UI (VALID_TRANSITIONS server-avtoritar, version lock, outbox `delivery.status_update`), GPS tracking (45s, faqat `started`/`delivering`; `delivery_id` bilan, ADR §3.7), proof_photo (dio multipart, AuthInterceptor 401-refresh, camera stub), `deliveries` Drift jadvali + schemaVersion 2 migratsiya. **Mobil T14+T21+T20 yakunlandi.**

**Backend B2 — ✅ YAKUNLANDI.** T9✅ T10✅ T11✅ T12✅ T13✅ barcha vazifalari gate PASS.

**T16 (Davomat/Attendance) — ✅ Yakunlandi (v0.12.0, gate PASS, 483 test).**
**T17 (GPS Ingest servis) — ✅ Yakunlandi (v0.13.0, gate PASS, 513 test).**
**T18 (Yetkazish/Delivery) — ✅ Yakunlandi (v0.14.0, gate PASS, 554 test).**
**T19 (Push bildirishnomalar) — ✅ Yakunlandi (v0.15.0, gate PASS, 578 test). FCM/APNs HTTP implementatsiyasi v0.28.0 da to'liq yakunlandi (774 test).**

**Backend B3 — ✅ YAKUNLANDI.** T16✅ T17✅ T18✅ T19✅ barcha backend vazifalari gate PASS. Keyingi: **B4** (Statistika/Shartnoma/Murojaat/Aksiya) yoki **frontend** (T7/T8 React veb, T14/T15 Flutter mobil).

**T23 (Shartnoma/Contracts) — ✅ Yakunlandi (v0.16.0, gate PASS, 622 test).**
**T24 (Murojaat/Tickets) — ✅ Yakunlandi (v0.17.0, gate PASS, 658 test).**
**T25 (Aksiya/Promo) — ✅ Yakunlandi (v0.18.0, gate PASS, 701 test).**
**T22 (Statistika/Stats) — ✅ Yakunlandi (v0.19.0, gate PASS, 736 test).**

**Backend B4 — ✅ YAKUNLANDI.** T22✅ T23✅ T24✅ T25✅ barcha backend vazifalari gate PASS.

**T27 (Observability) — ✅ Yakunlandi (v0.26.0, gate PASS, 756 test).** Strukturalangan JSON logging, CorrelationIdMiddleware, Prometheus /metrics, OpenTelemetry tracing (no-op), Sentry (no-op). Production hardening birinchi qadami.

---

> ## BUTUN RETAIL MAHSULOTI FUNKSIONAL YAKUNLANDI.
>
> | Blok | Vazifalar | Holat |
> |---|---|---|
> | B1 — Auth/RBAC/i18n/Katalog/Mijoz/User | T1 T2 T3 T4 T5 T6 | ✅ |
> | B2 — Ombor/Buxgalteriya/Buyurtma/Shablon/Sync | T9 T10 T11 T12 T13 | ✅ |
> | B3 — Davomat/GPS/Yetkazish/Push | T16 T17 T18 T19 | ✅ |
> | B4 — Shartnoma/Murojaat/Aksiya/Statistika | T23 T24 T25 T22 | ✅ |
> | T27 — Observability (production hardening) | T27 | ✅ (v0.26.0) |
| CI/CD + Deploy — GitHub Actions, Dockerfile, infra | — | ✅ (v0.27.0) |
> | Push delivery — FCM HTTP v1, APNs JWT ES256 HTTP/2 | — | ✅ (v0.28.0) |
> | Stats SQL agregatsiya + indekslar (production hardening) | — | ✅ (v0.29.0) |
> | Frontend — Veb SPA poydevori | T7 | ✅ (v0.20.0) |
> | Frontend — Katalog/Mijoz veb UI | T8 | ✅ (v0.21.0) |
> | Frontend — Buyurtma/Statistika veb UI | — | ✅ (v0.22.0) |
> | Frontend — Foydalanuvchilar boshqaruvi veb UI | — | ✅ (v0.31.0) |
> | Frontend — Shartnoma/Murojaat/Aksiya veb UI | — | ✅ (v0.32.0) |
> | Mobil — Flutter offline yadro | T14 | ✅ (v0.23.0) |
> | Mobil — Agent ekranlari | T21 | ✅ (v0.24.0) |
> | Mobil — Kuryer ekranlari | T20 | ✅ (v0.25.0) |
> | Production-readiness: GPS filtri, seed, code-split, native paketlar | — | ✅ (v0.33.0) |
>
> **Backend jami: 811 test, 18 migratsiya, ~19 modul. Frontend T7+T8+Buyurtma/Statistika+Foydalanuvchilar+Shartnoma/Murojaat/Aksiya: 117 test, build toza. Mobil T14+T21+T20: 128 test, flutter analyze toza.**

---

## 5. Ma'lum cheklovlar va texnik qarz

Quyidagi ishlar aniqlandi va keyingi vazifalarga ko'chirildi:

| Cheklov | Rejalashtirilgan sprint |
|---|---|
| ~~PII pgcrypto AES shifrlash + HMAC blind-index (`inn`, `inps`, `phone`) — hozir ochiq-matnli~~ **✅ Hal qilindi (T5 — ilova-darajali AES-GCM, `EncryptedString`, `blind_index`)** | **T5** |
| ~~`app_user.phone`/`full_name` ochiq-matn — T6 gacha `VARCHAR`~~ **✅ Hal qilindi (T6 — `EncryptedString`, migratsiya 0005, phone_bi blind-index)** | **T6** |
| ~~`full_name` `mask_pii()` da maskalanmagan — audit logda ism ko'rinishi mumkin~~ **✅ Hal qilindi (T6 — `mask_pii()` ga `full_name` qo'shildi)** | **T6** |
| ~~PII kalit denylist yo'q — dev-default 64-belgili hex prod da format tekshiruvini o'tar edi~~ **✅ Hal qilindi (T6 — `validate_pii_keys_in_prod()` denylist qo'shildi)** | **T6** |
| ~~Prometheus metrikalar, OpenTelemetry tracing, Sentry, strukturalangan JSON log (`correlation_id`)~~ **✅ Hal qilindi (T27 — v0.26.0)** | **T27** |
| ~~DB-darajada append-only himoya (RLS/REVOKE UPDATE DELETE) moliyaviy jadvallarda~~ **✅ Qisman hal qilindi (T9/T10 — `stock_movement` va `ledger_entry` uchun Postgres RULE qo'shildi)**; `price_history`, `audit_log`, `outbox_event` uchun keyingi hardening da | **Hardening (B4)** |
| ~~`Order.warehouse_id` — buyurtma yaratilgandagi ombor ma'lumotini saqlash (kompensatsiya to'g'ri omborga borishi uchun)~~ **✅ Hal qilindi (T11 — migratsiya 0007, `order.warehouse_id`)** | **T11** |
| ~~Promo/discount logikasi — hozir `discount=0` qattiq kodlangan; chegirma klient tomonidan belgilanmaydi~~ **✅ Hal qilindi (T25 — `compute_line_discount()` server-avtoritar, `discount_percent ∈ (0,100]`, cap himoyasi)** | **T25** |
| `apply` warehouse_id passthrough — hozir `ApplyTemplateIn.warehouse_id` to'g'ridan-to'g'ri uzatiladi; warehouse moduli (kelajak) to'liq jihatda amalga oshirilganda default ombor tanlash mantig'i kengaytiriladi | **Warehouse moduli** |
| Shablon audit context — `apply` natijasidagi `audit_log` yozuvida `template_id` ref yo'q; kuzatuvchanlik uchun qo'shiladi | **Kichik (keyingi)** |
| Push SAVEPOINT + `create_order()` rollback o'zaro ta'siri: parallel bir xil `client_uuid` bilan batch idempotentlik konflikti (Postgres tor ssenariy) — T13 da qisman hal qilindi, to'liq yechim T14 da | **T14** |
| `delete_template` payload'da `store_id` kichik — pull scope filtri payload'dan `store_id` oladi, lekin order_template delete hodisasida store_id payload'da bo'lmasligi mumkin | **T14 (kichik)** |
| ~~Sync metrika (Prometheus): push/pull latency, batch hajmi, rate-limit hiti~~ **✅ Qisman hal qilindi (T27 — `sync_push_total` counter qo'shildi; push/pull latency kelajakda kengaytirish mumkin)** | **T27** |
| Valyuta whitelist (ISO 4217 to'liq ro'yxat) — hozir faqat `max_length=3` tekshiruvi; noto'g'ri kod (`ZZZ`) ham qabul qilinadi | **Kelajak** |
| `check_out` `IntegrityError` ushlash yo'q — parallel check_out race holati `500` qaytarishi mumkin (check_in da tuzatildi, check_out da qoldi) | **LOW (keyingi sprint)** |
| GPS `decimal_places` enforce — Pydantic `decimal_places=7` shart, lekin DB `NUMERIC(10,7)` qo'shimcha yumaloqlash qiladi; katta raqam uchun tekshiruv yo'q | **LOW (kuzatish)** |
| Multi-day timezone: UTC+5 muhitida yarim tunda `work_date` oldingi kun bo'lishi mumkin (server UTC bo'yicha hisoblaydi) | **LOW (kelajak hardening)** |
| **GPS: `alembic upgrade 0011` — `TIMESCALE_URL` alohida env kerak** (`alembic.ini` standart `DATABASE_URL` ishlatadi); infra konfiguratsiya avtomatlashtirilmagan. Runbook: `TIMESCALE_URL=<ts_url> alembic upgrade 0011` | **MEDIUM (infra sprint)** |
| ~~**GPS: ADR §3.7 work-hours filter** — agent/courier GPS faqat attendance shift oynasida ko'rinishi kerak; hozir enforce qilinmagan~~ **✅ Hal qilindi (v0.33.0 — `gps_work_hours_filter_enabled`, batch boshida bitta SELECT, cross-DB OLTP+TimescaleDB)** | — |
| MinIO real ulanish smoke-test — hozir `FakeStorage` (xotiraga) ishlatiladi; prod MinIO bucket yaratish va ulanishni tekshirish avtomatlashtirilmagan | **Hardening** |
| i18n `message_key` kengaytmasi — katalog xatolari (`catalog.*`) hozir `AppError` orqali lokalizatsiyalanmagan xom kalit qaytaradi; tarjima `MESSAGES` ga qo'shilishi kerak | **T7/T8** |
| ~~`role` ustuni `ENUM` yoki `CHECK` cheklovi — hozir `VARCHAR(20)`~~ **✅ Hal qilindi (T2 — CHECK constraint 0002)** | **T2** |
| ~~`store` roli deny-all — `Store.user_id` FK yo'qligi sababli IDOR xavfi~~ **✅ Hal qilindi (T5 — `Store.user_id` FK)** | **T5** |
| Production muhitida `openapi.json` endpointini yopish yoki autentifikatsiya bilan himoya qilish | **Keyingi commit** |
| ~~`python-jose` CVE~~ **✅ Hal qilindi (T1 — PyJWT)** | **T1** |
| ~~i18n backend~~ **✅ Hal qilindi (T3)** | **T3** |
| DB-darajali optimistik lock (`version_id_col` SQLAlchemy yoki `FOR UPDATE SKIP LOCKED`) — hozir faqat servis qatlamida `version` tekshiruvi | **Kelajak** |
| ~~Reactivate endpoint (is_active=False → True) yo'q — hozir faqat deaktivatsiya~~ **✅ Hal qilindi (v0.31.0 — `PATCH /users/{id}/activate`, `service.activate_user()`, audit+outbox, 2 test)**. Parol o'zgartirish endpointi hali yo'q | **Kelajak (parol o'zgartirish)** |
| Katta jadval migratsiya strategiyasi: agar `app_user` millionlab qatorga yetsa, 0005 in-migration backfill uzoq lock ushlab qolishi mumkin; online migration yondashuvi kerak | **Hardening (B4)** |
| ~~**Stats Python agregatsiya → DB GROUP BY**: `sales_stats()` va `delivery_stats()` barcha mos yozuvlarni Python ga yuklab agregatsiya qiladi. Yirik masshtabda Postgres `DATE_TRUNC` + `GROUP BY` afzal (servis qatlamini o'zgartirish, router/sxema/test o'zgarmaydi)~~ **✅ Hal qilindi (v0.29.0 — `func.count`/`func.sum`/`func.coalesce`/`func.avg` + `GROUP BY`; dialekt-aware sana guruhlash; indekslar `0017`)** | **Production scale oldidan** |
| ~~**recharts bundle 993 kB**: `StatsDashboardPage` da recharts to'liq import qilinmoqda. `React.lazy` + dinamik `import()` bilan ajratish kerak~~ **✅ Hal qilindi (v0.33.0 — `React.lazy` + `manualChunks`; asosiy bundle 566→210 kB)** | — |
| ~~**`@mantine/dates` React 19 muvofiqligi**: `valid_from`/`valid_to` maydonlari `TextInput` bilan (Shartnoma, Aksiya). `@mantine/dates@7.x` React 19 talab qiladi~~ **✅ Hal qilindi (v0.33.0 — `@mantine/dates@7.17.8` React 18 bilan mos `DateInput`)** | — |
| ~~**`alembic_timescale` / TimescaleDB migratsiya avtomatizatsiyasi**: `alembic upgrade 0011` uchun `TIMESCALE_URL` alohida env kerak; CI/CD da alohida step qo'shilishi kerak~~ **✅ Hal qilindi (v0.33.0 — `backend/alembic_timescale/` OLTP'dan mustaqil muhit, `make migrate-timescale`)** | — |
| ~~**OTel/Prometheus observability**: OpenTelemetry tracing, Prometheus metrikalar, strukturalangan JSON log (`correlation_id`), Sentry integratsiyasi~~ **✅ Hal qilindi (T27 — v0.26.0)** | **Production hardening** |
| ~~**CI/CD (GitHub Actions to'liq)**: backend/web/mobile workflow, Dockerfile multi-stage venv, docker-compose.prod.yml, infra/ konfiguratsiya~~ **✅ Hal qilindi (v0.27.0)** | **Production hardening** |
| ~~**FCM/APNs HTTP implementatsiyasi**: `FcmProvider` va `ApnsProvider` production skelet — hozir `httpx` TODO; real push notification uchun to'liq implement kerak~~ **✅ Hal qilindi (v0.28.0 — FCM HTTP v1 OAuth2 + APNs JWT ES256 HTTP/2, token invalidatsiya, PII-safe log, no-op)** | **Production hardening** |
| **Mobil: `build_runner` `.g.dart` regen**: `deliveries` jadvali qo'shilgandan keyin `dart run build_runner build --delete-conflicting-outputs` ishlatilishi kerak; CI da avtomatlashtirish tavsiya etiladi | **Production hardening** |
| ~~**Mobil: camera/biometric/geolocator production paketlar**: `image_picker`, `local_auth`, `geolocator` — hozir stub~~ **✅ Hal qilindi (v0.33.0 — real `local_auth`, `geolocator`, `image_picker`, `mobile_scanner`; AndroidManifest/Info.plist ruxsatlari; graceful fallback)** | — |
| ~~**DB append-only RLS**: `stock_movement`/`ledger_entry` UPDATE/DELETE DB-darajada bloklanishi kerak~~ **✅ Hal qilindi (v0.30.0 — `append_only.py` + migratsiya 0018: SQLite `RAISE(ABORT)` + PG `RAISE EXCEPTION` triggerlar; eski 0006 jim-yutar RULE'lar almashtirildi)**. Qoldi (ixtiyoriy): `audit_log`, `outbox_event`, `price_history` uchun ham kengaytirish | **Production hardening** |
| ~~**Demo seed / deploy prereq**: demo ma'lumotlar qo'lda kiritilardi; idempotent seed skripti va `make seed` buyrug'i yo'q edi~~ **✅ Hal qilindi (v0.33.0 — `backend/scripts/seed.py` idempotent; parol env'dan; `make seed`)** | — |
| ~~**`db.py` dialekt-aware engine**: `_make_engine` SQLite'da `pool_size`/`max_overflow` bersa `TypeError` chiqar edi — seed/demo SQLite rejimida ishlamasdi~~ **✅ Hal qilindi (v0.33.0 — `_make_engine(url)` sqlite URL ni aniqlaydi va faqat `echo` uzatadi)** | — |
| **Real Postgres/TimescaleDB + qurilma integratsiya testlari**: hozir barcha testlar SQLite in-memory; Postgres va TimescaleDB bilan to'liq integratsiya testi, Flutter real qurilmada smoke-test | **Pilot deploy oldidan** |
| **Mobil: native qurilmada real test**: `local_auth`, `geolocator`, `image_picker`, `mobile_scanner` paketlari real Android/iOS qurilmada sinalmagan | **Pilot deploy oldidan** |
| **FCM/APNs real kredensiallar**: `FCM_SERVICE_ACCOUNT_JSON` va APNs kalitlari production uchun hali tayyorlanmagan | **Pilot deploy oldidan** |
