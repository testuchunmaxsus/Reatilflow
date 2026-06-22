"""
Tenant (korxona) konteksti — so'rov doirasidagi joriy enterprise_id.

MT2: outbox_event va boshqa avtomatik yoziladigan yozuvlar enterprise_id'ni
shu ContextVar'dan oladi — har modulning _write_outbox'iga param uzatmasdan.

Oqim:
  1. So'rov boshida (router/dependency) `set_current_enterprise(user.enterprise_id)`.
  2. Service ichida OutboxEvent yaratilganda default `get_current_enterprise()` o'qiydi.
  3. ContextVar async/await bo'ylab bir task ichida tarqaladi (FastAPI har so'rov = task).

superadmin yoki kontekst yo'q → None (outbox enterprise_id NULL bo'lishi mumkin,
lekin domen yozuvlari doimo enterprise_id'ga ega bo'ladi — service to'g'ridan-to'g'ri qo'yadi).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_current_enterprise_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_enterprise_id", default=None
)


def set_current_enterprise(enterprise_id: uuid.UUID | None) -> None:
    """So'rov doirasidagi joriy korxona ID'ni o'rnatadi."""
    _current_enterprise_id.set(enterprise_id)


def get_current_enterprise() -> uuid.UUID | None:
    """Joriy korxona ID'ni qaytaradi (yo'q bo'lsa None)."""
    return _current_enterprise_id.get()
