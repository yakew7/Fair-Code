"""Chi-squared proxy hints (informational; CLI/Python only).

Flags pairs of detected demographic columns that are strongly associated - a
"this column may be a proxy for that protected attribute" signal, the same
chi-squared pattern the bias audits use. Requires the optional scipy extra
(`pip install faircode[proxy]`).

This is intentionally NOT part of profile() or the JS engine: it is an opt-in
add-on that never affects the representation score, so the two engines stay
bit-for-bit identical. The result is attached to the profile under
`proxy_hints` by the CLI when `--proxy-hints` is passed.
"""

from __future__ import annotations

import codecs
import math
import re
import unicodedata
from pathlib import Path

import pandas as pd

from .profiler import KEY_TRIM_CHARS, MAX_AGE, _age_band, _age_numbers, _is_categorical_age_sentinel, _looks_like_dates

PROXY_ALPHA = 0.05

# Chi-squared rule of thumb (#810): the approximation is unreliable when an
# expected cell count is below this, and a table is flagged `low_expected` when
# more than LOW_EXPECTED_SHARE of its cells fall under it. Mirrored in
# assets/profiler-engine.js.
LOW_EXPECTED_COUNT = 5
LOW_EXPECTED_SHARE = 0.2
PROXY_CORRECTIONS = ("bonferroni", "holm")


# Exact-test fallback for small-cell tables (#861). A 2x2 table gets Fisher's exact
# test; a larger one gets a seeded Monte-Carlo permutation estimate of the
# chi-squared statistic, capped at PERMUTATION_MAX_ROWS observations so it stays
# fast. Mirrored (including the PRNG) in assets/profiler-engine.js.
PERMUTATIONS = 1000
PERMUTATION_SEED = 42
# A typo such as 10**12 shuffles would run for days, so more than this is refused (#926).
MAX_PERMUTATIONS = 1_000_000
# A held-out column is "near-unique" (looks like an identifier) when its distinct values exceed
# --max-categorical-card and are at least this share of its non-null rows. Same value in
# profiler-engine.js (#957).
NEAR_UNIQUE_SHARE = 0.5
# Measured after #886: about 0.1 s per 1000 rows per pair in Python (0.07 s in JS), so 20000 rows keeps a
# pair near two seconds (#909). Same value in profiler-engine.js.
PERMUTATION_MAX_ROWS = 20000
_MASK32 = 0xFFFFFFFF


def _mulberry32_block(seed, start, count):
    """`count` consecutive mulberry32 floats starting after `start` draws, as a
    numpy array. The state is just `seed + k * 0x6D2B79F5`, so a whole block is
    computed at once (uint32 arithmetic wraps exactly like the masked scalar
    version), giving the identical stream to the scalar reference implementation kept in
    tests/test_proxy.py (`scalar_mulberry32`), which is the oracle this block
    version is checked against (#886, #927)."""
    import numpy as np
    k = np.arange(start + 1, start + count + 1, dtype=np.uint64)
    state = ((np.uint64(seed & _MASK32) + k * np.uint64(0x6D2B79F5)) & np.uint64(_MASK32)).astype(np.uint32)
    t = (state ^ (state >> np.uint32(15))) * (np.uint32(1) | state)
    t = (t + (((t ^ (t >> np.uint32(7))) * (np.uint32(61) | t)))) ^ t
    return (t ^ (t >> np.uint32(14))).astype(np.float64) / 4294967296


