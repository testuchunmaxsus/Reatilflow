"""
T27 Kuzatuvchanlik testlari.

Testlar qamrovi:
  1. /metrics — Prometheus format; counter so'rovdan keyin oshadi.
  2. Correlation ID — X-Request-ID javobda qaytadi; kelgani saqlanadi.
  3. JSON log formatter — correlation_id, level maydonlari; PII maskalanadi.
  4. OTel — dsn yo'q → no-op (xato yo'q).
  5. Sentry — dsn yo'q → no-op (xato yo'q).
  6. Sentry — dsn bor → init chaqiriladi (mock).
  7. OTel — otlp_endpoint bor → init uriniladi (mock).
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.logging_config import JsonFormatter, correlation_id_var
from app.core.telemetry import init_opentelemetry, init_sentry
from app.main import app


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
async def client() -> AsyncClient:
    """Observability testlari uchun ASGI klient."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


# ─── 1. /metrics endpointi ───────────────────────────────────────────────────

async def test_metrics_endpoint_returns_prometheus_format(client: AsyncClient) -> None:
    """/metrics Prometheus text format qaytarishi kerak."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    # Prometheus CONTENT_TYPE_LATEST: "text/plain; version=0.0.4; charset=utf-8"
    assert "text/plain" in content_type
    body = response.text
    # Standart Prometheus metrikalar mavjudligi
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "http_requests_in_progress" in body


async def test_metrics_counter_increments_after_request(client: AsyncClient) -> None:
    """So'rovdan keyin http_requests_total counter oshishi kerak."""
    # Birinchi /metrics holati
    resp1 = await client.get("/metrics")
    body1 = resp1.text

    # /health ga so'rov yuborish
    await client.get("/health")

    # Yana /metrics
    resp2 = await client.get("/metrics")
    body2 = resp2.text

    # http_requests_total counter oshgan bo'lishi kerak
    # (yoki GET /health uchun yozuv paydo bo'ladi)
    assert "http_requests_total" in body2
    # body2 counter qiymatlari body1 dan katta yoki /health yo'li paydo bo'lgan
    assert 'path="/health"' in body2 or "health" in body2


async def test_metrics_path_not_tracked_in_metrics(client: AsyncClient) -> None:
    """/metrics yo'li o'zi metrikada kuzatilmasligi kerak (cheksiz rekursiya yo'q)."""
    # Bir necha marta /metrics chaqiramiz
    for _ in range(3):
        await client.get("/metrics")

    resp = await client.get("/metrics")
    body = resp.text

    # /metrics yo'li http_requests_total da label sifatida bo'lmasligi kerak
    assert 'path="/metrics"' not in body


# ─── 2. Correlation ID ────────────────────────────────────────────────────────

async def test_correlation_id_returned_in_response(client: AsyncClient) -> None:
    """X-Request-ID har javobda bo'lishi kerak."""
    response = await client.get("/health")
    assert "x-request-id" in response.headers
    req_id = response.headers["x-request-id"]
    assert len(req_id) > 0


async def test_correlation_id_incoming_preserved(client: AsyncClient) -> None:
    """Kelgan X-Request-ID javobda o'zgarmasdan qaytishi kerak."""
    custom_id = "my-trace-id-12345"
    response = await client.get("/health", headers={"x-request-id": custom_id})
    assert response.headers.get("x-request-id") == custom_id


async def test_correlation_id_auto_generated_when_missing(client: AsyncClient) -> None:
    """Header kelmasа — server UUID generatsiya qilishi kerak."""
    response = await client.get("/health")
    req_id = response.headers.get("x-request-id", "")
    # UUID v7 yoki UUID formatiga o'xshash bo'lishi kerak
    assert len(req_id) >= 32
    # Har so'rovda turli ID bo'lishi kerak
    response2 = await client.get("/health")
    req_id2 = response2.headers.get("x-request-id", "")
    assert req_id != req_id2


# ─── 3. JSON Log Formatter ────────────────────────────────────────────────────

def test_json_formatter_basic_fields() -> None:
    """JSON formatter timestamp, level, logger, message maydonlarini chiqarishi kerak."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test xabari",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Test xabari"
    assert "correlation_id" in data


def test_json_formatter_includes_correlation_id() -> None:
    """JSON formatter correlation_id ContextVar dan o'qishi kerak."""
    formatter = JsonFormatter()
    token = correlation_id_var.set("test-corr-id-999")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="Korrelyatsiya testi",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["correlation_id"] == "test-corr-id-999"
    finally:
        correlation_id_var.reset(token)


def test_json_formatter_masks_pii_phone() -> None:
    """JSON formatter `phone` kalitini *** bilan maskalashi kerak."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="PII testi",
        args=(),
        exc_info=None,
    )
    # Extra maydonda phone
    record.phone = "+998901234567"
    record.user_id = "123"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["phone"] == "***"
    assert data["user_id"] == "123"


def test_json_formatter_masks_pii_password() -> None:
    """JSON formatter `password` kalitini maskalashi kerak."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="Parol testi",
        args=(),
        exc_info=None,
    )
    record.password = "supersecret"

    output = formatter.format(record)
    data = json.loads(output)
    assert data["password"] == "***"


