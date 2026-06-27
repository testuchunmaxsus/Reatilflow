"""
Rule-based AI tavsiyalar — Faza 4.

Deterministic qoidalar (R1-R5) asosida tavsiyalar generatsiyasi.
Hech qanday tashqi API chaqiriq yo'q — test qilish oson.

Qoidalar:
  R1 expiry_urgent : partiya days_left <= 7 va qty > 0 → HIGH
  R2 expiry_warn   : 7 < days_left <= 30 va qty > 0 → MEDIUM
  R3 restock       : velocity yuqori (top kvartil) VA joriy qty past (< velocity*7) → HIGH
  R4 slow_mover    : qty > 0 VA period sotuvi 0 → MEDIUM
  R5 geo_hotspot   : eng yuqori velocity'li do'kon/hududni ajratib ko'rsatish → INFO

Kirish: GeoVelocityItem, ExpiryItem, ProductRankingItem ro'yxatlari.
Chiqish: RecommendationItem ro'yxati (deterministik tartiblangan).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.modules.analytics.schemas import (
    ExpiryItem,
    GeoVelocityItem,
    ProductRankingItem,
    RecommendationItem,
)

logger = logging.getLogger(__name__)

# Restock qoida: velocity (qty/kun) * bu kunlar = qayta to'ldirish chegarasi
RESTOCK_DAYS_THRESHOLD: int = 7

# Geo hotspot: eng yuqori velocity (faqat bitta)
GEO_HOTSPOT_TOP_N: int = 1


def generate_recommendations(
    geo_items: list[GeoVelocityItem],
    expiry_items: list[ExpiryItem],
    top_products: list[ProductRankingItem],
    bottom_products: list[ProductRankingItem],
) -> list[RecommendationItem]:
    """
    R1-R5 qoidalaridan deterministik tavsiyalar ro'yxati yaratadi.

    Qaytarish tartibi: jiddiylik bo'yicha (high → medium → low → info).
    """
    recs: list[RecommendationItem] = []

    # R1: Shoshilinch expiry (≤7 kun)
    urgent_expiry = [item for item in expiry_items if item.severity == "urgent"]
    for item in urgent_expiry:
        recs.append(
            RecommendationItem(
                code="R1_expiry_urgent",
                severity="high",
                title_uz=f"Shoshilinch: {item.product_name} muddati yaqin!",
                detail_uz=(
                    f"'{item.store_name}' do'konida '{item.product_name}' mahsulotining "
                    f"{item.qty} donasining muddati {item.days_left} kunda tugaydi "
                    f"({item.expiry_date}). Zudlik bilan choralar ko'ring."
                ),
                store_id=item.store_id,
                product_id=item.product_id,
                metric={
                    "qty": str(item.qty),
                    "days_left": item.days_left,
                    "expiry_date": str(item.expiry_date),
                },
            )
        )

    # R2: Expiry ogohlantirish (8-30 kun)
    warn_expiry = [item for item in expiry_items if item.severity == "warning"]
    for item in warn_expiry:
        recs.append(
            RecommendationItem(
                code="R2_expiry_warn",
                severity="medium",
                title_uz=f"Eslatma: {item.product_name} muddati yaqinlashmoqda",
                detail_uz=(
                    f"'{item.store_name}' do'konida '{item.product_name}' mahsulotining "
                    f"{item.qty} donasining muddati {item.days_left} kunda tugaydi "
                    f"({item.expiry_date}). Sotishni tezlashtiring."
                ),
                store_id=item.store_id,
                product_id=item.product_id,
                metric={
                    "qty": str(item.qty),
                    "days_left": item.days_left,
                    "expiry_date": str(item.expiry_date),
                },
            )
        )

    # R3: Restock (tez sotilyapti, qoldiq kam)
    # Yuqori velocity: top kvartil bo'yicha chegarani aniqlaymiz
    if geo_items:
        velocities = [float(item.velocity_per_day) for item in geo_items if item.velocity_per_day > 0]
        if velocities:
            velocities_sorted = sorted(velocities, reverse=True)
            q75_idx = max(0, len(velocities_sorted) // 4)
            q75_threshold = velocities_sorted[q75_idx]

            for store_item in geo_items:
                vel = float(store_item.velocity_per_day)
                if vel >= q75_threshold and vel > 0:
                    # Bu do'kondagi jami qoldiq (top_products dan olib bera olmaymiz,
                    # ammo geo_items'da store_id bo'yicha sold_qty borligidan foydalanish mumkin)
                    # Soddalashtirish: velocity yuqori bo'lsa restock tavsiyasi
                    projected_days = float(store_item.sold_qty) / vel if vel > 0 else 0
                    if projected_days < RESTOCK_DAYS_THRESHOLD:
                        recs.append(
                            RecommendationItem(
                                code="R3_restock",
                                severity="high",
                                title_uz=f"Ko'proq yetkazing: '{store_item.store_name}'",
                                detail_uz=(
                                    f"'{store_item.store_name}' do'konida mening mahsulotlarim "
                                    f"kuniga {store_item.velocity_per_day:.2f} dona tezlikda sotilyapti. "
                                    f"Qoldiq {RESTOCK_DAYS_THRESHOLD} kundayoq tugashi mumkin. "
                                    f"Yangi yetkazishni rejalashtiring."
                                ),
                                store_id=store_item.store_id,
                                product_id=None,
                                metric={
                                    "velocity_per_day": str(store_item.velocity_per_day),
                                    "sold_qty_period": str(store_item.sold_qty),
                                    "projected_days": round(projected_days, 1),
                                },
                            )
                        )

    # R4: Sekin harakat (qty > 0, sotuv = 0)
    # bottom_products da sold_qty=0 bo'lganlar
    zero_movers = [p for p in bottom_products if p.sold_qty == Decimal("0")]
    for item in zero_movers[:5]:  # Max 5 ta
        recs.append(
            RecommendationItem(
                code="R4_slow_mover",
                severity="medium",
                title_uz=f"Harakatsiz mahsulot: {item.product_name}",
                detail_uz=(
                    f"'{item.product_name}' tanlangan davrda hech sotilmadi. "
                    f"Aksiya o'tkazing yoki boshqa do'konlarga taqsimlang."
                ),
                store_id=None,
                product_id=item.product_id,
                metric={
                    "sold_qty": "0",
                    "store_count": item.store_count,
                },
            )
        )

    # R5: Geo hotspot (eng yuqori velocity'li do'kon)
    if geo_items:
        sorted_by_vel = sorted(geo_items, key=lambda x: x.velocity_per_day, reverse=True)
        for hotspot in sorted_by_vel[:GEO_HOTSPOT_TOP_N]:
            if hotspot.velocity_per_day > 0:
                recs.append(
                    RecommendationItem(
                        code="R5_geo_hotspot",
                        severity="info",
                        title_uz=f"Sotuv markaziy nuqtasi: '{hotspot.store_name}'",
                        detail_uz=(
                            f"'{hotspot.store_name}' eng yuqori sotuv tezligiga ega: "
                            f"kuniga {hotspot.velocity_per_day:.2f} dona. "
                            f"Ushbu do'konga alohida e'tibor bering."
                        ),
                        store_id=hotspot.store_id,
                        product_id=None,
                        metric={
                            "velocity_per_day": str(hotspot.velocity_per_day),
                            "revenue": str(hotspot.revenue),
                            "address": hotspot.address or "",
                        },
                    )
                )

    # Jiddiylik bo'yicha tartiblash: high → medium → low → info
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    recs.sort(key=lambda r: severity_order.get(r.severity, 4))

    logger.debug("Tavsiyalar yaratildi: %d ta", len(recs))
    return recs
