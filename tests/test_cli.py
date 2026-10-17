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


@requires_scipy
def test_profile_held_out_file_can_override_the_dataset_encoding(tmp_path, capsys):
    dataset = tmp_path / "dataset-latin1.csv"
    held = tmp_path / "held-utf8.csv"
    dataset.write_bytes(
        ("sex,city\n" + "M,Café\nF,Thé\n" * 20).encode("latin-1")
    )
    held.write_bytes(
        ("ráce\n" + "A\nB\n" * 20).encode("utf-8")
    )

    assert main([
        "profile", str(dataset), "--encoding", "latin-1", "--proxy-hints",
        "--proxy-hints-with", f"{held}=ráce@utf-8", "--json",
    ]) == 0

    provenance = json.loads(capsys.readouterr().out)["provenance"]
    assert provenance["encoding"] == "latin-1"
    assert provenance["proxy_hints_with"][0]["column"] == "ráce"
    assert provenance["proxy_hints_with"][0]["encoding"] == "utf-8"


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
    assert (
        "warning: --n-resamples=50, --n-permutations=50 differs from the default (2000); "
        "the numbers will not match the published results in results/ or the reference "
        "snapshot in paper/results-frozen/." in captured.err
    )
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
@pytest.mark.slow   # trains models end to end (about 15 s); `make test-fast` skips it (#910)
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


