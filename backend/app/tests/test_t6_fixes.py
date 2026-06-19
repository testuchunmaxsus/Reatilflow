"""
T6 gate topilmalari uchun testlar.

Scenariylar:
  1. dummy_hash 60 belgi (unit assert) — timing himoya.
  2. mask_pii full_name ni maskalaydi.
  3. prod validator dev-default PII kalitni rad etadi.
  4. prod validator dev-default blind-index kalitni rad etadi.
  5. before_update: phone bytes bo'lsa to'g'ri ishlaydi (phone_bi yangilanadi).
  6. Migratsiya backfill: 0 qatorli DB da _backfill_user_pii no-op.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import mask_pii
from app.models.base import Base
from app.models.user import AppUser
from app.core.jwt import hash_password


def _load_migration_0005():
    """
    0005_user_phone_encrypt.py ni importlib orqali yuklaydi.
    Fayl nomi raqam bilan boshlanishi oddiy import'ni imkonsiz qiladi.

    Fayl joylashuvi: <backend_root>/alembic/versions/0005_user_phone_encrypt.py
    Bu test fayli: <backend_root>/app/tests/test_t6_fixes.py
    Demak: parent.parent.parent == backend_root

    alembic.op faqat migration run vaqtida mavjud — testda mock bilan almashtiramiz.
    """
    import sys
    import types
    from unittest.mock import MagicMock

    migration_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "alembic" / "versions" / "0005_user_phone_encrypt.py"
    )

    # alembic.op'ni mock qilish (faqat shu import uchun zarur)
    alembic_mock = types.ModuleType("alembic")
    alembic_mock.op = MagicMock()
    original_alembic = sys.modules.get("alembic")
    sys.modules["alembic"] = alembic_mock

    try:
        spec = importlib.util.spec_from_file_location("migration_0005", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        # Asl alembic modulini tiklash
        if original_alembic is not None:
            sys.modules["alembic"] = original_alembic
        elif "alembic" in sys.modules:
            del sys.modules["alembic"]

    return module


# ─── 1. dummy_hash uzunligi ───────────────────────────────────────────────────

def test_dummy_hash_is_60_chars() -> None:
    """
    service.py da ishlatilgan dummy_hash haqiqiy 60-belgilik bcrypt hash bo'lishi kerak.

    bcrypt format: $2b$12$ + 22 belgi salt + 31 belgi hash = 60 belgi jami.
    59 belgilik hash bcrypt.checkpw() ga berilsa ba'zi kutubxonalarda xato beradi
    — timing himoyasi buziladi.
    """
    # Moduldan dummy_hash ni o'qish (statik string — import orqali)
    import ast
    import pathlib

    service_path = pathlib.Path(__file__).parent.parent / "modules" / "auth" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    dummy_hash_value: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "dummy_hash":
                    if isinstance(node.value, ast.Constant):
                        dummy_hash_value = node.value.value

    assert dummy_hash_value is not None, "dummy_hash topilmadi service.py da"
    assert len(dummy_hash_value) == 60, (
        f"dummy_hash 60 belgi bo'lishi kerak, hozir {len(dummy_hash_value)} belgi: "
        f"{dummy_hash_value!r}"
    )
    assert dummy_hash_value.startswith("$2b$"), (
        f"dummy_hash '$2b$' bilan boshlanishi kerak: {dummy_hash_value!r}"
    )


def test_dummy_hash_bcrypt_checkpw_works() -> None:
    """
    dummy_hash bcrypt.checkpw() ga berilganda xato bermasligi kerak (False qaytishi kerak).
    """
    import bcrypt
    import pathlib
    import ast

    service_path = pathlib.Path(__file__).parent.parent / "modules" / "auth" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    dummy_hash_value: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "dummy_hash":
                    if isinstance(node.value, ast.Constant):
                        dummy_hash_value = node.value.value

    assert dummy_hash_value is not None
    # bcrypt.checkpw xato bermasligi kerak (False qaytishi to'g'ri)
    result = bcrypt.checkpw(b"wrong_password", dummy_hash_value.encode())
    assert result is False, "dummy_hash ga noto'g'ri parol False qaytarishi kerak"


# ─── 2. mask_pii — full_name ─────────────────────────────────────────────────

def test_mask_pii_masks_full_name() -> None:
    """mask_pii full_name ni maskalashi kerak (T6 — PII audit himoyasi)."""
    result = mask_pii({"full_name": "Ali Valiyev"})
    assert result["full_name"] == "***", (
        f"full_name '***' ga maskalanishi kerak, olingan: {result['full_name']!r}"
    )


def test_mask_pii_full_name_case_insensitive() -> None:
    """full_name katta harfda ham maskalanishi kerak."""
    result = mask_pii({"Full_Name": "Test User", "FULL_NAME": "Another"})
    assert result["Full_Name"] == "***"
    assert result["FULL_NAME"] == "***"


def test_mask_pii_full_name_not_leaked_in_mixed_dict() -> None:
    """full_name aralash lug'atda ham maskalanib, boshqa maydonlar saqlanadi."""
    data = {
        "id": "some-uuid",
        "full_name": "Maxfiy Ism",
        "role": "agent",
        "is_active": True,
    }
    result = mask_pii(data)
    assert result["full_name"] == "***"
    assert result["id"] == "some-uuid"
    assert result["role"] == "agent"
    assert result["is_active"] is True


