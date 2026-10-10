import builtins
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

import faircode.cli as cli
from faircode.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
SMALL_AUDIT = REPO_ROOT / "German Credit Lending" / "audit.yaml"

requires_openpyxl = pytest.mark.skipif(
    importlib.util.find_spec("openpyxl") is None,
    reason="optional 'excel' extra not installed",
)
requires_scipy = pytest.mark.skipif(
    importlib.util.find_spec("scipy") is None,
    reason="optional 'proxy' extra not installed",
)


def test_profile_fail_under_returns_nonzero_and_explains_score(tmp_path, capsys):
    path = tmp_path / "skewed.csv"
    path.write_text("sex\n" + "M\n" * 80 + "F\n" * 20, encoding="utf-8")

    exit_code = main(["profile", str(path), "--fail-under", "90"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Representation score:" in captured.out
    assert "representation score 72/100 is below --fail-under 90" in captured.err


def test_profile_rejects_out_of_range_min_share(tmp_path, capsys):
    # A percentage/fraction typo (15 instead of 0.15, or 1.5) used to be
    # accepted silently and produce a self-contradictory report (#511).
    path = tmp_path / "a.csv"
    path.write_text("sex\n" + "M\n" * 50 + "F\n" * 50, encoding="utf-8")

    exit_code = main(["profile", str(path), "--min-share", "1.5"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "min_share must be between 0 and 1" in captured.err


def test_compare_rejects_out_of_range_min_share(tmp_path, capsys):
    # compare accepts the same tunables as profile, but used to skip the
    # ValueError -> clean-exit handling profile has, crashing with a raw
    # traceback instead (#663).
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\n" + "M\n" * 50 + "F\n" * 50, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\n" + "M\n" * 60 + "F\n" * 40, encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--min-share", "1.5"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "min_share must be between 0 and 1" in captured.err


def test_profile_fail_under_keeps_json_output_machine_readable(tmp_path, capsys):
    path = tmp_path / "balanced.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--json", "--fail-under", "90"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["overall_score"] == 100
    assert captured.err == ""


def test_profile_fail_under_equal_threshold_returns_zero(tmp_path, capsys):
    path = tmp_path / "balanced.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--fail-under", "100"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Representation score: 100/100" in captured.out
    assert captured.err == ""


def test_profile_fail_under_reports_unmeasured_dataset(tmp_path, capsys):
    path = tmp_path / "identifiers.csv"
    path.write_text("id\n" + "\n".join(str(i) for i in range(40)), encoding="utf-8")

    exit_code = main(["profile", str(path), "--json", "--fail-under", "90"])

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert exit_code == 2
    assert result["overall_score"] is None
    assert "cannot apply --fail-under: no demographic columns detected" in captured.err


def test_compare_fail_on_drift_returns_nonzero_and_explains(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\n" + "M\n" * 50 + "F\n" * 50, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\n" + "M\n" * 90 + "F\n" * 10, encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--fail-on-drift"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "representation drift detected" in captured.err
    assert "--fail-on-drift" in captured.err


def test_compare_without_fail_on_drift_still_returns_zero(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\n" + "M\n" * 50 + "F\n" * 50, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\n" + "M\n" * 90 + "F\n" * 10, encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b)])

    assert exit_code == 0


def test_compare_fail_on_drift_returns_zero_when_stable(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--fail-on-drift"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""


def test_compare_applies_map_override_to_both_datasets(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("gndr\n" + "M\n" * 8 + "F\n" * 2, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("gndr\n" + "M\n" * 5 + "F\n" * 5, encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--json", "--map", "gndr=sex"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert [d["name"] for d in result["dimensions"]] == ["gndr"]
    assert [d["kind"] for d in result["dimensions"]] == ["sex"]


def test_compare_without_map_leaves_column_generically_categorical(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("gndr\n" + "M\n" * 8 + "F\n" * 2, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("gndr\n" + "M\n" * 5 + "F\n" * 5, encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert [d["kind"] for d in result["dimensions"]] == ["categorical"]


def test_profile_map_unknown_column_exits_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--map", "nonexistent_col=race"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "--map column(s) not found in the dataset: nonexistent_col" in captured.err


def test_compare_map_unknown_column_exits_2_with_clean_error(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["compare", str(path_a), str(path_b), "--map", "nonexistent_col=race"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "--map column(s) not found in the dataset: nonexistent_col" in captured.err


def test_compare_map_column_present_in_only_one_dataset_is_accepted(tmp_path):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex,extra\nM,1\nF,2\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--map", "extra=ignore", "--json"])

    assert exit_code == 0


def test_map_without_equals_sign_exits_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--map", "sex_no_equals"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "invalid --map 'sex_no_equals', expected COL=KIND" in captured.err


def test_map_with_invalid_kind_exits_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--map", "sex=not_a_real_kind"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "invalid --map kind 'not_a_real_kind' for column 'sex'" in captured.err


def test_profile_missing_file_exits_2_with_clean_error(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(missing)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert f"error: file not found: {missing}" in captured.err


def test_profile_csv_export_does_not_clobber_the_csv_dataset_argument(tmp_path, capsys):
    """--csv (the export flag) and the positional `csv` dataset path argument
    must not share an argparse dest - regression test for a real bug caught
    while implementing #739: --csv silently overwrote args.csv, so the
    dataset path used for reading (and for the provenance dataset_hash) was
    replaced by the export path instead."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    out_path = tmp_path / "export.csv"

    exit_code = main(["profile", str(path), "--csv", str(out_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"CSV export written to {out_path}" in captured.err
    assert out_path.exists()
    result = json.loads(captured.out)
    assert result["n_rows"] == 4  # read from `path`, not misdirected to out_path


def test_profile_csv_export_writes_a_flat_group_table(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    out_path = tmp_path / "export.csv"

    exit_code = main(["profile", str(path), "--csv", str(out_path)])

    assert exit_code == 0
    rows = out_path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "dimension,kind,label,count,share,ci_low,ci_high,under_represented,small_group"
    assert any(r.startswith("sex,sex,") for r in rows[1:])


def test_compare_csv_export_writes_group_and_summary_sections(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nM\nM\nF\n", encoding="utf-8")
    out_path = tmp_path / "drift.csv"

    exit_code = main(["compare", str(path_a), str(path_b), "--csv", str(out_path)])

    assert exit_code == 0
    text = out_path.read_text(encoding="utf-8")
    assert "dimension,kind_a,kind_b,label,share_a,share_b,share_delta,status" in text
    assert "dimension,kind_mismatch,dimension_score_a,dimension_score_b" in text


def test_profile_csv_export_unwritable_path_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--csv", "/nonexistent-dir/out.csv"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error: could not write CSV export to /nonexistent-dir/out.csv" in captured.err


def test_profile_sample_runs_without_a_file_argument(capsys):
    exit_code = main(["profile", "--sample", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert result["provenance"]["dataset_hash"].startswith("sha256:")
    assert any(d["name"] == "sex" for d in result["dimensions"])


def test_profile_sample_and_csv_both_given_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--sample"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "pass either csv or --sample, not both" in captured.err


def test_profile_without_csv_or_sample_returns_2_with_clean_error(capsys):
    exit_code = main(["profile"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "profile needs a csv argument (or --sample)" in captured.err


def test_profile_reads_csv_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("sex\nM\nF\nM\nF\n"))

    exit_code = main(["profile", "-", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert result["n_rows"] == 4
    assert result["dimensions"][0]["name"] == "sex"


def test_profile_reads_tsv_from_stdin_via_delimiter_sniffing(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("sex\tage\nM\t30\nF\t40\n"))

    exit_code = main(["profile", "-", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert result["n_cols"] == 2


def test_compare_reads_one_side_from_stdin(tmp_path, monkeypatch, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("sex\nM\nM\nM\nF\n"))

    exit_code = main(["compare", str(path_a), "-", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    assert result["a"]["n_rows"] == 4
    assert result["b"]["n_rows"] == 4


def test_compare_both_sides_from_stdin_returns_2_with_clean_error(capsys):
    exit_code = main(["compare", "-", "-"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--compare can't read both datasets from stdin" in captured.err


def test_profile_reference_and_input_from_stdin_returns_2_with_clean_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("sex\nM\nF\n"))

    exit_code = main(["profile", "-", "--reference", "-"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "profile input and --reference can't both read from stdin" in captured.err


def test_profile_proxy_held_out_and_input_from_stdin_returns_2_with_clean_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("sex\nM\nF\n"))

    exit_code = main(["profile", "-", "--proxy-hints", "--proxy-hints-with=-=race"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "profile input and --proxy-hints-with can't both read from stdin" in captured.err


def test_profile_read_table_runtime_error_exits_2_with_clean_error(tmp_path, capsys, monkeypatch):
    path = tmp_path / "a.parquet"
    path.write_text("not a real parquet file", encoding="utf-8")

    def raise_runtime(_path):
        raise RuntimeError("reading .parquet files requires the 'pyarrow' package")

    monkeypatch.setattr(cli, "read_table", raise_runtime)

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "error: reading .parquet files requires the 'pyarrow' package" in captured.err


def test_profile_read_table_generic_exception_exits_2_with_clean_error(tmp_path, capsys, monkeypatch):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    def raise_generic(_path):
        raise ValueError("boom")

    monkeypatch.setattr(cli, "read_table", raise_generic)

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert f"error: could not read dataset {path}: boom" in captured.err


def test_profile_malformed_cross_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--cross", "onlyonecolumn"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--cross expects two column names: COLA,COLB" in captured.err


def test_profile_cross_same_column_twice_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--cross", "sex,sex"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--cross needs two different columns, got 'sex' twice" in captured.err


def test_profile_cross_unknown_column_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex,race\n" + "M,A\nF,B\n" * 25, encoding="utf-8")

    exit_code = main(["profile", str(path), "--cross", "sex,raace"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "cross column(s) don't match any profiled dimension: raace" in captured.err


def test_profile_reference_missing_required_columns_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")
    ref_path = tmp_path / "ref.csv"
    ref_path.write_text("nothing,relevant\n1,2\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--reference", str(ref_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "reference needs column, group, and share columns" in captured.err


def test_profile_reference_with_no_matching_dimension_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nM\nF\n", encoding="utf-8")
    ref_path = tmp_path / "ref.csv"
    ref_path.write_text("column,group,share\ngendr,M,0.5\ngendr,F,0.5\n", encoding="utf-8")

    exit_code = main(["profile", str(path), "--reference", str(ref_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "reference file's column(s) don't match any profiled dimension: gendr" in captured.err


def test_profile_proxy_hints_runtime_error_returns_2_with_clean_error(tmp_path, capsys, monkeypatch):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    def raise_runtime(_df, _dimensions, **_kwargs):
        raise RuntimeError("proxy hints need scipy (install with: pip install faircode[proxy])")

    monkeypatch.setattr(cli, "proxy_hints", raise_runtime)

    exit_code = main(["profile", str(path), "--proxy-hints"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error: proxy hints need scipy" in captured.err


@requires_scipy
def test_proxy_hints_with_flags_a_dropped_column(tmp_path, capsys):
    path = tmp_path / "dropped.csv"
    held_path = tmp_path / "full.csv"
    zip_code = (["111"] * 100 + ["222"] * 100)
    race = (["A"] * 100 + ["B"] * 100)  # perfectly aligned with zip_code
    path.write_text("zip_code\n" + "\n".join(zip_code), encoding="utf-8")
    held_path.write_text("zip_code,race\n" +
                         "\n".join(f"{z},{r}" for z, r in zip(zip_code, race)),
                         encoding="utf-8")

    exit_code = main(["profile", str(path), "--proxy-hints",
                      "--proxy-hints-with", f"{held_path}=race", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    pair = next(h for h in result["proxy_hints"] if {h["a"], h["b"]} == {"zip_code", "race"})
    assert pair["p_value"] < 0.05


def test_proxy_hints_with_malformed_spec_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--proxy-hints", "--proxy-hints-with", "noequalssign"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "invalid --proxy-hints-with 'noequalssign'" in captured.err


def test_proxy_hints_with_unknown_column_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    held_path = tmp_path / "b.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")
    held_path.write_text("other\nx\ny\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--proxy-hints",
              "--proxy-hints-with", f"{held_path}=race"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert f"column 'race' not found in {held_path}" in captured.err


def test_proxy_hints_with_column_collision_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    held_path = tmp_path / "b.csv"
    path.write_text("sex,race\nM,A\nF,B\n", encoding="utf-8")
    held_path.write_text("race\nX\nY\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--proxy-hints",
              "--proxy-hints-with", f"{held_path}=race"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "column 'race' already exists in the profiled dataset" in captured.err


def test_proxy_hints_with_row_count_mismatch_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    held_path = tmp_path / "b.csv"
    path.write_text("sex\nM\nF\nM\n", encoding="utf-8")
    held_path.write_text("race\nA\nB\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--proxy-hints",
              "--proxy-hints-with", f"{held_path}=race"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "rows must align 1:1" in captured.err


@requires_openpyxl
def test_proxy_hints_with_xlsx_reports_ignored_sheets(tmp_path, capsys):
    import openpyxl

    path = tmp_path / "a.csv"
    path.write_text("sex\n" + "M\n" * 50 + "F\n" * 50, encoding="utf-8")

    held_path = tmp_path / "multi_sheet.xlsx"
    wb = openpyxl.Workbook()
    first = wb.active
    first.title = "Data"
    first.append(["race"])
    for _ in range(50):
        first.append(["A"])
    for _ in range(50):
        first.append(["B"])
    wb.create_sheet("Notes")
    wb.save(held_path)

    exit_code = main(["profile", str(path), "--proxy-hints",
                      "--proxy-hints-with", f"{held_path}=race"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"{held_path}: read sheet 'Data' - 1 other sheet(s) ignored." in captured.err


def test_proxy_hints_with_without_proxy_hints_returns_2_with_clean_error(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["profile", str(path),
                      "--proxy-hints-with", "/nonexistent/file.csv=race"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--proxy-hints-with needs --proxy-hints" in captured.err


requires_scipy = pytest.mark.skipif(
    importlib.util.find_spec("scipy") is None,
    reason="optional 'proxy' extra not installed",
)


@requires_scipy
def test_compare_proxy_hints_flags_a_real_proxy_in_both_datasets(tmp_path, capsys):
    # occupation is a perfect function of sex in both files -> maximal
    # association, so both A and B should surface the same proxy pair.
    rows = ["sex,occupation"] + [
        f"{'male' if i % 2 == 0 else 'female'},{'engineer' if i % 2 == 0 else 'nurse'}"
        for i in range(100)
    ]
    path_a = tmp_path / "a.csv"
    path_a.write_text("\n".join(rows), encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("\n".join(rows), encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--proxy-hints", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    for key in ("proxy_hints_a", "proxy_hints_b"):
        pair = next(h for h in result[key] if {h["a"], h["b"]} == {"sex", "occupation"})
        assert pair["p_value"] < 0.05


@requires_scipy
def test_compare_proxy_hints_with_flags_a_dropped_column_in_each_dataset(tmp_path, capsys):
    zip_code = (["111"] * 100 + ["222"] * 100)
    race = (["A"] * 100 + ["B"] * 100)  # perfectly aligned with zip_code

    path_a = tmp_path / "a.csv"
    path_a.write_text("zip_code\n" + "\n".join(zip_code), encoding="utf-8")
    held_a = tmp_path / "held_a.csv"
    held_a.write_text("zip_code,race\n" +
                      "\n".join(f"{z},{r}" for z, r in zip(zip_code, race)),
                      encoding="utf-8")

    path_b = tmp_path / "b.csv"
    path_b.write_text("zip_code\n" + "\n".join(zip_code), encoding="utf-8")
    held_b = tmp_path / "held_b.csv"
    held_b.write_text("zip_code,race\n" +
                      "\n".join(f"{z},{r}" for z, r in zip(zip_code, race)),
                      encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b), "--proxy-hints",
                      "--proxy-hints-with-a", f"{held_a}=race",
                      "--proxy-hints-with-b", f"{held_b}=race", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    result = json.loads(captured.out)
    for key in ("proxy_hints_a", "proxy_hints_b"):
        pair = next(h for h in result[key] if {h["a"], h["b"]} == {"zip_code", "race"})
        assert pair["p_value"] < 0.05


def test_compare_proxy_hints_with_a_without_proxy_hints_returns_2_with_clean_error(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")

    exit_code = main(["compare", str(path_a), str(path_b),
                      "--proxy-hints-with-a", "/nonexistent/file.csv=race"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--proxy-hints-with-a/-b needs --proxy-hints" in captured.err


def test_compare_proxy_hints_runtime_error_returns_2_with_clean_error(tmp_path, capsys, monkeypatch):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")

    def raise_runtime(_df, _dimensions, **_kwargs):
        raise RuntimeError("proxy hints need scipy (install with: pip install faircode[proxy])")

    monkeypatch.setattr(cli, "proxy_hints", raise_runtime)

    exit_code = main(["compare", str(path_a), str(path_b), "--proxy-hints"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "error: proxy hints need scipy" in captured.err


def test_profile_html_write_failure_returns_2_with_clean_error_not_a_traceback(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")
    bad_html_path = tmp_path / "no_such_dir" / "out.html"

    exit_code = main(["profile", str(path), "--html", str(bad_html_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert f"error: could not write HTML report to {bad_html_path}" in captured.err


def test_profile_html_write_success_reports_path(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")
    html_path = tmp_path / "out.html"

    exit_code = main(["profile", str(path), "--html", str(html_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert html_path.read_text(encoding="utf-8")
    assert f"HTML report written to {html_path}" in captured.err


def test_compare_html_write_failure_returns_2_with_clean_error_not_a_traceback(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")
    bad_html_path = tmp_path / "no_such_dir" / "out.html"

    exit_code = main(["compare", str(path_a), str(path_b), "--html", str(bad_html_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert f"error: could not write HTML report to {bad_html_path}" in captured.err


def test_compare_html_write_success_reports_path(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nF\n", encoding="utf-8")
    html_path = tmp_path / "out.html"

    exit_code = main(["compare", str(path_a), str(path_b), "--html", str(html_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert html_path.read_text(encoding="utf-8")
    assert f"HTML report written to {html_path}" in captured.err


@requires_openpyxl
def test_profile_xlsx_reports_ignored_sheets(tmp_path, capsys):
    import openpyxl

    path = tmp_path / "multi_sheet.xlsx"
    wb = openpyxl.Workbook()
    first = wb.active
    first.title = "Data"
    first.append(["sex"])
    first.append(["M"])
    first.append(["F"])
    wb.create_sheet("Notes")
    wb.create_sheet("Extra")
    wb.save(path)

    exit_code = main(["profile", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Read sheet 'Data' - 2 other sheet(s) ignored." in captured.err


@requires_openpyxl
def test_profile_xlsx_single_sheet_stays_silent(tmp_path, capsys):
    import openpyxl

    path = tmp_path / "single_sheet.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["sex"])
    ws.append(["M"])
    ws.append(["F"])
    wb.save(path)

    exit_code = main(["profile", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ignored" not in captured.err


@requires_openpyxl
def test_profile_xlsx_warns_when_encoding_has_no_effect(tmp_path, capsys):
    """#870: --encoding is accepted for .xlsx but does nothing; say so on stderr."""
    import openpyxl

    path = tmp_path / "data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["sex"])
    ws.append(["M"])
    ws.append(["F"])
    wb.save(path)

    exit_code = main(["profile", str(path), "--encoding", "latin-1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--encoding has no effect on .xlsx/.parquet files" in captured.err


def test_profile_parquet_warns_when_encoding_has_no_effect(tmp_path, capsys, monkeypatch):
    """#870: .parquet gets the same notice before the read fails without pyarrow."""
    path = tmp_path / "a.parquet"
    path.write_text("not a real parquet file", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("reading .parquet files requires the 'pyarrow' package")

    monkeypatch.setattr(cli, "read_table", boom)
    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(path), "--encoding", "latin-1"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "--encoding has no effect on .xlsx/.parquet files" in captured.err
    assert "error: reading .parquet files requires the 'pyarrow' package" in captured.err


def test_profile_csv_encoding_stays_silent(tmp_path, capsys):
    """#870: delimited input still uses --encoding; no false warning."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="latin-1")
    exit_code = main(["profile", str(path), "--encoding", "latin-1"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--encoding has no effect" not in captured.err


def _make_multi_sheet_xlsx(path, sex_values):
    import openpyxl

    wb = openpyxl.Workbook()
    first = wb.active
    first.title = "Data"
    first.append(["sex"])
    for value in sex_values:
        first.append([value])
    wb.create_sheet("Notes")
    wb.create_sheet("Extra")
    wb.save(path)


@requires_openpyxl
def test_compare_xlsx_reports_ignored_sheets_for_both_files(tmp_path, capsys):
    path_a = tmp_path / "a.xlsx"
    path_b = tmp_path / "b.xlsx"
    _make_multi_sheet_xlsx(path_a, ["M", "F"])
    _make_multi_sheet_xlsx(path_b, ["M", "M"])

    exit_code = main(["compare", str(path_a), str(path_b)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"{path_a}: read sheet 'Data' - 2 other sheet(s) ignored." in captured.err
    assert f"{path_b}: read sheet 'Data' - 2 other sheet(s) ignored." in captured.err


@requires_openpyxl
def test_compare_xlsx_single_sheet_stays_silent(tmp_path, capsys):
    import openpyxl

    path_a = tmp_path / "a.xlsx"
    path_b = tmp_path / "b.xlsx"
    for path, sex_values in ((path_a, ["M", "F"]), (path_b, ["M", "M"])):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        ws.append(["sex"])
        for value in sex_values:
            ws.append([value])
        wb.save(path)

    exit_code = main(["compare", str(path_a), str(path_b)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ignored" not in captured.err


# ── Benchmark subcommand tests ────────────────────────────────────────────────

@pytest.mark.parametrize("flag", ["--n-resamples", "--n-permutations"])
@pytest.mark.parametrize("value", ["0", "-1", "1.5", "abc"])
def test_cli_benchmark_rejects_invalid_counts(flag, value, monkeypatch, tmp_path, capsys):
    real_import = builtins.__import__

    def guard_benchmark_import(name, *args, **kwargs):
        if name in ("benchmark", "faircode.benchmark"):
            pytest.fail("invalid counts must be rejected before importing the benchmark")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard_benchmark_import)
    out_dir = tmp_path / "results"

    with pytest.raises(SystemExit) as exc:
        main(["benchmark", flag, value, "--out", str(out_dir)])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "usage: faircode benchmark" in captured.err
    assert f"argument {flag}:" in captured.err
    assert "positive integer" in captured.err
    assert value in captured.err
    assert "warning:" not in captured.err
    assert captured.out == ""
    assert not out_dir.exists()


@pytest.mark.parametrize("argv, expected_resamples, expected_permutations", [
    ([], 2000, 2000),
    (["--n-resamples", "1"], 1, 2000),
    (["--n-permutations", "1"], 2000, 1),
    (["--n-resamples", "50"], 50, 2000),
    (["--n-permutations", "50"], 2000, 50),
    (["--n-resamples", "3", "--n-permutations", "7"], 3, 7),
])
def test_cli_benchmark_passes_positive_and_default_counts(
    argv, expected_resamples, expected_permutations, monkeypatch, tmp_path,
):
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    received = {}

    def capture_benchmark(**kwargs):
        received.update(kwargs)
        return pd.DataFrame([{"audit": "test"}]), pd.DataFrame([{"audit": "test"}])

    monkeypatch.setattr("faircode.benchmark.run_benchmark", capture_benchmark)
    monkeypatch.setattr("faircode.benchmark.write_report", lambda *args, **kwargs: None)

    assert main(["benchmark", "--out", str(tmp_path / "results"), *argv]) == 0
    assert received["n_resamples"] == expected_resamples
    assert received["n_permutations"] == expected_permutations
    assert isinstance(received["n_resamples"], int)
    assert isinstance(received["n_permutations"], int)


def test_cli_benchmark_import_error_message(monkeypatch, capsys):
    """Lines 245-249: Catch ImportError and emit the optional install guidance."""
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "benchmark" in name:
            raise ImportError("No module named 'sklearn'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    monkeypatch.delitem(sys.modules, "faircode.benchmark", raising=False)

    exit_code = main(["benchmark"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "error: the benchmark command needs scikit-learn and pyyaml" in captured.err
    assert "pip install faircode[benchmark]" in captured.err


def test_cli_benchmark_paper_drift_warning_on_overrides(monkeypatch, tmp_path, capsys):
    """Lines 253-263: Stderr warning when overriding frozen default resamples/permutations."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    dummy_fairness = pd.DataFrame([{"audit": "German Credit Lending", "metric": "dp"}])
    dummy_perf = pd.DataFrame([{"audit": "German Credit Lending", "metric": "auc"}])

    monkeypatch.setattr(
        "faircode.benchmark.run_benchmark",
        lambda **kwargs: (dummy_fairness, dummy_perf),
    )
    monkeypatch.setattr("faircode.benchmark.write_report", lambda *args, **kwargs: None)

    out_dir = str(tmp_path / "results")
    exit_code = main([
        "benchmark",
        "--n-resamples", "50",
        "--n-permutations", "50",
        "--out", out_dir,
        "--no-plots",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "warning: --n-resamples=50, --n-permutations=50 differs from the frozen paper-run default (2000)" in captured.err
    assert f"Ran 1 audit(s), wrote 1 fairness rows and 1 performance rows to {out_dir}/" in captured.err


def test_cli_benchmark_missing_matplotlib_returns_2_with_clean_error(monkeypatch, tmp_path, capsys):
    """write_report's lazy `from .figures import generate_figures` (only reached
    when make_plots=True) used to raise a raw ImportError traceback instead of
    the same clean error the top-level scikit-learn/pyyaml import already gets."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    dummy_fairness = pd.DataFrame([{"audit": "German Credit Lending", "metric": "dp"}])
    dummy_perf = pd.DataFrame([{"audit": "German Credit Lending", "metric": "auc"}])

    monkeypatch.setattr(
        "faircode.benchmark.run_benchmark",
        lambda **kwargs: (dummy_fairness, dummy_perf),
    )

    def raise_import_error(*args, **kwargs):
        raise ImportError("No module named 'matplotlib'")

    monkeypatch.setattr("faircode.benchmark.write_report", raise_import_error)

    exit_code = main(["benchmark", "--out", str(tmp_path / "results")])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "error: writing benchmark plots needs matplotlib" in captured.err
    assert "pip install faircode[benchmark]" in captured.err


def test_cli_benchmark_no_manifests_found_error(tmp_path, capsys):
    """Lines 271-273: Error exit path when no audit.yaml manifests are found in --root."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    empty_dir = tmp_path / "empty_root"
    empty_dir.mkdir()

    exit_code = main(["benchmark", "--root", str(empty_dir)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert f"error: no audit.yaml manifests found under {empty_dir}" in captured.err


def test_cli_benchmark_missing_manifest_returns_2_with_clean_error(tmp_path, capsys):
    """A missing explicit manifest should report a clean path-aware error."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    missing = tmp_path / "missing" / "audit.yaml"
    exit_code = main(["benchmark", str(missing), "--no-plots"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert f"error: {missing}:" in captured.err
    assert "No such file or directory" in captured.err


def test_cli_benchmark_malformed_manifest_returns_2_with_clean_error(monkeypatch, tmp_path, capsys):
    """A malformed manifest or degenerate dataset used to crash `faircode
    benchmark` with a raw traceback (yaml.YAMLError/KeyError/sklearn
    ValueError) instead of the same clean CLI error every other anticipated
    failure in this subcommand already gets (#403)."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    def raise_value_error(**kwargs):
        raise ValueError("bad_audit/audit.yaml: 'target'")

    monkeypatch.setattr("faircode.benchmark.run_benchmark", raise_value_error)

    exit_code = main(["benchmark", "--out", str(tmp_path / "results")])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "error: bad_audit/audit.yaml: 'target'" in captured.err


@pytest.mark.skipif(not SMALL_AUDIT.is_file(), reason="German Credit Lending fixture not found")
def test_cli_benchmark_success_run(tmp_path, capsys):
    """Lines 274-283: Full benchmark execution against the German Credit Lending fixture."""
    pytest.importorskip("sklearn", reason="benchmark extra required")
    pytest.importorskip("fairlearn", reason="benchmark extra required")
    pytest.importorskip("yaml", reason="benchmark extra required")

    out_dir = tmp_path / "results"
    exit_code = main([
        "benchmark",
        str(SMALL_AUDIT),
        "--n-resamples", "5",
        "--n-permutations", "5",
        "--out", str(out_dir),
        "--no-plots",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Ran 1 audit(s)" in captured.err
    assert f"to {out_dir}/" in captured.err
    assert (out_dir / "results_fairness.csv").is_file()
    assert (out_dir / "results_performance.csv").is_file()
    assert (out_dir / "summary.csv").is_file()


def test_profile_csv_dash_writes_only_the_csv_to_stdout(tmp_path, capsys, monkeypatch):
    """#779: --csv - streams the export to stdout (no terminal report mixed in,
    no file literally named "-")."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["profile", str(path), "--csv", "-"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("dimension,kind,label,count,share,")
    assert "PROXY" not in out and "Dataset" not in out.splitlines()[0]
    assert not (tmp_path / "-").exists()


def test_compare_csv_dash_and_json_together_return_2(tmp_path, capsys):
    a = tmp_path / "a.csv"
    a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["compare", str(a), str(a), "--csv", "-", "--json"]) == 2
    assert "both write to stdout" in capsys.readouterr().err


def test_profile_proxy_alpha_out_of_range_returns_2(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["profile", str(path), "--proxy-hints", "--proxy-alpha", "1.5"]) == 2
    assert "--proxy-alpha must be in (0, 1]" in capsys.readouterr().err


def test_profile_proxy_alpha_changes_which_pairs_are_reported(tmp_path, capsys):
    pytest.importorskip("scipy")
    rows = ["sex,occupation"] + [
        f"{'male' if i % 2 == 0 else 'female'},{'engineer' if i % 2 == 0 else 'nurse'}"
        for i in range(100)
    ]
    path = tmp_path / "d.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert main(["profile", str(path), "--proxy-hints", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["proxy_hints"]
    assert main(["profile", str(path), "--proxy-hints", "--proxy-alpha", "1e-300", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["proxy_hints"] == []


def test_proxy_alpha_without_proxy_hints_returns_2_on_both_subcommands(tmp_path, capsys):
    """#804: --proxy-alpha alone used to validate and then silently do nothing."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["profile", str(path), "--proxy-alpha", "0.01"]) == 2
    assert "--proxy-alpha needs --proxy-hints" in capsys.readouterr().err
    assert main(["compare", str(path), str(path), "--proxy-alpha", "0.01"]) == 2
    assert "--proxy-alpha needs --proxy-hints" in capsys.readouterr().err


def test_compare_csv_export_unwritable_path_returns_2_with_clean_error(tmp_path, capsys):
    """#799: compare --csv goes through the same helper from its own call site."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    bad = tmp_path / "missing-dir" / "out.csv"
    assert main(["compare", str(path), str(path), "--csv", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "could not write CSV export" in err and "Traceback" not in err


def test_proxy_correction_flag_requires_proxy_hints_and_adds_p_adjusted(tmp_path, capsys):
    pytest.importorskip("scipy")
    rows = ["sex,occupation"] + [
        f"{'male' if i % 2 == 0 else 'female'},{'engineer' if i % 2 == 0 else 'nurse'}"
        for i in range(100)
    ]
    path = tmp_path / "d.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert main(["profile", str(path), "--proxy-correction", "holm"]) == 2
    assert "--proxy-correction needs --proxy-hints" in capsys.readouterr().err
    assert main(["profile", str(path), "--proxy-hints", "--proxy-correction", "bonferroni", "--json"]) == 0
    assert "p_adjusted" in json.loads(capsys.readouterr().out)["proxy_hints"][0]


def test_csv_provenance_appends_a_section_with_the_dataset_hash(tmp_path):
    """#800: --csv-provenance writes the same provenance --json attaches."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    out = tmp_path / "o.csv"
    assert main(["profile", str(path), "--csv", str(out)]) == 0
    assert "provenance_key" not in out.read_text(encoding="utf-8")
    assert main(["profile", str(path), "--csv", str(out), "--csv-provenance"]) == 0
    rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
    i = rows.index(["provenance_key", "provenance_value"])
    prov = dict(rows[i + 1:])
    assert prov["dataset_hash"].startswith("sha256:")
    assert prov["engine"] == "python" and "params.min_share" in prov


def test_csv_provenance_needs_csv_and_covers_compare(tmp_path, capsys):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["profile", str(path), "--csv-provenance"]) == 2
    assert "--csv-provenance needs --csv" in capsys.readouterr().err
    out = tmp_path / "c.csv"
    assert main(["compare", str(path), str(path), "--csv", str(out), "--csv-provenance"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "dataset_hash_a" in text and "dataset_hash_b" in text


def test_csv_bom_prefixes_file_with_utf8_bom(tmp_path, capsys):
    """#867: --csv-bom wires the unused bom= helper so Excel sees EF BB BF."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    out = tmp_path / "o.csv"
    assert main(["profile", str(path), "--csv", str(out)]) == 0
    assert not out.read_bytes().startswith(b"\xef\xbb\xbf")
    assert main(["profile", str(path), "--csv", str(out), "--csv-bom"]) == 0
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")
    # compare path too
    cout = tmp_path / "c.csv"
    assert main(["compare", str(path), str(path), "--csv", str(cout), "--csv-bom"]) == 0
    assert cout.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_bom_stdout_starts_with_feff_and_needs_csv(tmp_path, capsys):
    """#867: --csv - --csv-bom writes U+FEFF first; flag alone is rejected."""
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["profile", str(path), "--csv-bom"]) == 2
    assert "--csv-bom needs --csv" in capsys.readouterr().err
    assert main(["profile", str(path), "--csv", "-", "--csv-bom"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("\ufeff")
    assert "dimension" in out


def test_fail_under_error_explains_a_header_only_file_truthfully(tmp_path, capsys):
    """#839: columns WERE detected; what is missing is data, and the error says so."""
    path = tmp_path / "hdr.csv"
    path.write_text("sex,race\n", encoding="utf-8")
    assert main(["profile", str(path), "--fail-under", "50"]) == 2
    err = capsys.readouterr().err
    assert "no dimension had any non-missing values to measure" in err
    assert "no demographic columns" not in err


def test_header_only_file_shows_not_measured_not_zero_per_dimension(tmp_path, capsys):
    """#838: a dimension with no groups is "not measured", never "score 0/100"."""
    path = tmp_path / "hdr.csv"
    path.write_text("sex,race\n", encoding="utf-8")
    assert main(["profile", str(path)]) == 0
    out = capsys.readouterr().out
    assert "score not measured" in out and "score 0/100" not in out
    html = tmp_path / "r.html"
    assert main(["profile", str(path), "--html", str(html)]) == 0
    text = html.read_text(encoding="utf-8")
    assert "not measured" in text and "0/100" not in text


def test_profile_nested_json_flattens_and_profiles(tmp_path, capsys):
    # Issue #844: nested JSON records previously crashed with a raw traceback
    # due to TypeError: unhashable type: 'dict'.
    path = tmp_path / "nested.json"
    path.write_text(
        '[{"sex":"M","loc":{"state":"TX"}},{"sex":"F","loc":{"state":"CA"}}]',
        encoding="utf-8",
    )
    exit_code = main(["profile", str(path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Representation score:" in captured.out
    assert "sex" in captured.out
    assert "loc.state" in captured.out



def test_keywords_file_flag_types_columns_and_records_vocabulary(tmp_path, capsys):
    data = tmp_path / "d.csv"
    data.write_text("gndr,umr\n" + "\n".join(f"{'a' if i % 2 else 'b'},{20 + i}" for i in range(20)) + "\n")
    words = tmp_path / "kw.json"
    words.write_text('{"sex": ["gndr"], "age": ["umr"]}', encoding="utf-8")
    assert main(["profile", str(data), "--keywords", str(words), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert {d["name"]: d["kind"] for d in result["dimensions"]} == {"gndr": "sex", "umr": "age"}
    assert result["provenance"]["params"]["keywords"] == {"sex": ["gndr"], "age": ["umr"]}

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["profile", str(data), "--keywords", str(bad)])
    assert exc.value.code == 2 and "not valid JSON" in capsys.readouterr().err
    words.write_text('{"colour": ["x"]}', encoding="utf-8")
    assert main(["profile", str(data), "--keywords", str(words)]) == 2
    assert "unknown key(s): colour" in capsys.readouterr().err
