"""The benchmark strategies and the audit grid, on a tiny synthetic audit with one cheap model family (#1302).

`make coverage-fast` used to miss 50 lines of faircode/benchmark.py and strategies.py because the only tests that reached
them (the in-processing and post-processing fits, the intersectional rows) trained all three model families on real audits
and carried the slow marker. Here a 240-row toy audit and a logistic regression only keep each test well under a second.
"""
import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace

pytest.importorskip("sklearn", reason="the benchmark harness needs the optional benchmark extra")
pytest.importorskip("fairlearn", reason="the benchmark harness needs the optional benchmark extra")
yaml = pytest.importorskip("yaml", reason="the benchmark harness needs the optional benchmark extra")

from sklearn.linear_model import LogisticRegression  # noqa: E402

from faircode import benchmark, strategies  # noqa: E402
from faircode.manifest import load_manifest  # noqa: E402

LR_ONLY = {"logistic_regression": lambda random_state: LogisticRegression(max_iter=200, random_state=random_state)}


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


def test_the_audit_grid_covers_every_strategy_and_the_intersectional_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "MODEL_FAMILIES", LR_ONLY)
    monkeypatch.setattr("faircode.models.MODEL_FAMILIES", LR_ONLY)
    manifest = _write_toy_audit(tmp_path)
    fairness_rows, performance_rows = benchmark.run_audit(manifest, n_resamples=20, n_permutations=20)

    fairness, performance = pd.DataFrame(fairness_rows), pd.DataFrame(performance_rows)
    assert set(fairness["strategy"]) == set(strategies.STRATEGIES) and set(fairness["model"]) == {"logistic_regression"}
    inter = fairness[fairness["protected_attribute"] == "attr_a_x_attr_b"]
    assert len(inter) == len(strategies.STRATEGIES)
    assert (inter["metric"] == "intersectional_demographic_parity_diff").all() and inter["value"].notna().all()
    # post-processing has no probability output, so its AUC value is empty by design; the others have one
    auc = performance[performance["metric"] == "auc"]
    assert auc[auc["strategy"] == "post_processing"]["value"].isna().all()
    assert auc[auc["strategy"] != "post_processing"]["value"].notna().all()


@pytest.mark.parametrize("strategy", ["baseline", "in_processing", "post_processing"])
def test_run_strategy_fits_each_branch_and_returns_predictions_for_the_test_rows(strategy, tmp_path, monkeypatch):
    monkeypatch.setattr("faircode.models.MODEL_FAMILIES", LR_ONLY)
    manifest = _write_toy_audit(tmp_path)
    data = benchmark.prepare_audit(manifest)
    y_test, y_pred, y_proba = benchmark._run_strategy(
        strategy, "logistic_regression", manifest, data.X_all, data.y, data.masks, data.idx_train, data.idx_test)
    assert len(y_test) == len(y_pred) == len(data.idx_test) and set(np.unique(y_pred)) <= {0, 1}
    if strategy == "post_processing":
        assert y_proba is None                                  # a hard-threshold post-processor has nothing to rank
    else:
        assert y_proba is not None and len(y_proba) == len(y_test) and ((0 <= y_proba) & (y_proba <= 1)).all()


def test_in_processing_fit_and_predict_use_the_sensitive_feature_only_as_a_constraint():
    frame = _toy_frame()
    X, y = frame[["x", "z"]], frame["label"].to_numpy()
    sensitive = (frame["attr_a"] == "disadv").astype(int).to_numpy()
    mitigator = strategies.fit_in_processing(LogisticRegression(max_iter=200), X, y, sensitive)
    y_pred, y_proba = strategies.predict_in_processing(mitigator, X, random_state=0)
    assert len(y_pred) == len(X) and y_proba is not None and len(y_proba) == len(X)


def test_in_processing_prediction_falls_back_to_no_probabilities_when_pmf_predict_is_gone():
    class Mitigator:
        def predict(self, X, random_state=None):
            return np.zeros(len(X), dtype=int)

    y_pred, y_proba = strategies.predict_in_processing(Mitigator(), pd.DataFrame({"x": [1, 2, 3]}), random_state=0)
    assert list(y_pred) == [0, 0, 0] and y_proba is None

    class Short(Mitigator):
        def _pmf_predict(self, X):
            return np.zeros((len(X), 1))                        # a one-column result has no positive class

    assert strategies.predict_in_processing(Short(), pd.DataFrame({"x": [1, 2]}), random_state=0)[1] is None


def test_post_processing_prediction_needs_the_sensitive_feature_at_predict_time():
    frame = _toy_frame()
    X, y = frame[["x", "z"]], frame["label"].to_numpy()
    sensitive = (frame["attr_a"] == "disadv").astype(int).to_numpy()
    optimizer = strategies.fit_post_processing(LogisticRegression(max_iter=200), X, y, sensitive, random_state=0)
    y_pred, y_proba = strategies.predict_post_processing(optimizer, X, sensitive, random_state=0)
    assert len(y_pred) == len(X) and y_proba is None and set(np.unique(y_pred)) <= {0, 1}


def test_a_single_protected_attribute_adds_no_intersectional_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "MODEL_FAMILIES", LR_ONLY)
    monkeypatch.setattr("faircode.models.MODEL_FAMILIES", LR_ONLY)
    manifest = _write_toy_audit(tmp_path, protected=("attr_a",))
    fairness, _ = benchmark.run_audit(manifest, n_resamples=20, n_permutations=20)
    assert not any("_x_" in row["protected_attribute"] for row in fairness)


def test_a_stub_manifest_namespace_is_enough_for_run_strategy(tmp_path, monkeypatch):
    # the helper only reads the declared columns, features, protected attributes and the seed
    monkeypatch.setattr("faircode.models.MODEL_FAMILIES", LR_ONLY)
    manifest = _write_toy_audit(tmp_path)
    data = benchmark.prepare_audit(manifest)
    stub = SimpleNamespace(protected_attributes=manifest.protected_attributes, core_features=manifest.core_features,
                           proxy_features=manifest.proxy_features, random_state=manifest.random_state)
    _, y_pred, _ = benchmark._run_strategy("baseline", "logistic_regression", stub, data.X_all, data.y, data.masks,
                                           data.idx_train, data.idx_test)
    assert len(y_pred) == len(data.idx_test)
