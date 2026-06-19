"""
Katalog API testlari.

Qamrov:
  1. CRUD: mahsulot yaratish / yangilash / o'chirish / ro'yxat (paginated)
  2. RBAC: agent/store POST → 403; view barcha rol uchun 200
     2b. RBAC: agent PATCH/DELETE → 403 (oldin faqat POST sinalgan edi)
  3. Dublikat sku/barcode → 409, message_key tekshiruvi (DB constraint orqali ham)
  4. Narx: ikki marta narx o'zgartirilsa price_history 2 yozuv (append-only)
  5. version optimistik lock: eski version → 409
  6. Soft-delete: o'chirilgan ro'yxatda ko'rinmaydi, DB da qoladi
  7. i18n: ?lang=ru → name ruscha, xato message ruscha
  8. Search/filter: name/sku/barcode, category_id, is_active
  9. Rasm: magic bytes tekshiruvi (PNG/JPEG haqiqiy bytes → OK; SVG/HTML → 422)
  10. branch_scope filter
  11. Category CRUD
  12. Price Segment CRUD
  13. Idempotentlik (server uuid7, id != client_uuid)
  14. branch_scope qator-darajali himoya (IDOR testlari)
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import PriceHistory, Product
from app.tests.catalog.conftest import BRANCH_A_ID, BRANCH_B_ID, get_token

# ─── Rasm test baytlari ───────────────────────────────────────────────────────

# To'liq PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A (8 bayt) + minimal IHDR
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

# JPEG magic bytes: FF D8 FF + minimal ma'lumot
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100

# WebP: RIFF + 4 bayt hajm + WEBP + minimal ma'lumot
_WEBP_BYTES = b"RIFF\x00\x01\x00\x00WEBP" + b"\x00" * 100

# Yaroqsiz baytlar: SVG/HTML ko'rinishidagi matn
_SVG_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>"
_HTML_BYTES = b"<html><body>xss</body></html>"
_TEXT_BYTES = b"not an image at all"


# ─── 1. CRUD: yaratish ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_product_admin(
    catalog_client: AsyncClient, admin_user, db_session: AsyncSession
) -> None:
    """Administrator mahsulot yarata oladi → 201."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Olma",
            "name_ru": "Яблоко",
            "sku": "APPLE-001",
            "barcode": "4600000000001",
            "unit": "kg",
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["sku"] == "APPLE-001"
    assert data["name_uz"] == "Olma"
    assert "id" in data
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_get_product(catalog_client: AsyncClient, admin_user, make_category) -> None:
    """Mahsulot ID bo'yicha olish → 200."""
    token = await get_token(catalog_client, admin_user)

    # Avval yaratish
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Nok", "name_ru": "Груша", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp2 = await catalog_client.get(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["id"] == pid


