#!/usr/bin/env python3
"""Checks that the traction figures agree across README.md, ROADMAP.md and METRICS.md (#1097).

The same numbers (stars, forks, contributors, watching, social reach, countries, audits) are typed by
hand in the README's Traction table, the ROADMAP's "Current traction" row, METRICS.md's badges and the
newest row of its weekly table. When one is edited without the others they drift. This reads each
figure from each place and fails, naming the files and the values, when two of them disagree. It also
checks that the README's "Show N completed items" count equals the number of `- [x]` lines inside that
section. It compares the files with each other, never with GitHub, so it works offline. The explainer
count has its own checker, scripts/check_explainer_count.py.

    python3 scripts/check_traction.py
    python3 scripts/check_traction.py --live              # compare live figures, including Issues Closed for the latest ISO week
    python3 scripts/check_traction.py --live-data FILE    # same, from saved GitHub figures including issues_closed

Exit code: 0 = everything agrees, 1 = at least one disagreement or a figure that could not be found.

The files can all agree and still be stale (stars were 52 in all three while GitHub said 53), so --live reads
stars, forks, watchers (subscribers), contributors without bots, and Issues Closed for the latest ISO week from `gh api` and names every place whose
figure differs. It is off by default, so `make lint` and a pull request never depend on the network; the weekly
traction workflow runs it. The social reach, countries and audits figures have no GitHub source and are not
compared. Contributors count everyone the contributors API lists who is not a bot, owner included, matching
ROADMAP.md and METRICS.md.

The README table calls its contributor figure "External Contributors", which excludes the repository
owner, so it is expected to be exactly one lower than the total used in ROADMAP.md and METRICS.md.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

try:                                    # run as a script (scripts/ on the path) or imported as scripts.<name>
    from scripts.ghcall import run_gh
except ImportError:
    from ghcall import run_gh

ROOT = Path(__file__).resolve().parent.parent
REPO = "yakew7/Fair-Code"
LIVE_FIGURES = ("stars", "forks", "watching", "contributors", "issues_closed")

FIGURES = ("stars", "contributors", "forks", "watching", "social", "countries", "audits")

# README row label -> figure; the contributors row is offset by the owner (see the module docstring).
README_ROWS = {
    "GitHub Stars": "stars",
    "External Contributors": "contributors",
    "Forks": "forks",
    "Watching": "watching",
    "Combined Social Reach (Instagram + LinkedIn)": "social",
    "Countries Reached (Website Visitors)": "countries",
    "Code Audits Published": "audits",
}
README_OFFSETS = {"contributors": -1}

ROADMAP_HEADER = "| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits |"
ROADMAP_COLUMNS = ("stars", "contributors", "forks", "watching", "social", "countries", "audits")

METRICS_BADGES = {"Stars": "stars", "Contributors": "contributors", "Forks": "forks",
                  "Watching": "watching", "Countries": "countries"}
# | Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |
METRICS_ROW_COLUMNS = {1: "stars", 2: "forks", 3: "watching", 4: "contributors", 5: "social",
                       6: "countries", 7: "issues_closed", 8: "audits"}

# Observations are (figure, where, value), value being the number as written, e.g. "30K+" or "51".
Observation = tuple[str, str, str]


def _clean(cell: str) -> str:
    """A table cell without markdown noise or a trailing " total"."""
    return re.sub(r"\s+total$", "", cell.replace("*", "").replace("`", "").strip())


def _number(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def readme_observations(text: str) -> tuple[list[Observation], list[str]]:
    found, problems = [], []
    for label, figure in README_ROWS.items():
        m = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([^|\n]+?)\s*\|", text, re.M)
        if not m:
            problems.append(f"README.md: no Traction table row for {label!r}")
            continue
        value = _clean(m.group(1))
        offset = README_OFFSETS.get(figure)
        number = _number(value)
        if offset and number is not None:
            value = str(number - offset)
        found.append((figure, f"README.md ({label})", value))
    return found, problems


def roadmap_observations(text: str) -> tuple[list[Observation], list[str]]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(ROADMAP_HEADER):
            for row in lines[i + 1:i + 4]:
                if row.startswith("|") and re.search(r"\d", row):
                    cells = [_clean(c) for c in row.strip().strip("|").split("|")]
                    return [(fig, f"ROADMAP.md (Current traction, {fig})", cells[idx])
                            for idx, fig in enumerate(ROADMAP_COLUMNS) if idx < len(cells)], []
            break
    return [], ["ROADMAP.md: no 'Current traction' table found"]


def metrics_observations(text: str) -> tuple[list[Observation], list[str]]:
    found, problems = [], []
    for name, figure in METRICS_BADGES.items():
        m = re.search(r"img\.shields\.io/badge/" + name + r"-([^-?]+)-", text)
        if m:
            found.append((figure, f"METRICS.md (badge {name})", _clean(m.group(1).replace("%2B", "+"))))
        else:
            problems.append(f"METRICS.md: no {name} badge")
    rows = [ln for ln in text.splitlines() if re.match(r"\|\s*\d{4}-W\d+", ln)]
    if not rows:
        problems.append("METRICS.md: no weekly row found")
    else:
        row = rows[-1]
        cells = [_clean(c) for c in row.strip().strip("|").split("|")]
        week = cells[0]
        for idx, figure in METRICS_ROW_COLUMNS.items():
            if idx < len(cells) and cells[idx] not in ("-", ""):
                found.append((figure, f"METRICS.md (latest weekly row, {week})", cells[idx]))
    return found, problems


def latest_metrics_week(text: str) -> str | None:
    """The ISO year-week on the newest weekly row, or None when no row exists."""
    rows = [line for line in text.splitlines() if re.match(r"\|\s*\d{4}-W\d+", line)]
    if not rows:
        return None
    cells = [_clean(cell) for cell in rows[-1].strip().strip("|").split("|")]
    return cells[0] if cells else None


def iso_week_bounds(week: str) -> tuple[str, str]:
    """Inclusive Monday and Sunday dates for an ISO year-week label."""
    match = re.fullmatch(r"(?P<year>\d{4})-W(?P<week>\d{2})", week)
    if not match:
        raise ValueError(f"METRICS.md: latest week {week!r} is not a valid ISO year-week")
    try:
        monday = date.fromisocalendar(int(match["year"]), int(match["week"]), 1)
    except ValueError as exc:
        raise ValueError(f"METRICS.md: latest week {week!r} is not a valid ISO year-week") from exc
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def completed_items(text: str) -> tuple[int | None, int | None]:
    """(claimed, counted) for the README's "Show N completed items" section; None if not found."""
    m = re.search(r"Show (\d+) completed items", text)
    if not m:
        return None, None
    end = text.find("</details>", m.end())
    section = text[m.end():end if end != -1 else len(text)]
    return int(m.group(1)), len(re.findall(r"^- \[x\]", section, re.M))


