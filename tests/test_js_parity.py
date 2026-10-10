"""Parity tests between the Python and JavaScript profiler implementations."""

import csv
import importlib.util
import io
import json
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from faircode import compare, profile
from faircode.loaders import read_table

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


def test_compare_card_renderers_special_case_kind_mismatch():
    """driftCard() and buildCompareHtmlReport()'s per-dimension section must
    both read cd.kind_mismatch, so a skipped comparison isn't drawn as a
    "none drift" badge next to a real score change (#519). Source-level check
    (mirrors test_sheetjs_cdn_url_matches) - these renderers are DOM-coupled
    and have no unit harness."""
    src = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")

    drift_card = src[src.index("function driftCard("):]
    drift_card = drift_card[: drift_card.index("\n  }\n")]
    assert "kind_mismatch" in drift_card
    assert "comparison skipped" in drift_card

    report = src[src.index("function buildCompareHtmlReport("):]
    assert "if (cd.kind_mismatch)" in report
    # the skipped badge is styled in both the live css and the report's own <style>
    assert ".drift-badge.skipped" in src
    assert ".drift-badge.skipped" in (REPO_ROOT / "assets" / "profiler.css").read_text(encoding="utf-8")


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


def test_python_js_profiler_parity_sniffs_quoted_newlines(tmp_path):
    """Embedded newlines do not split logical rows during delimiter sniffing."""
    dataset = tmp_path / "sniff_quoted_newline.dat"
    dataset.write_text(
        'sex;race;age;notes\n'
        'M;White;25;"single line"\n'
        'F;Black;30;"multi\nline note"\n'
        'M;White;45;"ok"\n'
        'F;Asian;22;"fine"\n'
        'M;White;50;"good"\n',
        encoding="utf-8",
    )

    python_result = profile(read_table(str(dataset)))
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(dataset)],
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


def test_python_js_profiler_parity_detects_dates_appended_after_numeric_ages(tmp_path):
    """A merged-in birthdate block cannot become a fabricated elderly group."""
    csv = tmp_path / "mixed-age-and-birthdate.csv"
    ages = [str(age) for age in range(20, 80)]
    dates = ["1985-03-21", "1990-07-14", "2001-11-02"] * 20
    csv.write_text("age\n" + "\n".join(ages + dates) + "\n", encoding="utf-8")

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
    assert all(dim["name"] != "age" for dim in python_result["dimensions"])


def test_python_js_profiler_parity_handles_scientific_and_nonfinite_ages(tmp_path):
    """Scientific notation follows pandas' numeric inference; inf/nan stay missing."""
    csv = tmp_path / "scientific-and-nonfinite-ages.csv"
    csv.write_text(
        "age,sex\n"
        "1e2,F\n"
        "25,M\n"
        "40,F\n"
        "60,M\n"
        "inf,F\n"
        "nan,M\n",
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
    age = next(d for d in python_result["dimensions"] if d["name"] == "age")
    labels = {group["label"] for group in age["groups"]}
    assert "75+" in labels
    assert "inf" not in labels
    assert "nan" not in labels
    assert age["missing_pct"] == 0.3333


def test_python_js_profiler_handles_overflowing_scientific_age_as_missing(tmp_path):
    """A value such as 1e400 parses to Infinity in JS and must not become an age group."""
    csv = tmp_path / "overflow-age.csv"
    csv.write_text(
        "age\n"
        "25\n"
        "40\n"
        "60\n"
        "1e400\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    javascript_result = json.loads(completed.stdout)
    age = next(d for d in javascript_result["dimensions"] if d["name"] == "age")
    labels = {group["label"] for group in age["groups"]}

    assert "inf" not in labels
    assert "1e400" not in labels
    assert age["missing_pct"] == 0.25


def test_python_js_profiler_parity_rejects_negative_age_sentinels(tmp_path):
    """Signed sentinel ages stay missing in both profiler engines."""
    csv = tmp_path / "negative-age-sentinels.csv"
    csv.write_text(
        "age,sex\n25,F\n30,M\nage -5,F\n-1,M\n45,F\n",
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
    age = next(d for d in python_result["dimensions"] if d["name"] == "age")
    assert "75+" not in {group["label"] for group in age["groups"]}
    assert age["missing_pct"] == 0.4


def test_python_js_na_token_parity_on_literal_na_and_none(tmp_path):
    """NA_TOKENS / isMissing() must match pandas' default STR_NA_VALUES
    exactly and case-sensitively: literal "None" is missing, bare lowercase
    "na" is a real category. The JS engine used to have both backwards and
    lower-cased the cell before comparing (#491)."""
    csv = tmp_path / "na_test.csv"
    csv.write_text(
        "status,x\n"
        "active,1\ninactive,2\nna,3\nna,4\nNone,5\nNone,6\n"
        "active,7\ninactive,8\nactive,9\ninactive,10\n",
        encoding="utf-8",
    )

    python_result = profile(read_table(str(csv)))
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)
    assert javascript_result == python_result

    status = next(d for d in python_result["dimensions"] if d["name"] == "status")
    labels = {g["label"] for g in status["groups"]}
    assert "na" in labels          # bare lowercase "na" is NOT a pandas NA token
    assert "None" not in labels    # "None" IS a pandas NA token
    assert status["missing_pct"] == 0.2


def test_python_js_public_params_parity_for_a_defaulted_run():
    """A web-profiler export with no threshold ever touched must still record
    the 7 resolved defaults in provenance.params, matching the CLI/MCP path -
    E.publicParams({}) mirrors provenance.public_params(_resolve_opts(None)) (#490)."""
    from faircode.profiler import _resolve_opts
    from faircode.provenance import public_params

    expected = public_params(_resolve_opts(None))

    script = (
        "require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(globalThis.FairCodeProfiler.publicParams({})));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js")],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert json.loads(completed.stdout) == expected
    assert set(expected) == {
        "cross", "imbalance_flag", "intersection_floor", "max_categorical_card",
        "age_reference_year", "keywords", "max_age", "max_dimension_groups", "min_group_size",
        "min_share", "missing_flag", "reference_flag",
    }
    assert "reference" not in expected


def test_python_js_parity_for_implausible_ages(tmp_path):
    """#840: ages above max_age are flagged and left out of the bands identically in
    both engines, including in the intersection and with a custom --max-age."""
    path = tmp_path / "ages.csv"
    path.write_text("sex,age\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{[25, 33, 47, 62, 80, 150, 200, 1985][i % 8]}" for i in range(64)) + "\n")
    for opts in ({}, {"max_age": 70}):
        opts_file = tmp_path / "opts.json"
        opts_file.write_text(json.dumps({"overrides": {}, "opts": opts}))
        python_result = dict(profile(pd.read_csv(path), None, opts))
        completed = subprocess.run(
            ["node", "scripts/engine-js.js", "profile", str(path), str(opts_file)],
            capture_output=True, text=True, encoding="utf-8", check=True)
        javascript_result = json.loads(completed.stdout)
        py_flags, js_flags = python_result.pop("flags"), javascript_result.pop("flags")
        assert javascript_result == python_result
        age = next(d for d in python_result["dimensions"] if d["name"] == "age")
        assert age["implausible_values"] == (24 if not opts else 32)
        implausible = [f for f in py_flags if "implausible age" in f]
        assert implausible and implausible == [f for f in js_flags if "implausible age" in f]


def test_python_js_parity_for_negative_sentinel_ages(tmp_path):
    """#863: negative sentinel ages are flagged identically in both engines."""
    path = tmp_path / "neg_ages.csv"
    path.write_text("sex,age\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{[25, 33, -1, 62, -9, 150, 40, 200][i % 8]}" for i in range(64)) + "\n")
    opts_file = tmp_path / "opts.json"
    opts_file.write_text(json.dumps({"overrides": {}, "opts": {}}))
    python_result = dict(profile(pd.read_csv(path), None, {}))
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(path), str(opts_file)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    javascript_result = json.loads(completed.stdout)
    py_flags, js_flags = python_result.pop("flags"), javascript_result.pop("flags")
    assert javascript_result == python_result
    age = next(d for d in python_result["dimensions"] if d["name"] == "age")
    assert age["implausible_values"] == 32
    assert age["has_negative_ages"] is True
    sentinel_flags = [f for f in py_flags if "sentinel/implausible age" in f]
    assert sentinel_flags and sentinel_flags == [f for f in js_flags if "sentinel/implausible age" in f]


