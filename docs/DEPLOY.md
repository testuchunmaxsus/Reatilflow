# RETAIL — Deploy Runbook

| | |
|---|---|
| **Versiya** | 0.28.0 |
| **Sana** | 2026-06-19 |
| **Maqsad** | Production va staging muhitlarini ishga tushirish |

> **Muhim:** Bu muhitda GitHub Actions va Docker ishga tushirilmagan.
> Barcha workflow va compose fayllar sintaktik jihatdan to'g'ri va ishlatishga tayyor,
> ammo real CI/CD pipeline sozlashda ushbu runbook'dagi qadamlarni bajar.

---

## 0. Talablar

| Dastur | Versiya |
|---|---|
| Docker | >= 25.x |
| Docker Compose plugin | >= 2.27 |
| Git | >= 2.40 |
| openssl | >= 3.x |

---

## Deploy oldidan tayyorgarlik / TODO

Quyidagi elementlar fayllar darajasida tayyorlangan, lekin real deployment paytida qo'lda bajarilishi kerak.
CI/CD va infra agenti eslatmalari asosida to'plangan.

### TLS sertifikat va domen

`infra/nginx/nginx.prod.conf` da `retail.example.com` o'rniga real domenni yozing va sertifikatni qo'ying:

```bash
mkdir -p infra/nginx/certs
# Let's Encrypt (production):
certbot certonly --standalone -d your-domain.com
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infra/nginx/certs/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem   infra/nginx/certs/
chmod 600 infra/nginx/certs/privkey.pem

# nginx.prod.conf dagi barcha "retail.example.com" ni real domenda almashtiring:
sed -i 's/retail.example.com/your-domain.com/g' infra/nginx/nginx.prod.conf
```

### postgres-replica streaming replication

`docker-compose.prod.yml` da `postgres-replica` servisi placeholder sifatida mavjud.
`infra/postgres/replica-setup.sh` skripti bilan streaming replication avtomatlashtirilgan:

```bash
# Primary serverda:
export REPLICATOR_PASSWORD="$(openssl rand -base64 24)"
export REPLICA_IP="<replica_server_ip>"
bash infra/postgres/replica-setup.sh primary

# Primary PostgreSQL qayta ishga tushiring (wal_level o'zgardi):
docker compose -f docker-compose.prod.yml restart postgres-primary

# Replica serverda:
export REPLICATOR_PASSWORD="<yuqoridagi_parol>"
export PRIMARY_HOST="postgres-primary"
bash infra/postgres/replica-setup.sh replica

# Holat tekshiruv (primary da):
bash infra/postgres/replica-setup.sh status
# yoki:
psql -U postgres -c "SELECT * FROM pg_stat_replication;"
```

Murakkabroq sozlash uchun skriptning `--help` qismini o'qing:
`bash infra/postgres/replica-setup.sh help`

Replica tayyor bo'lgunga qadar `.env.prod` da `DATABASE_REPLICA_URL` ni primary URL ga teng qo'ying:

```
DATABASE_REPLICA_URL=postgresql+asyncpg://retail_user:PASSWORD@postgres-primary:5432/retail_db
```

### Prometheus alert qoidalari

`infra/prometheus/rules/alerts.yml` tayyor — deploy qilishda hech narsa qo'shimcha qilish shart emas.
`infra/prometheus/prometheus.yml` da `rule_files` allaqachon yoqilgan:

```yaml
rule_files:
  - /etc/prometheus/rules/*.yml
```

Qamrab olingan alertlar:
- `ApiDown` — retail-api 1 daqiqa ishlamasa (critical)
- `GpsIngestDown` — GPS ingest servis 2 daqiqa ishlamasa (warning)
- `HighErrorRate` — 5xx > 1% (critical)
- `SlowP99` — p99 latency > 1s (warning)
- `HighClientErrorRate` — 4xx > 5% (warning)
- `DatabaseConnectionPoolExhausted` — DB ulanish > 85% (critical)
- `ReplicationLagHigh` — replica lag > 10MB (warning)
- `PushNotificationErrorRate` — push xato > 5% (warning)
- `PushWorkerStalled` — push worker to'xtab qolsa (critical)
- `DiskSpaceLow` / `DiskSpaceCritical` — disk < 15% / < 5% (warning/critical)
- `TimescaleDbDiskLow` — TimescaleDB disk < 20% (warning)
- `GpsIngestErrorRate` — GPS ingest xato > 2% (warning)

