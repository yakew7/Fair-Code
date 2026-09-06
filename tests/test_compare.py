"""Tests for the dataset-comparison (representation drift) module.

Run from the repo root:  pytest tests/ -q
"""

import pandas as pd

from faircode import compare, profile
from faircode.compare import _drift_level, _psi_term


# ── Helpers ──────────────────────────────────────────────────────────────────
def _find(dims, name):
    return next(d for d in dims if d["name"] == name)


def _group(groups, label):
    return next(g for g in groups if g["label"] == label)


# ── PSI internals ─────────────────────────────────────────────────────────────
def test_psi_term_zero_when_shares_equal():
    assert _psi_term(0.5, 0.5) == 0.0


def test_psi_term_positive_when_shares_differ():
    # PSI contributions are always non-negative regardless of shift direction.
    assert _psi_term(0.6, 0.8) > 0
    assert _psi_term(0.8, 0.6) > 0


def test_drift_level_thresholds():
    assert _drift_level(0.05) == "none"
    assert _drift_level(0.10) == "moderate"
    assert _drift_level(0.24) == "moderate"
    assert _drift_level(0.25) == "significant"


# ── No drift: identical datasets ──────────────────────────────────────────────
def test_identical_datasets_show_no_drift():
    df = pd.DataFrame({"sex": ["M", "F"] * 100})
    cmp = compare(profile(df), profile(df))
    assert cmp["score_delta"] == 0
    dim = _find(cmp["dimensions"], "sex")
    assert dim["psi"] == 0.0
    assert dim["tvd"] == 0.0
    assert dim["drift_level"] == "none"
    assert all(g["status"] == "shifted" and g["share_delta"] == 0.0
               for g in dim["groups"])
    assert cmp["flags"] == []


# ── Significant drift: distribution collapses onto one group ──────────────────
def test_large_shift_is_significant_and_flagged():
    a = pd.DataFrame({"race": ["White"] * 50 + ["Black"] * 50})   # 50/50
    b = pd.DataFrame({"race": ["White"] * 90 + ["Black"] * 10})   # 90/10
    cmp = compare(profile(a), profile(b), name_a="a.csv", name_b="b.csv")
    dim = _find(cmp["dimensions"], "race")
    assert dim["drift_level"] == "significant"
    assert dim["psi"] >= 0.25
    white = _group(dim["groups"], "White")
    assert white["share_delta"] > 0
    assert any("significant representation drift" in f for f in cmp["flags"])


# ── Appeared / disappeared groups ─────────────────────────────────────────────
def test_appeared_and_disappeared_groups():
    a = pd.DataFrame({"region": ["North"] * 60 + ["South"] * 40})
    b = pd.DataFrame({"region": ["North"] * 60 + ["West"] * 40})
    cmp = compare(profile(a), profile(b))
    dim = _find(cmp["dimensions"], "region")
    south = _group(dim["groups"], "South")
    west = _group(dim["groups"], "West")
    assert south["status"] == "disappeared"
    assert west["status"] == "appeared"
    assert any("'South' disappeared" in f for f in cmp["flags"])
    assert any("'West' appeared" in f for f in cmp["flags"])


# ── Added / removed dimensions ────────────────────────────────────────────────
def test_added_and_removed_dimensions():
    a = pd.DataFrame({"sex": ["M", "F"] * 50, "race": ["White", "Black"] * 50})
    b = pd.DataFrame({"sex": ["M", "F"] * 50, "region": ["North", "South"] * 50})
    cmp = compare(profile(a), profile(b), name_a="a.csv", name_b="b.csv")
    assert cmp["removed_dimensions"] == ["race"]
    assert cmp["added_dimensions"] == ["region"]
    # sex is shared, so it still gets compared
    assert _find(cmp["dimensions"], "sex")["drift_level"] == "none"
    assert any("only in b.csv" in f for f in cmp["flags"])
    assert any("only in a.csv" in f for f in cmp["flags"])


# ── Groups ordered by descending absolute shift ───────────────────────────────
def test_groups_ordered_by_shift_magnitude():
    a = pd.DataFrame({"race": ["White"] * 50 + ["Black"] * 30 + ["Asian"] * 20})
    b = pd.DataFrame({"race": ["White"] * 55 + ["Black"] * 10 + ["Asian"] * 35})
    dim = _find(compare(profile(a), profile(b))["dimensions"], "race")
    deltas = [abs(g["share_delta"]) for g in dim["groups"]]
    assert deltas == sorted(deltas, reverse=True)


# ── Age-banding mismatch (#318) ─────────────────────────────────────────────
def test_age_banding_mismatch_skips_drift_instead_of_reporting_100_percent():
    # A: raw birthdates (never banded, per _looks_like_dates()). B: numeric
    # ages (banded into "18-30"/"30-45"). `kind` is "age" on both sides -
    # set from the column name, not the values - so it alone can't catch
    # this; before the fix, every label showed as appeared/disappeared and
    # PSI came out far past the "significant" threshold for no real reason.
    df_a = pd.DataFrame({"DOB": ["15/05/1980"] * 50 + ["20/06/1985"] * 50})
    df_b = pd.DataFrame({"DOB": [18] * 50 + [35] * 50})
    cmp = compare(profile(df_a), profile(df_b))
    dim = _find(cmp["dimensions"], "DOB")

    assert dim["kind_mismatch"] is True
    assert dim["kind_a"] == dim["kind_b"] == "age"
    assert dim["psi"] == 0.0
    assert dim["drift_level"] == "none"
    assert dim["groups"] == []
    assert any("banded" in f and "DOB" in f for f in cmp["flags"])


def test_matching_age_banding_still_compares_normally():
    # Same-shape ages on both sides (both banded) must not be treated as a
    # mismatch - only an asymmetry between the two sides should skip it.
    df_a = pd.DataFrame({"age": [20] * 50 + [40] * 50})
    df_b = pd.DataFrame({"age": [20] * 30 + [40] * 70})
    cmp = compare(profile(df_a), profile(df_b))
    dim = _find(cmp["dimensions"], "age")

    assert dim["kind_mismatch"] is False
    assert dim["groups"]


# ── Score-drop flag ───────────────────────────────────────────────────────────
def test_overall_score_drop_is_flagged():
    a = pd.DataFrame({"sex": ["M", "F"] * 100})            # balanced -> high score
    b = pd.DataFrame({"sex": ["M"] * 190 + ["F"] * 10})    # skewed   -> low score
    cmp = compare(profile(a), profile(b))
    assert cmp["score_delta"] < 0
    assert any("overall representation score dropped" in f for f in cmp["flags"])


def test_unmeasured_profile_has_no_score_delta():
    measured = profile(pd.DataFrame({"sex": ["M", "F"] * 20}))
    unmeasured = profile(pd.DataFrame({"id": range(40)}))

    cmp = compare(measured, unmeasured)

    assert cmp["score_delta"] is None
    assert cmp["b"]["dimensions_detected"] is False
    assert not any("overall representation score dropped" in f for f in cmp["flags"])
