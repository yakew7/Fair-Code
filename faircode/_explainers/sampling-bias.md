# Explainer: What Is Sampling Bias?

> *The reason your AI works great in the lab and fails on the people who need it most.*

---

## The One-Sentence Definition

**Sampling bias** occurs when the data used to train an AI system doesn't accurately represent the population it will be deployed on - so the model learns patterns that don't generalize, performing well for over-represented groups and failing for under-represented ones.

---

## Why This Matters

Most people assume that if you have a large dataset, the model will be fair. This is wrong.

Size doesn't equal representativeness. A dataset of 10 million records is still biased if 9.8 million of them come from the same demographic. The model doesn't know what it hasn't seen. It optimizes for the distribution it was trained on - and when that distribution doesn't match the real world, the people left out pay the price.

This is called **sampling bias**, and it shows up in facial recognition systems that fail on darker skin tones, clinical tools that miss diagnoses in women, and NLP models that perform worse on dialects outside Standard American English. In each case, the data collection process systematically excluded certain groups - and the model inherited that exclusion.

---

## Common Forms of Sampling Bias

| Form | What It Means | Real Example |
|---|---|---|
| **Underrepresentation** | A demographic group appears far less in training data than in the real world | Facial recognition trained mostly on light-skinned faces |
| **Selection bias** | Data is collected from a non-random subset of the population | Clinical AI trained on hospital records from affluent ZIP codes |
| **Historical bias** | Past data reflects past inequities; the model learns the inequity, not the truth | Hiring models trained on 10 years of male-dominated engineering hires |
| **Survivorship bias** | Only "successful" cases make it into the dataset; failures are invisible | Loan models trained only on approved applicants, never denied ones |
| **Temporal bias** | Training data is from a time period that no longer reflects current reality | A model trained on 2005 internet text used today |
| **Measurement bias** | The same underlying reality is measured differently for different groups | Over-policing means more arrest records for Black communities - not higher crime rates |

---

## Real-World Proof: MIT Gender Shades

The clearest documented case of sampling bias in AI is the Gender Shades study (Joy Buolamwini & Timnit Gebru, 2018).

Three commercial facial recognition systems were tested on a dataset specifically balanced across gender and skin tone. The results showed that every system performed dramatically worse on darker-skinned women - not because the algorithms were explicitly programmed to fail them, but because the training datasets were overwhelmingly composed of lighter-skinned faces.

| Group | Error Rate (best system) | Error Rate (worst system) |
|---|---|---|
| Lighter-skinned males | ~0.8% | ~3.4% |
| Lighter-skinned females | ~1.7% | ~7.1% |
| Darker-skinned males | ~10.8% | ~16.0% |
| Darker-skinned females | **~20.8%** | **~34.7%** |

The gap between best-case (lighter males) and worst-case (darker females) was **up to 34 percentage points** - from the same model, on the same task, because of who was and wasn't in the training data.

The fix was not a new algorithm. It was a more representative dataset.

---

## Simulating Sampling Bias

The following example simulates what happens when you train on an unbalanced sample and test on a balanced one. This mirrors the real-world failure mode exactly.

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

np.random.seed(42)

# Simulate a population: two groups with similar underlying skill distributions
n = 5000
group_a = pd.DataFrame({
    'skill_score': np.random.normal(75, 10, n),
    'group': 'A'
})
group_b = pd.DataFrame({
    'skill_score': np.random.normal(74, 10, n),  # Nearly identical
    'group': 'B'
})

# True hire threshold: skill_score >= 70
group_a['hired'] = (group_a['skill_score'] >= 70).astype(int)
group_b['hired'] = (group_b['skill_score'] >= 70).astype(int)

# BIASED SAMPLE: Group A is over-represented 9:1 in training data
train_a = group_a.sample(900, random_state=42)
train_b = group_b.sample(100, random_state=42)  # ← 10x undersampled
train = pd.concat([train_a, train_b]).sample(frac=1, random_state=42)

# Balanced test set (real-world deployment: equal numbers)
test_a = group_a.drop(train_a.index).sample(500, random_state=42)
test_b = group_b.drop(train_b.index).sample(500, random_state=42)
test = pd.concat([test_a, test_b])

# Train on biased sample
X_train = train[['skill_score']]
y_train = train['hired']
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

# Evaluate on balanced test set
test['predicted'] = clf.predict(test[['skill_score']])
results = test.groupby('group').apply(
    lambda x: pd.Series({
        'accuracy': accuracy_score(x['hired'], x['predicted']),
        'positive_rate': x['predicted'].mean()
    })
)

print("--- BIASED TRAINING SAMPLE RESULTS ---")
print(results.round(4))
print(f"\nAccuracy gap: {abs(results.loc['A','accuracy'] - results.loc['B','accuracy']):.4f}")
print(f"Positive rate gap: {abs(results.loc['A','positive_rate'] - results.loc['B','positive_rate']):.4f}")
```

**What you'll see:** both groups end up with near-perfect, nearly identical accuracy (~0.998-1.000) - accuracy alone hides the problem entirely. The real distortion shows up in the positive rate: Group B, the undersampled group, gets predicted "hired" noticeably less often than Group A (about an 8-point gap), despite having nearly identical underlying skill scores. The bias is entirely a function of who was in the training data, not who deserves to be hired - and it is invisible to an accuracy-only check.

---

## How to Detect Sampling Bias

```python
import pandas as pd
from scipy.stats import chi2_contingency

