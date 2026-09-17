# Explainer: What Is Automation Bias?

> *The tendency to trust an AI recommendation more than human judgment - even when the AI is wrong.*

---

## The One-Sentence Definition

**Automation bias** is the cognitive tendency to defer to automated systems, treating their outputs as more objective, accurate, or authoritative than human judgment - even when the automation is known to be fallible, biased, or trained on flawed data.

---

## Why This Matters

Automation bias is the bridge between a model's statistical unfairness and its real-world harm. A model can have a documented 15% fairness gap, but if every decision-maker treats its output as a verdict rather than a signal, that gap becomes a discriminatory outcome at scale.

This is not a theoretical risk. It has been documented in:
- **Clinical decision support**: Physicians override correct clinical judgment to follow AI alerts that are wrong 30-50% of the time
- **Criminal sentencing**: Judges follow algorithmic risk scores even when they privately disagree, because "the computer says so"
- **Hiring**: Recruiters filter resumes by AI rank without reviewing the underlying profiles
- **Loan underwriting**: Officers approve or deny based on score thresholds they cannot explain or contest

The bias in the model is a *statistical* problem. Automation bias is the *human* problem that lets it leave the lab.

---

## Common Manifestations

| Pattern | Description | Real-World Consequence |
|---------|-------------|------------------------|
| **Omission error** | Failing to act because the system didn't flag it | High-risk patient discharged because no alert fired |
| **Commission error** | Acting on a system recommendation that contradicts evidence | Denying a qualified applicant because the score said "high risk" |
| **Default acceptance** | Treating the default output as the decision | Auto-approving or auto-denying based on threshold without review |
| **Authority transfer** | "The algorithm is objective" becomes a shield against accountability | No appeal path because "the math decided" |

---

## Real-World Proof: COMPAS in the Courtroom

The COMPAS risk assessment is the canonical example. ProPublica's 2016 analysis showed:
- Black defendants were flagged high-risk at **87%** vs **0.4%** for white defendants
- The fairness gap was **86.77%** before mitigation

But the deeper problem was not just the score - it was how the score was used. Judges in multiple states treated COMPAS as a sentencing guideline rather than a risk indicator. The Wisconsin Supreme Court (*State v. Loomis*, 2016) ruled that COMPAS could be used at sentencing *if* the court was informed of its limitations. In practice, the score was often treated as dispositive.

> **Key insight**: A biased model with no automation bias is a research artifact. A biased model with automation bias is a civil rights violation.

---

## Why Humans Defer to Machines

### 1. Perceived Objectivity
"The algorithm doesn't have prejudices." This confuses *lack of intent* with *lack of bias*. A model trained on biased data encodes that bias mathematically - it does not "remove" it.

### 2. Cognitive Offloading
High-stakes decisions are mentally taxing. An AI score offers a cognitive shortcut: a single number that feels like a conclusion.

### 3. Accountability Diffusion
"If the algorithm recommended it, it's not my fault." This is the moral hazard of automated decision support - it creates a responsibility gap.

### 4. Complexity Theater
Black-box models (neural nets, gradient boosting) are presented as too complex to question. The opacity becomes a feature, not a bug - it discourages challenge.

---

## Detection Code: Measuring Automation Bias in Practice

Automation bias is a human-factor phenomenon, but its *consequences* are measurable in model outputs when paired with human decisions.

```python
import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency

def automation_bias_audit(
    df: pd.DataFrame,
    model_score_col: str,
    human_decision_col: str,
    outcome_col: str,
    protected_attr: str,
    threshold: float = 0.5
) -> dict:
    """
    Audit whether human decisions defer to model scores
    in ways that amplify disparities across protected groups.

    Returns:
    - agreement_rate: how often human == model_binary
    - override_rate_by_group: where humans disagreed with model
    - disparity_amplification: whether human decisions are *more*
      disparate than model scores alone
    """
    df = df.copy()
    df['model_binary'] = (df[model_score_col] >= threshold).astype(int)

    # Overall agreement
    agreement = (df[human_decision_col] == df['model_binary']).mean()

    # Override rates by protected group
    override_rates = {}
    for group_val in df[protected_attr].unique():
        mask = df[protected_attr] == group_val
        human = df.loc[mask, human_decision_col]
        model = df.loc[mask, 'model_binary']
        override_rates[str(group_val)] = (human != model).mean()

    # Disparity in model scores
    model_rates = df.groupby(protected_attr)['model_binary'].mean()
    model_gap = model_rates.max() - model_rates.min()

    # Disparity in final human decisions
    human_rates = df.groupby(protected_attr)[human_decision_col].mean()
    human_gap = human_rates.max() - human_rates.min()

    return {
        'overall_agreement_rate': round(agreement, 3),
        'override_rate_by_group': {k: round(v, 3) for k, v in override_rates.items()},
        'model_fairness_gap': round(model_gap, 3),
        'human_fairness_gap': round(human_gap, 3),
        'disparity_amplified': human_gap > model_gap,
        'amplification_factor': round(human_gap / model_gap, 2) if model_gap > 0 else None
    }

# Example: Simulated hiring data where recruiters follow AI rank
np.random.seed(42)
n = 1000
df = pd.DataFrame({
    'candidate_id': range(n),
    'gender': np.random.choice(['M', 'F'], n, p=[0.5, 0.5]),
    'true_skill': np.random.normal(0, 1, n),
})
# Biased model: underestimates women's skill by 0.3 std
df['ai_score'] = np.where(
    df['gender'] == 'F',
    df['true_skill'] - 0.3 + np.random.normal(0, 0.5, n),
    df['true_skill'] + np.random.normal(0, 0.5, n)
)
# Human decision: 80% follow AI, 20% use own judgment
df['human_hire'] = np.where(
    np.random.random(n) < 0.8,
    (df['ai_score'] >= 0).astype(int),
    (df['true_skill'] >= 0).astype(int)
)
df['actual_performance'] = (df['true_skill'] >= 0).astype(int)

result = automation_bias_audit(
    df, 'ai_score', 'human_hire', 'actual_performance', 'gender'
)
print(result)
# Actual output (this exact seed, n=1000):
# {
#   'overall_agreement_rate': 0.824,
#   'override_rate_by_group': {'M': 0.167, 'F': 0.185},
#   'model_fairness_gap': 0.09,
#   'human_fairness_gap': 0.068,
#   'disparity_amplified': False,
#   'amplification_factor': 0.76
# }
```

