# RETAIL — Ulgurji/Chakana Savdo va Distribyutsiya Platformasi

Modular monolit arxitektura: FastAPI backend, React+TypeScript veb/desktop (Tauri), Flutter mobil (offline-first).

## Holat

**v0.33.0 — Production-readiness (backend 811, veb 117, mobil 128 test). GPS ish-soati filtri✅ Seed✅ Code-split✅ Native paketlar✅. Qolgan: real-qurilma/jonli-infra test + pilot deploy (1-2 distribyutor).**

Backend: BACKEND B1-B4 + T27 Observability + CI/CD + FCM/APNs push delivery + Stats SQL agregatsiya + Append-only DB invariant + Production-readiness TO'LIQ YAKUNLANDI (811 test, har vazifa orkestrator gate PASS). 18 migratsiya, ~19 modul. Observability hujjatlari: [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md). Deploy runbook: [docs/DEPLOY.md](docs/DEPLOY.md).
Frontend: T7✅ veb SPA poydevori; T8✅ Katalog + Mijoz bazasi UI; ✅ Buyurtma + Statistika UI (recharts code-split: 566→210 kB); ✅ Foydalanuvchilar boshqaruvi UI; ✅ Shartnoma + Murojaat + Aksiya UI (React+TS+Vite+Mantine+TanStack+recharts, `@mantine/dates@7.17.8`). Jami: 8 modul, 117 test, build toza.
Mobil: T14✅ Flutter offline-first yadro (29 test); T21✅ Agent ekranlari (71 test); T20✅ Kuryer ekranlari — yetkazishlar ro'yxati/detali, holat mashinasi (VALID_TRANSITIONS), GPS (45s), proof_photo (128 test, flutter analyze toza). Native paketlar: local_auth, geolocator, image_picker, mobile_scanner.

**Yakuniy arxitektura xulosasi:**
- **Backend**: FastAPI modular monolit, PostgreSQL primary/replica, TimescaleDB (GPS), Redis, MinIO. Offline-first transactional outbox.
- **Veb**: React 18 + TypeScript + Vite + Mantine 7 + TanStack Query + i18next + Tauri. 8 modul: Katalog, Mijozlar, Buyurtmalar, Statistika, Foydalanuvchilar, Shartnomalar, Murojaatlar, Aksiyalar.
- **Mobil**: Flutter offline-first + Drift SQLite (8 jadval) + dio + Riverpod + go_router. Agent (T21) va Kuryer (T20) ilovasida SyncService, outbox, secure_storage auth.

Observability hujjatlari: [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md).
Veb frontend hujjatlari: [docs/WEB.md](docs/WEB.md).
Mobil hujjatlari: [docs/MOBILE.md](docs/MOBILE.md).
Statistika hujjatlari: [docs/STATS.md](docs/STATS.md).
Aksiya hujjatlari: [docs/PROMO.md](docs/PROMO.md). Migratsiya: `0016_promo.py`.
Murojaat hujjatlari: [docs/TICKETS.md](docs/TICKETS.md). Migratsiya: `0015_ticket.py`.
Shartnoma hujjatlari: [docs/CONTRACTS.md](docs/CONTRACTS.md). Migratsiya: `0014_contract.py`.
Push hujjatlari: [docs/PUSH.md](docs/PUSH.md). Migratsiya: `0013_push_log.py`.
Yetkazish hujjatlari: [docs/DELIVERY.md](docs/DELIVERY.md). Migratsiya: `0012_delivery.py`.
GPS hujjatlari: [docs/GPS.md](docs/GPS.md).
Davomat hujjatlari: [docs/ATTENDANCE.md](docs/ATTENDANCE.md).
Sync API hujjatlari: [docs/SYNC.md](docs/SYNC.md).

