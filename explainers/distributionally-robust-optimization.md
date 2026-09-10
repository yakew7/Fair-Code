# What Is Distributionally Robust Optimization (DRO) for Fairness?

> *A constraint-based fix needs you to name the fairness metric and the group up front. DRO instead trains against the worst subgroup your data might be under-representing - whichever one that turns out to be.*

---

## The One-Sentence Definition

**Distributionally Robust Optimization (DRO)** is an in-processing fairness technique that trains a model to minimize its *worst-case* loss over a set of plausible reweightings of the training distribution, rather than minimizing average loss or constraining a specific parity metric.

---

## Why It Matters

This repo's S3 in-processing strategy ([mitigation-strategies.md](mitigation-strategies.md)) is Fairlearn's `ExponentiatedGradient`: optimize accuracy subject to a fairness constraint, such as demographic parity, on a named protected attribute. That works well when you already know which metric matters and which group is at risk. It has two requirements baked in:

- **You choose the fairness metric before training.** The constraint is demographic parity, or equalized odds, or one specific thing. A gap on a metric you did not constrain is not touched.
- **You choose the group before training.** The constraint is defined on `race`, or `age`, or a fixed intersection. A subgroup you did not think to check is invisible to it.

DRO relaxes both. Instead of a constraint on one metric for one group, it hedges against the worst subgroup the training data might be under-representing - without committing to a parity metric at all, and (in the Hashimoto et al. 2018 form) without needing group labels. If the group actually being harmed is not the one you would have constrained, DRO can still help; `ExponentiatedGradient` cannot.

The cost is a free parameter and no guarantee, both covered below.

---

## Core Concept: The Min-Max Objective

`ExponentiatedGradient` solves a **constrained** problem:

```
minimise  average loss L(theta)
subject to  |demographic_parity_gap(theta)|  <=  epsilon
```

Group DRO solves a **min-max** problem instead:

```
minimise over theta of   max over Q in U of   E_Q[ loss(theta) ]
```

where `U` is an *uncertainty set*: a ball of distributions around the empirical training distribution. `E_Q[loss]` is the expected loss if the data were reweighted to `Q`. The model is trained so that even the least favourable reweighting in `U` still has low loss.

When `U` is "all reweightings that shift mass between predefined groups", this is **group DRO** (Sagawa et al. 2020), and it has a simple online algorithm:

1. Keep a probability vector `q` over groups.
2. Each step, raise `q` for whichever group currently has the highest loss.
3. Fit the model on `q`-reweighted examples.
4. Repeat until `q` stabilizes.

The size of `U` - how far `q` is allowed to move from the group base rates - is the **robustness knob**. Bigger `U` means the model hedges against more extreme reweightings.

This is the same reweighting loop as iterative [max-min (Rawlsian) fairness](maxmin-fairness.md); the difference is framing. Max-min asks "make the worst group's *outcome* as good as possible." DRO asks "stay robust to a *distribution shift* that inflates the worst group" - and the uncertainty set `U` is the explicit statement of which shifts you are hedging against.

---

## Concrete Example: German Credit Lending - Audit 03

Audit 03 ([`German Credit Lending/`](../German%20Credit%20Lending/)) predicts bad credit risk on 1,000 real loan records; the protected attribute is `age`, with "young" meaning under 30.

For reference, this repo's frozen benchmark ([`paper/results-frozen/results_fairness.csv`](../paper/results-frozen/), the earlier snapshot - see [CLAUDE.md](../CLAUDE.md)) records the S3 `in_processing` strategy driving the baseline logistic-regression `demographic_parity_diff` on `age` from **-0.129 (p = 0.05) at S0 to +0.023 (p = 0.71) at S3** - the constraint closes the parity gap it was given. Group DRO does not target that metric at all; it targets worst-group loss.

The script below runs an ERM (average-loss) baseline, then online group DRO, sweeping the robustness knob. Features drop `age` and `personal_status`; inputs are standardized; the split is 80/20 stratified at `random_state=42`.

