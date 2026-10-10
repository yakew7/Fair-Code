"""Tests for the Fair Code dataset profiler.

Run from the repo root:  pytest tests/ -q
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from faircode import profile
from faircode.detect import classify_name, detect_columns
from faircode.profiler import (
    _age_band,
    _age_to_numeric,
    _looks_like_dates,
    _skewness,
    parse_reference,
)

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


def test_age_to_numeric_rejects_negative_sentinels_in_numeric_and_string_cells():
    assert _age_to_numeric(-1) is None
    assert _age_to_numeric(-999.0) is None
    assert _age_to_numeric("-5") is None
    assert _age_to_numeric("unknown: -1") is None


def test_age_band_edges():
    assert _age_band(-1) is None
    assert _age_band(0) == "0-18"
    assert _age_band(17) == "0-18"
    assert _age_band(18) == "18-30"
    assert _age_band(80) == "75+"


def test_date_detection_samples_appended_values_across_the_column():
    ages = list(range(20, 80))
    dates = ["1985-03-21", "1990-07-14", "2001-11-02"] * 20

    assert _looks_like_dates(pd.Series(ages + dates)) is True


def test_date_detection_samples_large_columns_beyond_the_head():
    ages = list(range(20, 60)) * 4
    dates = ["1985-03-21", "1990-07-14"] * 90

    assert _looks_like_dates(pd.Series(ages + dates)) is True
def test_negative_age_sentinels_are_missing_instead_of_an_elderly_group():
    df = pd.DataFrame({"age": [25, 30, 45, 22, 60] + [-1] * 10})

    dim = profile(df)["dimensions"][0]

    assert "75+" not in {group["label"] for group in dim["groups"]}
    assert sum(group["count"] for group in dim["groups"]) == 5
    assert dim["missing_pct"] == 0.6667


def test_non_numeric_age_sentinels_get_their_own_categorical_group():
    # Regression test for #487: free-text age responses with no embedded
    # number ("unknown", "prefer not to say") used to silently fold into
    # missing_pct, indistinguishable from a genuinely blank cell -
    # contradicting SPEC.md section 2's "anything else: treat as
    # categorical" rule.
    df = pd.DataFrame({"age": [25, 30, 45, "unknown", "unknown", "unknown",
                                "prefer not to say", 22, 33, 41]})

    dim = profile(df)["dimensions"][0]

    labels = {group["label"]: group["count"] for group in dim["groups"]}
    assert labels["unknown"] == 3
    assert labels["prefer not to say"] == 1
    assert dim["missing_pct"] == 0.0
    assert dim["n_groups"] == 5


def test_non_numeric_age_sentinels_are_distinct_from_genuine_missing_cells():
    # A real None/NaN cell must still count toward missing_pct, not get
    # folded into a categorical sentinel group alongside real free text.
    df = pd.DataFrame({"age": [25, 30, 45, None, float("nan"), "unknown",
                                22, 33, 41, 29]})

    dim = profile(df)["dimensions"][0]

    labels = {group["label"]: group["count"] for group in dim["groups"]}
    assert labels["unknown"] == 1
    assert dim["missing_pct"] == 0.2


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


def test_max_categorical_card_tunable():
    # 30 distinct values - outside the default [2, 20] generic-categorical window.
    df = pd.DataFrame({"occupation_code": [f"occ_{i % 30}" for i in range(300)]})

    result = profile(df)
    assert result["dimensions"] == []

    result = profile(df, opts={"max_categorical_card": 30})
    assert [d["name"] for d in result["dimensions"]] == ["occupation_code"]


def test_max_dimension_groups_tunable():
    # "ethnicity" keyword-matches the "race" kind directly (not the generic
    # categorical fallback, so max_categorical_card doesn't apply), with 60
    # distinct values - past the default 50-group identifier/date-like cutoff.
    df = pd.DataFrame({"ethnicity": [f"group_{i % 60}" for i in range(600)]})

    result = profile(df)
    assert result["dimensions"] == []

    result = profile(df, opts={"max_dimension_groups": 60})
    assert [d["name"] for d in result["dimensions"]] == ["ethnicity"]


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


@pytest.mark.parametrize("opts, message", [
    ({"min_share": 1.5}, "min_share must be between 0 and 1"),
    ({"min_share": -0.1}, "min_share must be between 0 and 1"),
    ({"intersection_floor": 2.0}, "intersection_floor must be between 0 and 1"),
    ({"missing_flag": 5.0}, "missing_flag must be between 0 and 1"),
    ({"imbalance_flag": 0.5}, "imbalance_flag must be >= 1"),
    ({"min_group_size": 0}, "min_group_size must be >= 1"),
])
def test_out_of_range_tunables_raise_instead_of_contradicting_themselves(opts, message):
    # min_share=1.5 used to be accepted silently: every group flagged
    # "under-represented" while overall_score/grade stayed 100/"A" (#511).
    df = pd.DataFrame({"sex": ["M"] * 50 + ["F"] * 50})
    with pytest.raises(ValueError, match=message):
        profile(df, opts=opts)


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


def test_parse_reference_mixed_scale_is_decided_per_column():
    # A reference file assembled from multiple sources: `sex` given as
    # fractions, `race` given as percentages, in the same file. The
    # percent-vs-fraction decision used to be made once across the whole
    # table, so `race`'s 70 pushed a global scale=100 onto `sex`'s already
    # correct 0.6/0.4, corrupting them to 0.006/0.004 (#513).
    ref = parse_reference(pd.DataFrame({
        "column": ["sex", "sex", "race", "race", "race"],
        "group": ["Female", "Male", "White", "Black", "Other"],
        "share": [0.6, 0.4, 70, 20, 10],
    }))
    assert ref == {
        "sex": {"Female": 0.6, "Male": 0.4},
        "race": {"White": 0.7, "Black": 0.2, "Other": 0.1},
    }


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


def test_intersections_labelize_keeps_non_numeric_age_sentinels():
    # #524: _dimension()'s main breakdown gives "unknown"/"prefer not to say"
    # their own categorical group, but _intersections()'s labelize() used to
    # map them to None, so pd.crosstab dropped those rows entirely - the
    # crosstab and the main groups then disagreed about the same dataset.
    df = pd.DataFrame({
        "age": [25, 30, 45, "unknown", "unknown", "unknown",
                "prefer not to say", 22, 33, 41] * 3,
        "sex": ["M", "F"] * 15,
    })

    result = profile(df, opts={"cross": ["age", "sex"]})

    age_dim = next(d for d in result["dimensions"] if d["name"] == "age")
    main_labels = {g["label"] for g in age_dim["groups"]}
    assert {"unknown", "prefer not to say"} <= main_labels

    crosstab_a_labels = {c["a"] for c in result["intersections"][0]["cells"]}
    # a genuinely-missing (NaN) age cell would still be absent here, but a
    # present sentinel value must now appear as its own crosstab row
    assert "prefer not to say" in crosstab_a_labels


def test_intersections_labelize_still_drops_genuinely_missing_age_cells():
    # The flip side: a real blank / range-invalid age cell must still be
    # absent from the crosstab (mapped to None), not turned into a group.
    df = pd.DataFrame({
        "age": [25, 30, 45, None, float("nan"), -1, 22, 33, 41, 29] * 3,
        "sex": ["M", "F"] * 15,
    })

    result = profile(df, opts={"cross": ["age", "sex"]})

    crosstab_a_labels = {c["a"] for c in result["intersections"][0]["cells"]}
    assert "nan" not in crosstab_a_labels
    assert "-1" not in crosstab_a_labels
    assert "None" not in crosstab_a_labels


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


# --- #840: implausible ages -----------------------------------------------------

def _age_frame(ages):
    return pd.DataFrame({"sex": ["M", "F"] * (len(ages) // 2), "age": ages})


def _age_dim(result):
    return next(d for d in result["dimensions"] if d["name"] == "age")


def test_implausible_ages_are_not_banded_into_the_oldest_group():
    result = profile(_age_frame([25, 30, 41, 200]))
    age = _age_dim(result)
    assert "75+" not in {g["label"] for g in age["groups"]}
    assert age["implausible_values"] == 1
    assert age["missing_pct"] == 0.25
    assert any("1 implausible age value(s) above 120" in f for f in result["flags"])


def test_negative_sentinel_ages_are_flagged_with_sentinel_message():
    """#863: negative sentinel ages are counted as implausible/sentinel values."""
    result = profile(_age_frame([25, -1, 41, -9]))
    age = _age_dim(result)
    assert age["implausible_values"] == 2
    assert age["missing_pct"] == 0.5
    assert age["has_negative_ages"] is True
    assert any("2 sentinel/implausible age value(s) (negative or above 120)" in f for f in result["flags"])



