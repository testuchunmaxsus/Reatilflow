# Statistika moduli texnik qo'llanmasi (T22)

| | |
|---|---|
| **Versiya** | 0.29.0 |
| **Sprint** | B4 (T22) + production hardening |
| **Holat** | gate PASS (792/792 test) |
| **Migratsiya** | `0017_stats_indexes.py` (indekslar; jadval yaratilmadi) |

Statistika moduli mavjud `Order`, `Delivery`, `LedgerEntry`, `AccountBalance` jadvallaridan read-only o'qish orqali hisobotlar beradi. Hech qanday yangi model yoki migratsiya yo'q.

---

## Endpointlar jadvali

| Endpoint | Metod | Ruxsat | DB | Tavsif |
|---|---|---|---|---|
| `/stats/sales` | GET | `stats:view` (barcha rollar) | Read replica | Savdo statistikasi |
| `/stats/delivery` | GET | `stats:view` (barcha rollar) | Read replica | Yetkazish statistikasi |
| `/stats/finance` | GET | `finance:view` (courier yo'q) | **Primary DB** | Moliyaviy statistika |

### DB tanlash qoidasi (ADR §3.8)

- `sales` va `delivery` — non-financial, read replica (`get_db_replica`). Replikatsiya kechikishi qabul qilinadi.
- `finance` — moliyaviy aniqlik talab etiladi, primary DB (`get_db`). Replica kechikishi qarz/haqdorlik miqdorini noto'g'ri ko'rsatishi mumkin.

---

## Scope/IDOR jadvali (rol bo'yicha)

| Rol | `/stats/sales` | `/stats/delivery` | `/stats/finance` |
|---|---|---|---|
| `administrator` | Barchasi (branch_id filtr ixtiyoriy) | Barchasi (courier_id filtr ixtiyoriy) | Barchasi (branch_id filtr ixtiyoriy) |
| `accountant` | Barchasi | Barchasi | Barchasi |
| `agent` | Faqat o'z do'konlari buyurtmalari | Faqat o'z do'konlari buyurtmalarining yetkazishlari | Faqat o'z do'konlari balansi |
| `store` | Faqat o'z do'konining buyurtmalari | Faqat o'z do'konining buyurtmalarining yetkazishlari | Faqat o'z do'konining balansi |
| `courier` | Bo'sh javob (scope yo'q) | Faqat o'z yetkazishlari | **403** (`finance:view` ruxsati yo'q) |

Scope tashqarisida ma'lumot so'ralsa — 403 emas, bo'sh javob (0 qiymatlar bilan) qaytariladi (mavjudlikni oshkor qilmaslik). Faqat `/stats/finance` da courier uchun 403.

---

## GET /stats/sales

Buyurtmalar bo'yicha savdo statistikasi.

### So'rov parametrlari

| Parametr | Tur | Majburiy | Tavsif |
|---|---|---|---|
| `from` | ISO 8601 datetime | Yo'q | Boshlanish vaqti (`Order.ordered_at >= from`) |
| `to` | ISO 8601 datetime | Yo'q | Tugash vaqti (`Order.ordered_at <= to`) |
| `branch_id` | UUID string | Yo'q | Filial filtri (faqat admin/accountant uchun ishlaydi) |
| `group_by` | `day` \| `week` \| `month` | Yo'q | Dinamika guruhlash. Ko'rsatilmasa `dynamics: []` |

### Javob: `SalesStatsOut`

```json
{
  "total_orders": 42,
  "total_amount": "1850000.00",
  "currency": "UZS",
  "period_from": "2026-06-01T00:00:00",
  "period_to": "2026-06-30T23:59:59",
  "group_by": "week",
  "dynamics": [
    { "period": "2026-W22", "order_count": 18, "total_amount": "820000.00" },
    { "period": "2026-W23", "order_count": 24, "total_amount": "1030000.00" }
  ]
}
```

`period` formatlari:
- `group_by=day` → `"2026-06-15"` (`%Y-%m-%d`)
- `group_by=week` → `"2026-W23"` (`%Y-W%W`)
- `group_by=month` → `"2026-06"` (`%Y-%m`)

