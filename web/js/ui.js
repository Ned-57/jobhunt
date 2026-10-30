/* =====================================================
   ui.js - DOM helpers, toasts, modals, small formatters
   ===================================================== */
window.JH = window.JH || {};
(function (JH) {
  'use strict';

  const U = JH.ui = {};

  /* ---------- element creation ----------
     el('div.card#id', {onclick:fn}, [children])                       */
  U.el = function (spec, attrs, kids) {
    if (Array.isArray(attrs)) { kids = attrs; attrs = null; }
    const m = /^([a-z0-9]+)?((?:[.#][\w-]+)*)$/i.exec(spec) || [];
    const node = document.createElement(m[1] || 'div');
    (m[2] || '').split(/(?=[.#])/).filter(Boolean).forEach(t => {
      if (t[0] === '#') node.id = t.slice(1); else node.classList.add(t.slice(1));
    });
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'html') node.innerHTML = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else if (v === true) node.setAttribute(k, '');
      else node.setAttribute(k, v);
    }
    U.add(node, kids);
    return node;
  };

  U.add = function (parent, kids) {
    if (kids === null || kids === undefined || kids === false) return parent;
    if (Array.isArray(kids)) { kids.forEach(k => U.add(parent, k)); return parent; }
    parent.appendChild(kids instanceof Node ? kids : document.createTextNode(String(kids)));
    return parent;
  };

  U.clear = node => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
  U.$  = (sel, root) => (root || document).querySelector(sel);
  U.$$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ---------- escaping ---------- */
  U.esc = s => String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  /* ---------- ids ---------- */
  U.uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  /* ---------- dates ---------- */
  /* The user's calendar day, not UTC's. After 23:00 BST these differ, and a
     due date that flips a day early reads as a bug. */
  U.today = function () {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  };

  U.fmtDate = function (iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  U.fmtMonth = function (val) {
    if (!val) return '';
    const m = /^(\d{4})-(\d{2})$/.exec(val);
    if (!m) return String(val);
    const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
    return d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
  };

  U.fmtDateTime = function (iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + ', ' +
           d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  };

  U.daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);

  U.relative = function (iso) {
    if (!iso) return '';
    const days = U.daysBetween(iso, new Date().toISOString());
    if (days === 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 0) return 'in ' + Math.abs(days) + ' day' + (days === -1 ? '' : 's');
    if (days < 31) return days + ' days ago';
    if (days < 365) return Math.round(days / 30) + ' months ago';
    return Math.round(days / 365) + ' years ago';
  };

  /* ---------- toasts ---------- */
  U.toast = function (msg, kind, ms) {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const t = U.el('div.toast' + (kind ? '.' + kind : ''), { text: msg });
    root.appendChild(t);
    setTimeout(() => {
      t.style.transition = 'opacity .2s'; t.style.opacity = '0';
      setTimeout(() => t.remove(), 220);
    }, ms || 2800);
  };

  /* ---------- modal ----------
     U.modal({title, body, wide, actions:[{label,kind,onClick,close}]})
     Returns {close()}                                                  */
  U.modal = function (opts) {
    const root = document.getElementById('modal-root');
    const back = U.el('div.modal-back');
    const box  = U.el('div.modal' + (opts.wide ? '.wide' : ''));

    const close = () => { back.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = e => { if (e.key === 'Escape') close(); };

    box.appendChild(U.el('div.modal-head', [
      U.el('h2', { text: opts.title || '' }),
      U.el('div.spacer'),
      U.el('button.btn.btn-ghost.btn-sm', { text: 'Close', type: 'button', onclick: close })
    ]));

    const body = U.el('div.modal-body');
    U.add(body, typeof opts.body === 'function' ? opts.body(close) : opts.body);
    box.appendChild(body);

    if (opts.actions && opts.actions.length) {
      box.appendChild(U.el('div.modal-foot', opts.actions.map(a =>
        U.el('button.btn' + (a.kind ? '.btn-' + a.kind : ''), {
          text: a.label, type: 'button',
          onclick: () => {
            const r = a.onClick ? a.onClick(close) : undefined;
            if (a.close !== false && r !== false) close();
          }
        })
      )));
    }

    back.appendChild(box);
    back.addEventListener('mousedown', e => { if (e.target === back) close(); });
    document.addEventListener('keydown', onKey);
    root.appendChild(back);
    const first = box.querySelector('input,textarea,select');
    if (first) setTimeout(() => first.focus(), 30);
    return { close, box, body };
  };

  U.confirm = function (title, message, confirmLabel) {
    return new Promise(resolve => {
      U.modal({
        title,
        body: U.el('p', { text: message }),
        actions: [
          { label: 'Cancel', onClick: () => resolve(false) },
          { label: confirmLabel || 'Confirm', kind: 'danger', onClick: () => resolve(true) }
        ]
      });
    });
  };

  /* ---------- pasted bullet blocks ----------
     Mirrors app/custard.py so a paste behaves the same whether it is split
     here or on the way into the model. Kept deliberately conservative: a
     single line of prose comes back as one entry, never chopped up. */
  // A literal so the escapes are the regex's, not a string's. Anything used
  // as a bullet in Word, Docs, a PDF viewer or a plain text file.
  const BULLET_PREFIX =
    /^\s*(?:[*\-•▪●◦○■‣⁃›·∙+–—※▸►→]+|\d{1,2}[.)])\s*/;

  U.stripBullet = line => String(line || '').replace(BULLET_PREFIX, '').trim();

  U.splitBullets = function (text) {
    let s = String(text || '')
      .replace(/\r\n?/g, '\n')
      .replace(/[​‌‍⁠﻿­]/g, '')   // invisibles
      .replace(/ /g, ' ');
    if (!s.trim()) return [];

    // A block copied from a rendered document can arrive as one line with
    // glyphs acting as the separator.
    const parts = s.indexOf('\n') === -1
      ? s.split(/(?<=\S)\s*[•●▪]\s*/)
      : s.split('\n');

    return parts.map(U.stripBullet).filter(Boolean);
  };

  /* ---------- clipboard ---------- */
  U.copy = async function (text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // clipboard API needs a secure context; fall back to a hidden textarea
      const ta = U.el('textarea', {
        style: { position: 'fixed', top: '-2000px', opacity: '0' }
      });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
      ta.remove();
      return ok;
    }
  };

  /* ---------- download a generated file ---------- */
  U.download = function (filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = U.el('a', { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  };

  /* ---------- form field builders ---------- */
  U.field = function (labelText, control, hint) {
    return U.el('div.field', [
      labelText ? U.el('label', { text: labelText }) : null,
      control,
      hint ? U.el('div.hint', { text: hint }) : null
    ]);
  };

  U.input = function (value, onInput, attrs) {
    const node = U.el('input', Object.assign({ type: 'text', value: value || '' }, attrs || {}));
    node.addEventListener('input', () => onInput(node.value));
    return node;
  };

  U.textarea = function (value, onInput, attrs) {
    const node = U.el('textarea', attrs || {});
    node.value = value || '';
    node.addEventListener('input', () => onInput(node.value));
    return node;
  };

  /* An entry of the form {group, options:[...]} becomes an <optgroup>, so a
     long list can be sorted into sections without hiding anything. */
  U.select = function (value, options, onChange, attrs) {
    const node = U.el('select', attrs || {});
    const addOption = (parent, o) => parent.appendChild(
      U.el('option', { value: o.id !== undefined ? o.id : o, text: o.name || o }));
    options.forEach(o => {
      if (o && o.group && Array.isArray(o.options)) {
        if (!o.options.length) return;
        const group = U.el('optgroup', { label: o.group });
        o.options.forEach(child => addOption(group, child));
        node.appendChild(group);
      } else {
        addOption(node, o);
      }
    });
    node.value = value === null || value === undefined ? '' : value;
    node.addEventListener('change', () => onChange(node.value));
    return node;
  };

  U.checkbox = function (labelText, checked, onChange) {
    const box = U.el('input', { type: 'checkbox' });
    box.checked = !!checked;
    box.addEventListener('change', () => onChange(box.checked));
    return U.el('label.check', [box, U.el('span', { text: labelText })]);
  };

  /* ---------- multi-select chips backed by a string array ---------- */
  U.chipList = function (values, onChange, opts) {
    opts = opts || {};
    const wrap = U.el('div');
    const render = () => {
      U.clear(wrap);
      const group = U.el('div.chip-group');
      values.forEach((v, i) => {
        group.appendChild(U.el('span.chip.on', [
          U.el('span', { text: v }),
          U.el('span.chip-x', {
            text: '×', title: 'Remove',
            onclick: () => { values.splice(i, 1); onChange(values); render(); }
          })
        ]));
      });
      wrap.appendChild(group);

      const box = U.el('input', {
        type: 'text', placeholder: opts.placeholder || 'Type and press Enter',
        style: { marginTop: values.length ? '8px' : '0' }
      });
      box.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ',') return;
        e.preventDefault();
        const v = box.value.trim().replace(/,$/, '');
        if (v && values.indexOf(v) === -1) { values.push(v); onChange(values); render(); }
        else box.value = '';
      });

      // A pasted list becomes one chip per item, commas included since these
      // fields are usually copied out of a comma-separated skills line.
      box.addEventListener('paste', e => {
        const pasted = (e.clipboardData || window.clipboardData).getData('text');
        const items = U.splitBullets(pasted)
          .flatMap(line => line.split(',').map(part => part.trim()))
          .filter(Boolean);
        if (items.length < 2) return;
        e.preventDefault();
        let added = 0;
        items.forEach(item => {
          if (values.indexOf(item) === -1) { values.push(item); added++; }
        });
        if (!added) return;
        onChange(values);
        render();
        U.toast('Added ' + U.pluralise(added, 'entry', 'entries') + '.', 'ok');
      });

      wrap.appendChild(box);

      if (opts.suggest && opts.suggest.length) {
        const sug = opts.suggest.filter(s => values.indexOf(s) === -1);
        if (sug.length) {
          wrap.appendChild(U.el('div.chip-group', { style: { marginTop: '8px' } },
            sug.map(s => U.el('span.chip', {
              text: '+ ' + s,
              onclick: () => { values.push(s); onChange(values); render(); }
            }))
          ));
        }
      }
      const inp = wrap.querySelector('input');
      if (inp && document.activeElement !== document.body) inp.focus();
    };
    render();
    return wrap;
  };

  /* ---------- toggle group (pick many from a fixed set) ---------- */
  U.toggleSet = function (all, values, onChange) {
    const group = U.el('div.chip-group');
    all.forEach(a => {
      const on = values.indexOf(a) !== -1;
      group.appendChild(U.el('span.chip' + (on ? '.on' : ''), {
        text: a,
        onclick: e => {
          const i = values.indexOf(a);
          if (i === -1) values.push(a); else values.splice(i, 1);
          e.target.classList.toggle('on');
          onChange(values);
        }
      }));
    });
    return group;
  };

  /* ---------- editable list of plain strings (one textarea per line) ---------- */
  U.lineList = function (values, onChange, opts) {
    opts = opts || {};
    const wrap = U.el('div.bullets');
    const render = () => {
      U.clear(wrap);
      values.forEach((v, i) => {
        const ta = U.el('textarea', { placeholder: opts.placeholder || '' });
        ta.value = v;
        ta.addEventListener('input', () => { values[i] = ta.value; onChange(values); });

        // Paste a block of bullets straight off a CV and it becomes one entry
        // per bullet, rather than a single box full of newlines.
        ta.addEventListener('paste', e => {
          const pasted = (e.clipboardData || window.clipboardData).getData('text');
          const lines = U.splitBullets(pasted);
          if (lines.length < 2) return;   // ordinary paste, leave it alone
          e.preventDefault();

          // Respect where the caret was: text before it stays, text after it
          // is pushed onto the last new entry.
          const before = ta.value.slice(0, ta.selectionStart);
          const after = ta.value.slice(ta.selectionEnd);
          lines[0] = (before + lines[0]).trim();
          lines[lines.length - 1] = (lines[lines.length - 1] + after).trim();

          values.splice(i, 1, ...lines);
          onChange(values);
          render();
          const boxes = wrap.querySelectorAll('textarea');
          const landed = boxes[Math.min(i + lines.length - 1, boxes.length - 1)];
          if (landed) { landed.focus(); landed.setSelectionRange(landed.value.length, landed.value.length); }
          U.toast('Split into ' + lines.length + ' entries.', 'ok');
        });

        wrap.appendChild(U.el('div.bullet-row', [
          ta,
          U.el('button.btn.btn-ghost.btn-sm', {
            text: '×', title: 'Remove', type: 'button',
            onclick: () => { values.splice(i, 1); onChange(values); render(); }
          })
        ]));
      });
      wrap.appendChild(U.el('button.btn.btn-sm', {
        text: opts.addLabel || '+ Add', type: 'button',
        style: { alignSelf: 'flex-start' },
        onclick: () => { values.push(''); onChange(values); render(); const t = wrap.querySelectorAll('textarea'); if (t.length) t[t.length - 1].focus(); }
      }));
      if (opts.examples && opts.examples.length) {
        wrap.appendChild(U.el('div.hint', { text: 'Examples: ' + opts.examples.join('  ·  ') }));
      }
    };
    render();
    return wrap;
  };

  /* ---------- minimal markdown for job descriptions ---------- */
  U.mdLite = function (src) {
    const lines = String(src || '').split(/\r?\n/);
    let out = '', inList = false;
    const inline = s => U.esc(s)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    lines.forEach(raw => {
      const line = raw.trim();
      const li = /^[-*•]\s+(.*)$/.exec(line);
      if (li) { if (!inList) { out += '<ul>'; inList = true; } out += '<li>' + inline(li[1]) + '</li>'; return; }
      if (inList) { out += '</ul>'; inList = false; }
      if (!line) return;
      const h = /^(#{1,4})\s+(.*)$/.exec(line);
      if (h) { out += '<h3>' + inline(h[2]) + '</h3>'; return; }
      out += '<p>' + inline(line) + '</p>';
    });
    if (inList) out += '</ul>';
    return out;
  };

  /* ---------- misc ---------- */
  U.pluralise = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  U.truncate = (s, n) => (s = String(s || ''), s.length > n ? s.slice(0, n - 1) + '…' : s);
  U.stripHtml = s => String(s || '').replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|li|div|h\d)>/gi, '\n')
    .replace(/<li[^>]*>/gi, '- ').replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n').trim();

  U.pageHead = function (title, sub, actions) {
    return U.el('div.page-head', [
      U.el('div.ph-text', [
        U.el('h1', { text: title }),
        sub ? U.el('p.page-sub', { text: sub }) : null
      ]),
      actions ? U.el('div.page-actions', actions) : null
    ]);
  };

  U.empty = function (title, message, action) {
    return U.el('div.card', [U.el('div.empty', [
      U.el('h3', { text: title }),
      U.el('p.muted', { text: message }),
      action || null
    ])]);
  };

})(window.JH);
