# Explainer: What is Calibration?

> *The reason a model can be "equally accurate" for everyone - and still treat them unequally.*

---

## The One-Sentence Definition

A model is **calibrated** for a group if its predicted probabilities actually match real-world outcomes - so when it says "70% risk," roughly 70% of people in that group actually experience the outcome.

---

## Why It Matters

Most people evaluate AI models on accuracy. Calibration is a different question: *do the scores mean the same thing across demographic groups?*

If a risk-scoring system assigns a "70% recidivism risk" score to Black defendants and a "70% risk" score to White defendants, calibration asks: does 70% actually mean 70% for *both* groups? If the model is miscalibrated for one group - say, 70% translates to 50% actual recidivism for White defendants but 80% for Black defendants - then identical scores are producing fundamentally different real-world stakes depending on who receives them.

This is called **differential calibration**, and it's one of the central problems exposed by the ProPublica COMPAS investigation. It's also why calibration is often in direct conflict with other fairness metrics like equalized odds - you frequently cannot satisfy both at the same time.

---

## Concrete Example: COMPAS Recidivism Scores

The COMPAS risk tool, used in U.S. courts to inform bail and sentencing decisions, became the centre of a landmark fairness debate in 2016. ProPublica found that the tool made systematically different kinds of errors for Black and White defendants.

