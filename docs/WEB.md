# RETAIL — Veb SPA texnik qo'llanmasi (T7+)

| | |
|---|---|
| **Versiya** | 0.33.0 |
| **Sana** | 2026-06-19 |
| **Holati** | T7✅ poydevor; T8✅ Katalog/Mijoz sahifalari; ✅ Buyurtma/Statistika sahifalari; ✅ Foydalanuvchilar sahifasi; ✅ Shartnoma/Murojaat/Aksiya sahifalari |
| **Qamrov** | React veb SPA + Tauri desktop qobig'i (8 modul, barcha backend qoplangan) |

---

## 1. Frontend stek

| Kutubxona | Versiya | Rol |
|---|---|---|
| React | 18.3 | UI |
| TypeScript | 5.4 | Tiplar |
| Vite | 5.3 | Build + dev server |
| Mantine | 7.11 | UI komponent kutubxonasi |
| TanStack Query | 5.51 | Server state boshqaruvi |
| React Router | 6.24 | Yo'naltirish |
| i18next | 23.12 | Lokalizatsiya (uz/ru) |
| Tauri | (wrapper) | Desktop qobig'i |
| Vitest | 1.6 | Test ishlatuvchi |
| Testing Library | 16 | Komponent testlari |

---

## 2. Loyiha tuzilishi

```
web/
├── src/
│   ├── api/
│   │   ├── client.ts        # API klient (Bearer, Accept-Language, 401 refresh, upload)
│   │   ├── types.ts         # Qo'lda yozilgan asosiy tiplar (LoginRequest, TokenPair, ...)
│   │   ├── schema.ts        # OpenAPI generatsiya (make gen-client)
│   │   └── index.ts         # Qayta eksport
│   ├── auth/
│   │   ├── AuthContext.tsx  # AuthProvider, useAuth hook
│   │   ├── ProtectedRoute.tsx
│   │   ├── LoginPage.tsx
│   │   └── index.ts
│   ├── rbac/
│   │   ├── usePermissions.ts  # can(), canAny()
│   │   ├── Can.tsx            # <Can permission="..."> komponenti
│   │   └── index.ts
│   ├── i18n/
│   │   ├── index.ts           # i18next sozlamalari
│   │   └── locales/
│   │       ├── uz.json
│   │       └── ru.json
│   ├── layouts/
│   │   └── AppLayout.tsx      # Mantine AppShell (sidebar + header)
│   ├── features/
│   │   ├── catalog/           # T8: Katalog moduli
│   │   │   ├── CatalogListPage.tsx          # Jadval, qidiruv, filtr, pagination
│   │   │   ├── api/catalogApi.ts            # TanStack Query hooks
│   │   │   └── components/
│   │   │       ├── ProductFormModal.tsx     # Yaratish/tahrirlash modali
│   │   │       ├── PriceHistoryModal.tsx    # Narx tarixi modali
│   │   │       └── PhotoUploadModal.tsx     # Rasm yuklash modali
│   │   ├── customers/         # T8: Mijoz bazasi moduli
│   │   │   ├── CustomersListPage.tsx        # Jadval, 3-rejimli qidiruv, PII
│   │   │   ├── api/customersApi.ts          # TanStack Query hooks
│   │   │   └── components/
│   │   │       ├── CustomerFormModal.tsx    # Yaratish/tahrirlash modali
│   │   │       └── AssignAgentModal.tsx     # Agent biriktirish modali
│   │   ├── users/             # v0.31.0: Foydalanuvchilar boshqaruvi
│   │   │   ├── UsersListPage.tsx            # Jadval, rol/holat filtr, pagination
│   │   │   ├── api/usersApi.ts              # TanStack Query hooks
│   │   │   ├── types.ts                     # UserOut, UserRole, UserFilters
│   │   │   └── components/
│   │   │       ├── UserFormModal.tsx        # Yaratish/tahrirlash modali
│   │   │       └── AssignStoreModal.tsx     # Agent→do'kon biriktirish (Select)
│   │   ├── contracts/         # v0.32.0: Shartnomalar boshqaruvi
│   │   │   ├── ContractsListPage.tsx        # Jadval, status filtr, expiring tez-filtri
│   │   │   ├── api/contractsApi.ts          # TanStack Query hooks
│   │   │   ├── types.ts                     # ContractOut, ContractFilters
│   │   │   └── components/
│   │   │       ├── ContractFormModal.tsx    # Yaratish/tahrirlash modali
│   │   │       └── ContractFileUploadModal.tsx  # Fayl yuklash modali
│   │   ├── tickets/           # v0.32.0: Murojaatlar boshqaruvi
│   │   │   ├── TicketsListPage.tsx          # Jadval, status/tur filtr, pagination
│   │   │   ├── api/ticketsApi.ts            # TanStack Query hooks
│   │   │   ├── types.ts                     # TicketOut, TicketStatus, TicketType
│   │   │   └── components/
│   │   │       ├── TicketFormModal.tsx      # Yangi murojaat yaratish modali
│   │   │       └── TicketDetailModal.tsx    # Xabar tarixi + holat mashinasi
│   │   └── promo/             # v0.32.0: Aksiyalar boshqaruvi
│   │       ├── PromoListPage.tsx            # Jadval, is_active/tur filtr, rule_json
│   │       ├── api/promoApi.ts              # TanStack Query hooks
│   │       ├── types.ts                     # PromoOut, PromoFilters, RuleJson
│   │       └── components/
│   │           └── PromoFormModal.tsx       # Yaratish/tahrirlash modali (rule_json, banner)
│   ├── hooks/
│   │   ├── useApiError.ts     # ApiError → Mantine notification
│   │   └── useDebounce.ts     # Debounce (qidiruv inputlari uchun)
│   ├── components/
│   │   └── ConfirmDeleteModal.tsx  # Qayta ishlatiladigan o'chirish tasdiq modali
│   ├── pages/
│   │   ├── DashboardPage.tsx
│   │   └── PlaceholderPage.tsx  # Buyurtma/Statistika sahifalari uchun placeholder
│   ├── tauri.ts               # Tauri ipc wrapper skeleti
│   └── main.tsx               # Ilova kirish nuqtasi, routing
├── package.json
└── vite.config.ts
```

