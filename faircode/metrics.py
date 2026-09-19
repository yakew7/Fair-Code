"""Six fairness metrics, each with a bootstrap CI + permutation p-value -
the post-model counterpart to faircode.significance's single-gap report.

Every metric compares a "disadvantaged" group against an "advantaged" group
on the same held-out predictions, so all six describe one model run:

  demographic_parity_diff - selection-rate gap:   P(pred=1|disadv) - P(pred=1|adv)
  disparate_impact_ratio  - selection-rate ratio:  P(pred=1|disadv) / P(pred=1|adv)
                            (the "80% rule" - below 0.8 is the traditional flag)
  equal_opportunity_diff  - true-positive-rate gap, among y_true=1 rows
  equalized_odds_diff     - max(|TPR gap|, |FPR gap|) - whichever error-rate
                            gap is larger; `note` on the result says which
  predictive_parity_diff  - precision gap, among rows predicted positive
  accuracy_equality_diff  - overall accuracy gap

Difference metrics reuse faircode.significance.significance_report (bootstrap
CI + permutation test on a mean gap). disparate_impact_ratio needs its own
bootstrap/permutation since a ratio's sampling distribution isn't a
difference of means; the helpers below mirror significance.py's chunked
resampling so peak memory stays bounded on the larger audit datasets.

Also here: accuracy, AUC, and F1 - plain model-performance metrics (not
group comparisons), used for the results_performance.csv table alongside the
six fairness metrics above. accuracy and f1 get a bootstrap CI (vectorized
the same chunked way as the fairness metrics); auc gets a point estimate
only - each bootstrap resample needs an O(n log n) rank sort, which is too
expensive to repeat thousands of times at the scale of these audits. None of
the three get a permutation p-value: unlike a fairness gap, there's no
two-group null hypothesis to test a single performance number against.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

from .significance import significance_report

METRICS = (
    "demographic_parity_diff",
    "disparate_impact_ratio",
    "equal_opportunity_diff",
    "equalized_odds_diff",
    "predictive_parity_diff",
    "accuracy_equality_diff",
)

_RATIO_EPSILON = 1e-6


def _empty_result(note, n_disadvantaged=0, n_advantaged=0):
    return {
        "value": None, "ci_low": None, "ci_high": None, "p_value": None,
        "significant": False, "n_disadvantaged": n_disadvantaged, "n_advantaged": n_advantaged,
        "small_sample_warning": False, "note": note,
    }


def _resampled_means(values, n_resamples, rng):
    n = len(values)
    chunk = max(1, min(n_resamples, 1_000_000 // max(n, 1)))
    means = np.empty(n_resamples)
    done = 0
    while done < n_resamples:
        size = min(chunk, n_resamples - done)
        idx = rng.integers(0, n, size=(size, n))
        means[done:done + size] = values[idx].mean(axis=1)
        done += size
    return means


def _bootstrap_ratio(a, b, n_resamples, confidence, random_state):
    rng = np.random.default_rng(random_state)
    ratio = (a.mean() + _RATIO_EPSILON) / (b.mean() + _RATIO_EPSILON)
    means_a = _resampled_means(a, n_resamples, rng)
    means_b = _resampled_means(b, n_resamples, rng)
    ratios = (means_a + _RATIO_EPSILON) / (means_b + _RATIO_EPSILON)
    alpha = 1.0 - confidence
    ci_low = float(np.percentile(ratios, 100 * alpha / 2))
    ci_high = float(np.percentile(ratios, 100 * (1 - alpha / 2)))
    return float(ratio), ci_low, ci_high


def _permutation_ratio_p(a, b, n_permutations, random_state):
    rng = np.random.default_rng(random_state)
    observed = abs(np.log((a.mean() + _RATIO_EPSILON) / (b.mean() + _RATIO_EPSILON)))
    pooled = np.concatenate([a, b])
    n_pool, n_a = len(pooled), len(a)
    chunk = max(1, min(n_permutations, 1_000_000 // max(n_pool, 1)))
    at_least_as_extreme = 0
    done = 0
    while done < n_permutations:
        size = min(chunk, n_permutations - done)
        order = np.argsort(rng.random((size, n_pool)), axis=1)
        shuffled = pooled[order]
        ra = shuffled[:, :n_a].mean(axis=1)
        rb = shuffled[:, n_a:].mean(axis=1)
        stat = np.abs(np.log((ra + _RATIO_EPSILON) / (rb + _RATIO_EPSILON)))
        at_least_as_extreme += int(np.count_nonzero(stat >= observed))
        done += size
    return at_least_as_extreme / n_permutations


def _ratio_report(disadv_pred, adv_pred, n_resamples, n_permutations, confidence, random_state):
    a = np.asarray(disadv_pred, dtype=float)
    b = np.asarray(adv_pred, dtype=float)
    if len(a) == 0 or len(b) == 0:
        return _empty_result("insufficient_data", len(a), len(b))
    ratio, ci_low, ci_high = _bootstrap_ratio(a, b, n_resamples, confidence, random_state)
    p_value = _permutation_ratio_p(a, b, n_permutations, random_state)
    return {
        "value": ratio, "ci_low": ci_low, "ci_high": ci_high, "p_value": p_value,
        # round() strips 1.0 - confidence's floating-point representation
        # error, matching faircode.significance.significance_report's fix
        # for the same issue (#579).
        "significant": p_value < round(1.0 - confidence, 10),
        "n_disadvantaged": len(a), "n_advantaged": len(b),
        "small_sample_warning": len(a) < 30 or len(b) < 30, "note": None,
    }


def _diff_report(disadv, adv, n_resamples, n_permutations, confidence, random_state):
    if len(disadv) == 0 or len(adv) == 0:
        return _empty_result("insufficient_data", len(disadv), len(adv))
    sig = significance_report(disadv, adv, n_resamples, n_permutations, confidence, random_state)
    return {
        "value": sig["gap"], "ci_low": sig["ci_low"], "ci_high": sig["ci_high"],
        "p_value": sig["p_value"], "significant": sig["significant"],
        "n_disadvantaged": sig["n_a"], "n_advantaged": sig["n_b"],
        "small_sample_warning": sig["small_sample_warning"], "note": None,
    }


def compute_metrics(y_true, y_pred, disadvantaged, n_resamples=2000,
                    n_permutations=2000, confidence=0.95, random_state=42):
    """All six fairness metrics for one set of held-out predictions.

    y_true / y_pred are 0/1 arrays over the same rows; disadvantaged is a
    boolean mask over those rows (True = disadvantaged group). Rows where the
    protected attribute is unknown should already be excluded by the caller.
    Returns {metric_name: {value, ci_low, ci_high, p_value, significant,
    n_disadvantaged, n_advantaged, small_sample_warning, note}}.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    disadv = np.asarray(disadvantaged, dtype=bool)
    adv = ~disadv

    pred_disadv, pred_adv = y_pred[disadv], y_pred[adv]

    results = {}
    results["demographic_parity_diff"] = _diff_report(
        pred_disadv, pred_adv, n_resamples, n_permutations, confidence, random_state)
    results["disparate_impact_ratio"] = _ratio_report(
        pred_disadv, pred_adv, n_resamples, n_permutations, confidence, random_state)

    pos_disadv = disadv & (y_true == 1)
    pos_adv = adv & (y_true == 1)
    tpr_report = _diff_report(
        y_pred[pos_disadv], y_pred[pos_adv], n_resamples, n_permutations, confidence, random_state)
    results["equal_opportunity_diff"] = tpr_report

    neg_disadv = disadv & (y_true == 0)
    neg_adv = adv & (y_true == 0)
    fpr_report = _diff_report(
        y_pred[neg_disadv], y_pred[neg_adv], n_resamples, n_permutations, confidence, random_state)

    if tpr_report["value"] is None and fpr_report["value"] is None:
        eq_odds = _empty_result("insufficient_data")
    elif tpr_report["value"] is None:
        eq_odds = {**fpr_report, "note": "driven_by_fpr_gap"}
    elif fpr_report["value"] is None:
        eq_odds = {**tpr_report, "note": "driven_by_tpr_gap"}
    elif abs(fpr_report["value"]) > abs(tpr_report["value"]):
        eq_odds = {**fpr_report, "note": "driven_by_fpr_gap"}
    else:
        eq_odds = {**tpr_report, "note": "driven_by_tpr_gap"}
    results["equalized_odds_diff"] = eq_odds

    flagged_disadv = disadv & (y_pred == 1)
    flagged_adv = adv & (y_pred == 1)
    results["predictive_parity_diff"] = _diff_report(
        y_true[flagged_disadv], y_true[flagged_adv], n_resamples, n_permutations, confidence, random_state)

    correct = (y_true == y_pred).astype(int)
    results["accuracy_equality_diff"] = _diff_report(
        correct[disadv], correct[adv], n_resamples, n_permutations, confidence, random_state)

    return results


