# ADR-001: RETAIL — Ulgurji/Chakana Savdo va Distribyutsiya Platformasi Arxitekturasi

| | |
|---|---|
| **Holati** | Qabul qilindi (Accepted) |
| **Sana** | 2026-06-15 |
| **Muallif** | `architect-agent` (orkestr orqali) |
| **Doira** | To'liq tizim arxitekturasi (Backend, Klient, Ma'lumotlar, Offline, RBAC, Deploy) |
| **Keyingi agentlar** | `planner-agent` (DAG), `developer-agent` (implementatsiya) |

---

## 1. KONTEKST

RETAIL — bitta yirik kompaniya (ko'p filial) uchun ulgurji/chakana savdo va distribyutsiyani avtomatlashtirish platformasi. Ikki rejim: **RETAIL BOZOR** (agent + kuryer bilan to'liq distribyutsiya zanjiri) va **RETAIL ODDIY** (agentsiz, to'g'ridan-to'g'ri buyurtma).

**5 rol:** Administrator, Savdo agenti, Yetkazib beruvchi (kuryer), Buxgalter, Do'kon (mijoz).
**11 modul:** Katalog, Agent kabineti, Davomat, Yetkazib berish, Ombor, Buxgalteriya, Taklif/e'tirozlar, Mijoz bazasi, Statistika, Shartnoma, Aksiya + buyurtma shabloni.

**Tasdiqlangan texnik cheklovlar:** Python + PostgreSQL backend; Flutter mobil (maydon); **veb + desktop birlamchi** (korxona ofislari asosan veb/desktop ishlatadi); qurilma biometriyasi orqali Face ID; offline-first majburiy; uz/ru i18n; PII/biometrik shifrlash + RBAC + audit log; yirik masshtab (Redis, o'qish replikasi, gorizontal masshtablash); MXIK/to'lov hozircha ichki, kelajak uchun kengaytirish nuqtalari.

**Asosiy arxitektura kuchlari (drivers):**
1. **Offline-first majburiyligi** — maydon ilovalari ulanishsiz to'liq ishlashi va keyin ishonchli sinxronlanishi shart.
2. **Moliyaviy aniqlik** — qarz/haqdorlik, ombor qoldig'i pul bilan bog'liq → konflikt yechimi pulni yo'qotmasligi/ikkilantirmasligi shart.
3. **Yirik masshtab, bitta tenant** — ko'p filial va yuqori GPS/buyurtma hajmi.
4. **Aralash klient** — bitta backend uch xil klient tipiga (veb, desktop, mobil) xizmat qiladi.

---

## 2. KO'RIB CHIQILGAN VARIANTLAR

### 2.1. Arxitektura uslubi
- **A. To'liq mikroservis** — mustaqil deploy/masshtab; lekin distributed transaction (qarz+ombor+buyurtma atomik) saga murakkabligi, 11 servis bitta jamoaga ortiqcha, offline-sync bilan ikki barobar murakkab.
- **B. Modular monolit** (tanlandi) — modul ichida ACID tranzaksiya (moliyaviy aniqlik uchun KRITIK), sodda deploy, refaktoring oson, gorizontal replikalash yetarli.
- **C. Klassik bog'liq monolit** — tez boshlash, lekin modullar aralashadi, masshtab/test qiyin.

### 2.2. Backend freymvork
- **FastAPI (tanlandi)** + SQLAlchemy 2.0 + Alembic + Pydantic v2 — async (GPS/push/sync uchun), avtomatik OpenAPI (Flutter+veb klient generatsiyasi), validatsiya.
- **Django + DRF** — tayyor admin/ORM, lekin async cheklangan, OpenAPI kuchsizroq; maxsus admin panelimiz baribir kerak.

### 2.3. Desktop yondashuvi
- **A. Veb SPA (React+TS) + Tauri desktop wrapper (tanlandi)** — bitta kod bazasi veb+desktop; Tauri yengil (~10MB), nativ printer/skaner/eksport.
- **B. Electron** — keng ekotizim, lekin og'ir (~150MB).
- **C. Flutter Web+Desktop** — mobil bilan bir til, lekin murakkab jadval/buxgalteriya UI uchun zaif (canvas).
- **D. PWA** — arzon, lekin chuqur nativ kirish (printer/skaner) cheklangan.

### 2.4. Offline-sync strategiyasi
- **A. Outbox + domen-aware konflikt (tanlandi)** — sodda, oldindan aytib bo'ladigan, moliyaviy yozuvlar append-only (konflikt yo'q).
- **B. CRDT (Automerge/Yjs)** — avtomatik birlashma, lekin og'ir, moliyaviy domen uchun ortiqcha.
- **C. PowerSync/ElectricSQL** — tayyor engine, lekin tashqi bog'liqlik + moliyaviy logikani baribir o'zimiz yozamiz.

