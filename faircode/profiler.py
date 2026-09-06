"""Core representation-profiling engine (pure pandas, no scikit-learn).

Implements faircode/SPEC.md. The single public entry point is `profile(df)`,
which returns a plain dict matching the result shape in SPEC section 6. The JS
port in assets/profiler-engine.js mirrors this logic exactly.
"""

from __future__ import annotations

import math
import re

import pandas as pd

from .detect import VALID_KINDS, detect_columns

# ── Defaults (SPEC section 7) ───────────────────────────────────────────────
MIN_SHARE_THRESHOLD = 0.05
INTERSECTION_FLOOR = 0.01
IMBALANCE_FLAG = 3.0
MISSING_FLAG = 0.05
REFERENCE_DEVIATION_FLAG = 0.05  # under-representation vs a reference baseline
AGE_BANDS = [0, 18, 30, 45, 60, 75]  # left-closed edges; final band is "75+"
MAX_DIMENSION_GROUPS = 50  # drop identifier/date-like columns (geography exempt)
MIN_GROUP_SIZE = 100  # warn when a subgroup has fewer than N rows (default: 100)

_DATE_RE = re.compile(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}")

# 95% two-sided normal quantile, shared verbatim with the JS port so both engines
# return identical Wilson bounds (SPEC section 3).
Z95 = 1.959963984540054


