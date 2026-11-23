"""scripts/diff_results.py compares results/ against the paper/results-frozen/ snapshot (#1065)."""

import importlib
import json

import pandas as pd
import pytest

dr = importlib.import_module("scripts.diff_results")

FAIR_COLS = ["audit", "strategy", "model", "protected_attribute", "metric", "value"]


def _fair(rows):
    return pd.DataFrame(rows, columns=FAIR_COLS)


def _write(directory, fairness, performance=None):
    directory.mkdir(parents=True, exist_ok=True)
    fairness.to_csv(directory / "results_fairness.csv", index=False)
    (performance if performance is not None else pd.DataFrame(
        [["a", "baseline", "lr", "accuracy", 0.7]], columns=["audit", "strategy", "model", "metric", "value"])
     ).to_csv(directory / "results_performance.csv", index=False)


def test_rows_are_classified_moved_unchanged_and_one_sided():
    ref = _fair([["a", "baseline", "lr", "sex", "dp", 0.10], ["a", "baseline", "lr", "sex", "eo", 0.20],
                 ["a", "baseline", "lr", "sex", "gone", 0.30]])
    cur = _fair([["a", "baseline", "lr", "sex", "dp", 0.15], ["a", "baseline", "lr", "sex", "eo", 0.205],
                 ["a", "baseline", "lr", "sex", "new", 0.40]])
    rows = {r["metric"]: r for r in dr.diff_table(cur, ref, dr.KINDS["fairness"][1], threshold=0.01)}
    assert rows["dp"]["status"] == "moved" and rows["dp"]["delta"] == pytest.approx(0.05)
    assert rows["eo"]["status"] == "unchanged"
    assert rows["new"]["status"] == "only_current" and rows["new"]["current"] == 0.40
    assert rows["gone"]["status"] == "only_reference" and rows["gone"]["reference"] == 0.30


def test_a_value_missing_on_one_side_only_counts_as_moved():
    ref = _fair([["a", "b", "lr", "sex", "dp", None]])
    cur = _fair([["a", "b", "lr", "sex", "dp", 0.1]])
    (row,) = dr.diff_table(cur, ref, dr.KINDS["fairness"][1])
    assert row["status"] == "moved" and row["delta"] is None
    (same,) = dr.diff_table(ref, ref, dr.KINDS["fairness"][1])
    assert same["status"] == "unchanged"


def test_a_delta_exactly_at_the_threshold_is_not_flagged():
    ref = _fair([["a", "b", "lr", "sex", "dp", 0.10]])
    cur = _fair([["a", "b", "lr", "sex", "dp", 0.11]])
    (row,) = dr.diff_table(cur, ref, dr.KINDS["fairness"][1], threshold=0.01)
    assert row["status"] == "unchanged"


def test_main_prints_flagged_rows_and_fails_on_change(tmp_path, capsys):
    _write(tmp_path / "ref", _fair([["a", "baseline", "lr", "sex", "dp", 0.10]]))
    _write(tmp_path / "cur", _fair([["a", "baseline", "lr", "sex", "dp", 0.30]]))
    args = ["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref")]
    assert dr.main(args) == 0
    out = capsys.readouterr().out
    assert "fairness: 1 rows compared, 1 flagged" in out
    assert "a / baseline / lr / sex / dp: 0.1000 -> 0.3000 (+0.2000)" in out
    assert dr.main(args + ["--fail-on-change"]) == 1


def test_main_json_and_all_and_clean_exit(tmp_path, capsys):
    same = _fair([["a", "baseline", "lr", "sex", "dp", 0.10]])
    _write(tmp_path / "ref", same)
    _write(tmp_path / "cur", same)
    args = ["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref")]
    assert dr.main(args + ["--fail-on-change", "--kind", "fairness"]) == 0
    assert "0 flagged" in capsys.readouterr().out
    assert dr.main(args + ["--all", "--kind", "fairness"]) == 0
    assert "a / baseline / lr / sex / dp: 0.1000 -> 0.1000" in capsys.readouterr().out
    assert dr.main(args + ["--json", "--kind", "fairness"]) == 0
    assert json.loads(capsys.readouterr().out)["fairness"][0]["status"] == "unchanged"


