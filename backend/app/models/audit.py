"""
Audit log modeli — audit_log jadvali.

APPEND-ONLY: bu jadvalga faqat INSERT qilinadi.
UPDATE va DELETE huquqlari dastur tomonidan berilmaydi.

Har bir mutatsiya (auth, katalog, do'kon, RBAC) shu yerda qayd etiladi.
Moliyaviy va RBAC o'zgarishlari majburiy audit.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise


class AuditLog(Base):
    """
    Audit yozuvi.

    Maydonlar:
      actor_id     — kim qildi (NULL = tizim)
      action       — nima qildi (create, update, delete, login, logout, ...)
      entity_type  — qaysi modelga (app_user, product, store, ...)
      entity_id    — qaysi yozuvga (UUID string)
      before_json  — o'zgarishdan oldingi holat (JSON, PII maskalangan)
      after_json   — o'zgarishdan keyingi holat (JSON, PII maskalangan)
      ip           — IP manzil
      at           — qachon (UTC)

    PII eslatma: before_json/after_json da shaxsiy ma'lumotlar maskalanishi shart.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID birlamchi kalit",
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Kim amalga oshirdi (NULL = tizim/cron)",
    )

    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Harakat: create | update | delete | login | logout | approve | ...",
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Jadval/model nomi (app_user, product, store, ...)",
    )

    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Yozuv identifikatori (UUID yoki boshqa)",
    )

    before_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Oldingi holat (JSON) — PII maskalangan",
    )

    after_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Keyingi holat (JSON) — PII maskalangan",
    )

    ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4 yoki IPv6 manzil",
    )

    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Yozuv vaqti (UTC)",
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
            f"<AuditLog actor={self.actor_id} action={self.action!r} "
            f"entity={self.entity_type}:{self.entity_id}>"
        )
