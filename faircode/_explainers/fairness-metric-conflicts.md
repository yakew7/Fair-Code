# Explainer: Why Fairness Metrics Conflict

> *You can't be fair to everyone at once - and the math proves it.*

---

## The One-Sentence Definition

**Fairness metric conflict** is the mathematically proven impossibility of satisfying multiple fairness criteria simultaneously when base rates differ across demographic groups - meaning any choice of fairness metric is also a choice about who bears the cost of being wrong.

---

## Why This Matters

Most people assume that making an AI "fair" is a single, solvable problem. It isn't. Researchers have formally proven - not just observed, but *proven* - that several common fairness definitions are mutually incompatible except in degenerate edge cases.

This matters in practice because:

- Courts, regulators, and hiring committees each invoke different fairness definitions - and they are often in direct mathematical conflict
- A model optimized to satisfy one metric will *necessarily* perform worse on another
- Choosing a metric is an ethical and political decision, not a technical one - and pretending otherwise is its own form of bias

If you deploy a model and declare it "fair" without specifying which metric you used and why, you have not solved the fairness problem. You have hidden it.

---

## The Three Metrics That Can't All Be True

These are the three most commonly cited fairness criteria in AI systems:

### 1. Demographic Parity
The model produces positive outcomes at equal rates across groups.

```
P(Ŷ=1 | Group=A) = P(Ŷ=1 | Group=B)
```

*Used in:* hiring, lending, admissions audits. Underpins the 80% rule in disparate impact law.

### 2. Equalized Odds
The model makes errors at equal rates across groups - equal true positive rates *and* equal false positive rates.

```
P(Ŷ=1 | Y=1, Group=A) = P(Ŷ=1 | Y=1, Group=B)   [equal TPR]
P(Ŷ=1 | Y=0, Group=A) = P(Ŷ=1 | Y=0, Group=B)   [equal FPR]
```

*Used in:* criminal risk assessment, medical screening. ProPublica's COMPAS critique was built on this metric.

### 3. Predictive Parity (Calibration)
When the model flags someone as high-risk, that flag is equally accurate regardless of group membership.

```
P(Y=1 | Ŷ=1, Group=A) = P(Y=1 | Ŷ=1, Group=B)
```

*Used in:* credit scoring, recidivism prediction. Northpointe's defence of COMPAS was built on this metric.

---

## The Formal Impossibility

Chouldechova (2017) and Kleinberg et al. (2016) independently proved the same result: **when base rates differ between groups, you cannot simultaneously satisfy equalized odds and predictive parity** - except in trivial edge cases where the model is perfect or predicts at random.

The proof is mechanical. If Group A has a higher base rate of positive outcomes than Group B, and your model is calibrated (predictive parity holds), then equalizing true positive rates forces false positive rates to be unequal - and vice versa. You can fix one side of the error table or the other. Not both.

---

## Real-World Proof: COMPAS

The COMPAS debate is the clearest public illustration of this impossibility. ProPublica and Northpointe were both right - using different metrics.

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix

df = pd.read_csv('COMPAS/compas-scores-raw.csv')
df = df[df['Ethnic_Code_Text'].isin(['African-American', 'Caucasian'])].copy()
df = df[df['DisplayText'] == 'Risk of Recidivism'].copy()
df['high_risk'] = df['ScoreText'].isin(['High', 'Medium']).astype(int)
df['race_binary'] = df['Ethnic_Code_Text'].map({'African-American': 1, 'Caucasian': 0})

# Same recipe as COMPAS/unfair.py: race included directly as a feature
X = pd.get_dummies(df[['Sex_Code_Text', 'race_binary', 'CustodyStatus', 'MaritalStatus']])
y = df['high_risk']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)
model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

# Attach predictions back for group analysis
test_df = X_test.copy()
test_df['y_true'] = y_test.values
test_df['y_pred'] = y_pred
test_df['race'] = df.loc[X_test.index, 'Ethnic_Code_Text'].values

