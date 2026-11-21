"""The GitHub wrappers and the command-line modes of scripts/check_contributors.py (#1327)."""
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
    STUB_DOC,
    _stub_site,
    _two_newcomers,
)


def test_fix_requires_pr_data_and_does_not_change_the_file(tmp_path, capsys, monkeypatch):
    path = tmp_path / "CONTRIBUTORS.md"
    path.write_text(DOC, encoding="utf-8")
    monkeypatch.setattr(script, "fetch_prs", lambda: None)

    assert script.main(["--file", str(path), "--fix"]) == 2
    assert "needs merged pull request data" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == DOC


def test_without_gh_it_skips_unless_required(tmp_path, capsys, monkeypatch):
    (tmp_path / "CONTRIBUTORS.md").write_text(DOC, encoding="utf-8")
    monkeypatch.setattr(script, "fetch_prs", lambda: None)
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md")]) == 0
    assert "skipping the contributors check" in capsys.readouterr().out
    assert script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--require"]) == 1


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


def test_git_authors_also_counts_co_authored_by_trailers():
    # #1269
    from types import SimpleNamespace

    def runner(command, **kwargs):
        if "trailers" in command[-1]:
            return SimpleNamespace(stdout="Dana <dana@example.org>\n\nDana <dana@example.org>\nnot a trailer\n")
        return SimpleNamespace(stdout="Alice A.|alice@example.org\n")

    assert script.git_authors(runner=runner) == [("Dana", "dana@example.org", 2), ("Alice A.", "alice@example.org", 1)]


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


def test_main_does_not_call_gh_for_closing_issues_when_given_saved_pr_data(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "fetch_pr_details", lambda numbers: pytest.fail("gh must not be called for --prs data"))
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0


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


def test_run_pending_prints_the_closing_issues_fetched_from_github(capsys):
    entries, _ = script.parse(DOC)
    prs = [pr(101, "bob", "2026-10-30")]
    prs[0]["title"] = "fix: a"
    script.run_pending(entries, prs, 100, fetch=lambda numbers: {101: {"commit_authors": ["bob"], "closing_issues": [1304]}})
    assert "#101 fix: a (closes #1304)" in capsys.readouterr().out


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


def _documented_example():
    """The JSON example in the script's docstring (#1339)."""
    text = script.__doc__.split("An example:", 1)[1]
    return json.loads(text[text.index("["):text.rindex("]") + 1])


def test_the_documented_example_is_valid_json_with_every_documented_key():
    (item,) = _documented_example()
    assert {"number", "author", "mergedAt", "title", "body", "commit_authors", "closing_issues", "files"} <= set(item)
    for key in ("commit_authors", "closing_issues", "files"):
        assert key in script.__doc__


def test_the_documented_example_runs_through_pending_and_stub_without_calling_gh(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(script, "fetch_pr_details", lambda numbers: pytest.fail("the file carries the details already"))
    item = dict(_documented_example()[0], number=110, author={"login": "dave", "is_bot": False})
    prs = PRS + [item]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    base = ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]

    assert script.main(base + ["--pending"]) == 1
    out = capsys.readouterr().out
    assert "dave: 1 merged PR(s)" in out and "(closes #1303)" in out
    assert "has a commit authored by PRIYANKA2272004, not by dave" in out

    assert script.main(base + ["--stub", "dave"]) == 0
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert "closing issue #1303" in text and "Handles empty groups" in text and "authored by someone else" in text
