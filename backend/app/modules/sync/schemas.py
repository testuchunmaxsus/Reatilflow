"""
Sync moduli Pydantic schema'lari — T13.

Push (klient→server):
  SyncOp        — bitta operatsiya (op_type, client_uuid, payload).
  PushRequest   — operatsiyalar batchi (ops: list[SyncOp]).
  OpResult      — bitta op natijasi (applied|duplicate|conflict|error).
  PushResponse  — batch natijasi (results: list[OpResult]).

Pull (server→klient):
  PullResponse  — delta hodisalar (changes, next_cursor, has_more).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─── Push schema'lari ─────────────────────────────────────────────────────────


class SyncOp(BaseModel):
    """
    Bitta sync operatsiyasi.

    op_type    — operatsiya turi (masalan, "order.create").
    client_uuid — klient tomonidan generatsiya qilingan idempotentlik UUID.
    payload    — operatsiya ma'lumotlari (op_type ga qarab farqli struktura).
    """

    op_type: str = Field(
        ...,
        description="Operatsiya turi: 'order.create' va boshqalar.",
        examples=["order.create"],
    )
    client_uuid: str = Field(
        ...,
        description="Klient idempotentlik UUID (UUID string).",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Operatsiya ma'lumotlari (op_type ga qarab).",
    )


class PushRequest(BaseModel):
    """
    Push batchi — bir nechta SyncOp birgalikda.

    Maksimal batch hajmi: settings.sync_max_batch (default: 100).
    """

    ops: list[SyncOp] = Field(
        ...,
        description="Operatsiyalar ro'yxati (max: 100).",
        min_length=1,
    )


class OpResult(BaseModel):
    """
    Bitta operatsiya natijasi.

    client_uuid  — asl operatsiya client_uuid (aniqlash uchun).
    status       — applied | duplicate | conflict | error.
    server_id    — yaratilgan resurs ID (status=applied bo'lganda).
    message_key  — xato kaliti (status=error|conflict bo'lganda).
    """

    client_uuid: str
    status: str = Field(
        ...,
        description="Natija holati: applied | duplicate | conflict | error.",
    )
    server_id: str | None = None
    message_key: str | None = None


class PushResponse(BaseModel):
    """Push batch natijasi — har op uchun alohida OpResult."""

    results: list[OpResult]


# ─── Pull schema'lari ─────────────────────────────────────────────────────────


class ChangeItem(BaseModel):
    """
    Bitta delta o'zgarish elementi.

    entity_type — agregat turi (order, store, product, ...).
    entity_id   — agregat UUID string.
    event_type  — hodisa turi (order.created, product.updated, ...).
    seq         — monoton kursor qiymati (server-avtoritar).
    snapshot    — klient upsert qilishi uchun joriy entity holati.
    """

    entity_type: str
    entity_id: str
    event_type: str
    seq: int
    snapshot: dict[str, Any]


class PullResponse(BaseModel):
    """
    Delta pull natijasi.

    changes     — foydalanuvchi scope'idagi yangi hodisalar.
    next_cursor — qaytarilgan eng katta seq (keyingi so'rov uchun since= qiymati).
    has_more    — yana hodisalar bor (limit ga yetilgan).
    """

    changes: list[ChangeItem]
    next_cursor: int
    has_more: bool
