"""
Prometheus metrikalar — T27 Kuzatuvchanlik.

Xususiyatlari:
  - http_requests_total{method, path, status}  — Counter
  - http_request_duration_seconds{method, path} — Histogram
  - http_requests_in_progress{method, path}     — Gauge
  - Biznes counter helperlar: orders_created, auth_login{result},
    sync_push_total, gps_ingest_total.

Foydalanish:
    from app.core.metrics import (
        record_request_start, record_request_end,
        inc_orders_created, inc_auth_login,
        inc_sync_push, inc_gps_ingest,
    )

`/metrics` endpointi main.py da qo'shiladi:
    from app.core.metrics import metrics_response
    @app.get("/metrics")
    async def metrics_endpoint():
        return metrics_response()
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

# ─── HTTP metrikalar ─────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Umumiy HTTP so'rovlar soni",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP so'rov davomiyligi (soniyada)",
    ["method", "path"],
    # Standart buckets: 5ms–10s oralig'iga moslashtirilgan
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Hozir bajarilayotgan HTTP so'rovlar soni",
    ["method", "path"],
)

# ─── Biznes metrikalar ───────────────────────────────────────────────────────

orders_created_total = Counter(
    "orders_created_total",
    "Yaratilgan buyurtmalar soni",
)

auth_login_total = Counter(
    "auth_login_total",
    "Autentifikatsiya urinishlari soni",
    ["result"],  # "success" | "failure"
)

sync_push_total = Counter(
    "sync_push_total",
    "Sinxronlash push operatsiyalari soni",
)

gps_ingest_total = Counter(
    "gps_ingest_total",
    "GPS nuqtalari qabul qilingan soni",
)


# ─── Middleware yordamchi funksiyalar ────────────────────────────────────────

def record_request_start(method: str, path: str) -> None:
    """So'rov boshlanganda in_progress gauge oshiriladi."""
    http_requests_in_progress.labels(method=method, path=path).inc()


def record_request_end(method: str, path: str, status: int, duration: float) -> None:
    """So'rov tugaganda counter/histogram yangilanadi va gauge kamaytiriladi."""
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)
    http_requests_in_progress.labels(method=method, path=path).dec()


# ─── Biznes helper funksiyalar ────────────────────────────────────────────────

def inc_orders_created() -> None:
    """Yangi buyurtma yaratilganda chaqiriladi."""
    orders_created_total.inc()


def inc_auth_login(success: bool) -> None:
    """Login urinishida chaqiriladi — success=True yoki False."""
    result = "success" if success else "failure"
    auth_login_total.labels(result=result).inc()


def inc_sync_push() -> None:
    """Sync push operatsiyasida chaqiriladi."""
    sync_push_total.inc()


def inc_gps_ingest(count: int = 1) -> None:
    """GPS nuqtalari qabul qilinganida chaqiriladi."""
    gps_ingest_total.inc(count)


# ─── /metrics endpoint javobi ────────────────────────────────────────────────

def metrics_response() -> Response:
    """Prometheus scrape uchun `/metrics` endpointi javobi."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
