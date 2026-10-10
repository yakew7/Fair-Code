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
  var DATE_SAMPLE_SIZE = 200;
  var MAX_CATEGORICAL_CARD = 20;
  var MAX_DIMENSION_GROUPS = 50;
  var MIN_GROUP_SIZE = 100;  // warn when a subgroup has fewer than N rows (SPEC 3)
  var BIRTH_YEAR_MIN = 1900;  // with age_reference_year, whole numbers from here up to it are birth years
  var MAX_AGE = 120;         // numeric ages above this are implausible, not banded (SPEC 2)
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
    max_categorical_card: MAX_CATEGORICAL_CARD,
    max_dimension_groups: MAX_DIMENSION_GROUPS,
    max_age: MAX_AGE,  // ages above this are not banded; flagged instead (SPEC 2)
    age_reference_year: null,  // convert birth years in age columns to ages as of this year
    keywords: null,   // extra column-name vocabulary {kind: [words]} for detection (SPEC 1)
    cross: null,      // [colA, colB] to force the intersection pair (SPEC 4)
    reference: null   // {column: {group: expected_share}} baseline (SPEC 8)
  };

  // SPEC section 7 tunables that must fall in [0, 1]. Mirrors
  // faircode.profiler._UNIT_INTERVAL_OPTS.
  var UNIT_INTERVAL_OPTS = ['min_share', 'intersection_floor', 'missing_flag', 'reference_flag'];

  function validateOpts(o) {
    // Reject out-of-range tunables instead of silently producing a
    // self-contradictory report (#511). Mirrors _validate_opts in the
    // Python engine.
    UNIT_INTERVAL_OPTS.forEach(function (k) {
      var v = o[k];
      if (v !== null && v !== undefined && !(v >= 0 && v <= 1)) {
        throw new Error(k + ' must be between 0 and 1, got ' + v);
      }
    });
    if (o.imbalance_flag !== null && o.imbalance_flag !== undefined && o.imbalance_flag < 1) {
      throw new Error('imbalance_flag must be >= 1, got ' + o.imbalance_flag);
    }
    if (o.min_group_size !== null && o.min_group_size !== undefined && o.min_group_size < 1) {
      throw new Error('min_group_size must be >= 1, got ' + o.min_group_size);
    }
    if (o.max_categorical_card !== null && o.max_categorical_card !== undefined && o.max_categorical_card < 2) {
      throw new Error('max_categorical_card must be >= 2, got ' + o.max_categorical_card);
    }
    if (o.max_dimension_groups !== null && o.max_dimension_groups !== undefined && o.max_dimension_groups < 1) {
      throw new Error('max_dimension_groups must be >= 1, got ' + o.max_dimension_groups);
    }
    if (o.max_age !== null && o.max_age !== undefined && !(o.max_age > 0)) {
      throw new Error('max_age must be > 0, got ' + o.max_age);
    }
    var refYear = o.age_reference_year;
    if (refYear !== null && refYear !== undefined && (refYear !== Math.floor(refYear) || refYear < BIRTH_YEAR_MIN)) {
      throw new Error('age_reference_year must be a whole year >= ' + BIRTH_YEAR_MIN + ', got ' + refYear);
    }
  }

  function resolveOpts(opts) {
    var o = {};
    Object.keys(DEFAULT_OPTS).forEach(function (k) { o[k] = DEFAULT_OPTS[k]; });
    if (opts) {
      Object.keys(opts).forEach(function (k) {
        if (opts[k] !== null && opts[k] !== undefined) o[k] = opts[k];
      });
    }
    validateOpts(o);
    o.keywords = normalizeKeywords(o.keywords);
    return o;
  }

  // Parsed data structures that carry their own provenance field elsewhere -
  // echoing them into params would be noise. Mirrors
  // faircode.provenance._OPAQUE_PARAMS.
  var OPAQUE_PARAMS = { reference: 1 };

  // The resolved knobs as actually applied (defaults included), minus the
  // opaque parsed structures, key-sorted. Mirrors
  // faircode.provenance.public_params(faircode.profiler._resolve_opts(opts)),
  // so a web-profiler export's provenance.params matches the CLI/MCP path
  // even when the user never touched a threshold input (#490).
  function publicParams(opts) {
    var resolved = resolveOpts(opts);
    var out = {};
    Object.keys(resolved).sort().forEach(function (k) {
      if (!OPAQUE_PARAMS[k]) out[k] = resolved[k];
    });
    return out;
  }
  // ── Text decoding for uploaded files (#857) ─────────────────────────────
  // The browser counterpart of faircode/loaders.py's --encoding / BOM sniffing.
  // `choice` is 'auto' (BOM sniff, else UTF-8) or one of the Python codec names the
  // picker offers: 'utf-8', 'utf-16', 'cp1252', 'latin-1'. Returns the text and the
  // encoding to record in provenance: the explicit choice, or the sniffed BOM
  // ('utf-8-sig' / 'utf-16' / 'utf-32'), or null for plain UTF-8 (the default shape).
  function sniffBomEncoding(b) {
    if (b.length >= 4 && b[0] === 0xFF && b[1] === 0xFE && b[2] === 0 && b[3] === 0) return 'utf-32';
    if (b.length >= 4 && b[0] === 0 && b[1] === 0 && b[2] === 0xFE && b[3] === 0xFF) return 'utf-32';
    if (b.length >= 3 && b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF) return 'utf-8-sig';
    if (b.length >= 2 && ((b[0] === 0xFF && b[1] === 0xFE) || (b[0] === 0xFE && b[1] === 0xFF))) return 'utf-16';
    return null;
  }

  function decodeText(buffer, choice) {
    var bytes = new Uint8Array(buffer), explicit = choice && choice !== 'auto' ? choice : null;
    var enc = explicit || sniffBomEncoding(bytes) || 'utf-8';
    var text, i;
    if (enc === 'utf-8' || enc === 'utf-8-sig') {
      text = new TextDecoder('utf-8').decode(bytes);                 // drops a leading BOM
    } else if (enc === 'utf-16') {
      var be = bytes.length >= 2 && bytes[0] === 0xFE && bytes[1] === 0xFF;
      text = new TextDecoder(be ? 'utf-16be' : 'utf-16le').decode(bytes);
    } else if (enc === 'utf-32') {
      var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength - (bytes.byteLength % 4));
      var littleEndian = !(bytes.length >= 4 && bytes[0] === 0 && bytes[1] === 0 && bytes[2] === 0xFE && bytes[3] === 0xFF);
      var parts = [];
      for (i = 0; i + 4 <= view.byteLength; i += 4) {
        var cp = view.getUint32(i, littleEndian);
        if (i === 0 && cp === 0xFEFF) continue;
        parts.push(String.fromCodePoint(cp > 0x10FFFF ? 0xFFFD : cp));
      }
      text = parts.join('');
    } else if (enc === 'cp1252') {
      text = new TextDecoder('windows-1252').decode(bytes);
    } else if (enc === 'latin-1') {
      var chunks = [];
      for (i = 0; i < bytes.length; i += 8192) {
        chunks.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 8192)));
      }
      text = chunks.join('');
    } else {
      throw new Error('unsupported encoding ' + enc);
    }
    return { text: text, encoding: explicit || (enc === 'utf-8' ? null : enc) };
  }

  // Comparison / drift (SPEC section 8)
  var PSI_EPSILON = 0.0001;
  var MISSING_DRIFT_FLAG = 0.05;
  var PSI_MODERATE = 0.10;
  var PSI_SIGNIFICANT = 0.25;
  var SCORE_DROP_FLAG = 5;

  // Pandas' default na_values (pandas.io.parsers.readers.STR_NA_VALUES),
  // matched EXACTLY and case-sensitively so JS null-handling is bit-for-bit
  // identical to loaders.py's plain pd.read_csv(). Notably: "None" IS in this
  // set (pandas treats it as missing), while bare lowercase "na" and "none"
  // are NOT - the previous list had both backwards, and lower-cased the cell
  // before comparing, which also erased pandas' own case-sensitivity
  // ("NA" is missing, "na" is not). See #491.
  var NA_TOKENS = {
    '': 1,
    '#N/A': 1, '#N/A N/A': 1, '#NA': 1,
    '-1.#IND': 1, '-1.#QNAN': 1, '-NaN': 1, '-nan': 1,
    '1.#IND': 1, '1.#QNAN': 1, '<NA>': 1,
    'N/A': 1, 'NA': 1, 'NULL': 1, 'NaN': 1, 'None': 1,
    'n/a': 1, 'nan': 1, 'null': 1,
  };

  // ── Keyword lists - MUST mirror faircode/detect.py ─────────────────────
  var KEYWORDS = [
    ['sex', ['sex', 'gender',
             'sexo', 'genero', 'geschlecht', 'sexe', 'sesso', 'geslacht']],
    ['race', ['race', 'ethnic', 'ethnicity',
              'raza', 'etnia', 'rasse', 'ethnie', 'raca', 'razza', 'etnie', 'ras']],
    ['age', ['age', 'dob', 'yob', 'birth',
             'edad', 'nacimiento', 'alter', 'geburt', 'idade', 'nascimento', 'naissance',
             'eta', 'nascita', 'leeftijd', 'geboorte']],
    ['geography', ['region', 'state', 'zip', 'zipcode', 'postal', 'country',
                   'county', 'city', 'location', 'province',
                   'estado', 'pais', 'provincia', 'ciudad', 'bundesland', 'land', 'stadt',
                   'plz', 'ville', 'pays', 'departement', 'cidade', 'regiao', 'municipio',
                   'regione', 'paese', 'citta', 'comune', 'stad', 'gemeente', 'provincie']]
  ];

  var DATE_RE = /[0-9]{1,4}[/-][0-9]{1,2}[/-][0-9]{1,4}/;

  // Appended to `flags` when nothing was recognised by name (#847); must mirror
  // faircode/profiler.py's NO_KIND_DETECTED_FLAG.
  var NO_KIND_DETECTED_FLAG =
    'No column name matched sex, race, age or geography, so every dimension is a plain ' +
    'categorical (ages are not banded, geography is not recognised). If a column is one of ' +
    'these, map it by hand: --map COL=KIND, or the column-mapping control on the web.';

  // ── Delimiter sniffing (SPEC-adjacent; mirrors faircode/loaders.py) ─────
  // Picks whichever of , \t ; | appears the same number of times on every
  // sampled logical row - so quoted newlines do not corrupt the sample.
  var DELIMITER_CANDIDATES = [',', '\t', ';', '|'];

  function logicalRowDelimiterCounts(text, delimiter) {
    var counts = [], count = 0, inQuotes = false;
    var atFieldStart = true, hasContent = false;
    for (var i = 0; i < text.length && counts.length < 5; i++) {
      var c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') i++;
          else inQuotes = false;
        }
      } else if (c === '"' && atFieldStart) {
        inQuotes = true;
        hasContent = true;
      } else if (c === delimiter) {
        count++;
        atFieldStart = true;
        hasContent = true;
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        if (hasContent) counts.push(count);
        count = 0;
        atFieldStart = true;
        hasContent = false;
      } else {
        atFieldStart = false;
        hasContent = true;
      }
    }
    if (counts.length < 5 && hasContent && !inQuotes) counts.push(count);
    return counts;
  }

  function sniffDelimiter(text) {
    var sample = text.slice(0, 8192);
    if (!sample) return ',';
    var best = ',', bestCount = -1;
    DELIMITER_CANDIDATES.forEach(function (d) {
      var counts = logicalRowDelimiterCounts(sample, d);
      if (!counts.length) return;
      var first = counts[0];
      if (first <= 0) return;
      var consistent = counts.every(function (c) { return c === first; });
      if (consistent && first > bestCount) { bestCount = first; best = d; }
    });
    return best;
  }

  // ── CSV/TSV parsing ──────────────────────────────────────────────────────
  // Handles quoted fields, escaped quotes (""), and newlines inside quotes.
  // pandas renames a repeated header to name.1, name.2, ... (skipping any name
  // already taken); without this the second copy overwrote the first in every
  // row object and both dimensions read the LAST column's values (#834).
  function dedupeHeaders(columns) {
    var used = Object.create(null), seen = Object.create(null);
    columns.forEach(function (c) { used[c] = (used[c] || 0) + 1; });
    var taken = Object.create(null);
    return columns.map(function (c) {
      if (!taken[c]) { taken[c] = true; return c; }
      var n = (seen[c] || 0) + 1, candidate = c + '.' + n;
      while (used[candidate] || taken[candidate]) { n++; candidate = c + '.' + n; }
      seen[c] = n;
      taken[candidate] = true;
      return candidate;
    });
  }

  function parseCSV(text, delimiter) {
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); // strip BOM
    delimiter = delimiter || sniffDelimiter(text);
    var rows = [], field = '', row = [], inQuotes = false;
    // A row made of one quoted empty field ("") is a real missing value to
    // pandas, not a blank line to skip (#835).
    var rowQuoted = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += c;
      } else if (c === '"' && field === '') {
        inQuotes = true;
        rowQuoted = true;
      } else if (c === delimiter) {
        row.push(field); field = '';
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = '';
        if (row.length > 1 || row[0] !== '' || rowQuoted) rows.push(row);
        row = [];
        rowQuoted = false;
      } else field += c;
    }
    if (field !== '' || row.length || rowQuoted) { row.push(field); rows.push(row); }
    if (!rows.length) return { columns: [], rows: [] };

    var columns = dedupeHeaders(rows[0]);
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
    // Case-sensitive and whitespace-sensitive, matching pandas' STR_NA_VALUES
    // exactly: no lower-casing, and no trimming - " NA " (with surrounding
    // spaces) is a literal, non-missing value to pandas, not the token "NA".
    return NA_TOKENS.hasOwnProperty(String(v));
  }

  // ── Column detection (SPEC section 1) ──────────────────────────────────
  function tokens(name) {
    // Accent-stripped like detect.py's _tokens (NFD, then drop U+0300-U+036F).
    var stripped = String(name).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    var spaced = stripped.replace(/([a-z0-9])([A-Z])/g, '$1 $2');
    return spaced.split(/[^A-Za-z0-9]+/).filter(Boolean).map(function (t) {
      return t.toLowerCase();
    });
  }

  // Keywords whose prefix form collides with ordinary English words - see
  // faircode/detect.py's EXACT_ONLY_KEYWORDS, must mirror it exactly.
  var EXACT_ONLY_KEYWORDS = {
    race: 1, state: 1, city: 1, region: 1, country: 1,
    genero: 1, alter: 1, land: 1, raza: 1, raca: 1, rasse: 1, pais: 1, pays: 1, estado: 1,
    ville: 1, stadt: 1, razza: 1, paese: 1, citta: 1, stad: 1, ras: 1, eta: 1
  };

  // Validate and normalise the user's extra detection vocabulary; mirrors
  // faircode/detect.py normalize_keywords (#856). Returns null when empty.
  var KEYWORD_KINDS = ['sex', 'race', 'age', 'geography'];
  function normalizeKeywords(raw) {
    if (raw === null || raw === undefined) return null;
    if (typeof raw !== 'object' || Array.isArray(raw)) {
      throw new Error('keywords must be an object mapping a kind to a list of words');
    }
    var allowed = KEYWORD_KINDS.concat(['exact_only']);
    var given = Object.keys(raw);
    if (!given.length) return null;
    var unknown = given.filter(function (k) { return allowed.indexOf(k) === -1; });
    if (unknown.length) {
      throw new Error('keywords has unknown key(s): ' + unknown.join(', ') + '; allowed: ' + allowed.join(', '));
    }
    var out = {};
    allowed.forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(raw, key)) return;
      var words = raw[key];
      if (!Array.isArray(words)) throw new Error('keywords.' + key + ' must be a list of words');
      var normalised = [];
      words.forEach(function (word) {
        if (typeof word !== 'string' || !word.trim()) {
          throw new Error('keywords.' + key + ' entries must be non-empty strings');
        }
        var text = word.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
        if (!/^[a-z0-9]+$/.test(text)) {
          throw new Error('keywords.' + key + ' entry ' + JSON.stringify(word) + ' must be a single word of letters and digits');
        }
        if (normalised.indexOf(text) === -1) normalised.push(text);
      });
      out[key] = normalised;
    });
    return Object.keys(out).length ? out : null;
  }

  function tokenMatches(token, keyword, extraExact) {
    if (keyword.length < 4 || EXACT_ONLY_KEYWORDS.hasOwnProperty(keyword) ||
        (extraExact && extraExact.indexOf(keyword) !== -1)) return token === keyword;
    return token.indexOf(keyword) === 0; // prefix match
  }

  // Compound marital-status phrases that contain a geography stem (estado)
  // but are not geography - must mirror faircode/detect.py NON_GEOGRAPHY_PHRASES (#855).
  var NON_GEOGRAPHY_PHRASES = [
    ['estado', 'civil'],
    ['marital', 'status'],
    ['stato', 'civile'],
    ['etat', 'civil']
  ];

  function hasConsecutivePhrase(toks, phrase) {
    var n = phrase.length;
    if (n === 0 || toks.length < n) return false;
    for (var i = 0; i <= toks.length - n; i++) {
      var match = true;
      for (var j = 0; j < n; j++) {
        if (toks[i + j] !== phrase[j]) { match = false; break; }
      }
      if (match) return true;
    }
    return false;
  }

  function classifyName(name, keywords) {
    keywords = normalizeKeywords(keywords);
    var extra = keywords || {}, extraExact = extra.exact_only || [];
    var toks = tokens(name);
    for (var p = 0; p < NON_GEOGRAPHY_PHRASES.length; p++) {
      if (hasConsecutivePhrase(toks, NON_GEOGRAPHY_PHRASES[p])) return null;
    }
    for (var k = 0; k < KEYWORDS.length; k++) {
      var kind = KEYWORDS[k][0], words = KEYWORDS[k][1].concat(extra[KEYWORDS[k][0]] || []);
      for (var t = 0; t < toks.length; t++) {
        for (var w = 0; w < words.length; w++) {
          if (tokenMatches(toks[t], words[w], extraExact)) return kind;
        }
      }
    }
    return null;
  }

  function nunique(rows, col) {
    var seen = Object.create(null);
    for (var i = 0; i < rows.length; i++) {
      var v = rows[i][col];
      if (v !== null) seen[v] = 1;
    }
    return Object.keys(seen).length;
  }

  function detectColumns(table, overrides, maxCategoricalCard, keywords) {
    keywords = normalizeKeywords(keywords);
    overrides = overrides || {};
    if (maxCategoricalCard === null || maxCategoricalCard === undefined) {
      maxCategoricalCard = MAX_CATEGORICAL_CARD;
    }
    var detected = [];
    table.columns.forEach(function (col) {
      if (Object.prototype.hasOwnProperty.call(overrides, col)) {
        var forced = overrides[col];
        if (VALID_KINDS[forced]) detected.push({ name: col, kind: forced });
        return; // any other value (e.g. 'ignore') excludes the column
      }
      var kind = classifyName(col, keywords);
      if (kind !== null) { detected.push({ name: col, kind: kind }); return; }
      var n = nunique(table.rows, col);
      if (n >= 2 && n <= maxCategoricalCard) {
        detected.push({ name: col, kind: 'categorical' });
      }
    });
    return detected;
  }

  // ── Age handling (SPEC section 2) ──────────────────────────────────────
  // Match the numeric grammar used by pandas when it infers an otherwise
  // numeric age column, including scientific notation. Non-finite numeric
  // tokens (inf/nan) are treated as missing rather than categorical values.
  var AGE_NUMERIC_RE = /[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/;
  var AGE_NONFINITE_RE = /^[+-]?(?:inf(?:inity)?|nan)$/i;

  function rawAgeToNumeric(value) {
    if (value === null || value === undefined) return null;
    var numeric;
    if (typeof value === 'number') numeric = value;
    else {
      var text = String(value);
      var m = text.match(AGE_NUMERIC_RE);
      if (!m) return null;
      numeric = parseFloat(m[0]);
    }
    return Number.isFinite(numeric) ? numeric : null;
  }

  function ageToNumeric(value) {
    var numeric = rawAgeToNumeric(value);
    return numeric !== null && numeric >= AGE_BANDS[0] ? numeric : null;
  }

  // Mirrors faircode.profiler._age_numbers (#840, #863): per-cell numeric ages with those
  // above maxAge or negative removed (null), plus how many there were and if any were negative.
  function ageNumbers(rows, name, maxAge, referenceYear) {
    var nums = [], implausible = 0, hasNegative = false;
    for (var i = 0; i < rows.length; i++) {
      var n = rawAgeToNumeric(rows[i][name]);
      // A whole number from 1900 up to referenceYear is a birth year (#862).
      if (referenceYear !== null && referenceYear !== undefined && n !== null &&
          n >= BIRTH_YEAR_MIN && n <= referenceYear && n === Math.floor(n)) {
        n = referenceYear - n;
      }
      if (n !== null && (n < AGE_BANDS[0] || n > maxAge)) {
        implausible++;
        if (n < AGE_BANDS[0]) hasNegative = true;
        n = null;
      }
      nums.push(n);
    }
    return { nums: nums, implausible: implausible, hasNegative: hasNegative };
  }

  function ageBand(num) {
    if (num === null || !Number.isFinite(num) || num < AGE_BANDS[0]) return null;
    for (var i = 0; i < AGE_BANDS.length - 1; i++) {
      if (num >= AGE_BANDS[i] && num < AGE_BANDS[i + 1]) {
        return AGE_BANDS[i] + '-' + AGE_BANDS[i + 1];
      }
    }
    return AGE_BANDS[AGE_BANDS.length - 1] + '+';
  }

  // True only for free text with no embedded number at all (e.g. "unknown",
  // "prefer not to say") - SPEC.md section 2's "anything else: treat as
  // categorical" rule for a per-value age rule. False for null/undefined
  // and for any numeric value, including one embedded in a string - even a
  // number outside the valid age range, like a -1/999 sentinel, still
  // counts as "has a number" here and is routed to missing/null, matching
  // this profiler's prior behavior for range-invalid numeric sentinels.
  function isCategoricalAgeSentinel(value) {
    if (value === null || value === undefined || typeof value === 'number') return false;
    var text = String(value).trim();
    if (AGE_NONFINITE_RE.test(text)) return false;
    return !AGE_NUMERIC_RE.test(text);
  }

  var AGE_BAND_LABELS = Object.create(null);
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
    var values = [], sample = [], i;
    for (i = 0; i < rows.length; i++) {
      if (rows[i][col] !== null && rows[i][col] !== undefined) {
        values.push(String(rows[i][col]));
      }
    }
    if (!values.length) return false;
    if (values.length <= DATE_SAMPLE_SIZE) {
      sample = values;
    } else {
      for (i = 0; i < DATE_SAMPLE_SIZE; i++) {
        sample.push(values[Math.floor(i * (values.length - 1) / (DATE_SAMPLE_SIZE - 1))]);
      }
    }
    var hits = 0;
    for (i = 0; i < sample.length; i++) if (DATE_RE.test(sample[i])) hits++;
    return hits / sample.length >= 0.5;
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

  function dimension(table, name, kind, minShareThreshold, minGroupSize, maxAge, referenceYear) {
    var rows = table.rows, nTotal = rows.length, i, v;
    if (maxAge === undefined) maxAge = MAX_AGE;

    if (kind === 'age' && !looksLikeDates(rows, name)) {
      var parsedAges = ageNumbers(rows, name, maxAge, referenceYear);
      var nums = parsedAges.nums, numericVals = [];
      for (i = 0; i < nTotal; i++) {
        if (nums[i] !== null) numericVals.push(nums[i]);
      }
      if (numericVals.length || parsedAges.implausible) {
        var skew = numericVals.length ? skewness(numericVals) : null;
        var counts = Object.create(null), nullCount = 0;
        for (i = 0; i < nums.length; i++) {
          var b = ageBand(nums[i]);
          if (b !== null) {
            counts[b] = (counts[b] || 0) + 1;
          } else if (isCategoricalAgeSentinel(rows[i][name])) {
            // Non-numeric free text (e.g. "unknown", "prefer not to say") -
            // SPEC.md section 2's "anything else: treat as categorical"
            // rule. Distinct from a genuinely missing cell or an
            // out-of-range numeric sentinel (both still go to nullCount
            // below): gets its own group instead of silently folding into
            // missing_pct.
            var label = String(rows[i][name]).trim();
            counts[label] = (counts[label] || 0) + 1;
          } else {
            nullCount++;
          }
        }
        var res = analyzeGroups(counts, nTotal, nullCount, skew, minShareThreshold, minGroupSize);
        res.name = name; res.kind = kind;
        if (parsedAges.implausible) {
          res.implausible_values = parsedAges.implausible;
          if (parsedAges.hasNegative) res.has_negative_ages = true;
        }
        return res;
      }
    }

    // Categorical path.
    // Raw category labels may name Object.prototype properties. Keep them
    // as literal keys, matching Python's value_counts().
    var c = Object.create(null), nulls = 0;
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
  function labelize(table, name, kind, maxAge, referenceYear) {
    var rows = table.rows, out = [], i;
    if (maxAge === undefined) maxAge = MAX_AGE;
    if (kind === 'age' && !looksLikeDates(rows, name)) {
      var parsedAges = ageNumbers(rows, name, maxAge, referenceYear);
      var any = parsedAges.implausible > 0;
      for (i = 0; i < rows.length && !any; i++) {
        if (parsedAges.nums[i] !== null) any = true;
      }
      if (any) {
        for (i = 0; i < rows.length; i++) {
          var value = rows[i][name];
          var num = parsedAges.nums[i];
          // Non-numeric age sentinels get their own categorical label here
          // too, matching dimension()'s main breakdown - otherwise they map
          // to null and intersections() drops those rows, so the crosstab
          // and the main groups disagree (#524).
          out.push(num !== null ? ageBand(num)
                   : (isCategoricalAgeSentinel(value) ? String(value) : null));
        }
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

  function intersections(table, dims, intersectionFloor, cross, maxAge, referenceYear) {
    if (dims.length < 2) return [];
    if (intersectionFloor === undefined) intersectionFloor = INTERSECTION_FLOOR;
    var pair = pickCross(dims, cross), a = pair[0], b = pair[1];
    var nTotal = table.rows.length;
    var floor = intersectionFloor * nTotal;
    var la = labelize(table, a.name, a.kind, maxAge, referenceYear);
    var lb = labelize(table, b.name, b.kind, maxAge, referenceYear);

    var ct = Object.create(null), aVals = Object.create(null), bVals = Object.create(null), i, key;
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

  // ── Proxy-hint detection (issue #738) ──────────────────────────────────
  // Chi-squared test of independence over every pair of detected dimensions,
  // flagging pairs strongly associated with each other - "this column may be
  // a proxy for that protected attribute" - the same informational check the
  // CLI's `--proxy-hints` runs via faircode/proxy.py's proxy_hints(). This is
  // NOT part of profile()/compare(): it is opt-in, never touches the score,
  // and is not covered by the bit-for-bit parity test between this engine
  // and faircode/profiler.py - it just needs to exist and be reasonable, so
  // it reuses the same labelize() this engine already has for intersections.
  var PROXY_ALPHA = 0.05;

  // Regularized incomplete gamma functions (Numerical Recipes gammp/gammq),
  // used below to get a chi-squared p-value without scipy - there is no
  // other chi-squared CDF anywhere in this file.
  function logGamma(x) {
    var cof = [76.18009172947146, -86.50532032941677, 24.01409824083091,
               -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    var y = x, tmp = x + 5.5, ser = 1.000000000190015, j;
    tmp -= (x + 0.5) * Math.log(tmp);
    for (j = 0; j < 6; j++) { y += 1; ser += cof[j] / y; }
    return -tmp + Math.log(2.5066282746310005 * ser / x);
  }

  function gammaSeriesP(a, x) {
    var ITMAX = 100, EPS = 3e-7, ap = a, sum = 1 / a, del = sum, n;
    for (n = 1; n <= ITMAX; n++) {
      ap += 1;
      del *= x / ap;
      sum += del;
      if (Math.abs(del) < Math.abs(sum) * EPS) break;
    }
    return sum * Math.exp(-x + a * Math.log(x) - logGamma(a));
  }

  function gammaContinuedFractionQ(a, x) {
    var ITMAX = 100, EPS = 3e-7, FPMIN = 1e-30;
    var b = x + 1 - a, c = 1 / FPMIN, d = 1 / b, h = d, i, an, delta;
    for (i = 1; i <= ITMAX; i++) {
      an = -i * (i - a);
      b += 2;
      d = an * d + b;
      if (Math.abs(d) < FPMIN) d = FPMIN;
      c = b + an / c;
      if (Math.abs(c) < FPMIN) c = FPMIN;
      d = 1 / d;
      delta = d * c;
      h *= delta;
      if (Math.abs(delta - 1) < EPS) break;
    }
    return Math.exp(-x + a * Math.log(x) - logGamma(a)) * h;
  }

  function regularizedGammaQ(a, x) {
    if (x < 0 || a <= 0) return NaN;
    if (x === 0) return 1;
    return x < a + 1 ? 1 - gammaSeriesP(a, x) : gammaContinuedFractionQ(a, x);
  }

  function chiSquarePValue(chi2, dof) {
    if (chi2 <= 0 || dof <= 0) return 1;
    return regularizedGammaQ(dof / 2, chi2 / 2);
  }

  // Held-out columns (#781): {name: valuesArray} for a protected attribute
  // already dropped from `table` - the browser counterpart of the CLI's
  // --proxy-hints-with PATH=COLUMN, treated as plain categorical values.
  // parseHeldOut() applies the same checks as proxy.py's parse_held_out_specs,
  // including the optional join `key` (#822): rows are matched on that column
  // instead of by position.
  // The column names a join key refers to: the key itself when it is a column, else the
  // `+`-separated parts of a composite key when all are columns, else null. Mirrors
  // faircode/proxy.py key_columns (#859).
  function keyColumns(key, columns) {
    if (columns.indexOf(key) !== -1) return [key];
    var parts = key.split('+');
    if (parts.length > 1 && parts.every(function (p) { return p && columns.indexOf(p) !== -1; })) return parts;
    return null;
  }

  // Opt-in key normalisation: trim, lower-case, drop leading zeros of an all-digit value.
  // Mirrors proxy.py normalize_key_text (#859).
  function normalizeKeyText(value) {
    var text = String(value).trim().toLowerCase();
    if (/^[0-9]+$/.test(text)) text = text.replace(/^0+/, '') || '0';
    return text;
  }

  function parseHeldOut(heldTable, column, table, already, key, normalize) {
    if (!column) throw new Error('held-out column name is required');
    if (heldTable.columns.indexOf(column) === -1) {
      throw new Error("held-out column '" + column + "' not found in the held-out file");
    }
    if (table.columns.indexOf(column) !== -1) {
      throw new Error("held-out column '" + column + "' already exists in the profiled " +
        'dataset - held-out columns must not collide with a real one');
    }
    if (already && Object.prototype.hasOwnProperty.call(already, column)) {
      throw new Error("held-out column '" + column + "' was already supplied");
    }
    if (key) {
      var keyCols = keyColumns(key, table.columns);
      if (keyCols === null) {
        throw new Error("join key '" + key + "' not found in the profiled dataset");
      }
      if (!keyCols.every(function (c) { return heldTable.columns.indexOf(c) !== -1; })) {
        throw new Error("join key '" + key + "' not found in the held-out file");
      }
      var keyLabels = function (rows, what) {
        var seen = Object.create(null), labels = rows.map(function (r) {
          var v = keyCols.map(function (c) {
            var cell = r[c];
            if (cell === null || cell === undefined) {
              throw new Error('join key ' + what + ' has empty values - keys must all be present');
            }
            return normalize ? normalizeKeyText(cell) : String(cell);
          }).join('\u001f');
          if (seen[v]) throw new Error('join key ' + what + " has duplicate values (e.g. '" + v + "') - keys must be unique");
          seen[v] = 1;
          return v;
        });
        return labels;
      };
      var dfKeys = keyLabels(table.rows, "'" + key + "' in the profiled dataset");
      var heldKeys = keyLabels(heldTable.rows, "'" + key + "' in the held-out file");
      var lookup = Object.create(null);
      heldKeys.forEach(function (k, i) { lookup[k] = heldTable.rows[i][column]; });
      var missing = dfKeys.filter(function (k) { return !(k in lookup); });
      if (missing.length) {
        throw new Error('held-out file has no row for ' + missing.length + " key(s) of the profiled dataset (e.g. '" +
          missing[0] + "')");
      }
      return dfKeys.map(function (k) { return lookup[k]; });
    }
    if (heldTable.rows.length !== table.rows.length) {
      throw new Error('held-out file has ' + heldTable.rows.length + ' row(s), but the profiled ' +
        'dataset has ' + table.rows.length + ' - rows must align 1:1 (or add a join key)');
    }
    return heldTable.rows.map(function (r) { return r[column]; });
  }

  // Mirrors faircode/proxy.py adjust_p_values (#806): bonferroni = min(1, p*m);
  // holm = step-down with a running max, capped at 1. Returned in input order.
  function adjustPValues(ps, method) {
    var m = ps.length, i;
    if (method === 'bonferroni') return ps.map(function (p) { return Math.min(1, p * m); });
    if (method === 'holm') {
      var order = ps.map(function (_, idx) { return idx; })
        .sort(function (a, b) { return ps[a] - ps[b] || a - b; });
      var out = new Array(m), running = 0;
      for (i = 0; i < m; i++) {
        running = Math.max(running, Math.min(1, ps[order[i]] * (m - i)));
        out[order[i]] = running;
      }
      return out;
    }
    throw new Error("correction must be 'bonferroni' or 'holm', got " + method);
  }

  // Build a held-out map from several uploaded files (#801, #802, #803).
  // specs = [{name, column, key?, data}] where `data` is text (csv/tsv/json) or an
  // ArrayBuffer (.xlsx, first sheet - the same reader the main dropzone uses).
  // Every spec goes through parseHeldOut, with the running map as `already`,
  // so two specs naming the same column are rejected like the CLI's repeated
  // --proxy-hints-with.
  //
  // Only an .xlsx workbook's first sheet is read (#816). When `notes` (an array)
  // is passed, a note is pushed for every workbook with other sheets, like the
  // CLI's per-held-out-file "other sheet(s) ignored" line; and if the requested
  // column is missing from such a workbook, the error says which sheets were skipped.
  async function buildHeldOut(specs, table, notes) {
    var out = {};
    for (var i = 0; i < specs.length; i++) {
      var spec = specs[i], heldTable, sheetNote = null;
      if (/\.xlsx$/i.test(spec.name)) {
        var sheets = await parseXLSX(spec.data);
        heldTable = sheets.table;
        if (sheets.ignoredSheets.length > 0) {
          sheetNote = spec.name + ": only the first sheet '" + sheets.sheetName + "' was read; " +
            sheets.ignoredSheets.map(function (n) { return "'" + n + "'"; }).join(', ') +
            ' ignored';
          if (notes) notes.push(sheetNote);
        }
      }
      else if (/\.json$/i.test(spec.name)) heldTable = parseJSON(spec.data);
      else heldTable = parseCSV(spec.data);
      try {
        out[spec.column] = parseHeldOut(heldTable, spec.column, table, out, spec.key, spec.normalize);
      } catch (err) {
        if (sheetNote && heldTable.columns.indexOf(spec.column) === -1) {
          err.message += ' (' + sheetNote + ')';
        }
        throw err;
      }
    }
    return out;
  }

  // faircode/proxy.py LOW_EXPECTED_COUNT / LOW_EXPECTED_SHARE (#810): a table is
  // `low_expected` when over 20% of its cells expect fewer than 5 rows, which
  // makes the chi-squared p-value unreliable. Must mirror proxy.py.
  var LOW_EXPECTED_COUNT = 5, LOW_EXPECTED_SHARE = 0.2;

  // Exact-test fallback for small-cell tables (#861); mirrors faircode/proxy.py
  // (PERMUTATIONS, PERMUTATION_SEED, PERMUTATION_MAX_ROWS, _mulberry32).
  var PERMUTATIONS = 1000, PERMUTATION_SEED = 42, PERMUTATION_MAX_ROWS = 5000;

  function mulberry32(seed) {
    var a = seed | 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Two-sided Fisher exact p for [[a, b], [c, d]], matching scipy.stats.fisher_exact:
  // the sum of every table probability not above the observed one (relative 1e-7).
  function fisherExact2x2(a, b, c, d) {
    var n1 = a + b, m1 = a + c, n = a + b + c + d;
    var logFact = [0], i;
    for (i = 1; i <= n; i++) logFact.push(logFact[i - 1] + Math.log(i));
    function logChoose(nn, kk) { return logFact[nn] - logFact[kk] - logFact[nn - kk]; }
    function pmf(x) { return Math.exp(logChoose(m1, x) + logChoose(n - m1, n1 - x) - logChoose(n, n1)); }
    var lo = Math.max(0, n1 - (n - m1)), hi = Math.min(n1, m1);
    var pObs = pmf(a), p = 0;
    for (var x = lo; x <= hi; x++) {
      var px = pmf(x);
      if (px <= pObs * (1 + 1e-7)) p += px;
    }
    return Math.min(1, p);
  }

  function permutationPValue(rowIdx, colIdx, nRows, nCols) {
    var n = rowIdx.length, rowTot = [], colTot = [], i, r, c;
    for (r = 0; r < nRows; r++) rowTot.push(0);
    for (c = 0; c < nCols; c++) colTot.push(0);
    for (i = 0; i < n; i++) { rowTot[rowIdx[i]]++; colTot[colIdx[i]]++; }
    var expected = [];
    for (r = 0; r < nRows; r++) for (c = 0; c < nCols; c++) expected.push(rowTot[r] * colTot[c] / n);
    function statistic(cols) {
      var counts = [], k, s = 0;
      for (k = 0; k < nRows * nCols; k++) counts.push(0);
      for (k = 0; k < n; k++) counts[rowIdx[k] * nCols + cols[k]]++;
      for (k = 0; k < counts.length; k++) s += (counts[k] - expected[k]) * (counts[k] - expected[k]) / expected[k];
      return s;
    }
    var observed = statistic(colIdx), rand = mulberry32(PERMUTATION_SEED), cols = colIdx.slice(), hits = 0;
    for (var b = 0; b < PERMUTATIONS; b++) {
      for (i = n - 1; i > 0; i--) {
        var j = Math.floor(rand() * (i + 1)), tmp = cols[i];
        cols[i] = cols[j]; cols[j] = tmp;
      }
      if (statistic(cols) >= observed - 1e-9) hits++;
    }
    return (1 + hits) / (PERMUTATIONS + 1);
  }

  // Suffix for a hint's text line, mirroring report.py's _hint_notes() minus the
  // adjusted p-value (each renderer formats that itself).
  function proxyNotes(h) {
    if (!h.low_expected) return '';
    return (h.p_method === 'fisher' || h.p_method === 'permutation')
      ? ', small cells (' + h.p_method + ' exact p)' : ', small cells (p-value unreliable)';
  }

  // " (m=N pairs)" - the family size an adjusted p was computed over (#821).
  function proxyFamily(h) {
    return h.p_adjusted !== undefined && h.n_tests !== undefined ? ' (m=' + h.n_tests + ' pairs)' : '';
  }

  function proxyHints(table, dimensions, alpha, heldOut, multiCorrection, maxAge, referenceYear, exact) {
    if (alpha === undefined) alpha = PROXY_ALPHA;
    if (!(alpha > 0 && alpha <= 1)) throw new Error('alpha must be in (0, 1], got ' + alpha);
    if (multiCorrection) adjustPValues([], multiCorrection); // validates the method name
    var labelized = {}, i, j, k;
    dimensions.forEach(function (d) { labelized[d.name] = labelize(table, d.name, d.kind, maxAge, referenceYear); });
    Object.keys(heldOut || {}).forEach(function (name) { labelized[name] = heldOut[name]; });
    var names = Object.keys(labelized);
    var nTotal = table.rows.length;
    var hints = [], tested = [];

    for (i = 0; i < names.length; i++) {
      for (j = i + 1; j < names.length; j++) {
        var nameA = names[i], nameB = names[j];
        var la = labelized[nameA], lb = labelized[nameB];

        var ct = Object.create(null), aVals = Object.create(null), bVals = Object.create(null);
        for (k = 0; k < nTotal; k++) {
          if (la[k] === null || lb[k] === null) continue;
          aVals[la[k]] = 1; bVals[lb[k]] = 1;
          var key = la[k] + '\0' + lb[k];
          ct[key] = (ct[key] || 0) + 1;
        }
        var aKeys = Object.keys(aVals), bKeys = Object.keys(bVals);
        if (aKeys.length < 2 || bKeys.length < 2) continue;

        var rowTotals = {}, colTotals = {}, n = 0;
        aKeys.forEach(function (av) { rowTotals[av] = 0; });
        bKeys.forEach(function (bv) { colTotals[bv] = 0; });
        aKeys.forEach(function (av) {
          bKeys.forEach(function (bv) {
            var count = ct[av + '\0' + bv] || 0;
            rowTotals[av] += count;
            colTotals[bv] += count;
            n += count;
          });
        });
        if (!n) continue;

        // scipy.stats.chi2_contingency's default correction=True: Yates'
        // continuity correction applies only when dof === 1 (a 2x2 table).
        var dof = (aKeys.length - 1) * (bKeys.length - 1);
        var correction = dof === 1;
        var chi2 = 0, lowCells = 0;
        aKeys.forEach(function (av) {
          bKeys.forEach(function (bv) {
            var observed = ct[av + '\0' + bv] || 0;
            var expected = (rowTotals[av] * colTotals[bv]) / n;
            if (expected < LOW_EXPECTED_COUNT) lowCells++;
            if (!expected) return;
            var diff = Math.abs(observed - expected);
            if (correction) diff = Math.max(0, diff - 0.5);
            chi2 += (diff * diff) / expected;
          });
        });

        var pValue = chiSquarePValue(chi2, dof);
        var kMinusOne = Math.min(aKeys.length, bKeys.length) - 1;
        var cramersV = (n && kMinusOne) ? Math.sqrt(chi2 / (n * kMinusOne)) : 0;
        var lowShare = lowCells / (aKeys.length * bKeys.length);
        var hint = {
          a: nameA, b: nameB,
          p_value: pValue,
          cramers_v: Math.round(cramersV * 10000) / 10000,
          chi2: Math.round(chi2 * 100) / 100,
          low_expected_share: Math.round(lowShare * 10000) / 10000,
          low_expected: lowShare > LOW_EXPECTED_SHARE
        };
        if (exact) {
          hint.p_method = 'chi2';
          if (hint.low_expected) {
            if (aKeys.length === 2 && bKeys.length === 2) {
              var cell = function (av, bv) { return ct[av + '\0' + bv] || 0; };
              hint.p_chi2 = pValue;
              hint.p_value = fisherExact2x2(cell(aKeys[0], bKeys[0]), cell(aKeys[0], bKeys[1]),
                                            cell(aKeys[1], bKeys[0]), cell(aKeys[1], bKeys[1]));
              hint.p_method = 'fisher';
            } else if (n <= PERMUTATION_MAX_ROWS) {
              var aIndex = Object.create(null), bIndex = Object.create(null), rowIdx = [], colIdx = [];
              aKeys.forEach(function (v, vi) { aIndex[v] = vi; });
              bKeys.forEach(function (v, vi) { bIndex[v] = vi; });
              for (k = 0; k < nTotal; k++) {
                if (la[k] === null || lb[k] === null) continue;
                rowIdx.push(aIndex[la[k]]); colIdx.push(bIndex[lb[k]]);
              }
              hint.p_chi2 = pValue;
              hint.p_value = permutationPValue(rowIdx, colIdx, aKeys.length, bKeys.length);
              hint.p_method = 'permutation';
            }
          }
        }
        tested.push(hint);
      }
    }
    tested.forEach(function (h) { h.n_tests = tested.length; });
    if (!multiCorrection) {
      tested.forEach(function (h) { if (h.p_value < alpha) hints.push(h); });
    } else {
      var adjusted = adjustPValues(tested.map(function (h) { return h.p_value; }), multiCorrection);
      tested.forEach(function (h, idx) {
        if (adjusted[idx] < alpha) {
          hints.push(Object.assign({}, h, { p_adjusted: adjusted[idx] }));
        }
      });
    }
    hints.sort(function (x, y) { return x.p_value - y.p_value; });
    return hints;
  }

  // ── CSV cell/row writer shared by every browser export (#790) ──────────
  // Matches faircode/report.py's csv output: booleans as True/False, null as
  // empty, quoting on comma/quote/newline, CRLF row ends, and a single-quote
  // prefix on text a spreadsheet would evaluate as a formula (#791).
  function csvField(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'boolean') return v ? 'True' : 'False';
    var t = String(v);
    if (typeof v === 'string' && /^[=+\-@\t\r]/.test(t)) t = "'" + t;
    return /[",\r\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  }
  function csvRow(cells) { return cells.map(csvField).join(',') + '\r\n'; }

  // Provenance section for CSV exports (#800), mirroring faircode/report.py's
  // _write_provenance_rows: nested objects become dotted keys (params.min_share),
  // arrays become JSON text (Python's ', ' separators), null becomes empty.
  // JSON text formatted like Python's json.dumps() (", " and ": " separators,
  // non-ASCII escaped) so a list of objects - the held-out file entries (#811) -
  // renders identically in the web and CLI provenance CSV.
  function pyJson(v) {
    if (Array.isArray(v)) return '[' + v.map(pyJson).join(', ') + ']';
    if (v !== null && typeof v === 'object') {
      return '{' + Object.keys(v).map(function (k) { return pyJson(k) + ': ' + pyJson(v[k]); }).join(', ') + '}';
    }
    return JSON.stringify(v).replace(/[\u007f-\uffff]/g, function (c) {
      return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    });
  }

  function provenanceCsv(prov) {
    var out = csvRow(['provenance_key', 'provenance_value']);
    (function walk(obj, prefix) {
      Object.keys(obj).forEach(function (k) {
        var v = obj[k], name = prefix + k;
        if (Array.isArray(v)) {
          out += csvRow([name, pyJson(v)]);
        } else if (v !== null && typeof v === 'object') {
          walk(v, name + '.');
        } else {
          out += csvRow([name, v === null || v === undefined ? '' : v]);
        }
      });
    })(prov, '');
    return out;
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
      var actual = Object.create(null);
      d.groups.forEach(function (g) { actual[g.label] = g.share; });
      var labels = Object.create(null);
      Object.keys(actual).forEach(function (l) { labels[l] = 1; });
      Object.keys(ref).forEach(function (l) { labels[l] = 1; });
      var groups = [], deviation = 0;
      Object.keys(labels).forEach(function (label) {
        var exp = Object.prototype.hasOwnProperty.call(ref, label) ? ref[label] : 0;
        var act = actual[label] || 0, delta = act - exp;
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

  function buildFlags(dimensions, inters, imbalanceFlag, missingFlag, maxAge) {
    if (imbalanceFlag === undefined) imbalanceFlag = IMBALANCE_FLAG;
    if (missingFlag === undefined) missingFlag = MISSING_FLAG;
    if (maxAge === undefined) maxAge = MAX_AGE;
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
      if (d.implausible_values) {
        if (d.has_negative_ages) {
          flags.push(d.name + ': ' + d.implausible_values + ' sentinel/implausible age value(s) ' +
                     '(negative or above ' + maxAge + ') were treated as missing, not banded ' +
                     '(a mistyped age, birth year, or sentinel code?)');
        } else {
          flags.push(d.name + ': ' + d.implausible_values + ' implausible age value(s) above ' +
                     maxAge + ' were treated as missing, not banded ' +
                     '(a mistyped age or a birth year?)');
        }
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
    var detected = detectColumns(table, overrides, o.max_categorical_card, o.keywords);
    var dimensions = detected.map(function (d) {
      return dimension(table, d.name, d.kind, o.min_share, o.min_group_size, o.max_age, o.age_reference_year);
    });
    var forced = {};
    Object.keys(overrides).forEach(function (col) {
      if (VALID_KINDS[overrides[col]]) forced[col] = 1;
    });
    dimensions = dimensions.filter(function (d) {
      return d.kind === 'geography' || forced[d.name] || d.n_groups <= o.max_dimension_groups;
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
    var inters = intersections(table, detected, o.intersection_floor, o.cross, o.max_age, o.age_reference_year);

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

    // A dimension with zero observed groups (every value missing, or an empty
    // column) has nothing to measure - unlike a genuine single-group column,
    // which has real, lopsided data. Excluded from the mean so it can't
    // silently drag overall_score down for a column that was never actually
    // measured (see SPEC section 5). Mirrors faircode.profiler.profile.
    var measurable = dimensions.filter(function (d) { return d.n_groups > 0; });
    var overall = null;
    if (measurable.length) {
      var sum = 0;
      measurable.forEach(function (d) { sum += d.dimension_score; });
      overall = Math.round(sum / measurable.length);
    }

    var note;
    if (!dimensions.length) {
      note = 'No demographic columns detected.';
    } else if (!measurable.length) {
      note = 'No dimension had any non-missing values to measure.';
    } else {
      note = null;
    }

    return {
      n_rows: table.rows.length,
      n_cols: table.columns.length,
      overall_score: overall,
      grade: overall === null ? null : grade(overall),
      dimensions_detected: dimensions.length > 0,
      note: note,
      dimensions: dimensions,
      intersections: inters,
      flags: buildFlags(dimensions, inters, o.imbalance_flag, o.missing_flag, o.max_age).concat(refFlags)
        .concat(dimensions.length && !Object.keys(overrides).length &&
                dimensions.every(function (d) { return d.kind === 'categorical'; })
                ? [NO_KIND_DETECTED_FLAG] : [])
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
      var text = String(row[shrC]).trim();
      // A '%' suffix is an explicit, unambiguous scale signal - convert it
      // immediately rather than letting its raw (still-percent) magnitude
      // compete in the per-column heuristic below, where it could otherwise
      // force percent-scale onto a sibling row that was already a plain,
      // correctly-scaled fraction (e.g. "51%" next to "0.49").
      var alreadyScaled = text.endsWith('%');
      if (alreadyScaled) text = text.slice(0, -1).trim();
      // Number() rejects anything with trailing garbage or that isn't a full
      // numeric literal (unlike parseFloat, which parses only a leading
      // prefix - "60abc" -> 60, "1e1junk" -> 10), and rejects '' the same
      // way Python's float('') raises. Mirrors faircode.profiler.parse_reference.
      if (text === '') return;
      var share = Number(text);
      if (isNaN(share)) return;
      raw.push([String(row[colC]).trim(), String(row[grpC]).trim(), share, alreadyScaled]);
    });
    // Percent-vs-fraction scale is decided per column (grouped by the column
    // identifier), not once across the whole table: a reference file that
    // mixes conventions between columns would otherwise get the wrong scale
    // applied to whichever column didn't trigger the heuristic. Mirrors
    // faircode.profiler.parse_reference.
    var byCol = {};
    raw.forEach(function (r) {
      (byCol[r[0]] = byCol[r[0]] || []).push([r[1], r[2], r[3]]);
    });
    var reference = {};
    Object.keys(byCol).forEach(function (col) {
      var triples = byCol[col];
      var unscaled = triples.filter(function (t) { return !t[2]; });
      var scale = unscaled.some(function (t) { return t[1] > 1.5; }) ? 100 : 1;
      reference[col] = Object.create(null);
      triples.forEach(function (t) {
        reference[col][t[0]] = t[2] ? t[1] / 100 : t[1] / scale;
      });
    });
    return reference;
  }

  // ── Dataset comparison / drift (SPEC section 8) ────────────────────────
  function shareMap(dim) {
    var m = Object.create(null);
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
    // missing_pct is computed independently of kind/group classification,
    // so it's comparable even when the group-share PSI comparison below is
    // skipped for a kind mismatch - a column collapsing to mostly-missing
    // is real drift the non-null-share PSI calculation alone can't see (#461).
    var missingA = dimA.missing_pct, missingB = dimB.missing_pct;
    var missingDelta = round(missingB - missingA, 4);

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
        psi: 0, tvd: 0, drift_level: 'none', groups: [],
        missing_pct_a: missingA, missing_pct_b: missingB, missing_pct_delta: missingDelta
      };
    }
    var sa = shareMap(dimA), sb = shareMap(dimB);
    var labels = Object.create(null);
    Object.keys(sa).forEach(function (l) { labels[l] = 1; });
    Object.keys(sb).forEach(function (l) { labels[l] = 1; });

    var groups = [], psiTotal = 0, tvdTotal = 0;
    Object.keys(labels).forEach(function (label) {
      var a = sa[label] || 0, b = sb[label] || 0;
      psiTotal += psiTerm(a, b);
      tvdTotal += Math.abs(b - a);
      var delta = round(b - a, 4);
      var status = (a === 0 && b > 0) ? 'appeared'
                 : (a > 0 && b === 0) ? 'disappeared'
                 : (delta === 0) ? 'unchanged' : 'shifted';
      groups.push({ label: String(label), share_a: round(a, 4),
                    share_b: round(b, 4), share_delta: delta,
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
      // classify on the same rounded value that's displayed, matching
      // faircode/compare.py - see #462.
      drift_level: driftLevel(round(psiTotal, 4)), groups: groups,
      missing_pct_a: missingA, missing_pct_b: missingB, missing_pct_delta: missingDelta
    };
  }

  // Mirrors faircode/compare.py RENAME_MIN_OVERLAP / _possible_renames (#866).
  var RENAME_MIN_OVERLAP = 0.5;

  function possibleRenames(resultA, resultB, removed, added) {
    var byA = {}, byB = {}, taken = {}, pairs = [];
    resultA.dimensions.forEach(function (d) { byA[d.name] = d; });
    resultB.dimensions.forEach(function (d) { byB[d.name] = d; });
    removed.forEach(function (nameA) {
      var labelsA = {};
      byA[nameA].groups.forEach(function (g) { labelsA[g.label] = 1; });
      var best = null, bestOverlap = 0;
      added.forEach(function (nameB) {
        if (taken[nameB] || byB[nameB].kind !== byA[nameA].kind) return;
        var labelsB = {}, union = {}, inter = 0;
        byB[nameB].groups.forEach(function (g) { labelsB[g.label] = 1; });
        Object.keys(labelsA).forEach(function (l) { union[l] = 1; if (labelsB[l]) inter++; });
        Object.keys(labelsB).forEach(function (l) { union[l] = 1; });
        var size = Object.keys(union).length;
        var overlap = size ? inter / size : 0;
        if (overlap > bestOverlap) { best = nameB; bestOverlap = overlap; }
      });
      if (best !== null && bestOverlap >= RENAME_MIN_OVERLAP) {
        taken[best] = 1;
        pairs.push({ a: nameA, b: best, overlap: Math.round(bestOverlap * 10000) / 10000 });
      }
    });
    return pairs;
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
    // Data-quality carry-over (#868): optional keys, only when either side has any.
    dimensions.forEach(function (cd) {
      var impA = dimsA[cd.name].implausible_values || 0, impB = dimsB[cd.name].implausible_values || 0;
      if (impA || impB) { cd.implausible_a = impA; cd.implausible_b = impB; }
    });
    var renames = possibleRenames(resultA, resultB, removed, added);
    var scoreDelta = (resultA.overall_score === null || resultB.overall_score === null)
      ? null : resultB.overall_score - resultA.overall_score;

    // flags is every human-readable notice, including a kind-mismatch
    // dimension's "drift comparison skipped" message - informational, since
    // the comparison genuinely could not be measured. driftDetected is the
    // narrower, structural signal of whether any *real* drift was measured -
    // matches faircode/compare.py's _build_flags() so a CLI-equivalent
    // consumer wouldn't false-positive on a skipped/unmeasurable comparison
    // the way checking flags.length alone would (#472).
    var flags = [], driftDetected = false;
    if (scoreDelta !== null && scoreDelta <= -SCORE_DROP_FLAG) {
      flags.push('overall representation score dropped ' + Math.abs(scoreDelta) +
                 ' points (' + resultA.overall_score + ' → ' + resultB.overall_score + ')');
      driftDetected = true;
    }
    dimensions.forEach(function (cd) {
      if (Math.abs(cd.missing_pct_delta) >= MISSING_DRIFT_FLAG) {
        flags.push(cd.name + ': missing-data share shifted ' +
                   (cd.missing_pct_a * 100).toFixed(1) + '% → ' +
                   (cd.missing_pct_b * 100).toFixed(1) + '%');
        driftDetected = true;
      }
      if ((cd.implausible_a || 0) !== (cd.implausible_b || 0)) {
        flags.push(cd.name + ': implausible age values differ (' + cd.implausible_a + ' in ' + nameA +
                   ', ' + cd.implausible_b + ' in ' + nameB + ') - they were treated as missing in ' +
                   'each, so check the age shares for artefacts');
      }
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
        driftDetected = true;
      }
      cd.groups.forEach(function (g) {
        if (g.status === 'appeared') {
          flags.push(cd.name + ": '" + g.label + "' appeared (" +
                     (g.share_a * 100).toFixed(1) + '% → ' +
                     (g.share_b * 100).toFixed(1) + '%)');
          driftDetected = true;
        } else if (g.status === 'disappeared') {
          flags.push(cd.name + ": '" + g.label + "' disappeared (" +
                     (g.share_a * 100).toFixed(1) + '% → ' +
                     (g.share_b * 100).toFixed(1) + '%)');
          driftDetected = true;
        }
      });
    });
    added.forEach(function (n) { flags.push("dimension '" + n + "' is present only in " + nameB); driftDetected = true; });
    removed.forEach(function (n) { flags.push("dimension '" + n + "' is present only in " + nameA); driftDetected = true; });
    renames.forEach(function (r) {
      flags.push("'" + r.a + "' (" + nameA + ") and '" + r.b + "' (" + nameB + ') look like the same dimension (' +
                 (r.overlap * 100).toFixed(0) + '% of their group labels overlap) - rename one column ' +
                 'so the names match to compare them');
    });
    [[nameA, resultA], [nameB, resultB]].forEach(function (pair) {
      if ((pair[1].flags || []).indexOf(NO_KIND_DETECTED_FLAG) !== -1) {
        flags.push(pair[0] + ': no column name was recognised as sex, race, age or geography, so every ' +
                   'dimension is a plain categorical - map columns with --map COL=KIND');
      }
    });

    var out = {
      a: { name: nameA, n_rows: resultA.n_rows,
           overall_score: resultA.overall_score, grade: resultA.grade,
           dimensions_detected: resultA.dimensions_detected, note: resultA.note },
      b: { name: nameB, n_rows: resultB.n_rows,
           overall_score: resultB.overall_score, grade: resultB.grade,
           dimensions_detected: resultB.dimensions_detected, note: resultB.note },
      score_delta: scoreDelta, dimensions: dimensions,
      added_dimensions: added, removed_dimensions: removed, flags: flags,
      drift_detected: driftDetected
    };
    if (renames.length) out.possible_renames = renames;
    return out;
  }

  global.FairCodeProfiler = { parseCSV: parseCSV, parseJSON: parseJSON, parseXLSX: parseXLSX,
                              sniffDelimiter: sniffDelimiter,
                              profile: profile, compare: compare,
                              parseReference: parseReference,
                              // Opt-in, informational only (issue #738) - see
                              // proxyHints()'s own comment for why this is
                              // kept out of profile()/compare().
                              proxyHints: proxyHints, proxyNotes: proxyNotes, normalizeKeyText: normalizeKeyText, normalizeKeywords: normalizeKeywords, decodeText: decodeText, proxyFamily: proxyFamily, parseHeldOut: parseHeldOut, buildHeldOut: buildHeldOut,
                              adjustPValues: adjustPValues,
                              csvField: csvField, csvRow: csvRow, provenanceCsv: provenanceCsv,
                              // publicParams: resolved knobs for an export's
                              // provenance.params, matching the Python path (#490).
                              publicParams: publicParams,
                              // Exposed so the Profile/Compare threshold-input
                              // placeholders (issue #377) can be sourced from
                              // this single source of truth instead of a
                              // hardcoded, driftable copy in profiler.html.
                              DEFAULT_OPTS: DEFAULT_OPTS };
})(typeof globalThis !== 'undefined' ? globalThis : this);
