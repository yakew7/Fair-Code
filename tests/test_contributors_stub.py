"""Starting entries with --stub: summaries, areas, closing issues and foreign commit authors (#1327)."""
import json

import pytest

from contributors_helpers import (  # noqa: F401
    script,
    DOC,
    pr,
    PRS,
    run,
    STUB_DOC,
    AREA_DOC_TABLE,
    _stub_site,
    _replace_the_todo,
    _two_newcomers,
)


def test_stub_entry_uses_the_authors_merged_prs_and_titles():
    # #1249
    prs = [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "Dave", "2026-10-31"), title="docs: b"),
           pr(111, "bob", "2026-10-30")]
    stub = script.stub_entry("dave", prs)
    assert stub.startswith("### [@dave](https://github.com/dave)\n\n**2 merged PRs · 2 commits · first merged 2026-10-30**")
    assert "[#110](https://github.com/yakew7/Fair-Code/pull/110) fix: a; [#120]" in stub and "TODO" in stub
    with pytest.raises(ValueError, match="no merged pull requests"):
        script.stub_entry("nobody", prs)


def test_stub_for_a_new_author_leaves_a_file_the_plain_check_passes(tmp_path, capsys):
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "dave", "2026-10-31"), title="docs: b")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json"), "--stub", "dave"]) == 0
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")

    assert "covering everything merged through **PR #120**" in text
    dave = next(e for e in script.parse(text)[0] if e["handle"] == "dave")
    assert (dave["merged"], dave["first"]) == (2, "2026-10-30")
    assert "[@dave](https://github.com/dave) |" in text.split("Contributor tooling & docs")[1]
    capsys.readouterr()
    _replace_the_todo(tmp_path / "CONTRIBUTORS.md")        # the stub's TODO sentence has to be written by hand (#1285)
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]) == 0, capsys.readouterr().out


def test_stub_refuses_an_existing_entry_and_an_unknown_author(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(PRS), encoding="utf-8")
    base = ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]
    assert script.main(base + ["--stub", "bob"]) == 1 and "already has an entry" in capsys.readouterr().out
    assert script.main(base + ["--stub", "ghost"]) == 1 and "no merged pull requests" in capsys.readouterr().out


def test_the_plain_check_fails_on_a_left_over_stub_and_passes_once_it_is_replaced(tmp_path, capsys):
    stubbed = DOC.replace("Text.\n", "TODO: describe the work in a sentence or two.\n")
    code, out = run(tmp_path, capsys, doc=stubbed)
    assert code == 1 and "alice: the entry still has a TODO placeholder" in out
    code, out = run(tmp_path, capsys, doc=DOC)
    assert code == 0


