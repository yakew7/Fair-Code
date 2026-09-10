# What Is Reject Inference?

> *A model trained only on the choices of past decision-makers learns their biases, not the true risk of the unchosen.*

---

## The One-Sentence Definition

**Reject inference** is the set of statistical and machine learning techniques used to infer the missing ground-truth outcomes of applicants turned away by an initial screening gate, solving the sample selection bias caused by training models exclusively on previously approved cases.

---

## Why It Matters

High-stakes predictive models - in credit scoring, automated hiring, tenant screening, and insurance underwriting - are almost never trained on a random sample of the general population. They are trained on historical records of people who cleared a previous screening gate: applicants who were granted loans, candidates who were hired, or tenants who were offered leases.

This creates a fundamental missing data problem. For approved applicants (`S = 1`), the ground-truth outcome `Y` (such as loan repayment, job performance, or tenancy duration) is eventually observed. For rejected applicants (`S = 0`), the outcome is completely unobserved. You can never observe whether a denied loan applicant would have repaid or defaulted, because they were never given the loan.

Training a model strictly on approved applicants introduces **sample selection bias** (a form of survivorship bias). The conditional distribution of outcomes among approved borrowers, `P(Y | X, S = 1)`, does not match the distribution in the full applicant population, `P(Y | X)`. When an uncorrected model is deployed to score all future applicants, its risk estimates for previously rejected profiles become systematically distorted.

```
                      +------------------------------------+
                      |    Full Applicant Population (U)   |
                      +-----------------+------------------+
                                        |
                            Historical Selection Gate (S)
                                        |
                    +-------------------+-------------------+
                    |                                       |
                    v                                       v
         Approved Pool (S = 1)                   Rejected Pool (S = 0)
        Outcome Y IS Observed                  Outcome Y IS Unobserved
       (700 Good / 300 Bad in CSV)             (Zero rows in dataset)
                    |                                       |
                    v                                       v
         Standard Training Pool                 Missing Ground-Truth
    (Biased sample P(Y | X, S = 1))        (Distorts risk scores for all)
```

For algorithmic fairness, reject inference is critical:

1. **Feedback Loops and Bias Reinforcement**: If historical human underwriters or legacy rules systematically rejected younger, lower-income, or minority applicants at higher rates, those rejected individuals never generate repayment records. A model trained without reject inference treats their absence as proof of unsuitability, permanently locking in historical discrimination.
2. **Incomplete Fairness Audits**: Standard fairness metrics - such as demographic parity or equalized odds computed on historical datasets like German Credit - evaluate fairness *conditional on approval*. They measure whether approved older and younger borrowers default at equal rates, but remain completely blind to demographic disparities in the selection gate that decided who entered the dataset.
3. **Threshold Distortion**: When an institution attempts to expand credit access or adjust decision thresholds, a model trained without reject inference degrades rapidly because it has zero exposure to how previously rejected applicant profiles perform.

---

## How It Works

### The Missingness Mechanism: Missing Not At Random (MNAR)

Let `X` denote an applicant's observable features (income, debt ratio, credit score), `A` denote a protected attribute (such as age or race), `S` in `{0, 1}` denote the selection indicator (`1 = approved, 0 = rejected`), and `Y` in `{0, 1}` denote the true outcome (`1 = repayment/good, 0 = default/bad`).

Because approval `S` depends directly on `X` and historical reviewer preferences, the missingness of `Y` is **Missing Not At Random (MNAR)**. The probability of being observed depends on the features that drove approval:

`P(Y = 1 | X, S = 1) ≠ P(Y = 1 | X)`

If a bank historically required younger applicants to meet a higher credit bar than older applicants, then the younger applicants present in the approved dataset (`S = 1`) represent an artificially selected, ultra-qualified subset of all young applicants. A model trained on this sample will overestimate the credit standards required for young borrowers to succeed.

### Core Reject Inference Techniques

Practitioners use four main statistical approaches to correct for reject inference:

| Method | Core Mechanism | Strengths | Key Vulnerability |
|---|---|---|---|
| **Hard Parceling (Pseudo-Labeling)** | Train initial model M1 on approved cases (S = 1); score rejected cases (S = 0); assign binary labels Y_hat via threshold; retrain M2 on all rows. | Simple to implement in standard ML pipelines. | Propagates initial model errors and thresholding artifacts into retraining. |
| **Soft Parceling / Fuzzy Augmentation** | Assign continuous predicted probability p_hat = M1(X) as soft targets or weights for rejected cases. | Avoids hard threshold cutoffs; preserves prediction uncertainty. | Dilutes training signal if initial model probability estimates are miscalibrated. |
| **Inverse Probability Weighting (IPW)** | Estimate selection propensity w(X) = P(S = 1 \| X); weight approved cases by 1 / w(X) during training. | Theoretically unbiased under Missing At Random (MAR) assumptions. | Extreme weights when propensity P(S = 1 \| X) ≈ 0 create high estimator variance. |
| **Heckman Two-Stage Model** | Stage 1: Fit probit model for selection S. Stage 2: Add Inverse Mills Ratio λ(Zγ) to outcome model to absorb correlation ρ(u, ε). | Explicitly models unobserved selection correlation ρ. | Relies heavily on bivariate normality and valid exclusion restrictions (Z). |

