---
name: result-aggregation
description: Barcha agentlar natijalarini yig'uvchi, validatsiya qiluvchi va yagona yakuniy javobga birlashtiruvchi skill. Pipeline'ning oxirgi bosqichi — foydalanuvchiga tushunarli, to'liq va tekshirilgan natija qaytaradi.
---

# Result Aggregation — Natijalarni birlashtirish

Sen butun jarayon natijalarini **bitta ishonchli javobga** jamlaysan.

## Qadamlar
1. **Yig'ish** — architect, developer, reviewerlar, fix, tech-writer chiqishlarini to'pla.
2. **Validatsiya** — boshlang'ich maqsadlar (goals) va DoD bajarilganmi tekshir.
3. **Izchillik** — agentlar natijalari bir-biriga zid emasligini tasdiqla.
4. **Yakuniy javob** — strukturalangan, artefaktlar bilan.

## Chiqish formati
```
## Bajarilgan vazifa
<qisqacha>

## Bosqichlar va qarorlar
- Architect / Planner / Developer / Reviewlar / Fix / Docs xulosasi

## Natija / artefaktlar
<diff, fayllar, havolalar, hujjatlar>

## Maqsadlarga moslik
- [x] goal 1
- [x] goal 2

## Ochiq savollar / keyingi qadamlar
```

## Qoida
- Maqsad bajarilmagan bo'lsa — buni yashirma, ochiq ko'rsat.
- Faqat tekshirilgan, gate'dan o'tgan natijani "tayyor" deb belgila.
