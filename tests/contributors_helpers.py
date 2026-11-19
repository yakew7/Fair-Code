"""Shared documents, pull request data and runners for the tests of scripts/check_contributors.py (#1327).

The tests are split by module: test_contributors_entries.py (parsing and the checks), test_contributors_fix.py (--fix and the
snapshot line), test_contributors_stub.py (--stub) and test_contributors_cli.py (the GitHub wrappers and the command line).
"""
import importlib
import json  # noqa: F401 - used by the shared helpers below
import re  # noqa: F401

import pytest  # noqa: F401

script = importlib.import_module("scripts.check_contributors")

DOC = """# Contributors

**Snapshot:** 2026-10-24, covering everything merged through **PR #100**.

## Maintainer

Someone.

## Core contributors

### [@alice](https://github.com/alice)

**3 merged PRs · 5 commits · first merged 2026-05-01**

Text.

## Contributors

### Bob Builder - [@bob](https://github.com/bob)

**2 merged PRs · 4 commits · first merged 2026-06-01**

### Carol - [@carol](https://github.com/carol)

**2 merged PRs · 3 commits · first merged 2026-06-02**

### Old Timer - `ghost-user` (account deleted)

**1 merged PR · 2 commits · first merged 2026-05-19**
"""


def pr(number, login, day, bot=False):
    return {"number": number, "author": {"login": login, "is_bot": bot}, "mergedAt": f"{day}T10:00:00Z"}


PRS = [pr(1, "alice", "2026-05-01"), pr(2, "alice", "2026-05-02"), pr(3, "alice", "2026-05-03"),
       pr(4, "bob", "2026-06-01"), pr(5, "bob", "2026-06-05"), pr(6, "carol", "2026-06-02"),
       pr(7, "carol", "2026-06-09"), pr(8, "app/", "2026-05-19", bot=True),
       pr(9, "yakew7", "2026-05-20"), pr(10, "app/dependabot", "2026-05-21", bot=True)]


def run(tmp_path, capsys, doc=DOC, prs=PRS, extra=()):
    (tmp_path / "CONTRIBUTORS.md").write_text(doc, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = script.main(["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json"), *extra])
    return code, capsys.readouterr().out


COMMITS = {"live": {"alice": 6, "Bob": 5, "carol": 3}, "after_snapshot": {"alice": 1, "Bob": 1}}


IDENTITY_DOC = DOC + """
## Git identity map

| GitHub handle | Git author name(s) recorded in history |
|---------------|----------------------------------------|
| [@alice](https://github.com/alice) | `Alice A.`, `alice@example.org` |
| [@bob](https://github.com/bob) | `bob` |
"""


AREA_DOC = DOC + """
## Contributions by area

| Area | Contributors |
|------|--------------|
| **Audits** | [@alice](https://github.com/alice), [@Bob](https://github.com/bob) |
"""


STUB_DOC = AREA_DOC.replace("\n## Contributions by area", "\n---\n\n## Contributions by area").replace("[@Bob](https://github.com/bob) |", "[@Bob](https://github.com/bob), [@carol](https://github.com/carol) |") + """
| **Contributor tooling & docs** | [@alice](https://github.com/alice) |

---
"""


AREA_DOC_TABLE = STUB_DOC.replace("| **Audits** |", "| **Profiler - web** | [@alice](https://github.com/alice) |\n| **Tests** | [@bob](https://github.com/bob) |\n| **Audits** |")


def _stub_site(tmp_path):
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "dave", "2026-10-31"), title="docs: b")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    return ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]


def _replace_the_todo(path):
    """Replace the whole `TODO:` line of a stub with a real sentence, as the person writing the entry would."""
    path.write_text(re.sub(r"^TODO:.*$", "Fixed a thing.", path.read_text(encoding="utf-8"), flags=re.MULTILINE), encoding="utf-8")


def _two_newcomers(tmp_path):
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a"), dict(pr(120, "erin", "2026-10-31"), title="docs: b"),
                 dict(pr(121, "erin", "2026-11-01"), title="docs: c")]
    (tmp_path / "CONTRIBUTORS.md").write_text(STUB_DOC, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    return ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]
