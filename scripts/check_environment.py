#!/usr/bin/env python3
"""Warn when a package installed next to Fair Code's dependencies shadows a standard library module (#1247).

An old `pathlib.py` backport in site-packages shadowed the standard library whenever site-packages was on `PYTHONPATH`
(which ranks ahead of it), and the failure surfaced as an unrelated `ImportError` on `collections` in a CLI test (#1239).
Nothing told the contributor their environment had such a file. This lists every top-level module or package in the
interpreter's site directories whose name is a standard library module name (`sys.stdlib_module_names`), with the
distribution that owns it, and says how to remove it:

    python3 scripts/check_environment.py          # also: make doctor

Exit code: 0 = nothing shadows the standard library, 1 = at least one module does.
"""
from __future__ import annotations

import importlib.metadata
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
    shadows = shadowing_modules(site_directories())
    if not shadows:
        print("OK: nothing in site-packages shadows a standard library module.")
        return 0
    print("These installed modules shadow the standard library and can break imports when site-packages is on PYTHONPATH:")
    for name, path in shadows:
        owner = owner_of(name)
        remedy = f"python3 -m pip uninstall {owner}" if owner else f"delete {path}"
        print(f"  - {name}: {path} (fix: {remedy})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
