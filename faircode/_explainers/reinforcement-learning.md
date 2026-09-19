# Explainer: What Is Reinforcement Learning?

> *The reason an algorithm can lock someone up longer, flood your feed with outrage, and never once be told it did anything wrong.*

---

## The One-Sentence Definition

**Reinforcement learning** is a training approach where an agent learns to make decisions by receiving numerical rewards or penalties based on the outcomes of its actions, rather than from labelled examples - and in high-stakes domains, whoever defines the reward function decides whose outcomes count.

---

## Why This Matters

Most ML explainers treat reinforcement learning as a curiosity: robots learning to walk, agents beating chess engines. That framing misses where RL is actually deployed.

Parole boards use risk-score systems that function like RL policies - they encode a learned mapping from defendant profile to release/hold decision, shaped by feedback from observed reoffense rates. Content recommendation engines on platforms serving billions of users are trained with RL, optimising watch time as the reward signal. Credit and insurance pricing increasingly uses RL-style optimisation to set individualised rates based on behavioural feedback.

In every one of these cases, the reward function was written by a person who had to decide what "good" means. That decision is not technical. It is political. And once the reward function is fixed, the agent will do whatever it takes to maximise it - including exploiting demographic proxies, amplifying historical patterns, and hacking the metric in ways the designer never anticipated.

You can't audit what you don't understand. This explainer is the mechanics.

---

## The Three-Part Loop Every RL System Runs

Every reinforcement learning system - from a toy grid-world to a production-scale parole risk model - runs the same fundamental loop:

```
Observe state  →  Take action  →  Receive reward  →  Update policy
```

Repeat this across thousands or millions of interactions, and the agent learns a **policy**: a mapping from states to actions that maximises cumulative reward. The tragedy is that "maximises reward" means "maximises the specific scalar you defined" - not fairness, not accuracy, not justice.

---

## Part 1: State, Action, and Policy

The agent observes the world as a **state**, chooses an **action**, and updates its **policy** - the internal rulebook that maps states to actions.

### What These Look Like in Practice

```python
import numpy as np

# In a parole decision system:
state = {
    "age": 27,
    "prior_arrests": 3,
    "custody_status": "pretrial",    # proxy for race via over-policing
    "zip_code": "60619",             # proxy for race via redlining
    "employment": "part-time"
}

# The agent's action space
ACTIONS = ["recommend_release", "recommend_hold"]

# The policy maps states to action probabilities
def policy(state, weights):
    """
    A learned function that takes a state and returns
    the probability of each action.
    weights: the agent's internal parameters, updated by training
    """
    score = np.dot(encode_state(state), weights)
    p_hold = sigmoid(score)
    return {"recommend_hold": p_hold, "recommend_release": 1 - p_hold}

def sigmoid(z):
    return 1 / (1 + np.exp(-z))
```

The weights are everything. A high weight on `custody_status` means the agent has learned that pretrial detention predicts its reward signal - not because custody status is a fair input, but because it correlates with reoffense rates that were themselves shaped by selective policing.

### The Policy Update

After each interaction, the agent adjusts its weights in the direction that increases expected future reward. The most common update rule is a variant of gradient ascent on the expected return:

```python
def policy_gradient_step(weights, log_prob_gradient, reward, baseline, learning_rate=0.01):
    """
    REINFORCE update: move weights in the direction that makes
    rewarded actions more probable.

    log_prob_gradient: how much each weight affected the action's probability
    reward: what the environment returned
    baseline: a running average reward, subtracted to reduce variance
    """
    advantage = reward - baseline
    return weights + learning_rate * log_prob_gradient * advantage
```

If "no reoffense in 6 months" is the reward and a particular demographic profile correlates historically with that outcome, the agent will learn to treat that profile as high-value - regardless of whether the correlation is causal or merely a product of who gets monitored and who does not.

---

## Part 2: The Reward Function

The reward function is the most consequential design decision in any RL system. It is also the most politically loaded.

