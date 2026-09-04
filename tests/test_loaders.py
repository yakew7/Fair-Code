"""Tests for faircode.loaders: format-agnostic dataset reading (#59).

Run from the repo root:  pytest tests/ -q
"""

import importlib.util
import json

import pandas as pd
import pytest

from faircode import profile
from faircode.loaders import _sniff_delimiter
from faircode.loaders_extra import get_xlsx_sheet_info, read_table

requires_openpyxl = pytest.mark.skipif(
    importlib.util.find_spec("openpyxl") is None,
    reason="optional 'excel' extra not installed",
)

requires_pyarrow = pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None,
    reason="optional 'parquet' extra not installed",
)


ROWS = {
    "patient_id": [1, 2, 3, 4],
    "sex": ["M", "F", "M", "F"],
    "age": [24, 31, 45, 62],
}


def _write_csv(path, sep=","):
    df = pd.DataFrame(ROWS)
    df.to_csv(path, sep=sep, index=False)
    return df


# ── Delimiter sniffing ───────────────────────────────────────────────────────
def test_sniff_delimiter_detects_tab():
    sample = "a\tb\tc\n1\t2\t3\n4\t5\t6\n"
    assert _sniff_delimiter(sample) == "\t"


def test_sniff_delimiter_detects_comma():
    sample = "a,b,c\n1,2,3\n4,5,6\n"
    assert _sniff_delimiter(sample) == ","


def test_sniff_delimiter_falls_back_to_comma_default():
    assert _sniff_delimiter("just one column\nno delimiter at all\n") == ","


# ── read_table by extension ──────────────────────────────────────────────────
def test_read_table_tsv(tmp_path):
    path = tmp_path / "data.tsv"
    _write_csv(path, sep="\t")
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]
    assert len(df) == 4


def test_read_table_csv(tmp_path):
    path = tmp_path / "data.csv"
    _write_csv(path, sep=",")
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]

@pytest.mark.parametrize(
    "orient",
    ["records", "split"],
)
def test_read_table_json_orientations(tmp_path, orient):
    path = tmp_path / "data.json"
    expected = pd.DataFrame(ROWS)
    expected.to_json(path, orient=orient)
    df = read_table(str(path))

    pd.testing.assert_frame_equal(
        df.reset_index(drop=True),
        expected.reset_index(drop=True),
        check_dtype=False,
    )


def test_read_table_json_columns_orient_raises_ambiguous_error(tmp_path):
    # orient="columns" serializes to the same dict-of-dicts shape as
    # orient="index" - relying on it round-tripping was only ever correct
    # because pandas' own default guess happens to be "columns", not
    # because the shape is actually unambiguous (see the ambiguous-JSON
    # coverage in tests/test_json_edge_cases.py, and #405). read_table()
    # now raises for any dict-of-dicts JSON rather than guess.
    path = tmp_path / "data.json"
    pd.DataFrame(ROWS).to_json(path, orient="columns")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(path))


def test_read_table_json_split_orient_without_index_key(tmp_path):
    # A minimal, hand-written split-orient file that omits the optional
    # "index" key - the shape assets/profiler-engine.js's own parseJSON()
    # documents and accepts. pd.read_json(path) (the default orientation
    # guess) doesn't raise on this shape, it just returns two columns
    # literally named "columns" and "data", so detection can't rely on
    # the default orientation failing.
    path = tmp_path / "data.json"
    path.write_text(json.dumps({
        "columns": ["patient_id", "sex", "age"],
        "data": [[1, "M", 30], [2, "F", 25]],
    }))
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]
    assert df.iloc[0].tolist() == [1, "M", 30]
    assert df.iloc[1].tolist() == [2, "F", 25]


@requires_openpyxl
def test_read_table_xlsx(tmp_path):
    path = tmp_path / "data.xlsx"
    pd.DataFrame(ROWS).to_excel(path, index=False)
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]
    assert len(df) == 4


