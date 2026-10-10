"""Behavioral tests for the benchmark results dashboard (issue #744).

assets/benchmark-dashboard.js is DOM-coupled (no jsdom in this repo, matching
the rest of the web profiler's test story - see test_js_parity.py's #740
tests), so this drives the REAL file with a minimal hand-built DOM stub
rather than re-implementing its logic in the test. Every expected number is
computed from the real results/*.csv files via pandas rather than hardcoded,
so this stays correct as the benchmark harness's results/ evolves (no paper
freeze is in effect - see CLAUDE.md).
"""

import json
import subprocess
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

# A minimal DOM stub: enough getElementById/createElement/appendChild/
# addEventListener plumbing to actually execute assets/benchmark-dashboard.js
# end to end (fetch mocked to serve the real results/ CSVs), then drive a
# filter-select change, a "significant only" checkbox toggle, a sort-header
# click, a filter reset, and a tab switch - the same interactions a person
# would perform in a browser - and read back what actually got rendered.
_DOM_STUB = r"""
'use strict';
var fs = require('fs');
var path = require('path');
var REPO = process.argv[1];

function makeEl(id) {
  var el = {
    id: id,
    _listeners: {},
    dataset: {},
    style: { setProperty: function () {} },
    classList: { add: function () {}, remove: function () {}, contains: function () { return false; } },
    hidden: false,
    textContent: '',
    _innerHTML: '',
    parentElement: { hidden: false },
    addEventListener: function (type, fn) {
      (el._listeners[type] = el._listeners[type] || []).push(fn);
    },
    setAttribute: function (k, v) { el['attr_' + k] = v; },
    getAttribute: function (k) { return el['attr_' + k]; },
    removeAttribute: function (k) { delete el[k]; },
    appendChild: function (child) { (el._children = el._children || []).push(child); return child; },
    querySelectorAll: function (sel) {
      if (sel === '.bench-sort-btn') return el._sortButtons || [];
      return [];
    },
    click: function () { (el._listeners.click || []).forEach(function (f) { f(); }); },
  };
  Object.defineProperty(el, 'innerHTML', {
    get: function () { return el._innerHTML; },
    set: function (html) {
      el._innerHTML = html;
      el._sortButtons = [];
      var re = /class="bench-sort-btn" data-field="([^"]+)"/g, m;
      while ((m = re.exec(html))) {
        (function (field) {
          var btn = { dataset: { field: field }, _listeners: {},
            addEventListener: function (t, f) { (btn._listeners[t] = btn._listeners[t] || []).push(f); },
            click: function () { (btn._listeners.click || []).forEach(function (f) { f(); }); } };
          el._sortButtons.push(btn);
        })(m[1]);
      }
    },
  });
  return el;
}

var ids = ['loadBundledBtn', 'benchDropzone', 'benchFileInput', 'benchError', 'benchStatus',
  'benchResults', 'benchFilters', 'significantOnlyInput', 'benchSummary', 'benchTable',
  'benchChart', 'benchChartNote', 'benchChartBlock', 'benchExportBtn', 'benchResetBtn',
  'benchClearBtn', 'benchLegend', 'benchChartButtons', 'benchChartSvgBtn',
  'benchChartPngBtn', 'benchFigureBlock', 'benchFigureImg'];
var elements = {};
ids.forEach(function (id) { elements[id] = makeEl(id); });

var createdSelects = {};
global.document = {
  getElementById: function (id) {
    if (!elements[id]) elements[id] = makeEl(id);
    return elements[id];
  },
  querySelectorAll: function (sel) {
    if (sel === '.bench-tab') return global.__tabButtons;
    return [];
  },
  createElement: function (tag) {
    var node = makeEl('(created:' + tag + ')');
    node.tagName = tag;
    node.appendChild = function (child) {
      (node._children = node._children || []).push(child);
      if (tag === 'label' && child.tagName === 'select' && child.dataset.field) {
        createdSelects[child.dataset.field] = child;
      }
      return child;
    };
    if (tag === 'select') {
      node._options = [];
      node.appendChild = function (opt) { node._options.push(opt); return opt; };
      Object.defineProperty(node, 'value', {
        get: function () { return node._value || ''; },
        set: function (v) { node._value = v; },
      });
    }
    if (tag === 'canvas') {
      var ctx = {
        _calls: [],
        scale: function (sx, sy) { ctx._calls.push(['scale', sx, sy]); },
        drawImage: function (img, x, y) { ctx._calls.push(['drawImage', img, x, y]); },
      };
      node.getContext = function (kind) {
        node._contextKind = kind;
        return ctx;
      };
      node.toBlob = function (cb, mimeType) {
        node._toBlobMimeType = mimeType;
        var b = new global.Blob(['fake-png-bytes'], { type: mimeType });
        cb(b);
      };
      node._ctx = ctx;
      global.__lastCanvas = node;
    }
    if (tag === 'a') {
      node.click = function () {
        global.__lastDownloadName = node.download;
      };
    }
    return node;
  },
};

function makeTabButton(tab, selected) {
  var b = makeEl('tab-' + tab);
  b.dataset.tab = tab;
  b.setAttribute('aria-selected', String(selected));
  return b;
}
global.__tabButtons = [makeTabButton('fairness', true), makeTabButton('performance', false),
  makeTabButton('summary', false)];

var _origToLocaleString = Number.prototype.toLocaleString;
Number.prototype.toLocaleString = function (locales, options) {
  return _origToLocaleString.call(this, locales || 'en-US', options);
};

var fetchMap = {
  'results/results_fairness.csv': fs.readFileSync(path.join(REPO, 'results', 'results_fairness.csv'), 'utf-8'),
  'results/results_performance.csv': fs.readFileSync(path.join(REPO, 'results', 'results_performance.csv'), 'utf-8'),
  'results/summary.csv': fs.readFileSync(path.join(REPO, 'results', 'summary.csv'), 'utf-8'),
};
var blockUrl = process.argv[3] || '';
global.fetch = function (url) {
  if (blockUrl && url.indexOf(blockUrl) !== -1) {
    return Promise.resolve({
      ok: false,
      status: 404,
      text: function () { return Promise.reject(new Error('HTTP 404')); }
    });
  }
  return Promise.resolve({ ok: true, text: function () { return Promise.resolve(fetchMap[url]); } });
};
var lastBlob = null;
var lastBlobType = null;
global.Blob = function (parts, opts) {
  lastBlob = parts.join('');
  lastBlobType = (opts && opts.type) || null;
};
global.Image = function () {
  var self = {
    width: 0,
    height: 0,
    _src: '',
    onload: null,
  };
  Object.defineProperty(self, 'src', {
    get: function () { return self._src; },
    set: function (v) {
      self._src = v;
      try {
        var decoded = decodeURIComponent(v.split(',')[1] || '');
        var wm = decoded.match(/width="(\d+)"/);
        var hm = decoded.match(/height="(\d+)"/);
        if (wm) self.width = parseInt(wm[1], 10);
        if (hm) self.height = parseInt(hm[1], 10);
      } catch (e) {}
      if (typeof self.onload === 'function') {
        self.onload();
      }
    },
  });
  return self;
};
global.URL = { createObjectURL: function () { return 'blob:x'; }, revokeObjectURL: function () {} };
global.document.body = { appendChild: function () {}, removeChild: function () {} };
global.window = global;
global.window.location = { search: process.argv[2] || '' };
global.history = { replaceState: function (a, b, u) { global.__lastUrl = u; } };

require(path.join(REPO, 'assets', 'profiler-engine.js'));

var results = {};

(async function () {
  require(path.join(REPO, 'assets', 'benchmark-dashboard.js'));

  if (!process.argv[2]) elements.loadBundledBtn.click(); // a shared link must load by itself
  await new Promise(function (r) { setTimeout(r, 20); });

  results.last_url_after_first_render = global.__lastUrl;
  results.results_hidden_after_load = elements.benchResults.hidden;
  results.summary_unfiltered = elements.benchSummary.textContent;
  results.status_after_load = elements.benchStatus.textContent;
  results.error_after_load = elements.benchError.textContent;
  results.error_hidden_after_load = elements.benchError.hidden;

  if (process.argv[4] === 'sig-per-tab') {
    // #864: the toggle is per tab - fairness and summary never share it.
    function toggle(on) {
      elements.significantOnlyInput.checked = on;
      (elements.significantOnlyInput._listeners.change || []).forEach(function (f) { f(); });
    }
    toggle(true);                                   // fairness: on
    results.fairness_on = elements.benchSummary.textContent;
    global.__tabButtons[2].click();                 // -> summary
    results.summary_checked = !!elements.significantOnlyInput.checked;
    results.summary_text = elements.benchSummary.textContent;
    results.summary_url = global.__lastUrl;
    toggle(true);                                   // summary: on
    global.__tabButtons[0].click();                 // -> fairness again
    results.fairness_checked_again = !!elements.significantOnlyInput.checked;
    results.fairness_text_again = elements.benchSummary.textContent;
    toggle(false);                                  // fairness: off
    global.__tabButtons[2].click();
    results.summary_still_checked = !!elements.significantOnlyInput.checked;
    process.stdout.write(JSON.stringify(results));
    return;
  }

  if (process.argv[4] === 'chart-theme') {
    // #813: render the same chart under each export theme and read the SVG back.
    function pick(field, value) {
      var sel = createdSelects[field];
      sel.value = value;
      (sel._listeners.change || []).forEach(function (f) { f(); });
    }
    pick('metric', 'demographic_parity_diff');
    pick('protected_attribute', 'race');
    results.themes = {};
    ['page', 'light', 'dark', 'transparent'].forEach(function (theme) {
      elements.benchChartThemeSelect.value = theme;
      lastBlob = null;
      elements.benchChartSvgBtn.click();
      results.themes[theme] = lastBlob;
    });
    // a page whose resolved CSS variables are dark: 'page' must follow them
    global.getComputedStyle = function () {
      var vars = { '--bg': ' #15130d ', '--text': '#cfc7b0', '--muted': '#8d8367',
        '--bias-track-bg': '#242013', '--border2': '#443e2d', '--accent': '#cf6f49', '--accent3': '#79b294' };
      return { getPropertyValue: function (n) { return vars[n] || ''; } };
    };
    global.document.documentElement = {};
    elements.benchChartThemeSelect.value = 'page';
    lastBlob = null;
    elements.benchChartSvgBtn.click();
    results.themes.page_dark_vars = lastBlob;
    process.stdout.write(JSON.stringify(results));
    return;
  }

  if (process.argv[4] === 'load-only') {
    // Read back the significance toggle's state on whichever tab the URL opened (#819).
    results.sig_parent_hidden = elements.significantOnlyInput.parentElement.hidden;
    results.sig_checked = !!elements.significantOnlyInput.checked;
    results.sig_label = elements.significantOnlyText.textContent;
    elements.significantOnlyInput.checked = !elements.significantOnlyInput.checked;
    (elements.significantOnlyInput._listeners.change || []).forEach(function (f) { f(); });
    results.summary_after_toggle = elements.benchSummary.textContent;
    results.url_after_toggle = global.__lastUrl;
    process.stdout.write(JSON.stringify(results));
    return;
  }

  if (elements.benchResults.hidden) {
    process.stdout.write(JSON.stringify(results));
    return;
  }

  var auditSelect = createdSelects['audit'];
  results.audit_select_found = !!auditSelect;
  if (auditSelect) {
    auditSelect.value = 'compas';
    (auditSelect._listeners.change || []).forEach(function (f) { f(); });
  }
  results.summary_after_audit_filter = elements.benchSummary.textContent;
  var otherAudits = ['ai_fair_recruitment', 'benefits_denial', 'german_credit_lending',
    'healthcare_readmission', 'insurance_denial', 'tenant_screening'];
  results.table_has_only_compas = otherAudits.every(function (a) {
    return elements.benchTable.innerHTML.indexOf(a) === -1;
  });

  elements.significantOnlyInput.checked = true;
  (elements.significantOnlyInput._listeners.change || []).forEach(function (f) { f(); });
  results.summary_after_significant_only = elements.benchSummary.textContent;

  function firstRowValue() {
    var body = (elements.benchTable.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/) || [])[1] || '';
    var firstTr = (body.match(/<tr[^>]*>([\s\S]*?)<\/tr>/) || [])[1] || '';
    var tds = [];
    var re = /<td[^>]*>([^<]*)<\/td>/g, m;
    while ((m = re.exec(firstTr))) tds.push(m[1]);
    return tds[5] === undefined || tds[5] === '' ? null : parseFloat(tds[5]);
  }
  var valueBtn = elements.benchTable._sortButtons.filter(function (b) { return b.dataset.field === 'value'; })[0];
  results.value_sort_btn_found = !!valueBtn;
  if (valueBtn) valueBtn.click(); // ascending
  results.first_row_value_asc = firstRowValue();
  var valueBtn2 = elements.benchTable._sortButtons.filter(function (b) { return b.dataset.field === 'value'; })[0];
  if (valueBtn2) valueBtn2.click(); // descending
  results.first_row_value_desc = firstRowValue();
  results.aria_sort_value = /<th aria-sort="descending"><button[^>]*data-field="value"/.test(elements.benchTable.innerHTML);
  results.has_note_column = elements.benchTable.innerHTML.indexOf('<th>Note</th>') !== -1;
  results.small_badges = (elements.benchTable.innerHTML.match(/bench-small-badge/g) || []).length;
  results.legend_hidden = elements.benchLegend.hidden;

  results.export_btn_hidden = elements.benchExportBtn.hidden;
  elements.benchExportBtn.click();
  results.export_csv = lastBlob;

  // Signed-metric chart (#776): all-compas dpd/race has negative values.
  elements.benchResetBtn.click();
  [['metric', 'demographic_parity_diff'], ['protected_attribute', 'race']].forEach(function (kv) {
    var sel = createdSelects[kv[0]];
    sel.value = kv[1];
    (sel._listeners.change || []).forEach(function (f) { f(); });
  });
  results.svg_button_visible = elements.benchChartButtons.hidden === false;
  lastBlob = null;
  elements.benchChartSvgBtn.click();
  results.svg = lastBlob;

  // #812: PNG chart export rasterises the SVG via canvas
  global.__lastDownloadName = null;
  global.__lastCanvas = null;
  lastBlobType = null;
  elements.benchChartPngBtn.click();
  results.png_download_name = global.__lastDownloadName;
  results.png_blob_type = lastBlobType;
  results.canvas_context_kind = global.__lastCanvas ? global.__lastCanvas._contextKind : null;
  results.canvas_to_blob_type = global.__lastCanvas ? global.__lastCanvas._toBlobMimeType : null;
  results.canvas_width = global.__lastCanvas ? global.__lastCanvas.width : null;
  results.canvas_height = global.__lastCanvas ? global.__lastCanvas.height : null;
  results.canvas_calls = global.__lastCanvas && global.__lastCanvas._ctx ? global.__lastCanvas._ctx._calls : [];

  results.figure_hidden_without_audit = elements.benchFigureBlock.hidden;
  results.signed_chart = elements.benchChart.innerHTML.indexOf('bar-track signed') !== -1;
  results.neg_bars = (elements.benchChart.innerHTML.match(/bar-fill [a-z]+ neg/g) || []).length;

  results.reset_disabled_before_reset = elements.benchResetBtn.disabled;
  elements.benchResetBtn.click();
  results.summary_after_reset = elements.benchSummary.textContent;
  results.significant_only_after_reset = elements.significantOnlyInput.checked;
  results.sort_cleared_after_reset = elements.benchTable.innerHTML.indexOf('Value ▼') === -1;
  results.url_after_reset = global.__lastUrl;
  results.reset_disabled_after_reset = elements.benchResetBtn.disabled;

  var perfTab = global.__tabButtons[1];
  perfTab.click();
  results.performance_tab_summary = elements.benchSummary.textContent;
  results.perf_chart_note_before = elements.benchChartNote.textContent;
  var metricSelect = createdSelects['metric'];
  metricSelect.value = 'accuracy';
  (metricSelect._listeners.change || []).forEach(function (f) { f(); });
  results.perf_chart_bars = (elements.benchChart.innerHTML.match(/class="bar-row"/g) || []).length;
  results.perf_chart_hidden = elements.benchChart.hidden;
  results.perf_chart_unsigned = elements.benchChart.innerHTML.indexOf('bar-track signed') === -1;

  // Summary tab (#794) and committed figure (#795).
  var sumTab = global.__tabButtons[2];
  sumTab.click();
  results.summary_summary = elements.benchSummary.textContent;
  results.summary_header = (elements.benchTable.innerHTML.match(/<th[^>]*>/g) || []).length;
  results.summary_sig_cell = /\d+ \/ \d+<\/td>/.test(elements.benchTable.innerHTML);
  var auditSel = createdSelects['audit'];
  auditSel.value = 'compas';
  (auditSel._listeners.change || []).forEach(function (f) { f(); });
  results.figure_visible = elements.benchFigureBlock.hidden === false;
  results.figure_src = elements.benchFigureImg.src;
  var perfTab2 = global.__tabButtons[1];
  perfTab2.click();
  results.figure_hidden_on_performance = elements.benchFigureBlock.hidden;
  perfTab2.click();

  elements.benchClearBtn.click();
  results.after_clear_summary = elements.benchSummary.textContent;
  results.after_clear_status = elements.benchStatus.textContent;

  results.last_url = global.__lastUrl;
  process.stdout.write(JSON.stringify(results));
})();
"""


