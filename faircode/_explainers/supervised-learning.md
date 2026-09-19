> *Supervised learning has no opinion about fairness. It has one job - find the mapping from input to label - and it will find a discriminatory mapping just as faithfully as a fair one, because faithfulness to the data is the entire point.*

## The One-Sentence Definition

**Supervised learning** trains a model by showing it many examples of inputs paired with correct labels, so it learns a mapping that generalises to inputs it has never seen before.

## Why It Matters

87% of companies now use AI to screen job applicants before a human reads a resume. Every one of those screening models, and every credit scorer, recidivism tool, and insurance triage system in this repo, is built the same way: show the model historical inputs and historical outcomes, let it find the mapping between them, then apply that mapping to new people. The AI Fair Recruitment audit is a direct example - gender, age, experience, and test scores go in, a hire/no-hire decision comes out, and the model reproduces a 4.51 percentage point gender gap without ever being told gender should matter.

The non-obvious part is that this is not a malfunction. Supervised learning is not designed to check whether a pattern is legitimate signal or historical prejudice - it is designed to find *any* pattern that predicts the label, and it has no way to tell the two apart. A model that "learned to discriminate" did exactly what it was built to do: it found the mapping that best explains the labels it was shown. If that mapping includes a gender penalty, the model did not invent one. It found one that was already there.

## How It Works

### From Examples to a Mapping

A supervised learning problem has three parts: a set of input features (`Gender`, `Age`, `Experience_Years`, `Technical_Test_Score`), a label that represents the "correct" answer for each historical example (`Hiring_Decision`), and a model whose job is to find a function from the first to the second. Training does not mean the model is told any rules. It means the model is shown thousands of `(features, label)` pairs and adjusts itself until its own outputs match those labels as closely as possible. Once that mapping is fixed, it gets applied to people the model has never seen, on the assumption that whatever relationship held in the training examples will hold for them too.

### Walking Through `unfair.py`

The AI Fair Recruitment audit's biased model is a clean example of the mechanism with nothing hidden:

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

X = pd.get_dummies(df[['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score']])
y = df['Hiring_Decision']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)
predictions = model.predict(X_test)
```

`train_test_split` sets aside 20% of the historical examples so the model's generalization can be checked on rows it never trained on. `model.fit(X_train, y_train)` is the entire learning step - the Random Forest searches for splits across `Gender`, `Age`, `Experience_Years`, and `Technical_Test_Score` that best separate hired from not-hired in the training labels. `model.predict(X_test)` applies that learned mapping to the held-out rows. Nothing in this code path checks whether the mapping it found leans on `Gender` for a legitimate reason or an illegitimate one - the fit step optimises for one thing only: matching the labels it was shown.

### Two Different Kinds of Labels

The German Credit Lending audit is a useful second example because its label is a different kind of "ground truth." Where `Hiring_Decision` in the recruitment dataset is a direct historical human decision, the credit dataset's `class` (good/bad credit) label is closer to an observed outcome. Both are still supervised learning in exactly the same structural sense - features in, label out, mapping learned - and both still let a protected attribute back in through a correlated feature. In lending it is `employment` tenure standing in for `age`; in hiring, historical hiring patterns stand in for gender. The mechanism does not care what kind of label it is given. It treats a human decision and an observed outcome identically: as ground truth to be reproduced.

## Concrete Example: AI Fair Recruitment - Audit 02

The AI Fair Recruitment dataset pairs applicant features (gender, age, years of experience, technical test score) with a historical `Hiring_Decision` label. Trained on all four features, the model reproduced a hiring gap that closely tracked gender rather than the merit-based inputs alone.

| Group | Hire Rate |
|-------|:---------:|
| Men | 21.62% |
| Women | 17.10% |
| **Fairness Gap** | **4.51%** |

The model was never given a rule about gender. It inferred the gap because a gap already existed in the training labels, and inferring existing patterns is exactly what `model.fit()` does.

```python
# THE FIX: Merit only
X = df[['Experience_Years', 'Technical_Test_Score']]
# gender removed ✓
# age removed ✓
```

Retraining on experience and test score alone - the two features that plausibly measure job-relevant merit - collapsed the gap:

| Group | Hire Rate |
|-------|:---------:|
| Men | 11.48% |
| Women | 11.35% |
| **New Fairness Gap** | **0.12%** |

A 97.3% reduction, achieved without touching the learning algorithm at all. Same Random Forest, same `fit()` call, same `random_state=42` - the only thing that changed was which columns the mapping was allowed to use.

## Detection Code

The functions below train a supervised classifier on labeled data, then check whether the gap present in the original labels reappears in the model's own predictions on held-out data.

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split


def train_supervised_classifier(df, feature_cols, label_col, test_size=0.2, random_state=42):
    """
    Trains a Random Forest classifier on (features -> label) pairs.

    Parameters:
        df: DataFrame containing the feature columns and the label column.
        feature_cols: list of column names to use as input features.
        label_col: name of the column holding the ground-truth label.
        test_size: fraction of rows held out for testing.
        random_state: seed for reproducible splits and training.

    Returns:
        (model, X_test, y_test, predictions) - the fitted model, the held-out
        test features, their true labels, and the model's predictions on them.
    """
    X = pd.get_dummies(df[feature_cols])
    y = df[label_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    model = RandomForestClassifier(random_state=random_state)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    return model, X_test, y_test, predictions


def compare_label_vs_prediction_gap(df, protected_col, label_col, test_index, predictions):
    """
    Compares the positive-rate gap in the original training labels against the
    gap in the model's predictions on the held-out test rows, to show whether
    the model reproduced a pattern that was already present in the labels.

    Parameters:
        df: the full DataFrame (used to look up the protected attribute).
        protected_col: column name of the protected attribute (e.g. 'gender').
        label_col: name of the ground-truth label column.
        test_index: index of the held-out test rows (X_test.index).
        predictions: the model's predicted labels for those same rows.

    Returns:
        dict with the label gap, the prediction gap, and both group rates.
    """
    test_df = df.loc[test_index].copy()
    test_df["prediction"] = predictions

    label_rates = test_df.groupby(protected_col)[label_col].mean()
    pred_rates = test_df.groupby(protected_col)["prediction"].mean()

    groups = label_rates.index
    label_gap = abs(label_rates[groups[0]] - label_rates[groups[1]])
    pred_gap = abs(pred_rates[groups[0]] - pred_rates[groups[1]])

    return {
        "label_gap_pct": round(label_gap * 100, 2),
        "prediction_gap_pct": round(pred_gap * 100, 2),
        "label_rates": label_rates.to_dict(),
        "prediction_rates": pred_rates.to_dict(),
    }

# Usage example
# model, X_test, y_test, preds = train_supervised_classifier(
#     df, ['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score'], 'Hiring_Decision'
# )
# compare_label_vs_prediction_gap(df, 'Gender', 'Hiring_Decision', X_test.index, preds)
```

