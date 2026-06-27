"""
Korxona (Enterprise) modeli — multi-tenant SaaS poydevori.

ADR-002 §2.2 bo'yicha:
  id              — UUID v7 PK
  name            — korxona nomi
  inn             — soliq raqami (nullable)
  status          — active | suspended (default: active)
  enabled_modules — yoqilgan modul kalitlari (JSON array)
  created_at, updated_at, deleted_at — TimestampMixin

enabled_modules default: barcha modul kalitlari.
Soft-delete: deleted_at IS NOT NULL → o'chirilgan.

MT1 — Foundation.
"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# ─── Barcha modul kalitlari (ADR-002 §2.2) ───────────────────────────────────

ALL_MODULE_KEYS: list[str] = [
    "catalog",
    "customers",
    "orders",
    "stock",
    "finance",
    "delivery",
    "attendance",
    "gps",
    "contracts",
    "tickets",
    "promo",
    "stats",
    "push",
    "pos",
    "marketplace",  # MP1: B2B marketplace katalog
    "analytics",    # Faza 4: AI Tahlil (korxona-egasi paneli)
    "import",       # AI Import: Excel/Nakladnoy import
    "assistant",    # AI Assistant: o'zbekcha yordamchi chat
]

# Default korxona UUID (jonli ma'lumot backfill uchun — migratsiya 0020)
DEFAULT_ENTERPRISE_UUID: str = "00000000-0000-7000-8000-000000000001"


class Enterprise(TimestampMixin, Base):
    """
    Korxona (tenant) — multi-tenant SaaS ning asosiy birimi.

    Har korxona o'z ma'lumotlarini izolyatsiya qilingan holda saqlaydi.
    superadmin enterprise_id=NULL bilan ishlaydi (korxonasiz).

    Maydonlar:
      name            — korxona nomi (majburiy)
      inn             — soliq raqami (nullable, ixtiyoriy)
      status          — active | suspended
      enabled_modules — yoqilgan modul kalitlari JSON array
                        (default: ALL_MODULE_KEYS — hammasi yoqilgan)
      deleted_at      — soft delete (TimestampMixin dan — NULL = aktiv)

    Ruxsatlar:
      superadmin → korxona CRUD, modul toggle, suspend/activate
      administrator → faqat o'z korxonasini ko'radi
    """

    __tablename__ = "enterprise"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Korxona nomi",
    )

    inn: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Soliq identifikatsiya raqami (INN) — ixtiyoriy",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="Holat: active | suspended",
    )

    enabled_modules: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: list(ALL_MODULE_KEYS),
        comment=(
            "Yoqilgan modul kalitlari (JSON array). "
            "Default: barcha modullar. "
            "Misol: ['catalog','orders','stock']"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Enterprise id={self.id} name={self.name!r} status={self.status!r}>"
        )
