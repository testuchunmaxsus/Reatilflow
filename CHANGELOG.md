# CHANGELOG

Keep a Changelog formatida (https://keepachangelog.com/en/1.1.0/).
Versiyalash: Semantic Versioning (https://semver.org/).

---

## [0.33.0] - 2026-06-19 — Production-readiness: GPS filtri, seed, code-split, native paketlar

4 ta workstream va 2 ta gate-fix yakunlandi. Orkestrator gate **PASS** (backend 811, veb 117, mobil 128 test).

### Added

- **GPS ish-soati filtri (ADR §3.7, backend)** — `backend/app/modules/gps/service.py`:
  - GPS nuqtalar faqat foydalanuvchining aktiv davomat sessiyasi mavjud bo'lganda saqlanadi. Aktiv sessiya: `check_in_at <= server_now AND check_out_at IS NULL AND deleted_at IS NULL`.
  - Config flag: `gps_work_hours_filter_enabled` (default `True`). `False` da filtr o'chiriladi — barcha nuqtalar o'tkaziladi.
  - Cross-DB: attendance `oltp_db` (OLTP PostgreSQL) + GPS ingest `timescale_db` — birgalikda `ingest()` ga uzatiladi.
  - N+1 yo'q: attendance tekshiruvi batch boshida bitta `SELECT` bilan bajariladi; har nuqta uchun alohida so'rov yo'q.
  - Sessiya yo'q bo'lganda barcha nuqtalar jim tashlab yuboriladi (`rejected` hisoblagichiga qo'shiladi); klientga xato qaytarilmaydi (maxfiylik: shift oynasi oshkor qilinmaydi).
  - 9 yangi backend test. Backend jami: **811 test**.

- **`backend/scripts/seed.py`** — idempotent demo seed skripti:
  - Yaratadi: administrator (1), filial (2), kategoriya (4: 2 ildiz + 2 farzand), narx segmenti (2: chakana/ulgurji), mahsulot (8, MXIK + barcode bilan), do'kon (3), agent + kuryer + buxgalter; agent-do'kon biriktirishlari (2).
  - Idempotent: qayta ishga tushirilsa dublikat yaratmaydi (har yozuv `SELECT` → `INSERT` yoki o'tkazib yuborish).
  - Parol: `SEED_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` muhit o'zgaruvchisidan; o'rnatilmagan bo'lsa — dev-default ishlatiladi va konsol'da aniq `WARNING` chiqariladi. Production da `HECH QACHON` default parol bilan ishlatmaslik.
  - Ishga tushirish: `make seed` yoki `cd backend && python -m scripts.seed`.

- **`backend/alembic_timescale/`** — OLTP'dan mustaqil Alembic muhiti:
  - `TIMESCALE_URL` muhit o'zgaruvchisi orqali TimescaleDB ga ulangan alohida `env.py`, `alembic.ini`, `alembic_version_timescale` jadval (OLTP `alembic_version` bilan to'qnashmaydi).
  - `ts0001_gps_hypertable` — birinchi TimescaleDB migratsiyasi (hypertable va retention policy).
  - Ishga tushirish: `make migrate-timescale`.

- **Infra konfiguratsiya fayllari** (v0.33.0 da qo'shildi):
  - `infra/postgres/replica-setup.sh` — streaming replication avtomatlash skripti.
  - `infra/prometheus/rules/alerts.yml` — 12 Prometheus alert qoidasi.
  - `infra/minio/create-buckets.sh` — MinIO bucket yaratish skripti.
  - `prometheus.yml` da `rule_files` yoqildi (`alerts.yml` yuklash uchun).

### Changed

- **Veb: recharts code-split** — `web/src/features/stats/StatsDashboardPage.tsx`:
  - `React.lazy` + dinamik `import()` bilan lazy chunk: asosiy bundle `566 kB → 210 kB` (−63%); recharts alohida chunk sifatida faqat `/stats` sahifasida yuklanadi.
  - `vite.config.ts` `manualChunks`: `recharts` → alohida chunk.
  - `<Suspense fallback={<Loader />}>` grafik tarkibini o'rab turadi.

- **Veb: `@mantine/dates@7.17.8` React 18-mos `DateInput`** — Promo va Shartnoma forma modallarida `valid_from`/`valid_to` maydoni `TextInput` (YYYY-MM-DD) o'rniga `@mantine/dates@7.17.8` `DateInput` ga o'zgartirildi. Bu versiya React 18 bilan mos ishlaydi.

- **Mobil: stub → real native paketlar** (`mobile/pubspec.yaml`):
  - `local_auth` — biometrik autentifikatsiya (Face ID / Touch ID). AndroidManifest: `USE_BIOMETRIC` + `USE_FINGERPRINT`; Info.plist: `NSFaceIDUsageDescription`.
  - `geolocator` — GPS koordinatalar. AndroidManifest: `ACCESS_FINE_LOCATION` + `ACCESS_COARSE_LOCATION`; Info.plist: `NSLocationWhenInUseUsageDescription` + `NSLocationAlwaysAndWhenInUseUsageDescription`.
  - `image_picker` — proof_photo uchun kamera/galereya. AndroidManifest: `CAMERA`; Info.plist: `NSCameraUsageDescription` + `NSPhotoLibraryUsageDescription`.
  - `mobile_scanner` — barcode skaner. AndroidManifest: `CAMERA`; Info.plist: `NSCameraUsageDescription`.
  - `BiometricService`, `GpsService`, `DeliveryRepository.uploadProofPhoto()`, barcode scanner interfeyslari **o'zgarmagan** — stub dan real implementatsiyaga shaffof o'tish. 128 test o'zgarmasdan o'tadi. `flutter analyze` toza.

- **`backend/app/core/db.py` dialekt-aware engine** — `_make_engine(url)` yordamchi funksiya:
  - SQLite URL lari uchun `pool_size`/`max_overflow` argumentlari uzatilmaydi (SQLite `StaticPool`/`NullPool` bu parametrlarni qo'llab-quvvatlamaydi — `TypeError` beradi).
  - PostgreSQL/prod yo'li o'zgarmagan: to'liq pool sozlamalari (`pool_size=10`, `max_overflow=20`, `pool_pre_ping`, `pool_recycle=1800`).
  - Demo seed va test SQLite rejimida to'g'ri ishlashi ta'minlandi. 811 test buzilmadi.

### Fixed

- **Veb: UTC+5 off-by-one sana bug** — `web/src/utils/date.ts`:
  - `toLocalYMD(date)` — `Date` ob'ektidan mahalliy sana komponentlarini (`getFullYear`, `getMonth`, `getDate`) oladi; `toISOString()` dan foydalanish olib tashlandi (bu UTC vaqtini qaytaradi va UTC+5 muhitida yarim tunda oldingi kunga siljishi mumkin edi).
  - `parseYMD(str)` — YYYY-MM-DD satrini mahalliy sana sifatida tahlil qiladi; UTC tahlilidan qochish uchun `new Date(y, m, d)` shaklida.
  - Barcha `from`/`to` sana inputlari (Buyurtmalar, Statistika, Shartnomalar, Aksiyalar) shu yordamchi funksiyalar orqali normallashtirildi.

- **Mobil: `build_runner` `.g.dart` regen** — `image_picker`, `mobile_scanner` paketlari qo'shilgandan keyin `dart run build_runner build --delete-conflicting-outputs` qayta ishlatildi; barcha generated fayllar yangilandi.

### Test

| Komponent | Avvalgi | Joriy |
|---|---|---|
| Backend | 802 | **811** (+9, GPS ish-soati filtri) |
| Veb | 117 | **117** (o'zgarishsiz) |
| Mobil | 128 | **128** (o'zgarishsiz) |

---

## [0.32.0] - 2026-06-19 — Veb admin to'liq qoplash: Shartnoma/Murojaat/Aksiya

Veb admin paneliga uchta sahifa qo'shildi: Shartnoma, Murojaat, Aksiya. Veb endi backend'ning barcha 8 modulini qoplaydi. Orkestrator gate **PASS** (802 backend test, 117 veb test, tsc/build toza).

### Added (veb)

- **`web/src/features/contracts/`** — Shartnomalar boshqaruv moduli (`/contracts` route):
  - `ContractsListPage.tsx` — server-side paginated jadval (Mantine Table, horizontal scroll); filtrlar: `status` (`active` / `expiring` / `expired`) Select va "Tugayotgan" tez-murojaat tugmasi
  - `ContractFormModal.tsx` — yaratish va tahrirlash modali
  - `ContractFileUploadModal.tsx` — shartnoma faylini yuklash (`POST /contracts/{id}/file`, `apiClient.upload`)
  - Status DERIVED — backend hisoblaydi, UI faqat ko'rsatadi (badge rangi: `active`=green, `expiring`=orange, `expired`=red)
  - RBAC: `contracts:view` — sahifa; `contracts:create` — Yaratish tugmasi; `contracts:edit` — tahrirlash + fayl yuklash; `contracts:delete` — o'chirish (`ConfirmDeleteModal`)
  - i18n: uz/ru

- **`web/src/features/tickets/`** — Murojaatlar boshqaruv moduli (`/tickets` route):
  - `TicketsListPage.tsx` — server-side paginated jadval; filtrlar: `status` (new/in_progress/resolved/closed) va `ticket_type` (taklif/etiroz)
  - `TicketFormModal.tsx` — yangi murojaat yaratish modali
  - `TicketDetailModal.tsx` — detail modal: xabar tarixi ro'yxati + yangi xabar yuborish (`POST /tickets/{id}/messages`) + holat mashinasi (`PATCH /tickets/{id}/status`)
  - RBAC scope: admin/accountant barcha murojaatlarni ko'radi; boshqa rollar faqat o'zinikini (`tickets:view`)
  - RBAC: `tickets:create` — Yaratish tugmasi; `tickets:edit` — holat o'zgartirish
  - i18n: uz/ru

- **`web/src/features/promo/`** — Aksiyalar boshqaruv moduli (`/promo` route):
  - `PromoListPage.tsx` — server-side paginated jadval; filtrlar: `is_active` va `promo_type` (discount/bonus/gift); `rule_json` jadvalda ko'rsatiladi (`discount_percent` → `N%`, `discount_amount` → `N UZS`, `min_qty`)
  - `PromoFormModal.tsx` — yaratish va tahrirlash modali: `rule_json` (discount_percent/amount/min_qty), `target` (segment `Select` — `GET /catalog/price-segments`, product `Select` — `GET /catalog/products`), banner yuklash (`POST /promos/{id}/banner`), `is_active` checkbox, `valid_from`/`valid_to` (`TextInput`, YYYY-MM-DD format)
  - Discount server-avtoritar — UI hisob-kitob qilmaydi (`compute_line_discount()` backend tomonida)
  - RBAC: `promo:view` — sahifa; `promo:create` — Yaratish; `promo:edit` — tahrirlash; `promo:delete` — o'chirish
  - i18n: uz/ru

- **Routing va navigatsiya**: `/contracts`, `/tickets`, `/promo` routelari va mos navigatsiya menyusi elementlari qo'shildi
- **34 yangi veb test**. Jami veb test: **117**

### Notes

- **`@mantine/dates` muvofiqligi**: `@mantine/dates` v7.x React 19 talab qiladi; loyiha React 18 ishlatadi. Shu sababli sana inputlari `TextInput` (YYYY-MM-DD matn format) bilan amalga oshirildi. Kelajakda React 19 yoki `@mantine/dates@7.x` mos versiyasiga o'tilganda to'liq date picker komponentiga almashtirish mumkin.

### Tech-debt yopildi

- **Ixtiyoriy veb sahifalar (Shartnoma/Murojaat/Aksiya)**: veb admin panelining 6-7-8-modullari tayyor. Veb endi barcha 8 backend modulini qoplaydi.

---

## [0.31.0] - 2026-06-19 — Veb: Foydalanuvchilar boshqaruvi + activate endpoint

Veb admin paneliga Foydalanuvchilar boshqaruv sahifasi qo'shildi. Backend'ga `/users/{id}/activate` endpointi qo'shildi (deaktivatsiyaning simmetrik teskarisi). Orkestrator gate **PASS** (802 backend test, 83 veb test).

### Added (veb)

- **`web/src/features/users/`** — Foydalanuvchilar boshqaruv moduli (`/users` route):
  - `UsersListPage.tsx` — server-side paginated jadval (Mantine Table, horizontal scroll), server-side filtrlar: rol (`Select`, 5 variant) va holat (aktiv/nofaol), `PAGE_SIZE=20`
  - `UserFormModal.tsx` — foydalanuvchi yaratish va tahrirlash modali (to'liq maydonlar: `full_name`, `phone`, `role`, `password`, `branch_id`, `locale`, `biometric_enrolled`)
  - `AssignStoreModal.tsx` — agent → do'kon biriktirish: mavjud do'konlar `GET /customers/stores` orqali yuklanadi va `Select` komponentida tanlanadi (T8 xom-UUID `TextInput` kamchiligi tuzatildi)
  - Deaktivatsiya: `ConfirmDeleteModal` orqali tasdiqlash, `PATCH /users/{id}/deactivate`
  - Aktivlashtirish: to'g'ridan-to'g'ri `PATCH /users/{id}/activate` (tasdiqsiz, inline)
  - RBAC: `<Can permission="rbac:view">` — sahifa; `<Can permission="rbac:create">` — Yaratish tugmasi; `<Can permission="rbac:edit">` — tahrirlash, deaktivatsiya/aktivlashtirish, do'kon biriktirish
  - PII: telefon UI da maskalanadi — oxirgi 4 raqam ko'rsatiladi, qolganlari `*`
  - i18n: uz/ru, barcha matnlar tarjima kalitlari orqali
  - 14 yangi veb test. Jami veb test: **83**

### Added (backend)

- **`PATCH /users/{id}/activate`** (`backend/app/modules/users/router.py`) — deaktivatsiyaning simmetrik teskarisi:
  - `is_active=True` o'rnatiladi — ilgari bloklangan hisob qaytariladi
  - Faqat administrator (`require_permission(RBAC, EDIT)` + `_admin_only` ikki qatlamli himoya)
  - Audit log yozuvi + outbox event
  - 404: foydalanuvchi topilmasa
  - `service.activate_user()` biznes mantiqi
  - 2 yangi backend test. Jami backend test: **802**

### Fixed

- **T8 xom-UUID kamchiligi** — `AssignStoreModal` da agent → do'kon biriktirish ilgari `TextInput` (xom UUID kiritish) orqali amalga oshirilgan edi. Endi `GET /customers/stores` dan yuklab olingan do'konlar `Select` komponentida ko'rsatiladi — xato kiritmalar imkoni yo'q.
- **Reactivation bo'shlig'i yopildi** — ilgari deaktiv qilingan foydalanuvchi qaytarib aktivlashtirib bo'lmasdi (faqat `/deactivate` mavjud edi). Endi `/activate` endpointi orqali to'liq simmetrik tsikl: aktiv → deaktiv → aktiv.

### Tech-debt yopildi

- **Ixtiyoriy veb sahifalar — Foydalanuvchilar (Users)**: veb admin panelining 5-moduli tayyor. Qoldi: Shartnoma, Murojaat, Aksiya.

---

## [0.30.0] - 2026-06-19 — Append-only DB invariant (xavfsizlik hardening)

Moliyaviy append-only invariant DB darajasida majburlandi. Xavfsizlik/sifat darvozasi **PASS** (800 test, 8 yangi test).
**Production hardening — defense-in-depth: ilova kodi xato qilsa yoki to'g'ridan-to'g'ri SQL bajarilsa ham moliyaviy yaxlitlik DB tomonidan saqlanadi.**

### Added

- **`app/models/append_only.py`** — SQLAlchemy `event.listen(table, "after_create", DDL(...).execute_if(dialect=...))` orqali append-only triggerlar `Base.metadata.create_all` (test DB) va prod DB ikkalasida o'rnatiladi:
  - **SQLite**: `BEFORE UPDATE`/`BEFORE DELETE` triggerlar → `SELECT RAISE(ABORT, '... append-only ...')` — tranzaksiyani to'xtatadi.
  - **PostgreSQL**: `reject_append_only_mutation()` plpgsql funksiya (`RAISE EXCEPTION`, `CREATE OR REPLACE` — idempotent) + har jadval uchun `BEFORE UPDATE OR DELETE ... FOR EACH ROW` trigger.
  - Himoyalangan jadvallar: `ledger_entry`, `stock_movement` (faqat INSERT).
  - **Mutable (tegilmagan)**: `account_balance`, `stock_balance` — `version` optimistik lock bilan yangilanadi.
- **`app/models/__init__.py`** — `import app.models.append_only` (event'lar ro'yxatdan o'tishi uchun).
- **`backend/alembic/versions/0018_append_only_triggers.py`** — migratsiya `0018` (revises `0017`): PG funksiya + triggerlar, SQLite triggerlar; `upgrade()`/`downgrade()` idempotent (`DROP ... IF EXISTS`, `CREATE OR REPLACE`, `IF NOT EXISTS`).
- **`app/tests/test_append_only.py`** — 8 yangi test: `ledger_entry`/`stock_movement` INSERT muvaffaqiyatli; UPDATE/DELETE `sqlalchemy.exc.DatabaseError` ko'taradi; regressiya — `account_balance`/`stock_balance` hali ham mutable.

### Changed / Fixed

- **Migratsiya 0006 `DO INSTEAD NOTHING` RULE'lari almashtirildi** — bu PostgreSQL RULE'lar `ledger_entry`/`stock_movement` UPDATE/DELETE'ni **jim yutib** ketardi (tranzaksiya muvaffaqiyatli ko'rinardi, lekin o'zgarish saqlanmasdi — xato yashirin qolardi). Endi `RAISE EXCEPTION` triggerlar **baland ovozda rad etadi** — ilova xatoni ko'radi. Migratsiya 0018 eski RULE'larni o'chiradi.
- SQLite (test) muhitida ilgari bu jadvallarda hech qanday append-only cheklov yo'q edi; endi triggerlar bilan kuchaytirilgan. 792 mavjud test o'zgarmasdan o'tdi — invariant kod darajasida hech qachon buzilmagan.

### Tech-debt yopildi

- **DB append-only RLS/enforcement** — moliyaviy jadvallar uchun DB-darajali himoya.

---

## [0.29.0] - 2026-06-19 — Statistika SQL agregatsiya (production hardening)

Statistika moduli Python-tomon yig'ishdan DB darajali agregatsiyaga ko'chirildi. Xavfsizlik/sifat darvozasi **PASS** (792 test, 18 yangi test).
**Production hardening — stats masshtab hardening tayyor.**

### Changed

- **`app/modules/stats/service.py`** — savdo/yetkazish/moliyaviy statistika Python-tomon yig'ishdan (barcha qatorlarni xotiraga yuklash) DB darajasidagi agregatsiyaga ko'chirildi:
  - `sales_stats()` — `func.count()` + `func.coalesce(func.sum(Order.total_amount), 0)` bitta `SELECT` da jami; dinamika uchun `_period_label_expr()` → `GROUP BY period_expr ORDER BY period_expr` ikkinchi `SELECT` da. Barcha qatorlarni xotiraga yuklash bartaraf etildi.
  - `delivery_stats()` — bitta `SELECT` ichida barcha holat sanoqlari `func.sum(case(...))` orqali; `avg_delivery_minutes` ham shu `SELECT` da `func.avg(case(...))` — `started_at→delivered_at` oraliq, faqat `status='delivered'` qatorlar uchun.
  - `finance_stats()` — `LedgerEntry` `GROUP BY (store_id, type)` + `func.coalesce(func.sum(amount), 0)` bitta so'rovda barcha do'konlar uchun; Python da faqat guruhlovchi satrlar iterated (hajm: `N_stores × 2`).
  - Dialekt-aware sana guruhlash: SQLite `func.strftime('%Y-%m-%d'|'%Y-W%W'|'%Y-%m', col)`, PostgreSQL `func.to_char(col, 'YYYY-MM-DD'|'IYYY-"W"IW'|'YYYY-MM')` — `_get_dialect(db)` + `_period_label_expr(group_by, dialect)` orqali.
  - Avg yetkazish vaqti dialekt-agnostik: SQLite `(julianday(delivered_at) - julianday(started_at)) * 24 * 60`; PostgreSQL `EXTRACT(EPOCH FROM (delivered_at - started_at)) / 60`.
  - `NULL→0` barcha yig'indilar uchun `func.coalesce(..., 0)` bilan kafolatlangan.
  - Natija/JSON sxema o'zgarmagan (`SalesStatsOut`, `DeliveryStatsOut`, `FinanceStatsOut`); router, sxema va mavjud testlar o'zgarmagan.
  - Scope/IDOR izchil saqlangan: agent→o'z do'konlari, store→o'z, courier→bo'sh (sales/delivery), admin/accountant→branch_id filtr; `GET /stats/finance` courier uchun 403 (router darajasida).

### Added

- **`backend/alembic/versions/0017_stats_indexes.py`** — migratsiya `0017` (revises `0016`):
  - `ix_ledger_entry_store_date` — `ledger_entry (store_id, entry_date)` kompozit indeks. `finance_stats` `GROUP BY store_id, type` + `entry_date` range filtrida full-scan o'rniga indeks-scan.
  - `ix_delivery_assigned_at` — `delivery (assigned_at)` indeks. `delivery_stats` vaqt filtri (`assigned_at >= from_dt`) uchun.
  - Ikkala indeks model `__table_args__` ga ham qo'shilgan (`LedgerEntry`, `Delivery`) — `Base.metadata.create_all` (test DB) avtomatik oladi; migratsiya real PostgreSQL DB paritetini ta'minlaydi.
- **18 yangi test** (`backend/app/tests/stats/`) — SQL agregatsiya yo'llarini qamrab oladi: dialekt-moslik (SQLite path), `coalesce` NULL→0, dinamika `GROUP BY`, avg minutes `CASE WHEN`, scope filtrlari. Jami: **792 test**.

### Tech-debt yopildi

- **Stats DB GROUP BY** (`docs/FOUNDATION.md` tech-debt jadvalida rejalashtirilgan edi). Python-tomon `O(N)` yig'ish DB `O(1)` agregatga almashtirildi — million+ yozuvda xotira yuklamasi yo'q.

---

## [0.28.0] - 2026-06-19 — FCM/APNs HTTP push yetkazish (production hardening)

FCM va APNs HTTP push yetkazib berish to'liq implement qilindi. Xavfsizlik/sifat darvozasi **PASS** (774 test, 18 yangi test).
**Production hardening — push delivery qatlami tayyor.**

### Added

- **`app/modules/push/provider.py`** — push provider arxitekturasi:
  - `PushProvider` — abstrakt async interfeys (`send(device_token, title, body, data) -> PushResult`).
  - `PushResult` — natija dataclass (`ok`, `invalid_token`, `error`).
  - `FcmProvider` — FCM HTTP v1 (OAuth2 service-account JSON; `google-auth` bo'lsa ishlatiladi, yo'q bo'lsa `PyJWT + httpx` orqali qo'lda JWT RS256 imzolash). Legacy server-key (`FCM_SERVER_KEY`) backward-compat — Google 2024-yildan o'chirishni e'lon qildi, yangi loyihalar uchun v1 afzal. Token invalidatsiya: 404 + `UNREGISTERED`/`NOT_FOUND` → `invalid_token=True`.
  - `ApnsProvider` — APNs token-based JWT ES256, httpx HTTP/2 (`http2=True`, `h2` paketi talab qilinadi). JWT 45 daqiqa kesh (Apple talabi: 20–60 daqiqa oralig'ida yangilash), 10 daqiqa zaxira bilan. Token invalidatsiya: 410 yoki `BadDeviceToken`/`Unregistered`/`DeviceTokenNotForTopic` → `invalid_token=True`.
  - `FakePushProvider` — testlar uchun (tarmoq yo'q, `sent` ro'yxati, `set_fail_next`/`set_invalid_next`/`reset` yordamchi metodlar).
  - `get_push_provider()` — FCM factory: `APP_ENV=development` + FCM kredensial yo'q → `FakePushProvider`; production → `FcmProvider` (config asosida).
  - `get_apns_provider()` — APNs factory: config asosida `ApnsProvider`.
  - **Platform routing**: `service.py` da `device_id` `apns:` prefiksi bo'lsa → `ApnsProvider`, aks holda → `FcmProvider`.
  - **Token invalidatsiya oqimi**: `PushResult.invalid_token=True` → `app_user.device_id = NULL` + `push_log` yozuvi (append-only audit).
  - **PII-safe loglar**: device token log'ga `token[:8]***` shaklida maskalangan; `title`/`body` real provider log'iga tushirilmaydi.
  - **No-op xulq**: kredensial yo'q → `logger.warning` + `PushResult(ok=False)` — istisno tashlanmaydi, ilova buzilmaydi.

- **18 yangi test** (jami 774).

### Fixed

- **APNs `http2=False` → `http2=True`**: APNs HTTP/2 ni majburiy talab qiladi — HTTP/1.1 bilan ulanishni rad etadi. `httpx.AsyncClient(http2=True)` o'rnatildi.
- **`pyproject.toml` `httpx` → `httpx[http2]`**: APNs HTTP/2 uchun `h2` paketi talab qilinadi; `httpx[http2]` dependency sifatida qo'shildi.

### Tech-debt yopildi

- **FCM/APNs HTTP implementatsiyasi** (`docs/FOUNDATION.md` tech-debt jadvalida "FCM/APNs HTTP implementatsiya" sifatida belgilangan edi). Production push delivery tayyor.

---

## [0.27.0] - 2026-06-18 — CI/CD + Deploy konfiguratsiyasi (production hardening)

CI/CD pipeline va production deploy konfiguratsiyasi qurildi. Xavfsizlik/sifat darvozasi **PASS** (756 test, 2 HIGH build xatosi tuzatildi).
**Production hardening — CI/CD qatlami to'liq tayyor.**

### Added

- **GitHub Actions — 3 workflow** (`.github/workflows/`):
  - `backend.yml` — `lint (ruff+black)` → `pytest (756 test, SQLite mode)` → `SAST (Semgrep: p/python p/owasp-top-ten p/secrets)` → `Trivy fs (CRITICAL/HIGH)` → `docker-build + push ghcr.io` (faqat `main` branchda); `concurrency` cancel-in-progress.
  - `web.yml` — `tsc --noEmit` → `ESLint` → `vitest` → `build (Vite)` → `Trivy fs`; `web/**` o'zgarganda trigger.
  - `mobile.yml` — `flutter pub get` → `build_runner` → `flutter analyze` → `flutter test` → `Trivy fs`; `mobile/**` o'zgarganda trigger.

- **`docker-compose.prod.yml`** — production stack:
  - `api` (FastAPI, `/health` healthcheck), `gps-ingest`, `worker` — `ghcr.io` imagelari.
  - `nginx` — TLS termination, reverse proxy (`infra/nginx/nginx.prod.conf`).
  - `postgres-primary`, `postgres-replica` — PostgreSQL 16, streaming replication placeholder.
  - `timescaledb` — TimescaleDB 2.x (GPS hypertable izolyatsiyasi).
  - `redis` — Redis 7, AUTH paroli.
  - `minio` — MinIO, bucket yaratish birinchi deployda qo'lda.
  - `prometheus`, `grafana`, `loki`, `promtail` — observability stack.

- **`.env.prod.example`** — production muhit o'zgaruvchilari namunasi; barcha secrets uchun placeholder; git'ga commit qilinmaydigan `.env.prod` uchun asos.

- **`infra/`** — infra konfiguratsiya fayllari:
  - `infra/nginx/nginx.prod.conf` — HTTPS (443), HTTP→HTTPS redirect, `/api/` proxy, `/grafana/` sub-path, `/metrics` IP-whitelist namunasi.
  - `infra/nginx/certs/` — TLS sertifikat joyi (`.gitkeep`; haqiqiy sertifikat qo'lda qo'yiladi).
  - `infra/prometheus/prometheus.yml` — `retail-api`, `gps-ingest`, `worker` scrape konfiguratsiyasi.
  - `infra/grafana/` — provisioning: datasource (Prometheus, Loki), dashboard placeholder.
  - `infra/promtail/promtail.yml` — Docker container log yig'ish, Loki ga yuborish.

- **`backend/Dockerfile`** — multi-stage production image:
  - `builder` stage: `python:3.12-slim`, venv yaratish (`/opt/venv`), `pip install` (manba kodi yo'q).
  - `runtime` stage: non-root foydalanuvchi (`appuser:appuser`, UID 1001), `COPY --from=builder /opt/venv`, manba kodi ko'chirish, `PATH=/opt/venv/bin:$PATH`.
  - `HEALTHCHECK`: `curl -f http://localhost:8000/health`.
  - `uvicorn` `PATH`'da (venv `/opt/venv/bin`) — `CMD ["uvicorn", "app.main:app", ...]`.

- **`docs/DEPLOY.md`** — production runbook: secrets tayyorlash, TLS, migratsiya, MinIO bucket yaratish, sog'liq tekshiruvi, rollback, GitHub branch protection, SRE diqqat joylari.

- **`Makefile`** — yangi targetlar:
  - `make ci-backend` — ruff + black + pytest lokal (CI bilan bir xil).
  - `make ci-web` — tsc + eslint + vitest lokal.
  - `make ci-mobile` — flutter analyze + flutter test lokal.
  - `make deploy-up` — `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`.
  - `make deploy-migrate` — production migratsiyani ishga tushirish.

### Fixed

- **`pyproject.toml` build-backend (HIGH)**: `[build-system] build-backend` qiymati `setuptools.backends.legacy:build` edi — `pip install -e ".[dev]"` CI da `ModuleNotFoundError` bilan muvaffaqiyatsiz tugardi. Tuzatish: `setuptools.build_meta` ga o'zgartirildi (standart va to'g'ri qiymat).

- **`backend/Dockerfile` venv + PATH (HIGH)**: avvalgi Dockerfile `pip install -e .` (editable, venv yo'q) ishlatgan, `uvicorn` `CMD` da topilmasdi — konteyner start bo'lmasdi. Tuzatish: multi-stage venv (`/opt/venv`) + `PATH=/opt/venv/bin:$PATH`; manba kodi `builder`'dan emas, `runtime`'da alohida ko'chiriladi.

### Tech-debt yopildi

- CI/CD pipeline (GitHub Actions to'liq — backend/web/mobile).

---

## [0.26.0] - 2026-06-18 — T27: Observability (production hardening)

Observability moduli (T27) qurildi. Xavfsizlik/sifat darvozasi **PASS** (756 test).
**Production hardening boshlandi. Observability qatlami to'liq tayyor.**

### Added

- **Strukturalangan JSON logging** (`app/core/logging_config.py`):
  - Har log yozuvi JSON formatida: `timestamp` (ISO 8601 UTC), `level`, `logger`, `message`, `correlation_id`, va `extra` maydonlar.
  - `JsonFormatter` — `logging.Formatter` subklassi; `correlation_id_var` ContextVar'dan avtomatik o'qiydi.
  - PII maskalash: `inn`, `inps`, `phone`, `full_name`, `password`, `token`, `access_token`, `refresh_token`, `authorization`, `secret`, `api_key`, `jwt_secret_key`, `pii_encryption_key`, `blind_index_key` kalitlari `"***"` ga almashtiriladi.
  - `setup_logging(log_level)` — root logger JSON handler bilan sozlanadi; `uvicorn.access` o'chiriladi (middleware log yetarli); `sqlalchemy.engine` WARNING darajasida; `httpx`/`httpcore` WARNING darajasida.

- **`CorrelationIdMiddleware`** (`app/core/middleware.py`):
  - Har HTTP so'rovda `X-Request-ID` headeri tekshiriladi: kelsa — ishlatiladi, kelmasа — UUID v7 generatsiya qilinadi.
  - `correlation_id_var` (ContextVar) ga yoziladi — JSON logga avtomatik tushadi.
  - Javob headeriga `X-Request-ID` qo'shiladi.
  - So'rov boshi va oxirida `request_start` / `request_end` JSON log yoziladi (`http_method`, `http_path`, `http_status`, `duration_ms`).

- **Prometheus metrikalar** (`app/core/metrics.py`):
  - `http_requests_total{method, path, status}` — Counter.
  - `http_request_duration_seconds{method, path}` — Histogram (buckets: 5ms–10s).
  - `http_requests_in_progress{method, path}` — Gauge.
  - Biznes counterlar: `orders_created_total`, `auth_login_total{result}`, `sync_push_total`, `gps_ingest_total`.
  - `GET /metrics` endpointi (Prometheus text exposition format; `include_in_schema=False`).
  - `MetricsMiddleware` — `/metrics` yo'li o'zi kuzatilmaydi.

- **`MetricsMiddleware`** (`app/core/middleware.py`):
  - Har HTTP so'rovda Prometheus counterlar, histogram va gauge yangilanadi.
  - Kutilmagan exception da ham `status=500` bilan metrika yoziladi.

- **OpenTelemetry tracing** (`app/core/telemetry.py`):
  - `OTEL_EXPORTER_OTLP_ENDPOINT` ko'rsatilmasa — no-op (ilova ishlashda xato yo'q).
  - Ko'rsatilsa — `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-exporter-otlp-proto-http` orqali OTLP HTTP tracing yoqiladi.
  - `service.name = "retail-api"`, `BatchSpanProcessor`.
  - Paketlar topilmasa `ImportError` ushlanadi — no-op.

- **Sentry integratsiya** (`app/core/telemetry.py`):
  - `SENTRY_DSN` ko'rsatilmasa — no-op.
  - Ko'rsatilsa — `sentry_sdk.init(dsn=..., send_default_pii=False, traces_sample_rate=0.1)`.
  - `send_default_pii=False` — foydalanuvchi ma'lumotlari Sentry ga ketmaydi.
  - `sentry-sdk` paketi topilmasa `ImportError` ushlanadi — no-op.

- **Middleware tartibi** (`app/main.py`):
  - CORS → MetricsMiddleware → CorrelationIdMiddleware → LocaleMiddleware → endpoint.
  - Starlette LIFO: `add_middleware(LocaleMiddleware)`, `add_middleware(CorrelationIdMiddleware)`, `add_middleware(MetricsMiddleware)`.

- **756 test** — jami backend test soni.

### Tech-debt yopildi

- Prometheus/OTel/Sentry observability (`docs/FOUNDATION.md` tech-debt jadvalida `T27` sifatida rejalashtirilgan edi).

---

## [0.25.0] - 2026-06-18 — T20: Kuryer Flutter ilovasi — MAHSULOT FUNKSIONAL YAKUNLANDI

Kuryer Flutter ilovasi (T20) qurildi. Xavfsizlik/sifat darvozasi **PASS** (128 test, flutter analyze toza).
**MILESTONE: Butun RETAIL mahsuloti (backend B1-B4 + veb admin + mobil agent/kuryer) funksional yakunlandi.**

### Added

- **Kuryer dashboard ekrani** — faol yetkazishlar soni, bugungi yetkazilganlar soni, sync holati banneri; `BottomNavigationBar` navigatsiya (Dashboard / Yetkazishlar).

- **Yetkazishlar ro'yxati** — lokal Drift `deliveries` jadvalidan `watchAll()` / `watchActive()` stream; holat badge: `assigned` (kulrang), `started` (ko'k), `delivering` (to'q sariq), `delivered` (yashil), `failed` (qizil); real-time yangilanadi.

- **Yetkazish detali** — `watchById(id)` stream; joriy holat, manzil, mijoz nomi, tayinlangan vaqt, yetkazilgan vaqt; holat o'zgartirish tugmalari (`VALID_TRANSITIONS` bo'yicha faol).

- **Holat o'zgartirish (server-avtoritar VALID_TRANSITIONS, version lock)** — `DeliveryRepository.updateStatus()`: lokal Drift yangilash + `outbox_queue` ga `delivery.status_update` operatsiyasi BITTA tranzaksiyada; `version` optimistik lock payload da; server 422 qaytarsa `outbox.status='conflict'`; holat mashinasi: `assigned→{started,failed}`, `started→{delivering,failed}`, `delivering→{delivered,failed}`, `delivered/failed→{}` (terminal).

- **GPS tracking (45s faol yetkazishda)** — `DeliveryRepository.ingestGps()`: faqat `kGpsActiveStatuses = {started, delivering}` holatida outbox'ga `gps.ingest` yoziladi; `delivery_id` payload da; terminal holatga o'tgandan keyin GPS to'xtaydi (ADR §3.7).

- **proof_photo (dio multipart, 401-refresh)** — `DeliveryRepository.uploadProofPhoto()`: `POST /delivery/{id}/proof-photo` multipart so'rovi; `AuthInterceptor` orqali 401 kelganda token yangilanib so'rov qayta yuboriladi; `proof_photo_url` lokal bazada yangilanadi. Camera stub: `image_picker` paketi hozir yo'q (T20 qoida, izoh `delivery_repository.dart` da).

- **`deliveries` Drift jadvali + schemaVersion 2 migratsiya** — `DeliveriesTable` (8 ta jadval): `id`, `order_id`, `courier_id`, `status`, `address`, `customer_name`, `assigned_at`, `started_at`, `delivered_at`, `failure_reason`, `proof_photo_url`, `version`, `sync_status`, `created_at`, `updated_at`; `DeliveriesDao` (watchAll, watchActive, watchById, getById, countActive, upsert, updateStatus); `AppDatabase.schemaVersion = 2` + `onUpgrade` migratsiya.

- **128 test** (`mobile/test/`): T14 dan meros 29 + T21 qo'shilgan 42 + T20 qo'shilgan 57 test (kuryer dashboard, yetkazishlar ro'yxati/detali, holat mashinasi, GPS tracking `kGpsActiveStatuses` tekshiruvi, proof_photo multipart, `DeliveryRepository` stub, schemaVersion 2 migratsiya, `InvalidTransitionException`/`DeliveryNotFoundException`).

### Security

- **Holat mashinasi server-avtoritar**: `kValidTransitions` lokal tekshiruv klientda ham bajariladi (tez xato); lekin haqiqiy tasdiqlash server tomonida `VALID_TRANSITIONS` (`PATCH /delivery/{id}/status`); server 422 qaytarsa outbox `conflict` belgilanadi — klient soxta o'tishni yuklay olmaydi.
- **GPS faqat faol yetkazishda**: `ingestGps()` `kGpsActiveStatuses.contains(delivery.status)` tekshiruvi — terminal yoki `assigned` holatda GPS saqlanmaydi; ADR §3.7 talabi.
- **proof_photo AuthInterceptor refresh**: `uploadProofPhoto()` dio orqali yuboriladi; `AuthInterceptor` 401 kelganda `/auth/refresh` so'rov, asl so'rov 1 marta qayta yuboriladi — token eskirishi proof upload ni uzib qo'ymaydi.

### Known limitations

- Camera stub: `image_picker`/`camera` paketlari `pubspec.yaml` da yo'q; real qurilmada rasm tanlash uchun `image_picker: ^1.1.0` qo'shish kerak (izoh `delivery_repository.dart` `uploadProofPhoto()` da).
- `build_runner` `.g.dart` regen: `deliveries` jadvali qo'shilgandan keyin `dart run build_runner build --delete-conflicting-outputs` qayta ishlatilishi kerak.

---

## [0.24.0] - 2026-06-18 — T21: Agent Flutter ilovasi

Agent Flutter ilovasi qurildi. Xavfsizlik/sifat darvozasi **PASS** (71 test, flutter analyze toza).
**MILESTONE: Mobil — T14✅ T21✅. Agent ilovasi to'liq ishlaydigan holda tayyor.**

### Added

- **Agent dashboard ekrani** — sync holati, bugungi buyurtmalar soni, do'konlar soni; `BottomNavigationBar` navigatsiya (Dashboard / Do'konlar / Katalog / Buyurtmalar / Davomat).

- **Do'konlar ro'yxati va detali** — lokal Drift `stores` jadvalidan o'qiladi (agent-scope); qidiruv; `StoreDetailScreen` — do'kon ma'lumotlari, buyurtma yaratish tugmasi. Sinx orqali serverdan tortiladi.

- **Katalog (offline qidiruv)** — lokal Drift `products` jadvalidan real-time qidiruv (`watchProducts(query)`); offline holatda to'liq ishlaydi; barcode scanner keyingi sprint uchun placeholder.

- **Offline buyurtma yaratish** — `OrderRepository.createOrder()` (T14) ustiga qurilgan UI; mahsulot tanlash, miqdor kiritish, buyurtma tasdiqlash. Outbox payloadda `discount` va `unit_price` yo'q — narx server-avtoritar (T11/T25 naqshi).

- **Buyurtma ro'yxati** — `watchOrders()` Drift stream; `sync_status` badge: `pending` (sariq), `synced` (yashil), `error` (qizil); real-time yangilanadi.

- **Davomat ekrani (`AttendanceScreen`)** — `AttendanceRepository` orqali check-in/check-out:
  - `BiometricService` abstraktsiya — `local_auth` paketi orqali Face ID / Touch ID; biometrik ma'lumot serverga bormaydi, faqat `biometric_verified: true` bayroq.
  - `GpsService` abstraktsiya — `geolocator` paketi; joriy koordinata olish.
  - Check-in: biometrik tasdiqlangan bo'lsagina (`biometricVerified=true`) outbox'ga `attendance.check_in` operatsiya yoziladi.
  - Check-out: `attendance.check_out` outbox'ga yoziladi.
  - Xato holatlari: `BiometricRequiredException`, `AlreadyCheckedInException`, `NotCheckedInException`.

- **GPS tracking (`AttendanceRepository.ingestGps`)** — faqat `isCheckedIn=true` holatida (ADR §3.7 ish vaqti filtri); `gps.ingest` operatsiya outbox'ga yoziladi; check-out bo'lgandan keyin GPS to'xtatiladi.

- **71 test** (`mobile/test/`): T14 dan meros 29 test + T21 qo'shilgan 42 test (dashboard, do'konlar, katalog, buyurtma UI, davomat, GPS tracking, `BiometricService`/`GpsService` stub).

### Security

- **T11 narx himoyasi**: `outbox_queue` payloadida `discount` va `unit_price` maydonlari yo'q — narx va chegirma faqat backend `compute_line_discount()` tomonida hisoblanadi. Klient faqat `store_id`, `mode`, `currency`, `lines[]{product_id, qty}` yuboradi.
- **Biometrik qurilmada**: `local_auth` biometrik autentifikatsiyasi faqat qurilma darajasida bajariladi; serverga biometrik namuна yoki xesh bormaydi — faqat `biometric_verified: true` bayroq.
- **GPS faqat ish vaqtida**: `AttendanceRepository.ingestGps()` `isCheckedIn` tekshiruvi (ADR §3.7); check-out bo'lgandan keyin `ingestGps()` o'z-o'zidan qaytadi — GPS saqlanmaydi.

### Known limitations

- `local_auth` va `geolocator` production paketlari stub sifatida (`BiometricService`/`GpsService` abstraktsiya orqali); real qurilmada ishlatish uchun production implementation kerak (TODO).
- Barcode scanner placeholder — keyingi sprint.
- `AttendanceRepository._currentRecord` xotira holati — ilova qayta ishga tushirilganda yo'qoladi; SQLite persistence kelajak sprint uchun.

---

## [0.23.0] - 2026-06-18 — T14: Flutter offline-first yadrosi (Mobil boshlandi)

Flutter mobil ilovasining offline-first yadrosi qurildi. Xavfsizlik/sifat darvozasi **PASS** (29 test, flutter analyze toza).
**MILESTONE: Mobil boshlandi. T14 offline yadro tayyor.**

### Added

- **Flutter + Drift + dio + Riverpod + go_router skeleti** (`mobile/`):
  - Flutter `>=3.22.0`, Dart `>=3.4.0`
  - `drift ^2.18.0` — SQLite ORM (offline lokal baza)
  - `dio ^5.4.0` — HTTP klient (sync push/pull)
  - `flutter_riverpod ^2.5.0` + `riverpod_annotation ^2.3.0` — holat boshqaruvi
  - `go_router ^14.0.0` — deklarativ navigatsiya
  - `flutter_secure_storage ^9.0.0` — token xavfsiz saqlash
  - `connectivity_plus ^6.0.0` — tarmoq holati banneri
  - `uuid ^4.4.0` — `client_uuid` idempotentlik uchun

- **Drift 7-jadval** (`mobile/lib/data/local/`):
  - `products` — lokal katalog keshi (`id`, `name_uz`, `name_ru`, `sku`, `barcode`, `mxik_code`, `unit`, `category_id`, `photo_url`, `is_active`, `branch_scope`, `version`, `cached_at`)
  - `price_segments` — narx segmentlari keshi
  - `stores` — do'konlar keshi (`id`, `name`, `inn`, `phone`, `gps_lat`, `gps_lng`, `address`, `segment_id`, `agent_id`, `branch_id`, `credit_limit`, `version`, `cached_at`)
  - `orders` — lokal buyurtmalar (`id`, `store_id`, `agent_id`, `mode`, `status`, `total_amount`, `currency`, `ordered_at`, `client_uuid`, `server_id`, `sync_status`, `created_at`, `updated_at`)
  - `order_lines` — buyurtma qatorlari (`id`, `order_id`, `product_id`, `qty`, `unit_price`, `line_total`)
  - `outbox_queue` — yuborilishi kutilayotgan operatsiyalar (`id`, `op_type`, `client_uuid`, `payload` JSON, `status`, `attempts`, `response_data`, `created_at`)
  - `sync_cursors` — server delta kursori (`id`, `last_seq` — `GET /sync/pull?since=` parametri)

- **`SyncService`** (`mobile/lib/data/sync/sync_service.dart`):
  - **Push oqimi**: `outbox_queue.status='pending'` yozuvlarini max 50 li batch larda `POST /sync/push` ga yuboradi; har op natijasi: `applied` → outbox tozalanadi + `order.server_id` yangilanadi; `duplicate` → o'chiriladi (idempotent); `conflict` / `error` → status belgilanadi
  - **Pull oqimi**: `sync_cursors.last_seq` dan boshlab `GET /sync/pull?since={seq}` so'rovi; `changes[]` → entity_type bo'yicha (`product`, `catalog`, `store`, `order`) lokal Drift upsert; `next_cursor` saqlanadi; `has_more=true` bo'lsa sahifalar to'liq tortiladi
  - `sync()` — push + pull birgalikda; `SyncResult` qaytaradi: `success | partial | networkError | authError`

- **`OrderRepository`** (`mobile/lib/features/orders/order_repository.dart`) — atomik offline buyurtma:
  - `createOrder(storeId, agentId, lines, mode, currency)` — **BITTA TRANZAKSIYA** ichida: (1) `orders` ga yozadi, (2) `order_lines` ga yozadi, (3) `outbox_queue` ga `order.create` op qo'shadi; `CreateOrderResult(orderId, clientUuid)` qaytaradi
  - `getOrders()`, `getOrdersByStore(storeId)`, `getOrderLines(orderId)` — lokal o'qish
  - `watchOrders()`, `watchOrdersByStore(storeId)` — real-time Drift stream (UI reaktiv yangilanadi)

- **Auth** (`mobile/lib/data/remote/`):
  - `TokenStorage` abstraktsiya + `SecureTokenStorage` — iOS Keychain (`first_unlock_this_device`), Android EncryptedSharedPreferences
  - `AuthInterceptor` (dio) — har so'rovga `Authorization: Bearer <token>`; 401 kelganda `/auth/refresh` bilan yangi token, asl so'rov 1 marta qayta yuboriladi; parallel 401 larda bitta refresh (queue); refresh ham 401 bo'lsa `onLogout()` chaqiriladi

- **`ConnectivityBanner`** (`mobile/lib/features/home/connectivity_banner.dart`):
  - Offline bo'lganda ekran tepasida sariq banner ko'rsatiladi; UI hech qachon bloklanmaydi — lokal ma'lumotlar doim ko'rinadi

- **`AppConfig`** (`mobile/lib/core/config/app_config.dart`):
  - `API_BASE_URL` — `dart-define` orqali yetkaziladi (hardcode yo'q)

- **29 test** (`mobile/test/`): `SyncService` (push/pull oqimlari), `OrderRepository` (atomik tranzaksiya), `AuthInterceptor` (401→refresh oqimi), `TokenStorage`

### Security

- **Token saqlash**: `flutter_secure_storage` — iOS Keychain, Android Keystore (EncryptedSharedPreferences). Token hech qachon SharedPreferences yoki ochiq fayl tizimiga tushirilmaydi.
- **`client_uuid` idempotentlik**: har `order.create` operatsiyasi uchun UUID v4 generatsiya qilinadi; server `POST /sync/push` da `client_uuid` bo'yicha duplicate aniqlaydi — ikki marta yaratilmaydi.
- **`seq` kursor server-avtoritar**: `sync_cursors.last_seq` faqat server javobidagi `next_cursor` bilan yangilanadi; klient kursor qiymatini o'zi belgilay olmaydi.
- **API URL `dart-define`**: `API_BASE_URL` build vaqtida yetkaziladi — APK/IPA ichida hardcode yo'q.

---

## [0.22.0] - 2026-06-18 — Buyurtma + Statistika veb UI

Buyurtma va Statistika veb UI qurildi. Xavfsizlik/sifat darvozasi **PASS** (69 test, build toza).
**MILESTONE: Veb admin panelining 4 asosiy moduli (Katalog/Mijoz/Buyurtma/Statistika) tayyor.**

### Added

- **`web/src/features/orders/`** — Buyurtma moduli:
  - `OrderListPage.tsx` — buyurtmalar jadvali (raqam/sana/do'kon/rejim/status/summa); filtr: `status` Select, `from`/`to` sana; sahifalash (PAGE_SIZE=20); holat o'zgarganda sahifa 1 ga qaytadi
  - `components/OrderDetailModal.tsx` — buyurtma tafsilot modali; holat o'zgartirish (`VALID_TRANSITIONS` bo'yicha faol tugmalar); `useUpdateOrderStatus` mutation
  - `components/CreateOrderModal.tsx` — yangi buyurtma yaratish modali; `useCreateOrder` mutation
  - `components/OrderStatusBadge.tsx` — holat badge (Mantine `Badge`); har holat uchun rang: `confirmed`→blue, `packed`→yellow, `delivering`→orange, `delivered`→green, `canceled`→red
  - `api/ordersApi.ts` — TanStack Query hooks: `useOrders`, `useOrder`, `useCreateOrder`, `useUpdateOrderStatus`

- **`web/src/features/stats/`** — Statistika dashboard moduli:
  - `StatsDashboardPage.tsx` — savdo/yetkazish/moliyaviy bo'limlar; davr filtri (`from`/`to` date); `group_by` select (kun/hafta/oy)
  - Savdo bo'limi: `StatCard` (jami buyurtma, jami summa, davr); recharts `BarChart` (ikkita o'q — `count` chap, `amount` o'ng; `ResponsiveContainer` 260px)
  - Yetkazish bo'limi: 4 ta `StatCard` (jami/yetkazilgan/muvaffaqiyatsiz/jarayonda); `avg_delivery_minutes`; gorizontal `BarChart` taqsimot grafigi
  - Moliyaviy bo'lim: `<Can permission="finance:view">` ichida; jami debit/kredit/net_balance `StatCard`; do'kon darajasida jadval (nom, debit, kredit, balans, holat badge)
  - `api/statsApi.ts` — TanStack Query hooks: `useSalesStats`, `useDeliveryStats`, `useFinanceStats(params, enabled)`

- **69 test** (`web/src/__tests__/orders/`, `web/src/__tests__/stats/`), jami frontend: **69 test**

### Security

- **Narx server-avtoritar (T11 naqshi)**: `CreateOrderModal` da klient `discount` yoki `unit_price` kirmaydi — narx va chegirma faqat backend tomonida hisoblanadi (`compute_line_discount`, `product_price` jadvali). Klient faqat `store_id`, `lines[]{product_id, qty}` yuboradi.
- **Moliyaviy RBAC ikki qatlam**: `GET /stats/finance` router darajasida `finance:view` ruxsati (courier → 403). UI da `<Can permission="finance:view">` moliyaviy bo'limni yashiradi; `useFinanceStats` hook `enabled` parametri orqali faqat ruxsat bo'lsa so'rov yuboriladi (`enabled: canViewFinance`). Ikki qatlam: UI yashirish + query disable + backend 403.
- **Kuryer moliyaviy ko'rmaydi**: `courier` roli `finance:view` ruxsatiga ega emas — `<Can>` komponentida `fallback={null}`, `useFinanceStats(..., false)` so'rov umuman yuborilmaydi.

### Tech-debt

- **recharts bundle 993 kB**: `recharts` to'liq import qilinmoqda; `React.lazy` + dinamik `import()` bilan kod ajratish (code-splitting) kerak. Prioritet: keyingi sprint.

---

## [0.21.0] - 2026-06-18 — T8: Katalog + Mijoz veb UI

Katalog va Mijoz bazasi veb UI (T8) qurildi. Xavfsizlik/sifat darvozasi **PASS** (36 test, build toza).
**MILESTONE: Frontend T7✅ T8✅ yakunlandi.** Keyingi: Buyurtma/Statistika veb UI.

Orkestrator review tomonidan 1 ta MEDIUM topilma aniqlandi va tuzatildi:
1. `multipart/form-data` (rasm yuklash) so'rovlarda 401 kelganda `apiClient.get/post` oqimi ishlardi, lekin upload uchun alohida `fetch` chaqiruvi tokenni yangilagan so'ng qayta urinmasdi. Tuzatish: `apiClient.upload` metodi — mavjud refresh mutex oqimini meros oladi (401→refresh→retry).

### Added

- **`web/src/features/catalog/`** — Katalog moduli:
  - `CatalogListPage.tsx` — mahsulotlar jadvali (Mantine Table, scroll container); qidiruv (debounce 300ms); filtr: `is_active` checkbox, `category_id` select; sahifalash (Pagination, PAGE_SIZE=20); rasm thumbnail (36×36); lokalizatsiya (`name_uz`/`name_ru` `Accept-Language` bo'yicha); loading/empty/error holatlari
  - `components/ProductFormModal.tsx` — yaratish/tahrirlash modali; Mantine Form + Zod validatsiya; `name_uz`, `name_ru`, `sku`, `barcode`, `unit`, `price_segment_id`, `is_active` maydonlari; TanStack Query `useCreateProduct`/`useUpdateProduct` mutations
  - `components/PriceHistoryModal.tsx` — mahsulot narx tarixi modali; `usePriceHistory` hook; sanali narxlar jadvali (segment, `valid_from`, `valid_to`, summa)
  - `components/PhotoUploadModal.tsx` — rasm yuklash modali; `apiClient.upload` (multipart); JPEG/PNG/WebP; yuklash jarayonini ko'rsatish
  - `api/catalogApi.ts` — TanStack Query hooks: `useProducts`, `useCategories`, `useCreateProduct`, `useUpdateProduct`, `useDeleteProduct`, `usePriceHistory`

- **`web/src/features/customers/`** — Mijoz bazasi moduli:
  - `CustomersListPage.tsx` — do'konlar jadvali; 3-rejimli qidiruv (ism, INN, INPS) — backend blind-index orqali; agent biriktirish; PII yashirish: kuryer rolidagi foydalanuvchiga do'kon to'liq ma'lumoti (`StoreLimitedOut`) null sifatida ko'rsatiladi
  - `components/CustomerFormModal.tsx` — do'kon yaratish/tahrirlash modali; `store_id`, `name`, `inn`, `inps`, `credit_limit` maydonlari; Mantine Form
  - `components/AssignAgentModal.tsx` — agentni do'konga biriktirish modali; hozircha qo'lda UUID kiritish (T6 user-select qo'shilguncha); `useAssignAgent` mutation
  - `api/customersApi.ts` — TanStack Query hooks: `useCustomers`, `useCreateCustomer`, `useUpdateCustomer`, `useDeleteCustomer`, `useAssignAgent`

- **`web/src/api/client.ts`** — `apiClient.upload(path, formData)` metodi:
  - `multipart/form-data` so'rovlarini yuboradi
  - 401 kelganda mavjud refresh mutex orqali token yangilanadi, asl so'rov 1 marta qayta yuboriladi
  - Xato envelope `ApiError` sifatida qaytariladi (boshqa metodlar kabi)

- **`web/src/hooks/useApiError.ts`** — `useApiError()` hook:
  - `showError(err)` — `ApiError` yoki `Error` ni Mantine notification sifatida ko'rsatadi; `message_key` lokalizatsiyasi bilan (mavjud bo'lsa)

- **`web/src/hooks/useDebounce.ts`** — `useDebounce<T>(value, delay)` hook:
  - `delay` ms kutib qiymatni qaytaradi; qidiruv inputlari uchun (standart 300ms)

- **`web/src/components/ConfirmDeleteModal.tsx`** — qayta ishlatiladigan o'chirish tasdiqlash modali; `title`, `message`, `loading`, `onConfirm` proplari

- **RBAC-aware tugmalar**: `<Can permission="catalog:create/edit/delete">`, `<Can permission="customers:create/edit/delete">` — ruxsat yo'q bo'lsa tugmalar ko'rsatilmaydi

- **36 test** (`web/src/__tests__/catalog/`, `web/src/__tests__/customers/`), jami frontend: **36 test**

### Fixed

- **`apiClient.upload` — multipart 401→refresh oqimi (MEDIUM)**: rasm yuklashda (`POST /catalog/products/{id}/photo`) access token eskirgan bo'lsa `fetch` qayta urinmasdi. Tuzatish: `upload()` metodi `get/post/patch` metodlari bilan bir xil refresh mutex oqimini ishlatadi — token yangilanib, so'rov 1 marta avtomatik qayta yuboriladi.

### Security

- **PII yashirish (kuryer)**: `StoreLimitedOut` sxemasi bo'yicha kuryer rolidagi foydalanuvchiga do'kon to'liq ma'lumoti (INN, INPS, aloqa) UI da `null` sifatida ko'rsatiladi — backend `customers:view` ruxsati bo'lmagan rollar uchun cheklangan javob qaytaradi
- **RBAC-aware UI (UX)**: yaratish/tahrirlash/o'chirish tugmalari `<Can>` orqali faqat mos ruxsatga ega rollarga ko'rsatiladi; haqiqiy autorizatsiya backend RBAC middleware tomonida bajariladi

---

## [0.20.0] - 2026-06-18 — T7: Veb SPA poydevori (Frontend boshlandi)

Veb SPA skeleti (T7) qurildi. Xavfsizlik/sifat darvozasi **PASS** (14 test, build toza).
**MILESTONE: Frontend boshlandi.** Backend B1–B4✅; Frontend: T7✅ veb poydevor.

### Added

- **React + TypeScript + Vite + Mantine + TanStack + i18next + Tauri skeleti** (`web/`):
  - React 18, TypeScript 5.4, Vite 5.3 — SPA + Tauri desktop qobig'i bir kod bazasida
  - Mantine 7 (`@mantine/core`, `@mantine/hooks`, `@mantine/notifications`, `@mantine/form`) — UI komponent kutubxonasi
  - TanStack Query 5 — server state boshqaruvi (staleTime 5 daqiqa; 401/403 da qayta urinmaslik)
  - i18next 23 + react-i18next + i18next-browser-languagedetector — uz/ru lokalizatsiya
  - Vitest 1 + Testing Library — 14 test, coverage

- **`web/src/api/client.ts`** — typed API klient qatlami:
  - Har so'rovga `Authorization: Bearer <access_token>` va `Accept-Language` qo'shiladi
  - 401 → silent refresh: `/auth/refresh` bilan yangi token olinadi, asl so'rov 1 marta qayta yuboriladi
  - Refresh mutex — parallel 401 kelganda bitta refresh so'rovi (qolganlar natijani kutadi)
  - Refresh ham 401 bo'lsa → `retail:auth:logout` custom event yuboriladi
  - Xato envelope `{message_key, message, detail}` → `ApiError` (typed)
  - `apiClient.get/post/put/patch/delete` — typed HTTP metodlar

- **`web/src/auth/AuthContext.tsx`** — `AuthProvider` + `useAuth` hook:
  - `login(credentials)` → `/auth/login` → token saqlash → `/auth/me` yuklab olish
  - `logout()` → `/auth/logout` serverga xabar berish → tokenlarni tozalash
  - `refreshUser()` → `/auth/me` qayta yuklab olish
  - Silent restore: ilova ishga tushganda localStorage'da refresh token bo'lsa access token yangilanib sessiya tiklanadi
  - `user` holati: `null` (yuklanayapti) | `undefined` (login kerak) | `AuthUser` (kirgan)

- **`web/src/rbac/usePermissions.ts`** + **`web/src/rbac/Can.tsx`** — RBAC-aware UI:
  - `usePermissions()` → `{ role, permissions, can(permission), canAny(module, actions) }`
  - `<Can permission="catalog:create">...</Can>` — ruxsat bo'lmasa `fallback` yoki `null`
  - Sidebar nav elementlari `requiredPermission` bo'yicha filtrlanadi

- **`web/src/i18n/`** — uz/ru lokalizatsiya:
  - Standart til: `uz`; fallback: `uz`; saqlash: localStorage (`i18nextLng`)
  - `Accept-Language` API klient `getCurrentLocale()` orqali har so'rovga qo'shiladi
  - `LanguageSwitcher` — Mantine `Select` bilan til almashtirish

- **`web/src/layouts/AppLayout.tsx`** — Mantine AppShell:
  - Sidebar navigatsiya (ruxsatga qarab filtrlangan): Dashboard, Katalog, Mijozlar, Buyurtmalar, Statistika, Foydalanuvchilar, RBAC
  - Header: ilova nomi, `LanguageSwitcher`, `UserMenu` (logout)
  - Mobile burger menyusi (`useDisclosure`)

- **`web/src/main.tsx`** — yo'naltirish skeleti:
  - `/login` — ochiq sahifa (`LoginPage`)
  - `/*` — `ProtectedRoute` + `AppLayout`: Dashboard, Katalog, Mijozlar, Buyurtmalar, Statistika, Users, RBAC
  - Catalog/Mijozlar/Buyurtmalar/Statistika hozircha `PlaceholderPage` (T8 da to'liq)
  - Noma'lum yo'l → `/` ga yo'naltirish

- **`web/src/tauri.ts`** — Tauri ipc wrapper skeleti (desktop rejim uchun)

- **14 test** (`web/src/__tests__/`): `LoginPage`, `Can`, `usePermissions`

### Security

- **access_token xotirada (XSS-xavfsiz)**: `_accessToken` — modul darajasidagi o'zgaruvchi; localStorage/sessionStorage'ga YOZILMAYDI. XSS skriptlari tokenni o'g'irlay olmaydi.
- **refresh_token localStorage (tradeoff)**: Tauri desktop SPA uchun httpOnly cookie ishlatib bo'lmaydi (cross-origin/Tauri ipc); production veb deployda httpOnly cookie bilan almashtirish tavsiya etiladi. Bu ongli tradeoff — kod va hujjatda yozilgan.
- **RBAC-aware UI faqat UX**: `<Can>` va `usePermissions` faqat UI elementlarini yashiradi; haqiqiy autorizatsiya backend'da RBAC middleware tomonidan bajariladi.
- **Refresh mutex**: bir vaqtda bir nechta 401 da bitta `/auth/refresh` so'rovi yuboriladi — token race condition yo'q.

---

## [0.19.0] - 2026-06-18 — T22: Statistika (Stats) — Backend B1-B4 yakunlandi

Statistika moduli (T22) qurildi. Xavfsizlik/sifat darvozasi **PASS** (736/736 test).
**MILESTONE: Backend B1–B4 barcha vazifalari yakunlandi.** B1✅ B2✅ B3✅ B4✅.

### Added

- **`backend/app/modules/stats/router.py`** — statistika endpointlari (`/stats` prefiksi):
  - `GET /stats/sales` — savdo statistikasi (`stats:view`; barcha rollar); query parametrlari: `from` (ISO 8601), `to` (ISO 8601), `branch_id` (UUID), `group_by` (`day|week|month`); read replica ishlatiladi (ADR §3.4)
  - `GET /stats/delivery` — yetkazish statistikasi (`stats:view`; barcha rollar); query parametrlari: `from`, `to`, `courier_id` (UUID, admin uchun); read replica ishlatiladi
  - `GET /stats/finance` — moliyaviy statistika (`finance:view`; courier ko'ra olmaydi → 403); query parametrlari: `from`, `to`, `branch_id`; PRIMARY DB ishlatiladi (ADR §3.8 — moliyaviy aniqlik)
- **`backend/app/modules/stats/service.py`** — statistika biznes mantiq:
  - `sales_stats(db, user, from_dt, to_dt, branch_id, group_by)` — buyurtmalar bo'yicha saralash; group_by bo'yicha Python darajasida agregatsiya (kun/hafta/oy `SalesPeriodItem` ro'yxati); `stats.invalid_period` → 422; `stats.invalid_group_by` → 422
  - `delivery_stats(db, user, from_dt, to_dt, courier_id)` — yetkazishlar soni (jami/yetkazilgan/muvaffaqiyatsiz/jarayonda); `avg_delivery_minutes` — `started_at→delivered_at` oraliq, faqat `delivered` holat uchun, `Decimal` aniqlik
  - `finance_stats(db, user, from_dt, to_dt, branch_id)` — `LedgerEntry` + `AccountBalance` bo'yicha do'kon darajasida debit/kredit/balans; PRIMARY DB da chaqirilishi shart
  - `_get_agent_store_ids()` — agent uchun ruxsatli do'kon ID'larini qaytaradi (`AgentStore` + `Store.agent_id`)
  - `_get_store_id_for_store_user()` — store roli uchun bitta do'kon ID'si
  - `_format_period(dt, group_by)` — `"2026-06-01"` (kun), `"2026-W23"` (hafta), `"2026-06"` (oy)
- **`backend/app/modules/stats/schemas.py`** — Pydantic v2 sxemalari:
  - `SalesPeriodItem` — `period` (str), `order_count` (int), `total_amount` (Decimal)
  - `SalesStatsOut` — `total_orders`, `total_amount`, `currency`, `period_from`, `period_to`, `group_by`, `dynamics: list[SalesPeriodItem]`
  - `DeliveryStatsOut` — `total_deliveries`, `delivered_count`, `failed_count`, `in_progress_count`, `avg_delivery_minutes` (Decimal | None), `period_from`, `period_to`
  - `FinanceStoreItem` — `store_id`, `store_name`, `total_debit`, `total_credit`, `balance`, `currency`
  - `FinanceStatsOut` — `total_debit`, `total_credit`, `net_balance`, `stores: list[FinanceStoreItem]`, `period_from`, `period_to`
- **`app/modules/rbac/permissions.py`** — `Module.STATS` (`stats:view`) mavjud; `/stats/finance` uchun `Module.FINANCE` (`finance:view`) ishlatiladi — courier ruxsatsiz → 403
- **Yangi model yaratilmadi** — statistika faqat mavjud `Order`, `Delivery`, `LedgerEntry`, `AccountBalance` jadvallaridan o'qiydi; migratsiya yo'q
- **736 test** (`backend/app/tests/stats/`), jami: **736 test**

### Security

- **Scope/IDOR (sales)**: agent — faqat o'z do'konlari/buyurtmalari; store — faqat o'z do'konining buyurtmalari; courier — bo'sh javob (savdo ko'rinishi yo'q); admin/accountant — barchasi (`branch_id` bo'yicha ixtiyoriy filtr)
- **Scope/IDOR (delivery)**: courier — faqat o'z yetkazishlari (`Delivery.courier_id == user.id`); store — faqat o'z buyurtmalarining yetkazishlari (JOIN orqali); agent — o'z do'konlari buyurtmalarining yetkazishlari; admin/accountant — barchasi; `courier_id` filtri faqat admin/accountant uchun ishlaydi
- **Scope/IDOR (finance)**: `Module.FINANCE` → courier ruxsatga ega emas → 403 (router darajasida); agent — o'z do'konlari; store — faqat o'z balansi; admin/accountant — barchasi
- **Read replica vs Primary DB (ADR §3.8)**: `GET /stats/sales` va `GET /stats/delivery` — `get_db_replica` (non-financial); `GET /stats/finance` — `get_db` (primary, replikatsiya kechikishidan qochish)
- **Read-only**: statistika servisida hech qanday INSERT/UPDATE/DELETE yo'q — faqat SELECT

### Tech-debt

- **Stats Python agregatsiya → DB GROUP BY**: hozirgi implementatsiya barcha `Order`/`Delivery` yozuvlarini Python ga yuklab, Python darajasida agregatsiya qiladi. Yirik masshtabda (million+ yozuv) DB darajali `GROUP BY` / `DATE_TRUNC` afzal. Almashtirish: `_format_period()` o'rniga Postgres `DATE_TRUNC('day'/'week'/'month', ordered_at)` bilan `GROUP BY` so'rovi. SQLite moslik uchun `strftime` ishlatilishi kerak. Prioritet: production scale oldidan.

---

## [0.18.0] - 2026-06-18 — T25: Aksiya (Promo)

Aksiya (Promo) moduli (T25) qurildi. Xavfsizlik/sifat darvozasi **PASS** (701/701 test).
B4 (Statistika/Shartnoma/Murojaat/Aksiya) davom etmoqda — **T23✅ T24✅ T25✅**.

Orkestrator review tomonidan 1 ta MEDIUM topilma aniqlandi va tuzatildi:
1. `discount_percent` sxemada faqat `> 0` tekshirilgan edi, `<= 100` bo'lishi ham kerak edi. Tuzatish: `_validate_rule_json()` da `not (0 < pct <= 100)` koʻrsatkichi qo'shildi; `compute_line_discount()` da `discount = min(discount, line_gross)` cap — `line_total` hech qachon manfiy bo'lmaydi.

### Added

- **`app/modules/promo/router.py`** — aksiya endpointlari (`/promos` prefiksi):
  - `GET /promos` — paginated ro'yxat (`limit`, `offset`, `is_active`, `target_segment_id`, `target_product_id`, `promo_type` filtrlari; `promo:view`; barcha rollar)
  - `GET /promos/active` — hozir amal qiladigan aksiyalar (`is_active=True AND valid_from<=bugun<=valid_to`; `promo:view`; barcha rollar; `?at_date=YYYY-MM-DD` ixtiyoriy)
  - `POST /promos` — yangi aksiya yaratish (`promo:create`; faqat administrator); `client_uuid` idempotentlik; `valid_to >= valid_from` sana validatsiyasi; `rule_json` sxema validatsiyasi
  - `GET /promos/{id}` — bitta aksiya (`promo:view`; barcha rollar); topilmasa 404
  - `PATCH /promos/{id}` — qisman yangilash (`promo:edit`; faqat administrator); `version` optimistik lock; sana va `rule_json` validatsiyasi
  - `POST /promos/{id}/banner` — banner yuklash (`promo:edit`; faqat administrator); JPEG/PNG/WebP magic-byte validatsiya (storage darajasida); 5 MB chegara; `banner_url` yangilanadi
  - `DELETE /promos/{id}` — soft-delete (`promo:delete`; faqat administrator); `deleted_at` o'rnatiladi
- **`app/modules/promo/service.py`** — aksiya biznes mantiq:
  - `create_promo()` — admin scope; sana validatsiyasi; `promo_type` tekshiruvi; Redis idempotentlik (`idem:promo:create:{actor_id}:{client_uuid}`, TTL 24 soat); `IntegrityError` → rollback + mavjud qaytarish; audit + outbox
  - `get_promo()` — topilmasa 404; barcha rollar ko'ra oladi
  - `list_promos()` — paginated; `is_active`, `target_segment_id`, `target_product_id`, `promo_type` filtrlari; `created_at desc` tartib
  - `list_active_promos()` — `is_active=True AND valid_from<=at_date<=valid_to`; `valid_from asc` tartib; sync pull da global
  - `update_promo()` — admin scope; `version` optimistik lock → 409; faqat berilgan maydonlar yangilanadi; sana izchilligi yangilangandan keyin tekshiriladi; audit + outbox
  - `delete_promo()` — admin scope; soft-delete; audit + outbox
  - `update_banner()` — admin scope; `banner_url` + `version++` yangilash; audit + outbox
  - **`compute_line_discount()`** — SERVER-AVTORITAR chegirma (buyurtmaga ulangan); to'liq tavsif quyidagi Security bo'limida
- **`app/modules/promo/schemas.py`** — Pydantic v2 sxemalari:
  - `PromoCreate` — `name_uz`, `name_ru`, `promo_type` (`discount|bonus|gift`, default `discount`), `rule_json`, `banner_url` (ixtiyoriy), `valid_from`, `valid_to`, `target_segment_id` (NULL=barchasi), `target_product_id` (NULL=barchasi), `is_active` (default True), `branch_id`, `client_uuid`; `valid_to >= valid_from` model_validator; `_validate_rule_json()` model_validator
  - `PromoUpdate` — PATCH sxema; `version` majburiy; barcha maydonlar ixtiyoriy; sana va `rule_json` validatsiyasi
  - `PromoOut` — to'liq javob; `name` maydoni `Accept-Language` asosida lokalizatsiyalanadi (`name_uz` / `name_ru`)
  - `PaginatedPromos` — `items`, `total`, `limit`, `offset`
  - `_validate_rule_json()` — `discount_percent ∈ (0,100]` YOKI `discount_amount > 0`; ikkisi birga bo'lishi mumkin emas; `min_qty > 0` ixtiyoriy (MEDIUM tuzatish shu yerda)
- **`app/models/promo.py`** — `Promo` ORM modeli:
  - Ustunlar: `id` (UUID v7), `name_uz`/`name_ru` (VARCHAR 255), `promo_type` (VARCHAR 20, default `discount`), `rule_json` (JSON), `banner_url` (TEXT, NULL), `valid_from`/`valid_to` (DATE), `target_segment_id` (FK → price_segment, SET NULL, nullable), `target_product_id` (FK → product, SET NULL, nullable), `is_active` (BOOLEAN), `branch_id` (UUID, NULL), `client_uuid` (UUID, NULL), `version`, `created_at`, `updated_at`, `deleted_at`
  - Indekslar: `ix_promo_is_active`, `ix_promo_valid_from`, `ix_promo_valid_to`, `ix_promo_target_segment`, `ix_promo_target_product`
  - Idempotentlik: PostgreSQL `uq_promo_client_uuid_partial` (`client_uuid WHERE client_uuid IS NOT NULL`); SQLite `uq_promo_client_uuid` oddiy unique
- **`alembic/versions/0016_promo.py`** — migratsiya 0016: `promo` jadvali:
  - FK: `price_segment.id` (SET NULL), `product.id` (SET NULL) — segment/mahsulot o'chirilganda promo saqlanadi
  - Idempotentlik: PostgreSQL `uq_promo_client_uuid_partial` partial unique; SQLite oddiy unique
  - downgrade guard: `promo` da qatorlar bo'lsa `RuntimeError`
- **`app/modules/rbac/permissions.py`** — `Module.PROMO` (`promo:create`, `promo:view`, `promo:edit`, `promo:delete`)
- **701 test** (`backend/app/tests/promo/`), jami: **701 test**

### Fixed (orkestrator review)

- **`discount_percent` cap → (0,100] va `compute_line_discount` manfiy qarz himoyasi (MEDIUM)**:
  - `_validate_rule_json()` da `discount_percent` uchun `not (0 < pct <= 100)` tekshiruvi qo'shildi — avval faqat `> 0` edi, 150% ham qabul qilinar edi.
  - `compute_line_discount()` da `discount = min(discount, line_gross)` cap — `discount_percent=100` yoki yumaloqlash sababli `line_total < 0` bo'lishi imkonsiz. Xuddi shu cap `discount_amount` uchun ham qo'llanildi.

### Security

- **SERVER-AVTORITAR chegirma (`compute_line_discount`)**: chegirma faqat server tomonda hisoblanadi. Klient `OrderLineIn` sxemasida `discount` maydoni yo'q (schema darajasida himoya, T11 naqshi). `compute_line_discount(db, product_id, segment_id, qty, unit_price)` buyurtma `create_order()` ichida chaqiriladi. Algoritm:
  1. `is_active=True AND valid_from<=bugun<=valid_to AND promo_type='discount'` mos promo topiladi
  2. Ustuvorlik: `target_product_id NOT NULL` (aniq mahsulot) > `target_segment_id NOT NULL` (aniq segment) > global (ikkalasi NULL)
  3. `min_qty` tekshiruvi — miqdor yetarli bo'lmasa Decimal("0") qaytariladi
  4. `discount_percent`: `unit_price × qty × pct/100`, `min(discount, line_gross)` cap
  5. `discount_amount`: `min(amt, line_gross)` cap
  6. Mos promo yo'q yoki shartlar bajarilmasa → `Decimal("0")` (klient discount bera olmaydi)
- **`discount_percent ∈ (0,100]` sxema himoyasi**: `_validate_rule_json()` sxema va servis darajasida ikkita qatlamda tekshiriladi; 0 yoki 100 dan oshiq foiz rad etiladi
- **RBAC admin CRUD**: `POST/PATCH/DELETE /promos` va `POST /promos/{id}/banner` — faqat `administrator` roli; boshqa rol → 403. Barcha `GET` endpointlar `promo:view` — barcha autentifikatsiyalangan rollar
- **Banner magic-byte**: `storage.upload_product_photo()` mavjud validatsiya qayta ishlatiladi (JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `52 49 46 46`); Content-Type ga ishonilmaydi; 5 MB chegara
- **Idempotentlik**: Redis `SET NX ex` (TTL 24 soat) + DB `client_uuid` partial unique index — ikki qatlamli; `IntegrityError` ushlash + rollback + mavjud qaytarish (race condition himoyasi)
- **Sync (outbox)**: `promo.created/updated/deleted/banner_updated` hodisalari `outbox_event` ga yoziladi; sync pull da `promo` global — barcha autentifikatsiyalangan foydalanuvchilarga (katalog kabi)

---

## [0.17.0] - 2026-06-18 — T24: Murojaat (Tickets)

Murojaat moduli (T24) qurildi. Xavfsizlik/sifat darvozasi **PASS** (658/658 test).
B4 (Statistika/Shartnoma/Murojaat/Aksiya) davom etmoqda — **T23✅ T24✅**.

Orkestrator review tomonidan 1 ta MEDIUM topilma aniqlandi va tuzatildi:
1. `create_ticket()` da `client_uuid` UNIQUE constraint raqobati (race condition) `IntegrityError` sifatida tushardi — 500 qaytarar edi. Tuzatish: `IntegrityError` ushlash + rollback + mavjud ticketni qaytarish (idempotentlik kafolati).

### Added

- **`app/modules/tickets/router.py`** — murojaat endpointlari (`/tickets` prefiksi):
  - `GET /tickets` — paginated ro'yxat (`limit`, `offset`, `status`, `ticket_type`, `store_id` filtrlari; `tickets:view`; RBAC scope)
  - `POST /tickets` — yangi murojaat yaratish (`tickets:create`; administrator, agent, store, courier); `client_uuid` idempotentlik; `store_id=NULL` → xodim murojaati
  - `GET /tickets/{id}` — bitta murojaat xabarlar bilan (`tickets:view`; RBAC scope); scope tashqarisi → 404
  - `POST /tickets/{id}/messages` — murojaatga xabar qo'shish (`tickets:view`; murojaat ishtirokchilari yoki admin/buxgalter); `attachment_url` ixtiyoriy (storage'dan URL)
  - `PATCH /tickets/{id}/status` — holat o'zgartirish (`tickets:edit`; faqat administrator, accountant); server-avtoritar holat mashinasi; `version` optimistik lock
- **`app/modules/tickets/service.py`** — murojaat biznes mantiq:
  - `create_ticket()` — scope tekshiruvi (store/agent → o'z do'konlari); Redis idempotentlik (`idem:tickets:create:{actor_id}:{client_uuid}`, TTL 24 soat); `IntegrityError` → rollback + mavjud ticket qaytarish (MEDIUM tuzatildi); audit + outbox
  - `get_ticket()` — IDOR scope; topilmasa 404 (mavjudlikni oshkor qilmaslik)
  - `list_tickets()` — paginated; RBAC scope; `status`, `ticket_type`, `store_id` filtrlari
  - `add_message()` — scope tekshiruvi (`get_ticket()` orqali); `attachment_url` saqlanadi; `ticket.updated_at` yangilanadi; audit + outbox
  - `update_status()` — faqat admin/buxgalter; `is_valid_transition()` server-avtoritar; `version` optimistik lock → 409; audit + outbox
  - `_apply_ticket_scope()` — rol asosida WHERE: admin/buxgalter barchasi; agent → o'z do'konlari YOKI o'zi yaratgan; store → faqat o'z do'koni; courier → faqat o'zi yaratgan
- **`app/modules/tickets/schemas.py`** — Pydantic v2 sxemalari:
  - `TicketCreate` — `ticket_type` (`taklif|etiroz`), `subject` (≤255), `body`, `store_id` (ixtiyoriy; NULL=xodim murojaati), `client_uuid` (ixtiyoriy), `branch_id` (ixtiyoriy)
  - `TicketStatusUpdate` — `status` (`new|in_progress|resolved|closed`), `version` (optimistik lock uchun)
  - `TicketMessageCreate` — `body`, `attachment_url` (≤1024, ixtiyoriy)
  - `TicketMessageOut` — `id`, `ticket_id`, `author_id`, `body`, `attachment_url`, `created_at`
  - `TicketOut` — to'liq javob; `messages` ixtiyoriy (faqat `GET /tickets/{id}` da yuklangan); `from_orm_no_messages()` klassmetodi (lazy relationship greenlet xatosini oldini oladi)
  - `PaginatedTickets` — `items`, `total`, `limit`, `offset`
- **`app/models/ticket.py`** — `Ticket` va `TicketMessage` ORM modellari:
  - `Ticket` ustunlari: `id` (UUID v7), `store_id` (FK → store, SET NULL, nullable), `author_id` (FK → app_user, SET NULL), `assigned_to` (FK → app_user, SET NULL), `ticket_type` (VARCHAR 20), `subject` (VARCHAR 255), `body` (TEXT), `status` (VARCHAR 20, default `new`), `branch_id`, `client_uuid` (partial unique), `version`, `created_at`, `updated_at`, `deleted_at`
  - `TicketMessage` ustunlari: `id` (UUID v7), `ticket_id` (FK → ticket, CASCADE), `author_id` (FK → app_user, SET NULL), `body` (TEXT), `attachment_url` (VARCHAR 1024, NULL), `created_at`
  - `is_valid_transition(from, to)` funksiyasi — holat mashinasi mantiq: `new→in_progress`, `in_progress→resolved|closed`, `resolved→in_progress|closed`, `closed→{}` (terminal)
  - Indekslar: `ix_ticket_store_id`, `ix_ticket_author_id`, `ix_ticket_status`, `ix_ticket_message_ticket_id`
- **`alembic/versions/0015_ticket.py`** — migratsiya 0015: `ticket` va `ticket_message` jadvallari:
  - `ticket.client_uuid`: PostgreSQL partial unique `WHERE client_uuid IS NOT NULL`; SQLite oddiy unique
  - FK: `store.id` (SET NULL), `app_user.id` (SET NULL) — muallif o'chirilganda murojaat saqlanadi
  - `ticket_message.ticket_id`: CASCADE — murojaat o'chirilsa xabarlar ham o'chiriladi
  - downgrade guard: `ticket` da qatorlar bo'lsa `RuntimeError`
- **`app/modules/rbac/permissions.py`** — `Module.TICKETS` (`tickets:create`, `tickets:view`, `tickets:edit`)
- **658 test** (`backend/app/tests/tickets/`), jami: **658 test**

### Fixed (orkestrator review)

- **`create_ticket()` IntegrityError → idempotentlik (MEDIUM)**: `client_uuid` partial unique constraint raqobati (race condition) `IntegrityError` ga olib kelardi va 500 qaytarar edi. Tuzatish: `try/except IntegrityError` — `await db.rollback()` + mavjud `client_uuid` bo'yicha qidiruv + topilsa qaytarish. Redis idempotentlik qatlami birinchi himoya; DB unique constraint + `IntegrityError` ushlash ikkinchi himoya (race condition uchun).

### Security

- **Scope/IDOR (do'kon murojaati)**: `store` roli faqat `Store.user_id == current_user.id` bo'lgan do'kon murojaatlarini ko'radi va yarata oladi; boshqa do'kon murojaati → **404** (mavjudlikni oshkor qilmaslik)
- **Scope/IDOR (agent)**: agent `AgentStore` orqali biriktirilgan yoki `Store.agent_id` bo'lgan do'konlar murojaatlarini ko'radi + o'zi yaratgan (xodim) murojaatlarini ko'radi; boshqa → **404**
- **Holat o'zgartirish faqat admin/buxgalter**: `PATCH /tickets/{id}/status` — `tickets:edit` ruxsati + `update_status()` da qo'shimcha `user.role not in _RESOLVE_ROLES` tekshiruvi — ikki qatlamli himoya; boshqa rol → **403**
- **Xodim murojaati (store_id=None)**: `store_id` `None` bo'lsa do'kon scope tekshiruvi o'tkazib yuboriladi — admin/buxgalter/courier uchun xodim murojaati yaratish mumkin; `store` roli xodim murojaati yarata olmaydi (scope tekshiruvi `None` ga ham qo'llaniladi)
- **Idempotentlik (create_ticket)**: Redis `SET ex` + DB partial unique index — ikki qatlamli; race condition → `IntegrityError` ushlash + mavjud qaytarish (status 200, yangi yaratilmaydi)

---

## [0.16.0] - 2026-06-18 — T23: Shartnoma (Contracts)

Shartnoma moduli (T23) qurildi. Xavfsizlik/sifat darvozasi **PASS** (622/622 test).
B4 (Statistika/Shartnoma/Murojaat/Aksiya) boshlandi — **B4 davom etmoqda**.

### Added

- **`app/modules/contracts/router.py`** — shartnoma endpointlari (`/contracts` prefiksi):
  - `GET /contracts` — paginated ro'yxat (`limit`, `offset`, `store_id`, `status`, `valid_to_before`, `valid_to_after` filtrlari; `contracts:view`; RBAC scope)
  - `POST /contracts` — yangi shartnoma yaratish (`contracts:create`; administrator, accountant); `client_uuid` idempotentlik; `(store_id, number)` unikalligi; `valid_to >= valid_from` sana validatsiyasi
  - `GET /contracts/{id}` — bitta shartnoma (`contracts:view`; RBAC scope); scope tashqarisi → 404
  - `PATCH /contracts/{id}` — qisman yangilash (`contracts:edit`; administrator, accountant); `version` optimistik lock; sana validatsiyasi; number o'zgarganda unikalligi tekshiriladi
  - `POST /contracts/{id}/file` — PDF yoki rasm fayl yuklash (`contracts:edit`; administrator, accountant); magic-byte validatsiya (PDF `25 50 44 46`, JPEG, PNG, WebP); 20 MB chegara; `file_url` yangilanadi
  - `DELETE /contracts/{id}` — soft-delete (`contracts:delete`; faqat administrator); `deleted_at` o'rnatiladi
- **`app/modules/contracts/service.py`** — shartnoma biznes mantiq:
  - `create_contract()` — scope tekshiruvi; Redis idempotentlik (`idem:contracts:create:{actor_id}:{client_uuid}`, TTL 24 soat); `(store_id, number)` unikalligi; `begin_nested` + `IntegrityError` ikki qatlamli himoya; audit + outbox
  - `get_contract()` — IDOR scope; topilmasa 404 (mavjudlikni oshkor qilmaslik)
  - `list_contracts()` — paginated; RBAC scope; status filtri DB sana taqqoslash orqali (`valid_to` ga nisbatan); `valid_to_before`/`valid_to_after` qo'shimcha sana filtrlari
  - `update_contract()` — `version` optimistik lock; PATCH (faqat berilgan maydonlar); sana validatsiyasi; number unikalligi (o'zidan tashqari `exclude_id`); audit + outbox
  - `delete_contract()` — soft-delete; IDOR scope; audit + outbox
  - `update_contract_file()` — `file_url` yangilash; IDOR scope; audit + outbox
  - `list_expiring()` — `today <= valid_to <= today + days`; scope; worker/push notification uchun (kelajak)
- **`app/modules/contracts/schemas.py`** — Pydantic v2 sxemalari:
  - `ContractCreate` — `store_id`, `number`, `valid_from`, `valid_to`, `signed_at` (ixtiyoriy), `contract_type` (ixtiyoriy; `trade|employment|service|other`), `branch_id` (ixtiyoriy), `client_uuid` (ixtiyoriy); `valid_to >= valid_from` model_validator
  - `ContractUpdate` — kamida bitta maydon; `version` majburiy; `valid_to >= valid_from` model_validator
  - `ContractOut` — to'liq javob; `status` **DERIVED**: `valid_to < bugun → expired`, `valid_to - bugun <= 30 kun → expiring`, boshqa → `active`
  - `PaginatedContracts` — `items`, `total`, `limit`, `offset`
- **`alembic/versions/0014_contract.py`** — migratsiya 0014: `contract` jadvali:
  - Ustunlar: `id` (UUID v7), `store_id` (FK → store, RESTRICT), `number` (VARCHAR 100), `file_url` (VARCHAR 1024, NULL), `signed_at` (TIMESTAMPTZ, NULL), `valid_from` (DATE), `valid_to` (DATE), `contract_type` (VARCHAR 50, NULL), `branch_id` (UUID, NULL), `client_uuid` (UUID, NULL), `version`, `created_at`, `updated_at`, `deleted_at`
  - `uq_contract_store_number` — UNIQUE (`store_id`, `number`) `WHERE deleted_at IS NULL` (PostgreSQL partial unique); bir do'kon ichida raqam unikal
  - Indekslar: `ix_contract_store_id`, `ix_contract_valid_to`, `ix_contract_client_uuid`
  - downgrade guard: qatorlar bo'lsa `RuntimeError`
- **`app/modules/rbac/permissions.py`** — `Module.CONTRACTS` (mavjud; `contracts:create`, `contracts:edit`, `contracts:view`, `contracts:delete`)
- **622 test** (`backend/app/tests/contracts/`), jami: **622 test**

### Security

- **IDOR/scope**: agent faqat o'z do'konlariga biriktirilgan shartnomalarni ko'radi va yarata oladi; `store` roli faqat o'z do'konining shartnomalarini ko'radi; administrator va buxgalter barchani ko'radi. Scope tashqarisidagi shartnoma → **404** (mavjudlikni oshkor qilmaslik)
- **Raqam unikalligi (store darajasida)**: `(store_id, number)` partial unique DB indeksi + servis darajasida `_check_number_unique()` — ikki qatlamli himoya. `IntegrityError` ham ushlanadi (race condition)
- **Sana validatsiyasi**: `valid_to < valid_from` → 422; create va update ikkalasida ham tekshiriladi
- **Fayl magic-byte**: kontent-type headeriga ishonilmaydi; faylning birinchi baytlari tekshiriladi (PDF `%PDF`, JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `52 49 46 46`); SVG/HTML rad etiladi; 20 MB chegara
- **Optimistik lock**: `version` mos kelmasa → 409 (`contracts.version_conflict`); parallel PATCH konfliktini klient tomonida aniqlanadi

### Notes

- `list_expiring()` servis funksiyasi mavjud — worker/push notification integratsiyasi kelajak sprintda (B4 yoki alohida vazifa)
- Redis idempotentlik: `SET ex` (TTL bilan) ishlatilgan; `SET nx` (faqat yangi) emas — bu LOW cheklov sifatida qayd etildi (`docs/CONTRACTS.md`)
- `signed_at` null ga qaytarib o'rnatish (`null` → null) hozir qo'llab-quvvatlanmaydi — `ContractUpdate.signed_at` faqat yangi qiymat o'rnatadi; LOW cheklov

---

## [0.15.0] - 2026-06-18 — T19: Push bildirishnomalar (FCM/APNs)

Push bildirishnoma moduli (T19) qurildi. Xavfsizlik/sifat darvozasi **PASS** (578/578 test).
B3 (maydon operatsiyalari) ning oxirgi vazifasi — **B3 YAKUNLANDI**.

Orkestrator review tomonidan 2 ta muhim topilma aniqlandi va tuzatildi:
1. Push worker 100 hodisadan keyin to'xtab qolishi (stall) mumkin edi — `process_pending_pushes` faqat `published_at IS NULL` bo'yicha filtrlar edi; push consumer outbox'ni o'zgartirmaydi, shuning uchun bir xil 100 ta hodisa qayta-qayta olinib qolishi mumkin edi. Tuzatish: NOT EXISTS subquery filtri — `push_log` da hech qanday yozuvi yo'q hodisalar olinadi; har run yangi hodisalar `seq` bo'yicha oldinga suriladi. Alohida PASS 2 (retry): `status=failed AND attempts < MAX_RETRIES` bo'lgan yozuvlar uchun.
2. `db.rollback()` — `IntegrityError` yuz berganda butun sessiya rollback qilinar edi, boshqa push yozuvlari ham yo'qolar edi. Tuzatish: `begin_nested()` (SAVEPOINT) izolyatsiyasi — faqat muammoli INSERT rollback bo'ladi, sessiya va batch'dagi boshqa yozuvlar saqlanadi. T13/T18 naqshi.

### Added

- **`app/modules/push/service.py`** — `process_pending_pushes(db, provider, limit=100)`:
  - Sync'dan ALOHIDA consumer — `outbox.published_at` ga TEGMAYDI; `seq` kursori bilan to'qnashmaydi
  - PASS 1 (yangi hodisalar): NOT EXISTS subquery orqali `push_log` da hech qanday yozuvi yo'q outbox hodisalari — har run oldinga suriladi (stall yo'q)
  - PASS 2 (retry): `status=failed AND attempts < MAX_RETRIES` push_log yozuvlari — PASS 1 dan OLDIN yig'ilib, alohida qayta ishlanadi (shu runda yangi failed yozuvlar aralashmaydi)
  - Maqsad foydalanuvchilar: `order.status_updated` → do'kon egasi (`store.user_id`) + agent (`order.agent_id`); `delivery.created` / `delivery.status_updated` → kuryer (`delivery.courier_id`) + do'kon egasi
  - `device_id` yo'q → skip (log); `user` topilmasa → skip
  - `begin_nested()` SAVEPOINT — `IntegrityError` (race/duplicate) faqat shu INSERT ni rollback qiladi; sessiya tirik qoladi
  - Retry: 3 urinishgacha (`PUSH_MAX_RETRIES`); 3 dan keyin `failed` (manual tekshiruv kerak)
- **`app/modules/push/provider.py`** — `PushProvider` abstrakt interfeys:
  - `send(device_id, channel, title, body) -> bool`
  - `FcmProvider` — FCM (Firebase Cloud Messaging) production skelet; FCM v1 API (`httpx` TODO); `fcm_server_key` / `fcm_credentials` env orqali
  - `ApnsProvider` — APNs (Apple) production skelet; ES256 JWT (`httpx` TODO); `apns_key_id`, `apns_team_id`, `apns_bundle_id`, `apns_private_key_pem` env orqali
  - `FakePushProvider` — test uchun; yuborilgan pushlarni xotirada saqlaydi; `set_fail_next(n)` retry testi uchun
  - `get_push_provider()` factory — `APP_ENV=development` va FCM kaliti yo'qsa `FakePushProvider`; production da `FcmProvider`
- **`app/modules/push/router.py`** — push endpointlari (`/push` prefiksi):
  - `PATCH /push/device-token` — joriy foydalanuvchi o'z FCM/APNs `device_id` ni yangilaydi; IDOR himoyasi: faqat `current_user` (JWT) yangilanadi; `device_id=null` → o'chirish (push to'xtatiladi); barcha autentifikatsiyalangan rollar ruxsat etilgan
- **`app/modules/push/messages.py`** — i18n push matn katalogi:
  - `push.order_status_updated`, `push.delivery_created`, `push.delivery_status_updated`, `push.general` — uz/ru
  - `push_text(key, locale, **params) -> (title, body)` wrapper
- **`app/modules/push/worker.py`** — arq worker skelet:
  - `push_worker_task(ctx)` — arq davriy vazifasi; `process_pending_pushes()` chaqiradi
  - `WorkerSettings` — `on_startup` (DB sessiya factory + provider), `on_shutdown` (dispose); ishga tushirish: `arq app.modules.push.worker.WorkerSettings`
  - Poll intervali: `PUSH_POLL_INTERVAL = 30` soniya (default)
- **`app/models/push.py`** — `PushLog` ORM modeli:
  - Ustunlar: `id` (UUID v7), `outbox_event_id` (FK → outbox_event, CASCADE), `user_id` (FK → app_user, CASCADE), `device_id` (VARCHAR 512, NULL), `channel` (VARCHAR 10), `title`, `body`, `status` (`pending|sent|failed`), `attempts` (INTEGER), `last_error` (TEXT NULL), `created_at`, `sent_at` (NULL = yuborilmagan)
  - `uq_push_log_event_user` — UNIQUE (`outbox_event_id`, `user_id`) — idempotentlik
  - Indekslar: `ix_push_log_outbox_event_id`, `ix_push_log_user_id`, `ix_push_log_status`
- **`alembic/versions/0013_push_log.py`** — migratsiya 0013: `push_log` jadvali:
  - FK: `outbox_event.id` (CASCADE), `app_user.id` (CASCADE)
  - Idempotentlik: `uq_push_log_event_user` UNIQUE constraint
  - Postgres/SQLite cross-DB mosligi (`UUID` vs `String(36)`)
  - downgrade guard: qatorlar bo'lsa `RuntimeError`
- **578 test** (`backend/app/tests/push/`), jami: **578 test**

### Fixed (orkestrator review)

- **Push stall (NOT EXISTS filtr + alohida retry pass)**: push consumer `published_at` ga tegmasligi sababli bir xil hodisalar qayta-qayta olinib qolishi mumkin edi. Tuzatish: PASS 1 da `NOT EXISTS (SELECT 1 FROM push_log WHERE push_log.outbox_event_id = OutboxEvent.id)` — har run faqat yangi hodisalar; PASS 2 alohida `failed` loglarni retry qiladi. Progress kafolatlanadi (stall yo'q).
- **Savepoint izolyatsiya**: `IntegrityError` da `db.rollback()` butun sessiyani ifloslantirdi. Tuzatish: `begin_nested()` (SAVEPOINT) — faqat muammoli `push_log` INSERT rollback; boshqa yozuvlar saqlanadi.

---

## [0.14.0] - 2026-06-18 — T18: Yetkazib berish (Delivery)

Yetkazib berish moduli (T18) qurildi. Xavfsizlik/sifat darvozasi **PASS** (554/554 test).

Orkestrator review tomonidan 1 ta HIGH topilma aniqlandi va tuzatildi:
1. Bir buyurtmaga bir nechta aktiv yetkazish yaratilishi mumkin edi — `create_delivery()` da servis darajasida aktiv yetkazish tekshiruvi (`3c` qadam) qo'shildi; `IntegrityError` ushlash qo'shimcha himoya sifatida saqlanib qolindi; Postgres `uq_delivery_order_id_active_partial` partial unique index (`order_id WHERE status NOT IN ('delivered','failed') AND deleted_at IS NULL`) race condition uchun DB darajali ikkinchi himoya qatlami bo'lib xizmat qiladi.

### Added

- **`app/modules/delivery/router.py`** — yetkazish endpointlari (`/delivery` prefiksi):
  - `POST /delivery` — kuryer tayinlash (`delivery:create`; administrator, agent); `client_uuid` idempotentlik; boshlang'ich holat: `assigned`; buyurtma holati `confirmed|packed|delivering` bo'lishi shart
  - `PATCH /delivery/{id}/status` — holat o'zgartirish (`delivery:edit`; courier — faqat o'ziniki, administrator); holat mashinasi server-avtoritar; `version` optimistik lock
  - `POST /delivery/{id}/proof-photo` — dalil rasmi yuklash (`delivery:edit`; courier — faqat o'ziniki, administrator); magic-byte validatsiya (JPEG/PNG/WebP, 5 MB)
  - `GET /delivery` — paginated ro'yxat (`delivery:view`; RBAC scope); filtrlar: `status`, `courier_id`, `order_id`, `date_from`, `date_to`; javobda `gps_track_url`
  - `GET /delivery/{id}` — bitta yetkazish (`delivery:view`; RBAC scope); javobda `gps_track_url` → `GET /gps/track?delivery_id=...`
- **`app/modules/delivery/service.py`** — yetkazish biznes mantiq:
  - `create_delivery()` — idempotentlik (Redis SET NX + DB partial unique); buyurtma holati tekshiruvi; agent scope (cross-tenant IDOR); kuryer roli tekshiruvi; aktiv yetkazish tekshiruvi (bir buyurtmaga bitta aktiv); `begin_nested()` SAVEPOINT; audit + outbox
  - `update_status()` — `SELECT ... FOR UPDATE` (race guard); `VALID_TRANSITIONS` server-avtoritar holat mashinasi; GPS key nuqtalar: `started` → `start_gps_lat/lng`, `delivered` → `delivery_gps_lat/lng`; `version` optimistik lock; audit + outbox
  - `set_proof_photo()` — IDOR scope; `proof_photo_url` yangilash; audit
  - `get_delivery()` — IDOR scope; topilmasa 404
  - `list_deliveries()` — paginated; RBAC scope (courier: o'ziniki, agent/store: o'z buyurtmalari, admin/accountant: barchasi, branch_id filtr)
  - `_check_delivery_access()` — IDOR himoya; courier FAQAT o'ziga tayinlangan; agent/store buyurtma orqali scope tekshiruvi
- **`app/modules/delivery/schemas.py`** — Pydantic v2 sxemalari:
  - `DeliveryCreate` — `order_id`, `courier_id`, `client_uuid` (ixtiyoriy)
  - `DeliveryStatusUpdate` — `status`, `version` (optimistik lock), `gps_lat`/`gps_lng` (ixtiyoriy), `failure_reason` (ixtiyoriy)
  - `DeliveryOut` — to'liq javob (`gps_track_url` dinamik URL bilan)
  - `PaginatedDeliveries` — `items`, `total`, `limit`, `offset`
- **`app/models/delivery.py`** — `Delivery` ORM modeli:
  - Ustunlar: `id` (UUID v7), `order_id` (FK → order, RESTRICT), `courier_id` (FK → app_user, RESTRICT), `status` (VARCHAR 20), `assigned_at`, `started_at`, `delivered_at`, `start_gps_lat/lng` (NUMERIC(11,8)/(12,8)), `delivery_gps_lat/lng`, `proof_photo_url` (VARCHAR 1024), `failure_reason` (TEXT), `branch_id`, `client_uuid`, `version`, `created_at`, `updated_at`, `deleted_at`
  - `VALID_TRANSITIONS` konstantasi: `assigned→{started,failed}`, `started→{delivering,failed}`, `delivering→{delivered,failed}`, `delivered→{}` (terminal), `failed→{}` (terminal)
  - Indekslar: `ix_delivery_order_id`, `ix_delivery_courier_id`, `ix_delivery_status`, `uq_delivery_client_uuid`
- **`alembic/versions/0012_delivery.py`** — migratsiya 0012: `delivery` jadvali:
  - FK: `order.id` (RESTRICT), `app_user.id` (RESTRICT) — OLTP bog'lanishlar
  - Idempotentlik: PostgreSQL `uq_delivery_client_uuid_partial` (`client_uuid WHERE IS NOT NULL`); SQLite `uq_delivery_client_uuid` oddiy unique
  - Operatsion yaxlitlik: PostgreSQL `uq_delivery_order_id_active_partial` (`order_id WHERE status NOT IN ('delivered','failed') AND deleted_at IS NULL`) — race condition DB himoyasi
  - downgrade guard: qatorlar bo'lsa `RuntimeError`
  - Cross-DB FK YO'Q: `GpsPoint.delivery_id` faqat UUID reference (TimescaleDB alohida baza)
- **`app/modules/rbac/permissions.py`** — `Module.DELIVERY` qo'shildi (`delivery:create`, `delivery:edit`, `delivery:view`)
- **GPS bog'lanishi**: `delivery` jadvalida faqat key GPS nuqtalar (`start_gps_lat/lng`, `delivery_gps_lat/lng`); to'liq trek `GET /gps/track?delivery_id={id}` (TimescaleDB, GPS moduli; cross-DB FK yo'q); `DeliveryOut.gps_track_url` dinamik URL reference
- **554 test** (`backend/app/tests/delivery/`), jami: **554 test**

### Security

- **IDOR himoya (kuryer)**: kuryer faqat o'ziga tayinlangan yetkazishni o'zgartiradi yoki ko'radi; boshqa kuryerning `delivery_id` → **403** (`delivery.forbidden`). `update_status()` va `set_proof_photo()` da `_check_delivery_access()` + alohida `courier_id` tekshiruvi — ikki qatlamli himoya
- **Bir buyurtmaga bitta aktiv yetkazish**: servis darajasida `active_stmt` tekshiruvi (qadam 3c) + Postgres `uq_delivery_order_id_active_partial` partial unique index (race guard ikkinchi qatlam); terminal holatdan (delivered/failed) keyin qayta tayinlash mumkin
- **`version` + `FOR UPDATE` race himoya**: `update_status()` `SELECT ... FOR UPDATE` (DB seriallash) + `version` optimistik lock (klient konflikti aniqlanadi); ikkita parallel PATCH parallel oyna yo'q
- **Agent cross-tenant IDOR**: `create_delivery()` da agent faqat o'z do'konlari buyurtmalariga kuryer tayinlay oladi; boshqa do'kon buyurtmasi → **404** (`delivery.order_not_found`)
- **proof_photo magic-byte**: `storage.upload_product_photo()` mavjud validatsiya qayta ishlatiladi (JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `52 49 46 46`); SVG/HTML rad etiladi; kontent-type headeriga ishonilmaydi

---

## [0.13.0] - 2026-06-18 — T17: GPS Ingest (TimescaleDB)

GPS Ingest moduli (T17) qurildi. Xavfsizlik/sifat darvozasi **PASS** (513/513 test).

SRE tomonidan 3 ta HIGH topilma aniqlandi va tuzatildi:
1. TimescaleDB engine `primary_engine` dan alohida pool ochilmagan edi — `get_timescale_db` dependency `primary_engine` ga fallback qilardi; `timescale_engine` yaratildi (`settings.timescale_url` ga ulanadi, mustaqil pool).
2. `0011_gps` migratsiyasida `create_hypertable` chaqiruvi TimescaleDB extension mavjud bo'lmasa `500` bilan tushardi; `try/except` + `logger.warning` bilan ishlov berildi — extension topilmasa oddiy Postgres jadvali saqlanadi, ogohlantirish chiqariladi.
3. Retention policy (`add_retention_policy`) ham shu blokga kiritildi — extension yo'qligida jimgina o'tib ketmaslik uchun `logger.warning` qo'shildi.

### Added

- **`app/modules/gps/router.py`** — GPS endpointlari (`/gps` prefiksi):
  - `POST /gps/ingest` — batch GPS nuqtalarni yuklash (`gps:create`; agent, courier); `user_id` SERVER'dan (klient boshqa nomidan ingest qila olmaydi); `recorded_at` qurilma vaqti; batch limit 500; idempotentlik `(user_id, recorded_at)` ON CONFLICT DO NOTHING; rate-limit 600 so'rov/daqiqa
  - `GET /gps/track/{delivery_id}` — yetkazish marshrutini ko'rish (`gps:view`; agent, courier, administrator); paginated; IDOR himoya; rate-limit 120 so'rov/daqiqa
  - `GET /gps/track?user_id=&date=` — foydalanuvchi + sana bo'yicha marshrut (`gps:view`); `?date=` filtr range-based (TimescaleDB chunk pruning uchun); IDOR himoya; rate-limit 120 so'rov/daqiqa
- **`app/modules/gps/service.py`** — GPS biznes mantiq:
  - `ingest()` — `user_id` server'dan; `recorded_at` validatsiya (kelajak >5 daqiqa → reject; eski >30 kun → reject); PostgreSQL: `pg_insert().on_conflict_do_nothing()`; SQLite: `begin_nested()` savepoint; `IngestResult(accepted, rejected, duplicate)` qaytaradi; audit/outbox YO'Q (yuqori hajm — log/metrika)
  - `get_track()` — RBAC scope (agent/courier: faqat o'z nuqtalari; administrator: barchasi); `filter_date` range filter (TimescaleDB indeks va chunk pruning uchun `func.date()` ishlatilmaydi); paginated
- **`app/modules/gps/schemas.py`** — Pydantic v2 sxemalari:
  - `GpsPointIn` — `lat` (`Decimal`, `[-90, 90]`), `lng` (`Decimal`, `[-180, 180]`), `recorded_at` (qurilma vaqti), `speed` (m/s, `[0, 150]`, ixtiyoriy), `delivery_id` (UUID nullable)
  - `GpsBatchIngest` — `points: list[GpsPointIn]` (min 1)
  - `IngestResult` — `accepted`, `rejected`, `duplicate`
  - `GpsTrackOut` — to'liq nuqta javob sxemasi (`user_id`, `lat`, `lng`, `recorded_at`, `ingested_at`, ...)
  - `PaginatedTrack` — `items`, `total`, `limit`, `offset`
- **`app/models/gps.py`** — `GpsPoint` ORM modeli:
  - Ustunlar: `id` (UUID v7), `user_id` (NOT NULL, server'dan), `delivery_id` (nullable, T18 da FK), `lat` (NUMERIC(11,8)), `lng` (NUMERIC(12,8)), `recorded_at` (TIMESTAMPTZ, qurilma vaqti), `speed` (NUMERIC(8,3), nullable), `ingested_at` (TIMESTAMPTZ, server vaqti), `created_at` (TIMESTAMPTZ)
  - Indekslar: `ix_gps_point_user_recorded (user_id, recorded_at)`, `ix_gps_point_delivery_recorded (delivery_id, recorded_at)`
  - Idempotentlik: `uq_gps_point_user_recorded UNIQUE (user_id, recorded_at)`
- **`alembic/versions/0011_gps.py`** — migratsiya 0011: `gps_point` jadvali:
  - TimescaleDB `timescaledb` extension tekshiruvi; mavjud bo'lsa `create_hypertable('gps_point', 'recorded_at')` + `add_retention_policy('gps_point', INTERVAL '90 days')`; mavjud bo'lmasa `logger.warning` (oddiy Postgres jadvali)
  - Runbook: `TIMESCALE_URL=<ts_url> alembic upgrade 0011` (alohida TimescaleDB URL muhiti)
  - downgrade guard: `gps_point` da qatorlar bo'lsa `RuntimeError`
- **`app/core/db.py`** — `timescale_engine` (alohida pool, `settings.timescale_url`), `AsyncSessionTimescale`, `get_timescale_db` FastAPI dependency; `close_db_connections()` da dispose qo'shildi
- **`app/modules/rbac/permissions.py`** — `Module.GPS` qo'shildi (`gps:create`, `gps:view`)
- **513 test** (`backend/app/tests/gps/`), jami: **513 test**

### Security

- **IDOR himoya (user_id server'dan)**: `POST /gps/ingest` da `user_id` `current_user.id` dan olinadi — klient boshqa foydalanuvchi nomidan joylashuv yuklata olmaydi. Klient so'rovida `user_id` maydoni yo'q
- **IDOR himoya (track ko'rish)**: agent/courier boshqa `user_id` yoki boshqa delivery_id bo'yicha track so'rasa → **403** (`gps.forbidden_track`). Administrator istalgan foydalanuvchini ko'rishi mumkin
- **Joylashuv PII**: `GpsTrackOut` da `user_id` mavjud — GPS koordinatalar foydalanuvchiga bog'liq PII hisoblanadi. `gps:view` ruxsati faqat agent, courier, administrator da bor; do'kon va buxgalter GPS ko'rmaydi
- **recorded_at validatsiya**: kelajak (>5 daqiqa) yoki juda eski (>30 kun) vaqt rad etiladi — noto'g'ri qurilma soati yoki atakadan himoya

### Notes

- `alembic upgrade 0011` — TimescaleDB URL alohida `TIMESCALE_URL` env o'zgaruvchisidan olinishi kerak (OLTP URL emas). Runbook: `TIMESCALE_URL=postgresql+asyncpg://user:pass@timescaledb:5432/retail alembic upgrade 0011`. Bu infra konfiguratsiya kelajak sprintda avtomatlashtiriladi
- ADR §3.7 work-hours GPS filter (attendance shift oynasi bo'yicha GPS cheklash) hozir implement qilinmagan — TODO, kelajak sprint

---

## [0.12.0] - 2026-06-17 — T16: Davomat (Attendance)

Davomat moduli (T16) qurildi. Xavfsizlik/sifat darvozasi **PASS** (483/483 test).

SRE tomonidan 2 ta HIGH topilma aniqlandi va tuzatildi:
1. check-in parallel race `IntegrityError` → 500 edi; `IntegrityError` ushlanib → 409 qaytariladi.
2. `biometric_verified=false` tekshiruvi `try/except` blokiga tushib `fail-open` bo'lish xavfi bor edi; tekshiruv blokdan oldin `fail-closed` holatiga o'tkazildi.

### Added

- **`app/modules/attendance/router.py`** — davomat endpointlari (`/attendance` prefiksi):
  - `POST /attendance/check-in` — kirish qayd etish (`attendance:create`; agent, courier); `biometric_verified=true` MAJBURIY; vaqt SERVER tomonida belgilanadi; GPS klientdan qabul qilinadi; idempotentlik `client_uuid` orqali
  - `POST /attendance/check-out` — chiqish qayd etish (`attendance:create`; agent, courier); shu kunning ochiq davomatini yopadi; ochiq davomat yo'q → 404; GPS klientdan qabul qilinadi
  - `GET /attendance?user_id=&date=&limit=&offset=` — paginated davomat ro'yxati (`attendance:view`; agent/courier/administrator/accountant); IDOR himoya aktiv
- **`app/modules/attendance/service.py`** — biznes mantiq:
  - `check_in()` — biometric_verified tekshiruvi (fail-closed, blokdan birinchi); shu kun ochiq davomat tekshiruvi; `IntegrityError` → 409 (race himoya); Redis + DB ikki qatlamli idempotentlik; SERVER vaqti (`_now()`); audit + outbox
  - `check_out()` — ochiq davomatni topish → `check_out_at` + GPS yozish; Redis idempotentlik (check_out uchun alohida prefix); audit + outbox
  - `list_attendance()` — RBAC scope; agent/courier boshqa `user_id` so'rasa → 403 (IDOR); `check_in_at DESC` tartiblash
- **`app/modules/attendance/schemas.py`** — Pydantic v2 sxemalari:
  - `CheckInRequest` — `biometric_verified` (bool, majburiy), `gps_lat`/`gps_lng` (`Decimal(10,7)`, oraliq chegaralangan), `source` (`device_faceid|device_fingerprint`), `client_uuid` (ixtiyoriy)
  - `CheckOutRequest` — `gps_lat`/`gps_lng`, `client_uuid` (ixtiyoriy)
  - `AttendanceOut` — to'liq davomat javob sxemasi
  - `PaginatedAttendance` — `items`, `total`, `limit`, `offset`
- **`alembic/versions/0010_attendance.py`** — migratsiya 0010: `attendance` jadvali:
  - Ustunlar: `id` (UUID v7), `user_id` (FK → `app_user`, RESTRICT), `work_date` (DATE), `check_in_at` (TIMESTAMPTZ), `check_in_gps_lat/lng` (NUMERIC(10,7)), `check_out_at` (NULL = ochiq), `check_out_gps_lat/lng` (NULL), `biometric_verified` (BOOLEAN), `source` (VARCHAR(30)), `client_uuid` (UUID, NULL), `version`, `created_at`, `updated_at`, `deleted_at`
  - Oddiy indekslar: `ix_attendance_user_id`, `ix_attendance_work_date`, `ix_attendance_client_uuid`
  - Partial unique (PostgreSQL): `uq_attendance_user_date_open` — `(user_id, work_date) WHERE deleted_at IS NULL` (bir foydalanuvchi bir kunda bitta ochiq davomat); `uq_attendance_client_uuid` — `client_uuid WHERE IS NOT NULL`
  - SQLite (test): `BIGINT` + oddiy indeks (partial unique servis darajasida)
  - downgrade guard: qatorlar bo'lsa `RuntimeError`
- **Sync scope `attendance`**: outbox payload'da `user_id` mavjud — pull scope filtri uchun
- **483 test** (`backend/app/tests/attendance/`), jami: **483 test**

### Security

- **`biometric_verified=false` → 403 (fail-closed)**: biometric bayrog'i `false` bo'lsa check-in qat'iy rad etiladi. Maqsad: birovning qurilmasidan check-in oldini olish. Tekshiruv har qanday cache/idempotentlik blokidan OLDIN ishlaydi
- **IDOR himoya**: agent/courier boshqa foydalanuvchining `user_id` ni so'rasa → 403 (enumeration oldini olish); admin/accountant istalgan `user_id` ni ko'rishi mumkin
- **Server-avtoritar vaqt**: `check_in_at`, `check_out_at`, `work_date` — faqat `datetime.now(timezone.utc)` (klient qiymati qabul qilinmaydi; ADR §3.5)
- **Race condition → 409**: parallel ikki check-in `IntegrityError` ga olib kelsa → `await db.rollback()` + 409 (500 emas); SRE HIGH tuzatildi
- **Biometrik maʼlumot saqlanmaydi**: server faqat `biometric_verified` boolean bayrog'ini yozadi; yuz tasviri, barmoq izi yoki boshqa biometrik ma'lumot hech qachon serverga yuborilmaydi yoki saqlanmaydi (qurilma-lokal ishonch modeli)

---

## [0.11.0] - 2026-06-17 — T13: Outbox Sync API (offline-first)

Outbox Sync API (T13) qurildi. Xavfsizlik/sifat darvozasi **PASS** (452/452 test, gate iteratsiya 2).

### Added

- **`app/modules/sync/router.py`** — sync endpointlari (`/sync` prefiksi):
  - `POST /sync/push` — offline operatsiyalar batchi (klient→server); har op uchun alohida `applied|duplicate|conflict|error` natija; bitta op xato bo'lsa batch davom etadi; `client_uuid` idempotentlik kafolatlanadi; batch limit: 100 op
  - `GET /sync/pull?since=&limit=` — delta hodisalar (server→klient); `since` kursori server-avtoritar monoton `seq` (Postgres Sequence — klient soatiga ishonmaslik, ADR §3.5); `next_cursor`/`has_more` semantikasi; scope filtr (IDOR himoya); limit: 1–200, default 50
- **`app/modules/sync/service.py`** — sync biznes mantiq:
  - `push()` — op-darajali dispatch + SAVEPOINT izolyatsiyasi; har op `db.begin_nested()` (SAVEPOINT) ichida; bitta op rollback bo'lsa sessiya ifloslanmaydi; kengaytiriladigan `_OP_REGISTRY` (hozir: `order.create`)
  - `_handle_order_create()` — mavjud `create_order()` servisini qayta ishlatadi (atomiklik, narx server-avtoritarligi, idempotentlik meros oladi)
  - `pull()` — `OutboxEvent.seq > since_seq` delta fetch; scope filtr; batch snapshot fetch (N+1 yo'q: aggregate_type bo'yicha guruhlab `WHERE id IN (...)` so'rovi); kursor har vaqt ilgarilaydi (filtrlangan hodisalarda ham)
  - `_can_see_scoped_event()` — IDOR himoya: agent/store faqat o'z do'konlari; fail-safe deny (store_id payload'da yo'q bo'lsa ruxsat berilmaydi)
- **`app/modules/sync/schemas.py`** — Pydantic v2 sxemalari:
  - `SyncOp` — `op_type`, `client_uuid`, `payload` (dict)
  - `PushRequest` — `ops: list[SyncOp]` (min 1 element)
  - `OpResult` — `client_uuid`, `status`, `server_id` (applied bo'lganda), `message_key` (error/conflict bo'lganda)
  - `PushResponse` — `results: list[OpResult]`
  - `ChangeItem` — `entity_type`, `entity_id`, `event_type`, `seq`, `snapshot` (dict)
  - `PullResponse` — `changes`, `next_cursor`, `has_more`
- **`alembic/versions/0009_outbox_seq.py`** — migratsiya 0009: `outbox_event` jadvaliga `seq` (monoton kursor):
  - Postgres: `CREATE SEQUENCE outbox_event_seq` → `ADD COLUMN seq BIGINT NULL DEFAULT nextval(...)` → backfill (`UPDATE ... WHERE seq IS NULL`) → `SET NOT NULL` → `UNIQUE INDEX ix_outbox_event_seq` — xavfsiz multi-step (mavjud qatorlarda lock/backfill muammosi yo'q)
  - SQLite (test): `BIGINT` ustun + unique index (ORM counter orqali)
  - downgrade guard: `outbox_event` da qatorlar bo'lsa `RuntimeError` — kursor ma'lumotlari buzilmasin
- **Redis rate-limit** (`_check_rate_limit`): `INCR+EXPIRE` sodda token-bucket; push: 60 so'rov/60 s; pull: 120 so'rov/60 s; Redis xato bo'lsa graceful degradation (rate-limit o'tkazib yuboriladi)
- **452 test** (`backend/app/tests/sync/`), jami: **452 test**

### Security

- **Pull scope (IDOR)**: agent va store foydalanuvchilari faqat o'z do'konlariga tegishli `order`/`store`/`order_template` hodisalarini oladi; `product`/`price`/`promo`/`catalog` hodisalari global read-only (hammaga); moliyaviy va noma'lum aggregate_type — faqat administrator/accountant; noma'lum tip ham fail-safe deny
- **fail-safe deny**: `store_id` payload'da bo'lmasa yoki JSON parse xatosi bo'lsa — hodisa ko'rinmaydi (ruxsat berilmaydi, xato chiqarilmaydi)
- **Push avtorizatsiya**: `order.create` uchun `create_order()` orqali RBAC scope meros; sync modul o'z RBAC tekshiruvini qo'shmaydi — mavjud mexanizm qayta ishlatiladi
- **Rate-limit**: Redis counter `rate:{endpoint}:{user_id}` kaliti bilan; oshsa → 429 (`sync.rate_limited`)

---

## [0.10.0] - 2026-06-16 — T12: Buyurtma shabloni

Buyurtma shabloni (T12) qurildi. Xavfsizlik/sifat darvozasi **PASS** (428/428 test).

SRE tomonidan `op.get_bind()` haqida HIGH topilma aniqlandi — false-positive. Alembic async `run_sync` retseptida `op.get_bind()` to'g'ri ishlaydi; 0004–0007 migratsiyalarda ham xuddi shu naqsh ishlatilgan va production da sinovdan o'tgan.

### Added

- **`app/modules/orders/router.py`** — shablon endpointlari (`/orders/templates` prefiksi):
  - `POST /orders/templates` — yangi shablon yaratish (`orders:create`); faqat `product_id + qty` saqlanadi, narx SAQLANMAYDI
  - `GET /orders/templates` — paginated ro'yxat (`store_id` filtr; `orders:view` + RBAC scope)
  - `GET /orders/templates/{id}` — bitta shablon (`orders:view` + RBAC scope)
  - `DELETE /orders/templates/{id}` — soft-delete (`orders:edit`; `deleted_at` o'rnatiladi)
  - `POST /orders/templates/{id}/apply` — shablondan buyurtma yaratish (`orders:create`); mavjud `create_order` funksiyasini qayta ishlatadi — atomiklik, narx server-avtoritarligi va idempotentlik meros oladi
- **`app/modules/orders/schemas.py`** — yangi sxemalar:
  - `OrderTemplateLineIn` — `product_id`, `qty` (Decimal, musbat); narx maydoni YO'Q
  - `OrderTemplateCreate` — `store_id`, `name`, `lines`, `client_uuid`
  - `OrderTemplateLineOut` — shablon qatori javob sxemasi (faqat `product_id`, `qty`)
  - `OrderTemplateOut` — to'liq shablon javob sxemasi
  - `ApplyTemplateIn` — apply so'rovi: `mode`, `currency`, `client_uuid`, `warehouse_id`
  - `PaginatedTemplates` — `items`, `total`, `limit`, `offset`
- **`app/modules/orders/service.py`** — shablon biznes mantiq:
  - `create_template` — shablon + qatorlar INSERT; RBAC scope tekshiruvi (agent faqat o'z do'konlariga)
  - `get_template` — RBAC scope (`_check_template_access`); ruxsatsiz → 404 (IDOR)
  - `list_templates` — paginated, `store_id` filtr, RBAC scope
  - `delete_template` — soft-delete; RBAC scope
  - `apply_template` — shablon qatorlaridan `OrderCreate` tuzib `create_order` ga uzatadi; narx `apply` paytida katalogdan (server-avtoritar); shablon o'zgarmaydi
- **`alembic/versions/0008_order_templates.py`** — migratsiya 0008: 2 jadval:
  - `order_template` — shablon bosh yozuvi (`store_id`, `name`, `created_by`, soft-delete)
  - `order_template_line` — shablon qatorlari (`template_id`, `product_id`, `qty`; `unit_price` YO'Q)
  - `ix_order_template_store_id` — store bo'yicha qidiruv indeksi
  - `ix_order_template_line_template_id` — join indeksi
  - downgrade guard: jadvallarda qatorlar bo'lsa `RuntimeError` (T5 naqshi)
- **`app/modules/rbac/permissions.py`** — `Module.ORDERS` ga `templates` ruxsatlari qo'shildi
- **23 yangi shablon testi** (`backend/app/tests/orders/`), jami: **428 test**

### Security

- **Shablon narx SAQLAMAYDI**: `order_template_line` jadvalida `unit_price` ustuni yo'q; `OrderTemplateLineIn` sxemasida narx, segment, chegirma maydonlari mavjud emas — klient narx qo'sha olmaydi va saqlangan narxni manipulyatsiya qila olmaydi
- **Narx faqat `apply` paytida**: `apply_template` → `create_order` zanjiri orqali narx har safar katalog + do'kon segmentidan server tomonida olinadi; eski narx ishlatilmaydi
- **IDOR scope**: `get_template` va `delete_template` — ruxsatsiz shablon 404 qaytaradi (mavjudlikni oshkor qilmaslik); `list_templates` — rol asosida WHERE sharti
- **Atomiklik meros**: apply `create_order` ni qayta ishlatadi — ombor chiqimi + ledger debit + idempotentlik kafolati meros oladi; alohida kod yo'q

---

## [0.9.0] - 2026-06-16 — T11: Buyurtma yadrosi (atomik tranzaksiya)

Buyurtma yadrosi (T11) qurildi. Xavfsizlik/sifat darvozasi **PASS** (405/405 test, gate iteratsiya 3).

### Added

- **`app/modules/orders/router.py`** — buyurtma endpointlari (`/orders` prefiksi):
  - `POST /orders` — yangi buyurtma yaratish (`orders:create`); ATOMIK tranzaksiya (order + order_line + ombor chiqimi + qarz — bitta ACID); qoldiq yetmasa → 409 BUTUN rollback
  - `GET /orders` — paginated ro'yxat (`store_id`, `agent_id`, `status`, `date_from`, `date_to` filtrlari; `orders:view` + RBAC scope)
  - `GET /orders/{id}` — bitta buyurtma (`orders:view` + RBAC scope)
  - `PATCH /orders/{id}/status` — holat o'zgartirish (`orders:edit`); server-avtoritar holat mashinasi; noqonuniy o'tish → 422; `version` optimistik lock → 409
- **`app/modules/orders/schemas.py`** — Pydantic v2 sxemalari:
  - `OrderLineIn` — `product_id`, `qty` (Decimal, musbat); `unit_price`/`segment_id`/`discount` OLIB TASHLANGAN (narx manipulyatsiyasi yo'li yopildi)
  - `OrderCreate` — `store_id`, `mode` (`bozor|oddiy`), `lines`, `client_uuid`, `currency`, `warehouse_id`
  - `OrderLineOut` — qator javob sxemasi (`unit_price`, `segment_id`, `discount`, `line_total` server tomonidan to'ldirilgan)
  - `OrderOut` — to'liq buyurtma javob sxemasi
  - `OrderStatusUpdate` — `status`, `version` (optimistik lock uchun)
  - `PaginatedOrders` — `items`, `total`, `limit`, `offset`
- **`app/modules/orders/service.py`** — biznes mantiq:
  - `create_order` — ATOMIK: order + order_line INSERT → stock `_record_movement_tx` (LOCK→check→INSERT) → ledger `_record_entry_tx`; barcha operatsiyalar bitta DB sessiyasida, caller commit qiladi
  - `update_status` — server-avtoritar holat mashinasi (`VALID_TRANSITIONS`); canceled kompensatsiya (ombor `in` + ledger `credit`, ACID)
  - `get_order` — RBAC scope (`_check_order_access`); ruxsatsiz → 404 (IDOR)
  - `list_orders` — paginated, `selectinload(Order.lines)` (N+1 yo'q), RBAC scope
  - `_record_movement_tx` — tranzaksiya-xavfsiz ombor yordamchisi (Redis chaqirilmaydi, faqat DB flush)
  - `_record_entry_tx` — tranzaksiya-xavfsiz buxgalteriya yordamchisi (Redis chaqirilmaydi, faqat DB flush)
  - `_get_product_price` — narxni aniq segment bo'yicha katalogdan oladi (fallback yo'q)
- **`alembic/versions/0007_orders.py`** — migratsiya 0007: 2 jadval:
  - `order` — buyurtma bosh yozuvi (`status`, `total_amount`, `currency`, `ordered_at`, `warehouse_id`, `branch_id`, `client_uuid`, `version`, soft-delete)
  - `order_line` — buyurtma qatorlari (`order_id`, `product_id`, `qty`, `unit_price`, `segment_id`, `discount`, `line_total`)
  - `uq_order_store_client_uuid` — `(store_id, client_uuid) WHERE client_uuid IS NOT NULL` partial unique index (idempotentlik + DoS himoyasi)
  - `ix_order_store_id`, `ix_order_agent_id`, `ix_order_status`, `ix_order_ordered_at` — qidiruv/filtr indekslari
  - `ix_order_line_order_id` — order_line bo'yicha join indeksi
  - downgrade guard: jadvallarda qatorlar bo'lsa `RuntimeError` (T5 naqshi)
- **`app/modules/rbac/permissions.py`** — `Module.ORDERS` qo'shildi
- **42 yangi buyurtma testi** (`backend/app/tests/orders/`), jami: **405 test**

### Security

- **Narx SERVER-AVTORITAR**: `OrderLineIn` sxemasida `unit_price`, `segment_id`, `discount` maydonlari mavjud emas — klient narx/chegirma/segment bera olmaydi. Narx faqat `Store.segment_id` + katalog `ProductPrice` dan server tomonida olinadi
- **Idempotentlik**: `(store_id, client_uuid)` DB unique partial index + Redis `SET NX` (`idem:orders:create:{actor_id}:{store_id}:{client_uuid}`, TTL 24 soat); boshqa aktor bir xil `store+client_uuid` ishlatsa → 409 (DoS himoyasi)
- **IDOR scope**: `GET /orders/{id}` va `PATCH /orders/{id}/status` — ruxsatsiz buyurtma 404 qaytaradi (mavjudlikni oshkor qilmaslik); `list_orders` — rol asosida WHERE sharti qo'shiladi

---

## [0.8.0] - 2026-06-16 — T9+T10: Ombor & Buxgalteriya (append-only ledger)

Ombor (T9) va Buxgalteriya (T10) modullari qurildi. Xavfsizlik/sifat darvozasi **PASS** (363/363 test).

### Added

- **`app/modules/stock/router.py`** — ombor endpointlari (`/stock` prefiksi):
  - `POST /stock/movements` — harakat qayd etish (faqat administrator; `stock:create`); APPEND-ONLY
  - `GET /stock/balance` — mahsulot + ombor bo'yicha joriy qoldiq (`product_id`, `warehouse_id` query param; `stock:view`)
  - `GET /stock/movements` — paginated harakatlar ro'yxati (`product_id`, `warehouse_id`, `movement_type` filtrlari; `stock:view`)
- **`app/modules/stock/schemas.py`** — Pydantic v2 sxemalari:
  - `StockMovementCreate` — `product_id`, `warehouse_id`, `type` (`in|out|transfer|adjust`), `qty` (Decimal, musbat), `ref_type`, `ref_id`, `client_uuid`
  - `StockMovementOut` — harakat javob sxemasi (`moved_by`, `moved_at` bilan)
  - `StockBalanceOut` — `qty_on_hand`, `qty_reserved`, `version`, `updated_at`
  - `PaginatedMovements` — `items`, `total`, `limit`, `offset`
- **`app/modules/stock/service.py`** — biznes mantiq: `record_movement`, `get_balance`, `list_movements`; Redis idempotentlik (`idem:stock:movement:{actor_id}:{client_uuid}`, TTL 24 soat); audit_log + outbox_event
- **`app/modules/finance/router.py`** — buxgalteriya endpointlari (`/finance` prefiksi):
  - `POST /finance/ledger` — yozuv qayd etish (faqat buxgalter; `finance:create`); APPEND-ONLY
  - `GET /finance/balance/{store_id}` — do'kon moliyaviy balansi (`finance:view` + IDOR scope)
  - `GET /finance/ledger` — paginated yozuvlar ro'yxati (`store_id`, `entry_type` filtrlari; `finance:view` + scope)
- **`app/modules/finance/schemas.py`** — Pydantic v2 sxemalari:
  - `LedgerEntryCreate` — `store_id`, `type` (`debit|credit`), `amount` (Decimal, musbat), `currency` (ISO 4217, default `UZS`), `ref_type`, `ref_id`, `client_uuid`
  - `LedgerEntryOut` — yozuv javob sxemasi (`entry_date`, `created_by` bilan)
  - `AccountBalanceOut` — `balance`, `currency`, `last_recalc_at`, `version`
  - `PaginatedLedger` — `items`, `total`, `limit`, `offset`
- **`app/modules/finance/service.py`** — biznes mantiq: `record_entry`, `get_balance`, `list_entries`; valyuta mosligi tekshiruvi (currency_mismatch → 409); primary DB dan o'qish (replica kechikishini oldini olish); Redis idempotentlik (`idem:finance:ledger:{actor_id}:{client_uuid}`, TTL 24 soat)
- **`alembic/versions/0006_stock_finance.py`** — migratsiya 0006: 4 jadval + DB-darajali append-only RULE (Postgres):
  - `stock_movement` — APPEND-ONLY ombor harakatlari (`Numeric(18,4)` miqdor)
  - `stock_balance` — `(product_id, warehouse_id)` UNIQUE kesh jadvali; `qty_on_hand`, `qty_reserved`
  - `ledger_entry` — APPEND-ONLY buxgalteriya yozuvlari (`Numeric(18,2)` miqdor)
  - `account_balance` — `store_id` UNIQUE kesh jadvali; `balance`, `currency`, `last_recalc_at`
  - `uq_stock_movement_client_uuid` — partial unique index (`client_uuid IS NOT NULL`); idempotentlik
  - `uq_ledger_entry_client_uuid` — partial unique index (`client_uuid IS NOT NULL`); idempotentlik
  - PostgreSQL `RULE`: `stock_movement_no_update`, `stock_movement_no_delete`, `ledger_entry_no_update`, `ledger_entry_no_delete` — DB darajasida UPDATE/DELETE bloklash (defence-in-depth)
  - downgrade guard: jadvallarda qatorlar bo'lsa `RuntimeError` (T5 naqshi)
- **41 yangi test** (`backend/app/tests/stock/`, `backend/app/tests/finance/`), jami: **363 test**

### Security

- **Moliyaviy IDOR himoya (scope)**: `GET /finance/balance/{store_id}` — `store` roli faqat o'z `store_id` ini ko'radi; boshqa `store_id` → 404 (mavjudlikni oshkor qilmaslik); agent — faqat o'z do'konlari; accountant/administrator — barchasi
- **DB-darajali UPDATE/DELETE bloklash (PostgreSQL RULE)**: `stock_movement` va `ledger_entry` jadvallarida `DO INSTEAD NOTHING` RULE — servis qatlami chetlab o'tilsa ham yozuvni o'zgartirib bo'lmaydi
- **Valyuta mosligi (currency_mismatch)**: yangi yozuv valyutasi do'konning mavjud valyutasiga mos kelishi shart; mos kelmasa → 409
- **Idempotentlik (Redis SET NX + DB unique)**: `client_uuid` Redux NX Redis kaliti (24 soat TTL) + `partial unique` DB indeks — ikki qatlamli himoya; takroriy so'rov bir xil javob qaytaradi

---

## [0.7.0] - 2026-06-16 — T6: Foydalanuvchi boshqaruvi

Foydalanuvchi boshqaruvi moduli qurildi. Xavfsizlik/sifat darvozasi **PASS** (322/322 test).

### Added

- **`app/modules/users/router.py`** — foydalanuvchilar endpointlari (`/users` prefiksi):
  - `GET /users` — paginated ro'yxat (`limit`/`offset`, `role`, `branch_id`, `is_active` filtrlari)
  - `POST /users` — yangi foydalanuvchi yaratish (faqat administrator); telefon unikal bo'lishi shart
  - `GET /users/{id}` — bitta foydalanuvchi
  - `PATCH /users/{id}` — qisman yangilash (`version` optimistik lock majburiy)
  - `PATCH /users/{id}/deactivate` — deaktivatsiya (`is_active=False`); admin o'zini bloklash rad etiladi
- **`app/modules/users/schemas.py`** — Pydantic v2 sxemalari:
  - `UserCreate` — yangi foydalanuvchi (`full_name`, `phone`, `role`, `password`, `branch_id`, `locale`, `biometric_enrolled`, `device_id`, `client_uuid`)
  - `UserUpdate` — PATCH so'rovi (`version` majburiy, kamida bitta maydon)
  - `UserOut` — to'liq javob (`phone`/`full_name` deshifrlanib qaytadi; `password_hash` hech qachon chiqmaydi)
  - `PaginatedUsers` — paginated ro'yxat javob sxemasi
- **`app/modules/users/service.py`** — biznes mantiq qatlami:
  - `create_user` — PII shifrlash, phone_bi blind-index, Redis idempotentlik (`idem:users:create:{actor_id}:{client_uuid}`, TTL 24 soat), audit_log + outbox_event
  - `get_user` — ID bo'yicha, topilmasa 404
  - `list_users` — paginated, `role`/`branch_id`/`is_active` filtrlari
  - `update_user` — PATCH, optimistik lock, phone o'zgarganda phone_bi yangilanadi, audit trail
  - `deactivate_user` — `is_active=False`, self-deactivation himoyasi, audit trail
- **`alembic/versions/0005_user_phone_encrypt.py`** — migratsiya 0005:
  - `app_user.phone` — `VARCHAR(20) → BYTEA` (AES-256-GCM shifrlangan)
  - `app_user.full_name` — `VARCHAR(255) → BYTEA` (AES-256-GCM shifrlangan)
  - `app_user.phone_bi` — yangi `VARCHAR(64)` ustun (HMAC blind-index, UNIQUE partial index)
  - `uq_app_user_phone_bi` — partial unique index: `(phone_bi) WHERE phone_bi IS NOT NULL` (PostgreSQL)
  - `ix_app_user_phone_bi` — phone_bi ustuni indeksi
  - Eski `uq_app_user_phone` unique constraint olib tashlandi (shifrlangan ustunda ma'nosiz)
  - **Backfill (in-migration data migration)**: mavjud qatorlar batch'da (500 ta) o'qilib, `phone`/`full_name` `encrypt_pii()` bilan shifrlanganladi, `phone_bi = blind_index(phone)` to'ldirildi
- **44 yangi users testi** (`backend/app/tests/users/`), jami: **322 test**

### Changed

- **`app/modules/auth/service.py` — `login()`**: foydalanuvchini `AppUser.phone` (shifrlangan ustun) bo'yicha emas, `AppUser.phone_bi == blind_index(phone)` orqali qidiradi. Shifrlangan `LargeBinary` ustunida `WHERE phone = :val` ishlamaydi — blind-index yagona xavfsiz yondashuv.
- **`app/core/security.py` — `mask_pii()`**: `full_name` kaliti qo'shildi — audit logda to'liq ism ham maskalanadi.
- **`app/core/config.py` — `validate_pii_keys_in_prod()`**: dev-default kalit qiymatlari **denylist** qo'shildi. Dev-default kalitlar haqiqiy 64-belgili hex bo'lgani uchun format tekshiruvi ularni o'tkazib yuborardi; production/staging da bu ikkala aniq qiymat ham bloklanadi.
- **Alembic 0004/0005 downgrade Postgres guard**: `downgrade()` da `app_user` jadvalida qatorlar bo'lsa `RuntimeError` — shifrlangan PII tasodifan NULL ga aylanib yo'qolmasligi uchun.

### Security

- **`app_user.phone` va `app_user.full_name` shifrlangan saqlash**: `EncryptedString` TypeDecorator — DB da hech qachon ochiq-matn saqlanmaydi; ORM qatlamida shaffof.
- **`password_hash` hech qachon `UserOut` ga kirmaydi**: `UserOut` sxemasida ushbu maydon yo'q; `_write_audit()` da `mask_pii()` orqali maskalanadi.
- **Faqat administrator (ikki qatlamli himoya)**: `require_permission(Module.RBAC, ...)` + `_admin_only()` role check — har bir endpoint uchun. Bitta qatlam aylanib o'tilsa ikkinchisi bloklaydi.
- **Self-deactivation himoyasi**: `deactivate_user()` — `current_user.id == user_id` bo'lsa 403; administrator akkaunti o'chirib tashlanmaydi.
- **dummy_hash 60-belgilik (timing himoya)**: foydalanuvchi topilmagan holatda ham `verify_password()` chaqiriladi; response vaqti foydalanuvchi mavjudligini oshkor qilmaydi.
- **phone_bi partial unique**: bir telefon raqamiga faqat bitta aktiv yozuv; dublikat → 409.

---

## [0.6.0] - 2026-06-16 — T5: Mijoz bazasi (PII shifrlash)

Mijoz bazasi moduli qurildi. Xavfsizlik/sifat darvozasi **PASS** (278/278 test, gate iteratsiya 2).

### Added

- **`app/modules/customers/router.py`** — do'konlar endpointlari (`/customers/stores` prefiksi):
  - `GET /customers/stores` — paginated ro'yxat (`limit`/`offset`, `branch_id`, `search_inn`, `search_phone`, `search_name` filtrlari)
  - `POST /customers/stores` — yangi do'kon yaratish (admin yoki agent); INN unikalligi `inn_bi` blind-index orqali
  - `GET /customers/stores/{id}` — bitta do'kon (RBAC + scope; kuryer `StoreLimitedOut` oladi)
  - `PATCH /customers/stores/{id}` — qisman yangilash (`version` optimistik lock majburiy)
  - `DELETE /customers/stores/{id}` — soft-delete (`deleted_at` o'rnatiladi, admin)
  - `POST /customers/stores/{id}/assign-agent` — do'konga agent biriktirish (faqat administrator); `AgentStore` yozuvi yaratiladi, idempotent
- **`app/modules/customers/schemas.py`** — Pydantic v2 sxemalari:
  - `StoreCreate` — yangi do'kon (PII maydonlar: `inn`, `inps`, `owner_name`, `phone`)
  - `StoreUpdate` — PATCH so'rovi (`version` majburiy, kamida bitta maydon)
  - `StoreOut` — to'liq javob (admin/accountant/agent; PII deshifrlanib qaytadi)
  - `StoreLimitedOut` — kuryer uchun cheklangan javob (faqat `id`, `name`, `address`, `gps_lat`, `gps_lng`; PII va `credit_limit` yo'q)
  - `AssignAgentRequest` — agent biriktirish so'rovi (`agent_id`)
  - `PaginatedStores` — paginated ro'yxat javob sxemasi
- **`app/core/crypto.py`** — ilova-darajali PII shifrlash moduli:
  - `encrypt_pii(plaintext)` — AES-256-GCM shifrlash; har chaqiruvda yangi 12-baytli IV; format: `iv(12) + gcm_tag(16) + ciphertext`
  - `decrypt_pii(ciphertext)` — AES-GCM deshifrlash; faqat `InvalidTag` ushlanadi va `CRITICAL` loglanadi; boshqa xatolar qayta ko'tariladi
  - `blind_index(value)` — HMAC-SHA256 blind-index (normalize: strip + lowercase); `base64url` encoded, padding yo'q
  - `verify_crypto_keys()` — startup encrypt→decrypt round-trip self-check; muvaffaqiyatsiz bo'lsa `RuntimeError` — ilova boshlanmaydi
  - `EncryptedString` — SQLAlchemy `TypeDecorator` (`LargeBinary` ustida): yozishda `str → encrypt_pii()`, o'qishda `decrypt_pii() → str`; shaffof (ORM foydalanuvchi shifrlashni ko'rmaydi)
- **`alembic/versions/0004_store_pii_and_user_fk.py`** — migratsiya 0004:
  - `store.inn`, `inps`, `owner_name`, `phone` — `VARCHAR → BYTEA` (shifrlangan saqlash)
  - `store.inn_bi`, `phone_bi` — yangi `VARCHAR(64)` ustunlar (HMAC blind-index)
  - `uix_store_inn_bi_active` — partial unique index: `(inn_bi) WHERE deleted_at IS NULL AND inn_bi IS NOT NULL` (PostgreSQL)
  - `ix_store_phone_bi` — `phone_bi` ustuni indeksi
  - `store.user_id` — nullable FK → `app_user.id` (`ON DELETE SET NULL`); `ix_store_user_id` indeks
  - Upgrade guard: `inn IS NOT NULL` qatorlar bo'lsa `RuntimeError` — ma'lumot yo'qolmasin
- **`app/models/store.py`** kengaytmasi — `inn`, `inps`, `owner_name`, `phone` ustunlari `EncryptedString()` tipiga o'tkazildi; `inn_bi`, `phone_bi`, `user_id` maydonlari qo'shildi
- **Startup crypto probe** — `main.py lifespan` da `verify_crypto_keys()` chaqiriladi; noto'g'ri kalit yoki round-trip xatosida ilova ishga tushmaydi
- **49 yangi customers testi** (`backend/app/tests/customers/`), jami: **278 test**

### Changed

- **`store` roli scope** (`app/modules/rbac/scope.py`) endi `Store.user_id == user.id` orqali ishlaydi — T2 da qo'yilgan vaqtinchalik `deny-all` (texnik qarz) hal qilindi
- **`cryptography`** bog'liqligi `pyproject.toml` ga qo'shildi (`cryptography>=42.0`)

### Security

- **PII shifrlangan saqlash**: `store.inn`, `inps`, `owner_name`, `phone` DB da hech qachon ochiq-matn saqlanmaydi — `EncryptedString` ORM darajasida majburiy shifrlash ta'minlaydi
- **Blind-index qidiruv**: `inn`/`phone` bo'yicha qidiruv `inn_bi`/`phone_bi` HMAC orqali — DB da ochiq-matn `LIKE` qidiruv yo'q
- **Audit `mask_pii`**: `_write_audit()` da `before_json`/`after_json` `mask_pii()` dan o'tkaziladi — PII audit logga tushmaydi
- **`assign-agent` + scope-fields admin-only**: `user_id`/`agent_id`/`branch_id` o'zgartirish faqat administrator; agent/store/courier scope-fieldlarni o'zgartira olmaydi
- **`decrypt_pii` fail-safe**: faqat `InvalidTag` ushlanadi va `CRITICAL` loglanadi — jimgina PII yo'qolish (silent data loss) yo'q; kalit qiymati hech qachon logga tushirilmaydi
- **Kalit format validatsiya**: `PII_ENCRYPTION_KEY` va `BLIND_INDEX_KEY` faqat 64-belgili hex qabul qilinadi; SHA-256 fallback ataylab olib tashlangan — noto'g'ri format yashirin o'tib ketmaydi
- **`StoreLimitedOut`** kuryer uchun: `inn`, `inps`, `owner_name`, `phone`, `credit_limit` oqib ketmaydi

---

## [0.5.0] - 2026-06-16 — T4: Katalog CRUD

Katalog moduli qurildi. Xavfsizlik/sifat darvozasi **PASS** (229/229 test).

### Added

- **`app/modules/catalog/router.py`** — katalog endpointlari (`/catalog` prefiksi):
  - `GET /catalog/categories` — faol kategoriyalar ro'yxati
  - `POST /catalog/categories` — yangi kategoriya (admin)
  - `GET /catalog/price-segments` — narx segmentlar ro'yxati
  - `POST /catalog/price-segments` — yangi narx segmenti (admin)
  - `GET /catalog/products` — paginated ro'yxat (limit/offset, search, category_id, is_active, branch_scope filtrlari)
  - `POST /catalog/products` — yangi mahsulot (admin); idempotentlik `client_uuid` + Redis orqali
  - `GET /catalog/products/{id}` — mahsulot (view, branch visibility)
  - `PATCH /catalog/products/{id}` — qisman yangilash (edit); optimistik lock (`version`)
  - `DELETE /catalog/products/{id}` — soft-delete (admin); `deleted_at` o'rnatiladi
  - `POST /catalog/products/{id}/prices` — narx o'rnatish (edit); oldingi narx `price_history` ga APPEND
  - `GET /catalog/products/{id}/price-history` — narx tarixi, yangirog'i birinchi
  - `POST /catalog/products/{id}/photo` — MinIO rasm upload (JPEG/PNG/WebP, 5 MB, magic-byte validatsiya)
- **`app/modules/catalog/service.py`** — biznes mantiq qatlami:
  - `create_category`, `list_categories` — kategoriya CRUD
  - `create_segment`, `list_segments` — narx segmenti CRUD
  - `create_product`, `get_product`, `list_products`, `update_product`, `delete_product` — mahsulot CRUD
  - `set_price`, `get_price_history` — narx o'rnatish va tarix
  - `update_photo_url` — rasm URL yangilash
  - `_apply_branch_visibility()` — branch-darajali ko'rinish filtri (RBAC integratsiya)
  - `_write_audit()` + `_write_outbox()` — har mutatsiyada audit_log va outbox_event yozuvi
- **`app/modules/catalog/schemas.py`** — Pydantic v2 sxemalari: `CategoryCreate/Out`, `PriceSegmentCreate/Out`, `PriceSet`, `PriceOut`, `PriceHistoryOut`, `ProductCreate`, `ProductUpdate`, `ProductOut`, `PaginatedProducts`
- **`app/core/storage.py`** — `StorageBackend` interfeysi: `MinIOStorage` (prod) va `FakeStorage` (test); magic-byte validatsiya (JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `52 49 46 46`); SVG/HTML rad; 5 MB chegara
- **`alembic/versions/0003_catalog_constraints.py`** — migratsiya 0003:
  - `uix_product_barcode_active` — partial unique index (`barcode WHERE deleted_at IS NULL`)
  - `ix_product_mxik_code_v2` — `mxik_code` indeks
  - `uix_product_price_open` — partial unique index (`product_id, segment_id WHERE valid_to IS NULL`): bir mahsulot × segment uchun faqat bitta ochiq narx
- **43 yangi katalog testi** (`backend/app/tests/catalog/`), jami: **229 test**
- **i18n integratsiya**: `?lang=uz|ru` yoki `Accept-Language` → `ProductOut.name` va `CategoryOut.name` lokalizatsiyalangan; `localized_name()` ishlatiladi; `name_uz` ga fallback
- **Pagination**: `GET /catalog/products` — `limit` (1–200, default 20), `offset` (default 0), `total` javob ichida
- **Search**: `name_uz`, `name_ru`, `sku`, `barcode` ustunlarida `ILIKE` qidiruv

### Security

- **IDOR yopildi**: `client_uuid` endi PK emas — server har doim `uuid7()` bilan ID generatsiya qiladi; `client_uuid` faqat Redis idempotentlik kaliti sifatida ishlatiladi va hech qachon `Product.id` ga yozilmaydi
- **Branch scope majburiy ko'rinish**: `administrator` va `accountant` rollari barcha mahsulotlarni ko'radi; boshqa rollar (`agent`, `courier`, `store`) faqat `branch_scope IS NULL` (global) yoki o'z `branch_id` ga mos mahsulotlarni ko'radi; doiradan tashqari mahsulot uchun 404 qaytariladi (mavjudlikni oshkor qilmaslik)
- **Rasm magic-byte tekshiruvi**: faylning birinchi baytlari tekshiriladi; SVG va HTML rad etiladi; kontent-type headeriga ishonilmaydi
- **Audit PII maskalash**: `_write_audit()` da `before_json`/`after_json` `mask_pii()` dan o'tkaziladi
- **Race condition himoyasi**: `set_price()` — `SELECT FOR UPDATE` + `uix_product_price_open` partial unique index birgalikda

---

## [0.4.0] - 2026-06-16 — T3: i18n (ko'p tillilik)

i18n qatlami qurildi. Xavfsizlik/sifat darvozasi **PASS** (186/186 test).

### Added

- **`app/core/i18n.py`** — i18n qatlami:
  - `SUPPORTED_LOCALES = ("uz", "ru")`, `DEFAULT_LOCALE = "uz"`
  - `current_locale` — `ContextVar[str]` (per-request, async-safe)
  - `parse_accept_language(header)` — RFC 5646 q-faktor bilan til ajratadi; 256 belgidan uzun header DoS himoyasi bilan rad etiladi
  - `localized_name(obj, locale)` — `name_uz`/`name_ru` atribyutli ORM obyektdan til bo'yicha nom qaytaradi; `name_uz` ga fallback
- **`app/core/messages.py`** — xabarlar katalogi (`MESSAGES` dict) va `translate(key, locale, **params)` funksiyasi:
  - `auth.*` guruh: `invalid_credentials`, `inactive_user`, `token_expired`, `token_invalid`, `token_wrong_type`, `authentication_required`, `user_not_found`
  - `rbac.*` guruh: `permission_denied` (format: `{module}`, `{action}`, `{role}`)
  - `common.*` guruh: `not_found`, `validation_error`, `internal_error`
  - Fallback zanjiri: `locale` → `uz` → `message_key` o'zi
- **`app/core/errors.py`** — standart xato sinflari va envelope:
  - `AppError(message_key, status_code, params, detail)` — barcha domenli xatolar bazaviy sinfi
  - `AuthAppError` — `AppError` dan meros (standart 401)
  - `error_envelope(message_key, message, detail)` → `{"message_key": ..., "message": ..., "detail": ...}`
- **`app/core/middleware.py`** — `LocaleMiddleware` (Starlette `BaseHTTPMiddleware`):
  - Til aniqlash ustuvorligi: `?lang=` > `Accept-Language` > `uz` (default)
  - Har request oxirida `current_locale.reset(token)` (coroutine izolyatsiyasi)
- **Global exception handlerlar** (`app/main.py`):
  - `AppError` → envelope + lokalizatsiya + HTTP status
  - `RequestValidationError` (422) → `common.validation_error` envelope; `input`/`url`/`ctx` maydonlari olib tashlangan
  - `HTTPException` / 404 → `common.not_found` envelope
  - `Exception` (500) → `common.internal_error` envelope; stack trace mijozga chiqmaydi
- **55 yangi i18n testi** (`backend/app/tests/i18n/test_i18n.py`), jami: **186 test**

### Changed

- Auth/RBAC xatolari endi `message_key` + lokalizatsiyalangan matn bilan qaytadi (oldin `{"detail": "..."}`)
- `AuthAppError` va `AppError` `require_permission` dependency da ishlatiladi — til middleware orqali avtomatik

### Security

- **HIGH**: `RequestValidationError` (422) javobidan `input`/`url`/`ctx` maydonlari olib tashlandi — parol/token qiymatlari echo qilinmaydi
- **MEDIUM**: 500 handler — ichki stack trace va xato matni mijozga chiqmaydi
- **MEDIUM**: `Accept-Language` uzunlik cheklovi (> 256 belgi → `DEFAULT_LOCALE`) — regex ReDoS oldini olish

---

## [0.3.0] - 2026-06-16 — T2: RBAC

5 rol × 11 modul ruxsat matritsasi qurildi. Xavfsizlik/sifat darvozasi **PASS** (131/131 test).

### Added

- **Ruxsat matritsasi** (`app/modules/rbac/permissions.py`) — ADR §3.6 bo'yicha 5 rol (`administrator`, `agent`, `courier`, `accountant`, `store`) × 11 modul (`catalog`, `agent_cabinet`, `attendance`, `delivery`, `stock`, `finance`, `tickets`, `customers`, `stats`, `contracts`, `promo`) + `rbac` moduli; `Module` va `Action` `StrEnum` konstantalari
- **`require_permission(module, action)`** FastAPI dependency factory (`app/modules/rbac/dependency.py`) — endpoint dekoratorida `Depends(require_permission(Module.X, Action.Y))` ko'rinishida ishlatiladi; ruxsat yo'q bo'lsa HTTP 403 chiqaradi
- **`has_permission(user, module, action)`** sof sinxron yordamchi (`app/modules/rbac/service.py`) — Redis chaqiriqsiz, matritsadan to'g'ridan-to'g'ri; middleware darajasida tezkor tekshiruv uchun
- **`get_permissions_for_role(role, redis)`** async servis — Redis kesh (`rbac:perms:{role}`, 5 daqiqa TTL) orqali ruxsatlar to'plamini qaytaradi
- **Qator-darajali scope** (`app/modules/rbac/scope.py`):
  - `apply_store_scope(query, user)` — SQLAlchemy SELECT ga rol asosida WHERE sharti qo'shadi (immutabel)
  - `get_user_store_ids(user, db)` — agent/store uchun ruxsat etilgan do'kon UUID ro'yxatini qaytaradi
  - Agent scope N+1 tuzatildi: ikkita alohida DB so'rov o'rniga `OR + scalar_subquery` bilan bitta so'rov
- **Redis kesh** — 5 daqiqa TTL; Redis o'chsa matritsadan to'g'ridan-to'g'ri (fail-closed, graceful degradation)
- **`GET /auth/me`** kengaytmasi — T2 da javobga `permissions: list[str]` maydoni qo'shildi (rol ruxsatlari, Redis kesh orqali)
- **`GET /rbac/my-permissions`** — joriy foydalanuvchi barcha ruxsatlarini qaytaradi (`role`, `permissions`, `total`)
- **`GET /rbac/check`** — `?module=catalog&action=view` query params bilan aniq ruxsat tekshiruvi; 403 emas — `allowed: true/false` qaytaradi (UI uchun)
- **Alembic 0002** (`alembic/versions/0002_role_check.py`) — `app_user.role` ustuniga `CHECK` constraint (`ck_app_user_role_valid`): faqat `administrator | agent | courier | accountant | store` qabul qilinadi; PostgreSQL ENUM o'rniga `CHECK` — migratsiyada reverse-compatible
- **403 rad etish logging** — `require_permission` har rad etishda `user_id`, `role`, `perm_module`, `action` maydonlari bilan `WARNING` yozadi (`perm_module` — `module` LogRecord da band bo'lgani uchun)
- **131 test**, hammasi PASS (oldingi 44 + 87 yangi RBAC testi)

### Security

- **`store` roli vaqtinchalik deny-all** — `apply_store_scope` da `Store.id.is_(None)` filtri: `Store.user_id` FK yo'qligi uchun `Store.agent_id == user.id` bog'liq noto'g'ri (IDOR xavfi); T5 da `Store.user_id` FK qo'shilgach tuzatiladi
- **Agent scope N+1 → bitta so'rov** — `OR + scalar_subquery` bilan IDOR oldini olinadi va DB yuklamasi kamayadi

---

## [0.2.0] - 2026-06-15 — T1: Auth yadrosi

JWT autentifikatsiya yadrosi qurildi. Xavfsizlik/sifat darvozasi **PASS** (44/44 test).

### Added

- `POST /auth/login` — telefon + parol bilan kirish; access token (15 daqiqa) va refresh token (30 kun, rotatsiyali) qaytaradi
- `POST /auth/refresh` — refresh token rotatsiyasi: eski token Redis denylist ga tushadi, yangi juft qaytaradi
- `POST /auth/logout` — refresh tokenni denylist ga qo'shib sessiyani yakunlaydi; token imzosi tekshiriladi
- `GET /auth/me` — Bearer access token orqali joriy foydalanuvchi profilini qaytaradi
- `get_current_user()` FastAPI dependency — T2 (RBAC) da `has_permission()` bilan kengaytiriladi
- `app/core/jwt.py` — `create_access_token()`, `create_refresh_token()`, `decode_token()`, `hash_password()`, `verify_password()`; algorithms qat'iy allowlist `["HS256"]`
- `app/core/redis.py` — markaziy async Redis klienti (`get_redis` dependency), ulanish timeout bilan
- Auth hodisalari logging — barcha login/logout/refresh hodisalari `mask_pii()` orqali PII maskalanib yoziladi
- **44 test**, hammasi PASS

### Changed

- `python-jose` → `PyJWT` — algorithm-confusion zaifligidan to'liq himoya; CVE/texnik qarz yopildi
- `passlib` → to'g'ridan-to'g'ri `bcrypt` (rounds=12) — `passlib` ning `bcrypt>=4.x` bilan muvofiqlik muammosi bartaraf etildi

### Security

- Fail-closed denylist: Redis mavjud bo'lmasa refresh token yangilanmaydi (xavfli holat ruxsat etilmaydi)
- Refresh rotatsiya + Redis denylist — replay attack oldini oladi
- `logout` endpoint imzo tekshiruvi — imzosiz token denylist ga qo'shilmaydi
- bcrypt rounds=12 — brute-force sekinlashtirish
- Enumeration/timing himoya — foydalanuvchi topilmasa va parol noto'g'ri bo'lsa bir xil 401 javob

---

## [0.1.0] - 2026-06-15 — Poydevor (Foundation)

Poydevor sprintlari P1–P5 yakunlandi. Xavfsizlik/sifat/SRE darvozasi (security/qa/sre gate)
iteratsiya 2 da **PASS** bilan o'tdi.

### Added

#### Loyiha tuzilishi
- Monorepo skeleti: `backend/`, `web/`, `mobile/`, `desktop/`, `infra/`, `docs/`
- `.pre-commit-config.yaml` (ruff, black, trailing-whitespace)
- `Makefile` — `up`, `down`, `migrate`, `gen-client`, `test`, `lint` buyruqlari

#### Backend skeleti (FastAPI)
- `backend/app/main.py` — FastAPI ilovasi (v0.1.0), `lifespan` lifecycle
- `GET /health` — liveness probe (DB tekshirmasdan), Kubernetes/Docker uchun
- `GET /readiness` — readiness probe: PostgreSQL (`SELECT 1`) + Redis (`PING`) + MinIO (`/minio/health/live`)
- `GET /openapi.json` — OpenAPI 3.x sxemasi (production da `/docs`/`/redoc` yopiq)
- `backend/app/core/config.py` — Pydantic Settings (`pydantic-settings`), `.env` asosida
- `backend/app/core/db.py` — async SQLAlchemy engine + session (primary + replica placeholder)
- `backend/app/core/uuid7.py` — UUID v7 generator (RFC 9562, vaqt-tartibli, thread-safe)
- `backend/app/core/security.py` — `mask_pii()` yordamchi funksiya

#### Ma'lumotlar bazasi sxemasi (Alembic)
- `alembic/versions/0001_initial.py` — 11 jadval to'liq DDL:
  - `app_user`, `store`, `agent_store`
  - `category`, `price_segment`, `product`, `product_price`
  - `price_history` (append-only), `product_note`
  - `audit_log` (append-only), `outbox_event`
- Barcha jadvallarda: `id` (UUID v7 PK), `version` (BIGINT, optimistik lock), `created_at`, `updated_at`, `deleted_at` (soft-delete)
- `set_updated_at()` PostgreSQL trigger funksiyasi — `updated_at` ni avtomatik yangilaydi
- Har jadvalga alohida `BEFORE UPDATE` trigger
- Qisman indekslar (partial index): `ix_app_user_active`, `ix_product_active` — `deleted_at IS NULL`
- GIN full-text indekslar: `ix_product_fts_uz`, `ix_product_fts_ru` (`to_tsvector('simple', ...)`)
- Qisman indekslar: `ix_product_barcode`, `ix_product_mxik_code`, `ix_product_sku`
- `outbox_event` uchun `ix_outbox_event_unpublished` — hali yuborilmagan hodisalar uchun
- `pgcrypto` kengaytmasi `CREATE EXTENSION IF NOT EXISTS` bilan (T5 uchun tayyorlov)
- `downgrade base` va `upgrade head` to'liq ishlaydi

#### Infra (Docker Compose)
- `docker-compose.yml` — to'rtta servis, barchasi `healthcheck` bilan:
  - `postgres` — PostgreSQL 16 primary (port 5432)
  - `timescaledb` — TimescaleDB 2.x / PostgreSQL 16 (port 5434, GPS ingest uchun)
  - `redis` — Redis 7 (port 6379, parol himoyasi)
  - `minio` — MinIO RELEASE (port 9000/9001)

#### OpenAPI va klient generatsiya
- `GET /openapi.json` — klient generatsiya kirish nuqtasi
- `make gen-client` — `openapi-typescript-codegen` (TypeScript, `web/src/api/`) va `openapi-generator` (Dart, `mobile/lib/api/`) ishga tushiradi
- `web/src/api/` va `mobile/lib/api/` — placeholder papkalar (T7/T14 da to'liq)

#### Xavfsizlik qo'riqlovlari
- `mask_pii(data: dict) -> dict` — `inn`, `inps`, `phone`, `password_hash`, `token`, `access_token`, `refresh_token`, `owner_name`, `secret`, `jwt_secret_key` kalitlarini `"***"` ga almashtiradi; asl lug'at o'zgartirilmaydi
- `jwt_secret_key` qo'riqlovchi — production/staging muhitida `CHANGE_ME` bilan boshlanadigan yoki 32 belgidan qisqa kalitni ilova ishga tushishida rad etadi
- CORS qo'riqlovchi — `allow_origins=['*']` + `allow_credentials=True` kombinatsiyasini `model_validator` darajasida rad etadi
- Production da `/docs` va `/redoc` endpointlari `None` ga o'rnatiladi

#### Testlar
- `backend/app/tests/test_health.py` — 7 test: `/health` va `/openapi.json` endpointlari
- `backend/app/tests/test_security.py` — 15 test: `mask_pii()` (9 test) va `uuid7` (6 test)
- Jami: **22 test, hammasi PASS**
- `conftest.py` — async pytest konfiguratsiyasi (`anyio`, ASGI transport)

### Security / Quality

- Xavfsizlik/sifat/SRE darvozasi: iteratsiya 2 da **PASS**
- Aniqlangan texnik qarz (keyingi sprintlarga ko'chirildi — batafsil `docs/FOUNDATION.md`)

---

<!-- Keyingi yozuv shablon:
## [Unreleased]
### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
-->
