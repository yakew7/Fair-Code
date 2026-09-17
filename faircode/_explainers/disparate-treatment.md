# Explainer: What is Disparate Treatment?

> *Disparate impact is accidental discrimination. Disparate treatment is deliberate - and the law treats them very differently.*

---

## The One-Sentence Definition

**Disparate treatment** is intentional discrimination: a decision-making process that treats an individual differently because of a protected characteristic (race, gender, age, religion, national origin, etc.) - regardless of whether that characteristic is named explicitly or encoded through a feature that serves as a stand-in for it.

---

## Why This Matters

Most algorithmic fairness work focuses on disparate impact - unequal outcomes produced by a model that never explicitly uses a protected attribute. Disparate treatment is the other half of discrimination law, and it is the half that is harder to escape in court.

Where disparate impact asks *"did outcomes differ across groups?"*, disparate treatment asks *"was the protected attribute a factor in the decision?"* A model that directly includes `Gender`, `Race`, or `Age` as input features is, by definition, engaging in disparate treatment - even if the resulting outcome gap is small. The intent is embedded in the design.

This matters in practice because:

- Including a protected attribute as a model feature is *per se* disparate treatment under Title VII, the Equal Credit Opportunity Act (ECOA), and the Fair Housing Act - regardless of whether you can measure a downstream gap
- Courts distinguish between the two doctrines sharply: disparate impact claims require statistical evidence of outcome disparity; disparate treatment claims require evidence that the protected characteristic was *used*, not just that outcomes differed
- Every biased model in this repo was first trained with protected attributes included - that is, every `unfair.py` script is a disparate treatment example before it becomes a disparate impact one

---

## Disparate Treatment vs Disparate Impact - The Distinction That Matters

These two doctrines are often confused. They are different legal claims with different burdens of proof and different fixes.

| | Disparate Treatment | Disparate Impact |
|---|---|---|
| **Definition** | Protected attribute was used as a factor in the decision | Neutral process produces unequal outcomes across groups |
| **Intent required?** | Yes - the attribute must have been used, deliberately or by design | No - no intent required; the outcome gap is the evidence |
| **Legal standard** | Title VII §703(a) - treating someone differently *because of* race, sex, etc. | Title VII §703(k) - neutral practice with unjustified disparate effect |
| **Proof** | Show the attribute was an input or a determinative factor | Show the statistical outcome gap (four-fifths rule, etc.) |
| **Defence** | Bona Fide Occupational Qualification (BFOQ) - narrow, rarely succeeds | Business necessity + job-relatedness |
| **Algorithmic form** | Protected attribute or known proxy included as a model feature | Protected attribute excluded but proxies remain; outcome gap persists |
| **Fix** | Remove the protected attribute from the feature set | Remove the protected attribute *and* its proxy variables |
| **Metric** | Feature presence audit - is it in the model at all? | Disparate impact ratio, demographic parity gap |

The critical asymmetry: you can have disparate treatment *without* disparate impact (the attribute is used but outcomes happen to be equal), and disparate impact *without* disparate treatment (no protected attribute was used but proxies recreated the gap). In practice, disparate treatment usually produces disparate impact - but the legal exposure exists independently.

---

## Real-World Proof: Every `unfair.py` in This Repo

Every biased model in this repo is a disparate treatment example. The protected attribute is a direct model input. The outcome gap is the downstream disparate impact. They are the same model - looked at through two different legal lenses.

### COMPAS - `unfair.py`

```python
# DISPARATE TREATMENT: Race is a direct model feature
# (compas-scores-raw.csv has no raw `race` column - `race_binary` is
# derived from the real `Ethnic_Code_Text` column, exactly as unfair.py does)
df['race_binary'] = df['Ethnic_Code_Text'].map({'African-American': 1, 'Caucasian': 0})
X = pd.get_dummies(df[[
    'race_binary',     # ← protected attribute, fed directly to the classifier
    'Sex_Code_Text',
    'CustodyStatus',
    'MaritalStatus'
]])
```

Race is an explicit input. The model is permitted to use race as a predictive signal. That is disparate treatment. The resulting 86.77pp gap between Black and White defendants is the disparate impact it produces.

### AI Fair Recruitment - `unfair.py`

```python
# DISPARATE TREATMENT: Gender and Age are direct model features
features = ['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score']
```

`Gender` is a direct input. `Age` is both an input and a proxy for gender (women in the dataset more often have career gaps, so age encodes gender signal twice over - once directly, once through correlation). The model was *designed* to see these attributes. The 4.51pp hire rate gap (21.62% vs 17.10%) is the disparate impact.

### The Fix - What Removing Disparate Treatment Looks Like

```python
# fair.py: protected attribute and its proxy removed
features = ['Experience_Years', 'Technical_Test_Score']
# Gender removed ✓  - eliminates disparate treatment
# Age removed ✓     - eliminates proxy-based disparate treatment
```

Removing the protected attribute ends the disparate treatment. Whether it also ends the disparate impact depends on whether proxies remain - which is why proxy variable analysis is a required step in every audit. See [`proxy-variables.md`](proxy-variables.md).

