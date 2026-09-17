> *A model doesn't know what a "pattern" is - it only knows which numbers tend to move together, and it will use any number that moves together with the target, including the ones that encode race, sex, or age.*

## The One-Sentence Definition

**Pattern detection** in machine learning is the process by which a model finds statistical correlations between input features and an outcome, weighting and combining those correlations to produce a prediction - with no built-in distinction between a causal pattern and a discriminatory one.

## Why It Matters

Every audit in this repo runs on the same underlying mechanism: a Random Forest Classifier finds patterns in `unfair.py` and the exact same patterns, minus a few columns, in `fair.py`. The gap between those two runs is the entire story of algorithmic bias. In hiring, lending, healthcare, and criminal justice, the "pattern" the model found was often a historical record of who got hired, approved, treated, or detained - not a measure of who deserved to be.

The non-obvious part is this: pattern detection has no concept of "should." A Random Forest does not know that `CustodyStatus` reflects decades of over-policing rather than individual criminality. It only knows that `CustodyStatus` and `race` move together, and that both move together with the recidivism label. From the model's point of view, a proxy and a cause look identical - both are just columns with high feature importance.

## How Pattern Detection Works

A Random Forest Classifier - the model used across every audit in this repo - detects patterns through three mechanisms working together.

### 1. Splitting on feature thresholds

Each decision tree in the forest repeatedly asks yes/no questions about feature values: "Is `employment` ≥ 7 years?", "Is `payer_code` == Medicaid?". A split is chosen because it best separates the training examples by outcome. The tree does not ask whether the split is *fair* - only whether it is *informative*.

### 2. Aggregating across many trees

A single tree overfits to noise. A forest of 100 trees (`n_estimators=100`, as used throughout this repo), each trained on a random subset of data and features, averages out that noise. What survives the averaging are the patterns that are *consistently* useful - which includes consistent societal patterns, not just consistent physical ones.

### 3. Ranking features by importance

After training, each feature gets an importance score based on how much it improved splits across the forest. In the COMPAS audit, `race_binary` scores highly - not because the model was told it matters, but because it correlated with the recidivism label in the training data. `CustodyStatus`, despite also correlating with race (see [confounding-variable.md](confounding-variable.md)), ends up with much lower importance here - a reminder that "correlates with a protected attribute" and "is highly ranked by this particular model" are different claims.

```python
# Feature importance after training on COMPAS data (importances summed
# back to their source column, since pd.get_dummies() one-hot-encodes
# CustodyStatus and MaritalStatus into several columns each)
importances = pd.Series(model.feature_importances_, index=X.columns)
print(importances.sort_values(ascending=False).head())

# MaritalStatus    0.4884
# race_binary      0.4208
# CustodyStatus    0.0517
# Sex_Code_Text    0.0391
```

A high importance score tells you the model relied on that feature. It does not tell you *why* the feature and the outcome are correlated - that requires the proxy analysis covered in [proxy-variables.md](proxy-variables.md).

## Concrete Example: COMPAS - Audit 01

The COMPAS dataset gives a Random Forest two protected-adjacent features: `race` and `CustodyStatus`. Trained on these alongside other inputs, the model produces an 87.16% high-risk flag rate for Black defendants versus 0.40% for White defendants - an 86.77% fairness gap.

The pattern the model found was real, in the sense that it exists in the data. Black defendants in this dataset genuinely were flagged at higher rates historically. But the pattern is not a measure of who is more likely to reoffend - it is a measure of who was more likely to be *flagged* by a system already shaped by over-policing.

```python
# unfair.py pattern: race_binary and CustodyStatus both carry signal
# (compas-scores-raw.csv has no raw `race` column - race_binary is
# derived from Ethnic_Code_Text, exactly as unfair.py does)
X = pd.get_dummies(df[['Sex_Code_Text', 'MaritalStatus', 'race_binary', 'CustodyStatus']])
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
```

When `race_binary` is dropped and `CustodyStatus` is kept, the gap falls from 86.77pp to 18.38pp - a ~79% reduction from dropping race alone, not "barely moves." Only when both `race_binary` and `CustodyStatus` are removed does the gap fall further to 15.69%, an 82% reduction overall from the original 86.77pp. `CustodyStatus`'s own marginal contribution beyond race is therefore only about 2.7 percentage points - it does not "reconstruct" the racial gap on its own, despite correlating with race (see [confounding-variable.md](confounding-variable.md) for how that correlation still matters even at low feature importance).

## Detection Code

The following functions inspect what patterns a trained model relied on, and flag features whose importance may be inflated by correlation with a protected attribute.

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from scipy.stats import chi2_contingency, pearsonr

def get_pattern_reliance(model, feature_names, top_n=10):
    """
    Return the top N features by importance from a trained
    RandomForestClassifier, paired with their importance scores.

    Parameters:
        model: a fitted RandomForestClassifier
        feature_names: list of column names matching the training matrix
        top_n: how many top features to return

    Returns:
        pandas.Series of feature importances, sorted descending
    """
    importances = pd.Series(model.feature_importances_, index=feature_names)
    return importances.sort_values(ascending=False).head(top_n)


