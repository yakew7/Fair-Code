> *"The algorithm is just math" is the most dangerous sentence in AI - because math trained on biased history produces biased math, and the bias arrives wearing a lab coat.*

## The One-Sentence Definition

The **AI objectivity myth** is the false belief that because a model's decisions come from numbers and statistics rather than human judgment, those decisions are neutral, unbiased, and free of the prejudices that affect human decision-makers.

## Why It Matters

This myth is why biased systems survive contact with the public. A loan officer who denies Black applicants at twice the rate of white applicants with identical financial profiles would face a discrimination lawsuit. A model that does the exact same thing gets described as "data-driven" and "removing human bias from the loop." The math doesn't make the outcome any less discriminatory - it just makes it harder to challenge, because "the computer said so" sounds like a fact rather than a decision.

The myth breaks the standard defense people reach for first: "we didn't tell it to discriminate, so it can't be discriminating." That defense assumes bias requires intent. It doesn't. A Random Forest Classifier has no intent at all - it just finds whatever patterns minimize prediction error on the training data. If the training data encodes a history of unequal policing, unequal lending, or unequal healthcare access, the model will faithfully learn that history and apply it forward. Objectivity isn't a property the model starts with. It's a property someone has to build in, audit for, and prove.

## Where the Myth Comes From

The myth has three load-bearing assumptions, and every audit in this repo breaks at least one of them.

### 1. "It's just statistics, and statistics don't have opinions"

Statistics describe whatever data you feed them. If the data itself reflects a biased world - more policing in some neighborhoods, fewer approved loans to some groups historically, different diagnostic follow-up by demographic - the statistics will describe that bias accurately. Accurate description of a biased world is not the same as a fair decision rule for that world. See [label-bias.md](label-bias.md) for how this plays out when the "ground truth" labels themselves are the product of biased human decisions.

### 2. "We removed the protected attribute, so it can't use it"

This is the single most common justification, and it's the one Fair Code exists to disprove. Every audit in this repo starts here. Dropping `race` or `gender` or `age` from the feature list does nothing if other columns - `CustodyStatus`, `employment` tenure, `payer_code`, `occupation` - carry the same signal through a side door. See [proxy-variables.md](proxy-variables.md) and [proxy-entanglement.md](proxy-entanglement.md) for the mechanics.

### 3. "High accuracy means the model is correct"

A model can be 99% accurate on its test set and still be wrong in exactly the cases that matter most - the ones involving the population it was never properly trained on, or the ones where "accurate" was measured against biased labels in the first place. Accuracy answers "does the model match the data?" It does not answer "is the data, or the decision rule, fair?" Those are different questions, and the objectivity myth conflates them.

## Concrete Example: COMPAS - Audit 01

COMPAS is used across 46 US states to score a defendant's likelihood of reoffending, and judges use that score in bail, sentencing, and parole decisions. It is presented to courts as a neutral, statistically validated risk tool - the textbook case of the objectivity myth in production.

The biased model (`unfair.py`), trained with race included, produced a "High Risk" classification rate of 86.77% for one group versus 0.4% for another - an 86.77% percentage-point fairness gap on a tool actively informing custody decisions for over a million people a year.

```python
# unfair.py - race_binary included as a direct feature
# (compas-scores-raw.csv has no raw `race` column - race_binary is
# derived from Ethnic_Code_Text, exactly as unfair.py does)
features = ['Sex_Code_Text', 'race_binary', 'CustodyStatus', 'MaritalStatus']
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
# Fairness Gap: 86.77%
```

Removing `race_binary` alone takes the gap from 86.77pp down to 18.38pp - a real, large drop, not a "barely moves" story. `CustodyStatus` does correlate with race (communities that were over-policed historically generate more "custody status" records today, independent of actual reoffense risk), but its own marginal contribution on top of race is only about 2.7 points: dropping `race_binary` *and* `CustodyStatus` together reaches 15.69%, an 82% reduction overall. The model was never neutral. It was a faithful record of an unequal criminal justice system, expressed as a probability - and most of that record ran through race directly, not through a single proxy standing in for it.

## Detection Code

This function checks whether a model's outcome rates differ across protected groups by more than a configurable threshold, and flags features that correlate with the protected attribute strongly enough to explain the gap on their own.

