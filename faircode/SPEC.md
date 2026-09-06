<div align="center">

# Fair Code Profiler - Analysis Spec

![Source of Truth](https://img.shields.io/badge/Source%20of%20Truth-Single%20Spec-blue?style=flat-square)
![Engines](https://img.shields.io/badge/Engines-Python%20%2B%20JS-orange?style=flat-square)
![Parity](https://img.shields.io/badge/Parity-Bit--for--Bit-brightgreen?style=flat-square)

This is the **single source of truth** for the Open Dataset Profiler. Both implementations -
the Python engine (`faircode/profiler.py`) and the browser engine (`assets/profiler-engine.js`) -
must implement *exactly* this spec so the same CSV yields the same numbers in the CLI and on the web.

The Profiler is **diagnostic**, not predictive. It audits a dataset's *demographic representation*
before any model is trained. It does not train models, drop columns, or measure prediction gaps -
that is what the `unfair.py` / `fair.py` audits do. The Profiler answers a different question:
**"who is, and is not, adequately represented in this data?"**

[1. Detection](#1-column-auto-detection) · [2. Age](#2-age-normalization) · [3. Metrics](#3-per-dimension-metrics) · [4. Intersections](#4-intersectional-gaps-informational-not-scored) · [5. Score](#5-headline-score--grade) · [6. Shape](#6-result-shape) · [7. Defaults](#7-defaults-single-place-to-tune) · [8. Comparison](#8-dataset-comparison-representation-drift) · [9. Reference](#9-reference-baseline) · [10. Provenance](#10-export-provenance) · [11. MCP](#11-mcp-tools)

</div>

---

## 1. Column auto-detection

**Tokenize** the column name: split on separators **and** camelCase boundaries, then lower-case.
`DateOfBirth → [date, of, birth]`, `Sex_Code_Text → [sex, code, text]`, `ageGroup → [age, group]`.
Token boundaries are what stop `age` from matching `Agency_Text` or `Language`.

A keyword matches a token by **exact match** when the keyword is <4 chars, or **prefix match** when
it is ≥4 chars (prefix, not substring - so `age` never matches `agency`, but `statecode` matches
`state`). Classify by the **first** keyword list that matches any token (order matters):

| Dimension   | Keywords                                                                 |
|-------------|--------------------------------------------------------------------------|
| `sex`       | `sex`, `gender`                                                          |
| `race`      | `race`, `ethnic`, `ethnicity`                                           |
| `age`       | `age`, `dob`, `yob`, `birth`                                            |
| `geography` | `region`, `state`, `zip`, `zipcode`, `postal`, `country`, `county`, `city`, `location`, `province` |

A column not matched above is treated as a **generic categorical** demographic *only if* its
distinct non-null value count is `2 ≤ n ≤ 20`.

Detection returns, for each kept column, its `name` and `kind` ∈ {`sex`, `race`, `age`,
`geography`, `categorical`}.

After per-dimension analysis, any dimension that exploded into more than `MAX_DIMENSION_GROUPS`
(default **50**) groups is **dropped** as a likely identifier/date column - *except* `geography`,
which legitimately has high cardinality (many cities/regions).

### Manual overrides

Both engines accept an optional `overrides` map (`{column: kind}`) that wins over auto-detection -
for datasets with unusual headers (`gndr`, `patient_region_code`) that the name heuristic misses or
mistypes. A value in {`sex`, `race`, `age`, `geography`, `categorical`} **forces** that column to
that kind regardless of its name; any other value (e.g. `ignore`) **excludes** the column. An
explicitly-forced column is also exempt from the `MAX_DIMENSION_GROUPS` drop above (the user's intent
overrides the heuristic). Surfaced as `faircode profile data.csv --map gndr=sex` in the CLI and as
editable per-column dropdowns in the web profiler.

---

## 2. Age normalization

Age columns come in three shapes - normalize to numeric bands:

- **Numeric** (e.g. `34`): use directly.
- **Interval string** (e.g. `[70-80)`): take the lower bound integer via the first run of digits.
- **Anything else**: treat as categorical (skip numeric handling).

Fixed bands (left-closed): `0–18`, `18–30`, `30–45`, `45–60`, `60–75`, `75+`.
The band shares are then analyzed exactly like a categorical column.

---

## 3. Per-dimension metrics

For a dimension with `k` groups and null-excluded normalized shares `p_1 … p_k` (each `p_i = count_i / N_nonnull`):

- **shares** - the `p_i`, descending, with raw counts.
- **ci_low / ci_high** - a 95% **Wilson score interval** on each group's share, so a share read off a small sample carries its sampling uncertainty. For a group with count `c` out of `N_nonnull = n`, `p = c/n`, `z = 1.959963984540054`:
  - `center = (p + z²/2n) / (1 + z²/n)`, `margin = (z / (1 + z²/n)) · √( p(1−p)/n + z²/4n² )`
  - `ci_low = max(0, center − margin)`, `ci_high = min(1, center + margin)`, each rounded to 4 dp.
  - Deterministic (no resampling), so the Python and JS engines return identical bounds. Wilson is used over the normal approximation because it stays inside `[0, 1]` and holds up for small/extreme groups - the under-represented cases this profiler targets.
- **min_share** = `min(p_i)`; **max_share** = `max(p_i)`.
- **imbalance_ratio** = `max_share / min_share` (the most-represented group is this many times the least).
- **entropy_ratio** = `H / ln(k)` where `H = −Σ p_i · ln(p_i)`.
  - Range `[0, 1]`; `1` = perfectly uniform, `0` = all mass in one group.
  - If `k ≤ 1`: `entropy_ratio = 0` (a single-group column has no diversity).
  - Use natural log in both languages (`Math.log` / `math.log`); the log base cancels in the ratio.
- **small_group** - `true` when a group's raw `count` is below `min_group_size` (default **100**). A flag on the group, not a score input: below this size the share and its interval are noisy enough that a gap should be treated as a lead to investigate, not a confirmed finding.
- **under_represented** - groups with `p_i < min_share_threshold` (default **0.05**).
- **missing_pct** = `null_count / N_total` for the column.

`dimension_score = round(entropy_ratio × 100)`.

### Numeric-age extra (informational, not scored)
- **skewness** - Fisher–Pearson sample skewness of the raw numeric ages:
  `g1 = (1/N · Σ (x−x̄)³) / (1/N · Σ (x−x̄)²)^1.5`. `null`/`0` if variance is 0 or `N < 3`.

### Proxy hints (opt-in, informational, not scored)
An optional pass (`faircode profile/compare … --proxy-hints`) runs a chi-squared test of independence
(`scipy.stats.chi2_contingency`) over every pair of detected dimensions and reports pairs with
`p < 0.05`, each with its p-value and Cramér's V effect size, most-significant first. It surfaces
"this column may be a proxy for that protected attribute" - the same pattern the bias audits use.
This is **Python/CLI-only** (needs the optional `scipy` extra) and never affects the score, so it is
intentionally **not** part of the JS engine; the two engines stay bit-for-bit identical without it.

**Limitation - a dropped column is invisible by construction.** `proxy_hints()` only tests pairs
drawn from `dimensions`, the columns actually present in the profiled data. If a protected attribute
was already removed before profiling - "we dropped the column so it's fine" - it can never be one
half of a tested pair, since it was never detected in the first place. This is silent: the pass
reports no association involving that attribute, which reads as "no proxy risk" rather than "this
column was never checked."

`faircode profile --proxy-hints --proxy-hints-with PATH=COLUMN` (repeatable) closes this specific
gap: `COLUMN` from `PATH` is treated as an additional column, tested against every detected dimension
and against every other held-out column, without needing it back in the profiled dataset itself.
`PATH`'s rows must align 1:1 (same order) with the profiled dataset - there is no join key, so a
mismatched row count is a hard error rather than a silently wrong result. Programmatically,
`proxy_hints(df, dimensions, held_out={"race": pd.Series(...)})` does the same thing directly.
Currently `profile`-only; `compare`'s `--proxy-hints` does not accept `--proxy-hints-with`.

---

## 4. Intersectional gaps (informational, not scored)

Take the **first two** detected demographic dimensions (in detection order) - or an explicit pair via
the `cross` option (`--cross colA,colB` in the CLI, two dropdowns in the web profiler; if either name
isn't detected, falls back to the first two). Build their crosstab of counts. Report every cell whose
count is `0` (an absent subgroup) or `< intersection_floor` of total rows (default **0.01** →
"near-empty"). Skip if fewer than two dimensions were detected.

---

## 5. Headline score & grade

```
overall_score = round( mean( dimension_score for every detected dimension ) )
```

If no dimensions are detected, the result is unmeasured: `overall_score`, `grade`, and comparison
`score_delta` are `null`, `dimensions_detected` is `false`, and `note` explains that no demographic
columns were detected. A missing measurement must not be interpreted as the numeric score zero.

Grade bands:

| Grade | Score   | Meaning                                              |
|:-----:|---------|------------------------------------------------------|
| A     | 85–100  | Well balanced across detected demographics           |
| B     | 70–84   | Mostly balanced, minor under-representation          |
| C     | 55–69   | Noticeable imbalance in one or more dimensions       |
| D     | 40–54   | Strong imbalance / sparse subgroups                  |
| F     | 0–39    | Severe imbalance or single-group dimensions          |

The score intentionally reflects **balance only**. Missing-data %, imbalance ratios, and
intersectional gaps are surfaced as **flags** alongside the score, not folded into it - this keeps
the two engines trivially in sync and the score easy to explain.

---

## 6. Result shape

Both engines produce this structure (keys identical; Python uses a dataclass serialized to the same
dict, JS uses a plain object):

```jsonc
{
  "n_rows": 1340,
  "n_cols": 11,
  "overall_score": 72,
  "grade": "B",
  "dimensions_detected": true,
  "note": null,
  "dimensions": [
    {
      "name": "gender", "kind": "sex", "n_groups": 2,
      "dimension_score": 99, "entropy_ratio": 0.999,
      "imbalance_ratio": 1.05, "min_share": 0.49, "missing_pct": 0.0,
      "skewness": null,
      "groups": [ {"label": "male", "count": 676, "share": 0.504,
                   "ci_low": 0.4775, "ci_high": 0.5305, "small_group": false},
                  {"label": "female", "count": 664, "share": 0.496,
                   "ci_low": 0.4695, "ci_high": 0.5225, "small_group": false} ],
      "under_represented": []
    }
  ],
  "intersections": [
    { "dims": ["age_band", "gender"], "cells": [ {"a": "75+", "b": "female", "count": 0} ] }
  ],
  "flags": [ "region: 'southwest' is under-represented (3.1%)", "..." ]
}
```

`flags` is a human-readable list assembled from: every `under_represented` group, every dimension
with `imbalance_ratio ≥ 3`, every dimension with `missing_pct ≥ 0.05`, and every intersectional gap.

---

## 7. Defaults (single place to tune)

The flagging thresholds are overridable per run without editing source: `profile(df, opts={...})`
in Python, `profile(table, overrides, opts)` in JS, and `--min-share` / `--intersection-floor` /
`--imbalance-flag` / `--missing-flag` / `--min-group-size` on the CLI. Omitted knobs fall back to the defaults below.

| Constant               | Default | Used by                          |
|------------------------|:-------:|----------------------------------|
| `MIN_SHARE_THRESHOLD`  | 0.05    | under-representation flagging    |
| `MIN_GROUP_SIZE`       | 100     | `small_group` unreliable-metric flag |
| `INTERSECTION_FLOOR`   | 0.01    | near-empty intersection cells    |
| `MAX_CATEGORICAL_CARD` | 20      | generic-categorical detection    |
| `IMBALANCE_FLAG`       | 3.0     | imbalance-ratio flag             |
| `MISSING_FLAG`         | 0.05    | missing-data flag                |
| `AGE_BANDS`            | 0,18,30,45,60,75 | age band edges          |
| `PSI_EPSILON`          | 0.0001  | share floor in PSI (§8)          |
| `PSI_MODERATE`         | 0.10    | PSI ≥ this → moderate drift (§8) |
| `PSI_SIGNIFICANT`      | 0.25    | PSI ≥ this → significant drift (§8) |
| `SCORE_DROP_FLAG`      | 5       | overall-score drop flagged (§8)  |

---

## 8. Dataset comparison (representation drift)

`compare(A, B)` takes two **profile results** - a baseline `A` (e.g. training data) and a
current `B` (e.g. production data) - and reports how each demographic dimension's representation
shifted. It is pure post-processing over two `profile()` outputs, so both engines agree bit-for-bit
(checked by `tests/test_js_parity.py::test_python_js_compare_parity`, via `scripts/engine-js.js compare`).
It reads the already-computed group **shares**; it never re-parses the raw rows.

Dimensions are matched by **name**. A dimension present in both is compared; one present only in `B`
is an `added_dimension`, only in `A` a `removed_dimension`.

For a shared dimension, take the **union** of group labels. Each label has `share_a` and `share_b`
(a share of `0` when the label is absent on that side). Per dimension:

- **PSI** (Population Stability Index) - the standard population-drift metric:
  `PSI = Σ (b_i − a_i) · ln(b_i / a_i)`, where `a_i = max(share_a_i, PSI_EPSILON)` and
  `b_i = max(share_b_i, PSI_EPSILON)`. The epsilon floor keeps appeared/disappeared groups finite.
  PSI ≥ 0; larger = more drift.
- **drift_level** from PSI: `none` (`< 0.10`), `moderate` (`0.10 ≤ PSI < 0.25`), `significant` (`≥ 0.25`).
- **TVD** (Total Variation Distance) - an easy-to-read companion: `0.5 · Σ |b_i − a_i|`, range `[0, 1]`.
- **dimension_score_delta** = `dimension_score_b − dimension_score_a`.
- Per group: `share_a`, `share_b`, `share_delta = share_b − share_a`, and a `status` of
  `appeared` (`a = 0, b > 0`), `disappeared` (`a > 0, b = 0`), or `shifted`. Groups are ordered by
  **descending `|share_delta|`**, then label ascending (deterministic tie-break, both engines agree).

Top level: `score_delta = overall_score_b − overall_score_a` when both scores are measured, and
`null` otherwise. `flags` is assembled from: an
overall-score drop of `≥ SCORE_DROP_FLAG` points, every dimension whose `drift_level ≠ none`, every
`appeared`/`disappeared` group, and every added/removed dimension.

### Result shape

```jsonc
{
  "a": { "name": "train.csv", "n_rows": 5000, "overall_score": 78, "grade": "B" },
  "b": { "name": "prod.csv",  "n_rows": 4200, "overall_score": 61, "grade": "C" },
  "score_delta": -17,
  "dimensions": [
    {
      "name": "race", "kind": "race",
      "dimension_score_a": 82, "dimension_score_b": 55, "dimension_score_delta": -27,
      "psi": 0.3412, "tvd": 0.21, "drift_level": "significant",
      "groups": [
        { "label": "White", "share_a": 0.60, "share_b": 0.81, "share_delta": 0.21, "status": "shifted" },
        { "label": "Asian", "share_a": 0.10, "share_b": 0.0,  "share_delta": -0.10, "status": "disappeared" }
      ]
    }
  ],
  "added_dimensions": ["income_bracket"],
  "removed_dimensions": [],
  "flags": [ "race: significant representation drift (PSI 0.34)", "race: 'Asian' disappeared (10.0% → 0.0%)" ]
}
```

Rounding uses the same half-up helper as the rest of the spec (`Math.round` / `floor(x·f + 0.5)`):
`psi`, `tvd`, and the share fields to 4 dp; score deltas are integers.

---

## 9. Reference baseline

"Balanced internally" ≠ "representative of the target population." An optional **reference baseline**
scores a dataset's shares against an external population (e.g. US Census age×sex), catching
under-sampling relative to who a model will actually serve. Supplied via `--reference baseline.csv`
(CLI) or an upload (web), and passed to the engine as the `reference` option.

**Format** - a long-format table with three columns (headers case-insensitive; `column`/`dimension`,
`group`/`value`/`label`, `share`/`expected`/`percent`). Shares may be fractions (`0.51`) or
percentages (`51`) - if any value exceeds `1.5` the whole table is read as percentages. Parsed into
`{column: {group: expected_share}}`.

```
column,group,share
sex,male,0.49
sex,female,0.51
race,White,0.60
race,Black,0.13
```

**Application** - for each detected dimension whose name is in the reference, take the union of its
group labels and the reference's. For each label compute `expected`, `actual`, and
`delta = actual − expected`; the dimension's `deviation = 0.5 · Σ |actual − expected|` (TVD vs the
baseline). Groups are ordered by descending `|delta|`. A group with `expected − actual ≥
REFERENCE_DEVIATION_FLAG` (default **0.05**) is flagged as *under-represented vs reference*. The
per-dimension `reference` block and its flags are additive; the balance-only headline score is
unchanged.

```jsonc
"reference": {
  "deviation": 0.23,
  "groups": [ { "label": "White", "expected": 0.60, "actual": 0.80, "delta": 0.20 } ]
}
```

---

## 10. Export provenance

Sections 1-9 describe *what the numbers are*. This section describes *what produced them*, so an
exported report can be tied back to its run. Without it a pasted result cannot be checked: the same
CSV scores differently under a different `--map`, a different `--min-share`, or a different
reference baseline, and none of that is visible in the result shape of section 6.

**The block is attached at the export boundary, not inside `profile()`/`compare()`.** The two
engines are compared with `==` in `tests/test_js_parity.py`, so a local file name cannot live in the
result. `report.to_json(result, provenance=...)` adds it in Python; the web export adds the same
field names in `copyResultAsJSON()`. Section 6's shape is unchanged, and the parity test needs no
edit.

```jsonc
"provenance": {
  "faircode_version": "2.0.0",
  "engine": "python",                       // or "js"
  "dataset_hash": "sha256:9f86d081884c7d65...",
  "params": { "cross": null, "imbalance_flag": 3.0, "intersection_floor": 0.01,
              "min_group_size": 100, "min_share": 0.05, "missing_flag": 0.05,
              "reference_flag": 0.05 },
  "overrides": { "gndr": "sex" }
}
```

- **`dataset_hash`** - lowercase hex of the SHA-256 over the **raw file bytes**, prefixed with the
  algorithm. Raw bytes, not the parsed frame: `hashlib.sha256().hexdigest()` and
  `crypto.subtle.digest('SHA-256', bytes)` rendered as hex give the identical string, so a CLI
  report and a web report of one upload are recognisably the same measurement with no shared code.
  The digest identifies the file **as stored** - a CRLF checkout of one logical CSV digests
  differently from an LF one.
- **`dataset_hash_a` / `dataset_hash_b`** - `compare` replaces `dataset_hash` with these two,
  matching the `a` / `b` naming the compare result already uses in section 8.
- **`reference_hash`** - present only when a section 9 baseline was supplied.
- **`<field>_note`** - present only when the matching digest is `null`, saying why the bytes were
  not available (stdin, an in-memory frame). An absent digest must not look like a present one, and
  must say why it is absent.
- **`params`** - the knobs of section 7 **as resolved**, defaults included, since a defaulted
  threshold is as load-bearing as a typed one. The parsed `reference` table is not echoed here; it
  is identified by `reference_hash` instead.
- **`overrides`** - the section 1 `{column: kind}` map. It changes which columns are scored at all,
  and a forced column is exempt from the `MAX_DIMENSION_GROUPS` drop, so it can change how many
  dimensions exist.

Every field is a function of the inputs, so `--json` output stays byte-for-byte reproducible across
runs. `--no-provenance` restores the previous shape exactly.

---

## 11. MCP tools

`faircode/mcp_server.py` exposes the Python engine as [MCP](https://modelcontextprotocol.io) tools
over stdio (`faircode-mcp`, needs the optional `mcp` extra), so an agent can call these directly
instead of shelling out to the CLI and parsing text. This is a thin adapter, not a third engine: it
calls the same `profile()`/`compare()`/`proxy_hints()` functions `cli.py` wraps, so it carries no
parity obligation of its own - there is no equivalent MCP surface for the JS engine, the same way
`--proxy-hints` (section 3) has none.

| Tool | Wraps | Notes |
|------|-------|-------|
| `profile_dataset` | `profile()` | Same shape as `profile --json` (section 6), `provenance` (section 10) attached by default via `include_provenance` |
| `compare_datasets` | `compare()` | Same shape as `compare --json` (section 8), `dataset_hash_a`/`dataset_hash_b` in provenance; `proxy_hints=true` attaches `proxy_hints_a`/`proxy_hints_b`, matching `compare --proxy-hints` |
| `proxy_hints` | `proxy_hints()` | Returns `{"hints": [...]}`, never a bare list - a list return value gets split by the MCP SDK into one content block per element, and an empty list becomes zero blocks, indistinguishable from an error to a caller |
| `list_explainers` | `assets/explainers-data.json` | Phase 2: read-only lookup, no analysis. Returns `{"explainers": [{slug, title, subtitle, summary, tags}, ...]}`; optional `tag` filters to explainers carrying it, erroring if none match |
| `get_explainer` | `explainers/<slug>.md` | Phase 2: returns `{slug, title, subtitle, tags, content}` - `content` is the raw Markdown source. Errors clearly (`FileNotFoundError`) for an unknown slug |
| `get_benchmark_results` | `paper/results-frozen/results_{fairness,performance}.csv` | Phase 2: filters the frozen CSV named by `kind` on exact-match `audit`/`model`/`strategy`/`metric`/`protected_attribute` (a filter naming a column `kind` doesn't have is ignored). Returns `{results, total_matches, truncated}`, capped at 200 rows |

The first three tools accept `overrides` (the section 1 `{column: kind}` map, as a JSON object rather
than repeated `--map COL=KIND` strings) and the relevant section 7 thresholds by name.
`profile_dataset` also accepts `cross` and `reference_path`, matching `profile`'s `--cross` and
`--reference`; `compare_datasets` does not, matching `compare`'s own flag set. `proxy_hints` only
exposes `min_share`/`min_group_size` - the two thresholds that feed dimension detection - since
`intersection_floor`/`imbalance_flag`/`missing_flag` affect intersections/flags, which this tool
never touches.

An anticipated failure (an unreadable path, an unknown `overrides` column, `proxy_hints` without
the `proxy` extra installed) is raised inside the tool as a plain Python exception and converted to
an MCP `ToolError` at the tool boundary, so the actual message reaches the calling agent - any other
exception is treated by the SDK as a crash and replaced with a generic `Error executing tool <name>`,
withholding the real text. A path of `"-"` (the CLI's documented stdin shorthand, section 2) is
explicitly rejected as a `ToolError` rather than attempted: this server runs over stdio transport, so
stdin is the JSON-RPC channel itself, and reading it inside a tool call would block on/consume the
same stream the server needs for its own protocol frames. See issue #385.

A multi-sheet `.xlsx` path attaches the same "read sheet 'X' - N other sheet(s) ignored" notice the
CLI already prints to stderr, as a `sheet_note` field (`sheet_note_a`/`sheet_note_b` on
`compare_datasets`; `sheet_notes`, a list, on `proxy_hints` covering both `path` and any
`held_out_with` files) - omitted entirely when nothing was ignored. See issue #386.

`proxy_hints` only tests columns present in the dataset given by default, so it cannot flag a
remaining column as a proxy for a protected attribute that has already been dropped from the
dataset entirely - unless `held_out_with` is given: a list of `"PATH=COLUMN"` strings mirroring the
CLI's `--proxy-hints-with`, each naming a file whose rows align 1:1 with the profiled dataset and a
column to pull the dropped attribute's original values from. Parsed via `proxy.py`'s shared
`parse_held_out_specs`, so the validation is identical to the CLI's. See section 3 and issue #328.

`list_explainers`/`get_explainer`/`get_benchmark_results` carry no dataset-reading trust boundary at
all - they only read this repo's own files, never a caller-supplied path - and use the same
`ValueError`/`FileNotFoundError` → `ToolError` conversion as the other three tools. `get_explainer`'s
`slug` is validated against the exact pattern every real slug matches (lowercase, digits, hyphens)
before it's used to build a filesystem path, closing a path-traversal read a malformed slug like
`"../README"` could otherwise reach (issue #387).

None of `explainers/`, `assets/explainers-data.json`, or `paper/results-frozen/` are files
`pyproject.toml` actually ships - a real `pip install faircode[mcp]` never has them on disk. All
three Phase 2 tools instead read a package-internal, generated mirror under `faircode/`
(`_explainers/`, built by `scripts/build_explainers.py`; `_results_frozen/`, built by
`scripts/freeze_paper_results.py`), declared as real `package-data` so it ships in the wheel. See
issue #388, verified by building an actual wheel and installing it in a clean venv.
