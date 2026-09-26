import importlib
import tempfile
from pathlib import Path

import pytest
from PIL import Image
import json
import shutil

_VALID_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="32" y="18" width="13" height="64" fill="#14171A"/>
  <rect x="32" y="18" width="42" height="13" fill="#14171A"/>
  <rect x="32" y="44" width="36" height="13" fill="#4F7A5B"/>
</svg>
"""


def test_parse_mark_accepts_the_real_logo_svg():
    script = importlib.import_module("scripts.generate_favicons")

    spec = script._parse_mark(script.ROOT / "assets" / "icons" / "logo.svg")

    assert spec["size"] == 100.0
    assert spec["mark_fill"] == "#14171A"
    assert spec["accent_fill"] == "#4F7A5B"


def test_parse_mark_rejects_non_square_viewbox(tmp_path):
    script = importlib.import_module("scripts.generate_favicons")
    bad_svg = tmp_path / "bad.svg"
    bad_svg.write_text(
        _VALID_SVG.replace('viewBox="0 0 100 100"', 'viewBox="0 0 100 80"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected a square viewBox starting at 0,0"):
        script._parse_mark(bad_svg)


def test_parse_mark_rejects_viewbox_not_at_origin(tmp_path):
    script = importlib.import_module("scripts.generate_favicons")
    bad_svg = tmp_path / "bad.svg"
    bad_svg.write_text(
        _VALID_SVG.replace('viewBox="0 0 100 100"', 'viewBox="10 0 100 100"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected a square viewBox starting at 0,0"):
        script._parse_mark(bad_svg)


def test_parse_mark_rejects_a_fourth_rect(tmp_path):
    script = importlib.import_module("scripts.generate_favicons")
    bad_svg = tmp_path / "bad.svg"
    bad_svg.write_text(
        _VALID_SVG.replace(
            "</svg>",
            '  <rect x="0" y="0" width="10" height="10" fill="#000000"/>\n</svg>',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no longer exactly three rects"):
        script._parse_mark(bad_svg)


def test_parse_mark_rejects_mismatched_stem_and_bar_fill(tmp_path):
    script = importlib.import_module("scripts.generate_favicons")
    bad_svg = tmp_path / "bad.svg"
    bad_svg.write_text(
        _VALID_SVG.replace(
            '<rect x="32" y="18" width="42" height="13" fill="#14171A"/>',
            '<rect x="32" y="18" width="42" height="13" fill="#000000"/>',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stem and top bar are expected to share one fill color"):
        script._parse_mark(bad_svg)


def test_generate_favicons(tmp_path, monkeypatch):
    script = importlib.import_module("scripts.generate_favicons")

    monkeypatch.setattr(script, "ICONS_DIR", tmp_path)
    monkeypatch.setattr(script, "LOGO_SVG", script.ROOT / "assets" / "icons" / "logo.svg")

    script.main()

    expected = {
        "favicon-16x16.png": (16, 16),
        "favicon-32x32.png": (32, 32),
        "favicon.ico": (32, 32),
        "apple-touch-icon.png": (180, 180),
        "icon-192.png": (192, 192),
        "icon-512.png": (512, 512),
    }

    for filename in expected:
        output = tmp_path / filename
        assert output.is_file(), f"Expected {filename} to be generated"
        assert output.stat().st_size > 0, f"{filename} is empty"

        with Image.open(output) as image:
            assert image.width > 0
            assert image.height > 0

        with Image.open(output) as image:
            assert image.size == expected[filename]


def test_generate_og_images(tmp_path, monkeypatch):
    script = importlib.import_module("scripts.generate_og_images")

    # main() computes each out_dir's relative_to(script.ROOT) for its summary print,
    # so the scratch dir has to live under script.ROOT - it can't just be tmp_path.
    # mkdtemp (not tmp_path.name, which repeats across separate pytest invocations)
    # creates it atomically with a unique name, so concurrent runs can't collide.
    test_root = Path(tempfile.mkdtemp(dir=script.ROOT, prefix=".tmp-test-"))

    try:
        monkeypatch.setitem(script.THEMES["dark"], "out_dir", test_root / "og")
        monkeypatch.setitem(script.THEMES["light"], "out_dir", test_root / "og-light")

        script.main()

        expected = ["home.png", "profiler.png"]

        for entry in json.loads(
            script.DATA_JSON.read_text(encoding="utf-8")
        ):
            expected.append(f"{entry['slug']}.png")

        for directory in (test_root / "og", test_root / "og-light"):
            for filename in expected:
                output = directory / filename
                assert output.is_file(), f"Expected {output} to be generated"
                assert output.stat().st_size > 0, f"{output} is empty"

                with Image.open(output) as image:
                    assert image.size == (1200, 630)
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
