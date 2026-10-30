/* =====================================================
   data.js - client-side constants and question copy.
   Field names match app/models.py exactly (snake_case),
   so profile objects move between the two untouched.
   ===================================================== */
window.JH = window.JH || {};

/* ---------- pipeline ---------- */
JH.STAGES = [
  { id: 'saved',        name: 'Saved',        colour: '#8a92a0',
    blurb: 'Found it, not applied yet' },
  { id: 'applied',      name: 'Applied',      colour: '#1f3864',
    blurb: 'Sent, no reply yet' },
  { id: 'interviewing', name: 'Interviewing', colour: '#b26b00',
    blurb: 'Screening call through final round' },
  { id: 'closed',       name: 'Closed',       colour: '#1f9254',
    blurb: 'Finished - see the outcome' }
];
JH.stage = id => JH.STAGES.find(s => s.id === id) || JH.STAGES[0];

/* ---------- ageing ---------- */
JH.STALE_DAYS = 30;   // no change in this long and an open application is stale
JH.CHASE_DAYS = 14;   // default gap before the suggested chase-up

/* Closed applications never go stale - they are finished, not neglected. */
JH.isStale = function (app) {
  if (!app || app.stage === 'closed') return false;
  const since = app.updated_at || app.created_at;
  if (!since) return false;
  return Math.round((Date.now() - new Date(since).getTime()) / 86400000) >= JH.STALE_DAYS;
};

JH.daysSince = function (iso) {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
};

JH.OUTCOMES = [
  { id: '',          name: 'Still live' },
  { id: 'rejected',  name: 'Rejected by employer' },
  { id: 'ghosted',   name: 'No response' },
  { id: 'withdrawn', name: 'Withdrawn by me' },
  { id: 'declined',  name: 'Offer declined' },
  { id: 'accepted',  name: 'Offer accepted' }
];

/* ---------- honesty gradient ---------- */
JH.TECH_LEVELS = [
  { id: 'production', name: 'Production / commercial', tag: 'ok',
    blurb: 'Substantial paid production use. Safe to lead with.' },
  { id: 'project',    name: 'Hands-on project work',   tag: 'info',
    blurb: 'Real independent or client work. Gets described as project experience.' },
  { id: 'training',   name: 'Training / coursework',   tag: 'warn',
    blurb: 'Covered in a course. Mentioned only where relevant, and labelled as such.' },
  { id: 'exposure',   name: 'Exposure only',           tag: 'warn',
    blurb: 'Touched it; would not defend it in an interview. Usually left off.' },
  { id: 'never',      name: 'Do not claim',            tag: 'bad',
    blurb: 'Off limits. Named in every prompt as something never to claim.' }
];
JH.techLevel = id => JH.TECH_LEVELS.find(l => l.id === id) || JH.TECH_LEVELS[1];

/* ---------- fixed option sets ---------- */
JH.WORK_MODES   = ['Remote', 'Hybrid', 'On-site'];
JH.EMPLOYMENT   = ['Permanent', 'Contract', 'Fixed term', 'Part time', 'Freelance'];
JH.COMPANY_SIZE = ['Startup (<50)', 'Scale-up (50-500)', 'Mid (500-5k)', 'Enterprise (5k+)'];
JH.CURRENCIES   = ['GBP', 'EUR', 'USD', 'CHF', 'SEK', 'PLN', 'AUD', 'CAD'];
JH.SENIORITY    = [
  { id: 'junior', name: 'Junior' },
  { id: 'mid',    name: 'Mid' },
  { id: 'senior', name: 'Senior' },
  { id: 'lead',   name: 'Lead / principal' }
];

JH.DEFAULT_EVIDENCE_GROUPS = [
  'Backend and production systems',
  'Migration and delivery pipelines',
  'Production investigation and controlled change',
  'Data flows, integrations and stakeholders',
  'Ownership end to end'
];

JH.DEFAULT_POSITIONING = [
  'Backend engineering',
  'Technical / systems analysis',
  'Implementation, integration or customer solutions'
];

/* =====================================================
   Where the Hunt button can send a prompt.
   `q` is the query parameter that pre-fills the composer;
   `limit` is a conservative cap before the URL gets unwieldy.
   ===================================================== */
JH.AI_TOOLS = [
  { id: 'claude',     name: 'Claude',     url: 'https://claude.ai/new',            q: 'q',
    limit: 6000, note: 'Switch web search on for live adverts.' },
  { id: 'chatgpt',    name: 'ChatGPT',    url: 'https://chatgpt.com/',             q: 'q',
    limit: 4000, note: 'Switch search on for live adverts.' },
  { id: 'perplexity', name: 'Perplexity', url: 'https://www.perplexity.ai/search', q: 'q',
    limit: 2000, note: 'Searches by default. Good at finding real adverts.' },
  { id: 'gemini',     name: 'Gemini',     url: 'https://gemini.google.com/app',    q: '',
    limit: 0,    note: 'No pre-fill available - the prompt is copied for you to paste.' },
  { id: 'copy',       name: 'Clipboard only', url: '',                             q: '',
    limit: 0,    note: 'Copy and paste it wherever you like.' }
];
JH.aiTool = id => JH.AI_TOOLS.find(t => t.id === id) || JH.AI_TOOLS[0];