---

## 3. Ishga tushirish

### Talablar

- Node.js >= 20
- `VITE_API_BASE_URL` muhit o'zgaruvchisi (ixtiyoriy; standart: `http://localhost:8000`)

### Buyruqlar

```bash
cd web

# O'rnatish
npm install

# Dev server (http://localhost:5173)
npm run dev

# TypeScript + build tekshiruvi
npm run build

# Testlar
npm test

# Testlar + coverage
npm run test:coverage

# Linting
npm run lint

# TypeScript tiplarni tekshirish (build qilmasdan)
npm run type-check
```

### Tauri desktop

```bash
cd web

# Dev rejim (desktop oyna + hot reload)
npm run tauri dev

# Production build (`.exe`, `.dmg`, `.AppImage`)
npm run tauri build
```

### OpenAPI klient generatsiya

Backend server `http://localhost:8000` da ishlab turgan holda:

```bash
# Loyiha ildizidan
make gen-client

# Faqat TypeScript tiplar (web/src/api/openapi.gen.ts)
cd web && npm run gen-types
```

`make gen-client` buyrug'i `web/src/api/` va `mobile/lib/api/` papkalarini to'ldiradi.

---

## 4. API ulanish

### client.ts asosiy oqimi

```
So'rov yuboriladi
    ↓
Authorization: Bearer <access_token>  (xotirada)
Accept-Language: uz | ru              (localStorage'dan)
    ↓
200-299 → javob qaytariladi
    ↓
401 → refreshAccessToken()
    ├── Mutex: parallel 401 bo'lsa bitta refresh so'rovi, qolganlar kutadi
    ├── POST /auth/refresh { refresh_token }
    │       ↓ 200 → yangi tokenlar saqlash → asl so'rov qayta yuboriladi (1 marta)
    │       ↓ 401 → clearTokens() + retail:auth:logout event
    └── AuthContext event handler → user = undefined → /login ga yo'naltirish
```

### Token saqlash

