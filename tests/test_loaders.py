"""Tests for faircode.loaders: format-agnostic dataset reading (#59).

Run from the repo root:  pytest tests/ -q
"""

import gc
import importlib.util
import json
import warnings

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


def test_sniff_delimiter_tolerates_one_messy_row_beyond_the_first_five():
    """A stray unquoted delimiter in a free-text field, past the first 5 rows,
    used to make csv.Sniffer() see an inconsistent sample and fall back to the
    default - even though assets/profiler-engine.js's own sniffer (which only
    checks the first 5 logical rows) picks the right delimiter every time.
    See issue #729 - both engines must agree.
    """
    sample = (
        "sex;race;age\n"
        "M;White;25\n"
        "F;Black;30\n"
        "M;White;45\n"
        "F;Asian;22\n"
        "M;White;50\n"
        "F;Black; recorded twice;29\n"
        "M;Asian;33\n"
    )
    assert _sniff_delimiter(sample) == ";"


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
    ("suffix", "separator"),
    [(".csv", ";"), (".tsv", ",")],
)
def test_read_table_sniffs_delimiter_despite_extension(tmp_path, suffix, separator):
    path = tmp_path / f"data{suffix}"
    expected = _write_csv(path, sep=separator)

    actual = read_table(str(path))

    pd.testing.assert_frame_equal(actual, expected)

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


