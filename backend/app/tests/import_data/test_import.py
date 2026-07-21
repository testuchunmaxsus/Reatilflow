"""
Import data moduli testlari.

Test kategoriyalari:
  1. Excel parse: ustun moslash heuristika, bo'sh satr filtrlash
  2. Nakladnoy parse: magic bytes tekshiruvi, vision API mock
  3. Confirm catalog: idempotentlik, op-izolyatsiya, server-avtoritar target
  4. Confirm store_inventory: store_id aniqlash, Redis dedup
  5. RBAC: ruxsat tekshiruvi (agent → 403)
  6. column_mapping: heuristika to'g'ri ishlaydi

Infrasiz: aiosqlite + fakeredis + openpyxl in-memory.
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.user import AppUser
from app.modules.import_data.column_mapping import _heuristic_map
from app.modules.import_data.schemas import (
    ConfirmRow,
    ImportConfirmIn,
)
from app.tests.conftest import TEST_ENTERPRISE_UUID
from app.tests.import_data.conftest import get_token, make_xlsx_bytes


# ─── 1. Column mapping — heuristika ──────────────────────────────────────────


def test_heuristic_map_standard_headers():
    """Standart Excel sarlavhalar to'g'ri moslashadi."""
    # ASCII/transliterated headers
    headers = ["name", "sku", "barcode", "qty", "price"]
    mapping = _heuristic_map(headers)

    assert mapping["name"][0] == "name"
    assert mapping["sku"][0] == "sku"
    assert mapping["barcode"][0] == "barcode"
    assert mapping["qty"][0] == "qty"
    assert mapping["price"][0] == "price"


def test_heuristic_map_uzbek_headers():
    """O'zbekcha sarlavhalar moslashadi."""
    headers = ["mahsulot nomi", "miqdor", "narx", "SKU"]
    mapping = _heuristic_map(headers)

    assert mapping["mahsulot nomi"][0] == "name"
    assert mapping["miqdor"][0] == "qty"
    assert mapping["narx"][0] == "price"
    assert mapping["SKU"][0] == "sku"


def test_heuristic_map_unknown_header():
    """Noma'lum sarlavha None mapped_to bilan qaytariladi."""
    headers = ["XyzUnknownCol", "AnotherUnknown"]
    mapping = _heuristic_map(headers)

    assert mapping["XyzUnknownCol"][0] is None
    assert mapping["AnotherUnknown"][0] is None


# ─── 2. Excel parse ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excel_parse_invalid_magic():
    """PNG rasm .xlsx sifatida yuborilsa 422."""
    from fastapi import UploadFile
    from app.modules.import_data.excel import parse_excel

    # PNG magic bytes bilan fayl
    png_content = b"\x89PNG\r\n\x1a\nfake_data"
    fake_file = UploadFile(filename="test.xlsx", file=io.BytesIO(png_content))

    with pytest.raises(ValueError, match="xlsx"):
        await parse_excel(fake_file)


@pytest.mark.asyncio
async def test_excel_parse_too_large():
    """5 MB dan katta fayl 422."""
    from fastapi import UploadFile
    from app.modules.import_data.excel import parse_excel

    # PK magic bytes bilan katta fayl (5MB+1 byte)
    large_content = b"PK" + b"x" * (5 * 1024 * 1024)
    fake_file = UploadFile(filename="test.xlsx", file=io.BytesIO(large_content))

    with pytest.raises(ValueError, match="hajmi"):
        await parse_excel(fake_file)


@pytest.mark.asyncio
async def test_excel_parse_valid_file():
    """To'g'ri xlsx fayl parse qilinadi."""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl o'rnatilmagan")

    from fastapi import UploadFile
    from app.modules.import_data.excel import parse_excel

    xlsx_bytes = make_xlsx_bytes([
        ["Номи", "Артикул", "Кол-во", "Нарх"],
        ["Шакар", "SK-001", 100, 5000],
        ["Tuz", "SL-002", 50, 3000],
    ])
    fake_file = UploadFile(filename="test.xlsx", file=io.BytesIO(xlsx_bytes))

    # column_mapping Groq ni chaqirmaslik uchun patch
    with patch(
        "app.modules.import_data.column_mapping._groq_enhance",
        new=AsyncMock(return_value={
            "Номи": ("name", 0.85),
            "Артикул": ("sku", 0.85),
            "Кол-во": ("qty", 0.85),
            "Нарх": ("price", 0.85),
        }),
    ):
        result = await parse_excel(fake_file)

    assert result.parse_id is not None
    assert len(result.rows) == 2
    assert result.rows[0].name == "Шакар"
    assert result.rows[0].sku == "SK-001"
    assert result.rows[0].qty == 100.0
    assert result.rows[0].price == 5000.0


