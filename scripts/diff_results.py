#!/usr/bin/env python3
"""Diff the live results/ against the paper/results-frozen/ reference snapshot.

`results/` moves every time the harness is rerun; `paper/results-frozen/` is the earlier snapshot
kept as a point of comparison. This joins the two result tables on the columns that identify a row
and prints the per-row change, so nobody has to diff two CSVs by hand:

    python3 scripts/diff_results.py                       # fairness + performance, moved rows only
    python3 scripts/diff_results.py --threshold 0.02      # flag rows that moved by more than 0.02
    python3 scripts/diff_results.py --kind fairness --all # every row, not just the ones that moved
    python3 scripts/diff_results.py --limit 100           # list at most 100 rows per kind
    python3 scripts/diff_results.py --json                # machine-readable: one list per kind plus a "provenance" key
    python3 scripts/diff_results.py --fail-on-change      # exit 1 if any row is flagged (for CI)
    python3 scripts/diff_results.py --audit COMPAS        # only these audits (repeatable)
    python3 scripts/diff_results.py --summary             # one line per audit and kind
    python3 scripts/diff_results.py --timing-threshold 2  # mark a fit SLOWER in the timing line from 2x (and 1 s) up

Each row also carries a `sample` field: `same` when both sides report the same group sizes
(fairness: n_disadvantaged and n_advantaged; performance: n), `different` when they differ (the two
runs were scored on different test rows, so the delta mixes a model change with a change in who was
tested; the sizes are in `sample_sizes`), and `unknown` when a side has no size columns or the row is
on one side only. `different` rows are marked `~` in the text output and counted in `--summary`.

Join keys: fairness = audit, strategy, model, protected_attribute, metric; performance = audit,
strategy, model, metric. A row present on one side only is reported as `only_current` or
`only_reference` (a new audit, strategy or metric, or one that was dropped) and always counts as
flagged. A row on both sides is `moved` when |current - reference| > --threshold (default 0.01),
else `unchanged`. A value that is empty on one side only (e.g. an AUC row's missing interval)
counts as moved.

A row whose value is empty on one side while that side's `note` column explains why (for example
`advantaged_selection_too_rare`, the disparate impact ratio withheld when the advantaged group is almost
never selected, #1132) is `withheld`, not `moved`: the benchmark chose not to report a number. It is
listed in its own block with both sides' notes, counted separately in `--summary`, and counts as
flagged for `--fail-on-change` because what the harness reports changed. A row withheld on both sides
is `unchanged`. Reads only; it never writes to either directory.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
import difflib

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENT_DIR = REPO_ROOT / "results"
REFERENCE_DIR = REPO_ROOT / "paper" / "results-frozen"
DEFAULT_THRESHOLD = 0.01
DEFAULT_TIMING_RATIO = 1.5      # a combination is marked slower when it took this many times as long ... (#1353)
TIMING_MIN_SECONDS = 1.0        # ... and at least this many seconds longer, so a 0.2 s fit that doubled is not a finding

SIZE_COLUMNS = {
    "fairness": ["n_disadvantaged", "n_advantaged"],
    "performance": ["n"],
}

KINDS = {
    "fairness": ("results_fairness.csv", ["audit", "strategy", "model", "protected_attribute", "metric"]),
    "performance": ("results_performance.csv", ["audit", "strategy", "model", "metric"]),
}


def _sizes(row, size_columns):
    """The row's group sizes as a list of ints, or None if a size column is missing or empty."""
    values = []
    for column in size_columns:
        if column not in row.index or pd.isna(row[column]):
            return None
        values.append(int(row[column]))
    return values