def _wilson(count: int, n: int) -> tuple:
    """95% Wilson score interval for the proportion count/n.

    Deterministic (no resampling), so the Python engine and the JS port in
    assets/profiler-engine.js produce identical bounds. The Wilson interval is
    preferred over the normal approximation because it stays inside [0, 1] and
    behaves sensibly for small groups and extreme shares - exactly the
    under-represented cases this profiler is built to surface.
    """
    if n <= 0:
        return 0.0, 0.0
    p = count / n
    z2 = Z95 * Z95
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (Z95 / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    lo = center - margin
    hi = center + margin
    return (lo if lo > 0 else 0.0), (hi if hi < 1 else 1.0)

# Tunable knobs (SPEC section 7); overridable per call via profile(opts=...).
_DEFAULT_OPTS = {
    "min_share": MIN_SHARE_THRESHOLD,
    "intersection_floor": INTERSECTION_FLOOR,
    "imbalance_flag": IMBALANCE_FLAG,
    "missing_flag": MISSING_FLAG,
    "reference_flag": REFERENCE_DEVIATION_FLAG,
    "min_group_size": MIN_GROUP_SIZE,  # warn when a subgroup has fewer than N rows
    "cross": None,       # [colA, colB] to force the intersection pair (SPEC 4)
    "reference": None,   # {column: {group: expected_share}} baseline (SPEC 8)
}


def _resolve_opts(opts) -> dict:
    o = dict(_DEFAULT_OPTS)
    if opts:
        o.update({k: v for k, v in opts.items() if v is not None})
    return o


def _r(x, dp: int = 0):
    """Round half-up, matching JavaScript's Math.round so both engines agree.

    Python's built-in round() uses banker's rounding (88.5 -> 88), which would
    diverge from the JS port (88.5 -> 89). floor(x*f + 0.5) mirrors Math.round.
    """
    if x is None:
        return None
    f = 10 ** dp
    val = math.floor(x * f + 0.5) / f
    return int(val) if dp == 0 else val


# ── Age handling (SPEC section 2) ───────────────────────────────────────────
def _looks_like_dates(series) -> bool:
    """True if a sample of values look like dates (e.g. birthdates), not ages."""
    sample = series.dropna().astype(str).head(50)
    if len(sample) == 0:
        return False
    hits = sum(1 for v in sample if _DATE_RE.search(v))
    return hits / len(sample) > 0.5



def _age_to_numeric(value):
    """Coerce one age cell to a numeric lower-bound, or None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        match = re.search(r"[+-]?\d+(?:\.\d+)?", str(value))
        if match is None:
            return None
        numeric = float(match.group())
    return numeric if math.isfinite(numeric) and numeric >= AGE_BANDS[0] else None


def _age_band(num) -> str | None:
    if num is None or not math.isfinite(num) or num < AGE_BANDS[0]:
        return None
    edges = AGE_BANDS
    for i in range(len(edges) - 1):
        if edges[i] <= num < edges[i + 1]:
            return f"{edges[i]}-{edges[i + 1]}"
    return f"{edges[-1]}+"


_AGE_BAND_LABELS = {f"{AGE_BANDS[i]}-{AGE_BANDS[i + 1]}" for i in range(len(AGE_BANDS) - 1)}
_AGE_BAND_LABELS.add(f"{AGE_BANDS[-1]}+")


def _is_age_band_label(label) -> bool:
    """True if `label` is exactly one of _age_band()'s possible outputs.

    compare() uses this to detect a kind="age" dimension banded on one side
    (numeric ages) but not the other (raw dates, which _dimension() never
    bands - see _looks_like_dates()): `kind` alone can't tell the two apart,
    since it's set from the column name and is identical either way."""
    return str(label) in _AGE_BAND_LABELS


def _skewness(values: list[float]):
    """Fisher–Pearson sample skewness; None if undefined."""
    n = len(values)
    if n < 3:
        return None
    mean = sum(values) / n
    m2 = sum((x - mean) ** 2 for x in values) / n
    m3 = sum((x - mean) ** 3 for x in values) / n
    if m2 == 0:
        return None
    return m3 / (m2 ** 1.5)


# ── Per-dimension metrics (SPEC section 3) ──────────────────────────────────
def _analyze_groups(labels_counts: dict, n_total: int, null_count: int,
                    skewness=None, min_share_threshold=MIN_SHARE_THRESHOLD, min_group_size=MIN_GROUP_SIZE) -> dict:
    """Given {label: count} for non-null values, compute the dimension metrics."""
    n_nonnull = sum(labels_counts.values())
    groups = []
    for label, count in labels_counts.items():
        share = count / n_nonnull if n_nonnull else 0.0
        lo, hi = _wilson(count, n_nonnull)
        groups.append({"label": str(label), "count": int(count), "share": share,
                       "ci_low": _r(lo, 4), "ci_high": _r(hi, 4),
                       "small_group": count < min_group_size})
    # count desc, then label asc - deterministic tie-break so the JS port agrees.
    groups.sort(key=lambda g: (-g["count"], g["label"]))

    shares = [g["share"] for g in groups]
    k = len(shares)
    min_share = min(shares) if shares else 0.0
    max_share = max(shares) if shares else 0.0
    imbalance_ratio = (max_share / min_share) if min_share > 0 else float("inf")

    if k <= 1:
        entropy_ratio = 0.0
    else:
        H = -sum(p * math.log(p) for p in shares if p > 0)
        entropy_ratio = H / math.log(k)

    under = [g["label"] for g in groups if g["share"] < min_share_threshold]

    return {
        "n_groups": k,
        "dimension_score": _r(entropy_ratio * 100),
        "entropy_ratio": _r(entropy_ratio, 4),
        "imbalance_ratio": (_r(imbalance_ratio, 2)
                            if imbalance_ratio != float("inf") else None),
        "min_share": _r(min_share, 4),
        "missing_pct": _r(null_count / n_total, 4) if n_total else 0.0,
        "skewness": _r(skewness, 4) if skewness is not None else None,
        "groups": groups,
        "under_represented": under,
    }


def _dimension(df: pd.DataFrame, name: str, kind: str,
               min_share=MIN_SHARE_THRESHOLD, min_group_size=MIN_GROUP_SIZE) -> dict:
    col = df[name]
    n_total = len(df)
    skewness = None

    if kind == "age" and not _looks_like_dates(col):
        nums = [_age_to_numeric(v) for v in col]
        numeric_vals = [n for n in nums if n is not None]
        # Numeric age → bands; if nothing parsed numerically, fall back to raw.
        if numeric_vals:
            skewness = _skewness(numeric_vals)
            bands = [_age_band(n) for n in nums]
            null_count = sum(1 for b in bands if b is None)
            counts: dict = {}
            for b in bands:
                if b is not None:
                    counts[b] = counts.get(b, 0) + 1
            result = _analyze_groups(counts, n_total, null_count, skewness, min_share, min_group_size)
            result.update({"name": name, "kind": kind})
            return result

    # Categorical path (sex, race, geography, generic categorical, non-numeric age).
    null_count = int(col.isna().sum())
    vc = col.dropna().value_counts()
    counts = {label: int(c) for label, c in vc.items()}
    result = _analyze_groups(counts, n_total, null_count, skewness, min_share, min_group_size)
    result.update({"name": name, "kind": kind})
    return result


# ── Intersectional gaps (SPEC section 4) ────────────────────────────────────
def _pick_cross(dims: list[dict], cross) -> tuple:
    """Choose the two dimensions to cross: an explicit [colA, colB] if both are
    detected, otherwise the first two (SPEC section 4)."""
    if cross and len(cross) == 2:
        by_name = {d["name"]: d for d in dims}
        if cross[0] in by_name and cross[1] in by_name:
            return by_name[cross[0]], by_name[cross[1]]
    return dims[0], dims[1]


def _intersections(df: pd.DataFrame, dims: list[dict],
                   intersection_floor=INTERSECTION_FLOOR, cross=None) -> list[dict]:
    if len(dims) < 2:
        return []
    a, b = _pick_cross(dims, cross)
    n_total = len(df)
    floor = intersection_floor * n_total

    def labelize(name, kind):
        if kind == "age" and not _looks_like_dates(df[name]):
            nums = [_age_to_numeric(v) for v in df[name]]
            if any(n is not None for n in nums):
                return pd.Series([_age_band(n) for n in nums], index=df.index)
        return df[name].astype("object")

    sa = labelize(a["name"], a["kind"])
    sb = labelize(b["name"], b["kind"])
    ct = pd.crosstab(sa, sb)

    cells = []
    for av in ct.index:
        for bv in ct.columns:
            count = int(ct.loc[av, bv])
            if count == 0 or count < floor:
                cells.append({"a": str(av), "b": str(bv), "count": count})
    if not cells:
        return []
    cells.sort(key=lambda c: (c["a"], c["b"]))  # deterministic order, matches JS
    return [{"dims": [a["name"], b["name"]], "cells": cells}]


# ── Flags + grade (SPEC sections 5 & 6) ─────────────────────────────────────
def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _apply_reference(dimensions: list[dict], reference: dict,
                     reference_flag=REFERENCE_DEVIATION_FLAG) -> list[str]:
    """Annotate each dimension with expected-vs-actual shares against a reference
    baseline (SPEC section 8) and return under-representation flags."""
    flags: list[str] = []
    for d in dimensions:
        ref = reference.get(d["name"])
        if not ref:
            continue
        actual = {g["label"]: g["share"] for g in d["groups"]}
        labels = set(actual) | set(ref)
        groups = []
        deviation = 0.0
        for label in labels:
            exp = ref.get(label, 0.0)
            act = actual.get(label, 0.0)
            delta = act - exp
            deviation += abs(delta)
            groups.append({"label": str(label), "expected": _r(exp, 4),
                           "actual": _r(act, 4), "delta": _r(delta, 4)})
            if exp - act >= reference_flag:
                flags.append(
                    f"{d['name']}: '{label}' under-represented vs reference "
                    f"({act * 100:.1f}% vs {exp * 100:.1f}% expected)"
                )
        groups.sort(key=lambda g: (-abs(g["delta"]), g["label"]))
        d["reference"] = {"deviation": _r(0.5 * deviation, 4), "groups": groups}
    return flags


def _build_flags(dimensions: list[dict], intersections: list[dict],
                 imbalance_flag=IMBALANCE_FLAG, missing_flag=MISSING_FLAG) -> list[str]:
    flags: list[str] = []
    for d in dimensions:
        for g in d["groups"]:
            if g["label"] in d["under_represented"]:
                flags.append(
                    f"{d['name']}: '{g['label']}' is under-represented "
                    f"({g['share'] * 100:.1f}%)"
                )
            if g.get("small_group"):
                flags.append(
                    f"{d['name']}: '{g['label']}' has only {g['count']} rows; "
                    f"fairness metrics may be unreliable"
                )
        if d["imbalance_ratio"] is not None and d["imbalance_ratio"] >= imbalance_flag:
            flags.append(
                f"{d['name']}: imbalance ratio {d['imbalance_ratio']:.1f}× "
                f"between largest and smallest group"
            )
        elif d["imbalance_ratio"] is None and d["n_groups"] > 1:
            flags.append(f"{d['name']}: a subgroup is effectively absent (0 rows)")
        if d["missing_pct"] >= missing_flag:
            flags.append(
                f"{d['name']}: {d['missing_pct'] * 100:.1f}% of values are missing"
            )
    for inter in intersections:
        a, b = inter["dims"]
        for cell in inter["cells"]:
            kind = "absent" if cell["count"] == 0 else f"only {cell['count']} rows"
            flags.append(
                f"{a}='{cell['a']}' × {b}='{cell['b']}' is {kind}"
            )
    return flags


_REF_COLUMN_ALIASES = ("column", "dimension", "dim")
_REF_GROUP_ALIASES = ("group", "value", "label", "category")
_REF_SHARE_ALIASES = ("share", "expected", "expected_share", "proportion",
                      "percent", "pct")


def parse_reference(df: pd.DataFrame) -> dict:
    """Parse a long-format reference baseline into {column: {group: share}}.

    Expected headers (case-insensitive): a column identifier, a group/value, and
    a share. Shares may be fractions (0.51) or percentages (51) - if any value
    exceeds 1.5 the whole table is read as percentages. See SPEC section 8.
    """
    lower = {str(c).strip().lower(): c for c in df.columns}

    def pick(aliases):
        for a in aliases:
            if a in lower:
                return lower[a]
        return None

    col_c = pick(_REF_COLUMN_ALIASES)
    grp_c = pick(_REF_GROUP_ALIASES)
    shr_c = pick(_REF_SHARE_ALIASES)
    if not (col_c and grp_c and shr_c):
        raise ValueError("reference needs column, group, and share columns "
                         "(e.g. headers: column,group,share)")

    raw = []
    for _, row in df.iterrows():
        value = row[shr_c]
        if isinstance(value, str) and value.strip().endswith("%"):
            value = value.strip()[:-1]
        try:
            share = float(value)
        except (TypeError, ValueError):
            continue
        raw.append((str(row[col_c]).strip(), str(row[grp_c]).strip(), share))

    scale = 100.0 if any(s > 1.5 for _, _, s in raw) else 1.0
    reference: dict = {}
    for col, grp, share in raw:
        reference.setdefault(col, {})[grp] = share / scale
    return reference


def profile(df: pd.DataFrame, overrides=None, opts=None) -> dict:
    """Profile a DataFrame for demographic representation. See SPEC section 6.

    `overrides` is an optional {column: kind} map (SPEC section 1) that forces a
    column's dimension when auto-detection misses or mislabels it.

    `opts` is an optional dict of tunable knobs (SPEC section 7): `min_share`,
    `intersection_floor`, `imbalance_flag`, `missing_flag`, `reference_flag`,
    `min_group_size`, a `cross` pair [colA, colB] for the intersection (SPEC 4),
    and a `reference` baseline {column: {group: expected_share}} (SPEC 8).

    """
    overrides = overrides or {}
    o = _resolve_opts(opts)
    detected = detect_columns(df, overrides)
    dimensions = [_dimension(df, d["name"], d["kind"], o["min_share"], o["min_group_size"])
                  for d in detected]
    # Drop identifier/date-like columns that exploded into many groups; geography
    # (cities, regions) legitimately has high cardinality, so it is exempt - as is
    # any column the user explicitly mapped (their intent overrides the heuristic).
    forced = {name for name, kind in overrides.items() if kind in VALID_KINDS}
    dimensions = [d for d in dimensions
                  if d["kind"] == "geography" or d["name"] in forced
                  or d["n_groups"] <= MAX_DIMENSION_GROUPS]
    kept_names = {d["name"] for d in dimensions}
    detected = [d for d in detected if d["name"] in kept_names]
    if o["cross"]:
        unknown = [name for name in o["cross"] if name not in kept_names]
        if unknown:
            raise ValueError(
                "cross column(s) don't match any profiled dimension: " + ", ".join(unknown))
    intersections = _intersections(df, detected, o["intersection_floor"], o["cross"])

    ref_flags = []
    if o["reference"]:
        if not any(d["name"] in o["reference"] for d in dimensions):
            raise ValueError(
                "reference file's column(s) don't match any profiled dimension: "
                + ", ".join(sorted(o["reference"])))
        ref_flags = _apply_reference(dimensions, o["reference"], o["reference_flag"])

    dimensions_detected = bool(dimensions)
    overall = (_r(sum(d["dimension_score"] for d in dimensions) / len(dimensions))
               if dimensions_detected else None)

    return {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "overall_score": overall,
        "grade": _grade(overall) if overall is not None else None,
        "dimensions_detected": dimensions_detected,
        "note": None if dimensions_detected else "No demographic columns detected.",
        "dimensions": dimensions,
        "intersections": intersections,
        "flags": _build_flags(dimensions, intersections,
                              o["imbalance_flag"], o["missing_flag"]) + ref_flags,
    }