def test_missing_directory_is_a_clean_error(tmp_path, capsys):
    assert dr.main(["--current", str(tmp_path / "nope")]) == 2
    assert "not found" in capsys.readouterr().err


def test_the_real_snapshot_and_current_results_compare():
    diff = dr.diff_dirs(dr.CURRENT_DIR, dr.REFERENCE_DIR)
    assert set(diff) == {"fairness", "performance"}
    assert diff["fairness"] and diff["performance"]


def _two_audits(tmp_path):
    ref = _fair([["a", "baseline", "lr", "sex", "dp", 0.10], ["b", "baseline", "lr", "sex", "dp", 0.10],
                 ["b", "baseline", "lr", "sex", "eo", 0.20]])
    cur = _fair([["a", "baseline", "lr", "sex", "dp", 0.10], ["b", "baseline", "lr", "sex", "dp", 0.30],
                 ["b", "baseline", "lr", "sex", "eo", 0.15]])
    _write(tmp_path / "ref", ref)
    _write(tmp_path / "cur", cur)
    return ["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref"), "--kind", "fairness"]


def test_audit_restricts_the_join_and_is_repeatable(tmp_path, capsys):
    args = _two_audits(tmp_path)
    assert dr.main([*args, "--audit", "a", "--json", "--all"]) == 0
    rows = json.loads(capsys.readouterr().out)["fairness"]
    assert {r["audit"] for r in rows} == {"a"}
    assert dr.main([*args, "--audit", "a", "--audit", "b", "--json", "--all"]) == 0
    assert len(json.loads(capsys.readouterr().out)["fairness"]) == 3


def test_unknown_audit_is_an_error(tmp_path, capsys):
    assert dr.main([*_two_audits(tmp_path), "--audit", "nope"]) == 2
    assert "unknown audit(s): nope" in capsys.readouterr().err


