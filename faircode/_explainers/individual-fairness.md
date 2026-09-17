# Explainer: What is Individual Fairness?

> *Group fairness says the model treats groups equally. Individual fairness asks something harder: does it treat similar people similarly - regardless of which group they belong to?*

---

## The One-Sentence Definition

**Individual Fairness** is a fairness criterion that requires a model to produce similar predictions for individuals who are similar with respect to the task at hand - so that two people who are equally qualified, equally risky, or equally creditworthy receive equally favourable outcomes, regardless of demographic group membership.

It was formalised by Dwork et al. (2012) as: *"similar individuals should be treated similarly."*

---

## Why This Matters

Every other fairness metric in this series - Demographic Parity, Equalized Odds, Disparate Impact - is a *group-level* measure. It asks whether two demographic populations receive equal treatment in aggregate. A model can pass every group-level fairness check and still discriminate against a specific individual, so long as that discrimination is consistent enough not to shift the group averages.

Consider two candidates for the same role:

- **Candidate A:** 9 years of experience, technical test score 88 - rejected
- **Candidate B:** 9 years of experience, technical test score 88 - hired

The only meaningful difference is demographic group membership. Group-level metrics will not catch this. If the pattern is consistent - women with score 88 rejected, men with score 88 hired - the Demographic Parity ratio might still hover near 0.80 and pass the Four-Fifths Rule. The individual is still harmed.

This is the gap individual fairness is designed to close: it operates at the level of the person, not the population.

---

## The Formal Definition

Dwork et al. formalise individual fairness using a **task-specific similarity metric** `d(x, y)` over individuals, and a **distance metric** `D(f(x), f(y))` over model outputs. The requirement is:

```
For any two individuals x and y:
D(f(x), f(y)) ≤ L · d(x, y)
```

Where:
- `f(x)` and `f(y)` are the model's predictions for individuals `x` and `y`
- `d(x, y)` is how different the two individuals are on task-relevant features
- `D(f(x), f(y))` is how different the model's outputs are
- `L` is a Lipschitz constant bounding the ratio

Plain English: if two people are close in the space of features that matter for the task, the model's decisions about them should also be close. Demographic group membership - being in `d(x, y)` - should not expand the decision gap beyond what the task-relevant distance justifies.

The key term is **task-relevant**. Individual fairness does not require treating everyone identically. It requires that differences in outcomes be proportional to differences in merit, risk, or qualification - and not inflated by demographic proxies.

---

## Concrete Example: AI Fair Recruitment

The [`AI Fair Recruitment`](../AI%20Fair%20Recruitment/) audit in this repo is a direct worked example of an individual fairness violation that group metrics partially miss.

Two candidates matched on the merit features the fair model retains:

| Feature | Candidate A (Female) | Candidate B (Male) |
|---|:---:|:---:|
| Experience Years | 8 | 8 |
| Technical Test Score | 84 | 84 |
| **Biased model prediction** | **0 - rejected** | **1 - hired** |

`d(A, B)` on task-relevant features: **zero** - they are identical.
`D(f(A), f(B))` on model output: **1** - opposite decisions.

This violates individual fairness: equal inputs, unequal outputs. Group-level metrics catch the aggregate pattern (a 4.51pp gender hire-rate gap). Individual fairness makes explicit why: these two specific people, who are the same on every dimension that should matter, received opposite verdicts.

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# Reproduce the individual fairness violation
np.random.seed(42)
n = 2000
df = pd.DataFrame({
    'experience_years':     np.random.randint(1, 15, n),
    'technical_test_score': np.random.randint(40, 100, n),
    'gender':               np.random.choice(['Male', 'Female'], n),
})

# Biased labels
base = (df['experience_years'] / 20) + (df['technical_test_score'] / 200)
penalty = np.where(df['gender'] == 'Female', -0.12, 0.0)
df['hired'] = (np.random.rand(n) < (base + penalty).clip(0, 1)).astype(int)

X = pd.get_dummies(df[['experience_years', 'technical_test_score', 'gender']])
y = df['hired']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Find matched pairs where the ONLY difference is gender
results = df.loc[X_test.index].copy()
results['prediction'] = model.predict(X_test)

male   = results[results['gender'] == 'Male']
female = results[results['gender'] == 'Female']

# Merge on identical merit profile
matched = pd.merge(
    male[['experience_years', 'technical_test_score', 'prediction']].rename(columns={'prediction': 'pred_male'}),
    female[['experience_years', 'technical_test_score', 'prediction']].rename(columns={'prediction': 'pred_female'}),
    on=['experience_years', 'technical_test_score']
)

