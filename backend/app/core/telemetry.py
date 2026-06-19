"""
OpenTelemetry va Sentry integratsiyasi — T27 Kuzatuvchanlik.

Yengil no-op rejimi:
  - `otel_exporter_otlp_endpoint` bo'lmasa — OTel ishga tushmaydi.
  - `sentry_dsn` bo'lmasa — Sentry ishga tushmaydi.

Foydalanish (main.py lifespan):
    from app.core.telemetry import init_telemetry
    init_telemetry()
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_opentelemetry(otlp_endpoint: str | None, service_name: str = "retail-api") -> None:
    """
    OpenTelemetry instrumentatsiyasini boshlaydi.

    otlp_endpoint bo'lmasa — no-op (hech narsa qilinmaydi).
    opentelemetry-sdk/instrumentation-fastapi/instrumentation-sqlalchemy
    o'rnatilgan bo'lishi shart.
    """
    if not otlp_endpoint:
        logger.debug("OTel OTLP endpoint ko'rsatilmagan — OTel o'chiq (no-op).")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()

        logger.info("OpenTelemetry OTLP tracing boshlandi.", extra={"otlp_endpoint": otlp_endpoint})

    except ImportError as exc:
        logger.warning(
            "OpenTelemetry paketlari topilmadi — OTel o'chiq.",
            extra={"error": str(exc)},
        )
    except Exception as exc:
        logger.error(
            "OpenTelemetry ishga tushishda xato — OTel o'chiq.",
            extra={"error": str(exc)},
        )


def init_sentry(dsn: str | None) -> None:
    """
    Sentry SDK ni boshlaydi.

    dsn bo'lmasa — no-op (hech narsa qilinmaydi).
    send_default_pii=False — PII ma'lumotlar Sentry ga ketmaydi.
    """
    if not dsn:
        logger.debug("Sentry DSN ko'rsatilmagan — Sentry o'chiq (no-op).")
        return

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            send_default_pii=False,
            traces_sample_rate=0.1,  # 10% tracing namunasi
        )
        logger.info("Sentry SDK boshlandi.")

    except ImportError as exc:
        logger.warning(
            "sentry-sdk paketi topilmadi — Sentry o'chiq.",
            extra={"error": str(exc)},
        )
    except Exception as exc:
        logger.error(
            "Sentry ishga tushishda xato — Sentry o'chiq.",
            extra={"error": str(exc)},
        )


def init_telemetry(otlp_endpoint: str | None = None, sentry_dsn: str | None = None) -> None:
    """
    Barcha kuzatuvchanlik instrumentatsiyasini ishga tushiradi.

    main.py lifespan da chaqiriladi:
        from app.core.telemetry import init_telemetry
        init_telemetry(
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
            sentry_dsn=settings.sentry_dsn,
        )
    """
    init_opentelemetry(otlp_endpoint)
    init_sentry(sentry_dsn)
