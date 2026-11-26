"""scripts/check_environment.py names installed modules that shadow the standard library (#1247)."""
import importlib
import os
import sys

script = importlib.import_module("scripts.check_environment")


def _site(tmp_path):
    (tmp_path / "pathlib.py").write_text("# the old backport\n")
    (tmp_path / "enum").mkdir()
    (tmp_path / "enum" / "__init__.py").write_text("")
    (tmp_path / "numpy").mkdir()
    (tmp_path / "numpy" / "__init__.py").write_text("")
    (tmp_path / "pandas.py").write_text("")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "pathlib-1.0.dist-info").mkdir()
    (tmp_path / "typing.pyc").write_bytes(b"")
    (tmp_path / "collections").mkdir()                 # a folder with no __init__.py is not a regular package
    return tmp_path


def test_a_backport_module_and_a_package_with_a_stdlib_name_are_found(tmp_path):
    found = script.shadowing_modules([_site(tmp_path)])
    assert [name for name, _ in found] == ["enum", "pathlib"]
    assert dict(found)["pathlib"] == tmp_path / "pathlib.py"


def test_ordinary_packages_metadata_and_bytecode_are_not_reported(tmp_path):
    assert script.shadowing_modules([_site(tmp_path)], stdlib={"numpy", "pandas"}) == [
        ("numpy", tmp_path / "numpy"), ("pandas", tmp_path / "pandas.py")]


def test_main_reports_the_module_with_its_owner_and_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "search_directories", lambda: [(_site(tmp_path), "site-packages")])
    monkeypatch.setattr(script, "owner_of", lambda name: "pathlib" if name == "pathlib" else None)
    assert script.main() == 1
    out = capsys.readouterr().out
    assert "pathlib" in out and "fix: python3 -m pip uninstall pathlib" in out
    assert "enum" in out and "fix: delete" in out


def test_main_passes_on_a_clean_environment(tmp_path, monkeypatch, capsys):
    (tmp_path / "numpy").mkdir()
    (tmp_path / "numpy" / "__init__.py").write_text("")
    monkeypatch.setattr(script, "search_directories", lambda: [(tmp_path, "site-packages")])
    assert script.main() == 0
    assert "OK:" in capsys.readouterr().out


def test_site_directories_exist_and_the_real_interpreter_has_a_stdlib_name_set():
    assert all(path.is_dir() for path in script.site_directories())
    assert "pathlib" in sys.stdlib_module_names


def test_search_directories_adds_pythonpath_entries_and_the_working_directory(tmp_path, monkeypatch):
    # #1267
    monkeypatch.setattr(script, "site_directories", lambda: [tmp_path / "site"])
    (tmp_path / "site").mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    found = dict(script.search_directories(environ={"PYTHONPATH": os.pathsep.join([str(extra), str(tmp_path / "nope"), ""])}, cwd=work))
    assert found == {(tmp_path / "site").resolve(): "site-packages", extra.resolve(): "PYTHONPATH",
                     work.resolve(): "the current directory"}


def test_a_directory_listed_twice_keeps_its_first_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "site_directories", lambda: [tmp_path])
    found = dict(script.search_directories(environ={"PYTHONPATH": str(tmp_path)}, cwd=tmp_path))
    assert found == {tmp_path.resolve(): "site-packages"}


def test_main_names_a_shadowing_module_in_pythonpath_and_the_current_directory(tmp_path, monkeypatch, capsys):
    extra, work = tmp_path / "extra", tmp_path / "work"
    extra.mkdir()
    work.mkdir()
    (extra / "enum.py").write_text("")
    (work / "random.py").write_text("")
    monkeypatch.setattr(script, "site_directories", lambda: [])
    monkeypatch.setenv("PYTHONPATH", str(extra))
    monkeypatch.chdir(work)
    assert script.main() == 1
    out = capsys.readouterr().out
    assert "enum" in out and "in PYTHONPATH" in out and "random" in out and "in the current directory" in out
    assert "delete or rename" in out


