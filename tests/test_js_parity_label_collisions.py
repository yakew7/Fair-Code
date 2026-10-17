"""Warnings for literal group labels that differ only in case or spacing."""

import html
import json
import subprocess

import pandas as pd
import pytest

from faircode import profile
from faircode.report import to_csv, to_html, to_terminal
from js_helpers import REPO_ROOT, _run_ui_exports


def _profile_both(df):
    script = (
        "require(process.argv[1]);var E=globalThis.FairCodeProfiler;"
        "process.stdout.write(JSON.stringify(E.profile(JSON.parse(process.argv[2]))));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"),
         json.dumps({"columns": list(df.columns), "rows": json.loads(df.to_json(orient="records"))})],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    result = profile(df)
    assert json.loads(completed.stdout) == result
    return result


@pytest.mark.parametrize("column", ["sex", "race", "region", "segment", "age"])
@pytest.mark.parametrize("labels", [
    ("M", "m"),
    ("m", " m "),
    ("M", "\t m\u00a0"),
    ("M", "\u0085m\u3000"),
    ("M", "\ufeffm\ufeff"),
    ("Stra\u00dfe", "STRASSE"),
    ("\u03c3", "\u03c2"),
    ("\ufb03", "FFI"),
    ("__proto__", "__PROTO__"),
    ("constructor", "CONSTRUCTOR"),
    ("toString", "TOSTRING"),
])
def test_collisions_warn_without_merging_groups(column, labels):
    first, second = labels
    result = _profile_both(pd.DataFrame({column: [first] * 3 + [second] * 2 + [None]}))
    warning = f"{column}: '{first}' and '{second}' differ only in case or spacing"
    assert result["flags"].count(warning) == 1
    dim = result["dimensions"][0]
    assert dim["n_groups"] == 2
    assert [(g["label"], g["count"], g["share"], g["small_group"]) for g in dim["groups"]] == [
        (first, 3, 0.6, True), (second, 2, 0.4, True),
    ]
    assert dim["missing_pct"] == pytest.approx(1 / 6, abs=0.0001)
    assert dim["imbalance_ratio"] == 1.5
    assert dim["dimension_score"] == result["overall_score"] == 97


@pytest.mark.parametrize("labels", [
    ["M", "F"],
    ["M", "M"],
    ["M", "M", None],
    [None, None],
    ["01", "1", "1.0"],
    ["\uff21", "A"],
    ["e", "\u00e9"],
    ["a b", "ab"],
])
def test_distinct_or_identical_labels_do_not_warn(labels):
    result = _profile_both(pd.DataFrame({"sex": labels}))
    assert not any("differ only in case or spacing" in f for f in result["flags"])


def test_collision_warnings_are_per_dimension_and_not_repeated_per_row():
    result = _profile_both(pd.DataFrame({
        "sex": ["M"] * 30 + ["m"] * 20 + [" m "] * 10,
        "race": ["M"] * 60,
    }))
    assert [f for f in result["flags"] if "differ only in case or spacing" in f] == [
        "sex: 'M' and 'm' differ only in case or spacing",
        "sex: 'M' and ' m ' differ only in case or spacing",
    ]


def test_collision_warning_reaches_reports_in_both_engines(tmp_path):
    df = pd.DataFrame({"sex": ["M"] * 15 + ["m"] * 15})
    path = tmp_path / "labels.csv"
    df.to_csv(path, index=False)
    result = _profile_both(df)
    warning = "sex: 'M' and 'm' differ only in case or spacing"
    assert warning in to_terminal(result)
    assert warning in html.unescape(to_html(result))
    assert warning in to_csv(result)
    web = _run_ui_exports(path, False)
    assert warning in html.unescape(web["html"])
    assert web["csv"].replace("\r\n", "\n") == to_csv(result).replace("\r\n", "\n")
