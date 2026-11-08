#!/usr/bin/env python3
"""Print the next weekly row for METRICS.md from GitHub (#1242).

Each sweep adds a row (stars, forks, watching, contributors, issues closed) typed by hand, and
`check_traction.py --live` can only say afterwards that the numbers are stale. This reads the live figures from
GitHub (the same ones `check_traction.py --live` compares), counts the issues closed since the Monday of the ISO week,
and carries the cells GitHub cannot supply (social views, countries, code audits) over from the newest row:

    python3 scripts/draft_metrics_row.py                    # row for today's ISO week, from gh
    python3 scripts/draft_metrics_row.py --date 2026-11-03  # row for the week containing that date
    python3 scripts/draft_metrics_row.py --live-data FILE   # FILE: {"stars", "forks", "watching", "contributors", "issues_closed"}
    python3 scripts/draft_metrics_row.py --note             # also print a draft sweep note: closed issues, figure changes, new people
    python3 scripts/draft_metrics_row.py --update           # refresh the newest row when it is already this week's (with --apply: in place)
    python3 scripts/draft_metrics_row.py --apply            # also write the row and the figures into METRICS.md, README.md and ROADMAP.md
    python3 scripts/draft_metrics_row.py --pending-closes   # also count the open issues the commits ahead of the base close on merge

A sweep row's Issues Closed is what is already closed this week plus what the sweep's commits close when they merge, so
`--pending-closes` adds the still-open issues named by `Closes #N` in the commits ahead of the base branch (a saved
--live-data file can carry the number as "pending_closes").

It prints one line and changes nothing; paste it under the last row of the weekly table, then update the figures in
README.md and ROADMAP.md and the badges. If the newest row is already for that week it says so and exits 1.
"""
from __future__ import annotations

import argparse
import datetime
import importlib
import json
import re
import shutil
import sys
from pathlib import Path

if __package__:                         # imported as scripts.<name> (tests, python -m) or run as a script (scripts/ is sys.path[0])
    from .ghcall import run_gh
else:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from ghcall import run_gh

ROOT = Path(__file__).resolve().parent.parent
HEADER = "| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |"
ROW = re.compile(r"^\|\s*\d{4}-W\d+\s*\|.*\|\s*$", re.M)


