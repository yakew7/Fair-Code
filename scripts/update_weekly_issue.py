"""Update the tracking issue for a weekly Fair Code report."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:                         # imported as scripts.<name> (tests, python -m) or run as a script (scripts/ is sys.path[0])
    from .ghcall import GH_TIMEOUT
else:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from ghcall import GH_TIMEOUT

REPORTS = {
    "external-links": {
        "title": "Dead external links (weekly check)",
        "close_comment": "The weekly check found no broken links or stale ignore entries.",
        "label": "documentation",
    },
    "traction": {
        "title": "Traction figures out of date (weekly check)",
        "close_comment": "The weekly check found every traction figure matching GitHub.",
        "label": "community",
    },
    "contributors": {
        "title": "CONTRIBUTORS.md is behind the merged pull requests (weekly check)",
        "close_comment": "The weekly check found nobody who merged since the CONTRIBUTORS.md snapshot.",
        "label": "community",
    },
}


def choose_action(report_state: bool | None, existing_issue: int | None) -> str:
    """Return create/edit/close/none for a report state and matching open issue."""
    if report_state is None:
        return "none"
    if report_state:
        return "edit" if existing_issue is not None else "create"
    return "close" if existing_issue is not None else "none"


def traction_issue_body(stderr: str) -> str:
    """Build the existing traction report body from check_traction stderr."""
    lines = [
        "The weekly `check_traction.py --live` run found figures that differ from GitHub or from each other:",
        "",
    ]
    for line in stderr.splitlines()[1:]:
        lines.append(f"- {line[4:]}" if line.startswith("  - ") else line)
    lines += [
        "",
        "Update the figures in README.md, ROADMAP.md and METRICS.md together, then run `python3 scripts/check_traction.py --live`. "
        "This issue closes itself on the next weekly run once they match.",
    ]
    return "\n".join(lines) + "\n"


def contributors_issue_body(stdout: str) -> str:
    """Build the contributors report body from `check_contributors.py --pending` output (the last line is a summary)."""
    lines = stdout.strip().splitlines()
    people = lines[:-1]
    body = ["The weekly `check_contributors.py --pending` run found people who merged pull requests after the "
            "snapshot in CONTRIBUTORS.md:", ""]
    # a line indented under an author is one of their pull requests with its title: a nested bullet
    body += [f"  - {line.strip()}" if line.startswith(" ") else f"- {line}" for line in people]
    newcomers = [line.split(":")[0] for line in people if not line.startswith(" ") and line.endswith("no entry yet")]
    if newcomers:
        body += ["", "Start the entry of each person with no entry (this also moves the snapshot, sorts and lists them in an area row):", ""]
        body += [f"- `python3 scripts/check_contributors.py --stub {login} --commits`" for login in newcomers]
    body += ["", "Add or update their entries, move the snapshot line to the newest merged PR and run "
             "`python3 scripts/check_contributors.py --fix` (then `--commits` to check commit counts). "
             "This issue closes itself on the next weekly run once nobody is pending."]
    return "\n".join(body) + "\n"


def external_links_issue_body(report: dict) -> str:
    """Use the external-link report's tested renderer, including its stale count."""
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    report_module = importlib.import_module("scripts.check_external_links")
    return report_module.render_issue_body(report)


def external_links_report_needs_issue(report: dict) -> bool:
    """Use the external-link report's tested issue-state rule, including stale ignores."""
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    report_module = importlib.import_module("scripts.check_external_links")
    return report_module.report_needs_issue(report)


def update_issue(
    repo: str,
    kind: str,
    report_state: bool | None,
    body: str = "",
    runner=subprocess.run,
) -> str:
    """Apply the report's open/edit/close decision through the GitHub CLI."""
    if report_state is None:
        return "none"

    config = REPORTS[kind]
    existing = runner(
        ["gh", "issue", "list", "--repo", repo, "--state", "open", "--search",
         f'"{config["title"]}" in:title', "--json", "number,title"],
        check=True,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT,
    )
    matches = [issue["number"] for issue in json.loads(existing.stdout)
               if issue["title"] == config["title"]]
    issue_number = matches[0] if matches else None
    action = choose_action(report_state, issue_number)

    if action in {"create", "edit"}:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
            file.write(body)
            body_path = Path(file.name)
        try:
            if action == "create":
                command = ["gh", "issue", "create", "--repo", repo, "--title", config["title"],
                           "--label", config["label"], "--body-file", str(body_path)]
            else:
                command = ["gh", "issue", "edit", str(issue_number), "--repo", repo,
                           "--body-file", str(body_path)]
            runner(command, check=True, timeout=GH_TIMEOUT)
        finally:
            body_path.unlink(missing_ok=True)
    elif action == "close":
        runner(
            ["gh", "issue", "close", str(issue_number), "--repo", repo,
             "--reason", "completed", "--comment", config["close_comment"]],
            check=True,
            timeout=GH_TIMEOUT,
        )
    return action


def describe_dry_run(kind: str, state: bool | None, body: str) -> str:
    """What a real run would do, without asking GitHub whether the issue already exists (#1245)."""
    config = REPORTS[kind]
    if state is None:
        return f"{kind}: the check did not produce a usable result; a real run fails the job"
    head = (f"{kind}: an issue is needed; a real run creates or edits \"{config['title']}\" (label {config['label']}) with:"
            if state else
            f"{kind}: no issue is needed; a real run closes \"{config['title']}\" if it is open, with the comment: "
            f"{config['close_comment']}")
    return head + ("\n\n" + body.rstrip("\n") if state else "")


def report_unusable(kind: str, status: str, environ=None) -> str:
    """The message for a status file holding anything other than 0 or 1, as a GitHub error annotation (#1244)."""
    env = os.environ if environ is None else environ
    message = (f"the {kind} check could not run (exit status {status!r}; usually the GitHub CLI failed or was offline), "
               "so this run says nothing about whether the figures are current")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### {kind} check did not run\n\n{message}.\n")
    return f"::error title={kind} check did not run::{message}"


def build_parser() -> argparse.ArgumentParser:
    """The command line (a function so a test can check the workflows' calls against it, #1274)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=REPORTS)
    parser.add_argument("report", type=Path, help="external-links JSON report or traction status file")
    parser.add_argument("details", type=Path, nargs="?", help="traction stderr file or contributors stdout file")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the decision and the issue body instead of calling gh (needs no GITHUB_REPOSITORY)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.kind == "external-links":
        report = json.loads(args.report.read_text(encoding="utf-8"))
        state = external_links_report_needs_issue(report)
        body = external_links_issue_body(report)
    else:
        if args.details is None:
            parser.error(f"{args.kind} requires a status file and an output file")
        status = args.report.read_text(encoding="utf-8").strip()
        state = True if status == "1" else False if status == "0" else None
        build = traction_issue_body if args.kind == "traction" else contributors_issue_body
        body = build(args.details.read_text(encoding="utf-8")) if state else ""

    if state is None and args.kind != "external-links":
        if args.dry_run:
            print(describe_dry_run(args.kind, state, body))
            return 1
        print(report_unusable(args.kind, status))
        return 1
    if args.dry_run:
        print(describe_dry_run(args.kind, state, body))
        return 0
    update_issue(os.environ["GITHUB_REPOSITORY"], args.kind, state, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
