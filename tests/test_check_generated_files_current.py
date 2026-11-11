"""Tests for scripts/check_generated_files_current.py.

Most tests point main() at an isolated tmp_path tree and fake out the `git`
subprocess calls. A focused temporary Git repository also exercises the
fresh-build copy and builder failure path end to end.
"""

import importlib
import json
import os
import subprocess
from contextlib import ExitStack

import pytest

from PIL import Image


def _script():
    return importlib.import_module("scripts.check_generated_files_current")


def _fake_run(ls_files_output):
    def run(cmd, cwd=None, capture_output=True, text=True, check=False):
        import types
        if cmd[:2] == ["git", "ls-files"]:
            return types.SimpleNamespace(returncode=0, stdout=ls_files_output)
        raise AssertionError(f"unexpected subprocess call: {cmd}")
    return run


def _fake_fresh_build_dir(tmp_path, files):
    """Monkeypatches script._fresh_build_dir to skip the real git-worktree
    checkout and subprocess build steps entirely, returning a plain
    directory pre-populated with `files` (rel path -> content) instead -
    the fresh-regeneration equivalent of _empty_repo() below, so tests
    still don't need a real git repository."""
    fresh = tmp_path / "_fresh"
    for rel, content in files.items():
        path = fresh / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return lambda stack: fresh


def _empty_repo(tmp_path, monkeypatch, script):
    """Points ROOT/DATA_JSON at an empty tmp_path tree with no text globs and
    no explainers, so only what a test explicitly adds is checked."""
    (tmp_path / "assets").mkdir()
    data_json = tmp_path / "assets" / "explainers-data.json"
    data_json.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "DATA_JSON", data_json)
    monkeypatch.setattr(script, "TEXT_GLOBS", [])


def _git_repo(root, *, failing_builder=False, require_new_assets=False, hanging_builder=None):
    root.mkdir()
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "tracked.txt").write_text("committed content\n", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    # a regular package like the real repo's: without it `from scripts.freeze_paper_results import ...` can resolve
    # to an unrelated `scripts` package installed in site-packages (#1192)
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    if hanging_builder:
        builder = "import time\ntime.sleep(60)\n"
    elif failing_builder:
        builder = "import sys\nprint('builder-specific failure', file=sys.stderr)\nsys.exit(7)\n"
    elif require_new_assets:
        builder = (
            "from pathlib import Path\n"
            "assert Path('explainers/new-explainer.md').is_file()\n"
            "assert Path('assets/og/new-explainer.png').is_file()\n"
            "assert Path('assets/og-light/new-explainer.png').is_file()\n"
        )
    else:
        builder = "pass\n"
    (scripts / "build_explainers.py").write_text("pass\n" if hanging_builder == "generate_og_images.py" else builder, encoding="utf-8")
    (scripts / "generate_og_images.py").write_text(builder if hanging_builder == "generate_og_images.py" else "pass\n", encoding="utf-8")
    (scripts / "freeze_paper_results.py").write_text(
        "def mirror_for_mcp(): pass\ndef mirror_current_for_mcp(): pass\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    env = os.environ | {
        "GIT_AUTHOR_NAME": "Fair-Code tests",
        "GIT_AUTHOR_EMAIL": "tests@example.invalid",
        "GIT_COMMITTER_NAME": "Fair-Code tests",
        "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    }
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "test fixture"],
        cwd=root,
        env=env,
        check=True,
    )
    return root


