"""Rewriting CONTRIBUTORS.md: the sort and refresh behind --fix, and the stubs behind --stub (#1319).

Split out of scripts/check_contributors.py. These functions take text and PR data and return text; they never call gh.
"""
from __future__ import annotations

import re

if __package__:                         # imported as scripts.<name> or run as a script (see ghcall's import for why)
    from .contributors_entries import ENTRY, SECTIONS, merged_by_author, parse
else:
    from contributors_entries import ENTRY, SECTIONS, merged_by_author, parse


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
        # the section's closing `---` rule (and whatever follows it) belongs to the section, not to the entry that happens
        # to be last: split it off before sorting so it stays at the end instead of travelling with that entry
        last_entry, last_block = blocks[-1]
        rule = re.search(r"^---[ \t]*$", last_block, re.MULTILINE)
        tail = ""
        if rule:
            tail = last_block[rule.start():]
            blocks[-1] = (last_entry, last_block[:rule.start()])
        blocks.sort(key=lambda item: (-item[0]["merged"], -item[0]["commits"], item[0]["first"]))
        replacements.append((start, section_end, "".join(block for _, block in blocks) + tail))

    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


DEFAULT_AREA = "Contributor tooling & docs"


# "## Summary", "**Summary**" or a bare "Summary" line (the form the last pull requests used)
SUMMARY_HEADING = re.compile(r"^[ \t]*(?:(?:#{1,6}[ \t]*|\*\*)Summary\b[^\n]*|Summary:?)[ \t]*$", re.IGNORECASE | re.MULTILINE)


def summary_line(body: str | None) -> str | None:
    """The first line or bullet under a `Summary` heading of a pull request body, without the bullet mark (#1307); None when
    the body has no Summary section or a heading follows it before any text."""
    found = SUMMARY_HEADING.search(body or "")
    if not found:
        return None
    for line in (body or "")[found.end():].splitlines():
        line = line.strip()
        if line.startswith("#"):
            return None
        text = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line).strip()
        if text:
            return text
    return None


def stub_entry(login: str, prs: list[dict]) -> str:
    """A starting entry for `login`: header, stats line from their merged PRs (the commit count is a placeholder that
    `--fix --commits` replaces) and their PR numbers and titles as links, with a TODO sentence for the prose (#1249)."""
    mine = sorted((pr for pr in prs if ((pr.get("author") or {}).get("login") or "").lower() == login.lower()),
                  key=lambda pr: pr["number"])
    if not mine:
        raise ValueError(f"{login} has no merged pull requests in the data")
    first = min((pr.get("mergedAt") or "")[:10] for pr in mine)
    count = len(mine)
    def link(pr: dict) -> str:
        text = f"[#{pr['number']}](https://github.com/yakew7/Fair-Code/pull/{pr['number']})"
        text += f" {pr['title']}" if pr.get("title") else ""
        summary = summary_line(pr.get("body"))
        return text + (f" ({summary})" if summary and summary.rstrip(".").lower() != (pr.get("title") or "").rstrip(".").lower() else "")

    links = "; ".join(link(pr) for pr in mine)
    return (f"### [@{login}](https://github.com/{login})\n\n"
            f"**{count} merged PR{'s' if count != 1 else ''} · {count} commit{'s' if count != 1 else ''} · first merged {first}**\n\n"
            f"TODO: describe the work in a sentence or two. Merged: {links}.\n\n")


def area_names(text: str) -> list[str]:
    """The row names of the "Contributions by area" table, without their bold markers (#1294)."""
    start = text.find("## Contributions by area")
    if start == -1:
        return []
    end = text.find("\n## ", start + 5)
    section = text[start:end if end != -1 else len(text)]
    return [m.group(1).strip() for m in re.finditer(r"^\| \*\*(.+?)\*\*(?: \([^|]*\))? \|", section, re.MULTILINE)
            if m.group(1).strip() != "Area"]


def add_stub(text: str, login: str, prs: list[dict], area: str = DEFAULT_AREA) -> str:
    """Move the snapshot to the newest merged PR, insert a stub entry for `login` and list them in the `area` row of the
    Contributions by area table; the caller then sorts and refreshes the counts with `fix_document`."""
    entries, _ = parse(text)
    if login.lower() in {e["handle"].lower() for e in entries}:
        raise ValueError(f"{login} already has an entry")
    names = area_names(text)
    match = next((name for name in names if name.lower() == area.lower()), None)
    if names and match is None:
        raise ValueError(f"unknown area {area!r}; the areas are: " + "; ".join(names))
    area = match or area
    stub = stub_entry(login, prs)
    text = move_snapshot(text, prs, max(pr["number"] for pr in prs))
    at = text.find("## Contributions by area")
    if at == -1:
        raise ValueError("no 'Contributions by area' section to insert before")
    rule = text.rfind("\n---\n", 0, at)
    cut = rule + 1 if rule != -1 else at
    text = text[:cut] + stub + text[cut:]
    row = re.search(r"^\| \*\*" + re.escape(area) + r"\*\* \|.*\|$", text, re.MULTILINE)
    if row:
        text = text.replace(row.group(0), row.group(0)[:-1].rstrip() + f", [@{login}](https://github.com/{login}) |", 1)
    return text
