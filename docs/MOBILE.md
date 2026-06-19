# RETAIL — Flutter Mobil Ilovasi (T14 offline-first yadrosi)

| | |
|---|---|
| **Versiya** | 0.33.0 |
| **Sana** | 2026-06-19 |
| **Holat** | T14✅ T21✅ T20✅ gate PASS (128 test, flutter analyze toza) — **Mobil yakunlandi** |
| **Qamrov** | Offline-first yadro + Agent ekranlari (dashboard, do'konlar, katalog, buyurtma, davomat, GPS) + Kuryer ekranlari (yetkazishlar, holat mashinasi, GPS, proof_photo) |

---

## 1. Flutter steki

| Paket | Versiya | Vazifasi |
|---|---|---|
| `drift` | `^2.18.0` | SQLite ORM — offline lokal baza |
| `sqlite3_flutter_libs` | `^0.5.0` | SQLite native kutubxona |
| `dio` | `^5.4.0` | HTTP klient (sync push/pull) |
| `flutter_riverpod` | `^2.5.0` | Holat boshqaruvi |
| `riverpod_annotation` | `^2.3.0` | Riverpod kod generatsiyasi |
| `go_router` | `^14.0.0` | Deklarativ navigatsiya |
| `flutter_secure_storage` | `^9.0.0` | Token — iOS Keychain / Android Keystore |
| `connectivity_plus` | `^6.0.0` | Tarmoq holati banneri |
| `uuid` | `^4.4.0` | `client_uuid` idempotentlik uchun |
| `json_annotation` | `^4.9.0` | JSON serialization |

Dev paketlar: `drift_dev`, `build_runner`, `riverpod_generator`, `json_serializable`, `mocktail`.

---

## 2. Loyiha tuzilishi

```
mobile/lib/
├── core/
│   ├── config/
│   │   └── app_config.dart       # API_BASE_URL dart-define orqali
│   └── router/
│       └── app_router.dart       # go_router marshrutlari
│
├── data/
│   ├── local/
│   │   ├── database.dart         # AppDatabase (Drift, 7 jadval)
│   │   ├── database_provider.dart
│   │   ├── tables/               # Drift jadval ta'riflari
│   │   │   ├── products_table.dart
│   │   │   ├── price_segments_table.dart
│   │   │   ├── stores_table.dart
│   │   │   ├── orders_table.dart
│   │   │   ├── outbox_table.dart
│   │   │   └── sync_cursor_table.dart
│   │   └── dao/                  # Data Access Objects
│   │       ├── products_dao.dart
│   │       ├── stores_dao.dart
│   │       ├── orders_dao.dart
│   │       ├── outbox_dao.dart
│   │       └── sync_cursor_dao.dart
│   │
│   ├── remote/
│   │   ├── api_client.dart       # dio + AuthInterceptor
│   │   ├── auth_interceptor.dart # 401 → refresh → retry
│   │   ├── token_storage.dart    # TokenStorage abstraktsiya
│   │   └── models/
│   │       ├── auth_models.dart
│   │       └── sync_models.dart  # SyncPushRequest/Response, ChangeItem
│   │
│   └── sync/
│       ├── sync_service.dart     # SyncService (push + pull)
│       └── sync_notifier.dart    # Riverpod notifier
│
└── features/
    ├── auth/
    │   ├── auth_repository.dart
    │   ├── auth_providers.dart
    │   └── login_screen.dart
    ├── home/
    │   ├── home_shell.dart
    │   ├── sync_providers.dart
    │   └── connectivity_banner.dart
    └── orders/
        ├── order_repository.dart  # Atomik offline buyurtma
        └── orders_providers.dart
```

---

## 3. Offline-first arxitektura

**Asosiy tamoyil**: UI hech qachon to'g'ridan-to'g'ri tarmoqqa murojaat qilmaydi. Barcha o'qish lokal Drift bazasidan, barcha yozish lokal + outbox orqali.

```
UI (Flutter widget)
  │
  ▼
Lokal Drift SQLite baza   ◄──── SyncService (pull) ◄──── Backend
  │
  ▼ (mutatsiya)
Lokal orders + order_lines + outbox_queue  ──► SyncService (push) ──► Backend
```

**Oqim:**
1. Foydalanuvchi buyurtma yaratadi — `OrderRepository.createOrder()` bitta tranzaksiyada lokal saqlaydi.
2. UI darhol natijani ko'radi (`syncStatus = 'pending'`).
3. `SyncService.push()` fonida outbox dan serverga yuboradi.
4. Server `applied` qaytarsa — `order.server_id` yangilanadi, `syncStatus = 'synced'`.
5. `SyncService.pull()` serverdan yangi o'zgarishlarni tortadi — katalog, do'konlar, holat yangilanishi.

---

## 4. SyncService oqimi

### Push

```
outbox_queue WHERE status='pending'
  → batch (max 50)
  → POST /sync/push { ops: [{op_type, client_uuid, payload}] }
  → natija har op uchun:
      applied   → outbox.status='applied'; order.server_id yangilanadi
      duplicate → outbox.status='duplicate' (idempotent, ikki marta yaratilmaydi)
      conflict  → outbox.status='conflict' + message_key
      error     → outbox.status='error' + attempts++
```

### Pull

```
sync_cursors.last_seq  (0 = birinchi pull)
  → GET /sync/pull?since={seq}
  → response.changes[] → entity_type bo'yicha upsert:
      'product' | 'catalog' → products jadvali
      'store'               → stores jadvali
      'order'               → orders jadvali (holat yangilash)
  → sync_cursors.last_seq = response.next_cursor
  → response.has_more = true bo'lsa takrorla
```

**Moslik**: backend `docs/SYNC.md` da tasvirlangan `POST /sync/push` va `GET /sync/pull` endpointlari bilan to'liq mos.

---

## 5. Atomik offline buyurtma (OrderRepository)

`createOrder()` BITTA SQLite tranzaksiyasi ichida uchta yozuv amalga oshiradi:

```dart
await _db.transaction(() async {
  // 1. orders ga
  await _ordersDao.insertOrder(OrdersCompanion.insert(
    id: orderId,
    clientUuid: clientUuid,
    syncStatus: const Value('pending'),
    // ...
  ));

  // 2. order_lines ga (har qator uchun)
  for (final line in lines) {
    await _ordersDao.insertLine(OrderLinesCompanion.insert(...));
  }

  // 3. outbox_queue ga — server kutgan format
  await _outboxDao.insertOp(OutboxQueueCompanion.insert(
    opType: 'order.create',
    clientUuid: clientUuid,
    payload: jsonEncode({
      'store_id': storeId,
      'mode': mode,
      'currency': currency,
      'lines': [{'product_id': ..., 'qty': ...}],
    }),
  ));
});
```

**Muhim**: outbox payload da `discount` maydoni yo'q — narx server-avtoritar (backend `compute_line_discount()`, T11/T25 naqshi). Klient faqat `store_id`, `mode`, `currency`, `lines[]{product_id, qty}` yuboradi.

---

## 6. Auth (secure_storage + 401→refresh)

**TokenStorage**: `flutter_secure_storage` orqali:
- iOS — Keychain, `KeychainAccessibility.first_unlock_this_device`
- Android — EncryptedSharedPreferences (AES-256)

**AuthInterceptor** (dio interceptor):
- Har so'rovga `Authorization: Bearer <access_token>` qo'shiladi.
- 401 kelganda: `/auth/refresh` so'rovi → yangi token saqlash → asl so'rov 1 marta qayta yuboriladi.
- Parallel 401 holati: birinchi 401 refresh boshlaydi, qolganlar navbatga tushadi; refresh tugagach hammasi qayta yuboriladi.
- Refresh ham 401 bo'lsa: `onLogout()` chaqiriladi, foydalanuvchi login ekraniga yo'naltiriladi.
- `/auth/login`, `/auth/refresh`, `/auth/logout` interceptordan o'tkazilmaydi.

---

## 7. ConnectivityBanner

Offline bo'lganda ekran tepasida axborot banneri ko'rsatiladi. UI bloklanmaydi — lokal ma'lumotlar har doim ko'rinadi.

```dart
// Offline aniqlash:
final isOffline = results.every((r) => r == ConnectivityResult.none);
```

---

## 8. Ishga tushirish

### Talablar

- Flutter `>=3.22.0` (`flutter --version` bilan tekshiring)
- Dart `>=3.4.0`
- Android Studio / Xcode (simulyator uchun)

### 1. Paketlarni o'rnatish

```bash
cd mobile
flutter pub get
```

### 2. Drift va Riverpod kod generatsiyasi

```bash
dart run build_runner build --delete-conflicting-outputs
```

Bu buyruq `database.g.dart`, DAO `.g.dart`, `sync_models.g.dart` va boshqa generated fayllarni yaratadi. Har schema o'zgarganda qayta ishlatiladi.

### 3. Testlar

```bash
flutter test
# Natija: 29/29 test passed
```

### 4. Ilovani ishga tushirish

Avval backend ishlaayotgan bo'lishi kerak (`http://localhost:8000`).

```bash
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

Fizik qurilma yoki emulyator uchun backend URL ni moslashtiring:

```bash
# Android emulyator (host machine = 10.0.2.2)
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# iOS simulator
flutter run --dart-define=API_BASE_URL=http://localhost:8000

# Fizik qurilma (lokal tarmoq IP)
flutter run --dart-define=API_BASE_URL=http://192.168.1.100:8000
```

### 5. Release build

```bash
# Android APK
flutter build apk --dart-define=API_BASE_URL=https://api.retail.example.com

# Android App Bundle
flutter build appbundle --dart-define=API_BASE_URL=https://api.retail.example.com

# iOS
flutter build ios --dart-define=API_BASE_URL=https://api.retail.example.com
```

---

## 9. Drift schema versiyasi

`AppDatabase.schemaVersion = 1`. Schema o'zgarganda:

```dart
onUpgrade: (Migrator m, int from, int to) async {
  if (from < 2) {
    await m.addColumn(orders, orders.someNewColumn);
  }
},
```

Va `schemaVersion` ni `2` ga oshiring. `build_runner build` qayta ishlatilishi kerak.

---

## 10. Agent ekranlari (T21)

T21 `features/` papkasiga quyidagi ekranlarni qo'shdi.

### BottomNavigationBar

Besh tab: Dashboard, Do'konlar, Katalog, Buyurtmalar, Davomat.

### Dashboard

Agent uchun umumiy ko'rinish: bugungi buyurtmalar soni, do'konlar soni, sync holati banneri.

### Do'konlar ro'yxati va detali

Lokal Drift `stores` jadvalidan o'qiladi — agent-scope (faqat agentga biriktirilgan do'konlar sinx orqali tortiladi). `StoreDetailScreen` — do'kon ma'lumotlari va buyurtma yaratish havolasi.

### Katalog (offline qidiruv)

Lokal Drift `products` jadvalidan `watchProducts(query)` stream orqali real-time qidiruv. Offline holatda ham ishlaydi. Barcode scanner keyingi sprint uchun placeholder.

### Offline buyurtma yaratish (T11 narx himoyasi)

`OrderRepository.createOrder()` ustiga qurilgan UI. Mahsulot tanlash, miqdor kiritish, tasdiqlash. Outbox payload:

```json
{
  "store_id": "<uuid>",
  "mode": "order",
  "currency": "UZS",
  "lines": [
    { "product_id": "<uuid>", "qty": 2 }
  ]
}
```

`discount` va `unit_price` yo'q — narx va chegirma faqat backend `compute_line_discount()` tomonida hisoblanadi (T11/T25 naqshi).

### Buyurtma ro'yxati

`watchOrders()` Drift stream. `sync_status` badge: `pending` (sariq), `synced` (yashil), `error` (qizil). Real-time yangilanadi.

### Davomat ekrani (`BiometricService` / `GpsService` abstraktsiya)

```
AttendanceScreen
  ├── BiometricService.authenticate()   ← local_auth (Face ID / Touch ID)
  ├── GpsService.getCurrentPosition()  ← geolocator
  └── AttendanceRepository
        ├── checkIn(biometricVerified, gpsPosition)
        │     → outbox: attendance.check_in
        ├── checkOut(gpsPosition)
        │     → outbox: attendance.check_out
        └── ingestGps(position)         ← faqat isCheckedIn=true (ADR §3.7)
              → outbox: gps.ingest
```

**`BiometricService`** — `local_auth` paketini o'raydigan abstraktsiya. `authenticate()` → `bool`. Biometrik namuна yoki xesh serverga bormaydi; faqat `biometric_verified: true` bayroq outbox payloadga yoziladi.

**`GpsService`** — `geolocator` paketini o'raydigan abstraktsiya. `getCurrentPosition()` → `GpsPosition?`. GPS koordinata `gps_lat`/`gps_lng` sifatida outbox payloadga yoziladi.

**Xato turlari:**

| Xato | Sabab |
|---|---|
| `BiometricRequiredException` | `biometricVerified=false` bilan `checkIn()` chaqirilgan |
| `AlreadyCheckedInException` | Allaqachon aktiv kirish mavjud |
| `NotCheckedInException` | `checkOut()` yoki `ingestGps()` kirish bo'lmasdan chaqirilgan |

### GPS tracking (ish vaqtida, ADR §3.7)

`ingestGps()` faqat `isCheckedIn=true` bo'lganda outbox'ga `gps.ingest` yozadi. Check-out bo'lgandan keyin metod darhol qaytadi — GPS yozilmaydi. Bu ADR §3.7 talabini bajaradi: GPS faqat ish vaqti oynasida (`check_in_at`–`check_out_at`) saqlanadi.

---

## 11. Ma'lum cheklovlar

| Cheklov | Holat |
|---|---|
| ~~`local_auth` production implementation~~ | **✅ Hal qilindi (v0.33.0 — real `local_auth` paketi)** |
| ~~`geolocator` production implementation~~ | **✅ Hal qilindi (v0.33.0 — real `geolocator` paketi)** |
| ~~Barcode scanner placeholder~~ | **✅ Hal qilindi (v0.33.0 — `mobile_scanner` paketi)** |
| `AttendanceRepository._currentRecord` xotira holati | Ilova qayta ishga tushirilganda yo'qoladi; SQLite persistence kelajak |
| Real qurilmada smoke-test | Native paketlar real Android/iOS qurilmada hali sinalmagan |

---

## 12. Kuryer ekranlari (T20)

T20 `features/delivery/` papkasiga quyidagi ekranlarni qo'shdi.

### BottomNavigationBar

Ikki tab: Dashboard, Yetkazishlar.

### Kuryer dashboard

Bugungi faol yetkazishlar soni, yetkazilganlar soni, sync holati banneri.

### Yetkazishlar ro'yxati

`DeliveryRepository.watchAll()` / `watchActive()` Drift stream. Holat badge:

| Holat | Rang |
|---|---|
| `assigned` | kulrang |
| `started` | ko'k |
| `delivering` | to'q sariq |
| `delivered` | yashil |
| `failed` | qizil |

### Holat mashinasi UI (server-avtoritar VALID_TRANSITIONS)

`DeliveryDetailScreen` — joriy holat bo'yicha faqat ruxsat etilgan tugmalar ko'rsatiladi:

```
assigned    → [started] [failed]
started     → [delivering] [failed]
delivering  → [delivered] [failed]
delivered   → (terminal, tugmalar yo'q)
failed      → (terminal, tugmalar yo'q)
```

`DeliveryRepository.updateStatus()` chaqirilganda lokal Drift + `outbox_queue` BITTA amalda yangilanadi. `version` optimistik lock payload ichida. Server `422` qaytarsa `outbox.status='conflict'` belgilanadi.

### GPS tracking (45s, faol yetkazishda)

`DeliveryRepository.ingestGps()` — faqat `kGpsActiveStatuses = {started, delivering}` holatida chaqiriladi:

```dart
// Har 45 soniyada (faol yetkazish vaqtida):
await deliveryRepository.ingestGps(
  deliveryId: id,
  position: GpsPosition(lat: lat, lng: lng),
);
// Terminal holatda yoki assigned da — metod darhol qaytadi (GPS yozilmaydi)
```

GPS payload da `delivery_id` mavjud — backend T17 GPS moduli `GpsPoint.delivery_id` reference bilan saqlaydi.

### proof_photo (dio multipart, 401-refresh)

```dart
// Rasm tanlash (image_picker qo'shilgandan keyin):
final photoUrl = await deliveryRepository.uploadProofPhoto(
  id: deliveryId,
  imagePath: '/path/to/image.jpg',
);
// POST /delivery/{id}/proof-photo — multipart/form-data
// AuthInterceptor: 401 → /auth/refresh → retry (1 marta)
```

**Eslatma**: `image_picker` paketi hozir `pubspec.yaml` da yo'q (camera stub). Ishlatish uchun `image_picker: ^1.1.0` qo'shing.

### `deliveries` Drift jadvali (schemaVersion 2)

`AppDatabase.schemaVersion` `1` dan `2` ga ko'tarildi. `onUpgrade` migratsiya:

```dart
onUpgrade: (Migrator m, int from, int to) async {
  if (from < 2) {
    await m.createTable(deliveries);
  }
},
```

`dart run build_runner build --delete-conflicting-outputs` schema o'zgartirilgandan keyin qayta ishlatilishi kerak.

---

## 13. Ma'lum cheklovlar (T20)

| Cheklov | Holat |
|---|---|
| ~~`local_auth` production implementation~~ | **✅ Hal qilindi (v0.33.0)** |
| ~~`geolocator` production implementation~~ | **✅ Hal qilindi (v0.33.0)** |
| ~~Camera / `image_picker` stub~~ | **✅ Hal qilindi (v0.33.0 — `image_picker` paketi)** |
| ~~Barcode scanner placeholder~~ | **✅ Hal qilindi (v0.33.0 — `mobile_scanner` paketi)** |
| `build_runner` `.g.dart` regen | Schema o'zgartirilganda qayta ishlatish kerak |
| `AttendanceRepository._currentRecord` xotira holati | Ilova qayta ishga tushirilganda yo'qoladi; SQLite persistence kelajak |
| Real qurilmada smoke-test | Native paketlar real Android/iOS qurilmada hali sinalmagan |

---

---

## 14. Native paketlar (v0.33.0)

v0.33.0 da `BiometricService`, `GpsService`, `DeliveryRepository.uploadProofPhoto()` va barcode scanner stub implementatsiyalardan real native paketlarga o'tkazildi. **Interfeyslari o'zgarmadi** — ichki implementatsiya almashtirildi. 128 test va `flutter analyze` o'zgarmasdan o'tdi.

### O'rnatilgan paketlar

| Paket | Maqsad | Eslatma |
|---|---|---|
| `local_auth` | Biometrik autentifikatsiya — Face ID / Touch ID | `BiometricService.authenticate()` |
| `geolocator` | GPS koordinatalar | `GpsService.getCurrentPosition()` |
| `image_picker` | proof_photo — kamera yoki galereya | `DeliveryRepository.uploadProofPhoto()` |
| `mobile_scanner` | Barcode skaner | Katalog ekranida ishlatiladi |

### Ruxsatlar

**Android (`android/app/src/main/AndroidManifest.xml`):**

```xml
<!-- Biometrika -->
<uses-permission android:name="android.permission.USE_BIOMETRIC"/>
<uses-permission android:name="android.permission.USE_FINGERPRINT"/>
<!-- GPS -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
<!-- Kamera (image_picker + mobile_scanner) -->
<uses-permission android:name="android.permission.CAMERA"/>
```

**iOS (`ios/Runner/Info.plist`):**

```xml
<key>NSFaceIDUsageDescription</key>
<string>Kirish uchun Face ID ishlatiladi</string>
<key>NSLocationWhenInUseUsageDescription</key>
<string>GPS joylashuv ish vaqtida kuzatiladi</string>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>GPS joylashuv ish vaqtida kuzatiladi</string>
<key>NSCameraUsageDescription</key>
<string>Yetkazish fotosini olish uchun kamera kerak</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>Yetkazish fotosini tanlash uchun galereya kerak</string>
```

### Graceful fallback

Har bir servis ruxsat berilmagan yoki qurilmada mavjud bo'lmagan holatni boshqaradi:

| Holat | Xulq |
|---|---|
| Biometrika qurilmada yo'q | `BiometricService.authenticate()` → `false`; check-in `BiometricRequiredException` |
| GPS ruxsat berilmagan | `GpsService.getCurrentPosition()` → `null`; GPS ingest o'tkazib yuboriladi |
| Kamera ruxsat berilmagan | `uploadProofPhoto()` IOException → `DeliveryRepository` xatoni qaytaradi |
| Barcode ruxsati yo'q | Scanner ekranida ruxsat so'rash dialogi |

### Interfeys o'zgarmaganligini tekshirish

Quyidagi interfeyslar v0.33.0 da o'zgarmadi:

```dart
// BiometricService
abstract class BiometricService {
  Future<bool> authenticate();
}

// GpsService
abstract class GpsService {
  Future<GpsPosition?> getCurrentPosition();
}

// DeliveryRepository (uploadProofPhoto imzosi)
Future<String> uploadProofPhoto({
  required String id,
  required String imagePath,
});
```

Mavjud testlar mock implementatsiya orqali ishlaveradi — real paket testlarda chaqirilmaydi.

---

> Backend sync endpointlari: [docs/SYNC.md](SYNC.md)
> Buyurtma yadrosi (backend): [docs/ORDERS.md](ORDERS.md)
> Davomat (backend): [docs/ATTENDANCE.md](ATTENDANCE.md)
> GPS (backend): [docs/GPS.md](GPS.md)
> Yetkazish (backend): [docs/DELIVERY.md](DELIVERY.md)
