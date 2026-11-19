from pathlib import Path
from types import SimpleNamespace

import pytest


pytest.importorskip("sklearn", reason="benchmark extra required")
pytest.importorskip("fairlearn", reason="benchmark extra required")
pytest.importorskip("yaml", reason="benchmark extra required")

import faircode.benchmark as benchmark
from faircode.cli import main


def test_run_audit_reports_each_completed_strategy_model(monkeypatch):
    strategies = ("first_strategy", "second_strategy")
    models = ("first_model", "second_model")
    manifest = SimpleNamespace(name="example_audit", protected_attributes=[])
    data = SimpleNamespace(
        random_state=7,
        X_all=None,
        y=None,
        masks={},
        idx_train=None,
        idx_test=None,
    )
    monkeypatch.setattr(benchmark, "STRATEGIES", strategies)
    monkeypatch.setattr(benchmark, "MODEL_FAMILIES", models)
    monkeypatch.setattr(benchmark, "PERFORMANCE_METRICS", ("accuracy",))
    monkeypatch.setattr(benchmark, "prepare_audit", lambda *args, **kwargs: data)
    monkeypatch.setattr(benchmark, "_run_strategy", lambda *args: (None, None, None))
    monkeypatch.setattr(
        benchmark,
        "compute_performance_metrics",
        lambda *args, **kwargs: {"accuracy": {"value": 1.0}},
    )
    completed = []

    fairness_rows, performance_rows = benchmark.run_audit(
        manifest, progress_callback=lambda *item: completed.append(item)
    )

    assert fairness_rows == []
    assert len(performance_rows) == len(strategies) * len(models)
    assert completed == [
        (manifest.name, strategy, model)
        for strategy in strategies
        for model in models
    ]


@pytest.mark.parametrize("quiet", [False, True])
def test_cli_benchmark_progress_uses_stderr_and_quiet_suppresses_it(
    quiet, monkeypatch, tmp_path, capsys
):
    manifest = SimpleNamespace(name="example_audit")
    monkeypatch.setattr(benchmark, "discover_manifests", lambda root: [Path("audit.yaml")])
    monkeypatch.setattr(benchmark, "load_manifest", lambda path: manifest)

    def run_audit(manifest, n_resamples, n_permutations, progress_callback=None, diagnostics=None):
        if progress_callback is not None:
            progress_callback(manifest.name, "baseline", "logistic_regression")
        rows = [{"audit": manifest.name}]
        return rows, rows

    monkeypatch.setattr(benchmark, "run_audit", run_audit)
    monkeypatch.setattr("faircode.benchmark.collect_provenance", lambda *args, **kwargs: {})
    monkeypatch.setattr("faircode.benchmark.write_report", lambda *args, **kwargs: None)
    args = ["benchmark", "--no-plots", "--out", str(tmp_path / "results")]
    if quiet:
        args.append("--quiet")

    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    progress_line = "completed example_audit / baseline / logistic_regression"
    if quiet:
        assert progress_line not in captured.err
    else:
        assert captured.err.startswith(progress_line + "\n")
    assert "Ran 1 audit(s), wrote 1 fairness rows and 1 performance rows" in captured.err
