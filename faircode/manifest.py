"""Declarative audit manifests (audit.yaml) - Layer 1 of the benchmark harness.

Each audit folder can carry an audit.yaml naming its dataset, label, protected
attributes, proxy features, and "core" (fair) feature set. faircode.benchmark
reads every manifest and runs the SAME modelling + fairness-metric pipeline
over all of them, so a cross-domain comparison rests on one code path rather
than N bespoke scripts. The schema is documented in faircode/MANIFEST_SPEC.md.

Contributors fill in audit.yaml. They never need to touch this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

MANIFEST_FILENAME = "audit.yaml"


@dataclass
class RowFilter:
    column: str
    isin: list | None = None
    not_isin: list | None = None
    equals: object | None = None
    not_equals: object | None = None
    notna: bool = False

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = pd.Series(True, index=df.index)
        if self.isin is not None:
            mask &= df[self.column].isin(self.isin)
        if self.not_isin is not None:
            mask &= ~df[self.column].isin(self.not_isin)
        if self.equals is not None:
            mask &= df[self.column] == self.equals
        if self.not_equals is not None:
            mask &= df[self.column] != self.not_equals
        if self.notna:
            mask &= df[self.column].notna()
        return df[mask]


@dataclass
class TargetSpec:
    column: str
    method: str  # "binary" | "equals" | "isin" | "above_median"
    value: object | None = None
    values: list | None = None

    def __post_init__(self):
        if self.method == "equals" and self.value is None:
            raise ValueError(f"{self.column}: target method 'equals' needs a 'value' field")
        if self.method == "isin" and self.values is None:
            raise ValueError(f"{self.column}: target method 'isin' needs a 'values' field")

    def compute(self, df: pd.DataFrame) -> pd.Series:
        col = df[self.column]
        if self.method == "binary":
            return col.astype(int)
        if self.method == "equals":
            return (col == self.value).astype(int)
        if self.method == "isin":
            return col.isin(self.values).astype(int)
        if self.method == "above_median":
            return (col > col.median()).astype(int)
        raise ValueError(f"unknown target method: {self.method!r}")


@dataclass
class ProtectedAttribute:
    name: str
    type: str  # "categorical" | "numeric_threshold" | "age_interval_threshold"
    column: str
    disadvantaged_values: list | None = None
    advantaged_values: list | None = None
    threshold: float | None = None
    disadvantaged: str = "below"  # "below" | "above" - which side of threshold is disadvantaged

    def __post_init__(self):
        if self.type in ("numeric_threshold", "age_interval_threshold") and self.threshold is None:
            raise ValueError(f"{self.name}: type {self.type!r} needs a 'threshold' field")

    def disadvantaged_mask(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Returns (disadvantaged_mask, known_mask) - both boolean Series aligned to df.

        known_mask is False for rows this attribute can't classify (e.g. a
        categorical value outside both the disadvantaged and advantaged
        lists, or a threshold column that failed to parse) so the caller can
        drop them instead of silently lumping them into "advantaged".
        """
        if self.type == "categorical":
            col = df[self.column]
            if self.disadvantaged_values is not None and self.advantaged_values is not None:
                known = col.isin(self.disadvantaged_values) | col.isin(self.advantaged_values)
                disadv = col.isin(self.disadvantaged_values)
            elif self.disadvantaged_values is not None:
                known = pd.Series(True, index=df.index)
                disadv = col.isin(self.disadvantaged_values)
            elif self.advantaged_values is not None:
                known = pd.Series(True, index=df.index)
                disadv = ~col.isin(self.advantaged_values)
            else:
                raise ValueError(f"{self.name}: need disadvantaged_values or advantaged_values")
            return disadv, known

        if self.type == "numeric_threshold":
            numeric = pd.to_numeric(df[self.column], errors="coerce")
            known = numeric.notna()
            disadv = numeric < self.threshold if self.disadvantaged == "below" else numeric >= self.threshold
            return disadv.fillna(False), known

        if self.type == "age_interval_threshold":
            # e.g. "[70-80)" -> 70. Non-matching values (already-numeric ages,
            # freeform strings) fall back to a direct numeric parse.
            extracted = df[self.column].astype(str).str.extract(r"\[(\d+)")[0]
            numeric = pd.to_numeric(extracted, errors="coerce")
            numeric = numeric.fillna(pd.to_numeric(df[self.column], errors="coerce"))
            known = numeric.notna()
            disadv = numeric < self.threshold if self.disadvantaged == "below" else numeric >= self.threshold
            return disadv.fillna(False), known

        raise ValueError(f"unknown protected attribute type: {self.type!r}")


@dataclass
class Manifest:
    name: str
    title: str
    path: Path  # path to audit.yaml
    dataset_path: Path  # resolved path to the dataset file
    row_filters: list
    target: TargetSpec
    protected_attributes: list
    core_features: list
    proxy_features: list
    random_state: int = 42
    test_size: float = 0.2

    @property
    def audit_dir(self) -> Path:
        return self.path.parent

    @classmethod
    def from_dict(cls, data: dict, manifest_path: Path) -> "Manifest":
        audit_dir = manifest_path.parent
        row_filters = [RowFilter(**rf) for rf in data.get("row_filters", [])]
        target = TargetSpec(**data["target"])
        protected = [ProtectedAttribute(**pa) for pa in data["protected_attributes"]]
        if not protected:
            raise ValueError(f"{manifest_path}: protected_attributes must have at least one entry")
        return cls(
            name=data["name"],
            title=data.get("title", data["name"]),
            path=manifest_path,
            dataset_path=audit_dir / data["dataset"]["path"],
            row_filters=row_filters,
            target=target,
            protected_attributes=protected,
            core_features=list(data["core_features"]),
            proxy_features=list(data.get("proxy_features", [])),
            random_state=data.get("random_state", 42),
            test_size=data.get("test_size", 0.2),
        )


def load_manifest(path) -> Manifest:
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
    return Manifest.from_dict(data, path)


def discover_manifests(root=".") -> list:
    root = Path(root)
    return sorted(root.glob(f"*/{MANIFEST_FILENAME}"))
