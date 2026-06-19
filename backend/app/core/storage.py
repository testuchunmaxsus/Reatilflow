"""
Fayl saqlash interfeysi va implementatsiyalari.

StorageBackend — abstrakt interfeys (dependency injection uchun).
MinIOStorage   — haqiqiy MinIO/S3 implementatsiyasi (production).
FakeStorage    — test uchun in-memory implementatsiyasi.

Foydalanish (endpoint da):
    storage = get_storage()  # dependency
    url = await storage.upload_product_photo(file)
    url = await storage.upload_contract_file(file)   # PDF yoki rasm

Validatsiya:
  - Magic bytes (imzo): faqat JPEG (FF D8 FF), PNG (89 50 4E 47), WebP (RIFF....WEBP)
  - PDF: %PDF magic bytes (25 50 44 46) — shartnoma fayllari uchun
  - Content-Type ga ishonilmaydi — magic bytes birlamchi manba
  - Fayl kengaytmasi whitelist'dan (jpg/jpeg/png/webp), foydalanuvchi nomidan emas
  - Hajm: MAX_PHOTO_SIZE_BYTES (5 MB), MAX_CONTRACT_FILE_BYTES (20 MB)

Xato: AppError("catalog.invalid_photo") noto'g'ri magic bytes, MIME yoki katta hajm.
      AppError("contracts.invalid_file") noto'g'ri shartnoma fayli.
      AppError("catalog.storage_error") MinIO upload xatosi (503).
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from fastapi import UploadFile

from app.core.errors import AppError

logger = logging.getLogger(__name__)

# ─── Konstantalar ────────────────────────────────────────────────────────────

MAX_PHOTO_SIZE_BYTES: int = 5 * 1024 * 1024    # 5 MB
MAX_CONTRACT_FILE_BYTES: int = 20 * 1024 * 1024  # 20 MB

# Magic bytes va kengaytmalar whitelist
# (magic_prefix, kengaytma)
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpg"),          # JPEG
    (b"\x89PNG\r\n\x1a\n", "png"),     # PNG (to'liq 8-bayt imzo)
    # WebP: "RIFF" + 4 bayt hajm + "WEBP"
]

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"jpg", "jpeg", "png", "webp"})

# WebP ajratib tekshiriladi (offset tufayli)
_WEBP_PREFIX = b"RIFF"
_WEBP_MARKER = b"WEBP"

# PDF magic bytes: %PDF (25 50 44 46)
_PDF_MAGIC = b"%PDF"

# Magic bytes uchun o'qiladigan minimal hajm
_MAGIC_READ_BYTES = 12


# ─── Magic bytes yordamchisi ─────────────────────────────────────────────────


def _detect_image_type(data: bytes) -> str | None:
    """
    Baytlarning magic bytes'ini tekshirib rasm turini aniqlaydi.

    Returns:
        Kengaytma: "jpg", "png", "webp" yoki None (tan olinmagan format).
    """
    if len(data) < _MAGIC_READ_BYTES:
        return None

    header = data[:_MAGIC_READ_BYTES]

    # JPEG: FF D8 FF
    if header[:3] == b"\xff\xd8\xff":
        return "jpg"

    # PNG: 89 50 4E 47 0D 0A 1A 0A (8 bayt)
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    # WebP: RIFF????WEBP (bytes 0-3 = "RIFF", bytes 8-11 = "WEBP")
    if header[:4] == _WEBP_PREFIX and header[8:12] == _WEBP_MARKER:
        return "webp"

    return None


def _detect_contract_file_type(data: bytes) -> str | None:
    """
    Shartnoma fayli turini magic bytes orqali aniqlaydi.

    Ruxsat etilgan formatlar:
      - PDF: %PDF (25 50 44 46)
      - Rasm: JPEG, PNG, WebP

    Returns:
        Kengaytma: "pdf", "jpg", "png", "webp" yoki None.
    """
    if len(data) < _MAGIC_READ_BYTES:
        return None

    # PDF: %PDF
    if data[:4] == _PDF_MAGIC:
        return "pdf"

    # Rasm formatlar (JPEG, PNG, WebP)
    return _detect_image_type(data)


# ─── Abstrakt interfeys ───────────────────────────────────────────────────────


class StorageBackend(ABC):
    """Fayl saqlash abstrakt interfeysi."""

    @abstractmethod
    async def upload_product_photo(self, file: UploadFile) -> str:
        """
        Mahsulot rasmini yuklaydi va URL qaytaradi.

        Magic bytes va hajm validatsiyasi shu metod ichida amalga oshiriladi.

        Args:
            file: FastAPI UploadFile obyekti.

        Returns:
            Rasm URL manzili (public yoki presigned).

        Raises:
            AppError("catalog.invalid_photo"): Magic bytes noto'g'ri yoki hajm katta.
            AppError("catalog.storage_error"): MinIO/S3 upload xatosi (503).
        """

    @abstractmethod
    async def upload_contract_file(self, file: UploadFile) -> str:
        """
        Shartnoma faylini yuklaydi va URL qaytaradi.

        Ruxsat etilgan formatlar: PDF, JPEG, PNG, WebP.
        Hajm: MAX_CONTRACT_FILE_BYTES (20 MB).

        Args:
            file: FastAPI UploadFile obyekti.

        Returns:
            Fayl URL manzili (public yoki presigned).

        Raises:
            AppError("contracts.invalid_file"): Magic bytes noto'g'ri yoki hajm katta.
            AppError("catalog.storage_error"): MinIO/S3 upload xatosi (503).
        """


# ─── Validatsiya yordamchisi ─────────────────────────────────────────────────


async def _validate_photo(file: UploadFile) -> tuple[bytes, str]:
    """
    Rasm faylini validatsiya qiladi va (baytlar, kengaytma) qaytaradi.

    Tekshiruvlar:
      1. Fayl o'qiladi va hajm MAX_PHOTO_SIZE_BYTES dan oshmasligi tekshiriladi.
      2. Magic bytes tekshiriladi: faqat JPEG, PNG, WebP ruxsat.
         Content-Type ga ishonilmaydi — magic bytes birlamchi.
      3. Kengaytma magic bytes dan aniqlangan turdan olinadi (whitelist).

    Raises:
        AppError("catalog.invalid_photo"): Validatsiya muvaffaqiyatsiz.

    Returns:
        (data_bytes, ext) — baytlar va whitelist kengaytmasi ("jpg", "png", "webp").
    """
    # Fayl o'qish + hajm tekshirish
    data = await file.read()

    if len(data) == 0:
        raise AppError("catalog.invalid_photo", status_code=422)

    if len(data) > MAX_PHOTO_SIZE_BYTES:
        raise AppError("catalog.invalid_photo", status_code=422)

    # Magic bytes tekshirish (Content-Type ga ishonilmaydi)
    detected_ext = _detect_image_type(data)
    if detected_ext is None:
        logger.warning(
            "_validate_photo: tan olinmagan magic bytes "
            "(content_type=%r, filename=%r, size=%d)",
            file.content_type, file.filename, len(data),
        )
        raise AppError("catalog.invalid_photo", status_code=422)

    return data, detected_ext


async def _validate_contract_file(file: UploadFile) -> tuple[bytes, str]:
    """
    Shartnoma faylini validatsiya qiladi va (baytlar, kengaytma) qaytaradi.

    Tekshiruvlar:
      1. Fayl o'qiladi va hajm MAX_CONTRACT_FILE_BYTES dan oshmasligi tekshiriladi.
      2. Magic bytes tekshiriladi: PDF, JPEG, PNG, WebP ruxsat.
         Content-Type ga ishonilmaydi — magic bytes birlamchi.

    Raises:
        AppError("contracts.invalid_file"): Validatsiya muvaffaqiyatsiz.

    Returns:
        (data_bytes, ext) — baytlar va whitelist kengaytmasi ("pdf", "jpg", "png", "webp").
    """
    data = await file.read()

    if len(data) == 0:
        raise AppError("contracts.invalid_file", status_code=422)

    if len(data) > MAX_CONTRACT_FILE_BYTES:
        raise AppError("contracts.invalid_file", status_code=422)

    detected_ext = _detect_contract_file_type(data)
    if detected_ext is None:
        logger.warning(
            "_validate_contract_file: tan olinmagan magic bytes "
            "(content_type=%r, filename=%r, size=%d)",
            file.content_type, file.filename, len(data),
        )
        raise AppError("contracts.invalid_file", status_code=422)

    return data, detected_ext


# ─── Fake implementatsiya (test uchun) ───────────────────────────────────────


class FakeStorage(StorageBackend):
    """
    In-memory test implementatsiyasi.

    Rasmlarni xotirada saqlaydi; haqiqiy MinIO kerak emas.
    `uploaded` dict — test tekshiruvi uchun.
    """

    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    async def upload_product_photo(self, file: UploadFile) -> str:
        data, ext = await _validate_photo(file)
        file_id = str(uuid.uuid4())
        self.uploaded[file_id] = data
        url = f"http://fake-storage/products/{file_id}.{ext}"
        logger.debug("FakeStorage: uploaded %s (%d bytes, ext=%s)", file_id, len(data), ext)
        return url

    async def upload_contract_file(self, file: UploadFile) -> str:
        data, ext = await _validate_contract_file(file)
        file_id = str(uuid.uuid4())
        self.uploaded[file_id] = data
        url = f"http://fake-storage/contracts/{file_id}.{ext}"
        logger.debug("FakeStorage: contract uploaded %s (%d bytes, ext=%s)", file_id, len(data), ext)
        return url


# ─── MinIO implementatsiyasi (production) ────────────────────────────────────


class MinIOStorage(StorageBackend):
    """
    MinIO/S3 implementatsiyasi.

    Smoke-test: haqiqiy MinIO instance kerak bo'lganda ishlatiladi.
    Test muhitida FakeStorage bilan almashtiriladi (dependency override).

    NOTE: boto3 yoki minio kutubxonasi o'rnatilmagan bo'lsa ImportError uchraydi.
    Bu holatda get_storage() FakeStorage qaytarishi mumkin (settings ga bog'liq).
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._client: Any = None

    def _get_client(self) -> Any:
        """boto3 klientini lazy init qilish."""
        if self._client is None:
            try:
                import boto3  # type: ignore[import-untyped]

                self._client = boto3.client(
                    "s3",
                    endpoint_url=self._endpoint_url,
                    aws_access_key_id=self._access_key,
                    aws_secret_access_key=self._secret_key,
                )
            except ImportError:
                logger.error("boto3 o'rnatilmagan — MinIO ishlamaydi")
                raise
        return self._client

    async def upload_product_photo(self, file: UploadFile) -> str:
        """Rasmni MinIO ga yuklaydi, public URL qaytaradi."""
        data, ext = await _validate_photo(file)

        # Kengaytma whitelist'dan (ext magic bytes dan aniqlangan),
        # foydalanuvchi fayl nomidan EMAS
        key = f"products/{uuid7()}.{ext}"

        # ContentType ham magic bytes dan aniqlangan turdan
        _mime_map = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
        content_type = _mime_map.get(ext, "image/jpeg")

        # asyncio.get_running_loop() — to'g'ri (get_event_loop() deprecated)
        loop = asyncio.get_running_loop()
        client = self._get_client()

        try:
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=io.BytesIO(data),
                    ContentType=content_type,
                    ContentLength=len(data),
                ),
            )
        except Exception as exc:
            logger.error(
                "MinIOStorage: upload xatosi key=%s size=%d error=%r",
                key, len(data), exc,
            )
            raise AppError("catalog.storage_error", status_code=503) from exc

        url = f"{self._endpoint_url}/{self._bucket}/{key}"
        logger.info("MinIOStorage: uploaded key=%s size=%d", key, len(data))
        return url

    async def upload_contract_file(self, file: UploadFile) -> str:
        """Shartnoma faylini (PDF yoki rasm) MinIO ga yuklaydi, public URL qaytaradi."""
        data, ext = await _validate_contract_file(file)

        key = f"contracts/{uuid7()}.{ext}"

        _mime_map = {
            "pdf":  "application/pdf",
            "jpg":  "image/jpeg",
            "png":  "image/png",
            "webp": "image/webp",
        }
        content_type = _mime_map.get(ext, "application/octet-stream")

        loop = asyncio.get_running_loop()
        client = self._get_client()

        try:
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=io.BytesIO(data),
                    ContentType=content_type,
                    ContentLength=len(data),
                ),
            )
        except Exception as exc:
            logger.error(
                "MinIOStorage: contract upload xatosi key=%s size=%d error=%r",
                key, len(data), exc,
            )
            raise AppError("catalog.storage_error", status_code=503) from exc

        url = f"{self._endpoint_url}/{self._bucket}/{key}"
        logger.info("MinIOStorage: contract uploaded key=%s size=%d", key, len(data))
        return url


# ─── FastAPI dependency ───────────────────────────────────────────────────────

# Global instance — test da override qilinadi
_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """
    FastAPI dependency: storage backend qaytaradi.

    Test muhitida `app.dependency_overrides[get_storage]` orqali
    FakeStorage bilan almashtiriladi.
    """
    global _storage_instance
    if _storage_instance is None:
        from app.core.config import settings

        _storage_instance = MinIOStorage(
            endpoint_url=settings.minio_endpoint_url,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            bucket=settings.minio_bucket_products,
        )
    return _storage_instance


def set_storage(backend: StorageBackend) -> None:
    """Test yoki startup da storage backendni almashtirishga imkon beradi."""
    global _storage_instance
    _storage_instance = backend
