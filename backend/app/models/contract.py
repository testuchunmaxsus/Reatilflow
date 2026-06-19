"""
Shartnoma (Contract) modeli — contract jadvali.

Shartnoma — do'kon bilan tuzilgan shartnoma hujjati.
Fayl (PDF) MinIO'da saqlanadi; file_url nullable.

status DERIVED maydon: valid_to ga qarab hisoblanadi.
  - expired  : valid_to < bugun
  - expiring : valid_to - bugun <= EXPIRING_DAYS (30)
  - active   : boshqa barcha holat

client_uuid — idempotentlik uchun (partial unique IS NOT NULL).
version     — optimistik lock.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# Muddati tugayotgan shartnoma ogohlantirish chegarasi (kunlar)
CONTRACT_EXPIRING_DAYS: int = 30


class Contract(TimestampMixin, Base):
    """
    Shartnoma hujjati.

    Maydonlar:
      store_id       — do'kon FK → store (RESTRICT)
      number         — shartnoma raqami (string, unique per store)
      file_url       — PDF fayl URL (MinIO; NULL agar hali yuklanmagan)
      signed_at      — imzolangan vaqt (NULL agar hali imzolanmagan)
      valid_from     — amal qilish boshlanishi (sana)
      valid_to       — amal qilish tugashi (sana)
      contract_type  — turi: trade | employment | service | other
      branch_id      — filial ID (ixtiyoriy)
      client_uuid    — idempotentlik UUID (partial unique IS NOT NULL)

    status — DERIVED: valid_to ga qarab Python da hisoblanadi.
      Saqlanmaydi — har o'qishda hisoblanadi.
    """

    __tablename__ = "contract"

    # ─── Asosiy maydonlar ──────────────────────────────────────────────────────

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Do'kon FK → store",
    )

    number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Shartnoma raqami (store ichida unikal)",
    )

    file_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="PDF fayl URL (MinIO/S3; NULL = hali yuklanmagan)",
    )

    signed_at: Mapped[datetime | None] = mapped_column(
        __import__("sqlalchemy").DateTime(timezone=True),
        nullable=True,
        comment="Imzolangan vaqt (UTC; NULL = imzolanmagan)",
    )

    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Amal qilish boshlanishi (sana)",
    )

    valid_to: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Amal qilish tugashi (sana) — status hisoblash uchun",
    )

    contract_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Shartnoma turi: trade | employment | service | other",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Filial ID (ixtiyoriy)",
    )

    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Idempotentlik UUID (partial unique IS NOT NULL)",
    )

    # ─── Status hisoblash ────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        """
        Status — DERIVED from valid_to.

        expired  : valid_to < bugun
        expiring : valid_to - bugun <= CONTRACT_EXPIRING_DAYS
        active   : boshqa
        """
        today = datetime.now(timezone.utc).date()
        if self.valid_to < today:
            return "expired"
        delta = (self.valid_to - today).days
        if delta <= CONTRACT_EXPIRING_DAYS:
            return "expiring"
        return "active"

    def __repr__(self) -> str:
        return (
            f"<Contract id={self.id} number={self.number!r} "
            f"store={self.store_id} status={self.status}>"
        )
