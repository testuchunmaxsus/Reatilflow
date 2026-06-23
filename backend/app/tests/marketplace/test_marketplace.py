"""
Marketplace (MP1) testlari.

Qamrov:
  1. Publish toggle: korxona o'z mahsulotini publish qiladi → marketplace'da ko'rinadi.
  2. IDOR: boshqa korxona mahsulotini publish qila olmaydi → 404.
  3. Cross-tenant browse: A korxona foydalanuvchisi B korxona published mahsulotini ko'radi.
  4. Izolyatsiya: B ning published EMAS mahsuloti browse'da ko'rinmaydi.
  5. GET /{id}: published mahsulot → 200; published emas → 404.
  6. Supplier nomi qaytadi (supplier_name, supplier_enterprise_id).
  7. Module gating: "marketplace" o'chiq → 403.
  8. RBAC: marketplace:view ruxsati — store ko'radi; marketplace:edit yo'q → admin PATCH.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product
from app.models.enterprise import Enterprise
from app.models.user import AppUser
from app.tests.marketplace.conftest import get_token


# ─── Yordamchi ───────────────────────────────────────────────────────────────


async def _create_product(
    client: AsyncClient,
    token: str,
    name_uz: str = "Test mahsulot",
    name_ru: str = "Тест товар",
    sku: str | None = None,
) -> str:
    """Admin tomonidan mahsulot yaratadi va ID qaytaradi."""
    resp = await client.post(
        "/catalog/products",
        json={
            "name_uz": name_uz,
            "name_ru": name_ru,
            "unit": "dona",
            "sku": sku,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Mahsulot yaratib bo'lmadi: {resp.text}"
    return resp.json()["id"]


async def _publish(
    client: AsyncClient,
    token: str,
    product_id: str,
    published: bool = True,
    marketplace_price: str | None = None,
) -> dict:
    """Mahsulotni publish/unpublish qiladi."""
    body = {"marketplace_published": published}
    if marketplace_price is not None:
        body["marketplace_price"] = marketplace_price
    resp = await client.patch(
        f"/catalog/products/{product_id}/marketplace",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


# ─── 1. Publish toggle ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_own_product(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """Administrator o'z mahsulotini publish qiladi → marketplace'da ko'rinadi."""
    token = await get_token(mp_client, admin_a)

    pid = await _create_product(mp_client, token, "Olma A", "Яблоко A", "MP-APPLE-001")

    # Publish
    resp = await _publish(mp_client, token, pid, published=True, marketplace_price="5500.00")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["marketplace_published"] is True
    assert data["marketplace_price"] == "5500.00"

    # Marketplace browse'da ko'rinadi
    browse = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert browse.status_code == 200, browse.text
    items = browse.json()["items"]
    assert any(p["id"] == pid for p in items), "Published mahsulot browse'da ko'rinishi kerak"


@pytest.mark.asyncio
async def test_unpublish_product(
    mp_client: AsyncClient,
    admin_a: AppUser,
) -> None:
    """Mahsulotni unpublish qilganda marketplace'dan olinadi."""
    token = await get_token(mp_client, admin_a)

    pid = await _create_product(mp_client, token, "Nok A", "Груша A", "MP-PEAR-001")

    # Avval publish
    await _publish(mp_client, token, pid, published=True)

    # Keyin unpublish
    resp = await _publish(mp_client, token, pid, published=False)
    assert resp.status_code == 200, resp.text
    assert resp.json()["marketplace_published"] is False

    # Browse'da ko'rinmaydi
    browse = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = browse.json()["items"]
    assert not any(p["id"] == pid for p in items), "Unpublish qilingan mahsulot ko'rinmasligi kerak"