Xatolar: `422` — `from > to` yoki yaroqsiz `group_by`.

---

## GET /stats/delivery

Yetkazishlar bo'yicha statistika (kuryer samaradorligi).

### So'rov parametrlari

| Parametr | Tur | Majburiy | Tavsif |
|---|---|---|---|
| `from` | ISO 8601 datetime | Yo'q | Boshlanish vaqti (`Delivery.assigned_at >= from`) |
| `to` | ISO 8601 datetime | Yo'q | Tugash vaqti |
| `courier_id` | UUID string | Yo'q | Kuryer filtri (faqat admin/accountant uchun ishlaydi) |

### Javob: `DeliveryStatsOut`

```json
{
  "total_deliveries": 30,
  "delivered_count": 25,
  "failed_count": 2,
  "in_progress_count": 3,
  "avg_delivery_minutes": "47.50",
  "period_from": "2026-06-01T00:00:00",
  "period_to": null
}
```

- `avg_delivery_minutes` — `started_at → delivered_at` oraliq, faqat `status=delivered` yetkazishlar uchun, `Decimal` aniqlik. Yetkazilgan yetkazish yo'q bo'lsa `null`.
- `in_progress_count` — terminal bo'lmagan holat (`assigned`, `started`, `delivering`).

Xatolar: `422` — `from > to`.

---

## GET /stats/finance

Do'kon bo'yicha qarz/haqdorlik va jami debit/kredit statistikasi.

**PRIMARY DB ishlatiladi** — moliyaviy aniqlik talabi (ADR §3.8).

### So'rov parametrlari

| Parametr | Tur | Majburiy | Tavsif |
|---|---|---|---|
| `from` | ISO 8601 datetime | Yo'q | `LedgerEntry.entry_date >= from` |
| `to` | ISO 8601 datetime | Yo'q | `LedgerEntry.entry_date <= to` |
| `branch_id` | UUID string | Yo'q | Filial filtri (faqat admin/accountant uchun ishlaydi) |

### Javob: `FinanceStatsOut`

```json
{
  "total_debit": "5000000.00",
  "total_credit": "3200000.00",
  "net_balance": "1800000.00",
  "stores": [
    {
      "store_id": "01900000-0000-7000-8000-000000000001",
      "store_name": "Yunusobod Supermarket",
      "total_debit": "3000000.00",
      "total_credit": "2000000.00",
      "balance": "1000000.00",
      "currency": "UZS"
    }
  ],
  "period_from": "2026-06-01T00:00:00",
  "period_to": null
}
```

- `balance > 0` — do'kon qarzdor (debit oshgan).
- `balance < 0` — do'konda ortiqcha kredit (to'lov oldindan qilingan).
- `balance` — `AccountBalance.balance` dan olinadi (kumulativ joriy balans). Period filtri balansga emas, faqat `LedgerEntry` agregatsiyasiga qo'llaniladi.
- `net_balance = total_debit - total_credit` (barcha do'konlar yig'indisi).

Xatolar: `403` — courier; `422` — `from > to`.

---

## curl misollari

```bash
# Savdo statistikasi — oy bo'yicha dinamika
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/stats/sales?from=2026-06-01T00:00:00&to=2026-06-30T23:59:59&group_by=month"

# Yetkazish statistikasi — muayyan kuryer uchun
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/stats/delivery?courier_id=01900000-0000-7000-8000-000000000042&from=2026-06-01T00:00:00"

# Moliyaviy statistika — filial bo'yicha
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/stats/finance?branch_id=01900000-0000-7000-8000-000000000010"

# group_by=week misoli
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/stats/sales?group_by=week&from=2026-06-01T00:00:00&to=2026-06-18T23:59:59"
```

---

## Sxemalar qisqacha

```
SalesPeriodItem     period: str, order_count: int, total_amount: Decimal
SalesStatsOut       total_orders, total_amount, currency, period_from, period_to,
                    group_by, dynamics: list[SalesPeriodItem]

DeliveryStatsOut    total_deliveries, delivered_count, failed_count,
                    in_progress_count, avg_delivery_minutes: Decimal|None,
                    period_from, period_to

FinanceStoreItem    store_id, store_name, total_debit, total_credit,
                    balance, currency
FinanceStatsOut     total_debit, total_credit, net_balance,
                    stores: list[FinanceStoreItem], period_from, period_to
```

