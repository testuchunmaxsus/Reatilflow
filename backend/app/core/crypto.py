"""
PII shifrlash moduli — ilova-darajali AES-GCM + HMAC blind-index.

Nima uchun ilova-darajali:
  - pgcrypto faqat PostgreSQL da ishlaydi.
  - Testlar aiosqlite da ishlanadi — ilova-darajali shifrlash ikkalasida ham ishlaydi.

Komponentlar:
  encrypt_pii(plaintext)   → bytes | None  — AES-GCM shifrlash
  decrypt_pii(ciphertext)  → str | None    — AES-GCM deshifrlash
  blind_index(value)       → str           — HMAC-SHA256 (aniq-moslik qidiruv)
  verify_crypto_keys()     → None          — Startup self-check (RuntimeError ko'taradi)
  EncryptedString          — SQLAlchemy TypeDecorator (shaffof shifrlash/deshifrlash)

Kalit:
  settings.pii_encryption_key — 64 belgili hex (32-bayt AES kalit), env dan
  settings.blind_index_key    — 64 belgili hex (32-bayt HMAC kaliti), env dan

  Qabul qilinadigan format:
    - Faqat 64 belgili hex string (openssl rand -hex 32).
    - Noto'g'ri format → ValueError (aniq xabar, ilova ishga tushmaydi).
    - SHA-256 fallback OLIB TASHLANGAN — yashirin format xatosi taqiqlangan.

Xavfsizlik:
  - Har encrypt_pii() chaqiruvida yangi 12-baytli IV (nonce) generatsiya qilinadi.
  - IV shifrlangan ma'lumot bilan birga saqlanadi: iv(12) + tag(16) + ciphertext.
  - Kalit hech qachon logga yoki exception xabariga tushmaydi.
  - decrypt_pii: faqat InvalidTag ushlanadi; boshqa xatolar qayta ko'tariladi.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Kalit tayyorlash ─────────────────────────────────────────────────────────

_AES_IV_SIZE = 12   # AES-GCM nonce hajmi (bayt)
_AES_TAG_SIZE = 16  # AES-GCM authentication tag (bayt, standart)
_EXPECTED_KEY_BYTES = 32
_EXPECTED_HEX_LEN = 64  # 32 bayt * 2


@lru_cache(maxsize=1)
def _get_aes_key() -> bytes:
    """
    AES kalit bytes ni qaytaradi.

    Qabul qilinadigan format:
      - Faqat 64 belgili hex string → 32 bayt decode qilinadi.
      - Boshqa har qanday format → ValueError (aniq xabar).

    SHA-256 fallback ataylab OLIB TASHLANGAN:
      Noto'g'ri kalit format yashirin o'tib ketmaslik uchun.

    Xavfsizlik: kalit qiymati hech qachon logga yozilmaydi.

    Raises:
        ValueError: kalit formati noto'g'ri bo'lsa.
    """
    key_str = settings.pii_encryption_key
    actual_len = len(key_str)
    if actual_len != _EXPECTED_HEX_LEN:
        raise ValueError(
            f"PII_ENCRYPTION_KEY noto'g'ri format: kutilgan {_EXPECTED_HEX_LEN} belgili hex, "
            f"olingan {actual_len} belgi. "
            "openssl rand -hex 32 bilan yangi kalit yarating."
        )
    try:
        return bytes.fromhex(key_str)
    except ValueError:
        raise ValueError(
            f"PII_ENCRYPTION_KEY valid hex string emas ({_EXPECTED_HEX_LEN} belgili). "
            "openssl rand -hex 32 bilan yangi kalit yarating."
        )


@lru_cache(maxsize=1)
def _get_hmac_key() -> bytes:
    """
    HMAC kalitini bytes sifatida qaytaradi.

    Qabul qilinadigan format:
      - Faqat 64 belgili hex string → 32 bayt decode qilinadi.
      - Boshqa har qanday format → ValueError (aniq xabar).

    Raises:
        ValueError: kalit formati noto'g'ri bo'lsa.
    """
    key_str = settings.blind_index_key
    actual_len = len(key_str)
    if actual_len != _EXPECTED_HEX_LEN:
        raise ValueError(
            f"BLIND_INDEX_KEY noto'g'ri format: kutilgan {_EXPECTED_HEX_LEN} belgili hex, "
            f"olingan {actual_len} belgi. "
            "openssl rand -hex 32 bilan yangi kalit yarating."
        )
    try:
        return bytes.fromhex(key_str)
    except ValueError:
        raise ValueError(
            f"BLIND_INDEX_KEY valid hex string emas ({_EXPECTED_HEX_LEN} belgili). "
            "openssl rand -hex 32 bilan yangi kalit yarating."
        )


def verify_crypto_keys() -> None:
    """
    Startup self-check: encrypt → decrypt round-trip to'g'ri ishlashini tekshiradi.

    main.py lifespan'dan chaqiriladi — ilova ishga tushganda bir marta.
    Muvaffaqiyatsiz bo'lsa RuntimeError ko'taradi → ilova boshlanmaydi.

    Raises:
        RuntimeError: kalit xato yoki round-trip muvaffaqiyatsiz bo'lsa.
        ValueError: kalit formati noto'g'ri bo'lsa (_get_aes_key dan).
    """
    probe = "crypto-probe-check"
    try:
        encrypted = encrypt_pii(probe)
    except Exception as exc:
        raise RuntimeError(
            f"Crypto startup probe FAILED (encrypt): {exc!r}. "
            "PII_ENCRYPTION_KEY to'g'ri ekanini tekshiring."
        ) from exc

    if encrypted is None:
        raise RuntimeError("Crypto startup probe FAILED: encrypt_pii None qaytardi.")

    try:
        decrypted = decrypt_pii(encrypted)
    except Exception as exc:
        raise RuntimeError(
            f"Crypto startup probe FAILED (decrypt): {exc!r}. "
            "PII_ENCRYPTION_KEY to'g'ri ekanini tekshiring."
        ) from exc

    if decrypted != probe:
        raise RuntimeError(
            f"Crypto startup probe FAILED: round-trip mos kelmadi. "
            f"Kutilgan={probe!r}, olingan={decrypted!r}. "
            "PII_ENCRYPTION_KEY to'g'ri ekanini tekshiring."
        )


# ─── PII shifrlash / deshifrlash ─────────────────────────────────────────────


def encrypt_pii(plaintext: str | None) -> bytes | None:
    """
    Oddiy matni AES-GCM bilan shifrlaydi.

    Formati: iv(12 bayt) + gcm_tag(16 bayt) + ciphertext
    Har chaqiruvda yangi IV — bir xil matn har safar boshqacha shifrlangan.

    Args:
        plaintext: Shifrlash uchun matn. None bo'lsa None qaytaradi.

    Returns:
        Shifrlangan bytes yoki None.
    """
    if plaintext is None:
        return None

    key = _get_aes_key()
    aesgcm = AESGCM(key)
    iv = os.urandom(_AES_IV_SIZE)
    ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    # iv + ciphertext_with_tag (tag ichida)
    return iv + ciphertext_with_tag


def decrypt_pii(ciphertext: bytes | None) -> str | None:
    """
    AES-GCM bilan shifrlangan bytes ni deshifrlaydi.

    Args:
        ciphertext: iv(12) + gcm_ciphertext_with_tag bytes.
                    None yoki bo'sh bo'lsa None qaytaradi.

    Returns:
        Oddiy matn yoki None (faqat InvalidTag xatosi yutiladi).

    Raises:
        Exception: InvalidTag dan boshqa barcha xatolar qayta ko'tariladi.

    Xavfsizlik:
        - Faqat InvalidTag (noto'g'ri authentication tag) ushlanadi va CRITICAL loglanadi.
        - Format/uzunlik xatolari (ciphertext juda qisqa va h.k.) ham CRITICAL loglanadi
          va None qaytariladi.
        - Kalit qiymati hech qachon logga tushtirilmaydi.
    """
    if not ciphertext:
        return None

    # Format/uzunlik tekshiruvi
    min_size = _AES_IV_SIZE + _AES_TAG_SIZE
    if len(ciphertext) < min_size:
        logger.critical(
            "decrypt_pii: ciphertext juda qisqa (uzunlik=%d, minimal=%d) — "
            "buzilgan ma'lumot yoki noto'g'ri format. PII yo'qolishi xavfi.",
            len(ciphertext),
            min_size,
        )
        return None

    try:
        key = _get_aes_key()
        aesgcm = AESGCM(key)
        iv = ciphertext[:_AES_IV_SIZE]
        ct_with_tag = ciphertext[_AES_IV_SIZE:]
        plaintext_bytes = aesgcm.decrypt(iv, ct_with_tag, None)
        return plaintext_bytes.decode("utf-8")
    except InvalidTag:
        # Noto'g'ri authentication tag: noto'g'ri kalit yoki buzilgan ma'lumot.
        # CRITICAL: PII jimgina None bo'lishi katta xavf — operatsiya xabardor etilsin.
        logger.critical(
            "decrypt_pii: InvalidTag — noto'g'ri AES kalit yoki buzilgan ciphertext. "
            "PII ma'lumot yo'qolishi xavfi bor. "
            "PII_ENCRYPTION_KEY va ma'lumot yaxlitligini tekshiring."
        )
        return None


# ─── HMAC Blind-index ─────────────────────────────────────────────────────────


def blind_index(value: str) -> str:
    """
    Aniq-moslik qidiruv uchun HMAC-SHA256 blind-index.

    Normalize: strip + lower case qilinadi.
    Natija: base64url-encoded HMAC string (URL-safe, padding yo'q).

    Foydalanish:
        # Yozishda:
        store.inn_bi = blind_index(inn)
        # Qidirishda:
        stmt = stmt.where(Store.inn_bi == blind_index(search_inn))

    Args:
        value: Indekslanadigan matn (inn, phone va h.k.).

    Returns:
        HMAC-SHA256 base64url string.
    """
    normalized = value.strip().lower()
    key = _get_hmac_key()
    mac = hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


# ─── SQLAlchemy TypeDecorator ─────────────────────────────────────────────────


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy TypeDecorator: str ↔ bytes (AES-GCM shifrlash).

    Yozishda: str → encrypt_pii() → bytes (DB da saqlash).
    O'qishda: bytes → decrypt_pii() → str (Python'da ishlatish).

    Ustun turi: LargeBinary (bytea PostgreSQL, BLOB SQLite).

    Foydalanish:
        class Store(Base):
            inn: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        """Python → DB: shifrlash."""
        if value is None:
            return None
        if isinstance(value, bytes):
            # Allaqachon shifrlangan (masalan, test da to'g'ridan-to'g'ri bytes)
            return value
        return encrypt_pii(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        """DB → Python: deshifrlash."""
        if value is None:
            return None
        if isinstance(value, str):
            # SQLite ba'zan string qaytaradi — bytes ga o'tkazish
            try:
                value = value.encode("latin-1")
            except Exception:
                return value
        return decrypt_pii(value)
