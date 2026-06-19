---
name: coordination
description: Vazifalarni agentlarga delegatsiya qiluvchi, ularning holatini kuzatuvchi va kerak bo'lsa qayta rejalashtiruvchi (re-planning) skill. Handoff kontraktlarini boshqaradi va gate FAIL bo'lganda fix → re-review siklini yuritadi.
---

# Coordination — Muvofiqlashtirish

Reja bo'yicha agentlarni ishga solasan va jarayonni jonli boshqarasan.

## Qadamlar
1. **Delegatsiya** — har bir agentga aniq **handoff kontrakti** ber:
   ```
   Maqsad: ...
   Kirish: ...
   Kutilayotgan chiqish (format): ...
   Cheklovlar: ...
   ```
2. **Holatni kuzatish** — qaysi vazifa qaysi holatda (pending/in-progress/done/failed).
3. **Qayta rejalashtirish** — gate FAIL yoki agent xatosida:
   - Topilmalarni `fix-developer-agent`'ga yo'naltir.
   - Review'ni qayta o'tkaz.
   - **Max 3 iteratsiya**; oshsa eskalatsiya.
4. **Blokirovkalar** — bog'liqlik tugamaguncha keyingi vazifani boshlama.

## Re-planning qoidasi
```
gate == FAIL && iteratsiya < 3  → fix-developer → re-review
gate == FAIL && iteratsiya >= 3 → STOP + foydalanuvchiga eskalatsiya
gate == PASS                    → keyingi bosqich (tech-writer)
```

## Qoida
- Har bir handoff va holat o'zgarishini `observability` orqali qayd et.
- Kontekstni yo'qotma — har bir agentga oldingi bosqich natijasini uzat.
