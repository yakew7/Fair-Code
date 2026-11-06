"""The Makefile's targets say what the documentation says they do."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dry_run(target: str) -> str:
    return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def test_test_fast_leaves_the_browser_tests_to_make_test_browser():
    # #1263: with Playwright installed `pytest tests/` also collected tests/browser (1,476 tests instead of 1,464)
    recipe = dry_run("test-fast")
    assert 'pytest tests/ -q -m "not slow"' in recipe and "--ignore=tests/browser" in recipe
    assert "tests/browser" in dry_run("test-browser")


def test_check_runs_the_environment_doctor_before_anything_that_could_fail_because_of_it():
    # #1268: a stdlib-shadowing module in site-packages makes tests fail with an unrelated ImportError
    recipe = dry_run("check")
    assert "scripts/check_environment.py" in recipe
    assert recipe.index("check_environment.py") < recipe.index("check_em_dash.py")


def test_every_described_makefile_target_is_documented_in_contributing():
    # #1275: `make key-fold-check` was the one target a contributor could not find; `help` is the only exception
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    targets = re.findall(r"^([a-zA-Z_-]+):.*?## ", makefile, re.MULTILINE)
    assert "key-fold-check" in targets and len(targets) > 10
    missing = [t for t in targets if t != "help" and not re.search(rf"make {re.escape(t)}(?![\w-])", contributing)]
    assert missing == [], f"add these to CONTRIBUTING.md: {missing}"
