# Murojaat (Tickets) moduli — texnik qo'llanma

| | |
|---|---|
| **Versiya** | 0.17.0 |
| **Modul** | `app/modules/tickets` |
| **Prefix** | `/tickets` |
| **Migratsiya** | `alembic/versions/0015_ticket.py` |
| **Test** | `backend/app/tests/tickets/` (658 jami) |

---

## 1. Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `GET` | `/tickets` | view: administrator, accountant, agent, store, courier | Paginated ro'yxat |
| `POST` | `/tickets` | create: administrator, agent, store, courier | Yangi murojaat |
| `GET` | `/tickets/{id}` | view: administrator, accountant, agent, store, courier | Murojaat + xabarlar |
| `POST` | `/tickets/{id}/messages` | view (o'z doirasi): hammasi | Xabar qo'shish |
| `PATCH` | `/tickets/{id}/status` | edit: administrator, accountant | Holat o'zgartirish |

### RBAC to'liq matritsasi

| Rol | GET ro'yxat | POST yaratish | GET bitta | POST xabar | PATCH status |
|---|---|---|---|---|---|
| administrator | ✅ barchasi | ✅ | ✅ barchasi | ✅ | ✅ |
| accountant | ✅ barchasi | ✗ | ✅ barchasi | ✅ | ✅ |
| agent | ✅ o'z do'konlari + yaratganlari | ✅ | ✅ o'z doirasi | ✅ | ✗ |
| store | ✅ o'z do'koni | ✅ | ✅ o'z do'koni | ✅ | ✗ |
| courier | ✅ faqat o'zi yaratganlari | ✅ | ✅ faqat o'ziniki | ✅ | ✗ |

---

## 2. Holat mashinasi

```
new ──────────────► in_progress
                        │
                   ┌────┴────┐
                   ▼         ▼
               resolved    closed
                   │
                   └──► in_progress  (qayta ochish)
```

To'liq o'tish matritsasi:

| Joriy holat | Ruxsat etilgan o'tishlar |
|---|---|
| `new` | `in_progress` |
| `in_progress` | `resolved`, `closed` |
| `resolved` | `in_progress` (qayta ochish), `closed` |
| `closed` | — (terminal holat) |

Noqonuniy o'tish → **422** (`tickets.invalid_transition`).
Faqat administrator va accountant holat o'zgartira oladi (`tickets:edit`).

---

## 3. Scope va IDOR qoidalari

### Do'kon murojaati (`store_id` berilgan)

| Rol | Ko'ra oladi | Yarata oladi |
|---|---|---|
| `store` | Faqat `Store.user_id == current_user.id` bo'lgan do'kon murojaatlari | Faqat o'z do'koni uchun |
| `agent` | `AgentStore` orqali biriktirilgan yoki `Store.agent_id == current_user.id` do'konlar | O'z do'konlari uchun |
| `administrator` / `accountant` | Barchasi | ✅ / ✗ |
| `courier` | ✗ (faqat o'zi yaratgan) | O'z nomidan (store_id ixtiyoriy) |

Scope tashqarisidagi murojaat → **404** (mavjudlikni oshkor qilmaslik).

### Xodim murojaati (`store_id = null`)

`store_id` `null` bo'lsa murojaat xodim (employee) murojaati hisoblanadi. Do'kon scope tekshiruvi o'tkazib yuboriladi.
`store` roli xodim murojaati ko'ra olmaydi (do'kon scope `null` ni qamrab olmaydi).
`courier` roli o'zi yaratgan xodim murojaatlarini ko'rishi mumkin.

---

## 4. So'rov va javob sxemalari

### POST /tickets — TicketCreate

```json
{
  "ticket_type": "taklif",
  "subject": "Yangi mahsulot taklifi",
  "body": "Iltimos, X mahsulotini katalogga qo'shing.",
  "store_id": "018f1a2b-0000-7000-8000-000000000001",
  "client_uuid": "018f1a2b-0000-7000-8000-000000000099",
  "branch_id": null
}
```

| Maydon | Turi | Shart | Tavsif |
|---|---|---|---|
| `ticket_type` | string | majburiy | `taklif` yoki `etiroz` |
| `subject` | string (1–255) | majburiy | Murojaat mavzusi |
| `body` | string (1+) | majburiy | Murojaat matni |
| `store_id` | UUID | ixtiyoriy | Do'kon ID (`null` = xodim murojaati) |
| `client_uuid` | UUID | ixtiyoriy | Idempotentlik identifikatori |
| `branch_id` | UUID | ixtiyoriy | Filial ID |

### GET /tickets/{id} — TicketOut (xabarlar bilan)

```json
{
  "id": "018f1a2b-0000-7000-8000-000000000010",
  "store_id": "018f1a2b-0000-7000-8000-000000000001",
  "author_id": "018f1a2b-0000-7000-8000-000000000005",
  "ticket_type": "taklif",
  "subject": "Yangi mahsulot taklifi",
  "body": "Iltimos, X mahsulotini katalogga qo'shing.",
  "status": "in_progress",
  "assigned_to": null,
  "branch_id": null,
  "client_uuid": "018f1a2b-0000-7000-8000-000000000099",
  "version": 2,
  "created_at": "2026-06-18T10:00:00Z",
  "updated_at": "2026-06-18T11:30:00Z",
  "deleted_at": null,
  "messages": [
    {
      "id": "018f1a2b-0000-7000-8000-000000000020",
      "ticket_id": "018f1a2b-0000-7000-8000-000000000010",
      "author_id": "018f1a2b-0000-7000-8000-000000000005",
      "body": "Taklif qabul qilindi, ko'rib chiqilmoqda.",
      "attachment_url": null,
      "created_at": "2026-06-18T11:30:00Z"
    }
  ]
}
```

`GET /tickets` (ro'yxat) da `messages` maydoni `null` qaytadi — xabarlar yuklanmaydi.

### POST /tickets/{id}/messages — TicketMessageCreate

```json
{
  "body": "Qo'shimcha ma'lumot: SKU raqami X-12345.",
  "attachment_url": "https://minio.example.com/retail/tickets/doc-001.pdf"
}
```

| Maydon | Turi | Shart | Tavsif |
|---|---|---|---|
| `body` | string (1+) | majburiy | Xabar matni |
| `attachment_url` | string (≤1024) | ixtiyoriy | Storage'dan olingan fayl URL |

`attachment_url` magic-byte validatsiyasi storage qatlamida (MinIO/S3 da yuklashda) amalga oshiriladi. Bu endpoint faqat URL saqlaydi.

### PATCH /tickets/{id}/status — TicketStatusUpdate

```json
{
  "status": "in_progress",
  "version": 1
}
```

| Maydon | Turi | Shart | Tavsif |
|---|---|---|---|
| `status` | string | majburiy | Yangi holat (`new\|in_progress\|resolved\|closed`) |
| `version` | integer | majburiy | Joriy `version` (optimistik lock) |

`version` mos kelmasa → **409** (`tickets.version_conflict`).

---

## 5. Idempotentlik

`POST /tickets` — ikki qatlamli idempotentlik:

1. **Redis** (birinchi himoya): `idem:tickets:create:{actor_id}:{client_uuid}` kaliti (TTL 24 soat). Kalit mavjud bo'lsa — saqlangan `ticket.id` bo'yicha DB dan qaytariladi.
2. **DB partial unique + IntegrityError** (ikkinchi himoya, race condition uchun): `ticket.client_uuid` ustunida `WHERE client_uuid IS NOT NULL` partial unique index. Parallel so'rovlar race qilsa `IntegrityError` ushlash → rollback → mavjud ticketni qaytarish.

Redis mavjud bo'lmasa yoki xato bo'lsa — graceful degradation: DB qatlamiga o'tiladi.

---

## 6. curl misollari

### Murojaat yaratish

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_type": "taklif",
    "subject": "Yangi mahsulot taklifi",
    "body": "Iltimos, X mahsulotini katalogga qo'\''shing.",
    "store_id": "018f1a2b-0000-7000-8000-000000000001",
    "client_uuid": "018f1a2b-0000-7000-8000-000000000099"
  }'
```

### Xabar qo'shish

```bash
curl -X POST http://localhost:8000/tickets/018f1a2b-0000-7000-8000-000000000010/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Qo'\''shimcha ma'\''lumot taqdim etildi.",
    "attachment_url": null
  }'
