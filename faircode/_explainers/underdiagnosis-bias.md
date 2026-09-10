> *A clinical model trained on electronic health records does not predict who is actually sick - it predicts who was tested, diagnosed, and recorded as sick. If a group faced historical barriers to care, systemic under-testing, or clinical dismissal, their negative labels include untreated disease - and the model learns to under-diagnose them too.*

## The One-Sentence Definition

**Underdiagnosis bias** is a clinical-specific form of label bias that occurs when historical disparities in healthcare access, diagnostic testing, or clinical recognition cause true disease cases in underserved or marginalized groups to be recorded as negative labels (`0`) in electronic health records - creating an unobserved label error that trains predictive models to systematically under-flag those exact groups.

## Why It Matters

Machine learning models in healthcare are trained under the implicit assumption that the ground-truth target label Y accurately reflects patient health. In reality, Y represents a *recorded diagnosis* - a downstream artifact requiring a patient to seek care, have health insurance, access a clinician, undergo diagnostic testing, and have that condition correctly coded in an Electronic Health Record (EHR).

When a patient group experiences systemic barriers to care - such as lower health insurance coverage, geographic provider shortages, implicit bias during clinical encounters, or diagnostic criteria validated only on majority populations - sick patients in that group remain undiagnosed. In the training data, their target variable is recorded as `disease = 0` (negative) despite active disease.

When a supervised model trains on these corrupted labels:

1. **Target Contamination**: The `0` label is noisy and asymmetric - `0` for the reference group means "tested and healthy", while `0` for the underdiagnosed group means "healthy OR sick but unobserved".
2. **Predictive Under-flagging**: The model learns feature patterns associated with underdiagnosed patients and maps them to low risk.
3. **Automated Perpetuation**: When deployed, the model assigns lower risk scores or fails to recommend diagnostic testing and follow-up care to the very patients who were historically missed, locking the historical access gap into automated clinical workflows.

Unlike standard label bias in hiring or lending (where human managers actively make discriminatory decisions), underdiagnosis bias is often passive and structural: the data pipeline reflects diagnostic absence rather than disease absence.

## How Underdiagnosis Corrupts the Target Variable

Standard fairness evaluations assume that the target column Y in a benchmark dataset represents objective ground truth. In clinical datasets, this assumption fails because of the gap between true disease state and recorded diagnostic label:

* **True Disease State (Y*)**: The biological reality of whether a patient has a condition (Y* = 0 or 1).
* **Diagnostic Encounter (D)**: Whether the healthcare system actually evaluated and tested the patient for the condition (D = 0 or 1).
* **Recorded Diagnosis Label (Y)**: The value recorded in the EHR (Y = 0 or 1).

A positive diagnosis requires both disease presence and diagnostic detection:

```
Y = Y* × D
```

If a patient is never tested or their symptoms are dismissed (D = 0), their recorded label is Y = 0, regardless of whether Y* = 1.

### Asymmetric Label Noise Across Groups

For a privileged or high-access group (A = 0), diagnostic detection probability conditional on illness is close to complete:

```
P(D = 1 | Y* = 1, A = 0) ≈ 1.0  =>  P(Y = 0 | Y* = 1, A = 0) ≈ 0.0
```

For an under-served group (A = 1), diagnostic barriers introduce a non-zero underdiagnosis rate eta > 0:

```
P(D = 1 | Y* = 1, A = 1) = 1 - eta  =>  P(Y = 0 | Y* = 1, A = 1) = eta
```

This creates **group-conditional false-negative label noise**. The label column Y is systematically sicker for A = 1 than the numbers show, because a fraction eta of sick individuals in A = 1 are labeled as healthy `0`s.

### Why Standard Bias Audits Fail to Catch It

Standard fairness metrics - such as Equalized Odds, Demographic Parity, or False Negative Rates - compare model predictions Y_pred against recorded labels Y.

