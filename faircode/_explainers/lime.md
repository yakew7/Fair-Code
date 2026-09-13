> *Two explainability methods can look interchangeable from a comparison table row - LIME and SHAP answer the same question ("why did the model do this?") through completely different mechanics, and the difference changes how much you should trust either one's answer.*

## The One-Sentence Definition

**LIME** (Local Interpretable Model-agnostic Explanations) explains one prediction by perturbing the input slightly, seeing how the model's output changes, and fitting a simple, interpretable model - usually linear - to that local neighborhood of perturbed points, then reading the surrogate's coefficients as the explanation.

## Why This Matters

[SHAP Values](shap-values.md) already covers the other major explainability technique used to inspect what actually drove a flagged decision. LIME shows up constantly alongside it - in papers, in tooling, in comparison tables - but "another explainability method" undersells what's actually a fundamentally different approach with its own specific failure modes. A fairness audit that treats LIME's output with the same confidence as SHAP's is trusting a different, and generally weaker, kind of guarantee.

That distinction matters in practice: if LIME says a flagged loan denial was driven mostly by income and a SHAP analysis of the same prediction says it was driven mostly by zip code, knowing *why* the two methods can disagree - not just that they did - is what tells you which one to trust for the decision in front of you.

## Core Concept: A Local Surrogate, Not a Global Explanation

LIME works in four steps, for one single prediction at a time:

1. Take the input you want to explain (one loan application, one recidivism score).
2. Generate a cloud of perturbed versions of it - slightly different feature values, sampled around the original.
3. Get the real model's prediction for every perturbed point, weighting each one by how close it is to the original input.
4. Fit a simple, interpretable model (typically linear regression) to those weighted (perturbation, prediction) pairs. The surrogate's coefficients become the explanation: how much each feature mattered *in this local neighborhood*.

The key word is **local**. LIME never claims to explain the model's global behavior - only what it's doing in the small region around one specific input. This is also LIME's central trade-off against SHAP: SHAP's Shapley-value approach comes with mathematical guarantees (the contributions sum exactly to the prediction, and satisfy specific consistency properties from game theory); LIME's surrogate model is only an *approximation* of the real model's local behavior, and how good that approximation is depends entirely on how the perturbation sampling and neighborhood weighting were configured. Run LIME twice on the same prediction with different random perturbation samples, and the resulting feature-importance ranking can shift - a stability problem SHAP's exact computation (for tree models) doesn't share.

## Concrete Example: COMPAS - Audit 01

Applying LIME to a single high-risk COMPAS prediction, using the same biased feature set (race included) as [SHAP Values](shap-values.md)'s own COMPAS example, illustrates what a local explanation looks like in practice - this is the actual output of the Detection Code below, for test row 0 (predicted probability 52.8% high-risk, predicted class: high risk):

```
--- LIME EXPLANATION FOR ONE PREDICTION (predicted: high risk) ---

Feature                                Local weight
------------------------------------------------------
0.00 < race_binary <= 1.00             +0.1906  ← pushed toward "high risk"
MaritalStatus_Married <= 0.00          +0.1201
MaritalStatus_Divorced <= 0.00         +0.0969
MaritalStatus_Separated <= 0.00        +0.0411
CustodyStatus_Probation <= 0.00        +0.0339
```

For this one individual (who is African-American, `race_binary = 1`), LIME's local surrogate says race is the single largest local contributor toward the "high risk" prediction, consistent with what SHAP's *aggregate* analysis found across many predictions in the SHAP explainer's own example. That agreement is reassuring, but it's also the exception worth watching for: LIME's local weights are computed fresh for every single prediction, so a different individual's flagged decision could show a completely different feature ranking even under the identical model, since each explanation only reflects the neighborhood immediately around that one input.

## Detection Code

```python
import lime
import lime.lime_tabular
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

df = pd.read_csv('COMPAS/compas-scores-raw.csv')
df = df[df['Ethnic_Code_Text'].isin(['African-American', 'Caucasian'])].copy()
df = df[df['DisplayText'] == 'Risk of Recidivism'].copy()
df['race_binary'] = df['Ethnic_Code_Text'].map({'African-American': 1, 'Caucasian': 0})

X = pd.get_dummies(df[['race_binary', 'Sex_Code_Text', 'CustodyStatus', 'MaritalStatus']])
y = df['ScoreText'].isin(['High', 'Medium']).astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)

explainer = lime.lime_tabular.LimeTabularExplainer(
    X_train.values,
    feature_names=X_train.columns.tolist(),
    class_names=['low_risk', 'high_risk'],
    mode='classification',
    random_state=42,
)

# Explain one specific prediction
instance = X_test.iloc[0].values
explanation = explainer.explain_instance(instance, model.predict_proba, num_features=5)

for feature, weight in explanation.as_list():
    print(f"{feature}: {weight:+.4f}")


# Usage note: run explain_instance() again on the same row with a different
# random_state on the explainer - if the top features reorder, the local
# surrogate fit was unstable for this specific point, and the explanation
# should not be trusted as strongly as a stable one.
```

## Limitations

### 1. It's an approximation, not an exact decomposition

Unlike SHAP's Shapley-value guarantees, LIME's surrogate is only as good as the local linear fit - a genuinely non-linear decision boundary in that neighborhood can produce a misleading local explanation even when the surrogate fits its own perturbed sample well.

### 2. Explanations can be unstable across repeated runs

Because the perturbation sample is random, two runs on the identical input and model can rank features differently, particularly near a decision boundary where the model's behavior changes quickly across small input changes.

### 3. It's genuinely local - it says nothing about the model overall

A LIME explanation for one denied application tells you nothing about whether the model is fair in aggregate. Global fairness metrics like [Demographic Parity](demographic-parity.md) or [Equalized Odds](equalized-odds.md) still require checking separately; LIME (and SHAP) explain individual decisions, not overall fairness.

### 4. The perturbation strategy has to make sense for the data

LIME's default tabular perturbation (sampling from feature distributions) can generate combinations that don't correspond to any realistic individual, producing an explanation grounded in inputs that could never actually occur.

## Related Concepts

* [What Are SHAP Values?](shap-values.md) - the other major feature-attribution method, with exact (not approximate) local guarantees for tree models.
* [What Is a Confounding Variable?](confounding-variable.md) - a reason two features can appear to "matter" in an explanation without either one being the true underlying cause.
* [Proxy Variables](proxy-variables.md) - what a proxy feature (like custody status standing in for race) looks like when it surfaces inside a LIME or SHAP explanation.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the audit both this explainer and [SHAP Values](shap-values.md) use to demonstrate feature-attribution output on the same biased model.

## Further Reading

* [Ribeiro, M. T., Singh, S., Guestrin, C. (2016): "Why Should I Trust You?": Explaining the Predictions of Any Classifier](https://arxiv.org/abs/1602.04938) - the original LIME paper.
* [Lundberg, S., Lee, S. (2017): A Unified Approach to Interpreting Model Predictions](https://arxiv.org/abs/1705.07874) - the SHAP paper, framing Shapley values as a unifying theory that LIME approximates a special case of.
* [Molnar, C.: *Interpretable Machine Learning*](https://christophm.github.io/interpretable-ml-book/lime.html) - a practical, freely available comparison of LIME against SHAP and other explanation methods.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
