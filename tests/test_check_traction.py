"""scripts/check_traction.py keeps the traction figures in step across README, ROADMAP and METRICS (#1097)."""
import subprocess
import importlib
from pathlib import Path

check = importlib.import_module("scripts.check_traction")

README = """| Metric | Count |
|--------|------:|
| GitHub Stars | 51 |
| External Contributors | 53 |
| Forks | 63 |
| Watching | 8 |
| Combined Social Reach (Instagram + LinkedIn) | 30K+ |
| Countries Reached (Website Visitors) | 20 |
| Code Audits Published | 7 |

<details>
<summary><strong>Show 2 completed items</strong></summary>

- [x] One
- [x] Two
- [ ] Not done

</details>
"""
ROADMAP = """| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits | Explainers | CI |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 51 | 54 | 63 | 8 | 30K+ | 20 | 7 | 82 | ok |
"""
METRICS = """![Stars](https://img.shields.io/badge/Stars-51-brightgreen?style=flat-square)
![Contributors](https://img.shields.io/badge/Contributors-54-blue?style=flat-square)
![Forks](https://img.shields.io/badge/Forks-63-orange?style=flat-square)
![Watching](https://img.shields.io/badge/Watching-8-yellow?style=flat-square)
![Countries](https://img.shields.io/badge/Countries-20-informational?style=flat-square)

| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |
|------|------:|------:|---------:|-------------:|-------------:|----------:|--------------:|------------:|
| 2026-W42 | 50 | 58 | 8 | 53 | 30K+ total | 20 | 123 | 7 total |
| 2026-W43 | 51 | 63 | 8 | 54 | 30K+ total | 20 | 28 | 7 total |
"""


def _site(root: Path, readme=README, roadmap=ROADMAP, metrics=METRICS) -> Path:
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "ROADMAP.md").write_text(roadmap, encoding="utf-8")
    (root / "METRICS.md").write_text(metrics, encoding="utf-8")
    return root


def test_matching_figures_pass(tmp_path):
    assert check.check(_site(tmp_path)) == []


def test_a_changed_traction_figure_names_every_place_that_disagrees(tmp_path):
    problems = check.check(_site(tmp_path, roadmap=ROADMAP.replace("| 63 |", "| 58 |")))
    assert len(problems) == 1
    assert problems[0].startswith("forks disagree")
    assert "ROADMAP.md" in problems[0] and "says 58" in problems[0]
    assert "README.md (Forks) says 63" in problems[0] and "METRICS.md (badge Forks) says 63" in problems[0]


def test_only_the_newest_weekly_row_is_compared(tmp_path):
    # W42 says 50 stars; that is history, not a disagreement.
    assert check.check(_site(tmp_path)) == []
    stale = METRICS.replace("| 2026-W43 | 51 |", "| 2026-W43 | 52 |")
    assert any(p.startswith("stars disagree") and "W43" in p for p in check.check(_site(tmp_path, metrics=stale)))


def test_each_weekly_figure_reports_a_metrics_disagreement(tmp_path):
    latest = "| 2026-W43 | 51 | 63 | 8 | 54 | 30K+ total | 20 | 28 | 7 total |"
    cases = (
        (1, "stars", "52"),
        (2, "forks", "64"),
        (3, "watching", "9"),
        (4, "contributors", "55"),
        (5, "social", "31K+ total"),
        (6, "countries", "21"),
        (8, "audits", "8"),
    )

    for column, figure, value in cases:
        cells = latest.strip("|").split("|")
        cells[column] = f" {value} "
        metrics = METRICS.replace(latest, "|" + "|".join(cells) + "|")
        problems = check.check(_site(tmp_path, metrics=metrics))

        assert any(
            problem.startswith(f"{figure} disagree")
            and "METRICS.md (latest weekly row, 2026-W43)" in problem
            for problem in problems
        ), figure


def test_readme_external_contributors_is_expected_one_below_the_total(tmp_path):
    assert check.check(_site(tmp_path)) == []
    problems = check.check(_site(tmp_path, readme=README.replace("| 53 |", "| 54 |")))
    assert any(p.startswith("contributors disagree") for p in problems)


def test_social_reach_text_is_compared_too(tmp_path):
    problems = check.check(_site(tmp_path, readme=README.replace("30K+", "27K+")))
    assert any(p.startswith("social disagree") for p in problems)


def test_completed_item_count_must_match_the_checked_lines(tmp_path):
    assert check.completed_items(README) == (2, 2)
    problems = check.check(_site(tmp_path, readme=README.replace("Show 2", "Show 3")))
    assert problems == ["README.md: 'Show 3 completed items' but the section has 2 '- [x]' lines"]


