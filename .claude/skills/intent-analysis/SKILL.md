---
name: intent-analysis
description: Tabiiy tildagi foydalanuvchi talabini intent va strukturalashgan vazifaga aylantiruvchi skill (NLP/Intent). Maqsad, cheklovlar va artefaktlarni ajratadi, noaniqlikda aniqlovchi savol beradi. Pipeline'ning eng birinchi bosqichi.
---

# Intent Analysis — So'rovni qabul qilish va tahlil

Foydalanuvchi talabini mashina tushunadigan, strukturalashgan vazifaga aylantirasan.

## Qadamlar
1. **Til aniqlash** — UZ/RU/EN.
2. **Intent** — foydalanuvchi nimani xohlayapti (yangi xususiyat / bug-fix / refactor / tahlil / hujjat)?
3. **Maqsadlar (goals)** — o'lchanadigan natijalar.
4. **Cheklovlar (constraints)** — texnologiya, vaqt, mosvlik, xavfsizlik.
5. **Artefaktlar** — berilgan fayllar, repo, havolalar.
6. **Noaniqlik** — agar muhim ma'lumot yetishmasa, **1-3 aniqlovchi savol** ber (taxmin qilma).

## Chiqish (strukturalashgan vazifa)
```json
{
  "language": "uz",
  "intent": "feature | bugfix | refactor | analysis | docs",
  "goals": ["..."],
  "constraints": ["..."],
  "artifacts": ["path|url"],
  "open_questions": ["..."]
}
```

## Qoida
- Noaniq talabni "to'g'rilab" yuborma — aniqlik so'ra yoki taxminlarni ochiq belgila.
