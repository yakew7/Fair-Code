"""scripts/draft_metrics_row.py prints the next METRICS.md weekly row from GitHub's figures (#1242)."""
import subprocess
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
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: SimpleNamespace(
        returncode=0, stdout=states[int(command[2].rsplit("/", 1)[1])] + "\n"))
    assert script.fetch_open_among({1, 2, 3}, "o/r") == 2
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: SimpleNamespace(returncode=1, stdout=""))
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


README_FIXTURE = """| Metric | Count |
|--------|------:|
| GitHub Stars | 53 |
| External Contributors | 54 |
| Forks | 64 |
| Watching | 8 |
| Combined Social Reach (Instagram + LinkedIn) | 30K+ |
"""
ROADMAP_FIXTURE = """| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits | Explainers | CI |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 53 | 55 | 64 | 8 | 30K+ | 20 | 7 | 114 | ok |
"""
METRICS_FIXTURE = """![Stars](https://img.shields.io/badge/Stars-53-brightgreen?style=flat-square)
![Contributors](https://img.shields.io/badge/Contributors-55-blue?style=flat-square)
![Forks](https://img.shields.io/badge/Forks-64-orange?style=flat-square)
![Watching](https://img.shields.io/badge/Watching-8-yellow?style=flat-square)
![Countries](https://img.shields.io/badge/Countries-20-informational?style=flat-square)

""" + METRICS + """
## Targets

| Metric | Current | Target | Timeline |
|--------|--------:|-------:|----------|
| Stars | 53 | 50+ | End of 2026 |
| Forks | 64 | 75+ | End of 2026 |
| Watching | 8 | 12+ | End of 2026 |
| Contributors | 55 | 20+ | End of 2026 |
| Social reach | 30K+ | 40K+ | End of 2026 |
| Issues closed | 55 (this week, since 2026-10-19) | Track weekly | Ongoing |
"""