def test_missing_rows_are_reported_not_ignored(tmp_path):
    problems = check.check(_site(tmp_path, roadmap="no table here\n"))
    assert "ROADMAP.md: no 'Current traction' table found" in problems


def test_the_real_repo_agrees():
    assert check.check() == []


def test_readme_missing_traction_row_is_reported():
    text = README.replace("| GitHub Stars | 51 |\n", "")

    observations, problems = check.readme_observations(text)

    assert not any(figure == "stars" for figure, _, _ in observations)
    assert problems == ["README.md: no Traction table row for 'GitHub Stars'"]


def test_roadmap_header_without_a_data_row_is_reported():
    text = check.ROADMAP_HEADER + "\n|---|---|---|---|---|---|---|\n"

    assert check.roadmap_observations(text) == (
        [],
        ["ROADMAP.md: no 'Current traction' table found"],
    )


def test_metrics_missing_badges_and_weekly_rows_are_reported():
    observations, problems = check.metrics_observations("no metrics here\n")

    assert observations == []
    assert problems == [
        "METRICS.md: no Stars badge",
        "METRICS.md: no Contributors badge",
        "METRICS.md: no Forks badge",
        "METRICS.md: no Watching badge",
        "METRICS.md: no Countries badge",
        "METRICS.md: no weekly row found",
    ]


def test_weekly_row_skips_empty_and_dash_cells():
    incomplete = METRICS.replace(
        "| 2026-W43 | 51 | 63 | 8 | 54 | 30K+ total | 20 | 28 | 7 total |",
        "| 2026-W43 | 51 | - |  | 54 | 30K+ total | 20 | 28 | 7 total |",
    )
    observations, problems = check.metrics_observations(incomplete)

    assert problems == []
    weekly = [item for item in observations if "latest weekly row" in item[1]]
    assert {figure for figure, _, _ in weekly} == {
        "stars",
        "contributors",
        "social",
        "countries",
        "issues_closed",
        "audits",
    }


def test_truncated_weekly_row_keeps_available_figures():
    text = "| 2026-W43 | 51 |\n"

    observations, problems = check.metrics_observations(text)

    assert problems == [
        "METRICS.md: no Stars badge",
        "METRICS.md: no Contributors badge",
        "METRICS.md: no Forks badge",
        "METRICS.md: no Watching badge",
        "METRICS.md: no Countries badge",
    ]
    assert observations == [("stars", "METRICS.md (latest weekly row, 2026-W43)", "51")]


def test_completed_items_counts_until_end_of_file_without_details_closer():
    text = "Show 2 completed items\n- [x] One\n- [x] Two\n"

    assert check.completed_items(text) == (2, 2)


def test_check_reports_missing_completed_items_summary(tmp_path):
    problems = check.check(
        _site(tmp_path, readme="README without a completed-items section")
    )

    assert "README.md: no 'Show N completed items' summary found" in problems


def test_main_reports_success_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(check, "check", lambda: [])
    assert check.main() == 0
    assert "Traction figures agree" in capsys.readouterr().out

    monkeypatch.setattr(check, "check", lambda: ["stars disagree"])
    assert check.main() == 1
    assert "stars disagree" in capsys.readouterr().err