def test_plausible_ages_have_no_implausible_field_or_flag():
    result = profile(_age_frame([25, 30, 41, 80]))
    assert "implausible_values" not in _age_dim(result)
    assert not any("implausible" in f for f in result["flags"])


def test_max_age_option_moves_the_cutoff_and_is_validated():
    ages = [25, 30, 41, 90]
    assert "implausible_values" not in _age_dim(profile(_age_frame(ages)))
    assert _age_dim(profile(_age_frame(ages), None, {"max_age": 80}))["implausible_values"] == 1
    with pytest.raises(ValueError, match="max_age"):
        profile(_age_frame(ages), None, {"max_age": 0})


def test_a_birth_year_column_is_flagged_not_called_all_75_plus():
    result = profile(_age_frame([1985, 1990, 1972, 2001]))
    age = _age_dim(result)
    assert age["n_groups"] == 0 and age["implausible_values"] == 4


def test_implausible_ages_are_left_out_of_the_intersection():
    df = pd.DataFrame({"sex": ["M", "F"] * 20, "age": [25, 200] * 20})
    result = profile(df)
    labels = {cell["b"] for inter in result["intersections"] for cell in inter["cells"]}
    assert "75+" not in labels


# --- #847: column-name detection beyond English -----------------------------------

@pytest.mark.parametrize("name, kind", [
    ("sexo", "sex"), ("Género", "sex"), ("Geschlecht", "sex"), ("sexe", "sex"),
    ("raza", "race"), ("Raça", "race"), ("Rasse", "race"), ("ethnie", "race"), ("etnia", "race"),
    ("edad", "age"), ("Alter", "age"), ("Âge", "age"), ("idade", "age"),
    ("Fecha de nacimiento", "age"), ("Geburtsdatum", "age"), ("date_naissance", "age"),
    ("Bundesland", "geography"), ("país", "geography"), ("Código postal", "geography"),
    ("ciudad", "geography"), ("PLZ", "geography"), ("ville", "geography"), ("cidade", "geography"),
])
def test_classify_name_understands_spanish_german_french_and_portuguese(name, kind):
    assert classify_name(name) == kind


