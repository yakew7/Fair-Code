"""Read a tabular dataset file, extending faircode.loaders with formats
added after the paper freeze (.json, .parquet).

`faircode/loaders.py` is on the frozen file list in CLAUDE.md and must stay
byte-identical to what the paper's benchmark was run against - the benchmark
harness (`faircode/benchmark.py`) reads its CSVs directly via `pd.read_csv`
and never imports it, so it has no bearing on any published number, but the
file itself is still not touched. New formats live here instead and delegate
to the frozen `read_table()` for everything it already handles.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd

from .loaders import SNIFF_SAMPLE_BYTES, _sniff_delimiter
from .loaders import read_table as _read_table_frozen


def read_table(path: str) -> pd.DataFrame:
    if path == "-":
        # No file extension to dispatch on for a stdin stream, so always
        # sniff - the same fallback loaders.read_table() uses for an
        # unrecognized/missing extension on a real file.
        content = sys.stdin.read()
        delimiter = _sniff_delimiter(content[:SNIFF_SAMPLE_BYTES])
        return pd.read_csv(io.StringIO(content), sep=delimiter)

    suffix = Path(path).suffix.lower()

    if suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            # pandas' own parser error for malformed JSON (e.g. a truncated
            # file) is an internal/version-specific message. Fail fast with
            # a clear message instead, mirroring the JS engine's parseJSON().
            raise ValueError(f"Unsupported JSON format (not valid JSON: {exc}).") from exc

        # Detect split-orient JSON:
        # {"columns": [...], "data": [...]}, optionally with "index".
        #
        # This must be checked before the generic dict-of-dicts detection
        # below because columns-oriented JSON is also represented as a
        # dictionary of dictionaries.
        if isinstance(parsed, dict) and {"columns", "data"} <= parsed.keys():
            return pd.read_json(path, orient="split")

        # Detect index-oriented JSON.
        #
        # pandas' "columns" and "index" orientations both use a
        # dict-of-dicts representation, so their shapes are inherently
        # ambiguous in JSON.
        #
        # Heuristic: when the dict-of-dicts is scalar and rectangular, prefer
        # the orientation implied by which dimension is larger (rows vs
        # columns). For square cases, use value type-homogeneity to prefer
        # columns-orient (columns are often homogeneous; rows often mix types).
        if isinstance(parsed, dict) and parsed and all(
            isinstance(value, dict) for value in parsed.values()
        ):
            inner_key_sets = [set(row.keys()) for row in parsed.values()]

            same_inner_keys = len({frozenset(keys) for keys in inner_key_sets}) == 1

            if same_inner_keys:
                inner_keys = inner_key_sets[0]

                cells_are_scalar = all(
                    not isinstance(cell, (dict, list))
                    for row in parsed.values()
                    for cell in row.values()
                )

                if cells_are_scalar:
                    outer_n = len(parsed)
                    inner_n = len(inner_keys)

                    if outer_n != inner_n:
                        orient = "index" if outer_n > inner_n else "columns"
                        return pd.read_json(path, orient=orient)

                    # Square case: prefer columns-orient when values are more type-homogeneous
                    # by column than by row.
                    row_type_score = sum(
                        len({type(cell) for cell in row.values()})
                        for row in parsed.values()
                    )
                    col_type_score = sum(
                        len({type(parsed[row_key][col_key]) for row_key in parsed})
                        for col_key in inner_keys
                    )

                    orient = "index" if row_type_score > col_type_score else "columns"
                    return pd.read_json(path, orient=orient)
        return pd.read_json(path)

    if suffix == ".parquet":
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise RuntimeError(
                "reading .parquet files requires the 'pyarrow' package "
                "(install with: pip install faircode[parquet])"
            ) from exc

    return _read_table_frozen(path)


def get_xlsx_sheet_info(path: str) -> tuple[str, list[str]] | None:
    """For an .xlsx file, return (sheet_name_read, other_sheet_names_ignored).

    `read_table()` always reads pandas' default sheet (index 0, via the
    frozen `loaders.read_table()`) - this only inspects what else is in the
    workbook so callers can tell a user which sheet was actually profiled,
    mirroring the web profiler's `parseXLSX()` (#182). Returns None for a
    non-.xlsx path, or if the workbook can't be opened - `read_table()`'s own
    error path already surfaces the real problem in that case.
    """
    if Path(path).suffix.lower() != ".xlsx":
        return None
    try:
        book = pd.ExcelFile(path)
    except Exception:
        return None
    if not book.sheet_names:
        return None

    return book.sheet_names[0], book.sheet_names[1:]