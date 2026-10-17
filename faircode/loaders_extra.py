"""Read a tabular dataset file, extending faircode.loaders with additional
formats (.json, .parquet) beyond its core CSV/Excel support.

New formats live here rather than in `faircode/loaders.py` itself so that
core CLI/profiler usage never pulls in the extra formats' optional
dependencies (e.g. `pyarrow` for `.parquet`) - `faircode/loaders.py` stays
minimal, and this module delegates to its `read_table()` for everything it
already handles. The benchmark harness (`faircode/benchmark.py`) reads its
CSVs directly via `pd.read_csv` and never imports either module.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd

from .loaders import NUL_MESSAGE, SNIFF_SAMPLE_BYTES, _plain_parser_message, _sniff_delimiter, resolve_encoding, sniff_bom_encoding
from .loaders import read_table as _read_table_frozen


EMPTY_DATASET_MESSAGE = "dataset is empty (no header row)"   # mirrors parseCSV() in assets/profiler-engine.js (#1010)


def read_table(path: str, encoding: str | None = None) -> pd.DataFrame:
    """Read `path` ("-" for stdin) into a DataFrame; see _read_table_impl for the formats."""
    try:
        return _read_table_impl(path, encoding)
    except pd.errors.EmptyDataError:   # pandas says "No columns to parse from file"
        raise ValueError(EMPTY_DATASET_MESSAGE) from None


def _read_table_impl(path: str, encoding: str | None = None) -> pd.DataFrame:
    if path == "-":
        # No file extension to dispatch on for a stdin stream, so always
        # sniff - the same fallback loaders.read_table() uses for an
        # unrecognized/missing extension on a real file.
        if hasattr(sys.stdin, "buffer"):
            raw = sys.stdin.buffer.read()
            content = raw.decode(encoding or sniff_bom_encoding(raw[:4]) or "utf-8")
        else:
            content = sys.stdin.read()
        if "\x00" in content:   # same check and wording as loaders.read_table (#1025)
            raise ValueError(NUL_MESSAGE.format(path="stdin"))
        delimiter = _sniff_delimiter(content[:SNIFF_SAMPLE_BYTES])
        try:
            return pd.read_csv(io.StringIO(content), sep=delimiter)
        except pd.errors.ParserError as exc:
            raise ValueError(_plain_parser_message(str(exc))) from exc

    suffix = Path(path).suffix.lower()

    if suffix in (".jsonl", ".ndjson"):   # JSON Lines: one object per line (#1027)
        encoding = resolve_encoding(path, encoding)
        with open(path, "r", encoding=encoding) as f:
            lines = f.read().splitlines()
        records = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line.lstrip("\ufeff"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {number} is not valid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {number} is not a JSON object")
            records.append(record)
        if not records:
            raise ValueError(EMPTY_DATASET_MESSAGE)
        return pd.json_normalize(records)

    if suffix == ".json":
        encoding = resolve_encoding(path, encoding)
        with open(path, "r", encoding=encoding) as f:
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
            return pd.read_json(path, orient="split", encoding=encoding)

        # Detect table-orient JSON: {"schema": {...}, "data": [...]} - a
        # real, valid pandas export (the only orientation that round-trips
        # dtypes) that otherwise falls through to the plain pd.read_json(path)
        # call below and raises pandas' own internal "Mixing dicts with
        # non-Series may lead to ambiguous ordering" error instead of a clear
        # one.
        if isinstance(parsed, dict) and {"schema", "data"} <= parsed.keys():
            return pd.read_json(path, orient="table", encoding=encoding)

        # Detect index/columns-oriented JSON: a dict whose every top-level
        # value is itself a dict of scalars.
        #
        # pandas' "columns" and "index" orientations both serialize to this
        # exact same dict-of-dicts shape, so there is no reliable way to
        # infer which one produced a given file from its shape or value
        # types alone - a columns-oriented export can have more columns
        # than rows (breaking a "larger dimension is the index" heuristic),
        # and an all-string index-oriented export (the common case for this
        # repo's own demographic columns) gives a type-homogeneity tie-break
        # nothing to key off. Guessing risks silently transposing or
        # mislabeling the data, which for a fairness-auditing tool can flip
        # which group looks disadvantaged with no visible sign anything went
        # wrong. Fail loudly instead and point at the one orientation that
        # round-trips unambiguously.
        if isinstance(parsed, dict) and parsed and all(
            isinstance(value, dict) for value in parsed.values()
        ):
            cells_are_scalar = all(
                not isinstance(cell, (dict, list))
                for row in parsed.values()
                for cell in row.values()
            )

            if cells_are_scalar:
                raise ValueError(
                    "Ambiguous JSON orientation: this file is a dict of "
                    "dicts, which pandas' \"columns\" and \"index\" "
                    "orientations both produce identically, so it can't be "
                    "told apart reliably. Re-export it with "
                    "orient=\"split\" (df.to_json(path, orient=\"split\")), "
                    "which this loader always parses correctly."
                )
        # Detect records-orient JSON: a list of dicts. Flatten nested
        # objects with pandas.json_normalize so sub-objects become dotted
        # column names (e.g. loc.state) instead of dict cells that fail with
        # TypeError: unhashable type: 'dict' during column detection (#844).
        if isinstance(parsed, list) and (
            not parsed or all(isinstance(row, dict) for row in parsed)
        ):
            return pd.json_normalize(parsed)

        return pd.read_json(path, encoding=encoding)

    if suffix == ".parquet":
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise RuntimeError(
                "reading .parquet files requires the 'pyarrow' package "
                "(install with: pip install faircode[parquet])"
            ) from exc

    return _read_table_frozen(path, encoding=encoding)


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
        with pd.ExcelFile(path) as book:
            sheet_names = book.sheet_names
    except Exception:
        return None
    if not sheet_names:
        return None
    return sheet_names[0], sheet_names[1:]


# Binary table formats that never decode as text, so an explicit text encoding
# cannot apply (#870). Keep the suffixes lower-case to match Path.suffix.lower().
_ENCODING_IGNORED_SUFFIXES = (".xlsx", ".parquet")

ENCODING_IGNORED_CLI = "--encoding has no effect on .xlsx/.parquet files"
ENCODING_IGNORED_NOTE = "encoding has no effect on .xlsx/.parquet files"


def encoding_ignored_for_path(path: str) -> bool:
    """True when `path`'s suffix is a format that ignores a text encoding."""
    return Path(path).suffix.lower() in _ENCODING_IGNORED_SUFFIXES


def held_out_encoding_ignored_notes(specs, encoding=None) -> list:
    """One note per held-out spec whose file is a binary workbook/Parquet that an explicit
    encoding (the spec's `@ENCODING` or the shared `encoding`) cannot apply to (#923)."""
    from .proxy import partition_held_out_path, split_held_out_encoding
    notes = []
    for spec in specs or []:
        try:
            bare, spec_encoding = split_held_out_encoding(spec)
        except ValueError:
            continue   # the real parse reports a malformed suffix
        path = partition_held_out_path(bare)[0]
        if (spec_encoding or encoding) and path and encoding_ignored_for_path(path):
            notes.append(f"{ENCODING_IGNORED_NOTE} (held-out file {path})")
    return notes


def encoding_ignored_note(path: str, encoding: str | None) -> str | None:
    """Return the MCP/agent note when `encoding` is set for a binary path."""
    if encoding is None or not encoding_ignored_for_path(path):
        return None
    return ENCODING_IGNORED_NOTE
