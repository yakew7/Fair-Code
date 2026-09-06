"""Read a tabular dataset file into a DataFrame, regardless of format.

Supports .csv, .tsv, and .xlsx (the last requires the optional `openpyxl`
extra: `pip install faircode[excel]`). Files with an unrecognized or missing
extension fall back to sniffing the delimiter from their content, so a
tab-separated export saved with a `.csv` extension still reads correctly.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

SNIFF_DELIMITERS = ",\t;|"
SNIFF_SAMPLE_BYTES = 8192


def read_table(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()

    if suffix == ".xlsx":
        try:
            return pd.read_excel(path)
        except ImportError as exc:
            raise RuntimeError(
                "reading .xlsx files requires the 'openpyxl' package "
                "(install with: pip install faircode[excel])"
            ) from exc

    if suffix == ".tsv":
        return _read_delimited(path, default="\t")

    if suffix == ".csv":
        return _read_delimited(path, default=",")

    return _read_delimited(path, default=",")


def _read_delimited(path: str, *, default: str) -> pd.DataFrame:
    """Read delimited text, using the extension's convention only as fallback."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        sample = fh.read(SNIFF_SAMPLE_BYTES)
    return pd.read_csv(path, sep=_sniff_delimiter(sample, default=default))


def _sniff_delimiter(sample: str, default: str = ",") -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=SNIFF_DELIMITERS).delimiter
    except csv.Error:
        return default