| Token | Saqlash joyi | Sabab |
|---|---|---|
| `access_token` | Xotira (JS o'zgaruvchi) | XSS da o'g'irlanmaydi |
| `refresh_token` | `localStorage` | Sahifa yangilanishdan omon qolish; Tauri ipc httpOnly cookie'ni qo'llab-quvvatlamaydi |

**Tradeoff eslatmasi:** production veb deployda (Tauri emas) `refresh_token` httpOnly cookie orqali yuborilsa XSS xavfi yo'q bo'ladi. Hozirgi `localStorage` yondashuvi ongli tradeoff — `client.ts` va `AuthContext.tsx` kodida sharhlangan.

### apiClient foydalanish

```typescript
import { apiClient } from "@/api/client";

// GET
const products = await apiClient.get<ProductListResponse>("/catalog/products?limit=20");

// POST
const order = await apiClient.post<OrderOut>("/orders", { store_id, lines });

// PATCH
await apiClient.patch<OrderOut>(`/orders/${id}`, { status: "confirmed" });

// DELETE
await apiClient.delete(`/catalog/products/${id}`);
```

Xato ushlash:

```typescript
import { apiClient, ApiError } from "@/api/client";

try {
  await apiClient.post("/orders", payload);
} catch (err) {
  if (err instanceof ApiError) {
    console.error(err.status, err.envelope.message_key);
    // err.envelope: { message_key, message, detail }
  }
}
```

---

## 5. Auth oqimi

```
Foydalanuvchi login formasini to'ldiradi
    ↓
login(credentials)
    → POST /auth/login { phone, password }
    → setTokens({ access_token, refresh_token })
    → GET /auth/me → AuthUser { id, phone, full_name, role, permissions, ... }
    ↓
AuthUser state ga saqlanadi → ProtectedRoute o'tkazadi

Sahifa yangilanganda (F5):
    → localStorage'da refresh_token bor → POST /auth/refresh
    → yangi access_token → GET /auth/me → sessiya tiklanadi

logout():
    → POST /auth/logout { refresh_token }  (server denylist)
    → clearTokens()
    → user = undefined → /login
```

---

## 6. RBAC-aware UI

RBAC-aware UI elementlari faqat **UX maqsadida** — menyu elementlarini yashirish, tugmalarni o'chirish. Haqiqiy autorizatsiya backend RBAC middleware tomonida bajariladi.

### usePermissions

```typescript
import { usePermissions } from "@/rbac/usePermissions";

function MyComponent() {
  const { role, can, canAny } = usePermissions();

  // Bitta ruxsat tekshiruvi
  if (can("catalog:create")) { /* ... */ }

  // Modulda istalgan amalni tekshirish
  if (canAny("catalog", ["create", "edit"])) { /* ... */ }
}
```

### Can komponenti

```tsx
import { Can } from "@/rbac/Can";

// Ruxsat yo'q bo'lsa — hech narsa ko'rsatilmaydi
<Can permission="catalog:create">
  <Button>Mahsulot qo'shish</Button>
</Can>

// fallback bilan
<Can permission="finance:approve" fallback={<Text c="dimmed">Ruxsat yo'q</Text>}>
  <ApproveButton />
</Can>
```

Ruxsatlar `AuthUser.permissions` dan (`/auth/me` javobi): `["catalog:view", "catalog:create", ...]` formatida.

---

## 7. i18n

- Standart til: `uz`; ikkinchi: `ru`
- Saqlash: localStorage (`i18nextLng`)
- Aniqlash tartibi: `localStorage → navigator`
- `Accept-Language` header: `client.ts` `getCurrentLocale()` funksiyasi `localStorage.getItem("i18nextLng") ?? "uz"` orqali o'qiydi — circular import yo'q

```typescript
import { useTranslation } from "react-i18next";

function MyComponent() {
  const { t, i18n } = useTranslation();

  return (
    <>
      <p>{t("nav.catalog")}</p>
      <button onClick={() => i18n.changeLanguage("ru")}>RU</button>
    </>
  );
}
```

Tarjima fayllari: `web/src/i18n/locales/uz.json`, `web/src/i18n/locales/ru.json`.

---

## 8. Sahifalar va routing

| Yo'l | Komponent | Holat | Ruxsat |
|---|---|---|---|
| `/login` | `LoginPage` | Tayyor | Ochiq |
| `/` | `DashboardPage` | Tayyor | Har kim |
| `/catalog` | `CatalogListPage` | T8✅ Tayyor | `catalog:view` |
| `/customers` | `CustomersListPage` | T8✅ Tayyor | `customers:view` |
| `/orders` | `OrderListPage` | ✅ Tayyor (v0.22.0) | `orders:view` |
| `/stats` | `StatsDashboardPage` | ✅ Tayyor (v0.22.0) | `stats:view` |
| `/users` | `UsersListPage` | ✅ Tayyor (v0.31.0) | `rbac:view` |
| `/contracts` | `ContractsListPage` | ✅ Tayyor (v0.32.0) | `contracts:view` |
| `/tickets` | `TicketsListPage` | ✅ Tayyor (v0.32.0) | `tickets:view` |
| `/promo` | `PromoListPage` | ✅ Tayyor (v0.32.0) | `promo:view` |

`ProtectedRoute` — `user === null` bo'lsa loading, `user === undefined` bo'lsa `/login` ga yo'naltirish.

---

## 9. T8 — Katalog sahifasi

### Xususiyatlar

- Mahsulotlar jadvali (Mantine Table, horizontal scroll container) — rasm thumbnail, nom (lokalizatsiyalangan), SKU, barcode, birlik, holat badge
- Qidiruv — debounce 300ms; qidiruv o'zgarganda sahifa 1 ga qaytadi
- Filtr — `is_active` checkbox, `category_id` select (kategoriyalar TanStack Query orqali)
- Sahifalash — `Pagination` (PAGE_SIZE=20); faqat 1 dan ortiq sahifada ko'rsatiladi
- CRUD modal — `ProductFormModal` (yaratish + tahrirlash, `useCreateProduct`/`useUpdateProduct`)
- Narx tarixi modal — `PriceHistoryModal` (`usePriceHistory`)
- Rasm yuklash modal — `PhotoUploadModal` (`apiClient.upload`)
- O'chirish tasdiq modal — `ConfirmDeleteModal` (`useDeleteProduct`)
- RBAC-aware: `catalog:create` → Qo'shish tugmasi; `catalog:edit` → tahrirlash + rasm; `catalog:delete` → o'chirish

### TanStack Query hooks (`features/catalog/api/catalogApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useProducts(params)` | `GET /catalog/products` | `search`, `is_active`, `category_id`, `limit`, `offset` |
| `useCategories()` | `GET /catalog/categories` | Filtr select uchun |
| `useCreateProduct()` | `POST /catalog/products` | mutation |
| `useUpdateProduct()` | `PATCH /catalog/products/{id}` | mutation |
| `useDeleteProduct()` | `DELETE /catalog/products/{id}` | mutation |
| `usePriceHistory(id)` | `GET /catalog/products/{id}/price-history` | `enabled: !!id` |

---

## 10. T8 — Mijoz sahifasi

### Xususiyatlar

- Do'konlar jadvali — nom, INN (maskalangan), manzil, agent, holat
- 3-rejimli qidiruv: ism / INN / INPS — backend blind-index orqali (`search_name`, `search_inn`, `search_phone` query parametrlari)
- PII yashirish: kuryer rolidagi foydalanuvchi `StoreLimitedOut` javob oladi — INN, INPS, aloqa ma'lumotlari UI da `null` sifatida ko'rsatiladi
- Agent biriktirish modal — `AssignAgentModal`; hozircha qo'lda UUID kiritish (T6 user-select qo'shilguncha)
- CRUD modal — `CustomerFormModal` (yaratish + tahrirlash)
- RBAC-aware: `customers:create` → Qo'shish; `customers:edit` → tahrirlash + agent biriktirish; `customers:delete` → o'chirish

