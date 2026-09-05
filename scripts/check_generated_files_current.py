#!/usr/bin/env python3
"""Fails if the generated site files (explainer pages, sitemap, OG images,
llms-full.txt) or the MCP results-frozen mirror (faircode/_results_frozen/)
are out of date relative to their sources.

Used by .github/workflows/build-explainers.yml, run *after* the workflow's
own `build_explainers.py`/`generate_og_images.py`/
`freeze_paper_results.mirror_for_mcp()` steps have already regenerated
everything fresh into the working tree.

Text-based generated files (explainer HTML, explainers-data.js,
sitemap.xml, llms-full.txt, faircode/_results_frozen/*.csv) are compared
byte-for-byte against the fresh regeneration via `git diff` - they've
never shown any platform-dependent variation, confirmed across two
separate incidents below.

One field is deliberately excluded from that byte-exact comparison:
build_explainers.py's `datePublished`/`dateModified` (JSON-LD) and
`<lastmod>` (sitemap.xml) are derived from `git log` on the source .md
file - which, for a brand new explainer, has no commit yet at the moment
it's first built (contributors necessarily build before their first
commit of that file exists, per CONTRIBUTING.md's own instructions), so
the very first commit's HTML is always missing them. A fresh regeneration
run afterwards - by this exact check, on the commit that just added the
file - correctly finds that commit and fills them in, which reads as
"stale" under a literal byte comparison even though nothing about the
source content changed. This isn't a staleness bug to catch, it's a
one-time, structural chicken-and-egg for any file's own introducing
commit, confirmed directly against the commit that added
explainers/equal-opportunity.md and explainers/intersectional-bias.md.
`_normalize_dates()` below strips exactly those fields (and only those)
before comparing, the same "verify what's actually meaningful, not what's
incidentally timing-dependent" approach the OG-image handling below
already takes.

OG PNGs are NOT compared against the fresh regeneration at all, by
design - two earlier attempts at that (byte-exact `git diff`, then a fixed
`compress_level`, then decoded-pixel comparison) all failed for the same
underlying reason: Pillow's bundled FreeType renders text with genuinely
different pixels on Ubuntu (CI) than on macOS (confirmed directly - a
macOS-side regeneration matches the macOS-committed original byte-for-byte
and pixel-for-pixel, while CI's Ubuntu-side regeneration of the exact same
inputs does not). That's not a staleness bug to catch, it's an inherent
cross-platform rendering difference with no fix available from either
side. What actually matters - and *is* platform-independent - is that a
current dark and light OG image exists for every explainer, is non-empty,
and has the right dimensions; `tests/test_generate_images.py` already
verifies the *generator* satisfies that in a temp directory, so this
script checks the same thing for what's actually committed.

Run locally:  python3 scripts/check_generated_files_current.py
Exit code:    0 = everything current, 1 = something is genuinely stale.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "assets" / "explainers-data.json"
OG_DIMENSIONS = (1200, 630)

TEXT_GLOBS = [
    "explainers/*.html",
    "assets/explainers-data.js",
    "sitemap.xml",
    "llms-full.txt",
    "faircode/_explainers/*.md",
    "faircode/_explainers/data.json",
    "faircode/_results_frozen/*.csv",
]

_JSONLD_DATE_LINE = re.compile(
    r'[ \t]*"date(?:Published|Modified)":\s*"\d{4}-\d{2}-\d{2}",?\r?\n'
)
_LASTMOD_TAG = re.compile(r"[ \t]*<lastmod>\d{4}-\d{2}-\d{2}</lastmod>\r?\n")
_TRAILING_COMMA_BEFORE_BRACE = re.compile(r",(\r?\n[ \t]*[}\]])")


def _normalize_dates(text: str) -> str:
    """Strips the git-log-derived datePublished/dateModified/lastmod fields
    (see module docstring) so a file's own introducing commit doesn't read
    as stale just because those fields couldn't exist yet when it was
    first built."""
    text = _JSONLD_DATE_LINE.sub("", text)
    text = _LASTMOD_TAG.sub("", text)
    return _TRAILING_COMMA_BEFORE_BRACE.sub(r"\1", text)


def _tracked_paths(pattern):
    out = subprocess.run(
        ["git", "ls-files", pattern], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [ROOT / line for line in out.splitlines() if line.strip()]


def _expected_og_slugs():
    entries = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    return ["home", "profiler"] + [entry["slug"] for entry in entries]


def main():
    stale = []

    for pattern in TEXT_GLOBS:
        for path in _tracked_paths(pattern):
            rel = path.relative_to(ROOT)
            show = subprocess.run(
                ["git", "show", f"HEAD:{rel.as_posix()}"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if show.returncode != 0:
                # Staged but never committed (e.g. running this locally
                # before the first commit of a brand new file) - trivially
                # differs from "nothing at HEAD", not a normalization case.
                stale.append((rel, "not yet committed"))
                continue
            fresh = path.read_text(encoding="utf-8")
            if _normalize_dates(show.stdout) != _normalize_dates(fresh):
                stale.append((rel, "content differs from a fresh regeneration"))

    for theme_dir in ("assets/og", "assets/og-light"):
        for slug in _expected_og_slugs():
            path = ROOT / theme_dir / f"{slug}.png"
            rel = path.relative_to(ROOT)
            if not path.is_file():
                stale.append((rel, "missing"))
                continue
            if path.stat().st_size == 0:
                stale.append((rel, "empty file"))
                continue
            try:
                with Image.open(path) as image:
                    size = image.size
            except Exception as exc:
                stale.append((rel, f"could not decode: {exc}"))
                continue
            if size != OG_DIMENSIONS:
                stale.append((rel, f"wrong dimensions: {size}, expected {OG_DIMENSIONS}"))

    if stale:
        print("Generated files are out of date - run 'make build-explainers' locally and commit the result.")
        for rel, reason in stale:
            print(f"  {rel}: {reason}")
        return 1

    print(
        "Generated files are up to date (text diff exact; OG images verified present, "
        "non-empty, and correctly sized - not compared pixel-for-pixel across platforms, see module docstring)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