def compute_metrics(group_df):
    tn, fp, fn, tp = confusion_matrix(group_df['y_true'], group_df['y_pred'], labels=[0, 1]).ravel()
    tpr = tp / (tp + fn) if (tp + fn) else float('nan')
    fpr = fp / (fp + tn) if (fp + tn) else float('nan')
    ppv = tp / (tp + fp) if (tp + fp) else float('nan')  # precision = predictive parity numerator
    return {'TPR': round(tpr, 3), 'FPR': round(fpr, 3), 'PPV (Precision)': round(ppv, 3),
            'n_predicted_positive': tp + fp}

black = test_df[test_df['race'] == 'African-American']
white = test_df[test_df['race'] == 'Caucasian']

print("Black defendants: ", compute_metrics(black))
print("White defendants: ", compute_metrics(white))
```

**Actual output** (this repo's `COMPAS/compas-scores-raw.csv`, same model/features `COMPAS/unfair.py` uses):

```
Black defendants:  {'TPR': 0.929, 'FPR': 0.781, 'PPV (Precision)': 0.628, 'n_predicted_positive': 1552}
White defendants:  {'TPR': 0.006, 'FPR': 0.003, 'PPV (Precision)': 0.5, 'n_predicted_positive': 6}
```

A seeded `RandomForestClassifier`'s output can shift slightly across CPU/BLAS backends (see issue #521); the White group's PPV in particular rests on only 6 predicted-positive rows and should be read as illustrative, not a precise estimate.

Now look at what each party claimed, and why both were technically correct:

| Metric | ProPublica's Claim | Northpointe's Claim |
|---|---|---|
| **False Positive Rate** | Black FPR 78.1% vs White 0.3% - *unfair* | (didn't dispute this) |
| **Predictive Parity** | (didn't dispute this) | PPV 62.8% vs 50.0% - *closer than the error-rate gap, if noisy on 6 White predictions* |
| **Who bears the cost** | Black defendants wrongly flagged high-risk | - |

**Both claims were mathematically accurate. They were measuring different things.**

ProPublica asked: *do false accusations fall equally?* Northpointe asked: *when we flag someone, are we equally right?* Because Black defendants reoffend at a higher base rate in this dataset - itself a product of over-policing - satisfying one criterion mathematically forces the other to fail.

---

## The Impossibility Visualised

Imagine two groups with different base rates: Group A reoffends at 40%, Group B at 20%.

A calibrated model (predictive parity) assigns risk scores that reflect these real rates. Now you want to equalise false positive rates - the rate at which truly low-risk people are wrongly flagged. To bring Group A's FPR down to match Group B's, you must raise the risk threshold for Group A. But raising the threshold also reduces Group A's true positive rate - now you catch fewer actual reoffenders from Group A. To compensate, you'd need to lower the threshold - which raises the FPR again. The system resists. The math won't let you square this circle.

```python
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Simulate two groups with different base rates
np.random.seed(42)
n = 1000

# Group A: 40% base rate
scores_A_pos = np.random.beta(6, 4, int(n * 0.4))   # reoffenders, higher scores
scores_A_neg = np.random.beta(3, 7, int(n * 0.6))   # non-reoffenders, lower scores
labels_A = [1]*int(n*0.4) + [0]*int(n*0.6)
scores_A = np.concatenate([scores_A_pos, scores_A_neg])

# Group B: 20% base rate
scores_B_pos = np.random.beta(6, 4, int(n * 0.2))
scores_B_neg = np.random.beta(3, 7, int(n * 0.8))
labels_B = [1]*int(n*0.2) + [0]*int(n*0.8)
scores_B = np.concatenate([scores_B_pos, scores_B_neg])

def metrics_at_threshold(scores, labels, threshold):
    preds = (scores >= threshold).astype(int)
    labels = np.array(labels)
    tp = ((preds == 1) & (labels == 1)).sum()
    fp = ((preds == 1) & (labels == 0)).sum()
    tn = ((preds == 0) & (labels == 0)).sum()
    fn = ((preds == 0) & (labels == 1)).sum()
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0
    return tpr, fpr, ppv

