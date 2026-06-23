"""
POS (Point-of-Sale) modellari — chakana sotuv yadrosi.

Jadvallar:
  pos_sale      — sotuv bosh yozuvi (kassir, do'kon, to'lov, holat)
  pos_sale_line — sotuv qatorlari (mahsulot, miqdor, narx, jami)

ADR §4.1 bo'yicha:
  - server-avtoritar narx (klient narx bermaydi — orders pattern)
  - enterprise_id har jadvalda (MT1 pattern, ORM nullable, migratsiyada NOT NULL)
  - client_uuid idempotentlik (orders pattern)
  - outbox event (pos.sale_created)

NARX XAVFSIZLIGI:
  Klient unit_price/discount BERMAYDI.
  Narx FAQAT server tomonida katalogdan (do'kon segmenti bo'yicha) olinadi.
  Bu orders moduli bilan izchil (T11 saboq).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise
    from app.models.store import Store
    from app.models.user import AppUser
    from app.models.catalog import Product


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── To'lov usullari ─────────────────────────────────────────────────────────

POS_PAYMENT_METHODS = frozenset({"cash", "card"})

# ─── Sotuv holatlari ──────────────────────────────────────────────────────────

POS_SALE_STATUSES = frozenset({"completed", "void"})


class PosSale(TimestampMixin, Base):
    """
    POS Sotuv bosh yozuvi.

    Har bir kassir amali (checkout) bitta PosSale yaratadi.
    Server-avtoritar narx: klient narx/discount bermaydi (T11 pattern).
    client_uuid idempotentlik: bir xil klient UUID → bir xil sotuv qaytaradi.

    Maydonlar:
      store_id       — do'kon FK (sotuv shu do'konda bajarildi)
      cashier_id     — kassir FK (sotuvchi foydalanuvchi)
      total_amount   — jami sotuv summasi (qatorlardan hisoblanadi)
      discount_amount — chegirma summasi (default 0 — klient bermaydi, server hisoblaydi)
      payment_method — to'lov usuli: cash | card
      customer_phone — xaridor telefoni (ixtiyoriy — PII, nullable)
      status         — completed | void (default completed)
      client_uuid    — idempotentlik UUID (ixtiyoriy)
      enterprise_id  — korxona FK (MT1)
    """

    __tablename__ = "pos_sale"
    __table_args__ = (
        Index("ix_pos_sale_store_created", "store_id", "created_at"),
        # Idempotentlik: (store_id, client_uuid) — partial, IS NOT NULL
        UniqueConstraint("store_id", "client_uuid", name="uq_pos_sale_store_client_uuid"),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Do'kon FK → store",
    )

    cashier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kassir FK → app_user (sotuvchi)",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Jami sotuv summasi (Decimal) — qatorlardan hisoblanadi",
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Jami chegirma summasi (Decimal, default=0) — server hisoblaydi",
    )

    payment_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="To'lov usuli: cash | card",
    )

    customer_phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Xaridor telefon raqami (PII, ixtiyoriy)",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
        comment="Holat: completed | void",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Klient idempotentlik UUID — UNIQUE partial index (IS NOT NULL)",
    )

    # ─── MT1: enterprise_id ──────────────────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Korxona FK → enterprise (MT1)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    lines: Mapped[list["PosSaleLine"]] = relationship(
        "PosSaleLine",
        back_populates="sale",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<PosSale id={self.id} store={self.store_id} "
            f"status={self.status!r} total={self.total_amount}>"
        )


class PosSaleLine(Base):
    """
    POS Sotuv qatori — bitta mahsulot.

    line_total = unit_price * qty (server hisoblab yozadi)
    unit_price — server tomonida katalogdan olinadi (klient bermaydi).
    enterprise_id — MT1 tenant izolyatsiyasi.
    """

    __tablename__ = "pos_sale_line"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    sale_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pos_sale.id", ondelete="CASCADE"),
        nullable=False,
        comment="Sotuv FK → pos_sale",
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Mahsulot FK → product",
    )

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Miqdor (Decimal, musbat)",
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Birlik narxi (Decimal) — SERVER TOMONIDA katalogdan olinadi",
    )

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Qator jami: unit_price * qty",
    )

    # ─── MT1: enterprise_id ──────────────────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Korxona FK → enterprise (MT1)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    sale: Mapped["PosSale"] = relationship(
        "PosSale",
        back_populates="lines",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<PosSaleLine sale={self.sale_id} product={self.product_id} "
            f"qty={self.qty} total={self.line_total}>"
        )
