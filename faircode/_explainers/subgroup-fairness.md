# What Is Subgroup Fairness (and Fairness Gerrymandering)?

> *A model can pass a fairness check on race, pass it on sex, pass it on age, and still fail badly on some combination like "women over 50 in a particular region" that nobody thought to check by hand. Subgroup fairness is what you get when you stop hand-picking the groups and search for the one where the guarantee breaks.*

## The One-Sentence Definition

**Subgroup fairness** requires a fairness metric to hold not just on each protected attribute checked individually, but across a large, structured class of subgroups defined by combinations of attributes and features - and **fairness gerrymandering** is the failure mode where a model satisfies every marginal check while hiding a large disparity inside one of those combinations.

## Why It Matters

Checking `race`, then `sex`, then `age` separately gives you three guarantees, one per axis. Adding a hand-chosen pair, the way this repo's `--cross` flag does for a single intersection (SPEC section 4), gives you a fourth. None of that is the same as a guarantee over *every* combinatorially definable subgroup.

The gap between "fair on each attribute I checked" and "fair on every subgroup" is exploitable, and not only by an adversary. A model trained to minimize a marginal fairness violation - equalize selection rates by race, and by sex - has no incentive to equalize them for `race x sex x age-band` cells it was never scored on. It can push the disparity into those cells precisely because doing so is invisible to the marginal metrics. Kearns et al. (2018) named this **fairness gerrymandering**, by analogy to how an oddly shaped electoral district can hide a population imbalance that looks fine at the state level.

This is the more general, adversarial version of [intersectional bias](intersectional-bias.md). Intersectional bias is about checking one specific human-chosen pair (Black women, say) and finding a compounding gap. Subgroup fairness replaces "the pair a human picked" with "an automated search over a whole hypothesis class of subgroups" - for example, every group definable by a linear threshold over the features - looking for the subgroup where a fairness constraint is violated by the most.

## How It Works

Fix a fairness metric - selection rate, false positive rate, whatever the audit uses. For a subgroup `g` (a subset of the population picked out by some rule over attributes and features), define its violation as how far that metric inside `g` sits from the population value:

```
violation(g) = | metric(g) - metric(overall) |   weighted by how large g is
```

Marginal fairness only bounds `violation(g)` for `g` in a short list: `g = {race = A}`, `g = {sex = F}`, and so on. Subgroup fairness bounds it for `g` in a much larger class `G` - all subgroups definable by a rule of a chosen form (conjunctions of a few attributes, or a linear threshold over features).

You cannot enumerate `G` when it is large, so the audit is framed as a search: an **auditor** tries to find the `g` in `G` with the biggest violation; if it finds one above a threshold, the model fails. Kearns et al. formalize this as a two-player game between a learner (trying to build a model with no high-violation subgroup) and an auditor (trying to find one). The practical brute-force version, for a small feature set, is just: enumerate every combination of a few columns' values and check the metric in each cell.

The reason this is worth doing rather than just checking more pairs by hand: the number of subgroups grows combinatorially, and the worst one is rarely the one an auditor would have guessed.

## Concrete Example: Healthcare Readmission - Audit 06

`Healthcare Readmission/` audits the UCI diabetes 130-hospitals dataset (`diabetic_data.csv`, 101,766 encounters). The target is `readmitted == '<30'` (readmission within 30 days), and `gender`, `race`, and `age` are declared protected attributes. Using the dataset's own readmission rates (the base rate a label-level demographic parity check compares):

**Marginal check on `gender` - passes:**

| Group | n | Readmit < 30 |
|---|---:|---:|
| Female | 54,708 | 11.25% |
| Male | 47,055 | 11.06% |
| Gap | | 0.18 pp (ratio 0.984) |

A 0.18-point gap clears the EEOC four-fifths rule (ratio 0.984, well above 0.80) and any reasonable demographic parity tolerance. On the `gender` axis alone, this dataset looks clean.

**Now `gender x race` - the gender gap inside each race stratum:**

| Race | Female rate | Male rate | Gender gap (F - M) | Subgroup n |
|---|---:|---:|---:|---:|
| Caucasian | 11.49% | 11.07% | +0.42 pp | 76,099 |
| AfricanAmerican | 11.08% | 11.43% | -0.34 pp | 19,210 |
| Hispanic | 9.16% | 11.85% | **-2.69 pp** | 2,037 |
| Asian | 7.55% | 12.69% | **-5.15 pp** | 641 |