### TanStack Query hooks (`features/customers/api/customersApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useCustomers(params)` | `GET /customers/stores` | `search_name`, `search_inn`, `search_phone`, `limit`, `offset` |
| `useCreateCustomer()` | `POST /customers/stores` | mutation |
| `useUpdateCustomer()` | `PATCH /customers/stores/{id}` | mutation |
| `useDeleteCustomer()` | `DELETE /customers/stores/{id}` | mutation |
| `useAssignAgent()` | `POST /customers/stores/{id}/assign-agent` | mutation |

### Ma'lum cheklov

`AssignAgentModal` da agent UUID qo'lda kiritiladi. T6 user-select komponenti qo'shilguncha bu holat davom etadi. Tuzatish keyingi sprint.

---

## 11. apiClient.upload — multipart so'rovlar

`apiClient.upload(path, formData)` metodi `multipart/form-data` yuklashlar uchun ishlatiladi. Ichki mexanizm `get/post/patch` bilan bir xil — 401 kelganda refresh mutex orqali token yangilanib, so'rov 1 marta qayta yuboriladi.

```typescript
import { apiClient } from "@/api/client";

// Rasm yuklash
const form = new FormData();
form.append("file", file);
const result = await apiClient.upload<{ photo_url: string }>(
  `/catalog/products/${productId}/photo`,
  form
);
```

Xato ushlash `get/post` bilan bir xil — `ApiError` instance qaytaradi.

---

## 12. useApiError va useDebounce

### useApiError

```typescript
import { useApiError } from "@/hooks/useApiError";

function MyComponent() {
  const { showError } = useApiError();

  const handleSubmit = async () => {
    try {
      await someApiCall();
    } catch (err) {
      showError(err); // Mantine notification sifatida ko'rsatadi
    }
  };
}
```

### useDebounce

```typescript
import { useDebounce } from "@/hooks/useDebounce";

const [input, setInput] = useState("");
const debouncedValue = useDebounce(input, 300); // 300ms kechikish

// debouncedValue ni TanStack Query params sifatida ishlatish
const { data } = useProducts({ search: debouncedValue || undefined });
```

---

## 13. Muhit o'zgaruvchilari

| O'zgaruvchi | Standart | Tavsif |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |

