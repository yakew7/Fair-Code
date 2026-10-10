"""Demographic column auto-detection.

Implements section 1 of faircode/SPEC.md. Kept dependency-free (no pandas import
required for the matching logic) so the keyword lists stay the single source of
truth that the JS port mirrors verbatim.
"""

from __future__ import annotations

import json
import re
import unicodedata

# Keyword lists - order matters; the first dimension that matches wins.
# Mirror these exactly in assets/profiler-engine.js.
#
# English first, then Spanish, German, French, Portuguese (#847), Italian and
# Dutch (#856); anything else can be added per run with the `keywords` option
# (`--keywords FILE`, see normalize_keywords). Names are
# matched accent-stripped and lower-cased (see _tokens), so "género" and
# "Geschlecht" need no accented keyword.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("sex", ("sex", "gender",
             "sexo", "genero", "geschlecht", "sexe", "sesso", "geslacht")),
    ("race", ("race", "ethnic", "ethnicity",
              "raza", "etnia", "rasse", "ethnie", "raca", "razza", "etnie", "ras")),
    ("age", ("age", "dob", "yob", "birth",
             "edad", "nacimiento", "alter", "geburt", "idade", "nascimento", "naissance",
             "eta", "nascita", "leeftijd", "geboorte")),
    ("geography", ("region", "state", "zip", "zipcode", "postal", "country",
                   "county", "city", "location", "province",
                   "estado", "pais", "provincia", "ciudad", "bundesland", "land", "stadt",
                   "plz", "ville", "pays", "departement", "cidade", "regiao", "municipio",
                   "regione", "paese", "citta", "comune", "stad", "gemeente", "provincie")),
]

MAX_CATEGORICAL_CARD = 20

# Keywords whose prefix form collides with ordinary English words - "race",
# "state", "city", "region", and "country" would otherwise prefix-match
# "raceway", "statement"/"stateless", "citycenter", "regional", and
# "countryside" respectively, none of which are demographic columns. These
# stay exact-match-only regardless of length; every other 4+ char keyword
# still uses prefix matching (see _token_matches).
#
# The non-English additions follow the same rule: "genero" would prefix-match "generosity",
# "alter" "alternative", "land" "landing", and the short country/city/state words (pais, pays,
# estado, ville, stadt) and race words (raza, raca, rasse) only mean what we want as a whole token.
EXACT_ONLY_KEYWORDS = frozenset({
    "race", "state", "city", "region", "country",
    "genero", "alter", "land", "raza", "raca", "rasse", "pais", "pays", "estado", "ville",
    "stadt", "razza", "paese", "citta", "stad", "ras", "eta",
})

# Compound phrases that contain a geography stem (e.g. estado) but name a
# non-geography concept - marital status in ES/PT/IT/FR/EN. Checked as
# consecutive tokens before the per-token keyword loop so they fall through
# to generic categorical instead of geography (#855). Mirror in profiler-engine.js.
NON_GEOGRAPHY_PHRASES: tuple[tuple[str, ...], ...] = (
    ("estado", "civil"),
    ("marital", "status"),
    ("stato", "civile"),
    ("etat", "civil"),
)

# Combining diacritical marks, removed after NFD so "género" tokenizes as "genero".
# Mirror in assets/profiler-engine.js (same Unicode range).
_COMBINING_MARKS = re.compile("[\u0300-\u036f]")

# Kinds a user may force a column to via a manual override. Anything else
# (e.g. "ignore") excludes the column from analysis. Mirror in profiler-engine.js.
VALID_KINDS = ("sex", "race", "age", "geography", "categorical")


def _tokens(name: str) -> list[str]:
    """Split a column name into lower-case tokens on separators AND camelCase.

    'DateOfBirth' -> ['date','of','birth']; 'Sex_Code_Text' -> ['sex','code','text'];
    'ageGroup' -> ['age','group']. This token boundary is what stops 'age' from
    matching 'Agency_Text' or 'Language'.
    """
    stripped = _COMBINING_MARKS.sub("", unicodedata.normalize("NFD", str(name)))
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stripped)
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


KEYWORD_KINDS = ("sex", "race", "age", "geography")
_WORD = re.compile("[a-z0-9]+")