def collect(root: Path = ROOT) -> tuple[list[Observation], list[str], dict[str, str]]:
    """(every figure as written, the problems finding them, the file texts)."""
    texts = {}
    for name in ("README.md", "ROADMAP.md", "METRICS.md"):
        path = root / name
        texts[name] = path.read_text(encoding="utf-8") if path.is_file() else ""
    observations: list[Observation] = []
    problems: list[str] = []
    for found, missing in (readme_observations(texts["README.md"]), roadmap_observations(texts["ROADMAP.md"]),
                           metrics_observations(texts["METRICS.md"])):
        observations += found
        problems += missing
    return observations, problems, texts


def check(root: Path = ROOT) -> list[str]:
    """Every disagreement or missing figure, as one message each (empty when all agree)."""
    observations, problems, texts = collect(root)
    for figure in FIGURES:
        seen = [(where, value) for fig, where, value in observations if fig == figure]
        if len({value for _, value in seen}) > 1:
            detail = "; ".join(f"{where} says {value}" for where, value in seen)
            problems.append(f"{figure} disagree: {detail}")
    claimed, counted = completed_items(texts["README.md"])
    if claimed is None:
        problems.append("README.md: no 'Show N completed items' summary found")
    elif claimed != counted:
        problems.append(f"README.md: 'Show {claimed} completed items' but the section has {counted} '- [x]' lines")
    return problems


def fetch_live(repo: str = REPO, week_bounds: tuple[str, str] | None = None) -> dict[str, int] | None:
    """Live repository figures and, when requested, closed issues for an inclusive ISO-week date range."""
    if shutil.which("gh") is None:
        return None

    def api(*args: str):
        done = run_gh(["gh", "api", *args])
        if done.returncode != 0 or not done.stdout.strip():
            return None
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError:
            return None

    info = api(f"repos/{repo}")
    people = api("--paginate", "--slurp", f"repos/{repo}/contributors?per_page=100")
    if not isinstance(info, dict) or not isinstance(people, list):
        return None
    people = [p for page in people for p in (page if isinstance(page, list) else [])]
    live = {"stars": info["stargazers_count"], "forks": info["forks_count"],
            "watching": info["subscribers_count"],
            "contributors": sum(1 for p in people if p.get("type") != "Bot" and not p.get("login", "").endswith("[bot]"))}
    if week_bounds is not None:
        start, end = week_bounds
        query = f"repo:{repo} is:issue is:closed closed:{start}..{end}"
        closed = api("--method", "GET", "search/issues", "-f", f"q={query}")
        if (not isinstance(closed, dict) or closed.get("incomplete_results") is not False
                or not isinstance(closed.get("total_count"), int)):
            return None
        live["issues_closed"] = closed["total_count"]
    return live


def live_differences(observations: list[Observation], live: dict[str, int]) -> list[str]:
    """One message per place whose figure differs from GitHub (a figure written as "30K+" is not numeric and is skipped)."""
    return [f"{figure}: {where} says {value}, GitHub says {live[figure]}"
            for figure, where, value in observations
            if figure in live and _number(value) is not None and int(value) != live[figure]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="also compare live figures, including Issues Closed for the latest METRICS week (needs gh)")
    parser.add_argument("--live-data", metavar="FILE", help="GitHub's figures, including issues_closed, as JSON instead of asking gh (implies --live)")
    args = parser.parse_args(argv or [])
    problems = check()
    if args.live or args.live_data:
        observations, _, texts = collect()
        week_bounds = None
        week = latest_metrics_week(texts["METRICS.md"])
        if week is not None:
            try:
                week_bounds = iso_week_bounds(week)
            except ValueError as exc:
                problems.append(str(exc))
        if args.live_data:
            live = json.loads(Path(args.live_data).read_text(encoding="utf-8"))
            needs_issues_closed = any(figure == "issues_closed" for figure, _, _ in observations)
            if needs_issues_closed and (not isinstance(live, dict) or type(live.get("issues_closed")) is not int):
                print("error: --live-data JSON must include an integer issues_closed count for the latest METRICS week", file=sys.stderr)
                return 2
        else:
            if not any(figure == "issues_closed" for figure, _, _ in observations):
                week_bounds = None
            live = fetch_live(week_bounds=week_bounds)
        if live is None:
            print("error: --live could not fetch GitHub figures; check that gh is installed, signed in and online, and that search results are complete", file=sys.stderr)
            return 2
        problems += live_differences(observations, live)
    if problems:
        print("Traction figures are out of step:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("Traction figures agree across README.md, ROADMAP.md and METRICS.md"
          + (" and with GitHub." if args.live or args.live_data else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
