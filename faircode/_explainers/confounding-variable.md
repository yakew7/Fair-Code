# Explainer: What Is a Confounding Variable?

> *The hidden cause that makes two things look connected when neither caused the other - and the reason removing a protected attribute from a model rarely removes the bias it produces.*

---

## The One-Sentence Definition

**A confounding variable** is a third variable that independently causes both an input feature and an outcome, creating a spurious statistical association between them that persists - and can dominate a model - even after the protected attribute is removed.

---

## Why It Matters

A model can appear to make a perfectly legitimate prediction - custody history predicts recidivism, healthcare cost predicts medical need, zip code predicts creditworthiness - while all of it is driven by a confounder the model never directly touches. When that confounder correlates with a protected attribute, the model inherits the discrimination and produces biased outcomes without ever using race, sex, or age explicitly.

Confounding is the mechanism behind some of the most consequential algorithmic bias failures on record. COMPAS assigned higher risk scores to Black defendants partly because `CustodyStatus` - a feature treated as a legitimate predictor of recidivism - correlates with both race (due to historical over-policing) and the recidivism label (due to differential surveillance). The pattern was statistically real. Its interpretation as a measure of individual risk was not.

This matters in practice:

- **Auditors** who check only feature importance will see `CustodyStatus` ranked highly and conclude it is a legitimate predictor. It predicts the label - but only because it encodes race and differential surveillance, not individual propensity.
- **Engineers** who drop the protected attribute will see no improvement because the confounding path runs through `CustodyStatus`, which stays in the feature set.
- **Courts** that accept statistical association as proof of predictive validity are accepting a spurious correlation as a fairness defense.

---

## Confounders vs. Proxy Variables: The Key Distinction

These two concepts are routinely conflated. They are not the same.

| | Proxy Variable | Confounding Variable |
|---|---|---|
| **Mechanism** | Encodes the protected attribute as a feature | Independently causes both the feature and the outcome |
| **Causal direction** | Protected attribute → proxy → prediction | Confounder → feature AND confounder → outcome |
| **Fix** | Remove the proxy | Remove or statistically adjust for the confounder |
| **Example in this repo** | `zip_code` encodes race | Over-policing causes elevated `CustodyStatus` AND inflated recidivism labels for Black defendants |

A proxy smuggles the protected attribute into the model through a correlated feature. A confounder creates a real statistical association between a feature and an outcome - but one that is entirely or partly driven by a third variable, not by the feature itself.

In practice, the same variable often plays both roles simultaneously. `CustodyStatus` in COMPAS is a proxy (it correlates with race) and a confounder (over-policing independently elevated custody records and generated more surveillance-driven recidivism labels). Treating it as only one or the other misses half the problem.

---

## Concrete Example: COMPAS and CustodyStatus

The COMPAS audit in this repo trains a Random Forest to predict recidivism. The biased model's Black/White fairness gap - the percentage-point difference in defendants flagged as high risk - is **86.77%**.

The standard naive fix is to drop `race`:

```python
# unfair.py: features include race + CustodyStatus + priors_count + charge_degree + age
# Black/White fairness gap: 86.77%

# Drop race only, retrain:
features_no_race = ['age', 'priors_count', 'CustodyStatus', 'charge_degree']
# Black/White fairness gap: still ~84% - dropping race alone changes almost nothing
```

The reason: `race` was not the direct driver. The confounding path runs through `CustodyStatus`:

```
Over-policing (systemic) ──→ CustodyStatus (elevated for Black defendants)
                         ──→ Recidivism label (inflated by differential surveillance)
```

Both arrows are caused by the same systemic factor. `CustodyStatus` is associated with the recidivism label not because custody history is a reliable individual risk signal, but because the same structural forces that produce elevated custody records also produce more recidivism label events - through monitoring, not through behavior.

Removing both `race` and `CustodyStatus` breaks this path:

```python
# fair.py: features include only priors_count + charge_degree + age
# Black/White fairness gap: 15.69% - 82% reduction
```

The residual 15.69% reflects other confounding paths (differential bail rates, charge severity distributions, surveillance-driven label noise) that require changes upstream of the model to eliminate entirely.

---

## Detection Code