def diff_table(current: pd.DataFrame, reference: pd.DataFrame, keys: list[str],
               threshold: float = DEFAULT_THRESHOLD, size_columns: list[str] | None = None) -> list[dict]:
    """One dict per row on either side: the key columns plus status, reference, current, delta, sample.

    `size_columns` names the columns holding the test-set sizes; when both sides have them for a row,
    `sample` is `same` or `different` (with `sample_sizes` giving both), otherwise `unknown`.
    """
    def index(df):
        out, sizes, notes = {}, {}, {}
        for _, row in df.iterrows():
            key = tuple(str(row[k]) for k in keys)
            out[key] = row["value"]
            sizes[key] = _sizes(row, size_columns or [])
            note = row["note"] if "note" in row.index else None
            notes[key] = None if note is None or pd.isna(note) or not str(note).strip() else str(note)
        return out, sizes, notes

    (cur, cur_sizes, cur_notes), (ref, ref_sizes, ref_notes) = index(current), index(reference)
    rows = []
    for key in sorted(set(cur) | set(ref)):
        entry = dict(zip(keys, key))
        c, r = cur.get(key), ref.get(key)
        entry["reference"] = None if r is None or pd.isna(r) else float(r)
        entry["current"] = None if c is None or pd.isna(c) else float(c)
        c_size, r_size = cur_sizes.get(key), ref_sizes.get(key)
        if key not in cur or key not in ref or c_size is None or r_size is None:
            entry["sample"] = "unknown"
        else:
            entry["sample"] = "same" if c_size == r_size else "different"
            if c_size != r_size:
                entry["sample_sizes"] = {"current": c_size, "reference": r_size}
        if key not in ref:
            entry["status"], entry["delta"] = "only_current", None
        elif key not in cur:
            entry["status"], entry["delta"] = "only_reference", None
        elif entry["current"] is None and entry["reference"] is None:
            entry["status"], entry["delta"] = "unchanged", 0.0
        elif (entry["current"] is None and cur_notes.get(key)) or (entry["reference"] is None and ref_notes.get(key)):
            entry["status"], entry["delta"] = "withheld", None
            entry["withheld"] = {"current": cur_notes.get(key) if entry["current"] is None else None,
                                 "reference": ref_notes.get(key) if entry["reference"] is None else None}
        elif entry["current"] is None or entry["reference"] is None:
            entry["status"], entry["delta"] = "moved", None
        else:
            delta = entry["current"] - entry["reference"]
            entry["delta"] = delta
            entry["status"] = "moved" if abs(delta) > threshold and not math.isclose(delta, threshold) else "unchanged"
        rows.append(entry)
    return rows


def diff_dirs(current_dir: Path, reference_dir: Path, kinds=("fairness", "performance"),
              threshold: float = DEFAULT_THRESHOLD, audits=None) -> dict:
    """With `audits`, only rows whose audit is one of those names are joined."""
    out = {}
    for kind in kinds:
        filename, keys = KINDS[kind]
        cur_path, ref_path = Path(current_dir) / filename, Path(reference_dir) / filename
        for p in (cur_path, ref_path):
            if not p.is_file():
                raise FileNotFoundError(f"{p} not found")
        current, reference = pd.read_csv(cur_path), pd.read_csv(ref_path)
        if audits:
            wanted = set(audits)
            current = current[current["audit"].astype(str).isin(wanted)]
            reference = reference[reference["audit"].astype(str).isin(wanted)]
        out[kind] = diff_table(current, reference, keys, threshold, SIZE_COLUMNS[kind])
    return out


def known_audits(current_dir: Path, reference_dir: Path, kinds=("fairness", "performance")) -> set[str]:
    """Every audit name on either side, for checking --audit."""
    names = set()
    for kind in kinds:
        filename = KINDS[kind][0]
        for directory in (current_dir, reference_dir):
            path = Path(directory) / filename
            if path.is_file():
                names.update(pd.read_csv(path)["audit"].astype(str))
    return names


def summarize(diff: dict) -> dict:
    """Per kind, one dict per audit: rows compared, rows flagged, largest absolute delta (None if no numeric delta)."""
    out = {}
    for kind, rows in diff.items():
        per_audit = {}
        for r in rows:
            s = per_audit.setdefault(r["audit"], {"audit": r["audit"], "compared": 0, "flagged": 0,
                                                  "max_abs_delta": None, "different_sample": 0, "withheld": 0})
            s["compared"] += 1
            s["flagged"] += _flagged(r)
            s["withheld"] += r["status"] == "withheld"
            s["different_sample"] += r.get("sample") == "different"
            if r["delta"] is not None and (s["max_abs_delta"] is None or abs(r["delta"]) > s["max_abs_delta"]):
                s["max_abs_delta"] = abs(r["delta"])
        out[kind] = [per_audit[a] for a in sorted(per_audit)]
    return out


