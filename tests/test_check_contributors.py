"""scripts/check_contributors.py compares CONTRIBUTORS.md with the merged pull requests (#1149)."""

import importlib
import json
import re

import pytest

script = importlib.import_module("scripts.check_contributors")

DOC = """# Contributors

**Snapshot:** 2026-10-24, covering everything merged through **PR #100**.

## Maintainer

Someone.

## Core contributors

### [@alice](https://github.com/alice)

**3 merged PRs · 5 commits · first merged 2026-05-01**

Text.

## Contributors

### Bob Builder - [@bob](https://github.com/bob)

**2 merged PRs · 4 commits · first merged 2026-06-01**

### Carol - [@carol](https://github.com/carol)

**2 merged PRs · 3 commits · first merged 2026-06-02**

### Old Timer - `ghost-user` (account deleted)

**1 merged PR · 2 commits · first merged 2026-05-19**
"""


def pr(number, login, day, bot=False):
    return {"number": number, "author": {"login": login, "is_bot": bot}, "mergedAt": f"{day}T10:00:00Z"}


PRS = [pr(1, "alice", "2026-05-01"), pr(2, "alice", "2026-05-02"), pr(3, "alice", "2026-05-03"),
       pr(4, "bob", "2026-06-01"), pr(5, "bob", "2026-06-05"), pr(6, "carol", "2026-06-02"),
       pr(7, "carol", "2026-06-09"), pr(8, "app/", "2026-05-19", bot=True),
       pr(9, "yakew7", "2026-05-20"), pr(10, "app/dependabot", "2026-05-21", bot=True)]


