"""
AI Tahlil (Analytics) moduli — Faza 4.

Korxona (ishlab chiqaruvchi) uchun do'kon-ombor intellekti.

Endpointlar (prefix /analytics):
  GET /overview         — KPI kartalar
  GET /stores           — Shartnoma qilgan do'konlar + holat
  GET /geo-velocity     — Geografik savdo tezligi
  GET /expiry           — Muddati o'tgan/o'tayotgan partiyalar
  GET /products         — Top/kam sotiladigan mahsulotlar
  GET /recommendations  — AI tavsiyalar (rule-based + ixtiyoriy Claude)

MT (xavfsizlik yadrosi):
  - Korxona FAQAT o'z mahsulotlari (Product.enterprise_id == me)
  - Korxona FAQAT shartnoma qilgan do'konlari
    (Contract.supplier_enterprise_id == me AND valid_to >= today)
"""