def flag_correlated_patterns(df, protected_attr, candidate_features, threshold=0.05):
    """
    For each candidate feature, test correlation with the protected
    attribute. Categorical features use chi-squared; continuous
    features use Pearson correlation. Flags features with p < threshold
    as potentially encoding the same pattern as the protected attribute.

    Parameters:
        df: pandas.DataFrame containing both the candidate features
            and the protected attribute
        protected_attr: column name of the protected attribute
        candidate_features: list of column names to test
        threshold: p-value cutoff for flagging (default 0.05)

    Returns:
        dict mapping feature name -> (test_used, p_value, flagged: bool)
    """
    results = {}
    for feature in candidate_features:
        if pd.api.types.is_numeric_dtype(df[feature]) and df[feature].nunique() > 10:
            corr, p = pearsonr(df[feature], df[protected_attr].astype("category").cat.codes)
            results[feature] = ("pearson", p, p < threshold)
        else:
            table = pd.crosstab(df[feature], df[protected_attr])
            _, p, _, _ = chi2_contingency(table)
            results[feature] = ("chi2", p, p < threshold)
    return results


# Usage example
# importances = get_pattern_reliance(model, X_train.columns)
# flags = flag_correlated_patterns(df, "race", ["CustodyStatus", "Sex_Code_Text"])
```

## Limitations and Trade-offs

### 1. Importance scores show reliance, not causation

A high feature importance score means the model used that feature heavily. It does not mean the feature *causes* the outcome. `CustodyStatus` and recidivism are correlated through a shared history of policing patterns, not through a direct causal link from custody status to future behavior. Distinguishing correlation from causation requires domain knowledge the model does not have.

### 2. Removing high-importance features can shift the pattern elsewhere

When a strongly relied-upon feature is dropped, the forest does not simply "give up" on the pattern - it redistributes importance to whatever remaining features are next most useful for the split, whether or not those features are the ones a human would expect. In the COMPAS audit, dropping `race_binary` redistributes most of its importance to `MaritalStatus`, not to `CustodyStatus` - importance redistribution follows whatever correlational structure the remaining features happen to have, not necessarily the feature an auditor most suspects. Pattern detection at the feature level must be paired with cluster-level analysis (see [proxy-entanglement.md](proxy-entanglement.md)).

### 3. Small subgroups produce unstable importance estimates

In datasets with small demographic subgroups - such as the Asian and Hispanic groups in the Healthcare Readmission audit - feature importance and correlation statistics are sensitive to sample size. A pattern that looks strong in a subgroup of a few hundred records may not replicate at scale, and a pattern that looks weak may simply be underpowered.

### 4. Pattern detection cannot tell you which patterns are legitimate

A Random Forest treats `education.num` and `relationship` identically: both are columns with non-zero importance. Whether `education.num` is a legitimate signal for income prediction and `relationship` is an illegitimate proxy for sex is a question the algorithm has no way to answer. That judgment has to come from the proxy analysis step, performed by a human, before training.

## Related Concepts

* [What Is a Proxy Variable?](proxy-variables.md) - explains why patterns the model detects can carry protected-class signal even when the protected column itself is removed.
* [What Happens Inside a Neural Network?](neural-networks.md) - covers pattern detection in a different model family, where patterns are encoded as learned weights rather than tree splits.
* [What Are SHAP Values?](shap-values.md) - a more granular way to inspect which patterns drove a single prediction, not just the model as a whole.
* [What Is Proxy Entanglement?](proxy-entanglement.md) - what happens when a detected pattern is spread across multiple correlated features instead of concentrated in one.

## Related Projects in This Repo

* [`COMPAS/`](../COMPAS/) - the clearest example of a model detecting a pattern (race-correlated custody history) that mirrors a discriminatory outcome rather than a behavioral one.
* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - shows pattern detection across an entangled cluster of administrative features, where no single feature's importance score tells the full story.
* [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - shows a clean before/after where the patterns driving 97.3% of the fairness gap were concentrated in just two features (`gender`, `age`).

## Further Reading

* [Breiman (2001): Random Forests, *Machine Learning* 45(1)](https://link.springer.com/article/10.1023/A:1010933404324) - the original paper describing how random forests aggregate split-based pattern detection across trees.
* [Lundberg & Lee (2017): A Unified Approach to Interpreting Model Predictions, *NeurIPS*](https://arxiv.org/abs/1705.07874) - formal grounding for SHAP, the standard tool for inspecting which patterns a model used on a per-prediction basis.
* [Barocas, Hardt & Narayanan: *Fairness and Machine Learning*](https://fairmlbook.org) - chapter on classification covers the gap between statistical pattern detection and causal or normative justification.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*