If a model predicts Y_pred = 0 for an undiagnosed sick patient in A = 1, standard evaluation compares Y_pred = 0 to Y = 0 and counts it as a **True Negative**, praising the model for high accuracy. In biological reality, relative to Y* = 1, the decision is a **Clinical False Negative**. Standard audits reward the model for faithfully reproducing the healthcare system's failure to diagnose.

## Concrete Example: Healthcare Utilization vs. True Disease Burden

Underdiagnosis bias appears across clinical specialties, EHR risk models, and medical device benchmarks.

### 1. Audit 06: Healthcare Readmission

In Audit 06 of this repo (`Healthcare Readmission/`), models predict 30-day hospital readmission from the Diabetes 130-US Hospitals dataset (101,766 records). Predictor features include `number_inpatient`, `number_emergency`, `number_diagnoses`, and prior hospitalizations.

In EHR datasets, features measuring prior hospital visits or recorded chronic comorbidities reflect **healthcare utilization** rather than raw disease burden. A patient with fewer recorded hospital visits or unlisted chronic conditions may appear lower risk to a model. If structural barriers prevent underserved patients from accessing inpatient care, their lower recorded visit count and un-coded comorbidities act as proxies for underdiagnosis, causing models to systematically underestimate their true readmission risk.

### 2. Documented Real-World Clinical Cases

* **Kidney Disease (CKD and eGFR)**: Historical clinical algorithms used race-adjusted estimated Glomerular Filtration Rate (eGFR) equations that added a multiplier for Black patients. This artificially inflated reported kidney function, delaying Stage 3/4 Chronic Kidney Disease diagnoses and specialist referrals. Models trained on historical EHR ICD codes inherited these delayed diagnosis labels.
* **Underdiagnosis in Medical Imaging (Seyyed-Kalantari et al., 2021)**: An audit of deep learning models trained on chest X-rays (MIMIC-CXR and CheXpert) revealed consistent underdiagnosis bias across underserved patient subpopulations. The algorithms produced significantly higher false-negative rates for female, Black, Hispanic, and lower-socioeconomic patients - under-flagging active pulmonary pathology despite identical imaging quality.
* **Healthcare Cost as a Proxy for Health Need (Obermeyer et al., 2019)**: A commercial risk score used for 200 million patients annually predicted future healthcare costs as a proxy for health need. At any given risk score, Black patients were considerably sicker than White patients (having more unmanaged chronic conditions) because historical healthcare spending on Black patients was lower due to access barriers. Using cost (Y) as the target created an underdiagnosis bias that halved the number of Black patients enrolled in high-risk care management programs.

## Detection Code

The Python code below demonstrates how underdiagnosis bias corrupts model evaluation. It creates a synthetic patient cohort where true disease status (Y*) is generated from biological markers, but recorded diagnosis (Y) suffers from group-conditional under-testing.

It runs two parallel audits:
1. **Standard Audit (against observed EHR labels Y)**: Shows how standard evaluation hides the bias.
2. **Ground-Truth Audit (against true disease state Y*)**: Reveals the true false-negative gap.
3. **Biomarker-to-Label Consistency Test**: Audits diagnosis rates across groups within matched lab value bands to flag suspected underdiagnosis in real-world data without unobserved labels.

