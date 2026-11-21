"""Which Contributions by area row --stub lists a new person in: --area, the rules in contributors-areas.json and their checks (#1294, #1333, #1335, #1327)."""
import json

import pytest

from contributors_helpers import (  # noqa: F401
    script,
    DOC,
    pr,
    PRS,
    run,
    STUB_DOC,
    AREA_DOC_TABLE,
    _stub_site,
    _two_newcomers,
)


def test_one_stub_run_can_start_several_entries_in_rule_order(tmp_path, capsys):
    # #1299
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave", "erin"]) == 0
    assert "stub entries for dave, erin" in capsys.readouterr().out
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    handles = [e["handle"] for e in script.parse(text)[0]]
    assert handles.index("erin") < handles.index("dave")                 # erin has 2 PRs, dave 1
    assert "covering everything merged through **PR #121**" in text
    assert text.count("TODO:") == 2
    assert text.count("[@dave](https://github.com/dave)") == 2 and text.count("[@erin](https://github.com/erin)") == 2   # header + area row


def test_area_names_lists_the_rows_of_the_area_table():
    # #1294
    assert script.area_names(STUB_DOC) == ["Audits", "Contributor tooling & docs"]
    assert script.area_names(DOC) == []
    real = script.area_names((script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"))
    assert script.DEFAULT_AREA in real and "Audits" in real and "Area" not in real and len(real) >= 8


def test_stub_area_lists_the_new_person_in_the_chosen_row_only(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave", "--area", "audits"]) == 0          # the match ignores case
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip(" *"): line for line in text.splitlines() if line.startswith("| **")}
    assert "[@dave](https://github.com/dave)" in rows["Audits"]
    assert "[@dave]" not in rows["Contributor tooling & docs"]


def test_stub_area_defaults_to_the_tooling_and_docs_row(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    text = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    tooling = next(line for line in text.splitlines() if line.startswith("| **Contributor tooling & docs**"))
    assert "[@dave](https://github.com/dave)" in tooling


def test_an_unknown_stub_area_is_an_error_naming_the_real_ones_and_writes_nothing(tmp_path, capsys):
    base = _stub_site(tmp_path)
    before = (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.main(base + ["--stub", "dave", "--area", "Nope"]) == 1
    out = capsys.readouterr().out
    assert "unknown area 'Nope'" in out and "Audits; Contributor tooling & docs" in out
    assert (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8") == before


def test_one_area_applies_to_every_login_of_a_stub_run(tmp_path, capsys):
    base = _two_newcomers(tmp_path)
    assert script.main(base + ["--stub", "dave", "erin", "--area", "Audits"]) == 0
    audits = next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines() if line.startswith("| **Audits**"))
    assert "[@dave]" in audits and "[@erin]" in audits


def test_suggest_area_picks_the_row_holding_most_of_the_changed_files():
    # #1333
    names = script.area_names(AREA_DOC_TABLE)
    prs = [dict(pr(1, "dave", "2026-11-01"), files=["assets/profiler-ui.js", "assets/profiler-engine.js", "tests/test_x.py"]),
           dict(pr(2, "dave", "2026-11-02"), files=["profiler.html"]),
           dict(pr(3, "erin", "2026-11-02"), files=["tests/test_y.py"])]
    assert script.suggest_area("dave", prs, names) == ("Profiler - web", 3)
    assert script.suggest_area("erin", prs, names) == ("Tests", 1)
    assert script.suggest_area("nobody", prs, names) is None
    assert script.suggest_area("dave", [pr(1, "dave", "2026-11-01")], names) is None            # no files in the data
    assert script.suggest_area("dave", [dict(pr(1, "dave", "2026-11-01"), files=["README.md"])], names) is None
    tie = [dict(pr(1, "dave", "2026-11-01"), files=["tests/a.py", "assets/profiler-ui.js"])]
    assert script.suggest_area("dave", tie, names)[0] == "Profiler - web"                      # ties go to the earlier rule


def test_rules_naming_a_row_the_table_does_not_have_are_ignored():
    assert script.suggest_area("dave", [dict(pr(1, "dave", "2026-11-01"), files=["tests/a.py"])], ["Audits"]) is None


def test_a_stub_without_area_uses_the_suggestion_and_says_so_and_area_still_overrides(tmp_path, capsys):
    (tmp_path / "CONTRIBUTORS.md").write_text(AREA_DOC_TABLE, encoding="utf-8")
    prs = PRS + [dict(pr(110, "dave", "2026-10-30"), title="fix: a", files=["assets/profiler-ui.js"])]
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    base = ["--file", str(tmp_path / "CONTRIBUTORS.md"), "--prs", str(tmp_path / "prs.json")]
    assert script.main(base + ["--stub", "dave"]) == 0
    out = capsys.readouterr().out
    assert "area chosen from the changed files (use --area NAME to override): dave: Profiler - web (1 changed file(s))" in out
    rows = {line.split("|")[1].strip(" *"): line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
            if line.startswith("| **")}
    assert "[@dave]" in rows["Profiler - web"] and "[@dave]" not in rows["Contributor tooling & docs"]

    (tmp_path / "CONTRIBUTORS.md").write_text(AREA_DOC_TABLE, encoding="utf-8")
    assert script.main(base + ["--stub", "dave", "--area", "Tests"]) == 0
    assert "area chosen" not in capsys.readouterr().out
    assert "[@dave]" in next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
                             if line.startswith("| **Tests**"))


def test_a_stub_without_files_in_the_data_keeps_the_default_area(tmp_path, capsys):
    base = _stub_site(tmp_path)
    assert script.main(base + ["--stub", "dave"]) == 0
    assert "area chosen" not in capsys.readouterr().out
    tooling = next(line for line in (tmp_path / "CONTRIBUTORS.md").read_text(encoding="utf-8").splitlines()
                   if line.startswith("| **Contributor tooling & docs**"))
    assert "[@dave]" in tooling


def test_the_committed_area_rules_load_in_priority_order_and_name_real_rows():
    # #1335: the rules live in scripts/contributors-areas.json, not in Python
    rules = script.load_area_rules()
    assert len(rules) >= 15 and rules[0] == ("assets/profiler-", "Profiler - web")
    assert script.AREA_RULES == rules
    real = (script.ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert script.area_rule_problems(real) == []


def test_editing_the_json_changes_the_suggestion_without_touching_python(tmp_path):
    names = script.area_names(AREA_DOC_TABLE)
    prs = [dict(pr(1, "dave", "2026-11-01"), files=["tests/test_x.py", "docs/guide.md"])]
    assert script.suggest_area("dave", prs, names) == ("Tests", 1)
    rules = tmp_path / "areas.json"
    rules.write_text(json.dumps({"rules": [{"match": "docs/", "area": "Audits"}, {"match": "tests/", "area": "Tests"}]}))
    assert script.suggest_area("dave", prs, names, rules=script.load_area_rules(rules)) == ("Audits", 1)


def test_load_area_rules_rejects_a_malformed_file_and_tolerates_a_missing_one(tmp_path):
    assert script.load_area_rules(tmp_path / "missing.json") == []
    for bad in ({"rules": "nope"}, {"rules": [{"match": "x/"}]}, {"rules": [{"match": "", "area": "A"}]}, {"rules": ["x"]}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            script.load_area_rules(path)


def test_a_rule_naming_a_row_the_table_does_not_have_is_reported():
    problems = script.area_rule_problems(AREA_DOC_TABLE, rules=[("tests/", "Tests"), ("docs/", "Documentation")])
    assert problems == ["contributors-areas.json: the rule for 'docs/' names the area 'Documentation', "
                        "which is not a row of the Contributions by area table"]
    assert script.area_rule_problems(DOC, rules=[("docs/", "Documentation")]) == []        # no table, nothing to check


def test_the_plain_check_validates_the_rules_only_for_the_repositorys_own_file(tmp_path, capsys, monkeypatch):
    # the toy documents of the other tests have two or three rows; the rules describe the real table
    from scripts import contributors_write
    monkeypatch.setattr(contributors_write, "AREA_RULES", [("x/", "No such row")])
    code, out = run(tmp_path, capsys, doc=STUB_DOC)
    assert "contributors-areas.json" not in out