# Disagreements = individual fairness violations
violations = matched[matched['pred_male'] != matched['pred_female']]
print(f"Matched pairs: {len(matched)}")
print(f"Individual fairness violations: {len(violations)}")
print(f"Violation rate: {len(violations)/len(matched)*100:.1f}%")
# Matched pairs: 44
# Individual fairness violations: 11
# Violation rate: 25.0% - 1 in 4 identical profiles, different outcomes
```

---

## How to Measure It in Python

Individual fairness has no single universal metric - it requires defining what "similar" means for the task. The three practical approaches are: matched-pair testing, Lipschitz testing, and consistency scoring.

### 1. Matched-pair consistency test

The most interpretable approach: find pairs of individuals who are identical (or very close) on task-relevant features and measure how often the model gives them different predictions.

```python
import pandas as pd
from sklearn.metrics.pairwise import euclidean_distances
import numpy as np

def individual_fairness_audit(
    df, prediction_col, group_col, feature_cols,
    distance_threshold=0.5
):
    """
    Identify pairs of individuals who are similar on task-relevant features
    (distance <= threshold) but received different predictions.

    These are individual fairness violations: same merit, different outcome.

    df                 : DataFrame with predictions, group, and features
    prediction_col     : binary model decision column
    group_col          : protected attribute column
    feature_cols       : list of task-relevant (merit) feature columns
    distance_threshold : max Euclidean distance to be considered 'similar'
    """
    from sklearn.preprocessing import StandardScaler

    df = df.copy().reset_index(drop=True)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[feature_cols])

    dists = euclidean_distances(X_scaled)
    n = len(df)

    violations = []
    for i in range(n):
        for j in range(i + 1, n):
            if dists[i, j] > distance_threshold:
                continue
            if df[group_col].iloc[i] == df[group_col].iloc[j]:
                continue  # same group - skip; we want cross-group pairs
            if df[prediction_col].iloc[i] != df[prediction_col].iloc[j]:
                violations.append({
                    'i': i, 'j': j,
                    'distance': round(dists[i, j], 4),
                    f'{group_col}_i': df[group_col].iloc[i],
                    f'{group_col}_j': df[group_col].iloc[j],
                    f'{prediction_col}_i': df[prediction_col].iloc[i],
                    f'{prediction_col}_j': df[prediction_col].iloc[j],
                })

    total_similar_pairs = int(((dists <= distance_threshold) & (dists > 0)).sum() / 2)

    return {
        'total_similar_cross_group_pairs': total_similar_pairs,
        'violations': len(violations),
        'violation_rate': round(len(violations) / total_similar_pairs, 3) if total_similar_pairs > 0 else None,
        'examples': violations[:5],  # first 5 for inspection
    }
```

### 2. Lipschitz consistency score (counterfactual perturbation)

This approach measures how much the model's output changes when you make small, demographic-only changes to an individual's record - keeping all task-relevant features fixed.

```python
import pandas as pd
import numpy as np

def lipschitz_consistency_score(model, X_test, group_col, other_group_val, feature_names):
    """
    For each individual, create a counterfactual twin by flipping their
    group membership while keeping all task-relevant features identical.

    A model with good individual fairness should produce similar predictions
    for the original and the twin.

    Returns the mean absolute prediction change across all individuals.
    Higher = worse individual fairness.

    model           : trained classifier with predict_proba
    X_test          : feature DataFrame (including encoded group columns)
    group_col       : name of the group column in the original dataframe
    other_group_val : the value to flip the group to (e.g. 'Male' → 'Female')
    feature_names   : columns passed to the model (post get_dummies)
    """
    X_original = X_test.copy()
    X_counterfactual = X_test.copy()

    # Flip the group encoding
    for col in feature_names:
        if group_col.lower() in col.lower():
            X_counterfactual[col] = 1 - X_counterfactual[col]  # binary flip

    proba_original       = model.predict_proba(X_original)[:, 1]
    proba_counterfactual = model.predict_proba(X_counterfactual)[:, 1]

    delta = np.abs(proba_original - proba_counterfactual)

    return {
        'mean_prediction_change':   round(float(delta.mean()), 4),
        'max_prediction_change':    round(float(delta.max()), 4),
        'pct_changed_above_0.1':    round(float((delta > 0.1).mean()), 3),
        'interpretation': (
            'Low individual fairness - group membership substantially affects predictions'
            if delta.mean() > 0.05 else
            'Acceptable individual fairness - predictions stable across group flip'
        ),
    }
```

### 3. Consistency metric (Zemel et al.)

The consistency metric from Zemel et al. (2013) formalises the matched-pair idea as a single number: for each individual, find their *k* nearest neighbours on task-relevant features and measure how often the model agrees with itself across the neighbourhood.

```python
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

