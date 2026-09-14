> *A fairness gap is a number computed from a sample, not a fact about the world - a bootstrap confidence interval and a permutation-test p-value are what tell you whether that number is real or just noise from a small subgroup.*

## The One-Sentence Definition

A **bootstrap confidence interval** estimates the range a fairness gap would plausibly fall in if you re-measured it on a different sample from the same population, by resampling the data you already have with replacement thousands of times; a **permutation test** estimates the probability of seeing a gap this large by chance alone, by reshuffling group labels and recomputing the gap under the assumption they carry no information.

## Why It Matters

Every fairness metric explainer in this repo - [Equal Opportunity](equal-opportunity.md), [Equalized Odds](equalized-odds.md), [Demographic Parity](demographic-parity.md), and the rest - reports a gap between two groups. A gap on its own is a single number computed from whatever rows happened to land in that dataset. It says nothing about whether a different, equally valid sample from the same underlying population would show a similar gap, a much smaller one, or none at all.

That question matters most exactly where fairness audits are weakest: small subgroups. A 12-point gap measured on 1,000 people per group is a very different claim than the same 12-point gap measured on 6 people in one group - the first is almost certainly a real pattern, the second could easily be five people going one way and one going the other. Without a confidence interval and a p-value attached, "is this gap real or just noise on a small subgroup" - the question this repo's own `small_sample_warning` flag exists to raise - has no answer at all.

`faircode/significance.py` attaches both to every one of the six fairness metrics, for every audit, strategy, and model this repo's benchmark harness runs: a 95% bootstrap confidence interval and a permutation-test p-value, computed the same way, every time.

## Core Concept

Both methods are non-parametric - they assume nothing about the shape of the underlying distribution, which matters because fairness metrics here are built on binary prediction rates, not smooth continuous measurements.

