"""
Excel (.xlsx) fayl o'qish va parse qilish.

Xavfsizlik:
  - Magic bytes tekshiruvi (PK zip header — .xlsx ZIP asosida).
  - Max 5 MB fayl hajmi.
  - Faqat .xlsx qabul qilinadi.

Oqim:
  1. Magic bytes + hajm tekshiruvi.
  2. openpyxl bilan birinchi sheet o'qiladi.
  3. Ustun moslash (column_mapping.map_columns).
  4. Har satr → ParsedRow.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from fastapi import UploadFile

from app.modules.import_data.column_mapping import map_columns
from app.modules.import_data.schemas import ColumnMapping, ExcelParseOut, ParsedRow

logger = logging.getLogger(__name__)

# ─── Konstantalar ─────────────────────────────────────────────────────────────

_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
# .xlsx — ZIP archive, magic: PK (0x50 0x4B)
_XLSX_MAGIC = b"PK"
_MAX_ROWS = 1000  # max parse qilinadigan satrlar


# ─── Excel parse ─────────────────────────────────────────────────────────────


async def parse_excel(file: UploadFile) -> ExcelParseOut:
    """
    Excel faylni parse qiladi.

    Args:
        file: FastAPI UploadFile (.xlsx).

    Returns:
        ExcelParseOut (columns_detected, rows, warnings, parse_id).

    Raises:
        ValueError: Noto'g'ri fayl (magic bytes, hajm, format).
    """
    warnings: list[str] = []

    # 1. Fayl o'qish
    content = await file.read()

    # 2. Hajm tekshiruvi
    if len(content) > _MAX_FILE_SIZE:
        raise ValueError(f"Fayl hajmi {_MAX_FILE_SIZE // (1024*1024)} MB dan oshmasin")

    # 3. Magic bytes tekshiruvi
    if not content.startswith(_XLSX_MAGIC):
        raise ValueError("Faqat .xlsx format qabul qilinadi (ZIP magic bytes topilmadi)")

    # 4. openpyxl bilan o'qish
    try:
        import openpyxl
    except ImportError:
        raise ValueError("openpyxl o'rnatilmagan — requirements'ga qo'shing")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            raise ValueError("Excel faylda faol sheet topilmadi")

        all_rows: list[list[Any]] = []
        for row in ws.iter_rows(values_only=True):
            all_rows.append(list(row))

        wb.close()
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Excel fayl o'qishda xato: {exc}") from exc

    if not all_rows:
        raise ValueError("Excel fayl bo'sh")

    # 5. Header satri
    header_row = all_rows[0]
    # None bo'lgan sarlavhalarni filtrlab, string'ga o'tkazish
    headers: list[str] = []
    for cell in header_row:
        if cell is not None:
            headers.append(str(cell).strip())
        else:
            headers.append("")

    # Bo'sh sarlavhalar haqida ogohlantirish
    empty_headers = [i for i, h in enumerate(headers) if not h]
    if empty_headers:
        warnings.append(f"Bo'sh sarlavhali ustunlar ({len(empty_headers)} ta) o'tkazib yuborildi")

    # 6. Ustun moslash (AI yordamida)
    data_rows = all_rows[1:_MAX_ROWS + 1]
    sample_rows = data_rows[:3]

    mapping = await map_columns(headers, sample_rows)

    # 7. ParsedRow yaratish
    rows: list[ParsedRow] = []
    for row_idx, raw_row in enumerate(data_rows):
        parsed = _row_to_parsed(raw_row, headers, mapping, row_idx + 1)
        if parsed is not None:
            rows.append(parsed)

    if len(all_rows) - 1 > _MAX_ROWS:
        warnings.append(
            f"Faqat birinchi {_MAX_ROWS} ta satr parse qilindi "
            f"(jami {len(all_rows) - 1} ta)"
        )

    # 8. ColumnMapping yaratish
    columns_detected = [
        ColumnMapping(
            source_header=h,
            mapped_to=mapping.get(h, (None, 0.0))[0],
            confidence=mapping.get(h, (None, 0.0))[1],
        )
        for h in headers
        if h  # bo'sh sarlavhalarni o'tkazib yuborish
    ]

    # Narx ustuni topilmadimi?
    has_price = any(cm.mapped_to == "price" for cm in columns_detected)
    has_name = any(cm.mapped_to == "name" for cm in columns_detected)
    if not has_price:
        warnings.append("Narx ustuni topilmadi — qo'lda belgilang")
    if not has_name:
        warnings.append("Mahsulot nomi ustuni topilmadi — qo'lda belgilang")

    return ExcelParseOut(
        parse_id=uuid.uuid4(),
        columns_detected=columns_detected,
        rows=rows,
        warnings=warnings,
    )


def _row_to_parsed(
    raw_row: list[Any],
    headers: list[str],
    mapping: dict[str, tuple[str | None, float]],
    row_idx: int,
) -> ParsedRow | None:
    """Bitta Excel satrini ParsedRow ga o'tkazadi. Bo'sh satrni None qaytaradi."""
    # Ustun → maydon xaritasi yaratish
    field_map: dict[str, Any] = {}
    for col_idx, header in enumerate(headers):
        if not header:
            continue
        mapped_field, _ = mapping.get(header, (None, 0.0))
        if mapped_field and col_idx < len(raw_row):
            val = raw_row[col_idx]
            if val is not None:
                field_map[mapped_field] = val

    # Barcha maydonlar bo'sh bo'lsa — satr o'tkaziladi
    if not field_map:
        return None

    name = _safe_str(field_map.get("name"))
    sku = _safe_str(field_map.get("sku"))
    barcode = _safe_str(field_map.get("barcode"))
    qty = _safe_float(field_map.get("qty"))
    price = _safe_float(field_map.get("price"))
    currency = _safe_str(field_map.get("currency")) or "UZS"
    if len(currency) != 3:
        currency = "UZS"
    expiry_date = _safe_date(field_map.get("expiry_date"))

    # Nom va narx bo'lmasa — satrni skip
    if not name and price is None and qty is None:
        return None

    return ParsedRow(
        row_index=row_idx,
        name=name,
        sku=sku,
        barcode=barcode,
        qty=qty,
        price=price,
        currency=currency.upper(),
        expiry_date=expiry_date,
        confidence=0.9,
    )


def _safe_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_date(val: Any):
    """datetime.date yoki datetime → date."""
    if val is None:
        return None
    import datetime
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    # String urinib ko'rish
    try:
        return datetime.date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None