def _site(tmp_path):
    (tmp_path / "README.md").write_text(README_FIXTURE, encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text(ROADMAP_FIXTURE, encoding="utf-8")
    (tmp_path / "METRICS.md").write_text(METRICS_FIXTURE, encoding="utf-8")
    return tmp_path


def test_apply_updates_every_place_and_leaves_check_traction_live_passing(tmp_path, capsys):
    # #1252
    site = _site(tmp_path)
    data = tmp_path / "live.json"
    data.write_text(json.dumps(LIVE), encoding="utf-8")
    assert script.main(["--file", str(site / "METRICS.md"), "--date", "2026-11-03", "--live-data", str(data), "--apply"]) == 0
    assert "updated: README.md, ROADMAP.md, METRICS.md" in capsys.readouterr().err

    assert "| GitHub Stars | 54 |" in (site / "README.md").read_text(encoding="utf-8")
    assert "| External Contributors | 57 |" in (site / "README.md").read_text(encoding="utf-8")
    assert "| 54 | 58 | 67 | 8 | 30K+ | 20 | 7 | 114 | ok |" in (site / "ROADMAP.md").read_text(encoding="utf-8")
    metrics = (site / "METRICS.md").read_text(encoding="utf-8")
    assert "badge/Stars-54-" in metrics and "badge/Contributors-58-" in metrics and "badge/Countries-20-" in metrics
    assert "| Forks | 67 | 75+ |" in metrics and "| Social reach | 30K+ |" in metrics
    assert metrics.index("| 2026-W45 |") > metrics.index("| 2026-W43 |")

    observations = traction.collect(site)[0]
    assert traction.live_differences(observations, LIVE) == []


def test_apply_changes_nothing_when_a_cell_cannot_be_found(tmp_path):
    site = _site(tmp_path)
    (site / "README.md").write_text(README_FIXTURE.replace("| Forks | 64 |\n", ""), encoding="utf-8")
    before = {name: (site / name).read_text(encoding="utf-8") for name in ("README.md", "ROADMAP.md", "METRICS.md")}
    with pytest.raises(ValueError, match="README Forks row"):
        script.apply_figures(site, LIVE, "| 2026-W45 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 12 | 7 total |")
    assert {name: (site / name).read_text(encoding="utf-8") for name in before} == before


def test_draft_note_lists_the_closed_issues_figure_moves_and_people():
    # #1262
    note = script.draft_note(
        "2026-W45", datetime.date(2026, 11, 2), script.latest_row(METRICS), LIVE,
        [{"number": 12, "title": "Second thing"}, {"number": 7, "title": "First thing"}],
        ["bob: 2 merged PR(s) after the snapshot (#101, #102); count to update", "    #101 fix: a thing",
         "newbie: 1 merged PR(s) after the snapshot (#103); no entry yet"])
    assert note.startswith("> **2026-W45 - DRAFT, 2 issue(s) closed since 2026-11-02:** First thing (#7); Second thing (#12).")
    assert "stars `53 → 54`, forks `64 → 67`, watching unchanged at 8, contributors `55 → 58`" in note
    assert note.endswith("Merged after the CONTRIBUTORS.md snapshot: @bob, @newbie.")


def test_draft_note_with_nothing_closed_or_pending_says_so():
    note = script.draft_note("2026-W45", datetime.date(2026, 11, 2), script.latest_row(METRICS),
                             {"stars": 53, "forks": 64, "watching": 8, "contributors": 55}, [], [])
    assert "0 issue(s) closed" in note and "none yet" in note and "Merged after" not in note


def test_main_note_prints_the_row_then_the_draft_from_saved_data(tmp_path, capsys):
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    data = tmp_path / "live.json"
    data.write_text(json.dumps({**LIVE, "closed_issues": [{"number": 7, "title": "First thing"}],
                                "pending": ["bob: 1 merged PR(s) after the snapshot (#9); count to update"]}), encoding="utf-8")
    assert script.main(["--file", str(metrics), "--date", "2026-11-03", "--live-data", str(data), "--note"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("| 2026-W45 |") and out[1] == "" and "First thing (#7)" in out[2] and "@bob" in out[2]


def test_apply_rewrites_the_targets_issues_closed_row_from_the_new_weekly_row(tmp_path):
    # #1273: the row said 55 (since 2026-10-19) while the newest weekly row said something else
    site = _site(tmp_path)
    script.main(["--file", str(site / "METRICS.md"), "--date", "2026-11-04", "--live-data", _live_file(tmp_path), "--apply"])
    metrics = (site / "METRICS.md").read_text(encoding="utf-8")
    assert "| Issues closed | 12 (this week, since 2026-11-02) | Track weekly | Ongoing |" in metrics
    assert "| 2026-W45 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 12 | 7 total |" in metrics


def test_apply_includes_pending_closes_in_the_targets_row(tmp_path):
    site = _site(tmp_path)
    data = tmp_path / "live2.json"
    data.write_text(json.dumps({**LIVE, "pending_closes": 4}), encoding="utf-8")
    script.main(["--file", str(site / "METRICS.md"), "--date", "2026-11-04", "--live-data", str(data), "--apply"])
    assert "| Issues closed | 16 (this week, since 2026-11-02) |" in (site / "METRICS.md").read_text(encoding="utf-8")


def _live_file(tmp_path):
    path = tmp_path / "live.json"
    path.write_text(json.dumps(LIVE), encoding="utf-8")
    return str(path)


def test_a_row_for_the_current_week_is_refused_unless_update_is_given_and_vice_versa():
    # #1286
    previous = script.latest_row(METRICS)
    with pytest.raises(ValueError, match=r"already for 2026-W43 \(use --update"):
        script.build_row(previous, LIVE, datetime.date(2026, 10, 22))
    with pytest.raises(ValueError, match="not 2026-W45: drop --update"):
        script.build_row(previous, LIVE, datetime.date(2026, 11, 3), update=True)
    row = script.build_row(previous, LIVE, datetime.date(2026, 10, 22), update=True)
    assert row == "| 2026-W43 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 12 | 7 total |"      # hand-written cells kept


def test_apply_with_update_rewrites_the_newest_row_in_place(tmp_path, capsys):
    site = _site(tmp_path)
    assert script.main(["--file", str(site / "METRICS.md"), "--date", "2026-10-22", "--live-data", _live_file(tmp_path),
                        "--update", "--apply"]) == 0
    metrics = (site / "METRICS.md").read_text(encoding="utf-8")
    assert metrics.count("| 2026-W43 |") == 1 and "| 2026-W43 | 54 | 67 | 8 | 58 | 30K+ total | 20 | 12 | 7 total |" in metrics
    assert "| 2026-W42 | 51 | 58 | 8 | 53 |" in metrics                         # the earlier week is untouched
    assert "| Issues closed | 12 (this week, since 2026-10-19) |" in metrics
    assert "badge/Stars-54-" in metrics


def test_update_note_compares_with_the_week_before_the_refreshed_one(tmp_path, capsys):
    metrics = tmp_path / "METRICS.md"
    metrics.write_text(METRICS, encoding="utf-8")
    data = tmp_path / "live.json"
    data.write_text(json.dumps({**LIVE, "closed_issues": [], "pending": []}), encoding="utf-8")
    assert script.main(["--file", str(metrics), "--date", "2026-10-22", "--live-data", str(data), "--update", "--note"]) == 0
    assert "stars `51 → 54`" in capsys.readouterr().out                          # W42 had 51 stars; W43 is being refreshed


def test_latest_row_can_look_back_and_complains_when_there_is_nothing_there():
    assert script.latest_row(METRICS, back=1)[0] == "2026-W42"
    with pytest.raises(ValueError, match="no weekly row 2 before"):
        script.latest_row(METRICS, back=2)
