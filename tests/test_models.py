"""Tests for faircode.models: the three model families (Layer 2 of the
benchmark harness).

Run from the repo root:  pytest tests/ -q
"""

import pytest

pytest.importorskip("sklearn", reason="faircode.models needs the optional benchmark extra")

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from faircode.models import MODEL_FAMILIES, build_model


def test_model_families_keys_match_expected_three():
    assert set(MODEL_FAMILIES) == {"logistic_regression", "random_forest", "gradient_boosting"}


def test_build_model_logistic_regression_hyperparameters():
    model = build_model("logistic_regression", random_state=7)
    assert isinstance(model, LogisticRegression)
    assert model.random_state == 7
    assert model.max_iter == 1000


def test_build_model_random_forest_hyperparameters():
    model = build_model("random_forest", random_state=7)
    assert isinstance(model, RandomForestClassifier)
    assert model.random_state == 7
    assert model.n_estimators == 100


def test_build_model_gradient_boosting_hyperparameters():
    model = build_model("gradient_boosting", random_state=7)
    assert isinstance(model, GradientBoostingClassifier)
    assert model.random_state == 7


def test_build_model_random_state_propagates_per_call():
    a = build_model("logistic_regression", random_state=1)
    b = build_model("logistic_regression", random_state=2)
    assert a.random_state == 1
    assert b.random_state == 2


def test_build_model_returns_a_fresh_unfit_estimator_each_call():
    a = build_model("random_forest", random_state=42)
    b = build_model("random_forest", random_state=42)
    assert a is not b


def test_build_model_unknown_name_raises_key_error():
    with pytest.raises(KeyError):
        build_model("not_a_real_model", random_state=42)
