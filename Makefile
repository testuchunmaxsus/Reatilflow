.PHONY: up down migrate migrate-down migrate-timescale seed gen-client \
        test test-cov lint lint-fix \
        ci-backend ci-web ci-mobile \
        deploy-prod help

# Default target
help:
	@echo "RETAIL — asosiy buyruqlar:"
	@echo ""
	@echo "  Dev infra:"
	@echo "  make up            Docker Compose (dev) servislarini ishga tushirish"
	@echo "  make down          Docker Compose (dev) servislarini to'xtatish"
	@echo "  make migrate             Alembic OLTP migratsiyalarini ishlatish"
	@echo "  make migrate-timescale   TimescaleDB alohida migratsiyasini ishlatish"
	@echo "  make seed                Demo ma'lumotlarini yuklash (idempotent)"
	@echo ""
	@echo "  Lokal CI simulyatsiya:"
	@echo "  make ci-backend    Backend CI: lint + test + (ixtiyoriy) SAST"
	@echo "  make ci-web        Veb CI: typecheck + lint + test + build"
	@echo "  make ci-mobile     Mobil CI: pub get + build_runner + analyze + test"
	@echo ""
	@echo "  Deploy:"
	@echo "  make deploy-prod   Production deploy eslatmasi (toʻliq: docs/DEPLOY.md)"
	@echo ""
	@echo "  Boshqalar:"
	@echo "  make gen-client    OpenAPI dan TS + Dart klientlarini generatsiya"
	@echo "  make test          pytest testlarini ishlatish"
	@echo "  make lint          ruff + black tekshiruvi"

# ─── Infra ───────────────────────────────────────────────────────────────────

up:
	docker compose up -d
	@echo "Servislar ishga tushdi. Holat:"
	docker compose ps

down:
	docker compose down

# ─── Backend ─────────────────────────────────────────────────────────────────

migrate:
	cd backend && alembic upgrade head

migrate-down:
	# OGOHLANTIRISH: Bu buyruq faqat bitta migratsiyani orqaga qaytaradi.
	# Toʻliq orqaga qaytarish (base) uchun: cd backend && alembic downgrade base
	cd backend && alembic downgrade -1

migrate-timescale:
	# TimescaleDB alohida Alembic migratsiyasi.
	# TIMESCALE_URL ga ulanadi (OLTP DATABASE_URL emas).
	# Talablar: TimescaleDB extension o'rnatilgan bo'lishi shart.
	#   CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;  (timescaledb'da)
	cd backend && alembic -c alembic_timescale.ini upgrade head

seed:
	# Demo ma'lumotlarni yuklash — idempotent (qayta ishga tushsa dublikat yaratmaydi).
	# Parol: SEED_ADMIN_PASSWORD va SEED_USER_PASSWORD muhit o'zgaruvchilaridan olinadi.
	# O'rnatilmagan bo'lsa — dev-default parol ishlatiladi (faqat dev/demo uchun).
	cd backend && python -m scripts.seed

# ─── Klient generatsiya ──────────────────────────────────────────────────────
#
# Talablar:
#   npm install -g @openapitools/openapi-generator-cli   (Dart/Flutter)
#   npx openapi-typescript                                (TypeScript)
#
# API serveri ishlab turishi kerak (yoki --input fayl orqali):
#   uvicorn app.main:app --host 0.0.0.0 --port 8000
#
gen-client:
	@echo "==> TypeScript klient generatsiya (web/src/api/)"
	npx openapi-typescript http://localhost:8000/openapi.json \
	    --output web/src/api/schema.ts
	@echo "==> Dart klient generatsiya (mobile/lib/api/)"
	openapi-generator-cli generate \
	    -i http://localhost:8000/openapi.json \
	    -g dart-dio \
	    -o mobile/lib/api \
	    --additional-properties=pubName=retail_api,pubVersion=0.1.0

# ─── Test ────────────────────────────────────────────────────────────────────

test:
	cd backend && python -m pytest app/tests/ -v

test-cov:
	cd backend && python -m pytest app/tests/ -v \
	    --cov=app --cov-report=term-missing --cov-report=html

# ─── Lint ────────────────────────────────────────────────────────────────────

lint:
	cd backend && ruff check app/ && black --check app/

lint-fix:
	cd backend && ruff check --fix app/ && black app/

# ─── Lokal CI simulyatsiya ────────────────────────────────────────────────────
#
# GitHub Actions ishga tushirishdan oldin lokal tekshirish uchun.
# Aynan CI workflow bosqichlarini takrorlaydi.