def run(tmp_path, capsys, doc=DOC, prs=PRS, extra=()):
    (tmp_path / "CONTRIBUTORS.md").write_text(doc, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json"), *extra])
    return code, capsys.readouterr().out


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


def test_fix_refreshes_counts_dates_and_order_without_changing_entry_prose(tmp_path, capsys):
    bob = ("### Bob Builder - [@bob](https://github.com/bob)\n\n"
           "**1 merged PR · 4 commits · first merged 2026-06-08**\n\n"
           "bob's original profile prose stays exactly as written.\n\n")
    carol = ("### Carol - [@carol](https://github.com/carol)\n\n"
             "**3 merged PRs · 3 commits · first merged 2026-06-09**\n\n"
             "carol's original profile prose stays exactly as written.\n\n")
    doc = DOC[:DOC.index("### Bob Builder")]
    doc += carol + bob + DOC[DOC.index("### Old Timer"):]
    # Carol is deliberately ahead of Bob and has the wrong count and date.
    path = tmp_path / "CONTRIBUTORS.md"
    prs_path = tmp_path / "prs.json"
    path.write_text(doc, encoding="utf-8")
    prs_path.write_text(json.dumps(PRS), encoding="utf-8")

    assert script.main(["--file", str(path), "--prs", str(prs_path), "--fix"]) == 0
    output = capsys.readouterr().out
    fixed = path.read_text(encoding="utf-8")
    assert "updated:" in output and "OK: 4 entries" in output
    assert fixed.index("Bob Builder") < fixed.index("Carol")
    assert "**2 merged PRs · 4 commits · first merged 2026-06-01**" in fixed
    assert "**2 merged PRs · 3 commits · first merged 2026-06-02**" in fixed
    assert "bob's original profile prose stays exactly as written." in fixed
    assert "carol's original profile prose stays exactly as written." in fixed

    assert script.main(["--file", str(path), "--prs", str(prs_path), "--fix"]) == 0
    assert "updated:" not in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == fixed


def test_fix_requires_pr_data_and_does_not_change_the_file(tmp_path, capsys, monkeypatch):
    path = tmp_path / "CONTRIBUTORS.md"
    path.write_text(DOC, encoding="utf-8")
    monkeypatch.setattr(script, "fetch_prs", lambda: None)

    assert script.main(["--file", str(path), "--fix"]) == 2
    assert "needs merged pull request data" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == DOC


def test_an_author_with_no_entry_fails_but_the_maintainer_and_bots_do_not(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=PRS + [pr(12, "dave", "2026-07-02")])
    assert code == 1 and "dave: 1 merged PRs on GitHub but no entry" in out
    assert "yakew7" not in out and "dependabot" not in out


def test_an_entry_github_has_never_heard_of_fails(tmp_path, capsys):
    code, out = run(tmp_path, capsys, prs=[p for p in PRS if p["author"]["login"] != "carol"])
    assert code == 1 and "carol: listed with 2 merged PRs but GitHub shows none" in out


def test_without_gh_it_skips_unless_required(tmp_path, capsys, monkeypatch):
    (tmp_path / "CONTRIBUTORS.md").write_text(DOC, encoding="utf-8")
    monkeypatch.setattr(script, "fetch_prs", lambda: None)
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md")]) == 0
    assert "skipping the contributors check" in capsys.readouterr().out
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--require"]) == 1


def test_the_real_file_parses_in_rule_order():
    entries, through = script.parse((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    assert through and len(entries) > 40
    problems, _ = script.check(entries, [], through)
    assert not [p for p in problems if "entry" in p and "puts" in p]


COMMITS = {"live": {"alice": 6, "Bob": 5, "carol": 3}, "after_snapshot": {"alice": 1, "Bob": 1}}


def test_commit_counts_are_live_minus_commits_after_the_snapshot(tmp_path, capsys):
    # alice 6 live - 1 after = 5 (file 5), bob 5 - 1 = 4 (file 4), carol 3 - 0 = 3 (file 3)  (#1199)
    (tmp_path / "commits.json").write_text(json.dumps(COMMITS), encoding="utf-8")
    code, out = run(tmp_path, capsys, extra=("--commits-data", str(tmp_path / "commits.json")))
    assert code == 0 and "with commit counts at the snapshot" in out


def test_a_wrong_commit_count_fails_and_a_missing_login_is_skipped(tmp_path, capsys):
    data = {"live": {"alice": 6, "bob": 9}, "after_snapshot": {"alice": 1}}
    (tmp_path / "commits.json").write_text(json.dumps(data), encoding="utf-8")
    code, out = run(tmp_path, capsys, extra=("--commits-data", str(tmp_path / "commits.json")))
    assert code == 1
    assert "bob: file says 4 commits, GitHub says 9 at the snapshot (9 now, 0 since)" in out
    assert "carol: not in the contributors API and not in COMMIT_EXCEPTIONS" in out


def test_snapshot_time_is_one_second_after_the_snapshot_pr_merged():
    prs = [{"number": 100, "mergedAt": "2026-10-26T19:51:50Z"}]
    assert script.snapshot_time(prs, 100) == "2026-10-26T19:51:51Z"
    assert script.snapshot_time(prs, 99) is None


def test_commits_without_gh_is_an_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "fetch_commit_data", lambda entries, since: None)
    code, out = run(tmp_path, capsys, prs=PRS + [{"number": 100, "author": {"login": "x", "is_bot": True},
                                                  "mergedAt": "2026-10-26T19:51:50Z"}], extra=("--commits",))
    assert code == 2 and "needs the GitHub CLI" in out


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


def test_move_snapshot_points_the_line_at_the_newest_pr_and_its_day():
    # #1235
    prs = [pr(100, "alice", "2026-10-24"), pr(130, "bob", "2026-10-30")]
    moved = script.move_snapshot(DOC, prs, 130)
    assert "**Snapshot:** 2026-10-30, covering everything merged through **PR #130**" in moved
    assert script.parse(moved)[1] == 130
    with pytest.raises(ValueError, match="PR #999 is not in"):
        script.move_snapshot(DOC, prs, 999)
    with pytest.raises(ValueError, match="could not find"):
        script.move_snapshot("no snapshot line", prs, 130)


def test_fix_document_refreshes_commit_counts_when_given_them_and_keeps_the_prose():
    fixed = script.fix_document(DOC, PRS, 100, commits={"Alice": 9, "bob": 4, "carol": 3})
    entries, _ = script.parse(fixed)
    assert {e["handle"]: e["commits"] for e in entries}["alice"] == 9
    assert "Text." in fixed and fixed.count("### ") == DOC.count("### ")
    assert script.fix_document(DOC, PRS, 100) == DOC          # without commit data nothing about commits changes


def test_fix_with_commits_moves_the_snapshot_and_leaves_a_file_the_commit_check_passes(tmp_path, capsys, monkeypatch):
    prs = PRS + [pr(110, "bob", "2026-10-30"), pr(120, "newbie", "2026-10-31")]
    doc = DOC.replace("**2 merged PRs · 4 commits · first merged 2026-06-01**", "**2 merged PRs · 1 commits · first merged 2026-06-01**")
    seen = {}

    def fake_fetch(entries, since):
        seen["since"] = since
        return {"live": {"alice": 5, "bob": 7, "carol": 3}, "after_snapshot": {}}

    monkeypatch.setattr(script, "fetch_commit_data", fake_fetch)
    code, out = run(tmp_path, capsys, doc=doc, prs=prs, extra=("--fix", "--commits"))
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")

    assert seen["since"] == "2026-10-31T10:00:01Z"
    assert "covering everything merged through **PR #120**" in text and "updated:" in out
    bob = next(e for e in script.parse(text)[0] if e["handle"] == "bob")
    assert (bob["merged"], bob["commits"]) == (3, 7)
    assert code == 1 and "newbie: 1 merged PRs on GitHub but no entry in the file" in out   # prose for a new person stays manual


IDENTITY_DOC = DOC + """
## Git identity map

| GitHub handle | Git author name(s) recorded in history |
|---------------|----------------------------------------|
| [@alice](https://github.com/alice) | `Alice A.`, `alice@example.org` |
| [@bob](https://github.com/bob) | `bob` |
"""


def test_unmapped_authors_lists_only_people_with_no_entry_or_identity_row():
    # #1236
    authors = [("Alice A.", "alice@example.org", 4), ("alice@example.org", "alice@example.org", 1),
               ("Carol", "carol@example.org", 2), ("Somebody Else", "12345+bob@users.noreply.github.com", 1),
               ("Stranger", "stranger@example.org", 3), ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", 9),
               ("GitHub", "noreply@github.com", 5), ("Erol Tasci", "e@example.org", 1)]
    lines = script.unmapped_authors(IDENTITY_DOC, authors)
    assert lines == ["Stranger <stranger@example.org>: 3 commit(s) map to no entry or Git identity map row"]


def test_git_authors_counts_each_name_and_email_pair():
    from types import SimpleNamespace
    out = "A|a@x\nA|a@x\nB|b@x\nA|other@x\n"
    authors = script.git_authors(runner=lambda *a, **k: SimpleNamespace(stdout=out))
    assert authors == [("A", "a@x", 2), ("A", "other@x", 1), ("B", "b@x", 1)]


def test_identities_flag_fails_on_an_unmapped_author_and_passes_when_all_map(tmp_path, capsys, monkeypatch):
    (tmp_path / "CONTRIBUTORS.md").write_text(IDENTITY_DOC, encoding="utf-8")
    monkeypatch.setattr(script, "git_authors", lambda: [("Stranger", "s@x", 2)])
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--identities"]) == 1
    assert "Stranger <s@x>: 2 commit(s)" in capsys.readouterr().out
    monkeypatch.setattr(script, "git_authors", lambda: [("Alice A.", "a@x", 2)])
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--identities"]) == 0
    assert "OK: every git author maps" in capsys.readouterr().out



def test_fix_with_commits_fetches_the_commit_data_once(tmp_path, capsys, monkeypatch):
    # #1248: the comparison after the rewrite reuses the data the rewrite fetched
    prs = PRS + [pr(120, "bob", "2026-10-31")]
    calls = []

    def fake_fetch(entries, since):
        calls.append(since)
        return {"live": {"alice": 5, "bob": 4, "carol": 3}, "after_snapshot": {}}

    monkeypatch.setattr(script, "fetch_commit_data", fake_fetch)
    monkeypatch.setattr(script, "_COMMIT_DATA", {})
    code, out = run(tmp_path, capsys, prs=prs, extra=("--fix", "--commits"))
    assert len(calls) == 1 and "with commit counts at the snapshot" in out


def test_save_commits_writes_the_fetched_data_for_commits_data(tmp_path, capsys, monkeypatch):
    prs = PRS + [pr(100, "x", "2026-10-24", bot=True)]
    data = {"live": {"alice": 5, "bob": 4, "carol": 3}, "after_snapshot": {}}
    monkeypatch.setattr(script, "fetch_commit_data", lambda entries, since: data)
    monkeypatch.setattr(script, "_COMMIT_DATA", {})
    saved = tmp_path / "commits.json"
    code, out = run(tmp_path, capsys, prs=prs, extra=("--commits", "--save-commits", str(saved)))
    assert code == 0 and json.loads(saved.read_text(encoding="utf-8")) == data

    code, out = run(tmp_path, capsys, prs=prs, extra=("--commits-data", str(saved)))
    assert code == 0 and "with commit counts at the snapshot" in out


def test_pending_adds_each_pull_requests_title_when_the_data_has_titles(tmp_path, capsys):
    # #1258
    prs = [dict(p, title=f"title {p['number']}") for p in PRS] + [
        dict(pr(101, "bob", "2026-10-30"), title="fix: a thing"), dict(pr(103, "newbie", "2026-10-31"), title="feat: new")]
    code, out = run(tmp_path, capsys, prs=prs, extra=("--pending",))
    assert code == 1
    assert "bob: 1 merged PR(s) after the snapshot (#101); count to update\n    #101 fix: a thing\n" in out
    assert "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet\n    #103 feat: new\n" in out
    assert out.strip().endswith("2 author(s) merged after the snapshot (PR #100).")


AREA_DOC = DOC + """
## Contributions by area

| Area | Contributors |
|------|--------------|
| **Audits** | [@alice](https://github.com/alice), [@Bob](https://github.com/bob) |
"""


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


STUB_DOC = AREA_DOC.replace("\n## Contributions by area", "\n---\n\n## Contributions by area").replace("[@Bob](https://github.com/bob) |", "[@Bob](https://github.com/bob), [@carol](https://github.com/carol) |") + """
| **Contributor tooling & docs** | [@alice](https://github.com/alice) |

---
"""


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


def test_git_authors_also_counts_co_authored_by_trailers():
    # #1269
    from types import SimpleNamespace

    def runner(command, **kwargs):
        if "trailers" in command[-1]:
            return SimpleNamespace(stdout="Dana <dana@example.org>\n\nDana <dana@example.org>\nnot a trailer\n")
        return SimpleNamespace(stdout="Alice A.|alice@example.org\n")

    assert script.git_authors(runner=runner) == [("Dana", "dana@example.org", 2), ("Alice A.", "alice@example.org", 1)]


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


def _stub_site(tmp_path):
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "dave", "2026-10-31"), title="docs: b")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    return ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]


