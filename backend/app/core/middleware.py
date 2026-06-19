"""
HTTP Middleware to'plami — T27 Kuzatuvchanlik + i18n.

Middleware lar:
  1. LocaleMiddleware     — Accept-Language / ?lang= dan til aniqlab ContextVar ga yozadi.
  2. CorrelationIdMiddleware — har request uchun X-Request-ID generatsiya qiladi yoki
                               kelganini qabul qilib correlation_id_var ga yozadi;
                               javobda X-Request-ID header qaytaradi.
  3. MetricsMiddleware    — Prometheus metrikalarini yig'adi (so'rov boshi/oxiri).

Tartib (main.py add_middleware LIFO):
    app.add_middleware(MetricsMiddleware)     — birinchi qo'shiladi = eng tashqi
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(LocaleMiddleware)      — oxirgi qo'shiladi = eng ichki
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.i18n import current_locale, parse_accept_language
from app.core.logging_config import correlation_id_var
from app.core.uuid7 import uuid7_str

logger = logging.getLogger(__name__)


# ─── LocaleMiddleware ─────────────────────────────────────────────────────────

class LocaleMiddleware(BaseHTTPMiddleware):
    """
    Starlette BaseHTTPMiddleware — Accept-Language / ?lang= dan til aniqlab
    current_locale ContextVar'ga yozadi.

    Middleware zanjiriga qo'shish (main.py):
        app.add_middleware(LocaleMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Har HTTP request uchun:
          1. `?lang=` query parametrini tekshir (prioritet yuqori).
          2. Accept-Language headeridan til ajrat.
          3. current_locale ContextVar'ini set() qil.
          4. Request ni davom ettir.
          5. ContextVar token'ini reset() qil (tozalash).
        """
        # 1. Query parametr (?lang=ru yoki ?lang=uz)
        lang_param = request.query_params.get("lang", "").strip().lower()

        from app.core.i18n import SUPPORTED_LOCALES

        if lang_param in SUPPORTED_LOCALES:
            locale = lang_param
        else:
            # 2. Accept-Language header
            accept_lang = request.headers.get("Accept-Language")
            locale = parse_accept_language(accept_lang)

        # 3. ContextVar'ni o'rnatish (token reset uchun saqlanadi)
        token = current_locale.set(locale)

        try:
            response = await call_next(request)
        finally:
            # 5. Tozalash — async context izolyatsiyasi
            current_locale.reset(token)

        return response


# ─── CorrelationIdMiddleware ──────────────────────────────────────────────────

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Har HTTP request uchun Correlation ID (so'rov izlash identifikatori):

    - `X-Request-ID` header kelsa — uni ishlatadi.
    - Kelmasа — UUID v7 generatsiya qiladi.
    - correlation_id_var (ContextVar) ga yozadi — JSON logga avtomatik tushadi.
    - Javob header'iga `X-Request-ID` qo'shadi.
    - So'rov boshi va oxirida strukturalangan log yozadi:
        request_start:  method, path
        request_end:    method, path, status_code, duration_ms
    """

    _HEADER = "x-request-id"

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Correlation ID aniqlash
        req_id = request.headers.get(self._HEADER) or uuid7_str()

        # 2. ContextVar ga yozish
        token = correlation_id_var.set(req_id)

        # 3. So'rov boshi log
        start_time = time.perf_counter()
        logger.info(
            "request_start",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
            },
        )

        try:
            response = await call_next(request)
        except Exception:
            # Kutilmagan xatoda ham log va header qaytaramiz
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "request_error",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            correlation_id_var.reset(token)

        # 4. So'rov oxiri log
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "request_end",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        # 5. Javob headeriga qo'shish
        response.headers["x-request-id"] = req_id
        return response


# ─── MetricsMiddleware ────────────────────────────────────────────────────────

class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Prometheus metrikalarini yig'uvchi middleware.

    `/metrics` yo'li o'zi kuzatilmaydi (cheksiz rekursiya oldini olish uchun).

    Yig'iladigan metrikalar (app/core/metrics.py):
      - http_requests_total{method, path, status}
      - http_request_duration_seconds{method, path}
      - http_requests_in_progress{method, path}
    """

    _SKIP_PATH = "/metrics"

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # /metrics yo'li uchun metrika yig'ilmaydi
        if path == self._SKIP_PATH:
            return await call_next(request)

        from app.core.metrics import record_request_end, record_request_start

        method = request.method
        record_request_start(method, path)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            record_request_end(method, path, response.status_code, duration)
            return response
        except Exception:
            duration = time.perf_counter() - start_time
            record_request_end(method, path, 500, duration)
            raise