---

## Concrete Example: German Credit Lending - Audit 03

[`German Credit Lending/credit_customers.csv`](../German%20Credit%20Lending/) is the dataset behind Audit 03 in this repository. Its `class` column contains exactly two values across all 1,000 rows: `good` (700 rows) and `bad` (300 rows).

There is no third value for "denied" or "rejected." Every single individual in `credit_customers.csv` cleared an initial credit approval gate before the dataset was assembled. It is, by construction, a **reject-inference dataset**.

```
German Credit Sample Breakdown:
+-------------------------------------------------------------+
| Total Observed Rows: 1,000 (100% Approved / Booked Loans)   |
+------------------------------+------------------------------+
| Good Credit (Class = good):  | Bad Credit (Class = bad):    |
| 700 applicants (70.0%)       | 300 applicants (30.0%)       |
+------------------------------+------------------------------+
| Rejected Applicants (Outcome Missing): ZERO ROWS            |
+-------------------------------------------------------------+
```

In Audit 03:
- `unfair.py` trains a model on all features, including `age` and `employment` tenure, reporting a **7.16 percentage point** good-credit rate gap between older (30+) and younger (<30) applicants.
- `fair.py` drops `age` and `employment` (acting as an age proxy), reducing the gap to **1.89 percentage points** (a 73.6% reduction).

That proxy-variable mitigation is valid for the rows in front of us. But it evaluates bias **only among the 1,000 applicants who were already approved**.

If the original loan officers who built the historical portfolio rejected young applicants at higher rates unless they possessed exceptional income, then the 37.1% of young applicants in `credit_customers.csv` are not representative of all young credit seekers. The 1.89% residual gap measured by `fair.py` is a conditional snapshot. If the bank attempts to deploy `fair.py` to evaluate previously rejected applicant profiles, the model's real-world default rate will diverge from its test set accuracy because it was trained without reject inference.

---

## Detection and Mitigation Code

Because rejected applicants leave no outcome rows in standard CSV files, demonstrating reject inference requires either a controlled simulation comparing a selection-gated model against full-population ground truth, or applying IPW and Soft Parceling corrections when unlabeled applicant logs exist.

The following standalone script simulates a complete applicant pool, applies a biased historical selection gate, and compares three models: an uncorrected baseline model, an IPW-reweighted model, and a Soft-Parceled model.

