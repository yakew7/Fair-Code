"""The Makefile's targets say what the documentation says they do."""
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
