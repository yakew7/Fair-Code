"""Command-line interface for the Fair Code dataset profiler.

    faircode profile data.csv
    faircode profile data.tsv
    faircode profile data.xlsx
    faircode profile data.json
    faircode profile data.parquet
    faircode profile data.csv --json
    faircode profile data.csv --html report.html
    faircode compare train.csv prod.csv
    faircode compare train.csv prod.csv --json
    faircode compare train.csv prod.csv --html report.html
    faircode benchmark
    faircode benchmark --out results/
    faircode benchmark COMPAS/audit.yaml "German Credit Lending/audit.yaml"

Uses only stdlib argparse + pandas (no heavyweight profiling dependency).
Reading .xlsx additionally requires the optional 'openpyxl' extra
(`pip install faircode[excel]`); reading .parquet additionally requires the
optional 'pyarrow' extra (`pip install faircode[parquet]`). The `benchmark`
command additionally requires the optional 'benchmark' extra
(`pip install faircode[benchmark]`: scikit-learn + pyyaml + fairlearn + matplotlib).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .compare import compare
from .detect import VALID_KINDS
from .loaders_extra import get_xlsx_sheet_info, read_table
# _resolve_opts gives the thresholds that were actually in force, defaults
# included, which is what the provenance block has to record. Reaching for the
# private helper follows the existing precedent in compare.py (`from .profiler
# import _r`) and keeps profiler.py - a parity-sensitive file - untouched.
from .profiler import _resolve_opts, parse_reference, profile
from .provenance import build as build_provenance
from .proxy import parse_held_out_specs, proxy_hints
from .report import compare_to_terminal, to_html, compare_to_html, to_json, to_terminal

_MAP_CHOICES = VALID_KINDS + ("ignore",)


def _parse_map(pairs):
    """Parse repeated --map COL=KIND flags into an {column: kind} override dict."""
    overrides = {}
    for pair in pairs or []:
        if "=" not in pair:
            print(f"error: invalid --map '{pair}', expected COL=KIND", file=sys.stderr)
            raise SystemExit(2)
        col, kind = pair.split("=", 1)
        kind = kind.strip().lower()
        if kind not in _MAP_CHOICES:
            print(f"error: invalid --map kind '{kind}' for column '{col.strip()}'; "
                  f"choose from {', '.join(_MAP_CHOICES)}", file=sys.stderr)
            raise SystemExit(2)
        overrides[col.strip()] = kind
    return overrides


def _check_map_columns(overrides, known_columns):
    """Error out on any --map key that isn't an actual column, instead of
    silently no-opping - detect_columns() only applies an override `if col
    in overrides` while iterating real df.columns, so a typo'd column name
    was previously dropped with no feedback at all."""
    unknown = [col for col in overrides if col not in known_columns]
    if unknown:
        print(f"error: --map column(s) not found in the dataset: {', '.join(unknown)}",
              file=sys.stderr)
        raise SystemExit(2)


def _build_held_out(specs, df):
    """Parse repeated --proxy-hints-with PATH=COLUMN flags via proxy.py's
    shared parse_held_out_specs, printing a plain error and raising
    SystemExit(2) on any parse failure, missing column, or row-count
    mismatch - _read_or_exit already does the same for an unreadable path.

    Also prints the same ignored-sheet notice the main dataset path already
    gets for a multi-sheet .xlsx file - a held-out file is a third dataset
    input, and only reading sheet 0 without saying so would otherwise be
    silently inconsistent with every other input path."""
    for spec in specs or []:
        path = spec.partition("=")[0]
        sheet_info = get_xlsx_sheet_info(path)
        if sheet_info is not None:
            sheet_name, ignored_sheets = sheet_info
            if ignored_sheets:
                print(
                    f"{path}: read sheet '{sheet_name}' - {len(ignored_sheets)} "
                    f"other sheet(s) ignored.",
                    file=sys.stderr,
                )
    try:
        return parse_held_out_specs(specs, df, _read_or_exit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _read_or_exit(path: str):
    """Read a table, or print a plain error and raise SystemExit(2)."""
    try:
        return read_table(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # noqa: BLE001 - surface any parse failure plainly
        print(f"error: could not read dataset {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faircode",
        description="Audit a tabular dataset for demographic representation.",
    )
    parser.add_argument("--version", action="version",
                        version=f"faircode {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile", help="profile a dataset for demographic imbalance")
    p.add_argument("csv", help="path to the dataset file (.csv, .tsv, .xlsx, .json, or .parquet), "
                               "or - to read CSV/TSV from stdin")
    p.add_argument("--json", action="store_true", help="emit JSON to stdout")
    p.add_argument("--html", metavar="PATH",
                   help="write a standalone HTML report to PATH")
    p.add_argument("--fail-under", type=float, metavar="N",
                   help="exit 1 when the overall representation score is below N")
    p.add_argument("--map", action="append", metavar="COL=KIND",
                   help="force a column's dimension when auto-detection misses it; "
                        "KIND is one of " + ", ".join(_MAP_CHOICES) + " (repeatable)")
    p.add_argument("--cross", metavar="COLA,COLB",
                   help="cross these two columns for the intersectional gap "
                        "(default: the first two detected dimensions)")
    p.add_argument("--reference", metavar="PATH",
                   help="score against a reference baseline dataset (columns: column,group,share)")
    p.add_argument("--proxy-hints", action="store_true",
                   help="flag strongly-associated column pairs via chi-squared (needs scipy)")
    p.add_argument("--proxy-hints-with", action="append", metavar="PATH=COLUMN",
                   help="also test proxy_hints against a column already dropped from "
                        "the dataset; PATH's rows must align 1:1 with the profiled "
                        "dataset (repeatable, needs --proxy-hints)")
    p.add_argument("--min-share", type=float, metavar="F",
                   help="under-representation threshold (default 0.05)")
    p.add_argument("--intersection-floor", type=float, metavar="F",
                   help="near-empty intersection-cell threshold (default 0.01)")
    p.add_argument("--imbalance-flag", type=float, metavar="F",
                   help="imbalance-ratio flag threshold (default 3.0)")
    p.add_argument("--missing-flag", type=float, metavar="F",
                   help="missing-data flag threshold (default 0.05)")
    p.add_argument("--min-group-size", type=int, metavar="N",
                   help="warn when a subgroup has fewer than N rows (default: profiler.MIN_GROUP_SIZE)")
    p.add_argument("--no-provenance", action="store_true",
                   help="omit the provenance block from --json output "
                        "(restores the pre-2.1 export shape exactly)")

    c = sub.add_parser("compare",
                       help="compare two datasets for representation drift")
    c.add_argument("csv_a", help="baseline dataset A (.csv, .tsv, .xlsx, .json, or .parquet), "
                                 "or - to read CSV/TSV from stdin")
    c.add_argument("csv_b", help="current dataset B (.csv, .tsv, .xlsx, .json, or .parquet), "
                                 "or - to read CSV/TSV from stdin")
    c.add_argument("--json", action="store_true", help="emit JSON to stdout")
    c.add_argument("--html", metavar="PATH",
                   help="write a standalone HTML report to PATH")
    c.add_argument("--proxy-hints", action="store_true",
                   help="flag strongly-associated column pairs via chi-squared, "
                        "for both datasets separately (needs scipy)")
    c.add_argument("--map", action="append", metavar="COL=KIND",
                   help="force a column's dimension when auto-detection misses it "
                        "(applied to both datasets); KIND is one of " +
                        ", ".join(_MAP_CHOICES) + " (repeatable)")
    c.add_argument("--min-share", type=float, metavar="F",
                   help="under-representation threshold (default 0.05)")
    c.add_argument("--intersection-floor", type=float, metavar="F",
                   help="near-empty intersection-cell threshold (default 0.01)")
    c.add_argument("--imbalance-flag", type=float, metavar="F",
                   help="imbalance-ratio flag threshold (default 3.0)")
    c.add_argument("--missing-flag", type=float, metavar="F",
                   help="missing-data flag threshold (default 0.05)")
    c.add_argument("--min-group-size", type=int, metavar="N",
                   help="warn when a subgroup has fewer than N rows (default: profiler.MIN_GROUP_SIZE)")
    c.add_argument("--fail-on-drift", action="store_true",
                   help="exit 1 when any dimension shows drift or the overall score drops")
    c.add_argument("--no-provenance", action="store_true",
                   help="omit the provenance block from --json output "
                        "(restores the pre-2.1 export shape exactly)")

    b = sub.add_parser("benchmark",
                       help="run the cross-domain fairness benchmark harness over every audit.yaml")
    b.add_argument("manifests", nargs="*", metavar="audit.yaml",
                   help="explicit manifest paths (default: discover */audit.yaml under --root)")
    b.add_argument("--root", default=".", metavar="PATH",
                   help="directory to search for */audit.yaml (default: current directory)")
    b.add_argument("--out", default="results", metavar="DIR",
                   help="output directory for results_fairness.csv, "
                        "results_performance.csv, summary.csv, and figures/ "
                        "(default: results)")
    b.add_argument("--n-resamples", type=int, default=2000, metavar="N",
                   help="bootstrap resamples per metric (default: 2000)")
    b.add_argument("--n-permutations", type=int, default=2000, metavar="N",
                   help="permutation-test shuffles per metric (default: 2000)")
    b.add_argument("--no-plots", action="store_true",
                   help="skip rendering figures/*.png (no matplotlib needed)")

    args = parser.parse_args(argv)

    if args.command == "profile":
        if args.proxy_hints_with and not args.proxy_hints:
            print("error: --proxy-hints-with needs --proxy-hints", file=sys.stderr)
            return 2

        df = _read_or_exit(args.csv)

        sheet_info = get_xlsx_sheet_info(args.csv)
        if sheet_info is not None:
            sheet_name, ignored_sheets = sheet_info
            if ignored_sheets:
                print(
                    f"Read sheet '{sheet_name}' - {len(ignored_sheets)} "
                    f"other sheet(s) ignored.",
                    file=sys.stderr,
                )

        opts = {
            "min_share": args.min_share,
            "intersection_floor": args.intersection_floor,
            "imbalance_flag": args.imbalance_flag,
            "missing_flag": args.missing_flag,
            "min_group_size": args.min_group_size,
        }
        if args.cross:
            parts = [c.strip() for c in args.cross.split(",")]
            if len(parts) != 2 or not all(parts):
                print("error: --cross expects two column names: COLA,COLB",
                      file=sys.stderr)
                return 2
            if parts[0] == parts[1]:
                print("error: --cross needs two different columns, got "
                      f"'{parts[0]}' twice", file=sys.stderr)
                return 2
            opts["cross"] = parts
        if args.reference:
            try:
                opts["reference"] = parse_reference(_read_or_exit(args.reference))
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2

        overrides = _parse_map(args.map)
        _check_map_columns(overrides, df.columns)
        try:
            result = profile(df, overrides, opts)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.proxy_hints or args.proxy_hints_with:
            held_out = _build_held_out(args.proxy_hints_with, df)
            try:
                result["proxy_hints"] = proxy_hints(df, result["dimensions"], held_out=held_out)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2

        if args.html:
            html_content = to_html(result)
            try:
                with open(args.html, "w", encoding="utf-8") as fh:
                    fh.write(html_content)
            except OSError as exc:
                print(f"error: could not write HTML report to {args.html}: {exc}",
                      file=sys.stderr)
                return 2
            print(f"HTML report written to {args.html}", file=sys.stderr)

        if args.json:
            provenance = None
            if not args.no_provenance:
                digests = [("dataset_hash", args.csv)]
                if args.reference:
                    digests.append(("reference_hash", args.reference))
                provenance = build_provenance(digests, _resolve_opts(opts), overrides)
            print(to_json(result, provenance=provenance))
        else:
            print(to_terminal(result))
        if args.fail_under is not None and result["overall_score"] is None:
            print(
                "error: cannot apply --fail-under: no demographic columns detected",
                file=sys.stderr,
            )
            return 2
        if args.fail_under is not None and result["overall_score"] < args.fail_under:
            print(
                f"error: representation score {result['overall_score']}/100 is below "
                f"--fail-under {args.fail_under:g}",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.command == "compare":
        if args.csv_a == "-" and args.csv_b == "-":
            print("error: --compare can't read both datasets from stdin "
                  "(a stream can only be read once)", file=sys.stderr)
            return 2
        overrides = _parse_map(args.map)
        opts = {
            "min_share": args.min_share,
            "intersection_floor": args.intersection_floor,
            "imbalance_flag": args.imbalance_flag,
            "missing_flag": args.missing_flag,
            "min_group_size": args.min_group_size,
        }
        df_a = _read_or_exit(args.csv_a)
        df_b = _read_or_exit(args.csv_b)
        _check_map_columns(overrides, set(df_a.columns) | set(df_b.columns))

        for path in (args.csv_a, args.csv_b):
            sheet_info = get_xlsx_sheet_info(path)
            if sheet_info is not None:
                sheet_name, ignored_sheets = sheet_info
                if ignored_sheets:
                    print(
                        f"{path}: read sheet '{sheet_name}' - {len(ignored_sheets)} "
                        f"other sheet(s) ignored.",
                        file=sys.stderr,
                    )

        profile_a = profile(df_a, overrides, opts)
        profile_b = profile(df_b, overrides, opts)
        result = compare(profile_a, profile_b, name_a=args.csv_a, name_b=args.csv_b)

        if args.proxy_hints:
            try:
                result["proxy_hints_a"] = proxy_hints(df_a, profile_a["dimensions"])
                result["proxy_hints_b"] = proxy_hints(df_b, profile_b["dimensions"])
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2

        if args.html:
            html_content = compare_to_html(result)
            try:
                with open(args.html, "w", encoding="utf-8") as fh:
                    fh.write(html_content)
            except OSError as exc:
                print(f"error: could not write HTML report to {args.html}: {exc}",
                      file=sys.stderr)
                return 2
            print(f"HTML report written to {args.html}", file=sys.stderr)
        if args.json:
            provenance = None
            if not args.no_provenance:
                provenance = build_provenance(
                    [("dataset_hash_a", args.csv_a), ("dataset_hash_b", args.csv_b)],
                    _resolve_opts(opts), overrides)
            print(to_json(result, provenance=provenance))
        else:
            print(compare_to_terminal(result))
        if args.fail_on_drift and result["flags"]:
            print(
                f"error: representation drift detected ({len(result['flags'])} flag(s)) "
                f"with --fail-on-drift set",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.command == "benchmark":
        try:
            from .benchmark import run_benchmark, write_report
        except ImportError as exc:
            print(f"error: the benchmark command needs scikit-learn and pyyaml "
                  f"(pip install faircode[benchmark]): {exc}", file=sys.stderr)
            return 2

        overridden = []
        if args.n_resamples != 2000:
            overridden.append(f"--n-resamples={args.n_resamples}")
        if args.n_permutations != 2000:
            overridden.append(f"--n-permutations={args.n_permutations}")

        if overridden:
            print(
                "warning: "
                + ", ".join(overridden)
                + " differs from the frozen paper-run default (2000); "
                "output will not match the frozen paper reference.",
                file=sys.stderr,
            )

        try:
            fairness_df, performance_df = run_benchmark(
                root=args.root, audits=args.manifests or None,
                n_resamples=args.n_resamples, n_permutations=args.n_permutations,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if fairness_df.empty:
            print(f"error: no audit.yaml manifests found under {args.root}", file=sys.stderr)
            return 2

        try:
            write_report(fairness_df, performance_df, args.out, make_plots=not args.no_plots)
        except ImportError as exc:
            print(f"error: writing benchmark plots needs matplotlib "
                  f"(pip install faircode[benchmark]): {exc}", file=sys.stderr)
            return 2
        n_audits = fairness_df["audit"].nunique()
        print(f"Ran {n_audits} audit(s), wrote {len(fairness_df)} fairness rows and "
              f"{len(performance_df)} performance rows to {args.out}/", file=sys.stderr)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
