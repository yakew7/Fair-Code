#!/usr/bin/env python3
"""Fails if the generated site files (explainer pages, sitemap, OG images,
llms-full.txt) or the MCP results-frozen mirror (faircode/_results_frozen/)
are out of date relative to their sources.

Used by .github/workflows/build-explainers.yml. Runs its own fresh
regeneration internally (see "self-sufficient" below), so it no longer
depends on the workflow's own build_explainers.py/generate_og_images.py/
freeze_paper_results.mirror_for_mcp() steps having run first - though CI
still runs those first anyway, since the workflow's later steps assume a
built working tree either way.

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
script checks the same thing for what's actually committed. Whether a
card's text is current is checked through the card-inputs.json file in
each OG folder (#1197): the generator stores a hash of each card's inputs
there, so it is compared byte-for-byte like the other text files, and an
explainer whose title or summary changed without a re-render reads as
stale.

This script is self-sufficient: it builds a fresh copy of the site itself
(via `git worktree`, with every tracked file and every untracked,
non-ignored file's working-tree content copied on top of the HEAD checkout,
so both edits to existing files and brand new files are what gets built) and
compares the real working tree against that regeneration - not against what's
committed at HEAD. Editing an explainer's .md without running `make build-explainers`
afterward is exactly the case this now catches; it no longer needs to run
after CI's own build_explainers.py/generate_og_images.py steps to be
meaningful, though CI still runs it there too.

Run locally:  python3 scripts/check_generated_files_current.py
Exit code:    0 = everything current, 1 = something is genuinely stale.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import ExitStack
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
    "faircode/_results_current/*.csv",
    "explainers/code/*.py",
    "assets/og/card-inputs.json",
    "assets/og-light/card-inputs.json",
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


BUILD_TIMEOUT = 600.0      # seconds for each of the three regeneration steps (#1292)


class BuilderTimeout(RuntimeError):
    """A regeneration step did not finish within BUILD_TIMEOUT; carries which one."""

    def __init__(self, builder: str, seconds: float):
        super().__init__(f"{builder} did not finish within {seconds:g} s")
        self.builder, self.seconds = builder, seconds


def _builder_name(cmd) -> str:
    """A short name for a builder command: its script path, or the module function a `-c` snippet calls."""
    if len(cmd) > 1 and cmd[1] == "-c":
        return "the MCP results mirror (scripts.freeze_paper_results)"
    return cmd[1] if len(cmd) > 1 else " ".join(cmd)


def _fresh_build_dir(stack):
    """Returns a Path to a real regeneration of the site, built from what's
    actually on disk right now - not from HEAD. `git worktree add` gives a
    checkout backed by the same object database/history as ROOT (so
    git-log-derived dates in build_explainers.py resolve identically to a
    regeneration done in ROOT itself), then every tracked file's
    *working-tree* content and every untracked, non-ignored file are copied
    on top of that HEAD checkout, so edits and new explainer files/assets
    are all included in the build. Ignored files stay out of the fresh
    checkout.

    `stack` is an ExitStack the caller uses to guarantee the worktree is
    cleaned up even if a later step raises.
    """
    tmp = Path(tempfile.mkdtemp(prefix="faircode-freshbuild-"))
    stack.callback(lambda: subprocess.run(
        ["git", "worktree", "remove", "--force", str(tmp)],
        cwd=ROOT, capture_output=True, check=False,
    ))
    subprocess.run(
        ["git", "worktree", "add", "--detach", "--quiet", str(tmp), "HEAD"],
        cwd=ROOT, check=True,
    )

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for rel in tracked + untracked:
        if not rel.strip():
            continue
        src, dst = ROOT / rel, tmp / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    for cmd in (
        [sys.executable, "scripts/build_explainers.py"],
        [sys.executable, "scripts/generate_og_images.py"],
        [sys.executable, "-c",
         "from scripts.freeze_paper_results import mirror_for_mcp, mirror_current_for_mcp; "
         "mirror_for_mcp(); mirror_current_for_mcp()"],
    ):
        try:
            subprocess.run(cmd, cwd=tmp, check=True, capture_output=True, text=True, timeout=BUILD_TIMEOUT)
        except subprocess.CalledProcessError as exc:
            if exc.stderr:
                print(exc.stderr, file=sys.stderr, end="")
            raise
        except subprocess.TimeoutExpired as exc:
            raise BuilderTimeout(_builder_name(cmd), BUILD_TIMEOUT) from exc

    return tmp


def main():
    stale = []

    with ExitStack() as stack:
        try:
            fresh_dir = _fresh_build_dir(stack)
        except BuilderTimeout as exc:
            print(f"error: {exc}: a hung builder blocks this check, so nothing was compared. "
                  f"Run it by hand to see where it stalls.", file=sys.stderr)
            return 1

        for pattern in TEXT_GLOBS:
            for path in _tracked_paths(pattern):
                rel = path.relative_to(ROOT)
                fresh_path = fresh_dir / rel
                if not fresh_path.is_file():
                    stale.append((rel, "not produced by a fresh regeneration"))
                    continue
                working_tree = path.read_text(encoding="utf-8")
                fresh = fresh_path.read_text(encoding="utf-8")
                if _normalize_dates(fresh) != _normalize_dates(working_tree):
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