---

## 3. QAROR

### 3.1. Umumiy uslub
**Modular monolit** (FastAPI, bitta deploy, qat'iy ichki modul chegaralari — modullar faqat servis interfeyslari orqali muloqot qiladi). Ikki ish yuki alohida deploylanadi:
1. **GPS Ingest Servis** — yuqori chastotali yozish, biznes tranzaksiyalardan izolyatsiya.
2. **Worker (Arq/Celery)** — push, hisobot, sync post-processing, shartnoma muddati.

**Nega monolit:** moliyaviy izchillik (buyurtma → ombor chiqimi → qarz yozuvi) bitta ACID tranzaksiyada bo'lishi kerak; mikroservisda bu xavfli saga talab qiladi. Masshtab — stateless API replikalash + o'qish replikasi + Redis bilan yechiladi.

### 3.2. Komponent topologiyasi

```
   KLIENTLAR                         EDGE: Nginx/Traefik (TLS, rate-limit, routing)
 ┌──────────────┐                              │
 │ Veb SPA      │ HTTPS ──┐         ┌───────────┴────────────────────────┐
 │ (React/TS)   │         │         │      FastAPI MODULAR MONOLIT         │
 │ admin/buxg.  │         │         │  API Layer (REST + OpenAPI)          │
 ├──────────────┤         │         │  /sync /auth /catalog ...            │
 │ Desktop      │ HTTPS ──┼────────►│  DOMEN MODULLARI (11):               │
 │ (Tauri+React)│         │         │  catalog·orders·stock·finance·       │
 │ ofis         │         │         │  customers·delivery·attendance·      │
 ├──────────────┤         │         │  contracts·tickets·stats·promo       │
 │ Mobil Flutter│ HTTPS ──┘         │  Cross-cutting: Auth/RBAC·Audit·     │
 │ agent/kuryer/│   (+ sync)        │  i18n·Outbox-sync·File svc           │
 │ do'kon       │                   └──────┬──────────────────┬───────────┘
 │ OFFLINE-FIRST│                          │                  │
 │ SQLite+outbox│                  ┌────────┴───┐      ┌───────┴────────┐
 └──────┬───────┘                  │ PostgreSQL │      │   Redis        │
        │ GPS oqim                 │ PRIMARY    │      │ kesh·session·  │
        ▼                          │ + 2 READ   │      │ rate-limit·    │
 ┌──────────────┐                  │ REPLICA    │      │ pub/sub·queue  │
 │ GPS INGEST   │                  └────────────┘      └────────────────┘
 │ SERVIS       │                  ┌────────────┐      ┌────────────────┐
 ├──────────────┤                  │ TimescaleDB│      │ Object Storage │
 │ WORKER       │── push(FCM/APNs) │ (GPS izlar)│      │ (S3/MinIO)+CDN │
 │ report·sync  │                  └────────────┘      └────────────────┘
 └──────────────┘   Kengaytirish hook: didox · Click/Payme (Adapter interfeys)
```

### 3.3. Klient ilovalari — rol/modul xaritasi

| Klient | Texnologiya | Rollar | Asosiy modullar |
|---|---|---|---|
| **Veb SPA** | React + TypeScript + TanStack Query/Router | Administrator, Buxgalter | Katalog, Ombor, Buxgalteriya, Statistika, Shartnoma, Aksiya, Mijoz bazasi, RBAC, audit |
| **Desktop (Tauri)** | Veb SPA + Tauri (nativ printer/skaner/eksport) | Admin, Buxgalter, Ofis | Veb + nativ: faktura/yorliq bosish, USB skaner, Excel eksport, lokal kesh |
| **Mobil (Flutter)** | Flutter + Drift(SQLite) + offline outbox | Agent, Kuryer, Do'kon | Agent: GPS-xarita, buyurtma, davomat; Kuryer: yetkazish+trekking; Do'kon: katalog, buyurtma, qarz, murojaat |

> Veb va Desktop — **bir xil React kod bazasi**; Tauri faqat nativ qobiq (nativ funksiyalar feature-detection bilan o'raladi).

### 3.4. Ma'lumotlar qatlami — PostgreSQL sxema

Umumiy ustunlar: `id (UUID v7 — offline klient generatsiya qiladi, vaqt-tartibli)`, `created_at`, `updated_at`, `version (BIGINT — optimistic lock + LWW)`, `deleted_at (soft delete)`, kerakli joyda `branch_id`.

```sql
-- KATALOG
product(id, name_uz, name_ru, sku, barcode, mxik_code, unit, category_id,
        photo_url, is_active, branch_scope, version, ...)
price_segment(id, name)
product_price(id, product_id, segment_id, price, currency, valid_from, valid_to)
price_history(id, product_id, segment_id, old_price, new_price, changed_by, changed_at)  -- append-only
product_note(id, product_id, author_id, rating, comment, created_at)

-- MIJOZ (DO'KON)
store(id, name, inn, inps, owner_name, phone, gps_lat, gps_lng, address,
      segment_id, agent_id, branch_id, credit_limit, version, ...)

-- FOYDALANUVCHI / AGENT
app_user(id, full_name, phone, role, branch_id, password_hash, biometric_enrolled,
         device_id, locale, is_active, version)
agent_store(agent_id, store_id, assigned_at)

-- DAVOMAT
attendance(id, user_id, work_date, check_in_at, check_in_gps, check_out_at,
           check_out_gps, biometric_verified, source, version)

-- BUYURTMA
order(id, store_id, agent_id, mode, status, total_amount, currency, ordered_at,
      client_uuid, version, ...)   -- status: draft→confirmed→packed→delivering→delivered→canceled
order_line(id, order_id, product_id, qty, unit_price, segment_id, discount, line_total)
order_template(id, store_id, name, created_by)
order_template_line(id, template_id, product_id, qty)

-- YETKAZIB BERISH
delivery(id, order_id, courier_id, status, started_at, start_gps, delivered_at,
         delivery_gps, proof_photo_url, version)
delivery_track(id, delivery_id, gps_lat, gps_lng, recorded_at, speed)

-- OMBOR
stock_balance(id, product_id, warehouse_id, qty_on_hand, qty_reserved, version)
stock_movement(id, product_id, warehouse_id, type, qty, ref_type, ref_id,
               moved_by, moved_at, client_uuid)   -- APPEND-ONLY (real-time qoldiq)

-- BUXGALTERIYA
ledger_entry(id, store_id, type, amount, currency, ref_type, ref_id, entry_date,
             created_by, client_uuid)   -- APPEND-ONLY (event-sourced)
account_balance(id, store_id, balance, currency, last_recalc_at, version)  -- ledger'dan derivatsiya

-- SHARTNOMA / MUROJAAT / AKSIYA
contract(id, store_id, number, file_url, signed_at, valid_from, valid_to, status, version)
ticket(id, store_id, author_id, type, subject, body, status, assigned_to, version)
ticket_message(id, ticket_id, author_id, body, attachment_url, created_at)
promo(id, name_uz, name_ru, type, rule_json, banner_url, valid_from, valid_to,
      target_segment_id, is_active, version)

-- CROSS-CUTTING
audit_log(id, actor_id, action, entity_type, entity_id, before_json, after_json, ip, at)  -- append-only
outbox_event(id, aggregate_type, aggregate_id, event_type, payload, created_at, published_at)
```

- **GPS izlari → TimescaleDB** (hypertable + partitsiya + retention) — asosiy OLTP bazani GPS oqimidan himoya qiladi.
- **Redis:** katalog/narx/balans kesh, sessiya/refresh denylist, rate-limit, pub/sub (real-time qoldiq), navbat (worker broker), idempotentlik kaliti.
- **O'qish replikasi:** statistika/hisobot/katalog o'qish → replica; yozish va **moliyaviy o'qish → primary** (replikatsiya kechikishidan qochish).

### 3.5. Offline-first sinxronlash (mobil yadrosi)

**Tamoyil:** mobil ilova lokal SQLite (Drift) ustida ishlaydi; UI hech qachon to'g'ridan-to'g'ri tarmoqqa bog'liq emas.

**Yozish (klient→server) — Transactional Outbox:** harakat lokalga + outbox'ga `client_uuid` bilan yoziladi (bitta tranzaksiya) → `POST /sync/push` batch+tartiblangan → server idempotentlik tekshiradi, qo'llaydi, yangi `version` qaytaradi → klient outbox'ni tozalaydi.

**O'qish (server→klient) — Delta sync:** `GET /sync/pull?since=<cursor>` — `version`/`updated_at` kursori bo'yicha faqat foydalanuvchi doirasidagi o'zgargan yozuvlar.

**Konflikt yechimi (qatlamli, domen-aware — eng muhim qaror):**

| Ma'lumot tipi | Strategiya | Asos |
|---|---|---|
| **Moliyaviy** (ledger, ombor, buyurtma) | **APPEND-ONLY, konflikt yo'q** — balans/qoldiq hodisalardan qayta hisoblanadi | Pul/qoldiq yo'qolmaydi/ikkilanmaydi |
| **Holat o'tishlari** (buyurtma, yetkazish) | **Server-avtoritar holat mashinasi** | Noqonuniy holatning oldini oladi |
| **Profil maydonlari** (telefon, izoh) | **Maydon-darajali LWW** (`version`+`updated_at`) | Konflikt kam va kam zararli |
| **Master data** (katalog, narx, aksiya) | **Faqat server yozadi, klient read-only** | Konflikt imkonsiz |

**Offline keshlanadi:** biriktirilgan do'konlar, katalog+narx, aktiv aksiyalar, buyurtma shablonlari, do'kon balans snapshot. **Keshlanmaydi:** boshqa agentlar, to'liq buxgalteriya, statistika.
**Idempotentlik:** har bir mutatsiya `client_uuid` bilan — qayta yuborishda takrorlanmaydi.

### 3.6. RBAC — 5 rol × 11 modul matritsasi

Model: `Role → Permission (module:action)`, action ∈ `view|create|edit|delete|approve`; Redis'da keshlanadi; **qator-darajali himoya** (agent faqat o'z do'konlari, kuryer faqat o'z yetkazishlari).

| Modul | Administrator | Savdo agenti | Kuryer | Buxgalter | Do'kon |
|---|---|---|---|---|---|
| 1. Katalog | CRUD | view | view | view | view |
| 2. Agent kabineti | view | view+edit (o'zi) | — | view | — |
| 3. Davomat | view | create+view (o'zi) | create+view (o'zi) | view | — |
| 4. Yetkazib berish | view | view (o'z buyurtma) | create+edit (o'ziga) | view | view (o'ziniki) |
| 5. Ombor | CRUD | view | view (yuk) | view | — |
| 6. Buxgalteriya | view | view (o'z do'konlari) | — | **CRUD+approve** | view (o'z balansi) |
| 7. Murojaat | view+resolve | create+view | create+view | view+resolve | create+view (o'ziniki) |
| 8. Mijoz bazasi | CRUD | view+edit (o'z do'konlari) | view (manzil) | view | view+edit (o'ziniki) |
| 9. Statistika | view | view (o'z natijasi) | view (o'z yetkazishlari) | view (moliyaviy) | view (o'z xaridlari) |
| 10. Shartnoma | CRUD | view (o'z do'konlari) | — | view+edit | view (o'ziniki) |
| 11. Aksiya | CRUD | view | — | view | view |
| RBAC/Audit | **CRUD** | — | — | view (audit) | — |

### 3.7. GPS-trekking pipeline
- **Adaptiv chastota:** kuryer faol yetkazishda 30–60s (yoki 100m distance filter); agent ish kunida 2–5 daq (geofence); ish tashqarisida GPS o'chiq.
- **Maxfiylik:** GPS faqat ish vaqtida (`check_in`→`check_out`), consent bilan.
- **Saqlash:** lokal bufer → batch `POST /gps/ingest` → TimescaleDB.
- **Retention:** xom nuqtalar 90 kun → marshrut sifatida agregatlanadi.

### 3.8. Cross-cutting
- **Auth:** telefon+parol/OTP → JWT (access ~15min) + refresh (~30kun, rotatsiyali, Keychain/Keystore). Qurilma biometriyasi **lokal** — biometrik ma'lumot hech qachon serverga bormaydi. Davomat/yetkazish "Face ID" = lokal `biometric_verified=true` + GPS server tomonda (faktning isboti). Refresh rotatsiya + Redis denylist.
- **Audit:** har mutatsiya append-only `audit_log` (kim/nima/qachon/oldin-keyin); moliyaviy+RBAC majburiy; PII maskalangan.
- **i18n (uz/ru):** backend `message_key`, ikki tilli ustunlar (`name_uz/name_ru`), foydalanuvchi `locale`.
- **Kuzatuvchanlik:** strukturalangan JSON log (`correlation_id`), Prometheus, OpenTelemetry, Grafana + alert.
- **Xavfsizlik:** PII (INN/INPS/telefon) ustun-darajali shifrlash (pgcrypto/AES) + TLS; biometrik faqat qurilmada; secrets — Vault/env.

### 3.9. Integratsiya/kengaytirish nuqtalari
- **Shtrix-kod/MXIK:** mobil — kamera (ML Kit), desktop — USB skaner (Tauri); `barcode`/`mxik_code` indekslangan.
- **MXIK kelajak:** `FiscalAdapter` interfeysi (hozir `InternalNoOpAdapter`) → keyin `DidoxAdapter` (port/adapter).
- **To'lov kelajak:** `PaymentProvider` interfeysi (hozir `InternalLedgerProvider`) → keyin Click/Payme webhook.
- **Outbox → integratsiya:** server outbox hodisalari kelajak tashqi tizimlar (BI, soliq) uchun tayyor nuqta.

### 3.10. Deploy topologiyasi
```
Docker (Compose → keyin K8s):
  api ×3+ (stateless, HPA) · gps-ingest ×2 · worker ×2 (Arq/Celery)
  nginx/traefik (ingress, TLS, rate-limit)
  postgres-primary + 2 read-replica (streaming) · timescaledb · redis (Sentinel HA)
  minio/S3 (rasm/shartnoma/hisobot) + CDN
  prometheus + grafana + loki
Push: FCM + APNs (worker). CI/CD: GitHub Actions → build→test→SAST(Semgrep)/Trivy→deploy.
Backup: PITR, kunlik snapshot, audit log alohida arxiv.
```

---

## 4. OQIBATLAR (Trade-off'lar, Risklar)

**Ijobiy:** ACID moliyaviy izchillik; bitta React kod bazasi veb+desktop; append-only model offline'da pul yo'qotmaydi; OpenAPI kontrakti avtomatik klient generatsiya; GPS izolyatsiyasi.

**Salbiy/Trade-off:** modul chegarasi intizomi kerak (import-linter); Tauri Rust qatlami bilim talab qiladi; append-only ledger ko'proq saqlash (snapshot keshi bilan yumshatiladi); delta sync `version` kursorga tayanishi kerak (klient soatiga ishonmaslik).

| Risk | Ta'sir | Yumshatish |
|---|---|---|
| Offline konflikt → moliyaviy xato | Yuqori | Append-only ledger, `client_uuid` idempotentlik, server-avtoritar balans |
| Soat siljishi offline'da | O'rta | `version`/serial kursor, klient soatiga ishonmaslik |
| GPS batareya sarfi | O'rta | Adaptiv chastota, geofence, ish vaqti bilan cheklash |
| Modul chegarasi eroziyasi | O'rta | Import-linter, interfeys kontrakti, review |
| Replikatsiya kechikishi → eski moliyaviy o'qish | Yuqori | Moliyaviy o'qish faqat primary'dan |
| Biometrik PII chiqib ketishi | Kritik | Biometrik faqat qurilmada |
| Yirik sync batch → server yuki | O'rta | Batch limit, sahifalash, rate-limit, async ingest |

---

## 5. MODULLAR BOG'LIQLIK GRAFI + 4 BOSQICH

```
              ┌─────────────┐
              │ Auth/RBAC   │  ← poydevor
              │ + i18n      │
              └──────┬──────┘
       ┌────────────┼────────────────┐
       ▼            ▼                 ▼
   ┌────────┐  ┌──────────┐      ┌─────────┐
   │ Katalog│  │ Mijoz    │      │ Agent   │
   └───┬────┘  │ bazasi   │◄─────┤ kabineti│
       │       └────┬─────┘      └────┬────┘
       ▼            ▼                 ▼
   ┌──────────────────────┐     ┌──────────┐
   │  BUYURTMA (markaz)   │     │ Davomat  │
   └──┬─────────┬─────────┘     └────┬─────┘
      ▼         ▼                     ▼
  ┌────────┐ ┌─────────────┐    ┌──────────────┐
  │ Ombor  │ │ Buxgalteriya│◄───┤ Yetkazib     │
  └────────┘ └─────────────┘    │ berish(GPS)  │
                                └──────────────┘
  Mustaqil: Shartnoma, Murojaat, Aksiya, Statistika(o'qish)
```

**Buyurtma — markaziy tugun:** Ombor (chiqim) va Buxgalteriya (qarz)ni atomik harakatga keltiradi.

| Bosqich | Mazmun | Natija |
|---|---|---|
| **B1 — Poydevor** | Auth/RBAC, i18n, Katalog, Mijoz bazasi, foydalanuvchi/rol, veb SPA + Tauri skeleti, OpenAPI kontrakt | Admin katalog+do'konlarni boshqaradi; rollar ishlaydi |
| **B2 — Buyurtma yadrosi + Offline** | Buyurtma, Ombor (append-only), Buxgalteriya (ledger/qarz), Flutter offline-first + outbox sync, buyurtma shabloni | Agent offline buyurtma oladi, sinxronlanadi; qoldiq/qarz avtomatik |
| **B3 — Maydon operatsiyalari** | Davomat (Face ID), Yetkazish (Face ID→GPS→trek), GPS ingest + TimescaleDB, push, kuryer ilovasi | To'liq distribyutsiya zanjiri (RETAIL BOZOR) |
| **B4 — Qo'shimcha + qattiqlashtirish** | Statistika/hisobot, Shartnoma, Murojaat, Aksiya, audit UI, kuzatuvchanlik, masshtab testi, integratsiya hook'lari | Production-ready |

---

## XULOSA

**FastAPI modular monolit** (+ GPS-ingest va worker servislari), **React+TS veb SPA** (veb + Tauri-desktop), **Flutter offline-first** maydon ilovasi. Offline yadrosi — **transactional outbox + append-only moliyaviy hodisalar + domen-aware konflikt** (moliyaviy=konflikt yo'q, holat=server-avtoritar, profil=LWW, master data=read-only). Masshtab — gorizontal API replikalash + Redis + o'qish replikasi + TimescaleDB.

- **Planner uchun:** B1–B4 va bog'liqlik grafini DAG asosi qiling; Auth/RBAC + OpenAPI kontrakti — barcha ishning oldingi sharti.
- **Developer uchun:** modul chegaralarini interfeys orqali ushlang (cross-modul SQL yo'q); har mutatsiyaga `client_uuid` idempotentlik + `version` optimistik blok; moliyaviy jadvallar append-only.