def test_a_stub_just_written_fails_until_its_sentence_is_replaced(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    capsys.readouterr()
    assert script.main(base) == 1 and "dave: the entry still has a TODO placeholder" in capsys.readouterr().out
    _replace_the_todo(tmp_path / "CONTRIBUTORS.md")
    assert script.main(base) == 0


def test_one_stub_run_can_start_several_entries_in_rule_order(tmp_path, capsys):
    # #1299
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave", "erin"]) == 0
    assert "stub entries for dave, erin" in capsys.readouterr().out
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    handles = [e["handle"] for e in script.parse(text)[0]]
    assert handles.index("erin") < handles.index("dave")                 # erin has 2 PRs, dave 1
    assert "covering everything merged through **PR #121**" in text
    assert text.count("TODO:") == 2
    assert text.count("[@dave](https://github.com/dave)") == 2 and text.count("[@erin](https://github.com/erin)") == 2   # header + area row


def test_one_bad_login_stops_the_whole_stub_run_before_anything_is_written(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    before = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.main(base + ["--stub", "dave", "ghost"]) == 1
    assert "ghost has no merged pull requests" in capsys.readouterr().out
    assert (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8") == before


def test_the_same_login_twice_is_added_once(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave", "dave"]) == 0
    assert (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").count("### [@dave]") == 1


@pytest.mark.parametrize("body, expected", [
    ("## Summary\n\nRun the doctor after setup. More.\n\n## Type\nfix", "Run the doctor after setup. More."),
    ("Summary\n- Added support for X\n- Kept the default\n\nTesting\n- ok", "Added support for X"),
    ("**Summary**\n1. First change\n", "First change"),
    ("### summary:  \n* a bullet", "a bullet"),
    ("## Summary\n\n## Type\nbug", None),
    ("Summaries are not a heading\n- x", None),
    ("no section at all", None),
    ("", None),
    (None, None),
])
def test_summary_line_takes_the_first_line_or_bullet_under_the_summary_heading(body, expected):
    # #1307
    assert script.summary_line(body) == expected


def test_a_stub_shows_the_pull_request_summary_when_it_has_one_and_only_the_title_when_not():
    prs = [dict(pr(110, "dave", "2026-10-30"), title="Run the doctor", body="## Summary\n- Runs the doctor after setup\n"),
           dict(pr(111, "dave", "2026-10-31"), title="Plain change", body="no summary"),
           dict(pr(112, "dave", "2026-11-01"), title="Same as title", body="## Summary\nSame as title.\n"),
           dict(pr(113, "dave", "2026-11-02"), title="No body")]
    stub = script.stub_entry("dave", prs)
    assert "[#110](https://github.com/yakew7/Fair-Code/pull/110) Run the doctor (Runs the doctor after setup);" in stub
    assert "[#111](https://github.com/yakew7/Fair-Code/pull/111) Plain change; " in stub
    assert "Same as title; " in stub and "Same as title (" not in stub          # a summary that repeats the title is dropped
    assert stub.rstrip().endswith("No body.")


def test_the_stub_gets_summaries_from_the_pull_request_data_it_was_given(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8"))
    for item in prs:
        if item["number"] == 110:
            item["body"] = "## Summary\n- Fixes the thing\n"
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(base + ["--stub", "dave"]) == 0
    assert "fix: a (Fixes the thing)" in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")


def test_area_names_lists_the_rows_of_the_area_table():
    # #1294
    assert script.area_names(STUB_DOC) == ["Audits", "Contributor tooling & docs"]
    assert script.area_names(DOC) == []
    real = script.area_names((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    assert script.DEFAULT_AREA in real and "Audits" in real and "Area" not in real and len(real) >= 8


def test_stub_area_lists_the_new_person_in_the_chosen_row_only(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave", "--area", "audits"]) == 0          # the match ignores case
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip(" *"): line for line in text.splitlines() if line.startswith("| **")}
    assert "[@dave](https://github.com/dave)" in rows["Audits"]
    assert "[@dave]" not in rows["Contributor tooling & docs"]


def test_stub_area_defaults_to_the_tooling_and_docs_row(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    tooling = next(line for line in text.splitlines() if line.startswith("| **Contributor tooling & docs**"))
    assert "[@dave](https://github.com/dave)" in tooling


def test_an_unknown_stub_area_is_an_error_naming_the_real_ones_and_writes_nothing(tmp_path, capsys):
    base = _stub_site(tmp_path)
    before = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.main(base + ["--stub", "dave", "--area", "Nope"]) == 1
    out = capsys.readouterr().out
    assert "unknown area 'Nope'" in out and "Audits; Contributor tooling & docs" in out
    assert (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8") == before


def test_one_area_applies_to_every_login_of_a_stub_run(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave", "erin", "--area", "Audits"]) == 0
    audits = next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines() if line.startswith("| **Audits**"))
    assert "[@dave]" in audits and "[@erin]" in audits


def test_a_stub_writes_the_closing_issue_numbers_in_the_entries_own_phrasing():
    # #1308
    prs = [dict(pr(110, "dave", "2026-10-30"), title="Fix a thing", body="## Summary\n- Fixes the thing\n", closing_issues=[1304]),
           dict(pr(111, "dave", "2026-10-31"), title="Two issues", closing_issues=[7, 9]),
           dict(pr(112, "dave", "2026-11-01"), title="No closes", closing_issues=[]),
           dict(pr(113, "dave", "2026-11-02"), title="Not looked up")]
    stub = script.stub_entry("dave", prs)
    assert "Fix a thing (Fixes the thing, closing issue #1304);" in stub
    assert "Two issues (closing issues #7, #9);" in stub
    assert "No closes; " in stub and stub.rstrip().endswith("Not looked up.")


def test_run_stub_looks_up_closing_issues_only_for_the_stubbed_peoples_prs_and_only_when_asked(tmp_path, capsys):
    _two_newcomers(tmp_path)
    asked = []

    def fetch(numbers):
        asked.append(sorted(numbers))
        return {110: {"commit_authors": ["dave"], "closing_issues": [1304]}, 120: {"commit_authors": ["erin"], "closing_issues": []},
                121: {"commit_authors": ["erin"], "closing_issues": [55]}}

    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8"))
    args = script.argparse.Namespace(stub=["dave", "erin"], commits=False, area=script.DEFAULT_AREA, save_commits=None,
                                     file=tmp_path / "CONTRIBUTORS.md")
    assert script.run_stub(args, (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8"), prs, fetch_details=fetch) == 0
    assert asked == [[110, 120, 121]]                       # not alice's, bob's or carol's PRs
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert "(closing issue #1304)" in text and "(closing issue #55)" in text


def test_add_details_fills_the_pr_dicts_without_overwriting_saved_data():
    prs = [dict(pr(1, "a", "2026-11-01"), closing_issues=[9]), pr(2, "b", "2026-11-02")]
    script.add_details(prs, {1: {"commit_authors": ["a"], "closing_issues": [1]}, 2: {"commit_authors": ["c"], "closing_issues": [2]}})
    assert prs[0]["closing_issues"] == [9] and prs[0]["commit_authors"] == ["a"]
    assert prs[1]["closing_issues"] == [2] and prs[1]["commit_authors"] == ["c"]
    script.add_details(prs, None)                              # a failed fetch changes nothing
    assert prs[1]["commit_authors"] == ["c"]


def test_a_stub_says_when_a_commit_is_authored_by_someone_else():
    # #1326: PR #1311 was opened by ranjanasri6 but the commit is authored by PRIYANKA2272004
    prs = [dict(pr(1311, "ranjanasri6", "2026-11-09"), title="Handle empty groups", commit_authors=["PRIYANKA2272004"]),
           dict(pr(1312, "ranjanasri6", "2026-11-09"), title="Own commit", commit_authors=["ranjanasri6", "yakew7"])]
    stub = script.stub_entry("ranjanasri6", prs)
    assert ("The commit of #1311 ([@PRIYANKA2272004](https://github.com/PRIYANKA2272004)) is authored by someone else, "
            "so GitHub counts it for that account, not this one.") in stub
    assert script.foreign_commit_authors("ranjanasri6", prs) == {1311: ["PRIYANKA2272004"]}
    assert "authored by someone else" not in script.stub_entry("ranjanasri6", prs[1:])        # the maintainer's merge commit is ignored
    assert "authored by someone else" not in script.stub_entry("ranjanasri6", [dict(p, commit_authors=None) for p in prs])


def test_the_exception_lines_to_add_are_suggested_for_an_unlisted_author_and_a_fully_foreign_pr():
    entries, _ = script.parse(DOC)
    prs = [dict(pr(1311, "dave", "2026-11-09"), commit_authors=["priyanka"])]
    lines = script.exception_suggestions(entries, prs, ["dave"])
    assert 'unlisted_authors: "priyanka": "authored the commit of PR #1311, which dave opened; no merged pull request of their own"' in lines
    assert any(line.startswith('commit_exceptions: "dave": "the commit of #1311 is authored by priyanka') for line in lines)
    # a foreign author who already has an entry needs no unlisted line, and a person with one own commit needs no exception
    mixed = [dict(pr(1311, "dave", "2026-11-09"), commit_authors=["dave", "alice"])]
    assert script.exception_suggestions(entries, mixed, ["dave"]) == []


def test_a_stub_without_foreign_commit_authors_prints_no_exception_lines(tmp_path, capsys):
    assert script.main(_two_newcomers(tmp_path) + ["--stub", "dave"]) == 0
    assert "contributors-exceptions.json" not in capsys.readouterr().out


def test_suggest_area_picks_the_row_holding_most_of_the_changed_files():
    # #1333
    names = script.area_names(AREA_DOC_TABLE)
    prs = [dict(pr(1, "dave", "2026-11-01"), files=["assets/profiler-ui.js", "assets/profiler-engine.js", "tests/test_x.py"]),
           dict(pr(2, "dave", "2026-11-02"), files=["profiler.html"]),
           dict(pr(3, "erin", "2026-11-02"), files=["tests/test_y.py"])]
    assert script.suggest_area("dave", prs, names) == ("Profiler - web", 3)
    assert script.suggest_area("erin", prs, names) == ("Tests", 1)
    assert script.suggest_area("nobody", prs, names) is None
    assert script.suggest_area("dave", [pr(1, "dave", "2026-11-01")], names) is None            # no files in the data
    assert script.suggest_area("dave", [dict(pr(1, "dave", "2026-11-01"), files=["README.md"])], names) is None
    tie = [dict(pr(1, "dave", "2026-11-01"), files=["tests/a.py", "assets/profiler-ui.js"])]
    assert script.suggest_area("dave", tie, names)[0] == "Profiler - web"                      # ties go to the earlier rule


def test_rules_naming_a_row_the_table_does_not_have_are_ignored():
    assert script.suggest_area("dave", [dict(pr(1, "dave", "2026-11-01"), files=["tests/a.py"])], ["Audits"]) is None


def test_a_stub_without_area_uses_the_suggestion_and_says_so_and_area_still_overrides(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(AREA_DOC_TABLE, encoding="utf-8")
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a", files=["assets/profiler-ui.js"])]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    base = ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]
    assert script.main(base + ["--stub", "dave"]) == 0
    out = capsys.readouterr().out
    assert "area chosen from the changed files (use --area NAME to override): dave: Profiler - web (1 changed file(s))" in out
    rows = {line.split("|")[1].strip(" *"): line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
            if line.startswith("| **")}
    assert "[@dave]" in rows["Profiler - web"] and "[@dave]" not in rows["Contributor tooling & docs"]

    (tmp_path / "CONTRIBUTORS.md").write_text(AREA_DOC_TABLE, encoding="utf-8")
    assert script.main(base + ["--stub", "dave", "--area", "Tests"]) == 0
    assert "area chosen" not in capsys.readouterr().out
    assert "[@dave]" in next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
                             if line.startswith("| **Tests**"))


def test_a_stub_without_files_in_the_data_keeps_the_default_area(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    assert "area chosen" not in capsys.readouterr().out
    tooling = next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
                   if line.startswith("| **Contributor tooling & docs**"))
    assert "[@dave]" in tooling
