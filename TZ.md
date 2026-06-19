# TEXNIK TOPSHIRIQ (TZ)
## AI Agent Orchestrator — Ko'p agentli dasturiy ta'minot ishlab chiqish tizimi

| | |
|---|---|
| **Hujjat nomi** | AI Agent Orchestrator — Texnik Topshiriq |
| **Versiya** | 1.0 |
| **Sana** | 2026-06-15 |
| **Holati** | Tasdiqlash uchun |
| **Manba** | MindMeister xaritasi (`map/4019357122`) + arxitektura diagrammasi |
| **Til** | O'zbek (texnik atamalar — inglizcha) |

---

## 1. KIRISH

### 1.1. Hujjatning maqsadi
Ushbu texnik topshiriq **AI Agent Orchestrator** tizimini ishlab chiqish uchun barcha funktsional va nofunktsional talablarni, arxitekturani, komponentlar spetsifikatsiyasini va qabul qilish mezonlarini belgilaydi. Hujjat buyurtmachi, arxitektor, dasturchilar, QA va DevOps jamoalari uchun yagona haqiqat manbai (single source of truth) hisoblanadi.

### 1.2. Loyiha haqida qisqacha
AI Agent Orchestrator — bu foydalanuvchi (stakeholder) talabini qabul qilib, uni avtomatik tarzda tushunadigan, mayda vazifalarga bo'ladigan, rejalashtiradigan va bir nechta **ixtisoslashgan AI agentlarga** delegatsiya qiladigan tizim. Har bir agent o'z sohasiga mas'ul (arxitektura, rejalashtirish, kod yozish, xavfsizlik, test, deploy, tuzatish, hujjatlashtirish). Orkestrator agentlar ishini muvofiqlashtiradi, sifat va xavfsizlik darvozalaridan o'tkazadi, natijalarni birlashtiradi va foydalanuvchiga yakuniy javob qaytaradi.

Tizim **kuzatuvchanlik (observability)**, **siyosatlar (policies & compliance)** va **uzoq muddatli xotira (memory & context)** bilan o'ralgan hamda tashqi **vositalar va integratsiyalar** (Git, CI/CD, Issue Tracker va h.k.) bilan ishlaydi.

### 1.3. Maqsad va vazifalar
**Asosiy maqsad:** dasturiy ta'minot ishlab chiqish jarayonining to'liq siklini (talabdan tortib hujjatlashgan, testdan o'tgan, deploy'ga tayyor natijagacha) avtomatlashtiruvchi ishonchli, kuzatiluvchan va xavfsiz multi-agent platforma yaratish.

**Vazifalar:**
- Tabiiy tildagi talabni intent va aniq vazifalarga aylantirish (NLP / Intent).
- Vazifani sub-vazifalarga bo'lib, optimal reja va agentlar ketma-ketligini tuzish.
- Vazifalarni mos agentlarga delegatsiya qilish va holatni real vaqtda kuzatish.
- Har bir bosqichda sifat, xavfsizlik va compliance darvozalarini majburiy o'tkazish.
- Natijalarni yig'ish, validatsiya qilish va yagona javobga birlashtirish.
- To'liq audit izi (loglar, metrikalar, tracing) va xatolik hodisalarida qayta rejalashtirish.

### 1.4. Ko'lam (Scope)
**Kiradi:**
- Orkestrator yadrosi va 9 ta ixtisoslashgan agent.
- Intent qabul qilish qatlami, xotira va kontekst boshqaruvi.
- Kuzatuvchanlik, siyosat (policy) va vositalar integratsiya qatlamlari.
- Pipeline (vazifa oqimi) va orkestrlovchi mantiq.

**Kirmaydi (kelajak bosqichlari):**
- Ko'p ijarachili (multi-tenant) bilingva UI portal.
- Tashqi mijozlarga ochiq SaaS billing.
- Domenga xos (masalan, faqat mobil yoki faqat ML) maxsus agentlar — bu kengaytma sifatida qo'shiladi.

---

## 2. ATAMALAR LUG'ATI

