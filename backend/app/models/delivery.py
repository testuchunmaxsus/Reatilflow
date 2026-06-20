"""
Yetkazib berish modeli — T18 Delivery.

Jadval:
  delivery — yetkazish yozuvi (holat mashinasi bilan)

ADR §3.4, §3.7:
  - status: assigned → started → delivering → delivered (→ failed istalgan joydan)
  - server-avtoritar holat mashinasi
  - client_uuid idempotentlik (UNIQUE partial index)
  - version — optimistik lock
  - delivery_track GpsPoint'da (TimescaleDB, ALOHIDA BAZA) — shu yerda FK YO'Q.
    GPS track GET /gps/track/{delivery_id} orqali o'qiladi (T17 GPS moduli).
  - FK faqat OLTP'ga: order (FK → order.id), courier (FK → app_user.id)

MUHIM: delivery_track (GPS) — ALOHIDA TimescaleDB baza.
  Cross-DB FK YO'Q — delivery.id faqat GpsPoint.delivery_id (FK siz UUID) orqali bog'lanadi.
  GPS trek o'qish: get_track(delivery_id=...) GPS moduli servisiga havola.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import AppUser
    from app.models.enterprise import Enterprise


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── Holat konstantalari ─────────────────────────────────────────────────────

DELIVERY_STATUSES = frozenset({
    "assigned",
    "started",
    "delivering",
    "delivered",
    "failed",
})

# Server-avtoritar qonuniy o'tishlar:
#   assigned  → started, failed
#   started   → delivering, failed
#   delivering → delivered, failed
#   delivered → (terminal holat — orqaga qaytish mumkin emas)
#   failed    → (terminal holat)
VALID_TRANSITIONS: dict[str, set[str]] = {
    "assigned":   {"started", "failed"},
    "started":    {"delivering", "failed"},
    "delivering": {"delivered", "failed"},
    "delivered":  set(),   # terminal holat
    "failed":     set(),   # terminal holat
}


class Delivery(TimestampMixin, Base):
    """
    Yetkazib berish yozuvi.

    Holat mashinasi (ADR §3.5, T18):
      assigned → started → delivering → delivered
      istalgan holat → failed (cheklovlar bilan)
      delivered va failed — terminal holatlar.

    GPS trek (ADR §3.7):
      Yetkazish GPS trek GpsPoint.delivery_id orqali bog'langan.
      GpsPoint — ALOHIDA TimescaleDB baza.
      Cross-DB FK YO'Q — faqat UUID reference (GpsPoint.delivery_id).
      Trek o'qish: GET /gps/track/{delivery_id} (GPS moduli).

    started holatida: start_gps_lat/lng yoziladi (kuryer yo'lga chiqqan joy).
    delivered holatida: delivery_gps_lat/lng + proof_photo_url yoziladi.

    Idempotentlik: client_uuid unique partial index (IS NOT NULL).
    """

    __tablename__ = "delivery"
    __table_args__ = (
        Index("ix_delivery_order_id", "order_id"),
        Index("ix_delivery_courier_id", "courier_id"),
        Index("ix_delivery_status", "status"),
        # Statistika (T22 SQL agg): delivery_stats assigned_at bo'yicha vaqt filtri.
        Index("ix_delivery_assigned_at", "assigned_at"),
        # Idempotentlik: client_uuid unique
        # PostgreSQL: migration 0012 partial unique index (IS NOT NULL) yaratadi.
        # SQLite (test): bu Index(unique=True) ishlaydi (NULL != NULL qoidasi partial ga ekvivalent).
        # ORM darajasida UniqueConstraint ISHLATILMAYDI — alembic autogenerate drift oldini olish.
        Index("uq_delivery_client_uuid", "client_uuid", unique=True),
    )

    # ─── FK ustunlar ─────────────────────────────────────────────────────────

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("order.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Buyurtma FK → order (OLTP)",
    )

    courier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Kuryer FK → app_user (OLTP)",
    )

    # ─── Holat ───────────────────────────────────────────────────────────────

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="assigned",
        comment="Holat: assigned | started | delivering | delivered | failed",
    )

    # ─── Vaqt damllari ────────────────────────────────────────────────────────

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Tayinlangan vaqt (UTC)",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Yo'lga chiqqan vaqt (started holati) (UTC)",
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Yetkazilgan vaqt (delivered holati) (UTC)",
    )

    # ─── GPS koordinatalar ────────────────────────────────────────────────────
    # MUHIM: Bu faqat KEY NUQTALAR (boshlash va yetkazish joylari).
    # To'liq GPS trek GpsPoint (TimescaleDB, alohida baza) da.

    start_gps_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=11, scale=8),
        nullable=True,
        default=None,
        comment=(
            "Boshlash GPS kenglik — started holatida yoziladi. "
            "To'liq trek GpsPoint(delivery_id=...) da (alohida TimescaleDB)."
        ),
    )

    start_gps_lng: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=8),
        nullable=True,
        default=None,
        comment="Boshlash GPS uzunlik — started holatida yoziladi.",
    )

    delivery_gps_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=11, scale=8),
        nullable=True,
        default=None,
        comment="Yetkazish GPS kenglik — delivered holatida yoziladi.",
    )

    delivery_gps_lng: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=8),
        nullable=True,
        default=None,
        comment="Yetkazish GPS uzunlik — delivered holatida yoziladi.",
    )

    # ─── Dalil rasm ──────────────────────────────────────────────────────────

    proof_photo_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        default=None,
        comment="Yetkazish dalil rasmi URL (MinIO/S3) — delivered holatida",
    )

    # ─── Muvaffaqiyatsizlik sababi ────────────────────────────────────────────

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Muvaffaqiyatsizlik sababi — failed holati uchun",
    )

    # ─── Qo'shimcha maydonlar ─────────────────────────────────────────────────

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
        comment="Filial ID (ixtiyoriy)",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
        comment=(
            "Klient idempotentlik UUID — UNIQUE partial index (IS NOT NULL). "
            "Takroriy tayinlashdan himoya qiladi."
        ),
    )

    # ─── MT1: enterprise_id ──────────────────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Korxona FK → enterprise (MT1)",
    )

    # ─── Relationships ─────────────────────────────────────────────────────────
    # String-based forward references (circular import oldini olish uchun)

    order: Mapped["Order"] = relationship(
        "Order",
        lazy="select",
        foreign_keys="[Delivery.order_id]",
    )

    courier: Mapped["AppUser"] = relationship(
        "AppUser",
        lazy="select",
        foreign_keys="[Delivery.courier_id]",
    )

    def __repr__(self) -> str:
        return (
            f"<Delivery id={self.id} order={self.order_id} "
            f"courier={self.courier_id} status={self.status!r}>"
        )
