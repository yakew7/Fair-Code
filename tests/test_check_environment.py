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
