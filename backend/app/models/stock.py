"""
Ombor (stock) modellari — APPEND-ONLY event-sourced ledger.

Jadvallar:
  stock_movement  — har bir harakatni qayd etadi (faqat INSERT).
  stock_balance   — harakatlardan derivatsiyalangan joriy qoldiq (kesh).

Muhim:
  - stock_movement APPEND-ONLY: UPDATE/DELETE TAQIQLANGAN.
    Balans faqat harakatlar yig'indisidan hisoblanadi.
  - stock_balance — performance uchun kesh; versiya orqali optimistik lock.
  - qty — Decimal (moliyaviy aniqlik talabi: float EMAS).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class StockMovement(Base):
    """
    Ombor harakati — APPEND-ONLY.

    Bu jadvalga faqat INSERT qilinadi; UPDATE/DELETE TAQIQLANGAN.
    Har bir kirim/chiqim/transfer/tuzatish alohida yozuv sifatida saqlanadi.

    type qiymatlari:
      in       — kirim (qoldiq oshadi)
      out      — chiqim (qoldiq kamayadi)
      transfer — bir ombordan boshqasiga ko'chirish (ikkita yozuv: out+in)
      adjust   — inventarizatsiya tuzatishi (+ yoki -)

    client_uuid — idempotentlik kaliti (UNIQUE partial index).
    """

    __tablename__ = "stock_movement"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Ombor/sklad ID (hozircha FK yo'q — kelajakda warehouse jadvali qo'shiladi)",
    )

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Harakat turi: in | out | transfer | adjust",
    )

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Miqdor (Decimal — aniqlik uchun; out/adjust manfiy bo'lishi mumkin)",
    )

    ref_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Havola turi: order | purchase | adjustment | ... (ixtiyoriy)",
    )

    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Havola ID (masalan, buyurtma ID, ixtiyoriy)",
    )

    moved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kim bajardi (FK → app_user)",
    )

    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Harakat vaqti (UTC)",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Klient idempotentlik UUID — UNIQUE partial index (client_uuid IS NOT NULL)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yaratilgan vaqt (UTC) — APPEND-ONLY: o'zgarmaydi",
    )

    def __repr__(self) -> str:
        return (
            f"<StockMovement id={self.id} product={self.product_id} "
            f"type={self.type!r} qty={self.qty}>"
        )


class StockBalance(Base):
    """
    Ombor qoldig'i — harakatlardan derivatsiyalangan kesh.

    Bu jadval HISOBLANGAN holat — stock_movement harakatlar yig'indisi.
    Optimistik lock: version majburiy (boshqa tranzaksiya o'rtada o'zgartirsa → 409).

    Muhim xavfsizlik izohi:
      - qty_on_hand va qty_reserved Decimal (float emas — aniqlik talab qilinadi).
      - Balans manfiy bo'lmasligi kerak (chiqim cheklanishi stock:create da tekshiriladi).
    """

    __tablename__ = "stock_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Ombor ID",
    )

    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        comment="Qo'ldagi miqdor (Decimal)",
    )

    qty_reserved: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        comment="Band qilingan miqdor (Decimal)",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        comment="Optimistik lock versiyasi",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Oxirgi yangilangan vaqt (UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<StockBalance product={self.product_id} "
            f"warehouse={self.warehouse_id} on_hand={self.qty_on_hand}>"
        )
