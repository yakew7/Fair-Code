# Explainer: What is Feedback Loop Bias?

> *The reason AI systems don't just reflect the past - they actively manufacture more of it.*

---

## The One-Sentence Definition

**Feedback loop bias** occurs when a model's predictions influence the real-world outcomes it will later be trained on, so the model's existing biases are continuously confirmed and amplified over successive retraining cycles - even without any human ever introducing new discrimination.

---

## Why This Matters

Proxy variables and sampling bias are problems you can fix at training time: audit your features, remove the proxies, retrain. Feedback loop bias is different. It's a *temporal* problem. The model doesn't just learn from biased historical data - it generates biased present-day data that then becomes the training set for the next version of itself.

This is sometimes called **performative prediction**: the model's output changes the world, and the changed world then feeds back into the model. Left unchecked, this process can take a modestly biased model and turn it into an extremely biased one - not because anyone made it worse, but because nothing stopped it from compounding.

The mechanism is self-sealing: the model predicts high risk for Group A, so Group A receives more scrutiny, so more violations are detected in Group A, so the next model sees even more Group A violations in its training data, so it predicts even higher risk for Group A. At no point does anyone add discrimination. The feedback loop does it automatically.

---

## Common Feedback Loop Scenarios

| Domain | How the Loop Forms |
|---|---|
| Predictive policing | Model flags high-crime zip codes → police are deployed there → more arrests are recorded there → next model treats those zip codes as even higher risk |
| Credit scoring | Model denies loans to certain groups → those groups can't build credit history → next model sees thin credit files and rates them as high risk |
| Hiring AI | Model deprioritizes candidates from certain schools → those schools produce fewer hires → next model has no positive signal from those schools and ranks them lower still |
| Content recommendation | Model shows certain content to a demographic → that demographic's engagement data is dominated by that content type → next model assumes that's all they want |
| Healthcare resource allocation | Model predicts Group A has lower healthcare costs → Group A receives fewer resources → Group A has lower recorded care utilisation → next model interprets low utilisation as lower need |

---

## Real-World Proof: Predictive Policing

The most documented case of feedback loop bias in production is predictive policing.

### How It Works

Predictive policing systems - like PredPol (now Geolitica) - train on historical arrest data to predict which areas or individuals are "high risk." Police are then deployed based on those predictions.

The flaw is structural. Arrest data doesn't measure crime - it measures *policing*. Areas that receive more police patrols generate more arrests, not because more crime happens there, but because more enforcement is present. When that arrest data is used to train the next iteration of the model, those over-policed areas appear even more dangerous.

A 2019 analysis by Rashida Richardson, Jason Schultz, and Kate Crawford documented what they called "dirty data" - cases where predictive policing systems were trained on data generated during periods of documented police misconduct, racial profiling, and corruption. The model learned the misconduct as signal.

### The Feedback Loop in Pseudocode

```python
# Iteration 1
model_v1 = train(historical_arrest_data)
patrol_zones = model_v1.predict_high_risk()  # Over-predicts Zone A

# Zone A receives 3x the patrols
zone_a_arrests = patrol(zone_a, intensity=3x)  # More arrests, not more crime

# Iteration 2 - the loop
new_training_data = historical_arrest_data + zone_a_arrests
model_v2 = train(new_training_data)  # Zone A signal is now even stronger
patrol_zones_v2 = model_v2.predict_high_risk()  # Zone A flagged at higher confidence
```

Each iteration makes the model more certain about Zone A - not because Zone A is more dangerous, but because the model kept looking there.

---

## Detection: Measuring Prediction Drift Across Retraining Cycles

Unlike proxy variables, feedback loop bias can't be caught by a single chi-squared test. You need to track how predictions shift across retraining cycles.

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

