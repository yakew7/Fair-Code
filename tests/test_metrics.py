"""Tests for the six fairness metrics + accuracy/AUC/F1 (faircode.metrics).

Every fairness-metric case below is a hand-computed tiny example - the
disadvantaged/advantaged rates, gaps, and group sizes are worked out on paper
in the comments, not just re-derived from the same code being tested.

Run from the repo root:  pytest tests/ -q
"""

import numpy as np
import pytest

pytest.importorskip("sklearn", reason="faircode.metrics needs the optional scikit-learn extra")

from sklearn.metrics import roc_auc_score

from faircode.metrics import (
    METRICS,
    PERFORMANCE_METRICS,
    accuracy,
    auc,
    compute_metrics,
    compute_performance_metrics,
    f1,
)

# ── Hand-computed fixture ────────────────────────────────────────────────────
#
# Disadvantaged group (n=10): 5 true positives, 5 true negatives.
#   y_true = [1,1,1,1,1, 0,0,0,0,0]
#   y_pred = [1,1,1,0,0, 1,1,0,0,0]
#   -> TPR = 3/5 = 0.60, FPR = 2/5 = 0.40, selection rate = 5/10 = 0.50
#   -> precision (among the 5 predicted-positive rows: 3 true1 + 2 true0) = 3/5 = 0.60
#   -> accuracy (correct: rows 0,1,2,7,8,9 = 6/10) = 0.60
#
# Advantaged group (n=10): 5 true positives, 5 true negatives.
#   y_true = [1,1,1,1,1, 0,0,0,0,0]
#   y_pred = [1,1,1,0,0, 0,0,0,0,0]
#   -> TPR = 3/5 = 0.60, FPR = 0/5 = 0.00, selection rate = 3/10 = 0.30
#   -> precision (3 predicted-positive rows, all true1) = 3/3 = 1.00
#   -> accuracy (correct: rows 0,1,2,5,6,7,8,9 = 8/10) = 0.80
#
# Expected gaps (disadvantaged - advantaged):
#   demographic_parity_diff = 0.50 - 0.30 = 0.20
#   disparate_impact_ratio  ~= 0.50 / 0.30 = 1.667
#   equal_opportunity_diff (TPR gap) = 0.60 - 0.60 = 0.00
#   FPR gap                          = 0.40 - 0.00 = 0.40  (the larger of the two -> drives equalized odds)
#   equalized_odds_diff = 0.40, note == "driven_by_fpr_gap"
#   predictive_parity_diff = 0.60 - 1.00 = -0.40
#   accuracy_equality_diff = 0.60 - 0.80 = -0.20

DISADV_Y_TRUE = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
DISADV_Y_PRED = [1, 1, 1, 0, 0, 1, 1, 0, 0, 0]
ADV_Y_TRUE = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
ADV_Y_PRED = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0]

Y_TRUE = np.array(DISADV_Y_TRUE + ADV_Y_TRUE)
Y_PRED = np.array(DISADV_Y_PRED + ADV_Y_PRED)
DISADVANTAGED = np.array([True] * 10 + [False] * 10)


@pytest.fixture(scope="module")
def metrics():
    return compute_metrics(Y_TRUE, Y_PRED, DISADVANTAGED, n_resamples=200, n_permutations=200,
                           random_state=42)


def test_all_six_metrics_present(metrics):
    assert set(metrics) == set(METRICS)


def test_demographic_parity_diff(metrics):
    m = metrics["demographic_parity_diff"]
    assert m["value"] == pytest.approx(0.20, abs=1e-9)
    assert m["n_disadvantaged"] == 10
    assert m["n_advantaged"] == 10
    assert m["ci_low"] <= m["value"] <= m["ci_high"]


def test_disparate_impact_ratio(metrics):
    m = metrics["disparate_impact_ratio"]
    assert m["value"] == pytest.approx(0.5 / 0.3, abs=1e-3)
    assert m["ci_low"] <= m["value"] <= m["ci_high"]


def test_equal_opportunity_diff_is_zero(metrics):
    m = metrics["equal_opportunity_diff"]
    assert m["value"] == pytest.approx(0.0, abs=1e-9)
    assert m["n_disadvantaged"] == 5   # only the 5 true-positive rows per group
    assert m["n_advantaged"] == 5


def test_equalized_odds_driven_by_fpr(metrics):
    m = metrics["equalized_odds_diff"]
    assert m["value"] == pytest.approx(0.40, abs=1e-9)
    assert m["note"] == "driven_by_fpr_gap"


def test_predictive_parity_diff(metrics):
    m = metrics["predictive_parity_diff"]
    assert m["value"] == pytest.approx(-0.40, abs=1e-9)
    assert m["n_disadvantaged"] == 5   # 5 predicted-positive rows in the disadvantaged group
    assert m["n_advantaged"] == 3      # 3 predicted-positive rows in the advantaged group


def test_accuracy_equality_diff(metrics):
    m = metrics["accuracy_equality_diff"]
    assert m["value"] == pytest.approx(-0.20, abs=1e-9)


