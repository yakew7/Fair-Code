#!/usr/bin/env python3
"""Fail when issue numbers cited in docs disagree with GitHub (#963, #981).

The roadmap, changelog, contributors and metrics cite issue numbers by hand and have been wrong
before (two sweeps listed the slow-test marker and the held-out encodings under each other's
numbers). Rules:

  * ROADMAP.md: a checked item (`- [x]`) may cite only closed issues, and an unchecked item
    (`- [ ]`) must cite at least one open issue (unless it cites none at all);
  * CHANGELOG.md: every `closes #N` / `(closes #N, #M)` must name a closed issue;
  * CONTRIBUTORS.md: every `closing issue #N` / `closing #N` must name a closed issue;
  * METRICS.md: every `#N` in a sweep note (`> ...`) must be an existing issue or pull request.

    python3 scripts/check_issue_refs.py                 # asks `gh` for the issue and PR states
    python3 scripts/check_issue_refs.py --issues FILE   # FILE: JSON [{"number": N, "state": "OPEN"|"CLOSED"|"MERGED"}]
    python3 scripts/check_issue_refs.py --assume-closed 12 --assume-closed 15   # treat #12 and #15 as closed

A pull request that fixes issue #N says `Closes #N` in its body, and its CHANGELOG and ROADMAP lines are part of the
same change, so #N is still open while the PR is checked and would fail the rules above (#1139). In a pull_request
run the script reads the PR body from the event payload (GITHUB_EVENT_PATH), takes the issues it closes (closes,
fixes or resolves, in any form GitHub accepts) and treats them as closed, saying so in the output. Citing any other
open issue as closed still fails. Locally the `Closes #N` lines of the commits ahead of the default branch of `upstream` (or
`origin`) are read the same way (#1240, #1250); any other open issue cited as closed still fails, and `--assume-closed` adds more.

Without `gh` (or a network) it prints a note and exits 0, so `make lint` works offline; pass
`--require` to make that an error (CI).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = re.compile(r"#(\d+)")
CLOSES = re.compile(r"closes? ((?:#\d+(?:,? (?:and )?)?)+)", re.IGNORECASE)
CLOSING = re.compile(r"closing\s+(?:issues?\s+)?((?:#\d+(?:(?:,| and|-)\s*)?)+)", re.IGNORECASE)


CLOSING_KEYWORD = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+(?:[\w.-]+/[\w.-]+)?#(\d+)", re.IGNORECASE)


def issues_closed_by(body: str | None) -> set[int]:
    """The issue numbers a pull request body closes, using the keywords GitHub recognises (each needs its own keyword)."""
    return {int(n) for n in CLOSING_KEYWORD.findall(body or "")}


def pull_request_closes(environ=None) -> set[int]:
    """Issues closed by the pull request this run is checking, from the event payload; empty outside a pull request."""
    env = os.environ if environ is None else environ
    if env.get("GITHUB_EVENT_NAME") not in ("pull_request", "pull_request_target"):
        return set()
    path = env.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).is_file():
        return set()
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return issues_closed_by((payload.get("pull_request") or {}).get("body"))


def find_base(runner=None, cwd: Path | None = None) -> str:
    """The ref the branch is measured against (#1250): the default branch of the `upstream` remote when there is one (a
    fork's own `origin/main` goes stale), else of `origin`, else the first of upstream/main, origin/main, upstream/master
    and origin/master that exists, else `origin/main`."""
    import subprocess
    run = runner or subprocess.run

    def git(*args: str):
        try:
            return run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True)
        except OSError:
            return None

    for remote in ("upstream", "origin"):
        done = git("symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
        if done is not None and done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    for ref in ("upstream/main", "origin/main", "upstream/master", "origin/master"):
        done = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if done is not None and done.returncode == 0:
            return ref
    return "origin/main"


def local_commits_close(base: str | None = None, runner=None, cwd: Path | None = None) -> set[int]:
    """Issues closed by the commits on this branch that are not on `base` (their `Closes #N` lines), so a local run on a
    branch that ticks ROADMAP items and writes `closes #N` in CHANGELOG passes without --assume-closed (#1240). `base`
    defaults to `find_base()`. Empty when git or `base` is not available."""
    import subprocess
    run = runner or subprocess.run
    base = base or find_base(runner, cwd)
    try:
        done = run(["git", "log", f"{base}..HEAD", "--format=%B"], cwd=cwd or ROOT, capture_output=True, text=True)
    except OSError:
        return set()
    return issues_closed_by(done.stdout) if done.returncode == 0 else set()


def load_states(issues_file: str | None) -> dict[int, str] | None:
    """{issue/PR number: "open" | "closed" | "merged"}, or None when GitHub cannot be asked."""
    if issues_file:
        data = json.loads(Path(issues_file).read_text(encoding="utf-8"))
    else:
        if shutil.which("gh") is None:
            return None
        done = subprocess.run(["gh", "issue", "list", "--state", "all", "--limit", "5000", "--json", "number,state"],
                              capture_output=True, text=True, cwd=ROOT)
        if done.returncode != 0:
            return None
        data = json.loads(done.stdout)
        prs = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "5000", "--json", "number,state"],
                             capture_output=True, text=True, cwd=ROOT)
        if prs.returncode == 0:
            data.extend(json.loads(prs.stdout))
    return {int(i["number"]): str(i["state"]).lower() for i in data}


def check_roadmap(text: str, states: dict[int, str]) -> list[str]:
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"\s*- \[([ xX])\]", line)
        if not match:
            continue
        cited = [int(n) for n in REF.findall(line) if int(n) in states]
        if not cited:
            continue
        done = match.group(1) != " "
        if done:
            open_ones = [n for n in cited if states[n] == "open"]
            if open_ones:
                problems.append(f"ROADMAP.md:{number}: checked item cites open issue(s) "
                                + ", ".join(f"#{n}" for n in open_ones))
        elif all(states[n] in ("closed", "merged") for n in cited):
            problems.append(f"ROADMAP.md:{number}: unchecked item cites only closed issue(s) "
                            + ", ".join(f"#{n}" for n in cited))
    return problems


def check_changelog(text: str, states: dict[int, str]) -> list[str]:
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        for group in CLOSES.findall(line):
            for ref in REF.findall(group):
                n = int(ref)
                if n in states and states[n] == "open":
                    problems.append(f"CHANGELOG.md:{number}: 'closes #{n}' but #{n} is still open")
    return problems


def check_contributors(text: str, states: dict[int, str]) -> list[str]:
    problems = []
    for match in CLOSING.finditer(text):
        number = text[:match.start()].count("\n") + 1
        for ref in REF.findall(match.group(1)):
            n = int(ref)
            if n in states and states[n] == "open":
                problems.append(f"CONTRIBUTORS.md:{number}: 'closing #{n}' but #{n} is still open")
    return problems


def check_metrics(text: str, states: dict[int, str]) -> list[str]:
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith(">"):
            continue
        for ref in REF.findall(line):
            n = int(ref)
            if n not in states:
                problems.append(f"METRICS.md:{number}: '#{n}' is not an existing issue or pull request")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--issues", metavar="FILE", help="issue states as JSON instead of asking gh")
    parser.add_argument("--require", action="store_true", help="fail when the issue states cannot be fetched")
    parser.add_argument("--assume-closed", type=int, action="append", default=[], metavar="N",
                        help="treat issue N as closed (repeatable); in a pull request the issues its body closes are assumed closed")
    args = parser.parse_args(argv)
    states = load_states(args.issues)
    if states is None:
        print("note: could not fetch issue states from GitHub (gh missing or offline); skipping the issue-reference check")
        return 2 if args.require else 0
    assumed = sorted((set(args.assume_closed) | pull_request_closes() | local_commits_close()) & {n for n, state in states.items() if state == "open"})
    for n in assumed:
        states[n] = "closed"
    if assumed:
        print("note: assuming " + ", ".join(f"#{n}" for n in assumed) + " closed (named by --assume-closed, closed by this pull request or by a commit ahead of the base branch)")
    problems = []
    for filename, checker in (
        ("ROADMAP.md", check_roadmap),
        ("CHANGELOG.md", check_changelog),
        ("CONTRIBUTORS.md", check_contributors),
        ("METRICS.md", check_metrics),
    ):
        path = ROOT / filename
        if path.is_file():
            problems.extend(checker(path.read_text(encoding="utf-8"), states))
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} issue reference(s) disagree with GitHub")
        return 1
    print(f"OK: issue references in ROADMAP.md, CHANGELOG.md, CONTRIBUTORS.md and METRICS.md agree with GitHub ({len(states):,} issues checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