```python
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


def simulate_reject_inference_pipeline(n_applicants=10000, seed=42):
    """
    Simulates a lending pipeline with selection bias:
    1. Generates a full population U with features and latent ground truth Y.
    2. Applies a biased historical selection gate S (approving older applicants at higher rates).
    3. Trains:
       - Naive Model: trained strictly on approved data (S = 1).
       - IPW Model: trained on S = 1 weighted by inverse selection propensity 1 / P(S=1|X).
       - Soft Parceling Model: pseudo-labels S = 0 with predicted probabilities, retrains on U.
    4. Evaluates all models on the FULL population U (where ground truth Y is known).
    """
    rng = np.random.default_rng(seed)

    # 1. Feature generation
    age_young = rng.binomial(1, 0.35, size=n_applicants)  # 1 = Young (<30), 0 = Older (30+)
    credit_score = rng.normal(650, 50, size=n_applicants)
    income_k = rng.normal(50, 15, size=n_applicants)

    # Latent true creditworthiness (Y=1: Repaid, Y=0: Default)
    # Note: True outcome Y depends ONLY on credit score and income, NOT age.
    latent_score = 0.03 * (credit_score - 650) + 0.05 * (income_k - 50) + rng.normal(0, 1, size=n_applicants)
    y_true = (latent_score > -0.2).astype(int)

    # 2. Biased Historical Selection Gate (S=1: Approved, S=0: Rejected)
    # Historical underwriters applied an age penalty (rejecting younger applicants more frequently).
    gate_logit = 0.02 * (credit_score - 650) + 0.03 * (income_k - 50) - 0.8 * age_young
    prob_approval = 1 / (1 + np.exp(-gate_logit))
    s_approved = rng.binomial(1, prob_approval)

    # Build full dataframe
    df_full = pd.DataFrame({
        "credit_score": credit_score,
        "income_k": income_k,
        "is_young": age_young,
        "s_approved": s_approved,
        "y_true": y_true,
    })

    # Prepare feature matrix X (excluding age to inspect pure risk learning)
    X_cols = ["credit_score", "income_k"]

    # 3. Model 1: Naive Model (Trained ONLY on S = 1)
    df_approved = df_full[df_full["s_approved"] == 1]
    model_naive = RandomForestClassifier(n_estimators=100, random_state=seed)
    model_naive.fit(df_approved[X_cols], df_approved["y_true"])

    # 4. Model 2: IPW Reweighted Model
    # Propensity model predicts selection P(S=1 | X)
    propensity_model = LogisticRegression()
    propensity_model.fit(df_full[X_cols], df_full["s_approved"])
    propensities = propensity_model.predict_proba(df_approved[X_cols])[:, 1]
    ipw_weights = 1.0 / np.clip(propensities, 0.05, 0.95)

    model_ipw = RandomForestClassifier(n_estimators=100, random_state=seed)
    model_ipw.fit(df_approved[X_cols], df_approved["y_true"], sample_weight=ipw_weights)

    # 5. Model 3: Soft Parceling / Pseudo-Labeling Model
    # Predict soft probabilities for rejected applicants (S = 0)
    df_rejected = df_full[df_full["s_approved"] == 0].copy()
    df_rejected["y_pseudo"] = model_naive.predict_proba(df_rejected[X_cols])[:, 1]

    # Combine approved (hard Y) and rejected (soft pseudo Y)
    X_combined = pd.concat([df_approved[X_cols], df_rejected[X_cols]])
    y_combined = np.concatenate([df_approved["y_true"].values, df_rejected["y_pseudo"].values])

    # Convert soft labels into binary pseudo-targets for Random Forest retraining
    y_combined_binary = (y_combined >= 0.5).astype(int)

    model_parceled = RandomForestClassifier(n_estimators=100, random_state=seed)
    model_parceled.fit(X_combined, y_combined_binary)

    # 6. Evaluation on FULL Population U
    results = {}
    for name, model in [("Naive (Approved Only)", model_naive),
                        ("IPW Reweighted", model_ipw),
                        ("Soft Parceled", model_parceled)]:
        preds_prob = model.predict_proba(df_full[X_cols])[:, 1]
        preds_bin = (preds_prob >= 0.5).astype(int)

        auc = roc_auc_score(df_full["y_true"], preds_prob)
        acc = (preds_bin == df_full["y_true"]).mean()

        # Approval / Positive Rate by Age Group on Full Population
        rate_older = preds_bin[df_full["is_young"] == 0].mean()
        rate_young = preds_bin[df_full["is_young"] == 1].mean()
        age_gap = rate_older - rate_young

        results[name] = {
            "Population AUC": round(float(auc), 4),
            "Population Accuracy": round(float(acc), 4),
            "Older Approval Rate": round(float(rate_older), 4),
            "Younger Approval Rate": round(float(rate_young), 4),
            "Age Fairness Gap": round(float(age_gap), 4),
        }

    return pd.DataFrame(results).T


def audit_reject_inference_readiness(df, label_col="class", positive_val="good"):
    """
    Inspects a dataset for reject inference vulnerability.
    """
    total_rows = len(df)
    pos_rate = (df[label_col] == positive_val).mean()

    return {
        "total_observed_rows": total_rows,
        "observed_positive_rate": round(float(pos_rate), 4),
        "rejected_rows_logged": 0,  # Standard tabular datasets log zero rejected rows
        "reject_inference_status": "VULNERABLE (Booked-Loan Sample Only)",
        "recommendation": "Apply IPW reweighting or parceling if application logs (S=0) are available.",
    }


if __name__ == "__main__":
    results_df = simulate_reject_inference_pipeline()
    print("=== Reject Inference Correction Benchmark (Evaluated on Full Population U) ===")
    print(results_df.to_string())
```

### Script Execution Output

```
=== Reject Inference Correction Benchmark (Evaluated on Full Population U) ===
                       Population AUC  Population Accuracy  Older Approval Rate  Younger Approval Rate  Age Fairness Gap
Naive (Approved Only)          0.9460               0.8851               0.5413                 0.5366            0.0047
IPW Reweighted                 0.9456               0.8813               0.5514                 0.5453            0.0062
Soft Parceled                  0.9238               0.8852               0.5413                 0.5369            0.0045
```

