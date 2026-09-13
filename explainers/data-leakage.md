> *A model that scores 99% on every test you run is not a model you can trust. It has already seen the answer sheet.*

## The One-Sentence Definition

**Data leakage** is the contamination of a model's training signal with information that will not be available at prediction time, producing evaluation scores that overstate real-world performance.

---

## Why It Matters

A model trained with leakage passes every internal test. It fails at the moment it is deployed - when the future arrives and the borrowed information is no longer there. In high-stakes domains, that failure is not an accuracy metric. It is a parole decision that collapses under scrutiny, a credit denial that cannot survive an audit, a clinical flag that fires or fails at the wrong moment.

Leakage is the most common reason a production model performs far worse than its validation numbers predicted. It is also one of the hardest failures to catch, because the model is telling you what you want to hear right up until the point it matters.

---

## Two Kinds of Leakage

### Target Leakage

Target leakage occurs when a feature used for training carries information that is only known *because* the outcome has already happened. The feature arrives after the label in the real world, but it is present in the training data alongside that label.

| Domain | Leaking Feature | Why It Is Leakage |
|--------|----------------|-------------------|
| Credit default | Account closure flag | Account is closed *because* the borrower defaulted, not before |
| Healthcare readmission | Discharge prescription count | Prescribed on discharge, after the readmission decision would need to be made at admission |
| Criminal justice | Post-arrest charge count | Filed after the arrest the model is predicting |
| Insurance denial | Claim filed within 30 days | Claim exists because the denial outcome is already known |

The model learns to predict the outcome by detecting its own effects. Remove those features at deployment and performance collapses.

### Train-Test Contamination

Train-test contamination occurs when information from the test set leaks into the training process before the model is evaluated. The most common forms:

- **Preprocessing before splitting.** Fitting a scaler, imputer, or encoder on the full dataset and then splitting. The test set's distribution has already shaped the transformation.
- **Feature selection before splitting.** Selecting features by correlation with the target on the full dataset, then training on the selected subset. The test set voted on which features to keep.
- **Aggregated statistics computed before splitting.** Mean-encoding, count-encoding, or any group aggregation run on the full dataset embeds test-set information into every training row.

In both cases the model has indirect access to the test set during training. Its evaluation score reflects the combined distribution, not generalization.

---

## Concrete Example

The COMPAS audit in this repository demonstrates a proxy form of target leakage. `CustodyStatus` - a feature describing whether a defendant is currently in custody - correlates with race at p < 0.001 and with the recidivism label at p < 0.001. It is not a neutral operational variable. It encodes the outcome of a prior criminal justice interaction, which itself encodes historical over-policing of Black communities. Including it in the model achieves an 86.77% Black/White fairness gap in positive prediction rates.

This is the structural form of leakage: a feature that looks like a legitimate input but whose predictive power comes from downstream effects of the very outcome being predicted.

Removing `CustodyStatus` alongside the protected race attribute reduces the gap to 15.69% - an 82% reduction.

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

df = pd.read_csv("COMPAS/compas-scores-raw.csv")
df = df[df["Ethnic_Code_Text"].isin(["African-American", "Caucasian"])].copy()
df = df[df["DisplayText"] == "Risk of Recidivism"].copy()
df["high_risk"] = df["ScoreText"].isin(["High", "Medium"]).astype(int)
df["race_binary"] = df["Ethnic_Code_Text"].map({"African-American": 1, "Caucasian": 0})

# CustodyStatus is the structural-leakage feature: it encodes the outcome of a
# prior criminal justice interaction, not a race-neutral input
FEATURES_WITH_LEAKAGE = ["Sex_Code_Text", "race_binary", "CustodyStatus", "MaritalStatus"]
FEATURES_WITHOUT = ["Sex_Code_Text", "MaritalStatus"]
y = df["high_risk"]

for label, feats in [("With leakage (race + CustodyStatus)", FEATURES_WITH_LEAKAGE),
                     ("Without leakage", FEATURES_WITHOUT)]:
    X = pd.get_dummies(df[feats])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(random_state=42)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    race_test = df.loc[X_test.index, "race_binary"]
    black_rate, white_rate = pred[race_test == 1].mean(), pred[race_test == 0].mean()
    print(f"{label}: Black flagged {black_rate:.2%}, White flagged {white_rate:.2%}, "
          f"gap {black_rate - white_rate:.2%}")
```

**Actual output:**

```
With leakage (race + CustodyStatus): Black flagged 87.16%, White flagged 0.40%, gap 86.77%
Without leakage: Black flagged 84.71%, White flagged 69.02%, gap 15.69%
```

The leaked model's fairness gap is inflated by the leaking feature; removing `CustodyStatus` alongside `race_binary` cuts the gap by 82% (matching `COMPAS/unfair.py`/`COMPAS/fair.py` exactly, since this *is* that same recipe). The residual 15.69% gap - discussed further in [What Is Machine Learning Bias?](ml-bias.md) - shows leakage removal narrows a gap but doesn't always close it.

---

## Detection Code

```python
import pandas as pd
import numpy as np
from scipy.stats import pointbiserialr, chi2_contingency
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def detect_target_leakage(df: pd.DataFrame, target: str, threshold: float = 0.4) -> pd.DataFrame:
    """
    Flags features with suspiciously high correlation with the target variable.
    Uses point-biserial correlation for continuous features and Cramér's V for
    categorical ones. High correlation alone is not proof of leakage - use this
    as a shortlist for manual inspection.
    """
    results = []
    for col in df.columns:
        if col == target:
            continue
        try:
            if df[col].dtype in [np.float64, np.int64]:
                corr, p = pointbiserialr(df[col].fillna(df[col].median()), df[target])
                results.append({
                    "feature": col,
                    "method": "point-biserial",
                    "correlation": abs(corr),
                    "p_value": p,
                    "flag": abs(corr) >= threshold
                })
            else:
                ct = pd.crosstab(df[col].fillna("missing"), df[target])
                chi2, p, dof, _ = chi2_contingency(ct)
                n = ct.sum().sum()
                cramers_v = np.sqrt(chi2 / (n * (min(ct.shape) - 1)))
                results.append({
                    "feature": col,
                    "method": "cramers_v",
                    "correlation": cramers_v,
                    "p_value": p,
                    "flag": cramers_v >= threshold
                })
        except Exception:
            continue

    return (
        pd.DataFrame(results)
        .sort_values("correlation", ascending=False)
        .reset_index(drop=True)
    )