def test_warn_only_prints_the_report_but_exits_0_and_the_default_says_how_to_continue(tmp_path, monkeypatch, capsys):
    # #1290
    site = _site(tmp_path)
    monkeypatch.setattr(script, "search_directories", lambda: [(site, "site-packages")])
    monkeypatch.setattr(script, "owner_of", lambda name: None)
    assert script.main() == 1
    assert "make check DOCTOR=warn" in capsys.readouterr().out
    assert script.main(["--warn-only"]) == 0
    out = capsys.readouterr().out
    assert "pathlib" in out and "warn-only: continuing anyway." in out and "make check DOCTOR=warn" not in out


def test_warn_only_is_quiet_about_options_on_a_clean_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "search_directories", lambda: [(tmp_path, "site-packages")])
    assert script.main(["--warn-only"]) == 0 and "OK:" in capsys.readouterr().out


def _installed(*names):
    """A stand-in for importlib.metadata.version that knows only `names`."""
    def version(dist):
        if dist not in names:
            raise script.importlib.metadata.PackageNotFoundError(dist)
        return "1.0"
    return version


def test_missing_test_packages_names_each_one_of_the_extra_that_is_not_installed():
    # #1346, #1357: make test-fast silently ran in one process, and the timeout setting only produced a pytest warning
    declared = ["pytest", "pytest-xdist", "pytest-timeout", "certifi"]
    assert script.missing_test_packages(declared, _installed(*declared)) == []
    missing = dict(script.missing_test_packages(declared, _installed("pytest", "pytest-timeout")))
    assert list(missing) == ["pytest-xdist", "certifi"]
    assert "every core" in missing["pytest-xdist"] and missing["certifi"] == script.GENERIC_CONSEQUENCE
    assert "hung test is never stopped" in dict(script.missing_test_packages(["pytest-timeout"], _installed()))["pytest-timeout"]


def test_the_check_reads_the_packages_from_the_test_extra_in_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project.optional-dependencies]\nbrowser = ["playwright>=1.40"]\n'
                         'test = ["pytest>=8.0", "pytest-xdist>=3.5",\n        "Some_New.Plugin==2.0; python_version>\'3.9\'"]   # note\n', encoding="utf-8")
    assert script.declared_test_extra(pyproject) == ["pytest", "pytest-xdist", "Some_New.Plugin"]
    (tmp_path / "empty.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert script.declared_test_extra(tmp_path / "empty.toml") == []


def test_the_real_extra_is_read_and_a_package_added_to_it_is_reported(monkeypatch):
    declared = script.declared_test_extra()
    assert {"pytest", "pytest-xdist", "pytest-timeout", "pytest-cov", "certifi", "pyyaml"} <= {name.lower() for name in declared}
    monkeypatch.setattr(script, "declared_test_extra", lambda: [*declared, "brand-new-test-tool"])
    assert ("brand-new-test-tool", script.GENERIC_CONSEQUENCE) in script.missing_test_packages(version=_installed(*declared))


def test_main_warns_about_missing_packages_with_the_fix_and_keeps_the_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "search_directories", lambda: [(tmp_path, "site-packages")])
    monkeypatch.setattr(script.importlib.metadata, "version", _installed())
    assert script.main() == 0                                          # a clean environment still passes
    out = capsys.readouterr().out
    assert "OK:" in out and "warning: pytest-xdist is not installed" in out and "warning: pytest-timeout is not installed" in out
    assert "warning: pyyaml is not installed: the tests that import it fail with an ImportError." in out     # a package of the extra, not a plugin
    assert 'pip install -e ".[test]"' in out
    (tmp_path / "shadow").mkdir()
    site = _site(tmp_path / "shadow")
    monkeypatch.setattr(script, "search_directories", lambda: [(site, "site-packages")])
    monkeypatch.setattr(script, "owner_of", lambda name: None)
    assert script.main() == 1 and "warning: pytest-xdist" in capsys.readouterr().out      # and a shadowing module still fails
    assert script.main(["--warn-only"]) == 0


def test_main_is_quiet_about_packages_when_all_are_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "search_directories", lambda: [(tmp_path, "site-packages")])
    monkeypatch.setattr(script.importlib.metadata, "version", lambda dist: "1.0")
    assert script.main() == 0
    assert "warning:" not in capsys.readouterr().out
