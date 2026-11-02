#!/usr/bin/env python3
"""Checks (and, with --fix, corrects) "current explainer count" mentions in
README.md, CONTRIBUTORS.md, METRICS.md, and ROADMAP.md against the real
count of explainers/*.md, and checks that README.md and llms.txt list every
explainers/*.md by slug (a missing listing is reported by name; --fix does
not add it).

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

class TableCell:
    """Stands in for a regex in CHECKS: finds the number in the first data row of the markdown table whose header row has
    a cell named `header`, whatever its position, so adding or reordering a column cannot make the check read the wrong
    cell or nothing. `search` returns an object with `group(1)` and `span(1)` like a regex match, or None."""

    def __init__(self, header: str):
        self.header = header
        self.pattern = f"the first data row's cell under the table header {header!r}"

    def search(self, text: str):
        offset = 0
        lines = text.splitlines(keepends=True)
        for number, line in enumerate(lines):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if line.lstrip().startswith("|") and self.header in cells:
                column = cells.index(self.header)
                position = offset + len(line)
                for row in lines[number + 1:]:
                    stripped = row.strip()
                    if not stripped.startswith("|"):
                        return None
                    if not re.fullmatch(r"[|\s:-]+", stripped):
                        parts = row.split("|")
                        # parts[0] is the text before the first pipe; cell `column` is parts[column + 1]
                        if column + 1 >= len(parts) - 1:
                            return None
                        cell = parts[column + 1]
                        found = re.search(r"\d+", cell)
                        if not found:
                            return None
                        start = position + sum(len(part) + 1 for part in parts[:column + 1]) + found.start()
                        return _Found(found.group(), (start, start + len(found.group())))
                    position += len(row)
                return None
            offset += len(line)
        return None


class _Found:
    def __init__(self, value: str, span: tuple[int, int]):
        self._value, self._span = value, span

    def group(self, _index: int = 1) -> str:
        return self._value

    def span(self, _index: int = 1) -> tuple[int, int]:
        return self._span


# (relative path, regex whose sole capture group is the claimed count)
CHECKS = [
    ("README.md", re.compile(r"Show all (\d+) explainers")),
    ("README.md", re.compile(r"Explainers Published \| (\d+)")),
    ("README.md", re.compile(r"(\d+) short, plain-language write-ups")),
    ("CONTRIBUTORS.md", re.compile(r"the bulk of the (\d+) explainers")),
    ("METRICS.md", re.compile(r"Explainers-(\d+)-blueviolet")),
    ("METRICS.md", re.compile(r"\| Explainers \| (\d+) \|")),
    ("ROADMAP.md", re.compile(r"(\d+) explainers published")),
    # the "Current traction" table: the cell under the "Explainers" header, found by name (#1257)
    ("ROADMAP.md", TableCell("Explainers")),
]

# Places that must list every explainer by slug (relative path, regex whose
# sole capture group is a listed slug). CONTRIBUTING.md's "Existing explainers"
# table is a short sample, not a full list, so it is not checked here.
LISTINGS = [
    ("README.md", re.compile(r"explainers/([a-z0-9-]+)\.(?:md|html)")),
    ("llms.txt", re.compile(r"/explainers/([a-z0-9-]+)\.html")),
]


def missing_listings(root: Path | None = None) -> list[tuple[str, list[str]]]:
    """(file, sorted missing slugs) for each listing that leaves out an explainer."""
    root = ROOT if root is None else root
    slugs = {path.stem for path in (root / "explainers").glob("*.md")}
    problems = []
    for rel_path, pattern in LISTINGS:
        listed = set(pattern.findall((root / rel_path).read_text(encoding="utf-8")))
        missing = sorted(slugs - listed)
        if missing:
            problems.append((rel_path, missing))
    return problems


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

    for rel_path, missing in missing_listings():
        unresolved.append((rel_path, "does not list " + ", ".join(missing)))

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
            print("\nRun 'python3 scripts/check_explainer_count.py --fix' to correct count "
                  "mentions automatically. A missing listing has to be added by hand.",
                  file=sys.stderr)
        return 1

    if not fixed:
        print(f"OK: all {len(CHECKS)} explainer-count mentions match explainers/*.md ({actual} files), "
              f"and {len(LISTINGS)} listings name every explainer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
