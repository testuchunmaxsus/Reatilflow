"""
Enterprise moduli sxemalari — MT3.

EnterpriseOut: GET /enterprise/me javob sxemasi.
Veb/mobil UI yoqilmagan modullarni yashirish uchun enabled_modules ishlatiladi.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EnterpriseOut(BaseModel):
    """
    Joriy korxona ma'lumotlari — GET /enterprise/me javob sxemasi.

    Maydonlar:
      id              — korxona UUID
      name            — korxona nomi
      inn             — soliq raqami (nullable)
      status          — active | suspended
      enabled_modules — yoqilgan modul kalitlari ro'yxati
      created_at      — yaratilgan vaqti
      updated_at      — yangilangan vaqti
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    inn: str | None = None
    status: str
    enabled_modules: list[str]
    created_at: datetime
    updated_at: datetime