thresholds = np.linspace(0.1, 0.9, 50)

tprs_A, fprs_A, ppvs_A = zip(*[metrics_at_threshold(scores_A, labels_A, t) for t in thresholds])
tprs_B, fprs_B, ppvs_B = zip(*[metrics_at_threshold(scores_B, labels_B, t) for t in thresholds])

fig, axes = plt.subplots(1, 3, figsize=(14, 4))
fig.patch.set_facecolor('#0f1117')
for ax in axes:
    ax.set_facecolor('#1a1d27')
    ax.tick_params(colors='#aaaaaa')
    ax.xaxis.label.set_color('#aaaaaa')
    ax.yaxis.label.set_color('#aaaaaa')
    ax.title.set_color('#ffffff')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333344')

axes[0].plot(thresholds, tprs_A, color='#e05c5c', label='Group A (40% base rate)')
axes[0].plot(thresholds, tprs_B, color='#5c9ee0', label='Group B (20% base rate)')
axes[0].set_title('True Positive Rate')
axes[0].set_xlabel('Decision Threshold')
axes[0].legend(facecolor='#1a1d27', labelcolor='white', fontsize=8)

axes[1].plot(thresholds, fprs_A, color='#e05c5c', label='Group A')
axes[1].plot(thresholds, fprs_B, color='#5c9ee0', label='Group B')
axes[1].set_title('False Positive Rate')
axes[1].set_xlabel('Decision Threshold')
axes[1].legend(facecolor='#1a1d27', labelcolor='white', fontsize=8)

axes[2].plot(thresholds, ppvs_A, color='#e05c5c', label='Group A')
axes[2].plot(thresholds, ppvs_B, color='#5c9ee0', label='Group B')
axes[2].set_title('Precision (Predictive Parity)')
axes[2].set_xlabel('Decision Threshold')
axes[2].legend(facecolor='#1a1d27', labelcolor='white', fontsize=8)

plt.suptitle('Fairness Metric Trade-offs Across Groups With Different Base Rates',
             color='white', fontsize=11, y=1.02)
plt.tight_layout()
plt.savefig('fairness-tradeoffs.png', dpi=150, bbox_inches='tight',
            facecolor='#0f1117')
print("Saved: fairness-tradeoffs.png")
```

The curves for Group A and Group B will only coincide if the base rates are equal. They never are, in practice.

---

## How to Navigate the Conflict

### Step 1 - Audit your base rates first

```python
def base_rate_audit(df, outcome_col, group_col):
    """
    Print base rates per group. If they differ significantly,
    fairness metric conflicts are guaranteed.
    """
    rates = df.groupby(group_col)[outcome_col].mean().round(4)
    print("Base rates by group:")
    print(rates.to_string())
    print(f"\nBase rate ratio (max/min): {rates.max() / rates.min():.2f}x")
    if rates.max() / rates.min() > 1.2:
        print("⚠ Base rates differ by >20% - metric conflicts will arise.")
    return rates

# Example
base_rate_audit(df, outcome_col='high_risk', group_col='Ethnic_Code_Text')
```

### Step 2 - Compute all three metrics simultaneously

```python
from sklearn.metrics import confusion_matrix

def full_fairness_audit(y_true, y_pred, groups):
    """
    Returns TPR, FPR, and PPV per group.
    Use to see which metrics are satisfied and which are violated.
    """
    results = {}
    for group in groups.unique():
        mask = groups == group
        tn, fp, fn, tp = confusion_matrix(y_true[mask], y_pred[mask]).ravel()
        results[group] = {
            'TPR (Recall)':     round(tp / (tp + fn), 3) if (tp + fn) > 0 else None,
            'FPR':              round(fp / (fp + tn), 3) if (fp + tn) > 0 else None,
            'PPV (Precision)':  round(tp / (tp + fp), 3) if (tp + fp) > 0 else None,
            'Positive Rate':    round((tp + fp) / (tp + fp + tn + fn), 3),
        }
    return pd.DataFrame(results).T