- [CHANGELOG.md](CHANGELOG.md) — versiyalar bo'yicha o'zgarishlar
- [docs/FOUNDATION.md](docs/FOUNDATION.md) — poydevor texnik xulosasi va texnik qarz
- [docs/AUTH.md](docs/AUTH.md) — Auth moduli texnik qo'llanmasi (endpointlar, token oqimi, xavfsizlik)
- [docs/RBAC.md](docs/RBAC.md) — RBAC moduli texnik qo'llanmasi (ruxsat matritsasi, dependency, scope, endpointlar)
- [docs/I18N.md](docs/I18N.md) — i18n qo'llanmasi (tillar, envelope format, `message_key` katalogi, T4/T5 uchun qo'shish tartibi)
- [docs/CATALOG.md](docs/CATALOG.md) — Katalog moduli texnik qo'llanmasi (endpointlar, narx tarixi, branch ko'rinish, idempotentlik, rasm upload, migratsiya 0003 runbook)
- [docs/CUSTOMERS.md](docs/CUSTOMERS.md) — Mijoz bazasi moduli texnik qo'llanmasi (endpointlar, PII shifrlash, blind-index qidiruv, RBAC scope, migratsiya 0004 runbook)
- [docs/USERS.md](docs/USERS.md) — Foydalanuvchi boshqaruvi moduli texnik qo'llanmasi (endpointlar, PII shifrlash, phone_bi, RBAC, migratsiya 0005 runbook)
- [docs/STOCK_FINANCE.md](docs/STOCK_FINANCE.md) — Ombor (T9) va Buxgalteriya (T10) texnik qo'llanmasi (endpointlar, append-only model, IDOR/scope, idempotentlik, migratsiya 0006 runbook)
- [docs/ORDERS.md](docs/ORDERS.md) — Buyurtma moduli texnik qo'llanmasi (endpointlar, atomik tranzaksiya, narx server-avtoritar, holat mashinasi, kompensatsiya, idempotentlik, migratsiya 0007 runbook)
- [docs/SYNC.md](docs/SYNC.md) — Sync moduli texnik qo'llanmasi (push/pull endpointlar, kursor mexanizmi, IDOR scope, offline-first oqimi, migratsiya 0009 runbook)
- [docs/ATTENDANCE.md](docs/ATTENDANCE.md) — Davomat moduli texnik qo'llanmasi (endpointlar, biometriya modeli, server-avtoritar vaqt, RBAC/IDOR, idempotentlik, migratsiya 0010 runbook)
- [docs/GPS.md](docs/GPS.md) — GPS Ingest moduli texnik qo'llanmasi (endpointlar, TimescaleDB izolyatsiya, recorded_at/ingested_at, RBAC/IDOR, idempotentlik, batch, migratsiya 0011 runbook)
- [docs/DELIVERY.md](docs/DELIVERY.md) — Yetkazib berish moduli texnik qo'llanmasi (endpointlar, holat mashinasi, GPS bog'lanishi, RBAC/IDOR, bir buyurtmaga bitta aktiv yetkazish, proof_photo, idempotentlik, migratsiya 0012 runbook)
- [docs/PUSH.md](docs/PUSH.md) — Push bildirishnomalar moduli texnik qo'llanmasi (FCM/APNs, outbox consumer izolyatsiyasi, process_pending_pushes oqimi, PushProvider, PATCH /push/device-token, arq worker, migratsiya 0013 runbook)
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — Shartnoma moduli texnik qo'llanmasi (endpointlar, RBAC/IDOR scope, status DERIVED modeli, fayl yuklash magic-byte, raqam unikalligi, list_expiring, migratsiya 0014 runbook)
- [docs/TICKETS.md](docs/TICKETS.md) — Murojaat moduli texnik qo'llanmasi (endpointlar, RBAC/IDOR scope, holat mashinasi, xabar va attachment, idempotentlik, migratsiya 0015 runbook)
- [docs/PROMO.md](docs/PROMO.md) — Aksiya moduli texnik qo'llanmasi (endpointlar, RBAC/scope, rule_json formati, server-avtoritar compute_line_discount oqimi, banner, idempotentlik, migratsiya 0016 runbook)
- [docs/STATS.md](docs/STATS.md) — Statistika moduli texnik qo'llanmasi (endpointlar, RBAC/scope jadvali, replica vs primary DB qoidasi, javob sxemalari, curl misollari, tech-debt)

## Loyiha tuzilishi

