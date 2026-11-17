> *Two groups can share one AUC and still get very different errors. Two groups can share one threshold and hide a real ranking gap.*

## The One-Sentence Definition

An **AUC gap between groups** is the difference in the area under the ROC curve, computed separately for each group: it measures how well the model ranks the people in one group compared with the other, before any cutoff is chosen.

## Why It Matters

Most fairness metrics in this repo are read at one threshold, usually 0.5. That makes them sensitive to where the cutoff happens to fall. AUC does not use a cutoff: it is the probability that a randomly chosen person with the positive label is scored above a randomly chosen person without it (see [ROC Curve and AUC](roc-curve-auc.md)). Computed per group, it separates two different questions that a single threshold mixes together:

* **Is the score equally good at ranking in both groups?** That is the AUC gap.
* **Does the chosen cutoff produce equal error rates?** That is a threshold question, covered by [Equal Opportunity](equal-opportunity.md) and [Group-Specific Thresholds](group-specific-thresholds.md).

Each can be fine while the other fails, and the examples below show both.

## Core Concept: A Gap, an Interval, and a Test

For each group, the AUC is the area under that group's own ROC curve. The gap is `AUC(disadvantaged) - AUC(advantaged)`. Because a gap is a statistic from a sample, it needs an interval. Two standard ways to get one:

* **Bootstrap:** resample each group's rows with replacement, recompute both AUCs, and take the 2.5th and 97.5th percentiles of the gap. This is the same idea the benchmark uses for its other metrics.
* **DeLong:** DeLong, DeLong and Clarke-Pearson (1988) gave a closed-form variance for an AUC from the "placement values" of each case. The two groups here are different people, so their AUCs are independent and the variances add. (DeLong's paper is mainly about comparing two curves on the *same* people; for different groups the independent form is the right one.)

The per-group AUC is also sensitive to group size. A group with only a few dozen people of each label to rank has a wide interval, and a gap can look large and still be indistinguishable from noise.

## Concrete Example: Three Audits, Three Different Stories

Logistic regression, core features only, the benchmark split, scores on the test set. "Advantaged" and "disadvantaged" follow each audit's manifest. The error rates are at the default 0.5 cutoff.

```
Tenant Screening - race  (test rows: advantaged 2224, disadvantaged 2943)
  advantaged    AUC 0.680 | FPR at 0.5 0.460 | TPR at 0.5 0.725
  disadvantaged AUC 0.672 | FPR at 0.5 0.610 | TPR at 0.5 0.809
  AUC gap -0.008 | bootstrap 95% interval [-0.037, +0.023] | DeLong z -0.53, p 0.593
Healthcare Readmission - age  (test rows: advantaged 10889, disadvantaged 9010)
  advantaged    AUC 0.600 | FPR at 0.5 0.001 | TPR at 0.5 0.003
  disadvantaged AUC 0.548 | FPR at 0.5 0.000 | TPR at 0.5 0.000
  AUC gap -0.052 | bootstrap 95% interval [-0.077, -0.026] | DeLong z -4.10, p 0.000
Insurance Denial - gender  (test rows: advantaged 133, disadvantaged 134)
  advantaged    AUC 0.638 | FPR at 0.5 0.354 | TPR at 0.5 0.559
  disadvantaged AUC 0.734 | FPR at 0.5 0.221 | TPR at 0.5 0.591
  AUC gap +0.095 | bootstrap 95% interval [-0.038, +0.221] | DeLong z +1.44, p 0.149
```

**Equal AUC, unequal errors (Tenant Screening, race).** The AUCs are 0.680 and 0.672, a gap of -0.008 with a bootstrap interval of [-0.037, +0.023]: the model ranks Black and White applicants about equally well. Yet at 0.5 it flags Black applicants who did not reoffend (false positive rate 0.610) far more often than White applicants (0.460). The unfairness here is a threshold effect, not a ranking effect, so a different cutoff or a calibration fix is the lever, not a better model.

**A real AUC gap that a threshold hides (Healthcare Readmission, age 70 and over).** The AUCs are 0.600 and 0.548, a gap of -0.052 with an interval of [-0.077, -0.026]; the DeLong test gives z = -4.10. The model ranks older patients worse. At 0.5 almost nobody is flagged in either group (true positive rate 0.003 against 0.000), so every threshold-based gap at 0.5 is near zero and looks fine. Only the threshold-free view shows the problem. Here the ranking itself is the thing to fix.

**A big gap that is mostly noise (Insurance Denial, gender).** The gap is +0.095, which looks larger than either of the above, but each group has only about 130 test rows and the interval is [-0.038, +0.221] with p = 0.149. Reporting this as "the model is better for women" would be reading noise.

## Detection/Implementation Code

Run from the repo root (`PYTHONPATH=. python3 explainers/code/auc-gaps-by-group.py`; that file is generated from the block below).

```python
import numpy as np
from math import erf, sqrt
from faircode.benchmark import load_audit
from faircode.models import build_model

def placement(score, other_sorted, above):
    """Share of the other class each score beats (ties count half), from two binary searches instead of a loop."""
    below = np.searchsorted(other_sorted, score, side="left")
    through = np.searchsorted(other_sorted, score, side="right")
    return (below + 0.5 * (through - below)) / len(other_sorted) if above else 1 - (below + 0.5 * (through - below)) / len(other_sorted)

def delong_auc_var(y, score):
    """AUC and its DeLong variance (DeLong, DeLong, Clarke-Pearson 1988) for one sample."""
    pos, neg = score[y == 1], score[y == 0]
    v10 = placement(pos, np.sort(neg), above=True)       # each positive: share of negatives it beats
    v01 = placement(neg, np.sort(pos), above=False)      # each negative: share of positives that beat it
    return v10.mean(), v10.var(ddof=1) / len(pos) + v01.var(ddof=1) / len(neg)

def fast_auc(y, level, n_levels):
    """AUC of a resample from its tie-aware score levels: two bincounts and a cumulative sum, no sorting."""
    pos = np.bincount(level[y == 1], minlength=n_levels)
    neg = np.bincount(level[y == 0], minlength=n_levels)
    if pos.sum() == 0 or neg.sum() == 0:
        raise ValueError("a bootstrap sample needs both classes")
    return float((pos * (np.cumsum(neg) - neg + 0.5 * neg)).sum() / (pos.sum() * neg.sum()))

def audit_auc(folder, attribute, n_boot=2000):
    """Per-group AUC, the gap with its two intervals, and the error rates at the default 0.5 cutoff."""
    data = load_audit(folder)
    tr, te = data.idx_train, data.idx_test
    model = build_model("logistic_regression", data.random_state).fit(data.X.iloc[tr], data.y.iloc[tr])
    p = model.predict_proba(data.X.iloc[te])[:, 1]
    y = data.y.iloc[te].to_numpy()
    s = data.group(attribute)[te]                       # 1 = disadvantaged group
    print(f"{folder} - {attribute}  (test rows: advantaged {(s == 0).sum()}, disadvantaged {(s == 1).sum()})")
    auc, var = {}, {}
    for g, name in ((0, "advantaged"), (1, "disadvantaged")):
        auc[g], var[g] = delong_auc_var(y[s == g], p[s == g])
        pred = p[s == g] >= 0.5
        yg = y[s == g]
        print(f"  {name:13s} AUC {auc[g]:.3f} | FPR at 0.5 {pred[yg == 0].mean():.3f} | TPR at 0.5 {pred[yg == 1].mean():.3f}")
    gap = auc[1] - auc[0]
    z = gap / sqrt(var[0] + var[1])
    p_value = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    rng = np.random.default_rng(data.random_state)
    idx = {g: np.flatnonzero(s == g) for g in (0, 1)}
    levels = {g: np.unique(p[idx[g]], return_inverse=True)[1] for g in (0, 1)}    # tie-aware rank of each row's score
    boots = []
    for _ in range(n_boot):
        a = []
        for g in (0, 1):
            pick = rng.choice(len(idx[g]), size=len(idx[g]), replace=True)       # the same draws as picking rows of idx[g]
            a.append(fast_auc(y[idx[g]][pick], levels[g][pick], levels[g].max() + 1))
        boots.append(a[1] - a[0])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"  AUC gap {gap:+.3f} | bootstrap 95% interval [{lo:+.3f}, {hi:+.3f}] | DeLong z {z:+.2f}, p {p_value:.3f}")

audit_auc("Tenant Screening", "race")
audit_auc("Healthcare Readmission", "age")
audit_auc("Insurance Denial", "gender")
```

## Limitations

1. **AUC averages over every threshold, including ones nobody would use.** A group can have a worse AUC only in a region of the curve that the deployed cutoff never visits. Look at the curves, or at a partial AUC, before acting on the single number.
2. **A single AUC gap does not say where on the curve it comes from.** Equal AUCs can come from curves that cross, and then one group is better served at low cutoffs and the other at high ones. See [Decision Curve Analysis by Group](decision-curve-analysis-by-group.md).
3. **Intervals for small groups are wide.** The Insurance Denial example has a larger point gap than the Healthcare one and much less evidence. Always report the interval, and for groups under a few hundred rows treat any gap as a question, not a finding.
4. **The two intervals can disagree.** The bootstrap and DeLong intervals agree closely on the large groups here, but they are different approximations; for very small groups or AUCs near 1 neither is reliable.
5. **Equal AUC does not mean equal treatment.** It says nothing about calibration, error balance or the decisions actually made. Use it next to, not instead of, [Disaggregated Evaluation](disaggregated-evaluation.md).

## Related Concepts

* [ROC Curve and AUC](roc-curve-auc.md) - the curve and area this explainer computes per group
* [Precision-Recall Curve](precision-recall-curve.md) - the better view when the positive class is rare, as in Healthcare Readmission
* [Disaggregated Evaluation](disaggregated-evaluation.md) - computing any metric per group
* [Group-Specific Thresholds](group-specific-thresholds.md) - the lever for the Tenant Screening case
* [Decision Curve Analysis by Group](decision-curve-analysis-by-group.md) - net benefit at each threshold, per group

## Related Projects in This Repo

* [`Tenant Screening/`](../Tenant%20Screening/), [`Healthcare Readmission/`](../Healthcare%20Readmission/), [`Insurance Denial/`](../Insurance%20Denial/) - the three audits used above

## Further Reading

* [DeLong, E. R., DeLong, D. M., Clarke-Pearson, D. L. (1988): Comparing the Areas under Two or More Correlated Receiver Operating Characteristic Curves](https://pubmed.ncbi.nlm.nih.gov/3203132/) - Biometrics 44(3); the variance estimate and test used above.
* [Hanley, J. A., McNeil, B. J. (1982): The Meaning and Use of the Area under a Receiver Operating Characteristic (ROC) Curve](https://pubs.rsna.org/doi/10.1148/radiology.143.1.7063747) - Radiology 143(1); why AUC is a probability of correct ranking.
* [Fawcett, T. (2006): An Introduction to ROC Analysis](https://doi.org/10.1016/j.patrec.2005.10.010) - Pattern Recognition Letters 27(8); how to read and compare ROC curves.

---
*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