Northpointe (the tool's developer) responded that COMPAS *was* calibrated: among defendants scored "high risk," roughly the same proportion reoffended regardless of race. That claim is true by the numbers. But calibration alone masked a different problem - the tool reached that calibration through asymmetric error rates. Black defendants were far more likely to be falsely labelled high risk (false positives), while White defendants were more likely to be falsely labelled low risk (false negatives).

This is the [Chouldechova (2017)](https://arxiv.org/abs/1703.00056) result in practice: **when base rates differ between groups, you cannot simultaneously achieve calibration and equal false positive/false negative rates.** You have to choose. COMPAS chose calibration. ProPublica measured the error rates. Both were right about what they measured.

Reproducing Northpointe's and ProPublica's exact tables takes ProPublica's independent *two-year recidivism outcome* - whether a defendant was actually rearrested within two years - matched against COMPAS's own score. This repo's `COMPAS/compas-scores-raw.csv` is the raw score file only: it has `ScoreText`/`DecileScore` (what COMPAS predicted) but no such outcome column to check those scores against, so the calibration gap above can't be reproduced from this file alone.

What this repo *can* verify directly is the same concept - do predicted probabilities match real outcome rates across groups? - on an audit that has both a model's own predicted probabilities and a genuine historical outcome: [German Credit Lending](../German%20Credit%20Lending/), where `class` (good/bad credit history) is a real recorded label, not a derived score.

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.calibration import calibration_curve

df = pd.read_csv('German Credit Lending/credit_customers.csv')
df['target'] = (df['class'] == 'good').astype(int)
df['is_young'] = (df['age'] < 30).astype(int)

cat_cols = ['checking_status', 'credit_history', 'purpose', 'savings_status',
            'employment', 'personal_status', 'other_parties', 'property_magnitude',
            'other_payment_plans', 'housing', 'job', 'own_telephone', 'foreign_worker']
for col in cat_cols:
    df[col] = LabelEncoder().fit_transform(df[col])

features = ['checking_status', 'duration', 'credit_history', 'purpose', 'credit_amount',
            'savings_status', 'employment', 'installment_commitment', 'personal_status',
            'other_parties', 'residence_since', 'property_magnitude', 'age',
            'other_payment_plans', 'housing', 'existing_credits', 'job',
            'num_dependents', 'own_telephone', 'foreign_worker']

X_train, X_test, y_train, y_test, g_train, g_test = train_test_split(
    df[features], df['target'], df['is_young'],
    test_size=0.2, random_state=42, stratify=df['target'])

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)
probs = model.predict_proba(X_test)[:, 1]

for group, label in [(1, 'Young (<30)'), (0, 'Older (30+)')]:
    mask = (g_test == group).values
    fraction_pos, mean_pred = calibration_curve(y_test[mask], probs[mask], n_bins=5)
    print(f"{label}: MACE = {np.mean(np.abs(fraction_pos - mean_pred)):.4f}")
    for mp, fp in zip(mean_pred, fraction_pos):
        print(f"  predicted {mp:.2f} -> actual {fp:.2f}")
```

**Actual output** (`n_test=200`: 69 young, 131 older):

| Group | Predicted | Actual |
|---|---:|---:|
| Young (<30) | 0.32 | 0.29 |
| Young (<30) | 0.52 | 0.62 |
| Young (<30) | 0.71 | 0.71 |
| Young (<30) | 0.90 | 1.00 |
| Older (30+) | 0.19 | 0.00 |
| Older (30+) | 0.36 | 0.43 |
| Older (30+) | 0.53 | 0.41 |
| Older (30+) | 0.71 | 0.80 |
| Older (30+) | 0.90 | 0.91 |

Mean Absolute Calibration Error: **0.0559** for young applicants, **0.0964** for older applicants - the model is *better* calibrated for young applicants here, the opposite of what the German Credit Lending audit's own headline gap (young applicants flagged as bad credit risks at a higher rate, see [`German Credit Lending/README.md`](../German%20Credit%20Lending/README.md)) might suggest. That's the point calibration and error-rate metrics make separately: a model can be reasonably calibrated for a group (its probabilities mean roughly what they say) while still treating that group's *predictions* asymmetrically - the same tension Northpointe and ProPublica each measured correctly, just along different axes.

---

## How to Measure Calibration

Calibration is measured by comparing predicted probabilities to actual outcome rates within prediction bins. The standard approach is a **calibration curve** (also called a reliability diagram).

```python
import pandas as pd
import numpy as np
from sklearn.calibration import calibration_curve
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

def measure_calibration_by_group(df, feature_cols, target_col, group_col, n_bins=5):
    """
    Train a classifier and plot calibration curves separately per group.
    A well-calibrated model produces a curve close to the diagonal.
    Divergence between groups indicates differential calibration.
    """
    X = pd.get_dummies(df[feature_cols])
    y = df[target_col]
    groups = df[group_col]

    X_train, X_test, y_train, y_test, g_train, g_test = train_test_split(
        X, y, groups, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(random_state=42)
    model.fit(X_train, y_train)
    probs = model.predict_proba(X_test)[:, 1]

    results = {}
    for group in g_test.unique():
        mask = g_test == group
        if mask.sum() < 20:
            continue
        fraction_pos, mean_pred = calibration_curve(
            y_test[mask], probs[mask], n_bins=n_bins
        )
        results[group] = {
            'mean_predicted': mean_pred,
            'fraction_positive': fraction_pos
        }

    return results


def calibration_gap(results):
    """
    Compute the mean absolute calibration error (MACE) per group.
    Higher = worse calibration for that group.
    """
    for group, data in results.items():
        error = np.mean(np.abs(data['fraction_positive'] - data['mean_predicted']))
        print(f"{group}: Mean Absolute Calibration Error = {error:.4f}")


# Example usage with German Credit Lending
df = pd.read_csv('German Credit Lending/credit_customers.csv')
df['target'] = (df['class'] == 'good').astype(int)
df['is_young'] = (df['age'] < 30).astype(int)
cat_cols = ['checking_status', 'credit_history', 'purpose', 'savings_status',
            'employment', 'personal_status', 'other_parties', 'property_magnitude',
            'other_payment_plans', 'housing', 'job', 'own_telephone', 'foreign_worker']
for col in cat_cols:
    df[col] = LabelEncoder().fit_transform(df[col])

feature_cols = ['checking_status', 'duration', 'credit_history', 'purpose', 'credit_amount',
                'savings_status', 'employment', 'installment_commitment', 'personal_status',
                'other_parties', 'residence_since', 'property_magnitude', 'age',
                'other_payment_plans', 'housing', 'existing_credits', 'job',
                'num_dependents', 'own_telephone', 'foreign_worker']
results = measure_calibration_by_group(df, feature_cols, 'target', 'is_young')
calibration_gap(results)
```

**Actual output:**

```
0: Mean Absolute Calibration Error = 0.0964
1: Mean Absolute Calibration Error = 0.0559
```

(group `0` = older/30+, group `1` = young/<30, matching the worked example above exactly - this function is the reusable version of the same computation.)

A perfectly calibrated model produces a diagonal line from (0, 0) to (1, 1). A model that is calibrated for one group but not another will show one group's curve hugging the diagonal while the other curves away - the gap between those curves is the differential calibration.

---

## Limitations and Trade-offs

Calibration is not a complete picture of fairness, and it has well-documented limitations.

**1. Calibration can coexist with discriminatory error patterns.**
A model can be calibrated across groups while still generating far more false positives for one group than another. Northpointe's defence of COMPAS is the canonical example. Calibration and equalised false positive/false negative rates are mathematically incompatible when base rates differ between groups - this is the Chouldechova (2017) impossibility result. See the [Fairness Metric Conflicts explainer](fairness-metric-conflicts.md) for the full proof.

**2. Calibration is sensitive to base rate differences.**
If Group A has a 20% base rate and Group B has a 40% base rate for the outcome, a model can be well-calibrated for both groups and still assign systematically higher scores to Group B - scores that reflect historical data patterns, not individual risk.

**3. Calibration says nothing about whether the outcome itself is fair.**
A model perfectly calibrated on arrest rates is calibrated on a measure that reflects over-policing, not actual crime. The fairness of the calibration target matters as much as the calibration itself.

**4. Small group sizes inflate calibration error estimates.**
With fewer samples, calibration curves are noisier. Always check sample size per bin before drawing conclusions about a subgroup's calibration.

---

## Related Concepts

- [Proxy Variables](proxy-variables.md) - features that encode protected attributes and corrupt training data before calibration is even measured
- [Equalized Odds](equalized-odds.md) - the metric that measures false positive and false negative rates across groups; often in direct conflict with calibration
- [Fairness Metric Conflicts](fairness-metric-conflicts.md) - the mathematical proof that calibration, demographic parity, and equalized odds cannot all be satisfied simultaneously when base rates differ
- [COMPAS/](../COMPAS/) - the audit where calibration vs. equalized odds plays out in full with real data

---

## Further Reading

- [ProPublica: Machine Bias (2016)](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the original investigation that triggered the calibration vs. error rate debate
- [Chouldechova, A.: Fair Prediction with Disparate Impact (2017)](https://arxiv.org/abs/1703.00056) - the paper that proved the mathematical incompatibility between calibration and equal error rates
- [Barocas, Hardt & Narayanan: Fairness and Machine Learning (2023)](https://fairmlbook.org/) - Chapter 3 covers calibration in depth with formal definitions

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
