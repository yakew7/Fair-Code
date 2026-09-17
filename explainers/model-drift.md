> *A fairness audit is a photograph. Model drift is what happens to the room after the shutter closes.*

## The One-Sentence Definition

**Model drift** is the ongoing process by which a deployed model's real-world accuracy and fairness gap change over calendar time, because the population it scores, or the relationship between that population's features and outcomes, keeps moving after the model was trained and audited.

## Why It Matters

Every audit in this repo reports a fairness gap as a single number: run `unfair.py`, get a gap, run `fair.py`, get a smaller gap, done. That number is true at the moment it was measured, on the data available at that moment. It says nothing about whether the same gap holds six months later. A benefits-eligibility model, a lending model, or a hiring model that clears a bias audit at launch can drift back into an unfair state purely by sitting still while the world around it keeps changing, with no code change, no retraining event, and no alert, unless someone is deliberately watching for it over time.

This is the practical, operational side of [What Is Distribution Shift?](distribution-shift.md). That explainer catalogs *why* a training distribution and a deployment distribution can diverge, covariate shift, label shift, concept drift, as a taxonomy, compared with a single reference snapshot against a single current snapshot. Model drift is what that divergence looks like from inside a production system that has to decide, on an ongoing basis and without a labeled "reference period" handed to it in advance, whether now is the moment performance has degraded enough to act on.

## How It Works

### Two Ways a Model Can Go Stale

A deployed model can drift in two distinct ways, and they call for different fixes:

- **Data drift**: the incoming feature distribution `P(X)` shifts, an applicant pool getting older, an economy sliding into recession, a labour market changing shape, while the model's learned relationship between features and outcome would still be valid if the input mix hadn't moved.
- **Concept drift**: the relationship between features and outcome `P(Y|X)` itself changes. The same income and debt levels that predicted low default risk in a boom predict something different in a downturn. Input data can look identical while what it *means* has changed underneath the model.

Conflating the two leads to the wrong fix: retraining on fresh data corrects data drift but does nothing for concept drift if the fresh data isn't representative of the new relationship yet, and vice versa.

### From a Single Snapshot to a Monitoring Problem

Distribution-shift detection, as covered elsewhere in this repo, compares one reference period against one current period with a KS test or a chi-squared test. That answers "has this specific pair of snapshots diverged," which is exactly right for a one-time before/after comparison. Model drift monitoring asks a different question: watching a metric across a rolling sequence of windows, when does it become clear that a real, sustained change is underway rather than ordinary noise between two arbitrary snapshots. That calls for two additional tools: the **Population Stability Index (PSI)**, a standard industry metric for how much a single feature's distribution has moved between two windows, and a **change-point test** like Page-Hinkley, built to flag the moment a stream of values shifts to a new mean rather than just fluctuating around the old one.

## Concrete Example: German Credit Lending - Audit 03

The German Credit Lending dataset has no timestamp column, it is a static, single-release academic dataset of 1,000 applicants, so there is no genuinely chronological split available. What follows treats row order as a stand-in for arrival order, which is a real limitation named explicitly below, not a claim that this specific file exhibits true calendar drift.

Splitting the 1,000 rows into five sequential windows of 200 and re-measuring the age-based fairness gap (`age < 30` vs `30+`, good-credit rate) in each window shows the gap is not a fixed number:

| Window | Good-credit rate | Share under 30 | Fairness gap (older - younger) |
|:-:|:-:|:-:|:-:|
| 1 | 71.5% | 33.5% | 4.3% |
| 2 | 74.5% | 40.0% | 11.7% |
| 3 | 65.5% | 38.5% | 13.6% |
| 4 | 69.0% | 38.5% | 15.1% |
| 5 | 69.5% | 35.0% | 10.2% |

The original `unfair.py` audit reports a single 6.39% gap from one random 80/20 split, not statistically significant at n=1,000 (`p=0.348`). That one number sits inside a range that swings from 4.3% to 15.1% depending on which 200-row slice happens to get measured. A single audit run can land near either end of that range purely by chance of which rows fall in the test set, which is exactly the instability a rolling-window view is built to catch and a one-shot snapshot cannot.