def test_proxy_exact_tuning_flags_need_proxy_exact_and_reach_provenance(tmp_path, capsys):
    # #906
    path = tmp_path / "d.csv"
    path.write_text("sex,race\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{'abcdef'[i % 6]}" for i in range(24)) + "\n", encoding="utf-8")
    assert main(["profile", str(path), "--proxy-hints", "--proxy-exact-permutations", "50"]) == 2
    assert "--proxy-exact-permutations needs --proxy-exact" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["profile", str(path), "--proxy-hints", "--proxy-exact", "--proxy-exact-max-rows", "0"])
    capsys.readouterr()
    assert main(["profile", str(path), "--proxy-hints", "--proxy-alpha", "1", "--proxy-exact",
                 "--proxy-exact-permutations", "99", "--proxy-exact-max-rows", "10", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provenance"]["params"]["exact_permutations"] == 99
    assert out["provenance"]["params"]["exact_max_rows"] == 10
    assert out["proxy_hints"][0]["p_method"] == "chi2-capped"
    assert main(["profile", str(path), "--proxy-hints", "--proxy-alpha", "1", "--proxy-exact", "--json"]) == 0
    params = json.loads(capsys.readouterr().out)["provenance"]["params"]
    assert (params["exact_permutations"], params["exact_max_rows"]) == (1000, 20000)


def test_near_unique_held_out_column_is_skipped_with_a_stderr_note(tmp_path, capsys):
    # #908
    n = 60
    data = tmp_path / "d.csv"
    data.write_text("sex,occupation\n" + "\n".join(f"{'m' if i % 2 else 'f'},{'x' if i % 2 else 'y'}" for i in range(n)) + "\n")
    held = tmp_path / "h.csv"
    held.write_text("ident\n" + "\n".join(f"id{i}" for i in range(n)) + "\n")
    assert main(["profile", str(data), "--proxy-hints", "--proxy-alpha", "1",
                 "--proxy-hints-with", f"{held}=ident", "--json"]) == 0
    captured = capsys.readouterr()
    assert "note: held-out column 'ident' has 60 distinct values" in captured.err
    assert all("ident" not in (h["a"], h["b"]) for h in json.loads(captured.out)["proxy_hints"])
    assert main(["profile", str(data), "--proxy-hints", "--proxy-alpha", "1", "--max-categorical-card", "100",
                 "--proxy-hints-with", f"{held}=ident", "--json"]) == 0
    assert "note:" not in capsys.readouterr().err


def test_compare_rename_flag_aligns_a_renamed_column_and_validates(tmp_path, capsys):
    # #913
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("race\n" + "x\ny\n" * 30)
    b.write_text("ethnicity\n" + "x\ny\n" * 30)
    assert main(["compare", str(a), str(b), "--rename", "race=ethnicity", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [d["name"] for d in out["dimensions"]] == ["race"]
    assert out["renamed_dimensions"] == [{"a": "race", "b": "ethnicity"}]
    assert out["provenance"]["params"]["renames"] == {"race": "ethnicity"}
    assert main(["compare", str(a), str(b), "--rename", "race=nope"]) == 2
    assert "not a dimension of the second dataset" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["compare", str(a), str(b), "--rename", "race"])
    assert "expected A_NAME=B_NAME" in capsys.readouterr().err
    assert main(["compare", str(a), str(a), "--rename", "race=race"]) == 2
    assert "renames a dimension to itself" in capsys.readouterr().err


def test_rename_given_twice_or_to_one_target_is_rejected(tmp_path, capsys):
    # #968
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("race,sex\n" + "x,m\ny,f\n" * 30)
    b.write_text("ethnicity,gender\n" + "x,m\ny,f\n" * 30)
    with pytest.raises(SystemExit) as exc:
        main(["compare", str(a), str(b), "--rename", "race=ethnicity", "--rename", "race=gender"])
    assert exc.value.code == 2
    assert "error: --rename 'race' given twice" in capsys.readouterr().err
    assert main(["compare", str(a), str(b), "--rename", "race=ethnicity", "--rename", "sex=ethnicity"]) == 2
    assert "--rename: 'ethnicity' is renamed more than once" in capsys.readouterr().err


def test_proxy_exact_permutations_rejects_more_than_a_million(tmp_path, capsys):
    # #926
    path = tmp_path / "d.csv"
    path.write_text("sex,race\n" + "\n".join(f"{'M' if i % 2 else 'F'},{'abcdef'[i % 6]}" for i in range(24)) + "\n")
    with pytest.raises(SystemExit):
        main(["profile", str(path), "--proxy-hints", "--proxy-exact", "--proxy-exact-permutations", "999999999999"])
    assert "at most 1,000,000" in capsys.readouterr().err
    assert main(["profile", str(path), "--proxy-hints", "--proxy-exact", "--proxy-exact-permutations", "50"]) == 0


def test_held_out_workbook_with_an_encoding_prints_the_ignored_notice(tmp_path, capsys):
    # #923: like the dataset notice from #870, for a held-out .xlsx given @ENCODING or --encoding.
    pytest.importorskip("openpyxl")
    data = tmp_path / "d.csv"
    data.write_text("id,occ\n" + "\n".join(f"{i},{i % 2}" for i in range(40)) + "\n")
    book = tmp_path / "h.xlsx"
    pd.DataFrame({"race": ["a", "b"] * 20}).to_excel(book, index=False)
    assert main(["profile", str(data), "--proxy-hints", "--proxy-hints-with", f"{book}=race@latin-1"]) == 0
    assert f"encoding has no effect on .xlsx/.parquet files (held-out file {book})" in capsys.readouterr().err
    assert main(["profile", str(data), "--proxy-hints", "--proxy-hints-with", f"{book}=race", "--encoding", "latin-1"]) == 0
    assert "held-out file" in capsys.readouterr().err
    assert main(["profile", str(data), "--proxy-hints", "--proxy-hints-with", f"{book}=race"]) == 0
    assert "held-out file" not in capsys.readouterr().err


def test_skipped_near_unique_held_out_column_reaches_json_notes_and_provenance(tmp_path, capsys):
    # #921
    n = 60
    data = tmp_path / "d.csv"
    data.write_text("sex,occupation\n" + "\n".join(f"{'m' if i % 2 else 'f'},{'x' if i % 2 else 'y'}" for i in range(n)) + "\n")
    held = tmp_path / "h.csv"
    held.write_text("ident,race\n" + "\n".join(f"id{i},{'ab'[i % 2]}" for i in range(n)) + "\n")
    assert main(["profile", str(data), "--proxy-hints", "--proxy-alpha", "1", "--proxy-hints-with", f"{held}=ident",
                 "--proxy-hints-with", f"{held}=race", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert any("held-out column 'ident'" in note for note in out["notes"])
    entries = {e["column"]: e for e in out["provenance"]["proxy_hints_with"]}
    assert entries["ident"]["tested"] is False and "identifier" in entries["ident"]["skip_reason"]
    assert "tested" not in entries["race"]


def test_readme_documents_every_held_out_spec_marker():
    # #922: ~, ! and @ENCODING (and the near-unique skip) are user-facing syntax, so the README says so.
    text = " ".join((Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8").split())
    for needle in ("PATH=COLUMN[:KEY][~|!][@ENCODING]", "full.csv=race:id~", "full.csv=race:id!", "full.csv=race@latin-1",
                   "looks like an identifier", "tested: false"):
        assert needle in text, needle


def test_python_dash_m_faircode_runs_the_cli():
    # #966: `python -m faircode` is the invocation the docs use; run it for real.
    import subprocess
    from faircode import __version__
    root = Path(__file__).resolve().parent.parent
    version = subprocess.run([sys.executable, "-m", "faircode", "--version"], capture_output=True, text=True, cwd=root)
    assert version.returncode == 0 and __version__ in (version.stdout + version.stderr)
    done = subprocess.run([sys.executable, "-m", "faircode", "profile", "--sample", "--json"],
                          capture_output=True, text=True, cwd=root)
    assert done.returncode == 0
    assert json.loads(done.stdout)["n_rows"] > 0
    bad = subprocess.run([sys.executable, "-m", "faircode", "profile", "--no-such-flag"], capture_output=True, text=True, cwd=root)
    assert bad.returncode == 2
    import shutil
    script = shutil.which("faircode")
    if script:   # the installed console script behaves the same
        assert subprocess.run([script, "--version"], capture_output=True, text=True).returncode == 0


@pytest.mark.parametrize("flags,message", [
    (["--proxy-alpha", "1.5", "--proxy-hints"], "--proxy-alpha must be in (0, 1]"),
    (["--proxy-alpha", "0.1"], "--proxy-alpha needs --proxy-hints"),
    (["--proxy-correction", "holm"], "--proxy-correction needs --proxy-hints"),
    (["--proxy-key-normalize"], "--proxy-key-normalize needs --proxy-hints"),
    (["--proxy-exact"], "--proxy-exact needs --proxy-hints"),
    (["--proxy-hints", "--proxy-exact-permutations", "50"], "--proxy-exact-permutations needs --proxy-exact"),
    (["--proxy-hints", "--proxy-exact-max-rows", "50"], "--proxy-exact-max-rows needs --proxy-exact"),
    (["--csv-provenance"], "--csv-provenance needs --csv"),
    (["--csv-bom"], "--csv-bom needs --csv"),
    (["--proxy-hints-with-a", "h.csv=race"], "--proxy-hints-with-a/-b needs --proxy-hints"),
])
def test_compare_proxy_flag_misuse_returns_2_with_the_message(flags, message, tmp_path, capsys):
    # #959: the compare branch repeats the profile branch's checks; each one is pinned here.
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("sex\n" + "m\nf\n" * 10)
    b.write_text("sex\n" + "m\nf\n" * 10)
    assert main(["compare", str(a), str(b)] + flags) == 2
    assert message in capsys.readouterr().err


def test_compare_refuses_two_inputs_that_both_read_stdin(tmp_path, capsys):
    # #959: a stream can only be read once, so csv_a / csv_b and a held-out spec cannot share "-".
    other = tmp_path / "b.csv"
    other.write_text("sex\n" + "m\nf\n" * 10)
    assert main(["compare", "-", str(other), "--proxy-hints", "--proxy-hints-with-a=-=race"]) == 2
    assert "csv_a and --proxy-hints-with-a can't both read from stdin" in capsys.readouterr().err
    assert main(["compare", str(other), "-", "--proxy-hints", "--proxy-hints-with-b=-=race"]) == 2
    assert "csv_b and --proxy-hints-with-b can't both read from stdin" in capsys.readouterr().err


def test_cli_accepts_an_escaped_equals_sign_in_a_held_out_path(tmp_path, capsys):
    # #958
    data = tmp_path / "d.csv"
    data.write_text("id,occ\n" + "\n".join(f"{i},{i % 2}" for i in range(40)) + "\n")
    held = tmp_path / "a=b.csv"
    held.write_text("id,race\n" + "\n".join(f"{i},{'ab'[i % 2]}" for i in range(40)) + "\n")
    assert main(["profile", str(data), "--proxy-hints", "--proxy-alpha", "1", "--json",
                 "--proxy-hints-with", f"{tmp_path}/a\\=b.csv=race:id"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provenance"]["proxy_hints_with"][0]["path"] == str(held)
    assert any({h["a"], h["b"]} == {"race", "occ"} for h in out["proxy_hints"])
    with pytest.raises(SystemExit):
        main(["profile", str(data), "--proxy-hints", "--proxy-hints-with", f"{held}=race:id"])
    assert "write the = inside the file name as" in capsys.readouterr().err


def test_held_out_report_is_explicit_and_compare_carries_per_side_skips(tmp_path, capsys):
    # #947: no hidden state on the argparse namespace; the report object feeds notes and provenance.
    from faircode.cli import HeldOutReport
    report = HeldOutReport()
    assert report.notes == [] and report.skipped_for("proxy_hints_with") == ()
    report.skipped.setdefault("proxy_hints_with_a", []).append("ident")
    assert report.skipped_for("proxy_hints_with_a") == ("ident",) and report.skipped_for("proxy_hints_with_b") == ()
    assert HeldOutReport().notes is not HeldOutReport().notes          # no shared mutable default

    n = 60
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    for path in (a, b):
        path.write_text("id,sex,occ\n" + "\n".join(f"{i},{'m' if i % 2 else 'f'},{'x' if i % 2 else 'y'}" for i in range(n)) + "\n")
    held = tmp_path / "h.csv"
    held.write_text("ident,race\n" + "\n".join(f"id{i},{'ab'[i % 2]}" for i in range(n)) + "\n")
    assert main(["compare", str(a), str(b), "--proxy-hints", "--proxy-alpha", "1", "--json",
                 f"--proxy-hints-with-a={held}=ident", f"--proxy-hints-with-b={held}=race"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert any("held-out column 'ident'" in note for note in out["notes"])
    prov = out["provenance"]
    assert prov["proxy_hints_with_a"][0]["tested"] is False and "tested" not in prov["proxy_hints_with_b"][0]


def _documented_faircode_commands():
    """Every `faircode ...` line in the README, CONTRIBUTING and SPEC code blocks (backslash
    continuations joined), as (file, line number, text)."""
    root = Path(__file__).resolve().parent.parent
    found = []
    for name in ("README.md", "CONTRIBUTING.md", "faircode/SPEC.md"):
        lines = (root / name).read_text(encoding="utf-8").split("\n")
        i = 0
        while i < len(lines):
            text = lines[i].removeprefix("$ ")
            if text.startswith("faircode "):
                start = i
                while text.rstrip().endswith("\\") and i + 1 < len(lines):
                    i += 1
                    text = text.rstrip()[:-1] + " " + lines[i]
                found.append((name, start + 1, text))
            i += 1
    return found


def test_every_documented_faircode_command_parses_with_the_real_parser(capsys):
    # #948: README/CONTRIBUTING/SPEC examples are checked against the argument parser, so a renamed or
    # removed flag, or a mistyped example, fails here instead of rotting. Parsing only; nothing is run.
    import shlex
    from faircode.cli import build_parser
    commands = _documented_faircode_commands()
    assert len(commands) >= 30                     # the cheat sheet is found, not silently empty
    failures = []
    for name, number, text in commands:
        try:
            tokens = shlex.split(text, comments=True)
        except ValueError as exc:
            failures.append(f"{name}:{number}: {exc}")
            continue
        try:
            build_parser().parse_args(tokens[1:])
        except SystemExit:
            failures.append(f"{name}:{number}: {capsys.readouterr().err.strip().splitlines()[-1]}  [{text[:70]}]")
    assert not failures, "\n".join(failures)


def test_every_long_option_is_mentioned_in_the_readme_or_spec():
    # #1040: a flag that only shows up in --help (benchmark --root, --no-plots) cannot be found by a reader.
    from faircode.cli import build_parser
    root = Path(__file__).resolve().parent.parent
    docs = (root / "README.md").read_text(encoding="utf-8") + (root / "faircode" / "SPEC.md").read_text(encoding="utf-8")
    subparsers = build_parser()._subparsers._group_actions[0].choices
    missing = [
        f"{name} {option}"
        for name, sub in subparsers.items()
        for action in sub._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help" and option not in docs
    ]
    assert not missing, "undocumented options: " + ", ".join(missing)


def test_the_documented_command_check_catches_a_bad_flag(capsys):
    import shlex
    from faircode.cli import build_parser
    for bad in ("faircode profile data.csv --no-such-flag", "faircode compare a.csv", "faircode profile --proxy-alpha"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(shlex.split(bad)[1:])
        capsys.readouterr()



def test_a_subcommand_without_a_handler_fails_loudly(monkeypatch):
    # #971: main() must not answer an unhandled command with the help text and exit 1.
    def parser_with_unhandled_command():
        parser = real_build_parser()
        parser._subparsers._group_actions[0].add_parser("bogus")
        return parser

    real_build_parser = cli.build_parser
    monkeypatch.setattr(cli, "build_parser", parser_with_unhandled_command)
    with pytest.raises(AssertionError, match="no handler for command 'bogus'"):
        main(["bogus"])



@pytest.mark.parametrize("command", ["profile", "compare"])
def test_csv_dash_with_json_is_refused_before_anything_reaches_stdout(tmp_path, capsys, command):
    # #970
    a = tmp_path / "a.csv"
    a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    inputs = [str(a)] if command == "profile" else [str(a), str(a)]
    assert main([command, *inputs, "--csv", "-", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().endswith("error: --csv - and --json both write to stdout; use one")



@pytest.mark.parametrize("command", ["profile", "compare"])
def test_unreadable_keywords_file_exits_2(tmp_path, capsys, command):
    # #969: a missing path and a directory both hit the OSError branch.
    a = tmp_path / "a.csv"
    a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    inputs = [str(a)] if command == "profile" else [str(a), str(a)]
    for bad in (tmp_path / "no-such-words.json", tmp_path):
        with pytest.raises(SystemExit) as exc:
            main([command, *inputs, "--keywords", str(bad)])
        assert exc.value.code == 2
        assert f"error: could not read --keywords file {bad}:" in capsys.readouterr().err



def _stdin_bytes(monkeypatch, raw):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="replace"))


def test_stdin_is_decoded_with_encoding_or_a_sniffed_bom(monkeypatch, capsys):
    # #972
    _stdin_bytes(monkeypatch, "sex,race\nM,Café\nF,Thé\nM,Café\nF,Thé\n".encode("latin-1"))
    assert main(["profile", "-", "--encoding", "latin-1", "--json"]) == 0
    race = next(d for d in json.loads(capsys.readouterr().out)["dimensions"] if d["name"] == "race")
    assert {g["label"] for g in race["groups"]} == {"Café", "Thé"}

    _stdin_bytes(monkeypatch, "sex,race\nM,Café\nF,Thé\nM,Café\nF,Thé\n".encode("utf-16"))   # BOM, no flag
    assert main(["profile", "-", "--json"]) == 0
    race = next(d for d in json.loads(capsys.readouterr().out)["dimensions"] if d["name"] == "race")
    assert {g["label"] for g in race["groups"]} == {"Café", "Thé"}


def test_stdin_that_is_not_utf8_names_the_encoding_flag(monkeypatch, capsys):
    # #972
    _stdin_bytes(monkeypatch, b"sex,race\nM,Caf\xe9\nF,Caf\xe9\n")
    with pytest.raises(SystemExit) as exc:
        main(["profile", "-"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "not valid utf-8" in err and "--encoding" in err
    _stdin_bytes(monkeypatch, b"sex\nM\nF\n")
    with pytest.raises(SystemExit) as exc:
        main(["profile", "-", "--encoding", "no-such-codec"])
    assert exc.value.code == 2 and "no-such-codec" in capsys.readouterr().err


@pytest.mark.parametrize("flag, value, message", [
    ("--max-categorical-card", "1", "max_categorical_card must be >= 2, got 1"),
    ("--max-dimension-groups", "0", "max_dimension_groups must be >= 1, got 0"),
])
@pytest.mark.parametrize("command", ["profile", "compare"])
def test_out_of_range_group_limits_exit_2(tmp_path, capsys, command, flag, value, message):
    # #974
    a = tmp_path / "a.csv"
    a.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    inputs = [str(a)] if command == "profile" else [str(a), str(a)]
    assert main([command, *inputs, flag, value]) == 2
    assert f"error: {message}" in capsys.readouterr().err


def test_compare_rename_across_kinds_reports_the_kind_mismatch(tmp_path, capsys):
    # #976: --rename pairs a sex column with a race column; the terminal report says why the
    # drift comparison was skipped (--map alone cannot do this: both sides share the override).
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("sex\n" + "m\nf\n" * 40)
    b.write_text("race\n" + "x\ny\n" * 40)
    assert main(["compare", str(a), str(b), "--rename", "sex=race"]) == 0
    assert "detected as sex vs race on the two datasets" in capsys.readouterr().out


def test_unsupported_spreadsheet_format_is_named_not_blamed_on_encoding(tmp_path, capsys):
    # #1018
    path = tmp_path / "old.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200)

    with pytest.raises(SystemExit) as exc:
        main(["profile", str(path)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unsupported format .xls" in err and ".xlsx" in err
    assert "--encoding" not in err and "not valid utf-8" not in err


def test_fail_on_drift_refuses_to_pass_when_nothing_can_be_compared(tmp_path, capsys):
    # #1017: two files with no detectable dimension, or only headers, are an error for the gate.
    nodims = tmp_path / "nodims.csv"
    nodims.write_text("x,y\n1,2\n", encoding="utf-8")
    header = tmp_path / "header.csv"
    header.write_text("sex,race\n", encoding="utf-8")
    for path in (nodims, header):
        assert main(["compare", str(path), str(path), "--fail-on-drift"]) == 2
        assert "cannot apply --fail-on-drift" in capsys.readouterr().err
    assert main(["compare", str(nodims), str(nodims)]) == 0          # without the gate it is just a report
    same = tmp_path / "same.csv"
    same.write_text("sex\n" + "m\nf\n" * 20, encoding="utf-8")
    assert main(["compare", str(same), str(same), "--fail-on-drift"]) == 0   # a real, drift-free comparison passes


def test_reference_csv_with_a_blank_share_ignores_that_row(tmp_path, capsys):
    # #1028: a blank share cell is skipped, not used as nan, and the rest of the baseline still applies.
    data = tmp_path / "d.csv"
    data.write_text("sex\n" + "M\nF\n" * 30, encoding="utf-8")
    ref = tmp_path / "ref.csv"
    ref.write_text("column,group,share\nsex,M,0.5\nsex,F,0.5\nsex,X,\n", encoding="utf-8")
    assert main(["profile", str(data), "--reference", str(ref), "--json"]) == 0
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    groups = {g["label"] for g in json.loads(out)["dimensions"][0]["reference"]["groups"]}
    assert groups == {"M", "F"}


def test_fail_under_outside_0_to_100_is_a_usage_error(tmp_path, capsys):
    """#1037: 150 would fail every run and -5 would never fail, so both are rejected."""
    path = tmp_path / "balanced.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    for value in ("150", "100.5", "-5", "-0.1", "nan", "inf"):
        assert main(["profile", str(path), "--fail-under", value]) == 2
        captured = capsys.readouterr()
        assert "--fail-under must be between 0 and 100, got " in captured.err
        assert captured.out == ""


def test_fail_under_accepts_both_ends_of_the_range(tmp_path, capsys):
    path = tmp_path / "balanced.csv"
    path.write_text("sex\nM\nF\nM\nF\n", encoding="utf-8")
    assert main(["profile", str(path), "--fail-under", "0"]) == 0
    assert main(["profile", str(path), "--fail-under", "100"]) == 0
    assert "must be between" not in capsys.readouterr().err
