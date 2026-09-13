> *A model can rank a random high-risk person above a random low-risk one about 68 times out of 100 - a perfectly ordinary score by the usual benchmark - and still send the wrong people to jail, and do it unevenly across race. AUC measures the ranking. It says nothing about where you draw the line, or who pays when the line is in the wrong place.*

## The One-Sentence Definition

**A ROC curve** plots a binary classifier's true positive rate against its false positive rate at every possible decision threshold, and **AUC** - the area under that curve - collapses the whole curve into one number: the probability that the model gives a randomly chosen positive case a higher score than a randomly chosen negative one. It is a threshold-free measure of *ranking* quality, which is exactly why it can look reassuring while hiding the two things fairness depends on - where you set the threshold, and whether the ranking is equally good for every group.

## Why It Matters

AUC is the single number that ends up on the model card, in the paper's abstract, and in the slide that gets the project approved. It earns that spot honestly: it does not depend on an arbitrary threshold, it is not fooled by class imbalance the way raw accuracy is, and it summarizes performance across every operating point at once. For comparing two models in the abstract, it is a reasonable first pass.

For deciding whether a model is *fair*, it is close to useless on its own, for three reasons.

First, AUC is **aggregate over the whole population**. It is a single average of ranking quality, and an average can stay high while a minority subgroup's ranking quality is much worse. A model with an overall AUC of 0.85 can quietly be a 0.87 ranker for the majority group and a 0.68 ranker for a smaller one - and nobody deploying on the headline number would ever know.

Second, AUC is **threshold-free, but harm is not**. Real systems do not deploy a curve; they deploy a single threshold, and every actual decision - bail granted, claim denied, patient flagged - happens at that one point. Two models with identical AUC can behave completely differently at the threshold you ship, one spreading its false positives evenly and the other concentrating them in one group. AUC integrates over all thresholds precisely so it can ignore the one you chose.

Third, AUC **ignores calibration**. It only cares about the *order* of the scores, not their values. A model can rank cases perfectly and still assign scores that mean different things for different groups - see [Calibration](calibration.md) - and AUC will happily report a high number either way.

## Reading a ROC Curve

Every point on a ROC curve is one threshold. As you sweep the threshold from strict to lenient, you trace the curve from the bottom-left to the top-right:

- The **y-axis is the true positive rate** (sensitivity, recall) - of the people who really are positive, what fraction did the model catch.
- The **x-axis is the false positive rate** (1 - specificity) - of the people who really are negative, what fraction did the model wrongly flag.
- The **diagonal line** from corner to corner is a coin flip: AUC 0.5, no ranking ability at all.
- The **top-left corner** is a perfect classifier: every positive caught, no negatives flagged, AUC 1.0.

A curve that bows toward the top-left is a better ranker. The area underneath it is the AUC.

| AUC | Rough interpretation |
|---|---|
| 0.5 | No better than random guessing |
| 0.6 - 0.7 | Weak - only slightly better than a coin flip |
| 0.7 - 0.8 | Acceptable for many applied settings |
| 0.8 - 0.9 | Strong ranking ability |
| > 0.9 | Excellent - or a sign of data leakage, worth checking |

| What AUC tells you | What AUC does not tell you |
|---|---|
| How well the model *orders* cases by risk | Where you should set the decision threshold |
| A threshold-independent summary of ranking | How the model behaves at the threshold you deploy |
| One number to compare models at a glance | Whether ranking quality is equal across groups |
| Robustness to class imbalance | Whether the scores are calibrated or comparable between groups |

## Concrete Example: COMPAS - Audit 01

Audit 01 in this repo models COMPAS's own high/medium risk label from the ProPublica dataset (3,254 test records), with race as the protected attribute; it does not predict an independent two-year recidivism outcome. Its baseline models are ordinary, unremarkable rankers: the logistic-regression baseline lands at an **AUC of 0.68**, and the random forest at **0.69** (frozen figures from `paper/results-frozen/summary.csv` and `results_performance.csv`).

That number sits squarely in the "weak" band - the model barely out-ranks a coin flip. But the documented harm in COMPAS was never really about *overall* ranking quality. It was about what happened at the operating threshold: Black defendants who did not go on to reoffend were labeled high-risk at nearly twice the rate of comparable white defendants. That is a false-positive-rate gap - a single point on the ROC curve, read separately for each group - and the aggregate AUC of 0.68 averages straight over it.

Plot a separate ROC curve for each group and the story changes. The two curves can diverge, and even when their *areas* are similar, the groups can sit at very different points along their own curves at one shared threshold. Neither of those facts is visible in a single pooled AUC:

```python
per_group_auc(compas_df, y_true_col="two_year_recid",
              y_score_col="risk_score", group_col="race")
#         auc     n
# White  0.69  1800
# Black  0.66  1454
# gap    0.03   NaN
```

This is illustrative output, not a published result of Audit 01, but it shows the trap: a small AUC gap (here 3 points) can look benign while a large false-positive-rate gap hides underneath it at the deployed threshold. AUC is the wrong instrument for that question - you need a per-group, per-threshold view, which is what [Equalized Odds](equalized-odds.md) formalizes.

