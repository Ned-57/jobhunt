/* =====================================================
   api.js - everything that talks to the Python backend
   ===================================================== */
window.JH = window.JH || {};
(function (JH) {
  'use strict';

  const api = JH.api = {};

  async function request(method, path, body) {
    let response;
    try {
      response = await fetch(path, {
        method,
        credentials: 'same-origin',
        // Never serve an API response from the HTTP cache. Without this a
        // cached error response survives a server restart and the app keeps
        // reporting a failure that no longer exists.
        cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (networkError) {
      throw new ApiError('Could not reach the server. Is it still running?', 0);
    }

    if (response.status === 204) return null;

    let payload = null;
    const text = await response.text();
    if (text) {
      try { payload = JSON.parse(text); } catch (_) { payload = { detail: text }; }
    }

    if (!response.ok) {
      throw new ApiError(readDetail(payload) || response.statusText, response.status, payload);
    }
    return payload;
  }

  /* FastAPI returns validation errors as a list of objects; flatten them
     into something a person can read. */
  function readDetail(payload) {
    if (!payload) return '';
    const detail = payload.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map(d => {
        const where = Array.isArray(d.loc) ? d.loc.filter(p => p !== 'body').join('.') : '';
        return (where ? where + ': ' : '') + (d.msg || 'invalid');
      }).join('; ');
    }
    return '';
  }

  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.payload = payload;
    }
  }
  api.ApiError = ApiError;

  /* ---------- auth ---------- */
  api.register = (email, password) => request('POST', '/api/auth/register', { email, password });
  api.login    = (email, password) => request('POST', '/api/auth/login',    { email, password });
  api.logout   = ()                => request('POST', '/api/auth/logout');
  api.me       = ()                => request('GET',  '/api/auth/me');

  /* ---------- profile ---------- */
  api.getProfile  = ()        => request('GET', '/api/profile');
  api.saveProfile = (profile) => request('PUT', '/api/profile', profile);

  /* ---------- applications ---------- */
  api.getApplications  = ()     => request('GET', '/api/applications');
  api.saveApplications = (apps) => request('PUT', '/api/applications', { applications: apps });

  /* ---------- prompts and import ---------- */
  api.buildPrompt = (opts) => request('POST', '/api/prompt', Object.assign({
    kind: 'hunt', brief: '', advert: '', application_id: '',
    include_boundaries: true, max_results: 12
  }, opts || {}));

  api.importReply = (text) => request('POST', '/api/import', { text });

  /* ---------- CV, built locally from the profile - no AI call ---------- */
  api.buildCv = (opts) => request('POST', '/api/cv', Object.assign({
    application_id: '', advert: '', title: '', company: '',
    max_lines: 9, include_independent: true, tailoring: null
  }, opts || {}));

  /* Re-render a CV the user has edited by hand, so markdown and the page
     verdict stay true without a second renderer in the browser. */
  api.renderCv = (doc) => request('POST', '/api/cv/render', doc);

  /* Binary response, so this bypasses the JSON helper. Returns a Blob and
     the filename the server chose. */
  api.cvDocx = async function (doc) {
    let response;
    try {
      response = await fetch('/api/cv/docx', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc)
      });
    } catch (e) {
      throw new ApiError('Could not reach the server.', 0);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = readDetail(await response.json()) || detail; } catch (_) {}
      throw new ApiError(detail, response.status);
    }
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="([^"]+)"/.exec(disposition);
    return { blob: await response.blob(), filename: match ? match[1] : 'cv.docx' };
  };

  /* ---------- mine an existing CV ----------
     Multipart, so it bypasses the JSON request helper. */
  api.mineCvs = async function (fileList) {
    const form = new FormData();
    Array.from(fileList).forEach(f => form.append('files', f, f.name));
    let response;
    try {
      response = await fetch('/api/mine', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', body: form
      });
    } catch (e) {
      throw new ApiError('Could not reach the server.', 0);
    }
    const text = await response.text();
    let payload = null;
    try { payload = JSON.parse(text); } catch (_) { payload = { detail: text }; }
    if (!response.ok) throw new ApiError(readDetail(payload) || response.statusText, response.status, payload);
    return payload;
  };

  /* ---------- meta ---------- */
  api.health = () => request('GET', '/api/health');

})(window.JH);