@pytest.mark.parametrize("name", ["generosity", "alternative", "landing", "razor", "Straße",
                                  "genre", "etat_civil"])
def test_non_english_keywords_do_not_overmatch_ordinary_words(name):
    assert classify_name(name) is None


@pytest.mark.parametrize("name", [
    "estado_civil", "estado civil", "EstadoCivil", "Estado Civil",
    "marital_status", "marital status",
    "stato_civile", "stato civile",
    "etat_civil", "état civil",
])
def test_marital_status_compounds_are_not_geography(name):
    # #855: estado alone is geography, but estado+civil (and EN/IT/FR siblings)
    # is marital status → no keyword kind (categorical via cardinality).
    assert classify_name(name) is None


def test_estado_alone_stays_geography_while_estado_civil_is_categorical():
    df = pd.DataFrame({
        "sexo": ["H", "M", "H", "M"],
        "estado_civil": ["soltero", "casado", "casado", "soltero"],
        "estado": ["TX", "CA", "TX", "CA"],
    })
    kinds = {d["name"]: d["kind"] for d in profile(df)["dimensions"]}
    assert kinds["sexo"] == "sex"
    assert kinds["estado"] == "geography"
    assert kinds["estado_civil"] == "categorical"


def test_spanish_dataset_gets_typed_dimensions_and_banded_ages():
    df = pd.DataFrame({"sexo": ["H", "M"] * 4, "edad": [25, 30, 41, 55, 62, 19, 33, 70],
                       "estado": ["TX", "CA"] * 4})
    result = profile(df)
    kinds = {d["name"]: d["kind"] for d in result["dimensions"]}
    assert kinds == {"sexo": "sex", "edad": "age", "estado": "geography"}
    edad = next(d for d in result["dimensions"] if d["name"] == "edad")
    assert all("-" in g["label"] or g["label"].endswith("+") for g in edad["groups"])
    assert not any("No column name matched" in f for f in result["flags"])


def test_no_recognised_kind_suggests_map():
    df = pd.DataFrame({"colA": ["x", "y"] * 4, "colB": ["p", "q"] * 4})
    flags = profile(df)["flags"]
    assert any("--map COL=KIND" in f for f in flags)
    # a hand-mapped run has already made the decision
    assert not any("No column name matched" in f
                   for f in profile(df, {"colA": "sex"})["flags"])


# --- #862: birth-year columns -------------------------------------------------------

def _dim(result, name):
    return next(d for d in result["dimensions"] if d["name"] == name)


def test_age_reference_year_converts_birth_years_to_ages():
    df = pd.DataFrame({"sex": ["M", "F"] * 4,
                       "yob": [1985, 1990, 1972, 2001, 1950, 2010, 40, 2090]})
    age = _dim(profile(df, None, {"age_reference_year": 2026}), "yob")
    labels = {g["label"]: g["count"] for g in age["groups"]}
    assert sum(labels.values()) == 7
    assert age["implausible_values"] == 1          # 2090 is after the reference year
    assert "75+" in labels                          # 1950 -> 76, a real age, banded


def test_birth_years_stay_implausible_without_a_reference_year():
    df = pd.DataFrame({"sex": ["M", "F"] * 2, "yob": [1985, 1990, 1972, 2001]})
    assert _dim(profile(df), "yob")["n_groups"] == 0


def test_age_reference_year_is_validated_and_ignores_non_integer_values():
    df = pd.DataFrame({"sex": ["M", "F"] * 2, "yob": [1985, 1990, 1972, 2001]})
    for bad in (1850, 2026.5):
        with pytest.raises(ValueError, match="age_reference_year"):
            profile(df, None, {"age_reference_year": bad})
    frac = pd.DataFrame({"sex": ["M", "F"], "age": [1985.5, 30]})
    assert _age_dim(profile(frac, None, {"age_reference_year": 2026}))["implausible_values"] == 1