```python
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import train_test_split


def load_german_credit(path="German Credit Lending/credit_customers.csv"):
    df = pd.read_csv(path)
    df["y_bad"] = (df["class"] == "bad").astype(int)
    df["age_group"] = np.where(df["age"] < 30, "young", "older")
    drop = {"class", "y_bad", "age", "age_group", "personal_status"}
    feats = [c for c in df.columns if c not in drop]
    return pd.get_dummies(df[feats], drop_first=True), df["y_bad"].to_numpy(), df["age_group"].to_numpy()


def per_group(model, X, y, groups):
    pred, proba = model.predict(X), model.predict_proba(X)[:, 1]
    rows = {}
    for g in ["older", "young"]:
        m = groups == g
        rows[g] = {"n": int(m.sum()),
                   "accuracy": round(float((pred[m] == y[m]).mean()), 4),
                   "log_loss": round(float(log_loss(y[m], proba[m], labels=[0, 1])), 4)}
    worst = max(rows["older"]["log_loss"], rows["young"]["log_loss"])
    return pd.DataFrame(rows).T, round(float(worst), 4), round(float((pred == y).mean()), 4)


def fit_group_dro(Xtr, ytr, gtr, robustness=1.0, n_rounds=100):
    """Online group DRO (Sagawa et al. 2020): keep a distribution q over groups,
    each round upweight whichever group has the highest loss, and fit the model
    on q-reweighted examples. `robustness` is the uncertainty-set knob - larger
    means q chases the worst group harder."""
    q = {"older": 0.5, "young": 0.5}
    frac = {g: (gtr == g).mean() for g in q}
    for _ in range(n_rounds):
        w = np.array([q[g] / frac[g] for g in gtr], dtype=float)
        w *= len(w) / w.sum()
        model = LogisticRegression(max_iter=5000).fit(Xtr, ytr, sample_weight=w)
        proba = model.predict_proba(Xtr)[:, 1]
        gl = {g: log_loss(ytr[gtr == g], proba[gtr == g], labels=[0, 1]) for g in q}
        for g in q:
            q[g] *= np.exp(robustness * gl[g])
        total = sum(q.values())
        q = {g: v / total for g, v in q.items()}
    return model, q


if __name__ == "__main__":
    X, y, g = load_german_credit()
    Xtr, Xte, ytr, yte, gtr, gte = train_test_split(
        X, y, g, test_size=0.2, random_state=42, stratify=y)
    mean, std = Xtr.mean(), Xtr.std().replace(0, 1)
    Xtr_s, Xte_s = ((Xtr - mean) / std).to_numpy(), ((Xte - mean) / std).to_numpy()

    erm = LogisticRegression(max_iter=5000).fit(Xtr_s, ytr)
    tbl, worst, acc = per_group(erm, Xte_s, yte, gte)
    print("=== ERM baseline (minimise average loss) ===")
    print(tbl.to_string())
    print(f"overall accuracy   : {acc:.4f}")
    print(f"worst-group log_loss: {worst:.4f}\n")

    print("=== Group DRO: sweep the robustness knob ===")
    print(f"{'robustness':>10} | {'q(young)':>8} | {'worst-group log_loss':>20} | {'overall acc':>11}")
    for r in [0.0, 0.5, 1.0, 2.0, 5.0]:
        model, q = fit_group_dro(Xtr_s, ytr, gtr, robustness=r)
        _, w, a = per_group(model, Xte_s, yte, gte)
        print(f"{r:>10.1f} | {q['young']:>8.2f} | {w:>20.4f} | {a:>11.4f}")
```

### Script Execution Output

```
=== ERM baseline (minimise average loss) ===
           n  accuracy  log_loss
older  121.0    0.8099    0.4285
young   79.0    0.7089    0.5880
overall accuracy   : 0.7700
worst-group log_loss: 0.5880

=== Group DRO: sweep the robustness knob ===
robustness | q(young) | worst-group log_loss | overall acc
       0.0 |     0.50 |               0.5910 |      0.7700
       0.5 |     0.62 |               0.5988 |      0.7750
       1.0 |     0.63 |               0.5991 |      0.7700
       2.0 |     0.63 |               0.5991 |      0.7700
       5.0 |     0.63 |               0.5991 |      0.7700
```

