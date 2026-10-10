"""Dataset comparison - representation drift between two profiles.

Implements section 8 of faircode/SPEC.md. Given two profile() results (a
baseline A and a current B, e.g. training vs. production), report how each
demographic dimension's representation shifted. This is pure post-processing
over profile() output - it reads the already-computed group shares and never
re-parses the raw rows - so the JS port in assets/profiler-engine.js mirrors
it exactly and both engines agree.

Drift is quantified with the Population Stability Index (PSI), the standard
population-drift metric in ML monitoring, alongside Total Variation Distance
(TVD) as an easy-to-read companion.
"""

from __future__ import annotations

import math

from .profiler import NO_KIND_DETECTED_FLAG, _is_age_band_label, _r

# A one-sided A/B dimension pair of the same kind whose group labels overlap at least
# this much (Jaccard) is reported as a probable rename (#866). Mirror in the JS engine.
RENAME_MIN_OVERLAP = 0.5

# ── Defaults (SPEC section 7) ───────────────────────────────────────────────
PSI_EPSILON = 0.0001      # share floor so appeared/disappeared groups stay finite
PSI_MODERATE = 0.10       # PSI >= this: moderate drift
PSI_SIGNIFICANT = 0.25    # PSI >= this: significant drift
SCORE_DROP_FLAG = 5       # overall-score drop (points) worth flagging
MISSING_DRIFT_FLAG = 0.05 # missing_pct jump (either direction) worth flagging


def _share_map(dimension: dict) -> dict:
    return {g["label"]: g["share"] for g in dimension["groups"]}


def _psi_term(share_a: float, share_b: float) -> float:
    a = share_a if share_a > 0 else PSI_EPSILON
    b = share_b if share_b > 0 else PSI_EPSILON
    return (b - a) * math.log(b / a)


def _drift_level(psi: float) -> str:
    if psi >= PSI_SIGNIFICANT:
        return "significant"
    if psi >= PSI_MODERATE:
        return "moderate"
    return "none"


def _age_banding_mismatch(dim_a: dict, dim_b: dict) -> bool:
    """True if a kind="age" dimension was banded into numeric ranges on one
    side but left as raw values (dates, most often) on the other. `kind` is
    set from the column name and is identical on both sides regardless, so
    it can't be used to detect this - only the actual group labels can."""
    if dim_a["kind"] != "age" or dim_b["kind"] != "age":
        return False
    labels_a = [g["label"] for g in dim_a["groups"]]
    labels_b = [g["label"] for g in dim_b["groups"]]
    if not labels_a or not labels_b:
        return False
    return (all(_is_age_band_label(l) for l in labels_a)
            != all(_is_age_band_label(l) for l in labels_b))


def _compare_dimension(dim_a: dict, dim_b: dict) -> dict:
    # missing_pct is computed independently of kind/group classification
    # (null_count / n_total, see SPEC section 7), so it's comparable even
    # when the group-share PSI comparison below is skipped for a kind
    # mismatch - a column collapsing to mostly-missing is real drift the
    # non-null-share PSI calculation alone can't see (#461).
    missing_a = dim_a["missing_pct"]
    missing_b = dim_b["missing_pct"]
    missing_delta = _r(missing_b - missing_a, 4)

    kind_mismatch = dim_a["kind"] != dim_b["kind"] or _age_banding_mismatch(dim_a, dim_b)
    if kind_mismatch:
        # A dimension auto-detected to different kinds in A vs B (e.g. one
        # side is date-like, the other plain numeric) labels its groups on
        # totally different schemes - every label looks "appeared" on one
        # side and "disappeared" on the other, producing a PSI many times
        # past the significant threshold that has nothing to do with the
        # underlying population actually changing. Skip the comparison
        # rather than report a number that looks alarming but isn't real.
        return {
            "name": dim_a["name"],
            "kind": dim_a["kind"],
            "kind_a": dim_a["kind"],
            "kind_b": dim_b["kind"],
            "kind_mismatch": True,
            "dimension_score_a": dim_a["dimension_score"],
            "dimension_score_b": dim_b["dimension_score"],
            "dimension_score_delta": dim_b["dimension_score"] - dim_a["dimension_score"],
            "psi": 0.0,
            "tvd": 0.0,
            "drift_level": "none",
            "groups": [],
            "missing_pct_a": missing_a,
            "missing_pct_b": missing_b,
            "missing_pct_delta": missing_delta,
        }

    sa = _share_map(dim_a)
    sb = _share_map(dim_b)
    labels = set(sa) | set(sb)

    groups = []
    psi_total = 0.0
    tvd_total = 0.0
    for label in labels:
        a = sa.get(label, 0.0)
        b = sb.get(label, 0.0)
        psi_total += _psi_term(a, b)
        tvd_total += abs(b - a)
        delta = _r(b - a, 4)
        if a == 0 and b > 0:
            status = "appeared"
        elif a > 0 and b == 0:
            status = "disappeared"
        elif delta == 0.0:
            status = "unchanged"
        else:
            status = "shifted"
        groups.append({
            "label": str(label),
            "share_a": _r(a, 4),
            "share_b": _r(b, 4),
            "share_delta": delta,
            "status": status,
        })
    # most-shifted first, then label asc - deterministic tie-break so JS agrees.
    groups.sort(key=lambda g: (-abs(g["share_delta"]), g["label"]))

    return {
        "name": dim_a["name"],
        "kind": dim_a["kind"],
        "kind_a": dim_a["kind"],
        "kind_b": dim_b["kind"],
        "kind_mismatch": False,
        "dimension_score_a": dim_a["dimension_score"],
        "dimension_score_b": dim_b["dimension_score"],
        "dimension_score_delta": dim_b["dimension_score"] - dim_a["dimension_score"],
        "psi": _r(psi_total, 4),
        "tvd": _r(0.5 * tvd_total, 4),
        # classify on the same rounded value that's displayed, so psi and
        # drift_level never contradict each other at the rounding boundary
        # (e.g. a true PSI of 0.09999... rounding to a displayed 0.1000
        # while classifying as "none" against the unrounded float) - #462.
        "drift_level": _drift_level(_r(psi_total, 4)),
        "groups": groups,
        "missing_pct_a": missing_a,
        "missing_pct_b": missing_b,
        "missing_pct_delta": missing_delta,
    }