def test_python_js_parity_for_non_english_column_names(tmp_path):
    """#847: accent-stripped, multilingual keyword detection agrees between engines,
    including the no-kind-detected --map hint."""
    names = ["sexo", "Género", "Geschlecht", "raza", "Rasse", "Raça", "edad", "Alter", "Âge",
             "Fecha de nacimiento", "Bundesland", "país", "Código postal", "estado",
             "generosity", "alternative", "landing", "Straße", "etat_civil",
             "estado_civil", "estado civil", "EstadoCivil", "marital_status",
             "stato_civile", "état civil"]
    script = (
        "require(process.argv[1]);var E=globalThis.FairCodeProfiler;"
        "var out={};JSON.parse(process.argv[2]).forEach(function(n){"
        "out[n]=E.profile({columns:[n],rows:[{[n]:'a'},{[n]:'b'}]}).dimensions[0].kind});"
        "process.stdout.write(JSON.stringify(out));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), json.dumps(names)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    from faircode.detect import classify_name
    js = json.loads(completed.stdout)
    for name in names:
        py = classify_name(name) or "categorical"
        assert js[name] == py, name

    path = tmp_path / "plain.csv"
    path.write_text("colA,colB\n" + "\n".join(f"{'x' if i % 2 else 'y'},{'p' if i % 3 else 'q'}" for i in range(40)) + "\n")
    python_result = dict(profile(pd.read_csv(path)))
    completed = subprocess.run(["node", "scripts/engine-js.js", "profile", str(path)],
                               capture_output=True, text=True, encoding="utf-8", check=True)
    javascript_result = json.loads(completed.stdout)
    assert javascript_result["flags"][-1] == python_result["flags"][-1]
    assert "--map COL=KIND" in python_result["flags"][-1]
    python_result.pop("flags"); javascript_result.pop("flags")
    assert javascript_result == python_result


def test_python_js_parity_for_birth_year_conversion(tmp_path):
    """#862: age_reference_year turns birth years into ages identically in both engines,
    including the intersection, and a future year stays implausible."""
    path = tmp_path / "yob.csv"
    path.write_text("sex,yob\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{[1985, 1990, 1972, 2001, 1950, 2010, 40, 2090][i % 8]}" for i in range(64)) + "\n")
    opts_file = tmp_path / "opts.json"
    opts_file.write_text(json.dumps({"overrides": {}, "opts": {"age_reference_year": 2026}}))
    python_result = dict(profile(pd.read_csv(path), None, {"age_reference_year": 2026}))
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(path), str(opts_file)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    javascript_result = json.loads(completed.stdout)
    py_flags, js_flags = python_result.pop("flags"), javascript_result.pop("flags")
    assert javascript_result == python_result
    yob = next(d for d in python_result["dimensions"] if d["name"] == "yob")
    assert yob["implausible_values"] == 8 and yob["n_groups"] >= 4  # only 2090 is implausible
    assert [f for f in py_flags if "implausible" in f] == [f for f in js_flags if "implausible" in f]


def test_python_js_compare_parity_for_quality_flags_and_renames(tmp_path):
    """#868/#866: implausible-age carry-over, the no-kind-detected note and rename
    suggestions are produced identically by both engines."""
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    path_a.write_text("sex,age,race\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{[25, 30, 41, 55][i % 4]},{['White', 'Black', 'Asian'][i % 3]}" for i in range(48)) + "\n")
    path_b.write_text("sex,age,ethnicity\n" + "\n".join(
        f"{'M' if i % 2 else 'F'},{[25, 200, 41, 150][i % 4]},{['White', 'Black', 'Asian'][i % 3]}" for i in range(48)) + "\n")
    python_result = compare(profile(pd.read_csv(path_a)), profile(pd.read_csv(path_b)), "a.csv", "b.csv")
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "compare", str(path_a), str(path_b)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    javascript_result = json.loads(completed.stdout)
    py_flags, js_flags = python_result.pop("flags"), javascript_result.pop("flags")
    assert javascript_result == dict(python_result)
    for needle in ("implausible age values differ", "look like the same dimension"):
        assert [f for f in py_flags if needle in f] == [f for f in js_flags if needle in f] != []
    assert python_result["possible_renames"][0]["b"] == "ethnicity"


def test_python_js_parity_for_extra_keywords_and_italian_dutch_terms(tmp_path):
    """#856: the user vocabulary (normalised, exact_only, validation errors) and the new
    Italian/Dutch built-ins behave identically in both engines."""
    from faircode.detect import classify_name, normalize_keywords

    extra = {"sex": ["GNDR", "Jenis"], "race": ["EtnGrp"], "age": ["Umur"], "exact_only": ["umur"]}
    names = ["sesso", "Età", "razza", "leeftijd", "geslacht", "geboortedatum", "regione", "paese",
             "gndr", "jenis", "umur", "umuraa", "jenis_x", "etngrp", "other"]
    script = (
        "require(process.argv[1]);var E=globalThis.FairCodeProfiler;var out={};"
        "var names=JSON.parse(process.argv[2]),extra=JSON.parse(process.argv[3]);"
        "names.forEach(function(n){"
        "out[n]=[E.profile({columns:[n],rows:[{[n]:'a'},{[n]:'b'}]},{},{}).dimensions[0].kind,"
        "E.profile({columns:[n],rows:[{[n]:'a'},{[n]:'b'}]},{},{keywords:extra}).dimensions[0].kind]});"
        "out.__norm=E.normalizeKeywords(extra);"
        "var bad=[{x:[1]},{sex:'a'},{sex:['a b']},[1],{sex:['']}];out.__errors=bad.map(function(b){"
        "try{E.normalizeKeywords(b);return null}catch(e){return e.message}});"
        "process.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"),
         json.dumps(names), json.dumps(extra)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    js = json.loads(done.stdout)
    for n in names:
        assert js[n] == [classify_name(n) or "categorical", classify_name(n, extra) or "categorical"], n
    assert js["__norm"] == normalize_keywords(extra) == {
        "sex": ["gndr", "jenis"], "race": ["etngrp"], "age": ["umur"], "exact_only": ["umur"]}
    py_errors = []
    for b in ({"x": [1]}, {"sex": "a"}, {"sex": ["a b"]}, [1], {"sex": [""]}):
        try:
            normalize_keywords(b)
            py_errors.append(None)
        except ValueError as exc:
            py_errors.append(str(exc))
    assert js["__errors"] == py_errors and all(py_errors)
    assert js["umuraa"] == ["categorical", "categorical"]   # exact_only: no prefix match


def test_keywords_textarea_is_wired_into_both_web_views():
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")
    assert 'id="keywordsInput"' in html and 'id="compareKeywordsInput"' in html
    assert html.count('data-opt-json="keywords"') == 2
    for name in ("profiler-ui.js", "profiler-compare.js"):
        js = (REPO_ROOT / "assets" / name).read_text(encoding="utf-8")
        assert "[data-opt-json]" in js and "JSON.parse(raw)" in js


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


def test_python_js_reject_out_of_range_min_share_parity(tmp_path):
    """Both engines reject an out-of-range tunable (min_share=1.5) rather
    than silently producing a self-contradictory report (#511)."""
    csv = CSV_PATHS["small.csv"]

    with pytest.raises(ValueError, match="min_share must be between 0 and 1"):
        profile(pd.read_csv(csv), opts={"min_share": 1.5})

    opts_path = tmp_path / "opts.json"
    opts_path.write_text(json.dumps({"opts": {"min_share": 1.5}}), encoding="utf-8")

    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv), str(opts_path)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode != 0
    assert "min_share must be between 0 and 1" in completed.stderr