**Bootstrap confidence interval.** Resample each group independently, with replacement, back up to its own original size, and recompute the gap. Do this thousands of times (`faircode/significance.py` defaults to 2,000 resamples, matching the paper's frozen run), and take the 2.5th and 97.5th percentile of the resulting distribution of gaps - that range is the 95% confidence interval. It answers: "given only the data I have, how much would this gap plausibly move around if I could resample from the same population again?"

**Permutation-test p-value.** Under the null hypothesis, group membership carries no real information about the outcome - so pool both groups together, reshuffle which rows are labeled which group, and recompute the gap. Repeat thousands of times (2,000, matching the CI resample count). The p-value is the fraction of those reshuffled gaps that are at least as extreme as the one actually observed. It answers a different question than the CI: "if there were truly no difference between groups, how often would random chance alone produce a gap this large?"

Neither method assumes normality, a minimum sample size, or a particular metric - the same two functions apply identically whether the metric is a proportion, a rate difference, or a ratio.

## Concrete Example: COMPAS - Audit 01

Two rows from the exact same audit and model show what a difference in sample size does to certainty, using frozen numbers straight from `paper/results-frozen/results_fairness.csv` (baseline logistic regression, race):

| Metric | Value | 95% CI | p-value | n (disadv. / adv.) | Verdict |
|---|---:|---|---:|---|---|
| Equal Opportunity Diff | 0.926 | [0.909, 0.942] | 0.0 | 1,048 / 467 | Clearly real |
| Predictive Parity Diff (random forest) | 0.128 | [-0.218, 0.475] | 0.663 | 1,552 / 6 | Cannot tell |

The first row has a huge effect and a tight interval - 1.7 percentage points wide, entirely on one side of zero, p essentially 0. There is no ambiguity: African-American defendants who did not reoffend were flagged as high-risk at a dramatically higher rate than Caucasian defendants who did not reoffend, and that conclusion would survive almost any resample.

The second row, on the same audit, has a point estimate of 12.8 points - not small - but the confidence interval runs from -21.8 to +47.5, spanning zero by a wide margin, and the permutation p-value is 0.663 (not remotely significant). The reason is visible in the last column: only 6 Caucasian defendants had a positive prediction to measure predictive parity against. A gap computed from 6 people can point in almost any direction depending on which 6 people happened to be in the sample - `faircode/metrics.py`'s own `small_sample_warning` flag is `True` on this row for exactly that reason. Reporting the 12.8-point number alone, without the interval, would misrepresent a genuinely uncertain measurement as a finding.

## Detection Code

A minimal, from-scratch implementation of both methods, so the mechanics are visible directly on the page rather than hidden behind a library call - this mirrors `faircode/significance.py`'s approach independently rather than wrapping it.

```python
import numpy as np


def bootstrap_ci_and_permutation_p(group_a, group_b, n_resamples=2000,
                                   n_permutations=2000, confidence=0.95,
                                   random_state=42):
    """
    Computes a bootstrap confidence interval and a permutation-test p-value
    for the gap mean(group_a) - mean(group_b), for binary (0/1) outcomes.

    Parameters:
        group_a, group_b: array-like of 0/1 values (e.g. "was this
            prediction correct", "was this row flagged")
        n_resamples: number of bootstrap resamples for the CI
        n_permutations: number of label-shuffles for the p-value
        confidence: confidence level, e.g. 0.95 for a 95% CI
        random_state: seed, for reproducibility

    Returns a dict with gap, ci_low, ci_high, p_value, and
    small_sample_warning (True if either group has fewer than 30 rows -
    a common rule-of-thumb threshold, not a hard statistical cutoff).
    """
    rng = np.random.default_rng(random_state)
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    observed_gap = a.mean() - b.mean()

    # Bootstrap: resample each group independently, with replacement.
    boot_gaps = np.empty(n_resamples)
    for i in range(n_resamples):
        resample_a = rng.choice(a, size=len(a), replace=True)
        resample_b = rng.choice(b, size=len(b), replace=True)
        boot_gaps[i] = resample_a.mean() - resample_b.mean()
    alpha = 1 - confidence
    ci_low, ci_high = np.percentile(boot_gaps, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    # Permutation test: pool both groups, reshuffle the group label.
    pooled = np.concatenate([a, b])
    n_a = len(a)
    perm_gaps = np.empty(n_permutations)
    for i in range(n_permutations):
        shuffled = rng.permutation(pooled)
        perm_gaps[i] = shuffled[:n_a].mean() - shuffled[n_a:].mean()
    p_value = np.mean(np.abs(perm_gaps) >= np.abs(observed_gap))

    return {
        "gap": observed_gap,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_value,
        "small_sample_warning": len(a) < 30 or len(b) < 30,
    }


# Usage example:
# result = bootstrap_ci_and_permutation_p(correct_disadvantaged, correct_advantaged)
# print(result)
# A CI that spans zero, or a small_sample_warning, means "cannot conclude a
# real gap exists" - regardless of how large the point estimate looks.
```

## Limitations

### 1. Small-n instability is fundamental, not a bug the CI fixes

A wide confidence interval on a small subgroup is not a flaw in the bootstrap method - it is the bootstrap correctly reporting that the data genuinely can't support a precise estimate. More resamples don't narrow a CI built on 6 real data points; only more real data does.

### 2. Multiple comparisons inflate the chance of a false positive

This repo's benchmark harness computes six metrics across every protected attribute, model, and strategy for seven audits - dozens of p-values per audit. At a 0.05 threshold, running enough independent tests will eventually produce a "significant" result by chance alone, even with no real effect anywhere. No correction (e.g. Bonferroni) is currently applied across this full set; a single p-value should be read in that context, not treated as a standalone finding.

### 3. Neither method fixes a biased ground-truth label

A confidence interval quantifies uncertainty in the *estimate* of a gap; it says nothing about whether the label the gap is measured against is itself trustworthy. See [What Is Label Bias?](label-bias.md).

### 4. A significant p-value is not the same as a large or important gap

With enough rows, even a trivially small gap can produce a low p-value. Always read the point estimate, the confidence interval, and the p-value together - not the p-value alone.

## Related Concepts

* [What Is the Base Rate Fallacy?](base-rate-fallacy.md) - like a confidence interval, a reminder that a raw number can mislead without the right context attached.
* [What Is Equal Opportunity?](equal-opportunity.md) - one of the metrics whose CI and p-value this explainer's example uses directly.
* [What Is Intersectional Bias?](intersectional-bias.md) - intersectional subgroups are smaller by construction, making this explainer's small-n warning especially relevant there.

## Related Projects in This Repo

* [`faircode/significance.py`](../faircode/significance.py) - the frozen implementation this explainer's detection code mirrors independently.
* [`COMPAS/`](../COMPAS/) - the audit above, where the same model produces both a rock-solid and a completely inconclusive gap depending on which metric's subgroup size you land on.

## Further Reading

* [Efron, B., Tibshirani, R. (1993): *An Introduction to the Bootstrap*](https://doi.org/10.1201/9780429246593) - the foundational reference for the bootstrap resampling method used here.
* [Good, P. (2005): *Permutation, Parametric, and Bootstrap Tests of Hypotheses*](https://doi.org/10.1007/b138696) - covers permutation testing as a distribution-free alternative to classical significance tests.
* [Ho, D. E., Imai, K. (2006): Randomization Inference With Natural Experiments](https://doi.org/10.1198/016214506000000330) - a practical treatment of permutation-based inference outside a designed experiment, close to how audit data is actually collected.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
