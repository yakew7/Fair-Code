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

Repeated header names are made unique the way pandas does (`name`, `name.1`, `name.2`, ... skipping names already taken) before anything else; the browser parser does the same so two same-named columns are two dimensions, never one overwriting the other (#834).

**Tokenize** the column name: strip accents (Unicode NFD, then drop U+0300-U+036F, so `Género`
becomes `Genero`), split on separators **and** camelCase boundaries, then lower-case.
`DateOfBirth → [date, of, birth]`, `Sex_Code_Text → [sex, code, text]`, `ageGroup → [age, group]`.
Token boundaries are what stop `age` from matching `Agency_Text` or `Language`.

A keyword matches a token by **exact match** when the keyword is <4 chars, or **prefix match** when
it is ≥4 chars (prefix, not substring - so `age` never matches `agency`, but `zipcode` matches
`zip`). A small set of keywords (`race`, `state`, `city`, `region`, `country` -
`detect.EXACT_ONLY_KEYWORDS`) are exact-match-only regardless of length, since their common prefixes
false-positive too easily (`statecode` would otherwise match `state`, `statement`/`stateless` would
too). The non-English additions below that would collide with ordinary words (`genero`,
`alter`, `land`, `raza`, `raca`, `rasse`, `pais`, `pays`, `estado`, `ville`, `stadt`) are exact-only too.
Classify by the **first** keyword list that matches any token (order matters):

| Dimension   | Keywords                                                                 |
|-------------|--------------------------------------------------------------------------|
| `sex`       | `sex`, `gender`; es/de/fr/pt: `sexo`, `genero`, `geschlecht`, `sexe`      |
| `race`      | `race`, `ethnic`, `ethnicity`; `raza`, `etnia`, `rasse`, `ethnie`, `raca` |
| `age`       | `age`, `dob`, `yob`, `birth`; `edad`, `nacimiento`, `alter`, `geburt`, `idade`, `nascimento`, `naissance` |
| `geography` | `region`, `state`, `zip`, `zipcode`, `postal`, `country`, `county`, `city`, `location`, `province`; `estado`, `pais`, `provincia`, `ciudad`, `bundesland`, `land`, `stadt`, `plz`, `ville`, `pays`, `departement`, `cidade`, `regiao`, `municipio` |

Before the per-token keyword match, a short list of **compound phrases** that contain a geography
stem but name a non-geography concept is checked as consecutive tokens (`estado`+`civil`,
`marital`+`status`, `stato`+`civile`, `etat`+`civil`). A hit returns no keyword kind so the column
falls through to generic categorical instead of `geography` - e.g. Spanish/Portuguese
`estado_civil` / `estado civil` (marital status) must not be typed as a place (#855). Plain
`estado` remains `geography`.

Names that are not covered (other languages, abbreviations) fall through to the generic categorical
rule below. When *no* column of a profile was recognised by name - every dimension is `categorical`
and no `--map` was given - a final flag says so and points at `--map COL=KIND` (#847), since ages
would otherwise silently go unbanded.

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

(Digits mean ASCII `0-9` only in both engines. Python's `\d` and the browser's `\d` disagree about Arabic-Indic or fullwidth digits, so a value written with them is *not* a number: it falls into the categorical branch below, identically in Python and JS - #836.)

- **Non-negative numeric** (e.g. `34`): use directly, up to `MAX_AGE` (default 120, `--max-age`).
  A value *above* it (`150`, `200`, a birth year such as `1985`) is **implausible**: it is not
  banded, is counted as missing like a negative value, and is reported as `implausible_values` on the
  dimension plus a flag - it must never inflate the `75+` band (#840). It is also left out of the
  skewness, the intersections and the proxy tests. If every value is implausible the dimension has
  no groups ("not measured").
- **Interval string** (e.g. `[70-80)`): take the lower bound via the first signed number.
- **Negative numeric or signed-string sentinel** (e.g. `-1`, `-9`, `"unknown: -999"`): treat as missing, report under `implausible_values` with a sentinel data-quality flag (#863); it must never fall through to the `75+` band.
- **Anything else**: treat as categorical (skip numeric handling).

Before numeric normalization, date detection checks a deterministic sample of up to **200**
non-null values spread across the whole column. If at least 50% of that sample is date-shaped, the
column stays categorical so later date rows cannot be converted into fabricated numeric age bands.

Fixed bands (left-closed): `0–18`, `18–30`, `30–45`, `45–60`, `60–75`, `75+`.
The band shares are then analyzed exactly like a categorical column.

---

## 3. Per-dimension metrics

For a dimension with `k` groups and null-excluded normalized shares `p_1 … p_k` (each `p_i = count_i / N_nonnull`):

Category labels are literal data, including names such as `__proto__`, `constructor`,
and `toString`. They must be retained in distinct counts, groups, intersections,
reference baselines, and drift comparisons, with no inherited-property lookups.

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
The Python/CLI path needs the optional `scipy` extra. It never affects the score, so it is
intentionally **not** part of `profile()`/`compare()`'s bit-for-bit parity contract between the two
engines - but as of #738, the web profiler has its own opt-in JS port of the same chi-squared test
(`FairCodeProfiler.proxyHints()` in `assets/profiler-engine.js`, wired to a "Check for proxy columns"
button below a profile's results), so this is no longer a CLI-only capability - it's just a
separate, non-parity-tested module in each engine, exercised by cross-checking known-correlated and
known-unrelated fixtures against `scipy.stats.chi2_contingency` (`tests/test_js_parity.py`) rather
than by the bit-for-bit parity assertion the rest of this file describes.

**Tunables.** The significance level defaults to `p < 0.05` and is `--proxy-alpha ALPHA` on the CLI,
`alpha` on the MCP tools and a "Significance level" input in the web views; it must be in `(0, 1]`
and, like `--proxy-hints-with`, errors if given without `--proxy-hints`. An opt-in multiple-comparison
correction (`--proxy-correction bonferroni|holm`, MCP `correction`, a web dropdown) adjusts p-values
across every testable pair - Bonferroni is `min(1, p·m)`, Holm is the step-down procedure with a
running maximum - reports a pair only when its *adjusted* p is below alpha, and adds `p_adjusted` to
each hint. The default (no correction) is unchanged. `faircode.proxy.adjust_p_values` and the JS
`adjustPValues` are cross-checked in `tests/test_js_parity.py`.

**Small expected cells (#810).** The chi-squared approximation is unreliable when many contingency
cells expect fewer than 5 rows (high-cardinality categoricals, rare groups). Every hint therefore
carries `low_expected_share` (share of cells with expected count < 5, 4 dp) and `low_expected`
(`true` when that share exceeds 0.2). The terminal/HTML/web output marks such a hint "small cells",
and the CSV proxy section gains a `low_expected` column. The p-value is still computed and reported.

**Family size (#821).** Every hint also carries `n_tests`, the number of pairs actually tested
(a pair with a constant column is skipped and does not count), so `p_adjusted` can be re-derived
from the export (Bonferroni: `min(1, p · n_tests)`). Adjusted hints print "(m=N pairs)" in the
terminal/HTML/web output, and the CSV proxy section gains an `n_tests` column before `low_expected`.

**Limitation - a dropped column is invisible by construction.** `proxy_hints()` only tests pairs
drawn from `dimensions`, the columns actually present in the profiled data. If a protected attribute
was already removed before profiling - "we dropped the column so it's fine" - it can never be one
half of a tested pair, since it was never detected in the first place. This is silent: the pass
reports no association involving that attribute, which reads as "no proxy risk" rather than "this
column was never checked."

`faircode profile --proxy-hints --proxy-hints-with PATH=COLUMN` (repeatable) closes this specific
gap: `COLUMN` from `PATH` is treated as an additional column, tested against every detected dimension
and against every other held-out column, without needing it back in the profiled dataset itself.
By default `PATH`'s rows must align 1:1 (same order) with the profiled dataset, so a mismatched row
count is a hard error rather than a silently wrong result - but a same-length file in a different
order would still be accepted, so a spec may instead be `PATH=COLUMN:KEY` (#822): rows are then
matched on the `KEY` column, which must exist in both files and be unique and non-empty in both,
and every key in the profiled dataset must appear in the held-out file (extra held-out rows are
ignored). Keys are compared as text. When `COLUMN` itself contains a colon (common in survey
exports like `race:self_reported`), either backslash-escape the literal colon (`PATH=a\:b`) or
rely on the fallback (#869): a trailing `:KEY` is only treated as a join key when `KEY` names a
real column of the profiled dataset - otherwise the whole right-hand side is the held-out column
name. The web views avoid the ambiguity entirely: column and join key are separate inputs, so a
column name may contain a colon without escaping. The same form works for `--proxy-hints-with-a/-b`,
the MCP `held_out_with*` parameters, and a "Join key (optional)" input per row in the web views; the
recorded provenance entry (section 10) gains a `key` field. Programmatically,
`proxy_hints(df, dimensions, held_out={"race": pd.Series(...)})` does the same thing directly.
`compare`'s `--proxy-hints` accepts the same idea per side - `--proxy-hints-with-a PATH=COLUMN`
and `--proxy-hints-with-b PATH=COLUMN` (each repeatable), aligned to `csv_a`/`csv_b` respectively -
added in #737. The MCP `compare_datasets` tool exposes the same held-out parameters as
`held_out_with_a` and `held_out_with_b` when `proxy_hints=true`.

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
overall_score = round( mean( dimension_score for every detected dimension with n_groups > 0 ) )
```

If no dimensions are detected, the result is unmeasured: `overall_score`, `grade`, and comparison
`score_delta` are `null`, `dimensions_detected` is `false`, and `note` explains that no demographic
columns were detected. A missing measurement must not be interpreted as the numeric score zero.

A detected dimension with **zero observed groups** (every value missing, or an empty column) is the
same kind of missing measurement, one level down: it is excluded from the mean rather than folding
its fabricated `dimension_score = 0` into it. This differs from a genuine single-group dimension
(`n_groups = 1`), which has real, lopsided data and correctly scores low - a zero-group dimension has
nothing to measure at all. If *every* detected dimension has zero groups, `overall_score`/`grade` are
`null` and `note` explains that no dimension had any non-missing values to measure.

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
with `imbalance_ratio ≥ 3`, every dimension with `missing_pct ≥ 0.05`, every age dimension with
`implausible_values` (an optional integer key present only when above zero, #840), and every
intersectional gap.

---

## 7. Defaults (single place to tune)

Human-readable terminal, browser, and exported HTML reports show at most the first **12** groups
per dimension. Whenever a dimension contains more groups, every report surface must state exactly
how many groups were omitted; the structured result remains complete.

The flagging thresholds are overridable per run without editing source: `profile(df, opts={...})`
in Python, `profile(table, overrides, opts)` in JS, and `--min-share` / `--intersection-floor` /
`--imbalance-flag` / `--missing-flag` / `--min-group-size` / `--max-categorical-card` /
`--max-dimension-groups` / `--max-age` on the CLI. Omitted knobs fall back to the defaults below.

| Constant               | Default | Used by                          |
|------------------------|:-------:|----------------------------------|
| `MIN_SHARE_THRESHOLD`  | 0.05    | under-representation flagging    |
| `MIN_GROUP_SIZE`       | 100     | `small_group` unreliable-metric flag |
| `INTERSECTION_FLOOR`   | 0.01    | near-empty intersection cells    |
| `MAX_CATEGORICAL_CARD` | 20      | generic-categorical detection    |
| `MAX_DIMENSION_GROUPS` | 50      | identifier/date-like dimension drop |
| `IMBALANCE_FLAG`       | 3.0     | imbalance-ratio flag             |
| `MISSING_FLAG`         | 0.05    | missing-data flag                |
| `AGE_BANDS`            | 0,18,30,45,60,75 | age band edges          |
| `MAX_AGE`              | 120     | numeric ages above this are implausible, not banded (§2) |
| `DATE_SAMPLE_SIZE`     | 200          | whole-column date-detection sample cap |
| `PSI_EPSILON`          | 0.0001  | share floor in PSI (§8)          |
| `PSI_MODERATE`         | 0.10    | PSI ≥ this → moderate drift (§8) |
| `PSI_SIGNIFICANT`      | 0.25    | PSI ≥ this → significant drift (§8) |
| `SCORE_DROP_FLAG`      | 5       | overall-score drop flagged (§8)  |
| `MISSING_DRIFT_FLAG`   | 0.05    | missing_pct jump flagged (§8)    |

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
- **drift_level** from the same **rounded** PSI shown as `psi` below (not the unrounded float) - so
  the label can never contradict the displayed number at a rounding boundary: `none` (`< 0.10`),
  `moderate` (`0.10 ≤ PSI < 0.25`), `significant` (`≥ 0.25`).
- **TVD** (Total Variation Distance) - an easy-to-read companion: `0.5 · Σ |b_i − a_i|`, range `[0, 1]`.
- **dimension_score_delta** = `dimension_score_b − dimension_score_a`.
- Per group: `share_a`, `share_b`, `share_delta = share_b − share_a`, and a `status` of
  `appeared` (`a = 0, b > 0`), `disappeared` (`a > 0, b = 0`), `unchanged` (`share_delta == 0`), or `shifted`. Groups are ordered by
  **descending `|share_delta|`**, then label ascending (deterministic tie-break, both engines agree).
- **missing_pct_a**, **missing_pct_b**, **missing_pct_delta** = `missing_pct_b − missing_pct_a` -
  each side's `missing_pct` (§7), diffed independently of the non-null-share PSI/TVD calculation
  above. A column collapsing to mostly-missing between A and B can leave the surviving non-null
  rows' group split unchanged (PSI 0, `drift_level: "none"`) while still being the loudest real
  signal in the comparison - this catches that case. Computed (and flagged) even for a
  `kind_mismatch` dimension, since `missing_pct` doesn't depend on kind classification.

Top level: `score_delta = overall_score_b − overall_score_a` when both scores are measured, and
`null` otherwise. `flags` is assembled from: an
overall-score drop of `≥ SCORE_DROP_FLAG` points, every dimension whose `|missing_pct_delta| ≥
MISSING_DRIFT_FLAG`, every dimension whose `drift_level ≠ none`, every `appeared`/`disappeared`
group, every added/removed dimension, **and** every `kind_mismatch` dimension's own
"drift comparison skipped" notice - that last case is informational only (the comparison genuinely
couldn't be measured, not evidence of drift), so it's the one category of `flags` entry
**excluded** from `drift_detected`.

`drift_detected` is a boolean - `true` iff at least one *real* drift signal fired (any of the first
five categories above), `false` if `flags` is empty or contains only kind-mismatch notices. The CLI's
`compare --fail-on-drift` checks `drift_detected`, not `bool(flags)`, so a schema change between two
snapshots that makes a dimension unmeasurable (e.g. one side's ages banded, the other left raw)
doesn't false-positive as "drift detected" in a CI gate (see issue #472).

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
      ],
      "missing_pct_a": 0.0, "missing_pct_b": 0.0, "missing_pct_delta": 0.0
    }
  ],
  "added_dimensions": ["income_bracket"],
  "removed_dimensions": [],
  "flags": [ "race: significant representation drift (PSI 0.34)", "race: 'Asian' disappeared (10.0% → 0.0%)" ],
  "drift_detected": true
}
```

Rounding uses the same half-up helper as the rest of the spec (`Math.round` / `floor(x·f + 0.5)`):
`psi`, `tvd`, the share fields, and `missing_pct_delta` to 4 dp (`missing_pct_a`/`missing_pct_b`
are already-rounded `missing_pct` values straight from each side's own profile); score deltas are
integers.

---

## 9. Reference baseline

"Balanced internally" ≠ "representative of the target population." An optional **reference baseline**
scores a dataset's shares against an external population (e.g. US Census age×sex), catching
under-sampling relative to who a model will actually serve. Supplied via `--reference baseline.csv`
(CLI) or an upload (web), and passed to the engine as the `reference` option.

**Format** - a long-format table with three columns (headers case-insensitive; `column`/`dimension`,
`group`/`value`/`label`, `share`/`expected`/`percent`). Shares may be fractions (`0.51`) or
percentages (`51`) - the scale is decided per column (rows grouped by the `column` identifier): if
any of a column's values exceeds `1.5` that column is read as percentages, so a reference file that
mixes conventions between columns still parses each column correctly. Parsed into
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
- **`encoding`** (`encoding_a` / `encoding_b` for `compare`) - present when an explicit `--encoding` was passed or a byte-order mark (BOM) was sniffed from the file, recording the character encoding used to decode the raw bytes (e.g. `"latin-1"`, `"utf-16"`, `"utf-8-sig"`). Omitted for the plain-UTF-8 default, preserving the existing export shape.
- **`reference_hash`** - present only when a section 9 baseline was supplied.
- **`proxy_hints_with`** (`proxy_hints_with_a` / `_b` for `compare`) - present only when held-out
  files were given to `--proxy-hints-with` (section 3; the web proxy results; MCP
  `compare_datasets`'s `held_out_with_a`/`_b`): a list of `{ "path", "column", "sha256" }` (plus `"key"` when a join key was given), one per
  file in the order given, with `sha256` hashed like `dataset_hash` and a `sha256_note` when it is
  `null`. It ties the proxy results in the same export to the files that produced them (#811).
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
| `profile_dataset` | `profile()` | Same shape as `profile --json` (section 6), `provenance` (section 10) attached by default via `include_provenance`; accepts `format` ("json" default, or "csv" returning `{"csv": "<text>"}`) |
| `compare_datasets` | `compare()` | Same shape as `compare --json` (section 8), `dataset_hash_a`/`dataset_hash_b` in provenance; accepts `format` ("json" default, or "csv"); `proxy_hints=true` attaches `proxy_hints_a`/`proxy_hints_b`, matching `compare --proxy-hints`, and accepts `alpha`, `correction` ("bonferroni"\|"holm"), and `held_out_with_a`/`held_out_with_b` |
| `proxy_hints` | `proxy_hints()` | Returns `{"hints": [...]}`, never a bare list - a list return value gets split by the MCP SDK into one content block per element, and an empty list becomes zero blocks, indistinguishable from an error to a caller. Accepts `alpha`, `correction`, `held_out_with`, and `include_provenance` (default true, attaching dataset hash, params, overrides, and held-out files, section 10) |
| `list_explainers` | `faircode/_explainers/data.json` (mirrored from `assets/explainers-data.json`) | Phase 2: read-only lookup, no analysis. Returns `{"explainers": [{slug, title, subtitle, summary, tags}, ...]}`; optional `tag` filters to explainers carrying it, erroring if none match |
| `get_explainer` | `faircode/_explainers/<slug>.md` (mirrored from `explainers/<slug>.md`) | Phase 2: returns `{slug, title, subtitle, tags, content}` - `content` is the raw Markdown source. Errors clearly (`FileNotFoundError`) for an unknown slug |
| `get_benchmark_results` | `faircode/_results_frozen/results_{fairness,performance}.csv` (mirrored from `paper/results-frozen/`) | Phase 2: filters the frozen CSV named by `kind` on exact-match `audit`/`model`/`strategy`/`metric`/`protected_attribute` (a filter naming a column `kind` doesn't have raises `ValueError` rather than being ignored). Returns `{results, total_matches, truncated}`, capped at 200 rows |

The first three tools accept `overrides` (the section 1 `{column: kind}` map, as a JSON object rather
than repeated `--map COL=KIND` strings) and the relevant section 7 thresholds by name.
`profile_dataset` also accepts `cross` and `reference_path`, matching `profile`'s `--cross` and
`--reference`. Both `profile_dataset` and `compare_datasets` accept `format` ("json", the default, or
"csv" returning `{"csv": "<text>"}` matching the CLI's `--csv` output, section 12); any other format
raises a `ValueError`.

`proxy_hints` takes no threshold parameters at all - only `path`, `overrides`, `held_out_with`,
`alpha` (significance level, default `0.05`, must be in `(0, 1]`), and `correction` (`"bonferroni"`
or `"holm"`, defaulting to unadjusted p-values) - since it only surfaces candidate proxy pairs for
a human/agent to review, not a scored or filtered result the section 7 thresholds would narrow. An
invalid `alpha` or unknown `correction` raises a `ValueError` converted to a `ToolError`.

`compare_datasets`'s `proxy_hints=true` mode similarly accepts `alpha`, `correction`, and
`held_out_with_a`/`held_out_with_b` (each a list of `"PATH=COLUMN"` strings for columns dropped
from dataset A / B respectively). Passing `held_out_with_a` or `held_out_with_b` without `proxy_hints=true`
raises a `ValueError` (`"held_out_with_a/held_out_with_b need proxy_hints=true"`).

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

The proxy-test and output parameters below are all optional. An invalid value is raised as a
`ValueError`, so it reaches the agent as a `ToolError` carrying the message shown.

| Parameter | Tools | Default | Behaviour and errors |
|-----------|-------|---------|----------------------|
| `alpha` | `proxy_hints`, `compare_datasets` | `null` (0.05) | Proxy-hint significance level, mirroring `--proxy-alpha` (section 3). A value outside `(0, 1]` raises `alpha must be in (0, 1], got ...`. On `compare_datasets` it is only read when `proxy_hints=true` |
| `correction` | `proxy_hints`, `compare_datasets` | `null` (no correction) | `"bonferroni"` or `"holm"`, mirroring `--proxy-correction` (section 3): a pair is reported only when its adjusted p is below `alpha`, and each hint gains `p_adjusted`. Any other value raises `correction must be one of ('bonferroni', 'holm'), got ...`. On `compare_datasets` it is only read when `proxy_hints=true` |
| `held_out_with_a` / `held_out_with_b` | `compare_datasets` | `null` | Lists of `"PATH=COLUMN"` strings testing a column already dropped from dataset A / B, mirroring `--proxy-hints-with-a`/`-b`. Parsed by `parse_held_out_specs` with the same validation as `held_out_with`, error messages naming the parameter. Given without `proxy_hints=true`, raises `held_out_with_a/held_out_with_b need proxy_hints=true` |
| `format` | `profile_dataset`, `compare_datasets` | `"json"` | `"json"` returns the result unchanged; `"csv"` returns `{"csv": "<text>"}`, the same text `profile --csv` / `compare --csv` writes (section 12), with its provenance section unless `include_provenance=false`. Any other value raises `format must be 'json' or 'csv', got ...` |

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

---

## 12. CSV export

`faircode profile --csv PATH` and `faircode compare --csv PATH` write a flat table meant for a
spreadsheet or BI tool; the web profiler's and compare view's **Download CSV** buttons, and the MCP
tools' `format="csv"`, emit the same text. The Python writers are `faircode.report.to_csv` /
`compare_to_csv` and the browser writers are `buildCsvReport` / `buildCompareCsvReport`; a
cross-engine test (`tests/test_js_parity.py`) asserts they produce the same file. Rows end in CRLF
and cells are quoted only when they contain a comma, quote or newline (Python `csv` defaults).

**Profile.** Header `dimension,kind,label,count,share,ci_low,ci_high,under_represented,small_group`,
one row per group of every dimension (not just the first 12 shown on screen), then optional sections,
each preceded by a blank row and its own header, in this order:

1. `flag` - one row per flag message;
2. reference baseline (only when `--reference` was used) -
   `dimension,reference_label,expected,actual,delta,reference_deviation`;
3. proxy hints (only when run) - `proxy_hint_a,proxy_hint_b,p_value,cramers_v`, plus `p_adjusted`
   when a correction was requested, then `n_tests`, `low_expected`;
4. provenance (only with `--csv-provenance` / the web checkbox / MCP `include_provenance`) -
   `provenance_key,provenance_value`, nested objects flattened to dotted keys (`params.min_share`),
   lists as JSON text, `null` as an empty cell. The values are exactly the block `--json` attaches
   (section 10).

**Compare.** Group rows `dimension,kind_a,kind_b,label,share_a,share_b,share_delta,status`, a
dimension-summary section `dimension,kind_mismatch,dimension_score_a,dimension_score_b,
dimension_score_delta,psi,tvd,drift_level`, a `dimension,present_in` section (only when a dimension
was detected in just one dataset: `a_only` / `b_only`, #842), `flag`, proxy hints (a leading `dataset` column holds `A`
or `B`), and provenance. A dimension skipped for a kind mismatch has no group rows, only its summary
row.

**Formula injection.** A *text* cell that begins with `=`, `+`, `-`, `@`, tab or CR gets a single-quote
prefix so a spreadsheet does not evaluate it as a formula (OWASP CSV-injection guidance); numbers and
booleans are never touched, so real negative values stay numeric.

**stdout.** `--csv -` streams the CSV to stdout, suppresses the terminal report so the stream stays
pure CSV, and is rejected together with `--json` (both would write to stdout).

**BOM.** `--csv-bom` (CLI only; needs `--csv`) prefixes the export with a UTF-8 byte-order mark
(`U+FEFF` / bytes `EF BB BF`) so Excel on Windows detects UTF-8 and keeps non-ASCII labels intact.
Without the flag the file stays plain UTF-8, matching the pre-#846 behaviour. On `--csv -` the BOM
is written as the character U+FEFF before the CSV text.