---

## Detection Code

### Audit whether protected attributes are in the feature set

```python
import pandas as pd

# Standard protected attributes under US federal law
PROTECTED_ATTRIBUTES = {
    'race', 'ethnicity', 'color', 'national_origin', 'origin',
    'sex', 'gender', 'pregnancy',
    'age',
    'religion',
    'disability',
    'marital_status',       # ECOA
    'family_status',        # Fair Housing Act
}

def disparate_treatment_audit(feature_columns, protected=PROTECTED_ATTRIBUTES):
    """
    Flag any feature that is a protected attribute or contains one as a substring.
    Returns a list of flagged column names.
    """
    flagged = []
    cols_lower = {col: col.lower().replace(' ', '_').replace('-', '_')
                  for col in feature_columns}

    for original, normalised in cols_lower.items():
        for attr in protected:
            if attr in normalised:
                flagged.append(original)
                break

    if flagged:
        print(f"⚠ Disparate treatment risk - protected attributes in feature set:")
        for f in flagged:
            print(f"  · {f}")
    else:
        print("✓ No protected attributes detected in feature set.")
        print("  Run a proxy variable audit next - see proxy-variables.md")

    return flagged


# Example - AI Fair Recruitment biased model
features_unfair = ['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score']

disparate_treatment_audit(features_unfair)
# ⚠ Disparate treatment risk - protected attributes in feature set:
#   · Gender
#   · Age

features_fair = ['Experience_Years', 'Technical_Test_Score']
disparate_treatment_audit(features_fair)
# ✓ No protected attributes detected in feature set.
#   Run a proxy variable audit next - see proxy-variables.md
```

### Check a trained sklearn model's feature list

```python
from sklearn.pipeline import Pipeline

def audit_sklearn_model(model, feature_names, protected=PROTECTED_ATTRIBUTES):
    """
    Given a fitted sklearn model (or Pipeline) and its input feature names,
    flag any protected attributes present in the training features.
    """
    print("=== Disparate Treatment Audit ===")
    print(f"Features used: {list(feature_names)}\n")
    flagged = disparate_treatment_audit(feature_names, protected)

    if flagged:
        print(f"\nThis model engaged in disparate treatment.")
        print(f"Remove flagged features and recheck for disparate impact via")
        print(f"proxy variable audit before redeployment.")
    return flagged


# Example
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

df = pd.read_csv('AI_Fair_Recruitment_Dataset.csv')
feature_cols = ['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score']
X = pd.get_dummies(df[feature_cols])
y = (df['Hiring_Decision'] == 1).astype(int)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

audit_sklearn_model(model, feature_cols)
```

### The full two-stage check: treatment → impact

```python
def full_discrimination_audit(feature_columns, y_true, y_pred, group_series):
    """
    Stage 1: Disparate treatment - are protected attributes in the feature set?
    Stage 2: Disparate impact   - does the outcome gap exceed the four-fifths threshold?

    Run both regardless: treatment can exist without impact, and impact without treatment.
    """
    print("=== Stage 1: Disparate Treatment ===")
    flagged = disparate_treatment_audit(feature_columns)

    print("\n=== Stage 2: Disparate Impact ===")
    results = pd.DataFrame({'y_pred': y_pred, 'group': group_series})
    rates = results.groupby('group')['y_pred'].mean()
    ratio = rates.min() / rates.max()
    passes = ratio >= 0.80

    print("Positive prediction rates by group:")
    print(rates.round(4).to_string())
    print(f"\nDisparate impact ratio: {ratio:.3f}  "
          f"{'✓ passes' if passes else '✗ fails'} four-fifths rule")

    return {'disparate_treatment': flagged, 'di_ratio': round(ratio, 3), 'passes_eeoc': passes}
```

---

## The Proxy Problem: Indirect Disparate Treatment

Removing the protected attribute stops *direct* disparate treatment. It does not stop *indirect* disparate treatment - where a correlated feature serves as a stand-in for the protected attribute the model is no longer permitted to see.

Courts have recognised this. In *Watson v. Fort Worth Bank & Trust* (1988), the Supreme Court held that facially neutral criteria that serve as proxies for protected characteristics can constitute disparate treatment - not just disparate impact - when the intent to use them as substitutes can be shown.

In algorithmic systems, proving intent is difficult. But the structure of indirect disparate treatment is mechanical and detectable:

```python
from scipy.stats import chi2_contingency

def proxy_treatment_check(df, feature_col, protected_col, threshold=0.05):
    """
    Test whether a feature is statistically associated with a protected attribute.
    A significant result (p < threshold) indicates potential indirect disparate treatment
    if the feature is included despite known correlation.
    """
    ct = pd.crosstab(df[feature_col], df[protected_col])
    chi2, p, dof, expected = chi2_contingency(ct)
    flag = p < threshold

    print(f"{feature_col} ~ {protected_col}:  χ²={chi2:.2f}, p={p:.4f}  "
          f"{'⚠ correlated - proxy risk' if flag else '✓ not significantly correlated'}")
    return flag

# Example - German Credit Lending: employment tenure as age proxy
# (German Credit Lending/credit_customers.csv has no `age_class` column -
# `is_young` is derived from the real `age` column, exactly as fair.py/unfair.py do)
df['is_young'] = (df['age'] < 30).astype(int)
proxy_treatment_check(df, feature_col='employment', protected_col='is_young')
```