def simulate_feedback_loop(df, feature_cols, label_col, group_col, n_cycles=5, scrutiny_multiplier=2.0):
    """
    Simulate n retraining cycles where the model's predictions
    influence the label distribution in the next training set.
    
    Returns a dict of {cycle: group_positive_rate} to surface drift.
    """
    results = {}
    data = df.copy()

    for cycle in range(n_cycles):
        X = pd.get_dummies(data[feature_cols])
        y = data[label_col]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        # Measure group-level positive prediction rates
        data['predicted'] = model.predict(X)
        cycle_results = (
            data.groupby(group_col)['predicted']
            .mean()
            .round(4)
            .to_dict()
        )
        results[f'cycle_{cycle + 1}'] = cycle_results

        # Feedback: model predictions influence next cycle's labels
        # Groups predicted high-risk receive more scrutiny → more positive labels recorded
        flagged_mask = data['predicted'] == 1
        noise = np.random.binomial(1, 0.1 * scrutiny_multiplier, size=flagged_mask.sum())
        data.loc[flagged_mask, label_col] = np.clip(
            data.loc[flagged_mask, label_col].values + noise, 0, 1
        )

    return results


def print_feedback_report(results, group_col):
    """Print a readable summary of group prediction rates across cycles."""
    print(f"\n{'='*55}")
    print(f"  FEEDBACK LOOP SIMULATION - {group_col.upper()}")
    print(f"{'='*55}")

    groups = list(next(iter(results.values())).keys())
    header = f"{'Cycle':<12}" + "".join(f"{str(g):<20}" for g in groups) + "Gap"
    print(header)
    print("-" * 55)

    for cycle, group_rates in results.items():
        rates = [group_rates.get(g, 0) for g in groups]
        gap = max(rates) - min(rates)
        row = f"{cycle:<12}" + "".join(f"{r:.2%}{'':>12}" for r in rates) + f"{gap:.2%}"
        print(row)

    print(f"{'='*55}\n")


# Example usage with COMPAS data
df = pd.read_csv('COMPAS/compas-scores-raw.csv')
df = df[df['Ethnic_Code_Text'].isin(['African-American', 'Caucasian'])].copy()
df = df[df['DisplayText'] == 'Risk of Recidivism'].copy()
df['high_risk'] = df['ScoreText'].isin(['High', 'Medium']).astype(int)

np.random.seed(42)
results = simulate_feedback_loop(
    df=df,
    feature_cols=['Sex_Code_Text', 'CustodyStatus', 'MaritalStatus'],
    label_col='high_risk',
    group_col='Ethnic_Code_Text',
    n_cycles=5
)

print_feedback_report(results, group_col='Ethnic_Code_Text')
```

**Actual output:**

```
African-American: 0.6653 at every cycle (1 through 5)
Caucasian:        0.5039 at every cycle (1 through 5)
Gap:              0.1614, unchanged across all 5 cycles
```

**What to look for:** If the gap between groups *grows* across cycles without any new discriminatory features being added, you have a feedback loop. A stable or shrinking gap means the loop is not compounding - which is exactly what this particular reproduction shows: on this dataset, with this coarse a feature set (sex, custody status, marital status), the scrutiny-driven label noise isn't strong enough to shift the retrained model's decision boundary in only 5 cycles, so the group gap stays perfectly flat. That is not evidence the mechanism is fake - the real-world predictive-policing case above is well documented - it's evidence that compounding depends on the retraining loop actually being sensitive to the perturbed labels, which has to be checked empirically rather than assumed.

---

## The Amplification Effect

The critical difference between feedback loop bias and ordinary historical bias:

| | Historical Bias | Feedback Loop Bias |
|---|---|---|
| **Source** | Biased past data | Model predictions shaping future data |
| **Trajectory** | Stable (fixed at training time) | Compounding (worsens each cycle) |
| **Fix** | Audit features once before training | Ongoing monitoring across retraining cycles |
| **Detectability** | Single-point audit | Requires longitudinal tracking |
| **Self-sealing?** | No | Yes - model confirms its own prior beliefs |

---

## Mitigation Strategies

Feedback loop bias requires interventions at the *deployment* level, not just the training level.

**1. Monitor group prediction rates across retraining cycles.** If one group's flagging rate is increasing iteration-over-iteration without a corresponding change in ground truth, the loop is amplifying. Automate this check before every retrain.

```python
def flag_feedback_drift(results, threshold=0.05):
    """
    Flag if the gap between groups increases by more than
    `threshold` across retraining cycles.
    """
    cycles = list(results.values())
    gaps = []
    for cycle in cycles:
        rates = list(cycle.values())
        gaps.append(max(rates) - min(rates))
    
    drift = gaps[-1] - gaps[0]
    return {
        'initial_gap': round(gaps[0], 4),
        'final_gap': round(gaps[-1], 4),
        'drift': round(drift, 4),
        'feedback_loop_detected': drift > threshold
    }
