"""Starting entries with --stub: summaries, closing issues and foreign commit authors (#1327)."""
import json

import pytest

from contributors_helpers import (  # noqa: F401
    script,
    DOC,
    pr,
    PRS,
    run,
    STUB_DOC,
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