Running PSI between the first and last windows on three features gives a concrete read on which ones actually moved:

| Feature | PSI (window 1 vs window 5) | Read |
|---|:-:|---|
| `age` | 0.096 | borderline, just under the conventional 0.10 "no significant shift" cutoff |
| `credit_amount` | 0.119 | moderate shift |
| `duration` | 0.045 | no meaningful shift |

`credit_amount` is the feature that moved the most between the two windows, ahead of `age` itself, which is the kind of result a rolling PSI check surfaces and a single covariate-shift test run only once would not necessarily have been pointed at.

## Detection Code

```python
import numpy as np
import pandas as pd


def population_stability_index(reference, current, bins=10):
    """
    Computes the Population Stability Index (PSI) between a reference window
    and a current window of a single continuous feature. PSI < 0.1 is
    conventionally read as no significant shift, 0.1-0.25 as a moderate
    shift worth investigating, and > 0.25 as a shift large enough to
    warrant retraining or review.

    Parameters:
        reference: array-like of the feature's values in the reference window.
        current: array-like of the feature's values in the current window.
        bins: number of quantile bins to compare across (default 10).

    Returns:
        float PSI value. Higher means more distributional movement.
    """
    breakpoints = np.quantile(reference, np.linspace(0, 1, bins + 1))
    breakpoints[0], breakpoints[-1] = -np.inf, np.inf

    ref_counts, _ = np.histogram(reference, bins=breakpoints)
    cur_counts, _ = np.histogram(current, bins=breakpoints)

    ref_pct = np.where(ref_counts == 0, 0.0001, ref_counts / len(reference))
    cur_pct = np.where(cur_counts == 0, 0.0001, cur_counts / len(current))

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def page_hinkley_test(values, delta=0.005, threshold=5.0):
    """
    Runs the Page-Hinkley change-point test over a sequence of values (e.g.
    a rolling fairness gap or accuracy measurement, one value per time
    window), and returns the index of the first point where a sustained
    change from the running mean is detected, if any.

    Parameters:
        values: sequence of scalar metric values in time order.
        delta: allowed slack around the running mean before it counts
            toward drift (guards against flagging ordinary noise).
        threshold: cumulative deviation required to declare a change point.

    Returns:
        index of the detected change point, or None if no change was flagged.
    """
    running_mean = values[0]
    cumulative = 0.0
    min_cumulative = 0.0

    for i, value in enumerate(values):
        running_mean += (value - running_mean) / (i + 1)
        cumulative += value - running_mean - delta
        min_cumulative = min(min_cumulative, cumulative)

        if cumulative - min_cumulative > threshold:
            return i

    return None


def rolling_fairness_gap(df, protected_col, label_col, n_windows=5):
    """
    Splits a DataFrame into n_windows sequential windows (by row order, a
    stand-in for time order when no real timestamp exists) and computes the
    fairness gap in each, to check whether a single-snapshot gap is stable
    or whether it swings across the deployment period.

    Parameters:
        df: DataFrame containing protected_col and label_col.
        protected_col: boolean/0-1 column flagging the disadvantaged group.
        label_col: 0/1 outcome column.
        n_windows: number of equal-sized sequential windows.

    Returns:
        list of per-window fairness gaps (float, one per window).
    """
    window_size = len(df) // n_windows
    gaps = []
    for i in range(n_windows):
        window = df.iloc[i * window_size:(i + 1) * window_size]
        rate_disadvantaged = window[window[protected_col] == 1][label_col].mean()
        rate_baseline = window[window[protected_col] == 0][label_col].mean()
        gaps.append(abs(rate_baseline - rate_disadvantaged))
    return gaps

# Usage example
# gaps = rolling_fairness_gap(df, 'is_young', 'target', n_windows=5)
# change_point = page_hinkley_test(gaps)
# psi_age = population_stability_index(df['age'].iloc[:200], df['age'].iloc[800:])
```

