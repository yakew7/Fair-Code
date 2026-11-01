#!/usr/bin/env python3
"""Fail when CONTRIBUTORS.md disagrees with the merged pull requests on GitHub (#1149).

The file's rule is "ordered by merged PR count, most first, ties broken by commit count, then by earliest
first-merged date", and its counts are kept by hand each sweep. This parses every entry header and its
`**N merged PRs · M commits · first merged YYYY-MM-DD**` line and checks, per section (Core contributors,
Contributors):

  * the merged PR count and the first-merged date against `gh pr list --state merged`, counting only pull
    requests up to the PR the snapshot line names ("covering everything merged through **PR #N**"), since
    anything merged later is expected to be missing until the next sweep;
  * the order of the entries against the rule above;
  * that every merged-PR author up to the snapshot (bots and the maintainer aside) has an entry.

Commit counts are only used to break ties in the order unless `--commits` is given (#1199). The contributors API is
live and cannot be asked for a past date, so with `--commits` the expected count at the snapshot is the live
contributors-graph count minus the commits the author made after the snapshot PR was merged (the commits API with
`since`), which keeps the file's meaning of "GitHub's contributors graph" and costs one request per entry. An entry
whose header says "account deleted" has no login left on GitHub (its pull requests show a ghost author), so its
counts are listed as skipped, not failed.

    python3 scripts/check_contributors.py                 # asks `gh` for the merged pull requests
    python3 scripts/check_contributors.py --prs FILE      # FILE: gh pr list --state merged --limit 5000 --json number,author,mergedAt
    python3 scripts/check_contributors.py --commits       # also compare commit counts (about 60 gh requests)
    python3 scripts/check_contributors.py --commits-data F # F: {"live": {login: n}, "after_snapshot": {login: n}}
    python3 scripts/check_contributors.py --pending       # who merged after the snapshot (exit 1 if anyone), for the weekly report
    python3 scripts/check_contributors.py --fix --commits # also refresh commit counts and move the snapshot to the newest merged PR
    python3 scripts/check_contributors.py --fix            # refresh known counts/dates and sort entries in place

Without `gh` (or a network) it prints a note and exits 0, so `make lint` works offline; pass `--require` to make
that an error. `--fix` requires GitHub data or `--prs FILE` and preserves entry prose and commit counts. Exit code:
0 = consistent (or skipped), 1 = a stale count, date, order or missing entry.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAINTAINER = "yakew7"
SECTIONS = ("Core contributors", "Contributors")
# Entries whose commits no GitHub API counts, so --commits cannot compare them (#1234). Both the contributors API and
# `commits?author=LOGIN` return nothing for them because the commit email is not linked to the account (the file's
# Git identity map explains the same for TanishGoyal-Dev and Ayaan-20-11). Anyone else missing from the API fails.
COMMIT_EXCEPTIONS = {
    "ayaan-20-11": "commit email not linked to the GitHub account",
    "raonishanth2000-hub": "commit email not linked to the GitHub account",
    "ege-arhan": "commit email not linked to the GitHub account",
}

ENTRY = re.compile(
    r"^### (?P<header>.+)\n\n\*\*(?P<merged>\d+) merged PRs? · (?P<commits>\d+) commits? · "
    r"first merged (?P<first>\d{4}-\d{2}-\d{2})\*\*",
    re.MULTILINE,
)
SNAPSHOT = re.compile(r"covering everything merged through \*\*PR #(\d+)\*\*")
HANDLE = re.compile(r"\[@([^\]]+)\]\(https://github\.com/[^)]+\)|`([^`]+)`")


def parse(text: str) -> tuple[list[dict], int | None]:
    """([entry, ...], snapshot PR number). An entry has section, handle, merged, commits, first, deleted."""
    snapshot = SNAPSHOT.search(text)
    sections = [(m.start(), m.group(1)) for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)]
    entries = []
    for match in ENTRY.finditer(text):
        section = next((name for start, name in reversed(sections) if start < match.start()), "")
        if section not in SECTIONS:
            continue
        header = match.group("header")
        handle = HANDLE.search(header)
        entries.append({
            "section": section,
            "handle": (handle.group(1) or handle.group(2)) if handle else header,
            "merged": int(match.group("merged")),
            "commits": int(match.group("commits")),
            "first": match.group("first"),
            "deleted": "account deleted" in header,
        })
    return entries, int(snapshot.group(1)) if snapshot else None


def merged_by_author(prs: list[dict], through: int | None) -> dict[str, dict]:
    """{login: {"count": N, "first": earliest merge date}} for the human authors of merged PRs up to `through`."""
    authors: dict[str, dict] = {}
    for pr in prs:
        login = (pr.get("author") or {}).get("login") or ""
        if (pr.get("author") or {}).get("is_bot") or login.startswith("app/") or login == "":
            continue
        if through is not None and pr["number"] > through:
            continue
        info = authors.setdefault(login, {"count": 0, "first": "9999-99-99"})
        info["count"] += 1
        info["first"] = min(info["first"], (pr.get("mergedAt") or "")[:10] or info["first"])
    return authors


def check(entries: list[dict], prs: list[dict], through: int | None) -> tuple[list[str], list[str]]:
    """(problems, skipped notes)."""
    problems: list[str] = []
    skipped: list[str] = []
    authors = merged_by_author(prs, through)
    listed = set()
    for entry in entries:
        handle = entry["handle"]
        listed.add(handle.lower())
        if entry["deleted"]:
            skipped.append(f"{handle}: account deleted, counts not comparable")
            continue
        actual = authors.get(next((k for k in authors if k.lower() == handle.lower()), ""), None)
        if actual is None:
            problems.append(f"{handle}: listed with {entry['merged']} merged PRs but GitHub shows none")
            continue
        if actual["count"] != entry["merged"]:
            problems.append(f"{handle}: file says {entry['merged']} merged PRs, GitHub says {actual['count']}")
        if actual["first"] != entry["first"]:
            problems.append(f"{handle}: file says first merged {entry['first']}, GitHub says {actual['first']}")
    for login in sorted(authors, key=str.lower):
        if login.lower() not in listed and login.lower() != MAINTAINER:
            problems.append(f"{login}: {authors[login]['count']} merged PRs on GitHub but no entry in the file")
    for section in SECTIONS:
        rows = [e for e in entries if e["section"] == section]
        want = sorted(rows, key=lambda e: (-e["merged"], -e["commits"], e["first"]))
        for position, (have, expected) in enumerate(zip(rows, want), 1):
            if have is not expected:
                problems.append(f"{section}: entry {position} is {have['handle']} "
                                f"({have['merged']} PRs, {have['commits']} commits, {have['first']}) "
                                f"but the rule puts {expected['handle']} "
                                f"({expected['merged']} PRs, {expected['commits']} commits, {expected['first']}) there")
                break
    return problems, skipped


def commit_problems(entries: list[dict], live: dict[str, int], after: dict[str, int]) -> tuple[list[str], list[str]]:
    """(problems, skipped notes): each entry's commit count against live contributors count minus commits after the snapshot."""
    live = {login.lower(): n for login, n in live.items()}
    after = {login.lower(): n for login, n in after.items()}
    problems, skipped = [], []
    for entry in entries:
        handle = entry["handle"].lower()
        if entry["deleted"]:
            continue
        if handle not in live:
            if handle in COMMIT_EXCEPTIONS:
                skipped.append(f"{entry['handle']}: commit count not compared ({COMMIT_EXCEPTIONS[handle]})")
            else:
                problems.append(f"{entry['handle']}: not in the contributors API and not in COMMIT_EXCEPTIONS, "
                                f"so its {entry['commits']} commit(s) cannot be checked")
            continue
        expected = live[handle] - after.get(handle, 0)
        if expected != entry["commits"]:
            problems.append(f"{entry['handle']}: file says {entry['commits']} commits, GitHub says {expected} at the snapshot "
                            f"({live[handle]} now, {after.get(handle, 0)} since)")
    return problems, skipped


