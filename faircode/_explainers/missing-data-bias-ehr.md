> *A blank field in a patient's chart is not neutral information. It usually means the patient did not get the lab ordered, the visit that would have recorded it, or the specialist who would have documented it - and who gets fewer of those is rarely random.*

## The One-Sentence Definition

**Missing data as bias** means that in electronic health records, how *much* is recorded about a patient is itself shaped by unequal access to care, so a model reading "no data" as "nothing notable happened" is actually reading "this group is observed less," and it learns that gap as if it were a clinical signal.

## Why It Matters

Every field in an EHR - a lab result, a specialist note, an insurance code - exists because someone ordered a test, made a referral, or processed a claim. Patients who see clinicians less often, whose insurance requires more paperwork before a test is approved, or whose regular care happens outside the hospital system generating the record, end up with sparser charts - not because they are healthier, but because less of their care was captured in this particular dataset.

A model has no way to tell those two situations apart unless it is told to. It sees a missing lab value and a low lab value through the same lens: neither one raised a flag. If missingness is concentrated in a particular group, the model quietly learns that "fewer records" correlates with "lower risk," when the correct read is "less-observed." The result is a **missing-not-at-random (MNAR)** problem: the *chance* a value is missing depends on the patient's group and their access to the system that would have recorded it, not just on the value itself.

This matters more than an ordinary data-quality issue because most default handling makes it worse, not better. Dropping rows with missing values removes exactly the less-observed patients from the training data, teaching the model even less about them. Naive imputation - filling every gap with the column mean or median - overwrites a meaningful absence with a falsely reassuring "typical" value, erasing the very signal that would have flagged unequal access as unequal access.

## Core Concept: Three Ways Missingness Can Arise

Missing data is usually classified by *why* it's missing, and only one of the three is safe to treat casually:

- **MCAR (missing completely at random)** - a lab was skipped for a reason with no connection to the patient or the outcome, e.g. a machine was down that day. Dropping or imputing these rows introduces no bias, but this case is rarer in real EHR data than it sounds.
- **MAR (missing at random)** - missingness is explainable by *other observed variables* (e.g. inpatients get more labs than outpatients, and "encounter type" is recorded). Once you condition on what you know, the gap is no longer connected to the unrecorded value itself.
- **MNAR (missing not at random)** - missingness depends on the unrecorded value or on something correlated with the protected attribute that the model doesn't otherwise see - such as insurance type, distance to a specialist, or historical under-referral of a group. This is where access-driven missingness lives, and no amount of imputation logic can fully correct for it because the reason for the gap isn't in the data at all.

The practical test is not "how much is missing" but "does the missingness rate differ by group, and does that difference track something structural rather than clinical."

## Concrete Example: Healthcare Readmission - Audit 06

Audit 06's underlying dataset, Diabetes 130-US Hospitals (101,766 encounters), is a well-known case of exactly this pattern - and the numbers below come from reading the CSV already in this repo, not from a benchmark run or a frozen result:

```text
Column               Overall missing   Caucasian   African American   Gap
weight                     96.9%          96.2%          99.4%        3.2 pts
payer_code                 39.6%          37.5%          48.2%       10.7 pts
medical_specialty          49.0%          50.9%          43.0%        7.9 pts
```

`weight` is missing for nearly everyone - it was rarely recorded in outpatient workflow regardless of group, which is a genuine (if extreme) case of a field that is close to useless everywhere rather than a fairness problem on its own. `payer_code` is different: it is far more often missing for African American patients (48.2%) than Caucasian patients (37.5%), a 10.7-point gap on a column this repo's own `audit.yaml` already flags as a proxy for insurance access, not clinical severity - a model reading a missing payer code as "nothing to flag" is simply less informed about that group's coverage situation than it is for the majority group. `medical_specialty` runs the other direction (Caucasian patients are *more* often missing a specialist referral), which is exactly why this needs to be checked column by column and group by group rather than assumed: unequal missingness does not always point the same way, and assuming a single direction is itself a way to miss it.

## Detection Code

Computes the missingness rate per column, per group, so a column that is quietly less complete for one group cannot hide inside an overall missingness percentage.