def normalize_keywords(raw):
    """Validate and normalise the user's extra detection vocabulary (#856).

    `raw` is None/empty or a dict with any of the kinds `sex`, `race`, `age`,
    `geography` mapped to a list of single words, plus an optional `exact_only`
    list of words that must match a whole token (like EXACT_ONLY_KEYWORDS). Words
    are accent-stripped and lower-cased exactly like column-name tokens, then
    de-duplicated in order. Returns the normalised dict, or None when empty.
    Raises ValueError for anything else. Mirrored by `normalizeKeywords` in
    assets/profiler-engine.js.
    """
    if raw is None or raw == {}:
        return None
    if not isinstance(raw, dict):
        raise ValueError("keywords must be an object mapping a kind to a list of words")
    allowed = KEYWORD_KINDS + ("exact_only",)
    unknown = [k for k in raw if k not in allowed]
    if unknown:
        raise ValueError(
            f"keywords has unknown key(s): {', '.join(map(str, unknown))}; allowed: {', '.join(allowed)}")
    out = {}
    for key in allowed:
        if key not in raw:
            continue
        words = raw[key]
        if not isinstance(words, list):
            raise ValueError(f"keywords.{key} must be a list of words")
        normalised = []
        for word in words:
            if not isinstance(word, str) or not word.strip():
                raise ValueError(f"keywords.{key} entries must be non-empty strings")
            text = _COMBINING_MARKS.sub("", unicodedata.normalize("NFD", word)).strip().lower()
            if not _WORD.fullmatch(text):
                raise ValueError(
                    f"keywords.{key} entry {json.dumps(word, ensure_ascii=False)} must be a single "
                    f"word of letters and digits")
            if text not in normalised:
                normalised.append(text)
        out[key] = normalised
    return out or None


def _token_matches(token: str, keyword: str, exact_only=EXACT_ONLY_KEYWORDS) -> bool:
    """Exact match for short keywords (<4 chars) and EXACT_ONLY_KEYWORDS;
    prefix match for other keywords of 4+ chars.

    Prefix (not substring) avoids 'age' matching 'agency' while still catching
    'statecode', 'ethnicity', etc. EXACT_ONLY_KEYWORDS carves out the stems
    whose prefix form collides with ordinary English words instead ('race'
    matching 'raceway', 'state' matching 'statement').
    """
    if len(keyword) < 4 or keyword in exact_only:
        return token == keyword
    return token.startswith(keyword)


def _has_consecutive_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    """True when `phrase` appears as consecutive tokens in `tokens`."""
    n = len(phrase)
    if n == 0 or len(tokens) < n:
        return False
    for i in range(len(tokens) - n + 1):
        if tuple(tokens[i : i + n]) == phrase:
            return True
    return False


def classify_name(name: str, keywords=None) -> str | None:
    """Return the dimension kind for a column name, or None if no keyword matches.

    `keywords` is an optional extra vocabulary (see normalize_keywords) searched
    after the built-in words of each kind."""
    keywords = normalize_keywords(keywords)
    extra = keywords or {}
    exact_only = EXACT_ONLY_KEYWORDS | frozenset(extra.get("exact_only", ()))
    tokens = _tokens(name)
    # Marital-status compounds before per-token match (#855).
    if any(_has_consecutive_phrase(tokens, phrase) for phrase in NON_GEOGRAPHY_PHRASES):
        return None
    for kind, words in KEYWORDS:
        words = tuple(words) + tuple(extra.get(kind, ()))
        if any(_token_matches(tok, word, exact_only) for tok in tokens for word in words):
            return kind
    return None


def detect_columns(df, overrides=None, max_categorical_card: int = MAX_CATEGORICAL_CARD,
                   keywords=None) -> list[dict]:
    """Detect demographic columns in a DataFrame.

    Returns a list of {"name": str, "kind": str} dicts. Keyword-matched columns
    are always kept; unmatched columns are kept as generic "categorical" only
    when their distinct non-null value count is in [2, max_categorical_card].

    `overrides` is an optional {column: kind} map that wins over auto-detection:
    a kind in VALID_KINDS forces that column to that dimension (regardless of its
    name); any other value (e.g. "ignore") drops the column from analysis.

    `max_categorical_card` raises or lowers the generic-categorical cardinality
    ceiling (SPEC section 7); defaults to MAX_CATEGORICAL_CARD.

    `keywords` adds user vocabulary to the built-in lists (#856).
    """
    keywords = normalize_keywords(keywords)
    overrides = overrides or {}
    detected: list[dict] = []
    for col in df.columns:
        if col in overrides:
            kind = overrides[col]
            if kind in VALID_KINDS:
                detected.append({"name": col, "kind": kind})
            # any other override value (e.g. "ignore") excludes the column
            continue
        kind = classify_name(col, keywords)
        if kind is not None:
            detected.append({"name": col, "kind": kind})
            continue
        # Generic categorical fallback for low-cardinality columns.
        series = df[col].dropna()
        try:
            n_unique = series.nunique()
        except TypeError:
            # Columns containing unhashable objects (e.g. dicts or lists)
            # cannot form categorical groups (#844).
            continue
        if 2 <= n_unique <= max_categorical_card:
            detected.append({"name": col, "kind": "categorical"})
    return detected