def read_provenance(directory) -> dict | None:
    """Where a result set came from (#1129): the commit, Python and library versions read from PROVENANCE.json (written by
    `faircode benchmark`) or, for the frozen snapshot, from its MANIFEST.md. None when neither exists."""
    directory = Path(directory)
    record = directory / "PROVENANCE.json"
    if record.is_file():
        runs = json.loads(record.read_text(encoding="utf-8")).get("runs", [])
        if not runs:
            return None
        last = runs[-1]
        return {"source": "PROVENANCE.json", "commit": last.get("commit"), "dirty": last.get("dirty"), "python": last.get("python"),
                "libraries": {k.lower(): v for k, v in (last.get("libraries") or {}).items() if v}, "runs": len(runs),
                "description": last.get("description"), "timings": last.get("timings") or []}
    manifest = directory / "MANIFEST.md"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        field = lambda name: (re.search(rf"\*\*{re.escape(name)}:\*\*\s*`?([^`\n]+)`?", text) or [None, None])[1]
        libraries = {n: field(n) for n in ("scikit-learn", "fairlearn", "pandas", "numpy") if field(n)}
        return {"source": "MANIFEST.md", "commit": field("Git commit"), "dirty": None, "python": field("Python"),
                "libraries": libraries, "runs": 1, "description": "frozen snapshot", "timings": []}
    return None


def describe_provenance(label, info) -> str:
    if info is None:
        return f"{label}: no provenance recorded"
    commit = (info["commit"] or "unknown")[:7] + (" (dirty tree)" if info.get("dirty") else "")
    libs = ", ".join(f"{name} {version}" for name, version in sorted(info["libraries"].items()))
    runs = f", {info['runs']} runs" if info.get("runs", 1) > 1 else ""
    return f"{label}: commit {commit}, Python {info['python']}{runs}; {libs or 'no library versions'}"


def _missing_side(now, before) -> str:
    return "both sides" if not now and not before else "the reference side" if not before else "the current side"


def timing_data(cur, ref, top: int = 5, ratio: float = DEFAULT_TIMING_RATIO) -> dict:
    """The structure behind `timing_lines` (#1345): `{"recorded": False, "missing": ...}` when a side has no timings, else the two totals
    and the `top` combinations whose seconds changed most, each as `{combination, reference, current, delta, ratio, slower}`
    (#1353): `ratio` is current over reference (None when the reference took no time) and `slower` is true when it is at least
    `ratio` and the fit took at least TIMING_MIN_SECONDS longer."""
    def seconds(info):
        return {f"{t['audit']}/{t['strategy']}/{t['model']}": t["seconds"] for t in (info or {}).get("timings") or []}

    now, before = seconds(cur), seconds(ref)
    if not now or not before:
        return {"recorded": False, "missing": _missing_side(now, before)}
    changes = sorted(((now[k] - before[k], k) for k in now.keys() & before.keys()), key=lambda item: (-abs(item[0]), item[1]))[:top]
    return {"recorded": True, "total_reference": sum(before.values()), "total_current": sum(now.values()),
            "changes": [{"combination": k, "reference": before[k], "current": now[k], "delta": delta,
                         "ratio": now[k] / before[k] if before[k] else None,
                         "slower": bool(before[k]) and now[k] / before[k] >= ratio and delta >= TIMING_MIN_SECONDS}
                        for delta, k in changes]}


def timing_lines(cur, ref, top: int = 5, ratio: float = DEFAULT_TIMING_RATIO) -> list[str]:
    """How long the fits took on each side (#1334): the totals and the `top` combinations whose seconds changed most, from the
    `timings` of the two runs' provenance entries; says so when a side recorded none (an older run or the frozen snapshot)."""
    data = timing_data(cur, ref, top, ratio)
    if not data["recorded"]:
        return ["timings: not recorded on " + data["missing"]]
    before, now = data["total_reference"], data["total_current"]
    line = f"timings: total {before:.1f} s -> {now:.1f} s ({now - before:+.1f} s)"
    if data["changes"]:
        line += "; largest changes: " + ", ".join(
            f"{c['combination']} {c['reference']:.1f} -> {c['current']:.1f} s ({c['delta']:+.1f}"
            + (f", {c['ratio']:.1f}x" if c["ratio"] is not None else "") + ")" + (" SLOWER" if c["slower"] else "")
            for c in data["changes"])
    return [line]


def _stopped(info) -> set[str] | None:
    """The `audit/strategy/model` combinations whose fits stopped at max_iter, or None when this side did not record it."""
    entries = [t for t in (info or {}).get("timings") or [] if "convergence_warnings" in t]
    if not entries:
        return None
    return {f"{t['audit']}/{t['strategy']}/{t['model']}" for t in entries if t["convergence_warnings"]}


def convergence_data(cur, ref) -> dict:
    """The structure behind `convergence_lines` (#1345): `{"recorded": False, "missing": ...}` or the two counts and the sorted lists
    of combinations that started and stopped stopping at max_iter."""
    now, before = _stopped(cur), _stopped(ref)
    if now is None or before is None:
        return {"recorded": False, "missing": _missing_side(now is not None, before is not None)}
    return {"recorded": True, "reference": len(before), "current": len(now),
            "newly_stopping": sorted(now - before), "no_longer_stopping": sorted(before - now)}


