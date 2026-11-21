"""Per-combination timings and convergence warnings of a benchmark run (#1328, #1329).

`run_audit(..., diagnostics=[])` records, for each strategy/model combination, the seconds the fit took and how many
scikit-learn ConvergenceWarnings it raised; the CLI prints one summary line per audit and writes the seconds into the new run's
PROVENANCE.json entry. None of it may change a result.
"""
import json
import warnings

import pandas as pd
import pytest

pytest.importorskip("sklearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("fairlearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("yaml", reason="the benchmark harness needs the optional benchmark extra")

from sklearn.exceptions import ConvergenceWarning  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from benchmark_helpers import LR_ONLY, _write_toy_audit  # noqa: E402
from faircode import benchmark  # noqa: E402
from faircode.cli import main  # noqa: E402

STOPS_EARLY = {"logistic_regression": lambda random_state: LogisticRegression(max_iter=1, random_state=random_state)}


def _use(monkeypatch, families):
    monkeypatch.setattr(benchmark, "MODEL_FAMILIES", families)
    monkeypatch.setattr("faircode.models.MODEL_FAMILIES", families)


def test_the_timed_run_counts_convergence_warnings_and_reissues_every_other_warning(monkeypatch):
    def fake(*args, **kwargs):
        for _ in range(3):
            warnings.warn("stopped", ConvergenceWarning)
        warnings.warn("something else", UserWarning)
        return "result"

    monkeypatch.setattr(benchmark, "_run_strategy", fake)
    with warnings.catch_warnings(record=True) as outer:
        warnings.simplefilter("always")
        result, seconds, stopped = benchmark._timed_strategy_run("baseline", "m")
    assert result == "result" and stopped == 3 and seconds >= 0
    assert [str(w.message) for w in outer] == ["something else"]               # the ConvergenceWarnings are not printed


def test_diagnostics_hold_one_entry_per_combination_and_change_no_result(tmp_path, monkeypatch):
    _use(monkeypatch, STOPS_EARLY)
    manifest = _write_toy_audit(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)                     # the plain run prints them, which is what #1328 is about
        plain_f, plain_p = benchmark.run_audit(manifest, n_resamples=20, n_permutations=20)
    diagnostics = []
    with warnings.catch_warnings(record=True) as printed:
        warnings.simplefilter("always")
        diag_f, diag_p = benchmark.run_audit(manifest, n_resamples=20, n_permutations=20, diagnostics=diagnostics)

    assert pd.DataFrame(plain_f).equals(pd.DataFrame(diag_f)) and pd.DataFrame(plain_p).equals(pd.DataFrame(diag_p))
    assert [(d["strategy"], d["model"]) for d in diagnostics] == [(s, "logistic_regression") for s in benchmark.STRATEGIES]
    assert all(d["audit"] == "toy" and d["seconds"] >= 0 for d in diagnostics)
    assert all(d["convergence_warnings"] >= 1 for d in diagnostics)             # max_iter=1 never converges
    assert not any(issubclass(w.category, ConvergenceWarning) for w in printed)


def test_a_converging_model_reports_zero_warnings(tmp_path, monkeypatch):
    _use(monkeypatch, LR_ONLY)
    diagnostics = []
    benchmark.run_audit(_write_toy_audit(tmp_path), n_resamples=20, n_permutations=20, diagnostics=diagnostics)
    assert {d["convergence_warnings"] for d in diagnostics} == {0}
    assert benchmark.convergence_summary(diagnostics) == []


def test_convergence_summary_is_one_line_per_audit_naming_the_combinations():
    diagnostics = [
        {"audit": "a", "strategy": "baseline", "model": "lr", "seconds": 1.0, "convergence_warnings": 2},
        {"audit": "a", "strategy": "in_processing", "model": "lr", "seconds": 1.0, "convergence_warnings": 40},
        {"audit": "a", "strategy": "post_processing", "model": "lr", "seconds": 1.0, "convergence_warnings": 0},
        {"audit": "b", "strategy": "baseline", "model": "lr", "seconds": 1.0, "convergence_warnings": 0}]
    assert benchmark.convergence_summary(diagnostics) == [
        "a: 2 of 3 combinations had a fit stop at max_iter (42 fit(s) in all): baseline/lr, in_processing/lr; "
        "see https://github.com/yakew7/Fair-Code#convergence-warnings"]


def test_timings_are_added_to_the_provenance_record_only_when_given():
    assert "timings" not in benchmark.collect_provenance(["a"], 10, 10)
    timings = [{"audit": "a", "strategy": "baseline", "model": "lr", "seconds": 1.5, "convergence_warnings": 3}]
    record = benchmark.collect_provenance(["a"], 10, 10, timings=timings)
    assert record["timings"] == [{"audit": "a", "strategy": "baseline", "model": "lr", "seconds": 1.5, "convergence_warnings": 3}]
    older = [{"audit": "a", "strategy": "baseline", "model": "lr", "seconds": 1.5}]            # diagnostics without the count
    assert benchmark.collect_provenance(["a"], 10, 10, timings=older)["timings"][0]["convergence_warnings"] == 0


def test_a_result_set_with_timings_in_its_provenance_still_verifies_and_merges(tmp_path, monkeypatch):
    _use(monkeypatch, LR_ONLY)
    diagnostics = []
    fairness, performance = benchmark.run_audit(_write_toy_audit(tmp_path), n_resamples=20, n_permutations=20, diagnostics=diagnostics)
    fairness, performance = pd.DataFrame(fairness), pd.DataFrame(performance)
    provenance = benchmark.collect_provenance(["toy"], 20, 20, timings=diagnostics)
    out = tmp_path / "out"
    benchmark.write_report(fairness, performance, out, make_plots=False, provenance=provenance)
    record = json.loads((out / benchmark.PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert len(record["runs"][0]["timings"]) == len(benchmark.STRATEGIES) and "convergence_warnings" in record["runs"][0]["timings"][0]
    benchmark.write_report(fairness, performance, out, make_plots=False, provenance=provenance, merge=True)   # verifies the old record
    merged = json.loads((out / benchmark.PROVENANCE_FILE).read_text(encoding="utf-8"))["runs"]
    assert len(merged) == 2 and all("timings" in run for run in merged)                # a merge appends the new run's entry


def test_the_cli_prints_the_summary_and_records_the_timings(tmp_path, monkeypatch, capsys):
    _use(monkeypatch, STOPS_EARLY)
    audit = tmp_path / "audit"
    audit.mkdir()
    _write_toy_audit(audit)
    out = tmp_path / "results"

    assert main(["benchmark", str(audit / "audit.yaml"), "--n-resamples", "20", "--n-permutations", "20",
                 "--no-plots", "--out", str(out), "--quiet"]) == 0

    err = capsys.readouterr().err
    assert "warning: toy: 5 of 5 combinations had a fit stop at max_iter" in err
    assert "lbfgs failed to converge" not in err and "STOP: TOTAL NO. OF ITERATIONS" not in err
    runs = json.loads((out / benchmark.PROVENANCE_FILE).read_text(encoding="utf-8"))["runs"]
    assert [(t["strategy"], t["model"]) for t in runs[0]["timings"]] == [(s, "logistic_regression") for s in benchmark.STRATEGIES]
    assert all(t["seconds"] >= 0 for t in runs[0]["timings"])


def test_the_summary_points_at_a_readme_section_that_exists_not_at_a_test_path():
    # #1340: a pip install has no tests/ directory
    from pathlib import Path
    line = benchmark.convergence_summary([{"audit": "a", "strategy": "baseline", "model": "lr", "seconds": 1.0,
                                           "convergence_warnings": 1}])[0]
    assert "tests/" not in line and line.endswith(benchmark.CONVERGENCE_DOC)
    anchor = benchmark.CONVERGENCE_DOC.rsplit("#", 1)[1]
    readme = (Path(benchmark.__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    headings = [h.lstrip("#").strip().lower().replace(" ", "-") for h in readme.splitlines() if h.startswith("#")]
    assert anchor in headings
    assert "(#convergence-warnings)" in readme                                  # the benchmark section links to it too


def test_provenance_records_the_convergence_counts_of_a_model_that_warns(tmp_path, monkeypatch):
    # #1341: a script or CI step can read which combinations stopped at max_iter without parsing stderr
    _use(monkeypatch, STOPS_EARLY)
    diagnostics = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fairness, performance = benchmark.run_audit(_write_toy_audit(tmp_path), n_resamples=20, n_permutations=20, diagnostics=diagnostics)
    out = tmp_path / "out"
    benchmark.write_report(pd.DataFrame(fairness), pd.DataFrame(performance), out, make_plots=False,
                           provenance=benchmark.collect_provenance(["toy"], 20, 20, timings=diagnostics))
    timings = json.loads((out / benchmark.PROVENANCE_FILE).read_text(encoding="utf-8"))["runs"][0]["timings"]
    assert len(timings) == len(benchmark.STRATEGIES) and all(t["convergence_warnings"] >= 1 for t in timings)
