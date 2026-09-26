# Explainer: What is Label Bias?

> *The training data your model learned from was itself a record of human prejudice. Garbage in, discrimination out - and the model has no idea.*

---

## The One-Sentence Definition

**Label Bias** is a form of historical bias that occurs when the ground-truth labels used to train a model reflect past human discrimination rather than actual merit, risk, or outcome - causing the model to learn and perpetuate that discrimination as if it were objective fact.

---

## Why This Matters

Every supervised learning model learns to predict a label. The quiet assumption is that the label is correct. In practice, labels in real-world datasets are often human decisions - hiring outcomes, parole approvals, loan denials, performance ratings - recorded by people operating inside systems that were already discriminatory.

When a model trains on those labels, it doesn't just learn patterns. It learns to reproduce the prejudice baked into every `0` and `1`.

This is what makes label bias fundamentally different from every other bias discussed in this repo:

- **Proxy variables** are a problem in the features. Label bias is a problem in the target.
- **Sampling bias** is a problem in who is represented. Label bias is a problem in whether the labels were fair in the first place.
- **Feedback loop bias** is label bias that compounds across retraining cycles.

You cannot detect label bias by looking at your data pipeline. The data pipeline is clean. The labels were just wrong to begin with - and you likely have no ground truth to compare them against.

---

## Concrete Example: Hiring Decisions

Imagine a company builds a resume-screening model trained on ten years of its own hiring data. The dataset has 50,000 applicants, features like education, experience, and technical scores, and a binary label: `hired = 1`.

The model trains, achieves 89% accuracy on a holdout set, passes the Four-Fifths Rule (Disparate Impact Ratio = 0.84), and ships.

The problem: over those ten years, the company's hiring managers disproportionately rejected women for senior roles - not because women were less qualified, but because of documented managerial bias. That pattern is now encoded in the label column.

The model learned that a woman with 8 years of experience and a high technical score is, historically, `hired = 0`. It's not discriminating against women directly. It's accurately predicting what biased humans would have decided.

This is label bias. The features are clean. The pipeline is clean. The metric passes. The harm is still real.

```python
# Simulated example of how label bias manifests silently

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

np.random.seed(42)
n = 2000

df = pd.DataFrame({
    'experience_years':     np.random.randint(1, 15, n),
    'technical_test_score': np.random.randint(40, 100, n),
    'gender':               np.random.choice(['Male', 'Female'], n),
})

# Simulate biased historical labels:
# Women with equal qualifications were hired ~30% less often by past managers
base_hire_prob = (df['experience_years'] / 20) + (df['technical_test_score'] / 200)
gender_penalty = np.where(df['gender'] == 'Female', -0.12, 0.0)
hire_prob = (base_hire_prob + gender_penalty).clip(0, 1)
df['hired'] = (np.random.rand(n) < hire_prob).astype(int)

# Train on these historically-biased labels
X = pd.get_dummies(df[['experience_years', 'technical_test_score', 'gender']])
y = df['hired']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

test_results = df.loc[X_test.index].copy()
test_results['prediction'] = model.predict(X_test)

rates = test_results.groupby('gender')['prediction'].mean()
print(rates)
# Female    0.668
# Male      0.773
# The model reproduces the historical gap - not because of any feature engineering,
# but because it faithfully learned from biased labels.
```

The model was never told about gender-based bias. It discovered the pattern in the `hired` column and replicated it. Accuracy is high. The damage is invisible to standard evaluation.

---

## Why It's So Hard to Detect

Most fairness checks - Disparate Impact, Equalized Odds, Demographic Parity - are comparisons between model predictions and ground-truth labels. Label bias breaks this test design at the root, because the ground-truth labels are the problem.

Consider the COMPAS audit in this repo. Black defendants are flagged as high-risk at dramatically higher rates than White defendants. One interpretation: the model is biased. Another, harder interpretation: the model learned from recidivism labels that were themselves shaped by over-policing, prosecution rate disparities, and sentencing gaps. A model trained to predict reoffending - using labels derived from who *got arrested again* - is training on a variable that reflects policing decisions as much as defendant behaviour.

No standard bias audit can distinguish between "the model is wrong" and "the labels were wrong." You need external ground truth to do that, and in most deployment domains, none exists.

