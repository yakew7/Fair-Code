# Explainer: What Happens Inside a Neural Network?

> *The reason a model can redline a neighborhood, deny a loan, or flag a face - without anyone writing a single rule to do it.*

---

## The One-Sentence Definition

A **neural network** is a stack of mathematical layers that repeatedly transforms an input (a resume, a face, a credit application) into a prediction - learning which patterns to amplify and which to ignore by adjusting millions of internal weights during training.

---

## Why This Matters

Most people treat neural networks as black boxes. You put data in, a decision comes out, and what happens in between is someone else's problem.

That attitude is how algorithmic bias gets deployed at scale.

The network doesn't discriminate by accident. It discriminates because of what it learned - from data that reflected a stratified world - and understanding *how* it learns is the only way to understand *what* it learns. You can't audit what you don't understand.

This explainer is not theory. It's the mechanics, so you can follow what the models in this repo are actually doing when they deny someone bail or reject a job application.

---

## The Three-Part Loop Every Network Runs

Every neural network - from a two-layer hiring classifier to a billion-parameter language model - runs the same fundamental loop:

```
Forward pass  →  Compute loss  →  Backward pass (update weights)
```

Repeat this thousands of times on your training data, and the network learns. The tragedy is that "learns" means "learns to replicate patterns in the training data" - including patterns that encode race, gender, or class.

---

## Part 1: The Forward Pass

The forward pass is how the network turns an input into a prediction.

### Neurons and Weights

Each neuron takes a set of inputs, multiplies each by a **weight**, sums them, then passes the result through an **activation function**.

```python
import numpy as np

def neuron(inputs, weights, bias):
    """
    One neuron. One decision unit.
    inputs: feature values [age, zip_code, credit_score, ...]
    weights: learned importance of each feature
    bias: a learned offset
    """
    z = np.dot(inputs, weights) + bias   # weighted sum
    return relu(z)                        # activation function

def relu(z):
    """
    ReLU: the most common activation function.
    Passes positive signals through. Kills negative ones.
    """
    return max(0, z)
```

The weight is everything. A high weight on `zip_code` means the network has learned that zip code is predictive - not because zip codes are fair inputs, but because zip codes correlate with whatever outcome existed in the training data, which was shaped by decades of redlining.

### Layers

A single neuron can only draw a straight line through the data. Layers stack neurons in sequence, letting each layer learn more abstract representations of the input.

```
Input Layer        Hidden Layer 1      Hidden Layer 2      Output Layer
─────────────      ──────────────      ──────────────      ────────────
[age          ]    [pattern_A    ]     [pattern_X    ]     
[zip_code     ] →  [pattern_B    ]  →  [pattern_Y    ]  →  [high_risk: 0.87]
[custody_status]   [pattern_C    ]     [pattern_Z    ]     
[marital_status]
```

By the final layer, the network has compressed raw input features into an abstract representation it uses to make the prediction. The problem: that representation can be heavily contaminated by proxy variables without any indication in the output.

---

## Part 2: Computing Loss

After a forward pass, the network has a prediction. It compares that prediction to the true label using a **loss function**.

```python
def binary_cross_entropy(y_true, y_pred):
    """
    The standard loss function for binary classification.
    Returns a number that measures how wrong the prediction was.
    Closer to 0 = better. Higher = worse.
    """
    epsilon = 1e-9  # prevent log(0)
    return -(y_true * np.log(y_pred + epsilon) +
             (1 - y_true) * np.log(1 - y_pred + epsilon))

# Example:
# True label: 1 (reoffended)
# Prediction: 0.87 (model is fairly confident)
loss = binary_cross_entropy(y_true=1, y_pred=0.87)
# → loss ≈ 0.14  (small - model was mostly right)

# True label: 0 (did NOT reoffend)
# Prediction: 0.87 (model is still confident, but wrong)
loss = binary_cross_entropy(y_true=0, y_pred=0.87)
# → loss ≈ 2.04  (large - model was badly wrong)
```

The network's only goal is to minimize this number across all training examples. It has no concept of fairness. It doesn't know it's making bail decisions. It will learn whatever pattern drives that number down - including racial proxies.

---

## Part 3: The Backward Pass (Backpropagation)

This is where the network learns. After computing the loss, it works backwards through every layer, calculating how much each weight contributed to the error and nudging it in the direction that reduces loss.

```python
def gradient_descent_step(weights, gradients, learning_rate=0.01):
    """
    Update every weight by a small amount in the direction that reduces loss.
    This is the core of how a network learns.
    """
    return weights - learning_rate * gradients
```

Repeat this across thousands of training examples and the weights converge - the network has "learned." What it's actually done is encode statistical patterns from the training data into its weights. If those patterns are biased, the weights are biased. If you then deploy the model, you've deployed the bias.

---

## Real-World Proof: Hiring Bias

We tested this directly using the [AI Fair Recruitment dataset](../AI%20Fair%20Recruitment/).