The standard statistical approach is stratified analysis: check whether the association between a feature and the outcome disappears or reverses within strata of the confounder. A marginal association that weakens substantially after stratification is the signature of confounding - known in extreme cases as Simpson's Paradox.

```python
import pandas as pd
from scipy.stats import chi2_contingency


def check_confounding(df, feature_col, outcome_col, confounder_col, protected_col=None):
    """
    Test whether a candidate confounder explains the association
    between a feature and an outcome.

    Steps:
    1. Compute the marginal association (feature vs. outcome, ignoring confounder).
    2. Compute stratified associations (feature vs. outcome within each confounder level).
    3. Optionally test whether the confounder associates with a protected attribute.

    A large marginal chi-squared that shrinks or disappears within strata
    indicates confounding. A large confounder-vs-protected chi-squared confirms
    the confounder is a vector for protected-attribute bias.

    df             : DataFrame with all relevant columns
    feature_col    : candidate predictor feature
    outcome_col    : model prediction or ground-truth label
    confounder_col : variable suspected of confounding the feature→outcome path
    protected_col  : protected attribute to check for confounder correlation (optional)
    """
    results = {}

    # Step 1 - marginal association
    ct_marginal = pd.crosstab(df[feature_col], df[outcome_col])
    chi2_m, p_m, _, _ = chi2_contingency(ct_marginal)
    results["marginal"] = {
        "chi2": round(chi2_m, 3),
        "p_value": round(p_m, 4),
        "associated": p_m < 0.05,
    }

    # Step 2 - stratified associations
    strata = {}
    for level, group in df.groupby(confounder_col):
        ct = pd.crosstab(group[feature_col], group[outcome_col])
        if ct.shape[0] > 1 and ct.shape[1] > 1:
            chi2_s, p_s, _, _ = chi2_contingency(ct)
            strata[level] = {
                "chi2": round(chi2_s, 3),
                "p_value": round(p_s, 4),
                "associated": p_s < 0.05,
                "n": len(group),
            }
    results["stratified"] = strata

    # Step 3 - confounder vs. protected attribute (optional)
    if protected_col:
        ct_prot = pd.crosstab(df[confounder_col], df[protected_col])
        chi2_p, p_p, _, _ = chi2_contingency(ct_prot)
        results["confounder_vs_protected"] = {
            "chi2": round(chi2_p, 3),
            "p_value": round(p_p, 4),
            "associated": p_p < 0.05,
        }

    return results
```

### Applying it to the COMPAS audit

```python
# Load the COMPAS dataset and generate predictions from unfair.py
# (compas-scores-raw.csv has no raw `race` column - race_binary is derived
# from Ethnic_Code_Text, exactly as unfair.py does)
result = check_confounding(
    df=df,
    feature_col="race_binary",       # the raw racial disparity in predictions
    outcome_col="prediction",        # model's high-risk flag
    confounder_col="CustodyStatus",  # suspected confounder
    protected_col="race_binary",     # confirms CustodyStatus itself correlates with race
)

print(result["marginal"])
# {'chi2': 2439.482, 'p_value': 0.0, 'associated': True}
# Strong marginal association - race predicts the model's high-risk flag.

print(result["confounder_vs_protected"])
# {'chi2': 67.491, 'p_value': 0.0, 'associated': True}
# CustodyStatus is also strongly associated with race.
# Both arms of the confounding path are confirmed.

# Within every CustodyStatus stratum (Jail Inmate, Pretrial Defendant,
# Probation), the race -> prediction association is still large and
# significant (chi2 ranging ~328-1308, vs. 2439 marginally) - attenuated,
# but not eliminated. CustodyStatus explains part of the marginal
# association, not all of it, which is exactly why dropping race and
# CustodyStatus together still leaves a residual 15.69% gap rather than
# closing it to zero.
```

For continuous features, replace `chi2_contingency` with a Pearson correlation or partial correlation controlling for the confounder.

---

## Limitations

1. **Stratified analysis cannot distinguish confounding from effect modification.** If a feature has a genuinely different causal effect on the outcome across strata - not just a different baseline - that is effect modification, not confounding. The two require different handling. Conflating them produces wrong adjustments.

2. **You can only condition on observed confounders.** If the confounder is unmeasured - historical policing intensity, neighbourhood-level surveillance, differential healthcare access - no statistical adjustment removes its effect. Causal inference methods (instrumental variables, propensity score matching, difference-in-differences) can partially address unmeasured confounding but require strong, often untestable assumptions about the causal structure.

