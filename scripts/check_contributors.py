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
    python3 scripts/check_contributors.py --stub LOGIN [LOGIN ...]  # start an entry for a new contributor (then --fix --commits)
    python3 scripts/check_contributors.py --stub LOGIN --area "Profiler - web"   # list them in another area row (default: Contributor tooling & docs)
    python3 scripts/check_contributors.py --stub LOGIN --commits   # the same, with the commit counts taken from GitHub too
    python3 scripts/check_contributors.py --fix --commits # also refresh commit counts and move the snapshot to the newest merged PR
    python3 scripts/check_contributors.py --fix            # refresh known counts/dates and sort entries in place

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
        merged_by_author, parse, pending, todo_problems)
    from .contributors_entries import commit_problems as _commit_problems
    from .contributors_entries import unmapped_authors as _unmapped_authors
    from .contributors_github import (  # noqa: F401
        TRAILER, fetch_closing_issues, fetch_commit_authors, fetch_commit_data, fetch_prs, git_authors, snapshot_time)
    from .contributors_write import (  # noqa: F401
        DEFAULT_AREA, SNAPSHOT_LINE, SUMMARY_HEADING, add_stub, area_names, fix_document, move_snapshot, stub_entry,
        summary_line)
else:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from contributors_entries import (  # noqa: F401
        ENTRY, HANDLE, IDENTITY_ROW, MAINTAINER, SECTIONS, SNAPSHOT, area_table_problems, check, identity_map,
        merged_by_author, parse, pending, todo_problems)
    from contributors_entries import commit_problems as _commit_problems
    from contributors_entries import unmapped_authors as _unmapped_authors
    from contributors_github import (  # noqa: F401
        TRAILER, fetch_closing_issues, fetch_commit_authors, fetch_commit_data, fetch_prs, git_authors, snapshot_time)
    from contributors_write import (  # noqa: F401
        DEFAULT_AREA, SNAPSHOT_LINE, SUMMARY_HEADING, add_stub, area_names, fix_document, move_snapshot, stub_entry,
        summary_line)

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


def run_stub(args, text: str, prs: list[dict], fetch_closing=None) -> int:
    """Start an entry for each login of `args.stub`: all of them are validated first (an existing entry or an author with no
    merged PRs stops the run before anything is written), added, then sorted and written once, and with `--commits` the commit
    data is fetched once for everyone (#1299, #1271)."""
    logins = list(dict.fromkeys(args.stub))
    # the issues each stubbed person's PRs close, unless the saved data already carries them (#1308)
    wanted = [pr["number"] for pr in prs if ((pr.get("author") or {}).get("login") or "").lower() in {name.lower() for name in logins}
              and "closing_issues" not in pr]
    if wanted and fetch_closing is not None:
        found = fetch_closing(wanted) or {}
        for pr in prs:
            if pr["number"] in found:
                pr["closing_issues"] = found[pr["number"]]
    stubbed = text
    try:
        for login in logins:
            stubbed = add_stub(stubbed, login, prs, area=args.area)
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


def run_pending(entries: list[dict], prs: list[dict], through: int | None, fetch=None) -> int:
    # the commit authors of the pending PRs, unless the saved data already carries them (--prs FILE with commit_authors)
    wanted = [pr["number"] for pr in prs if through is not None and pr["number"] > through and "commit_authors" not in pr
              and not (pr.get("author") or {}).get("is_bot") and not ((pr.get("author") or {}).get("login") or "app/").startswith("app/")]
    if wanted and fetch is not None:
        found = fetch(wanted)
        for pr in prs:
            if found and pr["number"] in found:
                pr["commit_authors"] = found[pr["number"]]
    later = pending(entries, prs, through)
    for line in later:
        print(line)
    authors = sum(not line.startswith(" ") for line in later)
    print(f"{authors} author(s) merged after the snapshot (PR #{through})." if later
          else f"Nobody has merged since the snapshot (PR #{through}).")
    return 1 if later else 0


def run_check(args, text: str, entries: list[dict], prs: list[dict], through: int | None) -> int:
    problems, skipped = check(entries, prs, through)
    problems += area_table_problems(text, entries)
    problems += todo_problems(text)
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
    parser.add_argument("--stub", metavar="LOGIN", nargs="+", help="add a starting entry for a new contributor (moves the snapshot, sorts, lists them in an area row)")
    parser.add_argument("--area", default=DEFAULT_AREA, metavar="NAME",
                        help=f"with --stub: the Contributions by area row to list the new people in (default: {DEFAULT_AREA!r})")
    parser.add_argument("--fix", action="store_true", help="rewrite known PR counts/dates and sort contributor entries")
    args = parser.parse_args(argv)

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
        # saved data (--prs FILE) is used as it is; only data fetched from GitHub gets the closing issues looked up too
        return run_stub(args, text, prs, fetch_closing=None if args.prs else fetch_closing_issues)
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
        return run_pending(entries, prs, through, fetch=None if args.prs else fetch_commit_authors)
    return run_check(args, text, entries, prs, through)


if __name__ == "__main__":
    sys.exit(main())
