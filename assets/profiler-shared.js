/* ════════════════════════════════════════════════════════════════════════
   Fair Code - helpers shared by the single-dataset and compare views (#983)

   The keywords box (stored text, validation, restored note, cross-view event),
   the exact-test inputs, the file digest and held-out provenance entries, the
   skipped-column notes and the copy-button helpers used to exist twice, in
   profiler-ui.js and profiler-compare.js, differing only by an element-id
   prefix. Loaded before both views; they read it from window.FairCodeShared.
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // Written into every web export's provenance; tests/test_js_parity_provenance.py checks it against
  // faircode.__version__ and pyproject.toml (#996).
  var VERSION = '2.4.0';

  // ── Keywords box ────────────────────────────────────────────────────────
  // Extra keywords describe the user's data conventions, not one file, so the text
  // survives file loads and page reloads (#888); localStorage can throw or be absent.
  var KEYWORDS_KEY = 'faircode.keywords.v1';
  function readStoredKeywords() {
    try { return window.localStorage.getItem(KEYWORDS_KEY) || ''; } catch (err) { return ''; }
  }
  function writeStoredKeywords(text) {
    try {
      if (text) window.localStorage.setItem(KEYWORDS_KEY, text); else window.localStorage.removeItem(KEYWORDS_KEY);
    } catch (err) { /* private window or blocked storage: the box just forgets */ }
  }
  // Names the problem under the textarea (role=alert, linked by aria-describedby) as well as
  // marking it invalid; an empty message clears both (#889).
  function setKeywordsError(area, message) {
    var note = document.getElementById(area.getAttribute('aria-describedby') || '');
    if (message) area.setAttribute('aria-invalid', 'true'); else area.removeAttribute('aria-invalid');
    if (note) { note.textContent = message || ''; note.hidden = !message; }
  }
  // Parses and validates the textarea text. Returns {empty:true}, {value:parsed} or
  // {error:message}; the engine's own vocabulary check supplies the rejection text.
  function checkKeywordsText(raw) {
    if (raw === '') return { empty: true };
    var parsed;
    try { parsed = JSON.parse(raw); } catch (err) { return { error: 'Not valid JSON: ' + err.message }; }
    try { window.FairCodeProfiler.normalizeKeywords(parsed); } catch (err) { return { error: err.message }; }
    return { value: parsed };
  }

  // "Restored from your last session" + Forget next to the keywords box (#930).
  function showRestoredNote(area, on) {
    var note = document.getElementById(area.id.replace('Input', 'Restored'));
    if (note) note.hidden = !on;
  }

  // Tell the other view that the vocabulary changed (#901); each view listens for KEYWORDS_EVENT
  // and refills its own box from the one stored text.
  var KEYWORDS_EVENT = 'faircode-keywords';
  function announceKeywords(area) {
    try { document.dispatchEvent(new CustomEvent(KEYWORDS_EVENT, { detail: { source: area.id } })); } catch (err) { /* no CustomEvent */ }
  }

  // ── Exact-test inputs ───────────────────────────────────────────────────
  // The Shuffles / Row cap inputs are only live while the exact box is ticked (#962). `prefix` is
  // the element-id prefix of the view: 'proxy' or 'compareProxy'.
  function createExactInputs(prefix) {
    function controls() {
      return { box: document.getElementById(prefix + 'ExactInput'),
               perm: document.getElementById(prefix + 'ExactPermutationsInput'),
               rows: document.getElementById(prefix + 'ExactMaxRowsInput'),
               error: document.getElementById(prefix + 'ExactError') };
    }
    function clearError() {
      var c = controls();
      [c.perm, c.rows].forEach(function (input) { input.removeAttribute('aria-invalid'); });
      c.error.textContent = '';
      c.error.hidden = true;
    }
    function showError(message) {
      var c = controls();
      clearError();
      (/^Shuffles/.test(message) ? c.perm : c.rows).setAttribute('aria-invalid', 'true');
      c.error.textContent = message;
      c.error.hidden = false;
    }
    function sync() {
      var c = controls();
      c.perm.disabled = c.rows.disabled = !c.box.checked;
      if (!c.box.checked) clearError();
    }
    function wire() {
      var c = controls();
      if (!c.box) return;
      c.box.addEventListener('change', sync);
      [c.perm, c.rows].forEach(function (input) { input.addEventListener('input', clearError); });
      sync();
    }
    return { controls: controls, clearError: clearError, showError: showError, sync: sync, wire: wire };
  }

  // ── Provenance and notes ────────────────────────────────────────────────
  // Hashes the raw File object's bytes, or reports why it can't (in-memory sample data, a read
  // failure) so an export can be tied back to what produced it (issue #375).
  async function fileDigest(file) {
    if (!file) {
      return {
        digest: null,
        note: 'dataset was generated in memory; raw bytes were not retained'
      };
    }
    try {
      var buffer = await file.arrayBuffer();
      var hash = await crypto.subtle.digest('SHA-256', buffer);
      var bytes = new Uint8Array(hash);
      var hex = Array.prototype.map.call(bytes, function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
      return { digest: 'sha256:' + hex, note: null };
    } catch (err) {
      return { digest: null, note: 'could not read file for hashing: ' + err.message };
    }
  }

  // Held-out files behind the proxy results, as {path, column, sha256[, sha256_note]}
  // like faircode/provenance.py's held_out_entries() (#811).
  async function heldOutEntries(specs) {
    var out = [];
    for (var i = 0; i < specs.length; i++) {
      var h = await fileDigest(specs[i].file);
      var entry = { path: specs[i].name, column: specs[i].column };
      if (specs[i].key) {
        entry.key = specs[i].key;
        if (specs[i].normalize) entry.key_normalize = true;
      }
      entry.sha256 = h.digest;
      if (h.note !== null) entry.sha256_note = h.note;
      if (specs[i].sheet) { entry.sheet = specs[i].sheet; entry.sheets_ignored = specs[i].sheetsIgnored; }
      if (specs[i].skipped) { entry.tested = false; entry.skip_reason = 'near-unique values (looks like an identifier)'; }
      if (specs[i].encoding) entry.encoding = specs[i].encoding;
      out.push(entry);
    }
    return out;
  }

  // Skipped near-unique held-out columns reach the exported result as `notes`, like the CLI (#951).
  function setSkipNotes(target, specs) {
    var notes = (specs || []).filter(function (h) { return h.skipped; }).map(function (h) { return h.skipNote; });
    if (notes.length) target.notes = notes; else delete target.notes;
  }

  // ── Copy buttons ────────────────────────────────────────────────────────
  function flashButton(btn, msg) {
    var original = btn.textContent;
    btn.textContent = msg;
    btn.disabled = true;
    setTimeout(function () {
      btn.textContent = original;
      btn.disabled = false;
    }, 1500);
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  // ── Small helpers both views used to define twice (#1008) ───────────────
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function pct(x) { return (x * 100).toFixed(1) + '%'; }
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  // Significance level for the proxy check (--proxy-alpha, #786): blank means
  // the 0.05 default; anything outside (0, 1] is rejected like the CLI does.
  function readProxyAlpha(input, host) {
    var raw = input.value.trim();
    if (raw === '') return 0.05;
    var a = parseFloat(raw);
    if (!(a > 0 && a <= 1)) {
      host.innerHTML = '<p class="profiler-error">Significance level must be in (0, 1].</p>';
      return null;
    }
    return a;
  }
  // {column: kind} for every mapping select in `list` that is not Auto; marks the row as overridden.
  function readOverrides(list) {
    var overrides = {};
    var selects = list.querySelectorAll('.map-select');
    for (var i = 0; i < selects.length; i++) {
      var sel = selects[i];
      var row = sel.closest('.map-row');
      if (sel.value !== 'auto') {
        overrides[sel.getAttribute('data-col')] = sel.value;
        if (row) row.classList.add('overridden');
      } else if (row) {
        row.classList.remove('overridden');
      }
    }
    return overrides;
  }

  window.FairCodeShared = {
    VERSION: VERSION, KEYWORDS_KEY: KEYWORDS_KEY, KEYWORDS_EVENT: KEYWORDS_EVENT,
    readStoredKeywords: readStoredKeywords, writeStoredKeywords: writeStoredKeywords,
    setKeywordsError: setKeywordsError, checkKeywordsText: checkKeywordsText,
    showRestoredNote: showRestoredNote, announceKeywords: announceKeywords,
    createExactInputs: createExactInputs, fileDigest: fileDigest, heldOutEntries: heldOutEntries,
    esc: esc, pct: pct, prefersReducedMotion: prefersReducedMotion, readProxyAlpha: readProxyAlpha,
    readOverrides: readOverrides, setSkipNotes: setSkipNotes, flashButton: flashButton, fallbackCopy: fallbackCopy
  };
})();