| Atama | Izoh |
|---|---|
| **Orkestrator (Orchestrator)** | Butun jarayonni boshqaruvchi markaziy yadro; agentlarni tanlaydi, muvofiqlashtiradi va natijalarni birlashtiradi. |
| **Agent** | Bitta ixtisoslikka ega avtonom AI ijrochi (masalan, Developer Agent). |
| **Skill** | Qayta ishlatiladigan qobiliyat/protsedura (masalan, intent tahlili, rejalashtirish). |
| **Intent** | Foydalanuvchi talabidan ajratib olingan maqsad/niyat. |
| **Delegatsiya** | Vazifani aniq agentga topshirish. |
| **Gate (Darvoza)** | O'tish uchun majburiy shart (sifat/xavfsizlik tekshiruvi). |
| **Pipeline** | Vazifaning agentlar orqali o'tish ketma-ketligi. |
| **Observability** | Loglar, metrikalar, tracing va ogohlantirishlar orqali tizim holatini kuzatish. |
| **Context/Memory** | Loyiha konteksti, qoidalar va andozalarni saqlovchi qatlam. |
| **Handoff** | Bir agentdan ikkinchisiga ish natijasini topshirish. |

---

## 3. UMUMIY ARXITEKTURA

Tizim 6 ta mantiqiy qatlamdan iborat:

```
┌───────────────────────────────────────────────────────────────────┐
│ 1) KIRISH QATLAMI                                                   │
│    Foydalanuvchi/Stakeholder → So'rovni qabul qilish (NLP/Intent)   │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─────────────┐   ┌───────────────────────────────────┐   ┌──────────────┐
│ KUZATUV &   │   │ 2) AI AGENT ORCHESTRATOR (yadro)   │   │ QOIDALAR &   │
│ KUZATILUV-  │◄──│  • Vazifa tahlili                  │──►│ SIYOSATLAR   │
│ CHANLIK     │   │  • Rejalashtirish                  │   │ • Ruxsatlar  │
│ • Loglar    │   │  • Muvofiqlashtirish               │   │ • Maxfiylik  │
│ • Metrikalar│   │  • Sifat & Xavfsizlik              │   │ • Xavfsizlik │
│ • Tracing   │   │  • Natija birlashtirish            │   │ • Compliance │
│ • Alert     │   │ ───────────────────────────────── │   └──────────────┘
└─────────────┘   │ 3) XOTIRA & KONTEKST              │
                  │  uzoq muddatli xotira • loyiha    │
                  │  konteksti • qoidalar • andozalar │
                  └───────────────────────────────────┘
                              │  (delegatsiya)
┌───────────────────────────────────────────────────────────────────┐
│ 4) IXTISOSLASHGAN AGENTLAR (9 ta)                                   │
│  Orchestrator · Architect · Planner · Developer · Security Reviewer │
│  · QA Reviewer · SRE Reviewer · Fix Developer · Tech Writer         │
└───────────────────────────────────────────────────────────────────┘
                              │
┌───────────────────────────────────────────────────────────────────┐
│ 5) VOSITALAR & INTEGRATSIYALAR                                      │
│  Git/Repo · CI/CD · Issue Tracker · Code Scanner · Test Framework   │
│  · Monitoring · Docs/Wiki · Communication                           │
└───────────────────────────────────────────────────────────────────┘
```

### 3.1. Ma'lumotlar oqimi (yuqori daraja)
1. Stakeholder talab/vazifa kiritadi.
2. Kirish qatlami NLP orqali intent va dastlabki vazifani ajratadi.
3. Orkestrator vazifani tahlil qiladi → reja tuzadi → agentlarni tanlaydi.
4. Vazifalar agentlarga delegatsiya qilinadi; har bir handoff'da policy va observability qatlamlari ishlaydi.
5. Sifat & Xavfsizlik darvozalari o'tkaziladi; muammo bo'lsa — Fix Developer'ga qaytariladi (qayta rejalashtirish).
6. Natijalar yig'iladi, validatsiya qilinadi va yakuniy javob shakllantiriladi.
7. Butun jarayon xotiraga yoziladi (kontekst keyingi vazifalar uchun).

---

## 4. KOMPONENTLAR SPETSIFIKATSIYASI

### 4.1. Kirish qatlami — So'rovni qabul qilish
- **Vazifa:** tabiiy tildagi talabni qabul qilish, intent va asosiy parametrlarni ajratish (NLP / Intent recognition).
- **Kirish:** matn (talab/vazifa), ixtiyoriy fayllar/kontekst.
- **Chiqish:** strukturalashgan vazifa obyekti `{intent, goals, constraints, artifacts}`.
- **Talablar:** noaniq talablarda aniqlovchi savol berish; tilni avtomatik aniqlash (UZ/RU/EN).

