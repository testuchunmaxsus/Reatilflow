"""
Ilova konfiguratsiyasi — Pydantic Settings.

Barcha o'zgaruvchilar .env faylidan (yoki muhit o'zgaruvchilaridan) o'qiladi.
Hech qachon bu yerda real qiymat yozmang — faqat .env.example dan foydalaning.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Ilova ─────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 1

    # CORS — vergul bilan ajratilgan originlar ro'yxati
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ─── PostgreSQL (Primary) ───────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://retail_user:devpassword@localhost:5432/retail"
    )
    # O'qish replikasi (keyinchalik; hozir primary URL ga fallback)
    database_replica_url: str | None = None

    # ─── TimescaleDB ────────────────────────────────────────────
    # Alohida TimescaleDB ixtiyoriy. Belgilanmasa (TIMESCALE_URL env yo'q) — asosiy
    # DB'ga fallback qilamiz: gps_point 0011 migratsiyada asosiy OLTP bazada ham
    # yaratiladi (timescaledb extension bo'lmasa oddiy jadval). Prod'da alohida
    # Timescale instance bo'lsa — TIMESCALE_URL bering.
    timescale_url: str | None = None

    # ─── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://:devpassword_redis@localhost:6379/0"
    redis_db_session: int = 0
    redis_db_cache: int = 1
    redis_db_queue: int = 2

    # ─── MinIO ──────────────────────────────────────────────────
    minio_endpoint_url: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "devpassword_minio"
    minio_bucket_products: str = "retail-products"
    minio_bucket_contracts: str = "retail-contracts"
    minio_bucket_proofs: str = "retail-delivery-proofs"

    # ─── JWT / Auth ─────────────────────────────────────────────
    jwt_secret_key: str = "CHANGE_ME_in_env_file_never_use_this_default"
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ─── Kuzatuvchanlik ─────────────────────────────────────────
    log_level: str = "INFO"
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: str | None = None

    # ─── SQL echo — alohida o'zgaruvchi (app_debug dan mustaqil) ────────────
    # SQL_ECHO=true/false — faqat shunga bog'liq; app_debug emas
    sql_echo: bool = False

    # ─── Ombor (T11) ────────────────────────────────────────────────────────
    # Standart ombor UUID — .env da DEFAULT_WAREHOUSE_ID o'zgaruvchisi orqali bering.
    # Dev default: T11 da ishlatiladigan fixed UUID.
    default_warehouse_id: str = "ffffcccc-0000-7000-8000-aaaaaaaaaaaa"

    # ─── Expiry (MP4) ───────────────────────────────────────────────────────────
    # Korxonaga bildirishnoma chegarasi (kun): expiry_date <= now + N → bildirishnoma
    expiry_notify_days: int = 2
    # POS sotuv blok chegarasi (kun): expiry_date <= now + N → sotuv bloklanadi
    pos_expiry_block_days: int = 3

    # ─── Sync (T13) ─────────────────────────────────────────────────────────
    # Push batch maksimal operatsiyalar soni
    sync_max_batch: int = 100
    # Pull maksimal hodisalar soni (bir so'rovda)
    sync_pull_limit: int = 200

    # ─── GPS Ingest (T17) ────────────────────────────────────────────────────
    # Batch GPS nuqtalar maksimal soni (bitta so'rovda)
    gps_max_batch: int = 500
    # GPS trekking retention davri (kun) — TimescaleDB add_retention_policy uchun
    # Hozir faqat izoh/TODO — scheduled job yoki migration kengaytirish kerak
    gps_retention_days: int = 90
    # ADR §3.7 — GPS ish-soati filtri (maxfiylik)
    # True  (default): GPS nuqtalar FAQAT aktiv attendance sessiyasida saqlanadi.
    #                  check_in_at <= ingested_at (server vaqti) < check_out_at
    #                  (yoki check_out_at IS NULL — hali chiqmagan).
    # False           : filtr o'chirilgan — barcha nuqtalar saqlanadi (backward-compat/test).
    # .env da: GPS_WORK_HOURS_FILTER_ENABLED=false
    gps_work_hours_filter_enabled: bool = True

    # ─── Push bildirishnomalar (T19) ─────────────────────────────────────────
    # FCM (Firebase Cloud Messaging) — production da .env orqali bering
    #
    # FCM v1 API (tavsiya etiladi):
    #   FCM_PROJECT_ID    — Firebase proyekt ID (FCM HTTP v1 uchun)
    #   FCM_CREDENTIALS_FILE — service-account JSON fayl yo'li (.env.prod da)
    #
    # ESKIRGAN: Legacy server key (FCM v0/HTTP v1 emas) — .env da FCM_SERVER_KEY.
    # FCM_SERVER_KEY ishlatish uchun qo'llab-quvvatlanadi, lekin
    # Google 2024-yildan FCM legacy API ni o'chirishni e'lon qildi.
    # Yangi loyihalar uchun FCM HTTP v1 + service account ishlatilsin.
    fcm_server_key: str | None = None
    # FCM v1: service account JSON fayl yo'li — .env da FCM_CREDENTIALS_FILE
    fcm_credentials_file: str | None = None
    # FCM v1: service account JSON to'g'ridan-to'g'ri (base64 yoki JSON satr) — .env da FCM_CREDENTIALS
    fcm_credentials: str | None = None
    # FCM v1: Firebase proyekt ID — .env da FCM_PROJECT_ID
    fcm_project_id: str | None = None

    # APNs (Apple Push Notification service) — production da .env orqali bering
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_bundle_id: str | None = None
    # APNs .p8 kalit fayl yo'li — .env da APNS_KEY_FILE
    apns_key_file: str | None = None
    # APNs private key PEM matni — .env da APNS_PRIVATE_KEY_PEM orqali (fayl yo'li o'rniga)
    apns_private_key_pem: str | None = None
    # APNs sandbox rejimi (development) — .env da APNS_USE_SANDBOX=true/false
    apns_use_sandbox: bool = False

    # Push worker sozlamalari
    # Bir ishlovda max qayta ishlanadigan hodisalar soni
    push_max_retries: int = 3
    # Push worker davriy ishga tushirish oraligi (sekunda)
    push_poll_interval_seconds: int = 30

    # ─── AI Tahlil (Faza 4) ─────────────────────────────────────────────────
    # Anthropic API kaliti (ixtiyoriy) — bo'lmasa rule-based fallback
    anthropic_api_key: str | None = None
    # Claude model ID (default: tez va arzon)
    anthropic_model: str = "claude-3-haiku-20240307"
    # AI boyitishni to'liq o'chirish (ANTHROPIC_API_KEY bo'lsa ham)
    analytics_ai_enabled: bool = True

    # ─── PII shifrlash kalitlari (T5) ──────────────────────────────────────
    # AES-256-GCM kaliti: 64 belgili hex (openssl rand -hex 32)
    # Dev default: haqiqiy 64 belgili hex — SHA-256 fallback yo'q (HIGH xavfsizlik fix).
    # PROD da albatta .env orqali yangi kalit bering.
    pii_encryption_key: str = (
        "213aa3cd714c3c908d44865643e3aff4e6018d4d147857dfd8f54a361fb50884"
    )
    # HMAC blind-index kaliti: 64 belgili hex
    blind_index_key: str = (
        "8d8305efc948d6c95b5048f4f914fc205ad45f5294e3ee71cee7911c230a189f"
    )

    @model_validator(mode="after")
    def validate_jwt_secret_in_prod(self) -> "Settings":
        """Production/staging muhitida zaif JWT kalitni rad etish."""
        if self.app_env in ("production", "staging"):
            key = self.jwt_secret_key
            if key.startswith("CHANGE_ME") or len(key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY production/staging muhitida kamida 32 belgili "
                    "bo'lishi va 'CHANGE_ME' bilan boshlanmasligi shart. "
                    "openssl rand -hex 32 bilan yangi kalit yarating."
                )
        return self

    @model_validator(mode="after")
    def validate_pii_keys_in_prod(self) -> "Settings":
        """
        PII shifrlash kalitlarini tekshiradi.

        Barcha muhitlarda:
          - Faqat 64 belgili hex qabul qilinadi (format validatsiyasi).
        Production/staging da qo'shimcha:
          - 'CHANGE_ME' taqiqlangan.
          - Ma'lum DEV-DEFAULT qiymatlari taqiqlangan (DENYLIST).
            Dev-default kalitlar haqiqiy 64-belgili hex bo'lgani uchun
            format tekshiruvi ularni o'tkazib yuboradi. Agar .env o'rnatilmasa
            va dev-default ishlatilsa — prod ishga tushmaydi.
        """
        _HEX_LEN = 64

        # Dev-default kalit qiymatlari (source code da hardcoded).
        # Bu qiymatlar ommaviy ma'lum — production da ishlatish taqiqlangan.
        _DEV_DEFAULT_PII_KEY = (
            "213aa3cd714c3c908d44865643e3aff4e6018d4d147857dfd8f54a361fb50884"
        )
        _DEV_DEFAULT_BLIND_KEY = (
            "8d8305efc948d6c95b5048f4f914fc205ad45f5294e3ee71cee7911c230a189f"
        )

        # Format validatsiyasi — barcha muhitlarda
        def _is_valid_hex(s: str) -> bool:
            if len(s) != _HEX_LEN:
                return False
            try:
                bytes.fromhex(s)
                return True
            except ValueError:
                return False

        if not _is_valid_hex(self.pii_encryption_key):
            raise ValueError(
                f"PII_ENCRYPTION_KEY noto'g'ri format: kutilgan {_HEX_LEN} belgili hex, "
                f"olingan {len(self.pii_encryption_key)} belgi. "
                "openssl rand -hex 32 bilan yangi kalit yarating."
            )
        if not _is_valid_hex(self.blind_index_key):
            raise ValueError(
                f"BLIND_INDEX_KEY noto'g'ri format: kutilgan {_HEX_LEN} belgili hex, "
                f"olingan {len(self.blind_index_key)} belgi. "
                "openssl rand -hex 32 bilan yangi kalit yarating."
            )

        if self.app_env in ("production", "staging"):
            if "CHANGE_ME" in self.pii_encryption_key:
                raise ValueError(
                    "PII_ENCRYPTION_KEY production/staging muhitida 'CHANGE_ME' "
                    "bilan boshlanmasligi shart. "
                    "openssl rand -hex 32 bilan yangi kalit yarating."
                )
            if "CHANGE_ME" in self.blind_index_key:
                raise ValueError(
                    "BLIND_INDEX_KEY production/staging muhitida 'CHANGE_ME' "
                    "bilan boshlanmasligi shart. "
                    "openssl rand -hex 32 bilan yangi kalit yarating."
                )
            # DENYLIST: dev-default qiymatlarni production/staging da taqiqlash.
            # Bu qiymatlar source code da ommaviy — ishlatish xavfsizlik buzilishi.
            if self.pii_encryption_key == _DEV_DEFAULT_PII_KEY:
                raise ValueError(
                    "PII_ENCRYPTION_KEY production/staging muhitida dev-default "
                    "qiymat bilan ishlatilmoqda. "
                    "Bu kalit ommaviy ma'lum — xavfsizlik xatosi. "
                    "openssl rand -hex 32 bilan yangi unikal kalit yarating va "
                    ".env faylida o'rnating."
                )
            if self.blind_index_key == _DEV_DEFAULT_BLIND_KEY:
                raise ValueError(
                    "BLIND_INDEX_KEY production/staging muhitida dev-default "
                    "qiymat bilan ishlatilmoqda. "
                    "Bu kalit ommaviy ma'lum — xavfsizlik xatosi. "
                    "openssl rand -hex 32 bilan yangi unikal kalit yarating va "
                    ".env faylida o'rnating."
                )
        return self

    @model_validator(mode="after")
    def normalize_async_pg_urls(self) -> "Settings":
        """
        PostgreSQL URL'larini asyncpg drayveriga normalizatsiya qiladi.

        Railway / Heroku / ko'pchilik managed Postgres `postgres://` yoki
        `postgresql://` sxemasida `DATABASE_URL` beradi. SQLAlchemy async engine
        esa `postgresql+asyncpg://` ni kutadi. Bu validator sxemani avtomatik
        to'g'rilaydi — shunda Railway'da `DATABASE_URL` ni qo'lda o'zgartirish
        shart emas.

        SQLite (test) va allaqachon `+asyncpg` bo'lgan URL'lar O'ZGARMAYDI.
        """

        def _to_asyncpg(url: str | None) -> str | None:
            if not url:
                return url
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            if url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            return url

        self.database_url = _to_asyncpg(self.database_url) or self.database_url
        self.database_replica_url = _to_asyncpg(self.database_replica_url)
        # TimescaleDB alohida sozlanmagan bo'lsa — asosiy DB'ga fallback
        # (gps_point 0011 da asosiy bazada ham mavjud). Aks holda gps endpointlari
        # ulanib bo'lmaydigan localhost'ga urinib 500 beradi.
        if not self.timescale_url:
            self.timescale_url = self.database_url
        self.timescale_url = _to_asyncpg(self.timescale_url) or self.timescale_url
        return self

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> "Settings":
        """allow_origins=['*'] + allow_credentials=True xavfli kombinatsiyani rad et."""
        origins = self.cors_origins_list
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS ichida '*' (wildcard) ishlatish mumkin emas — "
                "credentials=True bilan birgalikda xavfsizlik xatosi. "
                "Aniq originlarni ko'rsating."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Kesh bilan Settings singletoni — bitta o'qish."""
    return Settings()


# Modul darajasida qulay import uchun
settings = get_settings()
