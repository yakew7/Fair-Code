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
import codecs
import functools
import hashlib
import io
import sys

import pandas as pd

from . import __version__
from .compare import compare
from .detect import VALID_KINDS
from .loaders_extra import (
    ENCODING_IGNORED_CLI,
    encoding_ignored_for_path,
    get_xlsx_sheet_info,
    read_table,
)
# _resolve_opts gives the thresholds that were actually in force, defaults
# included, which is what the provenance block has to record. Reaching for the
# private helper follows the existing precedent in compare.py (`from .profiler
# import _r`) and keeps profiler.py - a parity-sensitive file - untouched.
from .profiler import _resolve_opts, parse_reference, profile
from .provenance import build as build_provenance
from .proxy import parse_held_out_specs, proxy_hints
from .report import (
    compare_to_csv, compare_to_html, compare_to_terminal, to_csv, to_html, to_json, to_terminal,
)
from .sample_data import SAMPLE_FILENAME, build_sample_csv

_MAP_CHOICES = VALID_KINDS + ("ignore",)


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for a benchmark iteration count."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")
    return parsed


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


def _build_held_out(specs, df, encoding=None):
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
        return parse_held_out_specs(specs, df, functools.partial(_read_or_exit, encoding=encoding))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _alpha(args):
    from .proxy import PROXY_ALPHA
    return PROXY_ALPHA if args.proxy_alpha is None else args.proxy_alpha


def _profile_provenance(args, opts, overrides, df=None):
    from .provenance import sniff_effective_encoding
    digests = [] if args.sample else [("dataset_hash", args.csv)]
    if args.reference:
        digests.append(("reference_hash", args.reference))
    columns = None if df is None else list(df.columns)
    enc = getattr(args, "encoding", None)
    if not enc and getattr(args, "csv", None) and not getattr(args, "sample", False):
        enc = sniff_effective_encoding(args.csv)
    provenance = build_provenance(digests, _resolve_opts(opts), overrides,
                                  held_out=[("proxy_hints_with", args.proxy_hints_with, columns)],
                                  encodings={"dataset_hash": enc} if enc else None)
    if args.sample:
        provenance["dataset_hash"] = "sha256:" + hashlib.sha256(
            build_sample_csv().encode("utf-8")).hexdigest()
    return provenance


def _compare_provenance(args, opts, overrides, df_a=None, df_b=None):
    from .provenance import sniff_effective_encoding
    cols_a = None if df_a is None else list(df_a.columns)
    cols_b = None if df_b is None else list(df_b.columns)
    enc = getattr(args, "encoding", None)
    enc_a = enc or sniff_effective_encoding(getattr(args, "csv_a", None))
    enc_b = enc or sniff_effective_encoding(getattr(args, "csv_b", None))
    encs = {}
    if enc_a:
        encs["dataset_hash_a"] = enc_a
    if enc_b:
        encs["dataset_hash_b"] = enc_b
    return build_provenance(
        [("dataset_hash_a", args.csv_a), ("dataset_hash_b", args.csv_b)],
        _resolve_opts(opts), overrides,
        held_out=[("proxy_hints_with_a", args.proxy_hints_with_a, cols_a),
                  ("proxy_hints_with_b", args.proxy_hints_with_b, cols_b)],
        encodings=encs if encs else None)


def _write_csv_export(path, text, bom=False):
    """Write a --csv export to PATH, or to stdout when PATH is "-" (#779).
    Returns True on failure (after printing the error), like the other writers."""
    if path == "-":
        if bom:
            sys.stdout.write("\ufeff")
        sys.stdout.write(text)
        return False
    try:
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"error: could not write CSV export to {path}: {exc}", file=sys.stderr)
        return True
    print(f"CSV export written to {path}", file=sys.stderr)
    return False


def _check_encoding(name):
    """Reject an unknown --encoding name up front (#843)."""
    if name is None:
        return
    try:
        codecs.lookup(name)
    except LookupError:
        print(f"error: unknown --encoding '{name}' (try utf-8, latin-1, cp1252 or utf-16)",
              file=sys.stderr)
        raise SystemExit(2)




def _warn_encoding_ignored(paths, encoding):
    """Print a one-line stderr notice when --encoding can't apply (#870)."""
    if encoding is None:
        return
    if any(encoding_ignored_for_path(p) for p in paths if p and p != "-"):
        print(ENCODING_IGNORED_CLI, file=sys.stderr)

