"""
RETAIL — FastAPI ilovasi kirish nuqtasi.

Endpointlar:
  GET  /health      — liveness probe (DB tekshirmasdan)
  GET  /readiness   — readiness probe (DB + Redis + MinIO tekshiradi)
  GET  /openapi.json — OpenAPI sxemasi (klient generatsiya uchun)

B1 modullari (T1-T8) router sifatida shu yerga ulanadi.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException

from app.core.config import settings
from app.core.crypto import verify_crypto_keys
from app.core.db import close_db_connections, primary_engine
from app.core.errors import AppError, error_envelope
from app.core.logging_config import setup_logging
from app.core.messages import translate
from app.core.metrics import metrics_response
from app.core.middleware import CorrelationIdMiddleware, LocaleMiddleware, MetricsMiddleware
from app.core.redis import close_redis, get_redis_client
from app.core.telemetry import init_telemetry
from app.modules.attendance.router import router as attendance_router
from app.modules.contracts.router import router as contracts_router
from app.modules.tickets.router import router as tickets_router
from app.modules.promo.router import router as promo_router
from app.modules.stats.router import router as stats_router
from app.modules.delivery.router import router as delivery_router
from app.modules.gps.router import router as gps_router
from app.modules.push.router import router as push_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.customers.router import router as customers_router
from app.modules.finance.router import router as finance_router
from app.modules.orders.router import router as orders_router
from app.modules.rbac.router import router as rbac_router
from app.modules.stock.router import router as stock_router
from app.modules.sync.router import router as sync_router
from app.modules.users.router import router as users_router

logger = logging.getLogger(__name__)


# ─── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ilova ishga tushganda va o'chganda bajariladigan amallar."""
    # 1. Strukturalangan JSON logging
    setup_logging(settings.log_level)

    logger.info(
        "RETAIL backend ishga tushmoqda",
        extra={"env": settings.app_env, "debug": settings.app_debug},
    )

    # 2. OTel + Sentry (dsn yo'q bo'lsa no-op)
    init_telemetry(
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        sentry_dsn=settings.sentry_dsn,
    )

    # 3. Crypto startup self-check: kalit noto'g'ri bo'lsa ilova ishga tushmasin.
    # verify_crypto_keys() → encrypt_pii("probe") → decrypt_pii(...) == "probe"
    # Muvaffaqiyatsiz bo'lsa RuntimeError ko'taradi.
    verify_crypto_keys()
    logger.info("Crypto kalit tekshiruvi muvaffaqiyatli o'tdi.")
    yield
    # Shutdown
    await close_db_connections()
    await close_redis()
    logger.info("RETAIL backend o'chdi, DB va Redis ulanishlari yopildi")


# ─── FastAPI ilova ───────────────────────────────────────────────────────────

# Production da docs endpointlarini yopish (xavfsizlik)
_docs_url = None if settings.app_env == "production" else "/docs"
_redoc_url = None if settings.app_env == "production" else "/redoc"