def test_summary_counts_rows_and_largest_delta_per_audit(tmp_path, capsys):
    args = _two_audits(tmp_path)
    assert dr.main([*args, "--summary", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)["fairness"]
    assert [s["audit"] for s in summary] == ["a", "b"]
    assert summary[0] == {"audit": "a", "compared": 1, "flagged": 0, "max_abs_delta": 0.0, "different_sample": 0, "withheld": 0}
    assert (summary[1]["compared"], summary[1]["flagged"]) == (2, 2)
    assert summary[1]["max_abs_delta"] == pytest.approx(0.2)

    assert dr.main([*args, "--summary", "--audit", "b"]) == 0
    out = capsys.readouterr().out
    assert "b: 2 compared, 2 flagged, 0 withheld, 0 on different test sets, largest |delta| 0.2000" in out
    assert "a:" not in out


def test_summary_largest_delta_is_none_without_numeric_deltas():
    diff = {"fairness": [{"audit": "a", "status": "only_current", "delta": None}]}
    assert dr.summarize(diff) == {"fairness": [{"audit": "a", "compared": 1, "flagged": 1, "max_abs_delta": None, "different_sample": 0, "withheld": 0}]}


SIZE_FAIR_COLS = FAIR_COLS + ["n_disadvantaged", "n_advantaged"]


def test_rows_measured_on_different_test_sets_are_marked():
    # #1095: same value change, but the second row was scored on different people.
    ref = pd.DataFrame([["a", "b", "lr", "sex", "dp", 0.10, 100, 200], ["a", "b", "lr", "sex", "eo", 0.10, 100, 200]],
                       columns=SIZE_FAIR_COLS)
    cur = pd.DataFrame([["a", "b", "lr", "sex", "dp", 0.20, 100, 200], ["a", "b", "lr", "sex", "eo", 0.20, 90, 210]],
                       columns=SIZE_FAIR_COLS)
    rows = {r["metric"]: r for r in dr.diff_table(cur, ref, dr.KINDS["fairness"][1], size_columns=dr.SIZE_COLUMNS["fairness"])}
    assert rows["dp"]["sample"] == "same" and "sample_sizes" not in rows["dp"]
    assert rows["eo"]["sample"] == "different"
    assert rows["eo"]["sample_sizes"] == {"current": [90, 210], "reference": [100, 200]}


def test_sample_is_unknown_without_size_columns_or_for_one_sided_rows():
    ref = _fair([["a", "b", "lr", "sex", "dp", 0.1], ["a", "b", "lr", "sex", "gone", 0.3]])
    cur = _fair([["a", "b", "lr", "sex", "dp", 0.2]])
    rows = {r["metric"]: r for r in dr.diff_table(cur, ref, dr.KINDS["fairness"][1], size_columns=dr.SIZE_COLUMNS["fairness"])}
    assert rows["dp"]["sample"] == "unknown" and rows["gone"]["sample"] == "unknown"


def test_different_test_sets_show_in_the_text_json_and_summary(tmp_path):
    perf_cols = ["audit", "strategy", "model", "metric", "value", "n"]
    for name, n in (("ref", 1000), ("cur", 950)):
        _write(tmp_path / name, _fair([["a", "b", "lr", "sex", "dp", 0.1]]),
               pd.DataFrame([["a", "b", "lr", "accuracy", 0.7, n]], columns=perf_cols))
    diff = dr.diff_dirs(tmp_path / "cur", tmp_path / "ref")
    assert diff["performance"][0]["sample"] == "different"
    assert diff["performance"][0]["sample_sizes"] == {"current": [950], "reference": [1000]}
    text = dr.render(diff, show_all=True)
    assert "1 measured on different test sets" in text and "[different test set: reference [1000], current [950]]" in text
    assert dr.summarize(diff)["performance"][0]["different_sample"] == 1
    assert "1 on different test sets" in dr.render_summary(dr.summarize(diff))
    assert json.loads(json.dumps(diff))["performance"][0]["sample"] == "different"


# ── Rows the benchmark withheld on purpose (#1132) ───────────────────────────────────────────

def _with_notes(rows):
    return pd.DataFrame(rows, columns=FAIR_COLS + ["note"])


def test_a_value_withheld_with_a_note_is_withheld_not_moved():
    ref = _with_notes([["a", "b", "lr", "race", "disparate_impact_ratio", 627.18, None]])
    cur = _with_notes([["a", "b", "lr", "race", "disparate_impact_ratio", None, "advantaged_selection_too_rare"]])
    (row,) = dr.diff_table(cur, ref, dr.KINDS["fairness"][1])
    assert row["status"] == "withheld" and row["delta"] is None
    assert row["withheld"] == {"current": "advantaged_selection_too_rare", "reference": None}
    assert dr._flagged(row)


def test_withheld_on_the_reference_side_and_on_both_sides():
    keys = dr.KINDS["fairness"][1]
    note = "advantaged_selection_too_rare"
    ref = _with_notes([["a", "b", "lr", "race", "disparate_impact_ratio", None, note]])
    cur = _with_notes([["a", "b", "lr", "race", "disparate_impact_ratio", 1.2, None]])
    (row,) = dr.diff_table(cur, ref, keys)
    assert row["status"] == "withheld" and row["withheld"] == {"current": None, "reference": note}
    both = _with_notes([["a", "b", "lr", "race", "disparate_impact_ratio", None, note]])
    (same,) = dr.diff_table(both, both, keys)
    assert same["status"] == "unchanged"


def test_an_empty_value_without_a_note_is_still_moved():
    ref = _with_notes([["a", "b", "lr", "race", "m", 0.5, None]])
    cur = _with_notes([["a", "b", "lr", "race", "m", None, None]])
    (row,) = dr.diff_table(cur, ref, dr.KINDS["fairness"][1])
    assert row["status"] == "moved"


def test_withheld_rows_have_their_own_block_and_summary_count(tmp_path, capsys):
    note = "advantaged_selection_too_rare"
    _write(tmp_path / "ref", _fair([["a", "baseline", "lr", "sex", "disparate_impact_ratio", 80.0]]))
    cur = _fair([["a", "baseline", "lr", "sex", "disparate_impact_ratio", None]])
    cur["note"] = note
    _write(tmp_path / "cur", cur)
    args = ["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref"), "--kind", "fairness"]
    assert dr.main(args) == 0
    out = capsys.readouterr().out
    assert "withheld (1 rows where the benchmark chose not to report a value" in out
    assert f"reference 80.0000, current withheld ({note})" in out
    assert dr.main(args + ["--summary"]) == 0
    assert "1 withheld" in capsys.readouterr().out
    assert dr.main(args + ["--fail-on-change"]) == 1


