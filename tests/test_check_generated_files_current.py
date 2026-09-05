"""Tests for scripts/check_generated_files_current.py.

main() operates on the real repo ROOT/TEXT_GLOBS/DATA_JSON by design (it's a
CI gate, not a library function), so these tests monkeypatch those module
globals to point at an isolated tmp_path tree and fake out the `git`
subprocess calls, rather than standing up a real git repository - the
behavior under test is the comparison/flagging logic itself, not git.
"""

import importlib
import json

from PIL import Image


def _script():
    return importlib.import_module("scripts.check_generated_files_current")


def _fake_run(ls_files_output, show_returncode=0, show_stdout=""):
    def run(cmd, cwd=None, capture_output=True, text=True, check=False):
        import types
        if cmd[:2] == ["git", "ls-files"]:
            return types.SimpleNamespace(returncode=0, stdout=ls_files_output)
        if cmd[:2] == ["git", "show"]:
            return types.SimpleNamespace(returncode=show_returncode, stdout=show_stdout)
        raise AssertionError(f"unexpected subprocess call: {cmd}")
    return run


def _empty_repo(tmp_path, monkeypatch, script):
    """Points ROOT/DATA_JSON at an empty tmp_path tree with no text globs and
    no explainers, so only what a test explicitly adds is checked."""
    (tmp_path / "assets").mkdir()
    data_json = tmp_path / "assets" / "explainers-data.json"
    data_json.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "DATA_JSON", data_json)
    monkeypatch.setattr(script, "TEXT_GLOBS", [])


def test_text_globs_covers_the_results_frozen_mcp_mirror():
    # faircode/_results_frozen/*.csv (closes #394) - without this, nothing
    # ever notices if paper/results-frozen/*.csv is edited directly and the
    # MCP get_benchmark_results tool's package-internal mirror silently
    # drifts out of sync.
    script = _script()
    assert "faircode/_results_frozen/*.csv" in script.TEXT_GLOBS


def test_normalize_dates_strips_jsonld_dates_and_lastmod():
    script = _script()
    text = (
        '{\n'
        '  "foo": "bar",\n'
        '  "datePublished": "2026-01-01",\n'
        '  "dateModified": "2026-01-02"\n'
        '}\n'
        '<lastmod>2026-01-01</lastmod>\n'
    )
    normalized = script._normalize_dates(text)
    assert "datePublished" not in normalized
    assert "dateModified" not in normalized
    assert "<lastmod>" not in normalized
    assert '"foo": "bar"' in normalized


def test_main_flags_a_stale_text_file(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["sitemap.xml"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    (tmp_path / "sitemap.xml").write_text("fresh content\n", encoding="utf-8")
    monkeypatch.setattr(
        script.subprocess, "run",
        _fake_run("sitemap.xml\n", show_returncode=0, show_stdout="stale committed content\n"))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sitemap.xml: content differs from a fresh regeneration" in captured.out


def test_main_passes_when_text_file_matches_head(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["sitemap.xml"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    (tmp_path / "sitemap.xml").write_text("same content\n", encoding="utf-8")
    monkeypatch.setattr(
        script.subprocess, "run",
        _fake_run("sitemap.xml\n", show_returncode=0, show_stdout="same content\n"))

    exit_code = script.main()

    assert exit_code == 0
    assert "up to date" in capsys.readouterr().out


def test_main_flags_a_file_not_yet_committed(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["sitemap.xml"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    (tmp_path / "sitemap.xml").write_text("brand new file\n", encoding="utf-8")
    monkeypatch.setattr(
        script.subprocess, "run",
        _fake_run("sitemap.xml\n", show_returncode=1, show_stdout=""))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sitemap.xml: not yet committed" in captured.out


def test_main_flags_a_missing_og_image(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "DATA_JSON", tmp_path / "assets" / "explainers-data.json")
    (tmp_path / "assets" / "explainers-data.json").write_text(
        json.dumps([{"slug": "example"}]), encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "assets/og/example.png: missing" in captured.out
    assert "assets/og-light/example.png: missing" in captured.out


def test_main_flags_an_og_image_with_wrong_dimensions(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "DATA_JSON", tmp_path / "assets" / "explainers-data.json")
    (tmp_path / "assets" / "explainers-data.json").write_text(
        json.dumps([{"slug": "example"}]), encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))

    for theme_dir in ("assets/og", "assets/og-light"):
        (tmp_path / theme_dir).mkdir(parents=True)
        for slug in ("home", "profiler", "example"):
            path = tmp_path / theme_dir / f"{slug}.png"
            Image.new("RGB", (100, 100)).save(path)  # wrong size on purpose

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "wrong dimensions: (100, 100), expected (1200, 630)" in captured.out


def test_main_passes_with_correctly_sized_og_images(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "DATA_JSON", tmp_path / "assets" / "explainers-data.json")
    (tmp_path / "assets" / "explainers-data.json").write_text(
        json.dumps([{"slug": "example"}]), encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))

    for theme_dir in ("assets/og", "assets/og-light"):
        (tmp_path / theme_dir).mkdir(parents=True)
        for slug in ("home", "profiler", "example"):
            path = tmp_path / theme_dir / f"{slug}.png"
            Image.new("RGB", script.OG_DIMENSIONS).save(path)

    exit_code = script.main()

    assert exit_code == 0
    assert "up to date" in capsys.readouterr().out
