import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score

from faircode.significance import significance_report, intersectional_report

# ============================================================
# BENEFITS DENIAL BIAS AUDIT - FAIR MODEL
# Dataset: UCI Adult Census Income
# https://www.kaggle.com/datasets/wenruliu/adult-income-dataset
#
# Protected attributes removed: sex, race, native.country, age
# Proxy variables removed:
#   relationship   → near-perfect sex encoding (Husband/Wife)
#   marital.status → reconstructs sex via spousal status
#   hours.per.week → encodes caregiving gender gap, not need
#   occupation     → encodes racial occupational segregation
#   fnlwgt         → census sampling weight; no causal link
#                    to individual eligibility, and may carry
#                    demographic weighting artefacts
#
# Retained: objective economic signals that benefits law
# explicitly uses as eligibility criteria -
#   workclass      → employment sector (government, private…)
#   education /    → human capital: education level and years
#   education.num
#   capital.gain / → financial assets: savings and investment
#   capital.loss     signals that directly affect means tests
# ============================================================

df = pd.read_csv(Path(__file__).parent / 'adult.csv')

df['target']    = (df['income'] == '>50K').astype(int)
df['is_female'] = (df['sex'] == 'Female').astype(int)
df['is_foreign'] = (df['native.country'] != 'United-States').astype(int)
df['is_elderly'] = (df['age'] >= 55).astype(int)
df['is_minority'] = (~df['race'].isin(['White', 'Asian-Pac-Islander'])).astype(int)

# ── PROXY VARIABLE ANALYSIS (retained for comparison) ────────
print("=" * 62)
print("PROXY VARIABLE ANALYSIS - WHY EACH FEATURE WAS DROPPED")
print("=" * 62)

print("""
  age            → protected. Age discrimination in benefits
                   eligibility is prohibited under the Age
                   Discrimination Act.

  sex            → protected. Title VII and the Equal Pay Act
                   prohibit sex-based distinctions in income-
                   support programme design.

  race           → protected. Equal protection and Title VI
                   prohibit race-based eligibility decisions
                   in any federally-funded programme.

  native.country → protected (national origin). Foreign-born
                   applicants are flagged ineligible at 4.40%
                   lower rates in the biased model - not
                   because of economic differences, but because
                   the country variable encodes labour market
                   discrimination into the prediction.

  relationship   → proxy: Husband=0% female, Wife=0% male.
                   A sex label renamed as a family role.

  marital.status → proxy: encodes sex via spousal status.
                   Male applicants are 'Married-civ-spouse'
                   at 4× the female rate.

  hours.per.week → proxy: women average 6 fewer hours/week
                   due to unpaid caregiving, not lower
                   economic need or effort.

  occupation     → proxy: racial occupational segregation
                   means job titles carry race signal.
                   penalizing low-skill occupations
                   penalizes race through labour history.

  fnlwgt         → census sampling weight. No causal link
                   to individual eligibility. May carry
                   demographic weighting artefacts from
                   historical census methodology.
""")

# Encode categoricals - only neutral ones remain
cat_cols = ['workclass', 'education']
le = LabelEncoder()
df_enc = df.copy()
for col in cat_cols:
    df_enc[col] = le.fit_transform(df_enc[col].astype(str))

