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


PR_DATA = [dict(pr(210, "dave", "2026-11-05"), files=["faircode/benchmark.py", "faircode/strategies.py", "README.md", "zzz/q.py"]),
           dict(pr(211, "erin", "2026-11-06"), files=[]), pr(212, "dave", "2026-11-07")]


def _explain(tmp_path, capsys, *extra, prs=PR_DATA, doc=STUB_DOC):
    (tmp_path / "CONTRIBUTORS.md").write_text(doc, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json"), "--explain-area", *extra])
    return code, capsys.readouterr().out


def test_explain_area_with_a_pr_explains_every_file_and_the_row_stub_would_choose(tmp_path, capsys):
    # #1366: the paths are already on the pull request, and --stub suggests the area from the same list
    code, out = _explain(tmp_path, capsys, "--pr", "210")
    lines = out.splitlines()
    assert code == 0 and lines[0] == "#210 by dave: 4 changed file(s)"
    assert [line.split(":")[0] for line in lines[1:5]] == ["faircode/benchmark.py", "faircode/strategies.py", "README.md", "zzz/q.py"]
    assert "--stub would list dave in:" in lines[-1]


def test_the_row_for_the_author_is_the_one_with_most_files_and_the_default_when_nothing_matches(tmp_path, capsys):
    doc = STUB_DOC.replace("Audits", "Benchmark harness & paper freeze", 1)
    _, out = _explain(tmp_path, capsys, "--pr", "210", doc=doc)
    assert out.splitlines()[-1] == "--stub would list dave in: Benchmark harness & paper freeze (2 changed file(s))"
    data = [dict(pr(220, "dave", "2026-11-05"), files=["zzz/q.py", "newdir/x.py"])]
    _, out = _explain(tmp_path, capsys, "--pr", "220", prs=data)
    assert out.splitlines()[-1] == f"--stub would list dave in: {script.DEFAULT_AREA} (no changed file matches a row of the table)"


def test_paths_and_a_pr_can_be_combined_and_a_pr_without_files_is_said_so(tmp_path, capsys):
    code, out = _explain(tmp_path, capsys, "Makefile", "--pr", "210")
    assert code == 0
    assert out.splitlines()[1].startswith("Makefile:") and out.splitlines()[2].startswith("faircode/benchmark.py:")
    code, out = _explain(tmp_path, capsys, "--pr", "211")
    assert code == 0 and out.strip().splitlines()[-1] == "#211 has no changed files"


def test_a_pr_that_the_saved_data_lacks_is_fetched_and_a_failed_fetch_is_a_note_not_an_error(tmp_path, capsys, monkeypatch):
    asked = []
    monkeypatch.setattr(script, "fetch_pr_files", lambda number: asked.append(number) or {"login": "frank", "files": ["tests/a.py"]})
    code, out = _explain(tmp_path, capsys, "--pr", "999", prs=[])
    assert asked == [999] and code == 0 and out.splitlines()[0] == "#999 by frank: 1 changed file(s)"      # not in the saved data: fetched
    monkeypatch.setattr(script, "fetch_pr_files", lambda number: None)
    code, out = _explain(tmp_path, capsys, "--pr", "999", prs=[])
    assert code == 0 and "could not read the files of pull request #999" in out
    from scripts import contributors_write as write
    assert write.run_explain([], 7, STUB_DOC, None, lambda number: {"login": "frank", "files": ["tests/a.py"]}) == 0
    assert write.run_explain([], 7, STUB_DOC, None, lambda number: None) == 0
    assert "could not read the files of pull request #7" in capsys.readouterr().out.splitlines()[-1]


def test_fetch_pr_files_reads_the_author_and_files_and_returns_none_on_any_failure(monkeypatch):
    import subprocess
    done = subprocess.CompletedProcess([], 0, '{"login": "frank", "files": ["a.py"]}', "")
    monkeypatch.setattr(script.shutil, "which", lambda name: "/usr/bin/gh")
    seen = []
    monkeypatch.setattr("scripts.contributors_github.run_gh", lambda cmd: seen.append(cmd) or done)
    assert script.fetch_pr_files(5) == {"login": "frank", "files": ["a.py"]}
    assert seen[0][:4] == ["gh", "pr", "view", "5"] and "author,files" in seen[0]
    for bad in (subprocess.CompletedProcess([], 1, "", "not found"), subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "not json", "")):
        monkeypatch.setattr("scripts.contributors_github.run_gh", lambda cmd, bad=bad: bad)
        assert script.fetch_pr_files(5) is None
    monkeypatch.setattr(script.shutil, "which", lambda name: None)
    assert script.fetch_pr_files(5) is None


def test_pr_without_explain_area_and_explain_area_with_nothing_are_usage_problems(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--pr", "5"])
    assert stopped.value.code == 2 and "--pr only goes with --explain-area" in capsys.readouterr().err
    code, out = _explain(tmp_path, capsys)
    assert code == 1 and "nothing to explain" in out