## Detection Code

Computes AUC within each group (so a low-AUC subgroup cannot hide inside a high overall number), and returns the per-group ROC points so you can overlay the curves and see where they diverge.

```python
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve


def per_group_auc(df, y_true_col, y_score_col, group_col):
    """
    Computes AUC within each group, plus the gap between the best- and
    worst-ranked group. A wide gap means the model orders cases well for
    one group and poorly for another - invisible in the pooled AUC.

    Parameters:
        df: DataFrame with true labels, model scores, and group membership
        y_true_col: column of the ground-truth binary label (1 = positive)
        y_score_col: column of the model's continuous score or probability
        group_col: column of the protected attribute or group label

    Returns a DataFrame indexed by group (plus a "gap" row) with auc, n.
    """
    rows = []
    for group, sub in df.groupby(group_col):
        # AUC is undefined if a group has only one class present.
        if sub[y_true_col].nunique() < 2:
            auc = float("nan")
        else:
            auc = roc_auc_score(sub[y_true_col], sub[y_score_col])
        rows.append({"group": group, "auc": auc, "n": len(sub)})

    result = pd.DataFrame(rows).set_index("group")
    result.loc["gap"] = [result["auc"].max() - result["auc"].min(), float("nan")]
    return result


def group_roc_points(df, y_true_col, y_score_col, group_col):
    """
    Returns, per group, the (fpr, tpr, thresholds) arrays for roc_curve.
    Overlay these to see whether the curves diverge, and where each group
    sits on its own curve at a shared decision threshold.
    """
    curves = {}
    for group, sub in df.groupby(group_col):
        if sub[y_true_col].nunique() < 2:
            continue  # a one-class group has no ROC curve
        fpr, tpr, thresholds = roc_curve(sub[y_true_col], sub[y_score_col])
        curves[group] = {"fpr": fpr, "tpr": tpr, "thresholds": thresholds}
    return curves


# Usage example
# gaps = per_group_auc(compas_df, "two_year_recid", "risk_score", "race")
# curves = group_roc_points(compas_df, "two_year_recid", "risk_score", "race")
```

## Limitations

### 1. AUC is threshold-free, but every deployed decision is not

AUC deliberately averages over all thresholds. The moment you ship a model you pick exactly one, and all real harm accrues there. Report the false positive and false negative rates *at your operating threshold*, by group, alongside any AUC - never instead of it.

### 2. A high overall AUC can hide a low subgroup AUC

A pooled AUC is a population average weighted by group size, so a small group with poor ranking quality barely moves it. Always compute AUC within each group, and treat a wide per-group gap as a signal to investigate, not a rounding error.

### 3. Small groups make per-group AUC noisy

An AUC computed on a few hundred cases has a wide confidence interval, and a group with only one class present has no AUC at all. Report subgroup sizes next to the rates, and bootstrap a confidence interval before calling a gap real.

### 4. Equal AUC across groups is not fairness

Two groups can have identical AUCs and still be treated unequally: same ranking quality, but a single threshold lands at a high-false-positive point for one group and a low one for the other. Equal ranking quality does not imply equal errors, equal calibration, or equal outcomes.

## Related Concepts

* [False Positives vs. False Negatives in Medical Risk Models](false-positives-vs-false-negatives.md) - what actually happens at the single threshold AUC averages over, and why the two error types are rarely equally costly.
* [Equalized Odds](equalized-odds.md) - the fairness metric that reads the ROC curve per group, requiring equal true positive *and* false positive rates instead of just equal area.
* [Calibration](calibration.md) - why AUC's blindness to the actual score values lets a well-ranked model still mean different things for different groups.
* [What Is Predictive Parity?](predictive-parity.md) - the COMPAS dispute in full, where two defensible error-based definitions of fairness could not both hold at once.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the recidivism audit behind the concrete example above, where a middling AUC coexisted with a large racial false-positive gap.
* [`Insurance Denial/`](../Insurance%20Denial/) - a health-adjacent audit where the threshold you pick on the ROC curve decides who gets a claim wrongly denied versus wrongly paid.

## Further Reading

* [Fawcett, T. (2006): An Introduction to ROC Analysis](https://www.sciencedirect.com/science/article/abs/pii/S016786550500303X) - the standard practical reference for reading ROC curves and the exact meaning of AUC.
* [Hanley, J.A., McNeil, B.J. (1982): The Meaning and Use of the Area Under a ROC Curve](https://pubs.rsna.org/doi/10.1148/radiology.143.1.7063747) - the paper that established AUC's probabilistic interpretation as the ranking probability.
* [Barocas, S., Hardt, M., Narayanan, A. (2019): *Fairness and Machine Learning*](https://fairmlbook.org/classification.html) - the classification chapter connects ROC geometry directly to group fairness criteria, showing why a single threshold on one shared curve cannot satisfy them all when base rates differ.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