---

---

## SQL agregatsiya (v0.29.0)

### Python→SQL ko'chirish

v0.19.0 da `sales_stats()` va `delivery_stats()` barcha mos yozuvlarni Python ga yuklab, xotira ichida agregatsiya qilardi. Million+ yozuvda bu yondashuv xotira sarfini oshiradi va javob vaqtini uzaytiradi.

v0.29.0 da barcha hisoblashlar DB darajasiga ko'chirildi: `func.count`, `func.sum`, `func.coalesce`, `func.avg`, `case(...)`. Python da faqat tayyor agregat satrlar iterated qilinadi.

**Natija/JSON sxema o'zgarmagan** — mavjud klientlar qayta ishlatilishi shart emas.

---

### Har bir funksiya SQL arxitekturasi

#### `sales_stats()` — savdo statistikasi

Ikki `SELECT`:

1. **Jami aggregat** — bitta `SELECT COUNT(*), COALESCE(SUM(total_amount), 0)`:
   ```sql
   SELECT COUNT(*) AS total_orders,
          COALESCE(SUM(total_amount), 0) AS total_amount
   FROM   "order"
   WHERE  deleted_at IS NULL
     [AND store_id IN (...) | branch_id = ...]
     [AND ordered_at >= :from_dt AND ordered_at <= :to_dt]
   ```

2. **Dinamika** (faqat `group_by` berilganda, `total_orders > 0`):
   ```sql
   -- SQLite
   SELECT strftime('%Y-%m', ordered_at) AS period,
          COUNT(*)                       AS order_count,
          COALESCE(SUM(total_amount), 0) AS total_amount
   FROM   "order"
   WHERE  deleted_at IS NULL [scope + vaqt filtrlari]
   GROUP  BY period
   ORDER  BY period;

   -- PostgreSQL
   SELECT to_char(ordered_at, 'YYYY-MM') AS period,
          COUNT(*),
          COALESCE(SUM(total_amount), 0)
   FROM   "order"
   WHERE  deleted_at IS NULL [scope + vaqt filtrlari]
   GROUP  BY period
   ORDER  BY period;
   ```

#### `delivery_stats()` — yetkazish statistikasi

Bitta `SELECT` — barcha sanoqlar va avg bir so'rovda:

```sql
-- SQLite
SELECT COUNT(*)                                                  AS total,
       SUM(CASE WHEN status='delivered'              THEN 1 ELSE 0 END) AS delivered_count,
       SUM(CASE WHEN status='failed'                 THEN 1 ELSE 0 END) AS failed_count,
       SUM(CASE WHEN status NOT IN ('delivered','failed') THEN 1 ELSE 0 END) AS in_progress_count,
       AVG(CASE WHEN status='delivered'
                 AND started_at IS NOT NULL
                 AND delivered_at IS NOT NULL
            THEN (julianday(delivered_at) - julianday(started_at)) * 24 * 60
            ELSE NULL END)                                       AS avg_minutes
FROM   delivery
WHERE  deleted_at IS NULL [scope + vaqt filtrlari];

-- PostgreSQL: avg_minutes CASE ichida
-- EXTRACT(EPOCH FROM (delivered_at - started_at)) / 60
```

