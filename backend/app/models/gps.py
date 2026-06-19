"""
GPS trekking modeli — gps_point jadvali.

T17: Yuqori chastotali GPS trekking (FastAPI).

ADR §3.7:
  - GPS nuqtalari time-series — asosiy OLTP bazadan izolyatsiya.
  - Postgres: TimescaleDB hypertable (recorded_at ustuni bo'yicha).
  - SQLite (test): oddiy jadval.
  - recorded_at — QURILMA vaqti (offline yozilgan, klientdan keladi).
  - ingested_at — SERVER qabul qilgan vaqt (server clock).
  - 90 kun retention (Postgres: add_retention_policy; hozir TODO).

XAVFSIZLIK:
  - user_id SERVER'dan olinadi (current_user.id) — klient boshqa nomidan
    ingest qila olmaydi (IDOR yo'q).
  - delivery_id ixtiyoriy — T18 da FK qo'shiladi; hozir UUID nullable.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class GpsPoint(Base):
    """
    GPS trekking nuqtasi.

    Har bir nuqta:
      - user_id       — foydalanuvchi (agent/kuryer); SERVER'dan olinadi
      - delivery_id   — yetkazish UUID (ixtiyoriy; T18 da FK bo'ladi)
      - lat / lng     — GPS koordinatalar (Decimal, 8 kasrga aniqlik)
      - recorded_at   — QURILMA vaqti (offline yozilgan — klientdan keladi)
      - speed         — tezlik m/s (ixtiyoriy)
      - ingested_at   — SERVER qabul qilgan vaqt (server clock)
      - created_at    — server qabul vaqti (ingested_at bilan teng)

    TimescaleDB hypertable (Postgres):
      - Partitsiya: recorded_at bo'yicha (vaqt bo'yicha sharding)
      - Retention: 90 kun (add_retention_policy — migration izohi/TODO)
      - Oddiy jadvaldan farqi: time-series queries uchun optimallashtirilgan

    Idempotentlik:
      - (user_id, recorded_at) juftligi UNIQUE — takror so'rov e'tiborsiz (ON CONFLICT DO NOTHING)
      - TimescaleDB hypertable bilan UNIQUE indeks faqat partitsiya ustunini
        o'z ichiga olishi shart → (user_id, recorded_at) to'g'ri.
    """

    __tablename__ = "gps_point"

    # Indekslar va UNIQUE constraint — ORM darajasida (metadata/test uchun)
    # Migratsiyada ham yaratiladi (TimescaleDB bilan mos)
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "recorded_at",
            name="uq_gps_point_user_recorded",
        ),
        Index("ix_gps_point_user_recorded", "user_id", "recorded_at"),
        Index("ix_gps_point_delivery_recorded", "delivery_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Foydalanuvchi ID — SERVER'dan olinadi (klientga ISHONMASLIK)",
    )

    delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment=(
            "Yetkazish UUID (ixtiyoriy; FK T18 da qo'shiladi — hozir faqat UUID)"
        ),
    )

    lat: Mapped[Decimal] = mapped_column(
        Numeric(precision=11, scale=8),
        nullable=False,
        comment="GPS kenglik (±90.00000000, 8 kasrga aniqlik)",
    )

    lng: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        nullable=False,
        comment="GPS uzunlik (±180.00000000, 8 kasrga aniqlik)",
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment=(
            "QURILMA vaqti — offline yozilgan (klientdan keladi). "
            "TimescaleDB hypertable partitsiya ustuni. "
            "ADR §3.7: klient soatiga ishonilmaydi — faqat trekking uchun."
        ),
    )

    speed: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=8, scale=3),
        nullable=True,
        comment="Tezlik m/s (ixtiyoriy — qurilmadan keladi)",
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        comment="SERVER qabul qilgan vaqt (UTC, server clock) — ADR §3.7",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        comment="Yaratilgan vaqt (ingested_at bilan teng — server clock)",
    )

    def __repr__(self) -> str:
        return (
            f"<GpsPoint id={self.id} user={self.user_id} "
            f"lat={self.lat} lng={self.lng} recorded_at={self.recorded_at}>"
        )
