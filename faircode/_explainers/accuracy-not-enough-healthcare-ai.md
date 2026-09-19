> *A model that predicts "no readmission" for every single patient can be 97% accurate in a hospital where only 3 in 100 come back - and it will have correctly identified exactly zero of the people who needed help. In healthcare, the headline accuracy number and the number of lives the model actually protects are often two completely different things.*

## The One-Sentence Definition

**"Accuracy is not enough"** means that the fraction of predictions a model gets right - its accuracy - can stay high while the model systematically fails the specific patients and groups that matter most, because accuracy averages over everyone, is dominated by the majority outcome when events are rare, and says nothing about which patients the errors land on.

## Why It Matters

In healthcare the outcomes worth predicting - a sepsis onset, a 30-day readmission, a missed cancer, a high-cost complication - are usually **rare**. When an event happens to only a few percent of patients, a model can score extremely high accuracy by quietly learning to predict "nothing will happen" almost every time. That model is accurate and useless: it never flags the people the tool exists to catch.

Worse, a single accuracy number is an **average over the whole population**, so it can hide a model that works well for the majority group and badly for a minority one. Two hospitals' models can both report 95% accuracy while one catches 80% of at-risk Black patients and the other catches 40% - the aggregate number cannot tell them apart. Accuracy is also tied to one **decision threshold**, so it says nothing about the trade-off between missing a sick patient (a false negative) and a false alarm (a false positive) - and in medicine those two errors are never equally costly.

This is why a fairness or safety audit that stops at accuracy is not an audit at all. The questions that matter - *who does the model miss, and how often, in which group* - live in per-group recall, false-negative rates, and calibration, not in the headline score.

## The Accuracy Paradox

The accuracy paradox is the point where high accuracy and low usefulness meet: the rarer the event, the easier it is to score well by ignoring it.

| Model on a 3%-readmission population | Accuracy | Readmitted patients caught |
|---|---|---|
| Predicts "no readmission" for everyone | 97% | 0 of every 100 at-risk patients |
| Flags the genuinely high-risk 3% | lower than 97% | most of them |

The "predict nothing" model wins on accuracy and loses on the only thing that matters. A useful clinical model often *accepts* a worse accuracy score on purpose - it takes on more false positives to stop missing true cases. Which means accuracy going **down** can be the sign of a **better** model, and a fairness gap can hide entirely inside a flat accuracy number: the same 95% can be 95% for one group and 95% for another while the false negatives are concentrated in whichever group the training data under-represented.

## Concrete Example: Healthcare Readmission - Audit 06

Audit 06 in this repo predicts 30-day hospital readmission from the Diabetes 130-US Hospitals dataset (101,766 records), with race and age as protected attributes. Readmission is a **rare, imbalanced** outcome - the baseline models flag only a tiny fraction of patients as high risk - so accuracy on this task is high almost by construction, and it is exactly the wrong number to trust.

Dropping the protected attributes and their proxies moved the audit's demographic-parity gaps in different directions per attribute (race 0.01% → 0.06%, actually widening; age 0.31% → 0.06%, an ~80% reduction) - those describe how *often* each group is flagged. They say nothing about whether the model's *misses* fall evenly. A model can post identical accuracy for two groups and still miss the sicker patients in one of them - which is precisely what a group-by-group accuracy-vs-recall breakdown, not the headline score, is built to reveal:

```python
group_accuracy_vs_recall(readmission_df, y_true_col="readmitted",
                         y_pred_col="predicted_high_risk", group_col="race")
#         accuracy  recall  n
# White       0.94    0.71  86527
# Black       0.94    0.55  10091
# gap         0.00    0.16    NaN
```

This is illustrative output, not a published result of Audit 06, but it shows the trap the accuracy number sets: identical 94% accuracy across groups sitting on top of a 16-point recall gap - the model quietly misses far more at-risk Black patients, and accuracy alone certifies it as fair.

This pattern is not hypothetical. Obermeyer et al. (2019) found a commercial risk algorithm used on millions of patients assigned Black and White patients the same risk score at the same predicted cost, but at that shared score the Black patients were considerably sicker - the model was systematically under-flagging them. No accuracy metric surfaced it; a group-stratified analysis of who got missed did.

## Detection Code

Computes accuracy alongside recall (sensitivity) and the false-negative rate **per group**, so a subgroup the model quietly under-serves cannot hide inside a high aggregate accuracy.

