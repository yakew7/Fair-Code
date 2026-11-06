"""scripts/check_issue_refs.py compares roadmap/changelog issue numbers with GitHub (#963, #981)."""

import subprocess
import importlib
import json

script = importlib.import_module("scripts.check_issue_refs")

STATES = {1: "closed", 2: "closed", 3: "open", 4: "open", 5: "merged"}


def test_checked_roadmap_items_may_cite_only_closed_issues():
    ok = "- [x] Done work (#1, #2)\n"
    bad = "- [x] Done work (#1, #3)\n"
    assert script.check_roadmap(ok, STATES) == []
    assert script.check_roadmap(bad, STATES) == ["ROADMAP.md:1: checked item cites open issue(s) #3"]


def test_unchecked_roadmap_items_need_an_open_issue_unless_they_cite_none():
    assert script.check_roadmap("- [ ] Todo (#1, #3)\n", STATES) == []          # one open is enough
    assert script.check_roadmap("- [ ] Todo (#1, #2)\n", STATES) == [
        "ROADMAP.md:1: unchecked item cites only closed issue(s) #1, #2"]
    assert script.check_roadmap("- [ ] Submit the paper next year\n", STATES) == []   # no issue cited
    assert script.check_roadmap("- [x] Shipped in PR #999\n", STATES) == []     # not an issue: ignored
    assert script.check_roadmap("Prose mentioning #3 is not a checklist item\n", STATES) == []


def test_changelog_closes_must_name_closed_issues():
    text = "- fixed (closes #1)\n- fixed (closes #1, #3)\n- hmm closes #4 and #2\n- mentions #3 without closing\n"
    assert script.check_changelog(text, STATES) == [
        "CHANGELOG.md:2: 'closes #3' but #3 is still open",
        "CHANGELOG.md:3: 'closes #4' but #4 is still open",
    ]


def test_contributors_closing_must_name_closed_issues():
    text = (
        "- Alice ([#10](...), closing issue #1)\n"
        "- Bob ([#11](...), closing issue #3)\n"
        "- Carol ([#12](...), closing #4 and #2)\n"
        "- Dave ([#13](...), closing issues #1, #3)\n"
        "- mentions #3 without closing\n"
    )
    assert script.check_contributors(text, STATES) == [
        "CONTRIBUTORS.md:2: 'closing #3' but #3 is still open",
        "CONTRIBUTORS.md:3: 'closing #4' but #4 is still open",
        "CONTRIBUTORS.md:4: 'closing #3' but #3 is still open",
    ]


def test_metrics_sweep_notes_must_cite_existing_issues_or_prs():
    text = (
        "# Metrics\n\n"
        "> **2026-W42 - sweep:** closed issues (#1, #2, #5)\n"
        "> **2026-W43 - next sweep:** closed issues (#1, #999)\n"
        "Regular prose citing #8888 is not a sweep note\n"
    )
    assert script.check_metrics(text, STATES) == [
        "METRICS.md:4: '#999' is not an existing issue or pull request",
    ]


def test_main_reads_an_issues_file_and_reports(tmp_path, capsys, monkeypatch):
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([{"number": n, "state": s.upper()} for n, s in STATES.items()]))
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("- [x] a (#3)\n")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("- b (closes #1)\n")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    assert script.main(["--issues", str(issues)]) == 1
    out = capsys.readouterr().out
    assert "checked item cites open issue(s) #3" in out and "1 issue reference(s) disagree" in out
    roadmap.write_text("- [x] a (#1)\n")
    assert script.main(["--issues", str(issues)]) == 0
    assert "agree with GitHub (5 issues checked)" in capsys.readouterr().out


def test_without_gh_the_check_is_skipped_unless_required(capsys, monkeypatch):
    monkeypatch.setattr(script, "load_states", lambda issues_file: None)
    assert script.main([]) == 0 and "skipping the issue-reference check" in capsys.readouterr().out
    assert script.main(["--require"]) == 2
    capsys.readouterr()


