# What Is Reject Option Classification?

> *When a model is least sure of itself, it has the least evidence to defend its choice. Reject Option Classification takes exactly those borderline cases and hands the favorable outcome to the group history treated worst, on the bet that correcting for bias costs the least where the model was already guessing.*

## The One-Sentence Definition

**Reject Option Classification** (ROC; Kamiran, Karim and Zhang, 2012) is a post-processing bias mitigation that defines a "critical region" of low-confidence predictions near the decision boundary and, only inside that region, assigns the favorable label to instances from the disadvantaged group and the unfavorable label to instances from the advantaged group.

> **Not the same as [Reject Inference](reject-inference.md).** That explainer's "reject" is about *rejected loan applicants* who never entered the training data - a selection-bias problem in credit scoring. This explainer's "reject" is the classifier's *reject option*: the band of inputs a probabilistic model is too uncertain about to commit to. Same word, unrelated ideas. (The same name-collision warning [Counterfactual Explanation](counterfactual-explanation.md) carries for its overlap with counterfactual fairness.)

## Why It Matters

This repo's benchmark harness already includes a post-processing mitigation as strategy **S4** - Fairlearn's `ThresholdOptimizer`, which searches for a *per-group decision threshold* that makes the whole model satisfy a fairness constraint. ROC is a different post-processing mechanism with the same access level (model outputs only, no retraining):