### 4.2. AI Agent Orchestrator (yadro) — 5 qobiliyat
| # | Qobiliyat | Kichik vazifalar |
|---|---|---|
| 1 | **Vazifa tahlili** | Talabni tushunish; vazifani sub-vazifalarga bo'lish |
| 2 | **Rejalashtirish** | Agentlarni tanlash; ketma-ketlikni belgilash; resurslarni ajratish |
| 3 | **Muvofiqlashtirish** | Vazifalarni delegatsiya qilish; holatni kuzatish; qayta rejalashtirish |
| 4 | **Sifat & Xavfsizlik** | Xavfsizlik tekshiruvi; sifat nazorati; muvofiqlik (compliance) qoidalari |
| 5 | **Natija birlashtirish** | Natijalarni yig'ish; validatsiya qilish; yakuniy javob |

**Talablar:**
- Orkestrator agentlarga to'g'ridan-to'g'ri kod yozmaydi — faqat boshqaradi va delegatsiya qiladi.
- Har bir qaror (qaysi agent, qanday ketma-ketlik) log va tracing'da qayd etiladi.
- Xatolik yoki gate "fail" bo'lsa, qayta rejalashtirish (re-planning) sikli ishga tushadi (cheklangan urinishlar bilan).

### 4.3. Xotira & Kontekst
- **Uzoq muddatli xotira:** oldingi vazifalar, qarorlar, foydalanuvchi afzalliklari.
- **Loyiha konteksti:** kod bazasi tuzilishi, texnologik stek, konvensiyalar.
- **Qoidalar va andozalar:** kodlash standartlari, hujjat shablonlari, review checklistlari.
- **Talab:** xotira faqat ruxsat etilgan ma'lumotni saqlaydi (policy bilan filtrlanadi); PII maxfiyligi.

