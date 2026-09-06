"""Tests for the S0-S2 mitigation strategies + feature encoding (faircode.strategies).

S3/S4's day-to-day feature-selection behavior (strategy_features) is a plain
column-set check, tested directly below. Their full model-fitting behavior is
otherwise exercised end-to-end by tests/test_benchmark.py, not unit-tested
here - a real audit run means more than a synthetic one. The exception is
fit_post_processing's insufficient-data guard below: it's cheap, deterministic,
needs no mocking (it raises before ever touching fairlearn), and is exactly
the kind of edge case a full benchmark run won't reliably exercise on its own.

Run from the repo root:  pytest tests/ -q
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn", reason="faircode.strategies needs the optional benchmark extra")
pytest.importorskip("fairlearn", reason="faircode.strategies needs the optional fairlearn extra")

from sklearn.ensemble import RandomForestClassifier

from faircode.strategies import STRATEGIES, encode_features, fit_post_processing, strategy_features

CORE = ["income", "education"]
PROXIES = ["zip_code"]
PROTECTED = ["race"]


# ── strategy_features: S0-S2 column sets ────────────────────────────────────
def test_strategies_tuple_has_five_entries_in_order():
    assert STRATEGIES == (
        "baseline", "unawareness", "unawareness_proxy_removal", "in_processing", "post_processing",
    )


def test_s0_baseline_includes_everything():
    cols = strategy_features("baseline", CORE, PROXIES, PROTECTED)
    assert set(cols) == set(CORE + PROXIES + PROTECTED)
    assert len(cols) == len(CORE) + len(PROXIES) + len(PROTECTED)   # no duplicates


def test_s1_unawareness_drops_protected_keeps_proxies():
    cols = strategy_features("unawareness", CORE, PROXIES, PROTECTED)
    assert set(cols) == set(CORE + PROXIES)
    for p in PROTECTED:
        assert p not in cols


def test_s2_unawareness_proxy_removal_keeps_only_core():
    cols = strategy_features("unawareness_proxy_removal", CORE, PROXIES, PROTECTED)
    assert set(cols) == set(CORE)
    for c in PROXIES + PROTECTED:
        assert c not in cols


def test_s3_and_s4_also_reduce_to_core_only():
    # S3/S4 train on the SAME reduced feature set as S2 - the protected
    # attribute reaches them only as sensitive_features, never as a column.
    for strategy in ("in_processing", "post_processing"):
        cols = strategy_features(strategy, CORE, PROXIES, PROTECTED)
        assert set(cols) == set(CORE)


def test_strategy_features_deduplicates_overlapping_names():
    # A column listed as both core and proxy (shouldn't happen in a
    # well-formed manifest, but the function must not double it up).
    cols = strategy_features("baseline", ["a", "b"], ["b", "c"], ["a"])
    assert cols.count("a") == 1
    assert cols.count("b") == 1
    assert set(cols) == {"a", "b", "c"}


def test_strategy_features_raises_on_unknown_strategy():
    with pytest.raises(ValueError, match="unknown strategy: 'in_procesing'"):
        strategy_features("in_procesing", CORE, PROXIES, PROTECTED)


def test_strategy_features_raises_on_empty_string():
    with pytest.raises(ValueError, match="unknown strategy: ''"):
        strategy_features("", CORE, PROXIES, PROTECTED)


# ── encode_features ──────────────────────────────────────────────────────────
def test_encode_features_passes_numeric_columns_through():
    df = pd.DataFrame({"age": [20.0, 30.0, 40.0]})
    out = encode_features(df, ["age"])
    assert out["age"].tolist() == [20.0, 30.0, 40.0]


def test_encode_features_label_encodes_categoricals():
    df = pd.DataFrame({"sex": ["male", "female", "male"]})
    out = encode_features(df, ["sex"])
    assert out["sex"].dtype.kind in "iu"          # now integer-coded
    assert out["sex"].nunique() == 2
    assert out.loc[0, "sex"] == out.loc[2, "sex"]  # both "male" rows encode identically


def test_encode_features_fills_missing_numeric_with_median():
    df = pd.DataFrame({"income": [10.0, 20.0, np.nan, 30.0]})
    out = encode_features(df, ["income"])
    assert not out["income"].isna().any()
    assert out.loc[2, "income"] == pytest.approx(20.0)   # median of [10, 20, 30]


def test_encode_features_fills_missing_categorical_with_sentinel():
    df = pd.DataFrame({"race": ["A", None, "B", "A"]})
    out = encode_features(df, ["race"])
    assert not out["race"].isna().any()
    assert out["race"].nunique() == 3   # A, B, and the missing-value sentinel


def test_encode_features_only_touches_requested_columns():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out = encode_features(df, ["a"])
    assert list(out.columns) == ["a"]
    assert "b" not in out.columns


# -- fit_post_processing: calibration split (#446) ---------------------------
# A guard that only checked "does y have 2+ classes with 2+ members each"
# (rather than every (label, sensitive-group) combination) still let a
# calibration split land with zero examples of a class for one sensitive
# group - ThresholdOptimizer.fit() then raises "Degenerate labels for
# sensitive feature value X", or, if the FIT split lost a class entirely,
# predict_proba returns one column and a plain IndexError follows. Both
# crash confusingly, one or more layers inside fairlearn/sklearn, instead of
# failing clearly in fit_post_processing itself.
def test_fit_post_processing_raises_clearly_on_a_too_sparse_combination():
    # Only 1 positive example total, so the (label=1, sensitive-group) pair
    # it belongs to can never appear in both the fit and calibration splits -
    # genuinely impossible to calibrate reliably, regardless of split luck.
    n = 20
    X_train = pd.DataFrame({"a": np.arange(n, dtype=float), "b": np.arange(n, dtype=float)[::-1]})
    y_train = np.zeros(n, dtype=int)
    y_train[5] = 1
    sensitive_train = np.array([0, 1] * (n // 2))

    for random_state in (0, 1, 7, 42, 100):
        with pytest.raises(ValueError, match="not enough data to calibrate reliably"):
            fit_post_processing(
                RandomForestClassifier(random_state=42, n_estimators=10),
                X_train, y_train, sensitive_train, random_state=random_state)


def test_fit_post_processing_succeeds_on_marginally_small_but_viable_data():
    # 2 positive examples per sensitive group (the minimum every (label,
    # group) combination needs) - small, but every combination can appear on
    # both sides of the split. Runs with real RandomForestClassifier and
    # real fairlearn ThresholdOptimizer, not mocks - this is exactly the
    # scenario the old guard's "column-set-only" testing missed.
    rng = np.random.default_rng(0)
    n = 40
    X_train = pd.DataFrame({"a": rng.random(n), "b": rng.random(n)})
    y_train = np.zeros(n, dtype=int)
    y_train[[0, 1, 20, 21]] = 1   # 2 positives in each half (each sensitive group)
    sensitive_train = np.array([0] * 20 + [1] * 20)

    for random_state in (0, 1, 7, 42, 100):
        optimizer = fit_post_processing(
            RandomForestClassifier(random_state=42, n_estimators=10),
            X_train, y_train, sensitive_train, random_state=random_state)
        assert optimizer is not None
