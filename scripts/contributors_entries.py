"""Parsing CONTRIBUTORS.md and the checks that need no GitHub access (#1319).

Split out of scripts/check_contributors.py: the entry parser, the PR-count, order, area-table and TODO checks, the pending list
and the identity-map check. Nothing here talks to gh or reads the exception file: the callers pass the data in, so the checks
can be tested (and reused) on their own.
"""
from __future__ import annotations

import re

MAINTAINER = "yakew7"


SECTIONS = ("Core contributors", "Contributors")


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


def area_table_problems(text: str, entries: list[dict]) -> list[str]:
    """Entries whose handle is in no row of the "Contributions by area" table (#1259); empty when the table is absent."""
    start = text.find("## Contributions by area")
    if start == -1:
        return []
    end = text.find("\n## ", start + 5)
    table = text[start:end if end != -1 else len(text)].lower()
    return [f"{e['handle']}: has an entry but is in no row of the Contributions by area table"
            for e in entries if not e["deleted"] and f"@{e['handle'].lower()}]" not in table]


def todo_problems(text: str) -> list[str]:
    """Entries that still contain the `TODO:` sentence `--stub` writes (#1285), so a placeholder cannot reach the published
    page. An entry is the text from its header to the next entry or section."""
    starts = [m.start() for m in ENTRY.finditer(text)]
    heads = [m.start() for m in re.finditer(r"^## ", text, re.MULTILINE)]
    problems = []
    for match in ENTRY.finditer(text):
        end = min([p for p in starts + heads if p > match.start()] or [len(text)])
        if "TODO:" in text[match.start():end]:
            handle = HANDLE.search(match.group("header"))
            name = (handle.group(1) or handle.group(2)) if handle else match.group("header")
            problems.append(f"{name}: the entry still has a TODO placeholder sentence (written by --stub); describe their work")
    return problems


def commit_problems(entries: list[dict], live: dict[str, int], after: dict[str, int], exceptions: dict[str, str]) -> tuple[list[str], list[str]]:
    """(problems, skipped notes): each entry's commit count against live contributors count minus commits after the snapshot."""
    live = {login.lower(): n for login, n in live.items()}
    after = {login.lower(): n for login, n in after.items()}
    problems, skipped = [], []
    for entry in entries:
        handle = entry["handle"].lower()
        if entry["deleted"]:
            continue
        if handle not in live:
            if handle in exceptions:
                skipped.append(f"{entry['handle']}: commit count not compared ({exceptions[handle]})")
            else:
                problems.append(f"{entry['handle']}: not in the contributors API and not in COMMIT_EXCEPTIONS, "
                                f"so its {entry['commits']} commit(s) cannot be checked")
            continue
        expected = live[handle] - after.get(handle, 0)
        if expected != entry["commits"]:
            problems.append(f"{entry['handle']}: file says {entry['commits']} commits, GitHub says {expected} at the snapshot "
                            f"({live[handle]} now, {after.get(handle, 0)} since)")
    return problems, skipped


def pending(entries: list[dict], prs: list[dict], through: int | None) -> list[str]:
    """One line per human author with merged PRs after the snapshot PR: who has no entry yet and whose count has grown."""
    listed = {e["handle"].lower() for e in entries}
    later: dict[str, list[int]] = {}
    titles = {pr["number"]: pr.get("title") for pr in prs}
    commit_authors = {pr["number"]: pr.get("commit_authors") or [] for pr in prs}
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
        # one indented line per PR with its title, so the entry can be written without looking each one up (#1258)
        lines += [f"    #{n} {titles[n]}" for n in sorted(later[login]) if titles.get(n)]
        # a commit authored by someone other than the PR author: that person is credited by GitHub, not this account (#1316)
        for n in sorted(later[login]):
            for other in sorted(commit_authors.get(n, []), key=str.lower):
                if other.lower() != login.lower() and other.lower() != MAINTAINER:
                    state = ("has an entry" if other.lower() in listed
                             else "has no entry: give them one, or add them to unlisted_authors in "
                                  "scripts/contributors-exceptions.json")
                    lines.append(f"    #{n} has a commit authored by {other}, not by {login}; {other} {state}")
    return lines


IDENTITY_ROW = re.compile(r"^\| \[@([^\]]+)\]\([^)]*\) \| (.+) \|$", re.MULTILINE)


def identity_map(text: str) -> dict[str, set[str]]:
    """{lower-case handle: {lower-case git author names}} from the Git identity map table."""
    return {m.group(1).lower(): {n.lower() for n in re.findall(r"`([^`]+)`", m.group(2))}
            for m in IDENTITY_ROW.finditer(text)}


def unmapped_authors(text: str, authors: list[tuple[str, str, int]], unlisted: dict[str, str]) -> list[str]:
    """Lines for the git authors (name, email, commits) that map to no entry: not in the identity map, not a handle,
    not a noreply address of a handle, not a bot and not in unlisted (#1236)."""
    entries, _ = parse(text)
    handles = {e["handle"].lower() for e in entries} | {MAINTAINER}
    names = {name for row in identity_map(text).values() for name in row}
    lines = []
    for name, email, count in authors:
        low, mail = name.lower(), email.lower()
        if ("[bot]" in low or "[bot]" in mail or mail == "noreply@github.com" or low in unlisted
                or mail.endswith("@anthropic.com") or low.startswith("copilot")):
            continue
        local = mail.split("@")[0].split("+")[-1] if mail.endswith("@users.noreply.github.com") else None
        if low in names or low in handles or (local and local in handles):
            continue
        lines.append(f"{name} <{email}>: {count} commit(s) map to no entry or Git identity map row")
    return lines
