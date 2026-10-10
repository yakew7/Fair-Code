/* ════════════════════════════════════════════════════════════════════════
   Fair Code - Benchmark Results Dashboard

   Interactive, filterable explorer for results/results_fairness.csv and
   results/results_performance.csv (issue #744, ROADMAP.md Phase 5) -
   mirrors the Open Dataset Profiler's web/CLI split: same numbers the
   benchmark harness writes to results/, no server, nothing uploaded.
   Depends on assets/profiler-engine.js for CSV parsing only (parseCSV);
   none of the demographic-profiling logic in that file is used here.
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var E = window.FairCodeProfiler;

  var FAIRNESS_COLUMNS = ['audit', 'strategy', 'model', 'protected_attribute', 'metric',
    'value', 'ci_low', 'ci_high', 'p_value', 'significant',
    'n_disadvantaged', 'n_advantaged', 'small_sample_warning', 'note'];
  var PERFORMANCE_COLUMNS = ['audit', 'strategy', 'model', 'metric', 'value', 'ci_low', 'ci_high', 'n'];
  // results/summary.csv: the harness's cross-model roll-up (issue #794).
  var SUMMARY_COLUMNS = ['audit', 'strategy', 'protected_attribute', 'metric', 'mean_value',
    'n_models_significant', 'n_models'];
  function columnsFor(kind) {
    return kind === 'fairness' ? FAIRNESS_COLUMNS : kind === 'summary' ? SUMMARY_COLUMNS : PERFORMANCE_COLUMNS;
  }

  var FILTER_FIELDS = {
    fairness: ['audit', 'strategy', 'model', 'protected_attribute', 'metric'],
    performance: ['audit', 'strategy', 'model', 'metric'],
    summary: ['audit', 'strategy', 'protected_attribute', 'metric']
  };

  var state = {
    fairness: null,   // { rows: [...] } once loaded
    performance: null,
    summary: null,
    tab: 'fairness',
    filters: { fairness: {}, performance: {}, summary: {} },
    // Per tab, like filters and sort (#864): 'significant' means a single result on
    // fairness but every model on the summary tab, so the choice must not carry over.
    significantOnly: { fairness: false, summary: false },
    sort: { fairness: null, performance: null, summary: null }, // { field, dir }
    bundled: { fairness: false, performance: false, summary: false } // loaded from results/ (figures exist)
  };

  var pending = { filters: {}, sort: {} }; // from the URL, applied when that tab's data loads
  var exportBtn = document.getElementById('benchExportBtn');
  var clearBtn = document.getElementById('benchClearBtn');
  var legendEl = document.getElementById('benchLegend');
  var chartButtons = document.getElementById('benchChartButtons');
  var chartSvgBtn = document.getElementById('benchChartSvgBtn');
  var chartPngBtn = document.getElementById('benchChartPngBtn');
  var chartThemeSelect = document.getElementById('benchChartThemeSelect');
  var figureBlock = document.getElementById('benchFigureBlock');
  var figureImg = document.getElementById('benchFigureImg');
  var tabButtons = Array.prototype.slice.call(document.querySelectorAll('.bench-tab'));
  var loadBundledBtn = document.getElementById('loadBundledBtn');
  var dropzone = document.getElementById('benchDropzone');
  var fileInput = document.getElementById('benchFileInput');
  var errorEl = document.getElementById('benchError');
  var statusEl = document.getElementById('benchStatus');
  var resultsEl = document.getElementById('benchResults');
  var filterBar = document.getElementById('benchFilters');
  var significantOnlyInput = document.getElementById('significantOnlyInput');
  var significantOnlyText = document.getElementById('significantOnlyText');
  var resetFiltersBtn = document.getElementById('benchResetBtn');
  var summaryEl = document.getElementById('benchSummary');
  var tableHost = document.getElementById('benchTable');
  var chartHost = document.getElementById('benchChart');
  var chartNote = document.getElementById('benchChartNote');

  function isMissing(v) { return v === null || v === undefined || v === ''; }
  function toNum(v) { return isMissing(v) ? null : parseFloat(v); }
  function toBool(v) { return v === 'True'; }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = !msg;
  }

  // ── Loading ───────────────────────────────────────────────────────────
  // results_fairness.csv has protected_attribute + value + p_value;
  // results_performance.csv has audit + metric + value but no protected_attribute.
  // summary.csv (protected_attribute + mean_value + n_models) is the cross-model
  // roll-up and gets its own tab (#794) - never mis-loaded as fairness rows
  // with blank values (#775).
  function detectKind(columns) {
    var has = function (c) { return columns.indexOf(c) !== -1; };
    if (has('protected_attribute') && has('mean_value') && has('n_models')) return 'summary';
    if (has('protected_attribute') && has('value') && has('p_value')) return 'fairness';
    if (has('audit') && has('metric') && has('value') && !has('protected_attribute')) return 'performance';
    return null;
  }

  function ingest(kind, table) {
    var rows = table.rows.map(function (r) {
      var row = {};
      columnsFor(kind).forEach(function (col) {
        row[col] = r[col] === undefined ? null : r[col];
      });
      if (kind === 'summary') {
        row.mean_value = toNum(row.mean_value);
        row.n_models_significant = toNum(row.n_models_significant);
        row.n_models = toNum(row.n_models);
        // `value` aliases mean_value so the chart and shared helpers need no special case;
        // "significant" for styling = every model agreed the gap is significant.
        row.value = row.mean_value;
        row.significant = row.n_models > 0 && row.n_models_significant === row.n_models;
        return row;
      }
      row.value = toNum(row.value);
      row.ci_low = toNum(row.ci_low);
      row.ci_high = toNum(row.ci_high);
      if (kind === 'fairness') {
        row.p_value = toNum(row.p_value);
        row.significant = toBool(row.significant);
        row.n_disadvantaged = toNum(row.n_disadvantaged);
        row.n_advantaged = toNum(row.n_advantaged);
        row.small_sample_warning = toBool(row.small_sample_warning);
      } else {
        row.n = toNum(row.n);
      }
      return row;
    });
    var carried = {};
    if (!pending.filters[kind] && state[kind]) {
      // Reloading keeps the filters that still match something in the new rows.
      Object.keys(state.filters[kind] || {}).forEach(function (f) {
        var v = state.filters[kind][f];
        if (v && rows.some(function (r) { return r[f] === v; })) carried[f] = v;
      });
    }
    state[kind] = { rows: rows };
    state.filters[kind] = pending.filters[kind] || carried;
    state.sort[kind] = pending.sort[kind] || null;
    pending.filters[kind] = null;
    pending.sort[kind] = null;
  }

  function loadText(kind, text, sourceName, bundled) {
    var table = E.parseCSV(text);
    var detected = detectKind(table.columns);
    if (detected && detected !== kind) kind = detected;
    ingest(kind, table);
    state.bundled[kind] = !!bundled;
    statusEl.textContent = (statusEl.textContent ? statusEl.textContent + ' · ' : '') +
      sourceName + ' (' + table.rows.length + ' rows, ' + kind + ')';
  }

  function loadBundled() {
    showError('');
    statusEl.textContent = 'Loading results/results_fairness.csv, results_performance.csv and summary.csv…';
    var targets = [
      { kind: 'fairness', path: 'results/results_fairness.csv' },
      { kind: 'performance', path: 'results/results_performance.csv' },
      { kind: 'summary', path: 'results/summary.csv' }
    ];
    Promise.allSettled(targets.map(function (t) {
      return fetch(t.path).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      });
    })).then(function (settled) {
      statusEl.textContent = '';
      var succeeded = 0;
      var failed = [];
      settled.forEach(function (res, i) {
        var t = targets[i];
        if (res.status === 'fulfilled') {
          loadText(t.kind, res.value, t.path, true);
          succeeded++;
        } else {
          failed.push(t.path + ' (' + ((res.reason && res.reason.message) || 'failed') + ')');
        }
      });
      if (succeeded > 0) {
        if (failed.length) {
          statusEl.textContent = (statusEl.textContent ? statusEl.textContent + ' · ' : '') +
            'Could not load: ' + failed.join(', ');
        }
        render();
      } else {
        showError('Could not fetch the bundled results/ CSVs (' +
          (failed.join(', ') || 'failed') + '). ' +
          'This works once the site is served over HTTP - locally over file:// the browser ' +
          'blocks it. Drop results_fairness.csv / results_performance.csv / summary.csv below instead.');
      }
    });
  }

  function readDroppedFile(file) {
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var table = E.parseCSV(String(reader.result));
        var kind = detectKind(table.columns);
        if (!kind) {
          showError(file.name + ' does not look like a results_fairness.csv or ' +
            'results_performance.csv / summary.csv export (expected value/p_value, or mean_value/n_models, columns).');
          return;
        }
        showError('');
        ingest(kind, table);
        state.bundled[kind] = false;
        statusEl.textContent = file.name + ' (' + table.rows.length + ' rows, ' + kind + ')';
        render();
      } catch (err) {
        showError('Could not parse ' + file.name + ': ' + err.message);
      }
    };
    reader.onerror = function () { showError('Could not read ' + file.name + '.'); };
    reader.readAsText(file);
  }

  loadBundledBtn.addEventListener('click', loadBundled);
  dropzone.addEventListener('click', function () { fileInput.click(); });
  dropzone.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener('change', function () {
    Array.prototype.forEach.call(fileInput.files, readDroppedFile);
    fileInput.value = '';
  });
  ['dragenter', 'dragover'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add('dragover'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      if (ev === 'dragleave' && dropzone.contains(e.relatedTarget)) return;
      dropzone.classList.remove('dragover');
    });
  });
  dropzone.addEventListener('drop', function (e) {
    var files = e.dataTransfer && e.dataTransfer.files;
    if (files) Array.prototype.forEach.call(files, readDroppedFile);
  });

  // ── Clear loaded data (#784) ──────────────────────────────────────────
  clearBtn.addEventListener('click', function () {
    var kind = state.tab;
    state[kind] = null;
    state.filters[kind] = {};
    state.sort[kind] = null;
    statusEl.textContent = 'Cleared ' + kind + ' results.';
    render();
  });

  // ── Tabs ──────────────────────────────────────────────────────────────
  tabButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      state.tab = btn.dataset.tab;
      tabButtons.forEach(function (b) { b.setAttribute('aria-selected', String(b === btn)); });
      render();
    });
  });

  significantOnlyInput.addEventListener('change', function () {
    if (hasSignificance(state.tab)) state.significantOnly[state.tab] = significantOnlyInput.checked;
    render();
  });

  resetFiltersBtn.addEventListener('click', function () {
    var kind = state.tab;
    state.filters[kind] = {};
    if (hasSignificance(kind)) state.significantOnly[kind] = false;
    significantOnlyInput.checked = false;
    state.sort[kind] = null;
    render();
  });

  // ── Filtering + sorting ───────────────────────────────────────────────
  function uniqueValues(rows, field) {
    var seen = Object.create(null), out = [];
    rows.forEach(function (r) {
      var v = r[field];
      if (v !== null && !seen[v]) { seen[v] = 1; out.push(v); }
    });
    out.sort();
    return out;
  }

  // The significance toggle applies to the fairness tab (per result row) and the
  // roll-up summary tab (a row counts when every model was significant, #819).
  function hasSignificance(kind) { return kind === 'fairness' || kind === 'summary'; }

  function filteredRows(kind) {
    var data = state[kind];
    if (!data) return [];
    var filters = state.filters[kind];
    return data.rows.filter(function (r) {
      if (hasSignificance(kind) && state.significantOnly[kind] && !r.significant) return false;
      return FILTER_FIELDS[kind].every(function (f) {
        return !filters[f] || r[f] === filters[f];
      });
    });
  }

  function sortedRows(kind, rows) {
    var sort = state.sort[kind];
    if (!sort) return rows;
    var out = rows.slice();
    out.sort(function (a, b) {
      var x = a[sort.field], y = b[sort.field];
      if (x === null && y === null) return 0;
      if (x === null) return 1;
      if (y === null) return -1;
      if (x < y) return sort.dir === 'asc' ? -1 : 1;
      if (x > y) return sort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return out;
  }

  // ── Rendering: filter bar ─────────────────────────────────────────────
  function renderFilters(kind) {
    filterBar.innerHTML = '';
    var data = state[kind];
    if (!data) return;
    FILTER_FIELDS[kind].forEach(function (field) {
      var label = document.createElement('label');
      label.className = 'bench-filter';
      var caption = document.createElement('span');
      caption.textContent = field.replace(/_/g, ' ');
      var select = document.createElement('select');
      select.dataset.field = field;
      var allOpt = document.createElement('option');
      allOpt.value = ''; allOpt.textContent = 'All';
      select.appendChild(allOpt);
      uniqueValues(data.rows, field).forEach(function (v) {
        var opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        if (state.filters[kind][field] === v) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener('change', function () {
        state.filters[kind][field] = select.value || null;
        render();
      });
      label.appendChild(caption);
      label.appendChild(select);
      filterBar.appendChild(label);
    });
    resetFiltersBtn.disabled = !FILTER_FIELDS[kind].some(function (field) {
      return Boolean(state.filters[kind][field]);
    }) && !(hasSignificance(kind) && state.significantOnly[kind]) && !state.sort[kind];
  }

  // ── Rendering: table ──────────────────────────────────────────────────
  function ciText(r) {
    return (r.ci_low !== null && r.ci_high !== null)
      ? r.ci_low.toFixed(4) + ' - ' + r.ci_high.toFixed(4) : '';
  }

  function headerCell(kind, field, label) {
    var sort = state.sort[kind];
    var active = sort && sort.field === field;
    var arrow = active ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '';
    var ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
    return '<th aria-sort="' + ariaSort + '"><button type="button" class="bench-sort-btn" data-field="' + field + '">' +
      esc(label) + arrow + '</button></th>';
  }

  function renderTable(kind, rows) {
    if (!rows.length) {
      tableHost.innerHTML = '<p class="section-note">No rows match the current filters.</p>';
      return;
    }
    var isFairness = kind === 'fairness';
    if (kind === 'summary') {
      var shead = headerCell(kind, 'audit', 'Audit') + headerCell(kind, 'strategy', 'Strategy') +
        headerCell(kind, 'protected_attribute', 'Attribute') + headerCell(kind, 'metric', 'Metric') +
        headerCell(kind, 'mean_value', 'Mean value') +
        headerCell(kind, 'n_models_significant', 'Models significant');
      var sbody = rows.map(function (r) {
        return '<tr><td>' + esc(r.audit) + '</td><td>' + esc(r.strategy) + '</td><td>' +
          esc(r.protected_attribute) + '</td><td>' + esc(r.metric) + '</td><td>' +
          (r.mean_value === null ? '' : r.mean_value.toFixed(4)) + '</td><td class="' +
          (r.significant ? 'bench-sig-yes' : 'bench-sig-no') + '">' +
          (r.n_models_significant === null ? '' : r.n_models_significant) + ' / ' +
          (r.n_models === null ? '' : r.n_models) + '</td></tr>';
      }).join('');
      tableHost.innerHTML = '<table class="bench-table"><thead><tr>' + shead + '</tr></thead>' +
        '<tbody>' + sbody + '</tbody></table>';
      wireSortButtons(kind);
      return;
    }
    var head = isFairness
      ? headerCell(kind, 'audit', 'Audit') + headerCell(kind, 'strategy', 'Strategy') +
        headerCell(kind, 'model', 'Model') + headerCell(kind, 'protected_attribute', 'Attribute') +
        headerCell(kind, 'metric', 'Metric') + headerCell(kind, 'value', 'Value') +
        '<th>95% CI</th>' + headerCell(kind, 'p_value', 'p-value') + headerCell(kind, 'significant', 'Sig.') +
        '<th>Note</th>'
      : headerCell(kind, 'audit', 'Audit') + headerCell(kind, 'strategy', 'Strategy') +
        headerCell(kind, 'model', 'Model') + headerCell(kind, 'metric', 'Metric') +
        headerCell(kind, 'value', 'Value') + '<th>95% CI</th>' + headerCell(kind, 'n', 'N');

    var body = rows.map(function (r) {
      var valueText = r.value === null ? '' : r.value.toFixed(4);
      if (isFairness) {
        var sigCls = r.significant ? 'bench-sig-yes' : 'bench-sig-no';
        var rowCls = r.small_sample_warning ? ' class="bench-row-warn"' : '';
        var badge = r.small_sample_warning
          ? ' <span class="bench-small-badge">⚠ small sample</span>' : '';
        return '<tr' + rowCls + '>' +
          '<td>' + esc(r.audit) + '</td><td>' + esc(r.strategy) + '</td><td>' + esc(r.model) + '</td>' +
          '<td>' + esc(r.protected_attribute) + '</td><td>' + esc(r.metric) + badge + '</td>' +
          '<td>' + valueText + '</td><td>' + ciText(r) + '</td>' +
          '<td>' + (r.p_value === null ? '' : r.p_value.toExponential(2)) + '</td>' +
          '<td class="' + sigCls + '">' + (r.significant ? 'yes' : 'no') + '</td>' +
          '<td class="bench-note">' + (r.note ? esc(r.note) : '') + '</td></tr>';
      }
      return '<tr>' +
        '<td>' + esc(r.audit) + '</td><td>' + esc(r.strategy) + '</td><td>' + esc(r.model) + '</td>' +
        '<td>' + esc(r.metric) + '</td><td>' + valueText + '</td><td>' + ciText(r) + '</td>' +
        '<td>' + (r.n === null ? '' : r.n) + '</td></tr>';
    }).join('');

    tableHost.innerHTML = '<table class="bench-table"><thead><tr>' + head + '</tr></thead>' +
      '<tbody>' + body + '</tbody></table>';
    wireSortButtons(kind);
  }

  function wireSortButtons(kind) {
    Array.prototype.forEach.call(tableHost.querySelectorAll('.bench-sort-btn'), function (btn) {
      btn.addEventListener('click', function () {
        var field = btn.dataset.field;
        var current = state.sort[kind];
        var dir = (current && current.field === field && current.dir === 'asc') ? 'desc' : 'asc';
        state.sort[kind] = { field: field, dir: dir };
        render();
      });
    });
  }

  // ── Rendering: chart ──────────────────────────────────────────────────
  // Fairness/summary: needs a metric + protected attribute so every bar shares
  // a scale. Performance (issue #762): needs a metric (accuracy/AUC/F1 differ
  // in meaning), has no significance flag so all bars use the neutral style.
  function chartReady(kind) {
    var filters = state.filters[kind];
    return kind === 'performance' ? !!filters.metric : !!(filters.metric && filters.protected_attribute);
  }

  // One model for both the HTML bars and the downloadable SVG/PNG (#796), so
  // the saved image can never disagree with what is on screen.
  function chartModel(kind, rows) {
    var maxAbs = rows.reduce(function (m, r) {
      return r.value === null ? m : Math.max(m, Math.abs(r.value));
    }, 0) || 1;
    // Signed metrics (e.g. demographic_parity_diff) draw from a centre line so
    // direction is visible, not just magnitude (#776).
    var signed = rows.some(function (r) { return r.value !== null && r.value < 0; });
    var sorted = rows.slice().sort(function (a, b) { return Math.abs(b.value || 0) - Math.abs(a.value || 0); });
    return {
      signed: signed,
      bars: sorted.map(function (r) {
        var mag = r.value === null ? 0 : Math.abs(r.value) / maxAbs * (signed ? 50 : 100);
        var neg = r.value !== null && r.value < 0;
        return {
          label: [r.audit, r.strategy].concat(r.model ? [r.model] : []).join(' · '),
          value: r.value,
          cls: (kind !== 'performance' && r.significant) ? 'bad' : 'good',
          neg: neg,
          width: mag,
          offset: signed ? (neg ? 50 - mag : 50) : 0
        };
      })
    };
  }

  function renderChart(kind, rows) {
    if (!chartReady(kind)) {
      chartHost.innerHTML = '';
      chartNote.textContent = kind === 'performance'
        ? 'Pick a metric above to chart every audit x strategy x model combination.'
        : 'Pick a metric and a protected attribute above to chart every ' +
          'audit x strategy' + (kind === 'fairness' ? ' x model' : '') + ' combination on the same scale.';
      chartHost.hidden = true;
      chartButtons.hidden = true;
      return;
    }
    chartNote.textContent = '';
    chartHost.hidden = false;
    if (!rows.length) { chartHost.innerHTML = ''; chartButtons.hidden = true; return; }
    chartButtons.hidden = false;

    var model = chartModel(kind, rows);
    chartHost.innerHTML = model.bars.map(function (bar) {
      var style = 'width:' + bar.width.toFixed(1) + '%' + (bar.offset ? ';margin-left:' + bar.offset.toFixed(1) + '%' : '');
      return '<div class="bar-row">' +
        '<span class="bar-label" title="' + esc(bar.label) + '">' + esc(bar.label) + '</span>' +
        '<span class="bar-track' + (model.signed ? ' signed' : '') + '"><span class="bar-fill ' + bar.cls +
          (bar.neg ? ' neg' : '') + '" style="' + style + '"></span></span>' +
        '<span class="bar-pct">' + (bar.value === null ? 'n/a' : bar.value.toFixed(4)) + '</span>' +
        '</div>';
    }).join('');
  }

  // ── Chart as SVG / PNG (issue #796) ────────────────────────────────────
  function svgEsc(t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  // Colours for the exported chart (#813): the site's light and dark tokens
  // (benchmark.html :root / html[data-theme="dark"]), keyed by role.
  var CHART_PALETTES = {
    light: { bg: '#f4f1e8', text: '#36321f', muted: '#7d7459', track: '#e2dcc9',
             axis: '#bdb59c', bad: '#a63a22', good: '#2f6b4f' },
    dark: { bg: '#15130d', text: '#cfc7b0', muted: '#8d8367', track: '#242013',
            axis: '#443e2d', bad: '#cf6f49', good: '#79b294' }
  };

  // The palette the on-screen chart is using right now, read from the page's
  // resolved CSS variables; falls back to the light tokens where a variable (or
  // getComputedStyle itself) is unavailable.
  function pagePalette() {
    var palette = Object.assign({}, CHART_PALETTES.light);
    try {
      var cs = getComputedStyle(document.documentElement);
      var vars = { bg: '--bg', text: '--text', muted: '--muted', track: '--bias-track-bg',
                   axis: '--border2', bad: '--accent', good: '--accent3' };
      Object.keys(vars).forEach(function (role) {
        var v = cs.getPropertyValue(vars[role]).trim();
        if (v) palette[role] = v;
      });
    } catch (e) { /* no DOM styles (tests, sandboxed frames) */ }
    return palette;
  }

  // theme: 'page' (default - match what is on screen), 'light', 'dark', or
  // 'transparent' (light ink, no background rect, for dropping onto a slide).
  function chartPalette(theme) {
    if (theme === 'light' || theme === 'dark') return CHART_PALETTES[theme];
    if (theme === 'transparent') return Object.assign({}, CHART_PALETTES.light, { bg: null });
    return pagePalette();
  }

  function chartToSvg(model, title, theme) {
    var LABEL_W = 380, TRACK_W = 400, ROW_H = 24, TOP = 34, W = LABEL_W + TRACK_W + 130;
    var H = TOP + model.bars.length * ROW_H + 12;
    var c = chartPalette(theme);
    var out = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H +
      '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-labelledby="t"><title id="t">' + svgEsc(title) + '</title>' +
      (c.bg ? '<rect width="100%" height="100%" fill="' + svgEsc(c.bg) + '"/>' : '') +
      '<text x="12" y="22" font-family="monospace" font-size="13" fill="' + svgEsc(c.text) + '">' + svgEsc(title) + '</text>';
    if (model.signed) {
      out += '<line x1="' + (LABEL_W + TRACK_W / 2) + '" y1="' + (TOP - 4) + '" x2="' + (LABEL_W + TRACK_W / 2) +
        '" y2="' + (H - 8) + '" stroke="' + svgEsc(c.axis) + '"/>';
    }
    model.bars.forEach(function (bar, i) {
      var y = TOP + i * ROW_H;
      var label = bar.label.length > 54 ? bar.label.slice(0, 53) + '…' : bar.label;
      var x = LABEL_W + TRACK_W * bar.offset / 100, w = TRACK_W * bar.width / 100;
      out += '<text x="12" y="' + (y + 14) + '" font-family="monospace" font-size="11" fill="' + svgEsc(c.text) + '">' +
        svgEsc(label) + '</text>' +
        '<rect x="' + LABEL_W + '" y="' + (y + 3) + '" width="' + TRACK_W + '" height="14" rx="3" fill="' + svgEsc(c.track) + '"/>' +
        '<rect x="' + x.toFixed(1) + '" y="' + (y + 3) + '" width="' + w.toFixed(1) + '" height="14" rx="3" fill="' +
        svgEsc(bar.cls === 'bad' ? c.bad : c.good) + '"' + (bar.neg ? ' opacity="0.75"' : '') + '/>' +
        '<text x="' + (LABEL_W + TRACK_W + 10) + '" y="' + (y + 14) + '" font-family="monospace" font-size="11" fill="' + svgEsc(c.muted) + '">' +
        (bar.value === null ? 'n/a' : bar.value.toFixed(4)) + '</text>';
    });
    return out + '</svg>';
  }

  function chartTitle(kind) {
    var f = state.filters[kind], parts = [f.metric];
    if (kind !== 'performance') parts.push(f.protected_attribute);
    if (f.audit) parts.push(f.audit);
    return parts.filter(Boolean).join(' · ') + ' (' + kind + ')';
  }

  function saveBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function currentChartSvg() {
    var kind = state.tab;
    if (!state[kind] || !chartReady(kind)) return null;
    var rows = sortedRows(kind, filteredRows(kind));
    var theme = chartThemeSelect && chartThemeSelect.value ? chartThemeSelect.value : 'page';
    return rows.length ? chartToSvg(chartModel(kind, rows), chartTitle(kind), theme) : null;
  }

  chartSvgBtn.addEventListener('click', function () {
    var svg = currentChartSvg();
    if (svg) saveBlob(new Blob([svg], { type: 'image/svg+xml' }), 'benchmark-' + state.tab + '-chart.svg');
  });

  chartPngBtn.addEventListener('click', function () {
    var svg = currentChartSvg();
    if (!svg) return;
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement('canvas');
      canvas.width = img.width * 2; canvas.height = img.height * 2;
      var ctx = canvas.getContext('2d');
      ctx.scale(2, 2);
      ctx.drawImage(img, 0, 0);
      canvas.toBlob(function (blob) {
        if (blob) saveBlob(blob, 'benchmark-' + state.tab + '-chart.png');
      }, 'image/png');
    };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });

  // ── Committed figures (issue #795) ─────────────────────────────────────
  // results/figures/<audit>_strategies.png is rendered by faircode/figures.py;
  // shown when exactly one audit is selected on bundled data (a dropped user
  // export has no matching file).
  function renderFigure(kind) {
    var audit = state.filters[kind].audit;
    if (!audit || !state.bundled[kind] || kind === 'performance') {
      figureBlock.hidden = true;
      figureImg.removeAttribute('src');
      return;
    }
    figureImg.alt = 'Fairness gap by mitigation strategy for the ' + audit +
      ' audit, rendered by faircode/figures.py from results_fairness.csv';
    figureImg.src = 'results/figures/' + encodeURIComponent(audit) + '_strategies.png';
    figureBlock.hidden = false;
  }
  figureImg.addEventListener('error', function () { figureBlock.hidden = true; });

  // ── Export of the current (filtered + sorted) view (issue #761) ────────
  var csvField = E.csvField;

  function rowsToCsv(kind, rows) {
    var cols = columnsFor(kind);
    return [cols.join(',')].concat(rows.map(function (r) {
      return cols.map(function (c) { return csvField(r[c]); }).join(',');
    })).join('\r\n') + '\r\n';
  }

  function downloadFiltered() {
    var kind = state.tab;
    if (!state[kind]) return;
    var csv = rowsToCsv(kind, sortedRows(kind, filteredRows(kind)));
    var blob = new Blob([csv], { type: 'text/csv' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'results_' + kind + '_filtered.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  exportBtn.addEventListener('click', downloadFiltered);

  // ── URL deep-linking (issue #764) ──────────────────────────────────────
  // Only the active tab's view is encoded: ?tab=fairness&audit=compas&sig=1&sort=value:asc
  function writeUrlState() {
    try {
      var kind = state.tab, params = new URLSearchParams();
      params.set('tab', kind);
      FILTER_FIELDS[kind].forEach(function (f) {
        if (state.filters[kind][f]) params.set(f, state.filters[kind][f]);
      });
      if (hasSignificance(kind) && state.significantOnly[kind]) params.set('sig', '1');
      if (state.sort[kind]) params.set('sort', state.sort[kind].field + ':' + state.sort[kind].dir);
      history.replaceState(null, '', '?' + params.toString());
    } catch (e) { /* file:// or sandboxed frames: deep-linking is best-effort */ }
  }

  function readUrlState() {
    var params;
    try { params = new URLSearchParams(window.location.search); } catch (e) { return false; }
    var tab = params.get('tab');
    if (tab !== 'fairness' && tab !== 'performance' && tab !== 'summary') return false;
    state.tab = tab;
    var f = {};
    FILTER_FIELDS[tab].forEach(function (field) { if (params.get(field)) f[field] = params.get(field); });
    pending.filters[tab] = f;
    var sort = (params.get('sort') || '').split(':');
    if (sort.length === 2 && (sort[1] === 'asc' || sort[1] === 'desc')) {
      pending.sort[tab] = { field: sort[0], dir: sort[1] };
    }
    if (hasSignificance(tab) && params.get('sig') === '1') {
      state.significantOnly[tab] = true;
      significantOnlyInput.checked = true;
    }
    tabButtons.forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.tab === tab)); });
    return true;
  }

  // ── Orchestrator ────────────────────────────────────────────────────────
  function render() {
    var kind = state.tab;
    var data = state[kind];
    resultsEl.hidden = !(state.fairness || state.performance || state.summary);
    if (!data) {
      filterBar.innerHTML = '';
      significantOnlyInput.parentElement.hidden = true;
      resetFiltersBtn.hidden = true;
      summaryEl.textContent = '';
      tableHost.innerHTML = '<p class="section-note">Load ' + kind + ' results above to explore them.</p>';
      chartHost.innerHTML = ''; chartHost.hidden = true; chartNote.textContent = '';
      chartButtons.hidden = true;
      figureBlock.hidden = true;
      exportBtn.hidden = true;
      clearBtn.hidden = true;
      legendEl.hidden = true;
      return;
    }
    significantOnlyInput.parentElement.hidden = !hasSignificance(kind);
    significantOnlyInput.checked = hasSignificance(kind) && state.significantOnly[kind];
    if (significantOnlyText) {
      significantOnlyText.textContent = kind === 'summary'
        ? ' Significant in every model only (p < 0.05)'
        : ' Significant results only (p < 0.05)';
    }
    resetFiltersBtn.hidden = false;
    renderFilters(kind);
    var rows = sortedRows(kind, filteredRows(kind));
    var sigCount = hasSignificance(kind) ? rows.filter(function (r) { return r.significant; }).length : null;
    summaryEl.textContent = rows.length.toLocaleString() + ' of ' + data.rows.length.toLocaleString() + ' rows shown' +
      (sigCount !== null ? ' · ' + sigCount.toLocaleString() + ' significant' +
        (kind === 'summary' ? ' in every model' : '') : '');
    renderTable(kind, rows);
    renderChart(kind, rows);
    renderFigure(kind);
    exportBtn.hidden = false;
    clearBtn.hidden = false;
    legendEl.hidden = !(kind === 'fairness' && rows.some(function (r) { return r.small_sample_warning; }));
    writeUrlState();
  }

  var restored = readUrlState();
  render();
  if (restored) loadBundled();
})();