def test_stub_with_commits_takes_the_new_persons_commit_count_from_github(tmp_path, capsys, monkeypatch):
    # #1271
    base = _stub_site(tmp_path)
    monkeypatch.setattr(script, "_COMMIT_DATA", {})
    monkeypatch.setattr(script, "fetch_commit_data", lambda entries, since: {
        "live": {"alice": 5, "bob": 4, "carol": 3, "dave": 9}, "after_snapshot": {}})
    assert script.main(base + ["--stub", "dave", "--commits"]) == 0
    assert "commit counts come from the contributors graph" in capsys.readouterr().out
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    dave = next(e for e in script.parse(text)[0] if e["handle"] == "dave")
    assert (dave["merged"], dave["commits"]) == (2, 9)


def test_stub_with_commits_says_so_when_the_new_person_is_not_in_the_api_yet(tmp_path, capsys, monkeypatch):
    base = _stub_site(tmp_path)
    monkeypatch.setattr(script, "_COMMIT_DATA", {})
    monkeypatch.setattr(script, "fetch_commit_data", lambda entries, since: {
        "live": {"alice": 5, "bob": 4, "carol": 3}, "after_snapshot": {}})
    assert script.main(base + ["--stub", "dave", "--commits"]) == 0
    assert "dave is not in the contributors API yet" in capsys.readouterr().out
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert next(e for e in script.parse(text)[0] if e["handle"] == "dave")["commits"] == 2          # the placeholder


