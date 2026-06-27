"""
Assistant moduli Pydantic v2 sxemalari.

Sxemalar:
  ChatMessage  — bitta chat xabari (rol + matn)
  ChatIn       — chat so'rov tanasi
  ChatOut      — chat javob tanasi
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Bitta chat xabari (tarix uchun)."""

    role: str = Field(
        ...,
        pattern="^(user|assistant)$",
        description="Rol: user | assistant",
    )
    content: str = Field(
        ..., max_length=2000, description="Xabar matni (max 2000 belgi)"
    )


class ChatIn(BaseModel):
    """Chat so'rov tanasi."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Foydalanuvchi xabari (max 1000 belgi)",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=20,
        description="Suhbat tarixi (max so'nggi 20 ta — server 6 tagacha kesadi)",
    )


class ChatOut(BaseModel):
    """Chat javob tanasi."""

    reply: str = Field(..., description="AI javobi (o'zbekcha)")
    ai_enabled: bool = Field(
        ..., description="Groq muvaffaqiyatli ishladimi"
    )
