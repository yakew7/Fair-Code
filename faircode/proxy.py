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

import math
import re

import pandas as pd

from .profiler import MAX_AGE, _age_band, _age_numbers, _is_categorical_age_sentinel, _looks_like_dates

PROXY_ALPHA = 0.05

# Chi-squared rule of thumb (#810): the approximation is unreliable when an
# expected cell count is below this, and a table is flagged `low_expected` when
# more than LOW_EXPECTED_SHARE of its cells fall under it. Mirrored in
# assets/profiler-engine.js.
LOW_EXPECTED_COUNT = 5
LOW_EXPECTED_SHARE = 0.2
PROXY_CORRECTIONS = ("bonferroni", "holm")


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
    path, _sep, rest = spec.partition("=")
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


def normalize_key_text(value):
    """Opt-in key normalisation (#859): trim, lower-case, and drop leading zeros
    from an all-digit value, so ` A1`/`a1` and `0042`/`42` match. Mirrored by
    `normalizeKeyText` in assets/profiler-engine.js."""
    text = str(value).strip().lower()
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


def parse_held_out_specs(specs, df: pd.DataFrame, read_table, *, flag="--proxy-hints-with",
                         normalize_keys=False):
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
    leading zeros (#859); both stay off by default so matching is exact.
    """
    held_out = {}
    for spec in specs or []:
        path, column, key = split_held_out_spec(spec, df.columns)
        if not path or not column or key == "" or "=" not in spec:
            raise ValueError(f"invalid {flag} '{spec}', expected PATH=COLUMN or PATH=COLUMN:KEY")
        held_df = read_table(path)
        if column not in held_df.columns:
            raise ValueError(f"{flag} column '{column}' not found in {path}")
        if column in df.columns:
            raise ValueError(
                f"{flag} column '{column}' already exists in the profiled dataset - "
                f"held-out columns must not collide with a real one")
        if column in held_out:
            raise ValueError(
                f"{flag} column '{column}' was already supplied by an earlier "
                f"{flag} spec - held-out columns must not collide with each other")
        if key is not None:
            cols = key_columns(key, df.columns)
            if cols is None:
                raise ValueError(f"{flag} join key '{key}' not found in the profiled dataset")
            if not all(c in held_df.columns for c in cols):
                raise ValueError(f"{flag} join key '{key}' not found in {path}")
            df_keys = _key_labels(df, cols, f"'{key}' in the profiled dataset", flag, normalize_keys)
            held_keys = _key_labels(held_df, cols, f"'{key}' in {path}", flag, normalize_keys)
            lookup = pd.Series(held_df[column].to_numpy(), index=held_keys.to_numpy())
            missing = ~df_keys.isin(lookup.index)
            if missing.any():
                raise ValueError(
                    f"{flag} {path} has no row for {int(missing.sum())} key(s) of the "
                    f"profiled dataset (e.g. '{df_keys[missing].iloc[0]}')")
            held_out[column] = pd.Series(lookup.loc[df_keys.to_numpy()].to_numpy(), index=df.index)
            continue
        if len(held_df) != len(df):
            raise ValueError(
                f"{flag} {path} has {len(held_df)} row(s), but the profiled "
                f"dataset has {len(df)} - rows must align 1:1 (or add a join key: "
                f"PATH=COLUMN:KEY)")
        held_out[column] = pd.Series(held_df[column].to_numpy(), index=df.index)
    return held_out


def proxy_hints(df: pd.DataFrame, dimensions: list, alpha=PROXY_ALPHA,
                held_out: dict | None = None, correction: str | None = None,
                max_age=MAX_AGE, age_reference_year=None) -> list:
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

    `correction` (None, "bonferroni" or "holm") opts in to a multiple-comparison
    adjustment across every testable pair (#806): a pair is reported only if its
    adjusted p-value is below `alpha`, and each hint then also carries
    `p_adjusted`. Default None keeps the original uncorrected behaviour.
    """
    if not 0 < alpha <= 1:
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    if correction is not None and correction not in PROXY_CORRECTIONS:
        raise ValueError(f"correction must be one of {PROXY_CORRECTIONS}, got {correction!r}")
    try:
        from scipy.stats import chi2_contingency
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
            tested.append({
                "a": name_a, "b": name_b,
                "p_value": p_value,
                "cramers_v": round(cramers_v, 4),
                "chi2": round(float(chi2), 2),
                "low_expected_share": round(low_share, 4),
                "low_expected": low_share > LOW_EXPECTED_SHARE,
            })
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