```python
import pandas as pd
from scipy.stats import chi2_contingency, pearsonr

def audit_objectivity_claim(df, predictions_col, protected_col, threshold=0.05):
    """
    Checks whether a model's positive prediction rate differs
    across groups in `protected_col` by more than `threshold`.

    Parameters:
        df: DataFrame containing predictions and protected attribute
        predictions_col: column name of the model's binary output (0/1)
        protected_col: column name of the protected attribute
        threshold: maximum acceptable gap in positive prediction rates

    Returns:
        dict with the rate per group, the gap, and a pass/fail flag
    """
    rates = df.groupby(protected_col)[predictions_col].mean()
    gap = rates.max() - rates.min()
    return {
        "rates_by_group": rates.round(4).to_dict(),
        "fairness_gap": round(gap, 4),
        "claim_holds": gap <= threshold,
    }


def find_features_explaining_gap(df, protected_col, candidate_cols, p_threshold=0.05):
    """
    Flags candidate features that correlate with the protected
    attribute strongly enough to act as a proxy - i.e. features
    that could reproduce a "fairness gap" even if the protected
    attribute itself is removed.

    Parameters:
        df: DataFrame containing the protected attribute and candidates
        protected_col: column name of the protected attribute
        candidate_cols: list of feature names to test
        p_threshold: significance level for flagging a proxy

    Returns:
        list of (feature, p_value) tuples for flagged proxies
    """
    flagged = []
    for col in candidate_cols:
        if pd.api.types.is_numeric_dtype(df[col]) and df[protected_col].nunique() <= 2:
            corr, p = pearsonr(df[col], df[protected_col].astype("category").cat.codes)
        else:
            table = pd.crosstab(df[col], df[protected_col])
            _, p, _, _ = chi2_contingency(table)
        if p < p_threshold:
            flagged.append((col, round(p, 5)))
    return flagged


# Usage example
# audit_objectivity_claim(df, "predicted_high_risk", "race_binary")
# find_features_explaining_gap(df, "race_binary", ["CustodyStatus", "MaritalStatus", "Sex_Code_Text"])
```

## Limitations and Trade-offs

### 1. A passing audit is a snapshot, not a guarantee

Demonstrating that a model's outcome rates are close across groups today says nothing about tomorrow. Retraining on new data, a shift in the applicant or defendant population, or a change in how an upstream system labels its inputs can reopen a gap that was previously closed. See [distribution-shift.md](distribution-shift.md).

### 2. "Objective" and "explainable" are not the same thing

A model can produce numerically identical outcome rates across groups while still being a black box about *why* it reached any individual decision. Demographic parity at the aggregate level does not mean any single person can get a meaningful answer to "why was I denied?" That's a separate problem - see [shap-values.md](shap-values.md).

### 3. Removing the myth doesn't remove the trade-off

Even a model that has been correctly audited and stripped of protected attributes and known proxies still has to choose *which* fairness definition to satisfy, and [fairness-metric-conflicts.md](fairness-metric-conflicts.md) shows that several of the most common definitions are mathematically impossible to satisfy all at once. "We fixed the objectivity problem" can quietly become "we picked one fairness metric and stopped checking the others."

### 4. The myth can survive the audit, just relocated

Even after a model is shown not to be objective, the institutional response is often to treat the *next* model as objective by default, restarting the same cycle. Calling out the myth once does not install permanent skepticism - it has to be re-applied to every new system, every retraining cycle, and every vendor claim of "AI-powered, bias-free decisioning."

## Related Concepts

* [What Is Machine Learning Bias?](ml-bias.md) - the four entry points (data, labels, proxies, feedback loops) through which the "neutral" model absorbs bias in the first place.
* [What Is a Proxy Variable?](proxy-variables.md) - the specific mechanism behind "we removed the protected attribute, so it's fine."
* [What Is Label Bias?](label-bias.md) - why the "ground truth" a model is trained to match is itself a human judgment, not a fact.
* [How Does AI Detect Patterns?](how-ai-detects-patterns.md) - the mechanical reason a Random Forest cannot tell a causal pattern from a discriminatory one.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the highest-profile example of a "neutral risk score" actively used in court decisions, with an 86.77% fairness gap before mitigation.
* [`Benefits Denial/`](../Benefits%20Denial/) - a welfare eligibility model where "objective" income and household features encode sex, race, and national origin simultaneously.
* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - clinical "risk scores" that look like medicine but encode insurance access and discharge-destination disparities.

## Further Reading

* [O'Neil, C. (2016): Weapons of Math Destruction](https://www.penguinrandomhouse.com/books/241363/weapons-of-math-destruction-by-cathy-oneil/) - the foundational case for why "it's just an algorithm" is not a defense, with examples spanning credit, employment, and criminal justice.
* [Angwin, J. et al. (2016): Machine Bias, ProPublica](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the original investigation showing COMPAS scores were presented as objective risk assessments while producing racially disparate outcomes.
* [Barocas, S., Hardt, M., & Narayanan, A.: *Fairness and Machine Learning* (fairmlbook.org)](https://fairmlbook.org) - the standard reference for why statistical models trained on historical data inherit the properties of that history, including its inequities.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
