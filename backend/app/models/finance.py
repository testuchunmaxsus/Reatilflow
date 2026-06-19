"""
Buxgalteriya (finance) modellari — APPEND-ONLY event-sourced ledger.

Jadvallar:
  ledger_entry    — har bir moliyaviy yozuvni qayd etadi (faqat INSERT).
  account_balance — ledger yozuvlaridan derivatsiyalangan joriy balans (kesh).

Muhim:
  - ledger_entry APPEND-ONLY: UPDATE/DELETE TAQIQLANGAN (ADR §3.4, §3.5).
    Balans faqat debit/credit yig'indisidan hisoblanadi.
  - account_balance — performance uchun kesh; versiya orqali optimistik lock.
  - amount — Decimal (moliyaviy aniqlik talabi: float EMAS).
  - Moliyaviy balans o'qish FAQAT primary DB dan (replica kechikishini oldini olish).
    Bu ADR §3.4 talabi — barcha get_balance() primary session ishlatishi shart.

Balans ishorasi kelishuvi:
  - debit  → mijozning qarzi oshadi (balance += amount, qarz ko'paydi)
  - credit → mijozning qarzi kamayadi yoki haq olinadi (balance -= amount)
  balance > 0 → mijoz qarz bergan (haq talab qilsa olishi mumkin)
  balance < 0 → mijoz qarz (to'lashi kerak)
  (Bu umumiy emas — loyiha kelishuvi bo'yicha teskari ham bo'lishi mumkin,
   lekin bu implementatsiyada balance kichikroq = yaxshiroq mazmunidir.)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class LedgerEntry(Base):
    """
    Buxgalteriya yozuvi — APPEND-ONLY.

    Bu jadvalga faqat INSERT qilinadi; UPDATE/DELETE TAQIQLANGAN.
    Har bir debit/credit operatsiya alohida yozuv sifatida saqlanadi.

    type qiymatlari:
      debit  — mijoz qarzi oshadi (tovar/xizmat yuborildi)
      credit — to'lov qabul qilindi, qarz kamayadi

    client_uuid — idempotentlik kaliti (UNIQUE partial index).
    """

    __tablename__ = "ledger_entry"
    __table_args__ = (
        # Statistika (T22 SQL agg): finance_stats store_id IN (...) + entry_date range
        # + GROUP BY store_id, type. Kompozit indeks ko'p-filial masshtabida scan'ni kamaytiradi.
        Index("ix_ledger_entry_store_date", "store_id", "entry_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Do'kon FK → store",
    )

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Yozuv turi: debit | credit",
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        comment="Miqdor (Decimal — moliyaviy aniqlik; musbat qiymat)",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="UZS",
        comment="Valyuta kodi (ISO 4217)",
    )

    ref_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Havola turi: order | payment | adjustment | ... (ixtiyoriy)",
    )

    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Havola ID (ixtiyoriy)",
    )

    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yozuv sanasi (hujjat vaqti, UTC)",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kim yaratdi (FK → app_user)",
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
            f"<LedgerEntry id={self.id} store={self.store_id} "
            f"type={self.type!r} amount={self.amount} {self.currency}>"
        )


class AccountBalance(Base):
    """
    Do'kon buxgalteriya balansi — ledger yozuvlaridan derivatsiyalangan kesh.

    Bu jadval HISOBLANGAN holat — ledger_entry yig'indisi.
    Optimistik lock: version majburiy.

    MUHIM (ADR §3.4):
      Ushbu jadvalni O'QISH FAQAT primary DB sessiyasida bajarilishi shart.
      Replica DB kechikishi tufayli moliyaviy qaror noto'g'ri bo'lib qolishi mumkin.
      get_balance() va record_entry() har doim primary sessiya ishlatadi.

    Balans ishorasi:
      balance > 0 → mijoz qarz (to'lanmagan debit)
      balance < 0 → ortiqcha kredit (qaytarilishi kerak)
      balance = 0 → hisob-kitob tamom
    """

    __tablename__ = "account_balance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — birlamchi kalit",
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        comment="Do'kon FK → store (UNIQUE: har do'kon uchun bitta balans yozuvi)",
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0"),
        comment="Joriy balans (Decimal): >0 = qarz, <0 = ortiqcha kredit",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="UZS",
        comment="Valyuta kodi (ISO 4217)",
    )

    last_recalc_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Oxirgi qayta hisoblangan vaqt (UTC)",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        comment="Optimistik lock versiyasi",
    )

    def __repr__(self) -> str:
        return (
            f"<AccountBalance store={self.store_id} "
            f"balance={self.balance} {self.currency}>"
        )
