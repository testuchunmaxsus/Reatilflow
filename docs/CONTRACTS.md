# Shartnoma (Contracts) moduli — texnik qo'llanma

| | |
|---|---|
| **Versiya** | 0.16.0 |
| **Modul** | `app/modules/contracts` |
| **Prefix** | `/contracts` |
| **Migratsiya** | `alembic/versions/0014_contract.py` |
| **Test** | `backend/app/tests/contracts/` (622 jami) |

---

## 1. Endpointlar

| Metod | URL | Ruxsat | Tavsif |
|---|---|---|---|
| `GET` | `/contracts` | view: administrator, accountant, agent, store | Paginated ro'yxat |
| `POST` | `/contracts` | create: administrator, accountant | Yangi shartnoma |
| `GET` | `/contracts/{id}` | view: administrator, accountant, agent, store | Bitta shartnoma |
| `PATCH` | `/contracts/{id}` | edit: administrator, accountant | Qisman yangilash |
| `POST` | `/contracts/{id}/file` | edit: administrator, accountant | Fayl (PDF/rasm) yuklash |
| `DELETE` | `/contracts/{id}` | delete: administrator | Soft-delete |

### RBAC to'liq matritsasi

| Rol | GET ro'yxat | POST yaratish | PATCH yangilash | POST fayl | DELETE |
|---|---|---|---|---|---|
| administrator | ✅ barchasi | ✅ | ✅ | ✅ | ✅ |
| accountant | ✅ barchasi | ✅ | ✅ | ✅ | ✗ |
| agent | ✅ o'z do'konlari | ✗ | ✗ | ✗ | ✗ |
| store | ✅ o'ziniki | ✗ | ✗ | ✗ | ✗ |
| courier | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## 2. So'rov va javob sxemalari

### POST /contracts — ContractCreate

```json
{
  "store_id": "018f1a2b-...",
  "number": "2024/001",
  "valid_from": "2024-01-01",
  "valid_to": "2024-12-31",
  "signed_at": "2024-01-01T10:00:00Z",
  "contract_type": "trade",
  "branch_id": null,
  "client_uuid": "018f1a2b-..."
}
```

| Maydon | Turi | Shart | Tavsif |
|---|---|---|---|
| `store_id` | UUID | majburiy | Do'kon (FK → store) |
| `number` | string (1–100) | majburiy | Shartnoma raqami (store ichida unikal) |
| `valid_from` | date | majburiy | Amal boshlanishi |
| `valid_to` | date | majburiy | Amal tugashi (`>= valid_from`) |
| `signed_at` | datetime UTC | ixtiyoriy | Imzolangan vaqt |
| `contract_type` | string (≤50) | ixtiyoriy | `trade \| employment \| service \| other` |
| `branch_id` | UUID | ixtiyoriy | Filial |
| `client_uuid` | UUID | ixtiyoriy | Idempotentlik kaliti |

### PATCH /contracts/{id} — ContractUpdate

```json
{
  "valid_to": "2025-12-31",
  "version": 1
}
```

`version` majburiy. Qolgan maydonlar ixtiyoriy — faqat berilganlar yangilanadi. Kamida bitta maydon (`version` dan tashqari) bo'lishi shart.

### ContractOut — javob sxemasi

```json
{
  "id": "018f1a2b-...",
  "store_id": "018f1a2b-...",
  "number": "2024/001",
  "file_url": "https://minio.example.com/contracts/018f1a2b-.../2024-001.pdf",
  "signed_at": "2024-01-01T10:00:00Z",
  "valid_from": "2024-01-01",
  "valid_to": "2024-12-31",
  "contract_type": "trade",
  "branch_id": null,
  "client_uuid": null,
  "status": "active",
  "version": 1,
  "created_at": "2024-01-01T10:05:00Z",
  "updated_at": "2024-01-01T10:05:00Z",
  "deleted_at": null
}
```

---

## 3. Status DERIVED modeli

`status` maydoni DB da saqlanmaydi — `valid_to` ga qarab har safar hisoblanadi.

```
bugun = server UTC sanasi

valid_to < bugun              → "expired"
bugun <= valid_to <= bugun+30 → "expiring"
valid_to > bugun+30           → "active"
```

30 kunlik chegara `DEFAULT_EXPIRING_DAYS = 30` konstanta bilan boshqariladi (servis qatlamida).

`GET /contracts?status=active|expiring|expired` filtri DB sana taqqoslash orqali ishlaydi — ORM property emas, indeksdan foydalanadigan `WHERE valid_to ...` sharti.

---

## 4. IDOR va Scope qoidalari

