> *When 99% of your data belongs to one group, a model can hit 99% accuracy by simply ignoring the 1% that matters most - like a rare disease, a fraudulent transaction, or a readmitted patient. Fixing the imbalance by oversampling forces the model to pay attention, but it can also force a massive increase in false positive rates for historically marginalized groups.*

## The One-Sentence Definition

**Class imbalance** occurs when one outcome in a dataset is overwhelmingly more frequent than another, causing algorithms optimizing for overall accuracy to practically ignore the minority class, which often represents the most critical events.

## Why It Matters

In high-stakes domains like healthcare, finance, and criminal justice, the events we care about predicting - a patient readmission, a fraudulent transaction, a default - are rare. When a dataset is 99% negative cases and 1% positive cases, the mathematically optimal path to high accuracy is to predict "negative" every single time. 

This creates two immediate problems for fairness. First, the model achieves its high score by failing completely on the very cases it was built to find (the minority class), disproportionately harming the groups most vulnerable to those events. Second, when engineers try to "fix" the imbalance - usually by oversampling the rare cases, undersampling the majority, or applying class weights - they fundamentally alter the model's decision boundary. A model aggressively tuned to find rare positive cases will flag many more people, drastically increasing the false positive rate. For historically marginalized groups, this often translates to being wrongly denied a loan, wrongly suspected of fraud, or subjected to unnecessary interventions.

## Concrete Example: Healthcare Readmission - Audit 06

Audit 06 in this repo predicts 30-day hospital readmissions using the Diabetes 130-US Hospitals dataset. Like most clinical prediction tasks, readmission is a relatively rare event compared to safe discharges. The baseline models flag only a tiny fraction of patients as high clinical risk, and the exact fraction varies noticeably by model family: logistic regression flags about 0.4%, random forest about 0.2%, and gradient boosting about 0.3%.

When an outcome is this rare, standard machine learning classifiers struggle to learn the pattern of the minority class. A model could simply output "no readmission" for everyone and achieve near-perfect global accuracy, completely missing the patients who actually need follow-up care.

If an engineering team steps in and applies a resampling technique like SMOTE (Synthetic Minority Over-sampling Technique) to force the model to learn the readmission pattern, the model will indeed find more true positives. However, because proxy variables for race and insurance access (like payer code and discharge destination) are heavily entangled with the outcome, the newly aggressive model will not spread its false positives evenly. It will over-flag the demographic groups most associated with those proxies, trading a high-accuracy but useless model for one that actively discriminates through false alarms.

## Detection Code

Detecting the impact of class imbalance requires looking past global accuracy. `balanced_accuracy_score` averages recall across both classes, preventing a massive negative class from hiding the failure on the positive class.

```python
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE

def audit_imbalance(X, y, protected_attribute):
    """
    Demonstrates how global accuracy hides failure on the minority class,
    and how fixing the imbalance affects the false positive rate per group.
    """
    # Split data
    X_train, X_test, y_train, y_test, group_train, group_test = train_test_split(
        X, y, protected_attribute, test_size=0.2, random_state=42
    )

    # 1. Naive Model (suffers from imbalance)
    clf_naive = RandomForestClassifier(random_state=42)
    clf_naive.fit(X_train, y_train)
    y_pred_naive = clf_naive.predict(X_test)
    
    print("--- NAIVE MODEL ---")
    print(f"Global Accuracy:   {accuracy_score(y_test, y_pred_naive):.4f}")
    print(f"Balanced Accuracy: {balanced_accuracy_score(y_test, y_pred_naive):.4f}")
    
    # 2. Resampled Model (fixing imbalance with SMOTE)
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train, y_train)
    
    clf_resampled = RandomForestClassifier(random_state=42)
    clf_resampled.fit(X_train_resampled, y_train_resampled)
    y_pred_resampled = clf_resampled.predict(X_test)
    
    print("\\n--- RESAMPLED MODEL (SMOTE) ---")
    print(f"Global Accuracy:   {accuracy_score(y_test, y_pred_resampled):.4f}")
    print(f"Balanced Accuracy: {balanced_accuracy_score(y_test, y_pred_resampled):.4f}")
    
    # Analyze False Positive Rates by group
    print("\\n--- FALSE POSITIVE RATES (RESAMPLED) ---")
    results = pd.DataFrame({'y_true': y_test, 'y_pred': y_pred_resampled, 'group': group_test})
    for group, sub in results.groupby('group'):
        tn, fp, fn, tp = confusion_matrix(sub['y_true'], sub['y_pred'], labels=[0, 1]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        print(f"Group {group} FPR: {fpr:.2%}")

# Usage example:
# audit_imbalance(X, y_imbalanced, df['Race'])
```

`imbalanced-learn` (the `imblearn` import above) is not part of this repo's own `requirements-lock.txt` - it is an illustrative external dependency, not something this repo's own audits install or run. Install it separately to run the code above:

```bash
pip install imbalanced-learn
```

## Limitations

### 1. Oversampling risks overfitting
Techniques like simple oversampling duplicate minority records, leading the model to memorize specific examples rather than learning generalizable patterns. This makes the model look fantastic on training data but brittle in production.

### 2. SMOTE creates synthetic noise
SMOTE generates fake minority-class examples by interpolating between real ones. If the real examples are noisy or if the decision boundary is complex, SMOTE can generate impossible data points that confuse the model, degrading overall performance.

### 3. Undersampling discards valuable data
To balance classes, undersampling throws away large portions of the majority class. In domains where every data point is expensive to collect (like clinical trials), discarding data to achieve mathematical balance is often unacceptable.

### 4. Resampling breaks calibration
Models trained on a 50/50 resampled dataset will output scores that assume the world is actually 50/50. The predicted probabilities will be drastically overconfident and uncalibrated for the real world, meaning the raw scores cannot be trusted without post-training probability calibration.

## Related Concepts

* [What Is a ROC Curve and AUC?](roc-curve-auc.md) - why AUC is mathematically robust to class imbalance, even when raw accuracy fails.
* [False Positives vs. False Negatives in Medical Risk Models](false-positives-vs-false-negatives.md) - how resampling to catch more rare positive cases inevitably trades off against the false positive rate.
* [What Is Sampling Bias?](sampling-bias.md) - when the imbalance is not a reflection of the real world, but a flaw in how the data was collected.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the audit demonstrating how extremely rare clinical flags interact with structural proxy variables, making aggressive resampling risky for fairness.

## Further Reading

* [Chawla, N. V., et al. (2002): SMOTE: Synthetic Minority Over-sampling Technique](https://arxiv.org/abs/1106.1813) - the foundational paper on generating synthetic examples to combat class imbalance.
* [Weiss, G. M. (2013): Foundations of Imbalanced Learning](https://doi.org/10.1002/9781118646106.ch2) - a comprehensive overview of why standard algorithms fail on skewed data and the trade-offs of various mitigation strategies.
* [Barocas, S., Hardt, M., Narayanan, A. (2019): *Fairness and Machine Learning*](https://fairmlbook.org/) - discusses how base rate differences between demographic groups create tensions when balancing error rates.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