def test_fresh_build_copies_new_files_but_not_ignored_files_and_keeps_tracked_edits(
    tmp_path, monkeypatch
):
    script = _script()
    root = _git_repo(tmp_path / "repo", require_new_assets=True)
    (root / "tracked.txt").write_text("unstaged edit\n", encoding="utf-8")
    explainer = root / "explainers" / "new-explainer.md"
    explainer.parent.mkdir()
    explainer.write_text("# New explainer\n", encoding="utf-8")
    for theme in ("og", "og-light"):
        image = root / "assets" / theme / "new-explainer.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"new image asset")
    (root / "ignored.txt").write_text("must not be copied\n", encoding="utf-8")
    monkeypatch.setattr(script, "ROOT", root)

    with ExitStack() as stack:
        fresh = script._fresh_build_dir(stack)

        assert (fresh / "tracked.txt").read_text(encoding="utf-8") == "unstaged edit\n"
        assert (fresh / "explainers/new-explainer.md").read_text(encoding="utf-8") == (
            "# New explainer\n"
        )
        assert (
            fresh / "assets/og/new-explainer.png"
        ).read_bytes() == b"new image asset"
        assert (
            fresh / "assets/og-light/new-explainer.png"
        ).read_bytes() == b"new image asset"
        assert not (fresh / "ignored.txt").exists()


def test_fresh_build_prints_builder_stderr_and_preserves_failure_status(
    tmp_path, monkeypatch, capsys
):
    script = _script()
    root = _git_repo(tmp_path / "repo", failing_builder=True)
    monkeypatch.setattr(script, "ROOT", root)

    with ExitStack() as stack, pytest.raises(subprocess.CalledProcessError) as error:
        script._fresh_build_dir(stack)

    assert error.value.returncode == 7
    assert "builder-specific failure" in capsys.readouterr().err


def test_text_globs_covers_the_results_frozen_mcp_mirror():
    # faircode/_results_frozen/*.csv (closes #394) - without this, nothing
    # ever notices if paper/results-frozen/*.csv is edited directly and the
    # MCP get_benchmark_results tool's package-internal mirror silently
    # drifts out of sync.
    script = _script()
    assert "faircode/_results_frozen/*.csv" in script.TEXT_GLOBS


def test_text_globs_cover_the_og_card_input_hashes():
    # #1197: an explainer's title or summary edited without re-rendering its card.
    script = _script()
    assert "assets/og/card-inputs.json" in script.TEXT_GLOBS
    assert "assets/og-light/card-inputs.json" in script.TEXT_GLOBS


def test_main_flags_a_stale_og_card_input_hash(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["assets/og/card-inputs.json"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    stored = tmp_path / "assets" / "og" / "card-inputs.json"
    stored.parent.mkdir(parents=True)
    stored.write_text('{\n  "example": "1111111111111111"\n}\n', encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run("assets/og/card-inputs.json\n"))
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {
        "assets/og/card-inputs.json": '{\n  "example": "2222222222222222"\n}\n',
    }))

    exit_code = script.main()

    assert exit_code == 1
    assert "assets/og/card-inputs.json: content differs from a fresh regeneration" \
        in capsys.readouterr().out


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
    (tmp_path / "sitemap.xml").write_text("stale working-tree content\n", encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run("sitemap.xml\n"))
    monkeypatch.setattr(
        script, "_fresh_build_dir",
        _fake_fresh_build_dir(tmp_path, {"sitemap.xml": "freshly regenerated content\n"}))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sitemap.xml: content differs from a fresh regeneration" in captured.out