@requires_openpyxl
def test_get_xlsx_sheet_info_closes_the_workbook(tmp_path):
    # Listing sheet names must not leak the workbook's file handle: an unclosed
    # handle raises a ResourceWarning on garbage collection and, on Windows,
    # keeps the file locked against deletion or overwrite (#1051).
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(ROWS).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame(ROWS).to_excel(writer, sheet_name="Second", index=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        info = get_xlsx_sheet_info(str(path))
        gc.collect()

    assert info == ("First", ["Second"])
    unclosed = [
        w
        for w in caught
        if issubclass(w.category, ResourceWarning) and "unclosed" in str(w.message)
    ]
    assert not unclosed, f"workbook left open: {[str(w.message) for w in unclosed]}"


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


# --- #843: non-UTF-8 input ---------------------------------------------------

_LATIN = "sex,race\nM,Café\nF,Señor\nM,Café\nF,Señor\n"


def test_read_table_encoding_argument_reads_latin1(tmp_path):
    path = tmp_path / "latin.csv"
    path.write_bytes(_LATIN.encode("latin-1"))
    df = read_table(str(path), encoding="latin-1")
    assert sorted(df["race"].unique()) == ["Café", "Señor"]


def test_read_table_without_encoding_still_rejects_latin1(tmp_path):
    path = tmp_path / "latin.csv"
    path.write_bytes(_LATIN.encode("latin-1"))
    with pytest.raises(UnicodeDecodeError):
        read_table(str(path))


@pytest.mark.parametrize("codec", ["utf-16", "utf-32", "utf-8-sig"])
def test_read_table_sniffs_bom_encodings(tmp_path, codec):
    path = tmp_path / "bom.csv"
    path.write_bytes(_LATIN.encode(codec))
    df = read_table(str(path))
    assert list(df.columns) == ["sex", "race"]
    assert sorted(df["race"].unique()) == ["Café", "Señor"]


def test_cli_encoding_flag_and_decode_error_hint(tmp_path, capsys):
    from faircode.cli import main
    path = tmp_path / "latin.csv"
    path.write_bytes(_LATIN.encode("latin-1"))

    with pytest.raises(SystemExit) as exc:
        main(["profile", str(path)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--encoding" in err and "not valid utf-8" in err

    assert main(["profile", str(path), "--encoding", "latin-1", "--json", "--no-provenance"]) == 0
    assert "Café" in json.dumps(json.loads(capsys.readouterr().out), ensure_ascii=False)

    with pytest.raises(SystemExit):
        main(["profile", str(path), "--encoding", "nope-9"])
    assert "unknown --encoding" in capsys.readouterr().err


def test_read_table_json_honours_encoding_and_bom(tmp_path):
    """#843 follow-up: .json used to be decoded as UTF-8 whatever --encoding said."""
    rows = [{"sex": "M", "race": "Café"}, {"sex": "F", "race": "Señor"}]
    text = json.dumps(rows, ensure_ascii=False)

    latin = tmp_path / "latin.json"
    latin.write_bytes(text.encode("latin-1"))
    assert list(read_table(str(latin), encoding="latin-1")["race"]) == ["Café", "Señor"]
    with pytest.raises(UnicodeDecodeError):
        read_table(str(latin))

    for codec in ("utf-16", "utf-8-sig"):
        bom = tmp_path / f"{codec}.json"
        bom.write_bytes(text.encode(codec))
        assert list(read_table(str(bom))["race"]) == ["Café", "Señor"]

    split = tmp_path / "split.json"
    split.write_bytes(json.dumps({"columns": ["race"], "data": [["Café"], ["Señor"]]},
                                 ensure_ascii=False).encode("latin-1"))
    assert list(read_table(str(split), encoding="latin-1")["race"]) == ["Café", "Señor"]


# #964: edge cases of the quote-aware delimiter sniffing (the JS engine mirrors it).
from js_helpers import SNIFF_CASES  # shared with the Python/JS parity test


@pytest.mark.parametrize("text,expected", SNIFF_CASES)
def test_sniff_delimiter_edge_cases(text, expected):
    assert _sniff_delimiter(text) == expected


def test_sniff_delimiter_uses_the_given_default_when_nothing_qualifies():
    assert _sniff_delimiter("a\n1\n", default="\t") == "\t"
    assert _sniff_delimiter("", default=";") == ";"


def test_logical_row_counts_skip_quoted_newlines_and_respect_max_rows():
    from faircode.loaders import _logical_row_delimiter_counts as counts
    assert counts('a;b\n"x;\ny";2\n', ";") == [1, 1]          # a quoted newline does not end the row
    assert counts("a;b\n" * 9, ";", max_rows=3) == [1, 1, 1]
    assert counts("", ";") == [] and counts("\n\n", ";") == []


def test_reading_xlsx_without_openpyxl_names_the_extra(tmp_path, monkeypatch, capsys):
    # #1004: pandas raises ImportError when openpyxl is missing; the user gets one plain line.
    from faircode.cli import main

    def no_openpyxl(*args, **kwargs):
        raise ImportError("Missing optional dependency 'openpyxl'")

    monkeypatch.setattr(pd, "read_excel", no_openpyxl)
    path = tmp_path / "a.xlsx"
    path.write_bytes(b"PK")
    with pytest.raises(RuntimeError, match=r"requires the 'openpyxl' package \(install with: pip install faircode\[excel\]\)"):
        read_table(str(path))
    with pytest.raises(SystemExit) as exc:
        main(["profile", str(path)])
    assert exc.value.code == 2
    assert "pip install faircode[excel]" in capsys.readouterr().err


def test_get_xlsx_sheet_info_returns_none_for_a_workbook_without_sheets(tmp_path, monkeypatch):
    # #1006: an opened workbook that lists no sheets stays silent; the real read reports the problem.
    class NoSheets:
        sheet_names = []

    monkeypatch.setattr(pd, "ExcelFile", lambda path: NoSheets())
    path = tmp_path / "a.xlsx"
    path.write_bytes(b"PK")
    assert get_xlsx_sheet_info(str(path)) is None


def test_held_out_encoding_notes_skip_a_malformed_encoding_suffix():
    # #1006: `h.xlsx=race@` has an empty codec name; the real parse reports it, the notice must not raise.
    from faircode.loaders_extra import held_out_encoding_ignored_notes
    assert held_out_encoding_ignored_notes(["h.xlsx=race@"], "latin-1") == []
    assert held_out_encoding_ignored_notes(["h.xlsx=race@no-such-codec"]) == []


def test_an_empty_file_says_so_in_plain_words(tmp_path, capsys, monkeypatch):
    # #1010: not pandas' "No columns to parse from file"; the same words in the CLI, stdin and MCP.
    import io
    from faircode.cli import main
    from faircode.loaders_extra import EMPTY_DATASET_MESSAGE
    path = tmp_path / "zero.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match=r"dataset is empty \(no header row\)"):
        read_table(str(path))
    with pytest.raises(SystemExit) as exc:
        main(["profile", str(path)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"could not read dataset {path}: {EMPTY_DATASET_MESSAGE}" in err and "No columns" not in err
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(ValueError, match="dataset is empty"):
        read_table("-")
    header_only = tmp_path / "header.csv"
    header_only.write_text("sex,race\n", encoding="utf-8")
    assert list(read_table(str(header_only)).columns) == ["sex", "race"]    # a header row is not empty


@pytest.mark.parametrize("suffix", [".xls", ".ods", ".feather", ".pkl", ".zip", ".7z", ".XLS"])
def test_read_table_names_an_unsupported_binary_format(tmp_path, suffix):
    # #1018: the old file read as text and failed with a "not valid utf-8, pass --encoding" hint, which cannot help.
    path = tmp_path / f"data{suffix}"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200)

    with pytest.raises(ValueError, match=r"unsupported format .*: save it as \.xlsx or \.csv") as exc:
        read_table(str(path))
    assert suffix.lower() in str(exc.value)
    assert "--encoding" not in str(exc.value)


def test_read_table_reports_a_missing_unsupported_file_as_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_table(str(tmp_path / "gone.xls"))


def test_read_table_still_sniffs_an_unknown_text_extension(tmp_path):
    path = tmp_path / "data.dat"
    path.write_text("sex,age\nM,30\nF,41\n", encoding="utf-8")

    assert list(read_table(str(path)).columns) == ["sex", "age"]


def test_a_binary_file_with_an_unknown_suffix_is_rejected(tmp_path):
    # #1019: a stub that is not text must not profile with exit 0; a real .dat TSV still reads.
    from faircode.cli import main
    binary = tmp_path / "a.sav"
    binary.write_bytes(b"ARROW1\x00\x00junk\x00\x01\x02")
    with pytest.raises(ValueError, match="looks like a binary file, not a table"):
        read_table(str(binary))
    with pytest.raises(SystemExit) as exc:
        main(["profile", str(binary)])
    assert exc.value.code == 2
    tsv = tmp_path / "a.dat"
    tsv.write_text("sex\tage\nM\t30\nF\t40\n", encoding="utf-8")
    assert list(read_table(str(tsv)).columns) == ["sex", "age"]
