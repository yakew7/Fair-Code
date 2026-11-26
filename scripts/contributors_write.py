"""Rewriting CONTRIBUTORS.md: the sort and refresh behind --fix, and the stubs behind --stub (#1319).

Split out of scripts/check_contributors.py. These functions take text and PR data and return text; they never call gh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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


AREAS_FILE = Path(__file__).resolve().parent / "contributors-areas.json"


def load_default_ok(path: Path = AREAS_FILE) -> list[str]:
    """The top-level paths that deliberately use the default area row (`default_ok` in the JSON file, #1336)."""
    if not Path(path).is_file():
        return []
    listed = json.loads(Path(path).read_text(encoding="utf-8")).get("default_ok", [])
    if not isinstance(listed, list) or not all(isinstance(item, str) for item in listed):
        raise ValueError(f"{path}: default_ok must be a list of paths")
    return listed


def load_area_rules(path: Path = AREAS_FILE) -> list[tuple[str, str]]:
    """[(match, Contributions by area row)] in priority order from the JSON data file (#1335): the first rule whose `match` a
    changed path starts or ends with decides its area. A missing file is no rules; an entry without a non-empty `match` and
    `area` is an error."""
    if not Path(path).is_file():
        return []
    rules = json.loads(Path(path).read_text(encoding="utf-8")).get("rules")
    if not isinstance(rules, list):
        raise ValueError(f"{path}: rules must be a list of {{match, area}} objects")
    out = []
    for number, rule in enumerate(rules, 1):
        if not isinstance(rule, dict) or not all(isinstance(rule.get(key), str) and rule[key].strip() for key in ("match", "area")):
            raise ValueError(f"{path}: rule {number} needs a non-empty match and area")
        out.append((rule["match"], rule["area"].strip()))
    return out


AREA_RULES = load_area_rules()


def area_rule_problems(text: str, rules: list[tuple[str, str]] | None = None) -> list[str]:
    """The rules that name an area row the Contributions by area table does not have (#1335); empty when the table is absent."""
    names = {name.lower() for name in area_names(text)}
    if not names:
        return []
    return [f"contributors-areas.json: the rule for {match!r} names the area {area!r}, which is not a row of the Contributions by area table"
            for match, area in (AREA_RULES if rules is None else rules) if area.lower() not in names]


def suggest_area(login: str, prs: list[dict], names: list[str], rules: list[tuple[str, str]] | None = None) -> tuple[str, int] | None:
    """The Contributions by area row that holds most of the files `login`'s PRs changed, and how many files matched it, from the
    `files` the PR data carries (#1333); None when the data has no files or nothing matches a row of the table. Ties go to the
    row that comes first in the rules (contributors-areas.json; `rules` overrides them)."""
    rules = AREA_RULES if rules is None else rules
    counts: dict[str, int] = {}
    for pr in prs:
        if ((pr.get("author") or {}).get("login") or "").lower() != login.lower():
            continue
        for path in pr.get("files") or []:
            area = next((area for pattern, area in rules if path.startswith(pattern) or path.endswith(pattern)), None)
            if area and area in names:
                counts[area] = counts.get(area, 0) + 1
    if not counts:
        return None
    first_rule = {}
    for index, (_, area) in enumerate(rules):
        first_rule.setdefault(area, index)
    best = min(counts, key=lambda area: (-counts[area], first_rule[area]))
    return best, counts[best]


def explain_area(path: str, names: list[str], rules: list[tuple[str, str]] | None = None, default_ok: list[str] | None = None) -> str:
    """What `--stub` would do with a changed `path` (#1351): the rule that matches it and the row it names, or the default row and
    whether the path's top-level entry is one of the `default_ok` paths. Reads only; `names` are the rows of the area table."""
    rules = AREA_RULES if rules is None else rules
    default_ok = load_default_ok() if default_ok is None else default_ok
    found = next(((match, area) for match, area in rules if path.startswith(match) or path.endswith(match)), None)
    if found:
        match, area = found
        note = "" if not names or area in names else "; the table has no such row, so --stub skips this rule"
        return f"{path}: {area} (rule {match!r}{note})"
    top = path.split("/")[0]
    why = (f"{top} is listed in default_ok" if top in default_ok
           else f"no rule matches and {top} is not in default_ok, so the area-rule test would fail for a tracked file there")
    return f"{path}: {DEFAULT_AREA} (default; {why})"


def run_explain(paths: list[str], pr: int | None, text: str, prs: list[dict] | None, fetch_pr=None) -> int:
    """`--explain-area [PATH ...] [--pr N]` (#1351, #1366): print the row of each path and, for a pull request, the row `--stub` would
    choose for its author. The pull request's files come from the saved data `prs` when it has them, else from `fetch_pr(N)` (gh).
    Exit 0 even when gh is unavailable (a note), like the other gh-backed options; 1 only when there is nothing to explain."""
    names = area_names(text)
    login = None
    if pr is not None:
        saved = next((p for p in prs or [] if p.get("number") == pr and p.get("files") is not None), None)
        found = ({"login": (saved.get("author") or {}).get("login"), "files": saved["files"]} if saved
                 else fetch_pr(pr) if fetch_pr else None)
        if found is None:
            print(f"note: could not read the files of pull request #{pr} (gh missing or offline, or no such pull request)")
            return 0
        login, paths = found.get("login"), [*paths, *found["files"]]
        print(f"#{pr} by {login or 'an unknown author'}: {len(found['files'])} changed file(s)")
    if not paths:
        print("nothing to explain: give PATH arguments or a pull request with changed files" if pr is None else f"#{pr} has no changed files")
        return 1 if pr is None else 0
    for path in paths:
        print(explain_area(path, names))
    if pr is not None and login:
        pick = suggest_area(login, [{"author": {"login": login}, "files": found["files"]}], names)
        print(f"--stub would list {login} in: " + (f"{pick[0]} ({pick[1]} changed file(s))" if pick
                                                    else f"{DEFAULT_AREA} (no changed file matches a row of the table)"))
    return 0


def choose_areas(logins: list[str], prs: list[dict], text: str, explicit: str | None) -> tuple[dict[str, str], list[str]]:
    """{login: area row} for a stub run and the notes saying where a suggestion came from (#1333): `explicit` (--area) for
    everyone, else the row holding most of each person's changed files, else DEFAULT_AREA."""
    areas, notes = {}, []
    for login in logins:
        found = None if explicit is not None else suggest_area(login, prs, area_names(text))
        areas[login] = explicit if explicit is not None else (found[0] if found else DEFAULT_AREA)
        if found:
            notes.append(f"{login}: {found[0]} ({found[1]} changed file(s))")
    return areas, notes


def foreign_commit_authors(login: str, prs: list[dict]) -> dict[int, list[str]]:
    """{PR number: logins other than `login` (and the maintainer) that authored a commit of one of `login`'s PRs}, from the
    `commit_authors` the PR data carries (#1326); empty when the data has none."""
    found: dict[int, list[str]] = {}
    for pr in prs:
        if ((pr.get("author") or {}).get("login") or "").lower() != login.lower():
            continue
        others = sorted({a for a in pr.get("commit_authors") or [] if a.lower() not in (login.lower(), "yakew7")}, key=str.lower)
        if others:
            found[pr["number"]] = others
    return found


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
        notes = []
        if summary and summary.rstrip(".").lower() != (pr.get("title") or "").rstrip(".").lower():
            notes.append(summary)
        closing = pr.get("closing_issues") or []
        if closing:                                        # the entries' own phrasing (#1308)
            notes.append(f"closing issue{'s' if len(closing) > 1 else ''} " + ", ".join(f"#{n}" for n in closing))
        return text + (f" ({', '.join(notes)})" if notes else "")

    links = "; ".join(link(pr) for pr in mine)
    foreign = foreign_commit_authors(login, prs)
    note = ""
    if foreign:                                  # GitHub credits a commit to its author, not to whoever opened the PR (#1326)
        parts = [f"{', '.join('#' + str(n) for n in sorted(group))} "
                 f"({' and '.join('[@' + a + '](https://github.com/' + a + ')' for a in authors)})"
                 for authors, group in _group_by_authors(foreign)]
        note = (" The commit" + ("s" if sum(len(v) for v in foreign.values()) > 1 else "") + " of " + "; ".join(parts)
                + " " + ("are" if sum(len(v) for v in foreign.values()) > 1 else "is")
                + " authored by someone else, so GitHub counts it for that account, not this one.")
    return (f"### [@{login}](https://github.com/{login})\n\n"
            f"**{count} merged PR{'s' if count != 1 else ''} · {count} commit{'s' if count != 1 else ''} · first merged {first}**\n\n"
            f"TODO: describe the work in a sentence or two. Merged: {links}.{note}\n\n")


def exception_suggestions(entries: list[dict], prs: list[dict], logins: list[str]) -> list[str]:
    """The lines to add to scripts/contributors-exceptions.json after stubbing `logins` (#1326): an `unlisted_authors` line for a
    foreign commit author with no entry, and a `commit_exceptions` line for a stubbed person none of whose commits is
    their own (no API counts those for their account)."""
    listed = {e["handle"].lower() for e in entries}
    lines = []
    for login in logins:
        foreign = foreign_commit_authors(login, prs)
        for number, authors in sorted(foreign.items()):
            for author in authors:
                if author.lower() not in listed:
                    lines.append(f'unlisted_authors: "{author.lower()}": "authored the commit of PR #{number}, which {login} '
                                 f'opened; no merged pull request of their own"')
        mine = [pr for pr in prs if ((pr.get("author") or {}).get("login") or "").lower() == login.lower()]
        if mine and all("commit_authors" in pr and login.lower() not in {a.lower() for a in pr["commit_authors"]} for pr in mine):
            numbers = ", ".join("#" + str(pr["number"]) for pr in mine)
            lines.append(f'commit_exceptions: "{login.lower()}": "the commit of {numbers} is authored by '
                         f'{", ".join(sorted({a for n in foreign.values() for a in n}, key=str.lower)) or "someone else"}, '
                         f'so no API counts it for this account"')
    return lines


def _group_by_authors(foreign: dict[int, list[str]]) -> list[tuple[list[str], list[int]]]:
    """[(authors, [PR numbers])] with the PRs that share the same foreign authors together."""
    groups: dict[tuple[str, ...], list[int]] = {}
    for number, authors in sorted(foreign.items()):
        groups.setdefault(tuple(authors), []).append(number)
    return [(list(authors), numbers) for authors, numbers in groups.items()]


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