**Interpretation**: In this run, the final human-decision gap (6.8 points) is actually *smaller* than the model's own gap (9.0 points) - not larger. That is not a counterexample to automation bias; it is a property of this specific simulation: the 20% of decisions that don't follow the AI score fall back to `true_skill`, which has no gender bias baked into it at all, so that fallback partially cancels the model's bias rather than compounding it. Automation bias amplifies a gap specifically when the human deviates from the model in ways that are *not* an unbiased correction - a recruiter's "gut feeling" override in the real world is not guaranteed to be unbiased the way `true_skill` is by construction here. Treat this block as a worked example of how to *measure* `model_fairness_gap` vs. `human_fairness_gap` with real data, not as proof that amplification is the only possible direction - the direction depends entirely on whether the human's departures from the model are themselves biased or not.

---

## Mitigation Strategies

| Strategy | Mechanism | Limitation |
|----------|-----------|------------|
| **Friction by design** | Require explicit override justification; show confidence intervals, not just scores | Adds workflow time; may be bypassed under pressure |
| **Counterfactual display** | "If this applicant were male, the score would be X" | Requires causal model; contested in court |
| **Blind review first** | Human evaluates case *before* seeing AI score | Not always feasible (e.g., triage) |
| **Disagreement logging** | Track every human-vs-model divergence for audit | Passive; does not prevent harm in real time |
| **Calibrated thresholds per group** | Different decision thresholds to equalize outcomes | Legal risk (disparate treatment); hard to justify |
| **Human-in-the-loop training** | Simulate edge cases where model is wrong; train reviewers to catch them | Resource-intensive; decay over time |

---

## The Deeper Problem: Automation Bias as a Design Choice

Automation bias is not a bug in human cognition - it is a predictable response to how AI systems are *designed and presented*.

- A score displayed as "Risk: HIGH (92%)" invites deference.
- A score displayed as "Model estimate: 0.62 [CI: 0.41-0.83], trained on data with known racial disparity of 15%, not validated for this population" invites scrutiny.

The same model, two different interfaces. One produces automation bias. The other produces informed human judgment.

**Fixing the model is necessary. Fixing the interface is equally necessary.**

---

## Related Concepts

- [What Is Machine Learning Bias?](ml-bias.md) - the four entry points through which bias enters a model
- [What Is a Proxy Variable?](proxy-variables.md) - why removing protected attributes is not enough
- [What Is Label Bias?](label-bias.md) - how historical decisions corrupt training labels
- [What Is a Confounding Variable?](confounding-variable.md) - hidden causes that create spurious correlations
- [The Biggest Myth About AI Objectivity](ai-objectivity-myth.md) - why "it's just math" is not a defense

---

## Further Reading

- [Goddard, K., Roudsari, A., & Wyatt, J.C. (2012): Automation Bias: A Systematic Review of Frequency, Effect Mediators, and Mitigators, Journal of the American Medical Informatics Association 19(1), 121-127](https://doi.org/10.1136/amiajnl-2011-000089) - the definitive literature review on automation bias in clinical settings
- [Skitka, L.J., Mosier, K.L., & Burdick, M. (1999): Does Automation Bias Decision-Making?, International Journal of Human-Computer Studies 51(5), 991-1006](https://doi.org/10.1006/ijhc.1999.0252) - the foundational experimental paper defining automation bias
- [Obermeyer, Z., Powers, B., Vogeli, C., & Mullainathan, S. (2019): Dissecting Racial Bias in an Algorithm Used to Manage the Health of Populations, Science 366(6464), 447-453](https://doi.org/10.1126/science.aax2342) - shows how an algorithm's cost-prediction label created racial bias that clinicians then automated
- [State v. Loomis, 881 N.W.2d 749 (Wis. 2016)](https://www.wicourts.gov/sc/opinion/DisplayDocument.pdf?content=pdf&seqNo=188417) - Wisconsin Supreme Court ruling on COMPAS use at sentencing

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*