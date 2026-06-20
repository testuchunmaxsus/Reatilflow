# ADR-002 — Multi-Tenant SaaS arxitekturasi

| | |
|---|---|
| **Status** | Qabul qilindi (2026-06-20) |
| **Kontekst** | RETAIL single-tenant'dan multi-tenant SaaS'ga o'tkaziladi |
| **Bog'liq** | [ADR-001](ADR-001-retail-architecture.md) |

## 1. Kontekst va maqsad

Hozir RETAIL **single-tenant** — bitta distribyutor korxona uchun. Yangi maqsad: **ko'p korxonaga sotiladigan SaaS platforma**:

- **superadmin** (platforma egasi) → **korxona (enterprise)** yaratadi: nom, INN, birinchi admin login/parol, holat. Korxonalararo ko'radi.
- Har **korxona** → o'z ishchilarini (administrator/agent/courier/accountant/store) yaratadi + o'ziga kerakli **modullarni yoqadi/o'chiradi** ("xizmat bo'limlari" = modul-yoqish).
- Har korxona ma'lumoti **to'liq izolyatsiya** — faqat o'zinikini ko'radi.

**Tizim JONLI (Railway)** — Postgres'da seed ma'lumot bor; migratsiya uni "default korxona"ga backfill qilishi shart.

## 2. Asosiy qarorlar

### 2.1 Izolyatsiya strategiyasi — shared-DB + `enterprise_id` + RLS
**Qaror:** Yagona DB, yagona sxema, har tenant-scoped jadvalda `enterprise_id` diskriminator ustun. Ikki qatlamli himoya:
1. **Ilova qatlami** — har query `WHERE enterprise_id = <joriy>` bilan filtrlanadi (scope helper).
2. **DB qatlami (defense-in-depth)** — PostgreSQL **Row-Level Security (RLS)** siyosatlari: ilova bitta filtrni o'tkazib yuborsa ham DB cross-tenant o'qishni BLOKLAYDI.

**Asos:** schema-per-tenant migratsiyani murakkablashtiradi; db-per-tenant og'ir. Cross-tenant ma'lumot sizishi = halokatli → RLS majburiy backstop.

### 2.2 `enterprise` modeli
```
enterprise: id (uuid7 PK), name, inn (nullable), status (active|suspended),
            enabled_modules (JSONB array), created_at, updated_at, deleted_at
```
`enabled_modules` — yoqilgan modul kalitlari: `["catalog","customers","orders","stock","finance","delivery","attendance","gps","contracts","tickets","promo","stats","push"]`. Default: hammasi yoqilgan.

### 2.3 `enterprise_id` qaysi jadvallarga
**Barcha tenant-scoped:** app_user*, store, agent_store, category, price_segment, product, product_price, price_history, product_note, order, order_line, order_template(+line), stock_movement, stock_balance, ledger_entry, account_balance, delivery, attendance, gps_point (TimescaleDB), contract, ticket, ticket_message, promo, push_log, device_token, outbox_event, audit_log.
**Scoped EMAS:** `enterprise` (tenant entity), `superadmin` user (`enterprise_id = NULL`).
\* `app_user`: superadmin'dan tashqari har user bitta korxonaga tegishli.

### 2.4 `superadmin` roli
RBAC'ga yangi rol. `enterprise_id = NULL`. Ruxsatlar: korxona CRUD, `enabled_modules` boshqarish, suspend/activate, korxonaning birinchi administratorini yaratish. **Korxona biznes-ma'lumotiga KIRMAYDI** (maxfiylik — faqat tenant boshqaruvi). RLS superadmin uchun bypass (yoki maxsus siyosat).

### 2.5 Modul-yoqish (module gating)
- `require_module(module_key)` dependency — `module_key in enterprise.enabled_modules` bo'lmasa **403 `feature_disabled`**. Har modul routeriga qo'shiladi.
- `GET /enterprise/me` — joriy korxona + enabled_modules qaytaradi. Veb/mobil UI yoqilmagan modullarni yashiradi.
- Korxona-admin o'z korxonasi modullarini yoqadi/o'chiradi; superadmin suspend qila oladi.

### 2.6 JWT
Token'ga `enterprise_id` claim (superadmin uchun `null`). Login'da beriladi. So'rovlar **token'dagi** enterprise_id bo'yicha scope qilinadi (query param EMAS — soxtalashtirib bo'lmaydi).