`.env` yoki `.env.local` faylda o'rnatiladi:

```
VITE_API_BASE_URL=https://api.retail.example.com
```

---

## 14. Buyurtma sahifasi (`/orders`)

### Xususiyatlar

- Buyurtmalar jadvali (Mantine Table, scroll container) — raqam (UUID 8 belgi), sana, do'kon ID, rejim badge, holat badge, summa
- Filtr: `status` Select (confirmed/packed/delivering/delivered/canceled), `from`/`to` sana inputlari
- Sahifalash — `Pagination` (PAGE_SIZE=20); filtr o'zgarganda sahifa 1 ga qaytadi
- `OrderDetailModal` — buyurtma tafsilot + holat o'zgartirish (`VALID_TRANSITIONS` bo'yicha faol tugmalar)
- `CreateOrderModal` — yangi buyurtma yaratish; klient faqat `store_id` + `lines[]{product_id, qty}` yuboradi
- `OrderStatusBadge` — har holat uchun rang belgisi (Mantine `Badge`)
- RBAC-aware: `orders:create` ruxsati bo'lsa Yangi buyurtma tugmasi ko'rsatiladi (`<Can permission="orders:create">`)

### Buyurtma holat mashinasi UI

`VALID_TRANSITIONS` backend konstantasidan olingan holat o'tish qoidalari UI ga ham tatbiq etiladi — faqat ruxsatli holatlarga o'tish tugmalari ko'rsatiladi:

| Hozirgi holat | Ruxsatli o'tishlar |
|---|---|
| `confirmed` | `packed`, `canceled` |
| `packed` | `delivering`, `canceled` |
| `delivering` | `delivered`, `canceled` |
| `delivered` | — (terminal) |
| `canceled` | — (terminal) |

### Narx server-avtoritar

`CreateOrderModal` da klient `discount` yoki `unit_price` maydoni kirmaydi. Backend `compute_line_discount()` funksiyasi narx va chegirmani `product_price` jadvali + aktiv promo asosida hisoblab qaytaradi. Bu T11 naqshining UI tomonidagi davomi.

### TanStack Query hooks (`features/orders/api/ordersApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useOrders(params)` | `GET /orders` | `status`, `from`, `to`, `limit`, `offset` |
| `useOrder(id)` | `GET /orders/{id}` | `enabled: !!id` |
| `useCreateOrder()` | `POST /orders` | mutation; `store_id` + `lines` |
| `useUpdateOrderStatus()` | `PATCH /orders/{id}/status` | mutation; `status` + `version` |

---

## 15. Statistika dashboard (`/stats`)

### Xususiyatlar

- Davr filtri: `from`/`to` sana inputlari; `group_by` select (kun/hafta/oy) — barcha bo'limlarga qo'llaniladi
- Savdo bo'limi: jami buyurtma va summa `StatCard`; `recharts BarChart` (ikkita o'q: `count` chap, `amount` o'ng; `ResponsiveContainer` 260px balandlik)
- Yetkazish bo'limi: 4 ta `StatCard` (jami/yetkazilgan/muvaffaqiyatsiz/jarayonda); `avg_delivery_minutes`; gorizontal `BarChart` taqsimot grafigi
- Moliyaviy bo'lim: faqat `finance:view` ruxsatiga ega rollarda ko'rsatiladi

### Statistika RBAC ikki qatlam

Moliyaviy bo'lim ikki qatlamda himoyalangan:

1. **UI qatlam**: `<Can permission="finance:view" fallback={null}>` — kuryer moliyaviy bo'limni ko'rmaydi
2. **Query qatlam**: `useFinanceStats(params, canViewFinance)` — `enabled: false` bo'lsa `GET /stats/finance` so'rovi umuman yuborilmaydi
3. **Backend qatlam**: `finance:view` ruxsati yo'q bo'lsa router 403 qaytaradi

### TanStack Query hooks (`features/stats/api/statsApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useSalesStats(params)` | `GET /stats/sales` | `from`, `to`, `group_by` |
| `useDeliveryStats(params)` | `GET /stats/delivery` | `from`, `to` |
| `useFinanceStats(params, enabled)` | `GET /stats/finance` | `enabled` false bo'lsa so'rov yuborilmaydi |

### recharts — bundle hajmi

recharts 993 kB bundle qo'shimchasi mavjud. `React.lazy` + dinamik `import()` bilan kod ajratish (code-splitting) qilinishi kerak. Hozircha to'liq import qilinmoqda — keyingi sprint.

---

## 16. Foydalanuvchilar sahifasi (`/users`)

### Xususiyatlar