def test_python_js_intersection_parity_keeps_non_numeric_age_sentinels(tmp_path):
    """labelize() gives a non-numeric age sentinel its own crosstab label on
    both engines, instead of mapping it to null and dropping the row (#524)."""
    csv = tmp_path / "age_sentinels.csv"
    ages = ["25", "30", "45", "unknown", "unknown", "unknown",
            "prefer not to say", "22", "33", "41"] * 3
    sexes = ["M", "F"] * 15
    csv.write_text(
        "age,sex\n" + "\n".join(a + "," + s for a, s in zip(ages, sexes)) + "\n",
        encoding="utf-8",
    )

    opts = {"cross": ["age", "sex"]}
    python_result = profile(pd.read_csv(csv, dtype={"age": str}), opts=opts)

    opts_path = tmp_path / "opts.json"
    opts_path.write_text(json.dumps({"opts": opts}), encoding="utf-8")
    completed = subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(csv), str(opts_path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    javascript_result = json.loads(completed.stdout)

    python_result = dict(python_result)
    javascript_result = dict(javascript_result)
    python_result.pop("flags", None)
    javascript_result.pop("flags", None)
    assert javascript_result == python_result

    a_labels = {c["a"] for c in python_result["intersections"][0]["cells"]}
    assert "prefer not to say" in a_labels


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


def test_python_js_parse_reference_mixed_scale_parity(tmp_path):
    """parse_reference / parseReference decide percent-vs-fraction per column,
    not once across the whole table, so a reference file mixing conventions
    between columns parses identically on both engines (#513)."""
    from faircode.profiler import parse_reference

    ref_df = pd.DataFrame({
        "column": ["sex", "sex", "race", "race", "race"],
        "group": ["Female", "Male", "White", "Black", "Other"],
        "share": [0.6, 0.4, 70, 20, 10],
    })
    py_result = parse_reference(ref_df)
    assert py_result == {
        "sex": {"Female": 0.6, "Male": 0.4},
        "race": {"White": 0.7, "Black": 0.2, "Other": 0.1},
    }

    table_json = tmp_path / "table.json"
    table_json.write_text(json.dumps({
        "columns": list(ref_df.columns),
        "rows": ref_df.to_dict(orient="records"),
    }), encoding="utf-8")

    script = (
        "const fs=require('fs');"
        "require(process.argv[1]);"
        "const t=JSON.parse(fs.readFileSync(process.argv[2],'utf-8'));"
        "process.stdout.write(JSON.stringify(globalThis.FairCodeProfiler.parseReference(t)));"
    )
    completed = subprocess.run(
        ["node", "-e", script,
         str(REPO_ROOT / "assets" / "profiler-engine.js"), str(table_json)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert json.loads(completed.stdout) == py_result


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


def test_proxy_hint_results_are_live_regions():
    """Proxy-hint results should be announced to screen-reader users."""
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")

    assert 'id="proxyHintsResults" aria-live="polite"' in html
    assert 'id="compareProxyHintsResults" aria-live="polite"' in html
    
    
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


def test_threshold_input_recovers_panel_after_invalid_value():
    """profiler-ui.js's threshold-input handler must recover when the engine
    rejects the typed value (e.g. min_share 1.5, see #602): reprofile() fails
    and showError() hides the whole #results panel, including the very input
    the user needs to correct. The handler must revert that opt to its
    last-known-good value and retry once, the same recovery the mapping-select
    handler got in #466. Source-level check (mirrors
    test_compare_card_renderers_special_case_kind_mismatch) - this handler is
    DOM-coupled and has no unit harness."""
    src = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")

    marker = "thresholdInputs.forEach(function (input) {\n    input.addEventListener('input'"
    handler = src[src.index(marker):]
    handler = handler[: handler.index("\n  });\n")]

    # it must notice that the re-profile failed ...
    assert "if (!reprofile(false))" in handler
    # ... revert the offending opt to the value it held before ...
    assert "currentOpts[opt] = previous;" in handler
    # ... and retry once so the #results panel (and this input) come back
    assert handler.count("reprofile(false)") >= 2


def test_dim_card_renders_an_expand_control_past_display_groups():
    """profiler-ui.js's dimCard() must render extra groups past DISPLAY_GROUPS
    up front (hidden) with a toggle button, rather than the old static "...and
    N more groups" text with no way to actually see them (#740). Source-level
    check (mirrors test_threshold_input_recovers_panel_after_invalid_value) -
    this is DOM-coupled and has no unit harness."""
    src = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")

    marker = "  function dimCard(d) {"
    fn = src[src.index(marker):]
    fn = fn[: fn.index("\n  function renderIntersections")]

    assert "dim-extra-groups" in fn
    assert 'aria-expanded="false"' in fn
    assert "dim-more-btn" in fn
    # the click handler must flip the hidden attribute and the aria state together
    assert "extra.hidden = expanded" in fn
    assert "btn.setAttribute('aria-expanded'" in fn
    # the old dead-end text is gone
    assert "… and " not in fn


def test_drift_card_renders_an_expand_control_past_display_groups():
    """assets/profiler-compare.js's driftCard() gets the same #740 treatment,
    with a resultsEl-level delegated click handler (driftCard rebuilds via an
    innerHTML string, not a DOM node dimCard() can attach a listener to
    directly)."""
    src = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")

    card_fn_marker = "  function driftCard(cd) {"
    card_fn = src[src.index(card_fn_marker):]
    card_fn = card_fn[: card_fn.index("\n\n  // ── Report export")]
    assert "dim-extra-groups" in card_fn
    assert "dim-more-btn" in card_fn
    assert "… and " not in card_fn

    delegated_marker = "resultsEl.addEventListener('click'"
    assert delegated_marker in src
    handler = src[src.index(delegated_marker):]
    handler = handler[: handler.index("\n  });")]
    assert "closest" in handler
    assert "extra.hidden = expanded" in handler


def test_python_js_sample_dataset_is_byte_identical():
    """faircode profile --sample (faircode/sample_data.py) and the web
    profiler's "Try it with a sample dataset" button
    (assets/profiler-ui.js's buildSampleCSV()) must produce the exact same
    CSV text, so a first-time user sees an identical demo either way (#741)."""
    from faircode.sample_data import build_sample_csv

    src = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")
    match = re.search(r"function buildSampleCSV\(\) \{[\s\S]*?\n  \}", src)
    assert match, "could not find buildSampleCSV() in profiler-ui.js"

    script = match.group(0) + ";process.stdout.write(buildSampleCSV());"
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert completed.stdout == build_sample_csv()


def _run_js_proxy_hints(csv_path, alpha=0.05, exact=False):
    script = (
        "require(process.argv[1]);"
        "var fs=require('fs');"
        "var table=globalThis.FairCodeProfiler.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));"
        "var r=globalThis.FairCodeProfiler.profile(table,{},{});"
        "var hints=globalThis.FairCodeProfiler.proxyHints(table,r.dimensions,"
        + repr(alpha) + ",null,null,undefined,undefined," + ("true" if exact else "false") + ");"
        "process.stdout.write(JSON.stringify(hints));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(csv_path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(completed.stdout)


def test_python_js_proxy_hints_parity_on_a_correlated_pair(tmp_path):
    """The web engine's proxyHints() (#738) is an opt-in, JS-only port of
    faircode/proxy.py's proxy_hints() - not covered by profile()/compare()'s
    bit-for-bit parity contract, but it should still agree with scipy's
    chi2_contingency on the same data: this builds a sex/race pair with a
    strong, deliberate correlation and checks both engines flag it with
    matching chi2/Cramer's V and a p-value that agrees to several digits
    (the two chi-squared CDF implementations differ past float precision)."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints

    rows = ["sex,race"]
    for i in range(60):
        sex = "male" if i % 2 == 0 else "female"
        if sex == "male":
            race = "White" if i % 5 != 0 else "Black"
        else:
            race = "White" if i % 4 == 0 else "Black"
        rows.append(f"{sex},{race}")
    csv = tmp_path / "proxy_pair.csv"
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

    df = pd.read_csv(csv)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    python_hints = proxy_hints(df, dims, alpha=0.9)
    js_hints = _run_js_proxy_hints(csv, alpha=0.9)

    assert len(python_hints) == 1
    assert len(js_hints) == 1
    py_hint, js_hint = python_hints[0], js_hints[0]
    assert (py_hint["a"], py_hint["b"]) == (js_hint["a"], js_hint["b"]) == ("sex", "race")
    assert py_hint["chi2"] == js_hint["chi2"]
    assert py_hint["cramers_v"] == js_hint["cramers_v"]
    assert py_hint["p_value"] == pytest.approx(js_hint["p_value"], rel=1e-6)
    # #810: the small-cell diagnostics must agree too
    assert py_hint["low_expected_share"] == js_hint["low_expected_share"]
    assert py_hint["low_expected"] == js_hint["low_expected"]
    assert py_hint["n_tests"] == js_hint["n_tests"] == 1


def test_python_js_proxy_hints_parity_flags_small_expected_cells(tmp_path):
    """#810: a sparse high-cardinality pair is flagged low_expected by both engines."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints

    rows = ["sex,race"]
    races = ["White", "Black", "Asian", "Latino", "Other", "Native"]
    for i in range(24):
        rows.append(f"{'male' if i % 2 == 0 else 'female'},{races[(i // 2 + i) % 6]}")
    csv = tmp_path / "sparse.csv"
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    df = pd.read_csv(csv)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    py = proxy_hints(df, dims, alpha=1.0)
    js = _run_js_proxy_hints(csv, alpha=1.0)
    assert len(py) == len(js) == 1
    assert py[0]["low_expected"] is True and js[0]["low_expected"] is True
    assert py[0]["low_expected_share"] == js[0]["low_expected_share"] > 0.2


def test_python_js_proxy_hints_parity_finds_nothing_for_unrelated_columns(tmp_path):
    """A column pair with no real association should not be flagged by either
    engine - proxyHints()'s job is precision (avoid crying wolf), not recall."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints

    rows = ["sex,race"]
    sexes = ["male", "female"]
    races = ["White", "Black", "Asian"]
    for i in range(90):
        rows.append(f"{sexes[i % 2]},{races[i % 3]}")
    csv = tmp_path / "proxy_unrelated.csv"
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

    df = pd.read_csv(csv)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    assert proxy_hints(df, dims, alpha=0.05) == []
    assert _run_js_proxy_hints(csv) == []


def test_proxy_hints_ui_wiring_present_in_profiler_html_and_ui_js():
    """Source-level check (like #740's dim/drift-card tests): the web results
    view must expose the opt-in proxy-hints button/section wired up in
    profiler-ui.js, and the dropzone hint text should no longer tell web
    users the feature is CLI-only, now that it's available in-browser (#738)."""
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")
    assert 'id="proxyHintsBlock"' in html
    assert 'id="proxyHintsBtn"' in html
    assert 'id="proxyHintsResults"' in html
    assert "CLI.) Proxy-hint detection: use" not in html

    ui = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")
    assert "proxyHintsBtn.addEventListener('click', renderProxyHints)" in ui
    assert "E.proxyHints(currentTable, currentResult.dimensions, alpha, heldOut," in ui
    assert 'id="proxyCorrectionInput"' in html


def _run_ui_exports(csv_path, with_hints, reference=None, provenance=None):
    """Execute profiler-ui.js's real buildHtmlReport/buildCsvReport (sliced out
    of the DOM-coupled file) against a real engine profile of `csv_path`."""
    src = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")
    helpers = src[src.index("var GRADE_COLOR"):src.index("function render(")]
    builders = src[src.index("function buildHtmlReport(r)"):src.index("async function downloadCsvReport")]
    script = (
        "var DISPLAY_GROUPS=12;" + helpers +
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        + builders +
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var r=E.profile(t,{}," + json.dumps({"reference": reference} if reference else {}) + ");"
        + ("r.proxy_hints=E.proxyHints(t,r.dimensions,0.9);" if with_hints else "") +
        "process.stdout.write(JSON.stringify({html:buildHtmlReport(r),csv:buildCsvReport(r," + json.dumps(provenance) + ")}));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(csv_path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(completed.stdout)


def _sex_race_csv(tmp_path):
    rows = ["sex,race"]
    for i in range(60):
        sex = "male" if i % 2 == 0 else "female"
        race = ("White" if i % 5 != 0 else "Black") if sex == "male" else ("White" if i % 4 == 0 else "Black")
        rows.append(f"{sex},{race}")
    path = tmp_path / "sr.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_web_csv_export_matches_python_to_csv(tmp_path):
    """The web "Download CSV" output (#755) must equal faircode's to_csv()
    for the same data, with and without proxy hints (#758, #760)."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints
    from faircode.report import to_csv

    path = _sex_race_csv(tmp_path)
    df = pd.read_csv(path)
    result = dict(profile(df))
    plain = _run_ui_exports(path, False)["csv"]
    assert plain.replace("\r\n", "\n") == to_csv(result).replace("\r\n", "\n")

    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    result["proxy_hints"] = proxy_hints(df, dims, alpha=0.9)
    with_hints = _run_ui_exports(path, True)["csv"].splitlines()
    py = to_csv(result).splitlines()
    i = with_hints.index("proxy_hint_a,proxy_hint_b,p_value,cramers_v,n_tests,low_expected")
    assert with_hints[:i] == py[:i]
    assert with_hints[i + 1].startswith("sex,race,") and py[i + 1].startswith("sex,race,")


def test_web_html_report_has_core_sections_and_proxy_hints(tmp_path):
    """buildHtmlReport() (the file the web "Download report" button emits) had
    no test (#765) and silently omitted proxy hints (#758)."""
    path = _sex_race_csv(tmp_path)
    plain = _run_ui_exports(path, False)["html"]
    assert "Dataset Representation Profile" in plain
    assert "<h2>sex" in plain and "<h2>race" in plain
    assert "Proxy hints" not in plain
    hinted = _run_ui_exports(path, True)["html"]
    assert "Proxy hints" in hinted and "sex ↔ race" in hinted


def test_web_compare_csv_and_html_match_python_and_include_proxy_hints(tmp_path):
    """Executes the real buildCompareCsvReport/buildCompareHtmlReport (#756,
    #757): the CSV's group and summary sections must equal Python's
    compare_to_csv() (flags differ in float formatting, so they are excluded),
    and attached proxy hints must reach both the CSV and the HTML report."""
    from faircode.report import compare_to_csv

    path_a = _sex_race_csv(tmp_path)
    rows = ["sex,race"] + [
        f"{'male' if i % 3 else 'female'},{'White' if i % 3 else 'Asian'}" for i in range(80)
    ]
    path_b = tmp_path / "b.csv"
    path_b.write_text("\n".join(rows) + "\n", encoding="utf-8")

    src = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")
    helpers = (src[src.index("function pct("):src.index("function wireSlot")]
               + src[src.index("function kindMismatchReason"):src.index("function driftCard")])
    builders = src[src.index("function proxyHintItems"):src.index("function compareReportBaseName")]
    csvs = src[src.index("var csvRow = E.csvRow"):src.index("async function downloadCompareCsvReport")]
    script = (
        "var DISPLAY_GROUPS=12;" + helpers +
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        + builders + csvs +
        "function load(p){return E.parseCSV(fs.readFileSync(p,'utf-8'));}"
        "var ta=load(process.argv[2]),tb=load(process.argv[3]);"
        "var pa=E.profile(ta,{},{}),pb=E.profile(tb,{},{});var c=E.compare(pa,pb,'a.csv','b.csv');"
        "var plain=buildCompareCsvReport(c);"
        "c.proxy_hints_a=E.proxyHints(ta,pa.dimensions,1);c.proxy_hints_b=E.proxyHints(tb,pb.dimensions,1);"
        "process.stdout.write(JSON.stringify({plain:plain,csv:buildCompareCsvReport(c),html:buildCompareHtmlReport(c)}));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(path_a), str(path_b)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    out = json.loads(completed.stdout)

    py = compare_to_csv(compare(profile(pd.read_csv(path_a)), profile(pd.read_csv(path_b)), "a.csv", "b.csv"))
    def head(text):
        # Python writes 0.0 where JS writes 0; compare numerically, not textually.
        def norm(cell):
            try:
                return float(cell)
            except ValueError:
                return cell
        body = text.replace("\r\n", "\n").split("\n\nflag\n")[0]
        return [[norm(c) for c in row] for row in csv.reader(io.StringIO(body))]

    assert head(out["plain"]) == head(py)
    assert "dataset,proxy_hint_a,proxy_hint_b,p_value,cramers_v,n_tests,low_expected" in out["csv"]
    assert "Proxy hints - A" in out["html"] and "Proxy hints - B" in out["html"]


def test_web_compare_csv_lists_one_sided_dimensions_like_python(tmp_path):
    """#842: a dimension present in only one dataset gets a dimension,present_in row
    in both writers, in the same position and order."""
    from faircode.report import compare_to_csv

    path_a = tmp_path / "a.csv"
    path_a.write_text("sex,race\n" + "\n".join(f"{'m' if i % 2 else 'f'},{'x' if i % 3 else 'y'}" for i in range(60)) + "\n")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex,region\n" + "\n".join(f"{'m' if i % 2 else 'f'},{'n' if i % 3 else 's'}" for i in range(60)) + "\n")

    src = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")
    csvs = src[src.index("var csvRow = E.csvRow"):src.index("async function downloadCompareCsvReport")]
    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;" + csvs +
        "function load(p){return E.parseCSV(fs.readFileSync(p,'utf-8'));}"
        "var pa=E.profile(load(process.argv[2]),{},{}),pb=E.profile(load(process.argv[3]),{},{});"
        "process.stdout.write(buildCompareCsvReport(E.compare(pa,pb,'a.csv','b.csv')));"
    )
    web = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(path_a), str(path_b)],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    py = compare_to_csv(compare(profile(pd.read_csv(path_a)), profile(pd.read_csv(path_b)), "a.csv", "b.csv"))
    section = "\n\ndimension,present_in\nrace,a_only\nregion,b_only\n\nflag\n"
    assert section in web.replace("\r\n", "\n")
    assert section in py.replace("\r\n", "\n")


def test_compare_view_download_csv_and_proxy_controls_are_wired():
    """#789: the compare view's new controls exist in profiler.html and are
    bound in profiler-compare.js; renaming an id in either file would
    otherwise break the buttons with the suite green. Also covers the
    --proxy-alpha inputs (#786) for both views."""
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")
    for element_id in ("compareDownloadCsvBtn", "compareProxyHintsBtn",
                       "compareProxyHintsBlock", "compareProxyHintsResults",
                       "compareProxyAlphaInput", "proxyAlphaInput"):
        assert f'id="{element_id}"' in html, element_id
        if element_id != "proxyAlphaInput":
            assert f"getElementById('{element_id}')" in js, element_id
    assert "downloadCsvBtn.addEventListener('click', downloadCompareCsvReport)" in js
    assert "proxyBtn.addEventListener('click', renderCompareProxyHints)" in js
    assert "E.proxyHints(slot.A.table, currentProfiles.A.dimensions, alpha, heldA, correction, currentOpts.max_age, currentOpts.age_reference_year, exact)" in js
    assert 'id="compareProxyCorrectionInput"' in html


def test_web_and_python_csv_exports_defuse_formula_labels_identically(tmp_path):
    """#791: a label like =1+1 is written with a leading ' by both engines, and
    both still agree on the whole file (#790: one shared helper)."""
    from faircode.report import to_csv

    rows = ["sex"] + ["=1+1"] * 30 + ["male"] * 30
    path = tmp_path / "inj.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    web = _run_ui_exports(path, False)["csv"]
    py = to_csv(dict(profile(pd.read_csv(path))))
    assert "'=1+1" in web and "'=1+1" in py
    assert web.replace("\r\n", "\n") == py.replace("\r\n", "\n")


def test_python_js_proxy_hints_held_out_column_parity(tmp_path):
    """#781: the web proxyHints(..., heldOut) flags a dropped column (race)
    against a surviving proxy (zip_code) like proxy_hints(held_out=...), and
    parseHeldOut enforces the same row-count/collision rules."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints

    zip_code = ["111"] * 40 + ["222"] * 40
    race = ["A"] * 40 + ["B"] * 40
    kept = tmp_path / "kept.csv"
    kept.write_text("zip_code,sex\n" + "\n".join(
        f"{z},{'m' if i % 2 else 'f'}" for i, z in enumerate(zip_code)) + "\n", encoding="utf-8")
    full = tmp_path / "full.csv"
    full.write_text("race\n" + "\n".join(race) + "\n", encoding="utf-8")
    short = tmp_path / "short.csv"
    short.write_text("race\nA\nB\n", encoding="utf-8")

    df = pd.read_csv(kept)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    py = proxy_hints(df, dims, held_out={"race": pd.read_csv(full)["race"]})

    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "function load(p){return E.parseCSV(fs.readFileSync(p,'utf-8'));}"
        "var t=load(process.argv[2]),h=load(process.argv[3]),s=load(process.argv[4]);"
        "var r=E.profile(t,{},{});var out={};"
        "out.hints=E.proxyHints(t,r.dimensions,0.05,{race:E.parseHeldOut(h,'race',t)});"
        "try{E.parseHeldOut(s,'race',t)}catch(e){out.short=e.message}"
        "try{E.parseHeldOut(h,'zip_code',t)}catch(e){out.missing=e.message}"
        "try{E.proxyHints(t,r.dimensions,0)}catch(e){out.alpha=e.message}"
        "process.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"),
         str(kept), str(full), str(short)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    js = json.loads(done.stdout)

    py_pair = next(h for h in py if {h["a"], h["b"]} == {"zip_code", "race"})
    js_pair = next(h for h in js["hints"] if {h["a"], h["b"]} == {"zip_code", "race"})
    assert py_pair["chi2"] == js_pair["chi2"] and py_pair["cramers_v"] == js_pair["cramers_v"]
    assert "rows must align 1:1" in js["short"]
    assert "not found" in js["missing"]
    assert "alpha must be in (0, 1]" in js["alpha"]


def test_python_js_proxy_correction_parity(tmp_path):
    """#806: the JS adjustPValues/proxyHints(correction) match faircode.proxy for
    both methods, and the HTML/CSV exports show the adjusted p-value."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import adjust_p_values, proxy_hints

    n = 120
    sex = ["m", "f"] * (n // 2)
    rows = ["sex,race,age"]
    for i in range(n):
        race = "a" if (i % 2 == 0) == (i % 10 != 0) else "b"
        age = 55 if (sex[i] == "m" and i % 3 == 0) or i % 11 == 0 else 25
        rows.append(f"{sex[i]},{race},{age}")
    path = tmp_path / "three.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    df = pd.read_csv(path)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]

    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var r=E.profile(t,{},{});"
        "var out={};['bonferroni','holm'].forEach(function(m){"
        "out[m]=E.proxyHints(t,r.dimensions,1,null,m);});"
        "try{E.proxyHints(t,r.dimensions,0.05,null,'fdr')}catch(e){out.bad=e.message}"
        "process.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    js = json.loads(done.stdout)
    for method in ("bonferroni", "holm"):
        py = proxy_hints(df, dims, alpha=1.0, correction=method)
        key = lambda h: (h["a"], h["b"])  # noqa: E731
        py_map = {key(h): h["p_adjusted"] for h in py}
        js_map = {key(h): h["p_adjusted"] for h in js[method]}
        assert py_map.keys() == js_map.keys() and py_map
        for k in py_map:
            assert py_map[k] == pytest.approx(js_map[k], rel=1e-6)
    assert "correction must be" in js["bad"]
    assert adjust_p_values([0.01, 0.04, 0.03], "holm") == pytest.approx([0.03, 0.06, 0.06])


def test_adjust_p_values_js_parity_ties_and_edge_cases():
    """#820: verify that JS adjustPValues exactly matches Python adjust_p_values
    for ties (breaking ties stably in input order), single tested pair (m=1), and empty input (m=0)."""
    from faircode.proxy import adjust_p_values

    cases = [
        ([], "bonferroni"),
        ([], "holm"),
        ([0.042], "bonferroni"),
        ([0.042], "holm"),
        ([0.8], "bonferroni"),
        ([0.8], "holm"),
        ([0.02, 0.02, 0.04], "holm"),
        ([0.05, 0.01, 0.01, 0.03], "holm"),
        ([0.03, 0.03], "bonferroni"),
        ([0.03, 0.03], "holm"),
        ([0.1, 0.1, 0.1], "holm"),
        ([0.01, 0.04, 0.03], "bonferroni"),
        ([0.01, 0.04, 0.03], "holm"),
    ]

    script = (
        "require(process.argv[1]);var E=globalThis.FairCodeProfiler;"
        "var cases=JSON.parse(process.argv[2]);"
        "var results=cases.map(function(c){return E.adjustPValues(c[0],c[1]);});"
        "process.stdout.write(JSON.stringify(results));"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), json.dumps(cases)],
        capture_output=True, text=True, encoding="utf-8", check=True
    )
    js_results = json.loads(done.stdout)
    for (ps, method), js_res in zip(cases, js_results):
        py_res = adjust_p_values(ps, method)
        assert js_res == pytest.approx(py_res), f"Mismatch for {ps} with {method}: JS={js_res}, PY={py_res}"



def test_web_csv_includes_the_reference_section_like_python(tmp_path):
    """#805: after scoring against a reference baseline, the browser CSV carries
    the same expected/actual/delta/deviation section as faircode's to_csv()."""
    from faircode.report import to_csv

    rows = ["sex"] + ["male"] * 45 + ["female"] * 15
    path = tmp_path / "ref.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    reference = {"sex": {"male": 0.5, "female": 0.5}}
    web = _run_ui_exports(path, False, reference)["csv"]
    py = to_csv(dict(profile(pd.read_csv(path), None, {"reference": reference})))
    assert "reference_label" in web
    assert web.replace("\r\n", "\n") == py.replace("\r\n", "\n")


def test_web_and_python_csv_provenance_sections_are_identical(tmp_path):
    """#800: the same provenance dict renders to the same CSV section in both
    engines - dotted keys for nested objects, JSON text for lists, empty for null."""
    from faircode.report import to_csv

    path = _sex_race_csv(tmp_path)
    prov = {"faircode_version": "2.3.0", "dataset_hash": None, "dataset_hash_note": "from stdin",
            "params": {"min_share": 0.05, "cross": ["sex", "race"], "reference_flag": 0.05},
            "overrides": {"zip": "geography"}}
    web = _run_ui_exports(path, False, None, prov)["csv"]
    py = to_csv(dict(profile(pd.read_csv(path))), provenance=prov)
    assert "provenance_key,provenance_value" in web
    assert "params.cross,\"[\"\"sex\"\", \"\"race\"\"]\"" in web
    assert web.replace("\r\n", "\n") == py.replace("\r\n", "\n")
    assert "provenance_key" not in _run_ui_exports(path, False)["csv"]


def test_web_and_python_csv_provenance_render_held_out_entries_identically(tmp_path):
    """#811: a list of {path, column, sha256} objects renders the same text in both
    engines, including a non-ASCII path (Python json.dumps escapes it)."""
    from faircode.report import to_csv

    path = _sex_race_csv(tmp_path)
    prov = {"faircode_version": "2.3.0", "dataset_hash": "sha256:ab",
            "params": {"min_share": 0.05}, "overrides": {},
            "proxy_hints_with": [
                {"path": "données/race.csv", "column": "race", "sha256": "sha256:cd"},
                {"path": "-", "column": "age", "sha256": None, "sha256_note": "read from stdin"}]}
    web = _run_ui_exports(path, False, None, prov)["csv"]
    py = to_csv(dict(profile(pd.read_csv(path))), provenance=prov)
    assert "proxy_hints_with" in web
    assert web.replace("\r\n", "\n") == py.replace("\r\n", "\n")


def test_held_out_rows_control_is_wired_into_profile_and_compare_views():
    """#801-#803: rows (any number, per dataset in compare) replace the old
    single file+column inputs; profiler.html loads the shared control first."""
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")
    for element_id in ("heldOutRows", "heldOutAddBtn", "compareHeldOutRowsA",
                       "compareHeldOutAddA", "compareHeldOutRowsB", "compareHeldOutAddB"):
        assert f'id="{element_id}"' in html, element_id
    assert 'id="heldOutFileInput"' not in html
    assert html.index("profiler-heldout.js") < html.index("profiler-ui.js")
    assert html.index("profiler-heldout.js") < html.index("profiler-compare.js")
    ui = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")
    cmp_js = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")
    assert "E.buildHeldOut(specs, currentTable, heldNotes)" in ui
    assert "E.buildHeldOut(specsA, slot.A.table, heldNotes)" in cmp_js
    assert "E.buildHeldOut(specsB, slot.B.table, heldNotes)" in cmp_js
    control = (REPO_ROOT / "assets" / "profiler-heldout.js").read_text(encoding="utf-8")
    assert ".xlsx" in control and "file.arrayBuffer()" in control


def test_build_held_out_handles_several_columns_formats_and_collisions(tmp_path):
    """#801/#802: buildHeldOut() merges several files (csv, json, and .xlsx via the
    first-sheet reader - stubbed here so no CDN is needed) into one map, and
    rejects a column named twice like the CLI's repeated --proxy-hints-with."""
    main_csv = tmp_path / "main.csv"
    main_csv.write_text("zip\n111\n111\n222\n222\n", encoding="utf-8")
    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "globalThis.XLSX={read:function(){return {SheetNames:['S'],Sheets:{S:{}}}},"
        "utils:{sheet_to_json:function(){return [{age:'old'},{age:'old'},{age:'young'},{age:'young'}]}}};"
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var out={};"
        "(async function(){"
        "out.map=await E.buildHeldOut(["
        "{name:'a.csv',column:'race',data:'race\\nA\\nA\\nB\\nB\\n'},"
        "{name:'b.json',column:'sex',data:JSON.stringify([{sex:'m'},{sex:'f'},{sex:'m'},{sex:'f'}])},"
        "{name:'c.xlsx',column:'age',data:new ArrayBuffer(1)}],t);"
        "try{await E.buildHeldOut([{name:'a.csv',column:'race',data:'race\\nA\\nA\\nB\\nB\\n'},"
        "{name:'z.csv',column:'race',data:'race\\nA\\nA\\nB\\nB\\n'}],t)}catch(e){out.dup=e.message}"
        "process.stdout.write(JSON.stringify(out));})();"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(main_csv)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    assert out["map"] == {"race": ["A", "A", "B", "B"], "sex": ["m", "f", "m", "f"],
                          "age": ["old", "old", "young", "young"]}
    assert "already supplied" in out["dup"]


def test_build_held_out_reports_ignored_xlsx_sheets(tmp_path):
    """#816: only the first sheet of a held-out workbook is read; the notes array gets
    an ignored-sheets line, and a column that lives on a later sheet gets an error
    that names the skipped sheets instead of a bare "not found"."""
    main_csv = tmp_path / "main.csv"
    main_csv.write_text("zip\n111\n111\n222\n222\n", encoding="utf-8")
    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "globalThis.XLSX={read:function(){return {SheetNames:['First','Second','Third'],Sheets:{First:{},Second:{},Third:{}}}},"
        "utils:{sheet_to_json:function(){return [{age:'old'},{age:'old'},{age:'young'},{age:'young'}]}}};"
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var out={notes:[]};"
        "(async function(){"
        "out.map=await E.buildHeldOut([{name:'c.xlsx',column:'age',data:new ArrayBuffer(1)}],t,out.notes);"
        "try{await E.buildHeldOut([{name:'c.xlsx',column:'race',data:new ArrayBuffer(1)}],t,[])}"
        "catch(e){out.err=e.message}"
        "out.plain=await E.buildHeldOut([{name:'a.csv',column:'race',data:'race\\nA\\nA\\nB\\nB\\n'}],t);"
        "process.stdout.write(JSON.stringify(out));})();"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(main_csv)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    assert out["map"] == {"age": ["old", "old", "young", "young"]}
    assert out["notes"] == ["c.xlsx: only the first sheet 'First' was read; 'Second', 'Third' ignored"]
    assert "not found" in out["err"] and "'Second', 'Third' ignored" in out["err"]
    assert out["plain"] == {"race": ["A", "A", "B", "B"]}


def test_build_held_out_joins_on_a_key_like_python(tmp_path):
    """#822: a PATH=COLUMN:KEY held-out file is matched on the key, not row order, and
    both engines reject the same bad inputs."""
    pytest.importorskip("pandas")
    from faircode.proxy import parse_held_out_specs

    main_csv = tmp_path / "main.csv"
    main_csv.write_text("id,zip\n1,111\n2,111\n3,222\n4,222\n", encoding="utf-8")
    held_csv = tmp_path / "held.csv"
    held_csv.write_text("id,race\n4,B\n2,A\n3,B\n1,A\n9,Z\n", encoding="utf-8")
    df = pd.read_csv(main_csv)
    py = parse_held_out_specs([f"{held_csv}=race:id"], df, pd.read_csv)
    assert list(py["race"]) == ["A", "A", "B", "B"]

    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var out={};"
        "var held=fs.readFileSync(process.argv[3],'utf-8');"
        "(async function(){"
        "out.ok=await E.buildHeldOut([{name:'h.csv',column:'race',key:'id',data:held}],t);"
        "async function err(name,spec,data){try{await E.buildHeldOut([spec],t)}catch(e){out[name]=e.message}}"
        "await err('missing_key',{name:'h.csv',column:'race',key:'nope',data:held});"
        "await err('dup',{name:'h.csv',column:'race',key:'id',data:'id,race\\n1,A\\n1,B\\n2,A\\n3,A\\n4,A\\n'});"
        "await err('unmatched',{name:'h.csv',column:'race',key:'id',data:'id,race\\n1,A\\n2,A\\n'});"
        "await err('positional',{name:'h.csv',column:'race',data:held});"
        "process.stdout.write(JSON.stringify(out));})();"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"),
         str(main_csv), str(held_csv)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    assert out["ok"] == {"race": ["A", "A", "B", "B"]}
    assert "not found in the profiled dataset" in out["missing_key"]
    assert "duplicate" in out["dup"]
    assert "no row for 2 key(s)" in out["unmatched"]
    assert "rows must align 1:1" in out["positional"]


def test_python_js_exact_p_values_agree_for_small_cell_tables(tmp_path):
    """#861: with exact on, a sparse 2x2 gets Fisher's exact p and a sparse 6x2 a seeded
    permutation p - identical PRNG stream, so both engines return the same numbers."""
    pytest.importorskip("scipy")
    from faircode.detect import detect_columns
    from faircode.proxy import proxy_hints

    rows = ["sex,race"]
    # 2x2, small: sex x group
    for i in range(14):
        rows.append(f"{'male' if i < 5 else 'female'},{'x' if (i % 7) < 3 else 'y'}")
    csv = tmp_path / "small2x2.csv"
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    df = pd.read_csv(csv)
    dims = [{"name": d["name"], "kind": d["kind"]} for d in detect_columns(df)]
    py = proxy_hints(df, dims, alpha=1.0, exact=True)
    js = _run_js_proxy_hints(csv, alpha=1.0, exact=True)
    assert len(py) == len(js) == 1 and py[0]["p_method"] == js[0]["p_method"] == "fisher"
    assert py[0]["p_value"] == pytest.approx(js[0]["p_value"], rel=1e-9)
    assert py[0]["p_chi2"] == pytest.approx(js[0]["p_chi2"], rel=1e-6)

    rows = ["sex,race"]
    races = ["White", "Black", "Asian", "Latino", "Other", "Native"]
    for i in range(24):
        rows.append(f"{'male' if i % 2 == 0 else 'female'},{races[(i // 2 + i) % 6]}")
    csv2 = tmp_path / "sparse6x2.csv"
    csv2.write_text("\n".join(rows) + "\n", encoding="utf-8")
    df2 = pd.read_csv(csv2)
    py2 = proxy_hints(df2, dims, alpha=1.0, exact=True)
    js2 = _run_js_proxy_hints(csv2, alpha=1.0, exact=True)
    assert py2[0]["p_method"] == js2[0]["p_method"] == "permutation"
    assert py2[0]["p_value"] == js2[0]["p_value"]          # same seeded stream, same count

    # off by default: no p_method key, p-values untouched
    assert "p_method" not in proxy_hints(df2, dims, alpha=1.0)[0]
    assert "p_method" not in _run_js_proxy_hints(csv2, alpha=1.0)[0]


def test_build_held_out_composite_and_normalised_keys_match_python(tmp_path):
    """#859: PATH=COLUMN:id+visit joins on two columns, and opt-in normalisation
    (trim, case, leading zeros) matches in both engines; exact matching stays the default."""
    from faircode.proxy import parse_held_out_specs

    main_csv = tmp_path / "main.csv"
    main_csv.write_text("id,visit,zip\n007,v1,111\n007,v2,111\nB2,v1,222\nB2,v2,222\n", encoding="utf-8")
    held_csv = tmp_path / "held.csv"
    held_csv.write_text("id,visit,race\n 7,V2,y\n7,V1,x\nb2,v1,z\nB2 ,v2,w\n", encoding="utf-8")
    df = pd.read_csv(main_csv, dtype=str)
    read = lambda p: pd.read_csv(p, dtype=str, keep_default_na=False)
    py = parse_held_out_specs([f"{held_csv}=race:id+visit"], df, read, normalize_keys=True)
    assert list(py["race"]) == ["x", "y", "z", "w"]
    import pytest as _pt
    with _pt.raises(ValueError, match="no row for"):
        parse_held_out_specs([f"{held_csv}=race:id+visit"], df, read)

    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;"
        "var t=E.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));var held=fs.readFileSync(process.argv[3],'utf-8');"
        "var out={};(async function(){"
        "out.ok=await E.buildHeldOut([{name:'h.csv',column:'race',key:'id+visit',normalize:true,data:held}],t);"
        "try{await E.buildHeldOut([{name:'h.csv',column:'race',key:'id+visit',data:held}],t)}catch(e){out.exact=e.message}"
        "out.norm=['  A01 ','a01','0042','000','x'].map(E.normalizeKeyText);"
        "process.stdout.write(JSON.stringify(out));})();"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(main_csv), str(held_csv)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    assert out["ok"] == {"race": ["x", "y", "z", "w"]}
    assert "no row for" in out["exact"]
    from faircode.proxy import normalize_key_text
    assert out["norm"] == [normalize_key_text(v) for v in ["  A01 ", "a01", "0042", "000", "x"]] == ["a01", "a01", "42", "0", "x"]


def test_held_out_control_adds_rows_collects_specs_and_validates():
    """Drives the real assets/profiler-heldout.js through a minimal DOM stub:
    rows can be added/removed, filled rows become specs ({name, column, data},
    xlsx as an ArrayBuffer), empty rows are skipped, half-filled rows throw."""
    script = r"""
    function El(tag){this.tag=tag;this.children=[];this.listeners={};this.value='';this.files=[];
      this.attrs={};}
    El.prototype.appendChild=function(c){this.children.push(c);c.parent=this;return c;};
    El.prototype.removeChild=function(c){this.children.splice(this.children.indexOf(c),1);};
    El.prototype.setAttribute=function(k,v){this.attrs[k]=v;};
    El.prototype.addEventListener=function(t,f){(this.listeners[t]=this.listeners[t]||[]).push(f);};
    El.prototype.click=function(){(this.listeners.click||[]).forEach(function(f){f();});};
    El.prototype.querySelectorAll=function(sel){var out=[];(function walk(n){n.children.forEach(function(c){
      if(c.tag===sel)out.push(c);walk(c);});})(this);return out;};
    global.document={createElement:function(t){return new El(t);}};
    global.window=global;
    require(process.argv[1]);
    var container=new El('div'),addBtn=new El('button');
    var ctl=FairCodeHeldOut.init(container,addBtn,'held-out');
    (async function(){
      var out={rows_initial:container.children.length};
      addBtn.click();addBtn.click();out.rows_after_add=container.children.length;
      function inputs(i){return container.children[i].querySelectorAll('input');}
      function fileOf(name,text){return {name:name,text:async function(){return text;},
        arrayBuffer:async function(){return 'AB:'+name;}};}
      inputs(0)[0].files=[fileOf('a.csv','race\nA\n')];inputs(0)[1].value=' race ';
      inputs(2)[0].files=[fileOf('b.xlsx','')];inputs(2)[1].value='age';
      out.specs=await ctl.collect();   // middle row empty -> skipped
      inputs(1)[1].value='orphan';
      try{await ctl.collect();}catch(e){out.half=e.message;}
      inputs(1)[1].value='';
      container.children[2].children[4].click();       // remove row 3
      out.rows_after_remove=container.children.length;
      ctl.reset();
      out.rows_after_reset=container.children.length;
      out.specs_after_reset=await ctl.collect();
      process.stdout.write(JSON.stringify(out));
    })();
    """
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-heldout.js")],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    assert out["rows_initial"] == 1 and out["rows_after_add"] == 3
    assert out["specs"] == [
        {"name": "a.csv", "column": "race", "data": "race\nA\n", "file": {"name": "a.csv"}},
        {"name": "b.xlsx", "column": "age", "data": "AB:b.xlsx", "file": {"name": "b.xlsx"}}]
    assert "needs both a file and a column name" in out["half"]
    assert out["rows_after_remove"] == 2
    assert out["rows_after_reset"] == 1 and out["specs_after_reset"] == []



@pytest.mark.parametrize("name,text", [
    ("duplicate_headers", "sex,sex,race\nM,F,A\nM,F,B\nM,F,A\nF,M,B\n"),
    ("duplicate_headers_colliding_suffix", "a,a,a,a.1\n1,2,3,4\n"),
    ("quoted_empty_single_column_row", 'region\r\n""\r\nN\r\nS\r\n'),
    ("quoted_empty_last_line", 'region\r\nN\r\n""'),
    ("non_ascii_digit_ages", "age\n٣٠\n25\n40\n٣٠\n"),
])
def test_python_js_parity_on_parser_edge_cases(tmp_path, name, text):
    """#834 (pandas-style header de-duplication), #835 (a quoted-empty row is a
    missing value, not a blank line) and #836 (only ASCII digits are ages):
    the CSV parsers and the profile of the result agree on each."""
    path = tmp_path / f"{name}.csv"
    path.write_text(text, encoding="utf-8", newline="")
    df = pd.read_csv(path)
    script = (
        "require(process.argv[1]);var fs=require('fs');"
        "var t=globalThis.FairCodeProfiler.parseCSV(fs.readFileSync(process.argv[2],'utf-8'));"
        "process.stdout.write(JSON.stringify({columns:t.columns,n:t.rows.length}));"
    )
    parsed = json.loads(subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert parsed["columns"] == list(df.columns)
    assert parsed["n"] == len(df)

    js = json.loads(subprocess.run(
        ["node", "scripts/engine-js.js", "profile", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    py = dict(profile(df))
    js.pop("flags", None)
    py.pop("flags", None)
    assert js == py


def test_web_decode_text_matches_python_loaders_and_names_the_encoding(tmp_path):
    """#857: decodeText() reads latin-1/cp1252/UTF-16/UTF-32/BOM'd UTF-8 like faircode.loaders
    and reports the encoding provenance should record (None for plain UTF-8)."""
    from faircode.loaders import read_table

    text = "sex,race\nM,Café\nF,Señor\n"
    cases = {
        "latin.csv": (text.encode("latin-1"), "latin-1", "latin-1"),
        "cp.csv": (text.encode("cp1252"), "cp1252", "cp1252"),
        "u16.csv": (text.encode("utf-16"), "auto", "utf-16"),
        "u16be.csv": (b"\xfe\xff" + text.encode("utf-16-be"), "auto", "utf-16"),
        "u32.csv": (text.encode("utf-32"), "auto", "utf-32"),
        "bom8.csv": (text.encode("utf-8-sig"), "auto", "utf-8-sig"),
        "plain.csv": (text.encode("utf-8"), "auto", None),
        "explicit8.csv": (text.encode("utf-8"), "utf-8", "utf-8"),
    }
    paths = {}
    for name, (raw, _choice, _enc) in cases.items():
        paths[name] = tmp_path / name
        paths[name].write_bytes(raw)
    spec = {name: [str(paths[name]), choice] for name, (_r, choice, _e) in cases.items()}
    script = (
        "require(process.argv[1]);var fs=require('fs');var E=globalThis.FairCodeProfiler;var out={};"
        "var spec=JSON.parse(process.argv[2]);Object.keys(spec).forEach(function(n){"
        "var b=fs.readFileSync(spec[n][0]);var ab=b.buffer.slice(b.byteOffset,b.byteOffset+b.length);"
        "var d=E.decodeText(ab,spec[n][1]);out[n]={text:d.text,encoding:d.encoding}});"
        "process.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run(
        ["node", "-e", script, str(REPO_ROOT / "assets" / "profiler-engine.js"), json.dumps(spec)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    out = json.loads(done.stdout)
    for name, (_raw, choice, enc) in cases.items():
        assert out[name]["text"] == text, name
        assert out[name]["encoding"] == enc, name
        py = read_table(str(paths[name]), encoding=None if choice == "auto" else choice)
        assert list(py["race"]) == ["Café", "Señor"], name


def test_web_encoding_picker_is_wired_and_recorded_in_provenance():
    html = (REPO_ROOT / "profiler.html").read_text(encoding="utf-8")
    for select_id in ("encodingSelect", "compareEncodingSelect"):
        assert f'id="{select_id}"' in html
    for value in ("auto", "utf-8", "utf-16", "cp1252", "latin-1"):
        assert html.count(f'<option value="{value}"') >= 2, value
    ui = (REPO_ROOT / "assets" / "profiler-ui.js").read_text(encoding="utf-8")
    cmp_js = (REPO_ROOT / "assets" / "profiler-compare.js").read_text(encoding="utf-8")
    assert "E.decodeText(reader.result" in ui and "E.decodeText(reader.result" in cmp_js
    assert "readAsText(" not in ui.split("function readFile")[1].split("function runText")[0]
    assert "provenance.encoding = currentEncoding" in ui
    assert "provenance.encoding_a = slot.A.encoding" in cmp_js and "provenance.encoding_b = slot.B.encoding" in cmp_js
    held = (REPO_ROOT / "assets" / "profiler-heldout.js").read_text(encoding="utf-8")
    assert "decodeText" in held
