# Explainer: What is Demographic Parity?

> *Equal outcomes, not equal treatment - and that distinction is everything.*

---

## The One-Sentence Definition

**Demographic parity** is a fairness metric that requires a model to produce positive predictions at equal rates across demographic groups - regardless of whether those groups have different underlying rates of the outcome being predicted.

---

## Why This Matters

Demographic parity is the most widely used fairness metric in practice. It underlies US employment discrimination law (the EEOC's 80% rule), EU AI Act high-risk system audits, and most corporate fairness dashboards. When someone says an algorithm is "biased," they are usually - whether they know it or not - pointing at a demographic parity violation.

It matters because:

- A model can be highly accurate overall and still produce systematically unequal outcomes for different groups - and demographic parity is the only metric that directly measures this
- It is the legal threshold in hiring, lending, and admissions in most jurisdictions - violating it exposes organisations to disparate impact liability
- It is the primary metric used throughout this repo - the fairness gaps in the COMPAS, Hiring, Credit, Insurance, and Benefits audits are all measured as demographic parity violations

But it also matters to understand what it *doesn't* catch - because a model can satisfy demographic parity while still being deeply unfair in other ways. See the Limitations section.

---

## The Formal Definition

```
P(Ŷ = 1 | Group = A) = P(Ŷ = 1 | Group = B)
```

The model's positive prediction rate must be equal across groups. That's it. The metric makes no claim about whether the predictions are correct - only that the *rate* of positive predictions is equalised.

In practice, you rarely demand perfect equality. The EEOC's **four-fifths rule** treats any selection rate below 80% of the highest group's rate as evidence of adverse impact:

```
P(Ŷ = 1 | Group = B) / P(Ŷ = 1 | Group = A) ≥ 0.80
```

A ratio below 0.80 triggers scrutiny. A ratio above 0.80 passes. The 80% threshold is a legal convention, not a mathematical optimum.

---

## Real-World Proof: Hiring Bias

The AI Fair Recruitment audit in this repo is a direct illustration of a demographic parity violation - and its fix.

A model trained with gender and age as features assigned hire recommendations at sharply different rates:

| Group | Hire Rate |
|---|---|
| Male applicants | 21.62% |
| Female applicants | 17.59% |
| **Fairness Gap** | **4.03 percentage points** |

(The disparate-impact ratio here is 17.59 / 21.62 = 0.81, just above the 0.80 four-fifths threshold - close enough that it's worth checking directly rather than assuming a pass.)

The model was not told to discriminate. It learned to - by treating gender as a direct signal, since it was fed to the model as a feature. `AI Fair Recruitment/audit.yaml` also lists `Age` as a declared proxy feature to remove alongside gender, but in this dataset Age is not actually correlated with Gender (point-biserial r ≈ -0.002, p ≈ 0.42 - not significant, and dropping only Gender while keeping Age already closes the gap to about 0.2 percentage points, nearly as small as the fully-fixed model below). The gap here was overwhelmingly about gender being visible to the model directly, not about a career-gap-driven age proxy.

After dropping gender and age (the protected attribute and the declared proxy), the gap closes to **0.16 percentage points** - a **96.1% reduction**. The gap wasn't in the underlying merit of candidates - it was in which features the model was permitted to see.

---

## Detection Code

### Measure demographic parity gap

```python
import pandas as pd

def demographic_parity_audit(df, prediction_col, group_col, positive_label=1):
    """
    Compute positive prediction rate per group and the parity gap.

    Returns a DataFrame with rates per group, plus the gap and
    the four-fifths ratio between the lowest and highest rate.
    """
    rates = (
        df.groupby(group_col)[prediction_col]
        .apply(lambda x: (x == positive_label).mean())
        .round(4)
        .rename('positive_rate')
        .reset_index()
        .sort_values('positive_rate', ascending=False)
    )

    max_rate = rates['positive_rate'].max()
    min_rate = rates['positive_rate'].min()
    gap = round(max_rate - min_rate, 4)
    ratio = round(min_rate / max_rate, 4) if max_rate > 0 else None

    print("Positive prediction rates by group:")
    print(rates.to_string(index=False))
    print(f"\nDemographic parity gap:   {gap:.4f} ({gap*100:.2f} pp)")
    print(f"Four-fifths ratio:        {ratio:.4f}  {'✓ passes' if ratio >= 0.8 else '✗ fails'} (threshold: 0.80)")

    return rates, gap, ratio

# Example - using the AI Fair Recruitment dataset
# df = pd.read_csv('AI Fair Recruitment/AI_Fair_Recruitment_Dataset.csv')
# df['predicted_hire'] = model.predict(X_test)  # substitute your trained model and its X_test
# demographic_parity_audit(df, prediction_col='predicted_hire', group_col='Gender')
```

### Compute across multiple protected attributes at once

```python
def multi_group_parity_audit(y_pred, groups_df, positive_label=1):
    """
    Run demographic parity audit for every column in groups_df simultaneously.
    Useful when auditing for race, gender, and age in a single pass.
    """
    results = {}
    for col in groups_df.columns:
        temp = groups_df[[col]].copy()
        temp['y_pred'] = y_pred
        rates = temp.groupby(col)['y_pred'].apply(
            lambda x: (x == positive_label).mean()
        ).round(4)
        max_r, min_r = rates.max(), rates.min()
        results[col] = {
            'rates': rates.to_dict(),
            'gap': round(max_r - min_r, 4),
            'four_fifths_ratio': round(min_r / max_r, 4) if max_r > 0 else None,
            'passes_eeoc': (min_r / max_r) >= 0.8 if max_r > 0 else None,
        }
    return results

# Example
# protected = df[['Gender', 'Race', 'AgeGroup']]
# audit = multi_group_parity_audit(y_pred, protected)  # y_pred = your model's predictions
# for attr, result in audit.items():
#     status = '✓' if result['passes_eeoc'] else '✗'
#     print(f"{attr}: gap={result['gap']:.4f}, 4/5 ratio={result['four_fifths_ratio']:.4f} {status}")
```

### Visualise the gap

```python
import matplotlib.pyplot as plt

def plot_parity_gap(rates_df, group_col, rate_col='positive_rate', title='Demographic Parity'):
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor('#0f1117')
    ax.set_facecolor('#1a1d27')

    colors = ['#e05c5c' if i == 0 else '#5c9ee0' for i in range(len(rates_df))]
    bars = ax.barh(rates_df[group_col], rates_df[rate_col], color=colors)
    ax.axvline(x=rates_df[rate_col].max() * 0.8, color='#f0c040',
               linestyle='--', linewidth=1.2, label='80% threshold (EEOC)')

    ax.set_xlabel('Positive Prediction Rate', color='#aaaaaa')
    ax.set_title(title, color='white')
    ax.tick_params(colors='#aaaaaa')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333344')
    ax.legend(facecolor='#1a1d27', labelcolor='white', fontsize=9)

    plt.tight_layout()
    plt.savefig('demographic-parity-gap.png', dpi=150, bbox_inches='tight',
                facecolor='#0f1117')
    print("Saved: demographic-parity-gap.png")
```

---

## What Demographic Parity Catches - and What It Doesn't

### What it catches

- Models that assign positive outcomes (loans, hires, parole, insurance approvals) at lower rates to protected groups
- Cases where a protected attribute or its proxies are driving the disparity - even if accuracy looks fine overall
- Legal violations under disparate impact law without requiring evidence of intent

### What it misses

**1. Parity in mediocrity.** A model achieves demographic parity by *reducing* the positive rate for the advantaged group rather than raising it for the disadvantaged group. The gap closes - but no one benefits. Always inspect absolute rates, not just the gap.

**2. Error rate disparities.** A model can satisfy demographic parity while making systematically different *types* of errors for different groups. It might approve loans at equal rates but deny creditworthy applicants from one group at a higher rate (a false negative disparity) while approving uncreditworthy applicants from another at a higher rate (a false positive disparity). Equalized odds catches this; demographic parity does not.

**3. Calibration failures.** A model can predict at equal rates across groups while its predictions mean different things for each group. If a risk score of 0.7 corresponds to 70% true risk for Group A but only 50% for Group B, the model is miscalibrated - but demographic parity will not flag it.

**4. The impossibility result.** When base rates differ between groups - which they almost always do - demographic parity cannot be satisfied simultaneously with equalized odds and predictive parity. Satisfying demographic parity will necessarily force one of the other two metrics to fail. This is not a flaw in the metric; it is a mathematical fact. See [`fairness-metric-conflicts.md`](fairness-metric-conflicts.md) for the proof.

---

## Limitations

**Demographic parity ignores the ground truth.** It does not ask whether the groups *should* receive different rates, given the actual distribution of the outcome. A perfectly accurate model trained on data where Group A has a genuinely higher rate of the positive outcome will violate demographic parity - not because it is biased, but because it is accurate. This is the core tension between parity-based and accuracy-based fairness.

**The 80% rule is a legal convention, not a scientific threshold.** The EEOC chose 80% pragmatically in 1978. There is no statistical basis for treating 79% as discriminatory and 81% as fair. Courts have found discrimination below and above this threshold. Treat it as a trigger for scrutiny, not a verdict.

**Intersectionality is not captured.** Auditing by race alone and by gender alone can pass demographic parity while Black women face a combined disparity that neither single-attribute audit would surface. Disaggregate by all relevant combinations when the data supports it.

**The baseline can be corrupted.** If the positive prediction rate you are equalising is itself built on biased historical data - arrest rates instead of actual crime rates, for example - equalising it embeds the historical bias into the fair model. See [`proxy-variables.md`](proxy-variables.md) and [`sampling-bias.md`](sampling-bias.md).

---

## Related Projects in This Repo

- All five audits ([`COMPAS/`](../COMPAS/), [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/), [`German Credit Lending/`](../German%20Credit%20Lending/), [`Insurance Denial/`](../Insurance%20Denial/), [`Benefits Denial/`](../Benefits%20Denial/)) - demographic parity gap is the primary fairness metric in every one
- [`explainers/fairness-metric-conflicts.md`](fairness-metric-conflicts.md) - why demographic parity cannot coexist with equalized odds and predictive parity when base rates differ
- [`explainers/equalized-odds.md`](equalized-odds.md) - the error-rate alternative to demographic parity
- [`explainers/disparate-impact.md`](disparate-impact.md) - how demographic parity maps onto the legal four-fifths rule
- [`explainers/proxy-variables.md`](proxy-variables.md) - how to find and remove features that smuggle protected attributes back into the model

---

## Further Reading

- [Feldman et al.: Certifying and Removing Disparate Impact (2015)](https://arxiv.org/abs/1412.3756) - foundational paper on measuring and removing demographic parity violations
- [EEOC: Uniform Guidelines on Employee Selection Procedures (1978)](https://www.eeoc.gov/laws/guidance/questions-and-answers-clarify-and-provide-common-interpretation-uniform-guidelines) - the original document establishing the four-fifths rule
- [Barocas & Hardt: Fairness and Machine Learning - Chapter 2](https://fairmlbook.org/) - formal treatment of demographic parity and its relationship to other metrics
- [ProPublica: Machine Bias (2016)](https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing) - the audit that brought parity-based fairness criticism into public view

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
