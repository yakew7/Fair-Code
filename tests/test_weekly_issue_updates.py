import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

script = importlib.import_module("scripts.update_weekly_issue")


@pytest.mark.parametrize(
    ("report_state", "existing_issue", "expected"),
    [
        (True, None, "create"),
        (True, 42, "edit"),
        (False, None, "none"),
        (False, 42, "close"),
        (None, None, "none"),
        (None, 42, "none"),
    ],
)
def test_report_state_selects_create_edit_close_or_noop(report_state, existing_issue, expected):
    assert script.choose_action(report_state, existing_issue) == expected


def test_traction_issue_body_preserves_actionable_differences_and_instructions():
    body = script.traction_issue_body(
        "Traction figures are out of step:\n"
        "  - issues_closed: METRICS.md (latest weekly row, 2026-W43) says 28, GitHub says 29\n"
        "  - stars: README=100, GitHub=101\n"
    )

    assert "- issues_closed: METRICS.md (latest weekly row, 2026-W43) says 28, GitHub says 29" in body
    assert "- stars: README=100, GitHub=101" in body
    assert "Update the figures in README.md, ROADMAP.md and METRICS.md together" in body


def test_external_links_issue_body_reuses_the_report_renderer(monkeypatch):
    report_module = importlib.import_module("scripts.check_external_links")
    monkeypatch.setattr(report_module, "render_issue_body", lambda report: f"stale={len(report['stale_ignored'])}", raising=False)
    monkeypatch.setattr(report_module, "report_needs_issue", lambda report: bool(report["stale_ignored"]), raising=False)

    assert script.external_links_issue_body({"stale_ignored": ["one"]}) == "stale=1"
    assert script.external_links_report_needs_issue({"stale_ignored": ["one"]}) is True


def test_external_links_integration_keeps_issue_open_for_stale_ignores():
    report = {
        "checked": 1,
        "ok": [],
        "broken": [],
        "unknown": [],
        "ignored": [],
        "stale_ignored": [{"url": "https://example.org/retired", "reason": "no longer referenced"}],
    }

    body = script.external_links_issue_body(report)

    assert "1 stale ignore-list entry" in body
    assert "https://example.org/retired" not in body
    assert script.external_links_report_needs_issue(report) is True
    assert script.external_links_report_needs_issue({**report, "stale_ignored": []}) is False


@pytest.mark.parametrize(
    ("state", "issues", "expected_action", "expected_command"),
    [
        (True, [], "create", "create"),
        (True, [{"number": 42, "title": "Traction figures out of date (weekly check)"}], "edit", "edit"),
        (False, [], "none", None),
        (False, [{"number": 42, "title": "Traction figures out of date (weekly check)"}], "close", "close"),
        (None, [], "none", None),
    ],
)
def test_update_issue_runs_only_the_selected_github_operation(
    state, issues, expected_action, expected_command
):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(stdout=json.dumps(issues))
        if "--body-file" in command:
            body_path = command[command.index("--body-file") + 1]
            assert Path(body_path).read_text(encoding="utf-8") == "report body"
        return SimpleNamespace(stdout="")

    action = script.update_issue("owner/repo", "traction", state, "report body", runner=runner)

    assert action == expected_action
    if expected_command:
        assert calls[-1][2] == expected_command
    assert len(calls) == (0 if state is None else 1 + (expected_command is not None))


def test_contributors_issue_body_lists_each_pending_author_and_the_next_steps():
    body = script.contributors_issue_body(
        "dxnnystyles: 9 merged PR(s) after the snapshot (#1216, #1217); count to update\n"
        "newperson: 1 merged PR(s) after the snapshot (#1230); no entry yet\n"
        "2 author(s) merged after the snapshot (PR #1191).\n"
    )

    assert "- dxnnystyles: 9 merged PR(s) after the snapshot (#1216, #1217); count to update" in body
    assert "- newperson: 1 merged PR(s) after the snapshot (#1230); no entry yet" in body
    assert "2 author(s)" not in body
    assert "check_contributors.py --fix" in body