def fetch_commit_data(entries: list[dict], since: str, repo: str = "yakew7/Fair-Code") -> dict | None:
    """{"live": {login: commits}, "after_snapshot": {login: commits since `since`}} from gh api, or None on failure."""
    if shutil.which("gh") is None:
        return None

    def api(*args: str):
        done = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
        return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    people = api("--paginate", "--slurp", f"repos/{repo}/contributors?per_page=100")
    if people is None:
        return None
    live = {p["login"]: p["contributions"] for page in people for p in page if p.get("type") != "Bot"}
    logins = [e["handle"] for e in entries if not e["deleted"] and e["handle"].lower() in {k.lower() for k in live}]

    def since_count(login: str) -> int | None:
        done = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/commits?author={login}&since={since}&per_page=100",
                               "--jq", ".[].sha"], capture_output=True, text=True)
        return len(done.stdout.split()) if done.returncode == 0 else None

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        counts = list(pool.map(since_count, logins))
    if any(count is None for count in counts):
        return None
    after = dict(zip(logins, counts))
    return {"live": live, "after_snapshot": after}


def snapshot_time(prs: list[dict], through: int | None) -> str | None:
    """One second after the snapshot PR was merged, so its own merge commit is not counted as 'after'."""
    from datetime import datetime, timedelta, timezone
    merged = next((pr.get("mergedAt") for pr in prs if pr["number"] == through), None)
    if not merged:
        return None
    moment = datetime.strptime(merged, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(seconds=1)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def pending(entries: list[dict], prs: list[dict], through: int | None) -> list[str]:
    """One line per human author with merged PRs after the snapshot PR: who has no entry yet and whose count has grown."""
    listed = {e["handle"].lower() for e in entries}
    later: dict[str, list[int]] = {}
    for pr in prs:
        author = pr.get("author") or {}
        login = author.get("login") or ""
        if author.get("is_bot") or login.startswith("app/") or not login or login.lower() == MAINTAINER:
            continue
        if through is not None and pr["number"] > through:
            later.setdefault(login, []).append(pr["number"])
    lines = []
    for login in sorted(later, key=str.lower):
        numbers = ", ".join(f"#{n}" for n in sorted(later[login]))
        lines.append(f"{login}: {len(later[login])} merged PR(s) after the snapshot ({numbers}); "
                     + ("count to update" if login.lower() in listed else "no entry yet"))
    return lines


SNAPSHOT_LINE = re.compile(r"\*\*Snapshot:\*\* \d{4}-\d{2}-\d{2}, covering everything merged through \*\*PR #\d+\*\*")


def move_snapshot(text: str, prs: list[dict], new_through: int) -> str:
    """Point the snapshot line at PR `new_through` and the day it was merged (#1235)."""
    merged = next((pr.get("mergedAt") for pr in prs if pr["number"] == new_through), None)
    if not merged:
        raise ValueError(f"PR #{new_through} is not in the merged pull request data")
    line = f"**Snapshot:** {merged[:10]}, covering everything merged through **PR #{new_through}**"
    text, count = SNAPSHOT_LINE.subn(line, text, count=1)
    if count != 1:
        raise ValueError("could not find the '**Snapshot:** DATE, covering everything merged through **PR #N**' line")
    return text


def fix_document(text: str, prs: list[dict], through: int | None, commits: dict[str, int] | None = None) -> str:
    """Refresh known PR counts/dates (and, given `commits` {login: count at the snapshot}, commit counts) and order
    entries without editing their prose."""
    entries, _ = parse(text)
    commits = {login.lower(): n for login, n in (commits or {}).items()}
    authors = merged_by_author(prs, through)
    by_login = {login.lower(): info for login, info in authors.items()}
    refreshed_entries = []
    for entry in entries:
        refreshed = dict(entry)
        actual = by_login.get(entry["handle"].lower())
        if actual is not None and not entry["deleted"]:
            refreshed["merged"] = actual["count"]
            refreshed["first"] = actual["first"]
        if entry["handle"].lower() in commits and not entry["deleted"]:
            refreshed["commits"] = commits[entry["handle"].lower()]
        refreshed_entries.append(refreshed)

    section_heads = [(m.start(), m.group(1)) for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)]
    entry_matches = list(ENTRY.finditer(text))
    replacements = []
    stats_pattern = re.compile(r"\*\*\d+ merged PRs? · \d+ commits? · first merged \d{4}-\d{2}-\d{2}\*\*")
    for section_index, (section_start, section) in enumerate(section_heads):
        if section not in SECTIONS:
            continue
        section_end = section_heads[section_index + 1][0] if section_index + 1 < len(section_heads) else len(text)
        matches = [m for m in entry_matches if section_start < m.start() < section_end]
        if not matches:
            continue
        start = matches[0].start()
        section_entries = [entry for entry in refreshed_entries if entry["section"] == section]
        blocks = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else section_end
            block = text[match.start():end]
            entry = section_entries[index]
            stats = (f"**{entry['merged']} merged PR{'s' if entry['merged'] != 1 else ''} · "
                     f"{entry['commits']} commit{'s' if entry['commits'] != 1 else ''} · "
                     f"first merged {entry['first']}**")
            block, count = stats_pattern.subn(stats, block, count=1)
            if count != 1:
                raise ValueError(f"could not locate statistics line for {entry['handle']}")
            blocks.append((entry, block))
        blocks.sort(key=lambda item: (-item[0]["merged"], -item[0]["commits"], item[0]["first"]))
        replacements.append((start, section_end, "".join(block for _, block in blocks)))

    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def fetch_prs() -> list[dict] | None:
    if shutil.which("gh") is None:
        return None
    done = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", "5000",
                           "--json", "number,author,mergedAt"], capture_output=True, text=True)
    return json.loads(done.stdout) if done.returncode == 0 else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=ROOT / "CONTRIBUTORS.md")
    parser.add_argument("--prs", metavar="FILE", help="merged pull requests as JSON instead of asking gh")
    parser.add_argument("--require", action="store_true", help="fail instead of skipping when GitHub cannot be reached")
    parser.add_argument("--commits", action="store_true", help="also compare commit counts with GitHub's contributors graph at the snapshot (needs gh)")
    parser.add_argument("--commits-data", metavar="FILE", help="commit data as JSON instead of asking gh (implies --commits)")
    parser.add_argument("--pending", action="store_true", help="list authors who merged after the snapshot and exit 1 if there are any")
    parser.add_argument("--fix", action="store_true", help="rewrite known PR counts/dates and sort contributor entries")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8")
    entries, through = parse(text)
    if not entries:
        print(f"error: no contributor entries found in {args.file}")
        return 1
    prs = json.loads(Path(args.prs).read_text(encoding="utf-8")) if args.prs else fetch_prs()
    if prs is None:
        if args.fix:
            print("error: --fix needs merged pull request data from GitHub or --prs FILE")
            return 2
        print("note: could not fetch merged pull requests from GitHub (gh missing or offline); "
              "skipping the contributors check")
        return 1 if args.require else 0
    if args.fix:
        commit_counts = None
        if args.commits:
            # move the snapshot to the newest merged PR and take the commit counts as of that moment
            newest = max(pr["number"] for pr in prs)
            since = snapshot_time(prs, newest)
            data = fetch_commit_data(entries, since) if since else None
            if data is None:
                print("error: --fix --commits needs the GitHub CLI (gh) signed in and online")
                return 2
            after = {k.lower(): v for k, v in data.get("after_snapshot", {}).items()}
            commit_counts = {login: n - after.get(login.lower(), 0) for login, n in data["live"].items()
                             if login.lower() not in COMMIT_EXCEPTIONS}
            text = move_snapshot(text, prs, newest)
            through = newest
        fixed = fix_document(text, prs, through, commit_counts)
        if fixed != args.file.read_text(encoding="utf-8"):
            args.file.write_text(fixed, encoding="utf-8")
            print(f"updated: {args.file}")
        text = fixed
        entries, through = parse(text)
    if through is None:
        print("note: no 'covering everything merged through **PR #N**' snapshot line found; counting every merged PR")

    if args.pending:
        later = pending(entries, prs, through)
        for line in later:
            print(line)
        print(f"{len(later)} author(s) merged after the snapshot (PR #{through})." if later
              else f"Nobody has merged since the snapshot (PR #{through}).")
        return 1 if later else 0

    problems, skipped = check(entries, prs, through)
    if args.commits or args.commits_data:
        since = snapshot_time(prs, through)
        if args.commits_data:
            data = json.loads(Path(args.commits_data).read_text(encoding="utf-8"))
        elif since is None:
            print("error: --commits needs the snapshot PR in the merged pull request data")
            return 2
        else:
            data = fetch_commit_data(entries, since)
        if data is None:
            print("error: --commits needs the GitHub CLI (gh) signed in and online")
            return 2
        more_problems, more_skipped = commit_problems(entries, data["live"], data.get("after_snapshot", {}))
        problems += more_problems
        skipped += more_skipped
    for note in skipped:
        print(f"skipped: {note}")
    if problems:
        print(f"CONTRIBUTORS.md disagrees with GitHub ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OK: {len(entries)} entries match the merged pull requests through #{through} and are in rule order"
          + (", with commit counts at the snapshot." if args.commits or args.commits_data else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
