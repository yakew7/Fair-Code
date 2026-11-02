"""scripts/draft_metrics_row.py prints the next METRICS.md weekly row from GitHub's figures (#1242)."""
import datetime
import importlib
import json

import pytest

script = importlib.import_module("scripts.draft_metrics_row")
traction = importlib.import_module("scripts.check_traction")

METRICS = """| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |
|------|------:|------:|---------:|-------------:|-------------:|----------:|--------------:|------------:|
| 2026-W42 | 51 | 58 | 8 | 53 | 30K+ total | 20 | 123 | 7 total |
| 2026-W43 | 53 | 64 | 8 | 55 | 30K+ total | 20 | 76 | 7 total |

> a note
"""
LIVE = {"stars": 54, "forks": 67, "watching": 8, "contributors": 58, "issues_closed": 12}


def test_iso_week_and_week_start_handle_the_year_boundary():
    assert script.iso_week(datetime.date(2026, 11, 1)) == "2026-W44"
    assert script.iso_week(datetime.date(2026, 12, 31)) == "2026-W53"
    assert script.iso_week(datetime.date(2027, 1, 1)) == "2026-W53"
    assert script.week_start(datetime.date(2026, 11, 1)) == datetime.date(2026, 10, 26)   # a Sunday belongs to the week before


def test_the_next_row_uses_github_figures_and_carries_the_hand_written_cells():
    previous = script.latest_row(METRICS)
    assert previous[0] == "2026-W43"
    row = script.build_row(previous, LIVE, datetime.date(2026, 11, 3))
    assert row == "| 2026-W45 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 12 | 7 total |"


def test_a_row_for_the_same_week_is_refused():
    with pytest.raises(ValueError, match="already for 2026-W43"):
        script.build_row(script.latest_row(METRICS), LIVE, datetime.date(2026, 10, 22))


def test_the_printed_row_passes_the_live_traction_comparison(tmp_path, capsys):
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    data = tmp_path / "live.json"
    data.write_text(json.dumps(LIVE), encoding="utf-8")

    assert script.main(["--file", str(metrics), "--date", "2026-11-03", "--live-data", str(data)]) == 0
    row = capsys.readouterr().out.strip()

    observations = traction.metrics_observations(METRICS.replace("> a note", row) + "\n![Stars](https://img.shields.io/badge/Stars-54-x)")[0]
    assert traction.live_differences([o for o in observations if "weekly row" in o[1]], LIVE) == []


def test_main_exits_1_for_a_repeated_week_and_2_without_gh(tmp_path, capsys, monkeypatch):
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    data = tmp_path / "live.json"
    data.write_text(json.dumps(LIVE), encoding="utf-8")
    assert script.main(["--file", str(metrics), "--date", "2026-10-22", "--live-data", str(data)]) == 1
    assert "already for 2026-W43" in capsys.readouterr().err

    monkeypatch.setattr(script.shutil, "which", lambda name: None)
    assert script.main(["--file", str(metrics), "--date", "2026-11-03"]) == 2
    assert "needs the GitHub CLI" in capsys.readouterr().err


def test_the_real_metrics_file_has_a_newest_row_to_carry_over():
    cells = script.latest_row((script.ROOT / "METRICS.md").read_text(encoding="utf-8"))
    assert len(cells) == 9 and cells[0].startswith("2026-W")


def test_pending_closes_are_added_to_the_issues_closed_cell(tmp_path, capsys):
    # #1251: 12 already closed this week + 16 the sweep's commits close on merge
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    data = tmp_path / "live.json"
    data.write_text(json.dumps({**LIVE, "pending_closes": 16}), encoding="utf-8")
    assert script.main(["--file", str(metrics), "--date", "2026-11-03", "--live-data", str(data)]) == 0
    assert capsys.readouterr().out.strip() == "| 2026-W45 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 28 | 7 total |"


def test_open_issues_are_counted_and_a_closed_one_is_not(monkeypatch):
    from types import SimpleNamespace
    states = {1: "open", 2: "closed", 3: "open"}
    monkeypatch.setattr(script.subprocess, "run", lambda command, **kw: SimpleNamespace(
        returncode=0, stdout=states[int(command[2].rsplit("/", 1)[1])] + "\n"))
    assert script.fetch_open_among({1, 2, 3}, "o/r") == 2
    monkeypatch.setattr(script.subprocess, "run", lambda command, **kw: SimpleNamespace(returncode=1, stdout=""))
    assert script.fetch_open_among({1}, "o/r") is None


def test_pending_closes_online_uses_the_local_commit_closes(monkeypatch, tmp_path, capsys):
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    refs = importlib.import_module("scripts.check_issue_refs")
    monkeypatch.setattr(script.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(traction, "fetch_live", lambda repo=traction.REPO: {"stars": 54, "forks": 67, "watching": 8, "contributors": 58})
    monkeypatch.setattr(script, "fetch_issues_closed", lambda since, repo: 10)
    monkeypatch.setattr(refs, "local_commits_close", lambda *a, **k: {5, 6, 7})
    monkeypatch.setattr(script, "fetch_open_among", lambda numbers, repo: len(numbers))
    assert script.main(["--file", str(metrics), "--date", "2026-11-03", "--pending-closes"]) == 0
    assert "| 13 |" in capsys.readouterr().out
