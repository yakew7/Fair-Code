"""scripts/check_contributors.py compares CONTRIBUTORS.md with the merged pull requests (#1149)."""

import importlib
import json

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
