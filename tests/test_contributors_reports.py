"""The read-only reports of check_contributors.py: `--pending --json` (#1354)."""
import json

import pytest

from contributors_helpers import DOC, PRS, pr, run, script  # noqa: F401

LATER = [pr(101, "bob", "2026-10-30"), pr(103, "dave", "2026-11-02"), pr(102, "dave", "2026-10-31"),
         pr(104, "app/dependabot", "2026-11-03", bot=True), pr(105, "yakew7", "2026-11-04"), pr(5, "erin", "2026-10-01")]


def test_pending_json_lists_each_author_with_their_prs_first_merge_and_whether_they_have_an_entry(tmp_path, capsys):
    # #1354: the workflow had to parse the text lines to get the logins and PR numbers
    code, out = run(tmp_path, capsys, prs=PRS + LATER, extra=("--pending", "--json"))
    assert code == 1
    assert json.loads(out) == [
        {"login": "bob", "prs": [101], "first_merged": "2026-10-30", "has_entry": True},
        {"login": "dave", "prs": [102, 103], "first_merged": "2026-10-31", "has_entry": False},
    ]                                                       # not the bot, the maintainer or erin's PR before the snapshot


def test_pending_json_is_an_empty_list_with_exit_0_when_nobody_is_pending(tmp_path, capsys):
    code, out = run(tmp_path, capsys, extra=("--pending", "--json"))
    assert code == 0 and json.loads(out) == []


def test_the_text_form_and_its_exit_code_are_unchanged(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=PRS + LATER, extra=("--pending",))
    assert code == 1 and "dave: 2 merged PR(s) after the snapshot (#102, #103); no entry yet" in out and not out.lstrip().startswith("[")
    assert script.pending_json(script.parse(DOC)[0], PRS + LATER, None) == []              # no snapshot line: nothing counts as after it


def test_json_without_pending_is_a_usage_error(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(DOC, encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--json"])
    assert stopped.value.code == 2 and "--json only goes with --pending" in capsys.readouterr().err