### 4.4. Kuzatuv & Kuzatiluvchanlik (Observability)
- **Loglar:** har bir agent harakati, kirish/chiqish (sensitive ma'lumot maskalangan).
- **Metrikalar:** vazifa davomiyligi, muvaffaqiyat darajasi, gate "pass/fail" nisbati, token/resurs sarfi.
- **Tracing:** uchidan-uchiga (end-to-end) so'rov izi — qaysi agent qancha vaqt sarfladi.
- **Ogohlantirishlar (Alerts):** gate fail, timeout, takroriy xatolik, byudjetdan oshib ketish.

### 4.5. Qoidalar & Siyosatlar (Policies & Compliance)
- **Ruxsatlar (Permissions):** qaysi agent qaysi vositaga/repoga/fayl tizimiga kira oladi (least privilege).
- **Maxfiylik (Privacy):** PII/maxfiy ma'lumotlarni aniqlash va maskalash.
- **Xavfsizlik (Security):** kiruvchi/chiquvchi ma'lumot validatsiyasi, secret leak'ning oldini olish.
- **Compliance:** litsenziya, ma'lumotlarni saqlash siyosati, audit talablari.

### 4.6. Vositalar & Integratsiyalar
| Vosita | Maqsad |
|---|---|
| **Git / Repo** | Kod bilan ishlash, branch, commit, PR |
| **CI/CD** | Build, test, deploy pipeline |
| **Issue Tracker** | Vazifa/bug kuzatuvi (Jira/GitHub Issues) |
| **Code Scanner** | SAST, sirlar (secrets), bog'liqlik (dependency) tekshiruvi |
| **Test Framework** | Unit/integration/e2e testlarni ishga tushirish |
| **Monitoring** | Runtime metrikalar va alertlar |
| **Docs / Wiki** | Hujjatlarni nashr qilish |
| **Communication** | Slack/Telegram/email orqali xabar berish |

---

## 5. AGENTLAR SPETSIFIKATSIYASI (9 ta)

Quyidagi jadval har bir agentning mas'uliyati, kirish/chiqishi va asosiy vositalarini belgilaydi.

| # | Agent | Mas'uliyat | Kirish | Chiqish | Asosiy vositalar |
|---|---|---|---|---|---|
| 1 | **Orchestrator Agent** | Jarayonni boshqarish, delegatsiya, birlashtirish | Strukturalashgan vazifa | Yakuniy natija + audit izi | Barchasi (koordinatsiya) |
| 2 | **Architect Agent** | Arxitektura qarorlari (ADR), texnik dizayn | Talab + kontekst | Dizayn hujjati, ADR, komponent chizmasi | Repo o'qish, Docs |
| 3 | **Planner Agent** | Ish rejasini, bosqichlar va ketma-ketlikni tuzish | Dizayn | Bajariladigan vazifalar ro'yxati (DAG) | Issue Tracker |
| 4 | **Developer Agent** | Kod yozish, implementatsiya | Reja + dizayn | Kod o'zgarishlari (diff/PR) | Git, Editor, Test |
| 5 | **Security Reviewer Agent** | Xavfsizlik tekshiruvi | Kod diff | Xavfsizlik hisobotcha + verdict | Code Scanner (SAST) |
| 6 | **QA Reviewer Agent** | Test va sifat nazorati | Kod diff | Test natijalari + bug hisoboti | Test Framework |
| 7 | **SRE Reviewer Agent** | Deploy tayyorligi, ishonchlilik | Kod + config | Deploy-readiness verdict | CI/CD, Monitoring |
| 8 | **Fix Developer Agent** | Topilgan muammolarni tuzatish | Review topilmalari | Tuzatilgan kod (diff) | Git, Editor, Test |
| 9 | **Tech Writer Agent** | Hujjatlashtirish | Yakuniy kod + qarorlar | README, API docs, changelog | Docs/Wiki |

### 5.1. Agentlararo aloqa (pipeline)
```
Intake ──► Architect ──► Planner ──► Developer ──┐
                                                 │
                            ┌────────────────────┴────────────────────┐
                            ▼                ▼                ▼
                   Security Reviewer    QA Reviewer    SRE Reviewer   (PARALLEL)
                            └────────────────┬───────────────┘
                                             ▼
                                    Gate: barchasi PASS?
                                       │             │
                                   YO'Q ▼         HA  ▼
                              Fix Developer ──►  Tech Writer ──► Orchestrator (aggregate) ──► Yakuniy javob
                                   │  (qayta review sikli, max N urinish)
                                   └──────────────────────────────┘
```

### 5.2. Re-planning (qayta rejalashtirish) qoidalari
- Har qanday gate "fail" bo'lsa → Fix Developer'ga topiladi va review qayta o'tkaziladi.
- Maksimal urinishlar: **3** (sozlanadi). Limit oshsa → eskalatsiya (foydalanuvchiga qaytarish).
- Har bir sikl observability'da alohida iteratsiya sifatida qayd etiladi.

---

## 6. SKILL'LAR (qayta ishlatiladigan qobiliyatlar)

| Skill | Tegishli qatlam | Vazifa |
|---|---|---|
| `intent-analysis` | Kirish | Talabni intent va vazifaga aylantirish |
| `planning` | Orkestrator | Reja, agent tanlash, DAG tuzish |
| `coordination` | Orkestrator | Delegatsiya, holat kuzatish, re-planning |
| `quality-security-gate` | Orkestrator | Sifat/xavfsizlik/compliance darvozasi |
| `result-aggregation` | Orkestrator | Natijalarni yig'ish va validatsiya |
| `observability` | Cross-cutting | Log/metrika/tracing/alert |
| `policy-guard` | Cross-cutting | Ruxsat, maxfiylik, xavfsizlik siyosati |
| `memory-context` | Cross-cutting | Xotira va kontekstni o'qish/yozish |
| `orchestra` | Entry point | Butun pipeline'ni ishga tushiruvchi buyruq |

---

## 7. NOFUNKTSIONAL TALABLAR

| Toifa | Talab |
|---|---|
| **Ishonchlilik** | Gate fail va xatoliklarda avtomatik retry/re-plan; idempotent qadamlar. |
| **Kuzatiluvchanlik** | 100% qadamlar log/trace'da; har bir gate natijasi qayd etilishi shart. |
| **Xavfsizlik** | Least-privilege; sirlar hech qachon log/chiqishga tushmaydi; SAST majburiy. |
| **Kengaytiriluvchanlik** | Yangi agent/skill plug-in tarzida qo'shiladi (kontrakt o'zgarmaydi). |
| **Unumdorlik** | Mustaqil reviewlar parallel ishlaydi; resurs/token byudjeti nazorat qilinadi. |
| **Audit** | Har bir vazifa uchun to'liq, qayta tiklanadigan (reproducible) audit izi. |
| **Maxfiylik** | PII maskalash; ma'lumotni saqlash muddati siyosatga bo'ysunadi. |

---

## 8. TEXNOLOGIK STEK (tavsiya)

