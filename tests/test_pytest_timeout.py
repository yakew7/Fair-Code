"""pytest-timeout is configured so a hung test fails instead of stalling the job (#1342)."""

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_test_extra_installs_pytest_timeout_and_the_default_timeout_is_set():
    assert re.search(r'^test = \[.*"pytest-timeout>=', PYPROJECT, re.MULTILINE)
    assert re.search(r"^timeout = (\d+)$", PYPROJECT, re.MULTILINE)


def test_the_ci_test_jobs_install_the_extra_that_brings_it():
    assert "[test," in (ROOT / ".github" / "workflows" / "audits.yml").read_text(encoding="utf-8")


def test_setup_installs_pytest_timeout_for_local_runs():
    assert "pytest-timeout" in (ROOT / "Makefile").read_text(encoding="utf-8").split("setup:", 1)[1].split("\n", 3)[1]


def test_the_lock_file_comment_lists_it_with_the_other_excluded_test_tools():
    assert "pytest-timeout" in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").split("appnope", 1)[0]


def test_slow_and_browser_tests_get_the_longer_timeout_unless_they_set_their_own(tmp_path):
    pytest.importorskip("pytest_timeout")
    (tmp_path / "conftest.py").write_text((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\ntimeout = 5\nmarkers =\n    slow: x\n    browser: x\n", encoding="utf-8")
    (tmp_path / "test_marks.py").write_text(textwrap.dedent("""
        import pytest
        def limit(request): return request.node.get_closest_marker("timeout")
        @pytest.mark.slow
        def test_slow(request): assert limit(request).args == (900,)
        @pytest.mark.browser
        def test_browser(request): assert limit(request).args == (900,)
        @pytest.mark.slow
        @pytest.mark.timeout(30)
        def test_own(request): assert limit(request).args == (30,)
        def test_plain(request): assert limit(request) is None
    """), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert result.returncode == 0 and "4 passed" in result.stdout, result.stdout


def test_a_test_that_hangs_fails_at_the_timeout_instead_of_stalling(tmp_path):
    pytest.importorskip("pytest_timeout")
    test = tmp_path / "test_hang.py"
    test.write_text("import time\n\ndef test_hangs():\n    time.sleep(60)\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "pytest", str(test), "-q", "-p", "no:cacheprovider", "--timeout=2", "--rootdir", str(tmp_path)],
                            capture_output=True, text=True, timeout=45, cwd=tmp_path)
    assert result.returncode == 1 and "Timeout (>2.0s)" in result.stdout and "1 failed" in result.stdout