### What We Did

**Step 1 - Biased model (gender + declared proxy `Age` included):**

```python
features = [
    'Gender',
    'Age',            # declared proxy in audit.yaml
    'Experience_Years',
    'Technical_Test_Score'
]
```

**Results:**

| Group | Hire Rate |
|---|---|
| Male candidates | 21.62% |
| Female candidates | 17.59% |
| **Fairness gap** | **4.03 percentage points** |

The network didn't contain a rule that said "prefer men." It learned from historical hiring data in which men were hired more. The weights encoded that pattern. The bias was invisible - buried in floating-point numbers across hidden layers.

---

**Step 2 - Remove gender + proxy (our fix):**

```python
features = [
    # Gender removed ✓
    # Age removed ✓  (declared proxy in audit.yaml)
    'Experience_Years',
    'Technical_Test_Score'
]
```

**Result:** the fairness gap closes to **0.16 percentage points**.

### Summary

| Approach | Fairness Gap | Reduction |
|---|---|---|
| Biased model | 4.03% | - |
| Remove gender only (keep Age) | 0.23% | 94% |
| Remove gender + proxy | 0.16% | **96.1%** |

**The network's architecture didn't change. The training procedure didn't change. Only the inputs changed - and the bias disappeared.**

---

## How to Inspect What a Network Learned

Neural networks are not fully interpretable, but you can probe them.

### SHAP Values: Attributing Predictions to Features

SHAP (SHapley Additive exPlanations) decomposes any prediction into a contribution from each input feature.

```python
import shap
from sklearn.ensemble import RandomForestClassifier

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# For one prediction, SHAP tells you:
# age contributed +0.34 to the high-risk score
# zip_code contributed +0.28
# custody_status contributed +0.19
# ...
```

If a protected attribute or its known proxy appears at the top of the SHAP rankings, the model is using it - regardless of what the feature list says it's "supposed" to be doing.

### Feature Importance: Coarser But Faster

```python
import pandas as pd

importances = pd.Series(
    model.feature_importances_,
    index=X_train.columns
).sort_values(ascending=False)

print(importances)
# custody_status      0.31   ← if this is high, you have a proxy problem
# zip_code            0.27
# marital_status      0.18
# ...
```

Any feature at the top that you know correlates with a protected attribute is a proxy variable. Remove it and retrain.

---

## The Architecture in One Diagram

```
RAW FEATURES             HIDDEN LAYERS              PREDICTION
────────────────         ───────────────────────    ──────────────────────
age ──────────────┐
zip_code ─────────┤      [weighted sum]    [weighted sum]
custody_status ───┼──→   [   + bias  ] →  [   + bias  ] →  0.87 (high-risk)
marital_status ───┤      [    relu   ]    [    relu   ]
sex ──────────────┘
                          ↑                ↑
                          learned from     learned from
                          training data    training data

                   ←────────────────────────────────────
                         backpropagation adjusts all
                         these weights to minimize loss
```

The network has no fairness objective. It has one objective: minimize loss on the training set. If the training set encodes historical discrimination, minimizing loss means learning that discrimination.

---

## The Bigger Picture

Neural networks are not neutral calculators. They are compression algorithms for historical patterns. Feed them data from a world shaped by redlining, over-policing, occupational segregation, and lending exclusion - and they will compress those patterns into their weights and reproduce them as predictions.

The architecture is not the problem. The weights are the problem. And the weights are determined by the data.

This is why the work in this repository matters: not to fix the math, but to fix the inputs. Remove the protected attributes. Audit every remaining feature for correlation with those attributes. Retrain. Measure the gap again.

**A neural network will learn exactly what you teach it. The question is whether you're paying attention to what that is.**

---

## Related Projects in This Repo

- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - Full hiring bias audit: 96.1% gap reduction after removing gender + age proxy
- [`German Credit Lending/`](../German%20Credit%20Lending/) - Lending bias: 73.6% gap reduction after removing age + employment tenure proxy
- [`Insurance Denial/`](../Insurance%20Denial/) - Healthcare bias: 60–72% reduction after removing BMI, smoking status, and diabetes status as proxies
- [`Benefits Denial/`](../Benefits%20Denial/) - Welfare eligibility: 46–88% gap reduction across race, sex, and national origin

---

## Further Reading

- [3Blue1Brown: Neural Networks (YouTube, 2017)](https://www.youtube.com/watch?v=aircAruvnKk) - the best visual introduction to how networks learn
- [Goodfellow, Bengio & Courville: Deep Learning (MIT Press)](https://www.deeplearningbook.org/) - the canonical textbook, free online
- [Lundberg & Lee: A Unified Approach to Interpreting Model Predictions (NeurIPS, 2017)](https://arxiv.org/abs/1705.07874) - the SHAP paper
- [Barocas & Hardt: Fairness and Machine Learning](https://fairmlbook.org/) - the standard reference for algorithmic fairness

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
