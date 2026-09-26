# Explainer: What is Disparate Impact (The 80% Rule)?

> *The legal test that has decided employment discrimination cases in US courtrooms since 1971 - and the simplest fairness check you can run on any hiring model.*

---

## The One-Sentence Definition

**Disparate Impact** is a legal and statistical test that flags a selection process as discriminatory when the selection rate for a protected group (women, racial minorities, applicants over 40, etc.) is **less than 80% of the selection rate for the most-selected group**.

That 80% threshold is called the **Four-Fifths Rule** - codified in the U.S. Equal Employment Opportunity Commission's [Uniform Guidelines on Employee Selection Procedures (1978), 29 CFR §1607.4(D)](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XIV/part-1607).

---

## Why This Matters

Most fairness metrics are abstract. The 80% rule is not. It is the actual threshold the EEOC, federal courts, and the Department of Labor use to decide whether to investigate an employer for discriminatory hiring, promotion, or firing.

If your model selects men at 80% and women at 60%, the ratio is 60 / 80 = **0.75**. Below 0.80. The selection process can be challenged as discriminatory under *Griggs v. Duke Power Co.*, 401 U.S. 424 (1971) - the Supreme Court case that established the disparate-impact doctrine even when there is **no proof of intent** to discriminate.

This is the rule that matters in practice:

- HR teams use it to screen vendor hiring tools before deployment
- Auditors use it to flag protected-class disparities for further investigation
- Plaintiffs use it as the *prima facie* evidence threshold in Title VII employment-discrimination lawsuits
- Procurement teams use it as a contractual acceptance criterion for AI screening products

A model can have 95% accuracy and still fail the 80% rule. Accuracy says nothing about who is being filtered out at the gate.

---

## Real-World Proof: AI Fair Recruitment Audit

The [`AI Fair Recruitment`](../AI%20Fair%20Recruitment/) audit in this repo trains a Random Forest classifier on a recruitment dataset with gender, age, experience, and technical test scores. Apply the 80% rule directly to its outputs:

### Biased Model - [`unfair.py`](../AI%20Fair%20Recruitment/unfair.py)

The dataset's `Gender` column has three values, not two - Male, Female, and Other. The Four-Fifths Rule compares *every* group's selection rate against the highest, not just whichever two look most convenient to compare:

| Group | Hire Rate |
|---|---:|
| Men | 21.62% |
| Women | 17.59% |
| Other | 13.40% |

**Disparate Impact Ratio = 13.40 / 21.62 = 0.620** (lowest rate ÷ highest rate, across all three groups - not just Men vs. Women)

**0.620 < 0.80 → FAILS the Four-Fifths Rule.**

Stopping at a Men-vs-Women comparison alone would understate the problem: that pair alone gives 17.59 / 21.62 = 0.81, just above the 0.80 line - a "pass" that hides the fact that the Other group is actually the most disadvantaged of the three, well below the threshold. A real EEOC complaint filed against this model would survive the *prima facie* stage. The employer would then bear the burden of proving the selection process is "job-related and consistent with business necessity" - the legal standard set in *Griggs* and codified in 42 U.S.C. §2000e-2(k).

### Mitigated Model - [`fair.py`](../AI%20Fair%20Recruitment/fair.py)

After dropping `Gender` and `Age` and retraining on `Experience_Years` and `Technical_Test_Score` only:

| Group | Hire Rate |
|---|---:|
| Men | 11.48% |
| Women | 11.32% |
| Other | 11.62% |

**Disparate Impact Ratio = 11.32 / 11.62 = 0.974** (lowest ÷ highest, across all three groups)

**0.974 ≥ 0.80 → PASSES the Four-Fifths Rule** - for every group, not just the two that happened to fail before.

The legal exposure is gone, and the model is selecting candidates on demonstrated ability rather than inferred demographic signal.

---

## How to Calculate It in Python

The 80% rule is one of the cheapest fairness checks you can run. No external library required.

