"""The Makefile's targets say what the documentation says they do."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dry_run(target: str) -> str:
    return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def test_test_fast_leaves_the_browser_tests_to_make_test_browser():
    # #1263: with Playwright installed `pytest tests/` also collected tests/browser (1,476 tests instead of 1,464)
    recipe = dry_run("test-fast")
    assert 'pytest tests/ -q -m "not slow"' in recipe and "--ignore=tests/browser" in recipe
    assert "tests/browser" in dry_run("test-browser")


def test_check_runs_the_environment_doctor_before_anything_that_could_fail_because_of_it():
    # #1268: a stdlib-shadowing module in site-packages makes tests fail with an unrelated ImportError
    recipe = dry_run("check")
    assert "scripts/check_environment.py" in recipe
    assert recipe.index("check_environment.py") < recipe.index("check_em_dash.py")


def test_every_described_makefile_target_is_documented_in_contributing():
    # #1275: `make key-fold-check` was the one target a contributor could not find; `help` is the only exception
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    targets = re.findall(r"^([a-zA-Z_-]+):.*?## ", makefile, re.MULTILINE)
    assert "key-fold-check" in targets and len(targets) > 10
    missing = [t for t in targets if t != "help" and not re.search(rf"make {re.escape(t)}(?![\w-])", contributing)]
    assert missing == [], f"add these to CONTRIBUTING.md: {missing}"


def test_every_script_make_lint_runs_has_a_pre_commit_hook():
    # #1276: a commit could pass the hooks and still fail `make lint`
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("\nlint:", 1)[1].split("\naudits:", 1)[0]
    scripts = re.findall(r"\$\(PY\) (scripts/\w+\.py)", recipe)
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert len(scripts) >= 8
    missing = [script for script in scripts if f"entry: python3 {script}" not in hooks]
    assert missing == [], f"add a pre-commit hook for: {missing}"


def test_the_new_hooks_run_only_for_the_files_their_checks_read():
    import yaml
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    for name, touched, untouched in (
        ("check-issue-refs", "ROADMAP.md", "README.md"),
        ("check-traction", "METRICS.md", "CHANGELOG.md"),
        ("check-dataset-sources", "COMPAS/fair.py", "ROADMAP.md"),
        ("check-contributors", "scripts/contributors-exceptions.json", "METRICS.md"),
    ):
        pattern = re.compile(hooks[name]["files"])
        assert pattern.search(touched) and not pattern.search(untouched), name
        assert hooks[name]["pass_filenames"] is False
