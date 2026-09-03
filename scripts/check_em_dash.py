#!/usr/bin/env python3
"""Fail if an em dash (U+2014) appears in tracked source or prose files.

Fair Code's contribution rule (CONTRIBUTING.md, and the new-audit / new-explainer
issue templates) is to write a spaced hyphen ' - ' instead of an em dash. This
script enforces that rule in CI so it is caught automatically, not by eye in
review. En dashes (–, U+2013) are intentionally allowed - they are used for
numeric ranges (e.g. a "47.8–53.1%" confidence interval).

Run locally:  python3 scripts/check_em_dash.py
Exit code:    0 = clean, 1 = at least one em dash found.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EM_DASH = "\u2014"  # em dash, the forbidden character
EN_DASH = "\u2013"  # en dash, allowed for numeric ranges

# Tracked text files with these extensions are scanned for em dashes. Data (.csv)
# and dependency pins (.txt) are deliberately out of scope.
SCAN_EXT = {".md", ".py", ".js", ".html", ".css", ".yml", ".yaml"}

# Opt-out path list (the escape hatch): files that legitimately contain an em
# dash, or that must not be edited. Keep this list short and justified.
ALLOWLIST = {
    # Frozen for the paper (CLAUDE.md §1) - must not be modified, even cosmetically.
    "faircode/significance.py",
    # Documents the rule itself and shows em dashes as the anti-pattern to avoid.
    "CONTRIBUTING.md",
    # Same reason: demonstrates the banned character inside a checkbox label.
    ".github/ISSUE_TEMPLATE/new_audit.yml",
    ".github/ISSUE_TEMPLATE/new_explainer.yml",
}
ALLOW_PREFIXES = (
    "paper/results-frozen/",  # frozen evidence, never modified
    "faircode/_explainers/",  # generated mirror of explainers/*.md, checking the source already covers it
)


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    for raw in out.splitlines():
        path = raw.strip()
        if not path or Path(path).suffix.lower() not in SCAN_EXT:
            continue
        if path in ALLOWLIST or path.startswith(ALLOW_PREFIXES):
            continue
        yield path


def main() -> int:
    hits = []
    for path in _tracked_files():
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            col = line.find(EM_DASH)
            if col != -1:
                hits.append((path, line_no, col + 1, line.strip()))

    if not hits:
        print("OK: no em dashes in tracked source/prose files.")
        return 0

    print(
        f"Found em dashes ({EM_DASH}). Use a spaced hyphen ' - ' instead "
        f"(the en dash '{EN_DASH}' is fine for ranges). See CONTRIBUTING.md.\n",
        file=sys.stderr,
    )
    for path, line_no, col, snippet in hits:
        print(f"  {path}:{line_no}:{col}: {snippet}", file=sys.stderr)
    n_files = len({h[0] for h in hits})
    print(f"\n{len(hits)} em dash(es) across {n_files} file(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