If a feature is significantly correlated with the protected attribute *and* you knowingly include it in the model, the case for indirect disparate treatment strengthens. The safest position is to document the decision either way. See [`proxy-variables.md`](proxy-variables.md) for the full proxy detection methodology.

---

## Limitations

**Intent is legally required but technically invisible.** Disparate treatment doctrine requires that the protected characteristic was *used* as a factor - which in ML terms means it was in the feature set, or a proxy was included with knowledge of its correlation. A model that produces equal outcomes using race as a feature technically engaged in disparate treatment even though the outcome was fair. The law cares about the process, not just the result.

**The BFOQ defence is narrower than most employers assume.** The Bona Fide Occupational Qualification exception - which allows using a protected attribute if it is genuinely necessary for the job - is extremely narrow under Title VII. Sex is permissible as a criterion for a role in a women's shelter. Age is permissible for an airline pilot under FAA safety rules. Race is almost never a permissible BFOQ. Do not rely on BFOQ as a general defence for including protected attributes in a model.

**Removing protected attributes does not eliminate all legal exposure.** A model with no protected attributes in its feature set can still produce a disparate impact ratio that fails the four-fifths rule - because proxy variables remain. Clearing the disparate treatment audit is the first step, not the last. Always follow it with a disparate impact audit and a proxy variable check.

**Intersectionality is not captured by single-attribute audits.** Auditing for `Gender` alone and `Race` alone can both pass while a model systematically discriminates against Black women specifically. Run the feature audit and the impact audit across all relevant intersecting combinations where sample sizes allow.

---

## Related Concepts

### Disparate Impact
Disparate impact is the outcome-based counterpart - a facially neutral process that produces unequal results across groups. You can have one without the other, but in practice biased models produce both. The fix for disparate treatment (remove the attribute) is necessary but not sufficient to fix disparate impact. See [`disparate-impact.md`](disparate-impact.md).

### Proxy Variables
The mechanism by which disparate treatment persists after the protected attribute is removed. If you drop `Gender` but keep `Age` - which correlates with gender in the dataset - the model reconstructs gender signal from age. That is proxy-based disparate treatment. See [`proxy-variables.md`](proxy-variables.md).

### Demographic Parity
The fairness metric that directly measures the downstream outcome of disparate treatment: equal positive prediction rates across groups. A model free of disparate treatment may still fail demographic parity if proxies remain. See [`demographic-parity.md`](demographic-parity.md).

---

## Related Projects in This Repo

- [`AI Fair Recruitment/`](../AI%20Fair%20Recruitment/) - `unfair.py` includes `Gender` and `Age` directly; `fair.py` removes both. The cleanest before/after disparate treatment example in the repo.
- [`COMPAS/`](../COMPAS/) - `unfair.py` includes `race` and `CustodyStatus` (a race proxy) directly. Removing both in `fair.py` ends both the disparate treatment and reduces the disparate impact gap from 86.77pp to 15.69pp.
- [`German Credit Lending/`](../German%20Credit%20Lending/) - `unfair.py` includes `age` and `employment` (an age proxy). The proxy relationship is documented in the notebook.
- [`explainers/disparate-impact.md`](disparate-impact.md) - the outcome-based counterpart; the four-fifths rule and how it is measured
- [`explainers/proxy-variables.md`](proxy-variables.md) - how indirect disparate treatment survives attribute removal and how to detect it
- [`explainers/demographic-parity.md`](demographic-parity.md) - the downstream metric that disparate treatment violations typically produce

---

## Further Reading

- [Title VII of the Civil Rights Act of 1964, 42 U.S.C. §2000e-2](https://www.eeoc.gov/statutes/title-vii-civil-rights-act-1964) - the statutory basis for both disparate treatment and disparate impact doctrine
- [*McDonnell Douglas Corp. v. Green*, 411 U.S. 792 (1973)](https://supreme.justia.com/cases/federal/us/411/792/) - the Supreme Court case establishing the burden-shifting framework for disparate treatment claims
- [*Watson v. Fort Worth Bank & Trust*, 487 U.S. 977 (1988)](https://supreme.justia.com/cases/federal/us/487/977/) - extended disparate impact analysis to subjective criteria; relevant to proxy-based indirect treatment
- [Barocas & Selbst (2016): *Big Data's Disparate Impact*, 104 Calif. L. Rev. 671](https://www.californialawreview.org/print/2-big-datas-disparate-impact) - the definitive law review article mapping both doctrines onto algorithmic decision-making
- [EEOC: Prohibited Employment Policies/Practices](https://www.eeoc.gov/prohibited-employment-policiespractices) - plain-language EEOC guidance distinguishing disparate treatment from disparate impact in employment contexts

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
