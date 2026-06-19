# Observability — T27 texnik qo'llanmasi

| | |
|---|---|
| **Versiya** | 0.26.0 |
| **Sana** | 2026-06-18 |
| **Modul** | `backend/app/core/` — `logging_config.py`, `middleware.py`, `metrics.py`, `telemetry.py` |

---

## 1. Strukturalangan JSON logging

### Format

Har log yozuvi bitta JSON qatorida chiqadi:

```json
{
  "timestamp": "2026-06-18T10:23:45.123456Z",
  "level": "INFO",
  "logger": "app.core.middleware",
  "message": "request_end",
  "correlation_id": "019333ab-0000-7000-8000-abcdef012345",
  "http_method": "POST",
  "http_path": "/orders",
  "http_status": 201,
  "duration_ms": 34.5
}
```

Maydonlar:

| Maydon | Turi | Tavsif |
|---|---|---|
| `timestamp` | ISO 8601 UTC | `2026-06-18T10:23:45.123456Z` |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | string | Python logger nomi (`app.modules.orders.service`) |
| `message` | string | Log matni |
| `correlation_id` | string \| null | X-Request-ID dan; request tashqarisida `null` |
| `exc_info` | string | Exception stack trace (faqat xato bo'lsa) |
| `...extra` | any | `logger.info("msg", extra={"key": val})` orqali qo'shiladi |

### PII maskalash

`JsonFormatter._sanitize()` quyidagi kalit nomlarini `"***"` ga almashtiradi:

```
inn, inps, phone, full_name, password, password_hash, token,
access_token, refresh_token, owner_name, secret, jwt_secret_key,
pii_encryption_key, blind_index_key, api_key, authorization
```

Maskalash faqat yuqori darajadagi kalit nomlarida ishlaydi (nested dict ichida emas). Nested PII ni logdan chiqarmaslik uchun `extra` ga faqat talab qilingan maydonlarni bering.

### Sozlash

`setup_logging()` ilova ishga tushganda bir marta chaqiriladi (`main.py` lifespan):

```python
from app.core.logging_config import setup_logging
setup_logging(settings.log_level)  # "INFO" | "DEBUG" | "WARNING"
```

`LOG_LEVEL` env o'zgaruvchisi orqali boshqariladi (standart: `INFO`).

---

## 2. Correlation ID oqimi

### Qanday ishlaydi

1. Klient `X-Request-ID: <uuid>` header yuborsa — o'sha qiymat ishlatiladi.
2. Header yo'q bo'lsa — `CorrelationIdMiddleware` UUID v7 generatsiya qiladi.
3. Qiymat `correlation_id_var` (ContextVar) ga yoziladi.
4. Barcha log yozuvlarida `"correlation_id"` maydoni avtomatik tushadi.
5. Javob headerida `X-Request-ID` qaytariladi.

### Misol

```
Klient → POST /orders   X-Request-ID: my-trace-id-123
Server  → 201 Created   X-Request-ID: my-trace-id-123

JSON log:
{"message": "request_start", "correlation_id": "my-trace-id-123", ...}
{"message": "request_end",   "correlation_id": "my-trace-id-123", "http_status": 201, ...}
```

### ContextVar import

```python
from app.core.logging_config import correlation_id_var

# So'rov ichida joriy correlation_id ni olish
req_id = correlation_id_var.get()  # str | None
```

---

## 3. Prometheus metrikalar

### HTTP metrikalar

| Metrika | Turi | Labellar | Tavsif |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `path`, `status` | Jami HTTP so'rovlar |
| `http_request_duration_seconds` | Histogram | `method`, `path` | So'rov davomiyligi (s) |
| `http_requests_in_progress` | Gauge | `method`, `path` | Hozir bajarilayotganlar |

Histogram buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0` soniya.

### Biznes counterlar

| Metrika | Turi | Labellar | Qachon oshadi |
|---|---|---|---|
| `orders_created_total` | Counter | — | Yangi buyurtma yaratilganda |
| `auth_login_total` | Counter | `result` (`success`\|`failure`) | Login urinishida |
| `sync_push_total` | Counter | — | Sync push operatsiyasida |
| `gps_ingest_total` | Counter | — | GPS nuqtasi qabul qilinganda |

### Biznes counterlarni ishlatish

```python
from app.core.metrics import (
    inc_orders_created,
    inc_auth_login,
    inc_sync_push,
    inc_gps_ingest,
)

# Orders servisida
inc_orders_created()

# Auth servisida
inc_auth_login(success=True)   # yoki success=False

# Sync servisida
inc_sync_push()

# GPS servisida
inc_gps_ingest(count=len(points))
```

### `/metrics` endpointi

```
GET /metrics
```

Prometheus scraper ushbu endpointni so'raydi. `MetricsMiddleware` `/metrics` yo'lini o'zi kuzatmaydi. Endpoint `include_in_schema=False` — Swagger UI da ko'rinmaydi.

Namuna chiqish:

```
# HELP http_requests_total Umumiy HTTP so'rovlar soni
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/orders",status="201"} 42.0
http_request_duration_seconds_bucket{method="POST",path="/orders",le="0.1"} 38.0
...
```

### Grafana va alerting tavsiyasi

- **p99 latency alert**: `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1.0`
- **Error rate alert**: `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01`
- **In-progress spike**: `http_requests_in_progress > 100`

---

## 4. OpenTelemetry tracing

### Sozlash

`OTEL_EXPORTER_OTLP_ENDPOINT` env o'zgaruvchisi:

```bash
# .env
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
```

Ko'rsatilmasa — OTel o'chiq (no-op). Ilova xatosiz ishlaydi.

### Instrumentatsiya

`OTEL_EXPORTER_OTLP_ENDPOINT` ko'rsatilganda quyidagi paketlar kerak:

```bash
pip install \
  opentelemetry-sdk \
  opentelemetry-instrumentation-fastapi \
  opentelemetry-instrumentation-sqlalchemy \
  opentelemetry-exporter-otlp-proto-http
```

Avtomatik instrumentatsiyalanadi:
- FastAPI — har endpoint uchun span.
- SQLAlchemy — har SQL so'rov uchun span.

### Xizmat nomi

`service.name = "retail-api"` (TracerProvider `Resource` da belgilangan).

### No-op rejimi

`OTEL_EXPORTER_OTLP_ENDPOINT` yo'q yoki bo'sh bo'lsa:

```
DEBUG: OTel OTLP endpoint ko'rsatilmagan — OTel o'chiq (no-op).
```

Paketlar o'rnatilmagan bo'lsa ham xato chiqmaydi — `ImportError` ushlanadi.

---

## 5. Sentry

### Sozlash

```bash
# .env
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

Ko'rsatilmasa — Sentry o'chiq (no-op).

### Konfiguratsiya

```python
sentry_sdk.init(
    dsn=dsn,
    send_default_pii=False,   # PII Sentry ga ketmaydi
    traces_sample_rate=0.1,   # 10% tracing namunasi
)
```

`send_default_pii=False` — foydalanuvchi IP, cookie, request body Sentry ga yuborilmaydi.

### No-op rejimi

`SENTRY_DSN` yo'q bo'lsa:

```
DEBUG: Sentry DSN ko'rsatilmagan — Sentry o'chiq (no-op).
```

`sentry-sdk` paketi o'rnatilmagan bo'lsa ham xato chiqmaydi.

---

## 6. Middleware tartibi

`main.py` da middleware qo'shilish tartibi (LIFO — eng oxirgi `add_middleware` eng birinchi ishlaydi):

```python
app.add_middleware(LocaleMiddleware)        # 3-chi qo'shildi → eng ichki
app.add_middleware(CorrelationIdMiddleware) # 2-chi qo'shildi
app.add_middleware(MetricsMiddleware)       # 1-chi qo'shildi → eng tashqi
```

Ishlash tartibi (tashqaridan ichkariga):

```
CORS → MetricsMiddleware → CorrelationIdMiddleware → LocaleMiddleware → endpoint
```

| Tartib | Middleware | Vazifasi |
|---|---|---|
| 1 (tashqi) | `MetricsMiddleware` | Prometheus metrikalarini yig'adi |
| 2 | `CorrelationIdMiddleware` | X-Request-ID, JSON log `request_start`/`request_end` |
| 3 (ichki) | `LocaleMiddleware` | `Accept-Language` / `?lang=` dan til aniqlaydi |

---

## 7. Ishga tushirish va sozlash

### Env o'zgaruvchilar

| O'zgaruvchi | Standart | Tavsif |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log darajasi: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (yo'q) | OTLP HTTP endpoint; yo'q bo'lsa no-op |
| `SENTRY_DSN` | (yo'q) | Sentry DSN; yo'q bo'lsa no-op |

### Minimal `.env` (faqat logging)

```bash
LOG_LEVEL=INFO
# OTEL va Sentry ko'rsatilmasa — no-op, xato yo'q
```

### To'liq `.env` (barcha observability)

```bash
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

### Prometheus scrape config (namuna)

```yaml
scrape_configs:
  - job_name: retail-api
    static_configs:
      - targets: ["retail-api:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```