- Foydalanuvchilar jadvali (Mantine Table, horizontal scroll) — to'liq ism, telefon (maskalangan), rol badge (rang-kodli), holat badge, filial ID
- Server-side filtrlar: rol (`Select`, 5 variant: administrator/agent/courier/accountant/store) va holat (aktiv/nofaol); filtr o'zgarganda sahifa 1 ga qaytadi
- Sahifalash — `Pagination` (PAGE_SIZE=20); faqat 1 dan ortiq sahifada ko'rsatiladi
- `UserFormModal` — yaratish va tahrirlash (maydonlar: `full_name`, `phone`, `role`, `password`, `branch_id`, `locale`, `biometric_enrolled`)
- `AssignStoreModal` — agent → do'kon biriktirish; do'konlar `GET /customers/stores` dan yuklanadi, `Select` bilan tanlanadi (xom UUID kiritish yo'q)
- Deaktivatsiya: `ConfirmDeleteModal` tasdiq, `PATCH /users/{id}/deactivate`
- Aktivlashtirish: inline (tasdiqsiz), `PATCH /users/{id}/activate`
- RBAC-aware: `rbac:view` — sahifani ko'rish; `rbac:create` — Yaratish tugmasi; `rbac:edit` — tahrirlash, deaktivatsiya/aktivlashtirish, do'kon biriktirish
- PII: telefon UI da maskalanadi — oxirgi 4 raqam ko'rsatiladi, qolganlari `*` (backend hali to'liq qaytaradi, UI muhofaza qatlami)
- i18n: uz/ru

### Ishlatilgan backend endpointlar

| Endpoint | Maqsad |
|---|---|
| `GET /users` | Paginated ro'yxat (`role`, `is_active`, `limit`, `offset`) |
| `POST /users` | Yangi foydalanuvchi yaratish |
| `PATCH /users/{id}` | Tahrirlash (optimistik lock, `version`) |
| `PATCH /users/{id}/deactivate` | Bloklash (`is_active=False`) |
| `PATCH /users/{id}/activate` | Qayta aktivlashtirish (`is_active=True`) |
| `GET /customers/stores` | Do'konlar ro'yxati (`AssignStoreModal` uchun) |
| `POST /customers/stores/{id}/assign-agent` | Agent → do'kon biriktirish |

### TanStack Query hooks (`features/users/api/usersApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useUsers(params)` | `GET /users` | `role`, `is_active`, `limit`, `offset` |
| `useCreateUser()` | `POST /users` | mutation |
| `useUpdateUser()` | `PATCH /users/{id}` | mutation; `version` majburiy |
| `useDeactivateUser()` | `PATCH /users/{id}/deactivate` | mutation |
| `useActivateUser()` | `PATCH /users/{id}/activate` | mutation |

---

## 17. Shartnomalar sahifasi (`/contracts`)

### Xususiyatlar

- Shartnomalar jadvali (Mantine Table, horizontal scroll) — raqam, do'kon ID, tur, amal qilish muddati (valid_from/valid_to), holat badge
- Filtrlar: `status` Select (active/expiring/expired) + "Tugayotgan" tez-murojaat tugmasi (orange, `GET /contracts?expiring=true`)
- `ContractFormModal` — yaratish va tahrirlash
- `ContractFileUploadModal` — shartnoma PDF/DOC faylini yuklash (`apiClient.upload`)
- Status DERIVED: backend `valid_from`/`valid_to` asosida hisoblaydi; UI faqat ko'rsatadi (badge: active=green, expiring=orange, expired=red)
- RBAC-aware: `contracts:view` — sahifani ko'rish; `contracts:create` — Yaratish tugmasi; `contracts:edit` — tahrirlash + fayl yuklash; `contracts:delete` — o'chirish

### Ishlatilgan backend endpointlar

| Endpoint | Maqsad |
|---|---|
| `GET /contracts` | Paginated ro'yxat (`status`, `limit`, `offset`) |
| `POST /contracts` | Yangi shartnoma yaratish |
| `GET /contracts/{id}` | Bitta shartnoma |
| `PATCH /contracts/{id}` | Tahrirlash (`version` majburiy) |
| `POST /contracts/{id}/file` | Fayl yuklash (multipart) |
| `DELETE /contracts/{id}` | O'chirish |

### TanStack Query hooks (`features/contracts/api/contractsApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useContracts(params)` | `GET /contracts` | `status`, `limit`, `offset` |
| `useContract(id)` | `GET /contracts/{id}` | `enabled: !!id` |
| `useCreateContract()` | `POST /contracts` | mutation |
| `useUpdateContract()` | `PATCH /contracts/{id}` | mutation; `version` majburiy |
| `useUploadContractFile()` | `POST /contracts/{id}/file` | mutation; `apiClient.upload` |
| `useDeleteContract()` | `DELETE /contracts/{id}` | mutation |

