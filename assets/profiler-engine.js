/* ════════════════════════════════════════════════════════════════════════
   Fair Code - Dataset Profiler ENGINE (browser port of faircode/profiler.py)

   This is a faithful JavaScript port of faircode/SPEC.md. It MUST produce the
   same numbers as the Python CLI for the same CSV. All analysis runs locally
   in the browser - the file never leaves the visitor's machine.

   Exposes window.FairCodeProfiler = { parseCSV, sniffDelimiter, profile }.
   ════════════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  // ── Defaults (SPEC section 7) ──────────────────────────────────────────
  var MIN_SHARE_THRESHOLD = 0.05;
  var INTERSECTION_FLOOR = 0.01;
  var IMBALANCE_FLAG = 3.0;
  var MISSING_FLAG = 0.05;
  var AGE_BANDS = [0, 18, 30, 45, 60, 75];
  var MAX_CATEGORICAL_CARD = 20;
  var MAX_DIMENSION_GROUPS = 50;
  var MIN_GROUP_SIZE = 100;  // warn when a subgroup has fewer than N rows (SPEC 3)
  var REFERENCE_DEVIATION_FLAG = 0.05;
  // Kinds a manual override may force a column to; mirror faircode/detect.py.
  var VALID_KINDS = { sex: 1, race: 1, age: 1, geography: 1, categorical: 1 };

  // Tunable knobs (SPEC section 7); overridable per call via profile(opts).
  var DEFAULT_OPTS = {
    min_share: MIN_SHARE_THRESHOLD,
    intersection_floor: INTERSECTION_FLOOR,
    imbalance_flag: IMBALANCE_FLAG,
    missing_flag: MISSING_FLAG,
    reference_flag: REFERENCE_DEVIATION_FLAG,
    min_group_size: MIN_GROUP_SIZE,  // warn when a subgroup has fewer than N rows
    cross: null,      // [colA, colB] to force the intersection pair (SPEC 4)
    reference: null   // {column: {group: expected_share}} baseline (SPEC 8)
  };

  function resolveOpts(opts) {
    var o = {};
    Object.keys(DEFAULT_OPTS).forEach(function (k) { o[k] = DEFAULT_OPTS[k]; });
    if (opts) {
      Object.keys(opts).forEach(function (k) {
        if (opts[k] !== null && opts[k] !== undefined) o[k] = opts[k];
      });
    }
    return o;
  }
  // Comparison / drift (SPEC section 8)
  var PSI_EPSILON = 0.0001;
  var PSI_MODERATE = 0.10;
  var PSI_SIGNIFICANT = 0.25;
  var SCORE_DROP_FLAG = 5;

  // Pandas-style missing tokens, so JS null-handling matches read_csv defaults.
  var NA_TOKENS = {
  '': 1,
  'na': 1,
  'n/a': 1,
  'nan': 1,
  'null': 1,
  // Intentionally exclude "none" to match the Python profiler.
  // In this project, pd.read_csv() preserves the literal string "none"
  // as a categorical value, so treating it as missing breaks Python↔JS
  // parity (see credit_customers.csv).
};

  // ── Keyword lists - MUST mirror faircode/detect.py ─────────────────────
  var KEYWORDS = [
    ['sex', ['sex', 'gender']],
    ['race', ['race', 'ethnic', 'ethnicity']],
    ['age', ['age', 'dob', 'yob', 'birth']],
    ['geography', ['region', 'state', 'zip', 'zipcode', 'postal', 'country',
                   'county', 'city', 'location', 'province']]
  ];

  var DATE_RE = /\d{1,4}[/-]\d{1,2}[/-]\d{1,4}/;

  // ── Delimiter sniffing (SPEC-adjacent; mirrors faircode/loaders.py) ─────
  // Picks whichever of , \t ; | appears the same number of times on every
  // sampled line - so a tab-separated export saved as .csv still parses.
  var DELIMITER_CANDIDATES = [',', '\t', ';', '|'];

  function sniffDelimiter(text) {
    var sample = text.slice(0, 8192).split(/\r\n|\r|\n/).filter(Boolean).slice(0, 5);
    if (!sample.length) return ',';
    var best = ',', bestCount = -1;
    DELIMITER_CANDIDATES.forEach(function (d) {
      var counts = sample.map(function (line) { return line.split(d).length - 1; });
      var first = counts[0];
      if (first <= 0) return;
      var consistent = counts.every(function (c) { return c === first; });
      if (consistent && first > bestCount) { bestCount = first; best = d; }
    });
    return best;
  }

  // ── CSV/TSV parsing ──────────────────────────────────────────────────────
  // Handles quoted fields, escaped quotes (""), and newlines inside quotes.
  function parseCSV(text, delimiter) {
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); // strip BOM
    delimiter = delimiter || sniffDelimiter(text);
    var rows = [], field = '', row = [], inQuotes = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += c;
      } else if (c === '"') {
        inQuotes = true;
      } else if (c === delimiter) {
        row.push(field); field = '';
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = '';
        if (row.length > 1 || row[0] !== '') rows.push(row);
        row = [];
      } else field += c;
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }
    if (!rows.length) return { columns: [], rows: [] };

    var columns = rows[0];
    var data = [];
    for (var r = 1; r < rows.length; r++) {
      var obj = {};
      for (var ci = 0; ci < columns.length; ci++) {
        var raw = rows[r][ci];
        raw = raw === undefined ? '' : raw;
        obj[columns[ci]] = isMissing(raw) ? null : raw;
      }
      data.push(obj);
    }
    return { columns: columns, rows: data };
  }
  // Shared by parseJSON's records branch and parseXLSX: turn an array of
  // plain-object records into { columns, rows }. Columns are the union of
  // every record's keys (first-seen order), not just the first record's -
  // pandas' read_json/read_excel do the same, so a later record with an
  // extra key (or an earlier one missing a key another has) isn't silently
  // dropped.
  function recordsToTable(records) {
    if (!records.length) return { columns: [], rows: [] };
    var columns = [];
    var seen = {};
    for (var pi = 0; pi < records.length; pi++) {
      var record = records[pi];
      if (!record || typeof record !== "object" || Array.isArray(record)) {
        throw new Error("Unsupported JSON format (expected records or split orientation).");
      }
      var keys = Object.keys(record);
      for (var ki = 0; ki < keys.length; ki++) {
        if (!seen[keys[ki]]) { seen[keys[ki]] = true; columns.push(keys[ki]); }
      }
    }
    var rows = [];
    for (var i = 0; i < records.length; i++) {
      var item = records[i];
      var obj = {};
      for (var ci = 0; ci < columns.length; ci++) {
        var raw = item[columns[ci]];
        raw = raw === undefined ? '' : raw;
        obj[columns[ci]] = isMissing(raw) ? null : raw;
      }
      rows.push(obj);
    }
    return { columns: columns, rows: rows };
  }

  // ── JSON parsing ────────────────────────────────────────────────────────
  // Handles Pandas/standard JSON in records ([{col: val}]) and split
  // ({columns: [...], data: [[...]]}) formats.
  function parseJSON(text) {
    if (typeof text !== 'string') text = String(text);
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); // strip BOM
    var parsed;
    try {
      parsed = JSON.parse(text);
    } catch (syntaxErr) {
      // Raw SyntaxError messages are browser-specific (e.g. "Unexpected end
      // of JSON input" vs "Unexpected token") and confusing in the dropzone's
      // error banner - wrap them like the tabular-shape checks below do.
      throw new Error('Unsupported JSON format (not valid JSON: ' + syntaxErr.message + ').');
    }
    if (!parsed) return { columns: [], rows: [] };

    // 1. Records format: [ { colA: 1, colB: 2 }, ... ].
    if (Array.isArray(parsed)) {
      if (!parsed.length) return { columns: [], rows: [] };
      if (!parsed[0] || typeof parsed[0] !== "object" || Array.isArray(parsed[0])) {
        throw new Error("Unsupported JSON format (expected records or split orientation).");
      }
      return recordsToTable(parsed);
    }

    // 2. Split format: { columns: ["colA", "colB"], data: [[1, 2], ...] }
    if (typeof parsed === 'object' && Array.isArray(parsed.columns) && Array.isArray(parsed.data)) {
      var splitColumns = parsed.columns.map(String);
      var splitRows = [];

      for (var r = 0; r < parsed.data.length; r++) {
        var rowVal = parsed.data[r] || [];
        var splitObj = {};
        for (var sci = 0; sci < splitColumns.length; sci++) {
          var splitRaw = rowVal[sci];
          splitRaw = splitRaw === undefined ? '' : splitRaw;
          splitObj[splitColumns[sci]] = isMissing(splitRaw) ? null : splitRaw;
        }
        splitRows.push(splitObj);
      }
      return { columns: splitColumns, rows: splitRows };
    }

    // 3. Columns format: { colA: { "0": v0, "1": v1 }, colB: { ... } }.
    // pandas' read_json defaults to this orientation for a plain object, so
    // the CLI already accepts it (README/#155) - match that here too. Row
    // order/index keys are the union across every column's keys, first-seen
    // order, same reasoning as the records branch above.
    if (typeof parsed === 'object' && !Array.isArray(parsed)) {
      var colNames = Object.keys(parsed);
      var looksColumnar = colNames.length > 0 && colNames.every(function (c) {
        var v = parsed[c];
        if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
        // Each entry must be a scalar (index -> value), not itself a nested
        // object - otherwise a deeply-nested, non-tabular structure like
        // {"a": {"b": {"c": 1}}} is silently misread as one column "a" with
        // a row "b" whose cell value is the object {"c": 1}.
        return Object.keys(v).every(function (k) {
          var cell = v[k];
          return cell === null || typeof cell !== 'object';
        });
      });
      if (looksColumnar) {
        var indexKeys = [];
        var indexSeen = {};
        for (var cni = 0; cni < colNames.length; cni++) {
          var idxKeys = Object.keys(parsed[colNames[cni]]);
          for (var iki = 0; iki < idxKeys.length; iki++) {
            if (!indexSeen[idxKeys[iki]]) { indexSeen[idxKeys[iki]] = true; indexKeys.push(idxKeys[iki]); }
          }
        }
        var colRows = [];
        for (var ri = 0; ri < indexKeys.length; ri++) {
          var colObj = {};
          for (var cni2 = 0; cni2 < colNames.length; cni2++) {
            var colRaw = parsed[colNames[cni2]][indexKeys[ri]];
            colRaw = colRaw === undefined ? '' : colRaw;
            colObj[colNames[cni2]] = isMissing(colRaw) ? null : colRaw;
          }
          colRows.push(colObj);
        }
        return { columns: colNames, rows: colRows };
      }
    }

    // 4. Reject non-tabular / unsupported objects explicitly
    throw new Error('Unsupported JSON format (expected records, split, or columns orientation).');
  }

  // ── XLSX parsing ────────────────────────────────────────────────────────
  // Reads the first sheet via SheetJS (loaded separately - see profiler.html
  // / assets/sheetjs.min.js), converts to records, and reuses the same
  // union-of-columns table builder as parseJSON. SheetJS isn't bundled into
  // this file since it's a large third-party library with its own license -
  // profiler.html loads it from a pinned CDN URL only when needed.
  async function parseXLSX(arrayBuffer) {
    await loadSheetJS();

    var workbook;
    try {
      workbook = global.XLSX.read(arrayBuffer, { type: "array" });
    } catch (readErr) {
      throw new Error("Unsupported .xlsx file (" + readErr.message + ").");
    }

    var sheetName = workbook.SheetNames[0];
    if (!sheetName) return { table: { columns: [], rows: [] }, ignoredSheets: [], sheetName: null };

    var sheet = workbook.Sheets[sheetName];
    var records = global.XLSX.utils.sheet_to_json(sheet, { defval: null, raw: true });

    if (records.length === 0) {
      // sheet_to_json() drops the header row entirely when there are no data
      // rows beneath it, which would silently lose a headers-only sheet's
      // column names. pandas.read_excel() keeps them (0 rows, N columns) -
      // read the raw header row instead of erroring, to match.
      var headerRow = global.XLSX.utils.sheet_to_json(sheet, { header: 1, raw: true })[0] || [];
      var columns = headerRow.map(function (h) {
        return h === null || h === undefined ? '' : String(h);
      });
      return { table: { columns: columns, rows: [] }, ignoredSheets: workbook.SheetNames.slice(1), sheetName: sheetName };
    }

    return { table: recordsToTable(records), ignoredSheets: workbook.SheetNames.slice(1), sheetName: sheetName };
  }

  var sheetJsPromise = null;

  async function loadSheetJS() {
    if (global.XLSX) {
      return Promise.resolve();
    }

    if (sheetJsPromise) {
      return sheetJsPromise;
    }

    sheetJsPromise = new Promise(function (resolve, reject) {
      var script = document.createElement("script");

      script.src = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";
      script.integrity = "sha384-vtjasyidUo0kW94K5MXDXntzOJpQgBKXmE7e2Ga4LG0skTTLeBi97eFAXsqewJjw";
      script.crossOrigin = "anonymous";

      script.onload = function () {
        resolve();
      };

      script.onerror = function () {
        script.remove();
        sheetJsPromise = null;  // let the next .xlsx upload retry instead of reusing this rejection forever
        reject(new Error(
          "The Excel parsing library failed to load (check your network connection), " +
          "or use the CLI instead: faircode profile data.xlsx"
        ));
      };

      document.head.appendChild(script);
    });

    return sheetJsPromise;
  }
  function isMissing(v) {
    if (v === null || v === undefined) return true;
    return NA_TOKENS.hasOwnProperty(String(v).trim().toLowerCase());
  }

  // ── Column detection (SPEC section 1) ──────────────────────────────────
  function tokens(name) {
    var spaced = String(name).replace(/([a-z0-9])([A-Z])/g, '$1 $2');
    return spaced.split(/[^A-Za-z0-9]+/).filter(Boolean).map(function (t) {
      return t.toLowerCase();
    });
  }

  // Keywords whose prefix form collides with ordinary English words - see
  // faircode/detect.py's EXACT_ONLY_KEYWORDS, must mirror it exactly.
  var EXACT_ONLY_KEYWORDS = { race: 1, state: 1, city: 1, region: 1, country: 1 };

  function tokenMatches(token, keyword) {
    if (keyword.length < 4 || EXACT_ONLY_KEYWORDS.hasOwnProperty(keyword)) return token === keyword;
    return token.indexOf(keyword) === 0; // prefix match
  }

  function classifyName(name) {
    var toks = tokens(name);
    for (var k = 0; k < KEYWORDS.length; k++) {
      var kind = KEYWORDS[k][0], words = KEYWORDS[k][1];
      for (var t = 0; t < toks.length; t++) {
        for (var w = 0; w < words.length; w++) {
          if (tokenMatches(toks[t], words[w])) return kind;
        }
      }
    }
    return null;
  }

  function nunique(rows, col) {
    var seen = {};
    for (var i = 0; i < rows.length; i++) {
      var v = rows[i][col];
      if (v !== null) seen[v] = 1;
    }
    return Object.keys(seen).length;
  }

  function detectColumns(table, overrides) {
    overrides = overrides || {};
    var detected = [];
    table.columns.forEach(function (col) {
      if (Object.prototype.hasOwnProperty.call(overrides, col)) {
        var forced = overrides[col];
        if (VALID_KINDS[forced]) detected.push({ name: col, kind: forced });
        return; // any other value (e.g. 'ignore') excludes the column
      }
      var kind = classifyName(col);
      if (kind !== null) { detected.push({ name: col, kind: kind }); return; }
      var n = nunique(table.rows, col);
      if (n >= 2 && n <= MAX_CATEGORICAL_CARD) {
        detected.push({ name: col, kind: 'categorical' });
      }
    });
    return detected;
  }

  // ── Age handling (SPEC section 2) ──────────────────────────────────────
  function ageToNumeric(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'number') return value;
    var m = String(value).match(/\d+/);
    return m ? parseFloat(m[0]) : null;
  }

  function ageBand(num) {
    if (num === null) return null;
    for (var i = 0; i < AGE_BANDS.length - 1; i++) {
      if (num >= AGE_BANDS[i] && num < AGE_BANDS[i + 1]) {
        return AGE_BANDS[i] + '-' + AGE_BANDS[i + 1];
      }
    }
    return AGE_BANDS[AGE_BANDS.length - 1] + '+';
  }

  var AGE_BAND_LABELS = {};
  (function () {
    for (var i = 0; i < AGE_BANDS.length - 1; i++) {
      AGE_BAND_LABELS[AGE_BANDS[i] + '-' + AGE_BANDS[i + 1]] = true;
    }
    AGE_BAND_LABELS[AGE_BANDS[AGE_BANDS.length - 1] + '+'] = true;
  })();

  // compare() uses this to detect a kind="age" dimension banded on one side
  // (numeric ages) but not the other (raw dates, which the profiler never
  // bands - see looksLikeDates()): `kind` alone can't tell the two apart,
  // since it's set from the column name and is identical either way.
  function isAgeBandLabel(label) {
    return !!AGE_BAND_LABELS[String(label)];
  }

  function looksLikeDates(rows, col) {
    var sample = [], i;
    for (i = 0; i < rows.length && sample.length < 50; i++) {
      if (rows[i][col] !== null) sample.push(String(rows[i][col]));
    }
    if (!sample.length) return false;
    var hits = 0;
    for (i = 0; i < sample.length; i++) if (DATE_RE.test(sample[i])) hits++;
    return hits / sample.length > 0.5;
  }

  function skewness(values) {
    var n = values.length;
    if (n < 3) return null;
    var mean = 0, i;
    for (i = 0; i < n; i++) mean += values[i];
    mean /= n;
    var m2 = 0, m3 = 0, d;
    for (i = 0; i < n; i++) { d = values[i] - mean; m2 += d * d; m3 += d * d * d; }
    m2 /= n; m3 /= n;
    if (m2 === 0) return null;
    return m3 / Math.pow(m2, 1.5);
  }

  function round(x, dp) {
    var f = Math.pow(10, dp || 0);
    return Math.round(x * f) / f;
  }

  // 95% normal quantile, shared verbatim with faircode/profiler.py so both
  // engines return identical Wilson bounds (SPEC section 3).
  var Z95 = 1.959963984540054;
  function wilson(count, n) {
    if (n <= 0) return [0, 0];
    var p = count / n;
    var z2 = Z95 * Z95;
    var denom = 1 + z2 / n;
    var center = (p + z2 / (2 * n)) / denom;
    var margin = (Z95 / denom) * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n));
    var lo = center - margin, hi = center + margin;
    return [lo > 0 ? lo : 0, hi < 1 ? hi : 1];
  }

  // ── Per-dimension metrics (SPEC section 3) ─────────────────────────────
  function analyzeGroups(counts, nTotal, nullCount, skew, minShareThreshold, minGroupSize) {
    if (minShareThreshold === undefined) minShareThreshold = MIN_SHARE_THRESHOLD;
    if (minGroupSize === undefined) minGroupSize = MIN_GROUP_SIZE;
    var labels = Object.keys(counts);
    var nNonnull = 0, i;
    for (i = 0; i < labels.length; i++) nNonnull += counts[labels[i]];

    var groups = labels.map(function (label) {
      var c = counts[label];
      var ci = wilson(c, nNonnull);
      return { label: String(label), count: c,
               share: nNonnull ? c / nNonnull : 0,
               ci_low: round(ci[0], 4), ci_high: round(ci[1], 4),
               small_group: c < minGroupSize };
    });
    // count desc, then label asc - deterministic tie-break to match Python.
    groups.sort(function (a, b) {
      return (b.count - a.count) ||
             (a.label < b.label ? -1 : a.label > b.label ? 1 : 0);
    });

    var shares = groups.map(function (g) { return g.share; });
    var k = shares.length;
    var minShare = k ? Math.min.apply(null, shares) : 0;
    var maxShare = k ? Math.max.apply(null, shares) : 0;
    var imbalance = minShare > 0 ? maxShare / minShare : Infinity;

    var entropyRatio;
    if (k <= 1) {
      entropyRatio = 0;
    } else {
      var H = 0;
      for (i = 0; i < shares.length; i++) {
        if (shares[i] > 0) H -= shares[i] * Math.log(shares[i]);
      }
      entropyRatio = H / Math.log(k);
    }

    var under = groups.filter(function (g) { return g.share < minShareThreshold; })
                      .map(function (g) { return g.label; });

    return {
      n_groups: k,
      dimension_score: Math.round(entropyRatio * 100),
      entropy_ratio: round(entropyRatio, 4),
      imbalance_ratio: imbalance === Infinity ? null : round(imbalance, 2),
      min_share: round(minShare, 4),
      missing_pct: nTotal ? round(nullCount / nTotal, 4) : 0,
      skewness: skew === null || skew === undefined ? null : round(skew, 4),
      groups: groups.map(function (g) {
        return { label: g.label, count: g.count, share: g.share,
                 ci_low: g.ci_low, ci_high: g.ci_high, small_group: g.small_group };
      }),
      under_represented: under
    };
  }

  function dimension(table, name, kind, minShareThreshold, minGroupSize) {
    var rows = table.rows, nTotal = rows.length, i, v;

    if (kind === 'age' && !looksLikeDates(rows, name)) {
      var nums = [], numericVals = [];
      for (i = 0; i < nTotal; i++) {
        var num = ageToNumeric(rows[i][name]);
        nums.push(num);
        if (num !== null) numericVals.push(num);
      }
      if (numericVals.length) {
        var skew = skewness(numericVals);
        var counts = {}, nullCount = 0;
        for (i = 0; i < nums.length; i++) {
          var b = ageBand(nums[i]);
          if (b === null) nullCount++;
          else counts[b] = (counts[b] || 0) + 1;
        }
        var res = analyzeGroups(counts, nTotal, nullCount, skew, minShareThreshold, minGroupSize);
        res.name = name; res.kind = kind;
        return res;
      }
    }

    // Categorical path.
    var c = {}, nulls = 0;
    for (i = 0; i < nTotal; i++) {
      v = rows[i][name];
      if (v === null) nulls++;
      else c[v] = (c[v] || 0) + 1;
    }
    var r = analyzeGroups(c, nTotal, nulls, null, minShareThreshold, minGroupSize);
    r.name = name; r.kind = kind;
    return r;
  }

  // ── Intersectional gaps (SPEC section 4) ───────────────────────────────
  function labelize(table, name, kind) {
    var rows = table.rows, out = [], i;
    if (kind === 'age' && !looksLikeDates(rows, name)) {
      var any = false;
      for (i = 0; i < rows.length; i++) {
        if (ageToNumeric(rows[i][name]) !== null) { any = true; break; }
      }
      if (any) {
        for (i = 0; i < rows.length; i++) out.push(ageBand(ageToNumeric(rows[i][name])));
        return out;
      }
    }
    for (i = 0; i < rows.length; i++) out.push(rows[i][name]);
    return out;
  }

  function pickCross(dims, cross) {
    if (cross && cross.length === 2) {
      var byName = {};
      dims.forEach(function (d) { byName[d.name] = d; });
      if (byName[cross[0]] && byName[cross[1]]) return [byName[cross[0]], byName[cross[1]]];
    }
    return [dims[0], dims[1]];
  }

  function intersections(table, dims, intersectionFloor, cross) {
    if (dims.length < 2) return [];
    if (intersectionFloor === undefined) intersectionFloor = INTERSECTION_FLOOR;
    var pair = pickCross(dims, cross), a = pair[0], b = pair[1];
    var nTotal = table.rows.length;
    var floor = intersectionFloor * nTotal;
    var la = labelize(table, a.name, a.kind);
    var lb = labelize(table, b.name, b.kind);

    var ct = {}, aVals = {}, bVals = {}, i, key;
    for (i = 0; i < nTotal; i++) {
      if (la[i] === null || lb[i] === null) continue;
      aVals[la[i]] = 1; bVals[lb[i]] = 1;
      key = la[i] + '\0' + lb[i];
      ct[key] = (ct[key] || 0) + 1;
    }
    var cells = [];
    Object.keys(aVals).forEach(function (av) {
      Object.keys(bVals).forEach(function (bv) {
        var count = ct[av + '\0' + bv] || 0;
        if (count === 0 || count < floor) {
          cells.push({ a: String(av), b: String(bv), count: count });
        }
      });
    });
    if (!cells.length) return [];
    cells.sort(function (x, y) {  // deterministic order, matches Python
      return x.a < y.a ? -1 : x.a > y.a ? 1 : (x.b < y.b ? -1 : x.b > y.b ? 1 : 0);
    });
    return [{ dims: [a.name, b.name], cells: cells }];
  }

  // ── Flags + grade (SPEC sections 5 & 6) ────────────────────────────────
  function grade(score) {
    if (score >= 85) return 'A';
    if (score >= 70) return 'B';
    if (score >= 55) return 'C';
    if (score >= 40) return 'D';
    return 'F';
  }

  function applyReference(dimensions, reference, referenceFlag) {
    if (referenceFlag === undefined) referenceFlag = REFERENCE_DEVIATION_FLAG;
    var flags = [];
    dimensions.forEach(function (d) {
      var ref = reference[d.name];
      if (!ref) return;
      var actual = {};
      d.groups.forEach(function (g) { actual[g.label] = g.share; });
      var labels = {};
      Object.keys(actual).forEach(function (l) { labels[l] = 1; });
      Object.keys(ref).forEach(function (l) { labels[l] = 1; });
      var groups = [], deviation = 0;
      Object.keys(labels).forEach(function (label) {
        var exp = ref[label] || 0, act = actual[label] || 0, delta = act - exp;
        deviation += Math.abs(delta);
        groups.push({ label: String(label), expected: round(exp, 4),
                      actual: round(act, 4), delta: round(delta, 4) });
        if (exp - act >= referenceFlag) {
          flags.push(d.name + ": '" + label + "' under-represented vs reference (" +
                     (act * 100).toFixed(1) + '% vs ' + (exp * 100).toFixed(1) + '% expected)');
        }
      });
      groups.sort(function (x, y) {
        return (Math.abs(y.delta) - Math.abs(x.delta)) ||
               (x.label < y.label ? -1 : x.label > y.label ? 1 : 0);
      });
      d.reference = { deviation: round(0.5 * deviation, 4), groups: groups };
    });
    return flags;
  }

  function buildFlags(dimensions, inters, imbalanceFlag, missingFlag) {
    if (imbalanceFlag === undefined) imbalanceFlag = IMBALANCE_FLAG;
    if (missingFlag === undefined) missingFlag = MISSING_FLAG;
    var flags = [];
    dimensions.forEach(function (d) {
      d.groups.forEach(function (g) {
        if (d.under_represented.indexOf(g.label) !== -1) {
          flags.push(d.name + ": '" + g.label + "' is under-represented (" +
                     (g.share * 100).toFixed(1) + '%)');
        }
        if (g.small_group) {
          flags.push(
            d.name + ": '" + g.label + "' has only " +
            g.count + " rows; fairness metrics may be unreliable"
          );
        }
      });
      if (d.imbalance_ratio !== null && d.imbalance_ratio >= imbalanceFlag) {
        flags.push(d.name + ': imbalance ratio ' + d.imbalance_ratio.toFixed(1) +
                   '× between largest and smallest group');
      } else if (d.imbalance_ratio === null && d.n_groups > 1) {
        flags.push(d.name + ': a subgroup is effectively absent (0 rows)');
      }
      if (d.missing_pct >= missingFlag) {
        flags.push(d.name + ': ' + (d.missing_pct * 100).toFixed(1) +
                   '% of values are missing');
      }
    });
    inters.forEach(function (inter) {
      var a = inter.dims[0], b = inter.dims[1];
      inter.cells.forEach(function (cell) {
        var kind = cell.count === 0 ? 'absent' : 'only ' + cell.count + ' rows';
        flags.push(a + "='" + cell.a + "' × " + b + "='" + cell.b + "' is " + kind);
      });
    });
    return flags;
  }

  // ── Public entry point ─────────────────────────────────────────────────
  function profile(table, overrides, opts) {
    overrides = overrides || {};
    var o = resolveOpts(opts);
    var detected = detectColumns(table, overrides);
    var dimensions = detected.map(function (d) {
      return dimension(table, d.name, d.kind, o.min_share, o.min_group_size);
    });
    var forced = {};
    Object.keys(overrides).forEach(function (col) {
      if (VALID_KINDS[overrides[col]]) forced[col] = 1;
    });
    dimensions = dimensions.filter(function (d) {
      return d.kind === 'geography' || forced[d.name] || d.n_groups <= MAX_DIMENSION_GROUPS;
    });
    var keptNames = {};
    dimensions.forEach(function (d) { keptNames[d.name] = 1; });
    detected = detected.filter(function (d) { return keptNames[d.name]; });

    if (o.cross && o.cross.length) {
      var unknownCross = o.cross.filter(function (name) { return !keptNames[name]; });
      if (unknownCross.length) {
        throw new Error("cross column(s) don't match any profiled dimension: " + unknownCross.join(", "));
      }
    }
    var inters = intersections(table, detected, o.intersection_floor, o.cross);

    var refFlags = [];
    if (o.reference) {
      var refMatched = dimensions.some(function (d) {
        return Object.prototype.hasOwnProperty.call(o.reference, d.name);
      });
      if (!refMatched) {
        throw new Error(
          "reference file's column(s) don't match any profiled dimension: "
          + Object.keys(o.reference).sort().join(", "));
      }
      refFlags = applyReference(dimensions, o.reference, o.reference_flag);
    }

    var overall = 0;
    if (dimensions.length) {
      var sum = 0;
      dimensions.forEach(function (d) { sum += d.dimension_score; });
      overall = Math.round(sum / dimensions.length);
    }

    return {
      n_rows: table.rows.length,
      n_cols: table.columns.length,
      overall_score: overall,
      grade: grade(overall),
      dimensions: dimensions,
      intersections: inters,
      flags: buildFlags(dimensions, inters, o.imbalance_flag, o.missing_flag).concat(refFlags)
    };
  }

  // ── Reference baseline parsing (mirror faircode.profiler.parse_reference) ──
  var REF_COLUMN_ALIASES = ['column', 'dimension', 'dim'];
  var REF_GROUP_ALIASES = ['group', 'value', 'label', 'category'];
  var REF_SHARE_ALIASES = ['share', 'expected', 'expected_share', 'proportion', 'percent', 'pct'];

  function parseReference(table) {
    var lower = {};
    table.columns.forEach(function (c) { lower[String(c).trim().toLowerCase()] = c; });
    function pick(aliases) {
      for (var i = 0; i < aliases.length; i++) if (lower[aliases[i]]) return lower[aliases[i]];
      return null;
    }
    var colC = pick(REF_COLUMN_ALIASES), grpC = pick(REF_GROUP_ALIASES), shrC = pick(REF_SHARE_ALIASES);
    if (!(colC && grpC && shrC)) {
      throw new Error('reference needs column, group, and share columns (e.g. headers: column,group,share)');
    }
    var raw = [];
    table.rows.forEach(function (row) {
      var share = parseFloat(row[shrC]);
      if (isNaN(share)) return;
      raw.push([String(row[colC]).trim(), String(row[grpC]).trim(), share]);
    });
    var scale = raw.some(function (r) { return r[2] > 1.5; }) ? 100 : 1;
    var reference = {};
    raw.forEach(function (r) {
      if (!reference[r[0]]) reference[r[0]] = {};
      reference[r[0]][r[1]] = r[2] / scale;
    });
    return reference;
  }

  // ── Dataset comparison / drift (SPEC section 8) ────────────────────────
  function shareMap(dim) {
    var m = {};
    dim.groups.forEach(function (g) { m[g.label] = g.share; });
    return m;
  }

  function psiTerm(shareA, shareB) {
    var a = shareA > 0 ? shareA : PSI_EPSILON;
    var b = shareB > 0 ? shareB : PSI_EPSILON;
    return (b - a) * Math.log(b / a);
  }

  function driftLevel(psi) {
    if (psi >= PSI_SIGNIFICANT) return 'significant';
    if (psi >= PSI_MODERATE) return 'moderate';
    return 'none';
  }

  function ageBandingMismatch(dimA, dimB) {
    if (dimA.kind !== 'age' || dimB.kind !== 'age') return false;
    var labelsA = dimA.groups.map(function (g) { return g.label; });
    var labelsB = dimB.groups.map(function (g) { return g.label; });
    if (!labelsA.length || !labelsB.length) return false;
    var bandedA = labelsA.every(isAgeBandLabel);
    var bandedB = labelsB.every(isAgeBandLabel);
    return bandedA !== bandedB;
  }

  function compareDimension(dimA, dimB) {
    if (dimA.kind !== dimB.kind || ageBandingMismatch(dimA, dimB)) {
      // See faircode/compare.py's _compare_dimension() for why a kind
      // mismatch skips the comparison instead of reporting a PSI that
      // looks alarming but isn't real.
      return {
        name: dimA.name, kind: dimA.kind,
        kind_a: dimA.kind, kind_b: dimB.kind, kind_mismatch: true,
        dimension_score_a: dimA.dimension_score,
        dimension_score_b: dimB.dimension_score,
        dimension_score_delta: dimB.dimension_score - dimA.dimension_score,
        psi: 0, tvd: 0, drift_level: 'none', groups: []
      };
    }
    var sa = shareMap(dimA), sb = shareMap(dimB);
    var labels = {};
    Object.keys(sa).forEach(function (l) { labels[l] = 1; });
    Object.keys(sb).forEach(function (l) { labels[l] = 1; });

    var groups = [], psiTotal = 0, tvdTotal = 0;
    Object.keys(labels).forEach(function (label) {
      var a = sa[label] || 0, b = sb[label] || 0;
      psiTotal += psiTerm(a, b);
      tvdTotal += Math.abs(b - a);
      var status = (a === 0 && b > 0) ? 'appeared'
                 : (a > 0 && b === 0) ? 'disappeared' : 'shifted';
      groups.push({ label: String(label), share_a: round(a, 4),
                    share_b: round(b, 4), share_delta: round(b - a, 4),
                    status: status });
    });
    // most-shifted first, then label asc - matches Python.
    groups.sort(function (x, y) {
      return (Math.abs(y.share_delta) - Math.abs(x.share_delta)) ||
             (x.label < y.label ? -1 : x.label > y.label ? 1 : 0);
    });

    return {
      name: dimA.name, kind: dimA.kind,
      kind_a: dimA.kind, kind_b: dimB.kind, kind_mismatch: false,
      dimension_score_a: dimA.dimension_score,
      dimension_score_b: dimB.dimension_score,
      dimension_score_delta: dimB.dimension_score - dimA.dimension_score,
      psi: round(psiTotal, 4), tvd: round(0.5 * tvdTotal, 4),
      drift_level: driftLevel(psiTotal), groups: groups
    };
  }

  function compare(resultA, resultB, nameA, nameB) {
    nameA = nameA || 'A'; nameB = nameB || 'B';
    var dimsA = {}, dimsB = {};
    resultA.dimensions.forEach(function (d) { dimsA[d.name] = d; });
    resultB.dimensions.forEach(function (d) { dimsB[d.name] = d; });

    var shared = resultA.dimensions.filter(function (d) { return dimsB[d.name]; })
                                   .map(function (d) { return d.name; });
    var added = resultB.dimensions.filter(function (d) { return !dimsA[d.name]; })
                                  .map(function (d) { return d.name; });
    var removed = resultA.dimensions.filter(function (d) { return !dimsB[d.name]; })
                                    .map(function (d) { return d.name; });

    var dimensions = shared.map(function (n) {
      return compareDimension(dimsA[n], dimsB[n]);
    });
    var scoreDelta = resultB.overall_score - resultA.overall_score;

    var flags = [];
    if (scoreDelta <= -SCORE_DROP_FLAG) {
      flags.push('overall representation score dropped ' + Math.abs(scoreDelta) +
                 ' points (' + resultA.overall_score + ' → ' + resultB.overall_score + ')');
    }
    dimensions.forEach(function (cd) {
      if (cd.kind_mismatch) {
        if (cd.kind_a !== cd.kind_b) {
          flags.push(cd.name + ': detected as different kinds in ' + nameA +
                     ' (' + cd.kind_a + ') and ' + nameB + ' (' + cd.kind_b +
                     ') - drift comparison skipped');
        } else {
          flags.push(cd.name + ': age values are banded (e.g. "18-30") in ' +
                     'one dataset but left raw in the other - drift ' +
                     'comparison skipped');
        }
        return;
      }
      if (cd.drift_level !== 'none') {
        flags.push(cd.name + ': ' + cd.drift_level +
                   ' representation drift (PSI ' + cd.psi.toFixed(2) + ')');
      }
      cd.groups.forEach(function (g) {
        if (g.status === 'appeared') {
          flags.push(cd.name + ": '" + g.label + "' appeared (" +
                     (g.share_a * 100).toFixed(1) + '% → ' +
                     (g.share_b * 100).toFixed(1) + '%)');
        } else if (g.status === 'disappeared') {
          flags.push(cd.name + ": '" + g.label + "' disappeared (" +
                     (g.share_a * 100).toFixed(1) + '% → ' +
                     (g.share_b * 100).toFixed(1) + '%)');
        }
      });
    });
    added.forEach(function (n) { flags.push("dimension '" + n + "' is present only in " + nameB); });
    removed.forEach(function (n) { flags.push("dimension '" + n + "' is present only in " + nameA); });

    return {
      a: { name: nameA, n_rows: resultA.n_rows,
           overall_score: resultA.overall_score, grade: resultA.grade },
      b: { name: nameB, n_rows: resultB.n_rows,
           overall_score: resultB.overall_score, grade: resultB.grade },
      score_delta: scoreDelta, dimensions: dimensions,
      added_dimensions: added, removed_dimensions: removed, flags: flags
    };
  }

  global.FairCodeProfiler = { parseCSV: parseCSV, parseJSON: parseJSON, parseXLSX: parseXLSX,
                              sniffDelimiter: sniffDelimiter,
                              profile: profile, compare: compare,
                              parseReference: parseReference,
                              // Exposed so the Profile/Compare threshold-input
                              // placeholders (issue #377) can be sourced from
                              // this single source of truth instead of a
                              // hardcoded, driftable copy in profiler.html.
                              DEFAULT_OPTS: DEFAULT_OPTS };
})(typeof globalThis !== 'undefined' ? globalThis : this);