```python
def parole_reward(action, outcome):
    """
    A simplified reward function for a parole decision agent.
    Every number here is a value judgment.
    """
    if action == "recommend_release" and outcome == "no_reoffense":
        return +1.0    # correct release - rewarded
    elif action == "recommend_hold" and outcome == "would_have_reoffended":
        return +0.5    # correct hold - rewarded
    elif action == "recommend_release" and outcome == "reoffense":
        return -2.0    # false release - penalised heavily (political cost)
    elif action == "recommend_hold" and outcome == "would_not_have_reoffended":
        return -0.1    # false hold - penalised lightly (low political cost)
    # The asymmetry above is not neutral.
    # It encodes the judgment that wrongful incarceration costs five times
    # less than a reoffense - a value choice, not a mathematical truth.
```

This asymmetry has a direct consequence: the agent will hold defendants at the margin more aggressively, because the penalty for a missed reoffense is ten times the penalty for a wrongful hold. Who lives "at the margin"? Whoever the state already treated as high-risk. The reward function launders that judgment as optimisation.

### Reward Hacking

Agents optimise the specified reward signal, not the intended objective. When these diverge, the result is **reward hacking**.

```python
# Intended objective:
# Accurately predict who will reoffend, regardless of demographics.

# Reward signal:
# Maximise accuracy on historical reoffense records.

# What the agent learns:
# Historical records reflect selective enforcement.
# Communities that were over-policed have higher documented reoffense rates.
# Optimising on those records means learning to predict policing patterns,
# not underlying criminal behaviour.

# The agent achieves high reward. The objective is not met.
# The bias is not a bug. It is the correct solution to the wrong problem.
```

---

## Part 3: The Credit Assignment Problem

RL's hardest technical challenge is also its deepest fairness problem: how do you attribute an outcome to the decision that caused it when the outcome arrives much later?

```python
def discounted_return(rewards, gamma=0.95):
    """
    Discount future rewards by gamma at each step.
    A reward received 10 steps from now is worth gamma^10 ≈ 0.60 of its face value.
    A reward received 50 steps from now is worth gamma^50 ≈ 0.08.

    In a parole system where 'success' is measured at 6 months:
    - Immediate indicators (employment, housing) get high credit.
    - Structural factors (neighbourhood disinvestment, lack of support) arrive later
      and are discounted away - even if they are the actual causes.
    """
    G = 0
    returns = []
    for r in reversed(rewards):
        G = r + gamma * G
        returns.insert(0, G)
    return returns

# The agent cannot assign credit to the parole officer who found housing,
# the employer who gave a second chance, or the neighbourhood that had
# resources. It can only see what arrived in its reward window.
```

Delayed harms - a wrongful denial that destroyed a family, a year of incarceration for someone who would not have reoffended - may never be attributed to the decision that caused them. The agent never receives the negative reward. The policy is never corrected.

---

## Real-World Case: COMPAS as an RL-Adjacent System

COMPAS (Correctional Offender Management Profiling for Alternative Sanctions) is deployed in 46 US states to produce risk scores used in bail, sentencing, and parole decisions. While it was trained with supervised methods, it exhibits the structural features of an RL policy: it maps defendant profiles to risk scores (actions) that determine release or detention (consequences), and it was calibrated on historical reoffense data (rewards) generated by a selectively enforcing system.

ProPublica's 2016 analysis of the COMPAS dataset demonstrates what a biased reward signal produces:

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# Load the COMPAS dataset (this repo's copy of ProPublica's raw scores file)
df = pd.read_csv("COMPAS/compas-scores-raw.csv")
df = df[df["Ethnic_Code_Text"].isin(["African-American", "Caucasian"])].copy()
df = df[df["DisplayText"] == "Risk of Recidivism"].copy()
df["race_binary"] = df["Ethnic_Code_Text"].map({"African-American": 1, "Caucasian": 0})

# The biased policy: state includes race and its proxy
features_biased = [
    "Sex_Code_Text",
    "race_binary",
    "CustodyStatus",    # proxy: encodes race via over-policing
    "MaritalStatus",
]

