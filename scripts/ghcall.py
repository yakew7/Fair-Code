"""One way to run a `gh` command with a timeout (#1266).

The weekly checks and the report scripts call the GitHub CLI. A stalled connection used to hold the job until the
workflow's ten-minute limit, and a local `make traction-live` hung without a message. `run_gh` gives every call a
timeout and turns a timeout into the same failed result an offline `gh` gives (return code 124, like `timeout(1)`),
so each caller's existing "gh failed" path handles it, after one note on stderr saying what stalled.
"""
from __future__ import annotations

import subprocess
import sys

GH_TIMEOUT = 60.0
TIMED_OUT = 124


def run_gh(command: list[str], timeout: float | None = None, **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run(command, capture_output=True, text=True, timeout=...)`; a timeout returns code 124 and empty output."""
    limit = GH_TIMEOUT if timeout is None else timeout
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    try:
        return subprocess.run(command, timeout=limit, **kwargs)
    except subprocess.TimeoutExpired:
        print(f"note: `{' '.join(command[:4])} ...` did not answer within {limit:g} s", file=sys.stderr)
        return subprocess.CompletedProcess(command, TIMED_OUT, stdout="", stderr=f"timed out after {limit:g} s")
