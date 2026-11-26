"""The longest per-test timeout stays below the limit of every CI job (and pytest step) that runs pytest (#1350, #1358).

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
    """{name: timeout-minutes} for each job of a workflow with a `run` step that runs pytest (directly or through make). A step that
    runs pytest and has its own `timeout-minutes` stops earlier than the job does (#1358), so the name is `job` or
    `job (step 'name')` and the limit is the smaller of the two."""
    jobs = (yaml.safe_load(workflow_text) or {}).get("jobs") or {}
    found = {}
    for name, job in jobs.items():
        job_limit = job.get("timeout-minutes", GITHUB_DEFAULT_MINUTES)
        for step in job.get("steps", []):
            if isinstance(step, dict) and RUNS_PYTEST.search(step.get("run", "")):
                found[name] = job_limit
                if "timeout-minutes" in step:
                    found[f"{name} (step {step.get('name') or step['run'].strip().splitlines()[0][:40]!r})"] = min(job_limit, step["timeout-minutes"])
    return found


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


STEP_WORKFLOW = """
jobs:
  suite:
    timeout-minutes: 30
    steps:
      - name: Fast tests
        run: pytest tests -m "not slow"
        timeout-minutes: 10
      - name: Slow tests
        run: pytest tests -m slow
      - name: Lint
        run: ruff check .
        timeout-minutes: 1
  tight-job:
    timeout-minutes: 12
    steps:
      - run: make coverage-fast
        timeout-minutes: 45
"""


def test_a_step_level_timeout_on_a_pytest_step_is_checked_with_the_step_named():
    # #1358: the job allowed 30 minutes but its fast-test step stopped at 10
    limits = pytest_job_limits(STEP_WORKFLOW)
    assert limits["suite"] == 30 and limits["suite (step 'Fast tests')"] == 10
    assert not any("Lint" in name for name in limits)                   # a step that does not run pytest is not a pytest step
    assert too_short(STEP_WORKFLOW, 900) == {"suite (step 'Fast tests')": 10, "tight-job": 12,
                                                     "tight-job (step 'make coverage-fast')": 12}


def test_a_step_limit_larger_than_its_job_never_loosens_the_job_limit():
    assert pytest_job_limits(STEP_WORKFLOW)["tight-job (step 'make coverage-fast')"] == 12


def test_the_failure_message_names_the_step_and_the_real_workflows_have_none_that_is_too_short():
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        assert not any("(step" in name for name in too_short(workflow.read_text(encoding="utf-8"), _long_running_timeout()))
