"""Parsing CONTRIBUTORS.md and the checks of scripts/contributors_entries.py (#1327)."""
import importlib
import json

import pytest

from contributors_helpers import (  # noqa: F401
    script,
    DOC,
    pr,
    PRS,
    run,
    COMMITS,
    IDENTITY_DOC,
    AREA_DOC,
    _two_newcomers,
)


def test_parse_reads_sections_handles_and_the_snapshot():
    entries, through = script.parse(DOC)
    assert through == 100
    assert [(e["section"], e["handle"], e["merged"], e["commits"], e["first"], e["deleted"]) for e in entries] == [
        ("Core contributors", "alice", 3, 5, "2026-05-01", False),
        ("Contributors", "bob", 2, 4, "2026-06-01", False),
        ("Contributors", "carol", 2, 3, "2026-06-02", False),
        ("Contributors", "ghost-user", 1, 2, "2026-05-19", True),
    ]


def test_a_consistent_file_passes_and_notes_the_deleted_account(tmp_path, capsys):
    code, out = run(tmp_path, capsys)
    assert code == 0 and out.startswith("skipped: ghost-user") and "OK: 4 entries" in out


def test_a_stale_pr_count_fails(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=PRS + [pr(11, "bob", "2026-07-01")])
    assert code == 1 and "bob: file says 2 merged PRs, GitHub says 3" in out


def test_a_pull_request_after_the_snapshot_is_not_counted(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=PRS + [pr(101, "bob", "2026-10-30")])
    assert code == 0, out


def test_a_wrong_first_merged_date_fails(tmp_path, capsys):
    code, out = run(tmp_path, capsys, doc=DOC.replace("first merged 2026-06-02", "first merged 2026-06-03"))
    assert code == 1 and "carol: file says first merged 2026-06-03, GitHub says 2026-06-02" in out


def test_a_mis_sorted_section_fails(tmp_path, capsys):
    swapped = DOC.replace("2 merged PRs · 4 commits", "2 merged PRs · 1 commits")
    code, out = run(tmp_path, capsys, doc=swapped)
    assert code == 1 and "Contributors: entry 1 is bob" in out and "puts carol" in out


def test_an_author_with_no_entry_fails_but_the_maintainer_and_bots_do_not(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=PRS + [pr(12, "dave", "2026-07-02")])
    assert code == 1 and "dave: 1 merged PRs on GitHub but no entry" in out
    assert "yakew7" not in out and "dependabot" not in out


def test_an_entry_github_has_never_heard_of_fails(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=[p for p in PRS if p["author"]["login"] != "carol"])
    assert code == 1 and "carol: listed with 2 merged PRs but GitHub shows none" in out