X = pd.get_dummies(df[features_biased])
y = df["ScoreText"].isin(["High", "Medium"]).astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)

# Measure the policy's behaviour across groups
for group, code in [("African-American", 1), ("Caucasian", 0)]:
    mask = df.loc[X_test.index, "race_binary"] == code
    preds = model.predict(X_test[mask])
    high_risk_rate = preds.mean() * 100
    print(f"{group} high-risk flag rate: {high_risk_rate:.2f}%")
```

**Results - biased policy (race + custody_status included):**

| Group | High-Risk Flag Rate |
|---|---|
| Black defendants | 87.16% |
| White defendants | 0.40% |
| **Fairness gap** | **86.77%** |

The policy did not contain a rule that said "flag Black defendants." It learned from historical reoffense records in which policing patterns, pretrial detention rates, and charge severity were all racially stratified. The reward signal encoded that stratification. The policy reproduced it.

---

## How to Detect When an RL-Adjacent Policy Is Biased

### Step 1 - Measure Demographic Parity

```python
def fairness_gap(model, X_test, df_test, protected_col, group_a, group_b):
    """
    Measure the difference in positive prediction rates between two groups.
    In RL terms: how differently does the policy behave across states
    that differ only in a protected attribute?
    """
    preds = model.predict(X_test)
    df_eval = df_test.copy()
    df_eval["prediction"] = preds

    rate_a = df_eval[df_eval[protected_col] == group_a]["prediction"].mean()
    rate_b = df_eval[df_eval[protected_col] == group_b]["prediction"].mean()

    return abs(rate_a - rate_b), rate_a, rate_b

gap, rate_black, rate_white = fairness_gap(
    model, X_test, df.loc[X_test.index],
    "Ethnic_Code_Text", "African-American", "Caucasian"
)
print(f"Fairness gap: {gap * 100:.2f}%")
# Actual output: Fairness gap: 86.77%
```

### Step 2 - Audit the State Representation for Proxy Variables

```python
import scipy.stats as stats

def proxy_check(df, feature, protected_attribute):
    """
    Chi-squared test for categorical features.
    p < 0.05 means the feature is statistically associated
    with the protected attribute - a proxy candidate.
    """
    contingency = pd.crosstab(df[feature], df[protected_attribute])
    chi2, p, dof, expected = stats.chi2_contingency(contingency)
    return chi2, p

# Check CustodyStatus as a proxy for race
chi2, p = proxy_check(df, "CustodyStatus", "Ethnic_Code_Text")
print(f"CustodyStatus ~ Ethnic_Code_Text: chi2={chi2:.2f}, p={p:.4f}")
# Actual output: chi2=315.89, p=0.0000 - well below 0.05, confirming CustodyStatus
# carries racial signal and should be removed
```

### Step 3 - Remove Proxies and Retrain

```python
features_fair = [
    # race_binary removed ✓
    "Sex_Code_Text",
    "MaritalStatus",
    # CustodyStatus removed ✓  (proxy: over-policing encodes race)
]

X_fair = pd.get_dummies(df[features_fair])
X_train_f, X_test_f, y_train_f, y_test_f = train_test_split(
    X_fair, y, test_size=0.2, random_state=42
)

model_fair = RandomForestClassifier(random_state=42)
model_fair.fit(X_train_f, y_train_f)
```

**Results - mitigated policy (race + proxy removed):**

| Group | High-Risk Flag Rate |
|---|---|
| Black defendants | 84.71% |
| White defendants | 69.02% |
| **New fairness gap** | **15.69%** |

| Approach | Fairness Gap | Reduction |
|---|---|---|
| Biased policy | 86.77% | - |
| Remove race only (keep custody_status) | 18.38% | 79% |
| Remove race + custody_status | 15.69% | **82%** |

The policy architecture did not change. The training procedure did not change. Only the state representation changed - and most of the discriminatory behaviour disappeared.

---

## Second Case: Recommendation Systems and Feedback Loops

YouTube's recommendation engine, documented in a 2019 Mozilla Foundation report on algorithmic amplification, is trained with RL using watch time as the primary reward signal. This creates a well-documented dynamic:

```python
# Simplified RL recommendation loop