- `avg_minutes` `NULL` → `avg_delivery_minutes: null` javobda (yetkazilgan yozuv yo'q).
- `in_progress_count` — terminal bo'lmagan barcha holatlar: `assigned`, `started`, `delivering`.

#### `finance_stats()` — moliyaviy statistika

Ikki `SELECT`:

1. **Ledger agregatsiya** — `GROUP BY store_id, type`:
   ```sql
   SELECT store_id,
          type,
          COALESCE(SUM(amount), 0) AS total,
          MAX(currency)            AS currency
   FROM   ledger_entry
   WHERE  store_id IN (...)
     [AND entry_date >= :from_dt AND entry_date <= :to_dt]
   GROUP  BY store_id, type;
   ```
   Python da iteratsiya hajmi: `N_stores × 2` guruhlovchi satr (barcha `ledger_entry` emas).

2. **Account balance** — kumulativ joriy balans (period filtrisiz):
   ```sql
   SELECT * FROM account_balance WHERE store_id IN (...);
   ```

---

### Dialekt-moslik jadvali

| Operatsiya | SQLite | PostgreSQL |
|---|---|---|
| Kun guruhlash | `strftime('%Y-%m-%d', ordered_at)` | `to_char(ordered_at, 'YYYY-MM-DD')` |
| Hafta guruhlash | `strftime('%Y-W%W', ordered_at)` | `to_char(ordered_at, 'IYYY-"W"IW')` |
| Oy guruhlash | `strftime('%Y-%m', ordered_at)` | `to_char(ordered_at, 'YYYY-MM')` |
| Avg yetkazish vaqti | `(julianday(delivered_at) - julianday(started_at)) * 24 * 60` | `EXTRACT(EPOCH FROM (delivered_at - started_at)) / 60` |
| Dialekt aniqlash | `db.get_bind().dialect.name` → `'sqlite'` | `db.get_bind().dialect.name` → `'postgresql'` |

Dialekt `_get_dialect(db)` orqali aniqlanadi; xato bo'lsa `'sqlite'` fallback qilinadi (test xavfsizligi uchun).

---

### Indekslar (migratsiya `0017`)

| Indeks | Jadval | Ustunlar | Maqsad |
|---|---|---|---|
| `ix_ledger_entry_store_date` | `ledger_entry` | `(store_id, entry_date)` | `finance_stats` `WHERE store_id IN (...) AND entry_date` range — full-scan o'rniga indeks-scan |
| `ix_delivery_assigned_at` | `delivery` | `(assigned_at)` | `delivery_stats` `WHERE assigned_at >= from_dt` vaqt filtri |

Ikkala indeks model `__table_args__` ga ham qo'shilgan — `Base.metadata.create_all` (SQLite in-memory test DB) avtomatik oladi. Migratsiya `alembic upgrade head` orqali real PostgreSQL ga qo'llaniladi.

---

### Scope/IDOR (SQL agregatsiyada o'zgarishsiz)

`total` va `dynamics` so'rovlari bir xil scope WHERE filtrlarini ishlatadi — ikkinchi `SELECT` ga filtrlar nusxalanadi:

| Rol | `sales` scope | `delivery` scope | `finance` scope |
|---|---|---|---|
| `administrator`/`accountant` | Barchasi (`branch_id` ixtiyoriy) | Barchasi (`courier_id` ixtiyoriy) | Barchasi (`branch_id` ixtiyoriy) |
| `agent` | `Order.store_id IN (agent_store_ids)` | JOIN `Order`, `Order.store_id IN (...)` | `LedgerEntry.store_id IN (agent_store_ids)` |
| `store` | `Order.store_id = store_id` | JOIN `Order`, `Order.store_id = store_id` | `LedgerEntry.store_id = store_id` |
| `courier` | Bo'sh (0 qaytaradi) | `Delivery.courier_id = user.id` | **403** (router darajasida) |

---

## Tech-debt: Python agregatsiya → DB GROUP BY

**v0.29.0 da hal qilindi.** Barcha statistika funksiyalari DB darajali agregatsiyaga ko'chirildi. Python-tomon `O(N)` yig'ish yo'q.

Arxiv maqsadida — asl yondashuv (`sales_stats` uchun) quyida:

```sql
-- Avvalgi yondashuv: barcha qatorlar Python ga yuklanib, iteratsiya qilinardi
-- Yangi yondashuv (v0.29.0):
SELECT to_char(ordered_at, 'YYYY-MM') AS period,  -- yoki strftime (SQLite)
       COUNT(*)                        AS order_count,
       COALESCE(SUM(total_amount), 0)  AS total_amount
FROM   "order"
WHERE  deleted_at IS NULL [scope + vaqt filtrlari]
GROUP  BY period
ORDER  BY period;
```