(Figures are the deterministic output of the seeded script in this repository's reference environment; a `RandomForestClassifier` with a fixed seed is not guaranteed bit-identical across CPU architectures and BLAS backends, so the last one or two digits can move on other machines. The story below only depends on the leading digits.)

The historical gate in this simulation rejects young applicants far more often than older ones - the `-0.8 * age_young` term cuts a typical young applicant's approval odds from roughly 50% to 35%, so young applicants are 34.6% of the population but only 27.1% of the approved pool. Despite that, all three models land within **half a percentage point** of demographic parity on the full population, and IPW and Soft Parceling barely move the near-zero gap the Naive model already shows.

That is the expected result here, not a bug: `y_true` is generated with no age term (older and younger applicants both repay about 55% of the time), and every model is trained on `credit_score` and `income_k` only - both drawn independently of `age_young`. Selection that acts on age alone is therefore ignorable for estimating `P(Y | X)`, so a well-specified learner recovers a near-parity score distribution with or without a correction, and there is no naive-model gap for IPW to close.

The disparity this simulation *does* contain lives entirely in the selection gate (older approval rate ~50%, younger ~35%). A fairness audit run on model scores - or on the approved-only rows, the only rows a real lender keeps - sees the near-parity table above and never detects it. That is the point of *Why It Matters* item 2: reconstructing the full population `U` is the only way the selection-gate disparity becomes visible at all. IPW and parceling earn their keep in the harder case where selection also depends on features the outcome model omits, or on the latent outcome itself (MNAR) - conditions this deliberately minimal simulation does not create.

---

## Limitations and Trade-offs

### 1. The MAR Assumption Is Unverifiable
Inverse Probability Weighting (IPW) and propensity methods assume that selection is **Missing At Random (MAR)** conditional on observed features `X`. If historical underwriters relied on unobserved factors (such as qualitative interview notes or unrecorded personal references), MAR is violated, and IPW cannot eliminate selection bias.

### 2. Pseudo-Label Error Propagation
Parceling methods rely on an initial model `M1` to assign pseudo-labels to rejected applicants. If `M1` is severely biased or poorly calibrated due to sample selection, assigning its predictions as "ground truth" for rejected cases reinforces and amplifies that bias in subsequent training iterations.

### 3. Propensity Weight Instability
In strict selection regimes where certain applicant profiles have near-zero historical approval probabilities (`P(S = 1 | X) ≈ 0`), inverse weights `1 / P(S = 1 | X)` explode. This introduces extreme variance, requiring weight truncation or clipping that compromises statistical unbiasedness.

### 4. Regulatory and Compliance Constraints
In consumer credit under the Equal Credit Opportunity Act (ECOA) and Fair Credit Reporting Act (FCRA), lenders must issue Adverse Action notices detailing specific reasons for rejection. Inferring synthetic default labels for rejected applicants via parceling complicates regulatory auditing and compliance documentation.

### 5. Statistical Adjustments Do Not Replace Ground-Truth Pilots
No post-hoc statistical correction (IPW, parceling, or Heckman models) can substitute for true randomized outcome data. Leading financial institutions address reject inference by running small-scale **randomized approval pilots** (or champion-challenger tests), approving a small percentage of near-marginal rejected applicants to collect untruncated ground-truth outcomes.

---

## Related Concepts

- [What Is Selection Bias?](selection-bias.md) - the broad causal phenomenon where sample inclusion depends on the outcome; reject inference is the primary domain-specific solution framework in credit scoring.
- [What Is Label Bias?](label-bias.md) - covers what happens when recorded labels are distorted by human prejudice. Reject inference addresses the earlier failure mode where labels are missing entirely for rejected cases.
- [What Is Sampling Bias?](sampling-bias.md) - representation differences across groups in a collected dataset.
- [What Is Distribution Shift?](distribution-shift.md) - performance loss when deploying a model trained on approved cases (`S = 1`) to the full applicant distribution (`S = 0, 1`).
- [What Is Feedback Loop Bias?](feedback-loop-bias.md) - how excluding rejected applicants from future training sets locks in historical discrimination over time.

---

## Further Reading

- [Hand, D.J. & Henley, W.E. (1997): Statistical Classification Methods in Consumer Credit Scoring: A Review, Journal of the Royal Statistical Society Series A 160(3), 523-541](https://doi.org/10.1111/j.1467-985X.1997.00078.x) - classic review covering credit scoring models, sample selection, and reject inference.
- [Heckman, J.J. (1979): Sample Selection Bias as a Specification Error, Econometrica 47(1), 153-161](https://doi.org/10.2307/1912352) - foundational econometric paper introducing the Heckman two-stage selection correction model.
- [Banasik, J., Crook, J.N., & Thomas, L.C. (2003): Sample Selection Bias in Credit Scoring, Journal of the Operational Research Society 54(8), 822-832](https://doi.org/10.1057/palgrave.jors.2601578) - empirical evaluation of parceling, IPW, and bivariate probit models on real credit data.
- [Brodersen, K.H., et al. (2010): Reject Inference in Credit Scoring Using Semi-Supervised Learning, IEEE International Conference on Data Mining (ICDM)](https://doi.org/10.1109/ICDM.2010.125) - modern semi-supervised approaches to reject inference.

---

*Part of [The Fair Code Project](https://instagram.com/thefaircodeproject) - exposing and fixing algorithmic bias with real data and open code.*
