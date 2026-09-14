# What Is Simpson's Paradox in Fairness Audits?

> *A model can look fair in aggregate while every disaggregated subgroup shows the opposite pattern, or look unfair in aggregate when no subgroup does - because pooling groups of different sizes and base rates lets the mix, not the model, drive the headline number.*

## The One-Sentence Definition

**Simpson's Paradox** is a statistical phenomenon in which a trend or association that holds within every subgroup of the data reverses, disappears, or appears out of nowhere once the subgroups are combined into a single aggregate, because the subgroups differ in size and in their baseline rates.

## Why It Matters

Almost every fairness metric in this repo is a single aggregate number: one `demographic_parity_diff`, one selection-rate gap, one accuracy-equality figure per audit. That number is computed by pooling every row for a protected group and comparing the pooled rate to another group's pooled rate.

Pooling is not neutral. When a protected group is distributed differently across the strata of some other variable - an occupation, a marital status, a loan product, a hospital - than the comparison group is, the aggregate comparison silently reweights those strata. The result is a headline gap that can be several times larger than any gap that actually exists within a stratum, can point the opposite direction from every stratum, or can vanish entirely.

This is distinct from [intersectional bias](intersectional-bias.md), which is about a compounding gap that only appears at the *intersection* of two attributes and is hidden when you check one attribute at a time. Simpson's Paradox is the reverse direction: a gap that appears (or flips) in the *aggregate* and is not present, or is present with the opposite sign, once you disaggregate. Both are failures of looking at the data at the wrong level, but they pull in opposite directions, and a serious audit has to check for both.

Simpson's Paradox does not tell you which view is correct. It only tells you that the aggregate and the disaggregated pictures disagree, which means the aggregate number alone cannot be trusted as a fairness finding without knowing why they disagree.

## How It Works

Let `Y` be a binary outcome (1 = the favorable outcome), `G` a protected group, and `S` a stratifying variable with levels `s`. The aggregate rate for a group is a weighted average of its within-stratum rates, where the weights are how that group is distributed across strata:

```
P(Y = 1 | G = g) = sum over s of  P(S = s | G = g) * P(Y = 1 | G = g, S = s)
```

Two things vary between groups in that sum: the within-stratum rates `P(Y = 1 | G = g, S = s)`, and the stratum weights `P(S = s | G = g)`. The aggregate gap between two groups blends both. If the weights differ enough, the weight term can dominate and the aggregate gap stops reflecting the within-stratum rates at all.

### A minimal reversal

Consider a hiring screen with two departments. Within each department the callback rate for Group A is higher than for Group B:

| Department | Group A callbacks | Group B callbacks |
|---|---|---|
| Engineering (easy to pass) | 70 / 80 = **87.5%** | 18 / 20 = **90.0%** |
| Design (hard to pass) | 2 / 20 = **10.0%** | 8 / 80 = **10.0%** |
| **Pooled** | 72 / 100 = **72.0%** | 26 / 100 = **26.0%** |

Within Engineering, Group B does slightly better (90.0% vs 87.5%); within Design the two are tied (10.0% vs 10.0%). Neither department favors Group A. Yet the pooled rate shows Group A ahead by 46 points, because 80% of Group A's applicants are in the high-callback department and 80% of Group B's are in the low-callback one. The pooled 46-point "gap" is entirely a fact about where each group applied, not about how either group was treated inside a department.

## Concrete Example: Benefits Denial - Audit 05

`Benefits Denial/` audits the Adult Census Income dataset (`adult.csv`, 32,561 rows), where the target is `income == '>50K'` and `sex` is a declared protected attribute. These are the dataset's own outcome rates (not a model's predictions), which is the base rate a demographic-parity check on the labels compares.

**Aggregate:**

| Group | n | P(income > 50K) |
|---|---:|---:|
| Male | 21,790 | **30.6%** |
| Female | 10,771 | **10.9%** |
| Gap (M - F) | | **+19.6 pp** |

Now stratify by `marital.status`. The single largest stratum, `Married-civ-spouse`, holds 14,976 rows - 46% of the entire dataset:

| Stratum | Male n | Male rate | Female n | Female rate | Gap (M - F) |
|---|---:|---:|---:|---:|---:|
| Married-civ-spouse | 13,319 | 44.6% | 1,657 | 45.5% | **-0.9 pp** |
| Never-married | 5,916 | 5.5% | 4,767 | 3.5% | +2.0 pp |
| Divorced | 1,771 | 16.0% | 2,672 | 6.7% | +9.3 pp |
| Widowed | 168 | 23.2% | 825 | 5.6% | +17.6 pp |
| Separated | 394 | 12.4% | 631 | 2.7% | +9.7 pp |

Collapsed to just married vs not-married, the gap shrinks from +19.6 pp to **+3.0 pp** (married) and **+3.9 pp** (not married). And inside `Married-civ-spouse` - nearly half the data - the sign **reverses**: women are 0.9 points ahead.

