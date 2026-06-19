# Arxitektura — AI Agent Orchestrator

Ushbu hujjat `photo_2026-06-15_18-12-49.jpg` diagrammasining matnli tavsifi va uning ushbu repozitoriyadagi implementatsiyaga to'g'ridan-to'g'ri xaritalanishi (mapping).

## 1. Yuqori darajadagi oqim

```
┌────────────────────────────────────────────────────────────────────────┐
│  Foydalanuvchi / Stakeholder  ──(talab/vazifa)──►  So'rovni qabul qilish │
│                                                     (NLP / Intent)        │
└────────────────────────────────────────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                       ▼
   ┌──────────────────┐   ┌────────────────────────┐  ┌──────────────────┐
   │ Kuzatuv &        │   │  AI AGENT ORCHESTRATOR │  │ Qoidalar &        │
   │ Kuzatiluvchanlik │◄──┤  1 Vazifa tahlili      ├─►│ Siyosatlar        │
   │ • Loglar         │   │  2 Rejalashtirish      │  │ • Ruxsatlar       │
   │ • Metrikalar     │   │  3 Muvofiqlashtirish   │  │ • Maxfiylik       │
   │ • Tracing        │   │  4 Sifat & Xavfsizlik  │  │ • Xavfsizlik      │
   │ • Ogohlantirish  │   │  5 Natija birlashtirish│  │ • Compliance      │
   └──────────────────┘   ├────────────────────────┤  └──────────────────┘
                          │  Xotira & Kontekst     │
                          │  xotira·kontekst·qoida │
                          │  ·andoza               │
                          └────────────────────────┘
                                     │ delegatsiya
                                     ▼
   Orchestrator · Architect · Planner · Developer · Security Reviewer ·
   QA Reviewer · SRE Reviewer · Fix Developer · Tech Writer
                                     │
                                     ▼
   Git/Repo · CI/CD · Issue Tracker · Code Scanner · Test Framework ·
   Monitoring · Docs/Wiki · Communication
```

## 2. Diagramma → Implementatsiya xaritasi

| Diagrammadagi blok | Repozitoriyadagi fayl |
|---|---|
| So'rovni qabul qilish (NLP/Intent) | `.claude/skills/intent-analysis/SKILL.md` |
| Orkestrator: Vazifa tahlili | `.claude/skills/intent-analysis` + `orchestrator-agent` |
| Orkestrator: Rejalashtirish | `.claude/skills/planning/SKILL.md` |
| Orkestrator: Muvofiqlashtirish | `.claude/skills/coordination/SKILL.md` |
| Orkestrator: Sifat & Xavfsizlik | `.claude/skills/quality-security-gate/SKILL.md` |
| Orkestrator: Natija birlashtirish | `.claude/skills/result-aggregation/SKILL.md` |
| Xotira & Kontekst | `.claude/skills/memory-context/SKILL.md` |
| Kuzatuv & Kuzatiluvchanlik | `.claude/skills/observability/SKILL.md` |
| Qoidalar & Siyosatlar | `.claude/skills/policy-guard/SKILL.md` |
| Orchestrator Agent | `.claude/agents/orchestrator-agent.md` |
| Architect Agent | `.claude/agents/architect-agent.md` |
| Planner Agent | `.claude/agents/planner-agent.md` |
| Developer Agent | `.claude/agents/developer-agent.md` |
| Security Reviewer Agent | `.claude/agents/security-reviewer-agent.md` |
| QA Reviewer Agent | `.claude/agents/qa-reviewer-agent.md` |
| SRE Reviewer Agent | `.claude/agents/sre-reviewer-agent.md` |
| Fix Developer Agent | `.claude/agents/fix-developer-agent.md` |
| Tech Writer Agent | `.claude/agents/tech-writer-agent.md` |
| Butun pipeline (orkestr dvigateli) | `.claude/workflows/orchestra.js` |
| Kirish nuqtasi (buyruq) | `.claude/skills/orchestra/SKILL.md` |
| Vositalar & Integratsiyalar | `developer/fix` agentlardagi `Bash`, `Git` + CI/CD/Scanner (tashqi) |

## 3. Ijro oqimi (pipeline)

```
intake ─► architect ─► planner ─► developer
        │
        ▼
   ┌────────── PARALLEL ──────────┐
   │ security │   qa   │   sre    │
   └────────────┬─────────────────┘
                ▼
          quality-security-gate
          ┌───────────┴───────────┐
       FAIL│                   PASS│
           ▼                       ▼
     fix-developer            tech-writer
     (max 3 iteratsiya) ──┐         │
           ▲              │         ▼
           └── re-review ─┘   result-aggregation ─► yakuniy javob
```

**Cross-cutting** (har bosqichda faol): `observability` (log/metrika/trace/alert), `policy-guard` (ruxsat/maxfiylik/compliance), `memory-context` (kontekst o'qish/saqlash).

## 4. Handoff kontrakti (agentlararo)

Har bir delegatsiya quyidagi strukturada bo'ladi:
```
Maqsad:               <agent nima qilishi kerak>
Kirish:               <oldingi bosqich natijasi>
Kutilayotgan chiqish: <format/sxema>
Cheklovlar:           <policy, doiradan chiqmaslik>
```

## 5. Gate va re-planning mantig'i

- 3 ta verdikt (security/qa/sre) — barchasi `PASS` bo'lsa gate ochiq.
- Bitta `Critical`/`High` topilma ham gate'ni `FAIL` qiladi.
- `FAIL` → topilmalar `fix-developer`'ga → qayta review.
- Maksimal **3** iteratsiya; oshsa eskalatsiya (foydalanuvchiga).
