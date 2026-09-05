"""End-to-end test of the benchmark harness against ONE small audit.

This is the test that catches a contributed audit.yaml (or a change to
manifest.py/strategies.py/models.py/metrics.py) breaking the pipeline before
it reaches a PR - it runs the real thing, not a mock of it. German Credit
Lending is used because it's the smallest dataset (1,000 rows): the full
five-strategy x three-model grid, including fairlearn's ExponentiatedGradient
(which refits its base estimator multiple times), finishes in seconds here.
The full seven-domain sweep is deliberately NOT run in this suite - it's slow
(fairlearn's in-processing strategy alone takes minutes per audit on the
larger datasets) - see "Reproducibility & Paper Freeze" in README.md: run it
locally and commit results/ output instead of running it in CI.

Run from the repo root:  pytest tests/ -q
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("fairlearn", reason="the benchmark harness needs the optional benchmark extra")
yaml = pytest.importorskip("yaml", reason="the benchmark harness needs the optional benchmark extra")

from faircode.benchmark import GLOBAL_SEED, run_audit, run_benchmark, write_report
from faircode.manifest import load_manifest
from faircode.metrics import METRICS, PERFORMANCE_METRICS
from faircode.strategies import STRATEGIES

REPO_ROOT = Path(__file__).resolve().parent.parent
SMALL_AUDIT = REPO_ROOT / "German Credit Lending" / "audit.yaml"

# Small enough to keep this test fast; not meant to be publication-quality.
N_RESAMPLES = 50
N_PERMUTATIONS = 50


@pytest.fixture(scope="module")
def result():
    manifest = load_manifest(SMALL_AUDIT)
    return run_audit(manifest, n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)


def test_runs_without_raising(result):
    fairness_rows, performance_rows = result
    assert fairness_rows
    assert performance_rows


def test_fairness_table_covers_every_strategy_and_model(result):
    fairness_rows, _ = result
    df = pd.DataFrame(fairness_rows)
    assert set(df["strategy"]) == set(STRATEGIES)
    assert set(df["model"]) == {"logistic_regression", "random_forest", "gradient_boosting"}
    assert set(df["metric"]) == set(METRICS)
    # German Credit Lending declares one protected attribute (age) and no
    # pairs, so there's no intersectional row and every row is tagged "age".
    assert set(df["protected_attribute"]) == {"age"}


def test_performance_table_covers_every_strategy_and_model(result):
    _, performance_rows = result
    df = pd.DataFrame(performance_rows)
    assert set(df["strategy"]) == set(STRATEGIES)
    assert set(df["model"]) == {"logistic_regression", "random_forest", "gradient_boosting"}
    assert set(df["metric"]) == set(PERFORMANCE_METRICS)


def test_expected_row_counts(result):
    fairness_rows, performance_rows = result
    n_strategies, n_models = 5, 3
    n_protected_attrs = 1   # German Credit Lending has one protected attribute, no pairs
    assert len(fairness_rows) == n_strategies * n_models * n_protected_attrs * len(METRICS)
    assert len(performance_rows) == n_strategies * n_models * len(PERFORMANCE_METRICS)


def test_every_fairness_row_has_required_keys(result):
    fairness_rows, _ = result
    required = {"audit", "strategy", "model", "protected_attribute", "metric",
               "value", "ci_low", "ci_high", "p_value", "significant",
               "n_disadvantaged", "n_advantaged", "small_sample_warning", "note"}
    for row in fairness_rows:
        assert required <= set(row)


def test_post_processing_has_no_auc_by_design(result):
    # ThresholdOptimizer (S4) has no probability output - see faircode.strategies.
    _, performance_rows = result
    df = pd.DataFrame(performance_rows)
    post_auc = df[(df["strategy"] == "post_processing") & (df["metric"] == "auc")]
    assert post_auc["value"].isna().all()


def test_baseline_demographic_parity_gap_is_a_plausible_fraction(result):
    fairness_rows, _ = result
    df = pd.DataFrame(fairness_rows)
    baseline_dp = df[(df["strategy"] == "baseline") & (df["metric"] == "demographic_parity_diff")]
    assert len(baseline_dp) == 3   # one per model
    assert baseline_dp["value"].between(-1.0, 1.0).all()


# ── write_report() / --no-plots (#210) ──────────────────────────────────────
# write_report() itself is frozen (CLAUDE.md) - these only call it, they never
# modify faircode/benchmark.py.

@pytest.fixture(scope="module")
def result_dfs(result):
    fairness_rows, performance_rows = result
    return pd.DataFrame(fairness_rows), pd.DataFrame(performance_rows)


def test_write_report_always_writes_the_three_csvs(tmp_path, result_dfs):
    fairness_df, performance_df = result_dfs

    out_dir = write_report(fairness_df, performance_df, tmp_path / "no_plots", make_plots=False)

    assert (out_dir / "results_fairness.csv").is_file()
    assert (out_dir / "results_performance.csv").is_file()
    assert (out_dir / "summary.csv").is_file()


def test_write_report_no_plots_skips_figures_directory(tmp_path, result_dfs):
    fairness_df, performance_df = result_dfs

    out_dir = write_report(fairness_df, performance_df, tmp_path / "no_plots", make_plots=False)

    assert not (out_dir / "figures").exists()


def test_write_report_default_writes_figures(tmp_path, result_dfs):
    pytest.importorskip("matplotlib", reason="figure generation needs matplotlib")
    fairness_df, performance_df = result_dfs

    out_dir = write_report(fairness_df, performance_df, tmp_path / "with_plots")

    figures = list((out_dir / "figures").glob("*.png"))
    assert len(figures) == 1
    assert figures[0].name == "german_credit_lending_strategies.png"


def test_write_report_skips_figures_for_empty_fairness_df(tmp_path):
    out_dir = write_report(pd.DataFrame(), pd.DataFrame(), tmp_path / "empty", make_plots=True)

    assert (out_dir / "results_fairness.csv").is_file()
    assert not (out_dir / "figures").exists()


# ── Intersectional reporting (#271) ─────────────────────────────────────────
# Insurance Denial is used here (not German Credit Lending, which has only
# one protected attribute and no intersectional row) because it's the
# smallest two-protected-attribute audit (1,341 rows, age x gender).

TWO_ATTR_AUDIT = REPO_ROOT / "Insurance Denial" / "audit.yaml"


@pytest.fixture(scope="module")
def two_attr_result():
    manifest = load_manifest(TWO_ATTR_AUDIT)
    return run_audit(manifest, n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)


def test_intersectional_row_present_for_a_two_attribute_audit(two_attr_result):
    fairness_rows, _ = two_attr_result
    df = pd.DataFrame(fairness_rows)
    intersectional = df[df["protected_attribute"] == "age_x_gender"]

    # One row per (strategy, model): 5 strategies x 3 models, all tagged with
    # the single intersectional metric - the pair combinations() produces for
    # exactly two declared protected attributes.
    assert len(intersectional) == 5 * 3
    assert (intersectional["metric"] == "intersectional_demographic_parity_diff").all()


def test_intersectional_row_has_required_keys(two_attr_result):
    fairness_rows, _ = two_attr_result
    df = pd.DataFrame(fairness_rows)
    row = df[df["protected_attribute"] == "age_x_gender"].iloc[0]

    for key in ("value", "ci_low", "ci_high", "p_value", "significant",
                "n_disadvantaged", "n_advantaged", "small_sample_warning", "note"):
        assert key in row.index

    # note is None, "superadditive", or "empty_intersectional_cell" - never a
    # different/unexpected value the intersectional_report() -> row mapping
    # could have mangled.
    assert row["note"] in (None, "superadditive", "empty_intersectional_cell")


# ── Empty intersectional cell doesn't fabricate significance (#413) ─────────
# intersectional_report() calls significance_report(y[both], y[neither], ...)
# unconditionally; when the "both" (doubly-disadvantaged) cell is empty, the
# permutation test over a zero-length array can report p_value=0.0 and
# significant=True on an undefined (gap=NaN) comparison - the opposite of a
# false negative, actively fabricating a finding. Constructed so every row
# has attr_a xor attr_b disadvantaged, never both - guaranteeing the "both"
# cell is empty regardless of how train_test_split splits the data.
EMPTY_CELL_AUDIT_NAME = "empty_intersectional_cell_toy"


@pytest.fixture(scope="module")
def empty_cell_result(tmp_path_factory):
    audit_dir = tmp_path_factory.mktemp(EMPTY_CELL_AUDIT_NAME)
    n = 40
    attr_a = ["disadv"] * 10 + ["ok"] * 10 + ["ok"] * 20
    attr_b = ["ok"] * 10 + ["disadv"] * 10 + ["ok"] * 20
    df = pd.DataFrame({
        "label": [0, 1] * (n // 2),
        "attr_a": attr_a,
        "attr_b": attr_b,
        "x": list(range(n)),
    })
    assert not ((df["attr_a"] == "disadv") & (df["attr_b"] == "disadv")).any()
    dataset_path = audit_dir / "toy.csv"
    df.to_csv(dataset_path, index=False)

    manifest_dict = {
        "name": EMPTY_CELL_AUDIT_NAME,
        "dataset": {"path": "toy.csv"},
        "target": {"column": "label", "method": "binary"},
        "protected_attributes": [
            {"name": "attr_a", "type": "categorical", "column": "attr_a",
             "disadvantaged_values": ["disadv"], "advantaged_values": ["ok"]},
            {"name": "attr_b", "type": "categorical", "column": "attr_b",
             "disadvantaged_values": ["disadv"], "advantaged_values": ["ok"]},
        ],
        "core_features": ["x"],
    }
    manifest_path = audit_dir / "audit.yaml"
    manifest_path.write_text(yaml.dump(manifest_dict))
    manifest = load_manifest(manifest_path)
    return run_audit(manifest, n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)


def test_empty_intersectional_cell_is_not_reported_significant(empty_cell_result):
    fairness_rows, _ = empty_cell_result
    df = pd.DataFrame(fairness_rows)
    intersectional = df[df["protected_attribute"] == "attr_a_x_attr_b"]
    assert len(intersectional) == 5 * 3

    assert intersectional["value"].isna().all()
    assert (~intersectional["significant"]).all()
    assert intersectional["p_value"].isna().all()
    assert (intersectional["note"] == "empty_intersectional_cell").all()


# ── run_benchmark() itself (#271) ────────────────────────────────────────────
# Existing tests above all call the lower-level run_audit() directly;
# run_benchmark() (discovery + seeding + multi-audit aggregation) had no
# direct test at all.

def test_run_benchmark_discovers_and_runs_a_manifest_directory(tmp_path):
    audit_dir = tmp_path / "Some Audit"
    audit_dir.mkdir()
    shutil.copy(SMALL_AUDIT, audit_dir / "audit.yaml")
    shutil.copy(SMALL_AUDIT.parent / "credit_customers.csv", audit_dir / "credit_customers.csv")

    fairness_df, performance_df = run_benchmark(
        root=str(tmp_path), n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)

    assert not fairness_df.empty
    assert not performance_df.empty
    assert set(fairness_df["audit"]) == {"german_credit_lending"}


def test_run_benchmark_uses_explicit_manifest_list_over_discovery(tmp_path):
    # An explicit `audits` list should be used as-is, without also scanning
    # `root` for other manifests - tmp_path here is deliberately empty.
    fairness_df, performance_df = run_benchmark(
        root=str(tmp_path), audits=[SMALL_AUDIT],
        n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)

    assert set(fairness_df["audit"]) == {"german_credit_lending"}
    assert not performance_df.empty


def test_run_benchmark_seeds_global_random_state(monkeypatch):
    seeds_used = []
    monkeypatch.setattr(np.random, "seed", lambda s: seeds_used.append(s))

    run_benchmark(audits=[SMALL_AUDIT], n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)

    assert seeds_used == [GLOBAL_SEED]


# ── run_benchmark() fails loudly, with the manifest path, on bad input (#403) ─
# A malformed manifest or degenerate dataset used to propagate a raw
# yaml.YAMLError/KeyError/sklearn ValueError all the way to the CLI with no
# indication of which manifest was responsible.
def test_run_benchmark_wraps_malformed_yaml_with_manifest_path(tmp_path):
    audit_dir = tmp_path / "Bad Audit"
    audit_dir.mkdir()
    (audit_dir / "audit.yaml").write_text("name: toy\n  bad_indent: [unclosed\n")

    with pytest.raises(ValueError, match=str(audit_dir / "audit.yaml")):
        run_benchmark(root=str(tmp_path), n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)


def test_run_benchmark_wraps_missing_required_key_with_manifest_path(tmp_path):
    audit_dir = tmp_path / "Bad Audit"
    audit_dir.mkdir()
    (audit_dir / "audit.yaml").write_text(yaml.dump({
        "name": "toy",
        "dataset": {"path": "toy.csv"},
        # no "target" key
        "protected_attributes": [
            {"name": "g", "type": "categorical", "column": "g",
             "disadvantaged_values": ["a"], "advantaged_values": ["b"]},
        ],
        "core_features": ["x"],
    }))

    with pytest.raises(ValueError, match=str(audit_dir / "audit.yaml")):
        run_benchmark(root=str(tmp_path), n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)


def test_run_benchmark_wraps_degenerate_zero_row_dataset_with_manifest_path(tmp_path):
    audit_dir = tmp_path / "Bad Audit"
    audit_dir.mkdir()
    pd.DataFrame({"label": [], "g": [], "x": []}).to_csv(audit_dir / "toy.csv", index=False)
    (audit_dir / "audit.yaml").write_text(yaml.dump({
        "name": "toy",
        "dataset": {"path": "toy.csv"},
        "target": {"column": "label", "method": "binary"},
        "protected_attributes": [
            {"name": "g", "type": "categorical", "column": "g",
             "disadvantaged_values": ["a"], "advantaged_values": ["b"]},
        ],
        "core_features": ["x"],
    }))

    with pytest.raises(ValueError, match=str(audit_dir / "audit.yaml")):
        run_benchmark(root=str(tmp_path), n_resamples=N_RESAMPLES, n_permutations=N_PERMUTATIONS)
