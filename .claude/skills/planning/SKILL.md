---
name: planning
description: Strukturalashgan vazifa va arxitektura dizaynini agentlar ketma-ketligi va bajariladigan vazifalar rejasiga (DAG) aylantiruvchi skill. Qaysi agent kerakligini tanlaydi, bog'liqliklarni va parallel bajariladigan ishlarni belgilaydi, resurs/byudjet ajratadi.
---

# Planning — Rejalashtirish

Vazifani **kim, qanday tartibda** bajarishini belgilaysan.

## Qadamlar
1. **Agent tanlash** — vazifaga qaysi agentlar kerak (architect, developer, reviewerlar, tech-writer)?
2. **Ketma-ketlik (DAG)** — bog'liqliklarni aniqla; nima nimadan keyin.
3. **Parallellik** — mustaqil ishlarni (masalan, 3 ta review) parallel belgila.
4. **Resurs/byudjet** — har bosqichga model darajasi va urinish limitini ajrat.
5. **Gate nuqtalari** — sifat/xavfsizlik darvozalarini qayerga qo'yish.

## Chiqish formati
```
## Agentlar ketma-ketligi
intake → architect → planner → developer → [sec ∥ qa ∥ sre] → gate → (fix?) → tech-writer → aggregate

## Vazifalar (DAG)
- T1 ... (dep: yo'q)
- T2 ... (dep: T1)
- [T3, T4] parallel

## Byudjet va limitlar
- max re-plan iteratsiya: 3
- model: arxitektura=opus, ijro=sonnet
```

## Qoida
- Standart pipeline'dan kerak bo'lmagan bosqichlarni olib tashlama — gate'lar majburiy.
- Parallel ishni aniq belgila (wall-clock tejaш uchun).