> Tizim Claude Code muhitida amalga oshiriladi (ushbu loyiha aynan shu tarzda yetkazib beriladi).

- **Orkestratsiya:** Claude Code subagentlar (`.claude/agents/*.md`) + Workflow pipeline (`.claude/workflows/orchestra.js`).
- **Qobiliyatlar:** Claude Code Skills (`.claude/skills/*/SKILL.md`).
- **Model:** Claude Opus 4.8 (murakkab tahlil/arxitektura) + Sonnet 4.6 (rutina ijro).
- **Vositalar:** Git, CI/CD (GitHub Actions), Code Scanner (Semgrep/Trivy), Test Framework (loyihaga mos), Monitoring.
- **Saqlash:** fayl asosidagi xotira (`memory/`) + loyiha konteksti.

---

## 9. IMPLEMENTATSIYA BOSQICHLARI (Roadmap)

| Bosqich | Mazmun | Natija |
|---|---|---|
| **B0 — Poydevor** | Repo, kontrakt sxemalari, policy va memory karkasi | Karkas tayyor |
| **B1 — Yadro** | Orchestrator + intake + planning + coordination skill | Bitta vazifani uchidan-uchiga o'tkazish |
| **B2 — Agentlar** | 9 ta agent ta'rifi va handoff kontraktlari | To'liq pipeline ishlaydi |
| **B3 — Darvozalar** | Sifat/xavfsizlik/SRE gate + re-planning sikli | Sifat kafolati |
| **B4 — Observability** | Log/metrika/trace/alert integratsiyasi | Kuzatiluvchanlik |
| **B5 — Integratsiyalar** | Git/CI-CD/Issue/Scanner/Docs ulanishi | Real vositalar bilan ishlash |
| **B6 — Qattiqlashtirish** | Xavfsizlik, masshtab, hujjatlar, pilot | Production-ready |

---

## 10. QABUL QILISH MEZONLARI (Acceptance Criteria)

1. **Uchidan-uchiga oqim:** foydalanuvchi talabi → arxitektura → reja → kod → review → fix → hujjat → yakuniy javob to'liq avtomatik bajariladi.
2. **9 agent** ham mavjud, har biri o'z kontraktiga (kirish/chiqish) rioya qiladi.
3. **Gate'lar majburiy:** xavfsizlik/sifat/SRE darvozasi "fail" bo'lsa, pipeline Fix Developer'ga qaytadi va qayta tekshiradi.
4. **Re-planning:** maksimal urinishlardan keyin to'g'ri eskalatsiya bo'ladi.
5. **Observability:** har bir bajarilgan vazifa uchun to'liq log + trace + metrika mavjud.
6. **Policy:** ruxsatsiz vositaga kirish bloklanadi; sirlar chiqishda ko'rinmaydi.
7. **Xotira:** loyiha konteksti keyingi vazifada qayta ishlatiladi.
8. **Kengaytirish:** yangi agent qo'shilganda mavjud kontraktlar buzilmaydi.

---

## 11. RISKLAR VA YUMSHATISH CHORALARI

| Risk | Ta'sir | Yumshatish |
|---|---|---|
| Cheksiz re-planning sikli | Resurs sarfi | Qattiq urinish limiti + byudjet nazorati |
| Gate'larni chetlab o'tish | Sifat/xavfsizlik | Gate'larni majburiy va auditlanadigan qilish |
| Sirlar log'ga tushishi | Xavfsizlik buzilishi | Avtomatik maskalash + secret scanner |
| Agentlar o'rtasida kontekst yo'qolishi | Xato natija | Strukturalashgan handoff kontraktlari |
| Noaniq talab | Noto'g'ri yo'nalish | Intake bosqichida aniqlovchi savollar |

---

## 12. ILOVALAR

- **A ilova:** Arxitektura diagrammasi — `photo_2026-06-15_18-12-49.jpg` va `ARCHITECTURE.md`.
- **B ilova:** Agent ta'riflari — `.claude/agents/`.
- **C ilova:** Skill ta'riflari — `.claude/skills/`.
- **D ilova:** Orkestrlovchi pipeline — `.claude/workflows/orchestra.js`.
- **E ilova:** Foydalanish qo'llanmasi — `README.md`.

---

*Ushbu TZ MindMeister loyiha xaritasi va arxitektura diagrammasi asosida tayyorlandi. Implementatsiya ushbu repozitoriyda berilgan agent, skill va workflow fayllari orqali amalga oshirilgan.*