```python
import pandas as pd

def disparate_impact_ratio(df, prediction_col, group_col, positive_label=1):
    """
    Compute the Four-Fifths Rule ratio: (lowest selection rate) / (highest selection rate).

    Returns the ratio and a pass/fail flag against the 0.80 threshold.

    df              : DataFrame with predictions and group membership
    prediction_col  : column holding the model's positive/negative decision
    group_col       : column holding the protected attribute (e.g. 'Gender')
    positive_label  : the value in prediction_col that counts as "selected" (default 1)
    """
    selection_rates = (
        df.assign(_selected=(df[prediction_col] == positive_label).astype(int))
          .groupby(group_col)["_selected"]
          .mean()
    )

    ratio = selection_rates.min() / selection_rates.max()
    passes = ratio >= 0.80

    return {
        "selection_rates": selection_rates.to_dict(),
        "disparate_impact_ratio": round(ratio, 3),
        "passes_four_fifths_rule": bool(passes),
    }
```

### Applying it to the hiring audit

Drop this into `AI Fair Recruitment/unfair.py` right after the predictions are generated:

```python
test_results["Gender"] = df.loc[X_test.index, "Gender"].values

result = disparate_impact_ratio(
    df=test_results,
    prediction_col="prediction",
    group_col="Gender",
    positive_label=1,
)

print(result)
# {
#   'selection_rates': {'Female': 0.1759, 'Male': 0.2162, 'Other': 0.1340},
#   'disparate_impact_ratio': 0.62,
#   'passes_four_fifths_rule': False
# }
# Note: this dataset's real Gender column has 3 values (Male/Female/Other),
# not just 2 - grouping by the raw column pulls in all three, giving a lower
# ratio (Other's rate vs Male's) than the Male/Female-only figure quoted
# above, which comes from unfair.py's own two-way "male_col" dummy split.
```

Run the same snippet against `fair.py` and the ratio climbs to **0.989** - passing.

### Using Fairlearn

