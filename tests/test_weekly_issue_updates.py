import importlib
import json
import subprocess
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
    assert len(calls) == 4 and all(call.get("timeout") == script.get_gh_timeout() for call in calls)


def test_contributors_issue_body_gives_the_stub_command_for_each_person_with_no_entry():
    # #1277
    body = script.contributors_issue_body(
        "bob: 2 merged PR(s) after the snapshot (#101, #102); count to update\n"
        "    #101 fix: a thing\n"
        "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet\n"
        "    #103 feat: new\n"
        "other-new: 1 merged PR(s) after the snapshot (#104); no entry yet\n"
        "3 author(s) merged after the snapshot (PR #100).\n"
    )
    assert "- `python3 scripts/check_contributors.py --stub newbie --commits`" in body
    assert "- `python3 scripts/check_contributors.py --stub other-new --commits`" in body
    assert "--stub bob" not in body


def test_contributors_issue_body_has_no_stub_section_when_everyone_has_an_entry():
    body = script.contributors_issue_body(
        "bob: 1 merged PR(s) after the snapshot (#101); count to update\n1 author(s) merged after the snapshot (PR #100).\n")
    assert "--stub" not in body and "Start the entry" not in body


WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _workflow_calls():
    """(workflow file name, workflow text, tokens after update_weekly_issue.py) for every workflow `run:` line that calls it."""
    import shlex
    calls = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "scripts/update_weekly_issue.py" in line:
                calls.append((path.name, text, shlex.split(line.split("scripts/update_weekly_issue.py", 1)[1])))
    return calls


def test_the_workflows_call_the_script_with_arguments_its_parser_accepts():
    # #1274: a renamed kind or a changed argument list would only fail on the next Monday
    calls = _workflow_calls()
    assert {tokens[0] for _, _, tokens in calls} == set(script.REPORTS), "every report kind needs a workflow, and no workflow an unknown kind"
    for name, text, tokens in calls:
        args = script.build_parser().parse_args(tokens)
        if args.kind != "external-links":
            assert args.details is not None, f"{name}: {args.kind} needs a status file and an output file"
        for path in [args.report, args.details]:
            if path is not None:
                assert text.count(str(path)) >= 2, f"{name}: {path} is passed to the script but nothing else in the workflow writes it"


def test_each_kind_is_called_by_exactly_one_workflow():
    kinds = [tokens[0] for _, _, tokens in _workflow_calls()]
    assert sorted(kinds) == sorted(set(kinds))


def test_the_parser_rejects_an_unknown_kind_and_a_missing_report():
    parser = script.build_parser()
    for bad in (["nope", "status"], ["traction"]):
        with pytest.raises(SystemExit):
            parser.parse_args(bad)


def _status_files(tmp_path, status="1\n"):
    state, out = tmp_path / "status", tmp_path / "out.txt"
    state.write_text(status)
    out.write_text("someone: 1 merged PR(s) after the snapshot (#9); no entry yet\n1 author(s) merged after the snapshot (PR #1).\n")
    return [str(state), str(out)]


@pytest.mark.parametrize("error, expected", [
    (subprocess.TimeoutExpired(["gh", "issue", "list", "--repo", "o/r"], 60), "did not answer within 60 s"),
    (subprocess.CalledProcessError(4, ["gh", "issue", "edit", "7"], stderr="boom\nHTTP 502\n"), "exited with status 4 (HTTP 502)"),
])
def test_a_failed_or_timed_out_gh_call_gives_an_error_annotation_and_exit_1(error, expected, tmp_path, monkeypatch, capsys):
    # #1288: this used to end in a Python traceback
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(script, "update_issue", failing)
    assert script.main(["contributors", *_status_files(tmp_path)]) == 1

    printed = capsys.readouterr().out
    assert printed.startswith("::error title=contributors report could not update its issue::") and expected in printed
    assert "contributors report could not update its issue" in summary.read_text(encoding="utf-8")


def test_the_annotation_names_an_unexpected_error_type_too(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert "ValueError: bad" in script.gh_call_failed("traction", ValueError("bad"))


PENDING_TEXT = ("bob: 2 merged PR(s) after the snapshot (#101, #102); count to update\n"
                "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet\n"
                "2 author(s) merged after the snapshot (PR #100).\n")


def test_the_stub_commands_come_from_the_json_when_it_is_given_not_from_the_wording_of_the_text():
    # #1364: a change to the text wording used to silently drop the stub commands
    pending = [{"login": "bob", "prs": [101, 102], "first_merged": "2026-10-30", "has_entry": True},
               {"login": "newbie", "prs": [103], "first_merged": "2026-10-31", "has_entry": False},
               {"login": "other-new", "prs": [104], "first_merged": "2026-11-01", "has_entry": False}]
    reworded = PENDING_TEXT.replace("no entry yet", "has no entry").replace("count to update", "needs a new count")
    body = script.contributors_issue_body(reworded, pending)
    assert "- `python3 scripts/check_contributors.py --stub newbie --commits`" in body
    assert "- `python3 scripts/check_contributors.py --stub other-new --commits`" in body and "--stub bob" not in body
    assert "--stub" not in script.contributors_issue_body(reworded)                       # the text alone no longer matches
    assert "--stub" not in script.contributors_issue_body(PENDING_TEXT, [pending[0]])      # nobody without an entry: no section
    assert script.contributors_issue_body(PENDING_TEXT, []).count("--stub") == 0          # an empty list is data too, not "missing"


def test_read_pending_json_returns_the_list_or_none_for_a_missing_or_unusable_file(tmp_path):
    good = tmp_path / "pending.json"
    good.write_text('[{"login": "a", "prs": [1], "first_merged": "2026-11-01", "has_entry": false}]', encoding="utf-8")
    assert script.read_pending_json(good)[0]["login"] == "a" and script.read_pending_json(None) is None
    assert script.read_pending_json(tmp_path / "missing.json") is None
    for bad in ("", "not json", '{"login": "a"}', '[1, 2]', '[{"prs": [1]}]'):
        good.write_text(bad, encoding="utf-8")
        assert script.read_pending_json(good) is None, bad


def test_main_uses_the_json_file_and_falls_back_to_the_text_when_it_is_unusable(tmp_path, monkeypatch, capsys):
    status, out, data = tmp_path / "status", tmp_path / "out.txt", tmp_path / "pending.json"
    status.write_text("1\n")
    out.write_text(PENDING_TEXT.replace("no entry yet", "has no entry"), encoding="utf-8")
    data.write_text('[{"login": "newbie", "prs": [103], "first_merged": "2026-10-31", "has_entry": false}]', encoding="utf-8")
    args = ["contributors", str(status), str(out), "--dry-run"]
    assert script.main([*args, "--pending-json", str(data)]) == 0 and "--stub newbie --commits" in capsys.readouterr().out
    data.write_text("garbage", encoding="utf-8")
    assert script.main([*args, "--pending-json", str(data)]) == 0 and "--stub" not in capsys.readouterr().out    # text wording changed: none found
    out.write_text(PENDING_TEXT, encoding="utf-8")
    assert script.main([*args, "--pending-json", str(data)]) == 0 and "--stub newbie --commits" in capsys.readouterr().out    # the text still works


def test_the_contributors_workflow_saves_the_json_it_hands_to_the_script():
    text = (WORKFLOWS / "contributors-drift.yml").read_text(encoding="utf-8")
    assert 'check_contributors.py --pending --json > "$RUNNER_TEMP/pending.json"' in text
    assert '--pending-json "$RUNNER_TEMP/pending.json"' in text
