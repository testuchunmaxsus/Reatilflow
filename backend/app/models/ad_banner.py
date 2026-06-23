"""
Reklama banner modeli — MP5.

Jadval:
  ad_banner — marketplace top qismida ko'rsatiladigan reklama bannerlari

XAVFSIZLIK va ARXITEKTURA:
  - enterprise_id NOT NULL + FK → korxona o'z reklamasini boshqaradi.
  - Korxona faqat O'Z bannerini yarata/tahrir qila oladi (enterprise-scoped CRUD).
  - GET /marketplace/banners — cross-tenant (barcha korxonalar aktiv bannerlari).
  - Faqat aktiv + valid_from<=bugun<=valid_to bannerlar ko'rinadi (izolyatsiya).
  - Superadmin har qanday bannerni moderatsiya qila oladi.

Indekslar:
  - enterprise_id: korxona bannerlarini tez qidirish.
  - (is_active, priority): aktiv bannerlarni priority bo'yicha saralash.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.uuid7 import uuid7
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.enterprise import Enterprise


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AdBanner(Base):
    """
    Marketplace reklama banneri.

    Korxona o'z reklamasini yaratadi → marketplace top'da ko'rsatiladi.
    cross-tenant ko'rish: aktiv + valid sanali barcha korxona bannerlari.
    CRUD: faqat o'z korxonasi (enterprise-scoped, IDOR-safe).
    Superadmin: har qanday bannerni faollashtirish/o'chirish (moderatsiya).

    Banner rasm: MinIO orqali yuklanadi (image_url).
    Banner havolasi: target_url yoki target_product_id (mahsulotga yo'naltirish).
    """

    __tablename__ = "ad_banner"
    __table_args__ = (
        Index("ix_ad_banner_enterprise_id", "enterprise_id"),
        Index("ix_ad_banner_active_priority", "is_active", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID v7 — vaqt-tartibli birlamchi kalit",
    )

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Reklama beruvchi korxona FK → enterprise (NOT NULL, tenant-scoped CRUD)",
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Banner sarlavhasi",
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Banner rasmi URL (MinIO, POST /marketplace/banners/{id}/image orqali yuklanadi)",
    )

    target_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Bannerga bosilganda yo'naltiriladigan URL (tashqi havola, ixtiyoriy)",
    )

    target_product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product.id", ondelete="SET NULL"),
        nullable=True,
        comment="Bannerga bosilganda yo'naltiriladigan mahsulot FK → product (ixtiyoriy)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Aktiv holat (False = deaktiv, ko'rinmaydi)",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Ko'rsatish ustuvorligi — yuqori son birinchi ko'rsatiladi",
    )

    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Banner ko'rsatish boshlanish sanasi (YYYY-MM-DD)",
    )

    valid_to: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Banner ko'rsatish tugash sanasi (YYYY-MM-DD)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
        comment="Yaratilgan vaqt (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
        nullable=False,
        comment="Oxirgi yangilangan vaqt (UTC)",
    )

    # ─── Relationships ────────────────────────────────────────────────────────

    enterprise: Mapped["Enterprise"] = relationship(
        "Enterprise",
        foreign_keys=[enterprise_id],
        lazy="select",
    )

    target_product: Mapped["Product | None"] = relationship(
        "Product",
        foreign_keys=[target_product_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<AdBanner id={self.id} enterprise={self.enterprise_id} "
            f"title={self.title!r} active={self.is_active} priority={self.priority}>"
        )
