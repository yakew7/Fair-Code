# Explainer: Proxy Entanglement

> *When multiple proxy variables encode the same protected attribute through independent causal paths, removing them one at a time guarantees the bias survives - because each variable acts as a redundant channel for the same signal.*

---

## The One-Sentence Definition

**Proxy entanglement** occurs when two or more features are individually correlated with a protected attribute *and* also correlated with each other, forming a reinforcing cluster that reconstructs the protected signal even after each variable is removed in isolation.

---

## Why It Matters

The standard mitigation playbook says: identify proxy variables, then remove them. That works when proxies are independent - when each one carries a distinct slice of the protected signal and dropping it cuts that slice out cleanly.

Proxy entanglement breaks that assumption. When proxies are entangled - when `feature A`, `feature B`, and `feature C` all carry the same protected signal *and* all correlate with each other - removing any single one still leaves the full signal alive in the others. Worse, a model that loses one entangled proxy can partially *reconstruct* it from the remaining ones, because the remaining features already encode much of the same information.

This is not a theoretical edge case. It is the default condition in datasets built on structural inequalities. Insurance access, discharge destination, specialty of the treating clinician, and prior hospitalisation don't each carry an independent slice of a patient's race and income - they carry *overlapping* slices, shaped by the same upstream structural inequalities in the US healthcare system. Removing `payer_code` still leaves race encoded in `discharge_disposition_id`. Removing both still leaves it partially encoded in `medical_specialty` and `number_inpatient`. All four variables originate from the same causal root: unequal access to care.

High-stakes systems that stop at one-variable-at-a-time removal will report a reduction in the fairness gap while leaving most of the bias mechanism intact.

---

## Real-World Case: Healthcare Readmission - Audit 06

The sharpest illustration of proxy entanglement in this repository is the `Healthcare Readmission` audit - the most structurally complex of all seven audits.

The dataset is `diabetic_data.csv`, drawn from 130 US hospitals between 1999 and 2008 (101,766 records). The model predicts whether a diabetic patient will be readmitted within 30 days and flags them as high clinical risk - a decision that directly affects discharge planning, post-acute care allocation, and follow-up resource assignment.

The protected attributes are race, gender, and age. The biased model (`unfair.py`) trained directly on all three alongside the full feature set, producing these gaps:

| Group | High-Risk Flag Rate |
|-------|:-------------------:|
| Caucasian / Asian | 0.25% |
| Other minorities | 0.17% |
| **Fairness Gap (Race)** | **0.08%** |

| Group | High-Risk Flag Rate |
|-------|:-------------------:|
| Under 70 | 0.36% |
| 70+ (elderly) | 0.08% |
| **Fairness Gap (Age)** | **0.28%** |

Removing race and age alone is not enough. Four proxy variables - `payer_code`, `discharge_disposition_id`, `medical_specialty`, and `number_inpatient` - form an entangled cluster, each encoding race and income through a different administrative channel, all tracing back to the same structural cause.

### The Entanglement Structure

```python
# Each proxy correlates with race through a different administrative pathway

# Proxy 1: payer_code → insurance type → encodes income + race
# Medicaid rate by race:
print(df.groupby('race')['is_medicaid'].mean().round(3))
# Hispanic: 9.0%,  AfricanAmerican: 5.5%,  Caucasian: 2.7%

# Proxy 2: discharge_disposition_id → SNF access → encodes insurance + geography
# Discharged-to-SNF rate by race:
print(df.groupby('race')['discharged_to_snf'].mean().round(3))
# Caucasian: 17.3%  vs  AfricanAmerican: 10.7%

# Proxy 3: number_inpatient → prior hospitalisation frequency → encodes access to preventive care
# Mean prior inpatient visits by race:
print(df.groupby('race')['number_inpatient'].mean().round(3))
# AfricanAmerican: 0.70  vs  Asian: 0.48
```

All three proxies are correlated with race. But they are also correlated with *each other*, because they share a common upstream cause: patients who lack adequate insurance (payer code) are also less likely to be discharged to a skilled nursing facility (discharge disposition) and more likely to have fragmented prior inpatient histories (number inpatient) - not because of clinical severity, but because structural access barriers affect all three at once.

A model that loses `payer_code` can partially reconstruct the insurance-access signal from `discharge_disposition_id`, because both measure the same underlying constraint. That is entanglement: the proxies are not independent channels. They are redundant encodings of the same latent variable - structural inequality.

### The Fix: Remove the Entire Cluster

