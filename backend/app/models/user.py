"""
Foydalanuvchi modeli — app_user jadvali.

Rollar: administrator, agent, courier, accountant, store
5 rol × 11 modul RBAC matritsasi (T2 da implement qilinadi).

T6 o'zgarishlari:
  - phone — EncryptedString (AES-GCM ilova-darajali shifrlash, PII)
  - phone_bi — HMAC blind-index (UNIQUE; login identifikatori qidiruvi uchun)
  - full_name — EncryptedString (PII shifrlash)
  - SQLAlchemy event listener: phone o'rnatilganda phone_bi avtomatik hisoblanadi.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, event
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString, blind_index
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.store import AgentStore
    from app.models.enterprise import Enterprise


class AppUser(TimestampMixin, Base):
    """
    Tizim foydalanuvchisi.

    Xavfsizlik eslatmalari:
      - password_hash: bcrypt (passlib) bilan hash; tekis parol hech qachon saqlanmaydi
      - biometric_enrolled: faqat flag — biometrik ma'lumot qurilmada saqlanadi
      - device_id: refresh token rotatsiyasida qurilma tekshiruvi uchun
      - phone: PII — EncryptedString (AES-GCM) bilan shifrlangan; login uchun
               phone_bi HMAC blind-index orqali qidiruv amalga oshiriladi
      - full_name: PII — EncryptedString (AES-GCM) bilan shifrlangan
      - phone_bi: UNIQUE blind-index — bir xil telefon raqami ikki marta ro'yxatga
                  olinishini oldini oladi va blind-index orqali tez qidiruv ta'minlaydi
    """

    __tablename__ = "app_user"

    full_name: Mapped[str] = mapped_column(
        EncryptedString(),
        nullable=False,
        comment="To'liq ismi (UZ/RU) — AES-GCM shifrlangan PII",
    )

    phone: Mapped[str] = mapped_column(
        EncryptedString(),
        nullable=False,
        comment="Telefon raqami — login uchun, AES-GCM shifrlangan PII; qidiruv phone_bi orqali",
    )

    phone_bi: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="Telefon HMAC blind-index (UNIQUE) — phone bo'yicha aniq-moslik qidiruv",
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="administrator | agent | courier | accountant | store",
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Filial ID (NULL = barcha filiallar, administrator uchun)",
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="bcrypt hash — tekis parol bu yerda saqlanmaydi",
    )

    biometric_enrolled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Qurilmada biometrik ro'yxatga olinganmi (lokal flag)",
    )

    device_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="So'nggi kirgan qurilma identifikatori (refresh token uchun)",
    )

    locale: Mapped[str] = mapped_column(
        String(5),
        default="uz",
        nullable=False,
        comment="Foydalanuvchi tili: uz | ru",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Hisobni bloklash uchun (False = bloklangan)",
    )

    # ─── MT1: enterprise_id (NULLABLE — superadmin uchun NULL) ──────────────────
    # app_user boshqa jadvallardan farqli: superadmin enterprise_id=NULL bo'lishi mumkin.
    # Mavjud foydalanuvchilar migratsiya (0020) da default korxonaga backfill qilinadi.

    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enterprise.id", ondelete="RESTRICT"),
        nullable=True,  # superadmin uchun NULL ruxsat
        index=True,
        comment=(
            "Korxona FK → enterprise. "
            "NULL = superadmin (korxonaga tegishli emas). "
            "MT1: mavjud foydalanuvchilar default korxonaga backfill qilinadi."
        ),
    )

    # ─── Relationships ───────────────────────────────────────
    agent_stores: Mapped[list["AgentStore"]] = relationship(
        "AgentStore",
        back_populates="agent",
        lazy="select",
    )

    enterprise: Mapped["Enterprise | None"] = relationship(
        "Enterprise",
        foreign_keys="[AppUser.enterprise_id]",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<AppUser id={self.id} role={self.role} enterprise={self.enterprise_id}>"


# ─── SQLAlchemy event listener: phone → phone_bi avtomatik ────────────────────
# Sababi: mavjud fixturelar AppUser(phone=...) orqali yaratiladi.
# phone set qilinganida phone_bi avtomatik hisoblanishi uchun event listener
# ishlatiladi — fixturelarni o'zgartirmasdan ishlash ta'minlanadi.

@event.listens_for(AppUser, "before_insert")
def _set_phone_bi_before_insert(mapper, connection, target: AppUser) -> None:  # type: ignore[type-arg]
    """
    INSERT oldidan phone_bi ni avtomatik to'ldiradi.

    phone o'rnatilgan, lekin phone_bi o'rnatilmagan bo'lsa,
    blind_index(phone) hisoblanib phone_bi ga yoziladi.
    """
    if target.phone is not None and target.phone_bi is None:
        target.phone_bi = blind_index(target.phone)


@event.listens_for(AppUser, "before_update")
def _set_phone_bi_before_update(mapper, connection, target: AppUser) -> None:  # type: ignore[type-arg]
    """
    UPDATE oldidan phone_bi ni avtomatik yangilaydi.

    phone o'zgargan bo'lsa (history da pending) phone_bi qayta hisoblanadi.

    Defensive: history.added[0] ba'zan bytes bo'lishi mumkin
    (EncryptedString TypeDecorator process_bind_param dan oldin).
    Bunday holda decrypt_pii() orqali ochiq-matnga o'girib, keyin blind_index hisoblanadi.
    """
    from sqlalchemy.orm import attributes as _attrs

    history = _attrs.get_history(target, "phone")
    if history.added:
        # phone o'zgargan — blind-index yangilansin
        new_phone = history.added[0]
        if new_phone is not None:
            # Defensive: TypeDecorator ba'zan bytes qaytarishi mumkin
            if isinstance(new_phone, bytes):
                from app.core.crypto import decrypt_pii
                new_phone = decrypt_pii(new_phone)
            if new_phone is not None:
                target.phone_bi = blind_index(new_phone)
            else:
                target.phone_bi = None
        else:
            target.phone_bi = None
