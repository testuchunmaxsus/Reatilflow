"""
RBAC ruxsat matritsasi — yagona haqiqat manbai (Python).

ADR-001 §3.6 bo'yicha 5 rol × 11 modul + rbac/audit + push.

Rollar (AppUser.role qiymatlari):
  administrator, agent, courier, accountant, store

Modullar:
  1. catalog         — Katalog
  2. agent_cabinet   — Agent kabineti
  3. attendance      — Davomat
  4. delivery        — Yetkazib berish
  5. stock           — Ombor
  6. finance         — Buxgalteriya
  7. tickets         — Murojaat (ticket)
  8. customers       — Mijoz bazasi
  9. stats           — Statistika
  10. contracts      — Shartnoma
  11. promo          — Aksiya
  +   rbac           — RBAC/Audit (faqat administrator)

Amallar: view | create | edit | delete | approve

Qator-darajali (row-level) qoidalar:
  - agent:    faqat o'z do'konlari (Store.agent_id == user.id yoki AgentStore)
  - courier:  faqat o'ziga tayinlangan yetkazishlar (Delivery.courier_id == user.id)
  - store:    faqat o'zi (Store.id == user.id bilan bog'liq yozuv)
  - accountant: branch_id bo'yicha (yoki barchasi, agar branch_id=None)
  - administrator: barchasi (branch_id bo'yicha yoki hamma)

Bu izohlar faqat `scope.py` da qo'llaniladi; bu fayl faqat modul-darajali ruxsatni belgilaydi.
"""

from __future__ import annotations

from enum import StrEnum


# ─── Modul va amal konstantalari ─────────────────────────────────────────────


class Module(StrEnum):
    """11 ta domen moduli + rbac/audit + orders (T11) + gps (T17) + pos (POS chakana sotuv)."""

    CATALOG = "catalog"
    AGENT_CABINET = "agent_cabinet"
    ATTENDANCE = "attendance"
    DELIVERY = "delivery"
    STOCK = "stock"
    FINANCE = "finance"
    TICKETS = "tickets"
    CUSTOMERS = "customers"
    STATS = "stats"
    CONTRACTS = "contracts"
    PROMO = "promo"
    RBAC = "rbac"
    ORDERS = "orders"        # T11: Buyurtma yadrosi
    GPS = "gps"              # T17: GPS Ingest (agent/courier trekking)
    POS = "pos"              # POS: Chakana sotuv yadrosi
    MARKETPLACE = "marketplace"  # MP1: B2B Marketplace katalog
    PUSH = "push"            # S2: Push bildirishnomalar


class Action(StrEnum):
    """5 ta standart amal."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    APPROVE = "approve"


def _p(module: Module | str, *actions: Action | str) -> set[str]:
    """Qisqa yordamchi: `module:action` stringlarini to'plam sifatida qaytaradi."""
    return {f"{module}:{action}" for action in actions}


# ─── Ruxsat matritsasi (ADR-001 §3.6) ────────────────────────────────────────
# Har rol uchun "module:action" to'plami.
# Keyingi modullarda: `has_permission(user, module, action)` yoki
# `require_permission(module, action)` dependency orqali tekshiriladi.