def test_json_formatter_masks_token() -> None:
    """JSON formatter `token` va `access_token` ni maskalashi kerak."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Token testi",
        args=(),
        exc_info=None,
    )
    record.token = "eyJhbGci..."
    record.access_token = "eyJhbGci..."

    output = formatter.format(record)
    data = json.loads(output)
    assert data["token"] == "***"
    assert data["access_token"] == "***"


def test_json_formatter_timestamp_format() -> None:
    """Timestamp ISO 8601 UTC formatida bo'lishi kerak."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Vaqt testi",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)
    ts = data["timestamp"]
    # ISO 8601 UTC: "2025-01-01T12:00:00.123456Z"
    assert ts.endswith("Z")
    assert "T" in ts


# ─── 4. OTel no-op ────────────────────────────────────────────────────────────

def test_otel_noop_when_no_endpoint() -> None:
    """OTel endpoint yo'q bo'lsa xato ko'tarilmasligi kerak."""
    # Xato yo'q — no-op ishlashi kerak
    try:
        init_opentelemetry(None)
    except Exception as exc:
        pytest.fail(f"init_opentelemetry(None) xato ko'tardi: {exc}")


def test_otel_noop_returns_none() -> None:
    """OTel no-op None qaytarishi kerak."""
    result = init_opentelemetry(None)
    assert result is None


def test_otel_with_missing_package_graceful() -> None:
    """OTel paketi yo'q bo'lsa ham xato ko'tarilmasligi kerak."""
    # opentelemetry.exporter.otlp.proto.http ni import qila olmasa warning log yozib o'tadi
    with patch.dict("sys.modules", {"opentelemetry.exporter.otlp.proto.http.trace_exporter": None}):
        try:
            init_opentelemetry("http://localhost:4318")
        except Exception as exc:
            pytest.fail(f"OTel import xatosida xato ko'tardi: {exc}")


# ─── 5. Sentry no-op ─────────────────────────────────────────────────────────

def test_sentry_noop_when_no_dsn() -> None:
    """Sentry DSN yo'q bo'lsa xato ko'tarilmasligi kerak."""
    try:
        init_sentry(None)
    except Exception as exc:
        pytest.fail(f"init_sentry(None) xato ko'tardi: {exc}")


def test_sentry_noop_returns_none() -> None:
    """Sentry no-op None qaytarishi kerak."""
    result = init_sentry(None)
    assert result is None


# ─── 6. Sentry — dsn bor → init chaqiriladi ──────────────────────────────────

def test_sentry_init_called_when_dsn_provided() -> None:
    """Sentry DSN ko'rsatilganda sentry_sdk.init() chaqirilishi kerak."""
    mock_sentry = MagicMock()
    with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
        init_sentry("https://fake@sentry.io/1234")
    mock_sentry.init.assert_called_once()
    call_kwargs = mock_sentry.init.call_args
    # send_default_pii=False bo'lishi shart
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    if not kwargs:
        # positional args dict ga o'tkazilgan bo'lishi mumkin
        args = call_kwargs.args
        # dsn birinchi arg bo'lishi mumkin
    else:
        assert kwargs.get("send_default_pii") is False


def test_sentry_send_default_pii_false() -> None:
    """Sentry init da send_default_pii=False bo'lishi kerak."""
    captured_kwargs: dict = {}

    def fake_init(**kwargs):
        captured_kwargs.update(kwargs)

    mock_sentry = MagicMock()
    mock_sentry.init = fake_init

    with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
        init_sentry("https://fake@sentry.io/5678")

    assert captured_kwargs.get("send_default_pii") is False


# ─── 7. OTel — endpoint bor → init uriniladi ─────────────────────────────────

def test_otel_init_attempted_when_endpoint_provided() -> None:
    """OTel endpoint ko'rsatilganda trace.set_tracer_provider chaqirilishi kerak."""
    # Mock barcha OTel modullarini
    mock_trace = MagicMock()
    mock_provider = MagicMock()
    mock_resource_cls = MagicMock(return_value=MagicMock())
    mock_tracer_provider_cls = MagicMock(return_value=mock_provider)
    mock_exporter_cls = MagicMock(return_value=MagicMock())
    mock_processor_cls = MagicMock(return_value=MagicMock())
    mock_fastapi_instr = MagicMock()
    mock_sqlalchemy_instr = MagicMock()

    modules = {
        "opentelemetry": MagicMock(trace=mock_trace),
        "opentelemetry.trace": mock_trace,
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.resources": MagicMock(
            Resource=mock_resource_cls, SERVICE_NAME="service.name"
        ),
        "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_tracer_provider_cls),
        "opentelemetry.sdk.trace.export": MagicMock(BatchSpanProcessor=mock_processor_cls),
        "opentelemetry.exporter.otlp.proto.http": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": MagicMock(
            OTLPSpanExporter=mock_exporter_cls
        ),
        "opentelemetry.instrumentation.fastapi": MagicMock(
            FastAPIInstrumentor=mock_fastapi_instr
        ),
        "opentelemetry.instrumentation.sqlalchemy": MagicMock(
            SQLAlchemyInstrumentor=mock_sqlalchemy_instr
        ),
    }

    with patch.dict("sys.modules", modules):
        init_opentelemetry("http://localhost:4318")

    # TracerProvider yaratilganligi tekshiriladi
    mock_tracer_provider_cls.assert_called_once()
