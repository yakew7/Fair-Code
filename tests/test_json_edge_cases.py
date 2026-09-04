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


# ── Index-oriented JSON ──────────────────────────────────────────────────────
def test_index_oriented_json_preserves_dataframe_shape(tmp_path):
    original = pd.DataFrame(
        {"sex": ["M", "F"], "age": [30, 40]},
        index=["a", "b"],
    )

    index_path = tmp_path / "index.json"
    original.to_json(index_path, orient="index")
    loaded_index = read_table(str(index_path))
    pd.testing.assert_frame_equal(loaded_index, original)

    # Ensure columns-oriented dict-of-dicts with a non-default index isn't
    # misclassified as index-oriented and transposed.
    columns_path = tmp_path / "columns.json"
    original.to_json(columns_path, orient="columns")
    loaded_columns = read_table(str(columns_path))
    pd.testing.assert_frame_equal(loaded_columns, original)