ROLE_PERMISSIONS: dict[str, set[str]] = {

    # ─── Administrator ─────────────────────────────────────────────────────────
    # Barcha modullarga to'liq kirish (CRUD), RBAC/Audit ham.
    "administrator": (
        _p(Module.CATALOG,       Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p(Module.AGENT_CABINET, Action.VIEW)                                       # admin faqat ko'radi
        | _p(Module.ATTENDANCE,  Action.VIEW)
        | _p(Module.DELIVERY,    Action.VIEW, Action.CREATE, Action.EDIT)             # T18: admin kuryer tayinlaydi
        | _p(Module.STOCK,       Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p(Module.FINANCE,     Action.VIEW)
        | _p(Module.TICKETS,     Action.VIEW, Action.EDIT)                            # view + resolve (edit)
        | _p(Module.CUSTOMERS,   Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p(Module.STATS,       Action.VIEW)
        | _p(Module.CONTRACTS,   Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p(Module.PROMO,       Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p(Module.RBAC,        Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        # T11: buyurtmalar — barcha filiallarga to'liq ko'rish + holat o'zgartirish
        | _p(Module.ORDERS,      Action.VIEW, Action.CREATE, Action.EDIT)
        # T17: GPS — administrator barcha agentlar/kuryerlar trekini ko'radi
        | _p(Module.GPS,         Action.VIEW)
        # POS: administrator barcha sotuvlarni ko'radi
        | _p(Module.POS,         Action.VIEW, Action.CREATE)
        # MP1: administrator marketplace browse + o'z mahsulotini publish qiladi
        # MP2: administrator buyurtma yaratadi va tasdiqlaydi/rad etadi
        | _p(Module.MARKETPLACE, Action.VIEW, Action.EDIT, Action.CREATE)
        # S2: administrator push bildirishnomalar log'ini ko'radi va qurilma tokenini boshqaradi
        | _p(Module.PUSH, Action.VIEW, Action.CREATE)
    ),

    # ─── Savdo agenti ──────────────────────────────────────────────────────────
    # ADR §3.6:
    #   catalog: view
    #   agent_cabinet: view + edit (o'zi)       → row-level scope qo'llaniladi
    #   attendance: create + view (o'zi)         → row-level scope
    #   delivery: view+create (o'z buyurtma)     → row-level scope (T18: kuryer tayinlaydi)
    #   stock: view
    #   finance: view (o'z do'konlari)           → row-level scope
    #   tickets: create + view                   → row-level scope
    #   customers: view + create + edit (o'z do'konlari)  → row-level scope
    #   stats: view (o'z natijasi)               → row-level scope
    #   contracts: view + create (o'z/biriktirilgan do'konlari) → row-level scope (ADR-003)
    #   promo: view
    #   orders: create + view (o'z do'konlari)  → row-level scope (T11)
    "agent": (
        _p(Module.CATALOG,       Action.VIEW)
        | _p(Module.AGENT_CABINET, Action.VIEW, Action.EDIT)
        | _p(Module.ATTENDANCE,  Action.VIEW, Action.CREATE)
        | _p(Module.DELIVERY,    Action.VIEW, Action.CREATE)                          # T18: agent kuryer tayinlaydi
        | _p(Module.STOCK,       Action.VIEW)
        | _p(Module.FINANCE,     Action.VIEW)
        | _p(Module.TICKETS,     Action.VIEW, Action.CREATE)
        | _p(Module.CUSTOMERS,   Action.VIEW, Action.CREATE, Action.EDIT)
        | _p(Module.STATS,       Action.VIEW)
        | _p(Module.CONTRACTS,   Action.VIEW, Action.CREATE)   # ADR-003: agent shartnoma tuzadi
        | _p(Module.PROMO,       Action.VIEW)
        # T11: agent o'z do'konlari uchun buyurtma yaratadi + ko'radi + holat o'zgartiradi
        | _p(Module.ORDERS,      Action.VIEW, Action.CREATE, Action.EDIT)
        # T17: GPS — agent o'z trekini ingest qiladi va ko'radi (row-level scope)
        | _p(Module.GPS,         Action.CREATE, Action.VIEW)
        # MP1: agent marketplace browse qiladi
        # MP2: agent buyurtma yaratadi (supplier sifatida emas, faqat buyer sifatida)
        | _p(Module.MARKETPLACE, Action.VIEW, Action.CREATE)
        # S2: agent o'z qurilma tokenini ro'yxatdan o'tkazadi
        | _p(Module.PUSH, Action.CREATE)
    ),

    # ─── Kuryer (yetkazib beruvchi) ────────────────────────────────────────────
    # ADR §3.6:
    #   catalog: view
    #   agent_cabinet: — (yo'q)
    #   attendance: create + view (o'zi)         → row-level scope
    #   delivery: create + edit (o'ziga)         → row-level scope
    #   stock: view (yuk)
    #   finance: — (yo'q)
    #   tickets: create + view
    #   customers: view (manzil)
    #   stats: view (o'z yetkazishlari)          → row-level scope
    #   contracts: — (yo'q)
    #   promo: — (yo'q)
    "courier": (
        _p(Module.CATALOG,      Action.VIEW)
        | _p(Module.ATTENDANCE, Action.VIEW, Action.CREATE)
        # T18: kuryer o'ziga tayinlangan yetkazishni ko'radi va o'zgartiradi (tayinlash emas)
        | _p(Module.DELIVERY,   Action.VIEW, Action.EDIT)
        | _p(Module.STOCK,      Action.VIEW)
        | _p(Module.TICKETS,    Action.VIEW, Action.CREATE)
        | _p(Module.CUSTOMERS,  Action.VIEW)
        | _p(Module.STATS,      Action.VIEW)
        # T17: GPS — kuryer o'z trekini ingest qiladi va ko'radi (row-level scope)
        | _p(Module.GPS,        Action.CREATE, Action.VIEW)
        # MP1: kuryer marketplace browse qiladi
        # MP3: kuryer tayinlangan buyurtmani yetkazildi deb belgilaydi (deliver endpoint)
        | _p(Module.MARKETPLACE, Action.VIEW, Action.EDIT)
        # POS: agent — ruxsati yo'q (pos checkout faqat store roli uchun)
        # S2: kuryer o'z qurilma tokenini ro'yxatdan o'tkazadi
        | _p(Module.PUSH, Action.CREATE)
    ),

    # ─── Buxgalter ─────────────────────────────────────────────────────────────
    # ADR §3.6:
    #   catalog: view
    #   agent_cabinet: view
    #   attendance: view
    #   delivery: view
    #   stock: view
    #   finance: CRUD + approve
    #   tickets: view + resolve (edit)
    #   customers: view
    #   stats: view (moliyaviy)
    #   contracts: view + edit
    #   promo: view
    #   rbac: view (audit)
    "accountant": (
        _p(Module.CATALOG,       Action.VIEW)
        | _p(Module.AGENT_CABINET, Action.VIEW)
        | _p(Module.ATTENDANCE,  Action.VIEW)
        | _p(Module.DELIVERY,    Action.VIEW)
        | _p(Module.STOCK,       Action.VIEW)
        | _p(Module.FINANCE,     Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE, Action.APPROVE)
        | _p(Module.TICKETS,     Action.VIEW, Action.EDIT)
        | _p(Module.CUSTOMERS,   Action.VIEW)
        | _p(Module.STATS,       Action.VIEW)
        | _p(Module.CONTRACTS,   Action.VIEW, Action.EDIT)
        | _p(Module.PROMO,       Action.VIEW)
        | _p(Module.RBAC,        Action.VIEW)
        # T11: buxgalter barcha buyurtmalarni ko'ra oladi (filial bo'yicha)
        | _p(Module.ORDERS,      Action.VIEW)
        # POS: buxgalter sotuvlarni ko'ra oladi
        | _p(Module.POS,         Action.VIEW)
        # MP1: buxgalter marketplace browse qiladi
        # MP2: buxgalter kiruvchi buyurtmalarni tasdiqlaydi/rad etadi (supplier sifatida)
        | _p(Module.MARKETPLACE, Action.VIEW, Action.EDIT, Action.CREATE)
        # S2: buxgalter o'z qurilma tokenini ro'yxatdan o'tkazadi
        | _p(Module.PUSH, Action.CREATE)
    ),

    # ─── Do'kon (mijoz) ────────────────────────────────────────────────────────
    # ADR §3.6:
    #   catalog: view
    #   agent_cabinet: — (yo'q)
    #   attendance: — (yo'q)
    #   delivery: view (o'ziniki)                → row-level scope
    #   stock: — (yo'q)
    #   finance: view (o'z balansi)              → row-level scope
    #   tickets: create + view (o'ziniki)        → row-level scope
    #   customers: view + edit (o'ziniki)        → row-level scope
    #   stats: view (o'z xaridlari)             → row-level scope
    #   contracts: view (o'ziniki)              → row-level scope
    #   promo: view
    "store": (
        _p(Module.CATALOG,    Action.VIEW)
        | _p(Module.DELIVERY, Action.VIEW)
        | _p(Module.FINANCE,  Action.VIEW)
        | _p(Module.TICKETS,  Action.VIEW, Action.CREATE)
        | _p(Module.CUSTOMERS, Action.VIEW, Action.EDIT)
        | _p(Module.STATS,    Action.VIEW)
        | _p(Module.CONTRACTS, Action.VIEW)
        | _p(Module.PROMO,    Action.VIEW)
        # T11: do'kon o'z buyurtmalarini ko'ra oladi (faqat view)
        | _p(Module.ORDERS,   Action.VIEW)
        # POS: do'kon (kassir) sotuv yaratadi va ko'radi
        | _p(Module.POS,      Action.VIEW, Action.CREATE)
        # MP1: do'kon marketplace browse qiladi
        # MP2: do'kon buyurtma yaratadi (faqat buyer sifatida, tasdiqlash/rad etish emas)
        # MP3: do'kon delivered buyurtmani qabul qiladi (accept endpoint)
        | _p(Module.MARKETPLACE, Action.VIEW, Action.CREATE, Action.EDIT)
        # S2: do'kon (kassir) o'z qurilma tokenini ro'yxatdan o'tkazadi
        | _p(Module.PUSH, Action.CREATE)
    ),

    # ─── Superadmin (platforma egasi) ─────────────────────────────────────────
    # enterprise_id = NULL. Korxona boshqaruviga kiradi, TENANT MA'LUMOTIGA KIRMAYDI.
    # MT1: enterprise CRUD, suspend, modul toggle ruxsatlari.
    # MT4 da to'liq implementatsiya qilinadi.
    "superadmin": (
        # Korxona boshqaruvi (MT1 poydevori)
        _p("enterprise", Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        | _p("enterprise", "suspend", "activate", "module_toggle")
        # RBAC va audit — platforma darajasida
        | _p(Module.RBAC, Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)
        # MP5: Marketplace banner moderatsiya — superadmin aktiv/deaktiv qiladi
        # LEKIN enterprise_id=None bo'lgani uchun banner yarata OLMAYDI (service tekshiradi)
        | _p(Module.MARKETPLACE, Action.VIEW, Action.EDIT)
        # Barcha modul ko'rinishi (statistika uchun) — LEKIN tenant ma'lumoti emas
        # MT4 da to'liq aniqlanadi; hozir minimal set
    ),
}

# ─── Qulaylik uchun hamma ruxsatlar to'plami ─────────────────────────────────
# ALL_VALID_ROLES: tenant rollari (superadmin — platform role, shu ro'yxatda yo'q)
ALL_VALID_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS.keys()) - {"superadmin"}
ALL_VALID_MODULES: frozenset[str] = frozenset(m.value for m in Module)
ALL_VALID_ACTIONS: frozenset[str] = frozenset(a.value for a in Action)
