# What Is Max-Min (Rawlsian) Fairness?

> *Parity asks whether the groups are equal to each other. Max-min asks how good we can make the worst-off group's outcome - even if the groups end up unequal.*

---

## The One-Sentence Definition

**Max-min fairness** (also called Rawlsian fairness, after the "difference principle" in John Rawls' *A Theory of Justice*) is a fairness objective that minimizes the maximum group-level loss - it makes the worst-off group's outcome as good as possible - instead of equalizing a rate across groups the way parity metrics do.

---

## Why It Matters

Every parity-based metric this repo already covers - [demographic parity](demographic-parity.md), [equalized odds](equalized-odds.md), [predictive parity](predictive-parity.md) - measures a *difference between groups* and drives it toward zero. That framing has a well-known escape hatch: you can satisfy a parity constraint by making the better-off group worse rather than making the worse-off group better. "Parity in mediocrity" passes the test.

Max-min fairness rejects that move by construction. It does not look at the gap between groups at all. It looks at the single worst group-level outcome and tries to lift it. Concretely:

- A model can satisfy demographic parity while both groups have poor accuracy. Max-min would prefer a model where the worst group's accuracy is higher, even if that widens the between-group gap.
- Conversely, optimizing only for the worst-off group can *widen* a parity gap: if you pour modeling capacity into the group with the higher error rate, its predictions improve, but its selection rate can move away from the other group's.

So max-min and parity are genuinely different objectives, not two names for the same goal - and a model tuned for one can fail the other. This repo's [Fairness Metric Conflicts](fairness-metric-conflicts.md) explainer covers conflicts *among* parity metrics; the conflict between parity and max-min is a separate axis it does not touch.

---

## Core Concept: A Different Objective Function

Write `L_g(theta)` for the expected loss (say, error rate) of model `theta` on group `g`.

**Demographic parity** constrains a rate to be equal across groups:

```
minimise  L(theta)          [average loss]
subject to  P(Y_hat = 1 | A = a)  equal for all a
```

**Max-min (Rawlsian) fairness** changes the thing being minimized:

```
minimise over theta of   max over groups g of   L_g(theta)
```

There is no equality constraint. The objective is a `min` of a `max`: push down the largest per-group loss, then whatever the next-largest one is, and so on. If lifting the worst group also happens to help the others, fine; if it leaves a between-group gap, that gap is not penalized.

Two standard ways to approximate it without a bespoke solver:

1. **Iterative group reweighting.** Train, measure each group's loss, upweight whichever group is currently worst, retrain. Repeat. The training objective drifts from "average loss" toward "worst-group loss." This is the approach in the code below, and the online form of it is what [group distributionally robust optimization](distributionally-robust-optimization.md) does.
2. **Distributionally robust optimization (DRO).** Minimize the worst-case loss over a set of reweightings of the data. Hashimoto et al. (2018) show a DRO objective controls the minority group's risk *without needing group labels*, which is why max-min and DRO are usually discussed together.

---

## Concrete Example: German Credit Lending - Audit 03

Audit 03 in this repo ([`German Credit Lending/`](../German%20Credit%20Lending/)) predicts bad credit risk on 1,000 real loan records. The protected attribute is `age`; here "young" means under 30 (the same cut `unfair.py` uses).

This repo's own frozen benchmark already records the gap max-min targets. In `paper/results-frozen/results_fairness.csv` (the earlier reference snapshot; see [CLAUDE.md](../CLAUDE.md)), the S0 baseline logistic-regression model on `age` has an **`accuracy_equality_diff` of -0.153** (p = 0.031) - a statistically significant 15-point per-group accuracy gap. None of this repo's S1-S4 mitigation strategies ([mitigation-strategies.md](mitigation-strategies.md)) target that number; they all target demographic parity. Max-min fairness is the objective that goes after `accuracy_equality_diff` directly.

The script below is an independent minimal implementation on the same dataset (not the S0-S4 harness): a plain logistic-regression baseline, then a max-min reweighting loop. Features drop `age` and `personal_status` (its proxy); inputs are standardized; the split is 80/20 stratified at `random_state=42`.

```python
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split


def load_german_credit(path="German Credit Lending/credit_customers.csv"):
    df = pd.read_csv(path)
    df["y_bad"] = (df["class"] == "bad").astype(int)            # 1 = bad credit risk
    df["age_group"] = np.where(df["age"] < 30, "young", "older")
    drop = {"class", "y_bad", "age", "age_group", "personal_status"}  # drop age + its proxy
    feats = [c for c in df.columns if c not in drop]
    X = pd.get_dummies(df[feats], drop_first=True)
    return X, df["y_bad"].to_numpy(), df["age_group"].to_numpy()


def per_group(y_true, y_pred, groups):
    out = {}
    for g in ["older", "young"]:
        m = groups == g
        acc = (y_pred[m] == y_true[m]).mean()
        out[g] = {"n": int(m.sum()), "accuracy": round(float(acc), 4),
                  "error": round(float(1 - acc), 4),
                  "selection_rate": round(float(y_pred[m].mean()), 4)}
    worst = max(out["older"]["error"], out["young"]["error"])
    dp_gap = out["young"]["selection_rate"] - out["older"]["selection_rate"]
    return pd.DataFrame(out).T, round(float(worst), 4), round(float(dp_gap), 4)


def fit_maxmin(Xtr, ytr, gtr, n_rounds=50, step=0.5):
    """Rawlsian max-min: iteratively reweight groups toward the worst per-group
    training error, so the optimizer minimizes the maximum group loss rather
    than the average loss."""
    gw = {"older": 1.0, "young": 1.0}
    for _ in range(n_rounds):
        w = np.array([gw[g] for g in gtr], dtype=float)
        w *= len(w) / w.sum()
        model = LogisticRegression(max_iter=5000).fit(Xtr, ytr, sample_weight=w)
        err = {g: 1 - (model.predict(Xtr)[gtr == g] == ytr[gtr == g]).mean()
               for g in gw}
        for g in gw:                       # multiplicative-weights update
            gw[g] *= np.exp(step * err[g])
        total = sum(gw.values())
        gw = {g: v / total * len(gw) for g, v in gw.items()}
    return model, gw


if __name__ == "__main__":
    X, y, g = load_german_credit()
    Xtr, Xte, ytr, yte, gtr, gte = train_test_split(
        X, y, g, test_size=0.2, random_state=42, stratify=y)
    mean, std = Xtr.mean(), Xtr.std().replace(0, 1)
    Xtr_s, Xte_s = ((Xtr - mean) / std).to_numpy(), ((Xte - mean) / std).to_numpy()

    base = LogisticRegression(max_iter=5000).fit(Xtr_s, ytr)
    b_tbl, b_worst, b_dp = per_group(yte, base.predict(Xte_s), gte)
    print("=== BASELINE (minimise average loss) ===")
    print(b_tbl.to_string())
    print(f"overall accuracy      : {(base.predict(Xte_s) == yte).mean():.4f}")
    print(f"worst-group error     : {b_worst:.4f}")
    print(f"demographic-parity gap: {b_dp:.4f}  (young selection rate - older)")

    mm, gw = fit_maxmin(Xtr_s, ytr, gtr)
    m_tbl, m_worst, m_dp = per_group(yte, mm.predict(Xte_s), gte)
    print("\n=== MAX-MIN (minimise the worst group's loss) ===")
    print(m_tbl.to_string())
    print(f"final group weights   : older {gw['older']:.2f}x, young {gw['young']:.2f}x")
    print(f"overall accuracy      : {(mm.predict(Xte_s) == yte).mean():.4f}")
    print(f"worst-group error     : {m_worst:.4f}")
    print(f"demographic-parity gap: {m_dp:.4f}  (young selection rate - older)")
```

### Script Execution Output

```
=== BASELINE (minimise average loss) ===
           n  accuracy   error  selection_rate
older  121.0    0.8099  0.1901          0.2066
young   79.0    0.7089  0.2911          0.3418
overall accuracy      : 0.7700
worst-group error     : 0.2911
demographic-parity gap: 0.1352  (young selection rate - older)

=== MAX-MIN (minimise the worst group's loss) ===
           n  accuracy   error  selection_rate
older  121.0    0.8099  0.1901          0.2066
young   79.0    0.7215  0.2785          0.3291
final group weights   : older 0.57x, young 1.43x
overall accuracy      : 0.7750
worst-group error     : 0.2785
demographic-parity gap: 0.1225  (young selection rate - older)
```

(Deterministic with these library versions; a solver's last digits can shift across BLAS backends, so the reading below only uses the leading digits.)

What the two runs show:

**The baseline hides a large per-group gap inside a decent average.** Overall accuracy is 77%, but that splits into **81% for older applicants and 71% for younger ones** - a 10-point accuracy gap, the same disparity the frozen `accuracy_equality_diff` flags. Average-loss training has no reason to close it: younger applicants are the smaller group (79 of 200 test rows) and carry a higher base rate of bad outcomes, so the optimizer spends its capacity where the rows are.

**Max-min lifts the worst group, and barely moves the other.** Reweighting drives the young group's weight up to 1.43x and the older group's down to 0.57x. Worst-group error falls from **29.1% to 27.9%**, the young group's accuracy rises about a point, the older group's predictions are unchanged, and overall accuracy is flat (77.0% to 77.5%). A small effect from a deliberately simple loop - stronger max-min methods (Martinez et al. 2020) push further - but it moves the right number in the right direction.

**It does not fix demographic parity, and was never trying to.** The selection-rate gap goes from 13.5 points to 12.3 points and stays large and in the same direction. A model can move toward max-min fairness while still plainly failing demographic parity: the two objectives are optimizing different things. If you need the selection rates equalized, that is a parity constraint (S3/S4 in [mitigation-strategies.md](mitigation-strategies.md)), not a max-min objective.

---

## Detection and Implementation Code

The `fit_maxmin` function above is the implementation. The check below reports whether a max-min run actually reduced the worst-group loss and what it cost the other groups - the two numbers that decide whether the trade was worth it.

```python
def maxmin_report(y_true, base_pred, maxmin_pred, groups):
    """Compare a baseline model against a max-min run, per group.

    Flags the change in worst-group error and whether any other group got
    worse (the price of the max-min trade).
    """
    rows = {}
    for g in sorted(set(groups)):
        m = groups == g
        base_err = float(1 - (base_pred[m] == y_true[m]).mean())
        mm_err = float(1 - (maxmin_pred[m] == y_true[m]).mean())
        rows[g] = {"n": int(m.sum()),
                   "baseline_error": round(base_err, 4),
                   "maxmin_error": round(mm_err, 4),
                   "delta": round(mm_err - base_err, 4)}
    base_worst = max(r["baseline_error"] for r in rows.values())
    mm_worst = max(r["maxmin_error"] for r in rows.values())
    regressed = [g for g, r in rows.items() if r["delta"] > 1e-4]
    return {
        "per_group": rows,
        "worst_group_error_before": round(base_worst, 4),
        "worst_group_error_after": round(mm_worst, 4),
        "worst_group_improved": mm_worst < base_worst,
        "groups_that_got_worse": regressed,
    }
```

---

## Limitations

### 1. A tiny or noisy subgroup can dominate

Max-min chases whichever group is currently worst. If one group is small, its measured loss is high-variance, and the loop can pour weight into fitting noise for a handful of rows - hurting everyone else for no real gain. In the example above the "young" test group is only 79 rows; a real deployment should pair max-min with a minimum-group-size floor, the same guard this repo's [significance module](../faircode/significance.py) applies with its small-sample warning. Without that floor, "worst-off group" is not a stable target.

### 2. "Worst-off" depends on a chosen loss function

The worst group under 0-1 error, under log-loss, under false-negative rate, and under calibration error can be three different groups. Max-min is only defined once you fix the loss, and that choice is a value judgment, not a technical default - the same point [Fairness Metric Conflicts](fairness-metric-conflicts.md) makes about parity metrics.

### 3. It is silent on between-group gaps

If your obligation is a legal disparate-impact standard (an 80%-rule selection-rate ratio), max-min does not help you meet it and can move you away from it, as the example shows. Max-min and parity are complementary tools for different requirements, not substitutes.

### 4. Levelling down is technically permitted at the margin

Minimizing the maximum loss is usually improved by *raising* the worst group, but a solver can also lower a better-off group if that reduces the maximum (for instance by shifting a shared threshold). Pareto-efficient formulations (Martinez et al. 2020) rule this out explicitly; a plain reweighting loop does not.

---

## Related Concepts

- [Why Fairness Metrics Conflict](fairness-metric-conflicts.md) - conflicts among parity metrics; the parity-vs-max-min conflict is a separate axis.
- [What Is Distributionally Robust Optimization (DRO) for Fairness?](distributionally-robust-optimization.md) - the worst-case-loss training method that is the online form of the reweighting loop here.
- [Mitigation Strategies](mitigation-strategies.md) - this repo's S0-S4 ladder, all of which target demographic parity rather than worst-group loss.
- [What Is Class Imbalance?](class-imbalance.md) - why the smaller, higher-base-rate group is the one average-loss training underserves.
- [What Is Demographic Parity?](demographic-parity.md) - the parity objective max-min is being contrasted against.

---

## Related Projects in This Repo

- [`German Credit Lending/`](../German%20Credit%20Lending/) - Audit 03, the dataset and `age` attribute used above.
- [`paper/results-frozen/results_fairness.csv`](../paper/results-frozen/) - the frozen `accuracy_equality_diff` figure this explainer cites as the repo's own record of the per-group accuracy gap.
- [`faircode/significance.py`](../faircode/significance.py) - the small-sample warning referenced in Limitation 1.

---

## Further Reading

- [Rawls, J. (1971, rev. 1999): *A Theory of Justice*, Harvard University Press](https://www.hup.harvard.edu/books/9780674000780) - the "difference principle": social and economic inequalities are just only if they benefit the least-advantaged members of society.
- [Hashimoto, Srivastava, Namkoong & Liang (2018): Fairness Without Demographics in Repeated Loss Minimization, ICML 2018, PMLR 80:1929-1938](https://proceedings.mlr.press/v80/hashimoto18a.html) - a DRO objective that bounds the minority group's risk without using group labels.
- [Martinez, Bertran & Sapiro (2020): Minimax Pareto Fairness: A Multi Objective Perspective, ICML 2020, PMLR 119:6755-6764](https://proceedings.mlr.press/v119/martinez20a.html) - treats each group's risk as a separate objective and finds a classifier that is minimax and Pareto-efficient, with no test-time access to the protected attribute.
- [Diana, Gill, Kearns, Kenthapadi & Roth (2021): Minimax Group Fairness: Algorithms and Experiments, AIES 2021](https://doi.org/10.1145/3461702.3462523) - practical algorithms for the min-max group-error objective and how it compares to statistical-parity mitigation.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
