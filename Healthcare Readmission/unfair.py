import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score

from faircode.significance import significance_report, intersectional_report

# ============================================================
# HOSPITAL READMISSION BIAS AUDIT - BIASED MODEL
# Dataset: Diabetes 130-US Hospitals (1999–2008)
# https://www.kaggle.com/datasets/brandao/diabetes
#
# Framing: 30-day readmission used as a clinical risk flag -
# the same logic used by hospital readmission prediction tools
# to allocate follow-up care and discharge planning resources.
#
# Protected attributes included: race, gender, age
# Proxy variables included:
#   payer_code          → encodes income and race. Medicaid
#                         patients are disproportionately
#                         Hispanic (9.0%) and other minorities
#                         vs Caucasian (2.7%). Self-pay encodes
#                         lack of insurance - a socioeconomic
#                         signal tightly correlated with race.
#   discharge_disposition_id → encodes access to post-acute
#                         care. SNF discharge rates differ
#                         by race: Caucasian 17.3% vs
#                         AfricanAmerican 10.7%. Discharge
#                         destination reflects wealth and
#                         insurance coverage, not clinical need.
#   medical_specialty   → encodes socioeconomic access.
#                         Specialty access is stratified by
#                         insurance type and geography, both
#                         of which correlate with race.
#   number_inpatient    → prior hospitalisation count carries
#                         race signal: AfricanAmerican patients
#                         average 0.70 prior visits vs 0.48
#                         for Asian patients - a gap driven by
#                         differential access to preventive
#                         care, not clinical severity alone.
# ============================================================

df = pd.read_csv(Path(__file__).parent / 'diabetic_data.csv')

# Remove invalid entries
df = df[~df['race'].isin(['?'])]
df = df[df['gender'] != 'Unknown/Invalid']

# Target: 1 = readmitted within 30 days (flagged as high-risk)
#         0 = not readmitted within 30 days
# In a clinical tool: model flags 1 as "high readmission risk"
# → triggers resource allocation, discharge planning scrutiny
df['target'] = (df['readmitted'] == '<30').astype(int)

# Protected attribute flags for fairness measurement
df['is_female']     = (df['gender'] == 'Female').astype(int)
df['is_minority']   = (~df['race'].isin(['Caucasian', 'Asian'])).astype(int)
df['age_numeric']   = df['age'].str.extract(r'\[(\d+)').astype(int)
df['is_elderly']    = (df['age_numeric'] >= 70).astype(int)

# ── PROXY VARIABLE ANALYSIS ──────────────────────────────────
print("=" * 62)
print("PROXY VARIABLE ANALYSIS")
print("=" * 62)

print("\nMedicaid payer rate by race:")
df['is_medicaid'] = (df['payer_code'] == 'MD').astype(int)
medicaid_race = df.groupby('race')['is_medicaid'].mean().round(3)
for r, v in medicaid_race.items():
    print(f"  {r:<22} {v:.1%}")
print("  → Medicaid encodes low income, which correlates with race.")
print("    Hispanic: 9.0%, AfricanAmerican: 5.5%, Caucasian: 2.7%")

print("\nSelf-pay rate by race:")
df['is_selfpay'] = (df['payer_code'] == 'SP').astype(int)
selfpay_race = df.groupby('race')['is_selfpay'].mean().round(3)
for r, v in selfpay_race.items():
    print(f"  {r:<22} {v:.1%}")
print("  → Self-pay = uninsured. Higher among Asian, Other, and Hispanic")
print("    patients than Caucasian; AfricanAmerican is actually lower (2.6%")
print("    vs 5.2%) - self-pay doesn't track the same minority/majority")
print("    split as the Medicaid-rate proxy above.")

print("\nSNF (skilled nursing) discharge rate by race:")
df['discharged_to_snf'] = df['discharge_disposition_id'].isin([2, 3]).astype(int)
snf_race = df.groupby('race')['discharged_to_snf'].mean().round(3)
for r, v in snf_race.items():
    print(f"  {r:<22} {v:.1%}")
print("  → SNF access requires insurance coverage and nearby facility.")
print("    Caucasian: 17.3% vs AfricanAmerican: 10.7%.")
print("    Lower SNF access → higher home readmission risk - encoding")
print("    structural inequality as individual clinical risk.")

