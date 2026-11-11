"""The benchmark-harness job has what it needs to run in parallel (#1301)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "audits.yml"


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _commands(job):
    return "\n".join(step["run"] for step in job["steps"] if "run" in step)


def test_the_benchmark_harness_job_installs_the_test_extra_and_runs_in_parallel():
    harness = _jobs()["benchmark-harness"]
    commands = _commands(harness)
    assert '.[test,benchmark]' in commands                        # pytest and pytest-xdist come from the extra
    assert "-n auto" in commands
    env = next(step["env"] for step in harness["steps"] if step.get("name") == "Run benchmark-harness unit + integration tests")
    assert env["OMP_NUM_THREADS"] == "1"
    assert "pytest-xdist" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