```python
# THE FIX: Clinical signals from this admission only.
# All entangled proxies removed as a block.
features = [
    'admission_type_id',    # emergency vs elective
    'admission_source_id',  # ER vs referral vs transfer
    'time_in_hospital',     # length of stay
    'num_lab_procedures',   # diagnostic intensity
    'num_procedures',       # procedures this visit
    'num_medications',      # medication burden
    'number_outpatient',    # outpatient visits
    'number_emergency',     # emergency visits
    'number_diagnoses',     # comorbidity count
    'max_glu_serum',        # glucose reading
    'A1Cresult',            # HbA1c - diabetes control
    'insulin',              # treatment this visit
    'change',               # medication change flag
    'diabetesMed',          # on diabetes medication
    'diag_1', 'diag_2', 'diag_3',  # ICD codes this admission
    # race                     removed ✓  (protected attribute)
    # gender                   removed ✓  (protected attribute)
    # age                      removed ✓  (protected attribute)
    # payer_code               removed ✓  (proxy cluster: encodes income + race)
    # discharge_disposition_id removed ✓  (proxy cluster: encodes insurance + geography)
    # medical_specialty        removed ✓  (proxy cluster: encodes insurance access)
    # number_inpatient         removed ✓  (proxy cluster: encodes preventive care gap)
]
```

| Gap | Before | After | Reduction |
|-----|:------:|:-----:|:---------:|
| Race | 0.08% | 0.06% | **25%** |
| Age | 0.28% | 0.09% | **68%** |

Removing the entire entangled cluster - rather than any single variable - is what produces the reduction. Dropping only `payer_code` and leaving `discharge_disposition_id`, `medical_specialty`, and `number_inpatient` in place would have left most of the race signal intact, because those three remaining variables still encode the same structural inequality through different administrative columns.

> **Key insight:** `payer_code`, `discharge_disposition_id`, `medical_specialty`, and `number_inpatient` are not four independent proxies. They are four administrative measurements of the same underlying structural gap in US healthcare access. The causal direction matters: lower insurance coverage creates both restricted discharge destinations and fragmented inpatient histories. The patient does not bring the disparity - the system creates it, and then measures it four times. Removing only one measurement while leaving the others is not mitigation; it is relabelling.

📓 **[Full notebook walkthrough →](../notebooks/06_healthcare_readmission_bias_audit.ipynb)**

---

## Detection Code

The key to detecting entanglement is to measure not just each proxy's correlation with the protected attribute, but the cross-correlations *between* the proxies themselves. A cluster of features that are (1) each correlated with the protected attribute and (2) also correlated with each other is an entangled cluster and must be removed as a block.

```python
import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency

def detect_proxy_entanglement(df, protected_col, candidate_proxies, p_threshold=0.05):
    """
    Detect proxy entanglement: find clusters of features that are each correlated
    with the protected attribute AND correlated with each other.

    protected_col:    name of the protected attribute column
    candidate_proxies: list of column names to test
    p_threshold:       chi-squared significance threshold for declaring correlation
    """

    # Step 1: Test each candidate proxy against the protected attribute
    protected_correlated = []
    print(f"=== Correlation with protected attribute: '{protected_col}' ===\n")
    for col in candidate_proxies:
        ct = pd.crosstab(df[col], df[protected_col])
        chi2, p, dof, _ = chi2_contingency(ct)
        flag = "⚠  PROXY" if p < p_threshold else "✓  clean"
        print(f"  {flag}  {col:40s}  p={p:.4f}")
        if p < p_threshold:
            protected_correlated.append(col)

    if not protected_correlated:
        print("\n✓ No proxies detected.")
        return

    # Step 2: Among confirmed proxies, measure cross-correlations
    print(f"\n=== Cross-correlations among {len(protected_correlated)} confirmed proxies ===\n")
    entangled_pairs = []
    for i, col_a in enumerate(protected_correlated):
        for col_b in protected_correlated[i+1:]:
            ct = pd.crosstab(df[col_a], df[col_b])
            chi2, p, dof, _ = chi2_contingency(ct)
            flag = "⚠  ENTANGLED" if p < p_threshold else "   independent"
            print(f"  {flag}  {col_a} ↔ {col_b:30s}  p={p:.4f}")
            if p < p_threshold:
                entangled_pairs.append((col_a, col_b))

    # Step 3: Report cluster summary
    if entangled_pairs:
        in_cluster = set()
        for a, b in entangled_pairs:
            in_cluster.add(a)
            in_cluster.add(b)
        print(f"\n⛔  ENTANGLED CLUSTER DETECTED - remove ALL of the following together:")
        for col in in_cluster:
            print(f"      · {col}")
        print("\n  Removing any single member while retaining the others will not eliminate")
        print("  the protected signal. The cluster must be dropped as a block.")
    else:
        print(f"\n  Proxies are independent. Each can be evaluated and removed individually.")

    return protected_correlated, entangled_pairs


# Example: reproduce the Healthcare Readmission proxy analysis
# (assumes diabetic_data.csv is loaded and pre-processed into df)

# proxy_cols = ['payer_code', 'discharge_disposition_id', 'number_inpatient', 'medical_specialty']
# detect_proxy_entanglement(df, protected_col='race', candidate_proxies=proxy_cols)

# Expected output for audit 06:
# ⚠  PROXY   payer_code                                p=0.0000
# ⚠  PROXY   discharge_disposition_id                  p=0.0000
# ⚠  PROXY   number_inpatient                          p=0.0000
# ⚠  PROXY   medical_specialty                         p=0.0000
#
# ⚠  ENTANGLED   payer_code ↔ discharge_disposition_id    p=0.0000
# ⚠  ENTANGLED   payer_code ↔ number_inpatient             p=0.0000
# ⚠  ENTANGLED   discharge_disposition_id ↔ number_inpatient p=0.0000
#
# ⛔  ENTANGLED CLUSTER DETECTED - remove ALL of the following together:
#       · payer_code
#       · discharge_disposition_id
#       · number_inpatient
#       · medical_specialty
```