## Limitations and Trade-offs

### 1. Row Order Is Not Real Time

The concrete example above uses row position as a proxy for arrival order because the dataset carries no timestamp. That is a demonstration of the *method*, not evidence that this specific 1,000-row academic release drifts in real deployment. Applying this to a real system requires an actual timestamp column; treating an arbitrary static file's row order as calendar time is a mistake this explainer is careful not to make more of than the data supports.

### 2. Data Drift and Concept Drift Need Different Fixes

Retraining on fresh data corrects data drift, a changed input mix, but does nothing for concept drift, a changed relationship, and can even make concept drift worse if the fresh data reflects a new but still-discriminatory process. Knowing which one is happening (see distribution-shift.md's covariate/label/concept breakdown) has to come before choosing a response, not after.

### 3. Monitoring Infrastructure Is the Bottleneck, Not the Math

PSI and Page-Hinkley are both cheap to compute. The actual obstacle to catching drift in most real deployments is that nobody is running them on a schedule against fresh production data with a maintained reference window. The gap between "drift is mathematically detectable" and "someone is actually watching for it" is where fairness harm accumulates silently.

### 4. Threshold Choices Are Judgment Calls

PSI's 0.1/0.25 cutoffs and Page-Hinkley's `delta`/`threshold` parameters are conventions, not laws of nature. A threshold tuned to catch subtle drift early will also fire on ordinary sampling noise; a threshold tuned to avoid false alarms will miss slow, gradual drift until it has already caused real harm. There is no setting that is simultaneously most sensitive and least noisy.

### 5. Small Windows Inflate Both PSI and the Fairness Gap

With only 200 rows per window here, and a youth subgroup that is a minority of that already-small window, both the PSI values and the fairness gaps above carry real sampling noise. A production system with a much smaller daily volume than this dataset's windows would need wider windows or a longer accumulation period before either statistic can be trusted.

## Related Concepts

* [What Is Distribution Shift?](distribution-shift.md) - the taxonomy (covariate shift, label shift, concept drift) and the one-shot reference-vs-current statistical tests this explainer's rolling, over-time monitoring builds on top of.
* [What Is Feedback Loop Bias?](feedback-loop-bias.md) - what happens when a drifted model is retrained on its own recent (already-biased) outputs rather than on fresh ground truth, compounding drift across cycles instead of correcting it.
* [What Is Supervised Learning?](supervised-learning.md) - describes the learned mapping this explainer covers the expiration of, once the population it was trained on stops matching the population it is scoring.

## Related Projects in This Repo

* [`German Credit Lending/`](../German%20Credit%20Lending/) - the anchor for this explainer: its `unfair.py` age/employment fairness gap re-measured across five sequential windows instead of one snapshot, and checked with PSI on three features.
* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - already used by distribution-shift.md as a decade-spanning, multi-hospital dataset; like German Credit Lending above, `diabetic_data.csv` carries no per-record date, so distribution-shift.md's early/late split there is also a row-order (`encounter_id`) proxy for chronological order, not a genuine calendar-based rolling drift check.

## Further Reading

* [Roberts et al. (2021): Common Pitfalls and Recommendations for Using Machine Learning to Detect and Prognosticate for COVID-19 Using Chest Radiographs and CT Scans, Nature Machine Intelligence 3, 199-217](https://doi.org/10.1038/s42256-021-00307-0) - a systematic review that screened 2,212 studies down to 61 meeting basic quality criteria, and found none of the resulting models fit for clinical use, in large part because models trained on one hospital's scanner and patient population failed to generalise once evaluated outside it.
* [Gama et al. (2014): A Survey on Concept Drift Adaptation, ACM Computing Surveys 46(4)](https://dl.acm.org/doi/10.1145/2523813) - the standard survey of concept drift detection and adaptation methods, including the change-point approach used above.
* [Page (1954): Continuous Inspection Schemes, Biometrika 41(1/2)](https://www.jstor.org/stable/2333009) - the original statistical process control paper the Page-Hinkley test is named for.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