def iso_week(day: datetime.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_start(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def latest_row(text: str, back: int = 0) -> list[str]:
    """The cells of the newest weekly row (`back` rows earlier with back > 0)."""
    rows = ROW.findall(text)
    if len(rows) <= back:
        raise ValueError("METRICS.md has no weekly row" if not rows else f"METRICS.md has no weekly row {back} before the newest")
    return [cell.strip() for cell in rows[-1 - back].strip().strip("|").split("|")]


def build_row(previous: list[str], live: dict, day: datetime.date, update: bool = False) -> str:
    """The next row: GitHub's figures for stars, forks, watching, contributors and issues closed, the rest carried over.
    With `update` the newest row may already be for this week: it is rebuilt from its own hand-written cells (#1286)."""
    week = iso_week(day)
    if previous[0] == week and not update:
        raise ValueError(f"the newest row is already for {week} (use --update to refresh it)")
    if update and previous[0] != week:
        raise ValueError(f"the newest row is for {previous[0]}, not {week}: drop --update to add this week's row")
    closed = live["issues_closed"] + live.get("pending_closes", 0)
    cells = [week, str(live["stars"]), str(live["forks"]), str(live["watching"]), str(live["contributors"]),
             previous[5], previous[6], str(closed), previous[8]]
    return "| " + " | ".join(cells) + " |"


def fetch_issues_closed(since: datetime.date, repo: str) -> int | None:
    done = run_gh(["gh", "api", "-X", "GET", "search/issues", "-f",
                   f"q=repo:{repo} is:issue is:closed closed:>={since.isoformat()}", "--jq", ".total_count"])
    return int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip().isdigit() else None


FIGURE_ROWS = {"stars": "GitHub Stars", "forks": "Forks", "watching": "Watching"}
BADGES = {"stars": "Stars", "contributors": "Contributors", "forks": "Forks", "watching": "Watching"}
TARGET_ROWS = {"stars": "Stars", "forks": "Forks", "watching": "Watching", "contributors": "Contributors"}


def _sub_once(text: str, pattern: str, replacement: str, what: str) -> str:
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"could not find {what}")
    return text


def apply_figures(root: Path, live: dict, row: str, replace: bool = False) -> list[Path]:
    """Write the new weekly `row` and the live stars, forks, watching and contributors into every place they are typed:
    the README traction table (External Contributors is one below the total), the ROADMAP Current traction row, the
    METRICS badges, its targets table and the weekly table (#1252). The cells check_traction.py reads are the ones
    changed, so `check_traction.py --live` passes afterwards; nothing else is touched. Returns the files rewritten."""
    texts = {name: (root / name).read_text(encoding="utf-8") for name in ("README.md", "ROADMAP.md", "METRICS.md")}

    readme = texts["README.md"]
    for figure, label in FIGURE_ROWS.items():
        readme = _sub_once(readme, rf"^(\|\s*{re.escape(label)}\s*\|\s*)\d+(\s*\|)", rf"\g<1>{live[figure]}\g<2>", f"the README {label} row")
    readme = _sub_once(readme, r"^(\|\s*External Contributors\s*\|\s*)\d+(\s*\|)", rf"\g<1>{live['contributors'] - 1}\g<2>",
                       "the README External Contributors row")
    texts["README.md"] = readme

    roadmap_lines = texts["ROADMAP.md"].splitlines(keepends=True)
    header = next((i for i, line in enumerate(roadmap_lines) if line.startswith("| Stars | Contributors | Forks | Watching |")), None)
    data = next((i for i in range(header + 1, header + 4) if re.search(r"\d", roadmap_lines[i]) and roadmap_lines[i].startswith("|")), None) \
        if header is not None else None
    if data is None:
        raise ValueError("could not find the ROADMAP Current traction row")
    cells = roadmap_lines[data].rstrip("\n").strip().strip("|").split("|")
    for index, figure in enumerate(("stars", "contributors", "forks", "watching")):
        cells[index] = f" {live[figure]} "
    roadmap_lines[data] = "|" + "|".join(cells) + "|\n"
    texts["ROADMAP.md"] = "".join(roadmap_lines)

    metrics = texts["METRICS.md"]
    for figure, name in BADGES.items():
        metrics = _sub_once(metrics, rf"(img\.shields\.io/badge/{name}-)\d+(-)", rf"\g<1>{live[figure]}\g<2>", f"the METRICS {name} badge")
    for figure, name in TARGET_ROWS.items():
        metrics = _sub_once(metrics, rf"^(\|\s*{name}\s*\|\s*)\d+(\s*\|)", rf"\g<1>{live[figure]}\g<2>", f"the METRICS targets {name} row")
    # the targets table's Issues closed row follows the new weekly row: "N (this week, since <Monday>)" (#1273)
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    year, week = cells[0].split("-W")
    monday = datetime.date.fromisocalendar(int(year), int(week), 1)
    metrics = _sub_once(metrics, r"^(\|\s*Issues closed\s*\|\s*)[^|]*?(\s*\|)",
                        rf"\g<1>{cells[7]} (this week, since {monday.isoformat()})\g<2>", "the METRICS targets Issues closed row")
    rows = list(ROW.finditer(metrics))
    if not rows:
        raise ValueError("METRICS.md has no weekly row to append after")
    if replace:                         # refresh the newest row in place (--update) instead of appending a new week
        metrics = metrics[:rows[-1].start()] + row + metrics[rows[-1].end():]
    else:
        metrics = metrics[:rows[-1].end()] + "\n" + row + metrics[rows[-1].end():]
    texts["METRICS.md"] = metrics

    changed = []
    for name, text in texts.items():
        if text != (root / name).read_text(encoding="utf-8"):
            (root / name).write_text(text, encoding="utf-8")
            changed.append(root / name)
    return changed


def draft_note(week: str, since: datetime.date, previous: list[str], live: dict, closed: list[dict], pending: list[str]) -> str:
    """A starting sweep note (a markdown quote line): the issues closed since `since` as `title (#N)` items, how the figures
    moved against the previous row and who merged after the contributors snapshot (#1262). It is a draft to edit."""
    items = "; ".join(f"{issue['title']} (#{issue['number']})" for issue in sorted(closed, key=lambda i: i["number"]))
    moves = []
    for name, cell, now in (("stars", previous[1], live["stars"]), ("forks", previous[2], live["forks"]),
                            ("watching", previous[3], live["watching"]), ("contributors", previous[4], live["contributors"])):
        moves.append(f"{name} `{cell} → {now}`" if str(now) != cell else f"{name} unchanged at {now}")
    people = [line.split(":")[0] for line in pending if line and not line.startswith(" ")]
    note = (f"> **{week} - DRAFT, {len(closed)} issue(s) closed since {since.isoformat()}:** "
            + (items if items else "none yet") + ". Figures: " + ", ".join(moves) + ".")
    if people:
        note += " Merged after the CONTRIBUTORS.md snapshot: " + ", ".join(f"@{name}" for name in people) + "."
    return note


def fetch_closed_issues(since: datetime.date, repo: str) -> list[dict] | None:
    done = run_gh(["gh", "issue", "list", "--repo", repo, "--state", "closed", "--limit", "500", "--search",
                   f"closed:>={since.isoformat()}", "--json", "number,title"])
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None


def fetch_open_among(numbers, repo: str) -> int | None:
    """How many of the issues `numbers` are still open (an already closed one is in the closed count), or None on failure."""
    total = 0
    for number in sorted(numbers):
        done = run_gh(["gh", "api", f"repos/{repo}/issues/{number}", "--jq", ".state"])
        if done.returncode != 0:
            return None
        total += done.stdout.strip() == "open"
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=ROOT / "METRICS.md")
    parser.add_argument("--date", type=datetime.date.fromisoformat, default=None, help="any date in the week (default: today)")
    parser.add_argument("--live-data", metavar="FILE", help="GitHub's figures as JSON instead of asking gh")
    parser.add_argument("--pending-closes", action="store_true",
                        help="add the open issues the commits ahead of the base branch close on merge to Issues Closed")
    parser.add_argument("--note", action="store_true",
                        help="also print a draft sweep note (closed issues, figure changes, people merged since the snapshot)")
    parser.add_argument("--update", action="store_true",
                        help="refresh the newest row when it is already for this week (instead of refusing), with --apply in place")
    parser.add_argument("--apply", action="store_true",
                        help="also write the row and the figures into METRICS.md, README.md and ROADMAP.md (next to --file)")
    args = parser.parse_args(argv)
    day = args.date or datetime.date.today()

    if args.live_data:
        live = json.loads(Path(args.live_data).read_text(encoding="utf-8"))
    else:
        if not (sys.path and str(ROOT) in sys.path):
            sys.path.insert(0, str(ROOT))
        traction = importlib.import_module("scripts.check_traction")
        live = traction.fetch_live() if shutil.which("gh") else None
        if live is None:
            print("error: needs the GitHub CLI (gh) signed in and online, or --live-data FILE", file=sys.stderr)
            return 2
        closed = fetch_issues_closed(week_start(day), traction.REPO)
        if closed is None:
            print("error: could not count the issues closed this week", file=sys.stderr)
            return 2
        live["issues_closed"] = closed
        if args.pending_closes:
            refs = importlib.import_module("scripts.check_issue_refs")
            pending = fetch_open_among(refs.local_commits_close(), traction.REPO)
            if pending is None:
                print("error: could not look up the issues the local commits close", file=sys.stderr)
                return 2
            live["pending_closes"] = pending
    try:
        metrics_text = args.file.read_text(encoding="utf-8")
        previous = latest_row(metrics_text)
        row = build_row(previous, live, day, update=args.update)
        if args.update:                 # the note compares with the week before the one being refreshed
            previous = latest_row(metrics_text, back=1)
        print(row)
        if args.note:
            if not args.live_data:
                contributors = importlib.import_module("scripts.check_contributors")
                prs = contributors.fetch_prs()
                text = (ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
                entries, through = contributors.parse(text)
                live["pending"] = contributors.pending(entries, prs, through) if prs is not None else []
                live["closed_issues"] = fetch_closed_issues(week_start(day), traction.REPO) or []
            print()
            print(draft_note(iso_week(day), week_start(day), previous, live, live.get("closed_issues", []), live.get("pending", [])))
        if args.apply:
            changed = apply_figures(args.file.parent, live, row, replace=args.update)
            print("updated: " + ", ".join(path.name for path in changed), file=sys.stderr)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