def test_limit_lists_at_most_n_rows_per_kind_and_counts_the_rest(tmp_path):
    """#1131: a lockfile bump can move hundreds of rows; --limit keeps the PR comment under GitHub's size cap."""
    ref = _fair([["a", "baseline", "lr", "sex", f"m{i}", 0.1] for i in range(5)])
    cur = _fair([["a", "baseline", "lr", "sex", f"m{i}", 0.5] for i in range(5)])
    diff = {"fairness": dr.diff_table(cur, ref, dr.KINDS["fairness"][1], threshold=0.01)}
    text = dr.render(diff, limit=2)
    assert text.count("0.1000 -> 0.5000") == 2
    assert "3 more rows not listed (--limit 2)" in text
    assert "more rows not listed" not in dr.render(diff, limit=5)
    assert dr.render(diff).count("0.1000 -> 0.5000") == 5


def test_limit_must_be_positive(tmp_path, capsys):
    _write(tmp_path / "cur", _fair([["a", "b", "lr", "sex", "dp", 0.1]]))
    _write(tmp_path / "ref", _fair([["a", "b", "lr", "sex", "dp", 0.1]]))
    with pytest.raises(SystemExit):
        dr.main(["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref"), "--limit", "0"])
    assert "--limit must be at least 1" in capsys.readouterr().err
def test_unknown_audit_suggests_valid_name(capsys):
    result = dr.main(["--audit", "German Credit Lending"])

    output = capsys.readouterr().err

    assert result == 2
    assert "unknown audit(s)" in output
    assert "german_credit_lending" in output
    assert "Did you mean" in output

def _provenance_dir(path, timings):
    path.mkdir(parents=True, exist_ok=True)
    run = {"description": "run", "commit": "abc1234", "dirty": False, "python": "3.13", "libraries": {}, "audits": ["a"]}
    if timings is not None:
        run["timings"] = timings
    (path / "PROVENANCE.json").write_text(json.dumps({"schema": 1, "files": {}, "runs": [run]}), encoding="utf-8")
    return path


def _timing(strategy, seconds, stopped=None, model="lr"):
    item = {"audit": "a", "strategy": strategy, "model": model, "seconds": seconds}
    if stopped is not None:
        item["convergence_warnings"] = stopped
    return item


def test_the_provenance_report_says_how_the_convergence_changed_between_two_sides(tmp_path):
    # #1341
    ref = _provenance_dir(tmp_path / "ref", [_timing("baseline", 1.0, 3), _timing("in_processing", 2.0, 0)])
    cur = _provenance_dir(tmp_path / "cur", [_timing("baseline", 1.0, 0), _timing("in_processing", 2.0, 5)])
    report = dr.provenance_report(cur, ref)
    assert ("convergence: combinations that stopped at max_iter 1 -> 1; newly stopping: a/in_processing/lr; "
            "no longer stopping: a/baseline/lr") in report


def test_the_provenance_report_says_when_convergence_was_not_recorded(tmp_path):
    with_counts = _provenance_dir(tmp_path / "new", [_timing("baseline", 1.0, 0)])
    without = _provenance_dir(tmp_path / "old", [_timing("baseline", 1.0)])
    no_timings = _provenance_dir(tmp_path / "none", None)
    assert "convergence: not recorded on the reference side" in dr.provenance_report(with_counts, without)
    assert "convergence: not recorded on the current side" in dr.provenance_report(without, with_counts)
    assert "convergence: not recorded on both sides" in dr.provenance_report(no_timings, without)
    assert "combinations that stopped at max_iter 0 -> 0" in dr.provenance_report(with_counts, with_counts)


