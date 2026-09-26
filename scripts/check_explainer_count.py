#!/usr/bin/env python3
"""Checks (and, with --fix, corrects) "current explainer count" mentions in
README.md, CONTRIBUTORS.md, METRICS.md, and ROADMAP.md against the real
count of explainers/*.md.

CHECKS below is a small, explicit list of exact regexes, one per mention -
not a fuzzy "N explainers" scan across each file. METRICS.md in particular
is a weekly log full of legitimate historical counts (e.g. "explainer count
`39 -> 44`" from an old week); matching those against today's count would be
a false positive worse than the drift this script is meant to catch. Each
regex below targets one specific line meant to state the current, live
total - README.md has three independent ones (the "Show all N explainers"
summary, the Traction table's "Explainers Published" row, and the
Explainers section's own "N short, plain-language write-ups" intro line).

Run locally:
    python3 scripts/check_explainer_count.py          # check only
    python3 scripts/check_explainer_count.py --fix     # check and correct

Exit code (without --fix): 0 = all mentions match, 1 = at least one is stale
or missing. With --fix, a found-and-corrected mention still exits 0 - the
mismatch was real but no manual edit is left for the contributor to make;
only a genuinely unrecognized pattern (an expected mention that's vanished
some other way) still exits 1, since --fix has nothing to rewrite there.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLAINERS_DIR = ROOT / "explainers"

# (relative path, regex whose sole capture group is the claimed count)
CHECKS = [
    ("README.md", re.compile(r"Show all (\d+) explainers")),
    ("README.md", re.compile(r"Explainers Published \| (\d+)")),
    ("README.md", re.compile(r"(\d+) short, plain-language write-ups")),
    ("CONTRIBUTORS.md", re.compile(r"the bulk of the (\d+) explainers")),
    ("METRICS.md", re.compile(r"Explainers-(\d+)-blueviolet")),
    ("METRICS.md", re.compile(r"\| Explainers \| (\d+) \|")),
    ("ROADMAP.md", re.compile(r"(\d+) explainers published")),
]


def main() -> int:
    fix = "--fix" in sys.argv[1:]
    actual = len(list(EXPLAINERS_DIR.glob("*.md")))
    fixed = []
    unresolved = []

    for rel_path, pattern in CHECKS:
        path = ROOT / rel_path
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is None:
            unresolved.append((rel_path, f"expected pattern not found: {pattern.pattern!r}"))
            continue
        claimed = int(match.group(1))
        if claimed == actual:
            continue
        if not fix:
            unresolved.append((rel_path, f"says {claimed} explainers, but explainers/*.md has {actual}"))
            continue
        start, end = match.span(1)
        path.write_text(text[:start] + str(actual) + text[end:], encoding="utf-8")
        fixed.append((rel_path, f"{claimed} -> {actual}"))

    if fixed:
        print(f"Corrected {len(fixed)} explainer-count mention(s) (explainers/*.md has {actual} files):")
        for rel_path, change in fixed:
            print(f"  {rel_path}: {change}")

    if unresolved:
        print(f"Explainer count drift found (explainers/*.md currently has {actual} files):",
              file=sys.stderr)
        for rel_path, reason in unresolved:
            print(f"  {rel_path}: {reason}", file=sys.stderr)
        if not fix:
            print("\nRun 'python3 scripts/check_explainer_count.py --fix' to correct this "
                  "automatically.", file=sys.stderr)
        return 1

    if not fixed:
        print(f"OK: all {len(CHECKS)} explainer-count mentions match explainers/*.md ({actual} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
