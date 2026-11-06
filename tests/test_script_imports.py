"""The scripts that share scripts/ghcall.py run both imported (scripts.<name>) and directly (python3 scripts/<name>.py).

Importing `scripts.ghcall` first, with a fallback, cached an unrelated top-level `scripts` package from site-packages
when the script was run directly, and the later `import_module("scripts.check_traction")` then failed (#1266, #1283).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ["check_contributors.py", "check_traction.py", "check_issue_refs.py", "draft_metrics_row.py", "update_weekly_issue.py"]


@pytest.mark.parametrize("name", SCRIPTS)
def test_a_script_runs_directly_even_when_another_scripts_package_is_first_on_the_path(name, tmp_path):
    decoy = tmp_path / "decoy"
    (decoy / "scripts").mkdir(parents=True)
    (decoy / "scripts" / "__init__.py").write_text("DECOY = True\n")
    env = os.environ | {"PYTHONPATH": str(decoy)}
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / name), "--help"], cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "usage:" in done.stdout


def test_draft_metrics_row_reaches_check_traction_when_run_directly_beside_a_decoy_scripts_package(tmp_path):
    decoy = tmp_path / "decoy"
    (decoy / "scripts").mkdir(parents=True)
    (decoy / "scripts" / "__init__.py").write_text("DECOY = True\n")
    metrics = tmp_path / "METRICS.md"
    metrics.write_text("| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |\n"
                       "|--|--|--|--|--|--|--|--|--|\n| 2026-W43 | 53 | 64 | 8 | 55 | 30K+ total | 20 | 76 | 7 total |\n")
    env = os.environ | {"PYTHONPATH": str(decoy), "PATH": str(tmp_path / "nothing")}      # no gh on PATH: the offline error is the proof
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "draft_metrics_row.py"), "--file", str(metrics),
                           "--date", "2026-11-03"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert "needs the GitHub CLI" in done.stderr and "ModuleNotFoundError" not in done.stderr
