"""Tests for the Fair Code dataset profiler.

Run from the repo root:  pytest tests/ -q
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from faircode import profile
from faircode.detect import classify_name, detect_columns
from faircode.profiler import _age_band, _age_to_numeric, _skewness, parse_reference

ROOT = Path(__file__).resolve().parent.parent


# ── Column detection ────────────────────────────────────────────────────────
def test_classify_keyword_columns():
    assert classify_name("gender") == "sex"
    assert classify_name("Sex_Code_Text") == "sex"
    assert classify_name("race") == "race"
    assert classify_name("Ethnic_Code_Text") == "race"
    assert classify_name("age") == "age"
    assert classify_name("DateOfBirth") == "age"
    assert classify_name("region") == "geography"
    assert classify_name("native.country") == "geography"


def test_classify_rejects_false_positives():
    # The bugs that token-matching fixes: 'age' must not match these.
    assert classify_name("Agency_Text") is None
    assert classify_name("Language") is None
    assert classify_name("LegalStatus") is None


def test_classify_keyword_precedence_for_an_ambiguous_name():
    # 'birth_state' matches both age's 'birth' keyword and geography's
    # 'state' keyword - KEYWORDS' declared order (age before geography)
    # decides it. Locks in the current, intentional precedence so a future
    # reordering of KEYWORDS can't silently reclassify a name like this one
    # with nothing to notice.
    assert classify_name("birth_state") == "age"


def test_classify_rejects_ambiguous_stem_prefix_false_positives():
    # A different failure mode from the precedence case above: these are
    # plain English words that happen to start with a demographic keyword
    # ('race'/'state'/'country'/'city'/'region'), not columns with any
    # actual demographic meaning. Plain prefix matching used to
    # misclassify all of them (#404).
    assert classify_name("raceway") is None
    assert classify_name("statement") is None
    assert classify_name("stateless") is None
    assert classify_name("countryside") is None
    assert classify_name("citycenter") is None
    assert classify_name("regional_manager") is None


def test_detect_includes_low_cardinality_categorical():
    df = pd.DataFrame({"smoker": ["y", "n"] * 25})
    kinds = {d["name"]: d["kind"] for d in detect_columns(df)}
    assert kinds["smoker"] == "categorical"


def test_high_cardinality_id_excluded_from_categorical():
    df = pd.DataFrame({"uid": [f"u{i}" for i in range(100)]})
    assert detect_columns(df) == []  # 100 distinct > MAX_CATEGORICAL_CARD


def test_categorical_cardinality_boundary_at_max_categorical_card():
    from faircode.detect import MAX_CATEGORICAL_CARD

    at_limit = pd.DataFrame({"code": [f"c{i}" for i in range(MAX_CATEGORICAL_CARD)] * 5})
    over_limit = pd.DataFrame({"code": [f"c{i}" for i in range(MAX_CATEGORICAL_CARD + 1)] * 5})

    assert {d["name"] for d in detect_columns(at_limit)} == {"code"}
    assert detect_columns(over_limit) == []


# ── Age helpers ──────────────────────────────────────────────────────────────
def test_age_to_numeric():
    assert _age_to_numeric(34) == 34.0
    assert _age_to_numeric("[70-80)") == 70.0
    assert _age_to_numeric(None) is None
    assert _age_to_numeric("n/a") is None


def test_age_band_edges():
    assert _age_band(0) == "0-18"
    assert _age_band(17) == "0-18"
    assert _age_band(18) == "18-30"
    assert _age_band(80) == "75+"


def test_skewness_symmetric_is_zero():
    assert abs(_skewness([1, 2, 3, 4, 5])) < 1e-9


# ── Core metrics ─────────────────────────────────────────────────────────────
def test_balanced_binary_scores_high():
    df = pd.DataFrame({"sex": ["M", "F"] * 50})
    result = profile(df)
    dim = result["dimensions"][0]
    assert dim["dimension_score"] == 100
    assert math.isclose(dim["entropy_ratio"], 1.0, abs_tol=1e-9)
    assert dim["under_represented"] == []


def test_skewed_distribution_flags_under_represented():
    df = pd.DataFrame({"sex": ["M"] * 98 + ["F"] * 2})
    result = profile(df)
    dim = result["dimensions"][0]
    assert "F" in dim["under_represented"]
    assert dim["dimension_score"] < 50
    assert any("under-represented" in f for f in result["flags"])

def test_min_group_size_tunable():
    df = pd.DataFrame({"sex": ["M"] * 80 + ["F"] * 20})

    # Default threshold (100): both groups are considered small.
    result = profile(df)
    dim = result["dimensions"][0]

    assert all(g["small_group"] for g in dim["groups"])

    flags = result["flags"]
    assert any("'M'" in f and "unreliable" in f for f in flags)
    assert any("'F'" in f and "unreliable" in f for f in flags)

    # Lowering the threshold means neither group is considered small.
    result = profile(df, opts={"min_group_size": 10})
    dim = result["dimensions"][0]

    assert not any(g["small_group"] for g in dim["groups"])

    flags = result["flags"]
    assert not any("fairness metrics may be unreliable" in f for f in flags)
def test_group_shares_carry_wilson_ci():
    from faircode.profiler import _r, _wilson

    dim = profile(pd.DataFrame({"sex": ["M"] * 98 + ["F"] * 2}))["dimensions"][0]
    f = {g["label"]: g for g in dim["groups"]}["F"]
    # Every group now carries a 95% Wilson interval that brackets its point
    # share and never escapes [0, 1].
    assert 0.0 <= f["ci_low"] <= f["share"] <= f["ci_high"] <= 1.0
    # And it matches the Wilson helper exactly (2 successes out of 100).
    lo, hi = _wilson(2, 100)
    assert f["ci_low"] == _r(lo, 4)
    assert f["ci_high"] == _r(hi, 4)
    assert math.isclose(f["ci_low"], 0.0055, abs_tol=5e-4)
    assert math.isclose(f["ci_high"], 0.0700, abs_tol=5e-4)


def test_wilson_interval_shrinks_with_sample_size():
    from faircode.profiler import _wilson

    lo_small, hi_small = _wilson(1, 10)      # 10% off just 10 rows
    lo_big, hi_big = _wilson(100, 1000)      # 10% off 1000 rows
    assert (hi_small - lo_small) > (hi_big - lo_big)   # more data → tighter CI
    assert lo_small <= 0.1 <= hi_small and lo_big <= 0.1 <= hi_big
    assert lo_small >= 0.0 and hi_big <= 1.0
    assert _wilson(5, 0) == (0.0, 0.0)                 # empty dimension is safe


def test_single_group_scores_zero():
    df = pd.DataFrame({"sex": ["M"] * 100})
    # one distinct value -> not a valid categorical (needs >=2), so not detected by
    # cardinality; but the name 'sex' is keyword-detected regardless.
    result = profile(df)
    dim = result["dimensions"][0]
    assert dim["dimension_score"] == 0


def test_empty_demographics_are_explicitly_unmeasured():
    # High-cardinality continuous columns -> nothing detected as demographic.
    df = pd.DataFrame({"price": [i * 1.5 for i in range(100)],
                       "qty": list(range(100))})
    result = profile(df)
    assert result["overall_score"] is None
    assert result["grade"] is None
    assert result["dimensions_detected"] is False
    assert result["note"] == "No demographic columns detected."
    assert result["dimensions"] == []


# ── End-to-end on bundled datasets ───────────────────────────────────────────
@pytest.mark.parametrize("csv", [
    "Insurance Denial/insurance.csv",
    "Benefits Denial/adult.csv",
])
def test_real_datasets_produce_sane_result(csv):
    path = ROOT / csv
    if not path.exists():
        pytest.skip(f"dataset not present: {csv}")
    result = profile(pd.read_csv(path))
    assert result["n_rows"] > 0
    assert 0 <= result["overall_score"] <= 100
    assert result["grade"] in {"A", "B", "C", "D", "F"}
    kinds = {d["kind"] for d in result["dimensions"]}
    assert "age" in kinds and "sex" in kinds  # both datasets have age + sex


# ── Manual overrides (issue #62) ─────────────────────────────────────────────
def test_override_forces_undetected_column():
    # 'gndr' is not a detection keyword, so it's normally missed (or categorical).
    df = pd.DataFrame({"gndr": ["M", "F"] * 50})
    result = profile(df, overrides={"gndr": "sex"})
    dim = next(d for d in result["dimensions"] if d["name"] == "gndr")
    assert dim["kind"] == "sex"


def test_override_ignore_excludes_column():
    df = pd.DataFrame({"sex": ["M", "F"] * 50})
    result = profile(df, overrides={"sex": "ignore"})
    assert result["dimensions"] == []


def test_override_exempts_forced_column_from_cardinality_drop():
    # 60 distinct values would normally be dropped (> MAX_DIMENSION_GROUPS), but a
    # forced non-geography override keeps it.
    df = pd.DataFrame({"code": [f"v{i}" for i in range(60)]})
    assert profile(df)["dimensions"] == []  # dropped by default
    result = profile(df, overrides={"code": "race"})
    assert [d["name"] for d in result["dimensions"]] == ["code"]


# ── Tunable thresholds (issue #63) ───────────────────────────────────────────
def test_min_share_threshold_tunable():
    df = pd.DataFrame({"race": ["White"] * 80 + ["Black"] * 10 + ["Asian"] * 10})
    assert profile(df)["dimensions"][0]["under_represented"] == []
    tuned = profile(df, opts={"min_share": 0.15})["dimensions"][0]
    assert set(tuned["under_represented"]) == {"Asian", "Black"}


def test_imbalance_flag_tunable():
    df = pd.DataFrame({"sex": ["M"] * 80 + ["F"] * 20})  # ratio 4.0×
    assert any("imbalance" in f for f in profile(df)["flags"])
    assert not any("imbalance" in f
                   for f in profile(df, opts={"imbalance_flag": 5.0})["flags"])


# ── Choosable intersection pair (issue #58) ──────────────────────────────────
def test_cross_selects_intersection_pair():
    df = pd.DataFrame({
        "sex": ["M", "F"] * 50,
        "race": ["White", "Black"] * 50,
        "age": [20, 80] * 50,
    })
    default = profile(df)["intersections"]
    crossed = profile(df, opts={"cross": ["race", "age"]})["intersections"]
    assert crossed[0]["dims"] == ["race", "age"]
    assert default[0]["dims"] != ["race", "age"]  # first two were sex × race


def test_cross_with_unknown_column_raises_instead_of_silently_falling_back():
    # A typo'd --cross column used to silently fall back to the first two
    # detected dimensions instead of erroring on the name the caller
    # actually asked for (issue #384).
    df = pd.DataFrame({"sex": ["M", "F"] * 50, "race": ["White", "Black"] * 50})
    with pytest.raises(ValueError, match="nonexistent"):
        profile(df, opts={"cross": ["sex", "nonexistent"]})


# ── Reference baseline (issue #56) ───────────────────────────────────────────
def test_parse_reference_fraction_and_percent():
    frac = parse_reference(pd.DataFrame({"column": ["sex", "sex"],
                                         "group": ["m", "f"], "share": [0.4, 0.6]}))
    pct = parse_reference(pd.DataFrame({"column": ["sex", "sex"],
                                        "group": ["m", "f"], "share": [40, 60]}))
    assert frac == {"sex": {"m": 0.4, "f": 0.6}}
    assert pct == {"sex": {"m": 0.4, "f": 0.6}}  # percentages normalized to fractions


def test_parse_reference_percent_string_values():
    # "49%" used to raise inside float() and get silently dropped by the
    # bare except - the whole --reference file went to {} with no error.
    # The JS engine's parseFloat("49%") == 49 already handled this.
    pct_strings = parse_reference(pd.DataFrame({
        "column": ["sex", "sex"], "group": ["m", "f"], "share": ["49%", "51%"],
    }))
    assert pct_strings == {"sex": {"m": 0.49, "f": 0.51}}


def test_reference_deviation_and_underrepresentation_flag():
    df = pd.DataFrame({"sex": ["M"] * 70 + ["F"] * 30})   # 70/30 actual
    ref = {"sex": {"M": 0.5, "F": 0.5}}
    dim = profile(df, opts={"reference": ref})["dimensions"][0]
    assert "reference" in dim
    assert dim["reference"]["deviation"] == pytest.approx(0.20, abs=1e-9)
    f = next(g for g in dim["reference"]["groups"] if g["label"] == "F")
    assert f["expected"] == 0.5 and f["actual"] == pytest.approx(0.3)
    flags = profile(df, opts={"reference": ref})["flags"]
    assert any("'F' under-represented vs reference" in x for x in flags)


def test_reference_with_no_matching_dimension_raises_instead_of_silently_no_opping():
    # A typo'd reference column ("gendr" instead of "sex") used to silently
    # produce zero reference groups/flags with no error anywhere.
    df = pd.DataFrame({"sex": ["M"] * 70 + ["F"] * 30})
    ref = {"gendr": {"M": 0.5, "F": 0.5}}
    with pytest.raises(ValueError, match="gendr"):
        profile(df, opts={"reference": ref})


def test_intersections_labelize_respects_date_guard():
    # Without the date-vs-age guard, _age_to_numeric() extracts the leading
    # digit run ("15") from both 15/05/1980 and 15/05/1990, banding both into
    # "0-18" - merging two distinct, fully-segregated-by-sex birthdates into
    # one balanced-looking bucket and silently hiding the real absent cells.
    rows = (
        [{"DateOfBirth": "15/05/1980", "sex": "M"}] * 60
        + [{"DateOfBirth": "15/05/1990", "sex": "F"}] * 60
        + [{"DateOfBirth": "20/06/1985", "sex": "M"}] * 5
        + [{"DateOfBirth": "20/06/1985", "sex": "F"}] * 5
    )
    df = pd.DataFrame(rows)
    result = profile(df)
    names = [d["name"] for d in result["dimensions"]]
    assert names == ["DateOfBirth", "sex"]

    cells = result["intersections"][0]["cells"]
    labels = {c["a"] for c in cells}
    assert labels == {"15/05/1980", "15/05/1990"}
    assert {(c["a"], c["b"]) for c in cells} == {
        ("15/05/1980", "F"),
        ("15/05/1990", "M"),
    }


def test_date_column_dropped_not_garbage():
    # A birthdate column must not become 6 nonsense age bands.
    df = pd.DataFrame({
        "DateOfBirth": [f"{1+i%12:02d}/05/19{40+i%50:02d}" for i in range(200)],
        "sex": ["M", "F"] * 100,
    })
    result = profile(df)
    names = {d["name"] for d in result["dimensions"]}
    assert "DateOfBirth" not in names
    assert "sex" in names
