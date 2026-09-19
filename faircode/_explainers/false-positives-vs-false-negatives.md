> *A model that misses a sick patient and a model that misses a healthy one have both made an error - but only one of those errors can kill someone, and a single accuracy number cannot tell you which model made which mistake, or to whom.*

## The One-Sentence Definition

**A false positive vs. false negative trade-off** is the unavoidable choice a risk model makes at its decision threshold between flagging people who will not actually experience the outcome (false positives) and missing people who will (false negatives) - and in medical risk models, that choice is rarely paid for equally across demographic groups.

## Why It Matters

In medicine, the two error types are not interchangeable. A false positive on a sepsis alert means an unnecessary blood draw and a false alarm. A false negative means a patient who needed early antibiotics does not get them. A false positive on a hospital readmission model means a wasted phone call from a care manager. A false negative means a preventable readmission, a penalty for the hospital, and a patient who relapses without support. The same asymmetry shows up in cancer screening, suicide-risk scoring, and insurance triage: missing a true case is almost always more expensive, in health and in dollars, than a false alarm.

This is why a model's overall accuracy or AUC can look excellent while quietly failing one group. Two models can hit the same 90% accuracy on the same population and still make completely different trades: one spreads its false negatives evenly, the other concentrates them in a single demographic group. Demographic parity, the metric most audits start with, only checks how often each group gets a positive prediction. It says nothing about which predictions were wrong, or in which direction. A model can pass a demographic parity check and still be silently under-flagging sicker patients in one group - which is exactly what happened in the most consequential case of this kind on record.

## False Positives vs. False Negatives

| | False Positive | False Negative |
|--|--|--|
| What happens | Model flags high risk; the event does not occur | Model says low risk; the event occurs anyway |
| Immediate cost | Extra test, outreach call, or short-term treatment | Missed intervention, delayed treatment, missed enrollment |
| Downstream cost | Alert fatigue, wasted clinical capacity, patient anxiety | Disease progression, preventable readmission, malpractice exposure |
| Who absorbs it | Health system budget, clinician time | Patient's health, sometimes the patient's life |

A model's decision threshold controls the trade-off directly. Lower the threshold and the model catches more true cases (fewer false negatives) at the cost of more false alarms (more false positives). Raise it and the reverse happens. Because a missed diagnosis is usually costlier than a false alarm, clinical risk models are often tuned deliberately toward higher sensitivity, accepting a worse false positive rate on purpose.

The fairness problem sits one layer beneath this. A single global threshold, chosen once for the whole population using an aggregate cost function, assumes the model's risk scores mean the same thing for every group. If the training data under-represents one group's true risk (through label bias, unequal access to care, or a proxy that behaves differently by group), the same threshold can produce a low false negative rate for one group and a high one for another - even while the overall accuracy number stays flat.

## Concrete Example: Healthcare Readmission - Audit 06

Audit 06 in this repo predicts 30-day hospital readmission risk from the Diabetes 130-US Hospitals dataset (101,766 records), with race and age as protected attributes and `payer_code`, `discharge_disposition_id`, and `number_inpatient` as identified proxies.

Dropping the protected attributes and their proxies moved the audit's demographic parity gaps in different directions per attribute: race actually widened from 0.01% to 0.06%, while age fell from 0.31% to 0.06% (an ~80% reduction). Those numbers describe how often each group was flagged as high risk overall. They say nothing about whether the model's mistakes, when it made them, fell more heavily on one group's missed cases than the other's. That second question needs a group-by-group breakdown of false positive and false negative rates, not just the flag rate:

```python
gaps = error_rate_gaps(
    readmission_df,
    y_true_col="readmitted",
    y_pred_col="predicted_high_risk",
    group_col="race",
)
print(gaps)
#            fpr    fnr      n
# White     0.18   0.09  86527
# Black     0.19   0.24  10091
# gap       0.01   0.15    NaN
```

This is illustrative output, not a published result of Audit 06, but it shows the pattern demographic parity alone would miss: a near-identical false positive rate across groups (a 1-point gap) sitting next to a 15-point false negative rate gap. The model would look fair on flag rate and badly unfair on who gets missed.

This exact pattern is not hypothetical. Obermeyer et al. (2019) found that a commercial risk-prediction algorithm used on millions of patients assigned Black and White patients the same risk score at the same level of predicted cost, but at that shared score Black patients were considerably sicker - the algorithm was systematically under-flagging them. Correcting the label the algorithm predicted (cost, a proxy, instead of illness) would have raised the share of Black patients identified for extra care from 17.7% to 46.5%.

The fix in both cases is the same: check false positive and false negative rates by group directly, using a metric like Equalized Odds, instead of stopping at the aggregate flag rate.

## Detection Code

Computes false positive and false negative rates per group, and sweeps candidate thresholds to find the one that minimizes a cost-weighted total error, letting the analyst encode that a missed case is worse than a false alarm.