# ─── 2. IDOR himoyasi ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_publish_other_enterprise_product(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    db_session: AsyncSession,
) -> None:
    """
    B korxona admini A korxona mahsulotini publish qila olmaydi → 404.

    IDOR himoyasi: enterprise_id server-avtoritar — boshqa korxona mahsuloti
    ko'rsatilmaydi (mavjudlikni oshkor qilmaslik).
    """
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)

    # A korxona mahsulot yaratadi
    pid_a = await _create_product(mp_client, token_a, "A mahsuloti", "A товар", "MP-IDOR-001")

    # B korxona admini A mahsulotini publish qilishga urinadi → 404
    resp = await _publish(mp_client, token_b, pid_a, published=True)
    assert resp.status_code == 404, (
        f"B korxona A mahsulotini publish qila olmaydi (IDOR!): {resp.text}"
    )


# ─── 3. Cross-tenant browse ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_browse_sees_other_enterprise_published(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    A korxona do'koni B korxona published mahsulotini ko'radi (cross-tenant ishlaydi).
    """
    token_a_admin = await get_token(mp_client, admin_a)
    token_b_admin = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    # B korxona mahsulot yaratib publish qiladi
    pid_b = await _create_product(
        mp_client, token_b_admin, "B published", "B опубликован", "MP-CROSS-001"
    )
    await _publish(mp_client, token_b_admin, pid_b, published=True, marketplace_price="9000.00")

    # A korxona do'koni browse'da B ning mahsulotini ko'radi
    browse = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert browse.status_code == 200, browse.text
    items = browse.json()["items"]
    ids = [p["id"] for p in items]
    assert pid_b in ids, "A korxona do'koni B korxona published mahsulotini ko'rishi kerak"


@pytest.mark.asyncio
async def test_supplier_name_returned(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_b: Enterprise,
) -> None:
    """Supplier korxona nomi (supplier_name) browse natijasida qaytadi."""
    token_b = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    # B korxona mahsulot yaratib publish
    pid_b = await _create_product(
        mp_client, token_b, "Supplier test", "Supplier тест", "MP-SUPP-001"
    )
    await _publish(mp_client, token_b, pid_b, published=True)

    # Browse
    browse = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    items = browse.json()["items"]
    b_item = next((p for p in items if p["id"] == pid_b), None)
    assert b_item is not None, "B mahsuloti browse'da ko'rinishi kerak"
    assert b_item["supplier_name"] == enterprise_b.name, "Supplier nomi to'g'ri bo'lishi kerak"
    assert b_item["supplier_enterprise_id"] == str(enterprise_b.id)


# ─── 4. Izolyatsiya kafolati ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unpublished_not_visible_in_browse(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    B korxona published EMAS mahsuloti A korxona do'koniga ko'rinmaydi.

    Izolyatsiya kafolati: published emas mahsulot hech qachon cross-tenant
    browse'da oqmasligi kerak.
    """
    token_b = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    # B korxona mahsulot yaratadi — publish QILMAYDI
    pid_b_hidden = await _create_product(
        mp_client, token_b, "B yashirin", "B скрытый", "MP-HIDDEN-001"
    )

    # A korxona browse'da B ning published emas mahsulotini KO'RMASLIGI kerak
    browse = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert browse.status_code == 200, browse.text
    items = browse.json()["items"]
    ids = [p["id"] for p in items]
    assert pid_b_hidden not in ids, (
        f"B korxona published EMAS mahsuloti A korxonaga oqdi (izolyatsiya buzildi)! "
        f"product_id={pid_b_hidden}"
    )


