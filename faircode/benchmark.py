"""Cross-domain fairness benchmark harness - Layer 2 of the two-layer
architecture documented in faircode/MANIFEST_SPEC.md.

Reads every audit.yaml manifest and runs the SAME pipeline over each one -
five mitigation strategies (faircode.strategies) x three model families
(faircode.models) x six fairness metrics, each with a bootstrap CI and a
permutation p-value (faircode.metrics), plus accuracy/AUC/F1 (also
faircode.metrics), plus the intersectional gap for every pair of declared
protected attributes (faircode.significance.intersectional_report) - and
returns two tidy results tables (fairness, performance). One code path, same
seed, same splits, same metric definitions, for every domain: a cross-domain
comparison is only as trustworthy as that uniformity, and this module is
what makes it literally true rather than an assertion in a write-up.

Contributors add a dataset + audit.yaml (Layer 1). They never touch this
module. faircode.figures reads this module's output tables to render the
paper figures - it never re-runs a model.

Reproducibility: every manifest's `random_state` (all seven ship with 42),
every model family (faircode.models), and every bootstrap/permutation draw
(faircode.significance, faircode.metrics) already take an explicit seed -
nothing here reads numpy's global random state. GLOBAL_SEED exists as a
defense-in-depth seed for any future strategy/model that isn't explicitly
seeded; it is not what makes today's runs reproducible, the explicit seeds
threaded through every call are. Do not change a manifest's random_state on
a run whose numbers are cited anywhere - see "Reproducibility & Paper
Freeze" in README.md before regenerating results/ for a citation.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .manifest import discover_manifests, load_manifest
from .metrics import METRICS, PERFORMANCE_METRICS, compute_metrics, compute_performance_metrics
from .models import MODEL_FAMILIES, build_model
from .significance import intersectional_report
from .strategies import (
    STRATEGIES,
    encode_features,
    fit_in_processing,
    fit_post_processing,
    predict_in_processing,
    predict_post_processing,
    strategy_features,
)

GLOBAL_SEED = 42


def _load_dataset(manifest):
    df = pd.read_csv(manifest.dataset_path, low_memory=False)
    for row_filter in manifest.row_filters:
        df = row_filter.apply(df)
    df = df.reset_index(drop=True)

    y = manifest.target.compute(df)

    protected_masks = {}
    known_mask = pd.Series(True, index=df.index)
    for pa in manifest.protected_attributes:
        disadv, known = pa.disadvantaged_mask(df)
        protected_masks[pa.name] = disadv
        known_mask &= known

    df = df[known_mask].reset_index(drop=True)
    y = y[known_mask].reset_index(drop=True)
    protected_masks = {
        name: mask[known_mask].reset_index(drop=True) for name, mask in protected_masks.items()
    }
    return df, y, protected_masks


def _run_strategy(strategy, model_name, manifest, X_all, y, protected_masks, idx_train, idx_test):
    protected_cols = [pa.column for pa in manifest.protected_attributes]
    feature_cols = strategy_features(strategy, manifest.core_features, manifest.proxy_features, protected_cols)
    X = X_all[feature_cols]
    X_train, X_test = X.iloc[idx_train], X.iloc[idx_test]
    y_train = y.iloc[idx_train].to_numpy()
    y_test = y.iloc[idx_test].to_numpy()
    rs = manifest.random_state

    # S3/S4 key their fairness constraint off the manifest's FIRST declared
    # protected attribute, passed as sensitive_features - never as a column
    # of X_train/X_test. It is not deleted from the dataset anywhere; it
    # simply never entered X_all's column selection for these two strategies
    # (see strategy_features). Every strategy is still scored against every
    # declared protected attribute below, regardless of which one drove S3/S4.
    primary = manifest.protected_attributes[0].name
    sensitive_train = protected_masks[primary].iloc[idx_train].to_numpy().astype(int)
    sensitive_test = protected_masks[primary].iloc[idx_test].to_numpy().astype(int)

    if strategy == "in_processing":
        mitigator = fit_in_processing(build_model(model_name, rs), X_train, y_train, sensitive_train)
        y_pred, y_proba = predict_in_processing(mitigator, X_test, rs)
    elif strategy == "post_processing":
        optimizer = fit_post_processing(
            build_model(model_name, rs), X_train, y_train, sensitive_train, random_state=rs)
        y_pred, y_proba = predict_post_processing(optimizer, X_test, sensitive_test, rs)
    else:
        model = build_model(model_name, rs)
        model.fit(X_train, y_train)
        y_proba = model.predict_proba(X_test)[:, 1]
        y_pred = np.asarray(model.predict(X_test)).astype(int)

    return y_test, y_pred, y_proba


def run_audit(manifest, n_resamples=2000, n_permutations=2000, random_state=None):
    """Run the full strategy x model x metric grid for one manifest.

    Returns (fairness_rows, performance_rows). fairness_rows has one dict per
    (strategy, model, protected attribute, metric), plus one per (strategy,
    model, attribute pair) for the intersectional gap when two or more
    protected attributes are declared. performance_rows has one dict per
    (strategy, model, performance metric).
    """
    rs = manifest.random_state if random_state is None else random_state
    df, y, protected_masks = _load_dataset(manifest)

    protected_cols = [pa.column for pa in manifest.protected_attributes]
    all_cols = list(dict.fromkeys(manifest.core_features + manifest.proxy_features + protected_cols))
    X_all = encode_features(df, all_cols)

    idx_train, idx_test = train_test_split(
        np.arange(len(df)), test_size=manifest.test_size, random_state=rs,
        stratify=y if y.nunique() > 1 else None,
    )

    fairness_rows = []
    performance_rows = []
    for strategy in STRATEGIES:
        for model_name in MODEL_FAMILIES:
            y_test, y_pred, y_proba = _run_strategy(
                strategy, model_name, manifest, X_all, y, protected_masks, idx_train, idx_test)

            perf = compute_performance_metrics(y_test, y_pred, y_proba, n_resamples, random_state=rs)
            for metric_name in PERFORMANCE_METRICS:
                p = perf[metric_name]
                performance_rows.append({
                    "audit": manifest.name, "strategy": strategy, "model": model_name,
                    "metric": metric_name, **p,
                })

            for pa in manifest.protected_attributes:
                disadv_test = protected_masks[pa.name].iloc[idx_test].to_numpy()
                metrics = compute_metrics(
                    y_test, y_pred, disadv_test, n_resamples, n_permutations, random_state=rs)
                for metric_name in METRICS:
                    m = metrics[metric_name]
                    fairness_rows.append({
                        "audit": manifest.name, "strategy": strategy, "model": model_name,
                        "protected_attribute": pa.name, "metric": metric_name, **m,
                    })

            if len(manifest.protected_attributes) >= 2:
                for pa_a, pa_b in itertools.combinations(manifest.protected_attributes, 2):
                    mask_a = protected_masks[pa_a.name].iloc[idx_test].to_numpy()
                    mask_b = protected_masks[pa_b.name].iloc[idx_test].to_numpy()
                    inter = intersectional_report(
                        y_pred, mask_a, mask_b, n_resamples, n_permutations, random_state=rs)
                    isr = inter["intersectional"]
                    # An empty "both" or "neither" cell makes the gap
                    # undefined (NaN) - intersectional_report still runs
                    # significance_report on it unconditionally, which can
                    # report p_value=0.0/significant=True on a meaningless
                    # comparison. Don't trust either field in that case.
                    cell_empty = (inter["cell_sizes"]["both"] == 0
                                  or inter["cell_sizes"]["neither"] == 0)
                    fairness_rows.append({
                        "audit": manifest.name, "strategy": strategy, "model": model_name,
                        "protected_attribute": f"{pa_a.name}_x_{pa_b.name}",
                        "metric": "intersectional_demographic_parity_diff",
                        "value": isr["gap"], "ci_low": isr["ci_low"], "ci_high": isr["ci_high"],
                        "p_value": None if cell_empty else isr["p_value"],
                        "significant": False if cell_empty else isr["significant"],
                        "n_disadvantaged": isr["n_a"], "n_advantaged": isr["n_b"],
                        "small_sample_warning": isr["small_sample_warning"],
                        "note": ("empty_intersectional_cell" if cell_empty
                                  else "superadditive" if inter["superadditive"] else None),
                    })
    return fairness_rows, performance_rows


def run_benchmark(root=".", audits=None, n_resamples=2000, n_permutations=2000):
    """Discover every audit.yaml under root (or use explicit manifest paths)
    and run them all. Returns (fairness_df, performance_df) across every audit."""
    np.random.seed(GLOBAL_SEED)  # defense-in-depth; see module docstring
    paths = [Path(a) for a in audits] if audits else discover_manifests(root)
    all_fairness = []
    all_performance = []
    for path in paths:
        manifest = load_manifest(path)
        fairness_rows, performance_rows = run_audit(manifest, n_resamples, n_permutations)
        all_fairness.extend(fairness_rows)
        all_performance.extend(performance_rows)
    return pd.DataFrame(all_fairness), pd.DataFrame(all_performance)


def summarize(fairness_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (audit, strategy, protected_attribute, metric): the point
    estimate averaged across the three model families, plus how many of
    them found the gap statistically significant."""
    if fairness_df.empty:
        return fairness_df
    return (
        fairness_df.groupby(["audit", "strategy", "protected_attribute", "metric"], as_index=False)
        .agg(mean_value=("value", "mean"),
             n_models_significant=("significant", "sum"),
             n_models=("model", "count"))
    )


def write_report(fairness_df: pd.DataFrame, performance_df: pd.DataFrame, out_dir,
                 make_plots: bool = True, plot_metric: str = "demographic_parity_diff"):
    """Write results_fairness.csv, results_performance.csv, and a summary.csv
    to out_dir, plus (if make_plots) render figures/*.png via faircode.figures."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fairness_df.to_csv(out_dir / "results_fairness.csv", index=False)
    performance_df.to_csv(out_dir / "results_performance.csv", index=False)
    summarize(fairness_df).to_csv(out_dir / "summary.csv", index=False)
    if make_plots and not fairness_df.empty:
        from .figures import generate_figures
        generate_figures(out_dir, metric=plot_metric)
    return out_dir