# ─── 3 & 4. prod validator — dev-default kalit denylist ─────────────────────

def test_prod_validator_rejects_dev_default_pii_key() -> None:
    """
    production muhitida dev-default PII_ENCRYPTION_KEY → ValueError.

    Dev-default kalit source code da ommaviy — prod da ishlatish taqiqlangan.
    """
    from pydantic import ValidationError
    from app.core.config import Settings

    dev_default_pii = "213aa3cd714c3c908d44865643e3aff4e6018d4d147857dfd8f54a361fb50884"
    # Boshqa kalit uchun yangi (boshqa) qiymat ishlatamiz
    safe_blind = "a" * 64  # haqiqiy hex emas — format xatosi beradi
    # Haqiqiy hex bo'lgan boshqa blind key
    other_valid_hex = "1234567890abcdef" * 4  # 64 belgi, valid hex

    with pytest.raises((ValidationError, ValueError)):
        Settings(
            app_env="production",
            jwt_secret_key="a" * 64,  # 64 belgi — CHANGE_ME yo'q
            pii_encryption_key=dev_default_pii,
            blind_index_key=other_valid_hex,
        )


def test_prod_validator_rejects_dev_default_blind_key() -> None:
    """
    production muhitida dev-default BLIND_INDEX_KEY → ValueError.
    """
    from pydantic import ValidationError
    from app.core.config import Settings

    dev_default_blind = "8d8305efc948d6c95b5048f4f914fc205ad45f5294e3ee71cee7911c230a189f"
    other_valid_hex = "fedcba9876543210" * 4  # 64 belgi, valid hex

    with pytest.raises((ValidationError, ValueError)):
        Settings(
            app_env="production",
            jwt_secret_key="b" * 64,
            pii_encryption_key=other_valid_hex,
            blind_index_key=dev_default_blind,
        )


def test_prod_validator_accepts_non_default_keys() -> None:
    """
    production muhitida yangi (non-default) kalitlar qabul qilinishi kerak.
    """
    from app.core.config import Settings

    # openssl rand -hex 32 bilan yaratilgan (namunaviy)
    new_pii_key = "deadbeefcafe1234" * 4      # 64 char valid hex
    new_blind_key = "0011223344556677" * 4     # 64 char valid hex

    # Xato bo'lmasligi kerak
    s = Settings(
        app_env="production",
        jwt_secret_key="c" * 64,
        pii_encryption_key=new_pii_key,
        blind_index_key=new_blind_key,
    )
    assert s.app_env == "production"


def test_dev_env_allows_default_keys() -> None:
    """
    development muhitida dev-default kalitlar qabul qilinishi kerak (test ishlashi uchun).
    """
    from app.core.config import Settings

    dev_default_pii = "213aa3cd714c3c908d44865643e3aff4e6018d4d147857dfd8f54a361fb50884"
    dev_default_blind = "8d8305efc948d6c95b5048f4f914fc205ad45f5294e3ee71cee7911c230a189f"

    # Xato bo'lmasligi kerak (development)
    s = Settings(
        app_env="development",
        jwt_secret_key="CHANGE_ME_in_env_file_never_use_this_default",
        pii_encryption_key=dev_default_pii,
        blind_index_key=dev_default_blind,
    )
    assert s.app_env == "development"


# ─── 5. before_update — bytes holati ─────────────────────────────────────────

