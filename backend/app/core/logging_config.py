"""
Strukturalangan JSON logging konfiguratsiyasi — T27 Kuzatuvchanlik.

Xususiyatlari:
  - Har log yozuvi JSON formatida: timestamp, level, logger, message,
    correlation_id (contextvars dan), va extra maydonlar.
  - setup_logging() — root logger va uchinci tomon logger larni sozlaydi.
  - PII/sirlar logga tushmaydi: mask_pii bilan uyg'un (security.py).
  - correlation_id — CorrelationIdFilter tomonidan har log yozuviga qo'shiladi.

Foydalanish (main.py lifespan):
    from app.core.logging_config import setup_logging
    setup_logging()
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ─── Correlation ID ContextVar ───────────────────────────────────────────────
# CorrelationIdMiddleware tomonidan har request uchun o'rnatiladi.
# log formatterlar shu ContextVar'dan correlation_id ni o'qiydi.
correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)


# ─── JSON Formatter ──────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """
    Har log yozuvini strukturalangan JSON ga aylantiradi.

    Chiqish formati:
      {
        "timestamp": "2025-01-01T12:00:00.123456Z",
        "level":     "INFO",
        "logger":    "app.core.middleware",
        "message":   "Request boshlandi",
        "correlation_id": "01933...",
        ... (extra maydonlar)
      }

    PII xavfsizligi:
      - extra dict ichida sezgir kalitlar (inn, phone, password, token, ...)
        mask_pii() orqali avtomatik maskalanadi.
      - Logni chiqarishdan oldin _sanitize() chaqiriladi.
    """

    # PII maskalash uchun sezgir kalit nomlari (kichik harfda)
    _SENSITIVE_KEYS: frozenset[str] = frozenset(
        {
            "inn",
            "inps",
            "phone",
            "full_name",
            "password",
            "password_hash",
            "token",
            "access_token",
            "refresh_token",
            "owner_name",
            "secret",
            "jwt_secret_key",
            "pii_encryption_key",
            "blind_index_key",
            "api_key",
            "authorization",
        }
    )
    _MASK = "***"

    def format(self, record: logging.LogRecord) -> str:
        """LogRecord ni JSON string ga aylantiradi."""
        log_entry: dict[str, Any] = {
            "timestamp": self._format_time(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        # Extra maydonlar — LogRecord'dagi standart bo'lmagan atribyutlar
        _std_attrs = frozenset(logging.LogRecord.__dict__.keys()) | frozenset(
            {
                "message", "asctime", "exc_text", "stack_info",
                "msg", "args", "exc_info", "created", "msecs",
                "relativeCreated", "thread", "threadName",
                "processName", "process", "taskName",
            }
        )
        for key, value in record.__dict__.items():
            if key not in _std_attrs and not key.startswith("_"):
                log_entry[key] = value

        # Exception ma'lumoti
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        # Stack info
        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        # PII maskalash (yuqori daraja kalitlar)
        log_entry = self._sanitize(log_entry)

        return json.dumps(log_entry, ensure_ascii=False, default=str)

    def _format_time(self, record: logging.LogRecord) -> str:
        """ISO 8601 UTC timestamp."""
        dt = datetime.fromtimestamp(record.created, tz=UTC)
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Lug'at ichidagi PII va sezgir kalitlarni maskalashtiradi.

        Faqat yuqori darajadagi kalitlarni tekshiradi (nested yo'q).
        Asl dict o'zgartirilmaydi.
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in self._SENSITIVE_KEYS:
                result[key] = self._MASK
            else:
                result[key] = value
        return result


# ─── Logging sozlash ──────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO") -> None:
    """
    Root logger va muhim uchinci tomon loggerlarni JSON formatter bilan sozlaydi.

    Args:
        log_level: Log darajasi (INFO, DEBUG, WARNING, ERROR, CRITICAL).

    main.py lifespan/startup'dan bir marta chaqirilishi kerak:
        setup_logging(settings.log_level)

    Xususiyatlari:
      - Root logger JSON formatter bilan stdout ga chiqaradi.
      - uvicorn.access — o'chiriladi (structlog/metrics orqali yoriladi).
      - sqlalchemy.engine — WARNING darajasida (SQL spam bo'lmasin).
      - httpx, httpcore — WARNING darajasida.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    json_formatter = JsonFormatter()

    # Root logger uchun handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(json_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Mavjud handler larni tozalash (ikki marta setup oldini olish)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Uvicorn access log — bizning middleware yetarli log yozadi
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").propagate = False

    # SQL spam
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # httpx, httpcore — MinIO/readiness uchun
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