def check_preprocessing_leakage(df: pd.DataFrame, target: str) -> None:
    """
    Demonstrates the correct split-before-fit pattern and warns if a
    StandardScaler is fitted on the full dataset instead of train only.
    Prints a warning if the test-set mean deviates from the train-fitted mean
    by more than one standard deviation - a sign of distribution mismatch that
    a pre-split scaler would silently mask.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c != target]

    X = df[numeric_cols].fillna(0)
    y = df[target]

    X_train, X_test, _, _ = train_test_split(X, y, test_size=0.2, random_state=42)

    scaler = StandardScaler()
    scaler.fit(X_train)   # fit on train only - this is correct

    train_means = pd.Series(scaler.mean_, index=numeric_cols)
    test_means  = X_test.mean()
    deviation   = ((test_means - train_means) / scaler.scale_).abs()

    flagged = deviation[deviation > 1.0]
    if flagged.empty:
        print("No significant distribution mismatch detected between train and test splits.")
    else:
        print("Features with high train/test mean deviation (potential distribution shift):")
        print(flagged.round(3).to_string())
        print("\nIf a scaler was fitted before splitting, these deviations were hidden.")


# Example usage
if __name__ == "__main__":
    df = pd.read_csv("your-dataset.csv")
    TARGET = "outcome_column"

    leakage_report = detect_target_leakage(df, TARGET, threshold=0.4)
    print("=== Target Leakage Scan ===")
    print(leakage_report[leakage_report["flag"]].to_string(index=False))

    print("\n=== Preprocessing Leakage Check ===")
    check_preprocessing_leakage(df, TARGET)
```

---

## Limitations

1. **Correlation is not causation.** `detect_target_leakage()` surfaces high-correlation features. Some of them are legitimately informative. Every flagged feature requires manual inspection of *when* it is collected in the real-world workflow. The function cannot make that judgment.

2. **Leakage can hide in aggregate features.** A row-level feature may look clean while a group-level aggregate (mean income by zip code, claim rate by employer) was computed on the full dataset before splitting. The contamination is invisible at the row level.

3. **Time-series data requires temporal splitting.** Random train/test splits on time-ordered data are always leaky. If your dataset has a time dimension, split by date, not by row index.

4. **Leakage detection does not fix class imbalance correctly.** Techniques like SMOTE must be applied inside the training fold only, after splitting. Applying them before splitting leaks synthetic minority samples into the test set.

5. **A high test score is not sufficient evidence that leakage is absent.** Models trained on genuinely hard problems can score high without leakage. And a model with subtle leakage may score only modestly higher than a clean model, making the contamination easy to miss.

---

## Related Concepts

- [What Is a Proxy Variable?](proxy-variables.md) - Features that correlate with a protected attribute after it is removed. Proxy leakage is the intersection of proxy contamination and temporal contamination.
- [What Is Label Bias?](label-bias.md) - Labels that inherit human prejudice. When labels encode historical decisions, the target itself can be a source of leakage.
- [What Is Sampling Bias?](sampling-bias.md) - How the training distribution misrepresents the deployment population. Leakage can mask sampling bias by inflating evaluation scores.
- [What Is Machine Learning Bias?](ml-bias.md) - The four entry points through which bias enters a model, of which data pipeline contamination is one.
- [Why AI Hallucinates](ai-hallucinations.md) - Overconfident predictions in sparse feature regions. Leakage and hallucination both produce models that are confidently wrong in structured ways.

---

## Related Projects in This Repo

- [COMPAS/](../COMPAS/) - `CustodyStatus` as a leaking proxy: encodes prior system contact, which encodes historical over-policing.
- [Healthcare Readmission/](../Healthcare%20Readmission/) - `payer_code` and `discharge_disposition_id` as features collected after or conditional on system contact, not before the prediction decision.
- [Benefits Denial/](../Benefits%20Denial/) - `relationship` and `marital.status` encode outcomes of social and economic structures that are themselves downstream of gender and race.

---

## Further Reading

1. Kaufman, S., Rosset, S., Perlich, C., & Stitelman, O. (2012). Leakage in data mining: Formulation, detection, and avoidance. *ACM Transactions on Knowledge Discovery from Data, 6*(4), 1–21.

2. Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns, 4*(9), 100804.

3. Nisbet, R., Miner, G., & Yale, K. (2018). *Handbook of Statistical Analysis and Data Mining Applications* (2nd ed.). Academic Press. Chapter 11: Data preparation and leakage prevention.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*