app = FastAPI(
    title="RETAIL API",
    description=(
        "Ulgurji/Chakana Savdo va Distribyutsiya Platformasi — "
        "FastAPI modular monolit. "
        "5 rol: administrator, agent, courier, accountant, store."
    ),
    version="0.1.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────────────────
# Eslatma: allow_origins=['*'] + allow_credentials=True kombinatsiyasi
# config.py da model_validator tomonidan rad etiladi.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── i18n Middleware ──────────────────────────────────────────────────────────
# LocaleMiddleware CORS dan keyin qo'shiladi — har request uchun til aniqlanadi.
# Starlette middleware zanjiri LIFO tartibida ishlanadi, shuning uchun
# eng oxirgi add_middleware eng birinchi chaqiriladi.
#
# Tartib (tashqaridan ichkariga):
#   CORS → MetricsMiddleware → CorrelationIdMiddleware → LocaleMiddleware → endpoint

app.add_middleware(LocaleMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(MetricsMiddleware)


# ─── Exception Handlerlar ─────────────────────────────────────────────────────

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """
    AppError va uning sub-turlari (AuthAppError va h.k.) uchun handler.

    Javob formati:
      {"message_key": "...", "message": "<lokalizatsiya>", "detail": null}
    """
    # LOW: 4xx xatolar log'ga tushadi (PII'siz — faqat message_key va status)
    logger.info(
        "AppError: message_key=%s status=%s",
        exc.message_key,
        exc.status_code,
    )
    message = exc.localized_message()
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.message_key, message, exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Pydantic 422 RequestValidationError uchun handler.

    Javob formati:
      {
        "message_key": "common.validation_error",
        "message": "<lokalizatsiya>",
        "detail": [<pydantic xato ro'yxati — sezgir maydonlar olib tashlangan>]
      }

    HIGH (Security): `input`, `url`, `ctx` maydonlari olib tashlanadi —
    parol/token kabi qiymatlar 422 javobida echo qilinmaydi.
    """
    # Har xatodan sezgir maydonlarni olib tashlash
    _SENSITIVE = {"input", "url", "ctx"}
    safe_errors = [
        {k: v for k, v in e.items() if k not in _SENSITIVE}
        for e in exc.errors()
    ]
    message = translate("common.validation_error")
    return JSONResponse(
        status_code=422,
        content=error_envelope("common.validation_error", message, safe_errors),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Starlette/FastAPI HTTPException uchun global handler.

    HTTPException detail o'rniga envelope formatida qaytaradi.
    404 uchun common.not_found message_key ishlatiladi.

    MEDIUM (SRE): Standart {'detail': '...'} javob o'rniga envelope format.
    """
    if exc.status_code == 404:
        message_key = "common.not_found"
    else:
        message_key = str(exc.detail)

    message = translate(message_key) if message_key in (
        "common.not_found", "common.internal_error"
    ) else str(exc.detail)

    logger.info("HTTPException: status=%s detail=%s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(message_key, message, None),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Kutilmagan barcha xatolar uchun global fallback handler.

    MEDIUM (SRE): Ichki trace/xato tafsilotlari mijozga chiqmaydi.
    Server logga to'liq stack trace yoziladi.
    """
    logger.exception("Unhandled 500", exc_info=exc)
    message = translate("common.internal_error")
    return JSONResponse(
        status_code=500,
        content=error_envelope("common.internal_error", message, None),
    )


# ─── Health / Readiness endpointlar ─────────────────────────────────────────

@app.get(
    "/health",
    tags=["ops"],
    summary="Liveness probe",
    response_description="Ilova ishlamoqda",
)
async def health() -> dict[str, str]:
    """
    Liveness probe — Kubernetes / Docker healthcheck uchun.

    DB/Redis tekshirmaydi; faqat ilova jarayoni tirikligini bildiradi.
    """
    return {"status": "ok", "service": "retail-api"}


@app.get(
    "/readiness",
    tags=["ops"],
    summary="Readiness probe",
    response_description="Ilova va infra tayyor",
)
async def readiness() -> JSONResponse:
    """
    Readiness probe — trafik yuborishdan oldin infra sog'lig'ini tekshiradi.

    Tekshirishlar:
      - PostgreSQL primary (SELECT 1)
      - Redis (PING)
      - MinIO (/minio/health/live)
    """
    checks: dict[str, Any] = {}
    overall_ok = True

    # PostgreSQL tekshiruvi
    try:
        async with primary_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("Readiness: postgres xatosi", exc_info=exc)
        checks["postgres"] = "error"
        overall_ok = False

    # Redis tekshiruvi (PING) — markaziy klient orqali (DRY)
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("Readiness: redis xatosi", exc_info=exc)
        checks["redis"] = "error"
        overall_ok = False

    # MinIO tekshiruvi (/minio/health/live)
    try:
        minio_health_url = f"{settings.minio_endpoint_url}/minio/health/live"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(minio_health_url)
            if resp.status_code == 200:
                checks["minio"] = "ok"
            else:
                logger.error(
                    "Readiness: minio noto'g'ri status",
                    extra={"status_code": resp.status_code},
                )
                checks["minio"] = "error"
                overall_ok = False
    except Exception as exc:
        logger.error("Readiness: minio xatosi", exc_info=exc)
        checks["minio"] = "error"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        content={"status": "ok" if overall_ok else "degraded", "checks": checks},
        status_code=status_code,
    )


# ─── Kuzatuvchanlik endpointlari ─────────────────────────────────────────────

@app.get(
    "/metrics",
    tags=["ops"],
    summary="Prometheus metrikalar",
    response_description="Prometheus text format metrikalar",
    include_in_schema=False,
)
async def metrics_endpoint():
    """
    Prometheus scrape endpointi.

    Qaytaradi: prometheus_client text exposition format.
    Metrics middleware bu yo'lni kuzatmaydi (cheksiz rekursiya oldini olish).
    """
    return metrics_response()


# ─── B1 routerlari ───────────────────────────────────────────────────────────

# T1: Auth
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# T2: RBAC
app.include_router(rbac_router, prefix="/rbac", tags=["rbac"])

# T4: Catalog
app.include_router(catalog_router, prefix="/catalog", tags=["catalog"])

# T5: Customers (do'konlar) — PII shifrlash bilan
app.include_router(customers_router, prefix="/customers", tags=["customers"])

# T6: Users (foydalanuvchilar boshqaruvi) — faqat administrator
app.include_router(users_router, prefix="/users", tags=["users"])

# T9: Ombor (stock) — APPEND-ONLY event-sourced ledger
app.include_router(stock_router, prefix="/stock", tags=["stock"])

# T10: Buxgalteriya (finance) — APPEND-ONLY event-sourced ledger
app.include_router(finance_router, prefix="/finance", tags=["finance"])

# T11: Buyurtma yadrosi — atomik tranzaksiya (order + stock + ledger)
app.include_router(orders_router, prefix="/orders", tags=["orders"])

# T13: Outbox Sync API — push/pull (offline-first sinxronlash)
app.include_router(sync_router, prefix="/sync", tags=["sync"])

# T16: Davomat (Face ID lokal biometrik + GPS)
app.include_router(attendance_router, prefix="/attendance", tags=["attendance"])

# T17: GPS Ingest — yuqori chastotali GPS trekking (alohida servis moduli)
app.include_router(gps_router, prefix="/gps", tags=["gps"])

# T18: Yetkazib berish — holat mashinasi + GPS trek
app.include_router(delivery_router, prefix="/delivery", tags=["delivery"])

# T19: Push bildirishnomalar — device token ro'yxatdan o'tkazish
app.include_router(push_router, prefix="/push", tags=["push"])

# T23: Shartnoma — CRUD + PDF yuklash
app.include_router(contracts_router, prefix="/contracts", tags=["contracts"])

# T24: Murojaat — CRUD + holat mashinasi
app.include_router(tickets_router, prefix="/tickets", tags=["tickets"])

# T25: Aksiya (Promo) — CRUD + banner + server-avtoritar chegirma
app.include_router(promo_router, prefix="/promos", tags=["promo"])

# T22: Statistika/Hisobot — read-only reporting (replica + primary)
app.include_router(stats_router, prefix="/stats", tags=["stats"])
