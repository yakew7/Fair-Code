#!/usr/bin/env python3
"""Print the next weekly row for METRICS.md from GitHub (#1242).

Each sweep adds a row (stars, forks, watching, contributors, issues closed) typed by hand, and
`check_traction.py --live` can only say afterwards that the numbers are stale. This reads the live figures from
GitHub (the same ones `check_traction.py --live` compares), counts the issues closed since the Monday of the ISO week,
and carries the cells GitHub cannot supply (social views, countries, code audits) over from the newest row:

    python3 scripts/draft_metrics_row.py                    # row for today's ISO week, from gh
    python3 scripts/draft_metrics_row.py --date 2026-11-03  # row for the week containing that date
    python3 scripts/draft_metrics_row.py --live-data FILE   # FILE: {"stars", "forks", "watching", "contributors", "issues_closed"}

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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = "| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |"
ROW = re.compile(r"^\|\s*\d{4}-W\d+\s*\|.*\|\s*$", re.M)


def iso_week(day: datetime.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_start(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def latest_row(text: str) -> list[str]:
    """The cells of the newest weekly row."""
    rows = ROW.findall(text)
    if not rows:
        raise ValueError("METRICS.md has no weekly row")
    return [cell.strip() for cell in rows[-1].strip().strip("|").split("|")]


def build_row(previous: list[str], live: dict, day: datetime.date) -> str:
    """The next row: GitHub's figures for stars, forks, watching, contributors and issues closed, the rest carried over."""
    week = iso_week(day)
    if previous[0] == week:
        raise ValueError(f"the newest row is already for {week}")
    cells = [week, str(live["stars"]), str(live["forks"]), str(live["watching"]), str(live["contributors"]),
             previous[5], previous[6], str(live["issues_closed"]), previous[8]]
    return "| " + " | ".join(cells) + " |"


def fetch_issues_closed(since: datetime.date, repo: str) -> int | None:
    done = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f",
                           f"q=repo:{repo} is:issue is:closed closed:>={since.isoformat()}", "--jq", ".total_count"],
                          capture_output=True, text=True)
    return int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip().isdigit() else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=ROOT / "METRICS.md")
    parser.add_argument("--date", type=datetime.date.fromisoformat, default=None, help="any date in the week (default: today)")
    parser.add_argument("--live-data", metavar="FILE", help="GitHub's figures as JSON instead of asking gh")
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
    try:
        print(build_row(latest_row(args.file.read_text(encoding="utf-8")), live, day))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
