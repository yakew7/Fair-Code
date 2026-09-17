> *A model that scored 95% in testing can fail the moment the world it was trained on stops looking like the world it operates in.*

## The One-Sentence Definition

**Distribution shift** occurs when the statistical properties of the data a model encounters in production differ from the data it was trained on, causing its learned patterns to stop matching reality.

## Why It Matters

A lending model trained on pre-2020 applicants, a hiring model trained on one industry's resumes, or a healthcare model trained on one hospital system's patients will all eventually meet a population that looks different from their training data. When that happens, accuracy degrades silently. No error is thrown. The model keeps producing confident scores, but those scores are calibrated to a world that no longer exists.

This breaks a common assumption in fairness work: that a model audited and mitigated once stays fair. Distribution shift means a fairness gap measured today can reopen tomorrow, not because the model changed, but because the population feeding it did. A model that passed a bias audit at deployment can become biased again purely through population drift, with no code change and no retraining trigger unless someone is watching for it.

## Types of Distribution Shift

### 1. Covariate Shift

The distribution of input features `P(X)` changes, but the relationship between features and outcome `P(Y|X)` stays the same. Example: a credit model trained mostly on applicants aged 25-45 starts seeing more applicants aged 60+ as the applicant pool ages. The features themselves shift, but a 60-year-old with a given income and credit history still behaves the same way the model expects.

### 2. Label Shift

The distribution of outcomes `P(Y)` changes, but `P(X|Y)` stays the same. Example: a recidivism model trained when a jurisdiction's re-arrest rate was 40% is deployed after a policy change drops it to 25%. The same defendant profiles now carry different real-world outcome rates than the model learned.

### 3. Concept Drift

The relationship between features and outcome `P(Y|X)` itself changes. This is the hardest to detect because the input data can look identical while what it *means* has changed. Example: during a recession, the same income and debt levels that once predicted "low default risk" now predict higher risk, because the economic context behind the numbers shifted.

## Concrete Example: Healthcare Readmission - Audit 06

The Healthcare Readmission audit uses the Diabetes 130-US Hospitals dataset, spanning 1999-2008 across 130 hospitals. That's nearly a decade of data pooled from many different care systems, each with its own admission practices, insurance mixes, and discharge protocols.

A model trained on this pooled data implicitly learns the *average* relationship between features like `payer_code`, `discharge_disposition_id`, and `number_inpatient` and the readmission outcome. But a hospital admitting patients early in this pooled record and one admitting patients later in it don't necessarily share the same payer mix, the same average length of stay, or the same discharge practices. `diabetic_data.csv` has no per-record date column - `encounter_id` is the closest stand-in for chronological order this dataset has (encounter IDs increase with each encounter, though they are not a calendar date), the same honest limitation this repo's [model drift](model-drift.md) explainer names explicitly for `German Credit Lending`'s row order. Splitting on encounter order this way, `payer_code` distributions shift enough on their own to plausibly change the racial composition of who gets flagged, since insurance type correlates with race in this dataset.

```python
# Compare feature distributions across an early vs. late slice of the same
# dataset, ordered by encounter_id - the closest stand-in for chronological
# order this dataset has, since it carries no real per-record date column.
ordered = df.sort_values("encounter_id")
early = ordered.iloc[:len(ordered) // 2]
late = ordered.iloc[len(ordered) // 2:]

print(early["payer_code"].value_counts(normalize=True))
print(late["payer_code"].value_counts(normalize=True))
# "?" (missing payer code) alone: 64.6% of the early half vs. 14.5% of the
# late half - a real, large shift, not a rounding artifact.
```

The fix for ml-bias-style audits isn't just removing proxies once. It's re-running the proxy analysis whenever the underlying population changes, because a proxy relationship measured on one slice of data can weaken or strengthen on another.

## Detection Code

These functions compare a reference (training) distribution against a current (production) distribution to flag features that have drifted.