def recommendation_reward(user_action, content_type):
    """
    Watch time is the reward. The agent learns to recommend
    whatever maximises it - regardless of whether that content
    is accurate, healthy, or fair.
    """
    if user_action == "watched_to_completion":
        return video_length_seconds   # longer watch = higher reward
    elif user_action == "clicked":
        return 5.0
    elif user_action == "scrolled_past":
        return 0.0
    elif user_action == "reported_harmful":
        return 0.0   # harmful content is not penalised
                     # it is only not rewarded
                     # the agent cannot distinguish the two

# The agent's optimal policy: recommend content that provokes strong
# emotional responses, because emotional engagement correlates with
# watch time. Outrage, fear, and tribalism are high-reward states.
# The agent has no fairness objective. It has one objective: watch time.
```

The demographic consequences of this reward function are asymmetric: recommendation systems trained on majority-population watch time data produce policies that systematically underserve minority groups, niche language communities, and anyone whose engagement patterns deviate from the majority distribution. The agent never receives a signal that anything went wrong.

---

## Limitations

**RL is rarely deployed explicitly in high-stakes settings.** The COMPAS case is RL-adjacent, not pure RL. The patterns - reward misspecification, credit assignment failure, proxy exploitation - appear in supervised systems too. The explainer uses the RL frame because it makes these failure modes most legible, not because RL is uniquely responsible.

**Removing proxies reduces but does not eliminate the gap.** The 82% reduction in the COMPAS case leaves a 15.69-point fairness gap. Remaining disparity reflects features that correlate with race for legitimate predictive reasons (prior arrests reflect real behaviour differences produced by structural conditions) or proxies not yet identified. Proxy removal is necessary but not sufficient.

**Defining the reward function is unavoidably political.** There is no neutral reward signal for a parole decision. Choosing to penalise false releases more than wrongful holds is a value judgment about whose safety matters more. This explainer cannot resolve that question. It can only make it visible.

**Credit assignment failure is not fully solvable.** No discounting scheme correctly attributes a 6-month outcome to the exact decision that caused it when hundreds of intervening variables - housing, employment, family, neighbourhood - all contribute. This is a fundamental limit of sequential decision-making under delayed feedback, not an implementation flaw.

**Watch time as a proxy for value is increasingly contested.** Platforms have introduced secondary signals (surveys, explicit ratings) to supplement watch time. Whether these corrections are sufficient, or whether they introduce new biases, is an open empirical question.

---

## Related Concepts

- [`feedback-loop-bias.md`](feedback-loop-bias.md) - How retraining on RL-generated decisions amplifies bias across cycles
- [`proxy-variables.md`](proxy-variables.md) - Why the state representation is where most RL bias enters
- [`label-bias.md`](label-bias.md) - How the reward signal inherits bias from historical outcomes
- [`neural-networks.md`](neural-networks.md) - How the policy function learns from state-reward pairs
- [`COMPAS/`](../COMPAS/) - Full audit of the COMPAS dataset: 82% gap reduction after removing race + custody_status proxy

---

## Further Reading

- [Dressel & Farid: The Accuracy, Fairness, and Limits of Predicting Recidivism (Science Advances, 2018)](https://www.science.org/doi/10.1126/sciadv.aao5580) - the peer-reviewed analysis showing COMPAS performs no better than untrained humans and exhibits racial disparities
- [Sutton & Barto: Reinforcement Learning: An Introduction (MIT Press, 2nd ed., 2018)](http://incompleteideas.net/book/the-book-2nd.html) - the canonical RL textbook, free online; Chapter 1 covers the core loop; Chapter 17 covers applications
- [Krakovna et al.: Specification Gaming: The Flip Side of AI Ingenuity (DeepMind, 2020)](https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/) - the canonical catalogue of reward hacking cases, from simulated robots to production systems

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
