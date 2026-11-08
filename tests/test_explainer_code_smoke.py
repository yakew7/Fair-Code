import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from load_helpers import load_factor

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPLAINERS_DIR = REPO_ROOT / "explainers"
PYTHON_BLOCK = re.compile(r"^```python[^\n]*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
RUNNABLE_MARKER = "# runnable"
SLOW_MARKER = "# slow"


def runnable_blocks():
    for path in sorted(EXPLAINERS_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for block_number, match in enumerate(PYTHON_BLOCK.finditer(content), start=1):
            lines = match.group(1).splitlines()
            first_content = next((line.strip() for line in lines if line.strip()), "")
            if first_content != RUNNABLE_MARKER:
                continue
            slow = SLOW_MARKER in [line.strip() for line in lines[:3]]
            code = "\n".join(
                line for line in lines if line.strip() not in {RUNNABLE_MARKER, SLOW_MARKER}
            )
            marks = [pytest.mark.slow] if slow else []
            yield pytest.param(
                path,
                block_number,
                code,
                slow,
                id=f"{path.name}-python-block-{block_number}",
                marks=marks,
            )


def run_block(code, slow, runner=subprocess.run, factor=None):
    """Run one explainer block: (result, seconds, timeout used). The timeout (30 s, or 120 s for a `# slow` block) is scaled by
    the machine load, and a block that still times out is run once more at the slow timeout before it counts as hung."""
    base = (120 if slow else 30) * (load_factor() if factor is None else factor)
    attempts = [base] if slow else [base, 120 * (load_factor() if factor is None else factor)]
    started = time.monotonic()
    for timeout in attempts:
        try:
            return runner([sys.executable, "-c", code], cwd=REPO_ROOT, text=True, capture_output=True,
                          timeout=timeout, check=False), time.monotonic() - started, timeout
        except subprocess.TimeoutExpired as exc:
            last = exc
    raise last


@pytest.mark.parametrize("path,block_number,code,slow", list(runnable_blocks()))
def test_runnable_explainer_python_blocks(path, block_number, code, slow):
    # A block that loads an audit needs the benchmark extra; the profiler CI job installs only the core package.
    if "faircode.benchmark" in code:
        for module in ("yaml", "sklearn"):
            pytest.importorskip(module)
    try:
        result, seconds, timeout = run_block(code, slow)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)} Python block {block_number} timed out "
            f"after {exc.timeout:g}s (load factor {load_factor():.1f}).\nstdout: {exc.stdout or ''}\nstderr: {exc.stderr or ''}"
        )

    assert result.returncode == 0, (
        f"{path.relative_to(REPO_ROOT)} Python block {block_number} exited "
        f"with status {result.returncode} after {seconds:.1f}s.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_a_block_that_times_out_once_is_run_again_at_the_slow_timeout():
    from types import SimpleNamespace
    seen = []

    def runner(command, **kwargs):
        seen.append(kwargs["timeout"])
        if len(seen) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result, seconds, timeout = run_block("pass", slow=False, runner=runner, factor=1.0)
    assert seen == [30, 120] and timeout == 120 and result.returncode == 0


def test_a_block_that_hangs_on_both_attempts_still_fails_with_the_timeout():
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(subprocess.TimeoutExpired) as caught:
        run_block("pass", slow=False, runner=runner, factor=2.0)
    assert caught.value.timeout == 240
    with pytest.raises(subprocess.TimeoutExpired):
        run_block("pass", slow=True, runner=runner, factor=1.0)          # a slow block is tried once


def test_the_timeout_is_scaled_by_the_load_factor():
    from types import SimpleNamespace
    seen = []
    run_block("pass", slow=False, runner=lambda c, **k: seen.append(k["timeout"]) or SimpleNamespace(returncode=0), factor=3.0)
    assert seen == [90.0]


def test_at_least_one_explainer_python_block_is_marked_runnable():
    assert list(runnable_blocks()), (
        "No runnable explainer Python blocks found. Add '# runnable' as the first "
        "nonblank line inside a Python fence in explainers/*.md."
    )