def _possible_renames(result_a: dict, result_b: dict, removed: list, added: list) -> list:
    """Pair each A-only dimension with the B-only dimension of the same kind whose
    group labels overlap most (Jaccard >= RENAME_MIN_OVERLAP), each B used once.
    A suggestion only - nothing is compared across the pair (#866)."""
    by_a = {d["name"]: d for d in result_a["dimensions"]}
    by_b = {d["name"]: d for d in result_b["dimensions"]}
    taken: set[str] = set()
    pairs = []
    for name_a in removed:
        labels_a = {g["label"] for g in by_a[name_a]["groups"]}
        best, best_overlap = None, 0.0
        for name_b in added:
            if name_b in taken or by_b[name_b]["kind"] != by_a[name_a]["kind"]:
                continue
            labels_b = {g["label"] for g in by_b[name_b]["groups"]}
            union = labels_a | labels_b
            overlap = len(labels_a & labels_b) / len(union) if union else 0.0
            if overlap > best_overlap:
                best, best_overlap = name_b, overlap
        if best is not None and best_overlap >= RENAME_MIN_OVERLAP:
            taken.add(best)
            pairs.append({"a": name_a, "b": best, "overlap": _r(best_overlap, 4)})
    return pairs


def _build_flags(result_a: dict, result_b: dict, score_delta: int | None,
                 dimensions: list, added: list, removed: list,
                 name_a: str, name_b: str, renames=()) -> tuple[list, bool]:
    """Returns (flags, drift_detected). `flags` is every human-readable
    notice, including a kind-mismatch dimension's "drift comparison
    skipped" message - informational, since the underlying comparison
    genuinely could not be measured (psi/drift_level are already zeroed
    for exactly this dimension in _compare_dimension()). `drift_detected`
    is the narrower, structural signal of whether any *real* representation
    drift was measured - CLI's --fail-on-drift checks this instead of
    `bool(flags)`, so a schema change that made a comparison unmeasurable
    (e.g. one side's ages banded, the other raw) doesn't false-positive as
    "drift detected" the way any flags existing at all would (#472)."""
    flags: list[str] = []
    drift_detected = False
    if score_delta is not None and score_delta <= -SCORE_DROP_FLAG:
        flags.append(
            f"overall representation score dropped {abs(score_delta)} points "
            f"({result_a['overall_score']} → {result_b['overall_score']})"
        )
        drift_detected = True
    for cd in dimensions:
        if abs(cd["missing_pct_delta"]) >= MISSING_DRIFT_FLAG:
            flags.append(
                f"{cd['name']}: missing-data share shifted "
                f"{cd['missing_pct_a'] * 100:.1f}% → {cd['missing_pct_b'] * 100:.1f}%"
            )
            drift_detected = True
        if cd.get("implausible_a", 0) != cd.get("implausible_b", 0):
            flags.append(
                f"{cd['name']}: implausible age values differ ({cd['implausible_a']} in "
                f"{name_a}, {cd['implausible_b']} in {name_b}) - they were treated as "
                f"missing in each, so check the age shares for artefacts"
            )
        if cd["kind_mismatch"]:
            if cd["kind_a"] != cd["kind_b"]:
                flags.append(
                    f"{cd['name']}: detected as different kinds in {name_a} "
                    f"({cd['kind_a']}) and {name_b} ({cd['kind_b']}) - drift "
                    f"comparison skipped"
                )
            else:
                flags.append(
                    f"{cd['name']}: age values are banded (e.g. \"18-30\") in "
                    f"one dataset but left raw in the other - drift "
                    f"comparison skipped"
                )
            continue
        if cd["drift_level"] != "none":
            flags.append(
                f"{cd['name']}: {cd['drift_level']} representation drift "
                f"(PSI {cd['psi']:.2f})"
            )
            drift_detected = True
        for g in cd["groups"]:
            if g["status"] == "appeared":
                flags.append(
                    f"{cd['name']}: '{g['label']}' appeared "
                    f"({g['share_a'] * 100:.1f}% → {g['share_b'] * 100:.1f}%)"
                )
                drift_detected = True
            elif g["status"] == "disappeared":
                flags.append(
                    f"{cd['name']}: '{g['label']}' disappeared "
                    f"({g['share_a'] * 100:.1f}% → {g['share_b'] * 100:.1f}%)"
                )
                drift_detected = True
    for n in added:
        flags.append(f"dimension '{n}' is present only in {name_b}")
        drift_detected = True
    for n in removed:
        flags.append(f"dimension '{n}' is present only in {name_a}")
        drift_detected = True
    for r in renames:
        flags.append(
            f"'{r['a']}' ({name_a}) and '{r['b']}' ({name_b}) look like the same dimension "
            f"({r['overlap'] * 100:.0f}% of their group labels overlap) - rename one column "
            f"so the names match to compare them"
        )
    for name, result in ((name_a, result_a), (name_b, result_b)):
        if NO_KIND_DETECTED_FLAG in result.get("flags", ()):
            flags.append(
                f"{name}: no column name was recognised as sex, race, age or geography, so "
                f"every dimension is a plain categorical - map columns with --map COL=KIND"
            )
    return flags, drift_detected