print("\nMean prior inpatient visits by race:")
prior_in = df.groupby('race')['number_inpatient'].mean().round(3)
for r, v in prior_in.items():
    print(f"  {r:<22} {v:.3f}")
print("  → AfricanAmerican patients average 0.70 prior visits vs")
print("    0.48 for Asian patients. Gap reflects differential access")
print("    to preventive care, not higher inherent clinical risk.")
print()

# Encode categoricals
cat_cols = [
    'race', 'gender', 'age', 'payer_code', 'medical_specialty',
    'diag_1', 'diag_2', 'diag_3', 'max_glu_serum', 'A1Cresult',
    'metformin', 'insulin', 'change', 'diabetesMed'
]
le = LabelEncoder()
df_enc = df.copy()
for col in cat_cols:
    df_enc[col] = le.fit_transform(df_enc[col].astype(str))

# ── FEATURES - BIASED (includes protected attrs + proxies) ───
features = [
    'race',                      # protected attribute ✗
    'gender',                    # protected attribute ✗
    'age',                       # protected attribute ✗
    'payer_code',                # proxy: encodes income + race ✗
    'discharge_disposition_id',  # proxy: encodes insurance/wealth ✗
    'medical_specialty',         # proxy: encodes insurance access ✗
    'number_inpatient',          # proxy: encodes preventive care access ✗
    'admission_type_id',
    'admission_source_id',
    'time_in_hospital',
    'num_lab_procedures',
    'num_procedures',
    'num_medications',
    'number_outpatient',
    'number_emergency',
    'number_diagnoses',
    'max_glu_serum',
    'A1Cresult',
    'insulin',
    'change',
    'diabetesMed',
    'diag_1',
    'diag_2',
    'diag_3',
]

X = df_enc[features]
y = df_enc['target']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

accuracy = accuracy_score(y_test, model.predict(X_test))

# ── MEASURE FAIRNESS GAPS ────────────────────────────────────
results = X_test.copy()
results['pred']       = model.predict(X_test)
results['is_female']  = df.loc[X_test.index, 'is_female'].values
results['is_minority'] = df.loc[X_test.index, 'is_minority'].values
results['is_elderly'] = df.loc[X_test.index, 'is_elderly'].values

sex_flag   = results.groupby('is_female')['pred'].mean()
race_flag  = results.groupby('is_minority')['pred'].mean()
age_flag   = results.groupby('is_elderly')['pred'].mean()

print("=" * 62)
print("BIASED MODEL - RESULTS")
print("=" * 62)
print(f"\nModel Accuracy: {accuracy:.2%}\n")

print("── High-Risk Flag Rate by Gender ────────────────────────")
print(f"  Male patients      : {sex_flag[0]:.2%} flagged high-risk")
print(f"  Female patients    : {sex_flag[1]:.2%} flagged high-risk")
sex_sig = significance_report(results[results['is_female'] == 0]['pred'],
                              results[results['is_female'] == 1]['pred'])
print(f"\n  Fairness Gap (Gender): {sex_sig['gap']:.2%}")
print(f"  95% CI: [{sex_sig['ci_low']:.2%}, {sex_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {sex_sig['p_value']:.4f} "
      f"({'significant' if sex_sig['significant'] else 'not significant'} at α=0.05)")
if sex_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={sex_sig['n_a']} vs {sex_sig['n_b']} (<30)")

print("\n── High-Risk Flag Rate by Race ──────────────────────────")
print(f"  Caucasian/Asian    : {race_flag[0]:.2%} flagged high-risk")
print(f"  Other minorities   : {race_flag[1]:.2%} flagged high-risk")
race_sig = significance_report(results[results['is_minority'] == 0]['pred'],
                               results[results['is_minority'] == 1]['pred'])
print(f"\n  Fairness Gap (Race): {race_sig['gap']:.2%}")
print(f"  95% CI: [{race_sig['ci_low']:.2%}, {race_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {race_sig['p_value']:.4f} "
      f"({'significant' if race_sig['significant'] else 'not significant'} at α=0.05)")
