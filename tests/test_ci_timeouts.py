"""The longest per-test timeout stays below the limit of every CI job that runs pytest (#1350).

tests/conftest.py gives the `slow` and `browser` tests LONG_RUNNING_TIMEOUT seconds. If a job's `timeout-minutes` is not larger, the
runner would stop the job before pytest-timeout fails the hung test, which is the stall #1342 removed. A job without
`timeout-minutes` gets GitHub's own default of 360 minutes.
"""
import importlib.util
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS_PYTEST = re.compile(r"\bpytest\b|\bmake (?:test|coverage|check)")
GITHUB_DEFAULT_MINUTES = 360


def _long_running_timeout():
    spec = importlib.util.spec_from_file_location("_faircode_tests_conftest", ROOT / "tests" / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LONG_RUNNING_TIMEOUT


def pytest_job_limits(workflow_text):
    """{job name: timeout-minutes} for each job of a workflow with a `run` step that runs pytest (directly or through make)."""
    jobs = (yaml.safe_load(workflow_text) or {}).get("jobs") or {}
    return {name: job.get("timeout-minutes", GITHUB_DEFAULT_MINUTES) for name, job in jobs.items()
            if any(RUNS_PYTEST.search(step.get("run", "")) for step in job.get("steps", []) if isinstance(step, dict))}


def too_short(workflow_text, seconds):
    """The pytest jobs whose limit is not larger than `seconds`."""
    return {name: minutes for name, minutes in pytest_job_limits(workflow_text).items() if minutes * 60 <= seconds}


def test_every_workflow_job_that_runs_pytest_outlasts_the_longest_test_timeout():
    seconds = _long_running_timeout()
    found = {}
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        found.update({f"{workflow.name}:{name}": minutes for name, minutes in pytest_job_limits(workflow.read_text(encoding="utf-8")).items()})
        assert too_short(workflow.read_text(encoding="utf-8"), seconds) == {}, (
            f"{workflow.name}: a job that runs pytest has timeout-minutes of at most {seconds // 60} (the slow and browser tests' "
            "timeout in tests/conftest.py), so the runner would stop it before pytest-timeout does")
    assert "audits.yml:profiler" in found and "audits.yml:benchmark-harness" in found          # the guard is looking at the real jobs


WORKFLOW = """
jobs:
  quick:
    timeout-minutes: 10
    steps:
      - run: pytest tests -q
  through-make:
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - run: make coverage-fast
  roomy:
    timeout-minutes: 30
    steps:
      - run: python3 -m pytest tests -m slow
  no-limit:
    steps:
      - run: make test-fast
  not-a-test-job:
    timeout-minutes: 5
    steps:
      - run: echo hello
      - run: python3 scripts/check_em_dash.py
"""


def test_the_guard_finds_short_jobs_through_pytest_and_make_and_ignores_jobs_that_run_neither():
    limits = pytest_job_limits(WORKFLOW)
    assert limits["quick"] == 10 and limits["through-make"] == 15 and limits["roomy"] == 30 and limits["no-limit"] == GITHUB_DEFAULT_MINUTES
    assert too_short(WORKFLOW, 900) == {"quick": 10, "through-make": 15}      # 15 minutes is not more than 900 s
    assert too_short(WORKFLOW, 600) == {"quick": 10}
    assert too_short("jobs: {}", 900) == {} and too_short("", 900) == {}


def test_the_conftest_timeout_is_what_the_guard_reads():
    assert _long_running_timeout() == 900
