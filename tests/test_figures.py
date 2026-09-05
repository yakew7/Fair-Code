"""Tests for faircode.figures: paper figure rendering (Layer 2 of the
benchmark harness).

Run from the repo root:  pytest tests/ -q
"""

import pandas as pd
import pytest

pytest.importorskip("matplotlib", reason="faircode.figures needs the optional benchmark extra")

from faircode.figures import generate_figures, main, plot_strategy_comparison
from faircode.strategies import STRATEGIES


def _fairness_df(metric="demographic_parity_diff", audit="toy_audit"):
    rows = []
    for strategy in STRATEGIES:
        for model in ("logistic_regression", "random_forest", "gradient_boosting"):
            rows.append({
                "audit": audit, "strategy": strategy, "model": model,
                "metric": metric, "value": 0.1,
            })
    return pd.DataFrame(rows)


def test_plot_strategy_comparison_raises_on_empty_subset(tmp_path):
    df = _fairness_df()
    with pytest.raises(ValueError, match="no rows for audit="):
        plot_strategy_comparison(df, "not_a_real_audit", tmp_path / "out.png")


def test_plot_strategy_comparison_writes_a_png(tmp_path):
    df = _fairness_df()
    out_path = tmp_path / "toy_audit_strategies.png"
    plot_strategy_comparison(df, "toy_audit", out_path)
    assert out_path.is_file()
    assert out_path.stat().st_size > 0


def test_generate_figures_writes_one_png_per_audit(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _fairness_df().to_csv(results_dir / "results_fairness.csv", index=False)

    figures_dir = generate_figures(str(results_dir))

    assert figures_dir == results_dir / "figures"
    assert (figures_dir / "toy_audit_strategies.png").is_file()


def test_generate_figures_custom_figures_dir(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _fairness_df().to_csv(results_dir / "results_fairness.csv", index=False)

    custom_dir = tmp_path / "custom_figures"
    figures_dir = generate_figures(str(results_dir), figures_dir=str(custom_dir))

    assert figures_dir == custom_dir
    assert (custom_dir / "toy_audit_strategies.png").is_file()


def test_main_smoke_test_with_metric_flag_and_custom_results_dir(tmp_path, capsys):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _fairness_df(metric="equalized_odds_diff").to_csv(
        results_dir / "results_fairness.csv", index=False)

    main([str(results_dir), "--metric", "equalized_odds_diff"])

    captured = capsys.readouterr()
    assert f"Figures written to {results_dir / 'figures'}/" in captured.out
    assert (results_dir / "figures" / "toy_audit_strategies.png").is_file()
