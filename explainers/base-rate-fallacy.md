# What Is the Base Rate Fallacy?

> *A screening tool with 90% accuracy and 90% sensitivity can still be wrong 80% of the time when it flags a positive case - because when the baseline prevalence of an event is low, most positive signals are false alarms. And when base rates differ across demographic groups, no model can satisfy both equalized odds and predictive parity at the same time.*

## The One-Sentence Definition

**The base rate fallacy** is a cognitive and statistical error where conditional probabilities (such as the likelihood of a positive test given that an individual is affected) are evaluated without accounting for the prior probability - the background prevalence or "base rate" - of the condition in the overall population.

## Why It Matters

High-stakes decision systems in medical diagnosis, criminal justice recidivism scoring, fraud detection, and credit underwriting rely heavily on binary flags ("high risk", "positive"). When evaluating these tools, decision-makers often look at sensitivity (true positive rate) or overall accuracy and assume a positive flag is overwhelmingly reliable.

When the underlying condition is rare, however, Bayes' theorem reveals a startling counter-intuitive reality: even a highly accurate model produces far more false alarms than true positives. A screening tool with a 95% true positive rate and a 5% false positive rate applied to a condition present in 1% of the population will be wrong roughly 84% of the time when it alerts.

In algorithmic fairness, the base rate fallacy takes on an even more critical role. Demographic groups frequently present different baseline outcome rates, P(Y = 1 | Group = A), due to historical, environmental, or structural factors. When base rates differ across groups, a fundamental mathematical impossibility theorem emerges: a risk scoring model **cannot** achieve both equalized odds (equal true and false positive rates) and predictive parity (equal positive predictive value) simultaneously. Ignoring base rates leads practitioners to treat these conflicting fairness definitions as interchangeable, when in fact they trade off directly against one another once base rates diverge.

## The Mathematics of the Base Rate Fallacy

The base rate fallacy occurs when one confuses P(Signal | Condition) with P(Condition | Signal). The relationship between them is governed by Bayes' Theorem.

Let Y represent the true binary outcome (0 or 1), and Ŷ represent the model's prediction (0 or 1). Define:
- Base Rate (Prevalence), p = P(Y = 1)
- True Positive Rate (Sensitivity), TPR = P(Ŷ = 1 | Y = 1)
- False Positive Rate (1 - Specificity), FPR = P(Ŷ = 1 | Y = 0)

The Positive Predictive Value (PPV), which measures the proportion of positive predictions that are actual positive cases, is calculated as:

```
PPV = P(Y = 1 | Ŷ = 1) = (TPR * p) / (TPR * p + FPR * (1 - p))
```

### Prevalence Impact on Reliability

To see how background prevalence dictates prediction reliability, consider a screening model with fixed TPR = 0.90 and FPR = 0.10 evaluated across varying base rates (p):

| Base Rate (p) | True Positives (TPR * p) | False Positives (FPR * (1 - p)) | PPV (P(Y = 1 \| Ŷ = 1)) | False Discovery Rate (1 - PPV) |
|---|---|---|---|---|
| **1%** | 0.0090 | 0.0990 | **8.33%** | **91.67%** |
| **5%** | 0.0450 | 0.0950 | **32.14%** | **67.86%** |
| **10%** | 0.0900 | 0.0900 | **50.00%** | **50.00%** |
| **30%** | 0.2700 | 0.0700 | **79.41%** | **20.59%** |
| **50%** | 0.4500 | 0.0500 | **90.00%** | **10.00%** |

At a 1% base rate, **over 91% of flagged individuals are false alarms**, despite the model having 90% sensitivity and 90% specificity.

### The Chouldechova Impossibility Identity

When evaluating models across demographic groups A and B, Chouldechova (2017) demonstrated that the false positive rate (FPR), false negative rate (FNR), positive predictive value (PPV), and base rate (p) are linked by a strict identity:

```
FPR = (p / (1 - p)) * ((1 - PPV) / PPV) * (1 - FNR)
```

If a model satisfies **predictive parity** (PPV_A = PPV_B) and has equal false negative rates (FNR_A = FNR_B), but the base rates differ (p_A != p_B), then:

```
p_A / (1 - p_A) != p_B / (1 - p_B)  =>  FPR_A != FPR_B
```

The false positive rates **must** differ between the groups. Equalizing predictive parity across groups with unequal base rates mathematically guarantees an unequal distribution of false alarms.

## Concrete Example: COMPAS - Audit 01

The COMPAS recidivism audit in this repository (`COMPAS/`) uses the ProPublica two-year recidivism dataset, evaluating predictions across racial groups.

In the dataset, the observed two-year recidivism base rates differ significantly by race:
- **Black defendants**: ~51.4% base rate
- **White defendants**: ~39.4% base rate

