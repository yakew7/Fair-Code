> *Removing the protected attribute from a model's inputs is the single most common first response to a fairness complaint - and on real data, it can leave the gap unchanged, or make it worse.*

## The One-Sentence Definition

**Fairness through unawareness** is the intuition that a model is fair simply because it does not use a protected attribute (race, sex, age) as an input - and it fails whenever other features carry enough correlated information to reconstruct what was removed.

## Why It Matters

Dropping the protected attribute feels like the obvious fix, and it's usually the first thing anyone tries: no race column, no racial bias. The reasoning has an intuitive appeal that makes it persistent even after it's been shown not to hold - "the model literally cannot see race" sounds like a complete argument.

It isn't, because a protected attribute rarely travels alone. Zip code correlates with race through housing patterns. Name correlates with sex and ethnicity. Employment history and arrest records correlate with race through decades of unequal enforcement and access. A model doesn't need the protected attribute itself if enough of its correlates are still sitting in the feature set - it can reconstruct the same decision boundary from the pieces left behind. This is exactly the mechanism [Proxy Variables](proxy-variables.md) describes, and it's why "fairness through unawareness" is treated in the fairness literature as a well-documented failure mode, not a live debate.

This repo's own benchmark harness names this exact strategy `unawareness` (S1 in the [mitigation strategies](mitigation-strategies.md) ladder) and runs it on every audit specifically to measure how much it actually helps - which, as the real numbers below show, is not a fixed or guaranteed amount.

## Concrete Example: Tenant Screening - Audit 07

The demographic parity gap for the baseline logistic regression model on race (disadvantaged: Black applicants, n=2,943; advantaged: White applicants, n=2,224), using the frozen numbers exactly as `faircode/benchmark.py` computed them:

| Strategy | Demographic Parity Diff | 95% CI | p-value |
|---|---:|---|---:|
| S0 baseline (race included) | 0.060 | [0.032, 0.086] | 0.0 |
| S1 unawareness (race dropped) | 0.105 | [0.077, 0.131] | 0.0 |

Dropping race from the model's inputs did not shrink the gap - it grew, from 6.0 points to 10.5 points, and both numbers are tightly estimated and clearly significant (large n, narrow CIs, p essentially 0). This is the opposite of what "fairness through unawareness" predicts.

It's tempting to explain this by saying the core features still available to the model - `Supervision_Risk_Score_First`, prior-arrest-episode counts, employment percentage - carry strong correlation with race, and the model just leaned on those correlates once race itself was gone. Running this file's own `unawareness_gap_check()` (below) against exactly that feature set on the real data doesn't support that story: reconstruction accuracy comes out to **0.602** (0.617 with a fuller feature list), barely above the 0.573 majority-class base rate and well under the function's own 0.75 "reconstructs well" threshold. By this check, these features do not cleanly reconstruct race - so a clean "the proxies stood in for race" explanation for the widened gap does not hold up against this repo's own tool.

What more plausibly moved the gap instead is the model's fitted coefficients, not a proxy reconstructing race: with race unavailable, `LogisticRegression` refits every remaining coefficient from scratch, and even a modest, imperfect correlate can get reweighted differently once it's the only remaining signal touching group membership - without that correlate ever reconstructing race well enough to clear a 0.75 bar. `faircode/strategies.py`'s next strategy, `unawareness_proxy_removal` (S2), goes further and drops the explicitly-listed proxy features too - see [Mitigation Strategies](mitigation-strategies.md) for how that step, and the constraint-based strategies after it, actually move this specific gap.

## Detection Code

Checks whether dropping a column actually reduces its correlation with the rest of the feature set, instead of assuming it does.

