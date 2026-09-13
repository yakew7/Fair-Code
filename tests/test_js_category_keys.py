"""Category labels must be data, even when they name JavaScript properties."""

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from faircode import compare, profile
from faircode.profiler import parse_reference

ROOT = Path(__file__).resolve().parent.parent
PROPERTY_NAMES = ["__proto__", "constructor", "toString", "hasOwnProperty"]


def js_result(script, data):
    completed = subprocess.run(
        ["node", "-e", "const fs=require('fs');require('./assets/profiler-engine.js');"
         "const E=globalThis.FairCodeProfiler;"
         "const data=JSON.parse(fs.readFileSync(0,'utf8'));" + script],
        input=json.dumps(data), cwd=ROOT, text=True, encoding="utf-8",
        capture_output=True, check=True,
    )
    return json.loads(completed.stdout)


def structured(result):
    return {key: value for key, value in result.items() if key != "flags"}


@pytest.mark.parametrize("label", PROPERTY_NAMES)
@pytest.mark.parametrize("column", ["sex", "segment", "age"])
def test_property_named_categories_match_python(label, column):
    # segment exercises automatic categorical detection; age exercises the
    # numeric-band plus free-text-sentinel path. Both intersection axes use
    # the property-named label and include absent cross-product cells.
    ordinary = "25" if column == "age" else "Male"
    df = pd.DataFrame({
        column: [ordinary] * 3 + [label] * 3 + ["Female"] * 2,
        "race": ["White"] * 3 + [label] * 3 + ["Black"] * 2,
    })
    actual = js_result(
        "process.stdout.write(JSON.stringify(E.profile(E.parseCSV(data))));",
        df.to_csv(index=False),
    )
    expected = profile(df)
    assert structured(actual) == structured(expected)
    assert actual["dimensions"][0]["n_groups"] == 3
    special = next(g for g in actual["dimensions"][0]["groups"] if g["label"] == label)
    assert special["count"] == 3
    assert special["share"] == 3 / 8


@pytest.mark.parametrize("label", PROPERTY_NAMES)
def test_property_named_categories_preserve_reference_and_drift(label):
    a = pd.DataFrame({"sex": [label] * 3 + ["Female"] * 5})
    b = pd.DataFrame({"sex": [label] * 5 + ["Male"] * 3})
    ref = pd.DataFrame({"column": ["sex", "sex"],
                        "group": [label, "Female"], "share": [0.5, 0.5]})
    expected_reference = parse_reference(ref)
    result = js_result(
        "const ref=E.parseReference(E.parseCSV(data.reference));"
        "const a=E.profile(E.parseCSV(data.a),null,{reference:ref});"
        "const b=E.profile(E.parseCSV(data.b));"
        "process.stdout.write(JSON.stringify({reference:ref,profile:a,"
        "comparison:E.compare(a,b,'A','B')}));",
        {"a": a.to_csv(index=False), "b": b.to_csv(index=False),
         "reference": ref.to_csv(index=False)},
    )
    expected_a = profile(a, opts={"reference": expected_reference})
    assert result["reference"] == expected_reference
    assert structured(result["profile"]) == structured(expected_a)
    assert structured(result["comparison"]) == structured(compare(expected_a, profile(b), "A", "B"))


def test_property_named_category_counts_toward_detection_threshold():
    df = pd.DataFrame({"segment": ["normal", "__proto__"]})
    actual = js_result(
        "process.stdout.write(JSON.stringify(E.profile(E.parseCSV(data))));",
        df.to_csv(index=False),
    )
    assert structured(actual) == structured(profile(df))
    assert len(actual["dimensions"]) == 1


@pytest.mark.parametrize("label", PROPERTY_NAMES)
def test_property_named_category_absent_from_reference_is_zero(label):
    df = pd.DataFrame({"sex": [label, "Female"]})
    reference = {"sex": {"Female": 1}}
    actual = js_result(
        "process.stdout.write(JSON.stringify(E.profile(E.parseCSV(data.csv),"
        "null,{reference:data.reference})));",
        {"csv": df.to_csv(index=False), "reference": reference},
    )
    assert structured(actual) == structured(profile(df, opts={"reference": reference}))


@pytest.mark.parametrize("label", PROPERTY_NAMES)
def test_property_named_age_category_is_not_a_numeric_age_band(label):
    a = pd.DataFrame({"age": [label, label]})
    b = pd.DataFrame({"age": ["25", "35"]})
    actual = js_result(
        "process.stdout.write(JSON.stringify(E.compare("
        "E.profile(E.parseCSV(data.a)),E.profile(E.parseCSV(data.b)),'A','B')));",
        {"a": a.to_csv(index=False), "b": b.to_csv(index=False)},
    )
    expected = compare(profile(a), profile(b), "A", "B")
    assert expected["dimensions"][0]["kind_mismatch"] is True
    assert structured(actual) == structured(expected)