JH.PROMPT_KINDS = [
  { id: 'hunt',      name: 'Hunt for jobs',        needsAd: false,
    blurb: 'Find live vacancies that fit, returned in a format this app imports.' },
  { id: 'assess',    name: 'Assess one advert',    needsAd: true,
    blurb: 'Honest fit assessment against your evidence, with the gaps named.' },
  { id: 'cv',        name: 'Tailor a CV',          needsAd: true,
    blurb: 'One-page CV for a specific vacancy, using only evidence you have.' },
  { id: 'letter',    name: 'Draft a cover letter', needsAd: true,
    blurb: 'Short, role-specific letter in your style rules.' },
  { id: 'interview', name: 'Interview prep',       needsAd: true,
    blurb: 'Likely questions, the evidence to answer each, and your weak spots.' }
];
JH.promptKind = id => JH.PROMPT_KINDS.find(k => k.id === id) || JH.PROMPT_KINDS[0];

/* =====================================================
   The questionnaire.

   Ten steps is only daunting when nothing says which ones
   matter or when you may stop. Each step declares the
   phase it belongs to and what it actually buys you, so
   the sidebar reads as a map rather than a to-do list.
   ===================================================== */
JH.WIZARD_PHASES = [
  { id: 'essential', name: 'Essentials',
    blurb: 'Enough for a CV. Roughly five minutes.' },
  { id: 'strong',    name: 'Makes it tailor properly',
    blurb: 'Without these, every CV comes out the same.' },
  { id: 'polish',    name: 'Refinement',
    blurb: 'Optional. Sharpens what gets written about you.' }
];

JH.WIZARD_STEPS = [
  { id: 'contact',     name: 'Contact & location',  phase: 'essential',
    feeds: 'The header of every CV, and where the job hunt looks' },
  { id: 'core',        name: 'Core profile',        phase: 'essential',
    feeds: 'Your opening paragraph, and what the job hunt searches for' },
  { id: 'history',     name: 'Employment & study',  phase: 'essential',
    feeds: 'The Experience and Education sections' },
  { id: 'evidence',    name: 'Evidence bank',       phase: 'strong',
    feeds: 'The bullet points a tailored CV picks from' },
  { id: 'independent', name: 'Independent work',    phase: 'strong',
    feeds: 'The projects section, when a role calls for it' },
  { id: 'tech',        name: 'Technology profile',  phase: 'strong',
    feeds: 'Key skills - and how far each claim may be pushed' },
  { id: 'prefs',       name: 'What you will take',  phase: 'polish',
    feeds: 'Filters the job hunt before results reach you' },
  { id: 'position',    name: 'Positioning',         phase: 'polish',
    feeds: 'A note on which of your angles fits a given role' },
  { id: 'boundaries',  name: 'Accuracy boundaries', phase: 'polish',
    feeds: 'Claims that must never appear, in any draft' },
  { id: 'style',       name: 'Style & documents',   phase: 'polish',
    feeds: 'How drafts are written, and what format you want' }
];

/* Values the app ships with. A profile holding only these has not been
   answered, so progress must not count them. */
JH.PROFILE_DEFAULTS = {
  'core.seniority': 'mid',
  'style.english': 'British',
  'doc_prefs.font': 'Calibri',
  'doc_prefs.accent': '#1F3864',
  'doc_prefs.max_pages': 1,
  'prefs.currency': 'GBP'
};

JH.ESSENTIAL_STEPS = JH.WIZARD_STEPS.filter(s => s.phase === 'essential').map(s => s.id);

/* ---------- question copy, kept out of the render code ---------- */
JH.COPY = {
  contact: {
    lead: 'The details that go at the top of every CV, and where the job hunt should look.',
    where: 'Add each city, country or "Remote". These are what the job hunt searches.'
  },
  core: {
    lead: 'The shape of the move you are making. This drives what the hunt looks for.',
    summary: 'Plain description of the work you do. Not a pitch.',
    positioning: 'The single sentence you would open a CV with. It gets rewritten per role later.',
    targets: 'Add several. These are what the job hunt actually searches for.'
  },
  history: {
    lead: 'Roles and study. Keep the bullet points factual here — the persuasive version gets written per application.'
  },
  evidence: {
    lead: 'The bank every CV and letter draws from. Group by theme rather than by employer, so a tailored CV can pull the right five without rewriting history.',
    rule: 'Write each item as something you could defend in an interview: specific, and true.'
  },
  independent: {
    lead: 'Side projects, client work, open source. Often the strongest evidence for a move sideways.'
  },
  tech: {
    lead: 'The part that stops a generated CV overclaiming. Be strict with yourself here — every level below "production" is passed to the assistant with instructions on exactly how far it may go.'
  },
  prefs: {
    lead: 'What you would actually accept. Anything outside this gets filtered out before it reaches you.'
  },
  position: {
    lead: 'For each kind of role you are targeting, what should lead? Different evidence goes first for a backend role than for an analysis role.'
  },
  boundaries: {
    lead: 'Claims that must never appear in a generated CV, letter or answer. This list is passed verbatim into every prompt.',
    examples: [
      'Do not claim production Rust experience — it is project work only.',
      'Do not imply I have held a formal analyst title.',
      'Do not describe planned client work as completed.',
      'Do not claim industry experience in sectors I have not worked in.'
    ]
  },
  style: {
    lead: 'How things should be written, and what format you want out.',
    examples: [
      'Use British English.',
      'Avoid filler and generic enthusiasm.',
      'Prefer concrete examples over skill lists.',
      'Address a stack or title difference directly, then connect it to evidence.',
      'Keep cover letters written for the role, not as a CV summary.'
    ]
  }
};
