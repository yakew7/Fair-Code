"""The functions that shell out to `gh` build the right commands and handle a failed call or a missing gh (#1253).

The other tests replace these functions with fakes; here a fake `subprocess.run` records the command lines.
"""
import subprocess
import importlib
import json
from types import SimpleNamespace

import pytest

contributors = importlib.import_module("scripts.check_contributors")
traction = importlib.import_module("scripts.check_traction")
metrics = importlib.import_module("scripts.draft_metrics_row")
ghcall = importlib.import_module("scripts.ghcall")

MODULES = [contributors, traction, metrics]


class FakeGh:
    """A stand-in for subprocess.run: `answers` maps a substring of the joined command to (returncode, stdout)."""

    def __init__(self, answers):
        self.answers, self.commands = answers, []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        joined = " ".join(command)
        for key, (code, out) in self.answers.items():
            if key in joined:
                return SimpleNamespace(returncode=code, stdout=out, stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="no answer")


def install(monkeypatch, module, answers, gh=True):
    fake = FakeGh(answers)
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/gh" if gh else None)
    return fake


def test_fetch_prs_asks_for_merged_pull_requests_with_titles(monkeypatch):
    prs = [{"number": 1, "author": {"login": "a"}, "mergedAt": "2026-10-01T00:00:00Z", "title": "t"}]
    fake = install(monkeypatch, contributors, {"pr list": (0, json.dumps(prs))})
    assert contributors.fetch_prs() == prs
    command = fake.commands[0]
    assert command[:5] == ["gh", "pr", "list", "--state", "merged"] and "5000" in command
    assert command[command.index("--json") + 1] == "number,author,mergedAt,title"


def test_fetch_prs_is_none_when_gh_fails_or_is_missing(monkeypatch):
    install(monkeypatch, contributors, {"pr list": (1, "")})
    assert contributors.fetch_prs() is None
    install(monkeypatch, contributors, {}, gh=False)
    assert contributors.fetch_prs() is None


ENTRIES = [{"handle": "alice", "deleted": False}, {"handle": "Bob", "deleted": False},
           {"handle": "gone", "deleted": True}, {"handle": "unlinked", "deleted": False}]
PEOPLE = [[{"login": "alice", "contributions": 6, "type": "User"}, {"login": "dependabot[bot]", "contributions": 50, "type": "Bot"}],
          [{"login": "bob", "contributions": 5, "type": "User"}]]


def test_fetch_commit_data_reads_the_contributors_pages_and_counts_commits_since(monkeypatch):
    fake = install(monkeypatch, contributors, {
        "contributors?per_page=100": (0, json.dumps(PEOPLE)),
        "author=alice": (0, "sha1\nsha2\n"),
        "author=Bob": (0, ""),
    })
    data = contributors.fetch_commit_data(ENTRIES, "2026-10-26T19:51:51Z")
    assert data == {"live": {"alice": 6, "bob": 5}, "after_snapshot": {"alice": 2, "Bob": 0}}
    contributors_call = next(c for c in fake.commands if "contributors?per_page=100" in " ".join(c))
    assert "--paginate" in contributors_call and "--slurp" in contributors_call
    since_calls = [" ".join(c) for c in fake.commands if "commits?author=" in " ".join(c)]
    assert len(since_calls) == 2 and all("since=2026-10-26T19:51:51Z" in c for c in since_calls)
    assert not any("author=gone" in c or "author=unlinked" in c for c in since_calls)      # deleted and unknown logins are not asked


def test_fetch_commit_data_is_none_when_any_call_fails(monkeypatch):
    install(monkeypatch, contributors, {"contributors?per_page=100": (1, "")})
    assert contributors.fetch_commit_data(ENTRIES, "x") is None
    install(monkeypatch, contributors, {"contributors?per_page=100": (0, json.dumps(PEOPLE)), "author=alice": (0, "s\n")})
    assert contributors.fetch_commit_data(ENTRIES, "x") is None                              # the call for Bob failed
    install(monkeypatch, contributors, {}, gh=False)
    assert contributors.fetch_commit_data(ENTRIES, "x") is None