```
retail/
├── backend/          # FastAPI modular monolit (Python 3.12)
│   ├── app/
│   │   ├── main.py           # FastAPI ilova, health/readiness endpointlar
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic Settings (env o'zgaruvchilar)
│   │   │   ├── crypto.py     # AES-256-GCM PII shifrlash + HMAC blind-index
│   │   │   ├── db.py         # Async SQLAlchemy engine + session
│   │   │   └── uuid7.py      # UUID v7 generator
│   │   ├── models/           # SQLAlchemy ORM modellari (modul bo'yicha)
│   │   │   ├── base.py       # Umumiy mixin (id, version, timestamps)
│   │   │   ├── user.py       # app_user
│   │   │   ├── store.py      # store, agent_store
│   │   │   ├── catalog.py    # product, category, price_segment, ...
│   │   │   ├── audit.py      # audit_log
│   │   │   └── outbox.py     # outbox_event
│   │   └── tests/
│   │       └── test_health.py
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 0001_initial.py       # To'liq DDL (barcha B1 jadvallari)
│   │       ├── 0002_role_check.py    # app_user.role CHECK constraint
│   │       ├── 0003_catalog_constraints.py  # barcode/narx partial unique indekslar
│   │       ├── 0004_store_pii_and_user_fk.py  # PII BYTEA + blind-index + user_id FK
│   │       ├── 0005_user_phone_encrypt.py  # app_user phone/full_name BYTEA + phone_bi
│   │       ├── 0006_stock_finance.py       # stock_movement/balance + ledger_entry/account_balance + Postgres RULE
│       │   ├── 0007_orders.py             # order + order_line + partial unique (store_id, client_uuid)
│       │   ├── 0008_order_templates.py    # order_template + order_template_line (narxsiz)
│       │   ├── 0009_outbox_seq.py         # outbox_event.seq + Postgres Sequence (T13 kursor)
│       │   ├── 0010_attendance.py         # attendance + partial unique + downgrade guard (T16)
│       │   ├── 0011_gps.py               # gps_point + TimescaleDB hypertable + 90d retention (T17)
│       │   ├── 0012_delivery.py          # delivery + partial unique indekslar + downgrade guard (T18)
│       │   ├── 0013_push_log.py          # push_log + UNIQUE (outbox_event_id, user_id) + downgrade guard (T19)
│       │   ├── 0014_contract.py          # contract + partial unique (store_id, number) + downgrade guard (T23)
│       │   ├── 0015_ticket.py            # ticket + ticket_message + partial unique (client_uuid) + downgrade guard (T24)
│       │   └── 0016_promo.py             # promo + partial unique (client_uuid) + downgrade guard (T25)
│   ├── alembic.ini
│   └── pyproject.toml
│
├── web/              # React + TypeScript SPA (veb + Tauri desktop) — T7✅ T8✅
│   ├── src/
│   │   ├── api/        # API klient (client.ts, types.ts, schema.ts, upload)
│   │   ├── auth/       # AuthContext, ProtectedRoute, LoginPage
│   │   ├── rbac/       # usePermissions, <Can>
│   │   ├── i18n/       # uz/ru lokalizatsiya
│   │   ├── layouts/    # AppShell (AppLayout)
│   │   ├── features/   # Katalog (T8), Mijozlar (T8), Foydalanuvchilar (v0.31.0)
│   │   ├── hooks/      # useApiError, useDebounce
│   │   ├── components/ # ConfirmDeleteModal va boshqalar
│   │   └── pages/      # DashboardPage, PlaceholderPage
│   └── package.json
│
├── mobile/           # Flutter offline-first (agent, kuryer, do'kon) — T14✅ T21✅ T20✅
│   ├── lib/
│   │   ├── core/         # AppConfig (API_BASE_URL), app_router
│   │   ├── data/local/   # Drift SQLite (8 jadval + DAO, schemaVersion 2)
│   │   ├── data/remote/  # ApiClient, AuthInterceptor, TokenStorage
│   │   ├── data/sync/    # SyncService, SyncNotifier
│   │   └── features/     # auth, home, orders, delivery, attendance
│   └── pubspec.yaml
│
├── desktop/          # Tauri qobiq (web/ bilan bir xil React kod bazasi)
│   └── .gitkeep
│
├── infra/            # Kustomize/Helm manifests (keyinchalik)
│   └── .gitkeep
│
├── docs/
│   ├── ADR-001-retail-architecture.md
│   └── PLAN-retail-dag.md
│
├── docker-compose.yml    # Lokal dev: postgres, timescaledb, redis, minio
├── .env.example          # Barcha kerakli o'zgaruvchilar (placeholder)
├── Makefile              # up, migrate, gen-client, test, lint
└── .pre-commit-config.yaml
```

## Lokal ishga tushirish

### Talablar