---

## How to Detect It in Practice

There is no single metric for label bias. Detection requires a combination of approaches.

### 1. Label distribution audit

Start by checking whether positive labels are distributed equally across protected groups, conditional on merit-based features. If two groups with equivalent qualifications receive different label rates, the labels may be biased.

```python
import pandas as pd

def label_bias_audit(df, label_col, group_col, feature_cols, n_bins=4):
    """
    Check whether label rates differ across groups within merit-score quantiles.

    If two groups show meaningfully different label rates in the same score band,
    the labels may reflect historical discrimination rather than merit.

    df           : DataFrame with labels, group membership, and merit features
    label_col    : binary outcome column (ground truth)
    group_col    : protected attribute column
    feature_cols : list of merit-based numeric features to bin by
    n_bins       : number of quantile bins for merit score
    """
    df = df.copy()
    df['_merit_score'] = df[feature_cols].mean(axis=1)
    df['_merit_bin'] = pd.qcut(df['_merit_score'], q=n_bins, labels=False, duplicates='drop')

    result = (
        df.groupby(['_merit_bin', group_col])[label_col]
          .mean()
          .unstack(group_col)
          .round(3)
    )

    print("Label rates by merit band and group:")
    print(result)
    print("\nIf rates differ substantially within the same row, investigate label quality.")
    return result
```

### 2. Consistency test

Within the same merit tier, the label rate should be roughly equal across groups. If it is not - if highly-qualified members of one group received `0` labels at higher rates - that is a signal of label bias.

```python
# Apply it to the hiring simulation above
label_bias_audit(
    df=df,
    label_col='hired',
    group_col='gender',
    feature_cols=['experience_years', 'technical_test_score'],
    n_bins=4
)

# gender         Female    Male
# _merit_bin
# 0               0.480   0.531   ← low merit tier: 5.1pp gap
# 1               0.565   0.680   ← moderate tier: 11.5pp gap - widens
# 2               0.645   0.750   ← gap persists even at high merit: 10.5pp
# 3               0.770   0.865   ← top tier: 9.5pp gap - flags label bias
```

A consistent gap that does not shrink as merit rises - exactly where it should disappear if the labels reflected merit alone - is a strong label-bias signal.

### 3. Counterfactual label audit

Where records exist for both groups with matched features, compare label rates directly. This is the methodological approach used in audit studies - the "matched resume" experiments in hiring research - and it can be replicated computationally on historical datasets via propensity score matching.

```python
from sklearn.linear_model import LogisticRegression
import numpy as np

def propensity_matched_label_audit(df, label_col, group_col, feature_cols, protected_val):
    """
    Estimate label rate disparity between groups after propensity-score matching.

    Fits a logistic model to predict group membership from features alone.
    Matches each member of the protected group to a comparable member of the
    reference group by propensity score. Compares label rates in matched pairs.
    """
    df = df.copy()
    df['_is_protected'] = (df[group_col] == protected_val).astype(int)

    X = df[feature_cols]
    ps_model = LogisticRegression(max_iter=1000).fit(X, df['_is_protected'])
    df['_propensity'] = ps_model.predict_proba(X)[:, 1]

    protected = df[df['_is_protected'] == 1].copy()
    reference = df[df['_is_protected'] == 0].copy()

    # Greedy nearest-neighbor matching
    reference = reference.sort_values('_propensity')
    matched_ref = []
    used = set()
    for _, row in protected.iterrows():
        diffs = (reference['_propensity'] - row['_propensity']).abs()
        diffs = diffs[~diffs.index.isin(used)]
        if diffs.empty:
            continue
        best = diffs.idxmin()
        used.add(best)
        matched_ref.append(reference.loc[best])

    matched_reference = pd.DataFrame(matched_ref)

    protected_rate  = protected[label_col].mean()
    reference_rate  = matched_reference[label_col].mean()

    print(f"{protected_val} label rate (matched):    {protected_rate:.3f}")
    print(f"Reference label rate (matched): {reference_rate:.3f}")
    print(f"Gap after matching:             {abs(protected_rate - reference_rate):.3f}")
    print("If gap persists after matching on merit features, label bias is likely.")
```

---

## The Difference Between Label Bias and Model Bias

This distinction matters when deciding how to fix the problem.

