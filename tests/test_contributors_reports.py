"""The two read-only reports of check_contributors.py: `--pending --json` (#1354) and `--explain-area` (#1351)."""
import json

import pytest

from contributors_helpers import DOC, PRS, STUB_DOC, pr, run, script  # noqa: F401

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


RULES = [("faircode/benchmark", "Audits"), ("tests/", "Nowhere"), (".md", "Contributor tooling & docs")]
NAMES = ["Audits", "Contributor tooling & docs"]


def test_explain_area_names_the_matching_rule_and_the_row_it_gives():
    # #1351: the only way to see what a new rule matches was to stub a real contributor
    assert script.explain_area("faircode/benchmark.py", NAMES, RULES, []) == "faircode/benchmark.py: Audits (rule 'faircode/benchmark')"
    assert script.explain_area("notes/x.md", NAMES, RULES, []) == "notes/x.md: Contributor tooling & docs (rule '.md')"    # a match at the end


def test_explain_area_warns_when_a_rule_names_a_row_the_table_lacks():
    line = script.explain_area("tests/a.py", NAMES, RULES, [])
    assert "Nowhere (rule 'tests/'; the table has no such row, so --stub skips this rule)" in line
    assert "skips" not in script.explain_area("tests/a.py", [], RULES, [])               # no table: nothing to compare with


def test_explain_area_says_whether_a_default_path_is_allowed_to_use_the_default_row():
    allowed = script.explain_area("Makefile", NAMES, RULES, ["Makefile"])
    assert allowed == f"Makefile: {script.DEFAULT_AREA} (default; Makefile is listed in default_ok)"
    refused = script.explain_area("newdir/x.py", NAMES, RULES, ["Makefile"])
    assert "default; no rule matches and newdir is not in default_ok, so the area-rule test would fail" in refused


def test_main_explains_several_paths_and_changes_nothing(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    before = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--explain-area", "faircode/benchmark.py", "README.md", "zzz/q.py"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines] == ["faircode/benchmark.py", "README.md", "zzz/q.py"]
    assert "rule 'faircode/benchmark'" in lines[0] and "the table has no such row" in lines[0]      # the toy table has no benchmark row
    assert "default_ok" in lines[1] and "zzz is not in default_ok" in lines[2]
    assert (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8") == before            # and it never asked GitHub for anything