```

**2. Use counterfactual labels where possible.** In predictive policing and similar domains, arrest rates are not a neutral measure of the underlying behaviour you care about. Where possible, use outcome data that isn't itself a product of the model's prior predictions (e.g. victim-reported crime surveys instead of arrest records).

**3. Enforce prediction quotas or caps per group during deployment.** If a model is used to allocate scrutiny (audits, patrols, reviews), limit how much of that scrutiny can be concentrated in any one group. This breaks the amplification mechanism even if it doesn't fix the underlying model.

**4. Retrain from scratch on frozen historical data periodically**, rather than incrementally updating on live deployment data. Incremental updates on feedback-contaminated data are the mechanism of amplification.

---

## The Bigger Picture

Feedback loop bias is what happens when a biased model is treated as a neutral source of truth. The model's predictions become the next generation's labels. The next generation's labels become the next model's signal. The loop closes, and the bias compounds.

This is not a hypothetical. Predictive policing systems trained on over-policed communities have been formally documented producing exactly this pattern. Healthcare algorithms that used cost as a proxy for need have been documented under-allocating resources to Black patients - and those allocation decisions then reduced the care-seeking behaviour that would have corrected the signal.

Feedback loops are the reason algorithmic auditing cannot be a one-time exercise at deployment. It must be continuous. The model that passes a fairness audit on launch day may fail one a year later - not because anyone changed it, but because it has been changing its own training data the entire time.

---

## Limitations of Feedback Loop Detection

- Simulations like the one above are approximations. The real amplification rate depends on deployment intensity, retraining frequency, and how directly model predictions influence the label-generating process in your domain.
- In many production systems, the link between model output and training labels is indirect or obfuscated. Auditing requires access to the full pipeline, not just the model.
- Feedback loops interact with proxy variables: a proxy that produces mild bias in cycle 1 can produce severe bias by cycle 5 after amplification. Always audit both together.

---

## Related Projects in This Repo

- [`COMPAS/`](../COMPAS/) - The COMPAS criminal justice audit; the arrest-based training data used in this system is precisely the kind of feedback-contaminated label source this explainer describes
- [`explainers/proxy-variables.md`](proxy-variables.md) - Proxy variables are the mechanism that feedback loops amplify; read this first
- [`explainers/sampling-bias.md`](sampling-bias.md) - Feedback loops can be understood as a dynamic form of sampling bias that gets worse over time

---

## Further Reading

- [Richardson, Schultz & Crawford: Dirty Data, Bad Predictions (2019)](https://www.nyulawreview.org/online-features/dirty-data-bad-predictions-how-civil-rights-violations-impact-police-data-predictive-policing-systems-and-justice/) - Documents how predictive policing systems trained on misconduct-tainted data compound historical bias
- [Ensign et al.: Runaway Feedback Loops in Predictive Policing (FAT* 2018)](https://arxiv.org/abs/1706.09847) - The foundational paper formally modelling feedback loops in predictive policing
- [Obermeyer et al.: Dissecting racial bias in an algorithm used to manage the health of populations (Science, 2019)](https://science.sciencemag.org/content/366/6464/447) - Healthcare feedback loop case study; cost-as-proxy for need systematically under-allocated care to Black patients

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
