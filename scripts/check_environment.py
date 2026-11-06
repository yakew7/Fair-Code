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

Exit code: 0 = nothing shadows the standard library, 1 = at least one module does.
"""
from __future__ import annotations

import importlib.metadata
import os
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


def main() -> int:
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
