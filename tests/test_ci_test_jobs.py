"""Each slow test runs in exactly one CI job (#1300), and the benchmark-harness job has what it needs (#1301)."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "audits.yml"


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _commands(job):
    return [step["run"] for step in job["steps"] if "run" in step]


def _pytest_selection(job):
    """The pytest and make invocations of a job, joined (one string to search)."""
    return "\n".join(_commands(job))


def test_the_profiler_job_runs_the_fast_suite_and_the_benchmark_harness_job_runs_the_slow_tests():
    jobs = _jobs()
    profiler, harness = _pytest_selection(jobs["profiler"]), _pytest_selection(jobs["benchmark-harness"])
    assert "make coverage-fast" in profiler and "make coverage\n" not in profiler + "\n"
    assert '-m slow' in harness and "tests --ignore=tests/browser" in harness
    # the Makefile target the profiler job calls really leaves the slow tests out, and nothing else runs them twice
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    fast_recipe = re.search(r"^coverage-fast:.*\n\t(.*)$", makefile, re.MULTILINE).group(1)
    assert '-m "not slow"' in fast_recipe
    assert "-m slow" not in profiler and "not slow" not in harness


def test_both_jobs_are_gated_alike_so_the_slow_tests_are_never_skipped_while_the_fast_ones_run():
    jobs = _jobs()
    assert jobs["profiler"]["if"] == jobs["benchmark-harness"]["if"]
    assert jobs["profiler"]["needs"] == jobs["benchmark-harness"]["needs"]


def test_the_benchmark_harness_job_installs_the_test_extra_and_runs_in_parallel():
    harness = _jobs()["benchmark-harness"]
    commands = _pytest_selection(harness)
    assert '.[test,benchmark' in commands                        # pytest and pytest-xdist come from the extra (#1301)
    assert "-n auto" in commands
    env = next(step["env"] for step in harness["steps"] if step.get("name") == "Run every slow test")
    assert env["OMP_NUM_THREADS"] == "1"
    assert "pytest-xdist" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_every_file_with_slow_tests_is_collected_by_the_slow_step():
    # the step selects by marker over all of tests/, so a new slow test file needs no workflow edit
    slow_files = {path.name for path in (ROOT / "tests").glob("test_*.py") if "mark.slow" in path.read_text(encoding="utf-8")}
    assert {"test_benchmark.py", "test_benchmark_convergence.py"} <= slow_files
    assert "-m slow" in _pytest_selection(_jobs()["benchmark-harness"])