---

## Limitations and Trade-offs

### 1. Entanglement Detection Does Not Identify the Causal Root

The detection code above tells you that a cluster of features is entangled and correlated with a protected attribute. It does not tell you *why* - what the upstream structural cause is. Two auditors looking at the same entangled cluster could reasonably disagree about whether the shared cause is insurance access, geography, or historical under-investment in infrastructure. The statistical test is agnostic to causality. Human domain knowledge is required to interpret the cluster and construct the correct narrative for the key insight section.

### 2. Removing an Entangled Cluster Removes Legitimate Signal Too

The proxies in an entangled cluster are often administratively meaningful features that the model would legitimately use in a world without structural inequality. `payer_code` *does* carry information about care coordination. `discharge_disposition_id` *does* predict readmission risk - partially because patients discharged to SNFs receive better monitoring. Removing the entire cluster trades fairness for some loss in predictive accuracy. That trade-off is explicit and intentional in Fair Code's methodology, but it is a real trade-off that practitioners must defend.

### 3. Entanglement Threshold Is Sensitive to Base Rates

In large datasets (100K+ records), chi-squared tests become extremely sensitive. Two features that are weakly associated may still return `p < 0.05` because the sample size gives the test enormous power to detect trivial correlations. In audit 06, with 101,766 records, virtually every pair of features will be statistically correlated. The practical threshold for calling something an entangled proxy should combine statistical significance with a minimum effect size - for example, requiring that the Cramér's V association coefficient exceed 0.10 in addition to passing the chi-squared test.

### 4. Proxy Entanglement Is Not the Same as Multicollinearity

Multicollinearity is a model-training problem: when two features are highly correlated, coefficient estimates become unstable. Proxy entanglement is a fairness problem: when features encode a protected attribute through redundant channels, removing one leaves the others. These are related but not identical. A model can have severe proxy entanglement without suffering from multicollinearity (if the correlations are moderate rather than near-perfect), and it can suffer from multicollinearity without any fairness implication.

---

## Related Concepts

* [Proxy Variables](proxy-variables.md) - The foundation: what a proxy variable is and why removing the protected attribute alone is insufficient. Proxy entanglement is the extension of this problem to clusters.
* [Counterfactual Fairness](counterfactual-fairness.md) - An entangled proxy cluster is especially hard to reason about counterfactually, because the protected attribute flows into the prediction through multiple correlated paths simultaneously.
* [Label Bias](label-bias.md) - Entangled proxies often arise because training labels were generated by human decisions that were themselves made with knowledge of the protected attribute - the entanglement is inherited from the decision-making process, not just the feature set.
* [Feedback Loop Bias](feedback-loop-bias.md) - When a model trained on an entangled proxy cluster is redeployed and its predictions become new training labels, the entangled signal gets reinforced across cycles.

---

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - The audit where `payer_code`, `discharge_disposition_id`, `medical_specialty`, and `number_inpatient` form an entangled cluster, all encoding the same structural inequality in US healthcare access through independent administrative columns.

---

## Further Reading

* [Obermeyer et al. (2019): Dissecting Racial Bias in an Algorithm Used to Manage the Health of Populations](https://www.science.org/doi/10.1126/science.aax2342) - The landmark *Science* paper demonstrating that a commercial healthcare algorithm used healthcare cost as a proxy for health need, producing severe racial bias because cost and need are structurally decoupled by race.
* [Chiappa & Isaac (2019): A Causal Bayesian Networks Viewpoint on Fairness](https://arxiv.org/abs/1907.06430) - Formalizes the causal structure behind proxy entanglement: when multiple observed features share a latent common cause that is the protected attribute, standard covariate adjustment fails.
* [Kilbertus et al. (2017): Avoiding Discrimination Through Causal Reasoning](https://arxiv.org/abs/1706.02744) - Introduces the concept of resolving variables and unresolved discrimination, directly relevant to understanding when a cluster of correlated proxies shares a causal path through a protected attribute.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