---

## 18. Murojaatlar sahifasi (`/tickets`)

### Xususiyatlar

- Murojaatlar jadvali (Mantine Table, horizontal scroll) — mavzu, tur badge (taklif/etiroz), holat badge, do'kon ID, yaratilgan sana
- Filtrlar: `status` (new/in_progress/resolved/closed) va `ticket_type` (taklif/etiroz) — alohida Select komponentlar
- `TicketFormModal` — yangi murojaat yaratish
- `TicketDetailModal` — xabar tarixi ro'yxati + yangi xabar yuborish (`POST /tickets/{id}/messages`) + holat mashinasi (`PATCH /tickets/{id}/status`)
- Holat badge ranglari: new=blue, in_progress=orange, resolved=green, closed=gray
- RBAC scope: admin/accountant barcha murojaatlarni ko'radi; boshqa rollar faqat o'zinikini (backend RBAC scope)
- RBAC-aware: `tickets:view` — sahifani ko'rish; `tickets:create` — Yaratish tugmasi; `tickets:edit` — holat o'zgartirish

### Ishlatilgan backend endpointlar

| Endpoint | Maqsad |
|---|---|
| `GET /tickets` | Paginated ro'yxat (`status`, `ticket_type`, `limit`, `offset`) |
| `POST /tickets` | Yangi murojaat yaratish |
| `GET /tickets/{id}` | Bitta murojaat (xabarlar bilan) |
| `POST /tickets/{id}/messages` | Yangi xabar qo'shish |
| `PATCH /tickets/{id}/status` | Holat o'zgartirish |

### TanStack Query hooks (`features/tickets/api/ticketsApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `useTickets(params)` | `GET /tickets` | `status`, `ticket_type`, `limit`, `offset` |
| `useTicket(id)` | `GET /tickets/{id}` | `enabled: !!id` |
| `useCreateTicket()` | `POST /tickets` | mutation |
| `useSendMessage()` | `POST /tickets/{id}/messages` | mutation |
| `useUpdateTicketStatus()` | `PATCH /tickets/{id}/status` | mutation |

---

## 19. Aksiyalar sahifasi (`/promo`)

### Xususiyatlar

- Aksiyalar jadvali (Mantine Table, horizontal scroll) — nom (lokalizatsiyalangan), tur badge (discount/bonus/gift), chegirma (`rule_json` dan: `discount_percent` → `N%`, `discount_amount` → `N UZS`, `min_qty`), amal qilish muddati, faollik badge (dot: green/gray)
- Filtrlar: `is_active` (barchasi/faqat faol/faqat nofaol) va `promo_type` — alohida Select komponentlar
- `PromoFormModal` — yaratish va tahrirlash:
  - `rule_json`: `discount_percent` yoki `discount_amount` + ixtiyoriy `min_qty`
  - `target`: segment `Select` (`GET /catalog/price-segments`) va product `Select` (`GET /catalog/products`)
  - Banner yuklash: `POST /promos/{id}/banner` (`apiClient.upload`)
  - `is_active` checkbox, `valid_from`/`valid_to` TextInput (YYYY-MM-DD)
- Discount server-avtoritar: UI `compute_line_discount()` ni chaqirmaydi — buyurtma yaratilganda backend narxni hisoblaydi
- RBAC-aware: `promo:view` — sahifani ko'rish; `promo:create` — Yaratish; `promo:edit` — tahrirlash; `promo:delete` — o'chirish

### Ishlatilgan backend endpointlar

| Endpoint | Maqsad |
|---|---|
| `GET /promos` | Paginated ro'yxat (`is_active`, `promo_type`, `limit`, `offset`) |
| `GET /promos/active` | Faqat faol aksiyalar (buyurtma ekrani uchun) |
| `POST /promos` | Yangi aksiya yaratish |
| `GET /promos/{id}` | Bitta aksiya |
| `PATCH /promos/{id}` | Tahrirlash (`version` majburiy) |
| `POST /promos/{id}/banner` | Banner rasm yuklash (multipart) |
| `DELETE /promos/{id}` | O'chirish |
| `GET /catalog/price-segments` | Segment `Select` uchun variantlar |
| `GET /catalog/products` | Product `Select` uchun variantlar |

### TanStack Query hooks (`features/promo/api/promoApi.ts`)