This base rate gap (12.0 percentage points) was the direct mathematical cause of the public clash between ProPublica and Northpointe (COMPAS's vendor):

1. **Northpointe checked Predictive Parity**: They demonstrated that a high-risk score produced comparable Positive Predictive Value across racial groups (~63% to 65%). Given a high-risk flag, the probability of reoffending was nearly identical regardless of race.
2. **ProPublica checked Equalized Odds / False Positive Rates**: They demonstrated that Black defendants who did not reoffend were flagged as high-risk at nearly double the rate of non-reoffending white defendants (44.9% vs. 23.5%).

Both analyses were mathematically accurate. Northpointe's predictive parity was held up as evidence of model neutrality, while ProPublica's error-rate disparity demonstrated systemic unequal harm. Neither side acknowledged that because the base rates differed, satisfying predictive parity *forced* the false positive rate gap to exist. The model could not be adjusted to fix ProPublica's complaint without destroying Northpointe's proof of fairness, unless the underlying base rates were equalized first.

The 51.4%/39.4% base rates and the PPV/FPR figures above are ProPublica's own published numbers from their original two-year-outcome analysis file - a different file from this repo's `COMPAS/compas-scores-raw.csv`, which has no independent recidivism-outcome column to compute a base rate from at all. The same mechanic is directly reproducible in this repo on [German Credit Lending](../German%20Credit%20Lending/), where `class` (good/bad credit history) is a real recorded label:

```python
import pandas as pd

df = pd.read_csv("German Credit Lending/credit_customers.csv")
df["is_young"] = (df["age"] < 30).astype(int)
df["good_credit"] = (df["class"] == "good").astype(int)

base_rates = df.groupby("is_young")["good_credit"].mean()
print("Good-Credit Base Rates by Group:")
print(base_rates)
```

**Actual output:**

```
is_young
0    0.740859
1    0.630728
Name: good_credit, dtype: float64
```

Older applicants (`is_young=0`) have a good-credit base rate of 74.1%, younger applicants (`is_young=1`) 63.1% - an 11.0-point base-rate gap, the same shape of disparity the ProPublica base rates show, just verifiable end to end against a file this repo actually ships.

## Detection Code

The following Python module computes group-level base rates, PPV, FPR, and FNR, and quantifies the Chouldechova trade-off gap to detect when base rate disparities are driving fairness metric conflicts.

```python
import numpy as np
import pandas as pd


def analyze_base_rates_and_fairness(
    df: pd.DataFrame, y_true_col: str, y_pred_col: str, group_col: str
) -> pd.DataFrame:
    """
    Computes base rates (prevalence), PPV, FPR, and FNR per demographic group
    and evaluates the trade-off between predictive parity and equalized odds.

    Parameters:
        df: DataFrame containing ground truth, predictions, and group labels.
        y_true_col: Column name of the true binary outcome (1 = positive).
        y_pred_col: Column name of the predicted binary outcome (1 = positive).
        group_col: Column name of the protected demographic attribute.

    Returns:
        DataFrame summarizing metrics and gaps per group.
    """
    metrics = []

    for group_val, sub in df.groupby(group_col):
        y_true = sub[y_true_col].to_numpy()
        y_pred = sub[y_pred_col].to_numpy()

        n = len(sub)
        n_pos = np.sum(y_true == 1)
        n_neg = np.sum(y_true == 0)

        base_rate = n_pos / n if n > 0 else np.nan

        tp = np.sum((y_true == 1) & (y_pred == 1))
        fp = np.sum((y_true == 0) & (y_pred == 1))
        fn = np.sum((y_true == 1) & (y_pred == 0))
        tn = np.sum((y_true == 0) & (y_pred == 0))

        tpr = tp / n_pos if n_pos > 0 else np.nan
        fpr = fp / n_neg if n_neg > 0 else np.nan
        fnr = fn / n_pos if n_pos > 0 else np.nan
        ppv = tp / (tp + fp) if (tp + fp) > 0 else np.nan

        metrics.append({
            "group": group_val,
            "sample_size": n,
            "base_rate": base_rate,
            "tpr": tpr,
            "fpr": fpr,
            "fnr": fnr,
            "ppv": ppv,
        })

    result_df = pd.DataFrame(metrics).set_index("group")

    # Compute maximum pairwise gaps across groups
    gap_row = {
        "sample_size": len(df),
        "base_rate": result_df["base_rate"].max() - result_df["base_rate"].min(),
        "tpr": result_df["tpr"].max() - result_df["tpr"].min(),
        "fpr": result_df["fpr"].max() - result_df["fpr"].min(),
        "fnr": result_df["fnr"].max() - result_df["fnr"].min(),
        "ppv": result_df["ppv"].max() - result_df["ppv"].min(),
    }
    result_df.loc["max_gap"] = gap_row

    return result_df


def print_chouldechova_audit_summary(
    df: pd.DataFrame, y_true_col: str, y_pred_col: str, group_col: str
) -> None:
    """
    Prints a formatted summary of base rates and metric trade-offs.
    """
    metrics = analyze_base_rates_and_fairness(df, y_true_col, y_pred_col, group_col)

    print("=== Group Fairness & Base Rate Audit ===")
    for grp in metrics.index:
        if grp == "max_gap":
            continue
        row = metrics.loc[grp]
        print(f"\nGroup: {grp} (n={int(row['sample_size'])})")
        print(f"  Base Rate P(Y=1): {row['base_rate']:.2%}")
        print(f"  PPV P(Y=1|Ŷ=1): {row['ppv']:.2%}")
        print(f"  False Positive Rate: {row['fpr']:.2%}")
        print(f"  False Negative Rate: {row['fnr']:.2%}")

    gaps = metrics.loc["max_gap"]
    print("\n--- Disparity Summary ---")
    print(f"Base Rate Gap: {gaps['base_rate']:.2%}")
    print(f"PPV Gap (Predictive Parity Disparity): {gaps['ppv']:.2%}")
    print(f"FPR Gap (Equalized Odds Disparity): {gaps['fpr']:.2%}")

    if gaps["base_rate"] > 0.05 and gaps["ppv"] < 0.05 and gaps["fpr"] > 0.10:
        print("\n[ALERT] Active Chouldechova Trade-off:")
        print("  Base rates differ significantly while PPV is relatively balanced.")
        print("  Predictive parity is forcing a substantial false-positive rate gap.")


# Usage example:
# print_chouldechova_audit_summary(compas_df, "two_year_recid", "high_risk_flag", "race")
```

## Limitations and Trade-offs

### 1. Observed Base Rates May Reflect Label Bias

The statistical base rate P(Y = 1) is computed from ground-truth labels in the dataset. However, ground-truth labels are frequently corrupted by historical bias or selective enforcement (e.g., arrest records track policing patterns rather than underlying criminal activity). An apparent base rate difference between groups may reflect differential observation rather than true prevalence differences (see [Label Bias](label-bias.md) and [Underdiagnosis Bias](underdiagnosis-bias.md)).

### 2. Base Rate Awareness Cannot Resolve Policy Conflicts

Math reveals why metrics conflict, but it cannot decide which metric a legal or institutional policy should enforce. Prioritizing predictive parity protects the decision-maker's confidence in positive flags, while prioritizing equalized odds protects individuals from unequal exposure to false accusations. The choice is normative, not mathematical.

### 3. Small Subgroup Estimates Are Volatile

When estimating base rates and PPV for small demographic subgroups or intersectional populations, small sample sizes introduce high variance. A small subgroup with few positive predictions will produce noisy PPV estimates that fluctuate wildly across dataset splits.

### 4. Threshold Adjustments Cannot Reconcile Structural Imbalances

Attempting to force equal false positive rates by adjusting decision thresholds separately per group shifts the operational point along each group's ROC curve, but it necessarily breaks predictive parity or calibration. Threshold tuning alters how errors are allocated; it does not eliminate the fundamental constraint imposed by unequal base rates.

## Related Concepts

* [What Is Predictive Parity?](predictive-parity.md) - the sufficiency metric requiring equal PPV across groups.
* [What Is Equalized Odds?](equalized-odds.md) - the separation metric requiring equal TPR and FPR across groups.
* [Why Fairness Metrics Conflict](fairness-metric-conflicts.md) - the complete mathematical overview of fairness impossibility theorems.
* [What Is Calibration?](calibration.md) - score-level probability agreement across groups, which also conflicts with equalized odds when base rates differ.
* [False Positives vs. False Negatives in Medical Risk Models](false-positives-vs-false-negatives.md) - how error asymmetry compounds under low base rates.
* [What Is Label Bias?](label-bias.md) - how biased observation distorts the measured base rate.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - recidivism risk scoring audit demonstrating the real-world clash between predictive parity and equalized odds driven by racial base rate differences.
* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - clinical readmission model where base rate differences in hospital access corrupt risk predictions across insurance types.

## Further Reading

* [Bar-Hillel, M. (1980): The Base-Rate Fallacy in Probability Judgments, *Acta Psychologica*, 44(3), 211-233](https://www.researchgate.net/publication/223684493_The_base-rate_fallacy_in_probability_judgments) - the foundational cognitive psychology paper establishing how humans ignore prior probabilities.
* [Chouldechova, A. (2017): Fair Prediction with Disparate Impact](https://arxiv.org/abs/1610.07524) - the formal proof establishing the mathematical impossibility of satisfying predictive parity and equalized odds under unequal base rates.
* [Kleinberg, J., Mullainathan, S., Raghavan, M. (2017): Inherent Trade-Offs in the Fair Determination of Risk Scores](https://arxiv.org/abs/1609.05807) - independent proof of the impossibility theorem for calibrated continuous scores.
* [Angwin, J. et al. (2016): Machine Bias](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - ProPublica's seminal investigation into COMPAS error-rate disparities.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