```python
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder


def unawareness_gap_check(df, protected_column, feature_columns, group_disadvantaged, group_advantaged):
    """
    Fits a simple classifier on `feature_columns` to predict the protected
    attribute itself. A high accuracy means the remaining features can
    reconstruct the protected attribute almost as well as having it
    directly - the exact condition under which dropping it will fail to
    remove its effect on downstream predictions.

    Parameters:
        df: DataFrame containing both the protected column and the
            candidate feature columns
        protected_column: name of the protected-attribute column
        feature_columns: candidate columns to keep after "unawareness"
        group_disadvantaged, group_advantaged: the two values of
            protected_column to compare

    Returns a dict with reconstruction_accuracy (how well the remaining
    features predict the dropped attribute) and a plain verdict.
    """
    mask = df[protected_column].isin([group_disadvantaged, group_advantaged])
    sub = df[mask].dropna(subset=feature_columns + [protected_column])

    X = pd.get_dummies(sub[feature_columns])
    y = LabelEncoder().fit_transform(sub[protected_column])

    model = LogisticRegression(max_iter=1000)
    model.fit(X, y)
    accuracy = model.score(X, y)

    return {
        "reconstruction_accuracy": accuracy,
        "verdict": (
            "Remaining features reconstruct the protected attribute well - "
            "dropping it is unlikely to remove its effect."
            if accuracy > 0.75 else
            "Remaining features poorly predict the protected attribute - "
            "dropping it is more likely to actually help."
        ),
    }


# Usage example:
# result = unawareness_gap_check(
#     df, protected_column="Race",
#     feature_columns=["Supervision_Risk_Score_First", "Prior_Arrest_Episodes_Felony",
#                       "Prior_Arrest_Episodes_Violent", "Percent_Days_Employed"],
#     group_disadvantaged="BLACK", group_advantaged="WHITE",
# )
# print(result)
```

## Limitations

### 1. The gap can move in either direction, not just "stay the same"

As Tenant Screening shows, dropping the protected attribute can make the measured gap *larger*, not just fail to shrink it. There is no guarantee of direction, only that the outcome depends on exactly which correlated features remain and how the model reweights them.

### 2. Proxy removal is not a complete fix either

This repo's own next strategy after unawareness, `unawareness_proxy_removal`, only removes a pre-defined, finite list of known proxies - see [Proxy Variables](proxy-variables.md) for why an unlisted or newly-emerging proxy can slip through even that step.

### 3. It removes information the model might need for a *legitimate* reason

Some uses of a protected-adjacent attribute are lawful and relevant (age in certain insurance actuarial contexts, for instance); blanket removal without checking what else changes can trade one problem for a different, unexamined one.

### 4. It provides no way to measure whether it worked without checking a real fairness metric

"Unawareness" alone gives no signal, on its own, about whether the resulting model is more or less fair - only comparing an actual gap metric before and after, as this repo's benchmark harness does for every audit, can answer that.

## Related Concepts

* [Proxy Variables](proxy-variables.md) - the mechanism (correlated features standing in for the removed attribute) that makes fairness through unawareness fail.
* [What Are Pre-, In-, and Post-Processing Fairness Mitigations?](mitigation-strategies.md) - where "unawareness" sits as the first, weakest step in a five-strategy ladder, and what the stronger steps do differently.
* [What Is Demographic Parity?](demographic-parity.md) - the metric used to measure the gap in the Tenant Screening example above.

## Related Projects in This Repo

* [`Tenant Screening/`](../Tenant%20Screening/) - the audit above, where dropping race increased the measured gap rather than closing it.
* [`Insurance Denial/`](../Insurance%20Denial/) - a second real audit in this repo's benchmark harness where the same `unawareness` strategy is applied and measured independently.

## Further Reading

* [Pedreschi, D., Ruggieri, S., Turini, F. (2008): Discrimination-Aware Data Mining](https://doi.org/10.1145/1401890.1401959) - an early formal treatment of why removing a sensitive attribute doesn't remove its statistical effect.
* [Kusner, M. et al. (2017): Counterfactual Fairness](https://arxiv.org/abs/1703.06856) - proposes a causal alternative that explicitly accounts for what unawareness misses; see also [Counterfactual Fairness](counterfactual-fairness.md).
* [Barocas, S., Hardt, M., Narayanan, A. (2019): *Fairness and Machine Learning*](https://fairmlbook.org/introduction.html) - Chapter 1 covers "fairness through unawareness" directly as one of the field's earliest and most persistently re-discovered mistakes.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
