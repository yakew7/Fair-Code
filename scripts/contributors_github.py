"""What check_contributors.py asks GitHub and git (#1319): merged PRs, commit counts and commit authors.

Split out of scripts/check_contributors.py. Every `gh` call goes through ghcall.run_gh and so has a timeout.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
import subprocess
from pathlib import Path

if __package__:                         # imported as scripts.<name> or run as a script (see ghcall's import for why)
    from .ghcall import run_gh
else:
    from ghcall import run_gh

ROOT = Path(__file__).resolve().parent.parent

TRAILER = re.compile(r"^(?P<name>.+?)\s*<(?P<email>[^<>]+)>\s*$")


def fetch_commit_data(entries: list[dict], since: str, repo: str = "yakew7/Fair-Code") -> dict | None:
    """{"live": {login: commits}, "after_snapshot": {login: commits since `since`}} from gh api, or None on failure."""
    if shutil.which("gh") is None:
        return None

    def api(*args: str):
        done = run_gh(["gh", "api", *args])
        return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None

    people = api("--paginate", "--slurp", f"repos/{repo}/contributors?per_page=100")
    if people is None:
        return None
    live = {p["login"]: p["contributions"] for page in people for p in page if p.get("type") != "Bot"}
    logins = [e["handle"] for e in entries if not e["deleted"] and e["handle"].lower() in {k.lower() for k in live}]

    def since_count(login: str) -> int | None:
        done = run_gh(["gh", "api", "--paginate", f"repos/{repo}/commits?author={login}&since={since}&per_page=100",
                       "--jq", ".[].sha"])
        return len(done.stdout.split()) if done.returncode == 0 else None

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        counts = list(pool.map(since_count, logins))
    if any(count is None for count in counts):
        return None
    after = dict(zip(logins, counts))
    return {"live": live, "after_snapshot": after}


def fetch_commit_authors(numbers: list[int], repo: str = "yakew7/Fair-Code") -> dict[int, list[str]] | None:
    """{PR number: logins of the authors of its commits} from gh, or None when any call fails (#1316)."""
    if shutil.which("gh") is None:
        return None

    def one(number: int) -> list[str] | None:
        done = run_gh(["gh", "pr", "view", str(number), "--repo", repo, "--json", "commits",
                       "--jq", "[.commits[].authors[].login] | unique"])
        try:
            return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None
        except json.JSONDecodeError:
            return None

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        found = list(pool.map(one, numbers))
    return None if any(authors is None for authors in found) else dict(zip(numbers, found))


def snapshot_time(prs: list[dict], through: int | None) -> str | None:
    """One second after the snapshot PR was merged, so its own merge commit is not counted as 'after'."""
    from datetime import datetime, timedelta, timezone
    merged = next((pr.get("mergedAt") for pr in prs if pr["number"] == through), None)
    if not merged:
        return None
    moment = datetime.strptime(merged, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(seconds=1)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_prs() -> list[dict] | None:
    if shutil.which("gh") is None:
        return None
    done = run_gh(["gh", "pr", "list", "--state", "merged", "--limit", "5000",
                   "--json", "number,author,mergedAt,title,body"])
    return json.loads(done.stdout) if done.returncode == 0 else None


def git_authors(runner=None) -> list[tuple[str, str, int]]:
    """Distinct (name, email, commits) over the whole history: every commit's author, plus each `Co-authored-by:` trailer
    (#1269), so a person credited only through a trailer is checked like an author."""
    run = runner or subprocess.run
    counts: dict[tuple[str, str], int] = {}
    done = run(["git", "log", "--format=%an|%ae"], cwd=ROOT, capture_output=True, text=True)
    for line in done.stdout.splitlines():
        name, _, email = line.partition("|")
        counts[(name, email)] = counts.get((name, email), 0) + 1
    trailers = run(["git", "log", "--format=%(trailers:key=Co-authored-by,valueonly)"], cwd=ROOT, capture_output=True, text=True)
    for line in trailers.stdout.splitlines():
        found = TRAILER.match(line.strip())
        if found:
            key = (found.group("name"), found.group("email"))
            counts[key] = counts.get(key, 0) + 1
    return sorted(((n, e, c) for (n, e), c in counts.items()), key=lambda item: (-item[2], item[0]))
