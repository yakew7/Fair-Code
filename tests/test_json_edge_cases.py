"""Edge-case coverage for malformed/unusual JSON input on both the Python
CLI (faircode.loaders_extra.read_table) and the browser profiler engine's
parseJSON() (#169).

Run from the repo root:  pytest tests/ -q
"""

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from faircode.loaders_extra import read_table

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_js_parse(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text, encoding="utf-8")
    completed = subprocess.run(
        ["node", "scripts/parse-json-js.js", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


def _write_json(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text, encoding="utf-8")
    return path


# ── Truncated / syntactically invalid JSON ───────────────────────────────────
# Both engines used to leak their underlying parser's raw message here (a
# browser-specific SyntaxError in JS, an equally internal pandas ValueError
# in Python). Both now fail fast with a clear, consistent message.
def test_truncated_json_js_gives_clear_error(tmp_path):
    result = _run_js_parse(tmp_path, '{"a": 1, "b":')
    assert result["ok"] is False
    assert "Unsupported JSON format" in result["error"]


def test_truncated_json_python_gives_clear_error(tmp_path):
    path = _write_json(tmp_path, '{"a": 1, "b":')
    with pytest.raises(ValueError, match="Unsupported JSON format"):
        read_table(str(path))


# ── JSON array of primitives, e.g. [1, 2, 3] ─────────────────────────────────
def test_array_of_primitives_js_gives_clear_error(tmp_path):
    result = _run_js_parse(tmp_path, "[1, 2, 3]")
    assert result["ok"] is False
    assert "Unsupported JSON format" in result["error"]


def test_array_of_primitives_python_current_behavior(tmp_path):
    # pandas' read_json treats a bare array of primitives as a single-column
    # table (column "0"). This differs from the JS engine's stricter check
    # above; pinning it here documents the existing behavior rather than
    # changing it, since loosening/tightening pandas' own JSON orientation
    # handling is out of scope for this fix.
    path = _write_json(tmp_path, "[1, 2, 3]")
    df = read_table(str(path))
    assert df.to_dict(orient="list") == {0: [1, 2, 3]}


# ── Empty object {} ───────────────────────────────────────────────────────────
def test_empty_object_js_gives_clear_error(tmp_path):
    result = _run_js_parse(tmp_path, "{}")
    assert result["ok"] is False
    assert "Unsupported JSON format" in result["error"]


def test_empty_object_python_current_behavior(tmp_path):
    path = _write_json(tmp_path, "{}")
    df = read_table(str(path))
    assert df.empty


# ── Deeply-nested, non-tabular structure ─────────────────────────────────────
def test_deeply_nested_json_js_gives_clear_error(tmp_path):
    # {"a": {"b": {"c": 1}}} used to slip past the JS engine's "columns
    # orientation" check (which only verified each top-level value was a
    # plain object, not that its entries were scalars) and get silently
    # misread as one column "a" with a row "b" whose cell is {"c": 1}.
    result = _run_js_parse(tmp_path, json.dumps({"a": {"b": {"c": 1}}}))
    assert result["ok"] is False
    assert "Unsupported JSON format" in result["error"]


def test_deeply_nested_json_python_current_behavior(tmp_path):
    # pandas' read_json has no equivalent guard and happily returns a
    # DataFrame with a dict as a cell value. Pinning current behavior here;
    # not changed by this fix (see array-of-primitives note above).
    path = _write_json(tmp_path, json.dumps({"a": {"b": {"c": 1}}}))
    df = read_table(str(path))
    assert df.to_dict(orient="records") == [{"a": {"c": 1}}]


# ── Index/columns-oriented JSON ───────────────────────────────────────────────
# pandas' "columns" and "index" orientations serialize to the exact same
# dict-of-dicts shape, so there is no shape or type heuristic that reliably
# tells them apart - guessing risks silently transposing the data (see #405
# and the follow-up review on #410). read_table() now refuses to guess and
# raises a clear "ambiguous JSON orientation" error instead, pointing callers
# at orient="split", which round-trips correctly.
def test_index_oriented_json_raises_ambiguous_error(tmp_path):
    original = pd.DataFrame(
        {"sex": ["M", "F"], "age": [30, 40]},
        index=["a", "b"],
    )
    index_path = tmp_path / "index.json"
    original.to_json(index_path, orient="index")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(index_path))


def test_columns_oriented_json_raises_ambiguous_error(tmp_path):
    original = pd.DataFrame(
        {"sex": ["M", "F"], "age": [30, 40]},
        index=["a", "b"],
    )
    columns_path = tmp_path / "columns.json"
    original.to_json(columns_path, orient="columns")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(columns_path))


def test_wide_columns_oriented_json_raises_ambiguous_error(tmp_path):
    # A non-square, columns-oriented export with more columns than rows -
    # e.g. several demographic fields for a handful of records. A heuristic
    # that assumes "more rows than columns" (or vice versa) implies the
    # index dimension silently transposes exactly this shape; this must
    # raise instead of guessing wrong.
    original = pd.DataFrame(
        {
            "sex": ["M", "F", "F"],
            "race": ["A", "B", "A"],
            "region": ["N", "S", "E"],
            "income": [50000, 62000, 47000],
            "age": [30, 40, 25],
        }
    )
    assert original.shape == (3, 5)
    wide_path = tmp_path / "wide.json"
    original.to_json(wide_path, orient="columns")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(wide_path))


def test_square_all_string_index_oriented_json_raises_ambiguous_error(tmp_path):
    # A square, all-string dict-of-dicts - the normal shape for a small
    # demographic dataset - gives a type-homogeneity tie-break nothing to
    # key off, since every column is the same type. This must raise instead
    # of silently defaulting to the wrong orientation.
    original = pd.DataFrame(
        {
            "sex": ["M", "F", "M"],
            "race": ["A", "B", "A"],
            "region": ["N", "S", "E"],
        }
    )
    assert original.shape == (3, 3)
    square_path = tmp_path / "square.json"
    original.to_json(square_path, orient="index")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(square_path))


def test_non_square_index_oriented_json_raises_ambiguous_error(tmp_path):
    # More rows than columns - the shape the old "larger dimension wins"
    # heuristic happened to guess right for by coincidence. Still ambiguous
    # in principle, so this must raise rather than rely on that coincidence.
    original = pd.DataFrame(
        {"sex": ["M", "F", "M", "F", "M"]},
        index=["a", "b", "c", "d", "e"],
    )
    assert original.shape == (5, 1)
    tall_path = tmp_path / "tall.json"
    original.to_json(tall_path, orient="index")
    with pytest.raises(ValueError, match="Ambiguous JSON orientation"):
        read_table(str(tall_path))


def test_split_oriented_json_round_trips_correctly(tmp_path):
    # The one dict-of-dicts-adjacent shape that IS unambiguous, and the
    # format the ambiguous-orientation error above points users at - must
    # keep working and must not be caught by the dict-of-dicts check.
    original = pd.DataFrame(
        {"sex": ["M", "F"], "age": [30, 40]},
        index=["a", "b"],
    )
    split_path = tmp_path / "split.json"
    original.to_json(split_path, orient="split")
    loaded = read_table(str(split_path))
    pd.testing.assert_frame_equal(loaded, original)
