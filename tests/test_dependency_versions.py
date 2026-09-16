from pathlib import Path
import re


def test_requirements_lock_versions_satisfy_pyproject_minimums():
    root = Path(__file__).resolve().parents[1]

    pyproject = root / "pyproject.toml"
    requirements_lock = root / "requirements-lock.txt"

    assert pyproject.is_file(), f"Could not find {pyproject}"
    assert requirements_lock.is_file(), f"Could not find {requirements_lock}"

    pyproject_text = pyproject.read_text(encoding="utf-8")
    lock_text = requirements_lock.read_text(encoding="utf-8")

    pyproject_versions = {
        normalize_dependency(name): minimum
        for name, minimum in re.findall(
            r'([A-Za-z0-9_.-]+)\s*>=\s*([0-9]+(?:\.[0-9]+)*)',
            pyproject_text,
        )
    }

    locked_versions = {
        normalize_dependency(name): version
        for name, version in re.findall(
            r'^([A-Za-z0-9_.-]+)==([0-9]+(?:\.[0-9]+)*)',
            lock_text,
            re.MULTILINE,
        )
    }

    for dependency, minimum in pyproject_versions.items():
        locked = locked_versions.get(dependency)

        if locked is None:
            continue

        assert version_tuple(locked) >= version_tuple(minimum), (
            f"{dependency} is locked to {locked}, "
            f"but pyproject.toml requires >= {minimum}"
        )


def version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def normalize_dependency(name):
    return name.lower().replace("-", "_").replace(".", "_")