Among Asian patients, women are readmitted at 7.55% and men at 12.69% - a 5.15-point gap and a four-fifths ratio of 0.595, a clear violation, pointing the opposite direction from the (negligible) marginal gender gap. Among Hispanic patients the gender gap is -2.69 pp, also a reversal and also larger than the marginal. The `gender` guarantee that held at the population level does not hold once you condition on race, and no single-attribute check would have surfaced that.

Two honest caveats, both of which the Limitations section expands:

- The Asian subgroup has n = 641. That is above this repo's default `min_group_size` of 100, but small enough that a 5-point rate is not a precise estimate - exactly the case this repo's small-sample warnings exist for.
- This is on raw labels, not model predictions. The gerrymandering concern is strongest for a *model* that was optimized against marginal fairness metrics; a raw-label reversal like this is evidence that the phenomenon is present in the data the models are trained on.

This repo's `--cross` flag (or the MCP `profile_dataset` `cross` option) computes exactly one such pairwise combination - the specific pair you name. It does not perform an open-ended search. Subgroup fairness is what you would need on top of it: a scan over many candidate subgroups, not one.

```python
import pandas as pd

df = pd.read_csv("Healthcare Readmission/diabetic_data.csv", low_memory=False)
df["y"] = (df["readmitted"] == "<30").astype(int)

# marginal gender check - looks fine
by_sex = df.groupby("gender")["y"].mean()
print(by_sex["Female"] - by_sex["Male"])          # +0.0018

# the same gap inside the Asian stratum - a 5-point violation
asian = df[df["race"] == "Asian"]
by_sex_asian = asian.groupby("gender")["y"].mean()
print(by_sex_asian["Female"] - by_sex_asian["Male"])   # -0.0515
```

## Detection Code

The following module runs a brute-force subgroup scan: it enumerates every combination of values over a chosen set of columns, computes a rate metric inside each cell, and reports the cells whose deviation from the population rate exceeds a threshold - the manual, small-feature-set version of an auditor. It is contrasted with the single fixed pair `--cross` checks.

```python
import itertools

import numpy as np
import pandas as pd


def subgroup_scan(
    df: pd.DataFrame,
    outcome_col: str,
    subgroup_cols: list[str],
    max_depth: int = 2,
    min_subgroup_size: int = 100,
    deviation_threshold: float = 0.05,
) -> pd.DataFrame:
    """
    Brute-force fairness-gerrymandering audit over subgroups defined by
    conjunctions of up to max_depth of the subgroup_cols.

    outcome_col must be 0/1. For every conjunction (col_a = v_a AND col_b = v_b
    AND ...) with at least min_subgroup_size rows, computes:
      rate            P(outcome = 1) inside the subgroup
      deviation       rate - overall_rate
      four_fifths     min(rate, overall) / max(rate, overall)
    and returns the subgroups whose |deviation| >= deviation_threshold,
    sorted by a size-weighted deviation so a large, badly-off subgroup ranks
    above a tiny one.

    This is exhaustive only because subgroup_cols is small. A real subgroup-
    fairness auditor searches a parameterized hypothesis class (e.g. linear
    thresholds over features) instead of enumerating cells - see Kearns et
    al. (2018).
    """
    overall = df[outcome_col].mean()
    n_total = len(df)
    results = []

    for depth in range(1, max_depth + 1):
        for cols in itertools.combinations(subgroup_cols, depth):
            grouped = df.groupby(list(cols))[outcome_col].agg(["mean", "count"])
            for key, row in grouped.iterrows():
                if row["count"] < min_subgroup_size:
                    continue
                rate = row["mean"]
                deviation = rate - overall
                ff = (min(rate, overall) / max(rate, overall)
                      if max(rate, overall) > 0 else np.nan)
                results.append({
                    "subgroup": dict(zip(cols, key if depth > 1 else (key,))),
                    "n": int(row["count"]),
                    "rate": float(rate),
                    "deviation": float(deviation),
                    "four_fifths_ratio": float(ff),
                    "weighted_deviation": abs(deviation) * (row["count"] / n_total),
                })

    out = pd.DataFrame(results)
    if out.empty:
        return out
    flagged = out[out["deviation"].abs() >= deviation_threshold]
    return flagged.sort_values("weighted_deviation", ascending=False).reset_index(drop=True)


def compare_to_fixed_cross(df, outcome_col, pair):
    """What this repo's --cross gives you: the metric for that ONE pair,
    every cell, no search, no ranking by violation."""
    return df.groupby(list(pair))[outcome_col].agg(["mean", "count"]).round(4)


# Usage on the Healthcare Readmission audit:
# import pandas as pd
# df = pd.read_csv("Healthcare Readmission/diabetic_data.csv", low_memory=False)
# df["y"] = (df["readmitted"] == "<30").astype(int)
# print(subgroup_scan(df, "y", ["gender", "race", "age"], max_depth=2))
# # 9 cells clear the default 0.05 threshold; the top-ranked one is
# # race x age = (Caucasian, [20-30)), n=975, deviation ~ +0.055
```