```python
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix


def group_accuracy_vs_recall(df, y_true_col, y_pred_col, group_col):
    """
    For each group, reports accuracy next to recall (sensitivity) and the
    false-negative rate - the numbers accuracy hides. A wide recall / FNR
    gap alongside a flat accuracy gap is the accuracy-paradox signature:
    the model looks equally good everywhere and misses one group's true
    cases far more often.

    Parameters:
        df: DataFrame with true labels, binary predictions, and group membership
        y_true_col: ground-truth binary label (1 = event actually occurred)
        y_pred_col: model's binary prediction (1 = flagged high risk)
        group_col: protected attribute or group label

    Returns a DataFrame indexed by group (plus a "gap" row) with
    accuracy, recall, fnr, n.
    """
    rows = []
    for group, sub in df.groupby(group_col):
        tn, fp, fn, tp = confusion_matrix(
            sub[y_true_col], sub[y_pred_col], labels=[0, 1]
        ).ravel()
        total = tn + fp + fn + tp
        accuracy = (tp + tn) / total if total else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        fnr = fn / (tp + fn) if (tp + fn) else float("nan")
        rows.append({"group": group, "accuracy": accuracy,
                     "recall": recall, "fnr": fnr, "n": len(sub)})

    result = pd.DataFrame(rows).set_index("group")
    result.loc["gap"] = [
        result["accuracy"].max() - result["accuracy"].min(),
        result["recall"].max() - result["recall"].min(),
        result["fnr"].max() - result["fnr"].min(),
        float("nan"),
    ]
    return result


def majority_class_baseline(y_true):
    """
    The accuracy a do-nothing model gets by always predicting the majority
    class. If a real model barely beats this, its high accuracy is coming
    from the base rate, not from finding at-risk patients.
    """
    y = pd.Series(y_true)
    return max(y.mean(), 1 - y.mean())


# Usage example
# gaps = group_accuracy_vs_recall(readmission_df, "readmitted", "predicted_high_risk", "race")
# floor = majority_class_baseline(readmission_df["readmitted"])
```

## Limitations

### 1. Recall alone can be gamed too

A model can hit high recall by flagging almost everyone, trading a missed-patient problem for an alert-fatigue one. Read recall next to precision and the false-positive rate, not in isolation - no single number is enough, which is the whole point.

### 2. The right threshold is a clinical value judgment

How much recall to buy with how many false positives depends on the relative cost of a missed case versus a false alarm - a clinical and ethical decision, not something accuracy or any other metric decides on its own.

### 3. Small subgroups make per-group rates noisy

Recall computed on a few hundred patients has a wide confidence interval. Report subgroup sizes and bootstrap a confidence interval before treating a per-group gap as real rather than as a prompt to investigate.

### 4. Equal metrics still do not guarantee equal outcomes

Even a model with equal recall across groups only controls what it predicts. If flagged patients in one group are less likely to actually receive the follow-up care the flag was meant to trigger, on-paper parity never becomes equal real-world benefit.

## Related Concepts

* [False Positives vs. False Negatives in Medical Risk Models](false-positives-vs-false-negatives.md) - the two error types accuracy blends together, and why a missed diagnosis and a false alarm are almost never equally costly.
* [What Is a ROC Curve and AUC?](roc-curve-auc.md) - why a threshold-free summary score has the same blind spots as accuracy for per-group performance.
* [What Is a Confusion Matrix?](confusion-matrix.md) - where accuracy, recall, and the false-negative rate all come from, and why the last two matter more here.
* [Calibration](calibration.md) - why a model can be accurate on average and still assign scores that mean different things for different groups.
* [What Is Class Imbalance?](class-imbalance.md) - the rare-event setting that lets a "predict nothing" model score high accuracy in the first place.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the rare-outcome audit behind the example above, where accuracy is high by construction and the real question is who gets missed.
* [`Insurance Denial/`](../Insurance%20Denial/) - a second health-adjacent audit where a wrongly denied claim (false negative) and a wrongly paid one (false positive) carry very different costs.

## Further Reading

* [Obermeyer, Z., Powers, B., Vogeli, C., Mullainathan, S. (2019): Dissecting racial bias in an algorithm used to manage the health of populations](https://www.science.org/doi/10.1126/science.aax2342) - the study behind the concrete example; a race-neutral-looking, accurate-looking algorithm that systematically under-flagged sicker Black patients.
* [Rajkomar, A., Hardt, M., Howell, M.D., Corrado, G., Chin, M.H. (2018): Ensuring Fairness in Machine Learning to Advance Health Equity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6594166/) - how model design, data, and clinician interaction each decide which patients absorb a clinical model's errors.
* [Saito, T., Rehmsmeier, M. (2015): The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432) - why aggregate and threshold-free scores mislead exactly in the rare-event regime healthcare lives in.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
