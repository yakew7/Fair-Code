# Explainer: What is Counterfactual Fairness?

> *Group fairness asks whether outcomes are equal across populations. Individual fairness asks whether similar people are treated similarly. Counterfactual fairness asks something more precise: would this person's outcome have been different if they had been born into a different demographic group?*

---

## The One-Sentence Definition

**Counterfactual Fairness** is a causal fairness criterion that requires a model to produce the same prediction for an individual in the real world as it would in a counterfactual world where that individual belongs to a different demographic group - with all causally independent factors held constant.

It was formalised by Kusner et al. (2017) as: *"a decision is fair towards an individual if it is the same in the actual world and in a counterfactual world where the individual belonged to a different demographic group."*

---

## Why This Matters

Every fairness metric discussed so far - Demographic Parity, Equalized Odds, Individual Fairness - is fundamentally observational. It asks: *across people we can see in the data, are outcomes distributed fairly?* These metrics operate on what happened. They cannot tell you whether the demographic attribute itself caused the outcome to be different.

This distinction matters enormously in practice. Consider a loan model that doesn't use race as a feature, but uses zip code. Zip code correlates strongly with race due to decades of redlining and residential segregation. A Black applicant living in a historically redlined neighbourhood receives a rejection. An observationally identical white applicant living in the same zip code would also be rejected - so individual fairness is technically satisfied. But ask the counterfactual question: *if this applicant had been white, and had therefore grown up in a different neighbourhood due to the same historical forces, would they have been rejected?* Almost certainly not.

Counterfactual fairness captures what observational methods miss: when a demographic attribute is a root cause in the causal graph, dropping it from the feature set is not enough. The downstream variables it caused - the proxies - still carry the signal. The model is still, in a causal sense, discriminating on the basis of race.

This is the precise problem counterfactual fairness is designed to detect and prevent.

---

## The Formal Definition

Counterfactual fairness is grounded in the language of causal models. The framework requires a **Structural Causal Model (SCM)** - a directed acyclic graph (DAG) that represents the causal relationships between variables.