Alertmanager integratsiyasi (`prometheus.yml` da yoqish uchun):
```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]
```

### Push bildirishnomalar (FCM va APNs)

Push delivery production da ishlashi uchun quyidagi fayllar va o'zgaruvchilar tayyorlanishi kerak.

**FCM HTTP v1 (Android, tavsiya):**

```bash
# 1. Firebase Console → Project Settings → Service Accounts → "Generate new private key"
#    Natija: fcm-service-account.json

# 2. Faylni serverga ko'chirish
scp fcm-service-account.json user@prod-server:/run/secrets/fcm-service-account.json
chmod 400 /run/secrets/fcm-service-account.json

# 3. .env.prod ga qo'shish
FCM_PROJECT_ID=your-firebase-project-id
FCM_CREDENTIALS_FILE=/run/secrets/fcm-service-account.json
```

`FCM_SERVER_KEY` (legacy) eskirgan — Google 2024-yildan o'chirishni e'lon qildi. Faqat eski deployment uchun.

**APNs (iOS, token-based):**

```bash
# 1. Apple Developer Console → Certificates, Identifiers & Profiles
#    → Keys → "+" → APNs belgisi qo'yib kalit yaratish
#    Natija: AuthKey_XXXXXXXXXX.p8 (bir marta yuklanadi — zaxira saqlang)

# 2. Faylni serverga ko'chirish
scp AuthKey_XXXXXXXXXX.p8 user@prod-server:/run/secrets/AuthKey_XXXXXXXXXX.p8
chmod 400 /run/secrets/AuthKey_XXXXXXXXXX.p8

# 3. .env.prod ga qo'shish
APNS_KEY_FILE=/run/secrets/AuthKey_XXXXXXXXXX.p8
APNS_KEY_ID=XXXXXXXXXX          # 10 ta belgi (kalit nomi)
APNS_TEAM_ID=YYYYYYYYYY         # 10 ta belgi (Apple Developer Team ID)
APNS_BUNDLE_ID=com.example.retail
APNS_USE_SANDBOX=false          # production; staging uchun true
```

**Sandbox vs Production:**
- `APNS_USE_SANDBOX=true` — TestFlight yoki simulyator (endpoint: `api.sandbox.push.apple.com`).
- `APNS_USE_SANDBOX=false` — App Store ga chiqarilgan ilova (endpoint: `api.push.apple.com`).

**H2 bog'liqligi:** APNs HTTP/2 uchun `httpx[http2]` (`h2` paketi) talab qilinadi — `pyproject.toml` da allaqachon qo'shilgan.

**Tekshiruv:**
```bash
# Worker loglarida push yuborilayotganini tekshirish:
docker compose -f docker-compose.prod.yml --env-file .env.prod logs worker | grep -i "push"
# Kredensial noto'g'ri bo'lsa: "FcmProvider: FCM kredensial/config topilmadi" yoki
#                               "ApnsProvider: APNs kalitlari to'liq emas"
```

---

### SEMGREP_APP_TOKEN GitHub Secret

`.github/workflows/backend.yml` da Semgrep `SEMGREP_APP_TOKEN` secret dan foydalanadi.

