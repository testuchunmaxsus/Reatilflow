"""
Umumiy mixin va Base — barcha modellar uchun.

Har bir jadval quyidagi ustunlarga ega:
  id          — UUID v7 (vaqt-tartibli, offline klient generatsiya qila oladi)
  version     — BIGINT, optimistic lock + LWW (Last-Write-Wins) uchun
  created_at  — UTC timestamp, yozilgandan keyin o'zgarmaydi
  updated_at  — UTC timestamp, har yangilanishda avtomatik o'zgaradi
  deleted_at  — UTC timestamp, soft delete (NULL = aktiv)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.uuid7 import uuid7


def _now_utc() -> datetime:
    """Joriy UTC vaqt."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy deklarativ asosi — barcha modellar shu sinfdan meros oladi."""
    pass


class TimestampMixin:
    """
    Umumiy ustunlar mixini.

    Barcha jadvallarda qo'llash uchun:
        class MyModel(TimestampMixin, Base):
            __tablename__ = "my_table"
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    version: Mapped[int] = mapped_column(
        BigInteger,
        default=1,
        nullable=False,
        comment="Optimistik lock + LWW uchun versiya raqami",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        server_default=func.now(),
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        server_default=func.now(),
        onupdate=_now_utc,
        nullable=False,
        comment="Oxirgi yangilangan vaqt (UTC)",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Soft delete vaqti (NULL = aktiv yozuv)",
    )
