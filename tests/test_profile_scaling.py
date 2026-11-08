"""A high-cardinality geography column must not make profile() quadratic (#1042)."""

import time

import numpy as np
import pandas as pd

from faircode import profile


def _profile_seconds(n_rows, n_labels):
    rng = np.random.default_rng(5)
    df = pd.DataFrame({
        "sex": rng.choice(["m", "f"], n_rows),
        "zip": rng.integers(10000, 10000 + n_labels, n_rows).astype(str),
    })
    best = float("inf")
    for _ in range(3):
        # CPU time of this process, not wall-clock time: another process taking the CPU (a parallel suite, other work on the
        # machine) lengthens the wall-clock time of a run but not the CPU time it consumes (#1284)
        start = time.process_time()
        result = profile(df)
        best = min(best, time.process_time() - start)
    assert next(d for d in result["dimensions"] if d["name"] == "zip")["n_groups"] > 0.5 * n_labels
    return best


def test_profile_with_many_distinct_labels_is_not_quadratic():
    # Compare growth of CPU time, not wall-clock time, so a slow or busy runner does not matter: quadrupling the
    # labels costs about 4x when linear and about 16x when quadratic.
    small = _profile_seconds(40_000, 20_000)
    large = _profile_seconds(160_000, 80_000)
    assert large / small < 9, f"{small:.2f}s -> {large:.2f}s"


def test_the_scaling_measurement_uses_cpu_time_not_wall_clock_time(monkeypatch):
    # #1284: wall-clock time grows when other processes take the CPU; CPU time does not
    def forbidden():
        raise AssertionError("wall-clock time must not be used")

    monkeypatch.setattr(time, "perf_counter", forbidden)
    assert _profile_seconds(2_000, 1_000) >= 0.0