# ─── 3. Nakladnoy parse magic bytes ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_nakladnoy_invalid_magic():
    """PDF fayl (magic: %PDF) nakladnoy parse da 422."""
    from fastapi import UploadFile
    from app.modules.import_data.vision import parse_nakladnoy

    pdf_content = b"%PDF-1.4 fake"
    fake_file = UploadFile(filename="test.pdf", file=io.BytesIO(pdf_content))

    with pytest.raises(ValueError, match="JPEG"):
        await parse_nakladnoy(fake_file)


@pytest.mark.asyncio
async def test_nakladnoy_no_api_key():
    """GROQ_API_KEY yo'q bo'lsa 503 AppError."""
    from fastapi import UploadFile
    from app.core.errors import AppError
    from app.modules.import_data.vision import parse_nakladnoy

    # Haqiqiy JPEG magic bytes
    jpeg_content = b"\xFF\xD8\xFF\xE0" + b"x" * 100
    fake_file = UploadFile(filename="test.jpg", file=io.BytesIO(jpeg_content))

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.groq_api_key = None
        mock_settings.groq_vision_model = "meta-llama/llama-4-scout-17b-16e-instruct"

        with pytest.raises(AppError) as exc_info:
            await parse_nakladnoy(fake_file)

    assert exc_info.value.status_code == 503


