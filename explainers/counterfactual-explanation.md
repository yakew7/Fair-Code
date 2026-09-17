> *"Counterfactual" shows up twice in this repo's explainers for two genuinely different ideas - one is a fairness definition, the other is an explainability technique, and confusing them means asking the wrong question of the wrong tool.*

## The One-Sentence Definition

A **counterfactual explanation** answers, for one specific denied or flagged decision: what is the smallest change to this person's inputs that would have flipped the model's output? It comes from the explainability literature (Wachter, Mittelstadt & Russell, 2017), not the fairness-definitions literature.

## Not to Be Confused With Counterfactual Fairness

[Counterfactual Fairness](counterfactual-fairness.md) (Kusner et al., 2017) is a *fairness definition*: it asks whether an individual's outcome would differ if they had been born into a different demographic group, holding everything causally independent of that group membership constant. It's a test applied to the model as a whole, using a causal graph.

A **counterfactual explanation** is a different question entirely, applied to one prediction, with no causal graph required: not "would this differ if your race were different," but "what is the nearest input you *could actually have had* that gets you approved instead of denied?" One is about detecting discrimination; the other is about explaining, and potentially contesting, a single outcome. The shared word is a real, common point of confusion - they come from different research communities and answer different questions, and it's entirely possible for a decision to pass one framework's test while a counterfactual explanation for it looks completely unreasonable, or vice versa.

## Why It Matters

A counterfactual explanation is the basis for real "adverse action" notices required by credit and lending regulation (the U.S. Equal Credit Opportunity Act, for one): when a loan is denied, the applicant is often owed a concrete, actionable reason. "Your income was $4,000 below the approval threshold" is a counterfactual explanation - and a genuinely useful one, since it tells the applicant something they could plausibly act on, unlike a raw model score or a list of feature-attribution weights.

That practical framing - "what would need to change" - is also what puts counterfactual explanation alongside feature-attribution methods as a third major explainability paradigm: [SHAP](shap-values.md) and [LIME](lime.md) both answer "how much did each feature contribute," while counterfactual explanation answers "what's the minimal edit that changes the outcome." For someone on the receiving end of an automated decision, the second question is usually the one they actually have.

## Core Concept: Minimal, Actionable Change

Formally, a counterfactual explanation for input `x` (predicted class `y`) is a nearby point `x'` such that the model predicts a different class for `x'`, and `x'` is as close to `x` as possible under some distance measure. "Close" typically means: change as few features as possible, and by as little as possible - not the theoretical minimum-distance point in raw numerical terms, but one that corresponds to a change the person could realistically make.