```python
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split


def simulate_underdiagnosis_cohort(n_samples=3000, random_state=42):
    """
    Generates a synthetic patient dataset with true disease status (Y*)
    and observed diagnostic labels (Y) reflecting group underdiagnosis.
    """
    np.random.seed(random_state)

    group = np.random.choice(
        ['Group A (Reference)', 'Group B (Underserved)'], size=n_samples
    )
    biomarker = np.random.normal(loc=60, scale=15, size=n_samples)
    age = np.random.randint(25, 75, size=n_samples)

    # True disease state (Y*) based on biological biomarker score
    p_true_disease = 1 / (1 + np.exp(-(biomarker - 65) / 8))
    y_true_star = (np.random.rand(n_samples) < p_true_disease).astype(int)

    # Underdiagnosis mechanism:
    # Group A: 92% of true cases get tested and recorded
    # Group B: 55% of true cases get tested and recorded (45% missed in EHR)
    p_diagnosis = np.where(group == 'Group A (Reference)', 0.92, 0.55)
    y_observed = (y_true_star == 1) & (np.random.rand(n_samples) < p_diagnosis)

    return pd.DataFrame({
        'biomarker_score': biomarker,
        'age': age,
        'group': group,
        'true_disease_star': y_true_star,
        'recorded_diagnosis': y_observed.astype(int)
    })


def audit_underdiagnosis_bias(df, feature_cols, target_obs_col, target_true_col, group_col):
    """
    Evaluates a model against observed EHR labels vs true disease status.
    """
    X = pd.get_dummies(df[feature_cols + [group_col]], drop_first=True)
    y_obs = df[target_obs_col]

    X_train, X_test, y_train, y_test, idx_tr, idx_te = train_test_split(
        X, y_obs, df.index, test_size=0.3, random_state=42, stratify=y_obs
    )

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    test_df = df.loc[idx_te].copy()
    test_df['y_pred'] = clf.predict(X_test)

    rows = []
    for grp, sub in test_df.groupby(group_col):
        # 1. Audit against Observed EHR Label Y (Standard Evaluation)
        tn_o, fp_o, fn_o, tp_o = confusion_matrix(
            sub[target_obs_col], sub['y_pred'], labels=[0, 1]
        ).ravel()
        recall_obs = tp_o / (tp_o + fn_o) if (tp_o + fn_o) else 0.0
        fnr_obs = fn_o / (tp_o + fn_o) if (tp_o + fn_o) else 0.0

        # 2. Audit against True Disease State Y* (Biological Reality)
        tn_t, fp_t, fn_t, tp_t = confusion_matrix(
            sub[target_true_col], sub['y_pred'], labels=[0, 1]
        ).ravel()
        recall_true = tp_t / (tp_t + fn_t) if (tp_t + fn_t) else 0.0
        fnr_true = fn_t / (tp_t + fn_t) if (tp_t + fn_t) else 0.0

        rows.append({
            'group': grp,
            'n_test': len(sub),
            'obs_prevalence': sub[target_obs_col].mean(),
            'true_prevalence': sub[target_true_col].mean(),
            'obs_recall': recall_obs,
            'true_recall': recall_true,
            'obs_fnr': fnr_obs,
            'true_fnr': fnr_true
        })

    res = pd.DataFrame(rows).set_index('group')
    return res


def biomarker_label_consistency(df, biomarker_col, label_col, group_col, n_bins=4):
    """
    Audits diagnostic label rates across groups within matched lab value bands.
    If two groups with equal lab values show different diagnosis rates,
    underdiagnosis bias is present in the EHR labels.
    """
    df = df.copy()
    df['biomarker_band'] = pd.qcut(
        df[biomarker_col], q=n_bins, labels=[f'Q{i+1} (Low-High Risk)' for i in range(n_bins)]
    )

    rates = (
        df.groupby(['biomarker_band', group_col])[label_col]
          .mean()
          .unstack(group_col)
          .round(3)
    )
    return rates


# Run demonstration
cohort_df = simulate_underdiagnosis_cohort()

print("=== 1. MODEL AUDIT: OBSERVED EHR LABELS VS TRUE DISEASE STATE ===")
audit_results = audit_underdiagnosis_bias(
    cohort_df,
    feature_cols=['biomarker_score', 'age'],
    target_obs_col='recorded_diagnosis',
    target_true_col='true_disease_star',
    group_col='group'
)
print(audit_results[['obs_recall', 'true_recall', 'obs_fnr', 'true_fnr']])

print("\n=== 2. BIOMARKER-TO-LABEL CONSISTENCY AUDIT ===")
diagnosis_rates = biomarker_label_consistency(
    cohort_df,
    biomarker_col='biomarker_score',
    label_col='recorded_diagnosis',
    group_col='group'
)
print("Diagnostic label rate by biomarker band:")
print(diagnosis_rates)
```