def _run_dom_stub(search="", block_url="", mode=""):
    completed = subprocess.run(
        ["node", "-e", _DOM_STUB, str(REPO_ROOT), search, block_url, mode],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(completed.stdout)


def test_benchmark_dashboard_loads_filters_sorts_and_switches_tabs():
    """Drives the real assets/benchmark-dashboard.js through the interactions
    a person would perform in a browser, against the real results/*.csv, and
    checks every number against pandas ground truth rather than a hardcoded
    snapshot (results/ has no paper freeze and is expected to keep moving)."""
    fairness = pd.read_csv(REPO_ROOT / "results" / "results_fairness.csv")
    performance = pd.read_csv(REPO_ROOT / "results" / "results_performance.csv")

    total = len(fairness)
    total_significant = int(fairness["significant"].sum())
    compas = fairness[fairness["audit"] == "compas"]
    compas_significant = compas[compas["significant"]]

    r = _run_dom_stub()

    assert r["results_hidden_after_load"] is False
    assert r["summary_unfiltered"] == f"{total:,} of {total:,} rows shown · {total_significant:,} significant"

    assert r["audit_select_found"] is True
    assert r["table_has_only_compas"] is True
    assert r["summary_after_audit_filter"] == (
        f"{len(compas):,} of {total:,} rows shown · {int(compas['significant'].sum()):,} significant"
    )

    assert r["summary_after_significant_only"] == (
        f"{len(compas_significant):,} of {total:,} rows shown · {len(compas_significant):,} significant"
    )

    assert r["value_sort_btn_found"] is True
    assert r["first_row_value_asc"] == _rounded(compas_significant["value"].min())
    assert r["first_row_value_desc"] == _rounded(compas_significant["value"].max())

    assert r["performance_tab_summary"] == f"{len(performance):,} of {len(performance):,} rows shown"

    # #762: the performance tab charts too, once a metric is chosen.
    perf_accuracy = performance[performance["metric"] == "accuracy"]
    assert "Pick a metric" in r["perf_chart_note_before"]
    assert r["perf_chart_hidden"] is False
    assert r["perf_chart_bars"] == len(perf_accuracy)

    # #777 / #788 / #787: sort state is exposed, notes and small-sample rows are visible.
    assert r["aria_sort_value"] is True
    assert r["has_note_column"] is True
    assert (r["small_badges"] > 0) == bool(compas_significant["small_sample_warning"].any())

    # #776: a signed metric draws from a centre line, with negative bars marked.
    sel = fairness[(fairness["metric"] == "demographic_parity_diff") & (fairness["protected_attribute"] == "race")]
    assert r["signed_chart"] is bool((sel["value"] < 0).any())
    assert r["neg_bars"] == int((sel["value"] < 0).sum())
    assert r["perf_chart_unsigned"] is True

    # #784: clearing unloads the active tab's data.
    assert r["after_clear_summary"] == ""
    assert "Cleared performance" in r["after_clear_status"]

    # #796: the chart downloads as a real SVG built from the same data.
    assert r["svg_button_visible"] is True
    assert r["svg"].startswith("<svg") and "<title" in r["svg"]
    assert r["svg"].count("<rect x=") >= 1 and "demographic_parity_diff" in r["svg"]
    assert 'stroke="#bdb59c"' in r["svg"]  # signed metric -> centre line
    assert r["figure_hidden_without_audit"] is True

    # #812: the chart also downloads as a 2x rasterised PNG blob via canvas.
    assert r["png_download_name"] == "benchmark-fairness-chart.png"
    assert r["png_blob_type"] == "image/png"
    assert r["canvas_context_kind"] == "2d"
    assert r["canvas_to_blob_type"] == "image/png"
    assert r["canvas_width"] == 910 * 2
    assert r["canvas_height"] > 0
    assert ["scale", 2, 2] in r["canvas_calls"]
    assert any(call[0] == "drawImage" for call in r["canvas_calls"])

    # #794: the roll-up summary tab lists summary.csv's rows with "k / n" model counts.
    summary = pd.read_csv(REPO_ROOT / "results" / "summary.csv")
    assert r["summary_summary"].startswith(f"{len(summary):,} of {len(summary):,} rows shown")
    assert r["summary_sig_cell"] is True

    # #795: filtering to one audit on bundled data shows that audit's committed figure.
    assert r["figure_visible"] is True
    assert r["figure_src"] == "results/figures/compas_strategies.png"
    assert (REPO_ROOT / "results" / "figures" / "compas_strategies.png").exists()
    assert r["figure_hidden_on_performance"] is True

    # #761: the export is the filtered + sorted view, header included.
    assert r["export_btn_hidden"] is False
    lines = r["export_csv"].strip().split("\r\n")
    assert lines[0].startswith("audit,strategy,model,protected_attribute,metric,value")
    assert len(lines) == len(compas_significant) + 1
    assert round(float(lines[1].split(",")[5]), 4) == _rounded(compas_significant["value"].max())

    # Reset clears the active tab's dropdown filters and sort, as well as the
    # cross-view significance toggle, then rewrites the deep link to defaults.
    assert r["summary_after_reset"] == (
        f"{total:,} of {total:,} rows shown · {total_significant:,} significant"
    )
    assert r["reset_disabled_before_reset"] is False
    assert r["significant_only_after_reset"] is False
    assert r["sort_cleared_after_reset"] is True
    assert r["url_after_reset"] == "?tab=fairness"
    assert r["reset_disabled_after_reset"] is True


def _rounded(x):
    # Table cells are rendered with .toFixed(4); round the pandas ground
    # truth the same way for an exact equality check.
    return round(float(x), 4)


def test_benchmark_dashboard_ui_wiring_present_in_html_and_css():
    """Source-level check (matches the #740 precedent for DOM-coupled code):
    the dashboard page must expose the ids benchmark-dashboard.js binds to,
    and ROADMAP.md's Phase 5 checklist item should be checked off now that
    this exists."""
    html = (REPO_ROOT / "benchmark.html").read_text(encoding="utf-8")
    for expected_id in ["loadBundledBtn", "benchDropzone", "benchFileInput", "benchError",
                         "benchStatus", "benchResults", "benchFilters", "significantOnlyInput",
                         "benchSummary", "benchTable", "benchChart", "benchChartNote", "benchChartBlock",
                         "benchResetBtn"]:
        assert f'id="{expected_id}"' in html, expected_id

    css = (REPO_ROOT / "assets" / "benchmark.css").read_text(encoding="utf-8")
    assert ".bench-table" in css

    assert html.count('aria-live="polite"') >= 2  # #763
    for new_id in ("benchChartSvgBtn", "benchChartPngBtn", "benchFigureBlock", "benchFigureImg"):
        assert f'id="{new_id}"' in html, new_id  # #795, #796
    assert 'data-tab="summary"' in html  # #794
    js = (REPO_ROOT / "assets" / "benchmark-dashboard.js").read_text(encoding="utf-8")
    assert "canvas.toBlob" in js and "image/svg+xml" in js  # PNG path (needs a real canvas)
    assert 'id="benchExportBtn"' in html

    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "- [x] Fairness dashboard for the benchmark harness results" in roadmap


def test_benchmark_dashboard_url_state_round_trips():
    """#764: a shared link restores tab/filter/significant-only/sort and
    auto-loads the bundled results; later renders keep the URL in sync."""
    fairness = pd.read_csv(REPO_ROOT / "results" / "results_fairness.csv")
    expected = fairness[(fairness["audit"] == "compas") & fairness["significant"]]

    r = _run_dom_stub("?tab=fairness&audit=compas&sig=1&sort=value:desc")
    # significant-only was restored from ?sig=1, so even before the stub toggles it
    # the audit-filtered count is already the significant subset.
    assert r["summary_after_audit_filter"].startswith(f"{len(expected):,} of")
    url = r["last_url_after_first_render"]
    for part in ("tab=fairness", "audit=compas", "sig=1", "sort=value%3Adesc"):
        assert part in url
    # ...and the stub's later switch to the performance tab rewrites it.
    assert "tab=performance" in r["last_url"]


def test_benchmark_dashboard_detect_kind_tells_the_three_result_files_apart():
    """#775/#794: results/summary.csv (protected_attribute + mean_value, no value
    column) is its own kind - never mis-detected as a fairness file."""
    src = (REPO_ROOT / "assets" / "benchmark-dashboard.js").read_text(encoding="utf-8")
    start = src.index("function detectKind")
    fn = src[start:src.index("function ingest")]
    script = fn + "process.stdout.write(JSON.stringify([" + ",".join(
        f"detectKind({json.dumps(cols)})" for cols in (
            list(pd.read_csv(REPO_ROOT / "results" / "results_fairness.csv", nrows=0).columns),
            list(pd.read_csv(REPO_ROOT / "results" / "results_performance.csv", nrows=0).columns),
            list(pd.read_csv(REPO_ROOT / "results" / "summary.csv", nrows=0).columns),
        )) + "]));"
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True,
                                    encoding="utf-8", check=True).stdout)
    assert out == ["fairness", "performance", "summary"]


