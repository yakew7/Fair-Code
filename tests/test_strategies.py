"""Tests for the S0-S2 mitigation strategies + feature encoding (faircode.strategies).

S3/S4 (fairlearn in-processing/post-processing) are exercised end-to-end by
tests/test_benchmark.py instead of unit-tested in isolation here - they need a
real model + real fairlearn mitigator to mean anything, which belongs in an
integration test, not a column-set check.

Run from the repo root:  pytest tests/ -q
"""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fairlearn", reason="faircode.strategies needs the optional fairlearn extra")

from faircode.strategies import STRATEGIES, encode_features, strategy_features

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