def test_stub_without_commits_prints_the_reminder(tmp_path, capsys):
    assert script.main(_stub_site(tmp_path) + ["--stub", "dave"]) == 0
    assert "commit counts are placeholders" in capsys.readouterr().out


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


def test_the_plain_check_fails_on_a_left_over_stub_and_passes_once_it_is_replaced(tmp_path, capsys):
    stubbed = DOC.replace("Text.\n", "TODO: describe the work in a sentence or two.\n")
    code, out = run(tmp_path, capsys, doc=stubbed)
    assert code == 1 and "alice: the entry still has a TODO placeholder" in out
    code, out = run(tmp_path, capsys, doc=DOC)
    assert code == 0


def _replace_the_todo(path):
    """Replace the whole `TODO:` line of a stub with a real sentence, as the person writing the entry would."""
    path.write_text(re.sub(r"^TODO:.*$", "Fixed a thing.", path.read_text(encoding="utf-8"), flags=re.MULTILINE), encoding="utf-8")


def test_a_stub_just_written_fails_until_its_sentence_is_replaced(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    capsys.readouterr()
    assert script.main(base) == 1 and "dave: the entry still has a TODO placeholder" in capsys.readouterr().out
    _replace_the_todo(tmp_path / "CONTRIBUTORS.md")
    assert script.main(base) == 0


def test_the_sections_closing_rule_stays_at_the_end_when_entries_are_sorted():
    # stubbing a second newcomer used to carry the `---` with the entry that had been last and leave it mid-section
    doc = STUB_DOC
    prs = PRS + [pr(110, "zed", "2026-10-30"), pr(111, "zed", "2026-10-31"), pr(112, "zed", "2026-11-01")]
    text = script.add_stub(doc, "zed", prs)             # zed (3 PRs) sorts to the top, carol (the last entry) stays last
    fixed = script.fix_document(text, prs, 112)
    entries = [e["handle"] for e in script.parse(fixed)[0]]
    assert entries.index("zed") < entries.index("bob")
    body = fixed.split("## Contributors", 1)[1].split("## Contributions by area", 1)[0]
    assert body.count("\n---\n") == 1 and body.rstrip().endswith("---")


def test_two_stubs_in_a_row_leave_one_closing_rule_and_a_file_that_is_otherwise_unchanged(tmp_path, capsys):
    base = _stub_site(tmp_path)
    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8")) + [
        dict(pr(130, "erin", "2026-11-02"), title="docs: x"), dict(pr(131, "erin", "2026-11-03"), title="docs: y")]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(base + ["--stub", "dave"]) == 0
    assert script.main(base + ["--stub", "erin"]) == 0
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    body = text.split("## Contributors", 1)[1].split("## Contributions by area", 1)[0]
    assert body.count("\n---\n") == 1
    assert [e["handle"] for e in script.parse(text)[0]].count("erin") == 1
    assert script.fix_document(text, prs, 131) == text                        # sorting again changes nothing


