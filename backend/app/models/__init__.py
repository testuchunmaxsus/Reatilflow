"""
SQLAlchemy modellari — eksport ro'yxati.

Alembic env.py ushbu paketni import qilganda barcha modellar
Base.metadata ga ro'yxatdan o'tgan bo'lishi kerak.
"""

from app.models.base import Base, TimestampMixin  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.catalog import (  # noqa: F401
    Category,
    PriceHistory,
    PriceSegment,
    Product,
    ProductNote,
    ProductPrice,
)
from app.models.finance import AccountBalance, LedgerEntry  # noqa: F401
from app.models.order import Order, OrderLine  # noqa: F401
from app.models.outbox import OutboxEvent  # noqa: F401
from app.models.stock import StockBalance, StockMovement  # noqa: F401
from app.models.store import AgentStore, Store  # noqa: F401
from app.models.user import AppUser  # noqa: F401
from app.models.attendance import Attendance  # noqa: F401
from app.models.delivery import Delivery  # noqa: F401
from app.models.gps import GpsPoint  # noqa: F401
from app.models.push import PushLog  # noqa: F401
import app.models.append_only  # noqa: F401 — DDL event'larini ro'yxatga olish uchun

__all__ = [
    "Base",
    "TimestampMixin",
    "AppUser",
    "Store",
    "AgentStore",
    "Category",
    "PriceSegment",
    "Product",
    "ProductPrice",
    "PriceHistory",
    "ProductNote",
    "AuditLog",
    "OutboxEvent",
    "StockMovement",
    "StockBalance",
    "LedgerEntry",
    "AccountBalance",
    "Order",
    "OrderLine",
    "Attendance",
    "Delivery",
    "GpsPoint",
    "PushLog",
]