def consistency_score(X, y_pred, feature_cols, k=5):
    """
    Compute the Zemel et al. consistency metric.

    For each individual, find k nearest neighbours on task-relevant features.
    Measure how often the model gives the same prediction to the individual
    and their neighbours.

    Score of 1.0 = perfect consistency (same prediction for all similar people).
    Score near 0 = model gives different predictions to similar people.

    X            : DataFrame with task-relevant features
    y_pred       : array of binary predictions
    feature_cols : columns used for the similarity computation
    k            : number of neighbours to consider
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X[feature_cols])

    nbrs = NearestNeighbors(n_neighbors=k + 1, algorithm='ball_tree').fit(X_scaled)
    distances, indices = nbrs.kneighbors(X_scaled)

    # For each individual, measure prediction agreement with their k neighbours
    consistency_scores = []
    for i, neighbours in enumerate(indices):
        neighbours = neighbours[1:]  # exclude self
        neighbour_preds = y_pred[neighbours]
        agreement = (neighbour_preds == y_pred[i]).mean()
        consistency_scores.append(agreement)

    score = np.mean(consistency_scores)

    return {
        'consistency_score':   round(float(score), 4),
        'interpretation': (
            'Good individual fairness' if score >= 0.80 else
            'Moderate - similar individuals sometimes get different outcomes' if score >= 0.65 else
            'Poor individual fairness - similar people frequently get different outcomes'
        ),
    }
```

---

## Individual Fairness vs. Group Fairness

The two families of fairness criteria are not alternatives - they are different questions with different failure modes.

| | **Group Fairness** | **Individual Fairness** |
|---|---|---|
| **Unit of analysis** | Demographic population | Specific individual |
| **Question** | Are outcomes equal across groups? | Are similar people treated similarly? |
| **Can be satisfied without the other?** | Yes | Yes |
| **Legal grounding** | Disparate Impact (Title VII) | Intentional discrimination, due process |
| **What it catches** | Systematic demographic gaps | Within-group and cross-group inconsistency |
| **What it misses** | Harm to specific individuals inside a passing aggregate | Whether the task-relevant similarity metric is itself fair |
| **Typical detection method** | Fairness ratio, MetricFrame | Matched-pair tests, consistency score, counterfactual probing |
| **Repair strategy** | Resampling, reweighting, post-processing constraints | Regularisation, fairness-aware representation learning |

A model can pass Demographic Parity - equal hire rates across genders - while still systematically giving inconsistent decisions to matched pairs across groups. Equally, a model can achieve high individual consistency while producing aggregate outcome gaps if one group contains fewer high-merit individuals in the dataset (which may itself reflect historical bias, not ability).

The two are complementary, not competing. A complete fairness audit runs both.

---

## The Similarity Metric Problem

Individual fairness has one foundational difficulty: the framework requires a **task-specific similarity metric** `d(x, y)`, and defining a fair one is not a technical problem - it is a normative one.

Who decides that two people are "similar enough" to deserve similar treatment? The features included in `d` define what the task considers relevant. If the definition embeds a biased standard - for example, treating years-at-current-employer as a task-relevant merit signal when it structurally disadvantages career-changers and parents returning from leave - the individual fairness framework will certify those decisions as consistent, even though the similarity metric itself was discriminatory.

```python
# Similarity metric embeds the bias
d_biased = ['experience_years', 'tenure_current_employer']
# 'tenure_current_employer' disadvantages anyone who took a career break -
# disproportionately women. Two people who are equally productive are
# declared dissimilar under this metric. Individual fairness then permits
# different outcomes for them.

# Similarity metric strips the proxy
d_fair = ['experience_years', 'technical_test_score']
# Now matched pairs are defined on genuine merit signals only.
# Individual fairness violations reveal real discrimination, not
# artifacts of a biased distance function.
```

This is not a flaw to be patched - it is the central normative question that individual fairness makes explicit: *what does it mean to be equally qualified for this task?* The answer requires domain expertise, stakeholder input, and legal grounding. It cannot be solved by optimising a loss function.

---

## Limitations / Trade-offs

### Defining the similarity metric requires external judgment

The framework is only as fair as the task-relevant distance function. A biased similarity metric produces certified-consistent discrimination. There is no purely technical solution - the metric requires normative input from domain experts, affected communities, and legal frameworks.

### It can conflict with group fairness when base rates differ

If the underlying population has different distributions of task-relevant features across groups - not because of bias, but because of genuine variation - strict individual fairness can produce demographic outcome gaps, and strict group fairness can require treating dissimilar individuals as similar. These are the same impossibility constraints documented in Chouldechova (2017) and Kleinberg et al. (2016). No single metric resolves them. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

### Computational cost scales with dataset size

The matched-pair audit and consistency score both require pairwise distance computation. On large datasets this becomes expensive. Approximate nearest-neighbour search (`sklearn.neighbors.NearestNeighbors` with `algorithm='ball_tree'`) mitigates this at scale; exact exhaustive search is impractical above ~50,000 records.

### Consistency does not imply correctness

A model that rejects every applicant is perfectly consistent. A model that applies the same wrong standard uniformly satisfies individual fairness. Consistency is a necessary condition for fairness, not a sufficient one. It must be paired with accuracy, calibration, and group-level audits.

### It provides weaker legal protection than group metrics

Disparate Impact under Title VII and the EEOC's Four-Fifths Rule are legally enforceable in the United States. Individual fairness as a technical criterion has no direct legal analogue - courts assess discrimination through statistical patterns across groups and through specific instances of disparate treatment. Individual fairness violation evidence can support a disparate treatment claim, but it does not automatically constitute one.

---

## The Bigger Picture

Group fairness and individual fairness are not rival frameworks. They are different lenses on the same underlying problem: a decision system that uses demographic signal - directly or through proxies - to produce unequal outcomes for people who deserve equal ones.

Group metrics tell you that something is wrong at the population level. Individual fairness tells you exactly what that looks like for a specific person: they submitted the same credentials as someone else, and they received the opposite verdict.

The combination is also what turns a bias audit into evidence. A Demographic Parity gap tells you there is a problem. Matched-pair violations tell you the mechanism. A defendant flagged as high-risk by COMPAS, whose criminal history profile is identical to a defendant flagged as low-risk, is not a statistical artifact - that is a person who can point to a specific instance of unequal treatment. Individual fairness makes that visible in the data.

**The goal is not a model that treats groups equally in the aggregate. The goal is a model that gives the same answer to the same person regardless of which group that person belongs to. Group fairness is the aggregate consequence. Individual fairness is the standard.**

---

## Related Concepts

### Demographic Parity

Demographic Parity is the group-level counterpart: equal positive prediction rates across demographic groups. A model can satisfy Demographic Parity while failing individual fairness, and vice versa. The two are complementary, not interchangeable. See the [demographic parity explainer](demographic-parity.md).

### Disparate Treatment

Disparate Treatment occurs when a protected attribute is a direct model input. Every instance of disparate treatment produces individual fairness violations - but individual fairness violations can occur even when the protected attribute is not in the feature set, if proxy variables reconstruct the same signal. See the [disparate treatment explainer](disparate-treatment.md).

### Proxy Variables

Proxy variables are the mechanism that produces individual fairness violations in models where the protected attribute itself has been removed. Two people identical on merit features may receive different outcomes because a correlated proxy carries the demographic signal through. See the [proxy variables explainer](proxy-variables.md).

### Fairness Metric Conflicts

When base rates differ across demographic groups, there are provable mathematical incompatibilities between group-level and individual-level fairness criteria. Satisfying one can require violating another. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

### Counterfactual Fairness

Counterfactual fairness (Kusner et al., 2017) is a closely related criterion: a model is counterfactually fair if its predictions would be the same had the individual belonged to a different demographic group, holding all causally independent factors constant. Individual fairness asks whether similar people receive similar treatment in the observed data; counterfactual fairness asks whether the same person would receive the same treatment in a counterfactual world where they belong to a different group. The two are complementary; individual fairness is easier to measure empirically, counterfactual fairness requires a causal graph.

---

## Related Projects in This Repo

- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - the clearest worked example: the biased model produces matched-pair violations at a rate of ~21% across identical merit profiles. The fair model collapses this to near zero.
- [`COMPAS/`](../COMPAS/) - individual fairness violations are embedded in the dataset: defendants with identical prior-record profiles receive different risk scores depending on race. The 86.77pp group gap is the aggregate signature of those individual violations.
- [`German Credit Lending/`](../German%20Credit%20Lending/) - age used as a direct feature produces individual fairness violations for young applicants whose credit profiles are identical to older applicants rated good.

---

## Further Reading

- [Dwork et al. (2012): *Fairness Through Awareness*, ITCS 2012](https://arxiv.org/abs/1104.3913) - the paper that formalised individual fairness and introduced the Lipschitz condition
- [Zemel et al. (2013): *Learning Fair Representations*, ICML 2013](https://proceedings.mlr.press/v28/zemel13.html) - introduces the consistency metric used in the detection code above
- [Kusner et al. (2017): *Counterfactual Fairness*, NeurIPS 2017](https://arxiv.org/abs/1703.06856) - counterfactual fairness as an individual-level causal complement to the Dwork framework
- [Chouldechova (2017): *Fair Prediction with Disparate Impact*](https://arxiv.org/abs/1703.00056) - the impossibility result showing where individual and group fairness conflict when base rates differ

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
