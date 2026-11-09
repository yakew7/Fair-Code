"""Tests for the fairness-gap significance module.

Run from the repo root:  pytest tests/ -q
"""

import numpy as np
import pytest

from faircode.significance import (
    bootstrap_ci,
    intersectional_report,
    permutation_test,
    significance_report,
)


# ── Zero-gap case ────────────────────────────────────────────────────────────
def test_identical_groups_have_zero_gap_and_high_p():
    a = [1, 0] * 50
    b = [1, 0] * 50
    rep = significance_report(a, b)
    assert rep["gap"] == 0.0
    assert rep["p_value"] > 0.9          # label shuffling can't beat a zero gap
    assert not rep["significant"]
    assert rep["ci_low"] <= 0.0 <= rep["ci_high"]


# ── Large-gap case ───────────────────────────────────────────────────────────
def test_separated_groups_are_significant_and_ci_excludes_zero():
    a = [1] * 90 + [0] * 10   # 0.9 positive rate
    b = [0] * 90 + [1] * 10   # 0.1 positive rate
    rep = significance_report(a, b)
    assert rep["gap"] == pytest.approx(0.8, abs=1e-9)
    assert rep["p_value"] < 0.05
    assert rep["significant"]
    assert rep["ci_low"] > 0.0           # interval sits entirely above zero
    assert rep["ci_low"] <= rep["gap"] <= rep["ci_high"]


def test_confidence_tightens_the_significance_threshold_not_just_the_ci():
    # A gap with 0.01 < p < 0.05 is significant at the default confidence
    # (0.95 -> p < 0.05) but not at confidence=0.99 (-> p < 0.01). Before
    # #548 the `significant` flag was pinned to p < 0.05 regardless of
    # `confidence`, which only widened/narrowed the CI.
    rng = np.random.default_rng(0)
    for _ in range(5):
        a = rng.binomial(1, 0.55, size=60).astype(float)
        b = rng.binomial(1, 0.35, size=60).astype(float)

    r95 = significance_report(a, b, n_resamples=3000, n_permutations=3000,
                              confidence=0.95, random_state=4)
    r99 = significance_report(a, b, n_resamples=3000, n_permutations=3000,
                              confidence=0.99, random_state=4)

    assert r95["p_value"] == r99["p_value"]          # same permutation test
    assert 0.01 < r95["p_value"] < 0.05
    assert r95["significant"] is True
    assert r99["significant"] is False


# ── Determinism ──────────────────────────────────────────────────────────────
def test_random_state_makes_results_deterministic():
    a = [1] * 40 + [0] * 60
    b = [1] * 25 + [0] * 75
    assert significance_report(a, b) == significance_report(a, b)
    # An explicit seed pins bootstrap and permutation to the same numbers.
    assert bootstrap_ci(a, b, random_state=7) == bootstrap_ci(a, b, random_state=7)
    assert (permutation_test(a, b, random_state=7)
            == permutation_test(a, b, random_state=7))


# ── Small-sample warning ─────────────────────────────────────────────────────
def test_small_sample_warning_trigger():
    small = [1, 0] * 7           # n = 14 < 30
    large = [1, 0] * 100         # n = 200
    assert significance_report(small, large)["small_sample_warning"]
    assert significance_report(large, small)["small_sample_warning"]
    assert not significance_report(large, large)["small_sample_warning"]


# ── Intersectional report ────────────────────────────────────────────────────
def _crossed(cells):
    """Build (outcome, mask_a, mask_b) from a list of (a, b, n, n_ones) cells.

    Each cell is a quadrant of the mask_a x mask_b grid with a fixed positive
    rate, so the four cells are independent by construction - no interaction
    unless the cell rates put one there.
    """
    outcome, mask_a, mask_b = [], [], []
    for a, b, n, ones in cells:
        outcome += [1] * ones + [0] * (n - ones)
        mask_a += [bool(a)] * n
        mask_b += [bool(b)] * n
    return outcome, np.array(mask_a), np.array(mask_b)


def test_intersectional_additive_case_is_not_superadditive():
    # Balanced quadrants with purely additive rates: neither=0.20, +0.20 for a,
    # +0.10 for b, and both = 0.50 = 0.20 + 0.20 + 0.10 (no extra interaction).
    outcome, mask_a, mask_b = _crossed([
        (0, 0, 100, 20),   # neither
        (1, 0, 100, 40),   # a only  → effect_a = +0.20
        (0, 1, 100, 30),   # b only  → effect_b = +0.10
        (1, 1, 100, 50),   # both    → additive, no interaction
    ])
    rep = intersectional_report(outcome, mask_a, mask_b)
    assert not rep["superadditive"]
    assert rep["gap_a_alone"] == pytest.approx(0.20, abs=1e-9)
    assert rep["gap_b_alone"] == pytest.approx(0.10, abs=1e-9)
    # With no interaction the compounded gap is exactly the sum of the marginals.
    assert rep["intersectional"]["gap"] == pytest.approx(
        rep["gap_a_alone"] + rep["gap_b_alone"], abs=1e-9)


def test_intersectional_superadditive_case_is_flagged_and_significant():
    # A small doubly-disadvantaged cell with a rate far above what either
    # marginal predicts. Because the cell is thin, the marginals barely move,
    # so the compounded gap dwarfs their sum.
    outcome, mask_a, mask_b = _crossed([
        (0, 0, 400, 80),    # neither: 0.20
        (1, 0, 400, 140),   # a only : 0.35
        (0, 1, 400, 140),   # b only : 0.35
        (1, 1, 40,  36),    # both   : 0.90 - disproportionately worse
    ])
    rep = intersectional_report(outcome, mask_a, mask_b)
    assert rep["superadditive"]
    assert abs(rep["intersectional"]["gap"]) > (
        abs(rep["gap_a_alone"]) + abs(rep["gap_b_alone"]))
    assert rep["intersectional"]["significant"]


def test_intersectional_small_doubly_disadvantaged_cell_warns():
    # Overall attribute groups are large, but their intersection is tiny.
    # The warning must fire on the intersection, not on the marginals.
    outcome, mask_a, mask_b = _crossed([
        (0, 0, 400, 80),
        (1, 0, 400, 140),
        (0, 1, 400, 140),
        (1, 1, 20,  15),    # both: n = 20 < 30
    ])
    rep = intersectional_report(outcome, mask_a, mask_b)
    assert rep["cell_sizes"]["both"] == 20
    assert rep["intersectional"]["small_sample_warning"]
    # The a and b groups on their own are far larger than the 30-row floor.
    assert (mask_a.sum() >= 30) and (mask_b.sum() >= 30)

def test_empty_group_is_not_reported_significant():
    a = []
    b = [0, 1, 0, 1]

    gap, ci_low, ci_high = bootstrap_ci(a, b)

    assert np.isnan(gap)
    assert np.isnan(ci_low)
    assert np.isnan(ci_high)

    assert permutation_test(a, b) == 1.0

    rep = significance_report(a, b)

    assert np.isnan(rep["gap"])
    assert np.isnan(rep["ci_low"])
    assert np.isnan(rep["ci_high"])
    assert rep["p_value"] == 1.0
    assert rep["significant"] is False
    assert rep["n_a"] == 0
    assert rep["n_b"] == 4
    assert rep["small_sample_warning"] is True
