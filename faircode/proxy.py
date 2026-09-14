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

import pandas as pd

from .profiler import _age_band, _age_to_numeric, _is_categorical_age_sentinel, _looks_like_dates

PROXY_ALPHA = 0.05


def _labelize(df, name, kind):
    """Same value normalization the intersection crosstab uses (age → bands)."""
    if kind == "age" and not _looks_like_dates(df[name]):
        nums = [_age_to_numeric(v) for v in df[name]]
        if any(n is not None for n in nums):
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


def parse_held_out_specs(specs, df: pd.DataFrame, read_table, *, flag="--proxy-hints-with"):
    """Parse repeated PATH=COLUMN specs into a {column: pandas.Series} map
    aligned to `df`'s index, for proxy_hints()'s `held_out` param. Shared by
    the CLI's `--proxy-hints-with` and the MCP `proxy_hints` tool's
    `held_out_with`, so both get the same parse/column/row-count validation
    without re-implementing it. Raises ValueError on any parse failure or
    row-count mismatch; `read_table` is injected so a bad path's own failure
    (missing file, unreadable format) surfaces however the caller's `read_table`
    reports it - this function never prints or exits, only raises. `flag`
    names the caller's own flag/parameter in error messages.
    """
    held_out = {}
    for spec in specs or []:
        path, sep, column = spec.partition("=")
        if not sep or not path or not column:
            raise ValueError(f"invalid {flag} '{spec}', expected PATH=COLUMN")
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
        if len(held_df) != len(df):
            raise ValueError(
                f"{flag} {path} has {len(held_df)} row(s), but the profiled "
                f"dataset has {len(df)} - rows must align 1:1")
        held_out[column] = pd.Series(held_df[column].to_numpy(), index=df.index)
    return held_out


def proxy_hints(df: pd.DataFrame, dimensions: list, alpha=PROXY_ALPHA,
                held_out: dict | None = None) -> list:
    """Chi-squared test of independence over every pair of detected dimensions.

    Returns pairs with p < alpha, most-significant first, each with its p-value
    and Cramér's V effect size. Raises RuntimeError if scipy is unavailable.

    `held_out` is an optional {column_name: pandas.Series} map for testing
    against a protected attribute that has already been dropped from `df` -
    "we dropped the column so it's fine" is the exact failure mode this
    catches: without it, a dropped column can never be one half of a tested
    pair, since it never appears in `dimensions`. Each series must share
    `df`'s index (same rows, same order); pass the original, pre-drop values.
    Held-out columns are compared to every detected dimension and to each
    other, treated as plain categorical values (no age-band normalization,
    since there's no detected `kind` for a column that was never profiled).
    """
    try:
        from scipy.stats import chi2_contingency
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "proxy hints need scipy (install with: pip install faircode[proxy])"
        ) from exc

    labelized = {d["name"]: _labelize(df, d["name"], d["kind"]) for d in dimensions}
    for name, series in (held_out or {}).items():
        labelized[name] = series.astype("object")

    names = list(labelized)
    hints = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            ct = pd.crosstab(labelized[name_a], labelized[name_b])
            if ct.shape[0] < 2 or ct.shape[1] < 2:
                continue
            chi2, p_value, _dof, _exp = chi2_contingency(ct)
            n = int(ct.to_numpy().sum())
            k = min(ct.shape) - 1
            cramers_v = math.sqrt(chi2 / (n * k)) if n and k else 0.0
            if p_value < alpha:
                hints.append({
                    "a": name_a, "b": name_b,
                    "p_value": p_value,
                    "cramers_v": round(cramers_v, 4),
                    "chi2": round(float(chi2), 2),
                })
    hints.sort(key=lambda h: h["p_value"])
    return hints
