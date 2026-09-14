# What Is Predictive Parity?

> *COMPAS's defenders and its critics ran fairness checks on the same defendants and reached opposite verdicts - because predictive parity and equalized odds are both legitimate, and when base rates differ, they mathematically cannot both hold.*

## The One-Sentence Definition

**Predictive parity** is satisfied when the Positive Predictive Value, the share of positively-flagged cases that are actually positive, is equal across groups, so a "high risk" label carries the same real-world meaning no matter who receives it.

## Why It Matters

Algorithmic risk scores decide who gets held before trial, whose insurance claim gets flagged for review, and whose loan application gets extra scrutiny. Over 1M+ people are assessed by COMPAS-style recidivism tools every year, and 46 US states have used one in criminal sentencing. When a vendor says a "high risk" flag is trustworthy, predictive parity is usually the claim being made: given the flag, the predicted outcome holds up at the same rate for every group.

The non-obvious part is that "trustworthy for everyone" is not the same fairness property as "fair to everyone." A score can satisfy predictive parity perfectly and still send one group to jail on false pretenses far more often than another. Which group bears that cost depends on the false positive rate, a completely different metric, and the two cannot both be balanced unless the underlying base rates already match.

## Predictive Parity vs Equalized Odds

Predictive parity is a **sufficiency** metric: it conditions on the *prediction* and asks whether that prediction means the same thing across groups. Equalized Odds (see [explainers/equalized-odds.md](equalized-odds.md)) is a **separation** metric: it conditions on the *true outcome* and asks whether error rates match.

| Metric | Conditions on | Question it asks |
|---|---|---|
| Demographic Parity | nothing (prior) | Are positive predictions handed out at the same rate? |
| Equalized Odds | true label | Given the actual outcome, are error rates equal? |
| Predictive Parity | predicted label | Given a positive prediction, is it equally trustworthy? |

```
PPV(group) = TP(group) / (TP(group) + FP(group))

Predictive Parity holds when:  PPV(group a) ≈ PPV(group b)
```

Chouldechova (2017) proved the mechanism algebraically: if predictive parity holds but the base rate of the outcome differs between two groups, the false positive rate and false negative rate cannot be equal across those same groups. It is not a modeling flaw. It is an identity that follows directly from the definitions once base rates diverge.

## Concrete Example: COMPAS - Audit 01

The [COMPAS](../COMPAS/) audit in this repo uses the same ProPublica recidivism dataset at the center of the 2016 "Machine Bias" investigation, where race is the protected attribute - but this repo's `COMPAS/compas-scores-raw.csv` has no independent two-year re-offense outcome to check predictive parity against (per `COMPAS/audit.yaml`, its target is `ScoreText`, COMPAS's own risk label). The real-world 2016 controversy - which *is* about actual two-year re-offense, from ProPublica's own separate analysis file - unfolded exactly as follows:

ProPublica and Northpointe (COMPAS's vendor) checked different fairness criteria on that dataset and both were internally correct. ProPublica's reading, an error-rate check, found the false positive rate for Black defendants was roughly double that of white defendants: Black defendants who did not reoffend were flagged high-risk far more often. Northpointe's reading, a predictive-parity check, found PPV was close across race: a "high risk" label corresponded to actual reoffending at a similar rate for both groups. Northpointe presented that second result as proof the tool was not biased.

The same mechanism is directly reproducible in this repo on [German Credit Lending](../German%20Credit%20Lending/), where `class` (good/bad credit history) is a real recorded label a model can actually be scored against:

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

df = pd.read_csv("German Credit Lending/credit_customers.csv")
df["target"] = (df["class"] == "good").astype(int)
df["is_young"] = (df["age"] < 30).astype(int)

cat_cols = ["checking_status", "credit_history", "purpose", "savings_status",
            "employment", "personal_status", "other_parties", "property_magnitude",
            "other_payment_plans", "housing", "job", "own_telephone", "foreign_worker"]
for col in cat_cols:
    df[col] = LabelEncoder().fit_transform(df[col])

features = ["checking_status", "duration", "credit_history", "purpose", "credit_amount",
            "savings_status", "employment", "installment_commitment", "personal_status",
            "other_parties", "residence_since", "property_magnitude", "age",
            "other_payment_plans", "housing", "existing_credits", "job",
            "num_dependents", "own_telephone", "foreign_worker"]

X_train, X_test, y_train, y_test, g_train, g_test = train_test_split(
    df[features], df["target"], df["is_young"], test_size=0.2, random_state=42, stratify=df["target"])
model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)

predictions = pd.DataFrame({"target": y_test.values, "is_good_credit_pred": model.predict(X_test),
                            "is_young": g_test.values})

ppv_by_age, gap = predictive_parity_gap(
    predictions, y_true="target", y_pred="is_good_credit_pred", group_col="is_young"
)
```

**Actual output** (`is_young`: 1 = under 30, 0 = 30+):

```
PPV by group:
  0: 78.76%
  1: 73.08%
