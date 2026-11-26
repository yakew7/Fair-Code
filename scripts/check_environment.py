#!/usr/bin/env python3
"""Warn when a package installed next to Fair Code's dependencies shadows a standard library module (#1247).

An old `pathlib.py` backport in site-packages shadowed the standard library whenever site-packages was on `PYTHONPATH`
(which ranks ahead of it), and the failure surfaced as an unrelated `ImportError` on `collections` in a CLI test (#1239).
Nothing told the contributor their environment had such a file. This lists every top-level module or package in the
interpreter's site directories whose name is a standard library module name (`sys.stdlib_module_names`), with the
distribution that owns it, and says how to remove it. It also looks in the directories named by `PYTHONPATH` and in the
current directory, which shadow the standard library the same way (a stray `random.py` next to the script being run), and
says which of these a module was found in:

    python3 scripts/check_environment.py          # also: make doctor
    python3 scripts/check_environment.py --warn-only   # same report, exit 0 (make check DOCTOR=warn)

It also warns, without ever changing the exit code, when a package of the `test` extra in pyproject.toml is not installed (#1346, #1357). Without pytest-xdist
`make test-fast` runs in one process, and without pytest-timeout a hung test is never stopped and pytest warns about the `timeout`
option in pyproject.toml; any other missing package makes the tests that import it fail. The fix it prints is `python3 -m pip install -e ".[test]"`.

Exit code: 0 = nothing shadows the standard library (or --warn-only), 1 = at least one module does.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import site
import sys
import sysconfig
from pathlib import Path


def site_directories() -> list[Path]:
    """The interpreter's purelib, platlib and user site directories that exist."""
    paths = {sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]}
    try:
        paths.add(site.getusersitepackages())
    except AttributeError:
        pass
    return sorted(Path(p) for p in paths if Path(p).is_dir())


def search_directories(environ=None, cwd: Path | None = None) -> list[tuple[Path, str]]:
    """(directory, where it comes from) for the site directories, the `PYTHONPATH` entries and the working directory (#1267);
    a directory that is listed twice is reported under its first origin."""
    env = os.environ if environ is None else environ
    found: dict[Path, str] = {}
    for path in site_directories():
        found.setdefault(path.resolve(), "site-packages")
    for entry in filter(None, env.get("PYTHONPATH", "").split(os.pathsep)):
        if Path(entry).is_dir():
            found.setdefault(Path(entry).resolve(), "PYTHONPATH")
    here = (cwd or Path.cwd()).resolve()
    found.setdefault(here, "the current directory")
    return list(found.items())


def shadowing_modules(directories: list[Path], stdlib: frozenset[str] | set[str] | None = None) -> list[tuple[str, Path]]:
    """(module name, path) for each top-level `name.py` or `name/` package in `directories` whose name is a standard
    library module. Compiled and namespace-less leftovers (`__pycache__`, `*.dist-info`) are not modules and are skipped."""
    stdlib = set(sys.stdlib_module_names) if stdlib is None else set(stdlib)
    found = []
    for directory in directories:
        for entry in sorted(directory.iterdir()):
            if entry.is_dir():
                name = entry.name
                if not (entry / "__init__.py").is_file():
                    continue
            elif entry.suffix == ".py":
                name = entry.stem
            else:
                continue
            if name in stdlib:
                found.append((name, entry))
    return found


def owner_of(name: str) -> str | None:
    """The distribution that provides top-level module `name`, when the metadata says so."""
    try:
        owners = importlib.metadata.packages_distributions().get(name)
    except Exception:  # noqa: BLE001 - a broken metadata directory must not hide the warning itself
        return None
    return owners[0] if owners else None


ROOT = Path(__file__).resolve().parent.parent
# What is missing without the two plugins whose absence changes how `make` behaves (#1346); any other package of the extra gets
# the generic sentence below.
CONSEQUENCES = {
    "pytest-xdist": "make test-fast and make coverage run in one process instead of on every core",
    "pytest-timeout": "a hung test is never stopped, and pytest warns about the `timeout` option",
}
GENERIC_CONSEQUENCE = "the tests that import it fail with an ImportError"


def declared_test_extra(pyproject: Path | None = None) -> list[str]:
    """The distributions of the `test` extra in pyproject.toml, version specifiers dropped (#1357), so the check follows the extra
    instead of a list kept here. Reads the `test = [...]` line directly because Python 3.10 has no tomllib."""
    text = (pyproject or ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r"^test\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not found:
        return []
    return [re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", item).group(0) for item in re.findall(r'"([^"]+)"', found.group(1))]


def missing_test_packages(declared: list[str] | None = None, version=None) -> list[tuple[str, str]]:
    """(distribution, consequence) for each package of the `test` extra that is not installed. `version` is
    importlib.metadata.version by default (a PackageNotFoundError means missing); it also handles names like PyYAML and the
    difference between a distribution and its import name."""
    version = version or importlib.metadata.version
    missing = []
    for dist in declared_test_extra() if declared is None else declared:
        try:
            version(dist)
        except importlib.metadata.PackageNotFoundError:
            missing.append((dist, CONSEQUENCES.get(dist.lower(), GENERIC_CONSEQUENCE)))
    return missing


def warn_about_test_plugins() -> None:
    missing = missing_test_packages()
    for dist, effect in missing:
        print(f"warning: {dist} is not installed: {effect}.")
    if missing:
        print('  fix: python3 -m pip install -e ".[test]"   (a warning only; it does not change the exit code)')


def main(argv: list[str] | None = None) -> int:
    code = check_shadowing(argv)
    warn_about_test_plugins()
    return code


def check_shadowing(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--warn-only", action="store_true",
                        help="print the report but exit 0, for a machine with a shadowing module that cannot be removed (#1290)")
    args = parser.parse_args(argv or [])
    origins = dict(search_directories())
    shadows = shadowing_modules(list(origins))
    if not shadows:
        print("OK: nothing in site-packages, PYTHONPATH or the current directory shadows a standard library module.")
        return 0
    print("These modules shadow the standard library and can break imports (PYTHONPATH and the current directory rank "
          "ahead of it):")
    for name, path in shadows:
        origin = origins.get(path.parent.resolve(), "an import path")
        owner = owner_of(name) if origin == "site-packages" else None
        remedy = f"python3 -m pip uninstall {owner}" if owner else f"delete or rename {path}"
        print(f"  - {name}: {path} (in {origin}; fix: {remedy})")
    if args.warn_only:
        print("warn-only: continuing anyway.")
        return 0
    print("To go on without fixing it: make check DOCTOR=warn (or run this script with --warn-only).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