def test_the_provenance_report_shows_the_total_and_the_largest_timing_changes(tmp_path):
    # #1334: a slowdown after a dependency bump can be located without reading two JSON files
    ref = _provenance_dir(tmp_path / "ref", [_timing("baseline", 10.0), _timing("in_processing", 98.0), _timing("post_processing", 5.0)])
    cur = _provenance_dir(tmp_path / "cur", [_timing("baseline", 11.0), _timing("in_processing", 130.0), _timing("post_processing", 5.0)])
    line = next(l for l in dr.provenance_report(cur, ref).splitlines() if l.startswith("timings:"))
    assert line == ("timings: total 113.0 s -> 146.0 s (+33.0 s); largest changes: a/in_processing/lr 98.0 -> 130.0 s (+32.0, 1.3x), "
                    "a/baseline/lr 10.0 -> 11.0 s (+1.0, 1.1x), a/post_processing/lr 5.0 -> 5.0 s (+0.0, 1.0x)")


def test_only_the_five_largest_timing_changes_are_listed_and_unmatched_combinations_are_left_out(tmp_path):
    ref = _provenance_dir(tmp_path / "ref", [_timing(f"s{i}", 1.0) for i in range(8)] + [_timing("only_ref", 4.0)])
    cur = _provenance_dir(tmp_path / "cur", [_timing(f"s{i}", 1.0 + i) for i in range(8)] + [_timing("only_cur", 9.0)])
    line = next(l for l in dr.provenance_report(cur, ref).splitlines() if l.startswith("timings:"))
    assert line.count(" -> ") == 1 + 5                                              # the total and five combinations
    assert "s7" in line and "s6" in line and "s3" in line and "s2" not in line
    assert "only_ref" not in line.split("largest changes:")[1] and "only_cur" not in line.split("largest changes:")[1]


def test_the_provenance_report_says_when_timings_were_not_recorded(tmp_path):
    with_timings = _provenance_dir(tmp_path / "new", [_timing("baseline", 1.0)])
    without = _provenance_dir(tmp_path / "old", None)
    assert "timings: not recorded on the reference side" in dr.provenance_report(with_timings, without)
    assert "timings: not recorded on the current side" in dr.provenance_report(without, with_timings)
    assert "timings: not recorded on both sides" in dr.provenance_report(without, without)


def _compared_dirs(tmp_path, cur_timings, ref_timings):
    rows = _fair([["a", "baseline", "lr", "sex", "dp", 0.10]])
    for name, timings in (("cur", cur_timings), ("ref", ref_timings)):
        _write(tmp_path / name, rows)
        _provenance_dir(tmp_path / name, timings)
    return ["--current", str(tmp_path / "cur"), "--reference", str(tmp_path / "ref"), "--kind", "fairness"]