def convergence_lines(cur, ref) -> list[str]:
    """How the fits that stopped at max_iter changed between the two sides (#1341): the counts and the combinations that
    started or stopped stopping; says so when a side recorded nothing (an older run, or the frozen snapshot)."""
    data = convergence_data(cur, ref)
    if not data["recorded"]:
        return ["convergence: not recorded on " + data["missing"]]
    line = f"convergence: combinations that stopped at max_iter {data['reference']} -> {data['current']}"
    if data["newly_stopping"]:
        line += "; newly stopping: " + ", ".join(data["newly_stopping"])
    if data["no_longer_stopping"]:
        line += "; no longer stopping: " + ", ".join(data["no_longer_stopping"])
    return [line]


def _versions_differ(cur, ref) -> list[str]:
    names = sorted(set(cur["libraries"]) & set(ref["libraries"]))   # only libraries both sides recorded
    differ = [f"{n} {ref['libraries'][n]} -> {cur['libraries'][n]}" for n in names if cur["libraries"][n] != ref["libraries"][n]]
    if cur["python"] != ref["python"]:
        differ.insert(0, f"python {ref['python']} -> {cur['python']}")
    return differ


def provenance_data(current_dir, reference_dir, ratio: float = DEFAULT_TIMING_RATIO) -> dict:
    """What the text report's provenance block says, as data for `--json` (#1345): both sides' provenance (without the raw timings),
    the versions that differ, and the timing and convergence changes. The last three are None unless both sides have provenance."""
    cur, ref = read_provenance(current_dir), read_provenance(reference_dir)
    side = lambda info: None if info is None else {k: v for k, v in info.items() if k != "timings"}
    both = bool(cur and ref)
    return {"current": side(cur), "reference": side(ref),
            "versions_differ": _versions_differ(cur, ref) if both else None,
            "timings": timing_data(cur, ref, ratio=ratio) if both else None,
            "convergence": convergence_data(cur, ref) if both else None}


def provenance_report(current_dir, reference_dir, ratio: float = DEFAULT_TIMING_RATIO) -> str:
    """Both sides' provenance and the library versions that differ, so a moved row can be told apart from a library bump."""
    cur, ref = read_provenance(current_dir), read_provenance(reference_dir)
    lines = [describe_provenance("current  ", cur), describe_provenance("reference", ref)]
    if cur and ref:
        differ = _versions_differ(cur, ref)
        lines.append("versions that differ: " + (", ".join(differ) if differ else "none"))
        lines += timing_lines(cur, ref, ratio=ratio)
        lines += convergence_lines(cur, ref)
    return "\n".join(lines) + "\n\n"