| | `ThresholdOptimizer` (this repo's S4) | Reject Option Classification |
|---|---|---|
| What it changes | one decision threshold per group, applied to every prediction | the label of individual predictions, only inside a confidence band |
| Where it acts | globally, across the whole score range | locally, near `p = 0.5` |
| Free parameter | the fairness constraint to satisfy | the width of the critical region |
| Rationale | pick thresholds that equalize a chosen rate | flip where the model had the least evidence, so accuracy loss is smallest |

ROC's appeal is the "least evidence" argument: a prediction with `p = 0.52` is barely a prediction at all, so overriding it toward the disadvantaged group is a small, defensible correction. Its weakness is that "how wide is the band" has no principled answer - and, as the worked example shows, the answer completely determines whether you fix the gap, do nothing, or overcorrect into a mirror-image disparity.

## How It Works

Let `p_i = P(Y = 1 | X_i)` be the model's predicted probability of the *unfavorable* outcome (here: "high risk"), and let `Y = 1` be unfavorable, `Y = 0` favorable.

1. **Baseline prediction:** `y_hat_i = 1 if p_i >= 0.5 else 0`.
2. **Critical region:** pick a half-width `theta` in `(0, 0.5]` and define the region as `0.5 - theta <= p_i <= 0.5 + theta`. Outside it, keep the baseline prediction.
3. **Flip rule inside the region:**
   - disadvantaged group -> favorable outcome (`y_hat_i = 0`)
   - advantaged group -> unfavorable outcome (`y_hat_i = 1`)

The flip toward the advantaged group is what keeps ROC from simply lowering everyone's positive rate: it trades favorable outcomes from the advantaged group for favorable outcomes to the disadvantaged group, inside the band, rather than just relabelling one side.

`theta` is the entire design. `theta -> 0` recovers the untouched model. `theta = 0.5` puts every prediction in the region, so the output becomes "disadvantaged group all-favorable, advantaged group all-unfavorable" regardless of the features.

## Concrete Example: COMPAS - Audit 01

`COMPAS/` audits the ProPublica COMPAS raw file, filtered (per `audit.yaml`) to African-American and Caucasian defendants scored for "Risk of Recidivism" (~16.3k rows). Following the audit's setup, a logistic-regression baseline was trained on `Sex_Code_Text`, `race`, `CustodyStatus`, `MaritalStatus` (an 80/20 split, `random_state=42`), and ROC was applied to its test-set probabilities. Favorable outcome = "not high risk"; disadvantaged group = African-American defendants.

**Baseline model (no ROC):**

| | Value |
|---|---:|
| Black defendants flagged high-risk | 86.1% |
| White defendants flagged high-risk | 0.1% |
| Demographic parity gap | **+86.0 pp** |
| Test accuracy | 65.9% |

The baseline is close to a step function - `race` dominates the model, so almost every predicted probability sits near 0 or near 1 and very few land near the boundary. That is the setting ROC handles worst, and it shows:

| Critical region `theta` | Predictions in region (of 3,254) | Predictions flipped | New parity gap | Test accuracy |
|---|---:|---:|---:|---:|
| baseline | - | - | +86.0 pp | 65.9% |
| ±0.05 | 17 | 17 | **+85.0 pp** | 65.9% |
| ±0.10 | 671 | 651 | **+43.9 pp** | 61.0% |
| ±0.15 | 2,609 | 2,566 | **-70.2 pp** | 45.5% |

- **±0.05** touches 17 of 3,254 test rows. The gap barely moves and accuracy is unchanged, because the model is almost never uncertain - it committed hard, using race.
- **±0.10** flips 651 predictions and roughly halves the gap (+86 -> +44 pp), at a ~5-point accuracy cost. This is the band where ROC does what it is supposed to.
- **±0.15** pulls in 80% of the test set. The "flip rule" now overrides the model on the large majority of cases, the gap **reverses** to -70 pp (Black defendants now flagged *less*), and accuracy collapses to 45.5% - worse than predicting the majority class.

No value of `theta` was "correct"; the three rows above are three different fairness outcomes produced by three arbitrary choices of one number. That is the central caveat, made concrete.

```python
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

df = pd.read_csv("COMPAS/compas-scores-raw.csv")
df = df[df["Ethnic_Code_Text"].isin(["African-American", "Caucasian"])]
df = df[df["DisplayText"] == "Risk of Recidivism"].copy()
df["high_risk"] = df["ScoreText"].isin(["High", "Medium"]).astype(int)
df["is_black"] = (df["Ethnic_Code_Text"] == "African-American").astype(int)

X = pd.get_dummies(df[["Sex_Code_Text", "is_black", "CustodyStatus",
                       "MaritalStatus"]]).astype(float)
y, g = df["high_risk"].to_numpy(), df["is_black"].to_numpy()
X_tr, X_te, y_tr, y_te, g_tr, g_te = train_test_split(
    X, y, g, test_size=0.2, random_state=42, stratify=y)

scaler = StandardScaler().fit(X_tr)
model = LogisticRegression(max_iter=1000).fit(scaler.transform(X_tr), y_tr)
p = model.predict_proba(scaler.transform(X_te))[:, 1]
baseline = (p >= 0.5).astype(int)

for theta in (0.05, 0.10, 0.15):
    region = np.abs(p - 0.5) <= theta
    roc = baseline.copy()
    roc[region & (g_te == 1)] = 0   # disadvantaged -> favorable (not high risk)
    roc[region & (g_te == 0)] = 1   # advantaged   -> unfavorable
    gap = roc[g_te == 1].mean() - roc[g_te == 0].mean()
    print(f"theta=+/-{theta}: {region.sum():4d} in region, "
          f"{(roc != baseline).sum():4d} flipped, gap {gap:+.3f}, "
          f"acc {(roc == y_te).mean():.3f}")
```

## Detection / Implementation Code

A reusable ROC post-processor plus a helper that sweeps `theta` so the parameter's effect is visible rather than hidden.

```python
import numpy as np
import pandas as pd


def reject_option_classify(
    proba_unfavorable: np.ndarray,
    group: np.ndarray,
    disadvantaged_value,
    theta: float,
    boundary: float = 0.5,
) -> np.ndarray:
    """
    Apply Reject Option Classification to a probabilistic model's output.

    proba_unfavorable : P(Y = 1) where Y = 1 is the UNfavorable outcome.
    group             : group membership, aligned to proba_unfavorable.
    disadvantaged_value : the value in `group` that marks the disadvantaged
                          group (gets the favorable outcome inside the band).
    theta             : half-width of the critical region, in (0, boundary].
    boundary          : decision threshold (default 0.5).

    Returns the post-processed 0/1 predictions (1 = unfavorable).
    """
    if not 0 < theta <= boundary:
        raise ValueError(f"theta must be in (0, {boundary}], got {theta}")

    proba = np.asarray(proba_unfavorable, dtype=float)
    grp = np.asarray(group)
    pred = (proba >= boundary).astype(int)

    in_region = np.abs(proba - boundary) <= theta
    is_disadvantaged = grp == disadvantaged_value

    pred[in_region & is_disadvantaged] = 0    # favorable
    pred[in_region & ~is_disadvantaged] = 1   # unfavorable
    return pred


def sweep_theta(
    proba_unfavorable: np.ndarray,
    group: np.ndarray,
    y_true: np.ndarray,
    disadvantaged_value,
    advantaged_value,
    thetas=(0.02, 0.05, 0.10, 0.15, 0.20, 0.30),
    boundary: float = 0.5,
) -> pd.DataFrame:
    """Run ROC across a range of theta and report, for each: how many
    predictions fell in the critical region, how many actually flipped, the
    resulting demographic-parity gap (disadvantaged - advantaged positive
    rate on the UNfavorable label), and overall accuracy. There is no
    'best' row - the point is that the choice is unconstrained."""
    proba = np.asarray(proba_unfavorable, dtype=float)
    grp = np.asarray(group)
    y = np.asarray(y_true, dtype=int)
    baseline = (proba >= boundary).astype(int)

    def gap(pred):
        return (pred[grp == disadvantaged_value].mean()
                - pred[grp == advantaged_value].mean())

    rows = [{
        "theta": 0.0, "in_region": 0, "flipped": 0,
        "parity_gap": gap(baseline), "accuracy": (baseline == y).mean(),
    }]
    for theta in thetas:
        pred = reject_option_classify(proba, grp, disadvantaged_value,
                                      theta, boundary)
        in_region = int((np.abs(proba - boundary) <= theta).sum())
        rows.append({
            "theta": theta,
            "in_region": in_region,
            "flipped": int((pred != baseline).sum()),
            "parity_gap": gap(pred),
            "accuracy": (pred == y).mean(),
        })
    return pd.DataFrame(rows)


# Usage (see the COMPAS example above for how p, g_te, y_te are produced):
# print(sweep_theta(p, g_te, y_te, disadvantaged_value=1, advantaged_value=0))
```

## Limitations and Trade-offs

### 1. The critical-region width has no principled default

Every number in the worked example - "gap halved", "gap reversed", "accuracy destroyed" - is a consequence of picking `theta`. The original paper frames the choice through decision theory (a loss ratio between the two error types), which relocates the arbitrariness into choosing that ratio rather than removing it. In practice `theta` is tuned on a validation set against whatever fairness/accuracy trade-off the deployer already had in mind, which means ROC does not decide the trade-off, it just implements a chosen one.

### 2. It needs group membership at prediction time

Like every post-processing method (including this repo's `ThresholdOptimizer`), the flip rule reads the protected attribute for each individual at inference. In hiring, lending, and housing that is often the exact input a deployer is legally barred from using in the decision, or does not reliably have. A model that must not see race cannot run ROC on race.

### 3. It can invert the disparity instead of removing it

Because the flip rule is unconditional inside the band, a wide `theta` on a confident model (the COMPAS case) does not shrink the gap toward zero - it drags it past zero. ROC has no "stop at parity" mechanism; monitoring the post-processed gap and backing `theta` off is a manual outer loop.

### 4. It optimizes a rate, not the individuals

Two defendants with `p = 0.49` and `p = 0.51` get opposite treatment based on group, not on any difference between them - the same [individual-fairness](individual-fairness.md) objection that applies to per-group thresholds. ROC trades group-rate fairness for individual-level consistency in the band.

## Related Concepts

* [What Are Pre-, In-, and Post-Processing Fairness Mitigations?](mitigation-strategies.md) - where ROC sits among mitigation families, and this repo's own S4 `ThresholdOptimizer` post-processing strategy.
* [What Is Equalized Odds?](equalized-odds.md) and [What Is Equal Opportunity?](equal-opportunity.md) - the error-rate metrics a per-group threshold or a flip band is usually tuned against.
* [What Is Treatment Equality?](treatment-equality.md) - another lens on how a post-processing flip changes the *mix* of errors within each group.
* [What Is Reject Inference?](reject-inference.md) - the unrelated "reject" (missing rejected applicants in training data), kept adjacent here only to mark the name collision.
* [What Is Individual Fairness?](individual-fairness.md) - why treating near-boundary individuals differently by group is contested.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the audit used above; its baseline is confident enough that ROC either does almost nothing (`theta = 0.05`) or overcorrects (`theta >= 0.15`).
* [`German Credit Lending/`](../German%20Credit%20Lending/) - a smaller-gap audit where a model with more mass near the boundary would give ROC a wider useful `theta` range.

## Further Reading

* [Kamiran, F., Karim, A., Zhang, X. (2012): Decision Theory for Discrimination-Aware Classification, *IEEE ICDM 2012*, pp. 924-929](https://doi.org/10.1109/ICDM.2012.45) - the paper that introduces Reject Option based Classification and the disagreement-region variant, and ties both to decision theory. [Author PDF.](https://web.lums.edu.pk/~akarim/pub/decision_theory_icdm2012.pdf)
* [Kamiran, F., Mansha, S., Karim, A., Zhang, X. (2018): Exploiting Reject Option in Classification for Social Discrimination Control, *Information Sciences* 425](https://doi.org/10.1016/j.ins.2017.09.064) - a fuller treatment with more datasets and the multi-attribute case.
* [Hardt, M., Price, E., Srebro, N. (2016): Equality of Opportunity in Supervised Learning, *NeurIPS 2016*](https://arxiv.org/abs/1610.02413) - the per-group-threshold post-processing method this repo's `ThresholdOptimizer` implements, for contrast.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