audit = full_fairness_audit(
    y_true=test_df['y_true'],
    y_pred=test_df['y_pred'],
    groups=test_df['race']
)
print(audit)
```

### Step 3 - Choose your metric deliberately, and document the trade-off

There is no neutral choice. Each metric prioritises a different kind of fairness and imposes a different kind of cost:

| Metric | What it prioritises | Who bears the cost when it fails |
|---|---|---|
| **Demographic Parity** | Equal access to positive outcomes | Groups with higher true positive rates may be under-predicted |
| **Equalized Odds** | Equal error rates in both directions | Predictive accuracy per group may be sacrificed |
| **Predictive Parity** | Equal reliability of predictions | Groups with lower base rates face higher false positive rates |

Document your choice in the same place you document your model card. A model without a declared fairness metric has not been audited - it has been deployed.

---

## The Deeper Problem: Whose Baseline Is the Baseline?

Even before you pick a metric, there is a prior question: are the base rates in your data *true* rates, or are they artefacts of the system that generated the data?

In the COMPAS dataset, Black defendants appear to reoffend at higher rates. But this statistic is built on arrest records - and arrest rates reflect policing patterns, not actual crime rates. A neighbourhood that is over-policed will produce more arrests of its residents, inflating their apparent recidivism rates. The model treats this as ground truth and calibrates to it. Predictive parity then holds - but it holds against a corrupted baseline.

This is why choosing a metric is not sufficient. You must also audit the data that defines your ground truth. See the [Proxy Variables explainer](proxy-variables.md) and [Sampling Bias explainer](sampling-bias.md) for the methodology.

---

## Limitations

**There is no universally correct metric.** The choice depends on the domain, the asymmetry between error types, and a normative judgment about whose interests to protect. A hiring algorithm and a medical screening tool warrant different choices, for substantive ethical reasons - not because the math differs.

**Metric satisfaction does not prove fairness.** A model can satisfy demographic parity by systematically reducing outcomes for an advantaged group rather than improving them for a disadvantaged group. Parity in mediocrity is not justice. Always inspect absolute rates, not just gaps.

**Intersectionality is not captured by pairwise audits.** Auditing by race and by gender separately misses discrimination against Black women specifically, or other intersecting identities. Pairwise metrics pass while intersectional disparities persist. True auditing requires disaggregating by all relevant combinations - which is why large, representative datasets are a prerequisite.

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - The ProPublica / Northpointe conflict is a direct illustration of this metric incompatibility
- [`explainers/equalized-odds.md`](equalized-odds.md) - Deep dive on the error-rate fairness metric
- [`explainers/demographic-parity.md`](demographic-parity.md) - Deep dive on the equal-outcome-rate metric (the third leg of the impossibility triangle)
- [`explainers/proxy-variables.md`](proxy-variables.md) - How corrupted base rates flow into metric calculations
- [`explainers/disparate-impact.md`](disparate-impact.md) - The legal metric (demographic parity under the 80% rule) and its limits
- [`explainers/sampling-bias.md`](sampling-bias.md) - Why ground truth in training data may not be true

---

## Further Reading

- [Chouldechova: Fair Prediction with Disparate Impact (2017)](https://arxiv.org/abs/1703.00056) - formal proof of the incompatibility between equalized odds and predictive parity
- [Kleinberg, Mullainathan & Raghavan: Inherent Trade-offs in the Fair Determination of Risk Scores (2016)](https://arxiv.org/abs/1609.05807) - independent proof of the same impossibility result
- [Barocas & Hardt: Fairness and Machine Learning](https://fairmlbook.org/) - Chapter 2 (Classification) and Chapter 4 (Legal Background) are directly relevant
- [ProPublica: Machine Bias (2016)](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the audit that made this conflict visible to the public

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
