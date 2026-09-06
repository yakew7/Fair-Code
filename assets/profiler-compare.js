/* ════════════════════════════════════════════════════════════════════════
   Fair Code - Dataset Profiler: COMPARE controller (representation drift)

   Wires the two "A / B" dropzones to the engine's compare() and renders the
   side-by-side drift view. Like the single-profile UI, nothing is uploaded -
   both files are read locally with FileReader and diffed in-page.
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var DISPLAY_GROUPS = 12; // mirror faircode/report.py
  var FAIRCODE_VERSION = '2.2.0'; // mirrors profiler-ui.js's own copy
  var E = window.FairCodeProfiler;
  if (!E || !E.compare) return;

  var dropA = document.getElementById('dropA');
  var dropB = document.getElementById('dropB');
  var fileA = document.getElementById('fileA');
  var fileB = document.getElementById('fileB');
  var nameAEl = document.getElementById('nameA');
  var nameBEl = document.getElementById('nameB');
  var sampleBtn = document.getElementById('compareSampleBtn');
  var errorEl = document.getElementById('compareError');
  var fileStatusA = document.getElementById('statusA');
  var fileStatusB = document.getElementById('statusB');
  var resultsEl = document.getElementById('compareResults');
  var announcer = document.getElementById('compareAnnouncer');
  var reportActionsEl = document.getElementById('compareReportActions');
  var downloadHtmlBtn = document.getElementById('compareDownloadHtmlBtn');
  var copyJsonBtn = document.getElementById('compareCopyJsonBtn');
  var mappingBlock = document.getElementById('compareMappingBlock');
  var mappingList = document.getElementById('compareMappingList');
  var thresholdsBlock = document.getElementById('compareThresholdsBlock');
  var thresholdControls = document.getElementById('compareThresholdControls');
  var thresholdInputs = thresholdControls ?
    Array.prototype.slice.call(thresholdControls.querySelectorAll('[data-opt]')) : [];
  // Placeholders come from the engine's own defaults (issue #377), not a
  // hardcoded copy in profiler.html that could silently drift from them.
  thresholdInputs.forEach(function (input) {
    var def = E.DEFAULT_OPTS && E.DEFAULT_OPTS[input.dataset.opt];
    if (def !== undefined) input.placeholder = String(def);
  });

  // Kinds a column can be manually mapped to, plus Auto / Not-demographic.
  // Mirrors assets/profiler-ui.js's MAP_OPTIONS (issue #62's panel, ported
  // here for the compare view).
  var MAP_OPTIONS = [
    ['auto', 'Auto'], ['sex', 'Sex'], ['race', 'Race'], ['age', 'Age'],
    ['geography', 'Geography'], ['categorical', 'Categorical'], ['ignore', 'Not demographic']
  ];

  // Loaded datasets: each { table, name } once a valid file is parsed.
  var slot = { A: null, B: null };
  var currentCmp = null; // last successful compare() result, for export
  var currentOverrides = {}; // column -> forced kind, applied to both A and B
  var currentOpts = {}; // threshold overrides (issue #351), applied to both A and B

  function pct(x) { return (x * 100).toFixed(1) + '%'; }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function signed(x, dp) {
    var s = x.toFixed(dp === undefined ? 1 : dp);
    return (x > 0 ? '+' : '') + s;
  }
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // Ported from profiler-ui.js's fileDigest (issue #375) - hashes the raw
  // File object's bytes, or reports why it can't (in-memory sample data,
  // a read failure) so a Compare export can be tied back to what produced
  // it the same way the Profile view's export and the CLI/MCP provenance
  // block already can.
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

  // ── File wiring for one slot ('A' or 'B') ──────────────────────────────
  function wireSlot(key, drop, input, nameEl) {
    drop.addEventListener('click', function () { input.click(); });
    drop.addEventListener('keydown', function (e) {
      if (e.target !== drop) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
    });
    input.addEventListener('change', function (e) {
      if (e.target.files && e.target.files[0]) readFile(key, e.target.files[0], drop, nameEl);
      drop.focus();
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        if (ev === 'dragleave' && drop.contains(e.relatedTarget)) return;
        drop.classList.remove('dragover');
      });
    });
    drop.addEventListener('drop', function (e) {
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) readFile(key, f, drop, nameEl);
    });
  }

  function readFile(key, file, drop, nameEl) {
    var statusEl = key === 'A' ? fileStatusA : fileStatusB;
    var okExt = /\.(csv|tsv|json|xlsx)$/i.test(file.name);
    var okType = file.type === 'text/csv' || file.type === 'text/tab-separated-values' ||
      file.type === 'application/json' ||
      file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    if (!okExt && !okType) return showError('Please choose a .csv, .tsv, .json, or .xlsx file.');

    var reader = new FileReader();
    reader.onerror = function () { showError('Could not read dataset ' + key + '.'); };

    function applyTable(table) {
      if (!table.columns.length || !table.rows.length) {
        return showError('Dataset ' + key + ' looks empty or has no data rows.');
      }
      setSlot(key, table, file.name, drop, nameEl, file);
    }

    if (/\.xlsx$/i.test(file.name)) {
      reader.onload = async function () {
        try {
          var result = await E.parseXLSX(reader.result);

          applyTable(result.table);

          if (result.ignoredSheets.length > 0) {
            statusEl.textContent =
              'Read sheet "' + result.sheetName + '" - ' +
              result.ignoredSheets.length + ' other sheet(s) ignored.';
            statusEl.hidden = false;
          } else {
            statusEl.textContent =
              'Read sheet "' + result.sheetName + '".';
            statusEl.hidden = false;
          }
        } catch (err) {
          showError('Could not read dataset ' + key + ': ' + err.message);
        }
      };
      reader.readAsArrayBuffer(file);
    } else {
      reader.onload = async function () {
        try {
          var text = String(reader.result);
          var table = (/\.json$/i.test(file.name) || file.type === 'application/json')
            ? E.parseJSON(text) : E.parseCSV(text);
          applyTable(table);
        } catch (err) {
          showError('Could not read dataset ' + key + ': ' + err.message);
        }
      };
      reader.readAsText(file);
    }
  }

  function setSlot(key, table, name, drop, nameEl, file) {
    slot[key] = { table: table, name: name, file: file || null };
    nameEl.textContent = name;
    drop.classList.add('loaded');
    errorEl.hidden = true;
    currentOverrides = {}; // a changed input may have an entirely different schema
    currentOpts = {};
    resetThresholdInputs();
    thresholdsBlock.hidden = false;
    renderMapping(); // rebuild the panel for the new column set (once per file load)
    maybeCompare();
  }

  function resetThresholdInputs() {
    thresholdInputs.forEach(function (input) {
      input.value = '';
      input.classList.remove('overridden');
    });
  }

  thresholdInputs.forEach(function (input) {
    input.addEventListener('input', function () {
      var opt = input.dataset.opt;
      var raw = input.value.trim();
      if (raw === '') {
        delete currentOpts[opt];
        input.classList.remove('overridden');
      } else {
        var num = Number(raw);
        if (Number.isNaN(num)) return;
        currentOpts[opt] = num;
        input.classList.add('overridden');
      }
      maybeCompare(false);
    });
  });

  function maybeCompare(scroll) {
    if (!slot.A || !slot.B) return;
    try {
      var cmp = E.compare(E.profile(slot.A.table, currentOverrides, currentOpts),
                          E.profile(slot.B.table, currentOverrides, currentOpts),
                          slot.A.name, slot.B.name);
      errorEl.hidden = true;
      render(cmp, scroll !== false);
    } catch (err) {
      showError('Could not compare those files: ' + err.message);
    }
  }

  // ── Column mapping (issue #62's panel, ported for the two-dataset view) ──
  // Applies the same override dict to both A and B - a column renamed or
  // mistyped the same way on both sides (the common case) only needs mapping
  // once, and there is no single "auto-detected kind" to show per column
  // when A and B can each auto-detect it differently, so the hint instead
  // shows both sides' auto-detected kind (or "not detected").
  function renderMapping() {
    var columns = [];
    var seen = {};
    [slot.A, slot.B].forEach(function (s) {
      if (!s) return;
      s.table.columns.forEach(function (col) {
        if (!seen[col]) { seen[col] = true; columns.push(col); }
      });
    });
    if (!columns.length) { mappingBlock.hidden = true; return; }

    // Profile each side once (no overrides) and cache the column -> kind
    // map, rather than re-running profile() per column below.
    function autoKindsFor(s) {
      if (!s) return {};
      try {
        var kinds = {};
        E.profile(s.table).dimensions.forEach(function (d) { kinds[d.name] = d.kind; });
        return kinds;
      } catch (err) {
        return {};
      }
    }
    var autoKindsA = autoKindsFor(slot.A);
    var autoKindsB = autoKindsFor(slot.B);

    mappingList.innerHTML = '';
    columns.forEach(function (col) {
      var autoA = autoKindsA[col] || null;
      var autoB = autoKindsB[col] || null;
      var hint;
      if (!autoA && !autoB) {
        hint = 'auto: not detected';
      } else if (autoA === autoB) {
        hint = 'auto: <span class="on">' + esc(autoA) + '</span>';
      } else {
        hint = 'auto: <span class="on">A=' + esc(autoA || 'none') +
          ', B=' + esc(autoB || 'none') + '</span>';
      }

      var opts = MAP_OPTIONS.map(function (o) {
        return '<option value="' + o[0] + '">' + o[1] + '</option>';
      }).join('');

      var row = document.createElement('div');
      row.className = 'map-row';
      row.innerHTML =
        '<span class="map-col" title="' + esc(col) + '">' + esc(col) + '</span>' +
        '<span class="map-auto">' + hint + '</span>' +
        '<select class="map-select" data-col="' + esc(col) +
        '" aria-label="Map column ' + esc(col) + '">' + opts + '</select>';
      var select = row.querySelector('.map-select');
      select.value = currentOverrides[col] || 'auto';
      if (currentOverrides[col]) row.classList.add('overridden');

      mappingList.appendChild(row);
    });
    mappingBlock.hidden = false;
  }

  function readOverrides() {
    var overrides = {};
    var selects = mappingList.querySelectorAll('.map-select');
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

  // Delegated so it keeps working across re-renders of the list.
  mappingList.addEventListener('change', function (e) {
    if (!e.target.classList.contains('map-select')) return;
    currentOverrides = readOverrides();
    maybeCompare(false);
  });

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
    resultsEl.hidden = true;
    reportActionsEl.hidden = true;
    currentCmp = null;
  }

  // ── Rendering ──────────────────────────────────────────────────────────
  function render(cmp, scroll) {
    currentCmp = cmp;
    reportActionsEl.hidden = false;
    var d = cmp.score_delta;
    var measured = d !== null;
    var deltaClass = measured && d > 0 ? 'up' : measured && d < 0 ? 'down' : 'flat';
    var arrow = d === 0 ? '=' : '→';

    var summary =
      '<div class="drift-summary">' +
        scoreCell(cmp.a) +
        '<div class="drift-arrow" aria-hidden="true">' + arrow + '</div>' +
        scoreCell(cmp.b) +
        '<div class="drift-delta ' + deltaClass + '">' +
          (measured ? 'score ' + signed(d, 0) : 'score change not available') + '</div>' +
      '</div>';

    var flags = '';
    if (cmp.flags.length) {
      flags = '<div class="flags-block" style="margin-top:24px">' +
        '<h3><span aria-hidden="true">⚑</span> Drift flags <span class="count">(' +
        cmp.flags.length + ')</span></h3><ul>' +
        cmp.flags.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') +
        '</ul></div>';
    }

    var cards = cmp.dimensions.map(driftCard).join('');
    if (!cmp.dimensions.length) {
      cards = '<p class="section-note" style="margin-top:16px">No demographic dimension is ' +
        'present in both datasets, so there is nothing to compare directly.</p>';
    }

    var only = '';
    if (cmp.added_dimensions.length) {
      only += '<div class="drift-only">Only in B (' + esc(cmp.b.name) + '): <strong>' +
        cmp.added_dimensions.map(esc).join(', ') + '</strong></div>';
    }
    if (cmp.removed_dimensions.length) {
      only += '<div class="drift-only">Only in A (' + esc(cmp.a.name) + '): <strong>' +
        cmp.removed_dimensions.map(esc).join(', ') + '</strong></div>';
    }

    resultsEl.innerHTML = summary + flags + cards + only;
    resultsEl.hidden = false;
    if (scroll) {
      resultsEl.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
    }

    announcer.textContent = 'Comparison complete. Overall score change ' +
      (measured ? signed(d, 0) + ' points' : 'not available') + '. ' + cmp.flags.length +
      ' drift flag' + (cmp.flags.length === 1 ? '' : 's') + '.';
  }

  function scoreCell(side) {
    return '<div class="drift-score"><span class="n">' +
      (side.overall_score === null ? 'N/A' : side.overall_score) + '</span>' +
      '<span class="l">' + esc(side.name) + '</span></div>';
  }

  function driftCard(cd) {
    var head = '<div class="drift-card-head"><div>' +
      '<span class="dim-name">' + esc(cd.name) + '</span>' +
      '<span class="dim-kind">' + esc(cd.kind) + '</span>' +
      '<span class="drift-badge ' + cd.drift_level + '">' + cd.drift_level + ' drift</span>' +
      '</div><span class="drift-metrics">PSI ' + cd.psi.toFixed(3) +
      ' · TVD ' + cd.tvd.toFixed(3) +
      ' · score ' + cd.dimension_score_a + '→' + cd.dimension_score_b +
      ' (' + signed(cd.dimension_score_delta, 0) + ')</span></div>';

    // Scale bars to the largest share on either side, so shifts read visually.
    var maxShare = 0;
    cd.groups.forEach(function (g) {
      maxShare = Math.max(maxShare, g.share_a, g.share_b);
    });
    if (maxShare <= 0) maxShare = 1;

    var rows = cd.groups.slice(0, DISPLAY_GROUPS).map(function (g) {
      var cls = g.status === 'disappeared' ? ' gone' : g.status === 'appeared' ? ' new' : '';
      var wa = (g.share_a / maxShare) * 100;
      var wb = (g.share_b / maxShare) * 100;
      var deltaPP = g.share_delta * 100;
      var dCls = deltaPP > 0 ? 'up' : deltaPP < 0 ? 'down' : '';
      return '<div class="drift-row' + cls + '">' +
        '<span class="drift-row-label" title="' + esc(g.label) + '">' + esc(g.label) + '</span>' +
        '<span class="drift-bars" role="img" aria-label="' + pct(g.share_a) + ' to ' + pct(g.share_b) + '">' +
          '<span class="a" style="width:' + wa.toFixed(1) + '%"></span>' +
          '<span class="b" style="width:' + wb.toFixed(1) + '%"></span>' +
        '</span>' +
        '<span class="drift-row-delta">' + pct(g.share_a) + ' → ' + pct(g.share_b) +
          ' <span class="' + dCls + '">(' + signed(deltaPP) + 'pp)</span></span>' +
        '</div>';
    }).join('');

    var more = cd.groups.length > DISPLAY_GROUPS
      ? '<div class="dim-more">… and ' + (cd.groups.length - DISPLAY_GROUPS) + ' more groups</div>'
      : '';

    return '<div class="drift-card">' + head + rows + more + '</div>';
  }

  // ── Report export: "Download report (HTML)" / "Copy as JSON" ────────────
  // Ports faircode/report.py's compare_to_html so the browser report matches
  // the CLI's `faircode compare --html` output (same palette, same layout,
  // same field names as the DOM render above).
  function buildCompareHtmlReport(cmp) {
    var a = cmp.a, b = cmp.b;
    var scoreDelta = cmp.score_delta;
    var measured = scoreDelta !== null;
    var deltaClass = measured && scoreDelta > 0 ? 'up' : (measured && scoreDelta < 0 ? 'down' : 'flat');
    var arrow = scoreDelta === 0 ? '=' : '→';

    function reportScore(side) {
      if (side.overall_score === null) {
        return '<span class="n">N/A</span><span class="l">' + esc(side.name) +
          ' (' + side.n_rows.toLocaleString() + ' rows, not measured)</span>';
      }
      return '<span class="n">' + side.overall_score + '</span><span class="l">' +
        esc(side.name) + ' (' + side.n_rows.toLocaleString() + ' rows, Grade ' +
        side.grade + ')</span>';
    }

    var summaryHtml =
      '<div class="drift-summary">' +
      '<div class="drift-score">' + reportScore(a) + '</div>' +
      '<div class="drift-arrow" aria-hidden="true">' + arrow + '</div>' +
      '<div class="drift-score">' + reportScore(b) + '</div>' +
      '<div class="drift-delta ' + deltaClass + '">' +
        (measured ? 'score ' + signed(scoreDelta, 0) + ' pts' : 'score change not available') + '</div>' +
      '</div>';

    var cardsHtml;
    if (!cmp.dimensions.length) {
      cardsHtml = '<p class="section-note">No demographic dimension is present in both datasets to compare.</p>';
    } else {
      cardsHtml = cmp.dimensions.map(function (cd) {
        var maxShare = 0;
        cd.groups.forEach(function (g) { maxShare = Math.max(maxShare, g.share_a, g.share_b); });
        if (maxShare <= 0) maxShare = 1;

        var rows = cd.groups.slice(0, DISPLAY_GROUPS).map(function (g) {
          var cls = g.status === 'disappeared' ? ' gone' : (g.status === 'appeared' ? ' new' : '');
          var wa = (g.share_a / maxShare) * 100;
          var wb = (g.share_b / maxShare) * 100;
          var deltaPP = g.share_delta * 100;
          var dCls = deltaPP > 0 ? 'up' : (deltaPP < 0 ? 'down' : '');
          var tag = (g.status === 'appeared' || g.status === 'disappeared')
            ? ' <span class="tag">' + esc(g.status) + '</span>' : '';

          return '<tr class="drift-row' + cls + '">' +
            '<td class="label">' + esc(g.label) + tag + '</td>' +
            '<td class="num">' + (g.share_a * 100).toFixed(1) + '% → ' + (g.share_b * 100).toFixed(1) + '%</td>' +
            '<td class="num"><span class="' + dCls + '">' + signed(deltaPP) + ' pp</span></td>' +
            '<td class="bar"><div class="bar-container">' +
              '<span class="bar-a" style="width:' + wa.toFixed(1) + '%"></span>' +
              '<span class="bar-b" style="width:' + wb.toFixed(1) + '%"></span>' +
            '</div></td></tr>';
        }).join('');

        var moreHtml = cd.groups.length > DISPLAY_GROUPS
          ? '<div class="dim-more">… and ' + (cd.groups.length - DISPLAY_GROUPS) + ' more groups</div>' : '';

        return '<section class="drift-card"><div class="drift-card-head">' +
          '<h2>' + esc(cd.name) + ' <span class="kind">' + esc(cd.kind) + '</span> ' +
          '<span class="drift-badge ' + cd.drift_level + '">' + esc(cd.drift_level) + ' drift</span></h2>' +
          '<div class="drift-metrics">PSI ' + cd.psi.toFixed(3) + ' · TVD ' + cd.tvd.toFixed(3) +
          ' · score ' + cd.dimension_score_a + '→' + cd.dimension_score_b +
          ' (' + signed(cd.dimension_score_delta, 0) + ')</div></div>' +
          '<table>' + rows + '</table>' + moreHtml + '</section>';
      }).join('');
    }

    var flagsHtml = '';
    if (cmp.flags.length) {
      var items = cmp.flags.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('');
      flagsHtml = '<section class="flags"><h2>Drift Flags</h2><ul>' + items + '</ul></section>';
    }

    var onlyHtml = '';
    if (cmp.added_dimensions.length) {
      onlyHtml += '<div class="drift-only">Only in B (' + esc(b.name) + '): <strong>' +
        cmp.added_dimensions.map(esc).join(', ') + '</strong></div>';
    }
    if (cmp.removed_dimensions.length) {
      onlyHtml += '<div class="drift-only">Only in A (' + esc(a.name) + '): <strong>' +
        cmp.removed_dimensions.map(esc).join(', ') + '</strong></div>';
    }

    var style =
      ':root { --bg:#f4f1e8; --surface:#ebe7d9; --border:#d9d3c0; --accent:#a63a22; ' +
      '--accent3:#2f6b4f; --warn:#b8860b; --text:#36321f; --muted:#7d7459; --bar-a:#7d7459; --bar-b:#2f6b4f; } ' +
      'body { font-family:\'Helvetica Neue\',sans-serif; background:var(--bg); color:var(--text); ' +
      'max-width:820px; margin:0 auto; padding:48px 24px; } ' +
      'h1 { font-family:Georgia,serif; margin-bottom:8px; } ' +
      '.head { border-bottom:2px solid var(--accent); padding-bottom:12px; margin-bottom:20px; } ' +
      '.drift-summary { display:flex; align-items:center; justify-content:space-between; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:20px; } ' +
      '.drift-score { font-weight:bold; font-size:14px; display:flex; flex-direction:column; } ' +
      '.drift-score .n { font-size:24px; color:var(--accent3); } ' +
      '.drift-score .l { font-size:12px; color:var(--muted); font-weight:normal; } ' +
      '.drift-arrow { font-size:20px; color:var(--muted); } ' +
      '.drift-delta { font-weight:bold; padding:4px 8px; border-radius:4px; font-size:14px; } ' +
      '.drift-delta.down { color:var(--accent); background:#fbeae3; } ' +
      '.drift-delta.up { color:var(--accent3); background:#e2f0e8; } ' +
      '.drift-delta.flat { color:var(--muted); } ' +
      '.kind { color:var(--muted); font-size:.6em; text-transform:uppercase; letter-spacing:.08em; font-weight:normal; } ' +
      '.drift-badge { font-size:11px; padding:2px 6px; border-radius:4px; text-transform:uppercase; font-weight:bold; background:var(--border); margin-left:8px; } ' +
      '.drift-badge.none { background:var(--accent3); color:#fff; } ' +
      '.drift-badge.moderate { background:var(--warn); color:#fff; } ' +
      '.drift-badge.significant { background:var(--accent); color:#fff; } ' +
      '.drift-card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px 20px; margin:16px 0; } ' +
      '.drift-card-head { display:flex; justify-content:space-between; align-items:baseline; border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:12px; } ' +
      '.drift-card-head h2 { margin:0; font-size:18px; } ' +
      '.drift-metrics { font-size:12px; color:var(--muted); } ' +
      'table { width:100%; border-collapse:collapse; } ' +
      'td { padding:6px 8px; font-size:14px; border-bottom:1px solid var(--border); } ' +
      'td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; font-size:13px; } ' +
      'td.label { width:25%; } ' +
      'td.bar { width:40%; } ' +
      '.bar-container { display:flex; flex-direction:column; gap:3px; } ' +
      '.bar-a { display:block; height:6px; background:var(--bar-a); border-radius:2px; opacity:0.6; } ' +
      '.bar-b { display:block; height:6px; background:var(--bar-b); border-radius:2px; } ' +
      'tr.gone td.label { color:var(--accent); text-decoration:line-through; } ' +
      'tr.new td.label { color:var(--accent3); font-weight:bold; } ' +
      '.tag { font-size:10px; font-weight:bold; text-transform:uppercase; padding:1px 4px; border-radius:3px; border:1px solid currentColor; margin-left:4px; } ' +
      '.up { color:var(--accent3); } ' +
      '.down { color:var(--accent); } ' +
      '.dim-more { font-size:12px; color:var(--muted); margin-top:8px; font-style:italic; } ' +
      '.flags ul { list-style:none; padding:0; } ' +
      '.flags li { background:#fbeae3; border-left:3px solid var(--accent); padding:8px 12px; margin:6px 0; border-radius:0 4px 4px 0; font-size:14px; } ' +
      '.drift-only { font-size:13px; color:var(--muted); margin-top:8px; } ' +
      '.print-btn { position:fixed; top:16px; right:16px; background:var(--accent); color:#fff; border:0; border-radius:6px; padding:8px 14px; font-size:13px; cursor:pointer; font-family:inherit; } ' +
      '@media print { .print-btn { display:none; } body { padding:24px; max-width:none; } }';

    return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
      '<title>Fair Code - Representation Drift</title><style>' + style + '</style></head><body>' +
      '<button class="print-btn" onclick="window.print()">🖨 Print / Save as PDF</button>' +
      '<div class="head"><h1>Representation Drift (A → B)</h1></div>' +
      summaryHtml + cardsHtml + flagsHtml + onlyHtml +
      '<p style="color:var(--muted);font-size:12px;margin-top:32px">' +
      'Generated by <a href="https://github.com/yakew7/Fair-Code">Fair Code</a> - diagnostic only.</p>' +
      '</body></html>';
  }

  function compareReportBaseName() {
    var an = ((slot.A && slot.A.name) || 'A').replace(/\.(csv|tsv|json|xlsx)$/i, '');
    var bn = ((slot.B && slot.B.name) || 'B').replace(/\.(csv|tsv|json|xlsx)$/i, '');
    return an + '-vs-' + bn + '-drift-report';
  }

  function downloadCompareHtmlReport() {
    if (!currentCmp) return;
    var blob = new Blob([buildCompareHtmlReport(currentCmp)], { type: 'text/html' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = compareReportBaseName() + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

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

  async function copyCompareResultAsJSON() {
    if (!currentCmp) return;

    var hashA = await fileDigest(slot.A && slot.A.file);
    var hashB = await fileDigest(slot.B && slot.B.file);

    var provenance = {
      faircode_version: FAIRCODE_VERSION,
      engine: 'js',
      dataset_hash_a: hashA.digest,
      dataset_hash_b: hashB.digest,
      params: Object.assign({}, currentOpts),
      overrides: Object.assign({}, currentOverrides)
    };
    if (hashA.note !== null) provenance.dataset_hash_a_note = hashA.note;
    if (hashB.note !== null) provenance.dataset_hash_b_note = hashB.note;

    var exported = Object.assign({}, currentCmp, { provenance: provenance });
    var text = JSON.stringify(exported, null, 2);

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        flashButton(copyJsonBtn, '✓ Copied');
      }, function () {
        flashButton(copyJsonBtn, fallbackCopy(text) ? '✓ Copied' : 'Copy failed');
      });
    } else {
      flashButton(copyJsonBtn, fallbackCopy(text) ? '✓ Copied' : 'Copy failed');
    }
  }

  // ── Sample drift data ───────────────────────────────────────────────────
  // Baseline A is broadly balanced; current B drifts male-skewed, older, more
  // Caucasian, with one region collapsing and 'Asian' disappearing entirely -
  // so PSI clearly fires on race, age, sex, and region.
  function buildSample(key) {
    var header = ['patient_id', 'age', 'sex', 'race', 'region'];
    var rows = [header];
    var racesA = ['Caucasian', 'AfricanAmerican', 'Hispanic', 'Asian'];
    var racesB = ['Caucasian', 'Caucasian', 'Caucasian', 'AfricanAmerican', 'Hispanic'];
    var regionsA = ['Northeast', 'Midwest', 'South', 'West'];
    var regionsB = ['Northeast', 'Northeast', 'Midwest', 'South'];
    var agesA = [24, 29, 34, 41, 52, 63];
    var agesB = [38, 45, 52, 58, 64, 71];
    for (var i = 0; i < 300; i++) {
      var isB = key === 'B';
      var age = (isB ? agesB : agesA)[i % 6];
      var sex = isB ? (i % 10 < 7 ? 'male' : 'female') : (i % 2 === 0 ? 'male' : 'female');
      var race = (isB ? racesB : racesA)[i % (isB ? racesB.length : racesA.length)];
      var region = (isB ? regionsB : regionsA)[i % (isB ? regionsB.length : regionsA.length)];
      rows.push([String(1000 + i), String(age), sex, race, region]);
    }
    return rows.map(function (r) { return r.join(','); }).join('\n');
  }

  // ── Init ────────────────────────────────────────────────────────────────
  wireSlot('A', dropA, fileA, nameAEl);
  wireSlot('B', dropB, fileB, nameBEl);
  sampleBtn.addEventListener('click', function () {
    setSlot('A', E.parseCSV(buildSample('A')), 'sample-baseline.csv', dropA, nameAEl);
    setSlot('B', E.parseCSV(buildSample('B')), 'sample-current.csv', dropB, nameBEl);
  });
  downloadHtmlBtn.addEventListener('click', downloadCompareHtmlReport);
  copyJsonBtn.addEventListener('click', copyCompareResultAsJSON);
})();
