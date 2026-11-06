"""Every third-party package the codebase actually imports must be declared
in pyproject.toml (core `dependencies` or an `[project.optional-dependencies]`
extra) - otherwise `pip install faircode[...]` can leave a package missing
that faircode/scripts/tests import directly, and CI only finds out when a
test happens to hit that import. This is what caught Pillow being absent
from pyproject.toml while tests imported PIL (#235).

This does not require every import to sit behind a specific extra - just
that it's declared *somewhere* in pyproject.toml, since that's what
`pip install -e ".[extra1,extra2,...]"` draws from.

Run from the repo root:  pytest tests/ -q
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["faircode", "scripts", "tests"]

# Import root -> PyPI distribution name, for the handful of packages whose
# import name doesn't match the name they're declared under in pyproject.toml.
IMPORT_TO_DIST = {
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
}

# Imports that are intentionally not a faircode dependency: "faircode" is the
# package importing itself, and pytest is a dev-only test-runner tool
# installed separately (see Makefile's `make setup`), not a runtime dependency.
NOT_A_PYPROJECT_DEPENDENCY = {"faircode", "pytest"}
# Helper modules that live in tests/ itself (e.g. js_helpers.py) are local, not dependencies; they
# are importable because pyproject.toml puts tests/ on pytest's pythonpath (#938, #945).
TESTS_LOCAL_MODULES = {path.stem for path in (ROOT / "tests").glob("*.py")}
# The scripts/ modules import each other both as `scripts.<name>` (imported by tests) and as bare `<name>` (run as a
# script, when scripts/ is sys.path[0]); neither is a third-party package.
TESTS_LOCAL_MODULES |= {"scripts"} | {path.stem for path in (ROOT / "scripts").glob("*.py")}


def _normalize(name):
    return name.lower().replace("_", "-")


def _declared_dependencies(pyproject_text):
    return {
        _normalize(name)
        for name in re.findall(r'"([A-Za-z][A-Za-z0-9_.-]*)\s*[><=!~]', pyproject_text)
    }


def _stdlib_modules():
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib:
        return set(stdlib)
    # Python < 3.10 fallback: no sys.stdlib_module_names, so list the stdlib
    # modules this repo actually imports by hand.
    return {
        "__future__", "argparse", "csv", "dataclasses", "html", "importlib",
        "itertools", "json", "math", "pathlib", "re", "shutil", "subprocess",
        "sys", "textwrap", "urllib", "xml",
    }


def _imported_third_party_modules():
    stdlib = _stdlib_modules()
    found = {}  # dist name -> (import root, first file it's imported in)
    for scan_dir in SCAN_DIRS:
        for path in sorted((ROOT / scan_dir).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        roots.add(node.module.split(".")[0])
            for root in roots:
                if root in stdlib or root in NOT_A_PYPROJECT_DEPENDENCY or root in TESTS_LOCAL_MODULES:
                    continue
                dist = IMPORT_TO_DIST.get(root, root)
                found.setdefault(dist, (root, path.relative_to(ROOT)))
    return found


def test_every_imported_third_party_package_is_declared_in_pyproject():
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = _declared_dependencies(pyproject_text)

    missing = [
        f"{root!r} imported in {path} -> expected {dist!r} declared in pyproject.toml"
        for dist, (root, path) in sorted(_imported_third_party_modules().items())
        if _normalize(dist) not in declared
    ]

    assert not missing, (
        "The following imports have no matching dependency in pyproject.toml's "
        "core `dependencies` or any `[project.optional-dependencies]` extra:\n  "
        + "\n  ".join(missing)
    )


def test_pytest_pythonpath_makes_the_shared_test_helpers_importable_in_every_import_mode():
    # #945: js_helpers is imported by bare name, which needs tests/ (and the repo root, for
    # `scripts.*`) on pytest's pythonpath rather than relying on the default prepend mode.
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'pythonpath\s*=\s*\[[^\]]*"tests"[^\]]*\]', text)
    assert re.search(r'pythonpath\s*=\s*\[[^\]]*"\."[^\]]*\]', text)
    assert (ROOT / "tests" / "js_helpers.py").is_file()