@requires_pyarrow
def test_read_table_parquet(tmp_path):
    path = tmp_path / "data.parquet"
    pd.DataFrame(ROWS).to_parquet(path, index=False)
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]
    assert len(df) == 4


def test_read_table_parquet_missing_pyarrow_raises_clean_runtime_error(tmp_path, monkeypatch):
    # Simulates pyarrow genuinely being unavailable at the loaders_extra.py
    # level - tests/test_cli.py's equivalent test only monkeypatches
    # read_table itself, never exercising the real
    # `except ImportError as exc: raise RuntimeError(...)` conversion.
    import faircode.loaders_extra as loaders_extra

    path = tmp_path / "data.parquet"
    path.write_text("not a real parquet file", encoding="utf-8")

    def raise_import_error(*args, **kwargs):
        raise ImportError("No module named 'pyarrow'")

    monkeypatch.setattr(loaders_extra.pd, "read_parquet", raise_import_error)

    with pytest.raises(RuntimeError, match="reading .parquet files requires the 'pyarrow' package"):
        read_table(str(path))


def test_get_xlsx_sheet_info_returns_none_for_non_xlsx_path(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")

    assert get_xlsx_sheet_info(str(path)) is None


@requires_openpyxl
def test_get_xlsx_sheet_info_returns_none_for_a_corrupt_xlsx_file(tmp_path):
    # Genuinely unreadable content behind an .xlsx extension - the
    # except Exception: return None fallback, previously never exercised.
    # read_table()'s own error path is what's meant to surface this failure
    # instead, so this only checks the fallback doesn't itself misbehave.
    path = tmp_path / "corrupt.xlsx"
    path.write_bytes(b"not a real xlsx file")

    assert get_xlsx_sheet_info(str(path)) is None


def test_read_table_unknown_extension_sniffs_tabs(tmp_path):
    path = tmp_path / "data.txt"
    _write_csv(path, sep="\t")
    df = read_table(str(path))
    assert list(df.columns) == ["patient_id", "sex", "age"]


# ── Parity: profile() must produce identical results across formats ─────────
def test_tsv_and_csv_profile_identically(tmp_path):
    csv_path = tmp_path / "data.csv"
    tsv_path = tmp_path / "data.tsv"
    _write_csv(csv_path, sep=",")
    _write_csv(tsv_path, sep="\t")

    result_csv = profile(read_table(str(csv_path)))
    result_tsv = profile(read_table(str(tsv_path)))
    assert result_csv == result_tsv


@requires_openpyxl
def test_xlsx_and_csv_profile_identically(tmp_path):
    csv_path = tmp_path / "data.csv"
    xlsx_path = tmp_path / "data.xlsx"
    _write_csv(csv_path, sep=",")
    pd.DataFrame(ROWS).to_excel(xlsx_path, index=False)

    result_csv = profile(read_table(str(csv_path)))
    result_xlsx = profile(read_table(str(xlsx_path)))
    assert result_csv == result_xlsx

def test_json_and_csv_profile_identically(tmp_path):
    csv_path = tmp_path / "data.csv"
    json_path = tmp_path / "data.json"

    _write_csv(csv_path, sep=",")
    pd.DataFrame(ROWS).to_json(json_path, orient="records")

    result_csv = profile(read_table(str(csv_path)))
    result_json = profile(read_table(str(json_path)))

    assert result_csv == result_json


@requires_pyarrow
def test_parquet_and_csv_profile_identically(tmp_path):
    csv_path = tmp_path / "data.csv"
    parquet_path = tmp_path / "data.parquet"

    _write_csv(csv_path, sep=",")
    pd.DataFrame(ROWS).to_parquet(parquet_path, index=False)

    result_csv = profile(read_table(str(csv_path)))
    result_parquet = profile(read_table(str(parquet_path)))

    assert result_csv == result_parquet
