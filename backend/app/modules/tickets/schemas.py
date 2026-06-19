"""
Tickets moduli Pydantic v2 sxemalari — murojaat CRUD.

Sxemalar:
  TicketCreate      — yangi murojaat yaratish
  TicketStatusUpdate — holat yangilash (server-avtoritar holat mashinasi)
  TicketOut         — murojaat javob sxemasi (messages ixtiyoriy)
  TicketMessageCreate — murojaatga xabar qo'shish
  TicketMessageOut  — xabar javob sxemasi
  PaginatedTickets  — paginated murojaat ro'yxati
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ─── TicketCreate ─────────────────────────────────────────────────────────────


class TicketCreate(BaseModel):
    """Yangi murojaat yaratish so'rovi."""

    ticket_type: str = Field(
        ...,
        description="Murojaat turi: taklif | etiroz",
        pattern="^(taklif|etiroz)$",
    )
    subject: str = Field(..., min_length=1, max_length=255, description="Mavzu")
    body: str = Field(..., min_length=1, description="Murojaat matni")

    # Do'kon murojaati uchun — ixtiyoriy (NULL = xodim murojaati)
    store_id: uuid.UUID | None = Field(None, description="Do'kon ID (NULL=xodim murojaati)")

    # Idempotentlik
    client_uuid: uuid.UUID | None = Field(None, description="Idempotentlik UUID (ixtiyoriy)")

    # Filial
    branch_id: uuid.UUID | None = Field(None, description="Filial ID (ixtiyoriy)")


# ─── TicketStatusUpdate ───────────────────────────────────────────────────────


class TicketStatusUpdate(BaseModel):
    """Murojaat holati yangilash so'rovi."""

    status: str = Field(
        ...,
        description="Yangi holat: in_progress | resolved | closed | (resolved→in_progress)",
        pattern="^(new|in_progress|resolved|closed)$",
    )
    version: int = Field(..., description="Optimistik lock uchun joriy versiya")


# ─── TicketMessageCreate ──────────────────────────────────────────────────────


class TicketMessageCreate(BaseModel):
    """Murojaatga xabar qo'shish so'rovi."""

    body: str = Field(..., min_length=1, description="Xabar matni")
    attachment_url: str | None = Field(
        None,
        max_length=1024,
        description="Fayl URL (storage'dan; ixtiyoriy)",
    )


# ─── TicketMessageOut ─────────────────────────────────────────────────────────


class TicketMessageOut(BaseModel):
    """Xabar javob sxemasi."""

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    attachment_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── TicketOut ────────────────────────────────────────────────────────────────


class TicketOut(BaseModel):
    """Murojaat javob sxemasi."""

    id: uuid.UUID
    store_id: uuid.UUID | None
    author_id: uuid.UUID | None
    ticket_type: str
    subject: str
    body: str
    status: str
    assigned_to: uuid.UUID | None
    branch_id: uuid.UUID | None
    client_uuid: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    # Xabarlar — ixtiyoriy (faqat get_ticket da yuklangan).
    # model_validate da avtomatik yuklanmaydi — router tomonidan to'ldiriladi.
    messages: list[TicketMessageOut] | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_no_messages(cls, obj) -> "TicketOut":
        """
        Lazy messages yuklamasdan TicketOut yaratadi.

        list_tickets va create_ticket da ishlatiladi —
        messages kerak emas, lekin lazy relationship greenlet xatosini chiqaradi.
        """
        return cls(
            id=obj.id,
            store_id=obj.store_id,
            author_id=obj.author_id,
            ticket_type=obj.ticket_type,
            subject=obj.subject,
            body=obj.body,
            status=obj.status,
            assigned_to=obj.assigned_to,
            branch_id=obj.branch_id,
            client_uuid=obj.client_uuid,
            version=obj.version,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            deleted_at=obj.deleted_at,
            messages=None,
        )


# ─── PaginatedTickets ─────────────────────────────────────────────────────────


class PaginatedTickets(BaseModel):
    """Paginated murojaat ro'yxati javob sxemasi."""

    items: list[TicketOut]
    total: int = Field(..., description="Jami topilgan murojaat soni")
    limit: int = Field(..., description="So'rovdagi limit")
    offset: int = Field(..., description="So'rovdagi offset")