def test_script_entry_point_exits_with_the_checker_result(monkeypatch):
    import runpy

    monkeypatch.setattr("sys.argv", ["check_traction.py"])

    try:
        runpy.run_path(str(Path(check.__file__)), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("script entry point did not exit")


LIVE = {"stars": 51, "forks": 63, "watching": 8, "contributors": 54, "issues_closed": 28}


def _observations(tmp_path, **overrides):
    return check.collect(_site(tmp_path, **overrides))[0]


def test_live_figures_that_match_report_nothing(tmp_path):
    assert check.live_differences(_observations(tmp_path), LIVE) == []


def test_live_names_every_place_that_differs_from_github(tmp_path):
    # the files agree with each other (51 stars everywhere) and are still one behind GitHub (#1148)
    messages = check.live_differences(_observations(tmp_path), {**LIVE, "stars": 53})
    assert messages and all(m.startswith("stars: ") and m.endswith("GitHub says 53") for m in messages)
    assert any("README.md (GitHub Stars) says 51" in m for m in messages)
    assert any("ROADMAP.md" in m for m in messages) and any("METRICS.md (badge Stars)" in m for m in messages)
    assert any("latest weekly row, 2026-W43" in m for m in messages)


def test_live_ignores_figures_github_cannot_supply(tmp_path):
    messages = check.live_differences(_observations(tmp_path), {"stars": 51})
    assert messages == []
    assert check.live_differences([("social", "README.md", "30K+")], {"social": 1}) == []


def test_live_reports_a_weekly_issues_closed_mismatch(tmp_path):
    messages = check.live_differences(_observations(tmp_path), {**LIVE, "issues_closed": 29})

    assert messages == [
        "issues_closed: METRICS.md (latest weekly row, 2026-W43) says 28, GitHub says 29"
    ]


def test_latest_metrics_iso_week_uses_monday_sunday_and_crosses_year_boundaries():
    assert check.latest_metrics_week(METRICS) == "2026-W43"
    assert check.iso_week_bounds("2026-W43") == ("2026-10-19", "2026-10-25")
    assert check.iso_week_bounds("2026-W01") == ("2025-12-29", "2026-01-04")
    assert check.iso_week_bounds("2020-W53") == ("2020-12-28", "2021-01-03")


def test_iso_week_bounds_rejects_malformed_or_nonexistent_weeks():
    import pytest

    for week in ("2026-W1", "2026-W54", "not-a-week"):
        with pytest.raises(ValueError, match="not a valid ISO year-week"):
            check.iso_week_bounds(week)


def test_fetch_live_queries_issue_only_count_for_the_week_and_fails_on_incomplete_results(monkeypatch):
    import json
    from types import SimpleNamespace

    monkeypatch.setattr(check.shutil, "which", lambda command: "/usr/bin/gh")
    calls = []
    replies = [
        {"stargazers_count": 51, "forks_count": 63, "subscribers_count": 8},
        [[{"login": "person"}, {"login": "helper[bot]", "type": "Bot"}]],
        {"total_count": 28, "incomplete_results": False, "items": []},
    ]

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(replies[len(calls) - 1]))

    monkeypatch.setattr(subprocess, "run", run)
    live = check.fetch_live(week_bounds=("2026-10-19", "2026-10-25"))

    assert live == {"stars": 51, "forks": 63, "watching": 8, "contributors": 1, "issues_closed": 28}
    assert calls[2] == [
        "gh", "api", "--method", "GET", "search/issues", "-f",
        "q=repo:yakew7/Fair-Code is:issue is:closed closed:2026-10-19..2026-10-25",
    ]

    replies[2] = {"total_count": 28, "incomplete_results": True, "items": []}
    calls.clear()
    assert check.fetch_live(week_bounds=("2026-10-19", "2026-10-25")) is None

    replies[2] = []
    calls.clear()
    assert check.fetch_live(week_bounds=("2026-10-19", "2026-10-25")) is None


def test_main_live_data_fails_on_a_stale_figure_and_passes_when_current(tmp_path, monkeypatch, capsys):
    import json
    _site(tmp_path)
    original_check, original_collect = check.check, check.collect
    monkeypatch.setattr(check, "check", lambda root=tmp_path: original_check(root))
    monkeypatch.setattr(check, "collect", lambda root=tmp_path: original_collect(root))
    live = tmp_path / "live.json"

    live.write_text(json.dumps(LIVE), encoding="utf-8")
    assert check.main(["--live-data", str(live)]) == 0
    assert "and with GitHub." in capsys.readouterr().out

    live.write_text(json.dumps({**LIVE, "issues_closed": 29}), encoding="utf-8")
    assert check.main(["--live-data", str(live)]) == 1
    assert "issues_closed: METRICS.md (latest weekly row, 2026-W43) says 28, GitHub says 29" in capsys.readouterr().err

    legacy_live = {key: value for key, value in LIVE.items() if key != "issues_closed"}
    live.write_text(json.dumps(legacy_live), encoding="utf-8")
    assert check.main(["--live-data", str(live)]) == 2
    assert "must include an integer issues_closed count" in capsys.readouterr().err

    live.write_text(json.dumps({**LIVE, "stars": 52}), encoding="utf-8")
    assert check.main(["--live-data", str(live)]) == 1
    assert "stars: README.md (GitHub Stars) says 51, GitHub says 52" in capsys.readouterr().err


def test_live_without_gh_is_an_error_not_a_pass(monkeypatch, capsys):
    monkeypatch.setattr(check, "fetch_live", lambda repo=check.REPO, week_bounds=None: None)
    assert check.main(["--live"]) == 2
    assert "could not fetch GitHub figures" in capsys.readouterr().err