def test_benchmark_dashboard_bundled_load_partial_failure():
    """#817: if one bundled CSV fails to load (e.g. 404), loadBundled still
    loads whichever files succeeded and reports the failed ones in the status line,
    rather than failing completely with the full error banner."""
    fairness = pd.read_csv(REPO_ROOT / "results" / "results_fairness.csv")
    total = len(fairness)
    total_significant = int(fairness["significant"].sum())

    # Simulate missing summary.csv (404)
    r = _run_dom_stub(block_url="summary.csv")
    assert r["results_hidden_after_load"] is False
    assert r["error_hidden_after_load"] is True
    assert "Could not load: results/summary.csv (HTTP 404)" in r["status_after_load"]
    assert "results_fairness.csv" in r["status_after_load"]
    assert "results_performance.csv" in r["status_after_load"]
    assert r["summary_unfiltered"] == f"{total:,} of {total:,} rows shown · {total_significant:,} significant"

    # Simulate all bundled files failing (e.g. offline / file:// block)
    r_all_failed = _run_dom_stub(block_url="results")
    assert r_all_failed["results_hidden_after_load"] is True
    assert r_all_failed["error_hidden_after_load"] is False
    assert "Could not fetch the bundled results/ CSVs" in r_all_failed["error_after_load"]



def test_benchmark_dashboard_summary_tab_has_a_significance_filter():
    """#819: the roll-up summary tab shows the significance toggle, filters on the
    all-models-significant flag, and keeps it in the URL like the fairness tab."""
    summary = pd.read_csv(REPO_ROOT / "results" / "summary.csv")
    every_model = summary[(summary["n_models"] > 0)
                          & (summary["n_models_significant"] == summary["n_models"])]
    assert 0 < len(every_model) < len(summary), "fixture needs both kinds of summary row"

    r = _run_dom_stub("?tab=summary", mode="load-only")
    assert r["sig_parent_hidden"] is False  # visible on the summary tab now
    assert r["sig_checked"] is False
    assert "every model" in r["sig_label"]
    assert r["summary_unfiltered"] == (
        f"{len(summary):,} of {len(summary):,} rows shown"
        f" · {len(every_model):,} significant in every model")
    assert r["summary_after_toggle"] == (
        f"{len(every_model):,} of {len(summary):,} rows shown"
        f" · {len(every_model):,} significant in every model")
    assert "tab=summary" in r["url_after_toggle"] and "sig=1" in r["url_after_toggle"]

    restored = _run_dom_stub("?tab=summary&sig=1", mode="load-only")
    assert restored["sig_checked"] is True
    assert restored["summary_unfiltered"].startswith(f"{len(every_model):,} of {len(summary):,} rows shown")


