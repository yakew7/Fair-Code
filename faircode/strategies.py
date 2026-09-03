"""The five mitigation strategies (S0-S4) - Layer 2 of the benchmark harness.

Given a manifest's core/proxy/protected feature partition, builds the
train/test feature set (and, for S3/S4, fits the fairlearn mitigator) for
five strategies of increasing sophistication:

  S0 baseline                    - every feature; protected attributes and
                                    proxies included as model input. The "do
                                    nothing" reference.
  S1 unawareness                 - protected attribute dropped from the
                                    model input; proxies retained. The naive
                                    fix people assume works.
  S2 unawareness_proxy_removal   - protected attribute AND proxies dropped
                                    from the model input (the classic
                                    fair.py fix every existing audit uses).
  S3 in_processing               - fairlearn ExponentiatedGradient: trains
                                    an ensemble of base estimators under a
                                    fairness constraint (see
                                    FAIRNESS_CONSTRAINT).
  S4 post_processing             - fairlearn ThresholdOptimizer: fits one
                                    base estimator, then finds a per-group
                                    decision threshold over its predicted
                                    probabilities that satisfies the same
                                    constraint.

S3 and S4 use the SAME reduced feature set as S2 (core features only) - so a
residual gap there isn't explained by "the model could still see the
protected attribute or a proxy". The protected attribute is never deleted
from the working dataset (faircode.benchmark keeps it in `protected_masks`
throughout); for S3/S4 it is passed to fairlearn as `sensitive_features`
instead of as a column of X. That is the whole point of comparing S1/S2
against S3/S4: S1/S2 remove the protected attribute's influence by deleting
columns from the model input; S3/S4 remove its influence a different way,
via a fairness constraint, while seeing the identical feature set S2 sees.
Showing that S3/S4 hit roughly the same floor S2 does is what turns "here is
our fix" into "here is the residual floor even stronger tools can't clear".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.api.types as pdt
from fairlearn.postprocessing import ThresholdOptimizer
from fairlearn.reductions import DemographicParity, EqualizedOdds, ExponentiatedGradient
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

STRATEGIES = ("baseline", "unawareness", "unawareness_proxy_removal", "in_processing", "post_processing")

# Every audit is run under the SAME fairness constraint, so an in-processing/
# post-processing comparison across domains stays apples-to-apples. Flip this
# constant (not a per-manifest setting) to re-run the whole benchmark under
# the other constraint.
FAIRNESS_CONSTRAINT = "demographic_parity"  # or "equalized_odds"

_REDUCTIONS_CONSTRAINTS = {
    "demographic_parity": DemographicParity,
    "equalized_odds": EqualizedOdds,
}

# ExponentiatedGradient deep-copies and refits the base estimator once per
# iteration (its default max_iter is 50). At the row counts several of these
# audits have (Healthcare Readmission ~100k, AI Fair Recruitment ~121k) and
# with GradientBoostingClassifier as the base estimator, even 15 iterations
# measured at 256s for a single (audit, model) cell - 50 would make a full
# seven-domain run impractical. 10 iterations still converges well enough to
# demonstrate the constraint's effect. Raise this for a final,
# paper-quality run where wall-clock time isn't the binding constraint.
EXPONENTIATED_GRADIENT_MAX_ITER = 50


def encode_features(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """Label-encode categorical columns, pass numeric columns through.

    Uniform ordinal encoding (rather than one-hot) keeps the harness code
    path identical across audits regardless of a categorical column's
    cardinality - several audits (e.g. Healthcare Readmission's ICD
    diagnosis codes) have hundreds of categories, where one-hot encoding
    would blow up the feature matrix differently per audit. Missing values
    are filled (median for numeric, a sentinel category for categorical) so
    every model family gets a fully-populated matrix.
    """
    out = pd.DataFrame(index=df.index)
    for col in columns:
        series = df[col]
        if pdt.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            median = numeric.median()
            out[col] = numeric.fillna(0.0 if pd.isna(median) else median)
        else:
            filled = series.astype(str).fillna("__missing__")
            out[col] = LabelEncoder().fit_transform(filled)
    return out


def strategy_features(strategy: str, core: list, proxies: list, protected: list) -> list:
    if strategy == "baseline":
        return list(dict.fromkeys(core + proxies + protected))
    if strategy == "unawareness":
        return list(dict.fromkeys(core + proxies))
    if strategy in ("unawareness_proxy_removal", "in_processing", "post_processing"):
        return list(core)
    raise ValueError(f"unknown strategy: {strategy!r}")


def fit_in_processing(base_model, X_train, y_train, sensitive_train):
    """S3 - fairlearn ExponentiatedGradient (Agarwal et al. 2018).

    base_model is a fresh, unfit estimator; ExponentiatedGradient deep-copies
    it internally for each iteration and returns a randomized mixture over
    the resulting ensemble. sensitive_train is passed as `sensitive_features`
    - never as a column of X_train - so the constraint sees group membership
    without the base estimator ever training on it directly.
    """
    constraint = _REDUCTIONS_CONSTRAINTS[FAIRNESS_CONSTRAINT]()
    mitigator = ExponentiatedGradient(
        base_model, constraints=constraint, max_iter=EXPONENTIATED_GRADIENT_MAX_ITER)
    mitigator.fit(X_train, y_train, sensitive_features=sensitive_train)
    return mitigator


def predict_in_processing(mitigator, X_test, random_state):
    """Predict with an S3 mitigator. Returns (y_pred, y_proba); y_proba comes
    from fairlearn's internal (undocumented-but-stable) _pmf_predict - the
    probability-weighted mixture over the ensemble - and falls back to None
    (no AUC for this run) if a future fairlearn version removes it."""
    y_pred = np.asarray(mitigator.predict(X_test, random_state=random_state)).astype(int)
    try:
        y_proba = np.asarray(mitigator._pmf_predict(X_test))[:, 1]
    except (AttributeError, IndexError):
        y_proba = None
    return y_pred, y_proba


def fit_post_processing(base_model, X_train, y_train, sensitive_train,
                        random_state=42, calibration_size=0.3):
    """S4 - fairlearn ThresholdOptimizer (Hardt, Price & Srebro 2016 style).

    base_model is fit on a FIT split of the training data; per-group
    thresholds are then calibrated on a separate, held-out CALIBRATION split
    of that same training data (prefit=True). Calibrating thresholds against
    the same rows the base estimator was fit on - fairlearn's default
    prefit=False behaviour - lets an overfit classifier's in-sample
    confidence produce thresholds that don't generalize: on German Credit
    Lending this produced a near-zero demographic parity gap on the
    calibration data (as designed) but a gap of +0.22 on the held-out test
    set, because the base RandomForest's in-sample predict_proba is far more
    confident than its out-of-sample behaviour. This is the same failure
    mode faircode.benchmark's predecessor threshold-search had to work
    around with cross_val_predict; here it's solved by simply not
    calibrating against the rows the model memorized.
    """
    idx = np.arange(len(y_train))
    stratify = y_train if len(np.unique(y_train)) > 1 else None
    fit_idx, calib_idx = train_test_split(
        idx, test_size=calibration_size, random_state=random_state, stratify=stratify)

    base_model.fit(X_train.iloc[fit_idx], y_train[fit_idx])
    optimizer = ThresholdOptimizer(
        estimator=base_model, constraints=FAIRNESS_CONSTRAINT,
        predict_method="predict_proba", prefit=True)
    optimizer.fit(X_train.iloc[calib_idx], y_train[calib_idx],
                 sensitive_features=sensitive_train[calib_idx])
    return optimizer


def predict_post_processing(optimizer, X_test, sensitive_test, random_state):
    """Predict with an S4 optimizer. Needs sensitive_features at predict
    time too - it must know which group's threshold to apply per row.
    ThresholdOptimizer has no probability output, so y_proba is always None
    (no AUC for this strategy - a hard-threshold post-processor has nothing
    left to rank)."""
    y_pred = np.asarray(optimizer.predict(
        X_test, sensitive_features=sensitive_test, random_state=random_state)).astype(int)
    return y_pred, None
