# ============================================================
# RETAIL Backend — Production Dockerfile
# Multi-stage build: builder → runtime
# ============================================================

# ─── Stage 1: builder ────────────────────────────────────────
FROM python:3.12-slim AS builder

# System deps (asyncpg C extensions uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Izolyatsiyalangan venv yaratish
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Avval manba + metadata, keyin o'rnatish (non-editable, manba mavjud)
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install --no-cache-dir .

# ─── Stage 2: runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root foydalanuvchi (xavfsizlik)
RUN groupadd -r retail && useradd -r -g retail -d /app -s /sbin/nologin retail

# System runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Builder'dan to'liq venv ko'chirish (uvicorn PATH'da ishlaydi)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Ilova kodi
COPY --chown=retail:retail . /app/

USER retail

# Prometheus + health uchun
EXPOSE 8000

# Default: API server
# Worker uchun: docker compose override yoki CMD o'zgartiring
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