(Deterministic with these library versions; a solver's last digits can shift across BLAS backends.)

Three things this shows:

**DRO reliably redirects training weight to the worst group.** ERM weights groups by their size. As the robustness knob goes up, `q(young)` climbs from 0.50 to about 0.63 and then saturates - the min-max objective has found the worst group and is pushing on it. That part works exactly as designed.

**On this problem, redirecting the weight buys no worst-group generalization.** The young group's held-out `log_loss` is 0.588 under ERM and does not improve under any robustness setting - it drifts slightly *up*, to ~0.599. Overall accuracy stays flat at 0.77. A linear model on 800 training rows is capacity-limited, not distribution-limited: the young group is genuinely harder to predict here, and reweighting the objective toward it cannot manufacture signal that is not in the features.

**This is the paper's own headline finding, not a bug in the loop.** Sagawa et al. (2020) title their paper *"On the Importance of Regularization for Worst-Case Generalization"* precisely because plain group DRO increases worst-group training influence without improving worst-group test loss unless the model is strongly regularized (and, in their setting, overparameterized). The robustness knob is a real dial with a real cost - turn it up and `q` over-hedges toward an implausible worst case, shaving average-case accuracy - but it is not a guarantee of a fairer model.

---

## Detection and Implementation Code

`fit_group_dro` above is the implementation. The helper below reports whether a DRO run actually moved worst-group loss and what it cost average accuracy - the trade you are actually making.

```python
def dro_report(erm_model, dro_model, X, y, groups):
    """Compare an ERM model against a group-DRO model on held-out data."""
    def summarise(model):
        pred, proba = model.predict(X), model.predict_proba(X)[:, 1]
        per = {}
        for g in sorted(set(groups)):
            m = groups == g
            from sklearn.metrics import log_loss
            per[g] = {"acc": round(float((pred[m] == y[m]).mean()), 4),
                      "log_loss": round(float(log_loss(y[m], proba[m], labels=[0, 1])), 4)}
        return per, round(float((pred == y).mean()), 4)

    erm_per, erm_acc = summarise(erm_model)
    dro_per, dro_acc = summarise(dro_model)
    erm_worst = max(v["log_loss"] for v in erm_per.values())
    dro_worst = max(v["log_loss"] for v in dro_per.values())
    return {
        "erm_per_group": erm_per,
        "dro_per_group": dro_per,
        "worst_group_log_loss_before": erm_worst,
        "worst_group_log_loss_after": dro_worst,
        "worst_group_improved": dro_worst < erm_worst,
        "overall_accuracy_delta": round(dro_acc - erm_acc, 4),
    }
```

---

## Limitations

### 1. The uncertainty-set size is a free parameter with no data-driven default

`robustness` (equivalently, the radius of `U`) has to be picked. Too small and DRO collapses to ERM. Too large and the model hedges against reweightings that will never occur, trading real average-case accuracy for robustness to a fantasy worst case. There is no held-out quantity that tells you the "right" size - it encodes how much distribution shift you believe is plausible, which is a judgment call.

### 2. It still needs group labels at training time

The group-DRO form used here requires knowing each training example's group to maintain `q`. It removes the need to pick a *parity metric* up front, and it does not need group labels at prediction time, but it is not label-free. (Hashimoto et al. 2018's version drops the training-time group labels too, at the cost of hedging against *all* low-probability subpopulations, not just the ones you care about.)

### 3. Worst-case training loss is not worst-case test loss

As the example shows, pushing `q` toward the worst training group does not by itself improve that group's generalization. Without strong regularization or capacity control, group DRO can overfit the worst group's training set - the central caveat in Sagawa et al. (2020).

### 4. "Worst group" is only defined once you fix the loss and the grouping

DRO over groups defined by `age` says nothing about groups defined by `job` or by an `age x foreign_worker` intersection. And the worst group under log-loss, under 0-1 error, and under false-negative rate can differ. The uncertainty set is only as good as the grouping and loss you put into it.

---

## Related Concepts

- [Mitigation Strategies](mitigation-strategies.md) - this repo's S3 `ExponentiatedGradient` in-processing strategy, the constraint-based method DRO is contrasted against.
- [What Is Max-Min (Rawlsian) Fairness?](maxmin-fairness.md) - the same reweighting loop, framed as an objective on group outcomes rather than robustness to distribution shift.
- [What Is Distribution Shift?](distribution-shift.md) - the deployment-time phenomenon whose worst case DRO's uncertainty set is meant to bound.
- [What Is the Fairness-Accuracy Trade-off?](fairness-accuracy-tradeoff.md) - the average-case accuracy DRO spends when the robustness knob is turned up.
- [What Is Class Imbalance?](class-imbalance.md) - why average-loss training underserves the smaller, harder group DRO reweights toward.

---

## Related Projects in This Repo

- [`German Credit Lending/`](../German%20Credit%20Lending/) - Audit 03, the dataset and `age` attribute used above.
- [`faircode/strategies.py`](../faircode/strategies.py) - the S0-S4 implementation, including the S3 `ExponentiatedGradient` strategy DRO is compared with.
- [`paper/results-frozen/results_fairness.csv`](../paper/results-frozen/) - the frozen S0/S3 `demographic_parity_diff` figures cited above.

---

## Further Reading

- [Sagawa, Koh, Hashimoto & Liang (2020): Distributionally Robust Neural Networks for Group Shifts: On the Importance of Regularization for Worst-Case Generalization, ICLR 2020](https://arxiv.org/abs/1911.08731) - the group-DRO algorithm used here, and the finding that worst-case generalization needs strong regularization.
- [Hashimoto, Srivastava, Namkoong & Liang (2018): Fairness Without Demographics in Repeated Loss Minimization, ICML 2018, PMLR 80:1929-1938](https://proceedings.mlr.press/v80/hashimoto18a.html) - a DRO objective that bounds the minority group's risk without any group labels.
- [Duchi & Namkoong (2021): Learning Models with Uniform Performance via Distributionally Robust Optimization, Annals of Statistics 49(3), 1378-1406](https://doi.org/10.1214/20-AOS2004) - the statistical foundations of the uncertainty-set formulation.
- [Agarwal, Beygelzimer, Dudik, Langford & Wallach (2018): A Reductions Approach to Fair Classification, ICML 2018](https://proceedings.mlr.press/v80/agarwal18a.html) - the `ExponentiatedGradient` constraint-based method this repo uses at S3, for contrast.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