# ── Performance metrics (accuracy, AUC, F1) - not group comparisons ─────────

PERFORMANCE_METRICS = ("accuracy", "auc", "f1")


def accuracy(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    return float((y_true == y_pred).mean())


def f1(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return float(2 * precision * recall / (precision + recall))


def auc(y_true, y_proba) -> float:
    y_true = np.asarray(y_true, dtype=int)
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_proba))


def _bootstrap_accuracy_f1(y_true, y_pred, n_resamples, confidence, random_state):
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    n = len(y_true)
    rng = np.random.default_rng(random_state)

    correct = (y_true == y_pred)
    true_pos = (y_true == 1) & (y_pred == 1)
    false_pos = (y_true == 0) & (y_pred == 1)
    false_neg = (y_true == 1) & (y_pred == 0)

    chunk = max(1, min(n_resamples, 1_000_000 // max(n, 1)))
    acc_samples = np.empty(n_resamples)
    f1_samples = np.empty(n_resamples)
    done = 0
    while done < n_resamples:
        size = min(chunk, n_resamples - done)
        idx = rng.integers(0, n, size=(size, n))
        acc_samples[done:done + size] = correct[idx].mean(axis=1)
        tp = true_pos[idx].sum(axis=1).astype(float)
        fp = false_pos[idx].sum(axis=1).astype(float)
        fn = false_neg[idx].sum(axis=1).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            precision = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
            recall = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
            denom = precision + recall
            f1_samples[done:done + size] = np.where(denom > 0, 2 * precision * recall / denom, 0.0)
        done += size

    alpha = 1.0 - confidence
    acc_ci = (float(np.percentile(acc_samples, 100 * alpha / 2)),
             float(np.percentile(acc_samples, 100 * (1 - alpha / 2))))
    f1_ci = (float(np.percentile(f1_samples, 100 * alpha / 2)),
            float(np.percentile(f1_samples, 100 * (1 - alpha / 2))))
    return acc_ci, f1_ci


def compute_performance_metrics(y_true, y_pred, y_proba, n_resamples=2000,
                                confidence=0.95, random_state=42):
    """accuracy, auc, and f1 for one set of held-out predictions.

    y_proba is the predicted probability of the positive class (used for auc
    only); pass None to skip auc (its result will be NaN with no CI).
    Returns {metric_name: {value, ci_low, ci_high, n}} - no p_value/significant
    keys, since these aren't group-comparison gaps.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    n = len(y_true)

    acc_ci, f1_ci = _bootstrap_accuracy_f1(y_true, y_pred, n_resamples, confidence, random_state)
    auc_value = auc(y_true, y_proba) if y_proba is not None else float("nan")

    return {
        "accuracy": {"value": accuracy(y_true, y_pred), "ci_low": acc_ci[0], "ci_high": acc_ci[1], "n": n},
        "f1": {"value": f1(y_true, y_pred), "ci_low": f1_ci[0], "ci_high": f1_ci[1], "n": n},
        "auc": {"value": auc_value, "ci_low": None, "ci_high": None, "n": n},
    }