def audit_representation(df, group_col, expected_proportions=None):
    """
    Audit whether a dataset represents each group
    in proportion to their real-world population.
    
    expected_proportions: dict like {'A': 0.5, 'B': 0.5}
    If None, checks whether groups are roughly equal.
    Returns a summary DataFrame with over/underrepresentation flags.
    """
    counts = df[group_col].value_counts()
    proportions = df[group_col].value_counts(normalize=True)
    
    audit = pd.DataFrame({
        'count': counts,
        'dataset_proportion': proportions.round(4)
    })
    
    if expected_proportions:
        audit['expected_proportion'] = pd.Series(expected_proportions)
        audit['representation_ratio'] = (
            audit['dataset_proportion'] / audit['expected_proportion']
        ).round(4)
        audit['flag'] = audit['representation_ratio'].apply(
            lambda r: 'OVERREPRESENTED' if r > 1.5
                      else 'UNDERREPRESENTED' if r < 0.67
                      else 'OK'
        )
    
    return audit

# Example: Check representation in a hiring dataset
df = pd.read_csv('your-dataset.csv')
real_world_proportions = {'men': 0.51, 'women': 0.49}  # Adjust to your domain
result = audit_representation(df, 'gender', real_world_proportions)
print(result)

# Any group flagged UNDERREPRESENTED should be treated with caution.
# Options: oversample, collect more data, apply sample weights, or use fairness-aware training.
```

Run this before any training run. A group flagged `UNDERREPRESENTED` means the model will have less signal to learn from for that group - and more opportunity to get it wrong.

---

## How to Mitigate It

Detecting sampling bias is step one. Fixing it requires one of the following strategies, chosen based on how severe the imbalance is and how much data you can realistically collect:

**1. Collect more data** - the cleanest fix. Go get more samples from underrepresented groups before training. Not always possible, but always preferable when it is.

**2. Oversample** - repeat underrepresented examples during training so the model sees them more often. Simple and effective for moderate imbalances.

```python
from sklearn.utils import resample

minority = train[train['group'] == 'B']
majority = train[train['group'] == 'A']

minority_upsampled = resample(minority, replace=True, n_samples=len(majority), random_state=42)
balanced_train = pd.concat([majority, minority_upsampled])
```

**3. Apply sample weights** - tell the model to penalize errors on underrepresented groups more heavily. Works well when you can't change the dataset itself.

```python
from sklearn.utils.class_weight import compute_sample_weight

weights = compute_sample_weight('balanced', y=y_train)
clf.fit(X_train, y_train, sample_weight=weights)
```

**4. Stratified splits** - always split train/test data in a way that preserves group proportions. Prevents the test set itself from being biased.

```python
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=df['group'], random_state=42
)
```

---

## The Bigger Picture

Sampling bias is not a technical accident. It reflects who had access to the systems that generated the data in the first place. Facial recognition datasets are biased toward lighter-skinned faces because the researchers who collected them moved in predominantly lighter-skinned professional environments. Clinical AI is biased toward wealthy patients because hospitals in wealthy ZIP codes have better electronic health record infrastructure. NLP models are biased toward Standard American English because that's what most of the training corpus is written in.

The data you have is a record of the world as it was - including which people were visible, documented, and deemed worth measuring. A model trained on that data will reproduce those visibility decisions at scale.

**You cannot fix a representativeness problem with a better algorithm. You fix it with better data - or you disclose the limitation and restrict deployment accordingly.**

---

## Relationship to Other Concepts

Sampling bias is distinct from - but connected to - other fairness failure modes:

- **Proxy variables** encode protected attributes through correlated features. Sampling bias encodes them through who was included in the data at all. Both must be audited independently. See [`proxy-variables.md`](proxy-variables.md).
- **Demographic parity** (coming soon) measures whether positive prediction rates are equal across groups. Sampling bias is one of the root causes of demographic parity violations.
- **Measurement bias** is a sibling concept: the same feature (e.g., arrest records) means different things for different groups because it's collected differently. Sampling bias is about *who* is counted; measurement bias is about *how* they're counted.

---

## Further Reading

- [Buolamwini & Gebru: Gender Shades (2018)](http://proceedings.mlr.press/v81/buolamwini18a.html) - the foundational study on facial recognition sampling bias
- [Obermeyer et al.: Dissecting racial bias in an algorithm used to manage the health of populations (Science, 2019)](https://science.sciencemag.org/content/366/6464/447) - survivorship and selection bias in clinical AI
- [Bender et al.: On the Dangers of Stochastic Parrots (2021)](https://dl.acm.org/doi/10.1145/3442188.3445922) - sampling bias in large language model training corpora

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