def _two_newcomers(tmp_path):
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "erin", "2026-10-31"), title="docs: b"),
                 dict(pr(121, "erin", "2026-11-01"), title="docs: c")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    return ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]


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


def test_several_stubs_with_commits_fetch_the_data_once(tmp_path, capsys, monkeypatch):
    base = _two_newcomers(tmp_path)
    calls = []

    def fake_fetch(entries, since):
        calls.append(since)
        return {"live": {"alice": 5, "bob": 4, "carol": 3, "dave": 2, "erin": 6}, "after_snapshot": {}}

    monkeypatch.setattr(script, "_COMMIT_DATA", {})
    monkeypatch.setattr(script, "fetch_commit_data", fake_fetch)
    assert script.main(base + ["--stub", "dave", "erin", "--commits"]) == 0
    assert len(calls) == 1 and "commit counts come from the contributors graph" in capsys.readouterr().out
    entries = {e["handle"]: e for e in script.parse((tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8"))[0]}
    assert (entries["dave"]["commits"], entries["erin"]["commits"]) == (2, 6)


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


def test_run_pending_looks_the_commit_authors_up_only_for_pending_prs_and_only_when_asked_to(capsys):
    entries, _ = script.parse(DOC)
    prs = [pr(5, "alice", "2026-10-01"), pr(101, "bob", "2026-10-30"), pr(102, "app/dependabot", "2026-10-31", bot=True),
           dict(pr(103, "bob", "2026-10-31"), commit_authors=["bob"])]
    asked = []

    def fetch(numbers):
        asked.append(numbers)
        return {101: {"commit_authors": ["bob", "stranger"], "closing_issues": []}}

    assert script.run_pending(entries, prs, 100, fetch=fetch) == 1
    assert asked == [[101]]                                  # not #5 (before the snapshot), the bot's PR or #103 (has the data)
    assert "#101 has a commit authored by stranger" in capsys.readouterr().out
    asked.clear()
    script.run_pending(entries, prs, 100, fetch=None)
    assert asked == []


def test_main_does_not_call_gh_for_commit_authors_when_given_saved_pr_data(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "fetch_pr_details", lambda numbers: pytest.fail("gh must not be called for --prs data"))
    code, out = run(tmp_path, capsys, prs=PRS + [pr(101, "bob", "2026-10-30")], extra=("--pending",))
    assert code == 1 and "bob: 1 merged PR(s)" in out


def test_fetch_pr_details_makes_one_gh_call_per_pr_with_both_fields_and_gives_up_when_one_fails(monkeypatch):
    # #1332: --pending and --stub used to make two gh pr view calls per PR between them
    from types import SimpleNamespace
    import subprocess as sp
    calls = []

    def fake(command, **kwargs):
        calls.append(command)
        number = int(command[3])
        if number == 9:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"commit_authors": ["bob", f"user{number}"], "closing_issues": [number * 10],
                                                                     "files": [f"tests/t{number}.py"]}))

    monkeypatch.setattr(sp, "run", fake)
    monkeypatch.setattr(script.shutil, "which", lambda name: "/usr/bin/gh")
    assert script.fetch_pr_details([7, 8]) == {
        7: {"commit_authors": ["bob", "user7"], "closing_issues": [70], "files": ["tests/t7.py"]},
        8: {"commit_authors": ["bob", "user8"], "closing_issues": [80], "files": ["tests/t8.py"]}}
    assert len(calls) == 2 and all(c[:3] == ["gh", "pr", "view"] for c in calls)
    assert all("commits,closingIssuesReferences,files" in c for c in calls)
    assert script.fetch_pr_details([7, 9]) is None
    monkeypatch.setattr(script.shutil, "which", lambda name: None)
    assert script.fetch_pr_details([7]) is None


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


