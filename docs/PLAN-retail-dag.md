# RETAIL — Bajariladigan vazifalar rejasi (DAG)

| | |
|---|---|
| **Manba** | `docs/ADR-001-retail-architecture.md` |
| **Muallif** | `planner-agent` (orkestr orqali) |
| **Sana** | 2026-06-15 |
| **Keyingi agent** | `developer-agent` (B1 dan boshlab) |

> Belgilar: hajm S/M/L. Har backend endpoint: `client_uuid` idempotentlik + `version` optimistik lock + `audit_log` + `outbox_event`. Moliyaviy jadvallar (`stock_movement`, `ledger_entry`) append-only; moliyaviy o'qish faqat primary DB.

## To'liq DAG jadvali

| ID | Nom | Bosqich | Bog'liqlik | Qatlam | Hajm |
|---|---|---|---|---|---|
| P1 | Repo strukturasi va monorepo skeleti | Pre | yo'q | devops | S |
| P2 | Docker Compose (lokal dev) | Pre | P1 | devops/infra | S |
| P3 | PostgreSQL DDL migratsiya (B1 jadvallari) | Pre | P2 | backend | M |
| P4 | CI/CD pipeline — GitHub Actions | Pre | P1 | devops | M |
| P5 | OpenAPI kontrakt skeleti + klient generatsiya | Pre | P1 | backend+veb | M |
| T1 | Auth yadrosi — JWT + refresh + Redis | B1 | P3, P5 | backend | M |
| T2 | RBAC — rol/ruxsat + qator-himoya + kesh | B1 | T1 | backend | M |
| T3 | i18n backend — message_key + ikki tilli | B1 | T1 | backend | S |
| T4 | Katalog CRUD API | B1 | T2, T3, P3 | backend | M |
| T5 | Mijoz bazasi CRUD API | B1 | T2, T3, P3 | backend | M |
| T6 | Foydalanuvchi boshqaruvi API + biometrik flag | B1 | T2, T4, T5 | backend | S |
| T7 | Veb SPA + Tauri skeleti (React+TS) | B1 | P1, P5 | veb | M |
| T8 | Katalog + Mijoz bazasi veb UI | B1 | T4, T5, T7 | veb | M |
| T9 | Ombor — append-only stock_movement + balans | B2 | T4, T2 | backend | M |
| T10 | Buxgalteriya — ledger append-only + balans | B2 | T5, T2 | backend | M |
| T11 | Buyurtma yadrosi — atomik tranzaksiya | B2 | T9, T10 | backend | L |
| T12 | Buyurtma shabloni API | B2 | T11 | backend | S |
| T13 | Outbox sync API — push/pull endpointlar | B2 | T11 | backend | M |
| T14 | Flutter offline-first yadrosi — Drift + outbox | B2 | T12, T13 | mobil | L |
| T15 | Buyurtma veb UI | B2 | T11, T8 | veb | M |
| T16 | Davomat — Face ID (lokal biometrik) + GPS | B3 | T11, T14 | backend+mobil | M |
| T17 | GPS Ingest Servis — alohida servis + TimescaleDB | B3 | P2, P3 | backend/infra | M |
| T18 | Yetkazib berish — holat mashinasi + GPS | B3 | T17, T11 | backend | M |
| T19 | Push bildirishnomalar — FCM/APNs worker | B3 | T16, T18 | backend/devops | M |
| T20 | Kuryer Flutter ilovasi — GPS trek + yetkazish | B3 | T18, T14 | mobil | M |
| T21 | Agent Flutter ilovasi — GPS, buyurtma, do'kon | B3 | T18, T14 | mobil | M |
| T22 | Statistika/hisobot moduli | B4 | T11, T18, T10 | backend+veb | M |
| T23 | Shartnoma moduli | B4 | T5, T2 | backend+veb | S |
| T24 | Murojaat (ticket) moduli | B4 | T5, T2 | backend+veb+mobil | S |
| T25 | Aksiya moduli | B4 | T4, T5, T2 | backend+veb+mobil | M |
| T26 | Audit UI — veb admin paneli | B4 | T22, T2 | veb | S |
| T27 | Kuzatuvchanlik — Prometheus + OTel + Grafana | B4 | P4 | devops/infra | M |
| T28 | Integratsiya hook'lari — FiscalAdapter + PaymentProvider | B4 | T11, T10 | backend | S |
| T29 | Masshtab testi + production hardening | B4 | T22–T28 | devops/backend | L |

## Tanqidiy yo'l (Critical Path)
```
P1 → P2 → P3 → T1 → T2 → T5 → T10 → T11 → T13 → T14 → T18 → T19 → T29
                                 (T9 ↗ T11 ga ham kiradi)
```
Bu zanjirning har qanday kechikishi butun loyihani kechiktiradi.

## Parallel guruhlar (orkestr parallel ishi uchun)
- **Pre:** [P4, P5] ∥ (P1 dan keyin, P2 bilan parallel)
- **B1:** T1 → [T2, T3] ∥ → [T4, T5] ∥ (+ T7 erta) → [T6, T8] ∥
- **B2:** [T9, T10] ∥ → T11 → [T12, T13, T15] ∥ → T14
- **B3:** T17 (erta) ; [T16] ; T18 → T19 ; [T20, T21] ∥
- **B4:** [T22, T23, T24, T25, T27, T28] ∥ → T26 → T29

## B1 (Poydevor) — birinchi sprint, batafsil DoD
Har vazifaning to'liq DoD'si planner chiqishida; asosiy yo'naltiruvchilar:
- **P1** repo: `backend/ web/ mobile/ desktop/ infra/ docs/`, pre-commit, CI `push`da.
- **P2** docker-compose: postgres-primary, timescaledb, redis, minio — `healthy`.
- **P3** Alembic: `app_user, store, product, category, product_price, price_segment, price_history, agent_store, audit_log, outbox_event` (UUID v7, version, deleted_at, timestamps); `downgrade base`+`upgrade head` ishlaydi.
- **P5** OpenAPI: `/openapi.json`, `make gen-client` (TS + Dart), Auth endpointlar sxemada.
- **T1** Auth: `/auth/login|refresh|logout`, JWT 15min + refresh 30kun rotatsiya, Redis denylist.
- **T2** RBAC: 5 rol × 11 modul matritsasi seed, `has_permission` dependency, qator-darajali filtr, Redis kesh.
- **T3** i18n: `message_key` + `name_uz/name_ru`, `Accept-Language`.
- **T4** Katalog CRUD: mahsulot/kategoriya/segment/narx, `barcode/mxik/sku` indeks, narx tarixi append-only, MinIO rasm.
- **T5** Mijoz bazasi CRUD: store + agent biriktirish, `inn/inps` pgcrypto, audit.
- **T6** Foydalanuvchi boshqaruvi + biometrik flag.
- **T7** Veb+Tauri skeleti: Vite+React+TS+TanStack+i18next, login, ProtectedRoute, `tauri dev/build`.
- **T8** Katalog + Mijoz veb UI: ro'yxat/forma, RBAC-aware, uz/ru.