def test_equalized_odds_picks_the_larger_gap_regardless_of_sign():
    # Flip which side is larger: now TPR gap dominates FPR gap, and it's negative.
    y_true = np.array([1, 1, 0, 0] * 2)
    y_pred_disadv = np.array([0, 0, 0, 0])   # TPR=0, FPR=0
    y_pred_adv = np.array([1, 1, 0, 0])      # TPR=1, FPR=0
    y_pred = np.concatenate([y_pred_disadv, y_pred_adv])
    disadv = np.array([True, True, True, True, False, False, False, False])
    m = compute_metrics(y_true, y_pred, disadv, n_resamples=50, n_permutations=50)
    eq_odds = m["equalized_odds_diff"]
    tpr_gap = m["equal_opportunity_diff"]["value"]
    assert eq_odds["value"] == pytest.approx(tpr_gap, abs=1e-9)
    assert eq_odds["note"] == "driven_by_tpr_gap"


def test_insufficient_data_returns_empty_result_not_a_crash():
    # No disadvantaged rows with y_true == 1 -> equal_opportunity_diff can't be computed.
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_pred = np.array([0, 1, 0, 1, 0, 1])
    disadv = np.array([True, True, True, False, False, False])
    m = compute_metrics(y_true, y_pred, disadv, n_resamples=50, n_permutations=50)
    eq_opp = m["equal_opportunity_diff"]
    assert eq_opp["value"] is None
    assert eq_opp["note"] == "insufficient_data"
    assert eq_opp["significant"] is False
    # The disadvantaged side really has 0 positive-label rows, but the
    # advantaged side has 3 - n_advantaged must reflect that real count,
    # not be fabricated to 0 just because the metric itself is undefined.
    assert eq_opp["n_disadvantaged"] == 0
    assert eq_opp["n_advantaged"] == 3


def test_disparate_impact_ratio_of_one_for_identical_groups():
    y_true = np.array([1, 0] * 20)
    y_pred = np.array([1, 0] * 20)
    disadv = np.array(([True] * 20) + ([False] * 20))
    m = compute_metrics(y_true, y_pred, disadv, n_resamples=200, n_permutations=200)
    assert m["disparate_impact_ratio"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert not m["disparate_impact_ratio"]["significant"]


# ── Determinism ──────────────────────────────────────────────────────────────
def test_compute_metrics_is_deterministic_given_a_seed():
    a = compute_metrics(Y_TRUE, Y_PRED, DISADVANTAGED, n_resamples=100, n_permutations=100, random_state=7)
    b = compute_metrics(Y_TRUE, Y_PRED, DISADVANTAGED, n_resamples=100, n_permutations=100, random_state=7)
    assert a == b


# ── Performance metrics (accuracy, AUC, F1) ─────────────────────────────────
#
# Combined 20 rows (disadv + adv), hand-computed:
#   accuracy = (6 + 8) / 20 = 0.70
#   tp = 3 + 3 = 6, fp = 2 + 0 = 2, fn = 2 + 2 = 4
#   precision = 6/8 = 0.75, recall = 6/10 = 0.60
#   f1 = 2 * 0.75 * 0.60 / (0.75 + 0.60) = 0.9 / 1.35 = 2/3

def test_accuracy_hand_computed():
    assert accuracy(Y_TRUE, Y_PRED) == pytest.approx(0.70, abs=1e-9)


def test_f1_hand_computed():
    assert f1(Y_TRUE, Y_PRED) == pytest.approx(2 / 3, abs=1e-9)


def test_f1_is_zero_when_no_true_positives():
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([0, 0, 1, 1])   # every prediction wrong, zero true positives
    assert f1(y_true, y_pred) == 0.0


def test_auc_matches_sklearn_directly():
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, size=200)
    y_proba = rng.random(200)
    assert auc(y_true, y_proba) == pytest.approx(roc_auc_score(y_true, y_proba))


def test_auc_is_nan_for_single_class_y_true():
    y_true = np.zeros(10, dtype=int)
    y_proba = np.random.default_rng(0).random(10)
    assert np.isnan(auc(y_true, y_proba))


def test_compute_performance_metrics_shape_and_values():
    result = compute_performance_metrics(Y_TRUE, Y_PRED, y_proba=None, n_resamples=100, random_state=42)
    assert set(result) == set(PERFORMANCE_METRICS)
    assert result["accuracy"]["value"] == pytest.approx(0.70, abs=1e-9)
    assert result["f1"]["value"] == pytest.approx(2 / 3, abs=1e-9)
    # No y_proba given -> auc is NaN with no CI, per the module's documented tradeoff.
    assert np.isnan(result["auc"]["value"])
    assert result["auc"]["ci_low"] is None
    assert result["accuracy"]["ci_low"] <= result["accuracy"]["value"] <= result["accuracy"]["ci_high"]


# ── Regression: reproduces the COMPAS headline number ───────────────────────
def test_demographic_parity_diff_reproduces_compas_headline_gap():
    # unfair.py reports: Black 87.16%, White 0.40%, gap 86.77% (rounded).
    # Reconstruct arrays with those exact rates (n=10,000 each, matching the
    # bootstrap's own n_resamples convention) and confirm compute_metrics
    # reproduces the published number, not just some directionally-similar one.
    n = 10_000
    black_pred = np.array([1] * 8716 + [0] * (n - 8716))   # rate = 0.8716
    white_pred = np.array([1] * 40 + [0] * (n - 40))        # rate = 0.0040
    y_true = np.zeros(2 * n, dtype=int)   # irrelevant for demographic_parity_diff
    y_pred = np.concatenate([black_pred, white_pred])
    disadv = np.array([True] * n + [False] * n)
    m = compute_metrics(y_true, y_pred, disadv, n_resamples=50, n_permutations=50)
    assert m["demographic_parity_diff"]["value"] == pytest.approx(0.8677, abs=5e-4)