def test_json_carries_the_provenance_timings_and_convergence_the_text_report_shows(tmp_path, capsys):
    # #1345: a script reading --json could not tell a moved row from a slower or non-converging fit
    args = _compared_dirs(tmp_path, [_timing("baseline", 11.0, 4), _timing("in_processing", 130.0, 0)],
                          [_timing("baseline", 10.0, 0), _timing("in_processing", 98.0, 0)])
    assert dr.main([*args, "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fairness"][0]["status"] == "unchanged"                      # the existing keys keep their shape
    provenance = out["provenance"]
    assert provenance["current"]["commit"] == "abc1234" and "timings" not in provenance["current"]
    assert provenance["versions_differ"] == []
    timings = provenance["timings"]
    assert (timings["recorded"], timings["total_reference"], timings["total_current"]) == (True, 108.0, 141.0)
    assert timings["changes"][0] == {"combination": "a/in_processing/lr", "reference": 98.0, "current": 130.0, "delta": 32.0,
                              "ratio": pytest.approx(130 / 98), "slower": False}
    assert provenance["convergence"] == {"recorded": True, "reference": 0, "current": 1,
                                         "newly_stopping": ["a/baseline/lr"], "no_longer_stopping": []}


def test_json_provenance_says_what_was_not_recorded_and_is_null_without_provenance(tmp_path, capsys):
    args = _compared_dirs(tmp_path, [_timing("baseline", 1.0)], None)
    assert dr.main([*args, "--json"]) == 0
    provenance = json.loads(capsys.readouterr().out)["provenance"]
    assert provenance["timings"] == {"recorded": False, "missing": "the reference side"}
    assert provenance["convergence"] == {"recorded": False, "missing": "both sides"}      # neither side recorded counts
    (tmp_path / "ref" / "PROVENANCE.json").unlink()
    assert dr.main([*args, "--json"]) == 0
    provenance = json.loads(capsys.readouterr().out)["provenance"]
    assert provenance["reference"] is None
    assert provenance["versions_differ"] is None and provenance["timings"] is None and provenance["convergence"] is None


def test_summary_json_has_the_provenance_key_too_and_the_text_output_is_unchanged(tmp_path, capsys):
    args = _compared_dirs(tmp_path, [_timing("baseline", 2.0)], [_timing("baseline", 1.0)])
    assert dr.main([*args, "--summary", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fairness"][0]["audit"] == "a" and out["provenance"]["timings"]["total_current"] == 2.0
    assert dr.main([*args, "--summary"]) == 0
    assert "provenance" not in capsys.readouterr().out.split("\n\n", 1)[1]    # the text report keeps its own block above the summary


def _timing_line(tmp_path, ref_seconds, cur_seconds, **options):
    ref = _provenance_dir(tmp_path / "ref", [_timing(f"s{i}", v) for i, v in enumerate(ref_seconds)])
    cur = _provenance_dir(tmp_path / "cur", [_timing(f"s{i}", v) for i, v in enumerate(cur_seconds)])
    return next(l for l in dr.provenance_report(cur, ref, **options).splitlines() if l.startswith("timings:"))


def test_a_fit_that_took_much_longer_is_marked_slower_and_a_small_change_is_not(tmp_path):
    # #1353: a 3x slowdown and 0.4 s of noise printed the same way
    line = _timing_line(tmp_path, [10.0, 0.5, 20.0], [30.0, 0.9, 21.0])
    assert "a/s0/lr 10.0 -> 30.0 s (+20.0, 3.0x) SLOWER" in line
    assert "a/s1/lr 0.5 -> 0.9 s (+0.4, 1.8x)," in line + "," and "(+0.4, 1.8x) SLOWER" not in line     # 1.8x but under 1 s longer
    assert "a/s2/lr 20.0 -> 21.0 s (+1.0, 1.1x)" in line and "(+1.0, 1.1x) SLOWER" not in line


def test_the_timing_threshold_option_moves_the_marking_ratio(tmp_path):
    ref, cur = [10.0], [16.0]
    assert "SLOWER" in _timing_line(tmp_path, ref, cur)                              # 1.6x is over the default 1.5
    assert "SLOWER" not in _timing_line(tmp_path, ref, cur, ratio=2.0)
    assert "SLOWER" in _timing_line(tmp_path, ref, [21.0], ratio=2.0)


def test_a_speedup_and_a_zero_second_reference_are_never_marked(tmp_path):
    line = _timing_line(tmp_path, [30.0, 0.0], [10.0, 5.0])
    assert "SLOWER" not in line and "a/s1/lr 0.0 -> 5.0 s (+5.0)" in line            # no ratio against a reference that took no time


def test_json_timings_carry_the_ratio_and_the_slower_flag_and_the_cli_takes_the_threshold(tmp_path, capsys):
    args = _compared_dirs(tmp_path, [_timing("baseline", 30.0)], [_timing("baseline", 10.0)])
    assert dr.main([*args, "--json"]) == 0
    change = json.loads(capsys.readouterr().out)["provenance"]["timings"]["changes"][0]
    assert change["ratio"] == 3.0 and change["slower"] is True
    assert dr.main([*args, "--json", "--timing-threshold", "4"]) == 0
    assert json.loads(capsys.readouterr().out)["provenance"]["timings"]["changes"][0]["slower"] is False
    assert dr.main([*args, "--fail-on-change", "--timing-threshold", "1.2"]) == 0      # never changes the exit code


def test_the_timing_threshold_must_be_a_ratio_above_one(tmp_path, capsys):
    args = _compared_dirs(tmp_path, [_timing("baseline", 1.0)], [_timing("baseline", 1.0)])
    for bad in ("1", "0.5", "x"):
        with pytest.raises(SystemExit) as stopped:
            dr.main([*args, "--timing-threshold", bad])
        assert stopped.value.code == 2
    assert "greater than 1" in capsys.readouterr().err