| | **Model Bias** | **Label Bias** |
|---|---|---|
| **Source** | Features or training process | Ground-truth labels |
| **Location** | In the feature matrix or model weights | In the target column |
| **Detection** | Standard fairness metrics (DI ratio, Equalized Odds) | Conditional label distribution audits |
| **Fix** | Drop proxy variables, re-train, apply constraints | Relabel data, collect new labels, apply label-noise correction |
| **Detectable without external ground truth?** | Yes | Often no |

A model can be perfectly calibrated and still perpetuate label bias. It learned exactly what it was taught.

---

## Mitigation Strategies

Label bias cannot be fixed by removing a column. The contamination is in the target variable. Mitigation requires intervening at the label level.

### 1. Relabeling by audited human review

The most direct approach: convene a structured review of a sample of labels, specifically looking for cases where a protected-group member received a negative label despite strong merit signals. This is expensive and impractical at scale, but it is the only way to produce genuinely clean labels.

### 2. Learning with noisy labels

If you believe labels are biased but cannot relabel, noise-robust training methods can reduce the model's tendency to fit the biased signal. The key assumption: label errors are not random - they are correlated with the protected attribute.

```python
# Conceptual example: downweight training examples where label is
# suspected to be biased (low merit, wrong-group negative outcome)

def compute_sample_weights(df, label_col, group_col, feature_cols, protected_val):
    """
    Assign lower weight to training examples most likely to carry biased labels:
    high-merit, protected-group members who received a negative label.
    These are the records most likely to reflect historical discrimination.
    """
    df = df.copy()
    df['_merit'] = df[feature_cols].mean(axis=1)
    merit_median = df['_merit'].median()

    # Suspected biased negatives: high merit + protected group + negative label
    suspected_biased = (
        (df[group_col] == protected_val) &
        (df['_merit'] > merit_median) &
        (df[label_col] == 0)
    )

    weights = pd.Series(1.0, index=df.index)
    weights[suspected_biased] = 0.5   # downweight; tune this value

    return weights

weights = compute_sample_weights(
    df=df,
    label_col='hired',
    group_col='gender',
    feature_cols=['experience_years', 'technical_test_score'],
    protected_val='Female'
)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train, sample_weight=weights[X_train.index])
```

### 3. Outcome-based labels where possible

Where the label captures a *decision* (hired, approved, denied), consider replacing it with an *outcome* if one exists - actual job performance, actual loan repayment, actual recidivism. Decisions are biased by the decision-maker. Outcomes are closer to ground truth.

This is not always available (historical data may not include follow-up) and has its own complications (outcomes also reflect systemic inequities), but it is a stronger label where it exists.

### 4. Fairness constraints at training time

If you cannot fix the labels, you can constrain the model to ignore the discriminatory signal in them. Fairlearn's `ExponentiatedGradient` and `GridSearch` reducers can enforce Demographic Parity or Equalized Odds constraints regardless of what is in the label column - effectively refusing to learn the biased pattern even when it is present.

```python
from fairlearn.reductions import ExponentiatedGradient, DemographicParity
from sklearn.ensemble import RandomForestClassifier

estimator = RandomForestClassifier(n_estimators=100, random_state=42)
constraint = DemographicParity()

mitigator = ExponentiatedGradient(estimator, constraint)
mitigator.fit(
    X_train,
    y_train,
    sensitive_features=df.loc[X_train.index, 'gender']
)
```

This does not remove the label bias - it overrides it. The model learns a different mapping that satisfies the fairness constraint even though the labels were discriminatory.

---

## Limitations / Trade-offs

### You often can't prove it without external ground truth

The conditional label distribution test is suggestive, not conclusive. A gap in label rates within a merit tier could reflect label bias, or it could reflect a legitimate merit signal not captured in your features. Distinguishing the two requires either external validation data or a randomised audit study - both of which are rarely available in production settings.

### Fixing labels can introduce new errors

Relabeling historical data changes the ground truth that future models train on. Done without rigorous methodology, it can overcorrect, replacing one form of bias with another. Label corrections must be documented, versioned, and audited independently.

### Fairness constraints trade accuracy for parity

