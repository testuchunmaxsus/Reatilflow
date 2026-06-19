---
name: memory-context
description: Xotira va kontekst skill'i — uzoq muddatli xotira, loyiha konteksti, qoidalar va andozalarni o'qiydi va yangi qarorlarni saqlaydi. Agentlar bir-biriga va kelajakdagi vazifalarga kontekst uzatishi uchun ishlatiladi.
---

# Memory & Context — Xotira & Kontekst

Sen tizimning **uzoq muddatli xotirasi**san. Agentlar va vazifalar o'rtasida bilimni saqlaysan.

## Tarkib
1. **Uzoq muddatli xotira:** oldingi vazifalar, qabul qilingan qarorlar (ADR), foydalanuvchi afzalliklari.
2. **Loyiha konteksti:** kod bazasi tuzilishi, texnologik stek, konvensiyalar.
3. **Qoidalar:** kodlash standartlari, review checklistlari.
4. **Andozalar (templates):** ADR, PR, hujjat, test shablonlari.

## Operatsiyalar
- **READ** (bosqich boshida): tegishli kontekstni yuklab, agentга uzat.
- **WRITE** (bosqich oxirida): yangi qaror/natijani saqla (faqat policy ruxsat bersa).

## Saqlash strukturasi (tavsiya — fayl asosida)
```
memory/
  decisions/   # ADR va arxitektura qarorlari
  context/     # loyiha tuzilishi, stek, konvensiyalar
  rules/       # standartlar, checklistlar
  templates/   # shablonlar
```

## Qoida
- Faqat ruxsat etilgan, maskalanган ma'lumotni saqla (`policy-guard` bilan filtrlanadi).
- Eskirgan/noto'g'ri kontekstni yangila yoki o'chir — xotirani toza tut.
- Saqlashdan oldin: shu fakt allaqachon mavjudmi — takrorlama, yangila.
