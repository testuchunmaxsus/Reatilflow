"""
Murojaat (Ticket) modeli — ticket va ticket_message jadvallari.

Ticket — do'kon yoki xodim murojaati (taklif / e'tiroz).
TicketMessage — murojaatga qo'shilgan xabar (matn + ixtiyoriy fayl URL).

Murojaat turi:
  taklif  — taklif/tavsiya
  etiroz  — e'tiroz/shikoyat

Holat mashinasi:
  new → in_progress → resolved → closed
  resolved → in_progress  (qayta ochish mumkin — agent/do'kon yangi ma'lumot bersa)

store_id    nullable: NULL = xodim murojaati, qiymat = do'kon murojaati
author_id   murojaatni yaratgan foydalanuvchi (FK → app_user)
assigned_to murojaatni ko'ruvchi (FK → app_user, nullable)
client_uuid idempotentlik UUID (partial unique IS NOT NULL)
version     optimistik lock
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ─── Holat o'tish matritsasi ──────────────────────────────────────────────────

# To'g'ri holatlar to'plami
TICKET_STATUSES: frozenset[str] = frozenset({"new", "in_progress", "resolved", "closed"})

# Maqbul o'tishlar: {from_status: {to_status, ...}}
TICKET_TRANSITIONS: dict[str, frozenset[str]] = {
    "new":         frozenset({"in_progress"}),
    "in_progress": frozenset({"resolved", "closed"}),
    # resolved → in_progress: agent/do'kon yangi ma'lumot bersa qayta ochish mumkin.
    # resolved → closed: admin/buxgalter yakunlaydi.
    "resolved":    frozenset({"in_progress", "closed"}),
    # closed — terminal holat, hech qayerga o'tmaydi.
    "closed":      frozenset(),
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Holat o'tishi to'g'riligini tekshiradi."""
    return to_status in TICKET_TRANSITIONS.get(from_status, frozenset())


# ─── Ticket modeli ────────────────────────────────────────────────────────────


class Ticket(TimestampMixin, Base):
    """
    Murojaat (taklif / e'tiroz).

    store_id NULL    → xodim murojaati (agent, courier, accountant va h.k.)
    store_id NOT NULL → do'kon murojaati

    Xavfsizlik:
      - client_uuid partial unique (IS NOT NULL) — idempotentlik.
      - version optimistik lock.
      - assigned_to nullable — admin/buxgalter tekshiruvchi.
    """

    __tablename__ = "ticket"

    # ─── Asosiy maydonlar ──────────────────────────────────────────────────────

    store_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("store.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Do'kon FK → store (NULL = xodim murojaati)",
    )

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Murojaatni yaratgan foydalanuvchi FK → app_user",
    )

    ticket_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Murojaat turi: taklif | etiroz",
    )

    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Murojaat mavzusi",
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Murojaat matni",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="new",
        index=True,
        comment="Holat: new | in_progress | resolved | closed",
    )

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Mas'ul xodim FK → app_user (nullable)",
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

    # ─── Relationships ────────────────────────────────────────────────────────

    messages: Mapped[list["TicketMessage"]] = relationship(
        "TicketMessage",
        back_populates="ticket",
        lazy="select",
        order_by="TicketMessage.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<Ticket id={self.id} type={self.ticket_type!r} "
            f"status={self.status!r} store={self.store_id}>"
        )


# ─── TicketMessage modeli ─────────────────────────────────────────────────────


class TicketMessage(Base):
    """
    Murojaatga qo'shilgan xabar.

    Ixtiyoriy fayl URL (attachment_url) — storage'dan olingan URL.
    TimestampMixin emas: murojaat xabarlari o'zgartirilmaydi (append-only).
    """

    __tablename__ = "ticket_message"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: uuid.uuid4(),
        comment="UUID v7 — birlamchi kalit",
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Murojaat FK → ticket",
    )

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Xabar muallifi FK → app_user",
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Xabar matni",
    )

    attachment_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Fayl URL (MinIO/S3; NULL = fayl yo'q)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    ticket: Mapped["Ticket"] = relationship(
        "Ticket",
        back_populates="messages",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<TicketMessage id={self.id} ticket={self.ticket_id}>"