| Rol | Ruxsat etilgan do'konlar |
|---|---|
| administrator | Barchasi |
| accountant | Barchasi |
| agent | `agent_store` jadvalidagi o'z do'konlari (`get_user_store_ids`) |
| store | `store.user_id == current_user.id` bo'lgan do'konlar |

Scope tashqarisidagi shartnoma so'rovida **404** qaytariladi (mavjudlikni oshkor qilmaslik). `IDOR` himoyasi `get_contract()` va `list_contracts()` har ikkalasida ham ishlatiladi.

`create_contract()` da scope: agent/store ruxsat etilmagan `store_id` ga shartnoma yarata olmaydi → 404.

---

## 5. Fayl yuklash (PDF / rasm)

`POST /contracts/{id}/file` — `multipart/form-data`, `file` maydoni.

| Qoida | Tavsif |
|---|---|
| **Magic-byte validatsiya** | PDF: `25 50 44 46` (`%PDF`); JPEG: `FF D8 FF`; PNG: `89 50 4E 47`; WebP: `52 49 46 46` |
| **Maksimal hajm** | 20 MB |
| **SVG/HTML** | Rad etiladi (XSS xavfi) |
| **Content-Type** | Headerga ishonilmaydi — faqat bayt tekshiruvi |

Muvaffaqiyatli yuklashdan keyin `ContractOut.file_url` MinIO URL bilan yangilanadi.

---

## 6. Raqam unikalligi

`(store_id, number)` juftligi bir do'kon ichida unikal bo'lishi shart (`deleted_at IS NULL` qatorlar orasida).

Ikki qatlamli himoya:
1. `_check_number_unique()` — servis darajasi (race dan oldin)
2. `uq_contract_store_number` — PostgreSQL partial unique index (`WHERE deleted_at IS NULL`)

Dublikat → **409** (`contracts.duplicate_number`).

PATCH da number o'zgarganda yangi raqam ham tekshiriladi (`exclude_id` bilan — o'z raqamiga qaytish ruxsat etiladi).

---

## 7. list_expiring — muddati tugayotganlar

```python
await service.list_expiring(db, user=current_user, days=30)
```

`today <= valid_to <= today + days` bo'lgan shartnomalarni `valid_to ASC` tartibida qaytaradi. Scope qoidalari qo'llaniladi.

Bu funksiya hozir to'g'ridan-to'g'ri endpointga ulanmagan — worker yoki push notification xizmati uchun mo'ljallangan (kelajak sprint).

---

## 8. curl misollari

### Shartnoma yaratish

```bash
curl -X POST http://localhost:8000/contracts \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "018f1a2b-0000-7000-8000-000000000001",
    "number": "2024/001",
    "valid_from": "2024-01-01",
    "valid_to": "2024-12-31",
    "contract_type": "trade",
    "client_uuid": "018f1a2b-0000-7000-8000-000000000099"
  }'
```

### Fayl yuklash

```bash
curl -X POST http://localhost:8000/contracts/018f1a2b-.../file \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/contract.pdf"
```

### Ro'yxat — status filtri bilan

```bash
# Muddati tugayotganlar
curl "http://localhost:8000/contracts?status=expiring&limit=50" \
  -H "Authorization: Bearer <token>"

# Muddati o'tganlar, bitta do'kon
curl "http://localhost:8000/contracts?status=expired&store_id=018f1a2b-...&limit=20" \
  -H "Authorization: Bearer <token>"
```

### PATCH

```bash
curl -X PATCH http://localhost:8000/contracts/018f1a2b-... \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"valid_to": "2025-12-31", "version": 1}'
```

---

## 9. Migratsiya

```bash
cd backend
alembic upgrade 0014
# yoki to'liq:
alembic upgrade head
```

`0014_contract.py` downgrade guard: `contract` jadvalida qatorlar bo'lsa `RuntimeError` — tasodifiy ma'lumot yo'qolishini oldini oladi.

---

## 10. Ma'lum cheklovlar (LOW)

| Cheklov | Tavsif |
|---|---|
| Redis idem `ex` vs `nx` | `create_contract()` da `SET ex` ishlatilgan (TTL bilan qayta yozadi); `SET nx` (faqat yangi kalit) emas. Pratikda ta'siri minimal — TTL oynasida bir xil `client_uuid` bilan ikkinchi muvaffaqiyatli create bo'lmaydi, lekin texnik jihatdan `ex` kafolat bermaydi. |
| `signed_at` null ga qaytarish | `ContractUpdate.signed_at = null` holati (null ga reset) hozir qo'llab-quvvatlanmaydi — faqat yangi qiymat o'rnatiladi. Null ga qaytarish kerak bo'lsa alohida endpoint kerak bo'ladi. |
