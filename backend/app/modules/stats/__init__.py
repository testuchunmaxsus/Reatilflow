"""
Statistika moduli — T22 Stats/Hisobotlar.

Read-only reporting: mavjud jadvallardan o'qiydi (yangi model/migratsiya yo'q).

Endpointlar:
  GET /stats/sales?from=&to=&branch_id=&group_by=     — savdo statistikasi
  GET /stats/delivery?from=&to=&courier_id=&group_by= — yetkazish statistikasi
  GET /stats/finance?from=&to=&branch_id=             — moliyaviy statistika

ADR §3.4:
  - Non-financial hisobotlar (sales, delivery) → read replica (get_db_replica)
  - Moliyaviy hisobot (finance) → primary DB (get_db) — replikatsiya kechikishini oldini olish
"""
