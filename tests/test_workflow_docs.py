import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW_DOC = WORKFLOW_DIR / "README.md"


def test_workflow_reference_documents_every_workflow_file():
    rows = [line for line in WORKFLOW_DOC.read_text().splitlines() if line.startswith("|")]
    assert rows[0] == "| Workflow | Trigger | Merge gate | Script or action |"
    documented = set(re.findall(r"\]\(([^)]+\.ya?ml)\)", "\n".join(rows)))
    actual = {
        path.name
        for path in WORKFLOW_DIR.iterdir()
        if path.suffix in {".yml", ".yaml"} and path != WORKFLOW_DOC
    }

    assert documented == actual


def test_workflow_reference_says_which_job_runs_the_slow_tests():
    rows = [line for line in WORKFLOW_DOC.read_text().splitlines() if line.startswith("|")]
    audits_row = next(line for line in rows if "(audits.yml)" in line)

    # The split from #1300: the profiler job runs the fast suite with
    # coverage, and every `slow` test runs in benchmark-harness instead.
    assert "`profiler`" in audits_row
    assert "`make coverage-fast`" in audits_row
    assert "`benchmark-harness`" in audits_row
    assert "`slow`" in audits_row
