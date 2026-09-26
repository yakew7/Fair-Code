import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

from faircode.significance import significance_report

# 1. Load the dataset
df = pd.read_csv(Path(__file__).parent / 'AI_Fair_Recruitment_Dataset.csv')

# Drop missing metrics safely
df = df.dropna(subset=['Hiring_Decision', 'Gender', 'Age', 'Experience_Years', 'Technical_Test_Score'])
y = df['Hiring_Decision']

# 2. Features for the BIASED model (Includes Gender and Age)
biased_features = ['Gender', 'Age', 'Experience_Years', 'Technical_Test_Score']
X = pd.get_dummies(df[biased_features], drop_first=True)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Train Model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 4. Calculate the Bias Gap
test_results = X_test.copy()
test_results['prediction'] = model.predict(X_test)
test_results['gender'] = df.loc[X_test.index, 'Gender']

# Gender has a third category (Other, 5,881 rows) - compare Male vs Female only,
# matching audit.yaml's disadvantaged_values: [Female] / advantaged_values: [Male]
male_pred = test_results[test_results['gender'] == 'Male']['prediction']
female_pred = test_results[test_results['gender'] == 'Female']['prediction']
male_hire_rate = male_pred.mean()
female_hire_rate = female_pred.mean()

sig = significance_report(male_pred, female_pred)

print("=" * 40)
print("--- BIASED MODEL OUTPUT (unfair.jpg) ---")
print(f"Male Candidate Hire Rate: {male_hire_rate:.2%}")
print(f"Female Candidate Hire Rate: {female_hire_rate:.2%}")
print(f"Original Fairness Gap: {sig['gap']:.2%}")
print(f"95% CI: [{sig['ci_low']:.2%}, {sig['ci_high']:.2%}] (bootstrap, n=10,000 resamples)")
print(f"Permutation test p-value: {sig['p_value']:.4f} "
      f"({'statistically significant' if sig['significant'] else 'not statistically significant'} at α=0.05)")
if sig['small_sample_warning']:
    print(f"Small-sample warning: n={sig['n_a']} vs {sig['n_b']} (<30) - interpret with caution")
print("=" * 40)