def test_main_passes_when_text_file_matches_fresh_regeneration(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["sitemap.xml"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    (tmp_path / "sitemap.xml").write_text("same content\n", encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run("sitemap.xml\n"))
    monkeypatch.setattr(
        script, "_fresh_build_dir",
        _fake_fresh_build_dir(tmp_path, {"sitemap.xml": "same content\n"}))

    exit_code = script.main()

    assert exit_code == 0
    assert "up to date" in capsys.readouterr().out


def test_main_flags_a_file_not_produced_by_a_fresh_regeneration(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["sitemap.xml"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    (tmp_path / "sitemap.xml").write_text("tracked, but the fresh build made nothing here\n",
                                           encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run("sitemap.xml\n"))
    # No "sitemap.xml" key: the fresh regeneration never produced this path.
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "sitemap.xml: not produced by a fresh regeneration" in captured.out


def test_main_catches_an_uncommitted_edit_never_rebuilt(tmp_path, monkeypatch, capsys):
    # Regression test for #502: this script used to diff the working tree
    # against `git show HEAD:<path>`, which only catches "you forgot to
    # stage a file that differs from your last commit" - not "your source
    # and generated output have actually diverged". Editing a source file
    # without rebuilding, before ever committing anything, used to pass.
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", ["explainers/demographic-parity.html"])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: [])
    stale_html = (tmp_path / "explainers" / "demographic-parity.html")
    stale_html.parent.mkdir(parents=True)
    stale_html.write_text("<p>old content, source .md was edited after this was built</p>\n",
                           encoding="utf-8")
    monkeypatch.setattr(
        script.subprocess, "run", _fake_run("explainers/demographic-parity.html\n"))
    # A real _fresh_build_dir would rebuild from the edited .md and produce
    # different HTML; simulate exactly that divergence directly.
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {
        "explainers/demographic-parity.html":
            "<p>new content, reflects the edited .md source</p>\n",
    }))

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "explainers/demographic-parity.html: content differs from a fresh regeneration" \
        in captured.out


def test_main_flags_a_missing_og_image(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "DATA_JSON", tmp_path / "assets" / "explainers-data.json")
    (tmp_path / "assets" / "explainers-data.json").write_text(
        json.dumps([{"slug": "example"}]), encoding="utf-8")
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))

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
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))

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
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))

    for theme_dir in ("assets/og", "assets/og-light"):
        (tmp_path / theme_dir).mkdir(parents=True)
        for slug in ("home", "profiler", "example"):
            path = tmp_path / theme_dir / f"{slug}.png"
            Image.new("RGB", script.OG_DIMENSIONS).save(path)

    exit_code = script.main()

    assert exit_code == 0
    assert "up to date" in capsys.readouterr().out


def test_text_globs_covers_the_results_current_mcp_mirror():
    # faircode/_results_current/*.csv (#1049): the live-results mirror must be as
    # tamper-evident as the frozen one.
    assert "faircode/_results_current/*.csv" in _script().TEXT_GLOBS


