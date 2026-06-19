"""
Promo (Aksiya) sxemalari — T25.

Sxemalar:
  PromoCreate     — yangi aksiya yaratish (admin)
  PromoUpdate     — aksiyani yangilash (admin, PATCH — qisman)
  PromoOut        — javob sxemasi (lokalizatsiyalangan nom)
  PaginatedPromos — paginated ro'yxat

rule_json qoidalari:
  {"discount_percent": 10}                    — 10% chegirma
  {"discount_amount": 5000}                   — 5000 so'm chegirma (fixed)
  {"discount_percent": 15, "min_qty": 3}      — min 3 dona uchun 15%
  {"discount_amount": 2000, "min_qty": 2}     — min 2 dona uchun 2000 so'm

SERVER-AVTORITAR: klient discount kiritmaydi — promo server tomonda hisoblanadi.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.core.i18n import current_locale


# ─── Yaratish sxemasi ─────────────────────────────────────────────────────────


class PromoCreate(BaseModel):
    """Yangi aksiya yaratish sxemasi (admin uchun)."""

    name_uz: str = Field(..., min_length=1, max_length=255, description="Aksiya nomi (UZ)")
    name_ru: str = Field(..., min_length=1, max_length=255, description="Aksiya nomi (RU)")
    promo_type: str = Field(
        "discount",
        description="Aksiya turi: discount | bonus | gift",
    )
    rule_json: dict = Field(
        ...,
        description=(
            "Chegirma qoidalari. "
            "Misol: {\"discount_percent\": 10} yoki {\"discount_amount\": 5000, \"min_qty\": 2}"
        ),
    )
    banner_url: str | None = Field(None, description="Banner URL (ixtiyoriy; POST /promos/{id}/banner orqali yuklanadi)")
    valid_from: date = Field(..., description="Aksiya boshlanish sanasi (YYYY-MM-DD)")
    valid_to: date = Field(..., description="Aksiya tugash sanasi (YYYY-MM-DD)")
    target_segment_id: uuid.UUID | None = Field(None, description="Narx segmenti (NULL = barchasi)")
    target_product_id: uuid.UUID | None = Field(None, description="Mahsulot (NULL = barchasi)")
    is_active: bool = Field(True, description="Aktiv holat")
    branch_id: uuid.UUID | None = Field(None, description="Filial ID (NULL = global)")
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    @model_validator(mode="after")
    def check_dates(self) -> "PromoCreate":
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to valid_from dan oldin bo'lishi mumkin emas")
        return self

    @model_validator(mode="after")
    def check_rule_json(self) -> "PromoCreate":
        _validate_rule_json(self.rule_json)
        return self

    model_config = {"from_attributes": True}


# ─── Yangilash sxemasi ────────────────────────────────────────────────────────


class PromoUpdate(BaseModel):
    """Aksiyani qisman yangilash (PATCH). version optimistik lock uchun majburiy."""

    version: int = Field(..., ge=1, description="Joriy versiya (optimistik lock)")
    name_uz: str | None = Field(None, min_length=1, max_length=255)
    name_ru: str | None = Field(None, min_length=1, max_length=255)
    promo_type: str | None = Field(None)
    rule_json: dict | None = Field(None)
    valid_from: date | None = Field(None)
    valid_to: date | None = Field(None)
    target_segment_id: uuid.UUID | None = Field(None)
    target_product_id: uuid.UUID | None = Field(None)
    is_active: bool | None = Field(None)
    branch_id: uuid.UUID | None = Field(None)

    @model_validator(mode="after")
    def check_dates(self) -> "PromoUpdate":
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_to < self.valid_from:
                raise ValueError("valid_to valid_from dan oldin bo'lishi mumkin emas")
        return self

    @model_validator(mode="after")
    def check_rule_json(self) -> "PromoUpdate":
        if self.rule_json is not None:
            _validate_rule_json(self.rule_json)
        return self

    model_config = {"from_attributes": True}


# ─── Javob sxemasi ────────────────────────────────────────────────────────────


class PromoOut(BaseModel):
    """Aksiya javob sxemasi — lokalizatsiyalangan nom bilan."""

    id: uuid.UUID
    name_uz: str
    name_ru: str
    name: str = ""  # lokalizatsiyalangan — model_validator da to'ldiriladi
    promo_type: str
    rule_json: dict
    banner_url: str | None
    valid_from: date
    valid_to: date
    target_segment_id: uuid.UUID | None
    target_product_id: uuid.UUID | None
    is_active: bool
    branch_id: uuid.UUID | None
    client_uuid: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @model_validator(mode="after")
    def set_localized_name(self) -> "PromoOut":
        locale = current_locale.get()
        if locale == "ru" and self.name_ru:
            self.name = self.name_ru
        else:
            self.name = self.name_uz
        return self

    model_config = {"from_attributes": True}


# ─── Paginated ro'yxat ────────────────────────────────────────────────────────


class PaginatedPromos(BaseModel):
    """Paginated aksiyalar ro'yxati."""

    items: list[PromoOut]
    total: int
    limit: int
    offset: int

    model_config = {"from_attributes": True}


# ─── rule_json validatsiya yordamchisi ────────────────────────────────────────


def _validate_rule_json(rule: dict) -> None:
    """
    rule_json yaroqliligini tekshiradi.

    Qoidalar:
      - discount_percent yoki discount_amount bo'lishi shart (ikkalasi ham bo'lishi mumkin emas).
      - discount_percent: 0 < x <= 100 (foiz).
      - discount_amount: x > 0 (ijobiy son).
      - min_qty: ixtiyoriy, > 0 bo'lsa qabul qilinadi.

    Raises:
        ValueError: Yaroqsiz qoida.
    """
    has_percent = "discount_percent" in rule
    has_amount = "discount_amount" in rule

    if not has_percent and not has_amount:
        raise ValueError(
            "rule_json da 'discount_percent' yoki 'discount_amount' bo'lishi shart"
        )
    if has_percent and has_amount:
        raise ValueError(
            "rule_json da faqat bittasi bo'lishi mumkin: 'discount_percent' yoki 'discount_amount'"
        )
    if has_percent:
        pct = rule["discount_percent"]
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            raise ValueError("discount_percent son bo'lishi kerak")
        if not (0 < pct <= 100):
            raise ValueError("discount_percent 0 dan katta va 100 dan kichik yoki teng bo'lishi kerak")

    if has_amount:
        amt = rule["discount_amount"]
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            raise ValueError("discount_amount son bo'lishi kerak")
        if amt <= 0:
            raise ValueError("discount_amount musbat bo'lishi kerak")

    if "min_qty" in rule:
        mq = rule["min_qty"]
        try:
            mq = float(mq)
        except (TypeError, ValueError):
            raise ValueError("min_qty son bo'lishi kerak")
        if mq <= 0:
            raise ValueError("min_qty musbat bo'lishi kerak")
