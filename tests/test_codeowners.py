"""Validate that every path pattern in .github/CODEOWNERS still matches a
file or directory actually tracked in the repo (#207) - the same spirit as
tests/test_manifest.py's row_filters validation (#168), applied to the
review-routing config instead of an audit manifest.

Run from the repo root:  pytest tests/test_codeowners.py -q
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS_PATH = REPO_ROOT / ".github" / "CODEOWNERS"


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _split_codeowners_line(line):
    """Split one line into (pattern, owners), honoring GitHub's
    backslash-escaped-space syntax in the pattern (needed for a path like
    /AI\\ Fair\\ Recruitment/ - see #379). Owner handles never contain
    spaces, so a naive whitespace split breaks the pattern into multiple
    tokens wherever it has an escaped space; this reassembles it."""
    tokens = line.split()
    pattern = tokens[0]
    i = 1
    while pattern.endswith("\\") and i < len(tokens):
        pattern = pattern[:-1] + " " + tokens[i]
        i += 1
    return pattern, tokens[i:]


def _parse_codeowners_paths():
    """Return [(line_no, pattern, owners)] for every non-comment, non-blank line."""
    entries = []
    for line_no, raw in enumerate(CODEOWNERS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, owners = _split_codeowners_line(line)
        entries.append((line_no, pattern, owners))
    return entries


def _pattern_matches_a_tracked_path(pattern, tracked):
    """Mirror gitignore-style CODEOWNERS matching closely enough to validate
    the small set of pattern shapes this repo actually uses: an anchored
    file (/a/b.ext), an anchored directory (/a/b/), and a **/name glob."""
    if pattern.startswith("**/"):
        name = pattern[len("**/"):]
        return any(Path(t).name == name for t in tracked)

    anchored = pattern.lstrip("/")
    if pattern.endswith("/"):
        prefix = anchored.rstrip("/") + "/"
        return any(t.startswith(prefix) for t in tracked)

    return anchored in tracked


def test_codeowners_file_exists():
    assert CODEOWNERS_PATH.is_file(), ".github/CODEOWNERS is missing"


def test_split_codeowners_line_handles_escaped_spaces():
    pattern, owners = _split_codeowners_line(r"/AI\ Fair\ Recruitment/ @yakew7 @ahmdkaml")
    assert pattern == "/AI Fair Recruitment/"
    assert owners == ["@yakew7", "@ahmdkaml"]


def test_audit_directories_are_covered_by_a_codeowners_entry():
    # #379: every audit dataset directory (fair.py/unfair.py/CSVs/notebooks -
    # everything besides audit.yaml, which **/audit.yaml already covers) had
    # no owner at all until this test's own entries were added.
    audit_dirs = [
        "AI Fair Recruitment", "Benefits Denial", "COMPAS",
        "German Credit Lending", "Healthcare Readmission",
        "Insurance Denial", "Tenant Screening",
    ]
    tracked = _tracked_files()
    entries = _parse_codeowners_paths()
    patterns = [pattern for _line_no, pattern, _owners in entries]

    for audit_dir in audit_dirs:
        files = [t for t in tracked if t.startswith(audit_dir + "/") and not t.endswith("/audit.yaml")]
        assert files, f"no tracked non-manifest files found under {audit_dir!r}"
        assert any(_pattern_matches_a_tracked_path(p, [files[0]]) for p in patterns), (
            f"{audit_dir!r} has tracked files with no matching CODEOWNERS entry"
        )


def test_every_codeowners_path_matches_a_tracked_file_or_directory():
    tracked = _tracked_files()
    entries = _parse_codeowners_paths()
    assert entries, "no path entries found in .github/CODEOWNERS"

    stale = [
        f"{CODEOWNERS_PATH.relative_to(REPO_ROOT)}:{line_no}: pattern {pattern!r} "
        f"matches no tracked file or directory"
        for line_no, pattern, _owners in entries
        if not _pattern_matches_a_tracked_path(pattern, tracked)
    ]
    assert not stale, "Stale CODEOWNERS entries:\n" + "\n".join(stale)


def test_every_codeowners_entry_names_at_least_one_owner():
    entries = _parse_codeowners_paths()

    missing_owners = [
        f".github/CODEOWNERS:{line_no}: {pattern!r} has no owner listed"
        for line_no, pattern, owners in entries
        if not owners
    ]
    assert not missing_owners, "\n".join(missing_owners)


def test_every_tracked_file_has_at_least_one_codeowners_owner():
    # #585: the two existing coverage tests only check one direction each -
    # every audit directory is covered (test_audit_directories_are_covered_...)
    # and every pattern still matches something real
    # (test_every_codeowners_path_matches_a_tracked_file_or_directory). Neither
    # catches a directory/file that was simply never added to CODEOWNERS at
    # all - the exact gap that let notebooks/, results/, assets/icons/, and
    # several .github/ files sit unowned indefinitely (#581-#584) with this
    # suite green the whole time.
    tracked = _tracked_files()
    entries = _parse_codeowners_paths()
    patterns = [pattern for _line_no, pattern, _owners in entries]

    unowned = [
        t for t in tracked
        if not any(_pattern_matches_a_tracked_path(p, [t]) for p in patterns)
    ]
    assert not unowned, (
        "Tracked file(s) with no matching CODEOWNERS entry:\n" + "\n".join(unowned)
    )


def test_every_codeowners_owner_is_a_valid_github_handle():
    handle_re = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
    entries = _parse_codeowners_paths()

    bad = [
        f".github/CODEOWNERS:{line_no}: {pattern!r} has a malformed owner {owner!r}"
        for line_no, pattern, owners in entries
        for owner in owners
        if not handle_re.match(owner)
    ]
    assert not bad, "\n".join(bad)