| Hook | Endpoint | Eslatma |
|---|---|---|
| `usePromos(params)` | `GET /promos` | `is_active`, `promo_type`, `limit`, `offset` |
| `useActivePromos()` | `GET /promos/active` | faol aksiyalar ro'yxati |
| `usePromo(id)` | `GET /promos/{id}` | `enabled: !!id` |
| `useCreatePromo()` | `POST /promos` | mutation |
| `useUpdatePromo()` | `PATCH /promos/{id}` | mutation; `version` majburiy |
| `useUploadPromoBanner()` | `POST /promos/{id}/banner` | mutation; `apiClient.upload` |
| `useDeletePromo()` | `DELETE /promos/{id}` | mutation |

### Date picker eslatmasi

`valid_from`/`valid_to` maydonlari `TextInput` (YYYY-MM-DD) bilan amalga oshirilgan. `@mantine/dates` v7.x React 19 talab qiladi; loyiha React 18 ishlatadi. React 19 ga o'tganda yoki `@mantine/dates` mos versiyasi chiqqanda `DatePickerInput` ga almashtirish mumkin. Bu cheklov `ContractFormModal` (valid_from/valid_to) uchun ham amal qiladi.

---

## 20. recharts Code-Split (v0.33.0)

`StatsDashboardPage` ilgari recharts kutubxonasini to'liq import qilar edi — bu asosiy bundle hajmini ~566 kB ga yetkazardi.

### O'zgarish

`React.lazy` + dinamik `import()` bilan `StatsDashboardPage` alohida lazy chunk ga ajratildi:

```tsx
// web/src/main.tsx (yoki routing fayli)
const StatsDashboardPage = React.lazy(
  () => import("./features/stats/StatsDashboardPage")
);

// Ishlatilishi:
<Suspense fallback={<Loader />}>
  <StatsDashboardPage />
</Suspense>
```

`vite.config.ts` `manualChunks` sozlamasi:
```ts
manualChunks: {
  recharts: ["recharts"],
}
```

### Natija

| | Avval | Keyin |
|---|---|---|
| Asosiy bundle | ~566 kB | ~210 kB |
| recharts chunk | (asosiy bundle ichida) | alohida lazy chunk |
| Yuklash | Har sahifada | Faqat `/stats` da |

---

## 21. React 18-mos DateInput (v0.33.0)

`@mantine/dates@7.17.8` — React 18 bilan mos keluvchi versiya chiqdi. Promo va Shartnoma forma modallarida `valid_from`/`valid_to` maydonlari `TextInput` (YYYY-MM-DD) dan `DateInput` ga o'zgartirildi.

```tsx
import { DateInput } from "@mantine/dates";

<DateInput
  label="Boshlanish sanasi"
  value={form.values.valid_from}
  onChange={(date) => form.setFieldValue("valid_from", date)}
  valueFormat="YYYY-MM-DD"
/>
```

Avvalgi cheklov (v0.32.0 `Notes` bo'limida qayd etilgan — `@mantine/dates` v7.x React 19 talab qiladi) `@mantine/dates@7.17.8` bilan bartaraf etildi.

---

## 22. Timezone utility — UTC+5 off-by-one tuzatildi (v0.33.0)

### Muammo

`Date.toISOString()` har doim UTC vaqtini qaytaradi. UTC+5 muhitida kechki soatlarda (`toISOString()` bilan olingan) sana bir kun orqaga siljishi mumkin edi. Bu buyurtmalar, statistika, shartnomalar va aksiyalar sana filtrlarida noto'g'ri qiymatlarni yuborgan.

### Yechim

`web/src/utils/date.ts` fayliga ikkita yordamchi funksiya qo'shildi:

```typescript
/**
 * Date ob'ektidan mahalliy sana komponentlarini oladi (YYYY-MM-DD).
 * toISOString() dan foydalanmaydi — UTC siljishidan qochish uchun.
 */
export function toLocalYMD(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/**
 * "YYYY-MM-DD" satrini mahalliy sana sifatida tahlil qiladi.
 * new Date("YYYY-MM-DD") UTC kuni qaytaradi — UTC siljishi muammo.
 * Shu sababli komponentlarga bo'lib tahlil qilinadi.
 */
export function parseYMD(str: string): Date {
  const [y, m, d] = str.split("-").map(Number);
  return new Date(y, m - 1, d);
}
```

Barcha `from`/`to` sana inputlari (Buyurtmalar, Statistika, Shartnomalar, Aksiyalar) ushbu funksiyalar orqali normallashtirildi.

---

## 23. Keyingi: production hardening

Veb admin paneli barcha 8 backend modulini qoplaydi. v0.33.0 da recharts code-split va date picker yakunlandi. Qolgan:
- Integratsiya testlari: real Postgres/jonli infra
- Pilot deploy (1-2 distribyutor)