def test_fetch_live_reads_the_repository_and_counts_contributors_without_bots(monkeypatch):
    repo = {"stargazers_count": 55, "forks_count": 68, "subscribers_count": 8}
    people = [[{"login": "a", "type": "User"}, {"login": "b", "type": "User"}, {"login": "dependabot[bot]", "type": "Bot"},
               {"login": "app[bot]", "type": "User"}]]
    fake = install(monkeypatch, traction, {"contributors?per_page=100": (0, json.dumps(people)),
                                           f"repos/{traction.REPO}": (0, json.dumps(repo))})
    assert traction.fetch_live() == {"stars": 55, "forks": 68, "watching": 8, "contributors": 2}
    assert any("--slurp" in c and "--paginate" in c for c in fake.commands)


def test_fetch_live_is_none_when_either_call_fails_or_gh_is_missing(monkeypatch):
    install(monkeypatch, traction, {f"repos/{traction.REPO}": (0, json.dumps({"stargazers_count": 1, "forks_count": 1,
                                                                             "subscribers_count": 1}))})
    assert traction.fetch_live() is None                       # the contributors call has no answer
    install(monkeypatch, traction, {}, gh=False)
    assert traction.fetch_live() is None


def test_fetch_issues_closed_builds_the_search_and_parses_the_count(monkeypatch):
    import datetime
    fake = install(monkeypatch, metrics, {"search/issues": (0, "34\n")})
    assert metrics.fetch_issues_closed(datetime.date(2026, 10, 26), "o/r") == 34
    command = " ".join(fake.commands[0])
    assert "q=repo:o/r is:issue is:closed closed:>=2026-10-26" in command and ".total_count" in command
    install(monkeypatch, metrics, {"search/issues": (0, "not a number")})
    assert metrics.fetch_issues_closed(datetime.date(2026, 10, 26), "o/r") is None
    install(monkeypatch, metrics, {"search/issues": (1, "")})
    assert metrics.fetch_issues_closed(datetime.date(2026, 10, 26), "o/r") is None


def test_fetch_closed_issues_lists_number_and_title(monkeypatch):
    import datetime
    issues = [{"number": 3, "title": "a"}]
    fake = install(monkeypatch, metrics, {"issue list": (0, json.dumps(issues))})
    assert metrics.fetch_closed_issues(datetime.date(2026, 10, 26), "o/r") == issues
    assert "closed:>=2026-10-26" in " ".join(fake.commands[0]) and "number,title" in fake.commands[0]
    install(monkeypatch, metrics, {"issue list": (1, "")})
    assert metrics.fetch_closed_issues(datetime.date(2026, 10, 26), "o/r") is None


@pytest.mark.parametrize("module", MODULES)
def test_every_wrapper_module_calls_gh_through_the_timeout_helper(module):
    # #1266: no module may call subprocess.run for gh itself any more
    source = open(module.__file__, encoding="utf-8").read()
    assert "run_gh" in source
    assert 'subprocess.run(["gh"' not in source


def test_run_gh_gives_every_call_a_timeout_and_turns_a_timeout_into_a_failed_result(monkeypatch, capsys):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    done = ghcall.run_gh(["gh", "api", "repos/o/r"], timeout=5)
    assert seen["timeout"] == 5 and seen["capture_output"] is True and seen["text"] is True
    assert (done.returncode, done.stdout) == (ghcall.TIMED_OUT, "")
    assert "did not answer within 5 s" in capsys.readouterr().err

    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="ok", **{"stderr": ""}) if kwargs["timeout"] == ghcall.GH_TIMEOUT else None)
    assert ghcall.run_gh(["gh", "x"]).stdout == "ok"                            # the default timeout is applied


@pytest.mark.parametrize("call", [
    lambda: contributors.fetch_prs(),
    lambda: traction.fetch_live(),
    lambda: metrics.fetch_issues_closed(__import__("datetime").date(2026, 11, 2), "o/r"),
    lambda: metrics.fetch_open_among({1}, "o/r"),
    lambda: contributors.fetch_commit_data([{"handle": "a", "deleted": False}], "2026-11-01T00:00:00Z"),
])
def test_a_stalled_gh_call_behaves_like_an_offline_one(monkeypatch, capsys, call):
    def stalled(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", stalled)
    monkeypatch.setattr(contributors.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(traction.shutil, "which", lambda name: "/usr/bin/gh")
    assert call() is None
