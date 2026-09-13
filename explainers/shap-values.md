# Explainer: What Are SHAP Values?

> *The reason "the model said so" is not an explanation - and what to do instead.*

---

## The One-Sentence Definition

**SHAP values** (SHapley Additive exPlanations) are a method for explaining individual predictions made by any machine learning model - they tell you exactly how much each feature contributed to a specific output, in a unit you can reason about.

---

## Why This Matters

Most AI systems deployed in high-stakes domains - criminal justice, hiring, lending, healthcare - are black boxes. They produce a score or a decision, and they don't explain why. This is not just an inconvenience. It is a fairness problem.

If you cannot inspect how a model arrived at a decision, you cannot:
- Detect whether a protected attribute or proxy variable drove the outcome
- Challenge a decision that affected you
- Comply with regulations that require explainability (GDPR Article 22, EEOC, ECOA)
- Audit the system for bias before deployment

SHAP values make the black box transparent. They are grounded in cooperative game theory - specifically, Shapley values - which provide a mathematically principled way to attribute credit (or blame) across features. Unlike simpler techniques, SHAP values are consistent, locally accurate, and model-agnostic.

---

## The Intuition: Fair Credit Attribution

Imagine three people - Alice, Bob, and Carol - collaborate on a project that earns $300,000. Who gets credit for what? The Shapley value from game theory answers this by asking: *on average, across every possible ordering in which these people could join the project, how much does each person's addition increase the outcome?*

SHAP applies this same logic to features. For a single prediction:

- Your model outputs a score of 0.82 (high recidivism risk)
- SHAP asks: across all possible subsets of features, how much does each feature shift the prediction away from the average?
- The result is a signed contribution value for every feature - positive means it pushed the prediction up, negative means it pushed it down

**The key property:** the SHAP values for all features sum exactly to the difference between the model's prediction and the global average prediction.

```
model_output = base_value + shap(age) + shap(custody_status) + shap(race) + ...
```

---

## Real-World Proof: COMPAS Analysis