```python
import pandas as pd
import numpy as np
from scipy.stats import ks_2samp, chi2_contingency

def detect_covariate_shift(reference_df, current_df, continuous_cols, categorical_cols, alpha=0.05):
    """
    Compares feature distributions between a reference dataset and a current
    dataset to detect covariate shift.

    Parameters:
        reference_df: DataFrame from the training/reference period
        current_df: DataFrame from the current/production period
        continuous_cols: list of continuous column names to test with KS test
        categorical_cols: list of categorical column names to test with chi-squared
        alpha: significance threshold for flagging drift (default 0.05)

    Returns:
        DataFrame with columns: feature, test, statistic, p_value, drifted
    """
    results = []

    for col in continuous_cols:
        stat, p_value = ks_2samp(reference_df[col].dropna(), current_df[col].dropna())
        results.append({
            "feature": col,
            "test": "ks_2samp",
            "statistic": stat,
            "p_value": p_value,
            "drifted": p_value < alpha
        })

    for col in categorical_cols:
        ref_counts = reference_df[col].value_counts()
        cur_counts = current_df[col].value_counts()
        categories = sorted(set(ref_counts.index) | set(cur_counts.index))

        contingency = np.array([
            [ref_counts.get(cat, 0) for cat in categories],
            [cur_counts.get(cat, 0) for cat in categories]
        ])

        chi2, p_value, _, _ = chi2_contingency(contingency)
        results.append({
            "feature": col,
            "test": "chi2_contingency",
            "statistic": chi2,
            "p_value": p_value,
            "drifted": p_value < alpha
        })

    return pd.DataFrame(results)


def detect_label_shift(reference_df, current_df, label_col, alpha=0.05):
    """
    Compares the outcome distribution P(Y) between a reference dataset and a
    current dataset to detect label shift.

    Parameters:
        reference_df: DataFrame from the training/reference period
        current_df: DataFrame from the current/production period
        label_col: name of the outcome column
        alpha: significance threshold for flagging drift (default 0.05)

    Returns:
        dict with reference rate, current rate, chi-squared p-value, and a drift flag
    """
    ref_counts = reference_df[label_col].value_counts()
    cur_counts = current_df[label_col].value_counts()
    categories = sorted(set(ref_counts.index) | set(cur_counts.index))

    contingency = np.array([
        [ref_counts.get(cat, 0) for cat in categories],
        [cur_counts.get(cat, 0) for cat in categories]
    ])

    chi2, p_value, _, _ = chi2_contingency(contingency)

    return {
        "reference_rate": (ref_counts / ref_counts.sum()).to_dict(),
        "current_rate": (cur_counts / cur_counts.sum()).to_dict(),
        "chi2": chi2,
        "p_value": p_value,
        "drifted": p_value < alpha
    }

# Usage example
# continuous = ["age", "income", "credit_score"]
# categorical = ["payer_code", "discharge_disposition_id"]
# shift_report = detect_covariate_shift(train_df, production_df, continuous, categorical)
# label_report = detect_label_shift(train_df, production_df, "readmitted")
```

## Limitations and Trade-offs

### 1. Statistical significance is not the same as practical significance

With large enough datasets, the KS test and chi-squared test will flag tiny, meaningless differences as "drifted" simply because they have enough samples to detect them. A feature can be statistically drifted at p < 0.001 while changing the model's actual predictions by less than 1%. Pair statistical drift detection with a check on how much the model's output distribution actually changes, not just the input distribution.

### 2. Detecting drift does not tell you which direction fairness moves

A drifted feature distribution can make a fairness gap better or worse. Detection code flags *that* something changed, not *whether* it made the model more or less biased toward a protected group. That requires re-running the fairness gap measurement on the new data, not just the drift test.

### 3. Concept drift is invisible to input-distribution tests

Both functions above compare `P(X)` and `P(Y)`. Neither can detect concept drift, where `P(Y|X)` changes while the inputs and outcome rates look stable. Catching concept drift requires periodically re-labeling a sample of current data with ground truth and comparing the model's predictions against it, which is expensive and often skipped.

### 4. Reference period choice is arbitrary and consequential

Choosing "last quarter" versus "last year" as the reference window changes what counts as drift. A feature that shifted gradually over two years won't trigger a quarter-over-quarter comparison but will show up clearly in a year-over-year one. There's no universally correct window, only one that matches how often the deployment context actually changes.

### 5. Small subgroup sizes inflate drift statistics

For protected subgroups that are already small in the dataset (as in Audit 06, where some race categories have very few records), chi-squared tests on those subgroups alone are unreliable. A handful of records moving between categories can swing the p-value without representing a real shift in the underlying population.

## Related Concepts

* [What is Sampling Bias?](sampling-bias.md) - distribution shift is sampling bias that develops *after* deployment, rather than existing at collection time.
* [What is Feedback Loop Bias?](feedback-loop-bias.md) - retraining on a model's own drifted outputs can compound distribution shift across cycles.
* [What Is Data Leakage?](data-leakage.md) - both concepts explain why strong test performance can fail to predict production performance, for different underlying reasons.
* [What Is Machine Learning Bias?](ml-bias.md) - distribution shift is a fifth entry point for bias, occurring after the four covered there, once the model is already deployed.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the dataset spans nearly a decade across 130 hospitals, making it the clearest candidate in this repo for demonstrating drift across time slices.
* [`German Credit Lending/`](../German%20Credit%20Lending/) - lending criteria and applicant demographics shift with economic cycles, making age-related proxy strength a candidate for drift analysis.

## Further Reading

* [Quiñonero-Candela et al. (2009): Dataset Shift in Machine Learning, MIT Press](https://mitpress.mit.edu/9780262170055/dataset-shift-in-machine-learning/) - the foundational text formalizing covariate shift, label shift, and concept drift as distinct problems.
* [Lipton et al. (2018): Detecting and Correcting for Label Shift with Black Box Predictors, ICML](https://arxiv.org/abs/1802.03916) - introduces a practical method for detecting and correcting label shift using only model outputs.
* [Rabanser et al. (2019): Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift, NeurIPS](https://arxiv.org/abs/1810.11953) - empirical comparison of statistical tests for drift detection, including the KS test approach used above.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*