The same metric is available out-of-the-box in [Fairlearn](https://fairlearn.org/):

```python
from fairlearn.metrics import demographic_parity_ratio

ratio = demographic_parity_ratio(
    y_true=y_test,
    y_pred=model.predict(X_test),
    sensitive_features=df.loc[X_test.index, "Gender"],
)

print(f"DI ratio: {ratio:.3f}  |  passes 80% rule: {ratio >= 0.80}")
```

`demographic_parity_ratio` is mathematically identical to the Four-Fifths Rule ratio - `min(rate) / max(rate)` across groups.

---

## The Math

For a protected attribute `A` taking values `a` (disadvantaged) and `b` (advantaged):

**Selection rate for group g:**

P(Ŷ = 1 | A = g)

**Disparate Impact Ratio:**

DI = P(Ŷ = 1 | A = a) / P(Ŷ = 1 | A = b)

where `a` is the group with the *lower* selection rate.

**Four-Fifths Rule:**

DI ≥ 0.80  →  no disparate impact flag
DI < 0.80  →  disparate impact flag (legal scrutiny applies)

Where:

- Ŷ = model decision (hire / no hire, approve / deny, etc.)
- A = protected attribute (gender, race, age class, etc.)

The rule is symmetric - you always divide the smaller rate by the larger rate, so the ratio sits in [0, 1].

---

## Limitations / Trade-offs

The 80% rule is a legal screen, not a complete fairness audit. Treat it as a floor, not a ceiling.

### It is a threshold, not a guarantee

A model with a ratio of 0.81 passes the rule and a model at 0.79 fails it, but the real-world disparity is essentially identical. Courts treat the 80% line as a heuristic for triggering further investigation, not as a bright-line proof of fairness. The EEOC's own guidelines warn that "smaller differences in selection rate may nevertheless constitute adverse impact" when the sample size is large.

### It ignores error types

Disparate Impact only measures *who gets selected*. It says nothing about *who got selected wrongly*. A model that hires equal proportions of men and women - but among those rejected, disproportionately rejects qualified women - passes the 80% rule and still discriminates. [Equalized Odds](equalized-odds.md) is the metric that catches that.

### It is satisfiable by lowering the bar

You can pass the 80% rule by hiring everyone, or by hiring no one. Neither is fairness. The rule must be paired with a job-relatedness analysis: the selection process must still be predictive of actual performance. *Griggs v. Duke Power* and §2000e-2(k) both require this - passing the 80% rule does not exempt the employer from showing the process is "job-related and consistent with business necessity."

### It conflicts with Equalized Odds when base rates differ

If qualification rates genuinely differ across groups in the underlying population, enforcing equal selection rates can require selecting unqualified members of the lower-rate group - or rejecting qualified members of the higher-rate group. This is the same impossibility result that governs Equalized Odds and calibration: when base rates differ, no model can satisfy every fairness definition at once. See [Chouldechova (2017)](https://arxiv.org/abs/1703.00056).

### Proxy variables defeat it

Dropping the protected attribute is not enough. If `zip_code`, `employment_tenure`, or `CustodyStatus` correlate with the protected attribute, the model will reconstruct the bias from those proxies and the disparate-impact ratio will stay below 0.80. The Four-Fifths Rule tells you the model is biased; it does not tell you *which feature* is causing it. See the [proxy variables explainer](proxy-variables.md).

---

## The Bigger Picture

The 80% rule is one of the few places where civil-rights law, statistics, and machine learning all agree on the same number. It was written in 1978 for paper-and-pen hiring tests; it applies word-for-word to a Random Forest classifier in 2026.

That is what makes it useful as a deployment check: it is not a research metric. It is the metric that triggers an EEOC investigation, that survives the motion-to-dismiss stage of a Title VII lawsuit, and that procurement teams put in vendor contracts. If your hiring model fails it, you do not need a fairness expert to explain why that is a problem - the law has already explained it for you.

**Run the 80% rule against every classifier that decides who gets a job, a loan, a lease, or an insurance policy. If it fails, you have a legal problem before you have a technical one.**

---

## Related Concepts

### Demographic Parity

Demographic Parity is the academic name for the same idea: equal positive prediction rates across groups. The 80% rule is its legal-threshold version. A model that achieves Demographic Parity automatically passes the Four-Fifths Rule. The reverse is not true - a model can pass the 80% rule with a ratio of 0.81 and still have a real disparity worth fixing.

### Equalized Odds

Equalized Odds checks equal *error rates* - true positives and false positives - across groups. Disparate Impact checks equal *selection rates*. These are different metrics and can conflict. A model can pass one and fail the other. See the [equalized-odds explainer](equalized-odds.md).

### Proxy Variables

Removing the protected attribute does not automatically fix disparate impact. Features that correlate with the protected attribute will reconstruct the bias. The COMPAS audit's `CustodyStatus` and the German Credit audit's `employment` tenure are both worked examples. See the [proxy-variables explainer](proxy-variables.md).

### Business Necessity Defense

Under Title VII, an employer that fails the 80% rule can still defend its selection process by proving it is "job-related and consistent with business necessity." This is the legal counterweight to the Four-Fifths Rule and the reason the rule alone is not a complete fairness standard - courts weigh the disparity against the predictive validity of the selection process.

---

## Related Projects in This Repo

- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - the hiring audit this explainer is grounded in. Biased model fails the 80% rule (0.620, across all three Gender groups); mitigated model passes (0.974).
- [`COMPAS/`](../COMPAS/) - same rule applied to criminal risk scoring. The biased COMPAS model has a Black-vs-White high-risk-flag ratio of 0.40 / 87.16 ≈ 0.005 - a catastrophic Four-Fifths Rule failure.
- [`German Credit Lending/`](../German%20Credit%20Lending/) - same rule applied to credit decisions. Useful contrast: the gap is smaller (7.16 pp) but still legally relevant under the Equal Credit Opportunity Act, which adopts a similar disparate-impact analysis.
- [`explainers/equalized-odds.md`](equalized-odds.md) - the error-rate counterpart to selection-rate fairness
- [`explainers/proxy-variables.md`](proxy-variables.md) - why models keep failing the 80% rule even after you drop the protected attribute

---

## Further Reading

- [EEOC Uniform Guidelines on Employee Selection Procedures, 29 CFR Part 1607](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XIV/part-1607) - the source text of the Four-Fifths Rule (§1607.4(D))
- [*Griggs v. Duke Power Co.*, 401 U.S. 424 (1971)](https://supreme.justia.com/cases/federal/us/401/424/) - the Supreme Court case establishing the disparate-impact doctrine
- [Barocas & Selbst (2016): *Big Data's Disparate Impact*, 104 Calif. L. Rev. 671](https://www.californialawreview.org/print/2-big-datas-disparate-impact) - how the Four-Fifths Rule applies to algorithmic decision-making
- [Chouldechova (2017): *Fair Prediction with Disparate Impact*](https://arxiv.org/abs/1703.00056) - the impossibility result connecting disparate impact, calibration, and equalized odds
- [Fairlearn: `demographic_parity_ratio`](https://fairlearn.org/main/user_guide/assessment/common_fairness_metrics.html) - the library implementation used in the code snippet above

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
