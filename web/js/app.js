/* =====================================================
   app.js - the whole frontend.

   The questionnaire is driven by a declarative schema and
   one generic renderer, so adding a question is a line of
   data rather than a block of DOM code.
   ===================================================== */
(function (JH) {
  'use strict';

  const U = JH.ui, api = JH.api;
  const el = U.el, $ = U.$;

  let user = null;
  let profile = null;
  let apps = [];
  let completeness = null;
  let saveTimer = null;
  let step = 'contact';

  /* ---------- dotted path access ---------- */
  const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
  const set = (obj, path, value) => {
    const keys = path.split('.');
    const last = keys.pop();
    keys.reduce((o, k) => (o[k] = o[k] || {}), obj)[last] = value;
  };

  /* =====================================================
     Question schema
     ===================================================== */
  const C = JH.COPY;

  const JOB_ITEM = [
    { k: 'title',    l: 'Job title',  t: 'text' },
    { k: 'company',  l: 'Employer',   t: 'text' },
    { k: 'start',    l: 'Start',      t: 'month' },
    { k: 'end',      l: 'End',        t: 'month', h: 'Leave blank if this is your current role' },
    { k: 'current',  l: 'This is my current role', t: 'bool' },
    { k: 'location', l: 'Location',   t: 'text' },
    { k: 'note',     l: 'What the job actually was', t: 'area' },
    { k: 'bullets',  l: 'Factual bullet points', t: 'lines', h: 'Plain facts. The persuasive version gets written per application.' }
  ];

  const SCHEMA = {
    contact: { lead: C.contact.lead, fields: [
      { k: 'identity.name',      l: 'Full name', t: 'text' },
      { k: 'identity.email',     l: 'Email', t: 'email' },
      { k: 'identity.phone',     l: 'Phone', t: 'tel', h: 'Include the country code if you are applying abroad.' },
      { k: 'identity.portfolio', l: 'Portfolio or personal site', t: 'url' },
      { k: 'identity.linkedin',  l: 'LinkedIn', t: 'url' },
      { k: 'identity.github',    l: 'GitHub or equivalent', t: 'url' },
      { k: 'prefs.locations',    l: 'Where do you want to work?', t: 'chips', h: C.contact.where }
    ]},

    core: { lead: C.core.lead, fields: [
      { k: 'core.summary',      l: 'In two or three sentences, what do you actually do?', t: 'area', h: C.core.summary },
      { k: 'core.positioning',  l: 'Your one-line positioning statement', t: 'area', h: C.core.positioning },
      { k: 'core.target_roles', l: 'What job titles are you targeting?', t: 'chips', h: C.core.targets },
      { k: 'core.years',        l: 'Years of relevant experience', t: 'text' },
      { k: 'core.seniority',    l: 'Level you are aiming at', t: 'select', options: JH.SENIORITY }
    ]},

    history: { lead: C.history.lead, fields: [
      { k: 'employment', l: 'Employment', t: 'repeat', item: JOB_ITEM,
        title: j => [j.title, j.company].filter(Boolean).join(' — ') || 'New role',
        add: 'Add a role' },
      { k: 'education', l: 'Education and training', t: 'repeat', add: 'Add a qualification',
        title: e => [e.qualification, e.school].filter(Boolean).join(', ') || 'New qualification',
        item: [
          { k: 'qualification', l: 'Qualification', t: 'text' },
          { k: 'field',  l: 'Subject', t: 'text' },
          { k: 'school', l: 'Institution', t: 'text' },
          { k: 'start',  l: 'From', t: 'month' },
          { k: 'end',    l: 'To', t: 'month' },
          { k: 'note',   l: 'What it covered', t: 'area' }
        ]}
    ]},

    evidence: { lead: C.evidence.lead, fields: [
      { k: 'evidence', l: '', t: 'repeat', add: 'Add a theme', open: true,
        // A seeded theme name is scaffolding, not an answer.
        scaffold: 'group',
        title: g => g.group || 'New theme',
        count: g => (g.items || []).filter(Boolean).length,
        item: [
          { k: 'group', l: 'Theme', t: 'text' },
          { k: 'items', l: 'Evidence', t: 'lines', h: C.evidence.rule }
        ]}
    ]},

    independent: { lead: C.independent.lead, fields: [
      { k: 'independent', l: '', t: 'repeat', add: 'Add a project',
        title: p => p.name || 'New project',
        item: [
          { k: 'name', l: 'Name', t: 'text' },
          { k: 'url',  l: 'Link', t: 'url' },
          { k: 'description', l: 'What it is', t: 'area' },
          { k: 'bullets', l: 'What it evidences', t: 'lines' },
          { k: 'tech', l: 'Built with', t: 'chips' }
        ]}
    ]},

    tech: { lead: C.tech.lead, fields: [
      { k: 'tech', l: '', t: 'repeat', add: 'Add a technology', compact: true,
        title: t => (t.area || 'New entry') + (t.level ? '  ·  ' + JH.techLevel(t.level).name : ''),
        item: [
          { k: 'area', l: 'Technology or skill area', t: 'text' },
          { k: 'level', l: 'How strong is the claim, honestly?', t: 'select',
            options: JH.TECH_LEVELS, describe: id => JH.techLevel(id).blurb },
          { k: 'description', l: 'How you would describe it', t: 'text',
            h: 'e.g. "commercial backend and microservice work" or "independent pipeline project"' }
        ]}
    ]},

    prefs: { lead: C.prefs.lead, fields: [
      { k: 'prefs.work_modes',    l: 'Working pattern', t: 'toggles', options: JH.WORK_MODES },
      { k: 'prefs.employment',    l: 'Contract type', t: 'toggles', options: JH.EMPLOYMENT },
      { k: 'prefs.company_sizes', l: 'Company size', t: 'toggles', options: JH.COMPANY_SIZE },
      { k: 'prefs.salary_min',    l: 'Salary from', t: 'text', row: 'pay' },
      { k: 'prefs.salary_max',    l: 'Salary to', t: 'text', row: 'pay' },
      { k: 'prefs.currency',      l: 'Currency', t: 'select', options: JH.CURRENCIES, row: 'pay' },
      { k: 'prefs.notice_period', l: 'Notice period', t: 'text', row: 'when' },
      { k: 'prefs.earliest_start',l: 'Earliest start', t: 'text', row: 'when' },
      { k: 'prefs.avoid_sectors', l: 'Sectors to avoid', t: 'chips' },
      { k: 'prefs.dealbreakers',  l: 'Dealbreakers', t: 'lines',
        h: 'Things that rule a role out regardless of how good it looks.' }
    ]},

    position: { lead: C.position.lead, fields: [
      { k: 'positioning', l: '', t: 'repeat', add: 'Add a role type', open: true,
        scaffold: 'role_type',
        title: p => p.role_type || 'New role type',
        item: [
          { k: 'role_type', l: 'Role type', t: 'text' },
          { k: 'guidance',  l: 'What should lead for this kind of role?', t: 'area',
            h: 'Which evidence goes first, and what to be careful not to imply.' }
        ]}
    ]},

    boundaries: { lead: C.boundaries.lead, fields: [
      { k: 'boundaries', l: '', t: 'lines', examples: C.boundaries.examples,
        h: 'One rule per box. These are passed word for word into every prompt.' }
    ]},

    style: { lead: C.style.lead, fields: [
      { k: 'style.english', l: 'Which English?', t: 'text', row: 'st' },
      { k: 'style.tone',    l: 'Tone', t: 'area' },
      { k: 'style.rules',   l: 'Writing rules', t: 'lines', examples: C.style.examples },
      { k: 'doc_prefs.max_pages', l: 'Maximum CV pages', t: 'number', row: 'doc' },
      { k: 'doc_prefs.font',      l: 'House font', t: 'text', row: 'doc' },
      { k: 'doc_prefs.accent',    l: 'Accent colour', t: 'text', row: 'doc' },
      { k: 'doc_prefs.editor',    l: 'What do you edit documents in?', t: 'text', row: 'doc2' },
      { k: 'doc_prefs.folder',    l: 'Where do finished files go?', t: 'text', row: 'doc2' },
      { k: 'doc_prefs.notes',     l: 'Anything else about documents', t: 'area' }
    ]}
  };

  /* =====================================================
     Generic field renderer
     ===================================================== */
  function touch() {
    clearTimeout(saveTimer);
    setSync('Saving…');
    saveTimer = setTimeout(saveProfile, 900);
  }

  function renderField(field, target) {
    const obj = target || profile;
    const key = field.k;
    const value = get(obj, key);
    const change = v => { set(obj, key, v); touch(); };

    switch (field.t) {
      case 'bool':
        return el('div.field', [U.checkbox(field.l, value, change),
          field.h ? el('div.hint', { text: field.h }) : null]);

      case 'area':
        return U.field(field.l, U.textarea(value, change), field.h);

      case 'select': {
        const opts = field.options.map(o => (typeof o === 'string' ? { id: o, name: o } : o));
        const note = field.describe ? el('div.hint') : null;
        const paint = id => { if (note) note.textContent = field.describe(id); };
        const sel = U.select(value || opts[0].id, opts, v => { change(v); paint(v); });
        paint(value || opts[0].id);
        return el('div.field', [el('label', { text: field.l }), sel,
          note, field.h ? el('div.hint', { text: field.h }) : null]);
      }

      case 'chips':
        return U.field(field.l, U.chipList(value || (set(obj, key, []), get(obj, key)),
          change, { placeholder: 'Type and press Enter' }), field.h);

      case 'toggles':
        return U.field(field.l, U.toggleSet(field.options,
          value || (set(obj, key, []), get(obj, key)), change), field.h);

      case 'lines':
        return U.field(field.l, U.lineList(value || (set(obj, key, []), get(obj, key)),
          change, { addLabel: '+ Add', examples: field.examples }), field.h);

      case 'repeat':
        return renderRepeat(field, obj);

      default:
        return U.field(field.l, U.input(value, change, { type: field.t || 'text' }), field.h);
    }
  }

  function renderRepeat(field, obj) {
    let list = get(obj, field.k);
    if (!Array.isArray(list)) { set(obj, field.k, []); list = get(obj, field.k); }

    const wrap = el('div');
    const paint = () => {
      U.clear(wrap);
      if (field.l) wrap.appendChild(el('h3', { text: field.l }));

      list.forEach((row, i) => {
        const body = el('div.evgroup-body',
          field.item.map(sub => renderField(sub, row)));
        body.appendChild(el('div.row', [
          el('div.spacer'),
          el('button.btn.btn-sm.btn-danger', {
            text: 'Remove', type: 'button',
            onclick: async () => {
              const label = (field.title ? field.title(row) : 'this entry');
              if (!(await U.confirm('Remove entry', 'Remove ' + label + '?', 'Remove'))) return;
              list.splice(i, 1); touch(); paint();
            }
          })
        ]));

        const summary = el('summary', [
          el('span', { text: field.title ? field.title(row) : 'Entry ' + (i + 1) }),
          field.count ? el('span.ev-count', { text: field.count(row) + ' items' }) : null
        ]);
        const details = el('details.evgroup', { open: field.open || list.length === 1 });
        details.appendChild(summary);
        details.appendChild(body);
        // keep the header label live as the user types
        body.addEventListener('input', () => {
          summary.firstChild.textContent = field.title ? field.title(row) : 'Entry ' + (i + 1);
          if (field.count) summary.lastChild.textContent = field.count(row) + ' items';
        });
        wrap.appendChild(details);
      });

      wrap.appendChild(el('button.btn.btn-sm', {
        text: field.add || '+ Add', type: 'button',
        onclick: () => {
          const blank = {};
          field.item.forEach(sub => {
            if (sub.t === 'lines' || sub.t === 'chips') blank[sub.k] = [];
            else if (sub.t === 'bool') blank[sub.k] = false;
            // A select must start on a real option: the server validates these
            // against a Literal, and "" is not one of them.
            else if (sub.t === 'select' && sub.options && sub.options.length) {
              const first = sub.options[0];
              blank[sub.k] = typeof first === 'string' ? first : first.id;
            }
            else blank[sub.k] = '';
          });
          list.push(blank); touch(); paint();
        }
      }));
    };
    paint();
    return wrap;
  }

  /* =====================================================
     Views
     ===================================================== */
  /* Has this step been given anything? Used only to shade the sidebar. */
  function stepAnswered(id) {
    const spec = SCHEMA[id];
    if (!spec) return false;
    return spec.fields.some(f => {
      const v = get(profile, f.k);
      // A field still holding its shipped default was never answered.
      if (Object.prototype.hasOwnProperty.call(JH.PROFILE_DEFAULTS, f.k) &&
          v === JH.PROFILE_DEFAULTS[f.k]) return false;
      if (Array.isArray(v)) {
        return v.some(item => {
          if (typeof item === 'string') return item.trim();
          if (!item) return false;
          return Object.keys(item).some(key => {
            // Skip the pre-seeded label; only real content counts.
            if (f.scaffold && key === f.scaffold) return false;
            const x = item[key];
            if (Array.isArray(x)) return x.some(e => typeof e === 'string' ? e.trim() : e);
            return typeof x === 'string' ? x.trim() : (x !== undefined && x !== null && x !== false);
          });
        });
      }
      return typeof v === 'string' ? v.trim() : (v !== undefined && v !== null && v !== false);
    });
  }
  const essentialsDone = () => JH.ESSENTIAL_STEPS.every(stepAnswered);
  const allAnswered = () => JH.WIZARD_STEPS.every(s => stepAnswered(s.id));

  /* =====================================================
     Start from CVs you have already written.

     A blank ten-step questionnaire is the worst first
     impression this app can make. Most people arrive with
     tailored CVs on disk containing better prose than they
     would ever type into a form.
     ===================================================== */
  function mineCard() {
    const input = el('input', { type: 'file', accept: '.docx', multiple: true });
    const result = el('div');

    const run = async button => {
      if (!input.files.length) return U.toast('Choose at least one .docx CV.', 'warn');
      if (input.files.length > 10) return U.toast('Ten CVs at most.', 'warn');
      button.disabled = true;
      U.clear(result).appendChild(el('p.muted', [el('span.loading'), ' Reading…']));
      try {
        U.clear(result).appendChild(reviewPanel(await api.mineCvs(input.files)));
      } catch (err) {
        U.clear(result).appendChild(el('div.banner.bad', { text: err.message }));
      } finally { button.disabled = false; }
    };

    return el('div.card', { style: { marginBottom: '18px' } }, [
      el('div.card-head', [el('h3', { text: 'Start from a CV you already have' })]),
      el('div.card-body', [
        el('p.hint', { style: { marginTop: 0 },
          text: 'Upload up to ten Word CVs. Contact details, technologies and the ' +
                'bullet points themselves are pulled out for you to accept or reject. ' +
                'Nothing is saved until you choose it.' }),
        input, result,
        el('div.row', { style: { marginTop: '10px' } }, [
          el('button.btn.btn-primary', { text: 'Read my CVs', type: 'button',
            onclick: e => run(e.target) })
        ])
      ])
    ]);
  }

  /* Everything mined is opt-in, one line at a time. */
  function reviewPanel(data) {
    const chosen = new Set();
    const box = el('div', { style: { marginTop: '14px' } });
    const takeContact = {}, takeTech = new Set();

    if (Object.keys(data.contact).length) {
      box.appendChild(el('h4', { text: 'Contact details found' }));
      box.appendChild(el('div', Object.entries(data.contact).map(([k, v]) =>
        U.checkbox(k + ': ' + v, true, on => { takeContact[k] = on ? v : null; })
      )));
      Object.entries(data.contact).forEach(([k, v]) => takeContact[k] = v);
    }

    if (data.technologies.length) {
      box.appendChild(el('h4', { style: { marginTop: '14px' }, text: 'Technologies mentioned' }));
      box.appendChild(el('p.hint', { style: { marginTop: 0 },
        text: 'All selected, so click any you do not want. Added at "hands-on project ' +
              'work" so nothing is overclaimed. Set the real level afterwards in ' +
              'Technology profile.' }));
      const picked = data.technologies.slice();
      picked.forEach(t => takeTech.add(t));
      box.appendChild(U.toggleSet(data.technologies, picked, v => {
        takeTech.clear(); v.forEach(t => takeTech.add(t));
      }));
    }

    box.appendChild(el('h4', { style: { marginTop: '16px' },
      text: U.pluralise(data.candidates.length, 'line') + ' worth keeping?' }));
    box.appendChild(el('p.hint', { style: { marginTop: 0 },
      text: 'Only you know which of these are still true. Tick what you want.' }));

    const list = el('div', { style: { maxHeight: '340px', overflow: 'auto',
      border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '10px' } });
    data.candidates.forEach((c, i) => {
      list.appendChild(el('div', { style: { marginBottom: '9px' } }, [
        U.checkbox(c.text, false, on => on ? chosen.add(i) : chosen.delete(i)),
        el('div.tiny.dim', { style: { paddingLeft: '24px' },
          text: (c.technologies.join(', ') || 'no technologies detected') + '  ·  ' + c.source })
      ]));
    });
    box.appendChild(list);

    box.appendChild(el('div.row', { style: { marginTop: '12px' } }, [
      el('button.btn', { text: 'Select all', type: 'button', onclick: () => {
        U.$$('input[type=checkbox]', list).forEach((cb, i) => {
          if (!cb.checked) { cb.checked = true; chosen.add(i); }
        });
      } }),
      el('button.btn.btn-primary', { text: 'Add to my profile', type: 'button',
        onclick: () => applyMined(data, chosen, takeContact, takeTech) })
    ]));
    return box;
  }

  async function applyMined(data, chosen, contact, tech) {
    let added = 0;

    Object.entries(contact).forEach(([k, v]) => {
      if (!v) return;
      const target = k === 'name' ? 'identity.name' : 'identity.' + k;
      if (!get(profile, target)) { set(profile, target, v); added++; }
    });

    tech.forEach(name => {
      if (profile.tech.some(t => t.area.toLowerCase() === name.toLowerCase())) return;
      // Deliberately conservative: claimed no higher than project work until
      // the user says otherwise.
      profile.tech.push({ area: name, description: 'From an existing CV', level: 'project' });
      added++;
    });

    const lines = Array.from(chosen).map(i => data.candidates[i].text);
    if (lines.length) {
      const HEADING = 'From my previous CVs';
      let group = profile.evidence.find(g => g.group === HEADING);
      if (!group) { group = { group: HEADING, employer: '', items: [] }; profile.evidence.push(group); }
      lines.forEach(t => { if (!group.items.includes(t)) { group.items.push(t); added++; } });
    }

    if (!added) return U.toast('Nothing new to add.', 'warn');
    await saveProfile();
    U.toast('Added ' + added + ' item' + (added === 1 ? '' : 's') +
            '. Review them in Evidence bank and Technology profile.', 'ok', 5000);
    render();
  }

  function viewProfile() {
    const view = el('div');
    const spec = SCHEMA[step];

    view.appendChild(U.pageHead('Profile',
      'Answered once, reused in every prompt this app builds.',
      [completeness ? el('span.tag' + (completeness.percent > 70 ? '.ok' : '.warn'),
        { text: completeness.percent + '% complete' }) : null]));

    // Grouped by what each phase buys you, so ten steps read as three
    // decisions rather than ten chores.
    if (!essentialsDone() || !(profile.evidence || []).some(g => (g.items || []).some(Boolean))) {
      view.appendChild(mineCard());
    }

    const nav = el('div.wiz-steps');
    JH.WIZARD_PHASES.forEach(phase => {
      const inPhase = JH.WIZARD_STEPS.filter(x => x.phase === phase.id);
      if (!inPhase.length) return;
      const done = inPhase.filter(x => stepAnswered(x.id)).length;
      nav.appendChild(el('div.wiz-phase', [
        el('span.wiz-phase-name', { text: phase.name }),
        el('span.wiz-phase-count', { text: done + '/' + inPhase.length })
      ]));
      inPhase.forEach(x => {
        const i = JH.WIZARD_STEPS.indexOf(x);
        nav.appendChild(el('button.wiz-step' + (x.id === step ? '.on' : '') +
                           (stepAnswered(x.id) ? '.done' : ''), {
          type: 'button', title: x.feeds,
          onclick: () => { step = x.id; render(); scrollTop(); }
        }, [el('span.wiz-num', { text: String(i + 1) }), el('span', { text: x.name })]));
      });
      nav.appendChild(el('div.wiz-phase-blurb', { text: phase.blurb }));
    });

    const current = JH.WIZARD_STEPS.find(s => s.id === step);
    const panel = el('div.wiz-panel.card.card-pad', [
      el('h2', { text: current.name }),
      current.feeds ? el('p.page-sub', [el('strong', { text: 'Feeds: ' }), current.feeds]) : null,
      spec.lead ? el('p.page-sub', { text: spec.lead }) : null,
      el('hr')
    ]);
    spec.fields.forEach(f => panel.appendChild(renderField(f)));

    const at = JH.WIZARD_STEPS.findIndex(s => s.id === step);
    panel.appendChild(el('div.wiz-foot', [
      at > 0 ? el('button.btn', { text: '← Back', type: 'button',
        onclick: () => { step = JH.WIZARD_STEPS[at - 1].id; render(); scrollTop(); } }) : null,
      el('div.spacer'),
      at < JH.WIZARD_STEPS.length - 1
        ? el('button.btn.btn-primary', { text: 'Next →', type: 'button',
            onclick: () => { step = JH.WIZARD_STEPS[at + 1].id; render(); scrollTop(); } })
        : el('button.btn.btn-primary', { text: 'Done — hunt for jobs', type: 'button',
            onclick: () => { location.hash = '#/hunt'; } })
    ]));

    if (essentialsDone() && !allAnswered()) {
      view.insertBefore(el('div.banner.ok', { style: { marginBottom: '16px' } }, [
        el('div', [
          el('strong', { text: 'You have enough for a CV. ' }),
          'The rest is optional - each step says what it adds. ',
          el('a', { href: '#/cv', text: 'Build one now' }), '.'
        ])
      ]), view.querySelector('.wizard') || null);
    }

    view.appendChild(el('div.wizard', [nav, panel]));
    return view;
  }

  function viewHunt() {
    const view = el('div');
    view.appendChild(U.pageHead('Hunt for jobs',
      'Builds a prompt from your answers and hands it to whichever assistant you already use.'));

    const st = JH.__hunt = JH.__hunt || { kind: 'hunt', tool: 'claude', brief: '', advert: '', app_id: '' };
    const out = el('div');

    const kindSel = U.select(st.kind, JH.PROMPT_KINDS, v => { st.kind = v; render(); });
    const toolSel = U.select(st.tool, JH.AI_TOOLS, v => { st.tool = v; render(); });
    const needsAd = JH.promptKind(st.kind).needsAd;

    const controls = el('div.card.card-pad', [
      el('div.field-row', [
        U.field('What do you want?', kindSel),
        U.field('Send it to', toolSel)
      ]),
      el('p.hint', { text: JH.promptKind(st.kind).blurb + '  ' + JH.aiTool(st.tool).note }),

      needsAd ? U.field('Which application?',
        U.select(st.app_id, roleOptions('Paste an advert below instead'),
          v => { st.app_id = v; render(); })) : null,

      needsAd && !st.app_id
        ? U.field('Paste the job advert', U.textarea(st.advert, v => { st.advert = v; },
            { style: { minHeight: '150px' } }))
        : null,

      !needsAd ? U.field('Extra steer (optional)',
        U.input(st.brief, v => { st.brief = v; },
          { placeholder: 'e.g. focus on remote roles, backend or integration' })) : null,

      el('div.row', [
        el('button.btn.btn-primary', { text: 'Build prompt', type: 'button',
          onclick: e => buildPrompt(e.target, st, out) })
      ])
    ]);

    view.appendChild(controls);
    view.appendChild(out);
    view.appendChild(importCard());
    return view;
  }

  async function buildPrompt(button, st, out) {
    button.disabled = true;
    U.clear(out).appendChild(el('p.muted', [el('span.loading'), ' Building…']));
    try {
      const res = await api.buildPrompt({
        kind: st.kind, brief: st.brief, advert: st.advert,
        application_id: st.app_id, max_results: 12
      });
      const tool = JH.aiTool(st.tool);
      const tooLong = tool.limit && res.characters > tool.limit;

      U.clear(out).appendChild(el('div.card', { style: { marginTop: '16px' } }, [
        el('div.card-head', [
          el('h3', { text: 'Your prompt' }),
          el('span.tag', { text: res.characters.toLocaleString() + ' characters' }),
          el('div.spacer'),
          el('button.btn.btn-sm', { text: 'Copy', type: 'button',
            onclick: async () => U.toast(await U.copy(res.prompt)
              ? 'Copied.' : 'Could not copy — select the text instead.',
              'ok') }),
          tool.url ? el('button.btn.btn-sm.btn-primary', {
            text: 'Open ' + tool.name, type: 'button',
            onclick: () => openTool(tool, res.prompt, tooLong)
          }) : null
        ]),
        el('div.card-body', [
          res.warnings.length ? el('div.banner.warn', { style: { marginBottom: '12px' } },
            [el('div', [el('strong', { text: 'Worth fixing first' }),
              el('ul', { style: { margin: '4px 0 0', paddingLeft: '18px' } },
                res.warnings.map(w => el('li', { text: w })))])]) : null,
          tooLong ? el('div.banner.info', { style: { marginBottom: '12px' },
            text: 'Too long to pre-fill ' + tool.name + '. Opening it and copying the prompt '
                + 'to your clipboard instead — just paste.' }) : null,
          el('div.prompt-out', { text: res.prompt })
        ])
      ]));
    } catch (err) {
      U.clear(out).appendChild(el('div.banner.bad', { text: err.message }));
    } finally {
      button.disabled = false;
    }
  }

  async function openTool(tool, prompt, tooLong) {
    const copied = await U.copy(prompt);
    let url = tool.url;
    if (tool.q && !tooLong) url += (url.indexOf('?') === -1 ? '?' : '&') + tool.q + '=' + encodeURIComponent(prompt);
    window.open(url, '_blank', 'noopener');
    if (copied) U.toast('Prompt copied too, in case it does not pre-fill.', 'ok');
  }

  function importCard() {
    const box = U.textarea('', () => {}, {
      placeholder: 'Paste the whole reply here, including the ```json block.',
      style: { minHeight: '110px' }
    });
    const result = el('div');
    return el('div.card', { style: { marginTop: '16px' } }, [
      el('div.card-head', [el('h3', { text: 'Bring the results back' })]),
      el('div.card-body', [
        el('p.hint', { style: { marginTop: '0' },
          text: 'Paste what the assistant replied and the roles land in your tracker. '
              + 'Anything already there is skipped.' }),
        box, result,
        el('div.row', { style: { marginTop: '10px' } }, [
          el('button.btn.btn-primary', { text: 'Import', type: 'button',
            onclick: async e => {
              if (!box.value.trim()) return U.toast('Nothing pasted.', 'warn');
              e.target.disabled = true;
              try {
                const r = await api.importReply(box.value);
                apps = r.applications;
                box.value = '';
                U.clear(result).appendChild(el('div.banner.ok', { style: { marginTop: '10px' },
                  text: 'Imported ' + r.imported + ' of ' + r.found + ' found'
                      + (r.duplicates ? ', skipped ' + r.duplicates + ' already tracked' : '') + '.' }));
                paintBadges();
              } catch (err) {
                U.clear(result).appendChild(el('div.banner.bad',
                  { style: { marginTop: '10px' }, text: err.message }));
              } finally { e.target.disabled = false; }
            } })
        ])
      ])
    ]);
  }

  /* ---------- filters, kept outside the view so they survive a re-render ---- */
  const filters = { title: '', company: '', location: '', stage: '', action: '', age: '', batch: '' };
  const selected = new Set();
  let lastTouched = null;   // anchor for shift-click ranges
  const hasFilters = () => Object.keys(filters).some(k => filters[k]);

  const matches = (value, needle) =>
    String(value || '').toLowerCase().indexOf(needle.toLowerCase()) !== -1;

  function visibleApps() {
    return apps.filter(a => {
      if (filters.title    && !matches(a.title, filters.title)) return false;
      if (filters.company  && !matches(a.company, filters.company)) return false;
      if (filters.location && !matches(a.location + ' ' + a.work_mode, filters.location)) return false;
      if (filters.stage    && a.stage !== filters.stage) return false;
      if (filters.action   && !matches(a.next_action, filters.action)) return false;
      if (filters.age === 'stale' && !JH.isStale(a)) return false;
      if (filters.age === 'fresh' && JH.isStale(a)) return false;
      if (filters.batch && batchOf(a) !== filters.batch) return false;
      if (filters.age === 'due') {
        if (!a.next_action_due) return false;
        if (U.daysBetween(U.today(), a.next_action_due) > 2) return false;
      }
      return true;
    }).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  }

  /* Which import run a row belongs to.
     Rows added before import_batch existed fall back to when they were
     created, rounded to the minute, so old data is still groupable. */
  function batchOf(a) {
    if (a.import_batch) return a.import_batch;
    return a.created_at ? String(a.created_at).slice(0, 16) : '';
  }

  /* Distinct import runs, newest first, for the batch filter. */
  function batches() {
    const seen = new Map();
    apps.forEach(a => {
      const key = batchOf(a);
      if (!key) return;
      seen.set(key, (seen.get(key) || 0) + 1);
    });
    return Array.from(seen.entries())
      .sort((x, y) => y[0].localeCompare(x[0]))
      // Date alone is ambiguous - two imports in one day looked identical.
      .map(([id, n]) => ({ id, name: U.fmtDateTime(id) + ' · ' + U.pluralise(n, 'role') }))
      // Two imports inside the same minute would otherwise be indistinguishable.
      .map(function (row, i, all) {
        const clash = all.filter(r => r.name === row.name);
        if (clash.length < 2) return row;
        return { id: row.id, name: row.name + ' (' + (clash.indexOf(row) + 1) + ')' };
      });
  }

  async function deleteSelected() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    const ok = await U.confirm('Delete applications',
      'Delete ' + U.pluralise(ids.length, 'application') + '? This cannot be undone.',
      'Delete ' + ids.length);
    if (!ok) return;
    apps = apps.filter(a => selected.has(a.id) === false);
    selected.clear();
    await saveApps();
    render();
    U.toast('Deleted ' + U.pluralise(ids.length, 'application') + '.', 'ok');
  }

  /* ---------- date helpers ---------- */
  /* Calendar arithmetic, done entirely in UTC.
     Building a local midnight and reading it back with toISOString silently
     loses a day anywhere east of Greenwich - "chase in 14 days" landed on
     day 13 under BST. */
  const addDays = (iso, n) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return '';
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };

  const dueClass = d => {
    const days = U.daysBetween(U.today(), d);
    return days < 0 ? '.over' : days <= 2 ? '.soon' : '';
  };

  /* Moving to Applied fills in the things you would otherwise forget: when you
     applied, and when to chase. Only fills blanks - never overwrites. */
  function applyStageDefaults(a, next) {
    a.stage = next;
    const filled = [];
    if (next === 'applied') {
      if (!a.applied_on) { a.applied_on = U.today(); filled.push('applied date'); }
      if (!a.next_action) { a.next_action = 'Chase'; filled.push('next action'); }
      if (!a.next_action_due) {
        const due = addDays(a.applied_on, JH.CHASE_DAYS);
        if (due) { a.next_action_due = due; filled.push('chase date'); }
      }
    }
    return filled;
  }

  /* ---------- CSV ---------- */
  const CSV_COLUMNS = [
    ['Role', 'title'], ['Company', 'company'], ['Location', 'location'],
    ['Work mode', 'work_mode'], ['Stage', a => JH.stage(a.stage).name],
    ['Outcome', a => (JH.OUTCOMES.find(o => o.id === a.outcome) || {}).name || ''],
    ['Stale', a => (JH.isStale(a) ? 'yes' : 'no')],
    ['Applied on', 'applied_on'], ['Next action', 'next_action'], ['Due', 'next_action_due'],
    ['Salary', 'salary'], ['Advert URL', 'url'], ['Source', 'source'], ['Posted', 'posted'],
    ['Contact name', 'contact_name'], ['Contact email', 'contact_email'],
    ['Key requirements', a => (a.key_requirements || []).join('; ')],
    ['Why match', 'why_match'], ['Concerns', 'concerns'], ['Notes', 'notes'],
    ['Added', 'created_at'], ['Last updated', 'updated_at']
  ];

  const csvCell = v => {
    const s = String(v === null || v === undefined ? '' : v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };

  function toCsv(rows) {
    const lines = [CSV_COLUMNS.map(c => csvCell(c[0])).join(',')];
    rows.forEach(a => lines.push(CSV_COLUMNS.map(c =>
      csvCell(typeof c[1] === 'function' ? c[1](a) : a[c[1]])).join(',')));
    // BOM so Excel reads UTF-8 rather than guessing at the code page.
    return '﻿' + lines.join('\r\n');
  }

  function exportCsv() {
    const rows = visibleApps();
    if (!rows.length) return U.toast('Nothing to export.', 'warn');
    U.download('applications-' + U.today() + '.csv', toCsv(rows), 'text/csv;charset=utf-8');
    U.toast('Exported ' + U.pluralise(rows.length, 'row') +
      (hasFilters() ? ' (filtered)' : '') + '.', 'ok');
  }

  /* ---------- the view ---------- */
  function viewTracker() {
    const view = el('div');
    const staleCount = apps.filter(JH.isStale).length;

    view.appendChild(U.pageHead('Applications',
      apps.length ? U.pluralise(apps.length, 'role') + ' tracked' : 'Nothing tracked yet',
      [
        el('button.btn', { text: 'Export CSV', type: 'button', onclick: exportCsv,
          disabled: !apps.length }),
        el('button.btn', { text: '+ Add manually', type: 'button', onclick: () => editApp(null) })
      ]));

    view.appendChild(el('div.grid.g4', { style: { marginBottom: '18px' } },
      JH.STAGES.map(s => {
        const n = apps.filter(a => a.stage === s.id).length;
        return el('div.stat', {
          style: { cursor: 'pointer' }, title: 'Filter to ' + s.name,
          onclick: () => { filters.stage = filters.stage === s.id ? '' : s.id; render(); }
        }, [
          el('div.stat-label', { text: s.name }),
          el('div.stat-value', {
            text: String(n),
            style: filters.stage === s.id ? { color: s.colour } : null
          })
        ]);
      }).concat([
        el('div.stat', {
          style: { cursor: 'pointer' }, title: 'Nothing has moved in ' + JH.STALE_DAYS + ' days',
          onclick: () => { filters.age = filters.age === 'stale' ? '' : 'stale'; render(); }
        }, [
          el('div.stat-label', { text: 'Stale' }),
          el('div.stat-value', {
            text: String(staleCount),
            style: staleCount ? { color: 'var(--warn)' } : null
          }),
          el('div.stat-note', { text: 'no change in ' + JH.STALE_DAYS + 'd' })
        ])
      ])));

    if (!apps.length) {
      view.appendChild(U.empty('No applications yet',
        'Run a hunt, paste the reply back, and the roles appear here.',
        el('a.btn.btn-primary', { href: '#/hunt', text: 'Hunt for jobs' })));
      return view;
    }

    const tbody = el('tbody');
    const status = el('div.tiny.muted');

    const textFilter = key => U.input(filters[key], v => { filters[key] = v; paintRows(); },
      { placeholder: 'Filter…', 'aria-label': 'Filter by ' + key });

    const head = el('thead', [
      el('tr', ['Role', 'Company', 'Location', 'Stage', 'Next action', 'Imported', 'Updated']
        .map(h => el('th', { text: h }))),
      el('tr.filter-row', [
        el('th', [textFilter('title')]),
        el('th', [textFilter('company')]),
        el('th', [textFilter('location')]),
        el('th', [U.select(filters.stage,
          [{ id: '', name: 'Any stage' }].concat(JH.STAGES),
          v => { filters.stage = v; paintRows(); })]),
        el('th', [textFilter('action')]),
        el('th', [U.select(filters.batch,
          [{ id: '', name: 'Any import' }].concat(batches()),
          v => { filters.batch = v; paintRows(); })]),
        el('th', [U.select(filters.age, [
          { id: '', name: 'Any age' },
          { id: 'fresh', name: 'Active' },
          { id: 'stale', name: 'Stale only' },
          { id: 'due',   name: 'Action due' }
        ], v => { filters.age = v; paintRows(); })])
      ])
    ]);

    function paintRows() {
      const rows = visibleApps();
      U.clear(tbody);

      if (!rows.length) {
        tbody.appendChild(el('tr', [el('td', {
          colspan: '7', style: { textAlign: 'center', padding: '28px' }
        }, [el('span.muted', { text: 'Nothing matches those filters.' })])]));
      }

      rows.forEach(a => {
        const stale = JH.isStale(a);
        // Green marks "sent, now waiting" - the state you want to spot at a glance.
        const applied = a.stage === 'applied';
        // The whole row toggles selection - a 13px checkbox is a poor target.
        // Opening the detail moves onto the title, which reads as a link.
        const toggle = shiftKey => {
          const order = visibleApps().map(x => x.id);
          if (shiftKey && lastTouched && order.indexOf(lastTouched) !== -1) {
            // Range select, the way every file manager does it.
            const from = order.indexOf(lastTouched);
            const to = order.indexOf(a.id);
            const [lo, hi] = from < to ? [from, to] : [to, from];
            const adding = !selected.has(a.id);
            order.slice(lo, hi + 1).forEach(id =>
              adding ? selected.add(id) : selected.delete(id));
          } else {
            if (selected.has(a.id)) selected.delete(a.id); else selected.add(a.id);
          }
          lastTouched = a.id;
          paintRows();
        };
        const chosen = selected.has(a.id);
        tbody.appendChild(el('tr.clickable' + (applied ? '.is-applied' : '') +
                             (chosen ? '.is-selected' : ''), {
          onclick: e => toggle(e.shiftKey),
          tabindex: '0', role: 'checkbox', 'aria-checked': chosen ? 'true' : 'false',
          'aria-label': a.title + ' at ' + a.company,
          onkeydown: e => {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            e.preventDefault();
            toggle(e.shiftKey);
          }
        }, [
          el('td', [
            el('button.link-title', {
              text: a.title, type: 'button', title: 'Open ' + a.title,
              onclick: e => { e.stopPropagation(); editApp(a); }
            }),
            a.url ? el('a.tiny.dim.break', { href: a.url, target: '_blank', rel: 'noopener',
              text: 'advert', onclick: e => e.stopPropagation() }) : null
          ]),
          el('td', { text: a.company }),
          el('td', { text: [a.location, a.work_mode].filter(Boolean).join(' · ') }),
          el('td', [
            // Inline stage change: the most common edit on this page, and it
            // triggers the same autofill as the detail modal.
            U.select(a.stage, JH.STAGES, async v => {
              const filled = applyStageDefaults(a, v);
              await saveApps();
              if (filled.length) U.toast('Set ' + filled.join(', ') + '.', 'ok');
              render();
            }, { onclick: e => e.stopPropagation(), 'aria-label': 'Stage for ' + a.title }),
            stale ? el('span.tag.warn', { style: { marginTop: '4px' },
              text: 'Stale ' + JH.daysSince(a.updated_at || a.created_at) + 'd' }) : null
          ]),
          el('td', [
            a.next_action ? el('div', { text: a.next_action }) : el('span.dim', { text: '—' }),
            a.next_action_due ? el('span.due' + dueClass(a.next_action_due),
              { text: U.fmtDate(a.next_action_due) }) : null
          ]),
          el('td.tiny.dim', { text: U.fmtDateTime(batchOf(a)),
            title: a.import_batch ? 'Import batch ' + a.import_batch
                                  : 'Added ' + (a.created_at || 'unknown') }),
          el('td.tiny.dim', { text: U.relative(a.updated_at || a.created_at) })
        ]));
      });

      // Anything filtered out stays selected but is not actionable from here.
      const shown = new Set(rows.map(r => r.id));
      Array.from(selected).forEach(id => { if (!shown.has(id)) selected.delete(id); });
      paintSelection(rows);

      status.textContent = 'Showing ' + rows.length + ' of ' + apps.length +
        (hasFilters() ? ' (filtered)' : '');
    }

    const bulk = el('div.row.row-tight');
    function paintSelection(rows) {
      U.clear(bulk);
      if (selected.size) {
        U.add(bulk, [
          el('span.tag.accent', { text: selected.size + ' selected' }),
          el('button.btn.btn-sm.btn-danger', { text: 'Delete selected', type: 'button',
            onclick: deleteSelected }),
          el('button.btn.btn-ghost.btn-sm', { text: 'Clear', type: 'button',
            onclick: () => { selected.clear(); lastTouched = null; paintRows(); } })
        ]);
        return;
      }
      // Nothing picked: offer the filtered set, which is the common case -
      // "get rid of everything from that bad hunt".
      if (hasFilters() && rows && rows.length) {
        U.add(bulk, el('button.btn.btn-sm.btn-danger', {
          text: 'Delete all ' + rows.length + ' shown', type: 'button',
          onclick: () => { rows.forEach(r => selected.add(r.id)); deleteSelected(); }
        }));
      }
    }

    paintRows();

    view.appendChild(el('div.card', [
      el('div', { style: { overflowX: 'auto' } }, [el('table.tbl', [head, tbody])]),
      el('div.row', { style: { padding: '10px 14px', borderTop: '1px solid var(--border)' } }, [
        status, bulk,
        el('div.spacer'),
        el('span.tiny.dim', { text: 'Click a row to select · shift-click for a range' }),
        hasFilters() ? el('button.btn.btn-ghost.btn-sm', {
          text: 'Clear filters', type: 'button',
          onclick: () => { Object.keys(filters).forEach(k => filters[k] = ''); render(); }
        }) : null
      ])
    ]));
    return view;
  }

  function editApp(existing) {
    const a = existing ? Object.assign({}, existing) : {
      id: '', title: '', company: '', location: '', work_mode: '', url: '', salary: '',
      summary: '', key_requirements: [], why_match: '', concerns: '', source: 'manual',
      stage: 'saved', outcome: '', applied_on: '', next_action: '', next_action_due: '',
      contact_name: '', contact_email: '', notes: '', tags: [], events: []
    };
    // Keep a handle on each control so a stage change can push autofilled
    // values back into the boxes the user is looking at.
    const inputs = {};
    const f = (l, k, t) => {
      const control = t === 'area'
        ? U.textarea(a[k], v => a[k] = v)
        : U.input(a[k], v => a[k] = v, { type: t || 'text' });
      inputs[k] = control;
      return U.field(l, control);
    };

    const onStageChange = v => {
      const filled = applyStageDefaults(a, v);
      if (!filled.length) return;
      ['applied_on', 'next_action', 'next_action_due'].forEach(k => {
        if (inputs[k]) inputs[k].value = a[k] || '';
      });
      U.toast('Set ' + filled.join(', ') + '.', 'ok');
    };

    U.modal({
      title: existing ? a.title || 'Application' : 'Add an application',
      wide: true,
      body: el('div', [
        el('div.field-row', [f('Job title', 'title'), f('Company', 'company')]),
        el('div.field-row', [f('Location', 'location'), f('Working pattern', 'work_mode'),
          f('Salary', 'salary')]),
        f('Advert URL', 'url', 'url'),
        el('div.field-row', [
          U.field('Stage', U.select(a.stage, JH.STAGES, onStageChange)),
          U.field('Outcome', U.select(a.outcome, JH.OUTCOMES, v => a.outcome = v)),
          f('Applied on', 'applied_on', 'date')
        ]),
        el('div.field-row', [f('Next action', 'next_action'), f('Due', 'next_action_due', 'date')]),
        el('div.field-row', [f('Contact name', 'contact_name'), f('Contact email', 'contact_email', 'email')]),
        a.why_match ? el('div.banner.ok', { style: { marginBottom: '12px' } },
          [el('div', [el('strong', { text: 'Why it matched: ' }), a.why_match])]) : null,
        a.concerns ? el('div.banner.warn', { style: { marginBottom: '12px' } },
          [el('div', [el('strong', { text: 'Concerns: ' }), a.concerns])]) : null,
        a.key_requirements && a.key_requirements.length
          ? el('div.field', [el('label', { text: 'Key requirements' }),
              el('ul', { style: { margin: 0, paddingLeft: '18px', fontSize: '.86rem' } },
                a.key_requirements.map(r => el('li', { text: r })))]) : null,
        f('Notes', 'notes', 'area')
      ]),
      actions: [
        existing ? { label: 'Delete', kind: 'danger', onClick: async close => {
          if (!(await U.confirm('Delete application',
            'Delete ' + (a.title || 'this application') + '? This cannot be undone.', 'Delete'))) return false;
          apps = apps.filter(x => x.id !== a.id);
          await saveApps(); close(); render();
        }, close: false } : null,
        { label: 'Save', kind: 'primary', onClick: async () => {
          if (existing) Object.assign(apps.find(x => x.id === a.id), a);
          else apps.push(a);
          await saveApps(); render();
        }}
      ].filter(Boolean)
    });
  }

  /* Roles to choose from, newest activity first, with finished ones kept
     apart rather than mixed in - a closed application is rarely the one you
     want a fresh CV for, but hiding it outright is worse than grouping it. */
  function roleOptions(placeholder) {
    const label = a => a.title + ' — ' + a.company;
    const recent = (x, y) => (y.updated_at || '').localeCompare(x.updated_at || '');
    const open = apps.filter(a => a.stage !== 'closed').sort(recent);
    const closed = apps.filter(a => a.stage === 'closed').sort(recent);

    const out = [{ id: '', name: placeholder }];
    if (open.length) {
      out.push({ group: 'Open (' + open.length + ')',
                 options: open.map(a => ({ id: a.id, name: label(a) })) });
    }
    if (closed.length) {
      out.push({ group: 'Closed (' + closed.length + ')',
                 options: closed.map(a => ({ id: a.id, name: label(a) })) });
    }
    return out;
  }

  /* =====================================================
     Build a CV - assembled locally from the profile
     ===================================================== */
  const cvState = { app_id: '', advert: '', max_lines: 9, independent: true,
                    doc: null, tailoring: null, editing: false, edited: false };

  /* Hand edits survive navigation and reload, keyed by the role they belong
     to. Nobody wants to redo a tidy-up because they clicked Applications. */
  const editKey = () => 'jobhunt.cvedit.' + (cvState.app_id || 'adhoc');

  function saveEdits() {
    cvState.edited = true;
    try { localStorage.setItem(editKey(), JSON.stringify(cvState.doc)); } catch (_) {}
  }
  function loadEdits() {
    try {
      const raw = localStorage.getItem(editKey());
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }
  function clearEdits() {
    cvState.edited = false;
    try { localStorage.removeItem(editKey()); } catch (_) {}
  }

  /* Markdown and the page verdict are derived, so they go stale the moment a
     line is deleted. The server owns the renderer; ask it. */
  async function refreshRendered() {
    saveEdits();
    try {
      const fresh = await api.renderCv(cvState.doc);
      cvState.doc.markdown = fresh.markdown;
      cvState.doc.characters = fresh.characters;
      cvState.doc.fits_one_page = fresh.fits_one_page;
    } catch (_) { /* preview still correct; only the counter lags */ }
    render();
  }

  function viewCv() {
    const view = el('div');
    view.appendChild(U.pageHead('Build a CV',
      'Assembled from your evidence bank and scored against the role. No AI call, ' +
      'so it can only ever re-arrange what you already wrote.'));

    const controls = el('div.card.card-pad', [
      U.field('Which role?', U.select(cvState.app_id,
        roleOptions('Paste an advert below instead'),
        v => {
          cvState.app_id = v;
          // Bring back whatever was edited for this role last time.
          const saved = loadEdits();
          cvState.doc = saved;
          cvState.edited = !!saved;
          cvState.editing = false;
          render();
        })),

      !cvState.app_id ? U.field('Paste the job advert',
        U.textarea(cvState.advert, v => { cvState.advert = v; },
          { style: { minHeight: '120px' } })) : null,

      el('div.field-row', [
        U.field('Evidence lines', U.input(cvState.max_lines,
          v => { cvState.max_lines = Math.max(3, Math.min(20, Number(v) || 9)); },
          { type: 'number', min: '3', max: '20' }), 'Fewer keeps it to one page.'),
        el('div.field', [el('label', { text: 'Include' }),
          U.checkbox('Independent work, when relevant', cvState.independent,
            v => cvState.independent = v)])
      ]),

      el('div.row', [
        el('button.btn.btn-primary', { text: 'Build CV', type: 'button',
          onclick: e => buildCv(e.target) }),
        el('button.btn', { text: 'Tailor with AI first', type: 'button',
          title: 'A short prompt that returns only the opening paragraph and which evidence should lead',
          onclick: openTailor }),
        cvState.tailoring ? el('span.tag.accent', { text: 'Tailoring applied' }) : null,
        cvState.tailoring ? el('button.btn.btn-ghost.btn-sm', { text: 'Clear', type: 'button',
          onclick: () => { cvState.tailoring = null; render(); } }) : null
      ])
    ]);

    view.appendChild(controls);
    const out = el('div', { id: 'cv-out' });
    view.appendChild(out);
    if (cvState.doc) U.add(out, cvPanels(cvState.doc));
    return view;
  }

  async function buildCv(button) {
    if (!cvState.app_id && !cvState.advert.trim()) {
      return U.toast('Pick a role or paste an advert first.', 'warn');
    }
    if (cvState.edited && !(await U.confirm('Rebuild this CV',
        'You have edited this one by hand. Rebuilding replaces those edits.', 'Rebuild'))) {
      return;
    }
    clearEdits();
    button.disabled = true;
    try {
      cvState.doc = await api.buildCv({
        application_id: cvState.app_id, advert: cvState.advert,
        max_lines: cvState.max_lines, include_independent: cvState.independent,
        tailoring: cvState.tailoring
      });
      render();
    } catch (err) {
      U.toast(err.message, 'bad', 5000);
    } finally { button.disabled = false; }
  }

  /* ---------- rendering the document ---------- */
  function cvPaper(doc, edit) {
    /* Text you can correct in place. Writes back on blur rather than on every
       keystroke, so the caret is never yanked mid-word by a re-render. */
    const editable = (tag, value, apply) => {
      const node = el(tag, { text: value });
      if (!edit) return node;
      node.contentEditable = 'true';
      node.classList.add('cv-editable');
      node.addEventListener('blur', () => {
        const next = node.textContent.trim();
        if (next === value) return;
        apply(next);
        refreshRendered();
      });
      return node;
    };

    const remove = (label, apply) => edit ? el('button.cv-del', {
      text: '×', type: 'button', title: 'Remove ' + label,
      onclick: () => { apply(); refreshRendered(); }
    }) : null;

    const paper = el('div.cv-paper' + (edit ? '.is-editing' : ''), [
      editable('h1.cv-name', doc.name, v => doc.name = v),
      doc.headline ? editable('div.cv-headline', doc.headline, v => doc.headline = v) : null,
      el('div.cv-contact', doc.contact.map((c, i) => el('span', [
        editable('span', c, v => doc.contact[i] = v),
        remove('this contact detail', () => doc.contact.splice(i, 1))
      ])))
    ]);

    if (doc.summary) {
      paper.appendChild(el('div.cv-sec', [
        el('h3', ['Profile', remove('the profile paragraph', () => doc.summary = '')]),
        editable('div', doc.summary, v => doc.summary = v)
      ]));
    }

    doc.sections.forEach((section, si) => {
      const box = el('div.cv-sec', [
        el('h3', [
          editable('span', section.heading, v => section.heading = v),
          remove('the ' + section.heading + ' section', () => doc.sections.splice(si, 1))
        ])
      ]);

      if (section.lines.length) {
        if (section.kind === 'skills') {
          section.lines.forEach((l, li) => box.appendChild(el('div.cv-skillrow', [
            edit ? editable('span', l.text, v => l.text = v)
                 : el('span', { html: U.esc(l.text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>') }),
            remove('this line', () => section.lines.splice(li, 1))
          ])));
        } else {
          box.appendChild(el('ul', section.lines.map((l, li) => el('li', [
            editable('span', l.text, v => l.text = v),
            remove('this bullet point', () => section.lines.splice(li, 1))
          ]))));
        }
      }

      section.entries.forEach((entry, ei) => {
        box.appendChild(el('div.cv-job', [
          el('div.cv-job-h', [
            el('span.cv-job-t', [
              editable('span', entry.title, v => entry.title = v),
              entry.company ? el('span', [', ',
                editable('span', entry.company, v => entry.company = v)]) : null,
              remove('this entry', () => section.entries.splice(ei, 1))
            ]),
            entry.dates ? editable('span.cv-job-d', entry.dates, v => entry.dates = v) : null
          ]),
          entry.note ? el('div', [
            editable('span', entry.note, v => entry.note = v),
            remove('this description', () => entry.note = '')
          ]) : null,
          (entry.bullets || []).length
            ? el('ul', entry.bullets.map((b, bi) => el('li', [
                editable('span', b, v => entry.bullets[bi] = v),
                remove('this bullet point', () => entry.bullets.splice(bi, 1))
              ]))) : null
        ]));
      });
      paper.appendChild(box);
    });
    return paper;
  }

  function cvPanels(doc) {
    const paper = cvPaper(doc, cvState.editing);

    const notes = el('div.cv-side', [
      el('div.card', [
        el('div.card-head', [el('h3', { text: 'Output' })]),
        el('div.card-body', [
          el('div.row', [
            el('button.btn.btn-sm' + (cvState.editing ? '.btn-primary' : ''), {
              text: cvState.editing ? 'Done editing' : 'Edit', type: 'button',
              title: 'Change the wording, or delete anything you do not want',
              onclick: () => { cvState.editing = !cvState.editing; render(); }
            }),
            cvState.edited ? el('button.btn.btn-ghost.btn-sm', {
              text: 'Reset', type: 'button', title: 'Discard edits and rebuild',
              onclick: async () => {
                if (!(await U.confirm('Discard edits',
                  'Throw away your changes and rebuild from the profile?', 'Discard'))) return;
                clearEdits();
                const button = U.$$('#view button').find(b => b.textContent === 'Build CV');
                if (button) buildCv(button);
              }
            }) : null,
            el('button.btn.btn-primary.btn-sm', { text: 'Print / PDF', type: 'button',
              onclick: () => {
                // Never print the editing chrome.
                U.clear($('#print-root')).appendChild(cvPaper(doc, false));
                window.print();
              } }),
            el('button.btn.btn-sm', { text: 'Copy markdown', type: 'button',
              onclick: async () => U.toast(await U.copy(doc.markdown)
                ? 'Copied.' : 'Could not copy.', 'ok') }),
            el('button.btn.btn-sm.btn-primary', { text: 'Download .docx', type: 'button',
              title: 'Editable Word document in your house style',
              onclick: async e => {
                e.target.disabled = true;
                try {
                  const { blob, filename } = await api.cvDocx(doc);
                  const url = URL.createObjectURL(blob);
                  const a = el('a', { href: url, download: filename });
                  document.body.appendChild(a); a.click(); a.remove();
                  setTimeout(() => URL.revokeObjectURL(url), 1500);
                  U.toast('Saved ' + filename, 'ok', 4000);
                } catch (err) {
                  U.toast(err.message, 'bad', 5000);
                } finally { e.target.disabled = false; }
              } }),
            el('button.btn.btn-sm', { text: 'Download .md', type: 'button',
              onclick: () => U.download(
                (doc.name || 'cv').replace(/\s+/g, '-').toLowerCase() + '-cv.md',
                doc.markdown, 'text/markdown;charset=utf-8') })
          ]),
          el('p.hint', {
            text: doc.characters.toLocaleString() + ' characters. ' +
              (doc.fits_one_page ? 'Should fit one page.'
                : 'Likely over one page — delete a bullet point or two.')
          }),
          cvState.edited ? el('p.hint', [
            el('strong', { text: 'Edited by hand. ' }),
            'Kept for this role until you reset. Rebuilding replaces it.'
          ]) : null,
          cvState.editing ? el('div.banner.info', { style: { marginTop: '8px' },
            text: 'Click any text to change it. × removes a bullet point, an entry or a '
                + 'whole section. Nothing here touches your profile.' }) : null,
          doc.tailored_fields.length
            ? el('p.hint', { text: 'AI tailoring applied to: ' + doc.tailored_fields.join(', ') + '.' })
            : null,
          doc.positioning_used
            ? el('p.hint', { text: 'Your "' + doc.positioning_used + '" positioning note fits this role.' })
            : null
        ])
      ]),

      gapsPanel(doc.gaps),
      panel('Left off deliberately', doc.stretch, 'warn',
        'Below production level, so kept off the CV.'),
      panel('Accuracy reminders', doc.warnings, 'bad',
        'Your own boundaries, triggered by this advert.'),
      panel('Not used this time', doc.omitted, '',
        'Scored lower for this role. Still in your bank.')
    ]);

    if (doc.matched.length) {
      notes.appendChild(el('div.card', [
        el('div.card-head', [el('h3', { text: 'Requirements covered' }),
          el('span.tag.ok', { text: doc.matched.length + '/' +
            (doc.matched.length + doc.gaps.length) })]),
        el('div.card-body', doc.matched.map(m => el('div', { style: { marginBottom: '9px' } }, [
          el('div.tiny', [el('strong', { text: m.requirement }),
            el('span.dim', { text: '  ' + Math.round(m.coverage * 100) + '%' })]),
          el('div.tiny.muted', { text: U.truncate(m.evidence, 110) })
        ])))
      ]));
    }

    return el('div.cv-layout', [notes, paper]);
  }

  /* A gap you can answer on the spot.

     Answering a gap in a chat window and watching the answer evaporate is the
     whole problem: the same requirement comes back as a gap on the next
     application. Typing it here writes it into the evidence bank, so it is
     available to every CV from now on. */
  const ANSWERED_THEME = 'Answered while tailoring';

  function gapsPanel(gaps) {
    if (!gaps || !gaps.length) return null;

    const body = el('div.card-body', [
      el('p.hint', { style: { marginTop: 0 },
        text: 'Asked for, but nothing in your evidence bank covers it. If you can ' +
              'actually evidence one, write it here - it is saved to your profile and ' +
              'stops being a gap on every future application.' })
    ]);

    gaps.forEach(gap => {
      const answer = el('textarea', {
        placeholder: 'e.g. "Used Elasticsearch for log storage and search."',
        style: { minHeight: '54px', display: 'none' }
      });
      const actions = el('div.row.row-tight', { style: { display: 'none', marginTop: '6px' } });

      const save = async () => {
        const text = answer.value.trim();
        if (!text) return U.toast('Nothing written yet.', 'warn');
        let group = profile.evidence.find(g => g.group === ANSWERED_THEME);
        if (!group) {
          group = { group: ANSWERED_THEME, employer: '', items: [] };
          profile.evidence.push(group);
        }
        if (group.items.indexOf(text) === -1) group.items.push(text);
        await saveProfile();
        U.toast('Added to your evidence bank. Rebuilding…', 'ok');
        const button = U.$$('#view button').find(b => b.textContent === 'Build CV');
        if (button) buildCv(button); else render();
      };

      U.add(actions, [
        el('button.btn.btn-sm.btn-primary', { text: 'Save to profile', type: 'button', onclick: save }),
        el('button.btn.btn-ghost.btn-sm', { text: 'Cancel', type: 'button',
          onclick: () => { answer.style.display = 'none'; actions.style.display = 'none'; } })
      ]);

      body.appendChild(el('div', { style: { marginBottom: '12px' } }, [
        el('div.tiny', { style: { fontWeight: '600' }, text: gap }),
        el('button.btn.btn-ghost.btn-sm', {
          text: 'I can evidence this', type: 'button',
          style: { paddingLeft: 0 },
          onclick: e => {
            e.target.style.display = 'none';
            answer.style.display = '';
            actions.style.display = '';
            answer.focus();
          }
        }),
        answer, actions
      ]));
    });

    return el('div.card', [
      el('div.card-head', [el('h3', { text: 'Gaps' }),
        el('span.tag.warn', { text: String(gaps.length) })]),
      body
    ]);
  }

  function panel(title, items, kind, blurb) {
    if (!items || !items.length) return null;
    return el('div.card', [
      el('div.card-head', [el('h3', { text: title }),
        el('span.tag' + (kind ? '.' + kind : ''), { text: String(items.length) })]),
      el('div.card-body', [
        blurb ? el('p.hint', { style: { marginTop: 0 }, text: blurb }) : null,
        el('ul', { style: { margin: 0, paddingLeft: '18px', fontSize: '.82rem' } },
          items.map(i => el('li', { text: i, style: { marginBottom: '4px' } })))
      ])
    ]);
  }

  /* ---------- the optional short AI round trip ---------- */
  function openTailor() {
    if (!cvState.app_id && !cvState.advert.trim()) {
      return U.toast('Pick a role or paste an advert first.', 'warn');
    }
    const paste = U.textarea('', () => {}, {
      placeholder: 'Paste the ```json block back here.', style: { minHeight: '120px' } });

    U.modal({
      title: 'Tailor with AI',
      wide: true,
      body: el('div', [
        el('p.hint', { style: { marginTop: 0 },
          text: 'This asks only for the judgement calls — a role-specific opening ' +
                'paragraph, and which of your evidence should lead. The CV itself is ' +
                'still assembled here, so nothing can be invented.' }),
        el('div.row', [
          el('button.btn', { text: 'Copy prompt', type: 'button',
            onclick: async e => sendTailorPrompt(e.target, false) }),
          el('button.btn.btn-primary', { text: 'Open ' + JH.aiTool(huntTool()).name,
            type: 'button', onclick: async e => sendTailorPrompt(e.target, true) })
        ]),
        el('hr'), paste
      ]),
      actions: [{ label: 'Apply tailoring', kind: 'primary', onClick: close => {
        try {
          const parsed = parseTailoring(paste.value);
          cvState.tailoring = parsed;
          U.toast('Tailoring applied. Build the CV again.', 'ok');
          close(); render();
        } catch (err) {
          U.toast(err.message, 'bad', 5000);
          return false;
        }
      }, close: false }]
    });
  }

  const huntTool = () => (JH.__hunt && JH.__hunt.tool) || 'claude';

  async function sendTailorPrompt(button, open) {
    button.disabled = true;
    try {
      const res = await api.buildPrompt({
        kind: 'tailor', advert: cvState.advert, application_id: cvState.app_id });
      const tool = JH.aiTool(huntTool());
      if (open && tool.url) openTool(tool, res.prompt, tool.limit && res.characters > tool.limit);
      else U.toast(await U.copy(res.prompt) ? 'Prompt copied.' : 'Could not copy.', 'ok');
    } catch (err) {
      U.toast(err.message, 'bad', 5000);
    } finally { button.disabled = false; }
  }

  function parseTailoring(text) {
    const fenced = /```(?:json)?\s*([\s\S]+?)```/i.exec(text);
    let body = fenced ? fenced[1] : text;
    const start = body.indexOf('{'), end = body.lastIndexOf('}');
    if (start === -1 || end <= start) throw new Error('No JSON object found in that.');
    let parsed;
    try { parsed = JSON.parse(body.slice(start, end + 1)); }
    catch (e) { throw new Error('That JSON did not parse: ' + e.message); }
    return {
      headline: String(parsed.headline || ''),
      summary: String(parsed.summary || ''),
      lead_themes: Array.isArray(parsed.lead_themes) ? parsed.lead_themes.map(String) : [],
      emphasise: Array.isArray(parsed.emphasise) ? parsed.emphasise.map(String) : []
    };
  }

  function viewAccount() {
    const view = el('div');
    view.appendChild(U.pageHead('Account and data', 'Signed in as ' + (user ? user.email : '')));

    view.appendChild(el('div.grid.g2', [
      el('div.card', [
        el('div.card-head', [el('h3', { text: 'Your data' })]),
        el('div.card-body', [
          el('p.hint', { style: { marginTop: 0 }, text: 'Everything is stored by the backend this app is running against. Export gives you the lot as JSON.' }),
          el('div.row', [
            el('button.btn', { text: 'Export everything', type: 'button', onclick: () =>
              U.download('jobhunt-export-' + U.today() + '.json',
                JSON.stringify({ profile, applications: apps }, null, 2), 'application/json') }),
            el('button.btn', { text: 'Export profile as markdown', type: 'button',
              onclick: exportMarkdown })
          ])
        ])
      ]),
      el('div.card', [
        el('div.card-head', [el('h3', { text: 'Profile completeness' })]),
        el('div.card-body', completeness ? [
          el('div.bar' + (completeness.percent > 70 ? '.ok' : '.warn'),
            [el('i', { style: { width: completeness.percent + '%' } })]),
          el('p.hint', { text: completeness.done + ' of ' + completeness.total + ' sections done.' }),
          completeness.missing.length
            ? el('div', [el('label', { text: 'Still missing' }),
                el('div.chip-group', completeness.missing.map(m => el('span.chip.chip-static', { text: m })))])
            : el('p.muted', { text: 'All sections answered.' })
        ] : [el('p.muted', { text: 'Not loaded.' })])
      ])
    ]));
    return view;
  }

  /* Profile as a markdown master document - the format that reads well
     outside this app and can be handed to an assistant directly. */
  function exportMarkdown() {
    const p = profile, L = [];
    const push = (h, body) => { if (body && body.trim()) L.push('## ' + h + '\n\n' + body.trim() + '\n'); };
    const list = arr => (arr || []).filter(Boolean).map(i => '- ' + i).join('\n');

    L.push('# ' + (p.identity.name || 'Job application master') + '\n');
    L.push('Last updated: ' + U.fmtDate(new Date().toISOString()) + '\n');

    push('Contact', [
      p.identity.email && '- **Email:** ' + p.identity.email,
      p.identity.phone && '- **Phone:** ' + p.identity.phone,
      p.identity.portfolio && '- **Portfolio:** ' + p.identity.portfolio,
      p.identity.linkedin && '- **LinkedIn:** ' + p.identity.linkedin,
      p.identity.github && '- **GitHub:** ' + p.identity.github
    ].filter(Boolean).join('\n'));

    push('Where I want to work', list(p.prefs.locations));

    push('Core profile', [p.core.summary, p.core.positioning && '\n> ' + p.core.positioning,
      p.core.target_roles.length && '\nTarget roles:\n' + list(p.core.target_roles)].filter(Boolean).join('\n'));

    push('Employment and education', (p.employment || []).map(j =>
      '### ' + j.company + ' | ' + j.title + '\n\n**' + j.start + ' to ' +
      (j.current ? 'present' : j.end) + '**\n\n' + (j.note || '') +
      (j.bullets && j.bullets.length ? '\n\n' + list(j.bullets) : '')
    ).concat((p.education || []).map(e =>
      '### ' + (e.qualification || '') + (e.field ? ', ' + e.field : '') +
      '\n\n' + [e.school, e.start + ' to ' + e.end].filter(Boolean).join(', ')
    )).join('\n\n'));

    push('Evidence bank', (p.evidence || []).filter(g => (g.items || []).some(Boolean))
      .map(g => '### ' + g.group + '\n\n' + list(g.items)).join('\n\n'));

    push('Independent work', (p.independent || []).map(i =>
      '### ' + i.name + (i.url ? ' — ' + i.url : '') + '\n\n' + (i.description || '') +
      (i.bullets && i.bullets.length ? '\n\n' + list(i.bullets) : '')).join('\n\n'));

    push('Technology profile', '| Area | Description | Strength of claim |\n| --- | --- | --- |\n' +
      (p.tech || []).map(t => '| ' + t.area + ' | ' + (t.description || '') + ' | ' +
        JH.techLevel(t.level).name + ' |').join('\n'));

    push('Positioning', (p.positioning || []).filter(x => x.guidance)
      .map(x => '### ' + x.role_type + '\n\n' + x.guidance).join('\n\n'));

    push('Accuracy boundaries', list(p.boundaries));
    push('Application style', list([p.style.english && 'Use ' + p.style.english + ' English.',
      p.style.tone].filter(Boolean).concat(p.style.rules || [])));
    push('Document preferences', list([
      'Keep the CV to ' + p.doc_prefs.max_pages + ' page(s) unless the vacancy needs more.',
      p.doc_prefs.font && 'House font: ' + p.doc_prefs.font + '.',
      p.doc_prefs.accent && 'Accent colour: ' + p.doc_prefs.accent + '.',
      p.doc_prefs.editor && 'Edited in ' + p.doc_prefs.editor + '.',
      p.doc_prefs.folder && 'Final files go to ' + p.doc_prefs.folder + '.',
      p.doc_prefs.notes
    ].filter(Boolean)));

    U.download('job-application-master.md', L.join('\n'), 'text/markdown;charset=utf-8');
    U.toast('Markdown exported.', 'ok');
  }

  /* =====================================================
     Persistence
     ===================================================== */
  async function saveProfile() {
    try {
      const res = await api.saveProfile(profile);
      completeness = res.completeness;
      setSync('Saved ' + new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }));
      paintBadges();
    } catch (err) {
      setSync('Not saved');
      U.toast('Could not save: ' + err.message, 'bad', 5000);
    }
  }

  async function saveApps() {
    try {
      const res = await api.saveApplications(apps);
      apps = res.applications;
      paintBadges();
    } catch (err) {
      U.toast('Could not save: ' + err.message, 'bad', 5000);
    }
  }

  /* Pull applications again and re-render only if something actually moved,
     so this can be called freely without flicker. */
  async function refreshApps() {
    try {
      const res = await api.getApplications();
      const next = res.applications || [];
      if (JSON.stringify(next) === JSON.stringify(apps)) return;
      apps = next;
      paintBadges();
      if (['tracker', 'cv', 'hunt'].indexOf(currentView()) !== -1) render();
    } catch (_) { /* offline or signed out; the next action will surface it */ }
  }

  const setSync = text => { const n = $('#sync-state'); if (n) n.textContent = text; };

  function paintBadges() {
    const pb = $('#badge-profile'), ab = $('#badge-apps');
    if (pb && completeness) {
      pb.textContent = completeness.percent + '%';
      pb.className = 'nav-badge' + (completeness.percent < 60 ? ' warn' : '');
    }
    if (ab) {
      const live = apps.filter(a => a.stage !== 'closed').length;
      ab.textContent = live ? String(live) : '';
    }
  }

  /* =====================================================
     Auth gate
     ===================================================== */
  function showGate(message) {
    const gate = $('#gate'), inner = $('#gate-inner');
    $('#app').hidden = true;
    gate.hidden = false;

    let mode = 'login';
    const email = el('input', { type: 'email', placeholder: 'you@example.com', autocomplete: 'username' });
    const pass  = el('input', { type: 'password', placeholder: 'At least 8 characters',
      autocomplete: 'current-password' });
    const error = el('p.gate-err', { text: message || '' });
    const submit = el('button.btn.btn-primary.btn-block.btn-lg', { text: 'Sign in', type: 'submit' });

    const go = async e => {
      e.preventDefault();
      error.textContent = '';
      if (!email.value.trim() || pass.value.length < 8) {
        error.textContent = 'Email, and a password of at least 8 characters.';
        return;
      }
      submit.disabled = true;
      submit.textContent = mode === 'login' ? 'Signing in…' : 'Creating…';
      try {
        user = mode === 'login'
          ? await api.login(email.value.trim(), pass.value)
          : await api.register(email.value.trim(), pass.value);
        gate.hidden = true;
        await start();
      } catch (err) {
        error.textContent = err.message;
      } finally {
        submit.disabled = false;
        submit.textContent = mode === 'login' ? 'Sign in' : 'Create account';
      }
    };

    const tab = (id, label) => el('button.gate-tab' + (mode === id ? '.on' : ''), {
      type: 'button', text: label,
      onclick: () => {
        mode = id;
        U.$$('.gate-tab', inner).forEach(t => t.classList.toggle('on', t.textContent === label));
        submit.textContent = id === 'login' ? 'Sign in' : 'Create account';
        pass.autocomplete = id === 'login' ? 'current-password' : 'new-password';
        error.textContent = '';
      }
    });

    U.clear(inner).appendChild(el('div', [
      el('div.gate-brand', [el('span.brand-mark', { text: 'JH' }), 'JobHunt']),
      el('p.muted.tiny', { text: 'Answer once. Hunt, tailor and track from the same profile.' }),
      el('div.gate-tabs', [tab('login', 'Sign in'), tab('register', 'Create account')]),
      el('form', { onsubmit: go }, [
        U.field('Email', email),
        U.field('Password', pass),
        error,
        submit
      ])
    ]));
    email.focus();
  }

  /* =====================================================
     Router and boot
     ===================================================== */
  const VIEWS = { profile: viewProfile, hunt: viewHunt, tracker: viewTracker,
                  cv: viewCv, account: viewAccount };

  function currentView() {
    const name = (location.hash.replace('#/', '') || 'profile').split('?')[0];
    return VIEWS[name] ? name : 'profile';
  }

  function render() {
    const name = currentView();
    U.$$('#nav .nav-item').forEach(a =>
      a.classList.toggle('active', a.dataset.view === name));
    const host = $('#view');
    U.clear(host).appendChild(VIEWS[name]());
  }

  const scrollTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  async function start() {
    $('#app').hidden = false;
    $('#who').textContent = user.email;

    const [pr, ar] = await Promise.all([api.getProfile(), api.getApplications()]);
    profile = pr.profile;
    completeness = pr.completeness;
    apps = ar.applications || [];

    seedDefaults();
    paintBadges();
    setSync('');
    render();
  }

  /* Give a brand-new profile the scaffolding to type into, rather than an
     empty page with an Add button. */
  function seedDefaults() {
    if (!profile.evidence || !profile.evidence.length) {
      profile.evidence = JH.DEFAULT_EVIDENCE_GROUPS.map(g => ({ group: g, items: [''] }));
    }
    if (!profile.positioning || !profile.positioning.length) {
      profile.positioning = JH.DEFAULT_POSITIONING.map(r => ({ role_type: r, guidance: '' }));
    }
    if (!profile.identity.email && user) profile.identity.email = user.email;
  }

  function applyTheme(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    try { localStorage.setItem('jobhunt.theme', mode); } catch (_) {}
  }

  async function boot() {
    let stored = 'auto';
    try { stored = localStorage.getItem('jobhunt.theme') || 'auto'; } catch (_) {}
    applyTheme(stored);

    $('#theme-toggle').onclick = () => {
      const now = document.documentElement.getAttribute('data-theme');
      applyTheme(now === 'dark' ? 'light' : now === 'light' ? 'auto' : 'dark');
    };

    $('#signout-btn').onclick = async () => {
      await api.logout().catch(() => {});
      user = null; profile = null; apps = [];
      showGate('Signed out.');
    };

    window.addEventListener('hashchange', () => {
      render();
      // Applications change from imports, from another tab, and from the
      // tracker itself. Every view that lists them needs the current set,
      // not whatever was loaded at boot.
      if (['tracker', 'cv', 'hunt'].indexOf(currentView()) !== -1) refreshApps();
    });
    window.addEventListener('beforeunload', e => {
      if (saveTimer) { clearTimeout(saveTimer); saveProfile(); }
    });

    try {
      user = await api.me();
      $('#gate').hidden = true;
      await start();
    } catch (err) {
      if (err.status === 401) showGate('');
      else showGate(err.message);
    }
  }

  document.addEventListener('DOMContentLoaded', boot);

})(window.JH);
