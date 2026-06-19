"""
Do'kon (mijoz) modellari — store va agent_store jadvallari.

store — chakana do'kon / distribyutsiya mijozi.
agent_store — agent↔do'kon ko'p-ko'p bog'liq jadvali.

T5 o'zgarishlari:
  - inn, inps, owner_name, phone — EncryptedString (AES-GCM ilova-darajali shifrlash)
  - inn_bi, phone_bi — HMAC blind-index ustunlari (aniq-moslik qidiruv)
  - user_id FK — do'kon egasi/foydalanuvchisi (store roli scope uchun)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import AppUser


class Store(TimestampMixin, Base):
    """
    Chakana do'kon / distribyutsiya mijozi.

    Xavfsizlik:
      - inn, inps, owner_name, phone — EncryptedString (AES-GCM) orqali shifrlangan.
        DB da LargeBinary (bytea/BLOB) sifatida saqlanadi; Python'da to'g'ri str.
      - inn_bi, phone_bi — HMAC-SHA256 blind-index: aniq-moslik qidiruv uchun.
        Ochiq-matn LIKE qidiruv TAQIQLANGAN — faqat blind_index() orqali.
      - credit_limit — moliyaviy maydon; faqat primary DB dan o'qish.
      - user_id — do'kon egasi FK (store roli scope uchun, T5).
    """

    __tablename__ = "store"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Do'kon nomi",
    )

    # ─── PII maydonlar (shifrlangan) ─────────────────────────────────────────

    inn: Mapped[str | None] = mapped_column(
        EncryptedString(),
        nullable=True,
        comment="Soliq identifikatsiya raqami (INN) — AES-GCM shifrlangan PII",
    )

    inps: Mapped[str | None] = mapped_column(
        EncryptedString(),
        nullable=True,
        comment="INPS (shaxsiy soliq) — AES-GCM shifrlangan PII",
    )

    owner_name: Mapped[str | None] = mapped_column(
        EncryptedString(),
        nullable=True,
        comment="Egasi ismi — AES-GCM shifrlangan PII",
    )

    phone: Mapped[str | None] = mapped_column(
        EncryptedString(),
        nullable=True,
        comment="Telefon — AES-GCM shifrlangan PII",
    )

    # ─── Blind-index ustunlari (aniq-moslik qidiruv) ─────────────────────────

    inn_bi: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="INN HMAC blind-index — inn bo'yicha aniq-moslik qidiruv",
    )

    phone_bi: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Phone HMAC blind-index — phone bo'yicha aniq-moslik qidiruv",
    )

    # ─── Koordinatalar va manzil ──────────────────────────────────────────────

    gps_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        comment="Kenglik koordinatasi",
    )

    gps_lng: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        comment="Uzunlik koordinatasi",
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Manzil (matnli)",
    )

    # ─── FK maydonlar ─────────────────────────────────────────────────────────

    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_segment.id", ondelete="SET NULL"),
        nullable=True,
        comment="Narx segmenti (FK → price_segment)",
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Asosiy agent (FK → app_user)",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Filial ID",
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Do'kon egasi/foydalanuvchisi (FK → app_user) — store roli scope (T5)",
    )

    # ─── Moliyaviy maydon ─────────────────────────────────────────────────────

    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Kredit limiti (moliyaviy — faqat primary dan o'qing)",
    )

    # ─── Relationships ───────────────────────────────────────────────────────

    agent_stores: Mapped[list["AgentStore"]] = relationship(
        "AgentStore",
        back_populates="store",
        lazy="selectin",  # N+1 oldini olish: ro'yxat so'rovlarida IN-subquery bilan yuklaydi
    )

    owner: Mapped["AppUser | None"] = relationship(
        "AppUser",
        foreign_keys="[Store.user_id]",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Store id={self.id} name={self.name!r}>"


class AgentStore(Base):
    """
    Agent ↔ Do'kon ko'p-ko'p bog'liq jadval.

    Qo'shimcha ustunlar yo'q (TimestampMixin emas — minimal join table).
    Qator-darajali himoya: agent faqat o'z do'konlarini ko'radi (T2/T5 da).
    """

    __tablename__ = "agent_store"
    __table_args__ = (
        UniqueConstraint("agent_id", "store_id", name="uq_agent_store"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Agent FK → app_user",
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Do'kon FK → store",
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Biriktirilgan vaqt",
    )

    # ─── Relationships ───────────────────────────────────────────────────────

    agent: Mapped["AppUser"] = relationship(
        "AppUser",
        foreign_keys="[AgentStore.agent_id]",
        back_populates="agent_stores",
        lazy="select",
    )

    store: Mapped["Store"] = relationship(
        "Store",
        back_populates="agent_stores",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<AgentStore agent={self.agent_id} store={self.store_id}>"