```python
import pandas as pd


def missingness_by_group(df, group_col, missing_values=("?", "", "Unknown/Invalid")):
    """
    For each column, computes the missing-value rate overall and within
    each group, plus the gap between the group with the most and least
    missingness. A wide gap on a column that also correlates with a
    protected attribute (check with a chi-squared test, see
    CONTRIBUTING.md's proxy-variable section) is the access-driven
    missingness this explainer describes, not routine data noise.

    Parameters:
        df: DataFrame, e.g. a raw EHR extract before any imputation
        group_col: protected attribute or group label
        missing_values: sentinel values that mean "missing" in this dataset
            (EHR extracts frequently use "?", blanks, or a placeholder
            string instead of a true NaN)

    Returns a DataFrame indexed by column, with one rate column per group
    plus "gap" (max group rate - min group rate), sorted by gap descending.
    """
    is_missing = df.isna() | df.isin(missing_values)
    rows = []
    for col in df.columns:
        if col == group_col:
            continue
        rates = is_missing[col].groupby(df[group_col]).mean()
        row = {"column": col, **rates.to_dict()}
        row["gap"] = rates.max() - rates.min()
        rows.append(row)

    return pd.DataFrame(rows).set_index("column").sort_values("gap", ascending=False)


def flag_mnar_candidates(df, group_col, protected_col, missing_values=("?", "", "Unknown/Invalid"), min_gap=0.05):
    """
    Shortlists columns whose missingness gap by group exceeds min_gap -
    candidates worth a closer look before deciding how (or whether) to
    impute them. Does not decide MNAR on its own; a large gap is a prompt
    to investigate the mechanism, not proof of one.
    """
    gaps = missingness_by_group(df, group_col, missing_values)
    return gaps[gaps["gap"] >= min_gap]


# Usage example
# gaps = missingness_by_group(readmission_df, "race")
# candidates = flag_mnar_candidates(readmission_df, "race", protected_col="race", min_gap=0.05)
```

## Limitations

### 1. A missingness gap is a prompt to investigate, not proof of bias

Some legitimate clinical reasons produce group-correlated missingness too - a pediatric-heavy population will rarely have certain adult labs ordered, and that gap is clinical, not structural. Read the missingness gap next to what the column actually measures before concluding access is the cause.

### 2. Fixing missingness does not fix what caused it

Adding a "was this value missing" indicator column, or using a model that natively handles missing values, keeps the signal from being erased - but it does not correct the underlying access gap the missingness reflects. The model becomes honest about not knowing, which is real progress, but the patients behind that gap are still less observed.

### 3. Multiple imputation and indicator flags can leak the protected attribute back in

If missingness is itself correlated with the protected attribute, a "was this value imputed" flag is a new proxy variable for that attribute, even after the attribute itself is dropped. Check any missingness-indicator feature for correlation with the protected attribute the same way you would check any other proxy - see [Proxy Variables](proxy-variables.md).

### 4. Small groups make missingness rates noisy

A missingness rate computed on a few hundred records has a wide margin of error. Report group sizes next to any missingness gap, and treat a gap on a small subgroup as a signal to gather more data, not a confirmed disparity.

## Related Concepts

* [Sampling Bias](sampling-bias.md) - the closely related problem of who is captured in a dataset at all; missingness is sampling bias operating field-by-field within patients who are already in the dataset.
* [Selection Bias](selection-bias.md) - why the process that decides who enters a dataset (or which of their visits get recorded) can bias a model before any protected attribute is considered.
* [Label Bias](label-bias.md) - what happens when the outcome label itself, not just a feature, is less reliably recorded for one group.
* [Proxy Variables](proxy-variables.md) - why a missingness indicator can become a new proxy for the protected attribute it was meant to work around.

## Related Projects in This Repo

* [`Healthcare Readmission/`](../Healthcare%20Readmission/) - the dataset behind the missingness gaps above; `audit.yaml` already lists `payer_code` as a proxy feature for the reasons this explainer quantifies.
* [`Insurance Denial/`](../Insurance%20Denial/) - a second health-adjacent audit where which claims and conditions get documented at all is shaped by the same access patterns as EHR missingness.

## Further Reading

* [Gianfrancesco, M.A., Tamang, S., Yazdany, J., Schmajuk, G. (2018): Potential Biases in Machine Learning Algorithms Using Electronic Health Record Data](https://pmc.ncbi.nlm.nih.gov/articles/PMC6082530/) - a direct survey of how EHR missingness, documentation practices, and access disparities introduce bias before a model ever sees the data.
* [Rubin, D.B. (1976): Inference and Missing Data](https://www.jstor.org/stable/2335739) - the original MCAR/MAR/MNAR framework this explainer's core concept section is built on.
* [Getzen, E., Ungar, L., Mowery, D., Xu, X., Long, Q. (2023): Mining for Equitable Health: Assessing the Impact of Missing Data in Electronic Health Records](https://pmc.ncbi.nlm.nih.gov/articles/PMC10071455/) - a review connecting specific EHR missingness mechanisms to the demographic groups they disproportionately affect.

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
