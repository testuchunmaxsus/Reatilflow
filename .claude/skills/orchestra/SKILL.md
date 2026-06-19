---
name: orchestra
description: AI Agent Orchestrator'ning kirish nuqtasi. Foydalanuvchi dasturiy vazifa berganda butun multi-agent pipeline'ni ishga tushiradi — talab tahlili, rejalashtirish, agentlarga delegatsiya, sifat/xavfsizlik darvozalari va natijani birlashtirish. "orkestr ishga tushir", "ushbu vazifani orkestratorga ber", "to'liq pipeline bilan bajar" kabi so'rovlarda ishlatiladi.
---

# Orchestra — AI Agent Orchestrator kirish nuqtasi

Bu skill butun multi-agent jarayonni boshqaradi. Diagrammadagi to'liq oqimni amalga oshiradi.

## Qachon ishlatiladi
- Foydalanuvchi yangi xususiyat, tuzatish yoki ko'p bosqichli dasturiy vazifa bersa.
- "Orkestr/orchestrator orqali bajar", "to'liq sifat darvozalari bilan qil" deyilganda.

## Oqim (pipeline)

1. **Intake** — `intent-analysis` skill: talabni intent va strukturalashgan vazifaga aylantir. Noaniqlik bo'lsa savol ber.
2. **Architect** — `architect-agent`'ni chaqir: ADR + dizayn ol.
3. **Plan** — `planning` skill / `planner-agent`: bajariladigan reja (DAG) tuz.
4. **Develop** — `developer-agent`: rejani implementatsiya qil.
5. **Review (parallel)** — bir vaqtda chaqir:
   - `security-reviewer-agent`
   - `qa-reviewer-agent`
   - `sre-reviewer-agent`
6. **Gate** — `quality-security-gate` skill: barcha verdiktlar PASS'mi?
   - **FAIL** → `fix-developer-agent`'ga topilmalarni ber → 5-qadamga qayt (max 3 iteratsiya).
   - **PASS** → 7-qadam.
7. **Document** — `tech-writer-agent`: hujjatlarni yangila.
8. **Aggregate** — `result-aggregation` skill: natijalarni yig', validatsiya qil, yakuniy javob ber.

## Cross-cutting (har bosqichda)
- `observability` — har bir qadamni log/trace qil, metrikalarni yoz.
- `policy-guard` — ruxsat va maxfiylik siyosatini tekshir; sirlarni maskala.
- `memory-context` — loyiha kontekstini o'qi va yangi qarorlarni saqla.

## Ishga tushirish usullari

**A) Qo'lda (subagentlar bilan):** yuqoridagi tartibda `Task` orqali agentlarni chaqir, gate mantig'iga rioya qil.

**B) Avtomatik (workflow):** `.claude/workflows/orchestra.js` deterministik pipeline'ni ishga tushir (parallel review + gate + re-plan sikli kodlangan). Buning uchun Workflow tool'i bilan:
```
Workflow({ scriptPath: ".claude/workflows/orchestra.js", args: "<foydalanuvchi vazifasi>" })
```

## Yakuniy javob
Orchestrator formatida: bajarilgan vazifa, bosqichlar/qarorlar, artefaktlar, ochiq savollar.