### Output Interpretation

1. **The Evaluation Trap**: Against observed EHR labels (`obs_recall`), the model already recalls Group B worse than Group A (**~0.64** vs **~0.33**), but standard evaluation reads that as the model faithfully matching a lower "disease rate" in Group B. Against true disease status (`true_recall`), the real picture is worse: the model catches **62.5%** of sick Group A patients versus only **29.2%** of sick Group B patients - a **33.3-point true false-negative gap**, most of which standard evaluation scores as correct True Negatives.
2. **The Biomarker Audit**: In the highest biomarker band (Q4), Group A patients have a **0.785** recorded-diagnosis rate while Group B has a **0.497** rate, despite sharing the same objective clinical values. Disparities in diagnostic coding within matched biomarker bands flag underdiagnosis bias directly from EHR records, without needing the unobserved true label.

## Limitations

### 1. Unobserved True Disease State (Y*)

In observational healthcare data, true disease status Y* is rarely recorded. Identifying underdiagnosis requires objective proxy biomarkers (e.g., lab results, physiological waveforms), prospective screening studies, or external clinical audit samples.

### 2. Missing Lab Data Confounding

Biomarker-to-label audits rely on lab test values. However, if underserved patients also face lab testing access barriers, their lab results will be systematically missing (see the [missing data bias in EHR explainer](missing-data-bias-ehr.md)).

### 3. Post-Processing Fairness Constraints Can Backfire

Applying standard post-processing algorithms (e.g., equalizing positive prediction rates relative to observed Y) can reinforce bias. Equalizing prediction rates against a target Y that under-counts disease in Group B forces the model to maintain artificially low flag rates for Group B.

### 4. Over-testing vs. Under-testing Balance

Mitigating underdiagnosis bias requires expanding diagnostic testing and lowering intervention thresholds for underserved groups. Clinical teams must balance this against over-testing, alert fatigue, and unnecessary medical procedures.

## Related Concepts

* [What is Label Bias?](label-bias.md) - the overarching category of target variable corruption where historical human decisions introduce label noise.
* [Missing Data as Bias in Electronic Health Records](missing-data-bias-ehr.md) - how structural care access gaps cause missing lab fields and unrecorded observations.
* [What Is Selection Bias?](selection-bias.md) - how dataset entry filters exclude individuals before diagnostic labels are even created.
* [Why Accuracy Is Not Enough in Healthcare AI](accuracy-not-enough-healthcare-ai.md) - why high headline accuracy hides severe per-group recall and false-negative gaps.
* [False Positives vs. False Negatives in Medical Risk Models](false-positives-vs-false-negatives.md) - why false negatives in underserved groups carry disproportionate clinical harm.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - Audit 06, where prior inpatient visits and diagnosis counts reflect healthcare utilization and access rather than raw disease severity.
* [`Insurance Denial/`](../Insurance%20Denial/) - Audit 04, where insurance coverage decisions dictate which diagnostic tests get performed and recorded in medical datasets.

## Further Reading

* [Seyyed-Kalantari, L., Zhang, H., McDermott, M.B.A., Chen, I.Y., Ghassemi, M. (2021): Underdiagnosis bias: an underaddressed problem in artificial intelligence for healthcare](https://doi.org/10.1038/s41591-021-01595-0) - landmark study in *Nature Medicine* demonstrating systematic underdiagnosis bias in medical imaging models across demographic subgroups.
* [Obermeyer, Z., Powers, B., Vogeli, C., Mullainathan, S. (2019): Dissecting racial bias in an algorithm used to manage the health of populations](https://doi.org/10.1126/science.aax2342) - foundational paper in *Science* showing how using healthcare costs as a target variable caused algorithms to under-enroll sick Black patients.
* [Rajkomar, A., Hardt, M., Howell, M.D., Corrado, G., Chin, M.H. (2018): Ensuring Fairness in Machine Learning to Advance Health Equity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6594166/) - comprehensive framework for identifying and mitigating bias throughout the healthcare ML lifecycle.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