@pytest.fixture
async def sqlite_session():
    """before_update testi uchun aiosqlite in-memory session."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.mark.asyncio
async def test_before_update_bytes_phone_sets_phone_bi(sqlite_session: AsyncSession) -> None:
    """
    before_update event: phone bytes bo'lsa decrypt_pii() orqali ochiq-matnga o'girib
    blind_index hisoblanishi kerak.

    Bu EncryptedString TypeDecorator'dan oldin bytes kelishi mumkin bo'lgan holatni simulatsiya qiladi.
    """
    from app.core.crypto import blind_index, encrypt_pii

    original_phone = "+998901234599"

    user = AppUser(
        id=uuid.uuid4(),
        full_name="Bytes Test User",
        phone=original_phone,
        role="agent",
        branch_id=None,
        password_hash=hash_password("TestPass123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    sqlite_session.add(user)
    await sqlite_session.flush()

    # phone_bi avtomatik o'rnatilgan bo'lishi kerak
    assert user.phone_bi == blind_index(original_phone), (
        "INSERT dan keyin phone_bi to'g'ri hisoblanishi kerak"
    )

    # phone ni yangilash — before_update ishlashi kerak
    new_phone = "+998907654399"
    user.phone = new_phone
    await sqlite_session.flush()

    expected_bi = blind_index(new_phone)
    assert user.phone_bi == expected_bi, (
        f"UPDATE dan keyin phone_bi yangilanishi kerak. "
        f"Kutilgan: {expected_bi!r}, olingan: {user.phone_bi!r}"
    )


@pytest.mark.asyncio
async def test_before_update_bytes_phone_defensive(sqlite_session: AsyncSession) -> None:
    """
    before_update: history.added[0] bytes bo'lsa, decrypt_pii() orqali ishlaydi.

    Bu holatni to'g'ridan-to'g'ri model event'ga bytes berib simulatsiya qilamiz.
    """
    from app.core.crypto import blind_index, encrypt_pii, decrypt_pii
    from app.models.user import _set_phone_bi_before_update
    from unittest.mock import MagicMock

    original_phone = "+998909876543"
    encrypted_bytes = encrypt_pii(original_phone)

    user = AppUser(
        id=uuid.uuid4(),
        full_name="Defensive Test",
        phone=original_phone,
        role="courier",
        branch_id=None,
        password_hash=hash_password("TestPass123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    sqlite_session.add(user)
    await sqlite_session.flush()

    # Event listenerga bytes berib chaqirish (TypeDecorator simulatsiyasi)
    from sqlalchemy.orm import attributes as _attrs
    import unittest.mock as mock

    # phone_bi ni None ga qaytarish — keyin event'ni qo'lda chaqiramiz
    user.phone_bi = None

    # Qo'lda mapper history'ni simulatsiya qilish
    # (to'g'ridan-to'g'ri funksiya ichiga kirib bytes beriamiz)
    class FakeHistory:
        added = [encrypted_bytes]

    original_get_history = _attrs.get_history

    def mock_get_history(target, attr_name):
        if attr_name == "phone" and target is user:
            return FakeHistory()
        return original_get_history(target, attr_name)

    # sqlalchemy.orm.attributes.get_history ni patch qilamiz
    with mock.patch("sqlalchemy.orm.attributes.get_history", side_effect=mock_get_history):
        _set_phone_bi_before_update(None, None, user)

    expected_bi = blind_index(original_phone)
    assert user.phone_bi == expected_bi, (
        f"bytes phone berilganda phone_bi to'g'ri hisoblanishi kerak. "
        f"Kutilgan: {expected_bi!r}, olingan: {user.phone_bi!r}"
    )


# ─── 6. Migratsiya backfill — 0 qatorli DB no-op ─────────────────────────────

def test_migration_backfill_noop_on_empty_db() -> None:
    """
    _backfill_user_pii: 0 qatorli DB da hech narsa qilmaydi (no-op).

    Bu greenfield deployment uchun muhim — bo'sh DB da migratsiya xato bermasin.
    """
    from unittest.mock import MagicMock

    m = _load_migration_0005()
    _backfill_user_pii = m._backfill_user_pii

    mock_bind = MagicMock()
    # COUNT(*) → 0 qaytaradi
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0
    mock_bind.execute.return_value = mock_count_result

    # Xato bermasa — muvaffaqiyat
    _backfill_user_pii(mock_bind, is_postgres=True)

    # Faqat COUNT so'rovi chaqirilishi kerak (UPDATE yo'q)
    assert mock_bind.execute.call_count == 1


# ─── Import nomi tekshiruvi ───────────────────────────────────────────────────

def test_migration_module_importable() -> None:
    """
    0005 migratsiya moduli importlib orqali yuklanishi va
    kerakli funksiyalarni eksport qilishi kerak.
    """
    m = _load_migration_0005()
    assert hasattr(m, "_backfill_user_pii"), "_backfill_user_pii topilmadi"
    assert hasattr(m, "_backfill_user_pii_sqlite"), "_backfill_user_pii_sqlite topilmadi"
    assert hasattr(m, "upgrade"), "upgrade topilmadi"
    assert hasattr(m, "downgrade"), "downgrade topilmadi"