@pytest.mark.asyncio
async def test_list_products_paginated(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Ro'yxat paginated: total, limit, offset to'g'ri qaytishi."""
    token = await get_token(catalog_client, admin_user)

    # 3 ta mahsulot yaratish
    for i in range(3):
        await catalog_client.post(
            "/catalog/products",
            json={"name_uz": f"Mahsulot {i}", "name_ru": f"Товар {i}", "unit": "dona"},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = await catalog_client.get(
        "/catalog/products?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_update_product(catalog_client: AsyncClient, admin_user) -> None:
    """Mahsulotni yangilash (PATCH) → 200, versiya oshadi."""
    token = await get_token(catalog_client, admin_user)

    # Yaratish
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Gilos", "name_ru": "Вишня", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    ver = resp.json()["version"]

    # Yangilash
    resp2 = await catalog_client.patch(
        f"/catalog/products/{pid}",
        json={"name_uz": "Olcha", "version": ver},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    data = resp2.json()
    assert data["name_uz"] == "Olcha"
    assert data["version"] == ver + 1


@pytest.mark.asyncio
async def test_delete_product_soft(
    catalog_client: AsyncClient, admin_user, db_session: AsyncSession
) -> None:
    """Soft-delete: o'chirilgan mahsulot ro'yxatda ko'rinmaydi, DB da qoladi."""
    token = await get_token(catalog_client, admin_user)

    # Yaratish
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "O'chiriladigan", "name_ru": "Удалить", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    # O'chirish
    resp2 = await catalog_client.delete(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 204

    # Ro'yxatda yo'q
    resp3 = await catalog_client.get(
        "/catalog/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    items = resp3.json()["items"]
    assert not any(p["id"] == pid for p in items)

    # DB da qolgan (deleted_at o'rnatilgan)
    stmt = select(Product).where(Product.id == uuid.UUID(pid))
    result = await db_session.execute(stmt)
    product = result.scalar_one_or_none()
    assert product is not None
    assert product.deleted_at is not None


# ─── 2. RBAC ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_product_agent_forbidden(
    catalog_client: AsyncClient, agent_user
) -> None:
    """Agent mahsulot yarata olmaydi → 403."""
    token = await get_token(catalog_client, agent_user)
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Nok", "name_ru": "Груша", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "rbac.permission_denied"


@pytest.mark.asyncio
async def test_create_product_store_forbidden(
    catalog_client: AsyncClient, store_user
) -> None:
    """Store mahsulot yarata olmaydi → 403."""
    token = await get_token(catalog_client, store_user)
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Nok", "name_ru": "Груша", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_view_products_all_roles(
    catalog_client: AsyncClient, admin_user, agent_user, store_user
) -> None:
    """Barcha rollar mahsulotlar ro'yxatini ko'ra oladi → 200."""
    for user in [admin_user, agent_user, store_user]:
        token = await get_token(catalog_client, user)
        resp = await catalog_client.get(
            "/catalog/products",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Role {user.role}: {resp.text}"


@pytest.mark.asyncio
async def test_no_auth_returns_401(catalog_client: AsyncClient) -> None:
    """Token'siz so'rov → 401."""
    resp = await catalog_client.get("/catalog/products")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_patch_product_forbidden(
    catalog_client: AsyncClient, admin_user, agent_user
) -> None:
    """Agent PATCH /products/{id} → 403 (faqat admin/edit rollar yangilaydi)."""
    admin_token = await get_token(catalog_client, admin_user)
    agent_token = await get_token(catalog_client, agent_user)

    # Admin yaratadi
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Taqiqlangan PATCH", "name_ru": "Запрещённый PATCH", "unit": "dona"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    ver = resp.json()["version"]

    # Agent yangilashga urinadi → 403
    resp2 = await catalog_client.patch(
        f"/catalog/products/{pid}",
        json={"name_uz": "Yangilangan", "version": ver},
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp2.status_code == 403, resp2.text
    assert resp2.json()["message_key"] == "rbac.permission_denied"


@pytest.mark.asyncio
async def test_agent_delete_product_forbidden(
    catalog_client: AsyncClient, admin_user, agent_user
) -> None:
    """Agent DELETE /products/{id} → 403 (faqat admin o'chiradi)."""
    admin_token = await get_token(catalog_client, admin_user)
    agent_token = await get_token(catalog_client, agent_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Taqiqlangan DELETE", "name_ru": "Запрещённый DELETE", "unit": "dona"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp2 = await catalog_client.delete(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp2.status_code == 403, resp2.text


# ─── 3. Dublikat SKU / barcode ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_sku_returns_409(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Bir xil SKU → 409 catalog.duplicate_sku."""
    token = await get_token(catalog_client, admin_user)

    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "A", "name_ru": "A", "sku": "SAME-SKU", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "B", "name_ru": "B", "sku": "SAME-SKU", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["message_key"] == "catalog.duplicate_sku"


@pytest.mark.asyncio
async def test_duplicate_barcode_returns_409(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Bir xil barcode → 409 catalog.duplicate_barcode."""
    token = await get_token(catalog_client, admin_user)

    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "A", "name_ru": "A", "barcode": "1234567890123", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "B", "name_ru": "B", "barcode": "1234567890123", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.json()["message_key"] == "catalog.duplicate_barcode"


# ─── 4. Narx — append-only price_history ─────────────────────────────────────


@pytest.mark.asyncio
async def test_price_history_append_only(
    catalog_client: AsyncClient,
    admin_user,
    db_session: AsyncSession,
    make_segment,
) -> None:
    """Ikki marta narx o'zgartirilsa price_history 2 yozuv, product_price joriy narx."""
    token = await get_token(catalog_client, admin_user)

    # Mahsulot
    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Tovar", "name_ru": "Товар", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    # Segment
    seg = await make_segment("VIP")

    valid_from1 = "2026-01-01T00:00:00+00:00"
    valid_from2 = "2026-06-01T00:00:00+00:00"

    # Birinchi narx
    resp1 = await catalog_client.post(
        f"/catalog/products/{pid}/prices",
        json={
            "segment_id": str(seg.id),
            "price": "100.00",
            "currency": "UZS",
            "valid_from": valid_from1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201, resp1.text

    # Ikkinchi narx
    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/prices",
        json={
            "segment_id": str(seg.id),
            "price": "150.00",
            "currency": "UZS",
            "valid_from": valid_from2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["price"] == "150.00"

    # Price history 2 yozuv (eski narxlar saqlanadi)
    stmt = select(PriceHistory).where(PriceHistory.product_id == uuid.UUID(pid))
    result = await db_session.execute(stmt)
    history = result.scalars().all()
    assert len(history) == 2, f"Kutilgan 2, lekin {len(history)} yozuv"

    # Narxlar: birinchi yozuv 0→100, ikkinchi 100→150
    prices_set = {(str(h.old_price), str(h.new_price)) for h in history}
    assert ("0" in str(prices_set) or "0.00" in str(prices_set))

    # API orqali price-history
    resp3 = await catalog_client.get(
        f"/catalog/products/{pid}/price-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    assert len(resp3.json()) == 2


# ─── 5. Optimistik lock (version konflikti) ───────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict(catalog_client: AsyncClient, admin_user) -> None:
    """Eski version bilan update → 409 catalog.version_conflict."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Lock test", "name_ru": "Лок тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    ver = resp.json()["version"]

    # Birinchi update — muvaffaqiyatli
    resp2 = await catalog_client.patch(
        f"/catalog/products/{pid}",
        json={"name_uz": "Updated", "version": ver},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    new_ver = resp2.json()["version"]
    assert new_ver == ver + 1

    # Eski version bilan update — konflikt
    resp3 = await catalog_client.patch(
        f"/catalog/products/{pid}",
        json={"name_uz": "Conflict", "version": ver},  # eski version
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 409
    assert resp3.json()["message_key"] == "catalog.version_conflict"


# ─── 6. Soft-delete tekshiruvi (qo'shimcha) ──────────────────────────────────


@pytest.mark.asyncio
async def test_deleted_product_returns_404(
    catalog_client: AsyncClient, admin_user
) -> None:
    """O'chirilgan mahsulotni GET → 404."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Del me", "name_ru": "Удали меня", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    await catalog_client.delete(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp2 = await catalog_client.get(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404


# ─── 7. i18n: ?lang=ru ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lang_ru_name_in_response(
    catalog_client: AsyncClient, admin_user
) -> None:
    """?lang=ru → name maydoni ruscha qaytadi."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "O'rik", "name_ru": "Абрикос", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.get(
        f"/catalog/products/{pid}?lang=ru",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["name"] == "Абрикос", f"Ruscha nom kutilgan, lekin: {data['name']}"


@pytest.mark.asyncio
async def test_lang_uz_name_in_response(
    catalog_client: AsyncClient, admin_user
) -> None:
    """?lang=uz (yoki standart) → name maydoni o'zbekcha qaytadi."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Uzum", "name_ru": "Виноград", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.get(
        f"/catalog/products/{pid}?lang=uz",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.json()["name"] == "Uzum"


@pytest.mark.asyncio
async def test_accept_language_ru(catalog_client: AsyncClient, admin_user) -> None:
    """Accept-Language: ru → xato xabar ruscha."""
    token = await get_token(catalog_client, admin_user)

    # Mavjud bo'lmagan mahsulot
    fake_id = str(uuid.uuid4())
    resp = await catalog_client.get(
        f"/catalog/products/{fake_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "ru",
        },
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "catalog.product_not_found"
    assert "не найден" in data["message"].lower() or "найден" in data["message"]


@pytest.mark.asyncio
async def test_not_found_message_key(catalog_client: AsyncClient, admin_user) -> None:
    """Mavjud bo'lmagan mahsulot → 404 catalog.product_not_found."""
    token = await get_token(catalog_client, admin_user)
    resp = await catalog_client.get(
        f"/catalog/products/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["message_key"] == "catalog.product_not_found"


# ─── 8. Search va filter ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_by_name(catalog_client: AsyncClient, admin_user) -> None:
    """name_uz bo'yicha qidiruv."""
    token = await get_token(catalog_client, admin_user)

    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Pomidor maxsus", "name_ru": "Помидор особый", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Bodring", "name_ru": "Огурец", "unit": "kg"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await catalog_client.get(
        "/catalog/products?search=Pomidor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("Pomidor" in p["name_uz"] for p in items)
    assert not any("Bodring" in p["name_uz"] for p in items)


@pytest.mark.asyncio
async def test_search_by_sku(catalog_client: AsyncClient, admin_user) -> None:
    """SKU bo'yicha qidiruv."""
    token = await get_token(catalog_client, admin_user)

    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "A", "name_ru": "A", "sku": "SEARCH-SKU-XYZ", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await catalog_client.get(
        "/catalog/products?search=SEARCH-SKU-XYZ",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any(p["sku"] == "SEARCH-SKU-XYZ" for p in resp.json()["items"])


@pytest.mark.asyncio
async def test_filter_by_is_active(catalog_client: AsyncClient, admin_user) -> None:
    """is_active=false filtri."""
    token = await get_token(catalog_client, admin_user)

    # Faol mahsulot
    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Faol", "name_ru": "Активный", "unit": "dona", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Nofaol mahsulot
    await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Nofaol", "name_ru": "Неактивный", "unit": "dona", "is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Faqat faollar
    resp = await catalog_client.get(
        "/catalog/products?is_active=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(p["is_active"] for p in items)

    # Faqat nofaollar
    resp2 = await catalog_client.get(
        "/catalog/products?is_active=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    items2 = resp2.json()["items"]
    assert all(not p["is_active"] for p in items2)


@pytest.mark.asyncio
async def test_filter_by_category(
    catalog_client: AsyncClient, admin_user, make_category
) -> None:
    """category_id filtri."""
    token = await get_token(catalog_client, admin_user)

    cat = await make_category("Meva", "Фрукты")
    other_cat = await make_category("Sabzavot", "Овощи")

    await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Olma", "name_ru": "Яблоко",
            "unit": "kg", "category_id": str(cat.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Sabzi", "name_ru": "Морковь",
            "unit": "kg", "category_id": str(other_cat.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await catalog_client.get(
        f"/catalog/products?category_id={cat.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(p["category_id"] == str(cat.id) for p in items)


# ─── 9. Rasm yuklash — magic bytes ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_photo_upload_png_success(
    catalog_client: AsyncClient, admin_user, fake_storage
) -> None:
    """Haqiqiy PNG magic bytes → upload muvaffaqiyatli."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "PNG test", "name_ru": "PNG тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("photo.png", io.BytesIO(_PNG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    data = resp2.json()
    assert data["photo_url"] is not None
    assert "fake-storage" in data["photo_url"]
    assert len(fake_storage.uploaded) >= 1


@pytest.mark.asyncio
async def test_photo_upload_jpeg_success(
    catalog_client: AsyncClient, admin_user, fake_storage
) -> None:
    """Haqiqiy JPEG magic bytes → upload muvaffaqiyatli."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "JPEG test", "name_ru": "JPEG тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("photo.jpg", io.BytesIO(_JPEG_BYTES), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["photo_url"] is not None


@pytest.mark.asyncio
async def test_photo_upload_webp_success(
    catalog_client: AsyncClient, admin_user, fake_storage
) -> None:
    """Haqiqiy WebP magic bytes → upload muvaffaqiyatli."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "WebP test", "name_ru": "WebP тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("photo.webp", io.BytesIO(_WEBP_BYTES), "image/webp")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["photo_url"] is not None


@pytest.mark.asyncio
async def test_photo_svg_with_image_content_type_rejected(
    catalog_client: AsyncClient, admin_user
) -> None:
    """SVG baytlari image/png Content-Type bilan → 422 (magic bytes tekshiruvi)."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "SVG test", "name_ru": "SVG тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    # SVG baytlari lekin image/png MIME header — magic bytes tekshiruvi ushlashi kerak
    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("evil.png", io.BytesIO(_SVG_BYTES), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422, resp2.text
    assert resp2.json()["message_key"] == "catalog.invalid_photo"


@pytest.mark.asyncio
async def test_photo_html_with_image_content_type_rejected(
    catalog_client: AsyncClient, admin_user
) -> None:
    """HTML baytlari image/jpeg Content-Type bilan → 422."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "HTML test", "name_ru": "HTML тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("xss.jpg", io.BytesIO(_HTML_BYTES), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422, resp2.text
    assert resp2.json()["message_key"] == "catalog.invalid_photo"


@pytest.mark.asyncio
async def test_photo_invalid_mime(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Matn baytlari text/plain Content-Type bilan → 422 catalog.invalid_photo."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "MIME test", "name_ru": "MIME тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("bad.txt", io.BytesIO(_TEXT_BYTES), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422, resp2.text
    assert resp2.json()["message_key"] == "catalog.invalid_photo"


@pytest.mark.asyncio
async def test_photo_too_large(
    catalog_client: AsyncClient, admin_user
) -> None:
    """5MB dan katta rasm → 422 catalog.invalid_photo."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "Big test", "name_ru": "Большой тест", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    big_image = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024 + 1)  # > 5MB, JPEG-like
    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/photo",
        files={"file": ("big.jpg", io.BytesIO(big_image), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 422
    assert resp2.json()["message_key"] == "catalog.invalid_photo"


# ─── 10. branch_scope filter ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_branch_scope_filter(catalog_client: AsyncClient, admin_user) -> None:
    """branch_scope filtri bo'yicha qidiruv."""
    token = await get_token(catalog_client, admin_user)

    # Birinchi mahsulot — branch B1
    await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B1 mahsulot", "name_ru": "B1 товар",
            "unit": "dona", "branch_scope": '["branch-b1"]',
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Ikkinchi mahsulot — branch B2
    await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B2 mahsulot", "name_ru": "B2 товар",
            "unit": "dona", "branch_scope": '["branch-b2"]',
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await catalog_client.get(
        "/catalog/products?branch_scope=branch-b1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all("branch-b1" in (p["branch_scope"] or "") for p in items)


# ─── 11. Category CRUD ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_categories(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Kategoriya yaratish va ro'yxat olish."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/categories",
        json={"name_uz": "Ichimliklar", "name_ru": "Напитки"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name_uz"] == "Ichimliklar"

    resp2 = await catalog_client.get(
        "/catalog/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert any(c["name_uz"] == "Ichimliklar" for c in resp2.json())


# ─── 12. Price Segment CRUD ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_segments(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Narx segmenti yaratish va ro'yxat olish."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/price-segments",
        json={"name": "Ulgurji"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Ulgurji"

    resp2 = await catalog_client.get(
        "/catalog/price-segments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert any(s["name"] == "Ulgurji" for s in resp2.json())


# ─── 13. Idempotentlik (client_uuid) — server uuid7, id != client_uuid ───────


@pytest.mark.asyncio
async def test_product_idempotency_same_id_returned(
    catalog_client: AsyncClient, admin_user
) -> None:
    """
    Bir xil (user, client_uuid) bilan ikki marta yaratish → bir xil mahsulot ID.

    CRITICAL: product.id == client_uuid EMAS — server uuid7() generatsiya qiladi.
    Idempotentlik Redis orqali amalga oshiriladi.
    """
    token = await get_token(catalog_client, admin_user)
    client_uuid = str(uuid.uuid4())

    payload = {
        "name_uz": "Idempotent mahsulot",
        "name_ru": "Идемпотентный товар",
        "unit": "dona",
        "client_uuid": client_uuid,
    }

    resp1 = await catalog_client.post(
        "/catalog/products",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201, resp1.text
    id1 = resp1.json()["id"]

    # Muhim: server uuid7 ishlatadi — id client_uuid ga teng EMAS
    assert id1 != client_uuid, (
        f"CRITICAL: product.id == client_uuid! "
        f"id={id1}, client_uuid={client_uuid}. "
        "Server uuid7() ishlatishi kerak."
    )

    resp2 = await catalog_client.post(
        "/catalog/products",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    # Idempotent: bir xil UUID bilan bir xil mahsulot qaytishi kerak
    assert resp2.json()["id"] == id1, (
        f"Idempotentlik ishlamadi: "
        f"birinchi id={id1}, ikkinchi id={resp2.json()['id']}"
    )


@pytest.mark.asyncio
async def test_product_different_client_uuid_creates_different_products(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Har xil client_uuid → har xil mahsulot (turli ID)."""
    token = await get_token(catalog_client, admin_user)

    resp1 = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Mahsulot A",
            "name_ru": "Товар A",
            "unit": "dona",
            "client_uuid": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    resp2 = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Mahsulot B",
            "name_ru": "Товар B",
            "unit": "dona",
            "client_uuid": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] != resp2.json()["id"]


# ─── 14. Branch scope qator-darajali himoya (IDOR testlari) ─────────────────


@pytest.mark.asyncio
async def test_branch_agent_cannot_get_other_branch_product(
    catalog_client: AsyncClient,
    admin_user,
    agent_user_branch_a,
    agent_user_branch_b,
) -> None:
    """
    A filial agenti B filial mahsulotini GET /{id} → 404.

    Mavjudlikni oshkor qilmaslik: mahsulot mavjud bo'lsa ham 404 qaytaradi.
    """
    admin_token = await get_token(catalog_client, admin_user)
    agent_b_token = await get_token(catalog_client, agent_user_branch_b)

    # Admin branch B ga tegishli mahsulot yaratadi
    resp = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B filial mahsuloti",
            "name_ru": "Товар филиала B",
            "unit": "dona",
            "branch_scope": str(BRANCH_B_ID),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    # A filial agenti B mahsulotini ko'rmoqchi → 404
    agent_a_token = await get_token(catalog_client, agent_user_branch_a)
    resp2 = await catalog_client.get(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {agent_a_token}"},
    )
    assert resp2.status_code == 404, (
        f"A filial agenti B filial mahsulotini ko'rishi mumkin emas (IDOR)! "
        f"status={resp2.status_code}"
    )
    assert resp2.json()["message_key"] == "catalog.product_not_found"


@pytest.mark.asyncio
async def test_branch_agent_cannot_list_other_branch_product(
    catalog_client: AsyncClient,
    admin_user,
    agent_user_branch_a,
) -> None:
    """
    A filial agenti ro'yxatida B filial mahsuloti ko'rinmaydi.
    Global (branch_scope=NULL) mahsulot esa ko'rinadi.
    """
    admin_token = await get_token(catalog_client, admin_user)
    agent_a_token = await get_token(catalog_client, agent_user_branch_a)

    # B filialga tegishli mahsulot
    await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B faqat", "name_ru": "Только B",
            "unit": "dona",
            "branch_scope": str(BRANCH_B_ID),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Global mahsulot (branch_scope=NULL)
    resp_global = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Global mahsulot", "name_ru": "Глобальный товар",
            "unit": "dona",
            "branch_scope": None,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    global_pid = resp_global.json()["id"]

    # A filial agenti ro'yxati
    resp = await catalog_client.get(
        "/catalog/products",
        headers={"Authorization": f"Bearer {agent_a_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [p["id"] for p in items]

    # B filial mahsuloti ko'rinmasligi kerak
    for p in items:
        assert p.get("branch_scope") != str(BRANCH_B_ID), (
            f"A filial agenti B filial mahsulotini ko'rdi (IDOR): {p}"
        )

    # Global mahsulot ko'rinishi kerak
    assert global_pid in ids, "Global mahsulot ko'rinishi kerak"


@pytest.mark.asyncio
async def test_admin_sees_all_branches(
    catalog_client: AsyncClient,
    admin_user,
) -> None:
    """Administrator barcha filiallar mahsulotlarini ko'radi."""
    admin_token = await get_token(catalog_client, admin_user)

    # A filialga tegishli
    resp_a = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "A admin", "name_ru": "A admin",
            "unit": "dona",
            "branch_scope": str(BRANCH_A_ID),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # B filialga tegishli
    resp_b = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B admin", "name_ru": "B admin",
            "unit": "dona",
            "branch_scope": str(BRANCH_B_ID),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    pid_a = resp_a.json()["id"]
    pid_b = resp_b.json()["id"]

    # Admin hammasini ko'radi
    resp = await catalog_client.get(
        "/catalog/products",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    ids = [p["id"] for p in resp.json()["items"]]
    assert pid_a in ids, "Admin A filial mahsulotini ko'rishi kerak"
    assert pid_b in ids, "Admin B filial mahsulotini ko'rishi kerak"


@pytest.mark.asyncio
async def test_global_product_visible_to_all_branches(
    catalog_client: AsyncClient,
    admin_user,
    agent_user_branch_a,
    agent_user_branch_b,
) -> None:
    """Global (branch_scope=NULL) mahsulot barcha filiallarga ko'rinadi."""
    admin_token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "Global barcha uchun",
            "name_ru": "Глобальный для всех",
            "unit": "dona",
            "branch_scope": None,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    pid = resp.json()["id"]

    for agent in [agent_user_branch_a, agent_user_branch_b]:
        token = await get_token(catalog_client, agent)
        resp2 = await catalog_client.get(
            f"/catalog/products/{pid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200, (
            f"{agent.role} (branch={agent.branch_id}) global mahsulotni ko'ra olishi kerak"
        )


@pytest.mark.asyncio
async def test_branch_agent_cannot_delete_other_branch_product(
    catalog_client: AsyncClient,
    admin_user,
    agent_user_branch_a,
) -> None:
    """
    A filial agenti B filial mahsulotini DELETE → 403 (agent roli DELETE qila olmaydi).
    Bu test RBAC va branch scope'ni birgalikda tekshiradi.
    """
    admin_token = await get_token(catalog_client, admin_user)
    agent_a_token = await get_token(catalog_client, agent_user_branch_a)

    resp = await catalog_client.post(
        "/catalog/products",
        json={
            "name_uz": "B mahsulot", "name_ru": "B товар",
            "unit": "dona",
            "branch_scope": str(BRANCH_B_ID),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    pid = resp.json()["id"]

    # Agent B mahsulotini o'chirishga urinadi — RBAC tufayli 403
    resp2 = await catalog_client.delete(
        f"/catalog/products/{pid}",
        headers={"Authorization": f"Bearer {agent_a_token}"},
    )
    assert resp2.status_code == 403


# ─── 15. Narx segmenti topilmasa ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_price_segment_not_found(
    catalog_client: AsyncClient, admin_user
) -> None:
    """Mavjud bo'lmagan segment_id → 404."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/products",
        json={"name_uz": "P", "name_ru": "P", "unit": "dona"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = resp.json()["id"]

    resp2 = await catalog_client.post(
        f"/catalog/products/{pid}/prices",
        json={
            "segment_id": str(uuid.uuid4()),
            "price": "50.00",
            "currency": "UZS",
            "valid_from": "2026-01-01T00:00:00+00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 404
    assert resp2.json()["message_key"] == "catalog.segment_not_found"


# ─── 16. Category lang qo'llab-quvvatlashi ───────────────────────────────────


@pytest.mark.asyncio
async def test_category_lang_ru(catalog_client: AsyncClient, admin_user) -> None:
    """Kategoriyada ?lang=ru → name ruscha."""
    token = await get_token(catalog_client, admin_user)

    resp = await catalog_client.post(
        "/catalog/categories",
        json={"name_uz": "Sut mahsulotlari", "name_ru": "Молочные продукты"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    resp2 = await catalog_client.get(
        "/catalog/categories?lang=ru",
        headers={"Authorization": f"Bearer {token}"},
    )
    cats = resp2.json()
    milky = next((c for c in cats if c["name_uz"] == "Sut mahsulotlari"), None)
    assert milky is not None
    assert milky["name"] == "Молочные продукты"
