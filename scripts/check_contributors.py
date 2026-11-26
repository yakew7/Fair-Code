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
  * that every merged-PR author up to the snapshot (bots and the maintainer aside) has an entry;
  * that every entry's handle appears in at least one row of the "Contributions by area" table;
  * that no entry still holds the `TODO:` sentence `--stub` writes.

Commit counts are only used to break ties in the order unless `--commits` is given (#1199). The contributors API is
live and cannot be asked for a past date, so with `--commits` the expected count at the snapshot is the live
contributors-graph count minus the commits the author made after the snapshot PR was merged (the commits API with
`since`), which keeps the file's meaning of "GitHub's contributors graph" and costs one request per entry. An entry
whose header says "account deleted" has no login left on GitHub (its pull requests show a ghost author), so its
counts are listed as skipped, not failed.

    python3 scripts/check_contributors.py                 # asks `gh` for the merged pull requests
    python3 scripts/check_contributors.py --prs FILE      # FILE: gh pr list --state merged --limit 5000 --json number,author,mergedAt,title,body
    python3 scripts/check_contributors.py --commits       # also compare commit counts (about 60 gh requests)
    python3 scripts/check_contributors.py --commits --save-commits F  # also keep the fetched data (a --fix --commits run fetches once)
    python3 scripts/check_contributors.py --commits-data F # F: {"live": {login: n}, "after_snapshot": {login: n}}
    python3 scripts/check_contributors.py --identities   # every git commit author maps to an entry or an identity map row
    python3 scripts/check_contributors.py --pending       # who merged after the snapshot (exit 1 if anyone), for the weekly report
    python3 scripts/check_contributors.py --pending --json  # the same as a JSON list of {login, prs, first_merged, has_entry}, [] when nobody (#1354)
    python3 scripts/check_contributors.py --explain-area PATH [PATH ...]  # which area rule a changed path matches; changes nothing (#1351)
    python3 scripts/check_contributors.py --explain-area --pr 1356  # the same for every file of a pull request, plus the row --stub would pick (#1366)
    python3 scripts/check_contributors.py --stub LOGIN [LOGIN ...]  # start an entry for a new contributor (then --fix --commits)
    python3 scripts/check_contributors.py --stub LOGIN --area "Profiler - web"   # list them in another area row (default: Contributor tooling & docs)
    python3 scripts/check_contributors.py --stub LOGIN --commits   # the same, with the commit counts taken from GitHub too
    python3 scripts/check_contributors.py --fix --commits # also refresh commit counts and move the snapshot to the newest merged PR
    python3 scripts/check_contributors.py --fix            # refresh known counts/dates and sort entries in place

The pull request data (`--prs FILE`, or what `gh pr list` returns when it is fetched) is a JSON list with, per merged PR:

  number, author {login, is_bot}, mergedAt, title, body   what `gh pr list --state merged --json ...` returns
  commit_authors  [login, ...]   optional: who authored its commits; --pending lists the ones that are not the PR author (#1316)
  closing_issues  [number, ...]  optional: the issues it closes; --pending and --stub print them as "closes #N" (#1331, #1308)
  files           [path, ...]    optional: the paths it changed; --stub suggests the area row from them (#1333)

The optional keys are filled from one `gh pr view` call per PR when the data comes from GitHub, and are used as given when a
file carries them (offline runs and tests). An example:

    [{"number": 1311, "author": {"login": "ranjanasri6", "is_bot": false}, "mergedAt": "2026-11-09T10:00:00Z",
      "title": "Handle empty groups", "body": "## Summary\\n- Handles empty groups",
      "commit_authors": ["PRIYANKA2272004"], "closing_issues": [1303], "files": ["faircode/significance.py"]}]

Without `gh` (or a network) it prints a note and exits 0, so `make lint` works offline; pass `--require` to make
that an error. `--fix` requires GitHub data or `--prs FILE` and preserves entry prose and commit counts. Exit code:
0 = consistent (or skipped), 1 = a stale count, date, order or missing entry.
"""
from __future__ import annotations

import argparse
import json
import shutil  # noqa: F401 - tests patch shutil.which through this module
import subprocess  # noqa: F401 - tests patch subprocess.run through this module
import sys
from pathlib import Path

# The parsing and checks, the text rewriting and the GitHub calls live in the three modules below (#1319); the names are
# imported here so `scripts.check_contributors.<name>` keeps working, and the wiring that tests patch (the exception
# dictionaries, the fetchers, the commit-data cache and the run_* functions) stays in this file.
if __package__:                         # imported as scripts.<name> (tests, python -m) or run as a script (scripts/ is sys.path[0])
    from .contributors_entries import (  # noqa: F401
        ENTRY, HANDLE, IDENTITY_ROW, MAINTAINER, SECTIONS, SNAPSHOT, area_table_problems, check, identity_map,
        merged_by_author, parse, pending, pending_json, todo_problems)
    from .contributors_entries import commit_problems as _commit_problems
    from .contributors_entries import unmapped_authors as _unmapped_authors
    from .contributors_github import (  # noqa: F401
        TRAILER, add_details, fetch_commit_data, fetch_pr_details, fetch_prs, git_authors, run_pending, snapshot_time, fetch_pr_files)
    from .contributors_write import (  # noqa: F401
        AREA_RULES, DEFAULT_AREA, SNAPSHOT_LINE, SUMMARY_HEADING, add_stub, area_names, area_rule_problems,
        choose_areas, exception_suggestions, explain_area, fix_document, run_explain, foreign_commit_authors, load_area_rules, load_default_ok,
        move_snapshot, stub_entry, suggest_area, summary_line)
else:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from contributors_entries import (  # noqa: F401
        ENTRY, HANDLE, IDENTITY_ROW, MAINTAINER, SECTIONS, SNAPSHOT, area_table_problems, check, identity_map,
        merged_by_author, parse, pending, pending_json, todo_problems)
    from contributors_entries import commit_problems as _commit_problems
    from contributors_entries import unmapped_authors as _unmapped_authors
    from contributors_github import (  # noqa: F401
        TRAILER, add_details, fetch_commit_data, fetch_pr_details, fetch_prs, git_authors, run_pending, snapshot_time, fetch_pr_files)
    from contributors_write import (  # noqa: F401
        AREA_RULES, DEFAULT_AREA, SNAPSHOT_LINE, SUMMARY_HEADING, add_stub, area_names, area_rule_problems,
        choose_areas, exception_suggestions, explain_area, fix_document, run_explain, foreign_commit_authors, load_area_rules, load_default_ok,
        move_snapshot, stub_entry, suggest_area, summary_line)

ROOT = Path(__file__).resolve().parent.parent


EXCEPTIONS_FILE = ROOT / "scripts" / "contributors-exceptions.json"


def load_exceptions(path: Path = EXCEPTIONS_FILE) -> tuple[dict[str, str], dict[str, str]]:
    """(COMMIT_EXCEPTIONS, UNLISTED_AUTHORS) from the JSON data file (#1270), keys lower-cased. A missing file is two empty
    lists; an entry without a reason, or a section that is not an object, is an error, so every exception says why.

    commit_exceptions: a contributor whose commits no GitHub API counts (the commit email is not linked to the account), so
    `--commits` reports them as excused. unlisted_authors: a git author name (or co-author) who deliberately has no entry,
    so `--identities` skips them."""
    if not Path(path).is_file():
        return {}, {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lists = []
    for section in ("commit_exceptions", "unlisted_authors"):
        entries = data.get(section, {})
        if not isinstance(entries, dict):
            raise ValueError(f"{path}: {section} must be an object of name: reason")
        for name, reason in entries.items():
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{path}: {section} entry {name!r} needs a reason")
        lists.append({str(name).lower(): reason.strip() for name, reason in entries.items()})
    return lists[0], lists[1]


COMMIT_EXCEPTIONS, UNLISTED_AUTHORS = load_exceptions()


def commit_problems(entries: list[dict], live: dict[str, int], after: dict[str, int]) -> tuple[list[str], list[str]]:
    """Each entry's commit count against the live contributors count minus commits after the snapshot, excusing the
    people in COMMIT_EXCEPTIONS (see contributors_entries.commit_problems)."""
    return _commit_problems(entries, live, after, COMMIT_EXCEPTIONS)


def unmapped_authors(text: str, authors: list[tuple[str, str, int]]) -> list[str]:
    """The git authors that map to no entry or identity row, skipping UNLISTED_AUTHORS (see
    contributors_entries.unmapped_authors)."""
    return _unmapped_authors(text, authors, UNLISTED_AUTHORS)


_COMMIT_DATA: dict[str, dict] = {}


def get_commit_data(args, entries: list[dict], since: str) -> dict | None:
    """The commit data for `since`, fetched once per run (`--fix --commits` compares after it rewrites, which used to
    fetch the same sixty requests again) and written to `--save-commits FILE` when given (#1248)."""
    if since not in _COMMIT_DATA:
        data = fetch_commit_data(entries, since)
        if data is None:
            return None
        _COMMIT_DATA[since] = data
        if getattr(args, "save_commits", None):
            Path(args.save_commits).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _COMMIT_DATA[since]


def run_stub(args, text: str, prs: list[dict], fetch_details=None) -> int:
    """Start an entry for each login of `args.stub`: all of them are validated first (an existing entry or an author with no
    merged PRs stops the run before anything is written), added, then sorted and written once, and with `--commits` the commit
    data is fetched once for everyone (#1299, #1271)."""
    logins = list(dict.fromkeys(args.stub))
    # the details (closing issues) of each stubbed person's PRs, unless the saved data already carries them (#1308, #1332)
    wanted = [pr["number"] for pr in prs if ((pr.get("author") or {}).get("login") or "").lower() in {name.lower() for name in logins}
              and "closing_issues" not in pr]
    if wanted and fetch_details is not None:
        add_details(prs, fetch_details(wanted))
    stubbed = text
    areas, areas_chosen = choose_areas(logins, prs, text, args.area)
    try:
        for login in logins:
            stubbed = add_stub(stubbed, login, prs, area=areas[login])
    except ValueError as error:
        print(f"error: {error}")
        return 1
    newest = max(pr["number"] for pr in prs)
    commit_counts, note = None, "commit counts are placeholders: run --fix --commits (or add --commits to --stub)"
    if args.commits:
        since = snapshot_time(prs, newest)
        data = get_commit_data(args, parse(stubbed)[0], since) if since else None
        if data is None:
            print("error: --stub --commits needs the GitHub CLI (gh) signed in and online")
            return 2
        after = {k.lower(): v for k, v in data.get("after_snapshot", {}).items()}
        commit_counts = {login: n - after.get(login.lower(), 0) for login, n in data["live"].items()
                         if login.lower() not in COMMIT_EXCEPTIONS}
        known = {login.lower() for login in commit_counts}
        missing = [login for login in logins if login.lower() not in known]
        if not missing:
            note = "commit counts come from the contributors graph at the new snapshot"
        else:
            note = (f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not in the contributors API yet, so "
                    f"{'their commit count is' if len(missing) == 1 else 'their commit counts are'} still the PR-count "
                    "placeholder; run --fix --commits later")
    args.file.write_text(fix_document(stubbed, prs, newest, commit_counts), encoding="utf-8")
    print(f"added {'a stub entry' if len(logins) == 1 else 'stub entries'} for {', '.join(logins)} and moved the snapshot to "
          f"PR #{newest}; replace the TODO sentence{'s' if len(logins) > 1 else ''}; {note}")
    if areas_chosen:
        print("area chosen from the changed files (use --area NAME to override): " + "; ".join(areas_chosen))
    suggestions = exception_suggestions(parse(stubbed)[0], prs, logins)
    if suggestions:
        print("a commit of these pull requests is authored by someone other than the PR author; add to "
              "scripts/contributors-exceptions.json if that is right:")
        for line in suggestions:
            print(f"  {line}")
    return 0


def run_identities(args, text: str) -> int:
    lines = unmapped_authors(text, git_authors())
    for line in lines:
        print(f"  - {line}")
    print(f"{len(lines)} git author(s) are not mapped in {args.file.name}." if lines
          else "OK: every git author maps to an entry or an identity map row.")
    return 1 if lines else 0


def run_fix(args, text: str, entries: list[dict], through: int | None, prs: list[dict]) -> tuple[str, int | None] | int:
    """Rewrite the file (`--fix`, with `--commits` also the commit counts and the snapshot line); the new (text, through),
    or an exit code when the data could not be fetched."""
    commit_counts = None
    if args.commits:
        # move the snapshot to the newest merged PR and take the commit counts as of that moment
        newest = max(pr["number"] for pr in prs)
        since = snapshot_time(prs, newest)
        data = get_commit_data(args, entries, since) if since else None
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
    return fixed, parse(fixed)[1]


def run_check(args, text: str, entries: list[dict], prs: list[dict], through: int | None) -> int:
    problems, skipped = check(entries, prs, through)
    problems += area_table_problems(text, entries)
    problems += todo_problems(text)
    if args.file.resolve() == (ROOT / "CONTRIBUTORS.md").resolve():      # the rules describe this repository's own table (#1335)
        problems += area_rule_problems(text)
    with_commits = bool(args.commits or args.commits_data)
    if with_commits:
        since = snapshot_time(prs, through)
        if args.commits_data:
            data = json.loads(Path(args.commits_data).read_text(encoding="utf-8"))
        elif since is None:
            print("error: --commits needs the snapshot PR in the merged pull request data")
            return 2
        else:
            data = get_commit_data(args, entries, since)
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
          + (", with commit counts at the snapshot." if with_commits else "."))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=ROOT / "CONTRIBUTORS.md")
    parser.add_argument("--prs", metavar="FILE", help="merged pull requests as JSON instead of asking gh")
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS_FILE, metavar="FILE",
                        help="JSON file of commit_exceptions and unlisted_authors, each name with a reason (default: scripts/contributors-exceptions.json)")
    parser.add_argument("--require", action="store_true", help="fail instead of skipping when GitHub cannot be reached")
    parser.add_argument("--commits", action="store_true", help="also compare commit counts with GitHub's contributors graph at the snapshot (needs gh)")
    parser.add_argument("--commits-data", metavar="FILE", help="commit data as JSON instead of asking gh (implies --commits)")
    parser.add_argument("--save-commits", metavar="FILE", help="write the fetched commit data to FILE (usable later as --commits-data)")
    parser.add_argument("--identities", action="store_true", help="check that every git commit author maps to an entry or an identity map row (needs the git history)")
    parser.add_argument("--pending", action="store_true", help="list authors who merged after the snapshot and exit 1 if there are any")
    parser.add_argument("--json", action="store_true", help="with --pending: print a JSON list of {login, prs, first_merged, has_entry} instead of text")
    parser.add_argument("--explain-area", metavar="PATH", nargs="*", help="print the Contributions by area row each changed path maps to, and why; reads only")
    parser.add_argument("--pr", type=int, metavar="N", help="with --explain-area: also explain the files of pull request N and the row --stub would choose for its author (needs gh, or --prs data with files)")
    parser.add_argument("--stub", metavar="LOGIN", nargs="+", help="add a starting entry for a new contributor (moves the snapshot, sorts, lists them in an area row)")
    parser.add_argument("--area", default=None, metavar="NAME",
                        help="with --stub: the Contributions by area row to list the new people in (default: the row that holds "
                             f"most of the files their PRs changed, else {DEFAULT_AREA!r})")
    parser.add_argument("--fix", action="store_true", help="rewrite known PR counts/dates and sort contributor entries")
    args = parser.parse_args(argv)
    if args.json and not args.pending:
        parser.error("--json only goes with --pending")
    if args.pr is not None and args.explain_area is None:
        parser.error("--pr only goes with --explain-area")

    if args.exceptions != EXCEPTIONS_FILE:
        COMMIT_EXCEPTIONS.clear()
        UNLISTED_AUTHORS.clear()
        for target, loaded in zip((COMMIT_EXCEPTIONS, UNLISTED_AUTHORS), load_exceptions(args.exceptions)):
            target.update(loaded)
    text = args.file.read_text(encoding="utf-8")
    entries, through = parse(text)
    if not entries:
        print(f"error: no contributor entries found in {args.file}")
        return 1
    if args.explain_area is not None:
        saved = json.loads(Path(args.prs).read_text(encoding="utf-8")) if args.prs else None
        return run_explain(args.explain_area, args.pr, text, saved, fetch_pr_files)
    if args.identities:
        return run_identities(args, text)
    prs = json.loads(Path(args.prs).read_text(encoding="utf-8")) if args.prs else fetch_prs()
    if prs is None:
        if args.fix:
            print("error: --fix needs merged pull request data from GitHub or --prs FILE")
            return 2
        print("note: could not fetch merged pull requests from GitHub (gh missing or offline); "
              "skipping the contributors check")
        return 1 if args.require else 0
    if args.stub:
        # saved data (--prs FILE) is used as it is; only data fetched from GitHub gets the details looked up too
        return run_stub(args, text, prs, fetch_details=None if args.prs else fetch_pr_details)
    if args.fix:
        fixed = run_fix(args, text, entries, through, prs)
        if isinstance(fixed, int):
            return fixed
        text, through = fixed
        entries = parse(text)[0]
    if through is None:
        print("note: no 'covering everything merged through **PR #N**' snapshot line found; counting every merged PR")
    if args.pending:
        # saved data (--prs FILE) is used as it is; only data fetched from GitHub gets the commit authors looked up too
        return run_pending(entries, prs, through, fetch=None if args.prs else fetch_pr_details,
                           as_json=args.json)
    return run_check(args, text, entries, prs, through)


if __name__ == "__main__":
    sys.exit(main())