def compare(result_a: dict, result_b: dict, name_a="A", name_b="B") -> dict:
    """Compare two profile() results for representation drift. See SPEC section 8."""
    dims_a = {d["name"]: d for d in result_a["dimensions"]}
    dims_b = {d["name"]: d for d in result_b["dimensions"]}

    shared = [d["name"] for d in result_a["dimensions"] if d["name"] in dims_b]
    added = [d["name"] for d in result_b["dimensions"] if d["name"] not in dims_a]
    removed = [d["name"] for d in result_a["dimensions"] if d["name"] not in dims_b]

    dimensions = [_compare_dimension(dims_a[n], dims_b[n]) for n in shared]
    # Data-quality carry-over (#868): ages treated as implausible on either side, as
    # optional keys so the common result shape is unchanged.
    for cd in dimensions:
        imp_a = dims_a[cd["name"]].get("implausible_values", 0)
        imp_b = dims_b[cd["name"]].get("implausible_values", 0)
        if imp_a or imp_b:
            cd["implausible_a"], cd["implausible_b"] = imp_a, imp_b
    renames = _possible_renames(result_a, result_b, removed, added)
    scores = (result_a["overall_score"], result_b["overall_score"])
    score_delta = scores[1] - scores[0] if None not in scores else None
    flags, drift_detected = _build_flags(result_a, result_b, score_delta, dimensions,
                                        added, removed, name_a, name_b, renames)

    result = {
        "a": {"name": name_a, "n_rows": result_a["n_rows"],
              "overall_score": result_a["overall_score"], "grade": result_a["grade"],
              "dimensions_detected": result_a["dimensions_detected"],
              "note": result_a["note"]},
        "b": {"name": name_b, "n_rows": result_b["n_rows"],
              "overall_score": result_b["overall_score"], "grade": result_b["grade"],
              "dimensions_detected": result_b["dimensions_detected"],
              "note": result_b["note"]},
        "score_delta": score_delta,
        "dimensions": dimensions,
        "added_dimensions": added,
        "removed_dimensions": removed,
        "flags": flags,
        "drift_detected": drift_detected,
    }
    if renames:
        result["possible_renames"] = renames
    return result