Applying Demographic Parity or Equalized Odds constraints during training forces the model away from the labels - which means worse predictive accuracy on the (biased) test set. This is the right trade-off when the test labels are themselves biased, but it appears as an accuracy regression if evaluated naively. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

### It compounds with feedback loops

Label bias is the starting condition for feedback loop bias. A model trained on biased labels generates biased predictions. Those predictions become the next generation of "ground truth" labels when the system is retrained. Each cycle amplifies the initial distortion. See the [feedback loop bias explainer](feedback-loop-bias.md).

---

## The Bigger Picture

Label bias forces an uncomfortable question: if the training data records what humans decided, and humans decided in discriminatory ways, is a model trained on that data learning job-relevant patterns - or is it learning to replicate discrimination at scale?

The answer is usually both. The model learns real signal *and* discriminatory signal because both are present in the labels. Standard evaluation cannot distinguish them because it uses the same labels as the ground truth.

This is why label bias is particularly dangerous in high-stakes domains: criminal justice, hiring, lending, healthcare. These are exactly the domains where historical records exist at scale, where AI adoption is fastest, and where the decisions have the largest impact on people's lives. They are also the domains where historical discrimination was most systematic - and therefore most thoroughly documented in the label column.

**Auditing for label bias requires going beyond the model. It requires asking whether the target variable you trained on was ever a legitimate measure of what you claim to predict - or whether it was always a record of what biased humans decided.**

---

## Related Concepts

### Feedback Loop Bias

Label bias is the seed that feedback loops grow from. When biased predictions are harvested as new training labels, the distortion in the original label column compounds across retraining cycles. See the [feedback loop bias explainer](feedback-loop-bias.md).

### Proxy Variables

Label bias and proxy variables can interact. If a proxy variable correlates with the protected attribute, and the labels are biased, the proxy becomes a conduit that carries both the proxy bias *and* the label bias into the model simultaneously. See the [proxy variables explainer](proxy-variables.md).

### Sampling Bias

Sampling bias determines who is in the training data. Label bias determines whether their outcomes were recorded fairly. Both are required for the training data to be trustworthy. See the [sampling bias explainer](sampling-bias.md).

### Disparate Treatment

Disparate Treatment occurs when a protected attribute is used directly in the decision. Label bias is more subtle: the protected attribute may never appear in the model, but the labels it learned from were shaped by human actors who did consider it. See the [disparate treatment explainer](disparate-treatment.md).

### Fairness Metric Conflicts

Any fairness constraint applied to correct for label bias will trade off against accuracy on the biased labels. This apparent trade-off is a feature, not a bug - but it registers as an accuracy drop in standard evaluation. See the [fairness metric conflicts explainer](fairness-metric-conflicts.md).

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - recidivism labels derived from re-arrest data, which reflects policing decisions as much as defendant behaviour. The most direct worked example of label bias in this repo.
- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - hiring labels generated by human managers whose decisions carried gender and age bias. The biased model (DI ratio 0.620, across all three Gender groups) learns from those labels without any explicit demographic input.
- [`Benefits Denial/`](../Benefits%20Denial/) - income labels from 1994 Census data, a period when structural discrimination in wages and labour access was undocumented and unmitigated. The label column records outcomes, not potential.

---

## Further Reading

- [Barocas & Selbst (2016): *Big Data's Disparate Impact*, 104 Calif. L. Rev. 671](https://www.californialawreview.org/print/2-big-datas-disparate-impact) - Section III covers biased training labels as a mechanism of algorithmic discrimination
- [Friedler et al. (2019): *A Comparative Study of Fairness-Enhancing Interventions in Machine Learning*](https://arxiv.org/abs/1802.04422) - empirical comparison of pre-, in-, and post-processing mitigation strategies, including label noise correction
- [Jacobs & Wallach (2021): *Measurement and Fairness*, FAccT 2021](https://arxiv.org/abs/1912.05511) - the definitive paper on the gap between what ML labels purport to measure and what they actually encode
- [Obermeyer et al. (2019): *Dissecting Racial Bias in an Algorithm Used to Manage the Health of Populations*, Science](https://www.science.org/doi/10.1126/science.aax2342) - landmark audit showing a healthcare algorithm that used healthcare cost as a proxy for health need; the label itself (cost) was biased because Black patients had less access to care at equal health levels

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