# ── A pull request may cite the issues it closes as closed (#1139) ────────────────────────────

import pytest  # noqa: E402


@pytest.mark.parametrize("body,expected", [
    ("Closes #3", {3}),
    ("fixes #3 and resolves #4", {3, 4}),
    ("Closes #3, closes #4", {3, 4}),
    ("Closes #3, #4", {3}),                      # GitHub closes only the first without a keyword of its own
    ("resolved: #5", {5}),
    ("Fixed yakew7/Fair-Code#3", {3}),
    ("See #3, related to #4, not closing anything", set()),
    ("closest to #3", set()),
    ("", set()),
    (None, set()),
])
def test_issues_closed_by_a_pull_request_body(body, expected):
    assert script.issues_closed_by(body) == expected


def _event(tmp_path, body, name="pull_request"):
    payload = tmp_path / "event.json"
    payload.write_text(json.dumps({"pull_request": {"body": body}}), encoding="utf-8")
    return {"GITHUB_EVENT_NAME": name, "GITHUB_EVENT_PATH": str(payload)}


def test_the_closes_of_a_pull_request_come_from_the_event_payload(tmp_path):
    assert script.pull_request_closes(_event(tmp_path, "Closes #3")) == {3}
    assert script.pull_request_closes(_event(tmp_path, "Closes #3", name="push")) == set()
    assert script.pull_request_closes({}) == set()
    assert script.pull_request_closes({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(tmp_path / "missing.json")}) == set()


def test_a_malformed_pull_request_event_is_ignored(tmp_path):
    payload = tmp_path / "event.json"
    payload.write_text("not json", encoding="utf-8")
    assert script.pull_request_closes({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(payload)}) == set()


def test_load_states_skips_when_gh_is_missing_or_the_issue_query_fails(monkeypatch):
    monkeypatch.setattr(script.shutil, "which", lambda _name: None)
    assert script.load_states(None) is None

    class Failed:
        returncode = 1

    monkeypatch.setattr(script.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Failed())
    assert script.load_states(None) is None


def test_load_states_merges_pull_requests_when_available(monkeypatch):
    class Result:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

    results = iter((
        Result(0, '[{"number": 1, "state": "OPEN"}]'),
        Result(0, '[{"number": 2, "state": "MERGED"}]'),
    ))
    monkeypatch.setattr(script.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))
    assert script.load_states(None) == {1: "open", 2: "merged"}


def test_load_states_keeps_issue_states_when_the_pull_request_query_fails(monkeypatch):
    class Result:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

    results = iter((Result(0, '[{"number": 1, "state": "CLOSED"}]'), Result(1, "")))
    monkeypatch.setattr(script.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))
    assert script.load_states(None) == {1: "closed"}


def _docs(tmp_path, monkeypatch):
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([{"number": n, "state": s.upper()} for n, s in STATES.items()]))
    (tmp_path / "CHANGELOG.md").write_text("- fix (closes #3)\n- other fix (closes #4)\n")
    (tmp_path / "ROADMAP.md").write_text("- [x] done work (#3)\n")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    return issues


def test_a_pull_request_that_closes_the_issue_passes_but_another_open_issue_still_fails(tmp_path, capsys, monkeypatch):
    issues = _docs(tmp_path, monkeypatch)
    monkeypatch.setattr(script, "pull_request_closes", lambda environ=None: {3})
    assert script.main(["--issues", str(issues)]) == 1          # #4 is open and not closed by this PR
    out = capsys.readouterr().out
    assert "note: assuming #3 closed" in out and "'closes #4' but #4 is still open" in out and "#3" not in out.split("note:")[1].split("\n", 1)[1]


