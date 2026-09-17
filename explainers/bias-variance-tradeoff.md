> *Statistical bias and societal bias share a word but mean very different things. A model with high statistical bias is just too simple, making mistakes on everyone. But a model with high variance - one that memorizes the training data perfectly - often memorizes the majority group's patterns and fails the minority.*

## The One-Sentence Definition

**The bias-variance trade-off** is the tension between a model being too simple to capture real patterns (high statistical bias, or underfitting) and a model being so complex that it memorizes noise in the training data (high variance, or overfitting).

## Statistical Bias vs. Algorithmic Bias

Before applying this to fairness, we have to untangle the terminology:

- **Statistical Bias (Underfitting):** The model's assumptions are too rigid. It misses the true underlying relationship in the data. Think of drawing a straight line through a curved scatterplot.
- **Algorithmic/Societal Bias:** The model's decisions systematically disadvantage a specific demographic group, regardless of whether the model is statistically "accurate." 

A model can have low statistical bias (it fits the data perfectly) while exhibiting high algorithmic bias (it learned a prejudiced pattern). 

## Why It Matters for Fairness

When you tune a model's complexity, you are not just trading off overall accuracy. You are deciding *who* bears the cost of the model's errors.

An **underfit model** (high statistical bias) is a blunt instrument. It relies on overly simplistic rules, spreading errors somewhat broadly across the entire population. It fails equally.

An **overfit model** (high variance) is where fairness often breaks down silently. Because the training data usually contains a majority demographic group, an overfit model will dedicate its complexity to memorizing the nuanced, specific patterns of that majority group. It learns to predict them perfectly. But when it encounters a minority group applicant - whose valid patterns might look different or who are underrepresented in the training data - the brittle, overly complex rules fail to generalize. 

The result? The model performs flawlessly on the majority (low error) but makes wild, inaccurate predictions for the minority (high error), leading to severe algorithmic bias on unseen test data.

## Concrete Example: AI Fair Recruitment

Consider an automated hiring screening tool like the one in Audit 02 (AI Fair Recruitment). The training data predominantly consists of male applicants who followed traditional career paths.

If we train a very simple model (like a Decision Tree with `max_depth=1`), it might just hire everyone with more than 5 years of experience. This is **underfitting**. It misses talented juniors and over-indexes on tenure. The error rate is high for both men and women. 

If we train a highly complex model (like an unconstrained Random Forest or deep neural network), it might start combining 15 different features - memorizing that "people who play golf, went to State University, and know C++" are great hires. This is **overfitting**. Since men make up the majority of the training data, the model memorizes male-specific career trajectories. When a highly qualified woman applies with a slightly different background, the model rejects her because she doesn't match the hyper-specific, memorized majority pattern. The model generalizes beautifully for men, but fails terribly for women.

## Detection Code

You can detect if high variance is hurting a minority group by comparing the model's accuracy on the training set versus the test set, broken down by demographic group. A large train-test gap for the minority group indicates the model overfit the majority and generalized poorly to the minority.

```python
import pandas as pd
from sklearn.metrics import accuracy_score

def check_variance_by_group(model, X_train, y_train, X_test, y_test, group_col):
    """
    Measures the train-test performance gap (variance) for each demographic group.
    A large drop in test accuracy for a minority group indicates overfitting 
    that disproportionately harms them.
    
    Parameters:
        model: A trained scikit-learn classifier
        X_train, y_train: Training data and labels (must include group_col)
        X_test, y_test: Test data and labels (must include group_col)
        group_col: String name of the demographic column
    """
    results = []
    
    for group in X_train[group_col].unique():
        # Filter train and test sets by group
        train_mask = X_train[group_col] == group
        test_mask = X_test[group_col] == group
        
        if sum(train_mask) == 0 or sum(test_mask) == 0:
            continue
            
        # Get predictions (drop group_col - the model was fit on feature columns only)
        train_preds = model.predict(X_train[train_mask].drop(columns=[group_col]))
        test_preds = model.predict(X_test[test_mask].drop(columns=[group_col]))
        
        # Calculate accuracy
        train_acc = accuracy_score(y_train[train_mask], train_preds)
        test_acc = accuracy_score(y_test[test_mask], test_preds)
        
        results.append({
            "group": group,
            "train_accuracy": round(train_acc, 3),
            "test_accuracy": round(test_acc, 3),
            "generalization_gap": round(train_acc - test_acc, 3)
        })
        
    return pd.DataFrame(results).set_index("group")

# Usage example:
# gap_report = check_variance_by_group(rf_model, X_train, y_train, X_test, y_test, "gender")
# print(gap_report)
```

## Limitations

### 1. Tuning complexity does not fix bad data
You cannot hyperparameter-tune your way out of a fundamentally biased dataset. If your historical labels are discriminatory (see [Label Bias](label-bias.md)), an optimally tuned model will just learn to perfectly replicate that discrimination. 

### 2. The baseline error might still be unequal
Even if you find the perfect "sweet spot" in the bias-variance trade-off where the train-test gap is minimal for all groups, the base error rate for the minority group might still be higher simply because the model has less data to learn from them. 

### 3. Accuracy gaps are not the only measure of fairness
This detection method focuses on accuracy drops. However, a model might maintain high accuracy for a minority group but still fail on Demographic Parity or Equalized Odds. 

## Related Concepts

* [Distribution Shift](distribution-shift.md) - when the test data looks fundamentally different from the training data, exposing the brittleness of an overfit model.
* [Model Drift](model-drift.md) - how a model's generalization quality degrades over time as the real world moves away from the training patterns it memorized.
* [What Is Machine Learning Bias?](ml-bias.md) - the four entry points for bias, showing how training data composition forces these trade-offs.
* [Sampling Bias](sampling-bias.md) - why minority groups often lack enough data to build stable patterns, leading to the high-variance failures described above.

## Related Projects in This Repo

* [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - the hiring audit where complex models can easily learn to proxy gender through hyper-specific resume traits.
* [`COMPAS/`](../COMPAS/) - the recidivism audit demonstrating how risk models fail to generalize equally across racial groups.

## Further Reading

* [Hardt, M., Price, E., Srebro, N. (2016): Equality of Opportunity in Supervised Learning](https://arxiv.org/abs/1610.02413) - discusses how different groups might require different model complexities, and how forcing a single predictor can harm minority groups.
* [Chen, I., Johansson, F. D., Sontag, D. (2018): Why Is My Classifier Discriminatory?](https://arxiv.org/abs/1805.12002) - decomposes fairness metrics into bias, variance, and noise components, showing that minority group discrimination is often driven by high variance due to low sample size.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
