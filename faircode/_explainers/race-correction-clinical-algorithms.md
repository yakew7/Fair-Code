> *For decades, standard medical equations multiplied kidney function numbers, scaled lung capacity targets, and lowered birth success predictions based solely on a patient's self-reported race. The math claimed to adjust for biological differences - but in reality, it baked racial prejudice directly into clinical algorithms, delaying organ transplants, specialist referrals, and necessary medical care.*

## The One-Sentence Definition

**Race correction in clinical algorithms** is the practice of multiplying, scaling, or adjusting diagnostic formulas by a coefficient based on a patient's self-reported race - baking racial bias directly into medical decision-making under the false assumption that race is a biological category rather than a social construct.

## Why It Matters

When a medical algorithm includes an explicit racial multiplier or race-based dummy variable, it changes the calculated risk score or diagnostic metric for patients of specific racial backgrounds purely because of who they are.

In clinical practice, race adjustments almost always operate to **artificially inflate or deflate perceived health status** for minority patients:
- **Delaying Kidney Transplants and Specialist Care**: In nephrology, equations for estimated Glomerular Filtration Rate (eGFR) multiplied calculated kidney function by 1.159 or 1.212 for Black patients. This made a Black patient's kidneys appear healthier than they were on paper, delaying diagnoses of chronic kidney disease (CKD), referrals to nephrologists, and eligibility for kidney transplant waitlists.
- **Underdiagnosing Occupational and Chronic Lung Disease**: In pulmonology, spirometry reference equations scaled predicted lung function downward by 10% to 15% for Black and Asian patients. Lowering the threshold for "normal" lung capacity meant that Black and Asian workers with real lung impairment were classified as healthy, denying them disability benefits and workplace accommodations.
- **Driving Unnecessary Surgical Interventions**: In obstetrics, the Vaginal Birth After Cesarean (VBAC) calculator subtracted points from the predicted probability of successful vaginal delivery if the patient was identified as African American or Hispanic, steering minority women toward unnecessary repeat C-sections.

Using race as a surrogate for biology systematically disadvantages the very groups it claims to adjust for. Removing race coefficients is essential for health equity, but doing so requires clinical systems to recalibrate decision thresholds and adopt non-racial biomarkers like Cystatin C.

## Core Concepts

### 1. Race is a Social Construct, Not a Biological Category
Human genetic variation is continuous and geographically distributed, with far more genetic diversity *within* self-identified racial groups than *between* them. Self-reported race reflects social history, geography, and structural experience - not innate physiological differences in organ function, muscle mass, or metabolic rates.

### 2. Confounding Social Inequities with Innate Biology
Legacy race corrections were often justified using observational studies where differences in outcomes - such as serum creatinine concentrations or spirometric volumes - were observed between racial groups. However, these studies failed to account for environmental exposures, nutritional differences, social determinants of health, and occupational hazards. Treating social inequities as innate biological traits turned historical discrimination into hardcoded mathematical formulas.

### 3. The Dilemma of Removing Race Coefficients
Simply dropping a racial multiplier from a clinical equation is a vital first step, but it is not always straightforward:
- **Unintended Reclassifications**: Eliminating the eGFR Black multiplier reclassified hundreds of thousands of Black patients overnight into more advanced stages of chronic kidney disease (e.g., from Stage 3a to Stage 3b or Stage 4). While this opens access to specialist care and transplant lists, it also triggers automatic drug dosing adjustments (such as lowering or stopping metformin) that health systems must manage safely.
- **The Need for Direct Biomarkers**: To measure organ function accurately across all body compositions without racial proxies, medicine must shift toward direct biological markers. For instance, **Cystatin C** is a protein produced by all nucleated cells at a constant rate, unaffected by muscle mass, diet, or demographic background.

## Best-Documented Clinical Cases

### eGFR Kidney-Function Equations (MDRD & CKD-EPI)
The Modification of Diet in Renal Disease (MDRD) and 2009 CKD-EPI equations estimated kidney function (eGFR) from serum creatinine. Both equations multiplied the calculated eGFR by a race factor (1.159 for MDRD, 1.212 for CKD-EPI) if the patient was identified as Black.
- **The Justification**: Based on small cohort studies from the 1990s asserting that Black individuals had higher average muscle mass and serum creatinine.
- **The Impact**: A Black patient and a White patient with identical serum creatinine levels of 1.5 mg/dL would receive eGFR scores of 52 mL/min/1.73m² (White) vs. 63 mL/min/1.73m² (Black). The White patient was diagnosed with Stage 3 Chronic Kidney Disease (eGFR < 60), while the Black patient was labeled normal, delaying specialist nephrology care and transplant evaluation until disease progressed further.

### Spirometry Reference Values (Pulmonary Function Testing)
Spirometers measure Forced Expiratory Volume in 1 second (FEV1) and Forced Vital Capacity (FVC) to diagnose asthma, COPD, and occupational lung diseases. For decades, software automatically applied "race correction factors" (typically a 10% to 15% reduction for Black and Asian patients).
- **The Justification**: Historical assumptions dating back to the 19th century (including writings by Thomas Jefferson and Samuel Cartwright) that non-white populations had inherently smaller lung capacities.
- **The Impact**: Scaling reference norms downward meant that a Black worker with damaged lungs had to demonstrate much greater impairment to be diagnosed with disability or occupational lung disease compared to a White worker with identical lung measurements.

