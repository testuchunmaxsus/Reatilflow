"""
RBAC moduli — 5 rol × 11 modul ruxsat matritsasi.

Eksport qilinadigan asosiy elementlar:
  - ROLE_PERMISSIONS  — rol → ruxsatlar to'plami (yagona haqiqat manbai)
  - require_permission — FastAPI dependency factory
  - has_permission     — sof yordamchi funksiya
  - get_permissions_for_role — Redis keshli ruxsatlar olish
  - apply_store_scope  — qator-darajali SQLAlchemy filtr
"""