```

### Holat o'zgartirish (faqat admin/buxgalter)

```bash
curl -X PATCH http://localhost:8000/tickets/018f1a2b-0000-7000-8000-000000000010/status \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "version": 1
  }'
```

### Murojaat ro'yxati (status filtri bilan)

```bash
curl "http://localhost:8000/tickets?status=new&limit=20&offset=0" \
  -H "Authorization: Bearer <token>"
```

---

## 7. Xato kodlari

| Kod | `message_key` | Sabab |
|---|---|---|
| 404 | `tickets.not_found` | Murojaat topilmadi yoki scope tashqarisi |
| 403 | `tickets.forbidden` | Rol ruxsati yo'q (holat o'zgartirish) |
| 409 | `tickets.version_conflict` | `version` mos kelmadi (optimistik lock) |
| 422 | `tickets.invalid_transition` | Noqonuniy holat o'tishi |

---

## 8. Migratsiya runbook

```bash
# Standart migratsiya (OLTP DB)
cd backend
alembic upgrade 0015

# Yoki to'liq:
alembic upgrade head
```

Downgrade faqat bo'sh `ticket` jadvalida mumkin. Qatorlar mavjud bo'lsa `RuntimeError` chiqadi.

---

## 9. Ma'lumotlar bazasi sxemasi

### `ticket` jadvali

| Ustun | Turi | Tavsif |
|---|---|---|
| `id` | UUID v7 | Birlamchi kalit |
| `store_id` | UUID, FK → store (SET NULL) | Do'kon (NULL = xodim murojaati) |
| `author_id` | UUID, FK → app_user (SET NULL) | Muallif |
| `assigned_to` | UUID, FK → app_user (SET NULL) | Mas'ul xodim |
| `ticket_type` | VARCHAR(20) | `taklif` yoki `etiroz` |
| `subject` | VARCHAR(255) | Mavzu |
| `body` | TEXT | Murojaat matni |
| `status` | VARCHAR(20), default `new` | Joriy holat |
| `branch_id` | UUID, nullable | Filial |
| `client_uuid` | UUID, nullable | Idempotentlik (partial unique) |
| `version` | BIGINT | Optimistik lock |
| `created_at` | TIMESTAMPTZ | Yaratilgan (UTC) |
| `updated_at` | TIMESTAMPTZ | Oxirgi yangilangan (UTC) |
| `deleted_at` | TIMESTAMPTZ, nullable | Soft delete (NULL = aktiv) |

### `ticket_message` jadvali

| Ustun | Turi | Tavsif |
|---|---|---|
| `id` | UUID v7 | Birlamchi kalit |
| `ticket_id` | UUID, FK → ticket (CASCADE) | Murojaat |
| `author_id` | UUID, FK → app_user (SET NULL) | Xabar muallifi |
| `body` | TEXT | Xabar matni |
| `attachment_url` | VARCHAR(1024), nullable | Fayl URL (MinIO/S3) |
| `created_at` | TIMESTAMPTZ | Yaratilgan (UTC) |

`ticket_message` — append-only: UPDATE va DELETE servis qatlamida amalga oshirilmaydi.
`ticket` o'chirilsa (soft yoki CASCADE) xabarlar ham CASCADE bilan o'chiriladi.
