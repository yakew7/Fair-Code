"""Parity tests between the Python and JavaScript profiler implementations."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from faircode import compare, profile

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

requires_openpyxl = pytest.mark.skipif(
    importlib.util.find_spec("openpyxl") is None,
    reason="optional 'excel' extra not installed",
)


def _extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    assert match, f"Could not find {pattern!r}"
    return match.group(1)


def test_sheetjs_cdn_url_matches():
    engine = (REPO_ROOT / "assets" / "profiler-engine.js").read_text(encoding="utf-8")
    cli = (REPO_ROOT / "scripts" / "engine-js.js").read_text(encoding="utf-8")

    engine_url = _extract(r'script\.src\s*=\s*"([^"]+)"', engine)
    cli_url = _extract(r'XLSX_CDN_URL\s*=\s*"([^"]+)"', cli)

    assert engine_url == cli_url


# Real audit datasets are already tracked in their own audit folders - reuse
# them instead of keeping a second multi-megabyte copy under tests/fixtures.
CSV_PATHS = {
    "small.csv": FIXTURES / "small.csv",
    "adult.csv": REPO_ROOT / "Benefits Denial" / "adult.csv",
    "compas-scores-raw.csv": REPO_ROOT / "COMPAS" / "compas-scores-raw.csv",
    "credit_customers.csv": REPO_ROOT / "German Credit Lending" / "credit_customers.csv",
    "AI_Fair_Recruitment_Dataset.csv": REPO_ROOT / "AI Fair Recruitment" / "AI_Fair_Recruitment_Dataset.csv",
}


@pytest.mark.parametrize("csv_name", list(CSV_PATHS))
def test_python_js_profiler_parity(csv_name):
    """The Python and JavaScript profilers should produce equivalent structured JSON."""

    csv = CSV_PATHS[csv_name]

    python_result = profile(pd.read_csv(csv))

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    javascript_result = json.loads(completed.stdout)

    # Flags are human-readable messages. They duplicate information already
    # present in the structured output and may differ because Python and
    # JavaScript format floating-point values differently (e.g. 6.25 -> 6.2
    # vs 6.3). Compare the structured data instead.
    python_result = dict(python_result)
    javascript_result = dict(javascript_result)

    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result


def test_python_js_profiler_parity_preserves_mid_field_quotes(tmp_path):
    """Quotes after field content are literal in pandas and the browser parser."""
    csv = tmp_path / "space_before_quote.csv"
    csv.write_text(
        'sex, race, age\n'
        'Male, "White", 25\n'
        'Female, "Black", 30\n'
        'Male, "White", 45\n'
        'Female, "Asian", 22\n',
        encoding="utf-8",
    )

    python_result = profile(pd.read_csv(csv))
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result


def test_python_js_profiler_parity_with_overrides_cross_and_thresholds(tmp_path):
    """Non-default options - --map/--cross/--reference/thresholds - only ever
    had cross-engine parity coverage for their default-off path (issue #376).
    A future change to either _resolve_opts (Python) or resolveOpts (JS), or
    to either engine's override-handling branch, could silently diverge here
    with nothing in this suite to catch it."""
    csv = CSV_PATHS["adult.csv"]
    overrides = {"education": "categorical"}
    reference = {"race": {"White": 0.7, "Black": 0.2, "Other": 0.1}}
    opts = {"cross": ["age", "race"], "min_group_size": 500, "reference": reference}

    python_result = profile(pd.read_csv(csv), overrides, opts)

    opts_path = tmp_path / "opts.json"
    opts_path.write_text(json.dumps({"overrides": overrides, "opts": opts}), encoding="utf-8")

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv), str(opts_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result
    # Confirm the options actually took effect on both sides, not just that
    # both silently ignored them the same way.
    assert any(d["name"] == "education" and d["kind"] == "categorical"
               for d in python_result["dimensions"])
    assert python_result["intersections"][0]["dims"] == ["age", "race"]
    assert any("reference" in d for d in python_result["dimensions"])


def test_python_js_cross_parity_on_unmatched_column(tmp_path):
    """An unmatched `cross` column raises the same error on both engines
    instead of the JS engine silently falling back to the first two detected
    dimensions with no error (#420)."""
    csv = CSV_PATHS["adult.csv"]

    with pytest.raises(ValueError, match="cross column\\(s\\) don't match any profiled dimension: nonexistent_col"):
        profile(pd.read_csv(csv), opts={"cross": ["age", "nonexistent_col"]})

    opts_path = tmp_path / "opts.json"
    opts_path.write_text(json.dumps({"opts": {"cross": ["age", "nonexistent_col"]}}), encoding="utf-8")

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv), str(opts_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode != 0
    assert "cross column(s) don't match any profiled dimension: nonexistent_col" in completed.stderr


def test_python_js_reference_parity_on_unmatched_column(tmp_path):
    """A reference baseline whose column(s) don't match any profiled
    dimension raises the same error on both engines instead of the JS
    engine silently applying nothing (#419)."""
    csv = CSV_PATHS["adult.csv"]
    reference = {"totally_wrong_col": {"a": 0.5, "b": 0.5}}

    with pytest.raises(ValueError, match="reference file's column\\(s\\) don't match any profiled dimension: totally_wrong_col"):
        profile(pd.read_csv(csv), opts={"reference": reference})

    opts_path = tmp_path / "opts.json"
    opts_path.write_text(json.dumps({"opts": {"reference": reference}}), encoding="utf-8")

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv), str(opts_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode != 0
    assert "reference file's column(s) don't match any profiled dimension: totally_wrong_col" in completed.stderr


def test_python_js_json_parity_inconsistent_keys():
    """Records-orient JSON where later records add columns the first one
    doesn't have (#144). The JS parseJSON() used to derive columns from only
    the first record, silently dropping any column that first appeared later
    - pandas' read_json unions keys across every record instead."""

    json_path = FIXTURES / "inconsistent_keys.json"

    python_result = profile(pd.read_json(json_path))

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile-json", str(json_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result


def test_python_js_json_parity_columns_orientation():
    """Columns-orient JSON ({"col": {"0": v, ...}}, pandas' read_json default
    for a plain object) - #155 documented and tested this for the CLI, but
    the JS engine's parseJSON() only handled records/split and threw on it.
    Now handled the same way as the records branch (union of index keys)."""

    json_path = FIXTURES / "columns_orient.json"

    python_result = profile(pd.read_json(json_path))

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile-json", str(json_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result


@requires_openpyxl
def test_python_js_xlsx_parity():
    """.xlsx support (#158) - the JS engine's parseXLSX() (via SheetJS,
    fetched from the same pinned CDN profiler.html loads) should agree with
    pandas.read_excel() on the same workbook. Skips if the CDN is
    unreachable rather than failing the suite - see scripts/engine-js.js.
    """
    xlsx_path = FIXTURES / "adult_sample.xlsx"

    python_result = profile(pd.read_excel(xlsx_path))

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile-xlsx", str(xlsx_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode == 3:
        pytest.skip("SheetJS CDN unreachable: " + completed.stderr.strip())
    assert completed.returncode == 0, completed.stderr

    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result


def test_python_js_compare_parity_age_banding_mismatch(tmp_path):
    """The age-banding-mismatch guard (#318) agrees between engines too -
    `kind` alone can't detect it (it's set from the column name and is
    identical on both sides), so this exercises isAgeBandLabel()'s port of
    _is_age_band_label() directly, not just the already-covered common path.
    """
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    path_a.write_text("DOB\n" + "\n".join(["15/05/1980"] * 50 + ["20/06/1985"] * 50))
    path_b.write_text("DOB\n" + "\n".join(["18"] * 50 + ["35"] * 50))

    python_result = compare(
        profile(pd.read_csv(path_a)), profile(pd.read_csv(path_b)), "a.csv", "b.csv"
    )

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "compare", str(path_a), str(path_b)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)

    assert javascript_result == python_result
    dim = python_result["dimensions"][0]
    assert dim["kind_mismatch"] is True
    assert dim["kind_a"] == dim["kind_b"] == "age"


@pytest.mark.parametrize("csv_name", list(CSV_PATHS))
def test_python_js_compare_parity(csv_name):
    """faircode.compare() and the JS engine's compare() should agree too (#111).

    Compares each fixture against itself - not meant to exercise every drift
    level, just to confirm the two independent compare()/compare_to_html()
    implementations (faircode/report.py and assets/profiler-compare.js) are
    working off identically-shaped, identically-valued structured data.
    """

    csv = CSV_PATHS[csv_name]
    df = pd.read_csv(csv)

    python_result = compare(profile(df), profile(df), "a.csv", "b.csv")

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "compare", str(csv), str(csv)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)

    # As above: flags are human-readable and float-formatted differently
    # between Python and JS. Compare the structured data instead. Names also
    # differ (JS uses the file's basename via path.basename, Python uses
    # whatever the caller passed) - normalize both before comparing.
    python_result = dict(python_result)
    javascript_result = dict(javascript_result)

    for result in (python_result, javascript_result):
        result.pop("flags", None)
        for side in ("a", "b"):
            result[side] = dict(result[side])
            result[side].pop("name", None)

    assert javascript_result == python_result
