"""Sorting and refreshing CONTRIBUTORS.md with --fix and the snapshot line (#1327)."""
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
)


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
