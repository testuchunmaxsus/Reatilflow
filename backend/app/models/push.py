"""
Push bildirishnoma log modeli — T19 Push Worker.

push_log jadvali — har bir foydalanuvchiga har outbox hodisasi uchun
idempotent push yozuvi.

Idempotentlik invarianti:
  unique (outbox_event_id, user_id) — bir hodisa bir foydalanuvchiga faqat bir marta.
  Push consumer outbox.published_at ga TEGMAYDI — sync seq bilan to'qnashmaydi.

Kanal: fcm | apns
Status: pending | sent | failed

Retry: attempts ustuni — 3 urinishgacha (PUSH_MAX_RETRIES config).
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Ruxsat etilgan kanallar
PUSH_CHANNELS = frozenset({"fcm", "apns"})

# Ruxsat etilgan statuslar
PUSH_STATUSES = frozenset({"pending", "sent", "failed"})


class PushLog(Base):
    """
    Push bildirishnoma log yozuvi.

    Maydonlar:
      id               — UUID v7 PK
      outbox_event_id  — OutboxEvent FK (UUID) — qaysi outbox hodisasi
      user_id          — AppUser FK — kimga yuborildi
      device_id        — qurilma token/ID (FCM registration token yoki APNs device token)
      channel          — fcm | apns
      title            — push sarlavhasi
      body             — push matni
      status           — pending | sent | failed
      attempts         — urinishlar soni (retry uchun)
      last_error       — oxirgi xato matni (failed holat uchun)
      created_at       — yaratilgan vaqt
      sent_at          — muvaffaqiyatli yuborilgan vaqt (NULL = yuborilmagan)

    Idempotentlik:
      unique (outbox_event_id, user_id) — bir hodisa + bir foydalanuvchi = bir push.
      Bu push consumerini outbox.published_at ga tegmasdan ishlatishga imkon beradi.

    DIQQAT: outbox.published_at ni O'ZGARTIRMA — sync seq kursori unga tayanadi.
    Push o'z holatini push_log.status orqali boshqaradi.
    """

    __tablename__ = "push_log"

    __table_args__ = (
        # Idempotentlik: bir hodisa — bir foydalanuvchiga bir marta push
        UniqueConstraint(
            "outbox_event_id",
            "user_id",
            name="uq_push_log_event_user",
        ),
        # Tez qidiruv uchun indekslar
        Index("ix_push_log_outbox_event_id", "outbox_event_id"),
        Index("ix_push_log_user_id", "user_id"),
        Index("ix_push_log_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    outbox_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("outbox_event.id", ondelete="CASCADE"),
        nullable=False,
        comment="OutboxEvent FK — qaysi hodisa uchun push",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        comment="AppUser FK — kimga push yuboriladi",
    )

    device_id: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="FCM registration token yoki APNs device token",
    )

    channel: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="fcm",
        comment="Push kanali: fcm | apns",
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Push bildirishnoma sarlavhasi",
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Push bildirishnoma matni",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Holat: pending | sent | failed",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Yuborish urinishlari soni",
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Oxirgi xato xabari (failed holat uchun)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Muvaffaqiyatli yuborilgan vaqt (UTC) — NULL = yuborilmagan",
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
            f"<PushLog id={self.id} event={self.outbox_event_id} "
            f"user={self.user_id} status={self.status!r} attempts={self.attempts}>"
        )