## Limitations and Trade-offs

### 1. The Label Is Always a Proxy for the Real Target

"Hired" is not the same thing as "best candidate." It is what a human decision-maker did, filtered through whatever biases that person carried. Supervised learning cannot distinguish a label that reflects the true target from a label that reflects a flawed historical process, because it is only ever shown the label. Choosing what counts as ground truth is a judgment call made before any code runs, not something the training step can correct for. See [What Is Label Bias?](label-bias.md) for how far this problem extends.

### 2. Matching the Labels Is Not the Same as Fairness

A model that reproduces its training labels with high accuracy has done its job by the only definition it has - and can still have a large fairness gap, because accuracy is measured in aggregate while a fairness gap is measured between groups. A 95% accurate model can be 95% accurate for men and 70% accurate for women and still report 95% overall. The learning objective has no term for "equal treatment" unless someone adds one.

### 3. The Mapping Expires

A model learns the relationship between features and labels *as it existed in the training data at the time it was collected*. If the applicant pool changes, if hiring practices shift, or if the model is deployed on a different population than it was trained on, the learned mapping stops describing reality. Supervised learning has no built-in signal that this has happened - it will keep applying the old mapping with the same confidence. See [What Is Distribution Shift?](distribution-shift.md).

### 4. generalization Assumes the Future Looks Like the Past

The entire premise of a train/test split is that held-out rows are a fair preview of new, unseen cases. That assumption holds when the test set is drawn from the same process as future real-world inputs, and breaks down when it isn't - for instance, if the training data under-represents a group, the model's confidence on that group can be misleadingly high even at evaluation time, not just after deployment.

## Related Concepts

* [What Is Label Bias?](label-bias.md) - covers why the labels themselves are already tainted before any model ever sees them; this explainer covers how faithfully the model reproduces whatever is in them.
* [What Is Machine Learning Bias?](ml-bias.md) - places labels as one of four entry points bias can use to reach a model, alongside training data, proxies, and feedback loops.
* [What Is Distribution Shift?](distribution-shift.md) - what happens to a learned mapping after deployment, once the population it was trained on stops matching the population it is applied to.
* [What Is Calibration?](calibration.md) - a deeper look at why a model can be accurate overall while still treating groups unequally.

## Related Projects in This Repo

* [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - the primary anchor for this explainer: a hire/no-hire label learned from historical decisions, reproducing a 4.51 percentage point gender gap until gender and age are dropped from the feature set.
* [`German Credit Lending/`](../German%20Credit%20Lending/) - a second supervised task with a different label type (credit outcome rather than a hiring decision), showing the same mechanism reproduce an age gap through the `employment` tenure proxy.

## Further Reading

* [Hastie, Tibshirani & Friedman (2009): The Elements of Statistical Learning](https://hastie.su.domains/ElemStatLearn/) - the standard formal treatment of supervised learning as function estimation from labeled examples.
* [Barocas, Hardt & Narayanan: Fairness and Machine Learning](https://fairmlbook.org/) - formalises how the standard supervised learning setup, unmodified, produces and hides disparate outcomes.
* [Mehrabi et al. (2021): A Survey on Bias and Fairness in Machine Learning, ACM Computing Surveys](https://dl.acm.org/doi/10.1145/3457607) - surveys how bias enters supervised learning pipelines at the data, label, and modeling stages.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*