def test_the_real_file_parses_in_rule_order():
    entries, through = script.parse((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    assert through and len(entries) > 40
    problems, _ = script.check(entries, [], through)
    assert not [p for p in problems if "entry" in p and "puts" in p]


def test_pending_lists_authors_who_merged_after_the_snapshot(tmp_path, capsys):
    prs = PRS + [pr(101, "bob", "2026-10-30"), pr(102, "bob", "2026-10-31"), pr(103, "newbie", "2026-10-31"),
                 pr(104, "yakew7", "2026-10-31"), pr(105, "app/dependabot", "2026-10-31", bot=True)]
    code, out = run(tmp_path, capsys, prs=prs, extra=("--pending",))
    assert code == 1
    assert "bob: 2 merged PR(s) after the snapshot (#101, #102); count to update" in out
    assert "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet" in out
    assert "yakew7" not in out and "dependabot" not in out
    assert out.strip().endswith("2 author(s) merged after the snapshot (PR #100).")


def test_pending_is_clean_when_nobody_merged_since(tmp_path, capsys):
    code, out = run(tmp_path, capsys, extra=("--pending",))
    assert code == 0 and "Nobody has merged since the snapshot (PR #100)." in out


def test_a_listed_exception_is_excused_with_its_reason(monkeypatch):
    # #1234: three entries are in no API because their commit email is not linked to the account
    monkeypatch.setitem(script.COMMIT_EXCEPTIONS, "carol", "commit email not linked to the GitHub account")
    entries, _ = script.parse(DOC)
    problems, skipped = script.commit_problems(entries, COMMITS["live"] | {"carol": 99}, COMMITS["after_snapshot"])
    assert any("carol: file says 3 commits, GitHub says 99" in p for p in problems)   # in the API: compared as usual

    live_without_carol = {k: v for k, v in COMMITS["live"].items() if k != "carol"}
    problems, skipped = script.commit_problems(entries, live_without_carol, COMMITS["after_snapshot"])
    assert problems == []
    assert "carol: commit count not compared (commit email not linked to the GitHub account)" in skipped


def test_the_committed_exceptions_name_entries_that_exist():
    entries, _ = script.parse((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    handles = {e["handle"].lower() for e in entries}
    assert set(script.COMMIT_EXCEPTIONS) <= handles


def test_unmapped_authors_lists_only_people_with_no_entry_or_identity_row():
    # #1236
    authors = [("Alice A.", "alice@example.org", 4), ("alice@example.org", "alice@example.org", 1),
               ("Carol", "carol@example.org", 2), ("Somebody Else", "12345+bob@users.noreply.github.com", 1),
               ("Stranger", "stranger@example.org", 3), ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", 9),
               ("GitHub", "noreply@github.com", 5), ("Erol Tasci", "e@example.org", 1)]
    lines = script.unmapped_authors(IDENTITY_DOC, authors)
    assert lines == ["Stranger <stranger@example.org>: 3 commit(s) map to no entry or Git identity map row"]


def test_pending_adds_each_pull_requests_title_when_the_data_has_titles(tmp_path, capsys):
    # #1258
    prs = [dict(p, title=f"title {p['number']}") for p in PRS] + [
        dict(pr(101, "bob", "2026-10-30"), title="fix: a thing"), dict(pr(103, "newbie", "2026-10-31"), title="feat: new")]
    code, out = run(tmp_path, capsys, prs=prs, extra=("--pending",))
    assert code == 1
    assert "bob: 1 merged PR(s) after the snapshot (#101); count to update\n    #101 fix: a thing\n" in out
    assert "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet\n    #103 feat: new\n" in out
    assert out.strip().endswith("2 author(s) merged after the snapshot (PR #100).")


def test_area_table_problems_name_entries_in_no_row(tmp_path, capsys):
    # #1259: carol has an entry but is in no area row
    entries, _ = script.parse(AREA_DOC)
    assert script.area_table_problems(AREA_DOC, entries) == [
        "carol: has an entry but is in no row of the Contributions by area table"]
    assert script.area_table_problems(DOC, script.parse(DOC)[0]) == []          # no table, nothing to check

    code, out = run(tmp_path, capsys, doc=AREA_DOC)
    assert code == 1 and "carol: has an entry but is in no row" in out


def test_the_real_file_has_every_entry_in_the_area_table():
    text = (script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.area_table_problems(text, script.parse(text)[0]) == []


def test_a_co_author_with_no_entry_is_reported_and_tools_and_bots_are_not():
    authors = [("Alice A.", "alice@example.org", 1), ("Dana", "dana@example.org", 2),
               ("Claude Sonnet 5.5", "noreply@anthropic.com", 7), ("Copilot Autofix powered by AI", "1+Copilot@users.noreply.github.com", 7),
               ("Vercel", "vercel[bot]@users.noreply.github.com", 2), ("Voyagerroc-Code", "3+Voyagerroc-Code@users.noreply.github.com", 1)]
    assert script.unmapped_authors(IDENTITY_DOC, authors) == [
        "Dana <dana@example.org>: 2 commit(s) map to no entry or Git identity map row"]
    assert "voyagerroc-code" in script.UNLISTED_AUTHORS


def test_the_committed_exceptions_file_loads_with_a_reason_for_every_entry():
    # #1270
    commit, unlisted = script.load_exceptions()
    assert {"ayaan-20-11", "raonishanth2000-hub", "ege-arhan", "ranjanasri6"} <= set(commit)      # a superset: new exceptions are data
    assert {"erol tasci", "voyagerroc-code"} <= set(unlisted)
    assert all(reason for reason in [*commit.values(), *unlisted.values()])
    assert script.COMMIT_EXCEPTIONS == commit and script.UNLISTED_AUTHORS == unlisted


def test_load_exceptions_lowercases_names_and_rejects_a_missing_reason(tmp_path):
    good = tmp_path / "e.json"
    good.write_text(json.dumps({"commit_exceptions": {"Carol": "unlinked email"}, "unlisted_authors": {"Some Body": "why"}}))
    assert script.load_exceptions(good) == ({"carol": "unlinked email"}, {"some body": "why"})
    assert script.load_exceptions(tmp_path / "missing.json") == ({}, {})
    for bad in ({"commit_exceptions": {"carol": ""}}, {"unlisted_authors": {"x": 3}}, {"commit_exceptions": ["carol"]}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            script.load_exceptions(path)


def test_an_entry_added_to_the_json_file_is_honoured_without_touching_the_script(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "COMMIT_EXCEPTIONS", {})
    monkeypatch.setattr(script, "UNLISTED_AUTHORS", {})
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps({"commit_exceptions": {"carol": "email not linked"}}))
    data = {"live": {"alice": 5, "bob": 4}, "after_snapshot": {}}                       # carol is in no API
    (tmp_path / "commits.json").write_text(json.dumps(data))
    extra = ("--commits-data", str(tmp_path / "commits.json"))

    code, out = run(tmp_path, capsys, extra=extra)
    assert code == 1 and "carol: not in the contributors API and not in COMMIT_EXCEPTIONS" in out

    code, out = run(tmp_path, capsys, extra=extra + ("--exceptions", str(exceptions)))
    assert code == 0 and "carol: commit count not compared (email not linked)" in out


def test_todo_problems_names_each_entry_that_still_has_the_stub_sentence():
    # #1285: `--stub` writes "TODO: describe the work ..." and nothing noticed if it was committed
    doc = DOC.replace("### Carol - [@carol](https://github.com/carol)\n\n**2 merged PRs · 3 commits · first merged 2026-06-02**\n",
                      "### Carol - [@carol](https://github.com/carol)\n\n**2 merged PRs · 3 commits · first merged 2026-06-02**\n\n"
                      "TODO: describe the work in a sentence or two. Merged: [#6].\n")
    assert script.todo_problems(DOC) == []
    assert script.todo_problems(doc) == ["carol: the entry still has a TODO placeholder sentence (written by --stub); describe their work"]


def test_a_todo_in_one_entry_is_not_blamed_on_its_neighbours():
    doc = DOC.replace("Text.\n", "Text with TODO: mid-sentence.\n")        # alice's entry, in the Core section
    assert [p.split(":")[0] for p in script.todo_problems(doc)] == ["alice"]


def test_pending_names_a_commit_author_who_is_not_the_pr_author():
    # #1316: PR #1311 was opened by ranjanasri6 but its commit is authored by PRIYANKA2272004
    prs = [dict(pr(101, "bob", "2026-10-30"), title="fix", commit_authors=["bob", "stranger", "alice"]),
           dict(pr(102, "newbie", "2026-10-31"), title="docs", commit_authors=["newbie"]),
           dict(pr(103, "bob", "2026-10-31"), title="more")]
    entries, _ = script.parse(DOC)
    lines = script.pending(entries, prs, 100)
    assert "    #101 has a commit authored by stranger, not by bob; stranger has no entry: give them one, or add them to " \
           "unlisted_authors in scripts/contributors-exceptions.json" in lines
    assert "    #101 has a commit authored by alice, not by bob; alice has an entry" in lines
    assert not any("#102 has a commit" in line or "#103 has a commit" in line for line in lines)


def test_the_maintainer_as_a_commit_author_is_not_reported():
    prs = [dict(pr(101, "bob", "2026-10-30"), commit_authors=["bob", "yakew7"])]
    assert not any("has a commit authored" in line for line in script.pending(script.parse(DOC)[0], prs, 100))


def test_the_script_is_split_into_modules_that_stay_small_and_the_old_names_still_work():
    # #1319: parsing/checks, rewriting and the GitHub calls live in their own modules; the names used to live here
    from pathlib import Path
    folder = Path(script.__file__).parent
    for name in ("check_contributors", "contributors_entries", "contributors_write", "contributors_github"):
        lines = len((folder / f"{name}.py").read_text(encoding="utf-8").splitlines())
        assert lines < 350, f"{name}.py has {lines} lines"
    for name in ("parse", "check", "pending", "fix_document", "stub_entry", "add_stub", "summary_line", "move_snapshot",
                 "fetch_prs", "fetch_commit_data", "fetch_pr_details", "git_authors", "snapshot_time", "area_table_problems",
                 "todo_problems", "commit_problems", "unmapped_authors", "identity_map", "merged_by_author"):
        assert callable(getattr(script, name)), name


def test_the_checks_in_the_entries_module_take_the_exception_lists_as_arguments():
    entries_module = importlib.import_module("scripts.contributors_entries")
    entries, _ = script.parse(DOC)
    problems, skipped = entries_module.commit_problems(entries, {"alice": 5}, {}, {"bob": "unlinked", "carol": "unlinked"})
    assert any("bob: commit count not compared (unlinked)" in note for note in skipped) and problems == []
    assert entries_module.unmapped_authors(IDENTITY_DOC, [("Stranger", "s@x", 1)], {"stranger": "why"}) == []
    assert len(entries_module.unmapped_authors(IDENTITY_DOC, [("Stranger", "s@x", 1)], {})) == 1


def test_saved_data_may_carry_the_closing_issues_itself(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8"))
    for item in prs:
        if item["number"] == 110:
            item["closing_issues"] = [42]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(base + ["--stub", "dave"]) == 0
    assert "(closing issue #42)" in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")


def test_pending_shows_which_issues_each_pull_request_closes():
    # #1331: the person updating an entry no longer looks the issue up by hand
    prs = [dict(pr(101, "bob", "2026-10-30"), title="fix: a", closing_issues=[1304]),
           dict(pr(102, "bob", "2026-10-31"), title="docs: b", closing_issues=[7, 9]),
           dict(pr(103, "bob", "2026-11-01"), title="chore: c", closing_issues=[]),
           dict(pr(104, "bob", "2026-11-02"), title="no data")]
    lines = script.pending(script.parse(DOC)[0], prs, 100)
    assert "    #101 fix: a (closes #1304)" in lines
    assert "    #102 docs: b (closes #7, #9)" in lines
    assert "    #103 chore: c" in lines and "    #104 no data" in lines


def test_the_weekly_issue_body_carries_the_closing_issues_too():
    from scripts import update_weekly_issue as weekly
    body = weekly.contributors_issue_body(
        "bob: 1 merged PR(s) after the snapshot (#101); count to update\n    #101 fix: a (closes #1304)\n"
        "1 author(s) merged after the snapshot (PR #100).\n")
    assert "  - #101 fix: a (closes #1304)" in body


def test_the_contributors_test_files_stay_under_300_lines():
    # #1327: one 980-line file for four modules became four files and a helper module
    from pathlib import Path
    folder = Path(__file__).parent
    names = ["contributors_helpers", "test_contributors_entries", "test_contributors_fix", "test_contributors_stub", "test_contributors_areas",
             "test_contributors_cli", "test_contributors_reports"]
    for name in names:
        lines = len((folder / f"{name}.py").read_text(encoding="utf-8").splitlines())
        assert lines < 300, f"{name}.py has {lines} lines"
    assert not (folder / "test_check_contributors.py").exists()
