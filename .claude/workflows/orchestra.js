export const meta = {
  name: 'orchestra',
  description: 'AI Agent Orchestrator — talab tahlilidan deploy-tayyor, hujjatlangan natijagacha to\'liq multi-agent pipeline (architect → plan → develop → parallel review → gate/fix → docs → aggregate).',
  phases: [
    { title: 'Intake', detail: 'NLP/intent — talabni strukturalashgan vazifaga aylantirish' },
    { title: 'Architect', detail: 'arxitektura qarori (ADR) va dizayn', model: 'opus' },
    { title: 'Plan', detail: 'bajariladigan vazifalar rejasi (DAG)' },
    { title: 'Develop', detail: 'rejaga muvofiq kod yozish' },
    { title: 'Review', detail: 'security ∥ qa ∥ sre — parallel tekshiruv' },
    { title: 'Fix', detail: 'gate FAIL bo\'lsa muammolarni tuzatish (max 3 iteratsiya)' },
    { title: 'Document', detail: 'README/CHANGELOG/API hujjatlari' },
    { title: 'Aggregate', detail: 'natijalarni yig\'ish va yakuniy javob' },
  ],
}

// ---- Strukturalashgan chiqish sxemalari ----------------------------------

const INTENT_SCHEMA = {
  type: 'object',
  required: ['intent', 'goals', 'open_questions'],
  properties: {
    language: { type: 'string' },
    intent: { type: 'string', enum: ['feature', 'bugfix', 'refactor', 'analysis', 'docs'] },
    goals: { type: 'array', items: { type: 'string' } },
    constraints: { type: 'array', items: { type: 'string' } },
    artifacts: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['dimension', 'verdict', 'findings', 'summary'],
  properties: {
    dimension: { type: 'string', enum: ['security', 'qa', 'sre'] },
    verdict: { type: 'string', enum: ['PASS', 'FAIL'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'issue'],
        properties: {
          severity: { type: 'string', enum: ['Critical', 'High', 'Medium', 'Low'] },
          location: { type: 'string' },
          issue: { type: 'string' },
          recommendation: { type: 'string' },
        },
      },
    },
    summary: { type: 'string' },
  },
}

// ---- Yordamchi funksiyalar ------------------------------------------------

const MAX_REPLAN = 3

// Uchta mustaqil review'ni PARALLEL ishga tushirish (gate uchun barchasi kerak — barrier o'rinli).
function runReviews(changeSummary, round) {
  const reviewers = [
    { dim: 'security', agentType: 'security-reviewer-agent', focus: 'zaifliklar, secret leak, injection, authn/authz' },
    { dim: 'qa', agentType: 'qa-reviewer-agent', focus: 'testlar, qamrov, edge-case, regressiya, DoD' },
    { dim: 'sre', agentType: 'sre-reviewer-agent', focus: 'deploy tayyorligi, migratsiya, rollback, kuzatuvchanlik' },
  ]
  return parallel(reviewers.map(r => () =>
    agent(
      `Quyidagi kod o'zgarishini ${r.focus} bo'yicha tekshir va PASS/FAIL verdikt ber.\n\n` +
      `O'zgarish (raund ${round}):\n${changeSummary}`,
      { label: `review:${r.dim}#${round}`, phase: 'Review', agentType: r.agentType, schema: VERDICT_SCHEMA },
    )
  ))
}

function gatePassed(verdicts) {
  return verdicts.filter(Boolean).length === 3 &&
    verdicts.filter(Boolean).every(v => v.verdict === 'PASS')
}

function collectFailFindings(verdicts) {
  return verdicts.filter(Boolean)
    .filter(v => v.verdict === 'FAIL')
    .flatMap(v => v.findings.map(f => `[${v.dimension}/${f.severity}] ${f.location || ''} ${f.issue} → ${f.recommendation || ''}`))
}

// ---- PIPELINE -------------------------------------------------------------

const task = (typeof args === 'string' && args.trim()) ? args : (args && args.task) || ''
if (!task) {
  log('⚠️  Vazifa berilmadi. Workflow({ scriptPath, args: "<vazifa matni>" }) tarzida ishga tushiring.')
}