## Limitations and Trade-offs

### 1. A full combinatorial search is expensive and overfits noise

Enumerating every conjunction of `k` columns is exponential in `k`, and the search rewards finding the most extreme cell - which, for small subgroups, is often the noisiest one rather than the most unfair one. This repo's `min_group_size` default (100) and its "small group (metric may be unreliable)" warnings exist for exactly this reason. A flagged subgroup with 60 members and a 15-point deviation may be sampling noise; the same deviation at n = 5,000 is a finding.

### 2. The hypothesis class is a design choice, and it bounds what you can catch

An auditor that searches conjunctions of categorical attributes will not find a gerrymandered group defined by a linear threshold over continuous features, and vice versa. "Subgroup fair with respect to class G" is only as strong as G is expressive, and a richer G costs more compute and overfits harder.

### 3. Passing a subgroup audit is not the same as being fair

Kearns et al.'s guarantee is that no subgroup *in the searched class* has a large violation. A disparity that lives in a subgroup outside the class, or that only appears under a different metric, is still invisible. Subgroup fairness widens the net; it does not make it infinite.

### 4. Fixing a flagged subgroup can move the disparity, not remove it

Constraining the model to equalize a metric inside a discovered subgroup can push the imbalance into an adjacent, not-yet-searched subgroup - the same whack-a-mole that motivates the learner-auditor game in the first place. Iterating the game to convergence is the intended fix; a one-shot patch of the worst cell is not.

## Related Concepts

* [What Is Intersectional Bias?](intersectional-bias.md) - checking one specific, human-chosen combination of attributes; subgroup fairness is the open-ended search version.
* [What Is Individual Fairness?](individual-fairness.md) - the opposite pole: "similar individuals treated similarly" rather than any group-rate comparison.
* [What Is Simpson's Paradox in Fairness Audits?](simpsons-paradox.md) - why an aggregate rate can disagree with its disaggregated cells.
* [Why Fairness Metrics Conflict](fairness-metric-conflicts.md) - the impossibility results that also constrain what a subgroup audit can promise.
* [What Is the Base Rate Fallacy?](base-rate-fallacy.md) - why small subgroups produce volatile rate estimates.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the audit above; `gender` is clean marginally but the gender gap reaches -5 pp inside the Asian stratum.
* [`COMPAS/`](../COMPAS/) - `--cross race age` on this audit is a single fixed intersection; a subgroup scan would search race, sex, age, and custody-status combinations at once.

## Further Reading

* [Kearns, M., Neel, S., Roth, A., Wu, Z. S. (2018): Preventing Fairness Gerrymandering: Auditing and Learning for Subgroup Fairness, *ICML 2018* (PMLR 80)](https://arxiv.org/abs/1711.05144) - defines fairness gerrymandering and gives the learner-auditor game for auditing and enforcing subgroup fairness.
* [Kearns, M., Neel, S., Roth, A., Wu, Z. S. (2019): An Empirical Study of Rich Subgroup Fairness for Machine Learning, *FAT\* 2019*](https://arxiv.org/abs/1808.08166) - the follow-up experiments showing the method works on real datasets and what it costs.
* [Hebert-Johnson, U., Kim, M. P., Reingold, O., Rothblum, G. (2018): Multicalibration: Calibration for the (Computationally-Identifiable) Masses, *ICML 2018*](https://arxiv.org/abs/1711.08513) - a closely related guarantee (calibration, not selection rate) over a large class of subgroups.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