- Docker Desktop >= 24
- Python 3.12 (`pyenv` yoki `asdf` tavsiya etiladi)
- Node.js >= 20 (veb klient generatsiya uchun)
- Flutter >= 3.22 (mobil ilova uchun; T14✅ — `mobile/` papkasi to'liq)

### 1. .env faylini tayyorlash

```bash
cp .env.example .env
# .env faylini o'z qiymatlaringiz bilan to'ldiring
```

### 2. Infra servislarini ishga tushirish

```bash
make up
# yoki to'liq:
docker compose up -d
docker compose ps   # barcha servislar healthy bo'lishi kerak
```

### 3. Backend o'rnatish va migratsiya

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

make migrate
# yoki to'liq:
cd backend && alembic upgrade head
```

### 4. Backend serverini ishga tushirish

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
# OpenAPI JSON: http://localhost:8000/openapi.json
```

### 5. OpenAPI klientlarini generatsiya qilish

```bash
make gen-client
# web/src/api/ va mobile/lib/api/ papkalarini to'ldiradi
```

### 6. Testlarni ishlatish

```bash
make test
```

### 7. Linting

```bash
make lint
```

## Asosiy buyruqlar (Makefile)

| Buyruq | Tavsif |
|---|---|
| `make up` | Docker Compose servislarini ishga tushirish |
| `make down` | Docker Compose servislarini to'xtatish |
| `make migrate` | OLTP Alembic migratsiyalarini ishlatish (`upgrade head`) |
| `make migrate-timescale` | TimescaleDB Alembic migratsiyalarini ishlatish (`TIMESCALE_URL` kerak) |
| `make seed` | Demo ma'lumotlarni yuklash (idempotent) — `SEED_ADMIN_PASSWORD` env tavsiya etiladi |
| `make gen-client` | OpenAPI dan TS + Dart klientlarini generatsiya qilish |
| `make test` | pytest testlarini ishlatish |
| `make lint` | ruff + black tekshiruvi |

## CI va production deploy

> **Eslatma:** GitHub Actions va Docker bu ishlab chiqish muhitida ishga tushirilmagan.
> Barcha workflow va compose fayllar sintaktik jihatdan to'g'ri va ishlatishga tayyor;
> real CI/CD sozlashda [docs/DEPLOY.md](docs/DEPLOY.md) runbookidagi qadamlarni bajar.

### CI lokal tekshiruvi

```bash
make ci-backend   # ruff + black + pytest (811 test, SQLite mode)
make ci-web       # tsc + eslint + vitest
make ci-mobile    # flutter analyze + flutter test
```

### Production deploy

```bash
# 1. Secrets tayyorlash
cp .env.prod.example .env.prod
# .env.prod ni to'ldiring (openssl rand -hex 32 va boshqalar — DEPLOY.md §1)

# 2. Infra va migratsiya
make deploy-up
make deploy-migrate

# 3. Sog'liq tekshiruvi
curl -s https://your-domain.com/health
curl -s https://your-domain.com/readiness
```

To'liq qo'llanma, TLS sozlash, MinIO bucket yaratish, replica setup, Prometheus alert qoidalari:
**[docs/DEPLOY.md](docs/DEPLOY.md)**

## Arxitektura

Batafsil: [docs/ADR-001-retail-architecture.md](docs/ADR-001-retail-architecture.md)

**Qisqacha:** FastAPI modular monolit + PostgreSQL primary/replica + TimescaleDB (GPS ingest, alohida `timescale_url`) + Redis + MinIO.
Offline-first: transactional outbox + append-only moliyaviy hodisalar + domen-aware konflikt yechimi.

## Keyingi qadam

**BUTUN RETAIL MAHSULOTI FUNKSIONAL YAKUNLANDI. Production-readiness: v0.33.0.**

Backend 811 test + Veb 117 test + Mobil 128 test. Har workstream orkestrator gate PASS.

Qolgan — jonli infra va pilot:
- **Integratsiya testlari**: real Postgres/TimescaleDB bilan to'liq integratsiya (hozir SQLite in-memory).
- **Mobil: native qurilmada smoke-test**: `local_auth`, `geolocator`, `image_picker`, `mobile_scanner` real Android/iOS qurilmada sinalmagan.
- **FCM/APNs real kredensiallar**: production uchun `FCM_SERVICE_ACCOUNT_JSON` va APNs kalit fayllari tayyorlanishi kerak.
- **DB append-only**: ✅ `ledger_entry`, `stock_movement` (v0.30.0). Qoldi (ixtiyoriy): `audit_log`, `outbox_event`.
- **Pilot deploy** (1-2 distribyutor): `docs/DEPLOY.md` runbook, TLS sertifikat, MinIO bucketlar, replica setup.