def _read_or_exit(path: str, encoding: str | None = None):
    """Read a table, or print a plain error and raise SystemExit(2)."""
    try:
        return read_table(path, encoding=encoding) if encoding else read_table(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    except UnicodeDecodeError as exc:
        used = encoding or "utf-8"
        print(f"error: could not read dataset {path}: not valid {used} ({exc}); "
              f"pass --encoding NAME (e.g. latin-1, cp1252, utf-16)", file=sys.stderr)
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
    p.add_argument("csv", nargs="?",
                   help="path to the dataset file (.csv, .tsv, .xlsx, .json, or .parquet), "
                        "or - to read CSV/TSV from stdin (omit if using --sample)")
    p.add_argument("--sample", action="store_true",
                   help="profile a small bundled sample dataset instead of a file - "
                        "a zero-argument way to see what a profile looks like, "
                        "matching the web profiler's own sample-dataset button")
    p.add_argument("--json", action="store_true", help="emit JSON to stdout")
    p.add_argument("--html", metavar="PATH",
                   help="write a standalone HTML report to PATH")
    p.add_argument("--csv", dest="csv_out", metavar="PATH",
                   help="write a flat, one-row-per-group CSV export to PATH, or - for "
                        "stdout (dest csv_out - distinct from the csv dataset argument)")
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
    p.add_argument("--csv-provenance", action="store_true",
                   help="append a provenance section (dataset hash, resolved thresholds, "
                        "version) to the --csv export, like --json's provenance block")
    p.add_argument("--csv-bom", action="store_true",
                   help="prefix the --csv export with a UTF-8 BOM so Excel on Windows "
                        "opens non-ASCII labels correctly (needs --csv)")
    p.add_argument("--proxy-hints", action="store_true",
                   help="flag strongly-associated column pairs via chi-squared (needs scipy)")
    p.add_argument("--proxy-alpha", type=float, default=None, metavar="ALPHA",
                   help="significance level for --proxy-hints (default 0.05; must be in (0, 1])")
    p.add_argument("--proxy-correction", choices=("bonferroni", "holm"), default=None,
                   help="multiple-comparison correction across all tested pairs for "
                        "--proxy-hints (default: none; adds p_adjusted to each hint)")
    p.add_argument("--proxy-hints-with", action="append", metavar="PATH=COLUMN[:KEY]",
                   help="also test proxy_hints against a column already dropped from "
                        "the dataset; PATH's rows must align 1:1 with the profiled "
                        "dataset, or be joined on a key column present in both files "
                        "with :KEY (repeatable, needs --proxy-hints)")
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
    p.add_argument("--max-categorical-card", type=int, metavar="N",
                   help="raise/lower the generic-categorical auto-detect cardinality "
                        "ceiling (default: detect.MAX_CATEGORICAL_CARD)")
    p.add_argument("--max-dimension-groups", type=int, metavar="N",
                   help="raise/lower the group-count cutoff past which a non-geography "
                        "dimension is dropped as identifier/date-like "
                        "(default: profiler.MAX_DIMENSION_GROUPS)")
    p.add_argument("--max-age", type=float, metavar="N",
                   help="numeric ages above N are treated as implausible (flagged and "
                        "left out of the age bands) instead of landing in the oldest "
                        "band (default: profiler.MAX_AGE, 120)")
    p.add_argument("--encoding", metavar="NAME",
                   help="text encoding of the dataset (and any held-out/reference files), "
                        "e.g. latin-1, cp1252, utf-16 (default: a UTF-8/16/32 byte-order "
                        "mark if present, else utf-8)")
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
    c.add_argument("--csv", dest="csv_out", metavar="PATH",
                   help="write a flat, one-row-per-group CSV export to PATH, or - for stdout")
    c.add_argument("--csv-provenance", action="store_true",
                   help="append a provenance section (dataset hash, resolved thresholds, "
                        "version) to the --csv export, like --json's provenance block")
    c.add_argument("--csv-bom", action="store_true",
                   help="prefix the --csv export with a UTF-8 BOM so Excel on Windows "
                        "opens non-ASCII labels correctly (needs --csv)")
    c.add_argument("--proxy-hints", action="store_true",
                   help="flag strongly-associated column pairs via chi-squared, "
                        "for both datasets separately (needs scipy)")
    c.add_argument("--proxy-alpha", type=float, default=None, metavar="ALPHA",
                   help="significance level for --proxy-hints (default 0.05; must be in (0, 1])")
    c.add_argument("--proxy-correction", choices=("bonferroni", "holm"), default=None,
                   help="multiple-comparison correction across all tested pairs for "
                        "--proxy-hints (default: none; adds p_adjusted to each hint)")
    c.add_argument("--proxy-hints-with-a", action="append", metavar="PATH=COLUMN[:KEY]",
                   help="also test dataset A's proxy_hints against a column already "
                        "dropped from A; PATH's rows must align 1:1 with csv_a, or be "
                        "joined on a key column with :KEY (repeatable, needs --proxy-hints)")
    c.add_argument("--proxy-hints-with-b", action="append", metavar="PATH=COLUMN[:KEY]",
                   help="same as --proxy-hints-with-a, for dataset B (rows must align "
                        "1:1 with csv_b, or be joined with :KEY)")
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
    c.add_argument("--max-categorical-card", type=int, metavar="N",
                   help="raise/lower the generic-categorical auto-detect cardinality "
                        "ceiling (default: detect.MAX_CATEGORICAL_CARD)")
    c.add_argument("--max-dimension-groups", type=int, metavar="N",
                   help="raise/lower the group-count cutoff past which a non-geography "
                        "dimension is dropped as identifier/date-like "
                        "(default: profiler.MAX_DIMENSION_GROUPS)")
    c.add_argument("--max-age", type=float, metavar="N",
                   help="numeric ages above N are treated as implausible (flagged and "
                        "left out of the age bands) instead of landing in the oldest "
                        "band (default: profiler.MAX_AGE, 120)")
    c.add_argument("--fail-on-drift", action="store_true",
                   help="exit 1 when any dimension shows drift or the overall score drops")
    c.add_argument("--encoding", metavar="NAME",
                   help="text encoding of the dataset (and any held-out/reference files), "
                        "e.g. latin-1, cp1252, utf-16 (default: a UTF-8/16/32 byte-order "
                        "mark if present, else utf-8)")
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
    b.add_argument("--n-resamples", type=_positive_int, default=2000, metavar="N",
                   help="bootstrap resamples per metric (positive integer, default: 2000)")
    b.add_argument("--n-permutations", type=_positive_int, default=2000, metavar="N",
                   help="permutation-test shuffles per metric (positive integer, default: 2000)")
    b.add_argument("--no-plots", action="store_true",
                   help="skip rendering figures/*.png (no matplotlib needed)")

    args = parser.parse_args(argv)
    if args.command in ("profile", "compare"):
        _check_encoding(args.encoding)

    if args.command == "profile":
        if args.sample and args.csv:
            print("error: pass either csv or --sample, not both", file=sys.stderr)
            return 2
        if not args.sample and not args.csv:
            print("error: profile needs a csv argument (or --sample)", file=sys.stderr)
            return 2
        if args.proxy_alpha is not None and not 0 < args.proxy_alpha <= 1:
            print("error: --proxy-alpha must be in (0, 1]", file=sys.stderr)
            return 2
        if args.proxy_alpha is not None and not args.proxy_hints:
            print("error: --proxy-alpha needs --proxy-hints", file=sys.stderr)
            return 2
        if args.proxy_correction and not args.proxy_hints:
            print("error: --proxy-correction needs --proxy-hints", file=sys.stderr)
            return 2
        if args.csv_provenance and not args.csv_out:
            print("error: --csv-provenance needs --csv", file=sys.stderr)
            return 2
        if args.csv_bom and not args.csv_out:
            print("error: --csv-bom needs --csv", file=sys.stderr)
            return 2
        if args.proxy_hints_with and not args.proxy_hints:
            print("error: --proxy-hints-with needs --proxy-hints", file=sys.stderr)
            return 2
        if args.csv == "-" and args.reference == "-":
            print(
                "error: profile input and --reference can't both read from stdin "
                "(a stream can only be read once)",
                file=sys.stderr,
            )
            return 2
        held_out_uses_stdin = any(
            path == "-" and sep and column
            for path, sep, column in (
                spec.partition("=") for spec in args.proxy_hints_with or []
            )
        )
        if args.csv == "-" and held_out_uses_stdin:
            print(
                "error: profile input and --proxy-hints-with can't both read from stdin "
                "(a stream can only be read once)",
                file=sys.stderr,
            )
            return 2

        if args.sample:
            df = pd.read_csv(io.StringIO(build_sample_csv()))
            args.csv = SAMPLE_FILENAME  # for any downstream display purposes
            sheet_info = None
        else:
            _warn_encoding_ignored([args.csv], args.encoding)
            df = _read_or_exit(args.csv, args.encoding)
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
            "max_categorical_card": args.max_categorical_card,
            "max_dimension_groups": args.max_dimension_groups,
            "max_age": args.max_age,
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
                opts["reference"] = parse_reference(_read_or_exit(args.reference, args.encoding))
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
            held_out = _build_held_out(args.proxy_hints_with, df, args.encoding)
            try:
                result["proxy_hints"] = proxy_hints(df, result["dimensions"], alpha=_alpha(args), correction=args.proxy_correction, held_out=held_out,
                                                max_age=_resolve_opts(opts)["max_age"])
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

        if args.csv_out == "-" and args.json:
            print("error: --csv - and --json both write to stdout; use one",
                  file=sys.stderr)
            return 2
        if args.csv_out:
            prov = _profile_provenance(args, opts, overrides, df) if args.csv_provenance else None
            if _write_csv_export(args.csv_out, to_csv(result, provenance=prov),
                                    bom=args.csv_bom):
                return 2

        if args.json:
            provenance = None
            if not args.no_provenance:
                provenance = _profile_provenance(args, opts, overrides, df)
            print(to_json(result, provenance=provenance))
        elif args.csv_out != "-":  # stdout already carries the CSV
            print(to_terminal(result))
        if args.fail_under is not None and result["overall_score"] is None:
            print(
                "error: cannot apply --fail-under: " + _lower_first(
                    (result["note"] or "the dataset could not be measured").rstrip(".")),
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
        if args.proxy_alpha is not None and not 0 < args.proxy_alpha <= 1:
            print("error: --proxy-alpha must be in (0, 1]", file=sys.stderr)
            return 2
        if args.proxy_alpha is not None and not args.proxy_hints:
            print("error: --proxy-alpha needs --proxy-hints", file=sys.stderr)
            return 2
        if args.proxy_correction and not args.proxy_hints:
            print("error: --proxy-correction needs --proxy-hints", file=sys.stderr)
            return 2
        if args.csv_provenance and not args.csv_out:
            print("error: --csv-provenance needs --csv", file=sys.stderr)
            return 2
        if args.csv_bom and not args.csv_out:
            print("error: --csv-bom needs --csv", file=sys.stderr)
            return 2
        if (args.proxy_hints_with_a or args.proxy_hints_with_b) and not args.proxy_hints:
            print("error: --proxy-hints-with-a/-b needs --proxy-hints", file=sys.stderr)
            return 2

        def _held_out_uses_stdin(specs):
            return any(
                path == "-" and sep and column
                for path, sep, column in (spec.partition("=") for spec in specs or [])
            )

        if args.csv_a == "-" and _held_out_uses_stdin(args.proxy_hints_with_a):
            print(
                "error: csv_a and --proxy-hints-with-a can't both read from stdin "
                "(a stream can only be read once)",
                file=sys.stderr,
            )
            return 2
        if args.csv_b == "-" and _held_out_uses_stdin(args.proxy_hints_with_b):
            print(
                "error: csv_b and --proxy-hints-with-b can't both read from stdin "
                "(a stream can only be read once)",
                file=sys.stderr,
            )
            return 2

        overrides = _parse_map(args.map)
        opts = {
            "min_share": args.min_share,
            "intersection_floor": args.intersection_floor,
            "imbalance_flag": args.imbalance_flag,
            "missing_flag": args.missing_flag,
            "min_group_size": args.min_group_size,
            "max_categorical_card": args.max_categorical_card,
            "max_dimension_groups": args.max_dimension_groups,
            "max_age": args.max_age,
        }
        _warn_encoding_ignored([args.csv_a, args.csv_b], args.encoding)
        df_a = _read_or_exit(args.csv_a, args.encoding)
        df_b = _read_or_exit(args.csv_b, args.encoding)
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

        try:
            profile_a = profile(df_a, overrides, opts)
            profile_b = profile(df_b, overrides, opts)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        result = compare(profile_a, profile_b, name_a=args.csv_a, name_b=args.csv_b)

        if args.proxy_hints or args.proxy_hints_with_a or args.proxy_hints_with_b:
            held_out_a = _build_held_out(args.proxy_hints_with_a, df_a, args.encoding)
            held_out_b = _build_held_out(args.proxy_hints_with_b, df_b, args.encoding)
            try:
                result["proxy_hints_a"] = proxy_hints(df_a, profile_a["dimensions"], alpha=_alpha(args), correction=args.proxy_correction, held_out=held_out_a,
                                                        max_age=_resolve_opts(opts)["max_age"])
                result["proxy_hints_b"] = proxy_hints(df_b, profile_b["dimensions"], alpha=_alpha(args), correction=args.proxy_correction, held_out=held_out_b,
                                                        max_age=_resolve_opts(opts)["max_age"])
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

        if args.csv_out == "-" and args.json:
            print("error: --csv - and --json both write to stdout; use one",
                  file=sys.stderr)
            return 2
        if args.csv_out:
            prov = _compare_provenance(args, opts, overrides, df_a, df_b) if args.csv_provenance else None
            if _write_csv_export(args.csv_out, compare_to_csv(result, provenance=prov),
                                    bom=args.csv_bom):
                return 2
        if args.json:
            provenance = None
            if not args.no_provenance:
                provenance = _compare_provenance(args, opts, overrides, df_a, df_b)
            print(to_json(result, provenance=provenance))
        elif args.csv_out != "-":
            print(compare_to_terminal(result))
        if args.fail_on_drift and result["drift_detected"]:
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
