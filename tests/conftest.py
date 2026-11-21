"""Shared pytest hooks.

The default per-test timeout (300 s, `timeout` in pyproject.toml, from pytest-timeout) suits the fast tests. The `slow` model-training
tests and the `browser` tests legitimately run for minutes on a busy CI runner, so they get a longer one unless they set their own
with @pytest.mark.timeout (#1342).
"""

import pytest

LONG_RUNNING_MARKERS = ("slow", "browser")
LONG_RUNNING_TIMEOUT = 900


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("timeout") is None and any(item.get_closest_marker(m) for m in LONG_RUNNING_MARKERS):
            item.add_marker(pytest.mark.timeout(LONG_RUNNING_TIMEOUT))