if race_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={race_sig['n_a']} vs {race_sig['n_b']} (<30)")

print("\n── High-Risk Flag Rate by Age ───────────────────────────")
print(f"  Under 70           : {age_flag[0]:.2%} flagged high-risk")
print(f"  70+ (elderly)      : {age_flag[1]:.2%} flagged high-risk")
age_sig = significance_report(results[results['is_elderly'] == 0]['pred'],
                              results[results['is_elderly'] == 1]['pred'])
print(f"\n  Fairness Gap (Age): {age_sig['gap']:.2%}")
print(f"  95% CI: [{age_sig['ci_low']:.2%}, {age_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {age_sig['p_value']:.4f} "
      f"({'significant' if age_sig['significant'] else 'not significant'} at α=0.05)")
if age_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={age_sig['n_a']} vs {age_sig['n_b']} (<30)")

# ── INTERSECTIONAL GAP: Female × Minority ────────────────────
# Gender and race each report a marginal gap above; crossing them
# checks the doubly-disadvantaged cell (minority women) against
# the baseline (non-minority men) to see if the harm compounds.
inter = intersectional_report(
    results['pred'],
    results['is_female'] == 1,     # disadvantaged side of gender
    results['is_minority'] == 1,   # disadvantaged side of race
)
isr = inter['intersectional']
marg_sum = abs(inter['gap_a_alone']) + abs(inter['gap_b_alone'])
print("\n── Intersectional: Female × Minority ────────────────────")
print(f"  {'Both (minority women)':<25}: {inter['cell_rates']['both']:.2%}  (n={inter['cell_sizes']['both']})")
print(f"  {'Neither (baseline)':<25}: {inter['cell_rates']['neither']:.2%}  (n={inter['cell_sizes']['neither']})")
print(f"  {'Marginal gap (sex alone)':<25}: {inter['gap_a_alone']:.2%}")
print(f"  {'Marginal gap (race alone)':<25}: {inter['gap_b_alone']:.2%}")
print(f"  {'Intersectional gap':<25}: {isr['gap']:.2%}  [CI: {isr['ci_low']:.2%}, {isr['ci_high']:.2%}]  "
      f"p={isr['p_value']:.4f} ({'significant' if isr['significant'] else 'not significant'})")
if inter['superadditive']:
    print(f"  Superadditive: yes - compounded gap exceeds the sum of marginal gaps ({marg_sum:.2%})")
else:
    print(f"  Superadditive: no - compounded gap is within the sum of marginal gaps ({marg_sum:.2%})")
if isr['small_sample_warning']:
    print(f"  Small-sample warning: doubly-disadvantaged cell n={isr['n_a']} vs baseline n={isr['n_b']} (<30)")

print("\n" + "=" * 62)
print("WHAT'S WRONG")
print("=" * 62)
print("""
This model includes race, gender, and age as direct inputs -
all protected attributes under Title VI, the ADA, and Section
1557 of the ACA, which prohibit discrimination in healthcare
programmes that receive federal funding.

It also includes four proxy variables:

  payer_code          → Medicaid status encodes low income,
                        which is correlated with race by
                        structural gaps in employment and
                        insurance access. A model that penalises
                        Medicaid patients is penalizing poverty -
                        and penalizing poverty in healthcare
                        disproportionately penalises minority
                        patients.

  discharge_disposition_id → SNF (skilled nursing facility)
                        placement requires insurance coverage and
                        nearby facility access. Caucasian patients
                        are discharged to SNFs at 17.3% vs 10.7%
                        for AfricanAmerican patients. The model
                        learns that minority patients go home -
                        and then uses that as a risk signal,
                        when in fact it is a resource-access signal.

  medical_specialty   → Specialty care access is determined by
                        insurance type and geography, not clinical
                        presentation alone. Including specialty
                        lets the model encode differential access
                        to care as if it were a clinical variable.

  number_inpatient    → Prior hospitalisation counts are higher
                        for AfricanAmerican patients (0.70 vs 0.48
                        for Asian patients). A portion of this
                        gap reflects underinvestment in preventive
                        care in minority communities - not higher
                        individual risk. Training on it amplifies
                        that structural gap.

Run fair.py to see the fix.
""")