# Explainer: What is Equalized Odds?

> *The fairness metric that catches a model treating two groups differently - even when overall accuracy looks fine.*

---

## The One-Sentence Definition

**Equalized Odds** is a fairness metric that requires a model to make equally accurate decisions for every demographic group - meaning its true positive rate *and* false positive rate must be the same across protected groups like race, gender, or age.

---

## Why This Matters

Most people check model accuracy and call it done. This misses the problem entirely.

A model can be 90% accurate overall while still making systematically different *types* of mistakes for different groups. It might correctly identify qualified candidates in one group at 91%, while only correctly identifying them in another group at 69%. Same model. Same task. Different outcomes - depending on who you are.

This matters because the two types of errors a model makes are not morally equivalent:

- **False negatives** (missing someone who should have been flagged) can mean a qualified person is rejected, a sick patient goes undiagnosed, or a creditworthy borrower is denied a loan.
- **False positives** (flagging someone who shouldn't have been) can mean an innocent person is detained, an unqualified applicant is passed through, or a healthy patient is over-treated.

If those errors fall unevenly across demographic groups, the model is discriminating - regardless of what its accuracy score says.

This shows up in exactly the systems where it can't afford to:

- hiring pipelines
- loan and credit scoring
- insurance risk assessments
- healthcare triage
- criminal justice risk tools

---

## Real-World Proof: COMPAS Analysis

We can demonstrate this directly using the [ProPublica COMPAS dataset](https://github.com/propublica/compas-analysis).

COMPAS is a risk assessment tool deployed across 46 US states. Judges use its scores to make bail, sentencing, and parole decisions. It doesn't just need to be accurate - it needs to be *equally* accurate for every defendant, regardless of race.

### What We Measured

Training a `RandomForestClassifier(random_state=42)` on `Sex_Code_Text`, `CustodyStatus`, and `MaritalStatus` (race already removed, matching this repo's own "remove race only" recipe - see [proxy-variables.md](proxy-variables.md)), we measured true positive rate (TPR) and false positive rate (FPR) against `ScoreText`-derived `is_high_risk`, broken down by race:

| Group | True Positive Rate | False Positive Rate |
|---|---:|---:|
| Black Defendants | 0.73 | 0.61 |
| White Defendants | 0.64 | 0.43 |
| **Gap** | **0.08** | **0.18** |

Interpretation:

- Black defendants who *will* reoffend are correctly flagged at a somewhat higher rate - but
- Black defendants who *won't* reoffend are also incorrectly flagged at a much higher rate than white defendants

The model isn't just wrong more often for Black defendants. It's wrong in a specific *direction* - over-flagging them as high-risk. Equalized Odds catches this because it checks both error types, not just overall accuracy.

---

## How to Detect It in Python

```python
from fairlearn.metrics import MetricFrame, true_positive_rate, false_positive_rate
import pandas as pd

# Load your data
# y_true  = ground truth labels
# y_pred  = model predictions
# groups  = protected attribute (e.g. race, gender)

metrics = {
    "TPR": true_positive_rate,
    "FPR": false_positive_rate
}

frame = MetricFrame(
    metrics=metrics,
    y_true=y_true,
    y_pred=y_pred,
    sensitive_features=groups
)

print(frame.by_group)
print("\nDifferences:")
print(frame.difference())
```

Example output (this exact recipe, this exact seed - a `RandomForestClassifier` with a fixed seed is not guaranteed bit-identical across CPU architectures and BLAS backends, so treat these as this repo's reference-environment values rather than a universal constant):

```
                  TPR   FPR
Black Defendants  0.73  0.61
White Defendants  0.64  0.43

Differences:
TPR    0.08
FPR    0.18
```

Large differences in either metric indicate an Equalized Odds violation. Run this on every protected attribute in your dataset before deployment.

Install dependency:

```bash
pip install fairlearn
```

---

## The Math

Equalized Odds requires two conditions to hold simultaneously:

**Equal True Positive Rate:**

P(Ŷ = 1 | Y = 1, A = a) = P(Ŷ = 1 | Y = 1, A = b)

**Equal False Positive Rate:**

P(Ŷ = 1 | Y = 0, A = a) = P(Ŷ = 1 | Y = 0, A = b)

Where:

- Ŷ = model prediction
- Y = true label
- A = protected attribute (race, gender, age, etc.)

Both must hold. A model that satisfies one but not the other is still violating Equalized Odds.

---

## Limitations / Trade-offs

Equalized Odds is useful, but it isn't a complete solution on its own.

### It may reduce overall accuracy

Enforcing equal error rates across groups often requires adjusting decision thresholds per group, which can lower aggregate accuracy. There is a real trade-off between group fairness and individual predictive performance.

### It conflicts with calibration

A calibrated model ensures its predicted probabilities are consistent across groups - a 70% risk score means 70% chance of the outcome, for any group. It has been mathematically proven that a model cannot simultaneously satisfy Equalized Odds and be perfectly calibrated, unless base rates are equal across groups. In most real-world datasets, they aren't.

### It conflicts with Demographic Parity

Demographic Parity requires equal positive prediction rates across groups regardless of ground truth. Equalized Odds requires equal accuracy conditional on ground truth. These two definitions cannot both be satisfied at once when base rates differ - which is almost always.

### It doesn't fix the upstream problem

Equalized Odds is a post-hoc measurement. It tells you the model is biased - but it doesn't fix why. If the training data reflects historical discrimination (over-policing, hiring bias, discriminatory lending), the model will learn those patterns even after you correct for error rates. Measuring Equalized Odds is a starting point, not an endpoint.

---

## The Bigger Picture

Equalized Odds violations exist because our models are trained on data generated by unequal systems. A criminal justice dataset carries decades of over-policing. A hiring dataset carries decades of gender and racial exclusion. A healthcare dataset carries the structural inequalities of the American insurance system.

A model trained on that data learns those inequalities - and unless you actively measure both types of errors across every protected group, the bias remains hidden behind an accuracy score that looks fine.

**Equalized Odds is not a cure. It's a diagnostic. Run it before you deploy.**

---

## Related Concepts

### Equal Opportunity

A relaxed version of Equalized Odds. Requires only equal true positive rates - not equal false positive rates. Appropriate when false negatives carry more moral weight than false positives (e.g. missing a qualified candidate), but it lets false positive disparities go unchecked.

### Demographic Parity

Requires equal positive prediction rates regardless of ground truth. Unlike Equalized Odds, it doesn't account for whether the model's decisions are correct - only whether they're equally distributed. Conflicts with Equalized Odds when base rates differ across groups.

### Calibration

Requires that predicted probability scores have a consistent meaning across groups. A model can be perfectly calibrated and still violate Equalized Odds. These two definitions capture different aspects of fairness, and both should be checked.

### Proxy Variables

Even after correcting for Equalized Odds, models can still encode protected attributes through proxy variables - features like zip code, custody status, or employment tenure that correlate with race, age, or class in the training data. Equalized Odds doesn't detect these; proxy variable auditing does. See the [proxy variables explainer](proxy-variables.md).

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - Full COMPAS analysis: biased model → fair model → 82% gap reduction. Equalized Odds violations visible in the raw model outputs.
- [`explainers/proxy-variables.md`](proxy-variables.md) - Why AI stays biased even after you remove protected attributes
- [`explainers/shap-values.md`](shap-values.md) - How to see exactly what drove an AI decision - and use that to catch bias

---

## Further Reading

- [Hardt, Price, Srebro (2016): Equality of Opportunity in Supervised Learning](https://arxiv.org/abs/1610.02413) - the paper that formally defined Equalized Odds
- [Chouldechova (2017): Fair Prediction with Disparate Impact](https://arxiv.org/abs/1703.00056) - the mathematical proof that calibration and Equalized Odds conflict when base rates differ
- [Fairlearn documentation](https://fairlearn.org/v0.8/user_guide/fairness_in_machine_learning.html)
- [ProPublica: Machine Bias (2016)](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the original COMPAS investigation

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