def test_tracked_paths_ignores_blank_lines(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.setattr(script, "ROOT", tmp_path)

    def run(cmd, cwd=None, capture_output=True, text=True, check=True):
        import types
        assert cmd == ["git", "ls-files", "example/*"]
        return types.SimpleNamespace(stdout="example/one.txt\n\n  \nexample/two.txt\n")

    monkeypatch.setattr(script.subprocess, "run", run)

    assert script._tracked_paths("example/*") == [
        tmp_path / "example/one.txt",
        tmp_path / "example/two.txt",
    ]


def test_expected_og_slugs_includes_builtin_and_explainer_slugs(tmp_path, monkeypatch):
    script = _script()
    data_json = tmp_path / "explainers-data.json"
    data_json.write_text(
        json.dumps([{"slug": "demographic-parity"}, {"slug": "equal-opportunity"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "DATA_JSON", data_json)

    assert script._expected_og_slugs() == [
        "home",
        "profiler",
        "demographic-parity",
        "equal-opportunity",
    ]


def test_main_flags_empty_og_images(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", [])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: ["empty"])
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))

    for theme_dir in ("assets/og", "assets/og-light"):
        path = tmp_path / theme_dir / "empty.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "assets/og/empty.png: empty file" in captured.out
    assert "assets/og-light/empty.png: empty file" in captured.out


def test_main_flags_undecodable_og_images(tmp_path, monkeypatch, capsys):
    script = _script()
    _empty_repo(tmp_path, monkeypatch, script)
    monkeypatch.setattr(script, "TEXT_GLOBS", [])
    monkeypatch.setattr(script, "_expected_og_slugs", lambda: ["corrupt"])
    monkeypatch.setattr(script, "_fresh_build_dir", _fake_fresh_build_dir(tmp_path, {}))
    monkeypatch.setattr(script.subprocess, "run", _fake_run(""))

    for theme_dir in ("assets/og", "assets/og-light"):
        path = tmp_path / theme_dir / "corrupt.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a PNG")

    exit_code = script.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "assets/og/corrupt.png: could not decode:" in captured.out
    assert "assets/og-light/corrupt.png: could not decode:" in captured.out


@pytest.mark.parametrize("hanging", ["build_explainers.py", "generate_og_images.py"])
def test_a_hung_builder_ends_the_check_with_a_message_naming_it(tmp_path, monkeypatch, capsys, hanging):
    # #1292: the builders used to run with no timeout
    script = _script()
    root = _git_repo(tmp_path / "repo", hanging_builder=hanging)
    monkeypatch.setattr(script, "ROOT", root)
    monkeypatch.setattr(script, "BUILD_TIMEOUT", 1.0)

    assert script.main() == 1

    err = capsys.readouterr().err
    assert f"scripts/{hanging} did not finish within 1 s" in err and "nothing was compared" in err


def test_builder_names_say_which_step_stalled():
    script = _script()
    assert script._builder_name(["python", "scripts/build_explainers.py"]) == "scripts/build_explainers.py"
    assert "MCP results mirror" in script._builder_name(["python", "-c", "from scripts.freeze_paper_results import x"])
    assert str(script.BuilderTimeout("scripts/x.py", 5)) == "scripts/x.py did not finish within 5 s"

def test_build_timeout_uses_environment_variable(monkeypatch):
    script = _script()
    monkeypatch.setenv("FAIRCODE_BUILD_TIMEOUT", "120")

    assert script._get_build_timeout() == 120.0


def test_build_timeout_defaults_to_600(monkeypatch):
    script = _script()
    monkeypatch.delenv("FAIRCODE_BUILD_TIMEOUT", raising=False)

    assert script._get_build_timeout() == 600.0


@pytest.mark.parametrize("value", ["abc", "", "0", "-10"])
def test_build_timeout_invalid_values_fall_back_to_600(
    monkeypatch, value
):
    script = _script()
    monkeypatch.setenv("FAIRCODE_BUILD_TIMEOUT", value)

    assert script._get_build_timeout() == 600.0


@pytest.mark.parametrize("stalled, expected", [
    (["worktree", "add"], "git worktree add did not finish within 1 s"),
    (["ls-files"], "git ls-files did not finish within 1 s"),
    (["ls-files", "--others"], "git ls-files --others did not finish within 1 s"),
])
def test_a_stalled_git_call_ends_the_check_with_a_message_naming_it(tmp_path, monkeypatch, capsys, stalled, expected):
    # #1305: the builders had a timeout (#1292) but the git calls around them did not
    script = _script()
    root = _git_repo(tmp_path / "repo")
    monkeypatch.setattr(script, "ROOT", root)
    monkeypatch.setattr(script, "GIT_TIMEOUT", 1.0)
    real_run = subprocess.run

    def run(command, **kwargs):
        if command[:1] == ["git"] and command[1:1 + len(stalled)] == stalled:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return real_run(command, **kwargs)

    monkeypatch.setattr(script.subprocess, "run", run)
    assert script.main() == 1
    err = capsys.readouterr().err
    assert expected in err and "nothing was compared" in err


def test_every_git_call_of_the_fresh_build_has_a_timeout(tmp_path, monkeypatch):
    script = _script()
    root = _git_repo(tmp_path / "repo")
    monkeypatch.setattr(script, "ROOT", root)
    seen = []
    real_run = subprocess.run

    def run(command, **kwargs):
        if command[:1] == ["git"]:
            seen.append((command[1], kwargs.get("timeout")))
        return real_run(command, **kwargs)

    monkeypatch.setattr(script.subprocess, "run", run)
    with ExitStack() as stack:
        script._fresh_build_dir(stack)
    assert {name for name, _ in seen} >= {"worktree", "ls-files"} and all(t == script.GIT_TIMEOUT for _, t in seen)


def test_a_stalled_worktree_removal_is_reported_but_does_not_raise(tmp_path, monkeypatch, capsys):
    script = _script()
    monkeypatch.setattr(script, "ROOT", tmp_path)

    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(script.subprocess, "run", run)
    script._remove_worktree(tmp_path / "wt")
    assert "git worktree remove` did not finish" in capsys.readouterr().err