def permutation_p_value(row_idx, col_idx, n_rows, n_cols, permutations=PERMUTATIONS,
                        seed=PERMUTATION_SEED):
    """Monte-Carlo p-value for independence: shuffle the column labels with a
    seeded Fisher-Yates, recompute the plain chi-squared statistic each time, and
    return (1 + #{stat >= observed}) / (permutations + 1).

    The statistic is `sum(o^2 / e) - n` over the occupied cells only (an empty
    cell contributes exactly its expected count, and those sum to n), so a sparse
    table costs O(rows) per shuffle instead of O(cells) (#886). Same formula in
    assets/profiler-engine.js."""
    import numpy as np
    n = len(row_idx)
    rows = np.asarray(row_idx, dtype=np.int64)
    row_tot = np.bincount(rows, minlength=n_rows)
    col_tot = np.bincount(np.asarray(col_idx, dtype=np.int64), minlength=n_cols)

    def statistic(cols):
        cells, counts = np.unique(rows * n_cols + cols, return_counts=True)
        expected = row_tot[cells // n_cols] * col_tot[cells % n_cols] / n
        return float((counts.astype(np.float64) ** 2 / expected).sum() - n)

    cols = list(col_idx)
    observed = statistic(np.asarray(cols, dtype=np.int64))
    hits = 0
    steps = max(n - 1, 0)
    for b in range(permutations):
        js = (_mulberry32_block(seed, b * steps, steps) * np.arange(n, 1, -1)).astype(np.int64).tolist()
        i = n - 1
        for j in js:
            cols[i], cols[j] = cols[j], cols[i]
            i -= 1
        if statistic(np.asarray(cols, dtype=np.int64)) >= observed - 1e-9:
            hits += 1
    return (1 + hits) / (permutations + 1)


def adjust_p_values(p_values, method):
    """Family-wise error correction over every tested pair (#806).

    bonferroni: min(1, p * m). holm: the step-down procedure - sort ascending,
    multiply the i-th smallest (0-based) by (m - i), then take a running max so
    adjusted values never decrease, capped at 1. Returned in input order.
    """
    m = len(p_values)
    if method == "bonferroni":
        return [min(1.0, p * m) for p in p_values]
    if method == "holm":
        order = sorted(range(m), key=lambda i: p_values[i])
        adjusted = [0.0] * m
        running = 0.0
        for rank, i in enumerate(order):
            running = max(running, min(1.0, p_values[i] * (m - rank)))
            adjusted[i] = running
        return adjusted
    raise ValueError(f"correction must be one of {PROXY_CORRECTIONS}, got {method!r}")


def _labelize(df, name, kind, max_age=MAX_AGE, age_reference_year=None):
    """Same value normalization the intersection crosstab uses (age → bands)."""
    if kind == "age" and not _looks_like_dates(df[name]):
        nums, implausible, *_ = _age_numbers(df[name], max_age, age_reference_year)
        if implausible or any(n is not None for n in nums):
            # Non-numeric age sentinels ("unknown", "prefer not to say") get
            # their own categorical label here too, matching _dimension()'s
            # main breakdown and _intersections()'s labelize() - otherwise a
            # sentinel maps to None and pd.crosstab silently drops those rows
            # from the chi-squared test (#614, the same bug already fixed
            # for _intersections() as #524).
            labels = [
                _age_band(num) if num is not None
                else (str(value) if _is_categorical_age_sentinel(value) else None)
                for value, num in zip(df[name], nums)
            ]
            return pd.Series(labels, index=df.index)
    return df[name].astype("object")


def _rpartition_unescaped_colon(text):
    """Split on the last colon not preceded by an odd run of backslashes.

    Returns (before, after). after is None when no unescaped colon is present.
    """
    i = len(text) - 1
    while i >= 0:
        if text[i] == ":":
            n = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                n += 1
                j -= 1
            if n % 2 == 0:
                return text[:i], text[i + 1:]
        i -= 1
    return text, None


def _unescape_colons(text):
    """Turn backslash-escaped colons into literal colons (#869)."""
    return text.replace(r"\:", ":")


def partition_held_out_path(spec):
    """Split a held-out spec at its first *unescaped* `=` into (path, sep, rest).

    A backslash before an equals sign makes it a literal part of the path, so
    `data\\=v2.csv=race` is the file `data=v2.csv` and column `race` (#958); the
    returned path has those escapes removed. `sep` is "" when there is no
    unescaped `=`, and then `rest` is "".
    """
    i = 0
    while i < len(spec):
        if spec[i] == "\\" and spec.startswith("=", i + 1):
            i += 2
            continue
        if spec[i] == "=":
            return spec[:i].replace("\\=", "="), "=", spec[i + 1:]
        i += 1
    return spec.replace("\\=", "="), "", ""


def split_held_out_spec(spec, profiled_columns=None):
    """Split "PATH=COLUMN" or "PATH=COLUMN:KEY" into (path, column, key).

    `key` is None for the plain form. The optional `:KEY` names a join column
    present in both the profiled dataset and the held-out file (#822). A
    backslash before a colon makes that colon literal (#869), so PATH=a\\:b
    is column a:b with no key. When `profiled_columns` is given, a trailing
    `:KEY` is only treated as a join key if KEY names a column of the profiled
    dataset; otherwise the whole right-hand side is the column name (so
    `PATH=a:b` works when `b` is not a profiled column). Missing pieces come
    back as empty strings for the caller to reject.
    """
    path, _sep, rest = partition_held_out_path(spec)
    before, after = _rpartition_unescaped_colon(rest)
    if after is None:
        return path, _unescape_colons(rest), None
    column = _unescape_colons(before)
    key = _unescape_colons(after)
    if key == "":
        return path, column, ""
    if profiled_columns is not None and key_columns(key, profiled_columns) is None:
        return path, _unescape_colons(rest), None
    return path, column, key


def split_held_out_encoding(spec):
    """Split an optional ``@ENCODING`` suffix from a held-out file spec.

    The suffix lives on the right-hand side of ``PATH=...``, so ``@`` remains
    valid in the path itself. The encoding is validated through Python's codec
    registry here, before any file is read, and the caller receives the spec
    without the suffix plus the original encoding name.
    """
    path, sep, rest = partition_held_out_path(spec)
    if not sep or "@" not in rest:
        return spec, None
    value, _at, encoding = rest.rpartition("@")   # "@" is in `rest`, so _at is always "@"
    if not encoding:
        raise ValueError(f"invalid held-out encoding in '{spec}': expected @ENCODING")
    try:
        codecs.lookup(encoding)
    except LookupError:
        raise ValueError(f"unknown held-out encoding '{encoding}' in '{spec}'") from None
    raw_path = spec[:len(spec) - len(rest) - 1]   # keep any \\= escapes for the next split
    return f"{raw_path}={value}", encoding


def strip_key_normalize_marker(spec, profiled_columns=None):
    """Split a trailing `~` off "PATH=COLUMN:KEY~" and return (spec, marked).

    The marker turns on `--proxy-key-normalize` for that one spec (#892), so the
    CLI can express what the web's per-row "Normalise key" checkbox does. It only
    counts on a spec that has a join key, so a column that happens to end in `~`
    in a key-less spec is left alone.
    """
    if spec.endswith("~") and not spec.endswith("\\~"):
        stripped = spec[:-1]
        if split_held_out_spec(stripped, profiled_columns)[2]:
            return stripped, True
    return spec, False


def resolve_key_marker(spec, profiled_columns=None, default=False):
    """Return (spec_without_marker, normalise) for one held-out spec: a trailing `~`
    forces key normalisation on, a trailing `!` forces exact matching (#907), and a
    spec with neither follows `default` (the global --proxy-key-normalize)."""
    stripped, marked = strip_key_normalize_marker(spec, profiled_columns)
    if marked:
        return stripped, True
    if spec.endswith("!") and not spec.endswith("\\!"):
        bare = spec[:-1]
        if split_held_out_spec(bare, profiled_columns)[2]:
            return bare, False
    return spec, default


def key_columns(key, columns):
    """The column names a join key refers to: `[key]` when it is itself a column,
    else the `+`-separated parts of a composite key (`id+visit`) when every part is
    one, else None (#859)."""
    if key in columns:
        return [key]
    parts = key.split("+")
    if len(parts) > 1 and all(part and part in columns for part in parts):
        return parts
    return None


_DIGITS_ONLY = re.compile(r"[0-9]+")
_WHOLE_FLOAT = re.compile(r"([0-9]+)\.0+")


def normalize_key_text(value):
    """Opt-in key normalisation (#859, #884): trim, apply Unicode compatibility composition (NFKC, so full-width `４２`/`Ａ１` equal `42`/`a1`, #935),
    case-fold (so `ß` equals `ss`), drop a whole-number fraction (`42.0`), and drop leading zeros from an all-digit
    value, so ` A1`/`a1`, `0042`/`42`, `e` + U+0301 / `é` and `Straße`/`STRASSE`
    match. Mirrored by `normalizeKeyText` in assets/profiler-engine.js."""
    text = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", str(value).strip(KEY_TRIM_CHARS)).casefold())
    whole = _WHOLE_FLOAT.fullmatch(text)   # a spreadsheet's 42.0 is the key 42 (#903)
    if whole:
        text = whole.group(1)
    if _DIGITS_ONLY.fullmatch(text):
        text = text.lstrip("0") or "0"
    return text


def _key_labels(frame, cols, what, flag, normalize=False):
    """Join-key values as strings (composite keys joined on U+001F), rejecting
    nulls and duplicates (#822, #859)."""
    if frame[cols].isna().any().any():
        raise ValueError(f"{flag} join key {what} has empty values - keys must all be present")
    texts = frame[cols].astype(str)
    if normalize:
        texts = texts.apply(lambda col: col.map(normalize_key_text))
    labels = texts.iloc[:, 0] if len(cols) == 1 else texts.agg("\x1f".join, axis=1)
    if labels.duplicated().any():
        dup = labels[labels.duplicated()].iloc[0]
        raise ValueError(f"{flag} join key {what} has duplicate values (e.g. '{dup}') - "
                         f"keys must be unique")
    return labels


def near_unique_note(name, distinct, max_categorical_card):
    """The note for a held-out column skipped as an identifier (#908)."""
    return (f"held-out column '{name}' has {distinct} distinct values (more than "
            f"{max_categorical_card} and nearly one per row) - it looks like an identifier, "
            f"not a group, so it was not tested")


# ASCII-only so a column written in Arabic-Indic or full-width digits is judged the same as in the
# web engine, where \d is 0-9 only (#967).
_NUMBER = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?\Z", re.ASCII)


def _all_numeric(series):
    return all(
        (isinstance(v, (int, float)) and not isinstance(v, bool)) or bool(_NUMBER.fullmatch(str(v)))
        for v in series.dropna().tolist()
    )


def _keep_held_out(held_out, column, series, notes, max_categorical_card, skipped=None):
    """Store a held-out column unless it is near-unique (more distinct values than
    `max_categorical_card` and at least NEAR_UNIQUE_SHARE (half) of the non-null rows): testing an ID-like or
    free-text column builds a huge contingency table and means nothing. An all-numeric
    column is exempt - a raw age is a legitimate held-out attribute (#937). Only screened when
    the caller passes a `notes` list to receive the skip message (#908)."""
    if notes is not None:
        distinct, present = int(series.nunique(dropna=True)), int(series.notna().sum())
        if distinct > max_categorical_card and distinct >= NEAR_UNIQUE_SHARE * present and not _all_numeric(series):
            notes.append(near_unique_note(column, distinct, max_categorical_card))
            if skipped is not None:
                skipped.append(column)
            return
    held_out[column] = series


def parse_held_out_specs(specs, df: pd.DataFrame, read_table, *, flag="--proxy-hints-with",
                         normalize_keys=False, notes=None, max_categorical_card=20, skipped=None):
    """Parse repeated PATH=COLUMN[:KEY] specs into a {column: pandas.Series} map
    aligned to `df`'s index, for proxy_hints()'s `held_out` param. Shared by
    the CLI's `--proxy-hints-with` and the MCP `proxy_hints` tool's
    `held_out_with`, so both get the same parse/column/row-count validation
    without re-implementing it. Raises ValueError on any parse failure or
    row-count mismatch; `read_table` is injected so a bad path's own failure
    (missing file, unreadable format) surfaces however the caller's `read_table`
    reports it - this function never prints or exits, only raises. `flag`
    names the caller's own flag/parameter in error messages.

    Without `:KEY` the file must align with `df` 1:1 by row position. With it,
    rows are matched on that column instead (#822): the key must exist in both
    files, be unique and non-empty in both, and every key in `df` must be in the
    held-out file (extra held-out rows are ignored), so a re-sorted or filtered
    export still lines up. The key may be composite (`PATH=COLUMN:id+visit`), and
    `normalize_keys` makes the comparison tolerant of case, surrounding spaces and
    leading zeros (#859); both stay off by default so matching is exact. A spec
    ending in `~` (`PATH=COLUMN:KEY~`) normalises just that spec's key (#892) and one
    ending in `!` keeps just that spec exact even when `normalize_keys` is on (#907).
    An optional `@ENCODING` suffix overrides the caller's shared encoding for
    that file; it composes with the marker as `PATH=COLUMN:KEY~@ENCODING`.
    With a `notes` list, a near-unique held-out column (see `_keep_held_out`) is left out
    and a message appended instead of being tested (#908); its name is also appended to
    `skipped` when that list is given, so provenance can say it was not tested (#921).
    """
    held_out = {}
    seen_columns = set()   # kept or skipped: a column named twice is an error either way (#980)
    for original_spec in specs or []:
        spec, spec_encoding = split_held_out_encoding(original_spec)
        spec, normalize = resolve_key_marker(spec, df.columns, normalize_keys)
        path, column, key = split_held_out_spec(spec, df.columns)
        if not path or not column or key == "" or not partition_held_out_path(spec)[1]:
            raise ValueError(f"invalid {flag} '{spec}', expected PATH=COLUMN or PATH=COLUMN:KEY")
        _, _sep, after_path = partition_held_out_path(spec)
        if "=" in after_path and not Path(path).exists():
            guess = path + "=" + after_path.partition("=")[0]
            if Path(guess).exists():   # a file name containing "=" split at its first one (#958)
                raise ValueError(
                    f"{flag} file '{path}' does not exist but '{guess}' does - write the = inside the "
                    f"file name as \\= (for example {guess.replace('=', chr(92) + '=')}=COLUMN)")
        held_df = read_table(path, encoding=spec_encoding) if spec_encoding else read_table(path)
        if column not in held_df.columns:
            raise ValueError(f"{flag} column '{column}' not found in {path}")
        if column in df.columns:
            raise ValueError(
                f"{flag} column '{column}' already exists in the profiled dataset - "
                f"held-out columns must not collide with a real one")
        if column in seen_columns:
            raise ValueError(
                f"{flag} column '{column}' was already supplied by an earlier "
                f"{flag} spec - held-out columns must not collide with each other")
        seen_columns.add(column)
        if key is not None:
            # split_held_out_spec only returns a key that names profiled column(s), so this
            # resolves; an unknown key makes the whole right-hand side the column name (#869).
            cols = key_columns(key, df.columns)
            if not all(c in held_df.columns for c in cols):
                raise ValueError(f"{flag} join key '{key}' not found in {path}")
            df_keys = _key_labels(df, cols, f"'{key}' in the profiled dataset", flag, normalize)
            held_keys = _key_labels(held_df, cols, f"'{key}' in {path}", flag, normalize)
            lookup = pd.Series(held_df[column].to_numpy(), index=held_keys.to_numpy())
            missing = ~df_keys.isin(lookup.index)
            if missing.any():
                raise ValueError(
                    f"{flag} {path} has no row for {int(missing.sum())} key(s) of the "
                    f"profiled dataset (e.g. '{df_keys[missing].iloc[0]}')")
            _keep_held_out(held_out, column, pd.Series(lookup.loc[df_keys.to_numpy()].to_numpy(), index=df.index),
                           notes, max_categorical_card, skipped)
            continue
        if len(held_df) != len(df):
            raise ValueError(
                f"{flag} {path} has {len(held_df)} row(s), but the profiled "
                f"dataset has {len(df)} - rows must align 1:1 (or add a join key: "
                f"PATH=COLUMN:KEY)")
        _keep_held_out(held_out, column, pd.Series(held_df[column].to_numpy(), index=df.index),
                       notes, max_categorical_card, skipped)
    return held_out


def proxy_hints(df: pd.DataFrame, dimensions: list, alpha=PROXY_ALPHA,
                held_out: dict | None = None, correction: str | None = None,
                max_age=MAX_AGE, age_reference_year=None, exact=False,
                permutations=PERMUTATIONS, max_rows=PERMUTATION_MAX_ROWS) -> list:
    """Chi-squared test of independence over every pair of detected dimensions.

    Returns pairs with p < alpha, most-significant first, each with its p-value
    and Cramér's V effect size. Raises RuntimeError if scipy is unavailable.

    Each hint also carries `low_expected_share` (the share of contingency cells
    whose expected count is under 5) and `low_expected` (true when that share
    exceeds 20%): the chi-squared p-value is unreliable for such a table - a
    high-cardinality categorical or a rare group - so treat it as a lead, not
    a finding (#810).

    Each hint also carries `n_tests`, the number of pairs actually tested (pairs
    with a constant column are skipped and do not count): the `m` a reader needs
    to re-derive `p_adjusted` (Bonferroni is `min(1, p * n_tests)`, #821).

    `held_out` is an optional {column_name: pandas.Series} map for testing
    against a protected attribute that has already been dropped from `df` -
    "we dropped the column so it's fine" is the exact failure mode this
    catches: without it, a dropped column can never be one half of a tested
    pair, since it never appears in `dimensions`. Each series must share
    `df`'s index (same rows, same order); pass the original, pre-drop values.
    Held-out columns are compared to every detected dimension and to each
    other, treated as plain categorical values (no age-band normalization,
    since there's no detected `kind` for a column that was never profiled).

    `exact` (default False) opts in to an exact-test fallback for `low_expected`
    tables (#861): a 2x2 table's `p_value` becomes Fisher's exact p, a larger one's
    a seeded permutation estimate (tables over `max_rows` (20000) observations keep the
    chi-squared p). Every hint then carries `p_method` ("chi2", "fisher" or
    "permutation"); a replaced p-value keeps the original as `p_chi2`.
    `permutations` (default 1000) is the number of shuffles and `max_rows` the
    observation count above which a small-cell table keeps the chi-squared p
    (labelled "chi2-capped"); both are positive integers and `permutations` is at most 1,000,000 (#906, #926).

    `correction` (None, "bonferroni" or "holm") opts in to a multiple-comparison
    adjustment across every testable pair (#806): a pair is reported only if its
    adjusted p-value is below `alpha`, and each hint then also carries
    `p_adjusted`. Default None keeps the original uncorrected behaviour.
    """
    if not 0 < alpha <= 1:
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    if correction is not None and correction not in PROXY_CORRECTIONS:
        raise ValueError(f"correction must be one of {PROXY_CORRECTIONS}, got {correction!r}")
    for name, value in (("permutations", permutations), ("max_rows", max_rows)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")
    if permutations > MAX_PERMUTATIONS:
        raise ValueError(f"permutations must be at most {MAX_PERMUTATIONS:,}, got {permutations:,}")
    try:
        from scipy.stats import chi2_contingency, fisher_exact
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "proxy hints need scipy (install with: pip install faircode[proxy])"
        ) from exc

    labelized = {d["name"]: _labelize(df, d["name"], d["kind"], max_age, age_reference_year) for d in dimensions}
    for name, series in (held_out or {}).items():
        labelized[name] = series.astype("object")

    names = list(labelized)
    tested = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            ct = pd.crosstab(labelized[name_a], labelized[name_b])
            if ct.shape[0] < 2 or ct.shape[1] < 2:
                continue
            chi2, p_value, _dof, expected = chi2_contingency(ct)
            low_share = float((expected < LOW_EXPECTED_COUNT).mean())
            n = int(ct.to_numpy().sum())
            k = min(ct.shape) - 1
            cramers_v = math.sqrt(chi2 / (n * k)) if n and k else 0.0
            hint = {
                "a": name_a, "b": name_b,
                "p_value": p_value,
                "cramers_v": round(cramers_v, 4),
                "chi2": round(float(chi2), 2),
                "low_expected_share": round(low_share, 4),
                "low_expected": low_share > LOW_EXPECTED_SHARE,
            }
            if exact:
                hint["p_method"] = "chi2"
                if hint["low_expected"]:
                    if ct.shape == (2, 2):
                        hint["p_chi2"], hint["p_value"] = float(p_value), float(fisher_exact(ct.to_numpy())[1])
                        hint["p_method"] = "fisher"
                    elif n <= max_rows:
                        keep = labelized[name_a].notna().to_numpy() & labelized[name_b].notna().to_numpy()
                        row_idx = pd.factorize(labelized[name_a][keep])[0].tolist()
                        col_idx = pd.factorize(labelized[name_b][keep])[0].tolist()
                        hint["p_chi2"] = float(p_value)
                        hint["p_value"] = permutation_p_value(row_idx, col_idx, ct.shape[0], ct.shape[1], permutations)
                        hint["p_method"] = "permutation"
                    else:
                        # Too large for the permutation fallback: keep the chi-squared
                        # p-value but say why it was not replaced (#885).
                        hint["p_method"] = "chi2-capped"
            tested.append(hint)
    for h in tested:
        h["n_tests"] = len(tested)
    if correction is None:
        hints = [h for h in tested if h["p_value"] < alpha]
    else:
        adjusted = adjust_p_values([h["p_value"] for h in tested], correction)
        hints = []
        for h, p_adj in zip(tested, adjusted):
            if p_adj < alpha:
                hints.append(dict(h, p_adjusted=p_adj))
    hints.sort(key=lambda h: h["p_value"])
    return hints
