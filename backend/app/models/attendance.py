"""
Davomat modeli — attendance jadvali.

T16: Davomat (Face ID lokal biometrik + GPS).

XAVFSIZLIK:
  - biometric_verified: qurilmadan kelgan flag (bool) — yuz HECH QACHON serverga bormaydi.
  - GPS (check_in/check_out): server vaqti bilan qayd etiladi (klient soatiga ishonmaslik).
  - check_in_at / check_out_at: SERVER vaqti — klient bergan vaqtga ishonilmaydi.
  - source: 'device_faceid' | 'device_fingerprint' — qurilma biometriya turi.

UNIQUE constraint:
  Bir foydalanuvchi bir kun uchun faqat BITTA ochiq davomat bo'lishi mumkin.
  Partial unique: (user_id, work_date) WHERE deleted_at IS NULL.
  PostgreSQL: CREATE UNIQUE INDEX partial (WHERE deleted_at IS NULL).
  SQLite (test): ORM darajasida servis tekshiradi (SQLite partial unique to'liq qo'llab-quvvatlamaydi).

client_uuid idempotentlik:
  Partial unique: client_uuid IS NOT NULL da unique.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise


class Attendance(TimestampMixin, Base):
    """
    Davomat yozuvi.

    Har bir davomat:
      - check_in_at, check_in_gps_lat/lng  — kirish vaqti va joyi (server vaqti)
      - check_out_at, check_out_gps_lat/lng — chiqish vaqti va joyi (server vaqti, ixtiyoriy)
      - biometric_verified                  — qurilma biometriyasi bayrog'i
      - source                              — biometriya turi (device_faceid/device_fingerprint)
      - client_uuid                         — idempotentlik UUID (ixtiyoriy)

    Bir foydalanuvchi + bir kun = bitta ochiq davomat.
    """

    __tablename__ = "attendance"

    # user_id FK → app_user
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        comment="Foydalanuvchi FK → app_user",
    )

    # Ish kuni (Date) — server tomonida aniqlanadi
    work_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Ish kuni (UTC server vaqtidan olinadi)",
    )

    # Check-in vaqti va GPS (SERVER vaqti — klient vaqtiga ishonmaslik)
    check_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Kirish vaqti — SERVER vaqti (klient vaqtiga ISHONMASLIK)",
    )

    check_in_gps_lat: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=False,
        comment="Kirish GPS kenglik (±90.0000000)",
    )

    check_in_gps_lng: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=False,
        comment="Kirish GPS uzunlik (±180.0000000)",
    )

    # Check-out vaqti va GPS (ixtiyoriy — ochiq davomat bo'lishi mumkin)
    check_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Chiqish vaqti — SERVER vaqti (NULL = hali chiqmagan)",
    )

    check_out_gps_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=True,
        comment="Chiqish GPS kenglik (NULL = hali chiqmagan)",
    )

    check_out_gps_lng: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=True,
        comment="Chiqish GPS uzunlik (NULL = hali chiqmagan)",
    )

    # Biometriya bayrog'i — qurilma biometriyasi (YUZNI emas, FAQAT BAYROQ)
    biometric_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "Qurilma biometriyasi muvaffaqiyatli o'tganmi (lokal verifikatsiya bayrog'i). "
            "YUZNI serverga HECH QACHON YUBORMA — faqat bu boolean flag."
        ),
    )

    # Biometriya turi — qurilma tomonida qo'llanilgan usul
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Biometriya turi: 'device_faceid' | 'device_fingerprint'",
    )

    # Idempotentlik UUID — klientdan keladi (ixtiyoriy)
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        unique=False,  # Partial unique — migratsiyada belgilanadi
        index=True,
        comment="Klient idempotentlik UUID (ixtiyoriy; partial unique WHERE IS NOT NULL)",
    )

    # ─── MT1: enterprise_id ──────────────────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Korxona FK → enterprise (MT1)",
    )

    def __repr__(self) -> str:
        return (
            f"<Attendance id={self.id} user={self.user_id} "
            f"date={self.work_date} checked_out={self.check_out_at is not None}>"
        )
