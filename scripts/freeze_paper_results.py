"""Freeze the current results/ into paper/results-frozen/ as a comparison snapshot.

The repo keeps changing - new audits, new strategies, reruns with more resamples.
A paper cites specific numbers. This script separates the two: it snapshots
results/ plus everything needed to say precisely what produced those numbers, so
a future contributor's audit changes the LIVE results but never the numbers
already cited in print.

Run this once the numbers you're about to cite are final:

    python3 scripts/freeze_paper_results.py
    python3 scripts/freeze_paper_results.py --tag v1.0-paper   # also prints (not runs) the git tag command

It does NOT create a git tag itself - tagging is a deliberate, semi-permanent
repo action (it gets pushed to the remote and shows up as a GitHub release),
so the actual `git tag` + `git push --tags` is left as an explicit manual step
this script reminds you to run.

Writes paper/results-frozen/:
    results_fairness.csv, results_performance.csv, summary.csv, figures/*.png   (copied verbatim from results/)
    requirements-lock.txt                                                       (copied from repo root)
    MANIFEST.md                                                                 (this snapshot's provenance)

Also mirrors the three CSVs into faircode/_results_frozen/ - a package-internal
copy for faircode/mcp_server.py's get_benchmark_results tool, for the same
reason faircode/_explainers/ mirrors explainers/*.md (issue #388): paper/ lives
outside what pyproject.toml ships, so a real `pip install faircode[mcp]` never
has it on disk.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
FROZEN_DIR = REPO_ROOT / "paper" / "results-frozen"
LOCKFILE = REPO_ROOT / "requirements-lock.txt"
MCP_MIRROR_DIR = REPO_ROOT / "faircode" / "_results_frozen"
MCP_MIRROR_FILES = ("results_fairness.csv", "results_performance.csv", "summary.csv")


def mirror_for_mcp():
    """Copies the three frozen CSVs (not figures/MANIFEST/lockfile - just the
    tabular data get_benchmark_results reads) from FROZEN_DIR into
    MCP_MIRROR_DIR, a real Python-package-data location. Safe to call any
    time FROZEN_DIR already holds a real snapshot - only reads from it, never
    writes back."""
    MCP_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
    for name in MCP_MIRROR_FILES:
        src = FROZEN_DIR / name
        if src.exists():
            shutil.copy2(src, MCP_MIRROR_DIR / name)


def _run(cmd):
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _package_version(name):
    try:
        module = __import__(name)
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return "not installed"


def _discover_manifests():
    from faircode.manifest import discover_manifests  # local import: needs the repo on sys.path

    return sorted(str(p.relative_to(REPO_ROOT)) for p in discover_manifests(REPO_ROOT))


def freeze(tag: str | None = None) -> Path:
    if not RESULTS_DIR.exists():
        print(f"error: {RESULTS_DIR} does not exist - run `faircode benchmark` first", file=sys.stderr)
        raise SystemExit(2)

    # Capture provenance BEFORE we rewrite FROZEN_DIR - otherwise the frozen
    # files this script writes would themselves show up as uncommitted changes
    # and the dirty flag would always be True on any real freeze.
    commit = _run(["git", "rev-parse", "HEAD"]) or "unknown (not a git checkout?)"
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    dirty = bool(_run(["git", "status", "--porcelain"]))

    if FROZEN_DIR.exists():
        shutil.rmtree(FROZEN_DIR)
    FROZEN_DIR.mkdir(parents=True)

    for name in ("results_fairness.csv", "results_performance.csv", "summary.csv"):
        src = RESULTS_DIR / name
        if src.exists():
            shutil.copy2(src, FROZEN_DIR / name)
    figures_src = RESULTS_DIR / "figures"
    if figures_src.exists():
        shutil.copytree(figures_src, FROZEN_DIR / "figures")

    if LOCKFILE.exists():
        shutil.copy2(LOCKFILE, FROZEN_DIR / "requirements-lock.txt")

    manifests = _discover_manifests()

    manifest_lines = [
        "# Frozen results provenance",
        "",
        "This is a comparison snapshot, not evidence for a live publication. `results/` at the repo",
        "root keeps changing as contributors add audits or rerun the harness; this folder does not -",
        "regenerate it with `scripts/freeze_paper_results.py` only when you want a new fixed point to",
        "compare against.",
        "",
        "## Provenance",
        "",
        f"- **Git commit:** `{commit}`{' (WORKING TREE HAD UNCOMMITTED CHANGES AT FREEZE TIME)' if dirty else ''}",
        f"- **Git branch:** `{branch}`",
        f"- **Python:** {sys.version.split()[0]}",
        f"- **scikit-learn:** {_package_version('sklearn')}",
        f"- **fairlearn:** {_package_version('fairlearn')}",
        f"- **pandas:** {_package_version('pandas')}",
        f"- **numpy:** {_package_version('numpy')}",
        "- **Full environment:** `requirements-lock.txt` in this folder",
        "",
        f"## Audits included ({len(manifests)} domains)",
        "",
        "The exact, reproducible set of manifests this snapshot covers - not \"whatever was in the",
        "repo that week\":",
        "",
    ]
    manifest_lines += [f"- `{m}`" for m in manifests]
    manifest_lines += [
        "",
        "## Reproducing this snapshot",
        "",
        "```bash",
        f"git checkout {commit}",
        "pip install -r requirements-lock.txt",
        'pip install -e ".[benchmark]"',
        "faircode benchmark --out results/",
        "python3 scripts/freeze_paper_results.py",
        "```",
    ]
    if tag:
        manifest_lines += [
            "",
            "## Tag",
            "",
            f"This snapshot corresponds to the intended tag `{tag}` - not yet created. Run manually:",
            "",
            "```bash",
            f"git tag -a {tag} -m \"Results frozen for paper citation\"",
            f"git push origin {tag}",
            "```",
        ]

    (FROZEN_DIR / "MANIFEST.md").write_text("\n".join(manifest_lines) + "\n")
    mirror_for_mcp()

    print(f"Froze {RESULTS_DIR} -> {FROZEN_DIR}")
    print(f"  MCP mirror: {MCP_MIRROR_DIR}")
    print(f"  commit:    {commit}{'  [DIRTY]' if dirty else ''}")
    print(f"  audits:    {len(manifests)}")
    if tag:
        print(f"  next step: git tag -a {tag} -m \"Results frozen for paper citation\" && git push origin {tag}")
    else:
        print("  next step: pass --tag vX.Y-paper to get the exact tag command printed")
    return FROZEN_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", metavar="NAME", default=None,
                       help="tag name this snapshot is intended for (e.g. v1.0-paper) - "
                            "printed as a manual next step, never run automatically")
    args = parser.parse_args()
    freeze(tag=args.tag)


if __name__ == "__main__":
    main()