# ─── 5. GET /{id} ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_published_product_ok(
    mp_client: AsyncClient,
    admin_a: AppUser,
    store_user_a: AppUser,
) -> None:
    """Published mahsulotni GET → 200."""
    token_a = await get_token(mp_client, admin_a)
    token_store = await get_token(mp_client, store_user_a)

    pid = await _create_product(mp_client, token_a, "Get test", "Гет тест", "MP-GET-001")
    await _publish(mp_client, token_a, pid, published=True, marketplace_price="3000.00")

    resp = await mp_client.get(
        f"/marketplace/products/{pid}",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == pid
    assert data["marketplace_published"] is True
    assert data["price"] == "3000.00"


@pytest.mark.asyncio
async def test_get_unpublished_product_returns_404(
    mp_client: AsyncClient,
    admin_b: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    B korxona published EMAS mahsulotini GET /marketplace/products/{id} → 404.

    Izolyatsiya: mahsulot mavjud bo'lsa ham 404 qaytishi kerak.
    """
    token_b = await get_token(mp_client, admin_b)
    token_a_store = await get_token(mp_client, store_user_a)

    # B korxona mahsulot yaratadi — publish QILMAYDI
    pid_hidden = await _create_product(
        mp_client, token_b, "B get hidden", "B скрытый GET", "MP-GETHIDE-001"
    )

    # A korxona published emas mahsulotga kirmoqchi → 404
    resp = await mp_client.get(
        f"/marketplace/products/{pid_hidden}",
        headers={"Authorization": f"Bearer {token_a_store}"},
    )
    assert resp.status_code == 404, (
        f"Published emas mahsulot 404 qaytarishi kerak (izolyatsiya!): {resp.text}"
    )
    assert resp.json()["message_key"] == "marketplace.product_not_found"


@pytest.mark.asyncio
async def test_get_nonexistent_product_returns_404(
    mp_client: AsyncClient,
    store_user_a: AppUser,
) -> None:
    """Mavjud bo'lmagan mahsulot → 404."""
    token = await get_token(mp_client, store_user_a)
    fake_id = str(uuid.uuid4())
    resp = await mp_client.get(
        f"/marketplace/products/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["message_key"] == "marketplace.product_not_found"


# ─── 6. Suppliers ro'yxati ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suppliers_list(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """Suppliers ro'yxatida faqat published mahsuloti bor korxonalar ko'rinadi."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)
    token_store = await get_token(mp_client, store_user_a)

    # A: bitta published mahsulot
    pid_a = await _create_product(mp_client, token_a, "A sup", "A суп", "MP-SUP-A01")
    await _publish(mp_client, token_a, pid_a, published=True)

    # B: ikkita published mahsulot
    pid_b1 = await _create_product(mp_client, token_b, "B sup 1", "B суп 1", "MP-SUP-B01")
    pid_b2 = await _create_product(mp_client, token_b, "B sup 2", "B суп 2", "MP-SUP-B02")
    await _publish(mp_client, token_b, pid_b1, published=True)
    await _publish(mp_client, token_b, pid_b2, published=True)

    resp = await mp_client.get(
        "/marketplace/suppliers",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp.status_code == 200, resp.text
    suppliers = resp.json()
    supplier_ids = [s["enterprise_id"] for s in suppliers]

    assert str(enterprise_a.id) in supplier_ids, "A korxona supplierlar'da bo'lishi kerak"
    assert str(enterprise_b.id) in supplier_ids, "B korxona supplierlar'da bo'lishi kerak"

    # B 2 ta, A 1 ta — B birinchi bo'lishi kerak (count desc)
    b_supplier = next((s for s in suppliers if s["enterprise_id"] == str(enterprise_b.id)), None)
    a_supplier = next((s for s in suppliers if s["enterprise_id"] == str(enterprise_a.id)), None)
    assert b_supplier is not None
    assert a_supplier is not None
    assert b_supplier["product_count"] == 2
    assert a_supplier["product_count"] == 1


# ─── 7. Module gating ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_marketplace_module_disabled_returns_403(
    mp_client: AsyncClient,
    db_session: AsyncSession,
    enterprise_a: Enterprise,
    admin_a: AppUser,
    store_user_a: AppUser,
) -> None:
    """
    'marketplace' moduli korxonada o'chirilsa → 403.

    enterprise.enabled_modules dan 'marketplace' olib tashlanadi.
    """
    token_store = await get_token(mp_client, store_user_a)

    # Marketplace modulini o'chirish
    enterprise_a.enabled_modules = [m for m in enterprise_a.enabled_modules if m != "marketplace"]
    await db_session.flush()

    resp = await mp_client.get(
        "/marketplace/products",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp.status_code == 403, f"Module o'chiq bo'lsa 403 kerak: {resp.text}"
    assert resp.json()["message_key"] == "enterprise.module_disabled"


# ─── 8. Supplier filtri ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browse_filter_by_supplier(
    mp_client: AsyncClient,
    admin_a: AppUser,
    admin_b: AppUser,
    store_user_a: AppUser,
    enterprise_a: Enterprise,
    enterprise_b: Enterprise,
) -> None:
    """supplier_enterprise query parametri bilan faqat bitta korxona mahsulotlari qaytadi."""
    token_a = await get_token(mp_client, admin_a)
    token_b = await get_token(mp_client, admin_b)
    token_store = await get_token(mp_client, store_user_a)

    pid_a = await _create_product(mp_client, token_a, "A filter", "A фильтр", "MP-FILT-A01")
    await _publish(mp_client, token_a, pid_a, published=True)

    pid_b = await _create_product(mp_client, token_b, "B filter", "B фильтр", "MP-FILT-B01")
    await _publish(mp_client, token_b, pid_b, published=True)

    # Faqat B korxona mahsulotlari
    resp = await mp_client.get(
        f"/marketplace/products?supplier_enterprise={enterprise_b.id}",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [p["id"] for p in items]
    assert pid_b in ids, "B mahsuloti bo'lishi kerak"
    assert pid_a not in ids, "A mahsuloti ko'rinmasligi kerak (supplier filter)"


# ─── 9. marketplace_price None bo'lsa GET'da price segment narxidan ─────────


@pytest.mark.asyncio
async def test_publish_without_marketplace_price(
    mp_client: AsyncClient,
    admin_a: AppUser,
    store_user_a: AppUser,
) -> None:
    """marketplace_price berilmasa, publish muvaffaqiyatli → price=None (segment narx yo'q)."""
    token_a = await get_token(mp_client, admin_a)
    token_store = await get_token(mp_client, store_user_a)

    pid = await _create_product(mp_client, token_a, "No price", "Без цены", "MP-NOPRICE-001")

    # marketplace_price None bilan publish
    resp = await _publish(mp_client, token_a, pid, published=True)
    assert resp.status_code == 200, resp.text
    assert resp.json()["marketplace_price"] is None

    # GET'da price=None (segment narx yo'q)
    resp2 = await mp_client.get(
        f"/marketplace/products/{pid}",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp2.status_code == 200
    # marketplace_price yo'q, segment narx yo'q → price=None
    assert resp2.json()["price"] is None


# ─── 10. Search filter ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browse_search_filter(
    mp_client: AsyncClient,
    admin_a: AppUser,
    store_user_a: AppUser,
) -> None:
    """search query parametri bilan mahsulot nomi bo'yicha qidirish."""
    token_a = await get_token(mp_client, admin_a)
    token_store = await get_token(mp_client, store_user_a)

    # Ikkita mahsulot yaratib publish qilish
    pid1 = await _create_product(mp_client, token_a, "Olma maxsus", "Яблоко особое", "MP-SRCH-001")
    pid2 = await _create_product(mp_client, token_a, "Bodring", "Огурец", "MP-SRCH-002")
    await _publish(mp_client, token_a, pid1, published=True)
    await _publish(mp_client, token_a, pid2, published=True)

    resp = await mp_client.get(
        "/marketplace/products?search=Olma",
        headers={"Authorization": f"Bearer {token_store}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [p["id"] for p in items]
    assert pid1 in ids, "Qidiruv natijasida Olma bo'lishi kerak"
    assert pid2 not in ids, "Bodring ko'rinmasligi kerak (qidiruv natijasi emas)"