def test_when_the_pull_request_closes_everything_cited_the_check_passes(tmp_path, capsys, monkeypatch):
    issues = _docs(tmp_path, monkeypatch)
    monkeypatch.setattr(script, "pull_request_closes", lambda environ=None: {3, 4})
    assert script.main(["--issues", str(issues)]) == 0
    assert "note: assuming #3, #4 closed" in capsys.readouterr().out


def test_locally_the_check_stays_strict_unless_assume_closed_is_given(tmp_path, capsys, monkeypatch):
    issues = _docs(tmp_path, monkeypatch)
    monkeypatch.setattr(script, "pull_request_closes", lambda environ=None: set())
    assert script.main(["--issues", str(issues)]) == 1
    capsys.readouterr()
    assert script.main(["--issues", str(issues), "--assume-closed", "3", "--assume-closed", "4"]) == 0
    assert "note: assuming #3, #4 closed" in capsys.readouterr().out


def test_local_commits_close_reads_the_closing_keywords_of_commits_ahead_of_base():
    # #1240
    from types import SimpleNamespace
    seen = []

    def runner(command, **kwargs):
        seen.append(command)
        return SimpleNamespace(returncode=0, stdout="Fix a thing\n\nCloses #12\n\nSecond\n\nfixes #13 and mentions #99\n")

    assert script.local_commits_close(base="origin/main", runner=runner) == {12, 13}
    assert seen == [["git", "log", "origin/main..HEAD", "--format=%B"]]


def test_local_commits_close_is_empty_without_the_base_ref_or_git():
    from types import SimpleNamespace

    assert script.local_commits_close(base="origin/main", runner=lambda *a, **k: SimpleNamespace(returncode=128, stdout="Closes #1")) == set()

    def missing(*a, **k):
        raise FileNotFoundError("git")

    assert script.local_commits_close(base="origin/main", runner=missing) == set()


def _fake_git(answers):
    from types import SimpleNamespace

    def runner(command, **kwargs):
        key = " ".join(command[1:])
        if key in answers:
            return SimpleNamespace(returncode=0, stdout=answers[key] + "\n")
        return SimpleNamespace(returncode=1, stdout="")

    return runner


def test_find_base_prefers_the_upstream_default_branch_then_origin():
    # #1250
    both = {"symbolic-ref --short refs/remotes/upstream/HEAD": "upstream/trunk",
            "symbolic-ref --short refs/remotes/origin/HEAD": "origin/main"}
    assert script.find_base(runner=_fake_git(both)) == "upstream/trunk"
    assert script.find_base(runner=_fake_git({"symbolic-ref --short refs/remotes/origin/HEAD": "origin/develop"})) == "origin/develop"


def test_find_base_falls_back_to_a_named_branch_and_then_origin_main():
    assert script.find_base(runner=_fake_git({"rev-parse --verify --quiet upstream/main^{commit}": "abc"})) == "upstream/main"
    assert script.find_base(runner=_fake_git({"rev-parse --verify --quiet origin/master^{commit}": "abc"})) == "origin/master"
    assert script.find_base(runner=_fake_git({})) == "origin/main"


def test_a_fork_with_an_upstream_remote_reads_only_the_branchs_own_commits(tmp_path):
    import subprocess

    def git(*args, cwd=tmp_path / "work"):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                              env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
                                   "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)})

    upstream = tmp_path / "upstream.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "--initial-branch=trunk", str(upstream)], check=True, capture_output=True)
    work.mkdir()
    git("init", "--initial-branch=trunk")
    git("commit", "--allow-empty", "-m", "base\n\nCloses #1")
    git("remote", "add", "upstream", str(upstream))
    git("push", "upstream", "trunk")
    git("remote", "set-head", "upstream", "trunk")
    git("remote", "add", "origin", str(upstream))          # a stale origin that has nothing the branch shares
    git("checkout", "-b", "feature")
    git("commit", "--allow-empty", "-m", "feature work\n\nCloses #7")

    assert script.find_base(cwd=work) == "upstream/trunk"
    assert script.local_commits_close(cwd=work) == {7}