// 1) INTAKE — intent tahlili
phase('Intake')
const intent = await agent(
  `So'rovni qabul qil va strukturalashgan vazifaga aylantir. NLP/intent ajrat. Noaniqlik bo'lsa open_questions'ga yoz.\n\nFoydalanuvchi talabi:\n${task}`,
  { label: 'intake', schema: INTENT_SCHEMA },
)
if (intent && intent.open_questions && intent.open_questions.length) {
  log(`❓ Aniqlovchi savollar mavjud: ${intent.open_questions.join(' | ')}`)
}

const goalsText = intent ? `Maqsadlar: ${(intent.goals || []).join('; ')}\nCheklovlar: ${(intent.constraints || []).join('; ')}` : task

// 2) ARCHITECT — ADR va dizayn
phase('Architect')
const design = await agent(
  `Quyidagi vazifa uchun arxitektura qarorini (ADR) va dizaynni yoz: variantlar, tanlov, trade-off, komponentlar va ma'lumotlar oqimi.\n\n${goalsText}`,
  { label: 'architect', phase: 'Architect', agentType: 'architect-agent' },
)

// 3) PLAN — bajariladigan reja (DAG)
phase('Plan')
const plan = await agent(
  `Quyidagi dizaynni bajariladigan, tartiblangan vazifalar rejasiga (DAG) aylantir. Bog'liqlik va parallel ishlarni belgila, har biriga DoD ber.\n\nDizayn:\n${design}`,
  { label: 'planner', phase: 'Plan', agentType: 'planner-agent' },
)

// 4) DEVELOP — implementatsiya
phase('Develop')
let work = await agent(
  `Quyidagi rejani implementatsiya qil. Mavjud konvensiyalarga rioya qil, testlar yoz, o'zgarishlarni aniq xulosa bilan qaytar.\n\nReja:\n${plan}`,
  { label: 'developer', phase: 'Develop', agentType: 'developer-agent' },
)

// 5–6) REVIEW + GATE + FIX (re-planning sikli)
let round = 1
let verdicts = await runReviews(work, round)
while (!gatePassed(verdicts) && round < MAX_REPLAN) {
  const findings = collectFailFindings(verdicts)
  log(`🚧 GATE FAIL (raund ${round}). ${findings.length} ta topilma → fix-developer.`)
  phase('Fix')
  const fix = await agent(
    `Quyidagi review topilmalarini minimal o'zgarish bilan tuzat. Faqat ko'rsatilgan muammolarni hal qil, testlarni qayta ishga tushir.\n\nTopilmalar:\n- ${findings.join('\n- ')}`,
    { label: `fix#${round}`, phase: 'Fix', agentType: 'fix-developer-agent' },
  )
  work = `${work}\n\n--- Fix raund ${round} ---\n${fix}`
  round++
  verdicts = await runReviews(work, round)
}

const gateOk = gatePassed(verdicts)
log(gateOk ? `✅ GATE PASS (raund ${round}).` : `⛔ GATE hali ham FAIL — ${MAX_REPLAN} iteratsiya tugadi, eskalatsiya kerak.`)

// 7) DOCUMENT — hujjatlashtirish (faqat gate PASS bo'lsa)
let docs = null
if (gateOk) {
  phase('Document')
  docs = await agent(
    `Quyidagi yakuniy ish uchun hujjatlarni yangila: README, CHANGELOG, kerak bo'lsa API/migratsiya qo'llanmasi. Aniq va misollar bilan.\n\nIsh xulosasi:\n${work}\n\nDizayn:\n${design}`,
    { label: 'tech-writer', phase: 'Document', agentType: 'tech-writer-agent' },
  )
}

// 8) AGGREGATE — natijalarni birlashtirish
phase('Aggregate')
return {
  task,
  intent,
  design,
  plan,
  work,
  reviews: verdicts.filter(Boolean),
  gate: gateOk ? 'PASS' : 'FAIL',
  replan_rounds: round,
  docs,
  escalation: gateOk ? null : `Gate ${MAX_REPLAN} iteratsiyadan keyin ham FAIL. Ochiq topilmalar: ${collectFailFindings(verdicts).join(' | ')}`,
}