The mechanism is the stratum weights. Women are 52% of the "not married" pool, which has an overall high-income rate of 6.5%, but only 12% of the "married" pool, which has an overall rate of 43.7%. The aggregate comparison places most men in the high-earning stratum and splits women toward the low-earning one, so roughly 16 of the 19.6 aggregate points come from *where* each group sits, not from a within-stratum difference in outcome rates.

Whether `marital.status` is a legitimate thing to condition on here is a separate, normative question - see [Conditional Demographic Parity](conditional-demographic-parity.md) and the Limitations section below. The point Simpson's Paradox makes is narrower: the +19.6 pp aggregate figure, reported on its own, describes the dataset's composition at least as much as it describes any disparity in outcomes.

```python
import pandas as pd

df = pd.read_csv("Benefits Denial/adult.csv")
df["high_income"] = (df["income"] == ">50K").astype(int)


def sex_gap(frame):
    male = frame.loc[frame["sex"] == "Male", "high_income"].mean()
    female = frame.loc[frame["sex"] == "Female", "high_income"].mean()
    return male, female, male - female


print("aggregate:", sex_gap(df))
# (0.3057, 0.1095, 0.1962)

married = df[df["marital.status"] == "Married-civ-spouse"]
print("married-civ-spouse:", sex_gap(married))
# (0.4458, 0.4550, -0.0092)  <- sign reversed
```

## Detection Code

The following module compares a rate gap computed in aggregate against the same gap computed within each stratum of a chosen variable, and reports whether the aggregate sign matches the strata, whether it is inflated, or whether it reverses.

```python
import numpy as np
import pandas as pd


def simpsons_check(
    df: pd.DataFrame,
    outcome_col: str,
    group_col: str,
    advantaged: str,
    disadvantaged: str,
    stratify_col: str,
    min_stratum_size: int = 100,
    min_group_in_stratum: int = 30,
) -> dict:
    """
    Compare the (advantaged - disadvantaged) outcome-rate gap in aggregate
    against the same gap within each stratum of stratify_col.

    outcome_col must be 0/1. Returns a dict with the aggregate gap, a table
    of per-stratum gaps (sample-size weighted), the weighted-average
    within-stratum gap, and a verdict:

      "consistent"        aggregate agrees in sign and rough size with strata
      "inflated"          same sign, but |aggregate| far exceeds the weighted
                          within-stratum gap (aggregation is amplifying it)
      "sign_reversal"     aggregate sign is opposite the weighted within gap,
                          or opposite the majority of strata by sample size
    """
    d = df[[outcome_col, group_col, stratify_col]].dropna()
    d = d[d[group_col].isin([advantaged, disadvantaged])]

    def gap(frame):
        a = frame.loc[frame[group_col] == advantaged, outcome_col]
        b = frame.loc[frame[group_col] == disadvantaged, outcome_col]
        if len(a) == 0 or len(b) == 0:
            return np.nan, len(a), len(b)
        return a.mean() - b.mean(), len(a), len(b)

    agg_gap, n_adv, n_dis = gap(d)

    rows = []
    for value, sub in d.groupby(stratify_col):
        if len(sub) < min_stratum_size:
            continue
        g, na, nb = gap(sub)
        if np.isnan(g) or min(na, nb) < min_group_in_stratum:
            continue
        rows.append({"stratum": value, "n": len(sub), "gap": g,
                     "n_advantaged": na, "n_disadvantaged": nb})

    strata = pd.DataFrame(rows).sort_values("n", ascending=False)
    if strata.empty:
        return {"verdict": "insufficient_data", "aggregate_gap": agg_gap,
                "strata": strata}

    weights = strata["n"] / strata["n"].sum()
    weighted_within_gap = float((strata["gap"] * weights).sum())

    same_sign = np.sign(agg_gap) == np.sign(weighted_within_gap)
    majority_n_opposite = strata.loc[
        np.sign(strata["gap"]) != np.sign(agg_gap), "n"
    ].sum() > strata["n"].sum() / 2

    if not same_sign or majority_n_opposite:
        verdict = "sign_reversal"
    elif abs(agg_gap) > 2 * abs(weighted_within_gap) + 0.05:
        verdict = "inflated"
    else:
        verdict = "consistent"

    return {
        "verdict": verdict,
        "aggregate_gap": float(agg_gap),
        "weighted_within_stratum_gap": weighted_within_gap,
        "n_advantaged": int(n_adv),
        "n_disadvantaged": int(n_dis),
        "strata": strata.reset_index(drop=True),
    }


def print_simpsons_report(result: dict) -> None:
    print(f"Verdict: {result['verdict']}")
    print(f"  aggregate gap (adv - dis):       {result['aggregate_gap']:+.4f}")
    if "weighted_within_stratum_gap" in result:
        print(f"  weighted within-stratum gap:     "
              f"{result['weighted_within_stratum_gap']:+.4f}")
        print("\n  per-stratum gaps (largest first):")
        for _, row in result["strata"].iterrows():
            flip = "  <- opposite sign" if (
                np.sign(row["gap"]) != np.sign(result["aggregate_gap"])
            ) else ""
            print(f"    {str(row['stratum'])[:24]:24s} "
                  f"n={int(row['n']):6d}  gap={row['gap']:+.4f}{flip}")


# Usage on the Benefits Denial audit:
# import pandas as pd
# df = pd.read_csv("Benefits Denial/adult.csv")
# df["high_income"] = (df["income"] == ">50K").astype(int)
# print_simpsons_report(simpsons_check(
#     df, "high_income", "sex", "Male", "Female", "marital.status"))
```

