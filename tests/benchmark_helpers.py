"""A toy audit and a one-model family for the benchmark tests that do not need the real ones (#1302, #1325).

Shared by tests/test_benchmark.py, test_benchmark_fast.py and test_benchmark_outputs.py; a plain helper module like
js_helpers.py and load_helpers.py, not a test module.
"""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn", reason="the benchmark harness needs the optional benchmark extra")
yaml = pytest.importorskip("yaml", reason="the benchmark harness needs the optional benchmark extra")

from sklearn.linear_model import LogisticRegression  # noqa: E402

from faircode.manifest import load_manifest  # noqa: E402

LR_ONLY = {"logistic_regression": lambda random_state: LogisticRegression(max_iter=5000, random_state=random_state)}


def _toy_frame(n=240, seed=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    group_a = rng.choice(["disadv", "ok"], n, p=[0.4, 0.6])
    group_b = rng.choice(["disadv", "ok"], n, p=[0.3, 0.7])
    noise = rng.normal(scale=0.7, size=n)
    label = ((x + noise - 0.4 * (group_a == "disadv")) > 0).astype(int)
    return pd.DataFrame({"label": label, "x": x, "z": rng.normal(size=n), "attr_a": group_a, "attr_b": group_b})


def _write_toy_audit(directory, protected=("attr_a", "attr_b")):
    frame = _toy_frame()
    frame.to_csv(directory / "toy.csv", index=False)
    manifest = {
        "name": "toy",
        "dataset": {"path": "toy.csv"},
        "target": {"column": "label", "method": "binary"},
        "protected_attributes": [
            {"name": name, "type": "categorical", "column": name, "disadvantaged_values": ["disadv"], "advantaged_values": ["ok"]}
            for name in protected],
        "core_features": ["x", "z"],
    }
    (directory / "audit.yaml").write_text(yaml.dump(manifest))
    return load_manifest(directory / "audit.yaml")
