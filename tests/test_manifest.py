"""Tests for audit.yaml loading/validation (faircode.manifest).

Run from the repo root:  pytest tests/ -q
"""

from pathlib import Path

import pandas as pd
import pytest

yaml = pytest.importorskip("yaml", reason="manifest loading needs the optional pyyaml extra")

from faircode.manifest import (
    Manifest,
    ProtectedAttribute,
    RowFilter,
    TargetSpec,
    discover_manifests,
    load_manifest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_manifest(tmp_path, data):
    path = tmp_path / "audit.yaml"
    path.write_text(yaml.dump(data))
    return path


def _minimal_manifest_dict(**overrides):
    data = {
        "name": "toy",
        "dataset": {"path": "toy.csv"},
        "target": {"column": "label", "method": "binary"},
        "protected_attributes": [
            {"name": "group", "type": "categorical", "column": "group",
             "disadvantaged_values": ["a"], "advantaged_values": ["b"]},
        ],
        "core_features": ["x1", "x2"],
    }
    data.update(overrides)
    return data


# ── Loading a well-formed manifest ───────────────────────────────────────────
def test_load_minimal_manifest(tmp_path):
    path = _write_manifest(tmp_path, _minimal_manifest_dict())
    manifest = load_manifest(path)
    assert manifest.name == "toy"
    assert manifest.title == "toy"   # defaults to name when not given
    assert manifest.dataset_path == tmp_path / "toy.csv"
    assert manifest.core_features == ["x1", "x2"]
    assert manifest.proxy_features == []   # optional, defaults to empty
    assert manifest.random_state == 42     # documented default
    assert manifest.test_size == 0.2
    assert len(manifest.protected_attributes) == 1


def test_manifest_defaults_are_overridable(tmp_path):
    path = _write_manifest(tmp_path, _minimal_manifest_dict(
        title="Toy Audit", random_state=7, test_size=0.3, proxy_features=["p1"]))
    manifest = load_manifest(path)
    assert manifest.title == "Toy Audit"
    assert manifest.random_state == 7
    assert manifest.test_size == 0.3
    assert manifest.proxy_features == ["p1"]


# ── Failing loudly on bad input ──────────────────────────────────────────────
def test_malformed_yaml_syntax_raises(tmp_path):
    path = tmp_path / "audit.yaml"
    path.write_text("name: toy\n  bad_indent: [unclosed\n")
    with pytest.raises(yaml.YAMLError):
        load_manifest(path)


def test_missing_required_target_raises(tmp_path):
    data = _minimal_manifest_dict()
    del data["target"]
    path = _write_manifest(tmp_path, data)
    with pytest.raises(KeyError):
        load_manifest(path)


def test_missing_required_name_raises(tmp_path):
    data = _minimal_manifest_dict()
    del data["name"]
    path = _write_manifest(tmp_path, data)
    with pytest.raises(KeyError):
        load_manifest(path)


def test_empty_protected_attributes_raises(tmp_path):
    path = _write_manifest(tmp_path, _minimal_manifest_dict(protected_attributes=[]))
    with pytest.raises(ValueError, match="protected_attributes"):
        load_manifest(path)


def test_unknown_target_method_fails_loudly():
    spec = TargetSpec(column="x", method="not_a_real_method")
    df = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(ValueError, match="unknown target method"):
        spec.compute(df)


def test_unknown_protected_attribute_type_fails_loudly():
    pa = ProtectedAttribute(name="g", type="not_a_real_type", column="g")
    df = pd.DataFrame({"g": [1, 2, 3]})
    with pytest.raises(ValueError, match="unknown protected attribute type"):
        pa.disadvantaged_mask(df)


def test_categorical_protected_attribute_needs_a_values_list():
    pa = ProtectedAttribute(name="g", type="categorical", column="g")
    df = pd.DataFrame({"g": ["a", "b"]})
    with pytest.raises(ValueError, match="need disadvantaged_values or advantaged_values"):
        pa.disadvantaged_mask(df)


# ── TargetSpec / RowFilter / ProtectedAttribute behaviour ───────────────────
def test_target_spec_methods():
    df = pd.DataFrame({"income": [10, 60, 30, 90], "flag": ["yes", "no", "yes", "no"]})
    assert TargetSpec("income", "above_median").compute(df).tolist() == [0, 1, 0, 1]
    assert TargetSpec("flag", "equals", value="yes").compute(df).tolist() == [1, 0, 1, 0]
    assert TargetSpec("flag", "isin", values=["yes"]).compute(df).tolist() == [1, 0, 1, 0]


def test_row_filter_isin_and_notna():
    df = pd.DataFrame({"race": ["A", "B", "C", None]})
    kept = RowFilter(column="race", isin=["A", "B"]).apply(df)
    assert kept["race"].tolist() == ["A", "B"]
    kept = RowFilter(column="race", notna=True).apply(df)
    assert len(kept) == 3


def test_protected_attribute_categorical_complement():
    # Only advantaged_values given -> disadvantaged is "everything else".
    pa = ProtectedAttribute(name="g", type="categorical", column="g", advantaged_values=["white"])
    df = pd.DataFrame({"g": ["white", "black", "asian"]})
    disadv, known = pa.disadvantaged_mask(df)
    assert disadv.tolist() == [False, True, True]
    assert known.all()


def test_protected_attribute_numeric_threshold():
    pa = ProtectedAttribute(name="age", type="numeric_threshold", column="age",
                            threshold=30, disadvantaged="below")
    df = pd.DataFrame({"age": [20, 30, 40, None]})
    disadv, known = pa.disadvantaged_mask(df)
    assert disadv.tolist() == [True, False, False, False]
    assert known.tolist() == [True, True, True, False]


def test_protected_attribute_age_interval_threshold():
    pa = ProtectedAttribute(name="age", type="age_interval_threshold", column="age",
                            threshold=70, disadvantaged="above")
    df = pd.DataFrame({"age": ["[60-70)", "[70-80)", "[80-90)"]})
    disadv, known = pa.disadvantaged_mask(df)
    assert disadv.tolist() == [False, True, True]


# ── Every shipped audit.yaml loads and discovers correctly ──────────────────
def test_discover_manifests_finds_all_seven_shipped_audits():
    manifests = discover_manifests(REPO_ROOT)
    names = {load_manifest(p).name for p in manifests}
    assert names == {
        "compas", "ai_fair_recruitment", "german_credit_lending", "insurance_denial",
        "benefits_denial", "healthcare_readmission", "tenant_screening",
    }


@pytest.mark.parametrize("path", sorted(discover_manifests(REPO_ROOT)), ids=lambda p: p.parent.name)
def test_every_shipped_manifest_loads_without_error(path):
    manifest = load_manifest(path)
    assert manifest.dataset_path.exists(), f"{manifest.name}: dataset file missing at {manifest.dataset_path}"
    assert manifest.core_features
    assert manifest.protected_attributes
    assert manifest.random_state == 42   # the pinned reproducibility convention (see MANIFEST_SPEC.md)

    df = pd.read_csv(manifest.dataset_path)

    assert manifest.target.column in df.columns

    for attr in manifest.protected_attributes:
        assert attr.column in df.columns

    for row_filter in manifest.row_filters:
        assert row_filter.column in df.columns, (
            f"{manifest.name}: row_filters references column "
            f"'{row_filter.column}', which isn't in {manifest.dataset_path.name}"
        )
