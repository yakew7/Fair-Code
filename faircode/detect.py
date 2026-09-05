"""Demographic column auto-detection.

Implements section 1 of faircode/SPEC.md. Kept dependency-free (no pandas import
required for the matching logic) so the keyword lists stay the single source of
truth that the JS port mirrors verbatim.
"""

from __future__ import annotations

import re

# Keyword lists - order matters; the first dimension that matches wins.
# Mirror these exactly in assets/profiler-engine.js.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("sex", ("sex", "gender")),
    ("race", ("race", "ethnic", "ethnicity")),
    ("age", ("age", "dob", "yob", "birth")),
    ("geography", ("region", "state", "zip", "zipcode", "postal", "country",
                   "county", "city", "location", "province")),
]

MAX_CATEGORICAL_CARD = 20

# Keywords whose prefix form collides with ordinary English words - "race",
# "state", "city", "region", and "country" would otherwise prefix-match
# "raceway", "statement"/"stateless", "citycenter", "regional", and
# "countryside" respectively, none of which are demographic columns. These
# stay exact-match-only regardless of length; every other 4+ char keyword
# still uses prefix matching (see _token_matches).
EXACT_ONLY_KEYWORDS = frozenset({"race", "state", "city", "region", "country"})

# Kinds a user may force a column to via a manual override. Anything else
# (e.g. "ignore") excludes the column from analysis. Mirror in profiler-engine.js.
VALID_KINDS = ("sex", "race", "age", "geography", "categorical")


def _tokens(name: str) -> list[str]:
    """Split a column name into lower-case tokens on separators AND camelCase.

    'DateOfBirth' -> ['date','of','birth']; 'Sex_Code_Text' -> ['sex','code','text'];
    'ageGroup' -> ['age','group']. This token boundary is what stops 'age' from
    matching 'Agency_Text' or 'Language'.
    """
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


def _token_matches(token: str, keyword: str) -> bool:
    """Exact match for short keywords (<4 chars) and EXACT_ONLY_KEYWORDS;
    prefix match for other keywords of 4+ chars.

    Prefix (not substring) avoids 'age' matching 'agency' while still catching
    'statecode', 'ethnicity', etc. EXACT_ONLY_KEYWORDS carves out the stems
    whose prefix form collides with ordinary English words instead ('race'
    matching 'raceway', 'state' matching 'statement').
    """
    if len(keyword) < 4 or keyword in EXACT_ONLY_KEYWORDS:
        return token == keyword
    return token.startswith(keyword)


def classify_name(name: str) -> str | None:
    """Return the dimension kind for a column name, or None if no keyword matches."""
    tokens = _tokens(name)
    for kind, words in KEYWORDS:
        if any(_token_matches(tok, word) for tok in tokens for word in words):
            return kind
    return None


def detect_columns(df, overrides=None) -> list[dict]:
    """Detect demographic columns in a DataFrame.

    Returns a list of {"name": str, "kind": str} dicts. Keyword-matched columns
    are always kept; unmatched columns are kept as generic "categorical" only
    when their distinct non-null value count is in [2, MAX_CATEGORICAL_CARD].

    `overrides` is an optional {column: kind} map that wins over auto-detection:
    a kind in VALID_KINDS forces that column to that dimension (regardless of its
    name); any other value (e.g. "ignore") drops the column from analysis.
    """
    overrides = overrides or {}
    detected: list[dict] = []
    for col in df.columns:
        if col in overrides:
            kind = overrides[col]
            if kind in VALID_KINDS:
                detected.append({"name": col, "kind": kind})
            # any other override value (e.g. "ignore") excludes the column
            continue
        kind = classify_name(col)
        if kind is not None:
            detected.append({"name": col, "kind": kind})
            continue
        # Generic categorical fallback for low-cardinality columns.
        series = df[col].dropna()
        n_unique = series.nunique()
        if 2 <= n_unique <= MAX_CATEGORICAL_CARD:
            detected.append({"name": col, "kind": "categorical"})
    return detected
