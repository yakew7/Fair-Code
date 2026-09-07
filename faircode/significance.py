"""Statistical significance testing for fairness gaps (pure numpy/pandas).

A fairness gap like mean(group_a) - mean(group_b) is a point estimate. On its
own it can't tell a real disparity apart from sampling noise, which matters most
on the smaller subgroups the audits measure. This module attaches two
non-parametric measures to every gap:

  * Confidence interval - bootstrap. Resample each group independently with
    replacement, recompute the gap n_resamples times, and take the percentile
    interval of that distribution. Non-parametric: it assumes nothing about the
    shape of the underlying distribution, which suits the binary prediction
    rates the audits work with.

  * p-value - permutation test. Under the null hypothesis the group label
    carries no information, so we pool both groups, reshuffle the labels
    n_permutations times, and measure how often a permuted gap is at least as
    extreme (two-sided) as the observed one. Also distribution-free, and it
    stays valid on the small, unbalanced subgroups the audits routinely hit.

Unlike profiler.py, this module has no JS counterpart to stay in sync with, so
it is not part of faircode/SPEC.md.
"""

from __future__ import annotations

import numpy as np


def _as_array(group):
    return np.asarray(group, dtype=float)


# ── Bootstrap confidence interval ───────────────────────────────────────────
def _bootstrap_means(values, n_resamples, rng):
    """Means of n_resamples with-replacement resamples of values.

    Chunked so peak memory stays bounded regardless of len(values); a full
    (n_resamples x len(values)) index matrix would blow up on the larger audit
    datasets.
    """
    n = len(values)
    means = np.empty(n_resamples)
    chunk = max(1, min(n_resamples, 1_000_000 // max(n, 1)))
    start = 0
    while start < n_resamples:
        size = min(chunk, n_resamples - start)
        idx = rng.integers(0, n, size=(size, n))
        means[start:start + size] = values[idx].mean(axis=1)
        start += size
    return means


def bootstrap_ci(group_a, group_b, n_resamples=10000, confidence=0.95,
                 random_state=42):
    a = _as_array(group_a)
    b = _as_array(group_b)
    gap = a.mean() - b.mean()
    rng = np.random.default_rng(random_state)
    means_a = _bootstrap_means(a, n_resamples, rng)
    means_b = _bootstrap_means(b, n_resamples, rng)
    gaps = means_a - means_b
    alpha = 1.0 - confidence
    ci_low = float(np.percentile(gaps, 100 * alpha / 2))
    ci_high = float(np.percentile(gaps, 100 * (1 - alpha / 2)))
    return float(gap), ci_low, ci_high


# ── Permutation test ────────────────────────────────────────────────────────
def permutation_test(group_a, group_b, n_permutations=10000, random_state=42):
    a = _as_array(group_a)
    b = _as_array(group_b)
    observed = abs(a.mean() - b.mean())
    pooled = np.concatenate([a, b])
    n_pool = len(pooled)
    n_a = len(a)
    rng = np.random.default_rng(random_state)

    at_least_as_extreme = 0
    chunk = max(1, min(n_permutations, 1_000_000 // max(n_pool, 1)))
    done = 0
    while done < n_permutations:
        size = min(chunk, n_permutations - done)
        # One independent shuffle of the group labels per row.
        order = np.argsort(rng.random((size, n_pool)), axis=1)
        shuffled = pooled[order]
        gap = shuffled[:, :n_a].mean(axis=1) - shuffled[:, n_a:].mean(axis=1)
        at_least_as_extreme += int(np.count_nonzero(np.abs(gap) >= observed))
        done += size
    return at_least_as_extreme / n_permutations


# ── Combined report ─────────────────────────────────────────────────────────
def significance_report(group_a, group_b, n_resamples=10000,
                        n_permutations=10000, confidence=0.95,
                        random_state=42):
    a = _as_array(group_a)
    b = _as_array(group_b)
    gap, ci_low, ci_high = bootstrap_ci(a, b, n_resamples, confidence,
                                        random_state)
    p_value = permutation_test(a, b, n_permutations, random_state)
    n_a = len(a)
    n_b = len(b)
    return {
        "gap": gap,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_value,
        "significant": p_value < 0.05,
        "n_a": n_a,
        "n_b": n_b,
        "small_sample_warning": n_a < 30 or n_b < 30,
    }


# ── Intersectional (two-attribute) report ────────────────────────────────────
def intersectional_report(outcome, mask_a, mask_b, n_resamples=10000,
                          n_permutations=10000, confidence=0.95,
                          random_state=42):
    """Compounded gap for the group that sits at the intersection of two attributes.

    Measuring each protected attribute on its own can hide the harm that lands
    on the people who carry both. A model can look nearly fair on sex alone and
    on race alone, yet flag minority women far more often than either marginal
    gap would predict - the classic intersectionality argument (Crenshaw 1989):
    the disadvantage compounds rather than adding up. A single-axis audit
    literally cannot see this, because it averages the intersection back into
    each attribute's marginal.

    So we split the population into the four quadrants of mask_a x mask_b and
    compare the doubly-disadvantaged cell (both True) against the baseline cell
    (both False) with the same bootstrap CI + permutation test the single-axis
    audits use. We also keep each attribute's marginal gap (the gap it would
    report on its own, ignoring the other attribute) so the two views can be set
    side by side. When the intersectional gap exceeds the sum of the marginals
    the disparity is *superadditive* - the intersection is worse than the parts,
    which is the finding a marginal-only audit would have missed.

    outcome is the prediction/outcome series; mask_a and mask_b are boolean
    arrays/Series aligned to it, each True on the disadvantaged side of that
    attribute (same rows the single-axis audits already pass to
    significance_report). cell_rates / cell_sizes expose all four quadrants so a
    thin doubly-disadvantaged cell is visible on its own, before the
    small_sample_warning inside the intersectional result is even checked.
    """
    y = _as_array(outcome)
    a = np.asarray(mask_a, dtype=bool)
    b = np.asarray(mask_b, dtype=bool)

    both = a & b
    neither = ~a & ~b
    a_only = a & ~b
    b_only = ~a & b

    # Marginal gap = the gap each attribute reports on its own, ignoring the
    # other. This is exactly what a single-axis audit measures for that attr.
    gap_a_alone = float(y[a].mean() - y[~a].mean())
    gap_b_alone = float(y[b].mean() - y[~b].mean())

    intersectional = significance_report(y[both], y[neither], n_resamples,
                                         n_permutations, confidence,
                                         random_state)

    # abs() on both sides: two gaps in the same direction stack, and a
    # compounded gap larger than that stacked total is the superadditive signal.
    superadditive = (abs(intersectional["gap"])
                     > abs(gap_a_alone) + abs(gap_b_alone))

    def _rate(mask):
        return float(y[mask].mean()) if mask.any() else float("nan")

    cell_rates = {
        "both": _rate(both),
        "neither": _rate(neither),
        "a_only": _rate(a_only),
        "b_only": _rate(b_only),
    }
    cell_sizes = {
        "both": int(both.sum()),
        "neither": int(neither.sum()),
        "a_only": int(a_only.sum()),
        "b_only": int(b_only.sum()),
    }
    return {
        "gap_a_alone": gap_a_alone,
        "gap_b_alone": gap_b_alone,
        "intersectional": intersectional,
        "superadditive": bool(superadditive),
        "cell_rates": cell_rates,
        "cell_sizes": cell_sizes,
    }
