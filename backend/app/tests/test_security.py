"""
PII maskalash va uuid7 uchun testlar.

Ishlatish:
    cd backend
    pytest app/tests/test_security.py -v
"""

import uuid

import pytest

from app.core.security import mask_pii
from app.core.uuid7 import uuid7


# ─── mask_pii testlari ──────────────────────────────────────────────────────

def test_mask_pii_masks_inn() -> None:
    result = mask_pii({"inn": "123456789"})
    assert result["inn"] == "***"


def test_mask_pii_masks_phone() -> None:
    result = mask_pii({"phone": "+998901234567"})
    assert result["phone"] == "***"


def test_mask_pii_masks_password() -> None:
    result = mask_pii({"password": "supersecret"})
    assert result["password"] == "***"


def test_mask_pii_masks_token() -> None:
    result = mask_pii({"token": "eyJhbGc..."})
    assert result["token"] == "***"


def test_mask_pii_masks_owner_name() -> None:
    result = mask_pii({"owner_name": "Ali Valiyev"})
    assert result["owner_name"] == "***"


def test_mask_pii_keeps_safe_fields() -> None:
    result = mask_pii({"name": "Magazin A", "address": "Toshkent"})
    assert result["name"] == "Magazin A"
    assert result["address"] == "Toshkent"


def test_mask_pii_does_not_mutate_original() -> None:
    original = {"inn": "12345", "name": "Test"}
    mask_pii(original)
    assert original["inn"] == "12345"


def test_mask_pii_case_insensitive_key() -> None:
    result = mask_pii({"INN": "12345", "Phone": "+998"})
    assert result["INN"] == "***"
    assert result["Phone"] == "***"


def test_mask_pii_mixed_keys() -> None:
    data = {
        "id": "some-uuid",
        "inn": "111",
        "name": "Do'kon",
        "inps": "222",
        "address": "Andijon",
        "phone": "+998",
        "owner_name": "Ali",
    }
    result = mask_pii(data)
    assert result["id"] == "some-uuid"
    assert result["name"] == "Do'kon"
    assert result["address"] == "Andijon"
    assert result["inn"] == "***"
    assert result["inps"] == "***"
    assert result["phone"] == "***"
    assert result["owner_name"] == "***"


# ─── uuid7 testlari ─────────────────────────────────────────────────────────

def test_uuid7_returns_uuid_instance() -> None:
    assert isinstance(uuid7(), uuid.UUID)


def test_uuid7_version_is_7() -> None:
    u = uuid7()
    assert u.version == 7


def test_uuid7_variant_is_correct() -> None:
    u = uuid7()
    # RFC 9562: variant bits — yuqori 2 bit 10
    assert (u.int >> 62) & 0b11 == 0b10


def test_uuid7_monotonic_within_same_ms() -> None:
    """Bir xil ms ichida ketma-ket UUID lar monoton o'sishi kerak."""
    uuids = [uuid7() for _ in range(50)]
    ints = [u.int for u in uuids]
    assert ints == sorted(ints), "uuid7 lar monoton tartibda bo'lishi kerak"


def test_uuid7_unique() -> None:
    uuids = {str(uuid7()) for _ in range(1000)}
    assert len(uuids) == 1000


def test_uuid7_thread_safety() -> None:
    """Ko'p thread'da ham unikal UUID lar yaratilishi kerak."""
    import threading

    results: list[uuid.UUID] = []
    lock = threading.Lock()

    def generate() -> None:
        u = uuid7()
        with lock:
            results.append(u)

    threads = [threading.Thread(target=generate) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 200
    assert len({str(u) for u in results}) == 200