We applied SHAP to the [ProPublica COMPAS dataset](https://github.com/propublica/compas-analysis) to inspect what the biased model was actually using.

### Setup

```python
import shap
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

df = pd.read_csv('COMPAS/compas-scores-raw.csv')
df = df[df['Ethnic_Code_Text'].isin(['African-American', 'Caucasian'])].copy()
df = df[df['DisplayText'] == 'Risk of Recidivism'].copy()
df['race_binary'] = df['Ethnic_Code_Text'].map({'African-American': 1, 'Caucasian': 0})

# Biased feature set (includes race + proxy)
X = pd.get_dummies(df[['race_binary', 'Sex_Code_Text', 'CustodyStatus', 'MaritalStatus']])
y = df['ScoreText'].isin(['High', 'Medium']).astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)

# Compute SHAP values (index [:, :, 1] selects the "high risk" class)
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)[:, :, 1]
```

### What SHAP Revealed

**Actual output** (mean absolute SHAP value per feature, this repo's `COMPAS/compas-scores-raw.csv`):

```
--- MEAN ABSOLUTE SHAP VALUES (biased model) ---

Feature                     Mean |SHAP|
----------------------------------------------
race_binary                 0.1066   ← highest driver
MaritalStatus_Single        0.0624   ← second highest
MaritalStatus_Married       0.0234
CustodyStatus_Probation     0.0165   (proxy)
MaritalStatus_Divorced      0.0126
```

**The model's single largest driver was race.** `MaritalStatus_Single` was the second largest; `CustodyStatus_Probation` - a proxy for race - ranks fourth. Race alone accounted for roughly 40% of the top-5 features' combined influence.

Without SHAP, you would not know this. The model's accuracy numbers alone tell you nothing about which features drove individual predictions.

### After the Fix - Fair Model SHAP

```python
# Fair feature set (race + proxy removed)
X_fair = pd.get_dummies(df[['Sex_Code_Text', 'MaritalStatus']])
X_train_fair, X_test_fair, y_train_fair, y_test_fair = train_test_split(
    X_fair, y, test_size=0.2, random_state=42, stratify=y)
model_fair = RandomForestClassifier(random_state=42)
model_fair.fit(X_train_fair, y_train_fair)

explainer_fair = shap.TreeExplainer(model_fair)
shap_values_fair = explainer_fair.shap_values(X_test_fair)[:, :, 1]
```

**Actual output:**

```
--- MEAN ABSOLUTE SHAP VALUES (fair model) ---

Feature                     Mean |SHAP|
----------------------------------------------
MaritalStatus_Single        0.0626
MaritalStatus_Married       0.0270
MaritalStatus_Divorced      0.0195
```

Race is gone from the feature set. The model now distributes influence across legitimate remaining features. SHAP confirms the fix worked - not just at the aggregate fairness gap level, but at the level of individual decision logic.

---

## How to Use SHAP in Practice

### Installation

```bash
pip install shap
```

### For Tree Models (Random Forest, XGBoost, LightGBM)

```python
import shap

# TreeExplainer is fast and exact for tree-based models
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# shap_values shape: [n_samples, n_features] for binary classification (class 1)
# For multi-class: list of arrays, one per class
```

### For Any Model (Model-Agnostic)

```python
# KernelExplainer works with any model; slower but universal
explainer = shap.KernelExplainer(model.predict_proba, shap.sample(X_train, 100))
shap_values = explainer.shap_values(X_test[:10])
```

### Explaining a Single Prediction

```python
def explain_decision(model, explainer, X_test, sample_idx):
    """
    Return a sorted explanation for one prediction.
    Positive values → pushed prediction UP (toward flagged/rejected/denied)
    Negative values → pushed prediction DOWN
    """
    sv = explainer.shap_values(X_test.iloc[[sample_idx]])[0, :, 1]
    feature_names = X_test.columns.tolist()

    explanation = sorted(
        zip(feature_names, sv),
        key=lambda x: abs(x[1]),
        reverse=True
    )
    return explanation

# Actual output for test row 0 (a real high-risk COMPAS prediction):
# [('MaritalStatus_Single', -0.122), ('race_binary', +0.104), ('MaritalStatus_Significant Other', +0.027), ...]
```

### Bias Audit Using SHAP

```python
import numpy as np

def shap_bias_audit(shap_values, feature_names, protected_features):
    """
    Flag any protected attribute or known proxy in the top drivers.
    Returns sorted mean absolute SHAP values, with bias flags.
    """
    mean_abs_shap = pd.Series(
        np.abs(shap_values).mean(axis=0),
        index=feature_names
    ).sort_values(ascending=False)

    result = mean_abs_shap.reset_index()
    result.columns = ['feature', 'mean_abs_shap']
    result['bias_flag'] = result['feature'].apply(
        lambda f: 'PROTECTED OR PROXY' if any(p in f for p in protected_features) else ''
    )
    return result

# Run before deployment
protected = ['race_binary', 'CustodyStatus']
audit = shap_bias_audit(shap_values, X_test.columns, protected)
print(audit.head(6))
```

**Actual output:**

```
                feature  mean_abs_shap          bias_flag
            race_binary       0.106622 PROTECTED OR PROXY
   MaritalStatus_Single       0.062441
  MaritalStatus_Married       0.023384
CustodyStatus_Probation       0.016462 PROTECTED OR PROXY
 MaritalStatus_Divorced       0.012589
    Sex_Code_Text_Male        0.006635
```

---

## SHAP vs Other Explainability Methods

| Method | Scope | Consistency | Model-Agnostic | Speed |
|---|---|---|---|---|
| **SHAP** | Local + Global | ✓ Mathematically guaranteed | ✓ Yes | Medium–Fast |
| LIME | Local only | ✗ Approximate | ✓ Yes | Slow |
| Feature Importance (Gini) | Global only | ✗ Biased toward high-cardinality | ✗ Tree models only | Fast |
| Permutation Importance | Global only | Reasonable | ✓ Yes | Medium |

SHAP is the only method that is **locally accurate** (values sum exactly to the prediction), **consistent** (if a feature matters more, its SHAP value will be higher), and **unified** across model types. For fairness auditing specifically, local accuracy is essential - you need to know what drove *this specific decision*, not just what matters on average.

---

## Limitations

**1. SHAP values explain the model, not the world.** If your model is trained on biased data, SHAP will faithfully explain the biased decision. High SHAP for a legitimate feature doesn't mean the feature is fair - it means the model used it heavily. Use SHAP alongside the proxy variable audit, not instead of it.

**2. Correlation is not causation.** SHAP measures how much each feature shifted the prediction. It does not tell you whether that feature *should* shift the prediction. A model can assign high SHAP to zip code without zip code being a valid criterion for the decision.

**3. Computational cost at scale.** KernelExplainer is slow for large datasets. TreeExplainer is fast for tree-based models, but SHAP for deep neural networks (DeepExplainer, GradientExplainer) is approximate and can be expensive.

**4. SHAP values can mislead with correlated features.** When two features are highly correlated (like `age` and `employment_tenure`), SHAP distributes the shared contribution between them in ways that can understate either feature's individual influence. This is one more reason to run proxy variable detection *before* computing SHAP - so you already know which features are collinear.

---

## The Bigger Picture

Explainability is not a nice-to-have. It is the mechanism by which accountability becomes possible. A person denied a loan, flagged as high-risk in a courtroom, or rejected by a hiring algorithm has a legitimate interest in knowing why. A company deploying these systems has a legal and ethical obligation to be able to answer that question.

SHAP values do not fix bias. Removing protected attributes and proxy variables fixes bias. What SHAP does is make the model's reasoning visible - so you can catch problems before deployment, explain decisions to the people affected by them, and demonstrate to auditors and regulators that the system is operating as intended.

The pipeline is not complete until you can explain every decision the model makes.

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - The biased and fair models where SHAP reveals race as the top driver
- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - Gender + age influence exposed via feature attribution
- [`German Credit Lending/`](../German%20Credit%20Lending/) - Age and tenure SHAP contributions before and after mitigation
- [`explainers/proxy-variables.md`](proxy-variables.md) - What proxy variables are and how to detect them
- [`explainers/sampling-bias.md`](sampling-bias.md) - Why your training data may not represent the people your model affects

---

## Further Reading

- [Lundberg & Lee: A Unified Approach to Interpreting Model Predictions (NeurIPS 2017)](https://arxiv.org/abs/1705.07874) - the original SHAP paper
- [SHAP Documentation and Examples](https://shap.readthedocs.io/)
- [Barocas & Hardt: Fairness and Machine Learning](https://fairmlbook.org/) - Chapter 6 covers interpretability in the context of fairness

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