def test_main_does_not_call_gh_for_closing_issues_when_given_saved_pr_data(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "fetch_pr_details", lambda numbers: pytest.fail("gh must not be called for --prs data"))
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0


def test_saved_data_may_carry_the_closing_issues_itself(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8"))
    for item in prs:
        if item["number"] == 110:
            item["closing_issues"] = [42]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(base + ["--stub", "dave"]) == 0
    assert "(closing issue #42)" in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")


def test_add_details_fills_the_pr_dicts_without_overwriting_saved_data():
    prs = [dict(pr(1, "a", "2026-11-01"), closing_issues=[9]), pr(2, "b", "2026-11-02")]
    script.add_details(prs, {1: {"commit_authors": ["a"], "closing_issues": [1]}, 2: {"commit_authors": ["c"], "closing_issues": [2]}})
    assert prs[0]["closing_issues"] == [9] and prs[0]["commit_authors"] == ["a"]
    assert prs[1]["closing_issues"] == [2] and prs[1]["commit_authors"] == ["c"]
    script.add_details(prs, None)                              # a failed fetch changes nothing
    assert prs[1]["commit_authors"] == ["c"]


def test_one_stub_run_asks_for_each_pr_once_and_a_pending_run_too(tmp_path, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(script, "fetch_pr_details", lambda numbers: calls.append(sorted(numbers)) or {
        n: {"commit_authors": ["x"], "closing_issues": []} for n in numbers})
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "erin", "2026-10-31"), title="docs: b")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    entries, _ = script.parse(STUB_DOC)
    args = script.argparse.Namespace(stub=["dave", "erin"], commits=False, area=script.DEFAULT_AREA, save_commits=None,
                                     file=tmp_path / "CONTRIBUTORS.md")
    script.run_stub(args, STUB_DOC, [dict(p) for p in prs], fetch_details=script.fetch_pr_details)
    assert calls == [[110, 120]]                                # one fetch for both people, one call per PR inside it
    calls.clear()
    script.run_pending(entries, [dict(p) for p in prs], 100, fetch=script.fetch_pr_details)
    assert calls == [[110, 120]]


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


def test_run_pending_prints_the_closing_issues_fetched_from_github(capsys):
    entries, _ = script.parse(DOC)
    prs = [pr(101, "bob", "2026-10-30")]
    prs[0]["title"] = "fix: a"
    script.run_pending(entries, prs, 100, fetch=lambda numbers: {101: {"commit_authors": ["bob"], "closing_issues": [1304]}})
    assert "#101 fix: a (closes #1304)" in capsys.readouterr().out


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


def test_the_stub_run_prints_the_suggested_exception_lines(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    prs = json.loads((tmp_path / "prs.json").read_text(encoding="utf-8"))
    for item in prs:
        if item["number"] == 110:
            item["commit_authors"] = ["someone-else"]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    assert script.main(base + ["--stub", "dave"]) == 0
    out = capsys.readouterr().out
    assert "add to scripts/contributors-exceptions.json" in out
    assert '  unlisted_authors: "someone-else"' in out and '  commit_exceptions: "dave"' in out
    assert "authored by someone else" in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")


def test_a_stub_without_foreign_commit_authors_prints_no_exception_lines(tmp_path, capsys):
    assert script.main(_two_newcomers(tmp_path) + ["--stub", "dave"]) == 0
    assert "contributors-exceptions.json" not in capsys.readouterr().out


AREA_DOC_TABLE = STUB_DOC.replace("| **Audits** |", "| **Profiler - web** | [@alice](https://github.com/alice) |\n| **Tests** | [@bob](https://github.com/bob) |\n| **Audits** |")


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