### VBAC Calculator (Obstetrics)
The Grobman VBAC calculator estimates the probability that a pregnant individual who previously underwent a cesarean section can safely deliver vaginally. Until 2021, the algorithm subtracted specific point values if the patient was African American (-0.67) or Hispanic (-0.68).
- **The Justification**: Observational data showing lower historical rates of successful vaginal birth among Black and Hispanic women - driven by structural disparities in prenatal care, hospital quality, and clinician bias.
- **The Impact**: The formula systematically assigned lower success predictions to minority women, leading clinicians to recommend repeat cesarean deliveries, which carry higher risks of hemorrhage, infection, and surgical complications.

## Concrete Example: eGFR Diagnostic Shift Audit

To understand how a race multiplier shifts patients across clinical thresholds, consider a sample of 1,000 Black patients presenting with elevated serum creatinine (1.3 to 1.8 mg/dL).

When evaluated using the 2009 CKD-EPI equation, applying the 1.212 Black race multiplier inflates eGFR scores across the diagnostic boundary (60 mL/min/1.73m²):

| Metric | Without Race Multiplier (Unadjusted) | With 1.212 Race Multiplier (Race-Corrected) | Impact of Race Correction |
|---|---|---|---|
| Average eGFR Score | 53.4 mL/min/1.73m² | 64.7 mL/min/1.73m² | Inflated by +11.3 mL/min/1.73m² |
| Classified as CKD (eGFR < 60) | 640 patients (64.0%) | 410 patients (41.0%) | **230 patients (23.0%) denied CKD diagnosis** |
| Eligible for Transplant List (eGFR < 20) | 85 patients (8.5%) | 42 patients (4.2%) | **43 patients (4.3%) delayed from transplant list** |

The race multiplier hides real kidney impairment in 23% of patients, treating them as healthy on paper while their kidney function declines.

## Detection Code

Below are two modular Python functions:
1. `audit_race_corrected_formula`: Audits clinical datasets for diagnostic reclassification and care delays caused by race multipliers.
2. `scan_for_explicit_race_coefficients`: Scans model feature lists or code for hardcoded racial multipliers or race-based dummy variables.

```python
import numpy as np
import pandas as pd


def audit_race_corrected_formula(
    df: pd.DataFrame,
    raw_metric_col: str,
    race_col: str,
    target_race: str,
    multiplier: float,
    threshold: float,
    lower_is_worse: bool = True
) -> pd.DataFrame:
    """
    Audits the impact of a race multiplier on clinical threshold crossings.

    Parameters:
        df: DataFrame containing patient clinical data.
        raw_metric_col: Column name of unadjusted metric (e.g. unadjusted eGFR).
        race_col: Column name containing race/ethnicity labels.
        target_race: The group receiving the race adjustment (e.g. "Black").
        multiplier: The multiplicative race factor (e.g. 1.212).
        threshold: The clinical action threshold (e.g. 60.0 for CKD stage 3).
        lower_is_worse: If True, values below threshold indicate disease/risk.

    Returns:
        DataFrame summarizing diagnostic reclassification and care delays.
    """
    data = df.copy()

    # Calculate race-adjusted metric
    is_target = data[race_col] == target_race
    data['adjusted_metric'] = data[raw_metric_col].copy()
    data.loc[is_target, 'adjusted_metric'] = data.loc[is_target, raw_metric_col] * multiplier

    # Determine threshold crossing status
    if lower_is_worse:
        data['flag_raw'] = data[raw_metric_col] < threshold
        data['flag_adjusted'] = data['adjusted_metric'] < threshold
    else:
        data['flag_raw'] = data[raw_metric_col] > threshold
        data['flag_adjusted'] = data['adjusted_metric'] > threshold

    # A patient is delayed if unadjusted metric warrants action, but adjusted metric suppresses it
    data['care_delayed'] = data['flag_raw'] & (~data['flag_adjusted'])

    target_subset = data[is_target]
    total_target = len(target_subset)
    raw_flagged = target_subset['flag_raw'].sum()
    adj_flagged = target_subset['flag_adjusted'].sum()
    delayed_count = target_subset['care_delayed'].sum()

    summary = pd.DataFrame([{
        "target_group": target_race,
        "total_patients": total_target,
        "multiplier": multiplier,
        "threshold": threshold,
        "raw_action_needed": raw_flagged,
        "adjusted_action_needed": adj_flagged,
        "patients_care_delayed": delayed_count,
        "pct_target_care_delayed": (delayed_count / total_target * 100) if total_target else 0.0,
    }])

    return summary


def scan_for_explicit_race_coefficients(feature_names: list[str], code_str: str = "") -> dict:
    """
    Scans model feature sets and code logic for explicit race multipliers
    or race-based dummy variables.
    """
    race_keywords = ["race", "black", "african_american", "hispanic", "asian", "ethnicity"]

    flagged_features = [
        f for f in feature_names 
        if any(k in f.lower() for k in race_keywords)
    ]

    suspicious_code = []
    if code_str:
        for line in code_str.splitlines():
            line_lower = line.lower()
            if any(k in line_lower for k in race_keywords) and any(op in line for op in ["*", "+=", "*=", "-="]):
                suspicious_code.append(line.strip())

    return {
        "explicit_race_features_found": len(flagged_features) > 0,
        "flagged_features": flagged_features,
        "suspicious_multiplier_lines": suspicious_code,
    }


# Usage Example
if __name__ == "__main__":
    np.random.seed(42)
    sample_size = 500

    # Simulate creatinine-based eGFR values around the CKD stage 3 threshold (60)
    unadjusted_egfr = np.random.normal(loc=55, scale=10, size=sample_size)
    races = np.random.choice(["Black", "Non-Black"], size=sample_size, p=[0.3, 0.7])

    clinical_df = pd.DataFrame({
        "egfr_unadjusted": unadjusted_egfr,
        "race": races
    })

    audit_results = audit_race_corrected_formula(
        df=clinical_df,
        raw_metric_col="egfr_unadjusted",
        race_col="race",
        target_race="Black",
        multiplier=1.212,
        threshold=60.0,
        lower_is_worse=True
    )

    print("Race Correction Clinical Impact Audit:")
    print(audit_results.to_string(index=False))
```