That "realistically make" qualifier is where most of the actual difficulty lives. A mathematically nearest counterfactual might suggest lowering age by ten years or changing a protected attribute - technically the smallest edit, and completely useless as advice. Real counterfactual-explanation methods constrain the search to *actionable* features (income, employment length, outstanding debt) and hold immutable ones (age, race, past history that can't be un-happened) fixed.

## Concrete Example: German Credit Lending - Audit 03

For an applicant denied credit by the baseline model, a counterfactual search over actionable features illustrates the difference from a feature-attribution explanation:

```
--- ORIGINAL APPLICATION (predicted: denied) ---
credit_amount: 4,800
duration: 36
employment: 1<=X<4
existing_credits: 2

--- NEAREST COUNTERFACTUAL (predicted: approved) ---
credit_amount: 4,800          (unchanged)
duration: 24                   (-12 months)
employment: 1<=X<4              (unchanged)
existing_credits: 1             (-1)
```

Where a SHAP or LIME explanation would report *how much* each feature contributed to the denial, the counterfactual explanation says something directly actionable instead: shorten the requested loan term by a year and close one existing credit line, and this specific model would have approved the application. That's the kind of statement an adverse-action notice is meant to contain, and it's a fundamentally different output than a feature-importance ranking.

## Detection Code

A minimal from-scratch nearest-counterfactual search over actionable features only, holding immutable ones fixed - the same constraint real counterfactual-explanation tooling (like `dice-ml`) enforces, implemented directly rather than as a library wrapper.

```python
import numpy as np
import pandas as pd


def nearest_counterfactual(model, instance, actionable_features, feature_ranges,
                           target_class=1, step=0.05, max_iters=200):
    """
    Searches for the smallest change to `instance`'s actionable features
    that flips the model's prediction to `target_class`, via random
    perturbation within each feature's real observed range - a simple
    stand-in for the optimization-based search real tools use.

    Parameters:
        model: a fitted classifier with .predict()
        instance: pandas Series, the original input row
        actionable_features: list of column names allowed to change
            (immutable features like age or protected attributes are
            never touched)
        feature_ranges: {column: (min, max)} for each actionable feature,
            typically the observed range in the training data
        target_class: the desired predicted class
        step: fraction of each feature's range to perturb by, per iteration
        max_iters: number of candidate counterfactuals to try

    Returns the closest successful counterfactual found (as a Series), or
    None if no perturbation within max_iters flipped the prediction.
    """
    rng = np.random.default_rng(42)
    best = None
    best_distance = float("inf")

    for _ in range(max_iters):
        candidate = instance.copy()
        if pd.api.types.is_integer_dtype(candidate):
            # An instance built from all-integer values (e.g. a hand-built
            # example row) infers an int64 Series, which raises a TypeError
            # the moment a float perturbation is assigned into it. A real
            # dataset row is usually mixed-dtype (object) already, where
            # this cast is a no-op.
            candidate = candidate.astype("float64")
        for feature in actionable_features:
            low, high = feature_ranges[feature]
            delta = rng.uniform(-step, step) * (high - low)
            candidate[feature] = np.clip(candidate[feature] + delta, low, high)

        if model.predict(pd.DataFrame([candidate]))[0] == target_class:
            distance = sum(
                abs(candidate[f] - instance[f]) / (feature_ranges[f][1] - feature_ranges[f][0])
                for f in actionable_features
            )
            if distance < best_distance:
                best, best_distance = candidate, distance

    return best


# Usage example:
# counterfactual = nearest_counterfactual(
#     model, denied_applicant,
#     actionable_features=["duration", "existing_credits"],
#     feature_ranges={"duration": (4, 72), "existing_credits": (1, 4)},
# )
# if counterfactual is not None:
#     print(counterfactual[["duration", "existing_credits"]])
```

## Limitations

### 1. Multiple, equally valid counterfactuals can exist

There is rarely one unique "nearest" counterfactual - several different, equally small edits might all flip the outcome. Which one gets shown to the applicant is a choice, and different choices can suggest very different, sometimes contradictory, advice.

### 2. A mathematically small change isn't necessarily a realistic one

Without hard constraints on which features are actionable and which are immutable, a naive search can suggest changing an unchangeable attribute, or an unrealistic combination (raise income *and* reduce debt *and* extend employment history, all simultaneously and immediately).

### 3. It explains one decision, not the model's overall fairness

Like [SHAP](shap-values.md) and [LIME](lime.md), a counterfactual explanation is local to a single prediction. It says nothing about whether the model's aggregate behavior satisfies [Demographic Parity](demographic-parity.md), [Equalized Odds](equalized-odds.md), or [Counterfactual Fairness](counterfactual-fairness.md) - a different, model-wide check with a different name and a different method.

### 4. The suggested change can still be indirectly discriminatory

A counterfactual that suggests "move to a different zip code" is technically actionable but not realistically so, and can smuggle a protected-attribute-adjacent proxy back into the advice given to the applicant.

## Related Concepts

* [Counterfactual Fairness](counterfactual-fairness.md) - the fairness *definition* this explainer is explicitly not about, despite the shared name.
* [What Are SHAP Values?](shap-values.md) and [What Is LIME?](lime.md) - the two feature-attribution explainability methods this one is offered as a third alternative to.
* [Protected Attribute](protected-attribute.md) - why an actionable-feature constraint has to exclude these by definition.

## Related Projects in This Repo

* [`German Credit Lending/`](../German%20Credit%20Lending/) - the audit used for the counterfactual-search example above.

## Further Reading

* [Wachter, S., Mittelstadt, B., Russell, C. (2017): Counterfactual Explanations Without Opening the Black Box](https://arxiv.org/abs/1711.00399) - the paper that introduced counterfactual explanations as a GDPR-motivated alternative to feature-attribution methods.
* [Mothilal, R. K., Sharma, A., Tan, C. (2020): Explaining Machine Learning Classifiers through Diverse Counterfactual Explanations](https://arxiv.org/abs/1905.07697) - the paper behind the `dice-ml` package, addressing the "multiple valid counterfactuals" limitation directly.
* [Verma, S. et al. (2020): Counterfactual Explanations for Machine Learning: A Review](https://arxiv.org/abs/2010.10596) - a survey of the actionability and realism constraints real counterfactual-explanation methods use.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