- Token yo'q bo'lsa — Semgrep community rejimida ishlaydi (token majburiy emas, lekin dashboard yo'q).
- Token qo'shish: GitHub repo → Settings → Secrets and variables → Actions → `SEMGREP_APP_TOKEN`.

### MinIO bucketlarni birinchi deployda yaratish

`infra/minio/create-buckets.sh` skripti bilan bucket'larni avtomatik yaratish:

```bash
# mc o'rnatilgan bo'lsa:
MINIO_ENDPOINT=http://minio:9000 \
MINIO_ROOT_USER="$MINIO_ROOT_USER" \
MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
  bash infra/minio/create-buckets.sh

# Yoki Docker orqali (mc o'rnatilmagan bo'lsa):
docker run --rm --network retail_default \
  -e MINIO_ENDPOINT=http://minio:9000 \
  -e MINIO_ROOT_USER="$MINIO_ROOT_USER" \
  -e MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
  -v "$(pwd)/infra/minio/create-buckets.sh:/create-buckets.sh" \
  minio/mc:latest sh /create-buckets.sh
```

Yaratiladi: `retail-products`, `retail-contracts`, `retail-delivery-proofs`, `retail-promo`.
Idempotent — qayta ishga tushirilsa xato chiqmaydi.

---

## 1. Secrets tayyorlash

Barcha secrets generatsiya qilib `.env.prod` ga yoziladi.
**Hech qachon .env.prod ni git'ga qo'shmang.**

```bash
# 1.1. Namuna faylni ko'chirish
cp .env.prod.example .env.prod
chmod 600 .env.prod

# 1.2. JWT secret (kamida 32 bayt = 64 hex)
openssl rand -hex 32
# Natijani JWT_SECRET_KEY ga yozing

# 1.3. PII shifrlash kalitlari (har biri alohida, mustaqil)
openssl rand -hex 32   # -> PII_ENCRYPTION_KEY
openssl rand -hex 32   # -> BLIND_INDEX_KEY

# 1.4. DB parollari
openssl rand -base64 24   # -> POSTGRES_PASSWORD
openssl rand -base64 24   # -> TIMESCALE_PASSWORD
openssl rand -base64 24   # -> REDIS_PASSWORD

# 1.5. MinIO
openssl rand -base64 16   # -> MINIO_ROOT_USER (access key)
openssl rand -base64 32   # -> MINIO_ROOT_PASSWORD (secret key)

# 1.6. Grafana
openssl rand -base64 16   # -> GRAFANA_ADMIN_PASSWORD
```

### Secrets tekshiruvi (deploy oldidan majburiy)

```bash
# JWT_SECRET_KEY kamida 64 belgi bo'lishi kerak
python3 -c "
import os; v=os.getenv('JWT_SECRET_KEY','')
assert len(v)>=64, f'JWT_SECRET_KEY juda qisqa: {len(v)}'
print('JWT_SECRET_KEY: OK')
" < <(set -a; . .env.prod; set +a; env)

# PII kalitlar 64 hex bo'lishi kerak
for KEY in PII_ENCRYPTION_KEY BLIND_INDEX_KEY; do
  val=$(grep "^$KEY=" .env.prod | cut -d= -f2)
  [ ${#val} -eq 64 ] && echo "$KEY: OK" || echo "$KEY: XATO — ${#val} belgi"
done
```

---

## 2. TLS sertifikat

```bash
mkdir -p infra/nginx/certs

# Variant A: Let's Encrypt (production)
certbot certonly --standalone -d retail.example.com
cp /etc/letsencrypt/live/retail.example.com/fullchain.pem infra/nginx/certs/
cp /etc/letsencrypt/live/retail.example.com/privkey.pem   infra/nginx/certs/
chmod 600 infra/nginx/certs/privkey.pem

# Variant B: O'z-imzolangan (staging/test)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infra/nginx/certs/privkey.pem \
  -out    infra/nginx/certs/fullchain.pem \
  -subj   "/CN=retail.example.com"
```

---

## 3. Docker image pull / build

```bash
# GitHub Actions yig'ib push qiladi (main branchda).
# Agar local build kerak:
docker build -t ghcr.io/your-org/retail/retail-api:latest backend/

# GHCR dan pull (production):
echo $GITHUB_TOKEN | docker login ghcr.io -u your-org --password-stdin
docker pull ghcr.io/your-org/retail/retail-api:latest
```

---

## 4. Infra servislarini ishga tushirish

```bash
# 4.1. Faqat DB/Redis/MinIO/observability servislarini ishga tushirish
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d postgres-primary postgres-replica timescaledb redis minio \
     prometheus grafana loki promtail

# 4.2. DB sog'ligini tekshirish (barcha healthy bo'lgunga kut)
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
# postgres-primary, timescaledb, redis, minio — barchasi "healthy" bo'lishi kerak
```

---

## 5. Migratsiyalar (OLTP + TimescaleDB)

### 5.1. OLTP migratsiyasi (PostgreSQL primary)

```bash
# API konteynerini migratsiya rejimida ishga tushirish
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic upgrade head"

# Natija: 0001 → 0016 barcha migratsiyalar qo'llanishi kerak
```

### 5.2. TimescaleDB migratsiyasi (GPS hypertable)

`alembic_timescale/` — OLTP dan MUSTAQIL alohida Alembic muhiti.
`TIMESCALE_URL` ga ulanib, `alembic_version_timescale` jadvalida versiya saqlanadi.

**Talablar:** TimescaleDB extension avval o'rnatilishi shart:
```bash
# timescaledb konteynerida:
psql -h timescaledb -U retail_gps_user -d retail_gps \
  -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
```

**Migratsiya:**
```bash
# API konteyneri ichida:
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic -c alembic_timescale.ini upgrade head"

# Yoki make target bilan (lokal):
make migrate-timescale

# Holat tekshiruv:
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic -c alembic_timescale.ini current"
```

**Natija:** `gps_point` hypertable (recorded_at bo'yicha) + `{{ GPS_RETENTION_DAYS }}` kunlik retention policy.

> **Eslatma:** OLTP `alembic upgrade head` (§5.1) endi GPS hypertable DDL'ini chaqirmaydi.
> `0011_gps.py` saqlanadi (OLTP zanjirida), lekin `alembic_timescale/versions/ts0001_gps_hypertable.py`
> TimescaleDB uchun canonical migratsiya hisoblanadi.

#### Migratsiya runbook'lari (kritik migratsiyalar)

| Migratsiya | Tavsif | Ehtiyot chorasi |
|---|---|---|
| `0003` | Katalog constraints (barcode, mxik_code indeks) | Mavjud null barcode larni tozalang |
| `0004` | Store PII + user FK | `store.user_id` null bo'lishi mumkin (eski yozuvlar) |
| `0005` | User phone AES-GCM shifrlash + blind_index | `PII_ENCRYPTION_KEY` va `BLIND_INDEX_KEY` o'rnatilgan bo'lishi shart; backfill uzun vaqt olishi mumkin |
| `0011` | GPS hypertable (TimescaleDB) | `TIMESCALE_URL` alohida kerak; standart `DATABASE_URL` bilan ishlamaydi |

### 5.3. Migratsiya holatini tekshirish

```bash
# OLTP migratsiya holati:
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic current && alembic history --verbose | tail -5"
# Kutilgan: 0018 (head)

# TimescaleDB migratsiya holati:
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic -c alembic_timescale.ini current"
# Kutilgan: ts0001 (head)
```

---

## 6. Seed — admin va demo ma'lumotlar

`backend/scripts/seed.py` — idempotent seed skripti.
Qayta ishga tushirilsa dublikat yaratmaydi (mavjud yozuvlarni tekshiradi).

```bash
# MUHIM: Parolni muhit o'zgaruvchisi sifatida bering (hard-code emas!)
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps \
  -e SEED_ADMIN_PASSWORD="STRONG_ADMIN_PASSWORD_HERE" \
  -e SEED_USER_PASSWORD="STRONG_USER_PASSWORD_HERE" \
  api \
  sh -c "cd /app && python -m scripts.seed"

# Lokal dev uchun:
SEED_ADMIN_PASSWORD="<parol>" SEED_USER_PASSWORD="<parol>" make seed
```

Yaratiladi:
- 1 ta **administrator** (+998901000001)
- 1 ta **agent** (+998901000002, 1-filialga biriktirilgan)
- 1 ta **kuryer** (+998901000003, 2-filialga biriktirilgan)
- 1 ta **buxgalter** (+998901000004, 1-filialga biriktirilgan)
- 4 ta kategoriya (Oziq-ovqat, Ichimliklar, Sut mahsulotlari, Sharbatlar)
- 2 ta narx segmenti (chakana, ulgurji)
- 8 ta mahsulot (MXIK + barcode bilan)
- 3 ta do'kon
- 2 ta agent-do'kon biriktirishlar

> **Xavfsizlik:** `SEED_ADMIN_PASSWORD` o'rnatilmagan bo'lsa — dev-default parol ishlatiladi
> va konsol'da aniq OGOHLANTIRISH chiqariladi. **Production da default parol bilan HECH QACHON ishlatmang.**

---

## 7. Barcha servislarni ishga tushirish

```bash
# 7.1. Barcha servislar (api ×1, gps-ingest ×1, worker ×1)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 7.2. API ni 3 replika bilan (tavsiya etilgan production)
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --scale api=3 --scale gps-ingest=2 --scale worker=2

# 7.3. Holat
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
```

---

## 8. Sog'liq va tayorlik tekshiruvi

```bash
# 8.1. Health
curl -s https://retail.example.com/health | python3 -m json.tool
# Kutilgan: {"status": "ok", "service": "retail-api"}

# 8.2. Readiness (DB + Redis + MinIO)
curl -s https://retail.example.com/readiness | python3 -m json.tool
# Kutilgan: {"status": "ok", "checks": {"postgres": "ok", "redis": "ok", "minio": "ok"}}

# 8.3. Konteynerlar holati
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
# Barcha servislar: Up (healthy) bo'lishi kerak

# 8.4. Loglar (oxirgi 50 qator)
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  logs --tail=50 api

# 8.5. Migratsiya yakunlandi mi?
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic current"
# Kutilgan: 0016 (head)
```

---

## 9. Kuzatuvchanlik (Observability)

```bash
# Grafana: https://retail.example.com/grafana/
# Login: GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD

# Prometheus: (nginx orqali himoyalangan, to'g'ridan-to'g'ri 9090 portiga)
# docker compose port prometheus 9090

# Prometheus metrikalar to'g'ri ishlayaptimi?
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -A3 '"job"'
```

### Tavsiya etilgan Grafana dashboardlar

1. **RETAIL API Overview** — `http_requests_total`, `http_request_duration_seconds` (p50/p95/p99)
2. **Business Metrics** — `orders_created_total`, `auth_login_total`, `gps_ingest_total`, `sync_push_total`
3. **Error Rate** — `rate(http_requests_total{status=~"5.."}[5m])` / jami

### Alertlar (tavsiya)

```yaml
# Prometheus rules (infra/prometheus/rules/retail.yml — kelajak)
groups:
  - name: retail
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "5xx error rate yuqori (>1%)"

      - alert: SlowP99
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "p99 latency > 1s"

      - alert: ApiDown
        expr: up{job="retail-api"} == 0
        for: 1m
        labels:
          severity: critical
```

---

## 10. Rollback strategiyasi

### 10.1. Image rollback (eng tez)

```bash
# Avvalgi image SHA ni olish
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  logs api | grep "Starting retail-api"

# IMAGE_TAG ni o'zgartirish va qayta deploy
IMAGE_TAG=<previous-sha> \
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --no-deps api
```

### 10.2. Migratsiya rollback

> **Ogohlantirish:** PII migratsiyalari (`0005`) va TimescaleDB (`0011`)
> da `downgrade` guard'lar mavjud — ma'lumot yo'qolishini oldini oladi.
> Orqaga qaytarish faqat yozilgan guard'lar ruxsat bergan migratsiyalar uchun xavfsiz.

```bash
# Bitta qadam orqaga
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic downgrade -1"

# Ma'lum reviziyaga qaytish
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api \
  sh -c "cd /app && alembic downgrade 0010"

# DIQQAT: Moliyaviy jadvallar (ledger_entry, stock_movement) append-only.
# Bu jadvallar uchun downgrade faqat jadval tuzilmasini o'zgartiradi,
# mavjud ma'lumotlarni O'CHIMAYDI.
```

### 10.3. Backup dan tiklash (PITR)

```bash
# PostgreSQL PITR (Point-in-Time Recovery)
# 1. Konteynerlarni to'xtatish
docker compose -f docker-compose.prod.yml --env-file .env.prod down

# 2. Postgres volume ni almashtirish (pg_basebackup orqali)
# 3. recovery.conf ni sozlash
# 4. postgres-primary ni ishga tushirish
# 5. Migratsiya holatini tekshirish
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps api sh -c "cd /app && alembic current"
```

---

## 11. GitHub Branch Protection (eslatma)

```
Settings → Branches → main branch protection rules:
  [x] Require status checks to pass before merging
      Required: "Backend CI / pytest", "Web CI / Vitest", "Mobile CI / flutter test"
  [x] Require pull request reviews (min 1)
  [x] Dismiss stale pull request approvals when new commits are pushed
  [x] Require branches to be up to date before merging
```

---

## 12. CI/CD qisqa tavsif

| Fayl | Maqsad | Triggerlar |
|---|---|---|
| `.github/workflows/backend.yml` | ruff+black → pytest → Semgrep → Trivy → Docker push | `backend/**` o'zgarganda |
| `.github/workflows/web.yml` | tsc+ESLint → vitest → build → Trivy | `web/**` o'zgarganda |
| `.github/workflows/mobile.yml` | pub get → build_runner → analyze → flutter test → Trivy | `mobile/**` o'zgarganda |

Docker image **faqat main branchga push bo'lganda** ghcr.io ga yuboriladi.

---

## SRE/Security uchun diqqat joylari

1. **PII kalitlari rotatsiyasi** — `PII_ENCRYPTION_KEY` o'zgarganda barcha shifrlangan qatorlarni qayta shifrlash kerak (backfill). Hozir avtomatlashtirilmagan.
2. **FCM/APNs kalit xavfsizligi** — `FCM_CREDENTIALS_FILE` va `APNS_KEY_FILE` fayllar faqat `worker` konteyneriga mount qilinadi; boshqa servislar uchun emas. Fayl huquqlari `400` (faqat o'qish). Git'ga hech qachon qo'shilmasin.
3. **TimescaleDB migratsiya alohida** — `alembic_timescale/` muhiti `TIMESCALE_URL` ga qarshi ishga tushadi (`alembic_timescale.ini`). OLTP `alembic upgrade head` TimescaleDB migratsiyasini chaqirmaydi. CI da: `alembic -c alembic_timescale.ini upgrade head` alohida step sifatida qo'shing.
4. **MinIO bucketlar** — birinchi deployda `mc mb` bilan bucketlarni yaratish kerak (`retail-products`, `retail-contracts`, `retail-delivery-proofs`).
5. **Redis AUTH** — production'da `REDIS_PASSWORD` bo'sh bo'lmasligi shart; `validate_pii_keys_in_prod()` ga o'xshash tekshiruv redis uchun ham qo'shilishi tavsiya etiladi.
6. **Grafana sub-path** — nginx `/grafana/` sub-path orqali chiqaradi; `GF_SERVER_ROOT_URL` va `GF_SERVER_SERVE_FROM_SUB_PATH` to'g'ri o'rnatilgan.
7. **`/metrics` endpointi** — hozir ochiq; nginx'da IP-whitelist yoki basic auth bilan himoyalash tavsiya etiladi.
8. **Sentry PII** — `send_default_pii=False` o'rnatilgan; request body Sentry ga bormaydi.