3. **Conditioning on a collider opens new bias.** A collider is a variable caused by both the feature and the outcome - the reverse of a confounder. Controlling for a collider introduces a spurious association rather than removing one. Correctly distinguishing confounders from colliders requires a causal graph (a DAG), not statistical testing alone. Chi-squared tests cannot tell you which direction the arrows point.

4. **Confounder removal reduces but does not eliminate bias.** Removing `CustodyStatus` from COMPAS cuts the fairness gap from 86.77% to 15.69% - an 82% reduction. The remaining gap reflects additional confounding paths that cannot be closed by feature removal without changing the label generation process itself.

5. **Adjustment can introduce its own distortions.** Propensity score methods and inverse probability weighting reduce confounding but amplify variance, especially in small subgroups. In high-stakes settings, an overcorrected model may perform worse for the groups it was adjusted to protect.

---

## Related Concepts

### Proxy Variables
A proxy variable directly encodes a protected attribute as a feature; a confounder independently causes both the feature and the outcome. In practice, the same variable can act as both simultaneously - as `CustodyStatus` does in COMPAS. Identifying which role dominates determines the correct mitigation strategy. See [proxy-variables.md](proxy-variables.md).

### Counterfactual Fairness
Counterfactual fairness asks whether a model's decision would change if the protected attribute changed, holding everything else constant. Confounders make this question structurally hard: if `CustodyStatus` is partly caused by race (via systemic over-policing), you cannot change race while holding `CustodyStatus` fixed - the two are causally entangled. Answering counterfactual questions correctly requires a full causal graph. See [counterfactual-fairness.md](counterfactual-fairness.md).

### Disparate Impact
Disparate impact measures unequal selection rates across groups. Confounding is one of the primary mechanisms that generates disparate impact even without explicit use of the protected attribute: the confounder drives both the feature and the outcome, and the association carries the protected-attribute signal forward. Removing the protected attribute while leaving confounders in place leaves the disparate impact intact. See [disparate-impact.md](disparate-impact.md).

### Feedback Loop Bias
When a confounded model is deployed and its outputs influence future labels - recidivism surveillance, credit monitoring, healthcare resource allocation - the confounding strengthens across retraining cycles. The model's outputs become part of the data-generating process, reinforcing the spurious association with each iteration. See [feedback-loop-bias.md](feedback-loop-bias.md).

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - the primary worked example. `CustodyStatus` confounds the race→recidivism path, driving 82% of the Black/White fairness gap. Removing it alongside `race` reduces the gap from 86.77% to 15.69%.
- [`Benefits Denial/`](../Benefits%20Denial/) - `relationship` and `marital-status` act as confounders for sex: historical gender norms independently elevated male-coded relationship statuses and income levels in the census data, creating a spurious association the model amplifies.
- [`Healthcare Readmission/`](../Healthcare%20Readmission/) - `payer_code` is confounded by race: differential insurance access is caused by structural factors that also independently predict readmission risk, not only by individual health status.

---

## Further Reading

- [Pearl, J. (2009). *Causality: Models, Reasoning and Inference* (2nd ed.). Cambridge University Press.](https://doi.org/10.1017/CBO9780511803161) - the foundational text on causal graphs, the do-calculus, and the formal definitions of confounders, mediators, and colliders that underpin modern causal fairness work.
- [Obermeyer, Z., Powers, B., Vogeli, C., & Mullainathan, S. (2019). Dissecting racial bias in an algorithm used to manage the health of populations. *Science*, 366(6464), 447–453.](https://doi.org/10.1126/science.aax2342) - a documented case of confounding-driven racial bias: healthcare cost (the proxy label) was confounded by differential access, making Black patients appear healthier than white patients with the same conditions, and the algorithm allocated less care as a result.
- [VanderWeele, T. J., & Shpitser, I. (2013). On the definition of a confounder. *Annals of Statistics*, 41(1), 196–220.](https://doi.org/10.1214/12-AOS1058) - a rigorous definition of confounding that distinguishes it from colliders and mediators, resolving long-standing disagreements in the epidemiological and statistical literature that carry directly into algorithmic fairness auditing.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
