from pathlib import Path

import pytest
import yaml


WORKFLOWS_DIR = Path(__file__).parents[1] / ".github/workflows"
EXPECTED_SCHEDULED_PERMISSIONS = {
    "codeowners-access.yml": {"contents": "read"},
    "codeql.yml": {
        "actions": "read",
        "contents": "read",
        "security-events": "write",
    },
    "external-links.yml": {"contents": "read", "issues": "write"},
    "traction-live.yml": {"contents": "read", "issues": "write"},
    "contributors-drift.yml": {"contents": "read", "issues": "write"},
}


def _scheduled_workflows():
    workflows = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if "schedule" in workflow.get("on", {}):
            workflows.append((path, workflow))
    return workflows


SCHEDULED_WORKFLOWS = _scheduled_workflows()


def test_scheduled_workflows_have_explicit_minimal_permissions():
    actual = {path.name for path, _ in SCHEDULED_WORKFLOWS}
    assert actual == set(EXPECTED_SCHEDULED_PERMISSIONS)

    for path, workflow in SCHEDULED_WORKFLOWS:
        permissions = workflow.get("permissions")
        assert permissions == EXPECTED_SCHEDULED_PERMISSIONS[path.name]
        assert permissions["contents"] == "read"


@pytest.mark.parametrize(
    "path,workflow",
    SCHEDULED_WORKFLOWS,
    ids=[path.name for path, _ in SCHEDULED_WORKFLOWS],
)
def test_scheduled_workflows_have_concurrency_controls(path, workflow):
    concurrency = workflow.get("concurrency")
    assert isinstance(concurrency, dict), path.name
    assert concurrency.get("group", "").strip(), path.name
    assert "cancel-in-progress" in concurrency, path.name


@pytest.mark.parametrize(
    "path,workflow",
    SCHEDULED_WORKFLOWS,
    ids=[path.name for path, _ in SCHEDULED_WORKFLOWS],
)
def test_scheduled_workflow_jobs_have_timeouts(path, workflow):
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and jobs, path.name

    for job_name, job in jobs.items():
        timeout = job.get("timeout-minutes")
        assert timeout is not None, f"{path.name}:{job_name} has no timeout"
        assert 1 <= int(timeout) <= 360, f"{path.name}:{job_name} has invalid timeout"


RECORD_FILES = {"CONTRIBUTORS.md", "METRICS.md", "README.md", "ROADMAP.md"}


@pytest.mark.parametrize("name", ["contributors-drift.yml", "traction-live.yml"])
def test_the_report_workflows_also_run_on_a_push_that_updates_the_records(name):
    # #1317: the tracking issue closes when the records are fixed, not on the next Monday
    workflow = yaml.load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = workflow["on"]
    assert {"schedule", "workflow_dispatch", "push"} <= set(triggers)
    assert triggers["push"]["branches"] == ["main"]
    assert RECORD_FILES <= set(triggers["push"]["paths"])
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"       # two pushes in a row must not race on the issue


def test_each_report_workflow_watches_the_script_it_runs_and_the_workflow_docs_say_so():
    paths = {name: set(yaml.load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)["on"]["push"]["paths"])
             for name in ("contributors-drift.yml", "traction-live.yml")}
    assert "scripts/contributors-exceptions.json" in paths["contributors-drift.yml"]
    assert "scripts/check_traction.py" in paths["traction-live.yml"]
    readme = (WORKFLOWS_DIR / "README.md").read_text(encoding="utf-8")
    assert readme.count("push to `main` that changes the records") == 2