Let:
- `A` be the protected attribute (e.g. race, sex)
- `X` be the observed features (e.g. zip code, credit history, income)
- `U` be the unobserved background variables (the individual's "circumstances" independent of `A`)
- `Ŷ` be the model's prediction

A predictor `Ŷ` is **counterfactually fair** if, for every individual and every value of the protected attribute `a'`:

```
P(Ŷ_{A←a}(U) = y | X = x, A = a) = P(Ŷ_{A←a'}(U) = y | X = x, A = a)
```

Plain English: the probability of prediction `y` for this individual is the same whether we set their group membership to `a` (the real world) or to `a'` (the counterfactual). The subscript notation `A←a'` means "intervene on A, setting it to a'", following do-calculus notation.

The critical term is `U` - the unobserved background variables. These represent everything about the person that is causally independent of their demographic group: their intrinsic ability, their choices given their circumstances, their effort. A counterfactually fair model makes predictions based only on `U` - the factors the person controls - not on `A` or on features that `A` caused.

**Three categories of features** emerge from the causal graph:

| Category | Relationship to A | Allowed in fair model? |
|----------|-------------------|----------------------|
| **Resolving variables** | Causally downstream of A, but a direct, legitimate part of the task | Sometimes - context-dependent |
| **Proxy variables** | Causally downstream of A, encoding demographic signal | No |
| **Non-descendants** | Causally independent of A | Yes |

The challenge is that you must know the causal graph to make these determinations. And causal graphs are not discovered - they are specified, based on domain knowledge and subject to disagreement.

---

## Concrete Example: COMPAS Recidivism

The [`COMPAS/`](../COMPAS/) audit in this repo is a direct illustration of counterfactual fairness violation - even without using the causal framework explicitly.

COMPAS assigns recidivism risk scores based on features including prior arrest count, age at first arrest, and custody status. The biased model produces:

| Group | High-Risk Flag Rate |
|-------|---------------|
| Black defendants | 87.16% |
| White defendants | 0.40% |
| **Fairness Gap** | **86.77pp** |

Now ask the counterfactual question. Take a Black defendant with 3 prior arrests. Ask: *if this person had been white, with the same underlying behaviour and the same 3 prior arrests, would their risk score be the same?*

The answer is no - and the reason is `CustodyStatus`, which the [proxy variables explainer](proxy-variables.md) identifies as the key proxy. Black communities have been subject to historical over-policing: for the same underlying behaviour, Black individuals are arrested at higher rates than white individuals. Prior arrest count is therefore not causally independent of race - it is partly *caused* by race, via differential policing. A model trained on prior arrests is therefore using a variable that race, in part, caused.

```
Race ──→ Policing intensity ──→ Arrest rate ──→ Prior arrests ──→ Risk score
```

`Prior arrests` is downstream of `Race` in the causal graph. A counterfactually fair model cannot use it directly - or must adjust for the part of the variance in prior arrests that race caused.

This is the structural explanation for why removing race from the COMPAS feature set did not remove the racial bias. The bias had already been absorbed into the features race caused.

---

## How to Detect It in Python

Exact counterfactual fairness requires a specified causal graph and is computationally involved. The practical audit below uses a tractable approximation: train a model, then simulate counterfactual individuals by flipping their protected attribute and re-deriving causally downstream features, and measure how often predictions change.

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# ── Synthetic dataset mimicking a lending scenario ──────────────────────────
# Race causes neighbourhood (via historical redlining).
# Neighbourhood affects credit score (via structural access to credit).
# We want a model that does NOT change its prediction when we flip race.

np.random.seed(42)
n = 3000

race = np.random.choice(['White', 'Black'], n, p=[0.6, 0.4])

# Neighbourhood quality score - causally downstream of race
neighbourhood = np.where(
    race == 'Black',
    np.random.normal(40, 12, n),   # historically redlined areas score lower
    np.random.normal(65, 12, n)
).clip(0, 100)

# Credit score - causally downstream of neighbourhood (structural access)
credit_score = (neighbourhood * 3 + np.random.normal(400, 50, n)).clip(300, 850)

# Income - causally independent of race in this synthetic model
income = np.random.normal(55000, 15000, n).clip(20000, 150000)

# Loan outcome - set to depend on credit and income (not race)
prob_approve = (
    (credit_score - 300) / 550 * 0.5 +
    (income - 20000) / 130000 * 0.5
)
approved = (np.random.rand(n) < prob_approve).astype(int)

df = pd.DataFrame({
    'race':          race,
    'neighbourhood': neighbourhood,
    'credit_score':  credit_score,
    'income':        income,
    'approved':      approved
})


# ── Train a model that includes the proxy (neighbourhood) ───────────────────
features_biased = ['neighbourhood', 'credit_score', 'income']
X = df[features_biased]
y = df['approved']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

test_df = df.loc[X_test.index].copy()
test_df['prediction'] = model.predict(X_test)


# ── Counterfactual fairness audit ────────────────────────────────────────────
# For each individual, construct a counterfactual version:
# flip their race, re-derive neighbourhood (the downstream proxy), keep income.
# If the model's prediction changes, that is a counterfactual fairness violation.

def counterfactual_neighbourhood(r):
    """Re-sample neighbourhood from the counterfactual group's distribution."""
    if r == 'Black':
        return np.random.normal(65, 12)   # counterfactual: born White
    else:
        return np.random.normal(40, 12)   # counterfactual: born Black

np.random.seed(0)
cf_df = test_df.copy()
cf_df['cf_neighbourhood'] = cf_df['race'].apply(counterfactual_neighbourhood).clip(0, 100)

# Re-derive credit score from counterfactual neighbourhood, keep personal income
cf_df['cf_credit_score'] = (
    cf_df['cf_neighbourhood'] * 3 + np.random.normal(400, 50, len(cf_df))
).clip(300, 850)

X_cf = cf_df[['cf_neighbourhood', 'cf_credit_score', 'income']].rename(
    columns={'cf_neighbourhood': 'neighbourhood', 'cf_credit_score': 'credit_score'}
)
cf_df['cf_prediction'] = model.predict(X_cf)

# Count violations: prediction changed under counterfactual race
violations = cf_df[cf_df['prediction'] != cf_df['cf_prediction']]

print("── COUNTERFACTUAL FAIRNESS AUDIT ──\n")
print(f"Total test records:               {len(cf_df)}")
print(f"Counterfactual violations:        {len(violations)}")
print(f"Violation rate:                   {len(violations)/len(cf_df)*100:.1f}%")
print()

# Break down violations by actual race
for race_group in ['White', 'Black']:
    group = violations[violations['race'] == race_group]
    total = len(cf_df[cf_df['race'] == race_group])
    print(f"  {race_group} applicants whose decision flips: {len(group)}/{total} ({len(group)/total*100:.1f}%)")

# ── Expected output ──────────────────────────────────────────────────────────
# ── COUNTERFACTUAL FAIRNESS AUDIT ──
#
# Total test records:               600
# Counterfactual violations:        214
# Violation rate:                   35.7%
#
#   White applicants whose decision flips: 87/356 (24.4%)
#   Black applicants whose decision flips: 127/244 (52.0%)
```

A 35.7% violation rate means more than one in three applicants would receive a different loan decision if they had been born into the other racial group - with everything causally independent (income, personal behaviour) held constant. This is the operational signature of a model that is, at the causal level, making race-based decisions.

### The fix: use only causally independent features

```python
# ── Train a counterfactually fair model ──────────────────────────────────────
# Drop neighbourhood and credit_score - both causally downstream of race.
# Keep only income, which is causally independent of race in this model.

features_fair = ['income']
X_fair = df[features_fair]
X_train_f, X_test_f, y_train_f, y_test_f = train_test_split(
    X_fair, y, test_size=0.2, random_state=42
)

model_fair = RandomForestClassifier(n_estimators=100, random_state=42)
model_fair.fit(X_train_f, y_train_f)

cf_df['prediction_fair'] = model_fair.predict(X_test_f)

# Re-run audit - counterfactual flipping race no longer changes income,
# so predictions are now stable across the counterfactual
cf_df['cf_prediction_fair'] = model_fair.predict(
    cf_df[['income']]
)

violations_fair = cf_df[cf_df['prediction_fair'] != cf_df['cf_prediction_fair']]
print(f"Fair model violation rate: {len(violations_fair)/len(cf_df)*100:.1f}%")
# Fair model violation rate: 0.0%
# - predictions are identical in the real and counterfactual worlds
```

---

## The Causal Graph Requirement

Counterfactual fairness has one non-negotiable prerequisite: you must specify a causal graph. This is not a limitation that can be engineered away - it is a feature of the framework, because the question it asks (*what would have happened?*) is inherently causal, not statistical.

In practice, the graph is specified from domain knowledge and documented assumptions. For the lending example above:

```
Race ──→ Neighbourhood ──→ Credit Score ──→ Approval
  │                                           ↑
  │                    Income ────────────────┘
  │                      ↑
  │              (causally independent of Race)
  └──────────────────────────────────────────────→ (direct path, must be blocked)
```

Building the causal graph requires asking: *for this specific domain, what causes what?* That is a normative and domain-expert question, not a data question. Different stakeholders may specify different graphs - and different graphs will identify different sets of variables as proxies. Documenting and justifying the graph is therefore as important as running the code.

---

## Limitations / Trade-offs

### It requires a causal graph - which may be wrong or contested

The entire framework is contingent on the correctness of the specified DAG. If the causal assumptions are wrong - if a variable is placed on the wrong side of a causal path - then the audit will certify as fair a model that isn't, or reject as unfair a model that is. There is no statistical test that can validate a causal graph from observational data alone. The graph encodes assumptions that must be justified externally.

### Causally independent features may themselves carry historical bias

Even features deemed causally independent of the protected attribute may still encode historical inequality. Income, in the example above, is modelled as independent of race - but in the real world, the racial wealth gap means income distributions differ significantly by race. A model trained on income alone may still produce demographically unequal outcomes. Counterfactual fairness permits this, because the disparity traces back to background variables `U`, not to the causal effect of `A`. Whether that is morally acceptable is a separate question the framework does not answer.

### It can conflict with group fairness metrics

A counterfactually fair model will often produce demographic outcome gaps, because groups have different distributions of causally independent features. If those differences are real - rooted in the background variables `U` - counterfactual fairness does not require equalising the outcomes. Demographic Parity does. The two metrics therefore directly conflict whenever base rates of causally independent features differ across groups. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

### Resolving variables require judgment calls

Some features are causally downstream of the protected attribute but are also direct, legitimate merit signals. A law school applicant's grades are causally affected by the quality of their secondary education, which is causally affected by their race via school funding disparities. Should grades be treated as a proxy and dropped? Or are they a legitimate signal of performance, even if partially shaped by structural inequality?

Kusner et al. call these **resolving variables** - features where the causal path from `A` is mediated by a legitimate process (individual effort, direct performance). There is no automatic rule. Whether to treat a variable as a proxy or a resolving variable is a normative judgment that requires explicit documentation and justification.

### Approximate audits have simulation variance

The practical audit above approximates counterfactual individuals by re-sampling downstream features from the counterfactual group's distribution. This introduces randomness and may not accurately reflect the true counterfactual. Structural causal models, fitted to data, produce more principled counterfactual simulations - but require stronger modelling assumptions and significantly more implementation effort.

---

## Individual Fairness vs. Counterfactual Fairness

These two criteria are closely related and are often confused. The distinction is important:

| | Individual Fairness | Counterfactual Fairness |
|---|---|---|
| **Question** | Are similar people treated similarly in the observed data? | Would the same person receive the same outcome in a world where they belong to a different group? |
| **Framework** | Observational - operates on the data as-is | Causal - requires a structural causal model |
| **Unit of analysis** | Pairs of individuals | The same individual across possible worlds |
| **What it requires** | A task-specific similarity metric `d(x, y)` | A causal DAG specifying which features are downstream of `A` |
| **What it catches** | Inconsistent treatment of matched pairs | Decisions whose causal ancestry runs through the protected attribute |
| **What it misses** | When the similarity metric is itself biased | When the causal graph is mis-specified |
| **Easier to compute?** | Yes - no causal model needed | No - requires DAG + counterfactual simulation |
| **Easier to interpret?** | Less intuitive | Highly intuitive - maps to how people reason about discrimination |

The two are complementary. Individual fairness is easier to audit empirically; counterfactual fairness provides the causal explanation for *why* individual fairness violations occur. A defendant who receives a different risk score than an identical defendant is an individual fairness violation. The reason it happens - because prior arrest count is causally downstream of race via differential policing - is a counterfactual fairness explanation.

---

## Related Concepts

### Individual Fairness

The closest sibling criterion. Individual fairness asks whether similar people receive similar treatment in the observed world; counterfactual fairness asks whether the same person would receive the same treatment in a different possible world. Both operate at the level of the individual rather than the group. See the [individual fairness explainer](individual-fairness.md).

### Proxy Variables

Proxy variables are the mechanism that creates counterfactual fairness violations: they are features causally downstream of the protected attribute that carry demographic signal into the model even after the protected attribute itself is removed. Identifying and removing proxies is the core repair strategy for both proxy bias and counterfactual fairness violations. See the [proxy variables explainer](proxy-variables.md).

### Disparate Treatment

Disparate treatment occurs when the protected attribute is a direct model input. It is the simplest counterfactual fairness violation: the causal path from `A` to `Ŷ` runs directly, not through intermediate features. See the [disparate treatment explainer](disparate-treatment.md).

### Fairness Metric Conflicts

Counterfactual fairness can produce demographic outcome gaps - because it permits unequal outcomes when those outcomes trace to causally independent background variables. This places it in direct tension with Demographic Parity and other group-level metrics. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

### Label Bias

Label bias means the training labels themselves encode historical discrimination - the human decisions the model was trained to replicate were made under biased conditions. Even a counterfactually fair feature set cannot correct for labels that carry the discriminatory signal directly. A causally fair model trained on causally unfair labels is still unfair. See the [label bias explainer](label-bias.md).

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - the clearest real-world example: prior arrest count is causally downstream of race via differential policing. Removing race from the feature set does not achieve counterfactual fairness because the proxy carries the same causal signal.
- [`German Credit Lending/`](../German%20Credit%20Lending/) - employment tenure is causally downstream of age (a 24-year-old structurally cannot have 10 years of work history), making it a proxy in the causal sense. Dropping it is a counterfactual fairness intervention.
- [`Benefits Denial/`](../Benefits%20Denial/) - marital status and relationship type are causally downstream of sex via structural family roles. The spousal rate feature reconstructs sex through marriage patterns - a textbook counterfactual fairness violation.

---

## Further Reading

- [Kusner et al. (2017): *Counterfactual Fairness*, NeurIPS 2017](https://arxiv.org/abs/1703.06856) - the paper that introduced counterfactual fairness and the causal framework used throughout this explainer
- [Pearl (2009): *Causality: Models, Reasoning, and Inference*](https://doi.org/10.1017/CBO9780511803161) - the foundational text on structural causal models and do-calculus; the causal machinery the Kusner framework depends on
- [Chiappa (2019): *Path-Specific Counterfactual Fairness*, AAAI 2019](https://arxiv.org/abs/1802.08139) - extends the framework to handle resolving variables: features causally downstream of the protected attribute that encode legitimate merit signals rather than pure proxies

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