def test_benchmark_dashboard_chart_export_follows_the_chosen_colours():
    """#813: the SVG/PNG export no longer hard-codes the light tokens - it follows the
    page's resolved CSS variables by default and offers Light / Dark / Transparent."""
    r = _run_dom_stub("", mode="chart-theme")
    themes = r["themes"]
    light, dark = ('fill="#f4f1e8"', "#a63a22"), ('fill="#15130d"', "#cf6f49")

    assert all(token in themes["light"] for token in light)
    assert all(token in themes["dark"] for token in dark)
    assert "#f4f1e8" not in themes["dark"] and "#a63a22" not in themes["dark"]
    assert 'stroke="#443e2d"' in themes["dark"]  # signed metric -> the dark axis colour

    # transparent: no background rect, light ink so it reads on a white slide
    assert 'width="100%" height="100%"' not in themes["transparent"]
    assert 'fill="#36321f"' in themes["transparent"]

    # page: light fallback with no DOM styles, and the page's own variables when present
    assert all(token in themes["page"] for token in light)
    assert all(token in themes["page_dark_vars"] for token in dark)
    assert "#f4f1e8" not in themes["page_dark_vars"]


def test_benchmark_dashboard_chart_theme_control_is_wired():
    html = (REPO_ROOT / "benchmark.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "assets" / "benchmark-dashboard.js").read_text(encoding="utf-8")
    assert 'id="benchChartThemeSelect"' in html
    for value in ("page", "light", "dark", "transparent"):
        assert f'<option value="{value}"' in html
    assert "getComputedStyle(document.documentElement)" in js


def test_benchmark_dashboard_significance_toggle_is_per_tab():
    """#864: ticking it on Fairness leaves Summary untouched (and vice versa)."""
    fairness = pd.read_csv(REPO_ROOT / "results" / "results_fairness.csv")
    summary = pd.read_csv(REPO_ROOT / "results" / "summary.csv")
    sig_fair = int(fairness["significant"].sum())

    r = _run_dom_stub("?tab=fairness", mode="sig-per-tab")
    assert r["fairness_on"].startswith(f"{sig_fair:,} of {len(fairness):,} rows shown")
    assert r["summary_checked"] is False
    assert r["summary_text"].startswith(f"{len(summary):,} of {len(summary):,} rows shown")
    assert "sig=1" not in r["summary_url"]
    assert r["fairness_checked_again"] is True
    assert r["fairness_text_again"].startswith(f"{sig_fair:,} of")
    assert r["summary_still_checked"] is True