def render_summary(summary: dict) -> str:
    lines = []
    for kind, audits in summary.items():
        lines.append(f"{kind}:")
        for s in audits:
            largest = "n/a" if s["max_abs_delta"] is None else f"{s['max_abs_delta']:.4f}"
            lines.append(f"  {s['audit']}: {s['compared']} compared, {s['flagged']} flagged, "
                         f"{s['withheld']} withheld, {s['different_sample']} on different test sets, largest |delta| {largest}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _flagged(row: dict) -> bool:
    return row["status"] != "unchanged"


def render(diff: dict, show_all: bool = False, threshold: float = DEFAULT_THRESHOLD, limit: int | None = None) -> str:
    """`limit` caps the rows listed per kind (withheld rows count too); the rest are counted in a closing line (#1131)."""
    lines = []
    for kind, rows in diff.items():
        keys = KINDS[kind][1]
        flagged = [r for r in rows if _flagged(r)]
        different = sum(r.get("sample") == "different" for r in rows)
        lines.append(f"{kind}: {len(rows)} rows compared, {len(flagged)} flagged "
                     f"(moved by more than {threshold:g}, or present on one side only), "
                     f"{different} measured on different test sets")
        withheld = []
        listed = 0
        shown = rows if show_all else flagged
        for r in shown:
            if limit is not None and listed >= limit:
                break
            listed += 1
            label = " / ".join(r[k] for k in keys)
            if r["status"] == "withheld":
                notes = r["withheld"]
                side = lambda name, value: (f"{name} withheld ({notes[name]})" if notes[name]
                                            else f"{name} {value:.4f}")
                withheld.append(f"  ! {label}: {side('reference', r['reference'])}, {side('current', r['current'])}")
                continue
            if r["status"] == "only_current":
                detail = f"only in results/ (current {r['current']:.4f})" if r["current"] is not None else "only in results/"
            elif r["status"] == "only_reference":
                detail = (f"only in paper/results-frozen/ (reference {r['reference']:.4f})"
                          if r["reference"] is not None else "only in paper/results-frozen/")
            else:
                ref = "-" if r["reference"] is None else f"{r['reference']:.4f}"
                cur = "-" if r["current"] is None else f"{r['current']:.4f}"
                delta = "n/a" if r["delta"] is None else f"{r['delta']:+.4f}"
                detail = f"{ref} -> {cur} ({delta})"
            mark = "!" if _flagged(r) else " "
            if r.get("sample") == "different":
                sizes = r["sample_sizes"]
                detail += f" [different test set: reference {sizes['reference']}, current {sizes['current']}]"
                mark = "~" if mark == " " else mark
            lines.append(f"  {mark} {label}: {detail}")
        if withheld:
            lines.append(f"  withheld ({len(withheld)} rows where the benchmark chose not to report a value, with its reason):")
            lines.extend(withheld)
        if listed < len(shown):
            lines.append(f"  ... {len(shown) - listed} more rows not listed (--limit {limit}); run without --limit for all of them")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _ratio(value: str) -> float:
    number = float(value)
    if number <= 1:
        raise argparse.ArgumentTypeError("must be greater than 1 (a ratio of current to reference seconds)")
    return number


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--current", type=Path, default=CURRENT_DIR, help="directory holding the live results (default: results/)")
    p.add_argument("--reference", type=Path, default=REFERENCE_DIR,
                   help="directory holding the reference snapshot (default: paper/results-frozen/)")
    p.add_argument("--kind", choices=["fairness", "performance", "both"], default="both")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"flag a row whose value moved by more than this (default {DEFAULT_THRESHOLD})")
    p.add_argument("--timing-threshold", type=_ratio, default=DEFAULT_TIMING_RATIO, metavar="RATIO",
                   help=f"mark a fit SLOWER in the timing line when it took at least RATIO times as long and at least {TIMING_MIN_SECONDS:g} s "
                        f"longer (default {DEFAULT_TIMING_RATIO}); informational, never changes the exit code")
    p.add_argument("--all", action="store_true", help="list unchanged rows too")
    p.add_argument("--json", action="store_true", help="print the diff as JSON")
    p.add_argument("--fail-on-change", action="store_true", help="exit 1 if any row is flagged")
    p.add_argument("--audit", action="append", metavar="NAME",
                   help="only compare this audit (repeatable; default: every audit)")
    p.add_argument("--limit", type=int, metavar="N",
                   help="list at most N rows per kind and count the rest (keeps a PR comment under GitHub's size limit)")
    p.add_argument("--summary", action="store_true",
                   help="print one line per audit and kind instead of every row")
    args = p.parse_args(argv)
    if args.threshold < 0:
        p.error("--threshold must be zero or positive")
    if args.limit is not None and args.limit < 1:
        p.error("--limit must be at least 1")
    kinds = ("fairness", "performance") if args.kind == "both" else (args.kind,)
    try:
        if args.audit:
            unknown = sorted(set(args.audit) - known_audits(args.current, args.reference, kinds))
            if unknown:
                available = sorted(known_audits(args.current, args.reference, kinds))
                print(f"error: unknown audit(s): {', '.join(unknown)}", file=sys.stderr)
                if available:
                    print(f"Available audits: {', '.join(available)}", file=sys.stderr)
                    for name in unknown:
                        matches = difflib.get_close_matches(
                            name, available, n=1, cutoff=0.4
                        )
                        if matches:
                            print(f"Did you mean '{matches[0]}'?", file=sys.stderr)
                return 2
        diff = diff_dirs(args.current, args.reference, kinds, args.threshold, args.audit)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.json:
        print(provenance_report(args.current, args.reference, args.timing_threshold), end="")
    if args.summary:
        summary = summarize(diff)
        if args.json:
            print(json.dumps({**summary, "provenance": provenance_data(args.current, args.reference, args.timing_threshold)}, indent=2))
        else:
            print(render_summary(summary), end="")
    elif args.json:
        print(json.dumps({**diff, "provenance": provenance_data(args.current, args.reference, args.timing_threshold)}, indent=2))
    else:
        print(render(diff, args.all, args.threshold, args.limit), end="")
    if args.fail_on_change and any(_flagged(r) for rows in diff.values() for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