ci-backend:
	@echo "==> [1/3] Lint (ruff + black)"
	cd backend && ruff check app/ && black --check app/
	@echo "==> [2/3] pytest (SQLite test rejimi)"
	cd backend && \
	  APP_ENV=test \
	  DATABASE_URL="sqlite+aiosqlite:///:memory:" \
	  DATABASE_REPLICA_URL="sqlite+aiosqlite:///:memory:" \
	  TIMESCALE_URL="sqlite+aiosqlite:///:memory:" \
	  JWT_SECRET_KEY="ci-test-secret-key-at-least-32-characters-long" \
	  PII_ENCRYPTION_KEY="0000000000000000000000000000000000000000000000000000000000000000" \
	  BLIND_INDEX_KEY="0000000000000000000000000000000000000000000000000000000000000000" \
	  MINIO_ENDPOINT_URL="http://localhost:9000" \
	  MINIO_ROOT_USER="minioadmin" \
	  MINIO_ROOT_PASSWORD="minioadmin" \
	  LOG_LEVEL="WARNING" \
	  python -m pytest app/tests/ -v --tb=short
	@echo "==> [3/3] Semgrep (agar oʻrnatilgan boʻlsa)"
	@semgrep --config=p/python --config=p/secrets backend/app/ 2>/dev/null \
	  || echo "  Semgrep oʻrnatilmagan — oʻtkazib yuborildi (CI da ishga tushiriladi)"
	@echo "==> ci-backend PASS"

ci-web:
	@echo "==> [1/3] TypeScript check + ESLint"
	cd web && npm ci && npx tsc --noEmit && npm run lint
	@echo "==> [2/3] Vitest"
	cd web && npm test
	@echo "==> [3/3] Production build"
	cd web && npm run build
	@echo "==> ci-web PASS"

ci-mobile:
	@echo "==> [1/3] flutter pub get"
	cd mobile && flutter pub get
	@echo "==> [2/3] build_runner (Drift + Riverpod .g.dart)"
	cd mobile && dart run build_runner build --delete-conflicting-outputs
	@echo "==> [3/3] flutter analyze + test"
	cd mobile && flutter analyze --no-fatal-infos && flutter test
	@echo "==> ci-mobile PASS"

# ─── Production deploy ────────────────────────────────────────────────────────
#
# TOʻLIQ KOʻRSATMALAR: docs/DEPLOY.md
#
# Ushbu buyruq faqat eslatma chiqaradi.

deploy-prod:
	@echo ""
	@echo "RETAIL production deploy:"
	@echo ""
	@echo "  1. Secrets tayyorla (docs/DEPLOY.md §1):"
	@echo "     cp .env.prod.example .env.prod && chmod 600 .env.prod"
	@echo "     openssl rand -hex 32  # JWT_SECRET_KEY"
	@echo "     openssl rand -hex 32  # PII_ENCRYPTION_KEY"
	@echo "     openssl rand -hex 32  # BLIND_INDEX_KEY"
	@echo ""
	@echo "  2. TLS sertifikat (docs/DEPLOY.md §2):"
	@echo "     certbot certonly --standalone -d retail.example.com"
	@echo ""
	@echo "  3. Infra ishga tushir:"
	@echo "     docker compose -f docker-compose.prod.yml --env-file .env.prod up -d"
	@echo ""
	@echo "  4. Migratsiyalar (OLTP):"
	@echo "     docker compose -f docker-compose.prod.yml --env-file .env.prod \\"
	@echo "       run --rm --no-deps api sh -c 'alembic upgrade head'"
	@echo ""
	@echo "  5. TimescaleDB migratsiya (alohida env):"
	@echo "     make migrate-timescale"
	@echo "     # Yoki to'g'ridan-to'g'ri:"
	@echo "     cd backend && alembic -c alembic_timescale.ini upgrade head"
	@echo ""
	@echo "  5b. Seed (ixtiyoriy — demo muhit):"
	@echo "     SEED_ADMIN_PASSWORD=<strong_pass> make seed"
	@echo ""
	@echo "  5c. MinIO bucket'larni yaratish:"
	@echo "     MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... bash infra/minio/create-buckets.sh"
	@echo ""
	@echo "  6. Health tekshiruv:"
	@echo "     curl https://retail.example.com/health"
	@echo "     curl https://retail.example.com/readiness"
	@echo ""
	@echo "  Toʻliq runbook: docs/DEPLOY.md"
	@echo ""
