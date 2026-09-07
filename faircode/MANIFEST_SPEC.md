<div align="center">

# audit.yaml - Manifest Spec

![Layer](https://img.shields.io/badge/Layer%201-Contributor--facing-blue?style=flat-square)
![Reads](https://img.shields.io/badge/Read%20by-faircode.benchmark-orange?style=flat-square)

</div>

This is the schema for `audit.yaml` - the declarative file that lets a bias audit be run by the
shared benchmark harness (`faircode/benchmark.py`) instead of a bespoke script. Every audit folder
in this repo has one alongside its `unfair.py` / `fair.py` pair; the two scripts stay for the
website story, the manifest is what the harness (and a research write-up) reads.

The harness applies the **same pipeline** to every manifest: five mitigation strategies S0-S4
(`faircode/strategies.py` - baseline, unawareness, unawareness + proxy removal, fairlearn
`ExponentiatedGradient` in-processing, fairlearn `ThresholdOptimizer` post-processing), three model
families (`faircode/models.py`), six fairness metrics with a bootstrap CI and a permutation p-value
each plus accuracy/AUC/F1 (`faircode/metrics.py`), and the intersectional gap for every pair of
declared protected attributes (`faircode.significance.intersectional_report`). A cross-domain
fairness comparison is only trustworthy if every domain was measured identically - the manifest is
what makes that literally true rather than an assertion in a write-up.

---

## Top-level fields

```yaml
name: compas                    # short id - becomes the "audit" column in results
title: "COMPAS - Criminal Justice Recidivism Risk"   # human-readable, optional (defaults to name)
dataset:
  path: compas-scores-raw.csv   # relative to the audit.yaml's own directory
random_state: 42                # optional, default 42
test_size: 0.2                  # optional, default 0.2
```

All seven shipped manifests use `random_state: 42` - this is a hard convention, not a coincidence.
Every model family, train/test split, bootstrap resample, and permutation shuffle takes its seed
from this one value (see `faircode/benchmark.py`'s module docstring), so two runs of the same
manifest against the same data are bit-for-bit identical. **Do not change a manifest's
`random_state` on a run whose numbers are cited anywhere** - see "Reproducibility & Results History" in
[README.md](../README.md#reproducibility--results-history) before regenerating `results/` for a citation.

## `row_filters` (optional)

Applied in order, each narrowing the dataset further (AND semantics). Every filter needs `column`
plus exactly one of the operators below.

```yaml
row_filters:
  - column: Ethnic_Code_Text
    isin: [African-American, Caucasian]
  - column: DisplayText
    equals: "Risk of Recidivism"
  - column: Recidivism_Within_3years
    notna: true
```

| Operator     | Meaning                                  |
|--------------|-------------------------------------------|
| `isin`       | keep rows where `column` is one of a list |
| `not_isin`   | drop rows where `column` is one of a list |
| `equals`     | keep rows where `column == value`         |
| `not_equals` | keep rows where `column != value`         |
| `notna`      | keep rows where `column` is not null      |

## `target`

How the binary label is derived. Exactly one `method`:

```yaml
target:
  column: readmitted
  method: equals
  value: "<30"
```

| Method         | Extra field(s)          | Meaning                                              |
|----------------|--------------------------|-------------------------------------------------------|
| `binary`       | -                        | `column` is already 0/1 (or truthy) - just `astype(int)` |
| `equals`       | `value`                  | `1` where `column == value`                            |
| `isin`         | `values`                 | `1` where `column` is one of `values`                   |
| `above_median` | -                        | `1` where `column` is above its own median              |

## `protected_attributes`

At least one required. Each becomes one row-set in the results table; the harness scores every
strategy x model against every declared attribute (plus every pair, for the intersectional gap).

```yaml
protected_attributes:
  - name: race
    type: categorical
    column: Ethnic_Code_Text
    disadvantaged_values: [African-American]
    advantaged_values: [Caucasian]

  - name: age
    type: numeric_threshold
    column: age
    threshold: 30
    disadvantaged: below   # "below" or "above" the threshold

  - name: age
    type: age_interval_threshold   # for bucketed ages like "[70-80)"
    column: age
    threshold: 70
    disadvantaged: above
```

- `type: categorical` - needs `disadvantaged_values` and/or `advantaged_values` (lists). If only
  one side is given, the other is "everything else". If both are given, rows matching neither are
  dropped from *that attribute's* comparison (they're simply unclassified, not "advantaged").
- `type: numeric_threshold` - splits a numeric column at `threshold`; `disadvantaged` says which
  side is the disadvantaged group.
- `type: age_interval_threshold` - same as above, but first extracts the lower bound from a
  bucketed string like `"[70-80)"` (falls back to a direct numeric parse if the column is already
  numeric).

Rows where *any* declared protected attribute is unclassifiable are dropped before modelling (a
manifest with two attributes only trains on rows both attributes can classify).

The **first** declared attribute is the one S3 (`in_processing`) and S4 (`post_processing`) pass to
fairlearn as `sensitive_features` - see `faircode/strategies.py`. Every strategy is still scored
against every attribute, so a report can show whether mitigating attribute A helped or hurt
attribute B.

## `core_features` / `proxy_features`

```yaml
core_features: [Sex_Code_Text, MaritalStatus]
proxy_features: [CustodyStatus]
```

- `core_features` - the feature set a mitigated model trains on from S2 onward: "drop the protected
  attributes and their proxies, keep only defensible signal". This is the `fair.py` feature list,
  and also what S3/S4 train on (with the protected attribute carried alongside as
  `sensitive_features`, never as a column of X - see `faircode/strategies.py`).
- `proxy_features` - columns correlated with a protected attribute that a naive model would use to
  reconstruct it. Included in S0-S1, dropped from S2 onward. This is the difference between
  `unfair.py`'s feature list and `fair.py`'s, minus the protected attribute columns themselves.

Every column named anywhere in the manifest (core, proxy, or protected) is label-encoded uniformly
by `faircode.strategies.encode_features` - see that module's docstring for why (uniformity across
wildly different-cardinality categoricals, not one-hot's per-audit blowup risk).

## The five strategies (S0-S4)

| # | Strategy | What it does |
|---|----------|---------------|
| S0 | `baseline` | Every feature, including protected attributes and proxies. The "do nothing" reference. |
| S1 | `unawareness` | Drop the protected attribute only; keep the proxies. The naive fix people assume works. |
| S2 | `unawareness_proxy_removal` | Keep only `core_features`. The `fair.py` method every existing audit uses. |
| S3 | `in_processing` | `fairlearn.reductions.ExponentiatedGradient` with a fairness constraint (`faircode.strategies.FAIRNESS_CONSTRAINT`, default `demographic_parity`). Trains on `core_features`; the protected attribute is passed as `sensitive_features`, never as a model input. |
| S4 | `post_processing` | `fairlearn.postprocessing.ThresholdOptimizer` wrapping a freshly-fit base model; adjusts the decision threshold per group to satisfy the same constraint. |

S4 needs the protected attribute at both fit and predict time as `sensitive_features`; S3 needs it
only at fit time (`ExponentiatedGradient.predict` takes no `sensitive_features` argument at all).
Neither ever uses it as a model feature - so it's never dropped from the working dataset, only
excluded from the column list `X` is built from. Showing that S3/S4 land close to S2's gap - rather than
closing it further - is the basis for a "residual floor" claim: stronger, constraint-based tools
hit roughly the same wall a simple proxy-removal fix does.

## Full example

See `COMPAS/audit.yaml` for a filled-in manifest, or any of the other six audit folders.