def test_contributors_report_is_registered_with_its_own_title():
    assert script.REPORTS["contributors"]["title"] == "CONTRIBUTORS.md is behind the merged pull requests (weekly check)"


def test_contributors_main_opens_an_issue_only_when_someone_is_pending(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(script, "update_issue", lambda repo, kind, state, body="": calls.append((kind, state, body)) or "x")
    status, out = tmp_path / "status", tmp_path / "out.txt"
    out.write_text("someone: 1 merged PR(s) after the snapshot (#9); no entry yet\n1 author(s) merged after the snapshot (PR #1).\n")

    status.write_text("1\n")
    script.main(["contributors", str(status), str(out)])
    status.write_text("0\n")
    script.main(["contributors", str(status), str(out)])

    assert calls[0][:2] == ("contributors", True) and "someone" in calls[0][2]
    assert calls[1] == ("contributors", False, "")


@pytest.mark.parametrize(("kind", "label"), [("external-links", "documentation"), ("traction", "community"),
                                             ("contributors", "community")])
def test_each_report_creates_its_issue_with_its_own_label(kind, label):
    # #1241
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="[]")

    script.update_issue("owner/repo", kind, True, "body", runner=runner)

    create = calls[-1]
    assert create[:3] == ["gh", "issue", "create"] and create[create.index("--label") + 1] == label
    assert script.REPORTS[kind]["label"] == label


def test_dry_run_prints_the_decision_and_body_and_never_calls_gh(tmp_path, monkeypatch, capsys):
    # #1245: no GITHUB_REPOSITORY needed and no runner involved
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(script, "update_issue", lambda *a, **k: pytest.fail("gh must not be called"))
    status, out = tmp_path / "status", tmp_path / "out.txt"
    out.write_text("someone: 1 merged PR(s) after the snapshot (#9); no entry yet\n1 author(s) merged after the snapshot (PR #1).\n")

    status.write_text("1\n")
    assert script.main(["contributors", str(status), str(out), "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "an issue is needed" in printed and "(label community)" in printed and "- someone:" in printed

    status.write_text("0\n")
    assert script.main(["contributors", str(status), str(out), "--dry-run"]) == 0
    assert "no issue is needed" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["traction", "contributors"])
def test_a_status_other_than_0_or_1_fails_the_job_with_an_annotation(kind, tmp_path, monkeypatch, capsys):
    # #1244: exit status 2 means gh failed; that must not look like a clean week
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(script, "update_issue", lambda *a, **k: pytest.fail("no issue change on an unusable status"))
    status, out = tmp_path / "status", tmp_path / "out.txt"
    status.write_text("2\n")
    out.write_text("")

    assert script.main([kind, str(status), str(out)]) == 1

    printed = capsys.readouterr().out
    assert printed.startswith(f"::error title={kind} check did not run::") and "exit status '2'" in printed
    assert f"{kind} check did not run" in summary.read_text(encoding="utf-8")


def test_contributors_issue_body_nests_each_pull_request_title_under_its_author():
    body = script.contributors_issue_body(
        "bob: 2 merged PR(s) after the snapshot (#101, #102); count to update\n"
        "    #101 fix: a thing\n"
        "    #102 docs: another\n"
        "1 author(s) merged after the snapshot (PR #100).\n"
    )
    assert "- bob: 2 merged PR(s) after the snapshot (#101, #102); count to update\n  - #101 fix: a thing\n  - #102 docs: another\n" in body


def test_every_gh_call_of_update_issue_has_a_timeout():
    # #1266
    calls = []

    def runner(command, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stdout=json.dumps([{"number": 42, "title": script.REPORTS["traction"]["title"]}]))

    script.update_issue("o/r", "traction", True, "body", runner=runner)     # list, then edit
    script.update_issue("o/r", "traction", False, "", runner=runner)        # list, then close
    assert len(calls) == 4 and all(call.get("timeout") == script.GH_TIMEOUT for call in calls)
