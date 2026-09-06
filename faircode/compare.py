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

from .profiler import _is_age_band_label, _r

# ── Defaults (SPEC section 7) ───────────────────────────────────────────────
PSI_EPSILON = 0.0001      # share floor so appeared/disappeared groups stay finite
PSI_MODERATE = 0.10       # PSI >= this: moderate drift
PSI_SIGNIFICANT = 0.25    # PSI >= this: significant drift
SCORE_DROP_FLAG = 5       # overall-score drop (points) worth flagging


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
        if a == 0 and b > 0:
            status = "appeared"
        elif a > 0 and b == 0:
            status = "disappeared"
        else:
            status = "shifted"
        groups.append({
            "label": str(label),
            "share_a": _r(a, 4),
            "share_b": _r(b, 4),
            "share_delta": _r(b - a, 4),
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
        "drift_level": _drift_level(psi_total),
        "groups": groups,
    }


def _build_flags(result_a: dict, result_b: dict, score_delta: int | None,
                 dimensions: list, added: list, removed: list,
                 name_a: str, name_b: str) -> list:
    flags: list[str] = []
    if score_delta is not None and score_delta <= -SCORE_DROP_FLAG:
        flags.append(
            f"overall representation score dropped {abs(score_delta)} points "
            f"({result_a['overall_score']} → {result_b['overall_score']})"
        )
    for cd in dimensions:
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
        for g in cd["groups"]:
            if g["status"] == "appeared":
                flags.append(
                    f"{cd['name']}: '{g['label']}' appeared "
                    f"({g['share_a'] * 100:.1f}% → {g['share_b'] * 100:.1f}%)"
                )
            elif g["status"] == "disappeared":
                flags.append(
                    f"{cd['name']}: '{g['label']}' disappeared "
                    f"({g['share_a'] * 100:.1f}% → {g['share_b'] * 100:.1f}%)"
                )
    for n in added:
        flags.append(f"dimension '{n}' is present only in {name_b}")
    for n in removed:
        flags.append(f"dimension '{n}' is present only in {name_a}")
    return flags


def compare(result_a: dict, result_b: dict, name_a="A", name_b="B") -> dict:
    """Compare two profile() results for representation drift. See SPEC section 8."""
    dims_a = {d["name"]: d for d in result_a["dimensions"]}
    dims_b = {d["name"]: d for d in result_b["dimensions"]}

    shared = [d["name"] for d in result_a["dimensions"] if d["name"] in dims_b]
    added = [d["name"] for d in result_b["dimensions"] if d["name"] not in dims_a]
    removed = [d["name"] for d in result_a["dimensions"] if d["name"] not in dims_b]

    dimensions = [_compare_dimension(dims_a[n], dims_b[n]) for n in shared]
    scores = (result_a["overall_score"], result_b["overall_score"])
    score_delta = scores[1] - scores[0] if None not in scores else None
    flags = _build_flags(result_a, result_b, score_delta, dimensions,
                         added, removed, name_a, name_b)

    return {
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
    }
