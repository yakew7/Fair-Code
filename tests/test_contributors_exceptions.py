"""The real scripts/contributors-exceptions.json agrees with CONTRIBUTORS.md (#1365)."""

from contributors_helpers import script


def _entries():
    return {e["handle"].lower() for e in script.parse((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))[0]}


def test_every_commit_exception_is_a_person_who_has_an_entry():
    # an exception for a login with no entry would excuse nothing, and a missing one makes `--commits` fail (#1365)
    commit_exceptions, _ = script.load_exceptions()
    assert set(commit_exceptions) <= _entries(), sorted(set(commit_exceptions) - _entries())


def test_the_account_whose_commit_email_is_not_linked_is_excused_with_the_reason():
    commit_exceptions, _ = script.load_exceptions()
    reason = commit_exceptions["nitishchauhan002"]
    assert "2b2366d" in reason and "not linked" in reason and "#410" in reason


def test_an_excused_account_is_skipped_by_the_commit_comparison_and_an_unexcused_one_is_reported():
    entries, _ = script.parse((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    live = {e["handle"]: e["commits"] for e in entries if e["handle"].lower() != "nitishchauhan002"}
    problems, skipped = script.commit_problems([e for e in entries if e["handle"].lower() in {"nitishchauhan002"}], live, {})
    assert problems == [] and any("nitishchauhan002" in note for note in skipped)
    problems, _ = script._commit_problems([e for e in entries if e["handle"].lower() == "nitishchauhan002"], live, {}, {})
    assert any("nitishchauhan002" in problem and "not in the contributors API" in problem for problem in problems)
