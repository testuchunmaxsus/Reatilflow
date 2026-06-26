"""
Filial (Branch) modeli — branch jadvali.

branch — korxona ichidagi filial/bo'linma.
app_user.branch_id va store.branch_id shu jadvalga FK bo'lib ulanadi.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.enterprise import Enterprise


class Branch(TimestampMixin, Base):
    """
    Korxona filiallari.

    Har filial bitta korxonaga (enterprise) tegishli.
    app_user.branch_id va store.branch_id — bu jadvaldagi id ga FK.

    Maydonlar:
      name            — filial nomi (majburiy)
      address         — manzil (ixtiyoriy)
      phone           — telefon (ixtiyoriy)
      is_active       — faol/nofaol (default: True)
      enterprise_id   — korxona FK (NOT NULL, indexed)
    """

    __tablename__ = "branch"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Filial nomi",
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Filial manzili",
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Filial telefon raqami",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Filial faolligi (False = nofaol)",
    )

    # ─── MT: enterprise_id (NOT NULL) ───────────────────────────────────────
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Korxona FK → enterprise (NOT NULL)",
    )

    # ─── Relationships ───────────────────────────────────────────────────────

    enterprise: Mapped["Enterprise"] = relationship(
        "Enterprise",
        foreign_keys="[Branch.enterprise_id]",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Branch id={self.id} name={self.name!r} enterprise={self.enterprise_id}>"