```python
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix


def error_rate_gaps(df, y_true_col, y_pred_col, group_col):
    """
    Computes the false positive rate (FPR) and false negative rate (FNR) for
    each group in `group_col`, plus the gap between the highest and lowest
    group for each rate.

    Parameters:
        df: DataFrame with true labels, binary predictions, and group membership
        y_true_col: column name of the ground-truth binary label (1 = event occurred)
        y_pred_col: column name of the model's binary prediction (1 = flagged high risk)
        group_col: column name of the protected attribute or group label

    Returns a DataFrame indexed by group (plus a "gap" row) with fpr, fnr, n.
    """
    rows = []
    for group, sub in df.groupby(group_col):
        tn, fp, fn, tp = confusion_matrix(
            sub[y_true_col], sub[y_pred_col], labels=[0, 1]
        ).ravel()
        fpr = fp / (fp + tn) if (fp + tn) else float("nan")
        fnr = fn / (fn + tp) if (fn + tp) else float("nan")
        rows.append({"group": group, "fpr": fpr, "fnr": fnr, "n": len(sub)})

    result = pd.DataFrame(rows).set_index("group")
    result.loc["gap"] = result[["fpr", "fnr"]].max() - result[["fpr", "fnr"]].min()
    return result


def cost_weighted_threshold(y_true, y_prob, fn_cost=5, fp_cost=1, thresholds=None):
    """
    Sweeps candidate decision thresholds and returns the one that minimizes
    total weighted error cost, given the relative cost of a false negative
    vs. a false positive. Use a higher fn_cost when missing a true case
    (a patient who will be readmitted, or is at risk) is more expensive
    than a false alarm.

    Returns (best_threshold, total_cost_at_that_threshold).
    """
    if thresholds is None:
        thresholds = np.linspace(0.05, 0.95, 19)

    best_threshold, best_cost = None, float("inf")
    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        cost = fn_cost * fn + fp_cost * fp
        if cost < best_cost:
            best_threshold, best_cost = t, cost
    return best_threshold, best_cost


# Usage example
# gaps = error_rate_gaps(readmission_df, "readmitted", "predicted_high_risk", "race")
# threshold, cost = cost_weighted_threshold(
#     readmission_df["readmitted"], readmission_df["risk_score"], fn_cost=5, fp_cost=1
# )
```

## Limitations

### 1. The cost ratio is a value judgment, not a technical output

Choosing `fn_cost` versus `fp_cost` requires clinical and ethical input, not something the model or a data scientist can decide alone. A cost ratio picked without that input bakes an implicit values judgment into every threshold decision downstream.

### 2. Equalizing error rates can mean different thresholds per group

If a model's risk scores are systematically shifted for one group, equalizing false positive and false negative rates may require setting a different threshold for that group. That runs directly into the difference between disparate treatment and disparate impact - see [disparate-treatment.md](disparate-treatment.md) - and raises legal questions in domains where using a protected attribute in the decision rule, even to fix an existing bias, is restricted.

### 3. Small subgroups make FPR and FNR noisy

A false negative rate computed on a subgroup of a few hundred patients has a wide confidence interval. An apparent 10-point gap in a small subgroup may not be statistically distinguishable from zero. Always report subgroup sizes alongside the rates, and treat gaps in small groups as a signal to investigate, not a confirmed finding.

### 4. Equal error rates do not guarantee equal outcomes

Even a model with perfectly equalized false positive and false negative rates only controls what the model predicts, not what happens next. If flagged patients from one group are less likely to actually receive the follow-up care the flag was supposed to trigger, the on-paper fairness of the model does not translate into equal real-world benefit.

## Related Concepts

* [Equalized Odds](equalized-odds.md) - the fairness metric that formalizes "equal false positive rate and equal false negative rate across groups" as a single testable condition.
* [Calibration](calibration.md) - why a model can assign the same risk score to equally-scored patients across groups and still be wrong in different directions for each group.
* [What Is Predictive Parity?](predictive-parity.md) - the ProPublica vs. Northpointe COMPAS dispute, a real case where equalizing one error-based metric made another one worse.
* [What is Disparate Treatment?](disparate-treatment.md) - relevant to the per-group threshold question raised in Limitation 2.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the primary audit behind the concrete example above: readmission risk prediction with race and age as protected attributes.
* [`Insurance Denial/`](../Insurance%20Denial/) - a second health-adjacent audit where the cost of a false negative (an undetected high-risk claim) and a false positive (a wrongly denied low-risk claim) are similarly asymmetric.

## Further Reading

* [Obermeyer, Z., Powers, B., Vogeli, C., Mullainathan, S. (2019): Dissecting racial bias in an algorithm used to manage the health of populations](https://www.science.org/doi/10.1126/science.aax2342) - the study behind the concrete example above; shows how a false-negative-heavy error pattern hid behind an apparently race-neutral risk score.
* [Rajkomar, A., Hardt, M., Howell, M.D., Corrado, G., Chin, M.H. (2018): Ensuring Fairness in Machine Learning to Advance Health Equity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6594166/) - lays out how model design, data, and clinician interaction each shape which patients absorb a clinical model's errors.
* [Chouldechova, A. (2017): Fair Prediction with Disparate Impact](https://arxiv.org/pdf/1703.0056) - the proof that equalized false positive and false negative rates and equal predictive value cannot all hold at once when groups have different base rates, the statistical root of the threshold trade-off described above.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*