Run against `Benefits Denial/adult.csv` with `stratify_col="marital.status"`, this reports `inflated`, not `sign_reversal` - even though `Married-civ-spouse` (46% of the sample) reverses sign on its own, `sign_reversal` requires either the *weighted-average* within-stratum gap to disagree in sign with the aggregate, or a strict majority (over 50% of rows, not just the largest single stratum) to be opposite-signed. Neither holds here: the weighted within-stratum gap (`+0.024`) agrees in sign with the aggregate (`+0.196`), and the other five strata's combined weight still outweighs `Married-civ-spouse`'s 46%. What the aggregate figure is doing instead is amplifying a real, same-direction effect roughly eightfold (`0.196` vs. `0.024`), which is exactly what `inflated` means - a single large, sign-reversed stratum is a real and worth-noting finding on its own, but it isn't sufficient by itself to call the aggregate a fabrication; that requires weighing every stratum, not eyeballing the biggest one.

## Limitations and Trade-offs

### 1. There is no single correct level of aggregation

Simpson's Paradox flags a disagreement; it does not adjudicate it. Whether the aggregate or the within-stratum view is the "real" fairness finding depends on whether the stratifying variable is a legitimate explanation for the outcome difference or is itself part of the discrimination. Conditioning on a variable that is a proxy for the protected attribute launders the disparity away (see [Proxy Variables](proxy-variables.md)); conditioning on a genuinely exogenous factor removes a confound. That judgment is normative and domain-specific, not statistical.

### 2. Choosing the stratifying variable is a modeling decision

You will not find a reversal for every variable. The detection code above tests one variable at a time; running it across many candidate strata invites finding a reversal by chance, especially with small strata. A reported reversal is only meaningful for a variable there is an independent reason to care about.

### 3. Small strata produce unstable per-group rates

Disaggregation shrinks sample sizes fast. A stratum where one group has 30 members will have a within-stratum rate with a wide confidence interval, and its "gap" can flip sign across dataset splits from noise alone. The `min_group_in_stratum` guard mitigates but does not eliminate this.

### 4. Continuous confounders need binning, and the bins matter

The example used a categorical stratifier. For a continuous confounder (age, income, tenure) you have to choose bin edges, and coarse or misaligned bins can hide a reversal that finer bins would show, or manufacture one. Report the binning alongside the result.

## Related Concepts

* [What Is Intersectional Bias?](intersectional-bias.md) - the opposite failure: a compounding gap visible only at the intersection of two attributes, hidden when each is checked alone.
* [What Is Conditional Demographic Parity?](conditional-demographic-parity.md) - the fairness metric built specifically around checking parity *within* strata of a chosen legitimate factor.
* [What Is a Confounding Variable?](confounding-variable.md) - the underlying causal structure that makes Simpson's reversals possible.
* [What Is the Base Rate Fallacy?](base-rate-fallacy.md) - a related error about ignoring prior probabilities when reading a conditional rate.
* [What Is a Proxy Variable?](proxy-variables.md) - why conditioning on the wrong variable can hide real discrimination instead of explaining it.

## Related Projects in This Repo

* [`Benefits Denial/`](../Benefits%20Denial/) - the Adult Census Income audit used above; the aggregate `sex` income gap is roughly five times any within-marital-status gap and reverses inside the largest stratum.
* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - a multi-hospital readmission audit where per-facility case mix is a natural stratifier for an aggregate readmission-rate gap.

## Further Reading

* [Bickel, P. J., Hammel, E. A., O'Connell, J. W. (1975): Sex Bias in Graduate Admissions: Data from Berkeley, *Science*, 187(4175), 398-404](https://www.science.org/doi/10.1126/science.187.4175.398) - the canonical worked example: Berkeley's aggregate admit rate favored men, but department by department it did not.
* [Simpson, E. H. (1951): The Interpretation of Interaction in Contingency Tables, *Journal of the Royal Statistical Society B*, 13(2), 238-241](https://www.jstor.org/stable/2984065) - the paper the effect is named after.
* [Pearl, J. (2014): Comment: Understanding Simpson's Paradox, *The American Statistician*, 68(1), 8-13](https://ftp.cs.ucla.edu/pub/stat_ser/r414.pdf) - why the paradox is a causal question, not a statistical one, and why no purely statistical rule resolves it.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
