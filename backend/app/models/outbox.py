"""
Transactional Outbox modeli — outbox_event jadvali.

Offline-first sinxronlash arxitekturasining asosiy qismi.

Jarayon:
  1. Biznes tranzaksiyasi (masalan, buyurtma yaratish) bajariladi
  2. Bir xil DB tranzaksiyasida outbox_event ham yoziladi
  3. Background worker (yoki endpoint) published_at=NULL yozuvlarni
     o'qib, klientlarga/tashqi tizimlarga yuboradi
  4. Muvaffaqiyatli yetkazilgach published_at set qilinadi

Bu pattern tarmoq xatoliklarida hodisaning yo'qolishini oldini oladi.

seq KURSOR MEXANIZMI (ADR §3.5, T13):
  seq — Postgres DB SEQUENCE (outbox_event_seq) / SQLite surrogate counter.
  Global monoton ketma-ketlik — delta sync kursori = oxirgi ko'rilgan seq.
  created_at / wall-clock ga TAYANMA — klient soatiga ishonmaslik.

  Postgres production'da: DB SEQUENCE orqali (CREATE SEQUENCE + nextval default).
    SQLAlchemy Sequence("outbox_event_seq") ishlatiladi — multi-worker xavfsiz,
    har INSERT DB tomonida monoton seq oladi, Python counterga TAYANMAYDI.
  SQLite testlarda: ORM orqali `_next_seq` Python counter ishlatiladi
    (test izolatsiyasi uchun — har test o'z counter'iga ega).
    Sequence SQLite'da e'tiboriga olinmaydi (dialect-aware).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Index, Sequence, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.uuid7 import uuid7
from app.models.base import Base

# ─── SQLite test uchun in-process seq counter ────────────────────────────────
# Production'da Postgres DB SEQUENCE (outbox_event_seq) ishlatiladi.
# Testlarda (SQLite) ORM default orqali monotonik seq ta'minlanadi.
# Sequence() SQLite dialektida avtomatik e'tiboriga olinmaydi (optional=True kabi
# ishlaydi — SQLAlchemy Sequence faqat Postgres/Oracle da server_default qo'shadi).

_sqlite_seq_counter: int = 0


def _next_seq() -> int:
    """
    Monoton seq qiymat qaytaradi — FAQAT SQLite test muhiti uchun.

    Postgres: outbox_event_seq DB SEQUENCE (migratsiya 0009) — bu funksiya
    Postgres'da chaqirilmaydi. SQLAlchemy Sequence("outbox_event_seq") ustun
    uchun server_default sifatida nextval('outbox_event_seq') o'rnatadi.
    Python counterga TAYANMAYDI — har INSERT DB tomonida generatsiya qilinadi.

    SQLite testlarda: in-process monoton counter.
    """
    global _sqlite_seq_counter
    _sqlite_seq_counter += 1
    return _sqlite_seq_counter


def reset_seq_counter() -> None:
    """
    Test izolyatsiyasi uchun counter'ni nolga qaytaradi.

    Faqat test fixtures'da chaqirilishi kerak.
    """
    global _sqlite_seq_counter
    _sqlite_seq_counter = 0


# Postgres DB SEQUENCE obyekti — multi-worker xavfsiz monoton ketma-ketlik.
# optional=True: SQLite'da Sequence e'tiboriga olinmaydi (dialect-aware).
#   Postgres'da: server_default=nextval('outbox_event_seq') avtomatik qo'shiladi.
#   SQLite'da: Sequence optional=True → e'tiboriga olinmaydi, Python default ishlatiladi.
# Migratsiya 0009 CREATE SEQUENCE outbox_event_seq ishlatadi.
_outbox_seq = Sequence("outbox_event_seq", optional=True)


def _seq_default(context) -> int:
    """
    Dialekt-aware seq default (BUG FIX).

    AVVAL: `default=_next_seq` (Python counter) Sequence'ni BEKOR qilardi —
    Postgres'da ham har-jarayon xotira counter'i ishlatilardi (0'dan boshlanadi,
    restart/multi-worker da takrorlanadi) → `duplicate key ix_outbox_event_seq`.

    ENDI:
      - PostgreSQL: DB SEQUENCE `nextval('outbox_event_seq')` — DB-avtoritar,
        multi-worker/multi-process xavfsiz, hech qachon takrorlanmaydi.
      - SQLite (test): in-process monoton counter (Sequence SQLite'da yo'q).
    """
    if context.connection.dialect.name == "postgresql":
        return context.connection.execute(_outbox_seq.next_value()).scalar()
    global _sqlite_seq_counter
    _sqlite_seq_counter += 1
    return _sqlite_seq_counter


class OutboxEvent(Base):
    """
    Outbox hodisasi.

    Maydonlar:
      seq            — monoton autoincrement kursor (server-avtoritar, klient soatiga ishonmaslik)
      aggregate_type — qaysi agregat (order, store, product, ...)
      aggregate_id   — agregat identifikatori
      event_type     — hodisa turi (order.created, store.updated, ...)
      payload        — JSON payload (klient uchun delta)
      created_at     — yaratilgan vaqt
      published_at   — yuborilgan vaqt (NULL = hali yuborilmagan)

    KURSOR MEXANIZMI (ADR §3.5):
      seq — Postgres DB SEQUENCE (outbox_event_seq) / SQLite ORM counter.
      Postgres'da multi-worker xavfsiz: har INSERT nextval('outbox_event_seq')
      DB tomonida generatsiya qilinadi — Python counterga TAYANMAYDI.
      Delta sync kursori = oxirgi ko'rilgan seq.
      created_at / wall-clock ga TAYANMA — klient soatiga ishonmaslik.
    """

    __tablename__ = "outbox_event"

    __table_args__ = (
        # seq ustuni bo'yicha tez pull so'rovlari uchun
        Index("ix_outbox_event_seq", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        comment="UUID birlamchi kalit",
    )

    seq: Mapped[int] = mapped_column(
        BigInteger,
        # Postgres: Sequence("outbox_event_seq") → server_default=nextval(seq)
        #   SQLAlchemy avtomatik server_default o'rnatadi Postgres'da.
        #   Multi-worker xavfsiz: har INSERT DB-generatsiya qilingan monoton seq oladi.
        # SQLite: Sequence e'tiboriga olinmaydi → default=_next_seq ishlatiladi.
        _outbox_seq,
        nullable=False,
        unique=True,
        # Dialekt-aware: Postgres → DB SEQUENCE nextval; SQLite → counter.
        # (Avvalgi `default=_next_seq` Postgres'da ham counter ishlatib bug berardi.)
        default=_seq_default,
        comment=(
            "Monoton kursor (Postgres: DB SEQUENCE nextval — multi-worker xavfsiz; "
            "SQLite tests: ORM counter). "
            "Delta sync uchun ishlatiladi — klient soatiga TAYANMA."
        ),
    )

    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Agregat nomi: order | store | product | delivery | ...",
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Agregat identifikatori (UUID string)",
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Hodisa turi: order.created | product.updated | ...",
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON payload (klient delta sync uchun)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Yaratilgan vaqt (UTC) — kursor uchun ISHLATILMAYDI, seq ishlatiladi",
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Yuborilgan vaqt (NULL = navbatda kutilmoqda)",
    )

    def __repr__(self) -> str:
        return (
            f"<OutboxEvent seq={self.seq} type={self.event_type!r} "
            f"agg={self.aggregate_type}:{self.aggregate_id} "
            f"published={self.published_at}>"
        )
