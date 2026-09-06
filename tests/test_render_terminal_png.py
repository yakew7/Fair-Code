"""Tests for scripts/render_terminal_png.py.

This exact file previously hardcoded a macOS-only font path (fixed by
switching to the repo-bundled assets/fonts/IBMPlexMono-Regular.ttf, closing
#323) with no regression test guarding either the fix or the renderer's own
output shape - see issue #368.
"""

import importlib

import pytest
from PIL import Image


def _script():
    return importlib.import_module("scripts.render_terminal_png")


def test_render_produces_a_correctly_sized_png(tmp_path):
    script = _script()
    out_path = tmp_path / "out.png"
    text = "line one\nline two\nline three"

    script.render(text, out_path)

    with Image.open(out_path) as img:
        assert img.size[1] == script.PAD_Y * 2 + script.LINE_HEIGHT * 3
        assert img.size[0] > 0


def test_render_handles_a_single_line(tmp_path):
    script = _script()
    out_path = tmp_path / "out.png"

    script.render("just one line", out_path)

    with Image.open(out_path) as img:
        assert img.size[1] == script.PAD_Y * 2 + script.LINE_HEIGHT


def test_render_strips_a_single_trailing_newline_only(tmp_path):
    # rstrip("\n") should drop one trailing blank line, not collapse
    # intentional blank lines in the middle of the captured output.
    script = _script()
    out_path = tmp_path / "out.png"

    script.render("line one\n\nline three\n", out_path)

    with Image.open(out_path) as img:
        assert img.size[1] == script.PAD_Y * 2 + script.LINE_HEIGHT * 3


def test_render_wraps_long_lines_without_clipping_pixels(tmp_path):
    script = _script()
    capped_path = tmp_path / "capped.png"
    wrapped_path = tmp_path / "wrapped.png"

    script.render("ok\n" + "X" * script.MAX_WIDTH_CHARS, capped_path)
    script.render("ok\n" + "X" * 150, wrapped_path)

    def text_pixel_count(path):
        with Image.open(path) as img:
            pixels = img.load()
            return sum(
                pixels[x, y] != script.BG_COLOR
                for y in range(img.height)
                for x in range(img.width)
            )

    with Image.open(wrapped_path) as img:
        assert img.size[1] == script.PAD_Y * 2 + script.LINE_HEIGHT * 3
    # All 150 glyphs are present across two rows. The old renderer clipped the
    # overflow and produced approximately the same ink count as the 92-char image.
    assert text_pixel_count(wrapped_path) > text_pixel_count(capped_path) * 1.5


def test_main_wrong_arg_count_exits_2(capsys, monkeypatch):
    script = _script()
    monkeypatch.setattr("sys.argv", ["render_terminal_png.py", "only_one_arg"])

    with pytest.raises(SystemExit) as exc_info:
        script.main()

    assert exc_info.value.code == 2
    assert "usage:" in capsys.readouterr().err