Predictive Parity Gap: 5.68%
```

A real, if modest, predictive-parity gap - a "good credit" flag is a little more trustworthy for older applicants than younger ones. The COMPAS case above is the more dramatic historical illustration of the same trade-off (PPV close, FPR far apart), just not one this repo's own file can recompute end to end.

## Detection Code

Compute Positive Predictive Value per group, then pair it with a base-rate check, since a small PPV gap next to a large base-rate gap is the signature Chouldechova identified.

```python
import pandas as pd


def predictive_parity_gap(df: pd.DataFrame, y_true: str, y_pred: str, group_col: str):
    """
    Computes Positive Predictive Value (PPV) per group and the resulting
    predictive-parity gap.

    Parameters:
        df: dataframe containing predictions and outcomes
        y_true: column name of the ground-truth binary label
        y_pred: column name of the model's binary prediction
        group_col: column name of the protected attribute

    Returns:
        (dict of PPV by group, float gap between the max and min PPV)
    """
    ppv_by_group = {}
    for group, sub in df.groupby(group_col):
        predicted_positive = sub[sub[y_pred] == 1]
        if len(predicted_positive) == 0:
            ppv_by_group[group] = float("nan")
            continue
        true_positives = (predicted_positive[y_true] == 1).sum()
        ppv_by_group[group] = true_positives / len(predicted_positive)

    gap = max(ppv_by_group.values()) - min(ppv_by_group.values())

    print("PPV by group:")
    for g, v in ppv_by_group.items():
        print(f"  {g}: {v:.2%}")
    print(f"Predictive Parity Gap: {gap:.2%}")

    return ppv_by_group, gap


def base_rate_gap(df: pd.DataFrame, y_true: str, group_col: str):
    """
    Computes the true prevalence of the positive outcome per group.
    A large gap here next to a small PPV gap indicates the Chouldechova
    trade-off is active: predictive parity is being bought at the cost
    of unequal error rates.
    """
    rates = df.groupby(group_col)[y_true].mean()
    print("Base rate (true prevalence) by group:")
    print(rates)
    return rates.max() - rates.min()


# Usage example
# predictive_parity_gap(compas_df, y_true="two_year_recid", y_pred="flagged_high_risk", group_col="race")
# base_rate_gap(compas_df, y_true="two_year_recid", group_col="race")
```

## Limitations and Trade-offs

### 1. It cannot be satisfied alongside Equalized Odds when base rates differ

This is not a modeling choice, it is Chouldechova's impossibility result. If your domain has meaningfully different base rates across groups, you have to pick which metric to optimize for and be explicit about why.

### 2. A close PPV does not mean the harm is evenly distributed

As the COMPAS case shows, predictive parity can hold while one group absorbs a much larger false-positive rate. Reporting PPV alone, without the accompanying false-positive and false-negative rates, can make a system look fairer than the people affected by it actually experience.

### 3. Small subgroups produce noisy PPV estimates

PPV is computed only over the positively-predicted subset. If a group is small or rarely flagged positive, the denominator shrinks and the estimate becomes unstable. A large-looking gap in a small subgroup may be sampling noise rather than a real disparity, and a small gap can hide real disparity in a subgroup too small to measure reliably.

### 4. It says nothing about where the threshold is set

Predictive parity is a property of the decision threshold that produced the predictions, not a property of the underlying score. Moving the threshold up or down can shift PPV without changing whether the underlying risk score itself is fair, so a system can be re-tuned to pass a predictive-parity check without addressing the base-rate disparity driving it.

## Related Concepts

* [What is Equalized Odds?](equalized-odds.md) - the error-rate metric predictive parity trades off against once base rates diverge.
* [What is Demographic Parity?](demographic-parity.md) - the simpler, prior-only metric that ignores ground truth entirely, unlike predictive parity's reliance on it.
* [Why Fairness Metrics Conflict](fairness-metric-conflicts.md) - the full impossibility-theorem write-up that this explainer's COMPAS case is a worked instance of.
* [What is Disparate Impact?](disparate-impact.md) - a rate-based legal threshold that, like predictive parity, can be satisfied while a different fairness property is violated.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the audit built on the same ProPublica dataset behind the real-world predictive-parity dispute described above.

## Further Reading

* [Angwin, J. et al. (2016): Machine Bias](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the original ProPublica investigation that surfaced the COMPAS false-positive disparity.
* [Chouldechova, A. (2017): Fair Prediction with Disparate Impact](https://arxiv.org/abs/1610.07524) - the algebraic proof that predictive parity and error-rate balance conflict when base rates differ.
* [Kleinberg, J., Mullainathan, S., Raghavan, M. (2017): Inherent Trade-Offs in the Fair Determination of Risk Scores, ITCS 2017](https://arxiv.org/pdf/1609.05807) - an independent impossibility result reaching the same conclusion via a different route.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