### 2.7 Login / telefon yagonaligi
**Qaror:** telefon **platforma bo'yicha global yagona**. Login (telefon+parol) → user + uning enterprise_id topiladi → token o'sha enterprise_id bilan beriladi. Login'da korxona tanlash YO'Q (oddiy UX). `phone_bi` blind-index global unique qoladi.
**Trade-off:** bir telefon = bitta korxonada bitta akkaunt. v1 uchun maqbul.
**Per-enterprise unique:** product SKU/barcode, kategoriya nomi, client_uuid idempotentlik → `(enterprise_id, ...)` unique (turli korxonada bir xil SKU bo'lishi mumkin). Global unique faqat: phone_bi, enterprise INN(?).

### 2.8 Migratsiya + backfill (kritik — jonli ma'lumot)
Bosqichli, NON-DESTRUCTIVE (migratsiya 0020 + alembic_timescale ts0002):
1. `CREATE TABLE enterprise`.
2. **"Default Korxona"** INSERT (fixed UUID, status=active, hamma modul yoqilgan).
3. Har jadval: `ADD COLUMN enterprise_id` (nullable) → `UPDATE SET enterprise_id = <default>` → `ALTER NOT NULL` + FK + index `(enterprise_id)` (yoki kompozit).
4. Unique constraint'larni per-enterprise yangilash (global → `(enterprise_id, sku)` h.k.).
5. RLS siyosatlari (har jadval: `USING (enterprise_id = current_setting('app.current_enterprise_id')::uuid)`); ilova har request `SET app.current_enterprise_id` qiladi.
6. superadmin user — migratsiyada EMAS (parol hardcode qilinmaydi), alohida `scripts/seed.py`/superadmin-create skript orqali.
Downgrade: ustun/jadval drop (ma'lumot-yo'qotish ogohlantirishi).

### 2.9 Mavjud testlar strategiyasi
Testlar `create_all`'dan quriladi → enterprise_id NOT NULL bo'lsa mavjud fixture'lar buziladi. Yechim: test fixture'lar (conftest) "default test enterprise" yaratadi va factory'lar enterprise_id ni avtomatik to'ldiradi. Bosqichma-bosqich har modul testi yangilanadi.

## 3. Bosqichli rollout (orkestra DAG)

| Bosqich | Mazmun | Asosiy risk |
|---|---|---|
| **MT1 — Foundation** | enterprise model + migratsiya 0020 (enterprise_id + backfill + default korxona) + superadmin rol + JWT enterprise_id + scope helper + RLS + test fixture moslash | Backfill, RLS to'g'riligi |
| **MT2 — Per-modul scope** | HAR modul query'siga enterprise filtr (catalog, customers, orders, stock, finance, delivery, attendance, gps, contracts, tickets, promo, stats, sync, push, users). Cross-tenant IDOR testlari | Bitta filtrni o'tkazib yuborish |
| **MT3 — Modul-gating** | `require_module` + enabled_modules + `/enterprise/me` | — |
| **MT4 — superadmin backend** | enterprise CRUD + birinchi-admin yaratish + modul toggle + suspend | superadmin RLS bypass |
| **MT5 — Veb** | superadmin panel + korxona-admin modul sozlamalari + UI gating + login enterprise konteksti | — |
| **MT6 — Mobil** | enterprise konteksti (JWT), yoqilmagan modul yashirish | — |

Har bosqich: orkestra develop→review→gate, testlar yashil, Railway'ga deploy.

## 4. Xavfsizlik tahlili
**#1 risk: cross-tenant ma'lumot sizishi.** Mitigatsiya:
1. Ilova-darajali enterprise filtr HAR query'da (to'liq bo'lishi shart — bittasi o'tkazib yuborilsa risk).
2. **PostgreSQL RLS** — qattiq backstop (ilova xato qilsa ham DB bloklaydi). **MAJBURIY.**
3. Har modul uchun cross-tenant IDOR testlari (korxona A korxona B ma'lumotini ko'ra olmasligi).
4. JWT enterprise_id — server-avtoritar (token'dan, query'dan emas).

**#2: superadmin** — tenant ma'lumotiga kirmaydi (maxfiylik). RLS superadmin bypass ehtiyotkorlik bilan.

## 5. Ochiq savollar (foydalanuvchi tasdiqlashi kerak)
1. **Login:** telefon global-yagona (tavsiya) — tasdiqlansin.
2. **RLS:** DB-darajali himoya yoqilsinmi (tavsiya: ha) — qo'shimcha ishonchlilik.
3. **Backfill:** mavjud jonli ma'lumot "Default Korxona"ga o'tadi — tasdiqlansin.
4. **superadmin ma'lumot ko'rishi:** korxona biznes-ma'lumotini ko'rmaydimi (maxfiylik, tavsiya) yoki support uchun ko'radimi.
