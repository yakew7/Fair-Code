"""Writing, verifying and merging benchmark result sets, on a tiny synthetic audit (#1318).

The fast suite reached 94% of faircode/benchmark.py: the row filter, the provenance collection fallbacks, the report with plots
and the many "refusing to overwrite" branches were only covered, if at all, by the slow tests. A 240-row toy audit with a
logistic regression only produces the result tables in a fraction of a second.
"""
import json

import pandas as pd
import pytest

pytest.importorskip("sklearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("fairlearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("yaml", reason="the benchmark harness needs the optional benchmark extra")

from benchmark_helpers import LR_ONLY, _toy_frame, _write_toy_audit  # noqa: E402

from faircode import benchmark  # noqa: E402
from faircode.manifest import RowFilter, load_manifest  # noqa: E402


@pytest.fixture(scope="module")
def tables(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(benchmark, "MODEL_FAMILIES", LR_ONLY)
    mp.setattr("faircode.models.MODEL_FAMILIES", LR_ONLY)
    try:
        directory = tmp_path_factory.mktemp("toy")
        manifest = _write_toy_audit(directory)
        fairness, performance = benchmark.run_audit(manifest, n_resamples=20, n_permutations=20)
    finally:
        mp.undo()
    return pd.DataFrame(fairness), pd.DataFrame(performance)


def _provenance(audits):
    return {"schema": 1, "description": "test run", "commit": None, "dirty": None, "python": "3", "libraries": {},
            "lockfile_sha256": None, "n_resamples": 20, "n_permutations": 20, "audits": sorted(audits)}


@pytest.fixture
def written(tmp_path, tables):
    fairness, performance = tables
    out = tmp_path / "out"
    benchmark.write_report(fairness, performance, out, make_plots=False, provenance=_provenance(["toy"]))
    return out, fairness, performance


def test_a_row_filter_of_the_manifest_is_applied_before_the_audit_runs(tmp_path):
    _write_toy_audit(tmp_path)
    manifest = load_manifest(tmp_path / "audit.yaml")
    manifest.row_filters = [RowFilter(column="attr_b", equals="ok")]
    df, y, masks = benchmark._load_dataset(manifest)
    expected = int((_toy_frame()["attr_b"] == "ok").sum())
    assert len(df) == expected and set(df["attr_b"]) == {"ok"}
    assert len(y) == len(df) and all(len(mask) == len(df) for mask in masks.values())


def test_provenance_collection_survives_a_missing_git_and_an_uninstalled_library(monkeypatch):
    import subprocess

    def no_git(*args, **kwargs):
        raise OSError("git is not installed")

    def not_installed(name):
        raise benchmark.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(subprocess, "run", no_git)
    monkeypatch.setattr(benchmark.metadata, "version", not_installed)
    record = benchmark.collect_provenance(["toy"], 20, 20)
    assert record["commit"] is None and record["dirty"] is None
    assert set(record["libraries"]) == set(benchmark.PROVENANCE_LIBRARIES) and all(v is None for v in record["libraries"].values())


def test_write_report_with_plots_renders_the_figures(tmp_path, tables):
    fairness, performance = tables
    out = benchmark.write_report(fairness, performance, tmp_path / "plots", make_plots=True)
    assert (out / "figures").is_dir() and any((out / "figures").glob("*.png"))


def test_a_result_set_with_different_audits_in_its_two_tables_is_refused(tmp_path, tables):
    fairness, performance = tables
    other = performance.copy()
    other["audit"] = "another"
    with pytest.raises(ValueError, match="different audit sets"):
        benchmark.write_report(fairness, other, tmp_path / "x", make_plots=False)


@pytest.mark.parametrize("mutate, message", [
    (lambda record: record.update(schema=2), "unsupported or incomplete provenance record"),
    (lambda record: record.pop("files"), "unsupported or incomplete provenance record"),
    (lambda record: record.update(runs="nope"), "missing run records"),
    (lambda record: record["files"].update({"results_fairness.csv": "0" * 64}), "does not match its recorded hash"),
    (lambda record: record.update(runs=[{"audits": "toy"}]), "malformed run audit list"),
    (lambda record: record.update(runs=[{"audits": ["other"]}]), "recorded audits do not match"),
])
def test_an_existing_result_set_whose_provenance_is_inconsistent_is_never_overwritten(written, mutate, message):
    out, fairness, performance = written
    path = out / benchmark.PROVENANCE_FILE
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record), encoding="utf-8")
    before = (out / "results_fairness.csv").read_bytes()
    with pytest.raises(ValueError, match=message):
        benchmark.write_report(fairness, performance, out, make_plots=False, provenance=_provenance(["toy"]))
    assert (out / "results_fairness.csv").read_bytes() == before


def test_provenance_that_is_not_a_json_object_is_refused(written):
    out, fairness, performance = written
    (out / benchmark.PROVENANCE_FILE).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance is not a JSON object"):
        benchmark.write_report(fairness, performance, out, make_plots=False, provenance=_provenance(["toy"]))


def test_a_report_without_provenance_will_not_leave_stale_provenance_beside_new_results(written):
    out, fairness, performance = written
    with pytest.raises(ValueError, match="has provenance but this report does not"):
        benchmark.write_report(fairness, performance, out, make_plots=False)


def test_merge_requires_the_same_column_layout_audits_matching_provenance_and_an_existing_set(written, tmp_path, tables):
    out, fairness, performance = written
    provenance = _provenance(["toy"])
    narrower = fairness.drop(columns=[fairness.columns[-1]])
    with pytest.raises(ValueError, match="existing column layout"):
        benchmark.write_report(narrower, performance, out, make_plots=False, provenance=provenance, merge=True)
    with pytest.raises(ValueError, match="provenance audits do not match"):
        benchmark.write_report(fairness, performance, out, make_plots=False, provenance=_provenance(["other"]), merge=True)
    with pytest.raises(ValueError, match="requires provenance"):
        benchmark.write_report(fairness, performance, out, make_plots=False, provenance=None, merge=True)
    with pytest.raises(ValueError, match="requires an existing, provenance-verified"):
        benchmark.write_report(fairness, performance, tmp_path / "empty", make_plots=False, provenance=provenance, merge=True)
    with pytest.raises(ValueError, match="at least one audit"):
        benchmark.write_report(fairness.iloc[0:0], performance.iloc[0:0], out, make_plots=False, provenance=provenance, merge=True)


def test_merge_replaces_only_the_requested_audit_and_keeps_the_others(written):
    out, fairness, performance = written
    other_f, other_p = fairness.copy(), performance.copy()
    other_f["audit"], other_p["audit"] = "second", "second"
    benchmark.write_report(other_f, other_p, out, make_plots=False, provenance=_provenance(["second"]), merge=True)
    merged = pd.read_csv(out / "results_fairness.csv")
    assert set(merged["audit"]) == {"toy", "second"} and len(merged) == 2 * len(fairness)