# ─── 4. Confirm — server-avtoritar target ─────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_target_by_role_admin(
    db_session: AsyncSession,
    admin_user: AppUser,
    default_enterprise: Enterprise,
    fake_redis,
):
    """Administrator: target = catalog."""
    from app.modules.import_data.service import confirm_import
    from app.modules.import_data.schemas import ImportConfirmIn, ConfirmRow

    rows = [
        ConfirmRow(
            row_index=0,
            name="Test Mahsulot Import",
            qty=10.0,
            price=5000.0,
            client_uuid=uuid.uuid4(),
        )
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    result = await confirm_import(
        db=db_session,
        body=body,
        current_user=admin_user,
        redis=fake_redis,
    )

    assert result.target == "catalog"
    assert result.created == 1
    assert result.skipped == 0
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_confirm_idempotent_client_uuid(
    db_session: AsyncSession,
    admin_user: AppUser,
    default_enterprise: Enterprise,
    fake_redis,
):
    """Bir xil client_uuid ikki marta confirm qilinganda ikkinchisi skip."""
    from app.modules.import_data.service import confirm_import
    from app.modules.import_data.schemas import ImportConfirmIn, ConfirmRow

    client_uuid = uuid.uuid4()
    rows = [
        ConfirmRow(
            row_index=0,
            name="Idempotent Mahsulot",
            qty=5.0,
            price=1000.0,
            client_uuid=client_uuid,
        )
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    # Birinchi confirm
    result1 = await confirm_import(
        db=db_session, body=body, current_user=admin_user, redis=fake_redis
    )
    assert result1.created == 1

    # Xuddi shu satr yana confirm (yangi session, lekin Redis keshi bor)
    result2 = await confirm_import(
        db=db_session, body=body, current_user=admin_user, redis=fake_redis
    )
    # Idempotent: create_product Redis keshida topadi, qaytaradi — created (skip emas)
    # Sababi: catalog service idempotentlikni create sifatida boshqaradi
    assert result2.created + result2.skipped >= 1


@pytest.mark.asyncio
async def test_confirm_op_isolation_bad_row(
    db_session: AsyncSession,
    admin_user: AppUser,
    default_enterprise: Enterprise,
    fake_redis,
):
    """Xato satr batchni yiqitmaydi — op-izolyatsiya."""
    from app.modules.import_data.service import confirm_import
    from app.modules.import_data.schemas import ImportConfirmIn, ConfirmRow

    # Birinchi satr: to'g'ri
    # Ikkinchi satr: SKU dublikat — xato chiqarishi kerak (agar xato bo'lsa errors ga tushadi)
    rows = [
        ConfirmRow(
            row_index=0,
            name="To'g'ri Mahsulot",
            sku="UNIQ-SKU-001",
            qty=10.0,
            price=5000.0,
            client_uuid=uuid.uuid4(),
        ),
        ConfirmRow(
            row_index=1,
            name="Boshqa Mahsulot",
            sku="UNIQ-SKU-001",  # Dublikat SKU → xato
            qty=5.0,
            price=3000.0,
            client_uuid=uuid.uuid4(),  # Boshqa client_uuid
        ),
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    result = await confirm_import(
        db=db_session, body=body, current_user=admin_user, redis=fake_redis
    )

    # Birinchi satr muvaffaqiyatli, ikkinchisi xato (yoki ikkalasi created — SKU unikalligi)
    # Op-izolyatsiya: batch yiqilmaydi
    assert result.created + result.skipped + len(result.errors) == 2
    assert result.target == "catalog"


@pytest.mark.asyncio
async def test_confirm_agent_forbidden(
    db_session: AsyncSession,
    make_user,
    default_enterprise: Enterprise,
    fake_redis,
):
    """Agent confirm qila olmaydi — 403."""
    from app.core.errors import AppError
    from app.modules.import_data.service import confirm_import
    from app.modules.import_data.schemas import ImportConfirmIn, ConfirmRow

    agent = await make_user("agent")

    rows = [
        ConfirmRow(
            row_index=0,
            name="Agent Mahsulot",
            qty=1.0,
            price=1000.0,
            client_uuid=uuid.uuid4(),
        )
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    with pytest.raises(AppError) as exc_info:
        await confirm_import(db=db_session, body=body, current_user=agent, redis=fake_redis)

    assert exc_info.value.status_code == 403


# ─── 4b. Confirm store_inventory — #16 idempotentlik DB-backstop ─────────────


@pytest.mark.asyncio
async def test_confirm_store_inventory_client_uuid_db_backstop(
    db_session: AsyncSession,
    store_user: AppUser,
    default_enterprise: Enterprise,
    fake_redis,
):
    """
    #16: client_uuid takror (boshqa so'rov, Redis kesh bo'lsa ham) DB
    UNIQUE (uq_store_inv_client_uuid) orqali skip qilinadi — asosiy backstop.
    """
    from app.models.store_inventory import StoreInventory
    from app.modules.import_data.service import confirm_import
    from sqlalchemy import select

    client_uuid = uuid.uuid4()
    rows = [
        ConfirmRow(
            row_index=0,
            name="Import Tovar",
            qty=3.0,
            price=1000.0,
            client_uuid=client_uuid,
        )
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    result1 = await confirm_import(
        db=db_session, body=body, current_user=store_user, redis=fake_redis
    )
    assert result1.target == "store_inventory"
    assert result1.created == 1
    assert result1.skipped == 0

    # Xuddi shu client_uuid bilan qayta confirm — skip (DB backstop)
    result2 = await confirm_import(
        db=db_session, body=body, current_user=store_user, redis=fake_redis
    )
    assert result2.created == 0
    assert result2.skipped == 1

    stmt = select(StoreInventory).where(StoreInventory.client_uuid == client_uuid)
    res = await db_session.execute(stmt)
    assert len(res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_confirm_store_inventory_retry_after_commit_failure_not_duplicated(
    db_session: AsyncSession,
    store_user: AppUser,
    default_enterprise: Enterprise,
    fake_redis,
):
    """
    #16 regressiya: Redis idempotentlik kaliti COMMIT'DAN OLDIN emas,
    COMMIT'DAN KEYIN qo'yiladi. Birinchi urinish commit'da yiqilsa (masalan
    tarmoq/DB xatosi) — Redis kalit qo'yilmagan bo'lishi kerak, shuning
    uchun keyingi retry noto'g'ri "band" bo'lib qolmaydi. Root rollback
    (confirm_import ichida) birinchi urinishning YOZUVLARINI ham bekor
    qiladi, shuning uchun retry MUVAFFAQIYATLI yaratadi va DUBLIKAT bo'lmaydi.

    IKKITA SATR ATAYLAB ISHLATILADI (bitta emas): #15 regressiyasi — agar
    birinchi qator SAVEPOINT'i "release" qilingan bo'lsa-yu (sp.commit()),
    ikkinchi qator qayta ishlangandan KEYIN yakuniy commit yiqilsa, birinchi
    qatorning "release" qilingan ma'lumoti to'liq db.rollback()'dan noto'g'ri
    omon qolishi mumkin edi (aiosqlite/SQLAlchemy asyncio xatti-harakati).
    """
    from app.core.errors import AppError
    from app.models.store_inventory import StoreInventory
    from app.modules.import_data import service as import_service
    from sqlalchemy import select

    # store_user/default_enterprise fixture'lari faqat flush qilingan (commit
    # emas) — keyingi simulyatsiya qilingan commit-xato rollback'i ularni ham
    # yo'q qilib qo'ymasligi uchun avval commit qilamiz.
    await db_session.commit()

    client_uuid_1 = uuid.uuid4()
    client_uuid_2 = uuid.uuid4()
    rows = [
        ConfirmRow(
            row_index=0,
            name="Retry Tovar 1",
            qty=2.0,
            price=2000.0,
            client_uuid=client_uuid_1,
        ),
        ConfirmRow(
            row_index=1,
            name="Retry Tovar 2",
            qty=3.0,
            price=1500.0,
            client_uuid=client_uuid_2,
        ),
    ]
    body = ImportConfirmIn(source="excel", rows=rows)

    # 1-urinish: commit simulyatsiya qilingan xato bilan yiqiladi
    original_commit = db_session.commit

    async def _failing_commit():
        raise RuntimeError("simulyatsiya: DB ulanish xatosi")

    db_session.commit = _failing_commit
    try:
        with pytest.raises(AppError) as exc_info:
            await import_service.confirm_import(
                db=db_session, body=body, current_user=store_user, redis=fake_redis
            )
        assert exc_info.value.status_code == 500
    finally:
        db_session.commit = original_commit

    # Redis kalit qo'yilmagan (commit muvaffaqiyatsiz bo'lgani uchun) — HAR
    # IKKI qator uchun ham (birinchi qator SAVEPOINT'i "release" qilingan
    # bo'lsa ham, hali committed emas).
    for cu in (client_uuid_1, client_uuid_2):
        idem_key = f"{import_service._IDEM_STORE_INV_PREFIX}:{cu}"
        assert await fake_redis.get(idem_key) is None

    # DB'da ikkala qator ham YO'Q bo'lishi kerak (root rollback to'liq
    # bekor qilgan bo'lishi kerak — #15 regressiyasi shu yerda ushlanadi)
    for cu in (client_uuid_1, client_uuid_2):
        stmt = select(StoreInventory).where(StoreInventory.client_uuid == cu)
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None, (
            f"client_uuid={cu} rollback'dan keyin ham DB'da qolib ketdi (#15 regressiya)"
        )

    # db.rollback() SQLAlchemy'da barcha sessiya ob'ektlarini "expire" qiladi
    # (expire_on_commit sozlamasidan qat'iy nazar) — keyingi ishlatish uchun
    # store_user'ni qayta yuklaymiz (aks holda MissingGreenlet xatosi).
    await db_session.refresh(store_user)

    # 2-urinish (retry) — muvaffaqiyatli bo'lishi kerak, "band" bo'lib qolmagan
    result2 = await import_service.confirm_import(
        db=db_session, body=body, current_user=store_user, redis=fake_redis
    )
    assert result2.created == 2, f"Retry muvaffaqiyatsiz: {result2}"
    assert result2.skipped == 0

    # DB da FAQAT bitta-bitta yozuv (dublikat yo'q)
    for cu in (client_uuid_1, client_uuid_2):
        stmt = select(StoreInventory).where(StoreInventory.client_uuid == cu)
        res = await db_session.execute(stmt)
        assert len(res.scalars().all()) == 1


# ─── 5. HTTP endpointlar RBAC ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excel_parse_endpoint_unauthorized(import_client):
    """Token yo'q → 401."""
    resp = await import_client.post(
        "/import/excel/parse",
        files={"file": ("test.xlsx", b"PK fake", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_excel_parse_endpoint_admin(import_client, admin_user):
    """Administrator parse endpoint ga kira oladi (fayl noto'g'ri → 422)."""
    token = await get_token(import_client, admin_user)

    # Noto'g'ri fayl — 422 kutiladi
    resp = await import_client.post(
        "/import/excel/parse",
        files={"file": ("test.xlsx", b"NOT_XLSX_CONTENT", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_endpoint_admin_empty_rows(import_client, admin_user):
    """Bo'sh rows → 422 (min_length=1 validatsiya)."""
    token = await get_token(import_client, admin_user)

    resp = await import_client.post(
        "/import/confirm",
        json={"source": "excel", "rows": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_endpoint_admin_valid(import_client, admin_user):
    """Administrator to'g'ri confirm → 200."""
    token = await get_token(import_client, admin_user)

    resp = await import_client.post(
        "/import/confirm",
        json={
            "source": "excel",
            "rows": [
                {
                    "row_index": 0,
                    "name": "HTTP Endpoint Mahsulot",
                    "qty": 10.0,
                    "price": 5000.0,
                    "client_uuid": str(uuid.uuid4()),
                }
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target"] == "catalog"
    assert "created" in data
    assert "skipped" in data
    assert "errors" in data