# ── FEATURES - FAIR (policy-defined eligibility signals only) ─
features = [
    # age            removed ✓ (protected attribute)
    'workclass',       # retained: sector of employment
    # fnlwgt         removed ✓ (census weight artefact)
    'education',       # retained: human capital signal
    'education.num',   # retained: same signal, numeric form
    # marital.status removed ✓ (proxy: encodes sex)
    # occupation     removed ✓ (proxy: encodes race)
    # relationship   removed ✓ (proxy: near-perfect sex encoding)
    # race           removed ✓ (protected attribute)
    # sex            removed ✓ (protected attribute)
    'capital.gain',    # retained: financial asset signal
    'capital.loss',    # retained: financial asset signal
    # hours.per.week removed ✓ (proxy: encodes sex via caregiving gap)
    # native.country removed ✓ (protected attribute: national origin)
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
results['is_foreign'] = df.loc[X_test.index, 'is_foreign'].values
results['is_elderly'] = df.loc[X_test.index, 'is_elderly'].values
results['is_minority'] = df.loc[X_test.index, 'is_minority'].values

sex_flag  = results.groupby('is_female')['pred'].mean()
geo_flag  = results.groupby('is_foreign')['pred'].mean()
age_flag  = results.groupby('is_elderly')['pred'].mean()
race_flag = results.groupby('is_minority')['pred'].mean()

print("=" * 62)
print("FAIR MODEL - MITIGATED RESULTS")
print("=" * 62)
print(f"\nModel Accuracy: {accuracy:.2%}\n")

print("── Ineligibility Flag Rate by Sex ───────────────────────")
print(f"  Male applicants    : {sex_flag[0]:.2%} flagged ineligible")
print(f"  Female applicants  : {sex_flag[1]:.2%} flagged ineligible")
sex_sig = significance_report(results[results['is_female'] == 0]['pred'],
                              results[results['is_female'] == 1]['pred'])
print(f"\n  New Fairness Gap (Sex): {sex_sig['gap']:.2%}")
print(f"  95% CI: [{sex_sig['ci_low']:.2%}, {sex_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {sex_sig['p_value']:.4f} "
      f"({'significant' if sex_sig['significant'] else 'not significant'} at α=0.05)")
if sex_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={sex_sig['n_a']} vs {sex_sig['n_b']} (<30)")

print("\n── Ineligibility Flag Rate by National Origin ───────────")
print(f"  US-born            : {geo_flag[0]:.2%} flagged ineligible")
print(f"  Foreign-born       : {geo_flag[1]:.2%} flagged ineligible")
geo_sig = significance_report(results[results['is_foreign'] == 0]['pred'],
                              results[results['is_foreign'] == 1]['pred'])
print(f"\n  New Fairness Gap (Origin): {geo_sig['gap']:.2%}")
print(f"  95% CI: [{geo_sig['ci_low']:.2%}, {geo_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {geo_sig['p_value']:.4f} "
      f"({'significant' if geo_sig['significant'] else 'not significant'} at α=0.05)")
if geo_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={geo_sig['n_a']} vs {geo_sig['n_b']} (<30)")

print("\n── Ineligibility Flag Rate by Age ───────────────────────")
print(f"  Under 55           : {age_flag[0]:.2%} flagged ineligible")
print(f"  55+ (elderly)      : {age_flag[1]:.2%} flagged ineligible")
age_sig = significance_report(results[results['is_elderly'] == 0]['pred'],
                              results[results['is_elderly'] == 1]['pred'])
print(f"\n  New Fairness Gap (Age): {age_sig['gap']:.2%}")
print(f"  95% CI: [{age_sig['ci_low']:.2%}, {age_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {age_sig['p_value']:.4f} "
      f"({'significant' if age_sig['significant'] else 'not significant'} at α=0.05)")
if age_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={age_sig['n_a']} vs {age_sig['n_b']} (<30)")

print("\n── Ineligibility Flag Rate by Race ──────────────────────")
print(f"  White/Asian-PI     : {race_flag[0]:.2%} flagged ineligible")
print(f"  Other minorities   : {race_flag[1]:.2%} flagged ineligible")
race_sig = significance_report(results[results['is_minority'] == 0]['pred'],
                               results[results['is_minority'] == 1]['pred'])
print(f"\n  New Fairness Gap (Race): {race_sig['gap']:.2%}")
print(f"  95% CI: [{race_sig['ci_low']:.2%}, {race_sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"  Permutation p-value: {race_sig['p_value']:.4f} "
      f"({'significant' if race_sig['significant'] else 'not significant'} at α=0.05)")
if race_sig['small_sample_warning']:
    print(f"  Small-sample warning: n={race_sig['n_a']} vs {race_sig['n_b']} (<30)")

# ── INTERSECTIONAL GAP: Female × Minority ────────────────────
# Same cross as unfair.py, so the mitigation can be judged on the
# compounded gap too - proxy removal may close the marginal gaps
# without closing the intersectional one.
inter = intersectional_report(
    results['pred'],
    results['is_female'] == 1,     # disadvantaged side of sex
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
print("WHAT CHANGED")
print("=" * 62)
print("""
THE FIX: Drop the protected attributes AND their proxies.
         Retain only the policy-defined economic signals.

  sex, race, age, native.country → removed. These are
    protected characteristics. Their presence let the model
    reproduce structural inequalities in the census data
    as if they were legitimate eligibility signals.

  relationship + marital.status → removed together. Either
    one alone lets the model reconstruct sex almost perfectly.
    Both had to go. This is the same logic as dropping both
    'region' and 'office_type' - keeping one makes removing
    the other meaningless.

  hours.per.week → removed. The 6-hour weekly gap between
    women and men in this dataset is not a measure of economic
    need - it is a measure of how caregiving responsibilities
    are distributed by gender. A benefits model should assess
    financial need, not penalise unpaid domestic labour.

  occupation → removed. Racial occupational segregation is a
    product of discriminatory hiring, credentialing, and
    labour market access - not of individual productivity or
    eligibility. Keeping it lets the model penalise the
    downstream effects of discrimination as if they were
    individual characteristics.

  fnlwgt → removed. The census sampling weight has no causal
    relationship to an individual's benefit eligibility. Its
    only function in the model would be to absorb demographic
    signal - encoding geographic and racial composition of
    census tracts through a numeric weight.

Key Insight: Automated benefits systems don't need to name sex
or race to discriminate by them. 'Husband', 'hours per week',
and occupation are the 'documentation_score' of welfare AI -
features that sound economic but carry protected-class signal
because of structural inequalities baked into how work,
caregiving, and labour markets are organised.

What remains after mitigation: education level, employment
sector, and capital assets. These are the variables that a
means-tested benefits programme can legitimately consult.
""")