## Limitations

### 1. Unintended Clinical Reclassifications
Removing race multipliers overnight reclassifies large patient populations into sicker diagnostic stages. Without operational readiness, this can overwhelm nephrology clinics, trigger automated pharmacy alerts that halt necessary medications (like metformin or SGLT2 inhibitors), and require extensive workflow retraining.

### 2. Need for Direct Biological Markers
Simply dropping race from creatinine-based equations without alternative testing can lead to minor accuracy trade-offs in individuals with extreme muscle mass or atypical diets. The definitive clinical solution is ordering direct non-racial biomarkers like **Cystatin C** or combining creatinine and Cystatin C in refitted race-free equations (such as CKD-EPI 2021).

### 3. EHR Data Quality and Race Misclassification
Self-reported race in Electronic Health Records is frequently missing, incomplete, or incorrectly entered by administrative staff without patient input. Relying on flawed demographic fields to adjust deterministic equations introduces unpredictable error.

### 4. Structural Disparities Survive Algorithmic Fixes
Eliminating racial multipliers removes an artificial mathematical barrier to care, but it does not erase real-world health disparities caused by environmental exposure, food insecurity, uninsurance, or systemic discrimination in hospital access.

## Related Concepts

* [What Is a Protected Attribute?](protected-attribute.md) - why incorporating race directly into model equations creates structural discrimination.
* [What is a Proxy Variable?](proxy-variables.md) - how administrative features can smuggle demographic signals back into models even when explicit race terms are removed.
* [What is Label Bias?](label-bias.md) - how historical disparities in care and diagnostic testing corrupt ground-truth training data.
* [Underdiagnosis Bias in Healthcare AI](underdiagnosis-bias.md) - how under-testing and clinical bias lead to under-counting active disease in minority groups.
* [Miscalibration in Clinical Risk Scores Across Groups](clinical-score-miscalibration.md) - why a risk score can convey different real-world risks depending on patient background.
* [Why Accuracy Is Not Enough in Healthcare AI](accuracy-not-enough-healthcare-ai.md) - why aggregate performance numbers mask severe subgroup diagnostic gaps.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - clinical risk audit examining how administrative and demographic features encode racial and insurance access gaps.
* [`Insurance Denial/`](../Insurance%20Denial/) - health-adjacent audit where health status indicators act as proxies for demographic groups.

## Further Reading

* [Vyas, D. A., Eisenstein, L. G., & Jones, D. S. (2020): Hidden in Plain Sight - Reconsidering the Use of Race Correction in Clinical Algorithms](https://doi.org/10.1056/NEJMms2004740) - the landmark New England Journal of Medicine review analyzing race correction across nephrology, pulmonology, cardiology, and obstetrics.
* [Inker, L. A., Eneanya, N. D., Coresh, J., et al. (2021): New Creatinine- and Cystatin C-Based Equations to Estimate GFR without Race](https://doi.org/10.1056/NEJMoa2102953) - the CKD-EPI and NKF-ASN Task Force study establishing validated, race-free eGFR equations.
* [Grobman, W. A. et al. (2021): Inclusion of Race and Ethnicity in Vaginal Birth After Cesarean Prediction Models](https://doi.org/10.1097/AOG.0000000000004356) - evaluation of the VBAC calculator demonstrating that removing race parameters maintains predictive validity while removing racial bias.
* [Braun, L. (2014): Breathing Race into the Machine: The Surprising Career of the Spirometer from Plantation to Genetics](https://www.upress.umn.edu/book-division/books/breathing-race-into-the-machine) - historical examination of how racial assumptions became hardcoded into pulmonary diagnostic instruments.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
