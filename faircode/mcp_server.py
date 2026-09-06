"""MCP server exposing the profiler's Python API as tools for an LLM agent to
call directly, instead of shelling out to the CLI and parsing text.

    faircode-mcp                # run directly (stdio transport)
    python -m faircode.mcp_server

Stdio-only - no network listener, no auth, no hosting. Every tool reads a
local file path the calling process already has access to, the same trust
boundary the CLI already has: nothing here is a new capability, just a
different way to call the same profile()/compare()/proxy_hints() functions
cli.py already wraps. See faircode/SPEC.md section 11 for the tool contract.

Phase 2 (list_explainers, get_explainer, get_benchmark_results) adds
read-only lookups against package-internal mirrors of this repo's explainers/
and frozen benchmark results - the plan mentioned in CHANGELOG.md's Phase 1 note.

Needs the optional 'mcp' extra (`pip install faircode[mcp]`).

Tool logic lives in plain, directly-callable `_*_impl` functions (this
module's actual unit of testing - tests/test_mcp_server.py calls these, not
the MCP-decorated wrappers) so `mcp` SDK API churn - it renamed FastMCP to
MCPServer between v1 and v2 - stays contained to `build_server()` and doesn't
leak into anything else. The `_impl` functions raise plain ValueError /
FileNotFoundError / RuntimeError; `build_server()`'s wrappers translate those
into `ToolError` so the anticipated-failure message (e.g. "file not found:
X") actually reaches the calling agent - any other exception type is treated
by the SDK as a crash and replaced with a generic "Error executing tool X",
withholding the real text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from . import __version__
from .compare import compare
from .detect import VALID_KINDS
from .loaders_extra import get_xlsx_sheet_info, read_table
from .profiler import _resolve_opts, parse_reference, profile
from .provenance import build as build_provenance
from .proxy import parse_held_out_specs
from .proxy import proxy_hints as compute_proxy_hints

_MAP_CHOICES = VALID_KINDS + ("ignore",)

# Phase 2 of the plan discussed for #327-#329 (see CHANGELOG.md's Phase 1
# note): read-only lookups against explainers/, so an agent can discover and
# read an explainer without shelling out or re-deriving the index itself.
#
# Reads from _explainers/, a generated mirror INSIDE this package (built by
# scripts/build_explainers.py's build_package_mirror()) rather than the
# repo-root explainers/ and assets/ directories directly: those live outside
# what pyproject.toml actually ships, so a real `pip install faircode[mcp]`
# never has them on disk at all - only a git-checkout dev install would (see
# issue #388). The mirror ships as real package-data instead.
EXPLAINERS_DIR = Path(__file__).resolve().parent / "_explainers"
EXPLAINERS_DATA_JSON = EXPLAINERS_DIR / "data.json"

# The other half of the Phase 2 plan: read-only lookups against
# paper/results-frozen/'s benchmark numbers. Reads from _results_frozen/, a
# package-internal mirror (scripts/freeze_paper_results.py's
# mirror_for_mcp()) for the same packaging reason as EXPLAINERS_DIR above -
# paper/ is never shipped by pyproject.toml either.
RESULTS_FROZEN_DIR = Path(__file__).resolve().parent / "_results_frozen"
RESULTS_FROZEN_FILES = {
    "fairness": RESULTS_FROZEN_DIR / "results_fairness.csv",
    "performance": RESULTS_FROZEN_DIR / "results_performance.csv",
}
_RESULTS_ROW_LIMIT = 200
# Both frozen CSVs' own precision (float64, 15-17 significant digits) isn't
# meaningful at this granularity - every explainer citing these numbers
# already rounds to 3 decimal places. 6 keeps headroom for small effect
# sizes while cutting the unfiltered-call payload the row cap alone still
# leaves too large.
_RESULTS_ROUND_DECIMALS = 6
_RESULTS_NUMERIC_COLUMNS = ("value", "ci_low", "ci_high", "p_value")


def _read_table_or_raise(path: str):
    """Read a table, translating loader failures into a clear message instead
    of a raw pandas/parser traceback. Mirrors cli.py's _read_or_exit, minus
    the SystemExit - a tool function should raise, not exit the process.

    Rejects "-" (the CLI's documented stdin shorthand) before it ever reaches
    loaders_extra.py's sys.stdin.read(): this server runs over stdio
    transport, so stdin is the JSON-RPC channel itself - reading it inside a
    tool call would block on/consume the same stream the server needs for
    its own protocol frames (see issue #385)."""
    if path == "-":
        raise ValueError("stdin input ('-') is not supported over MCP - pass a real file path instead")
    try:
        return read_table(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"file not found: {path}") from None
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any parse failure plainly
        raise RuntimeError(f"could not read dataset {path}: {exc}") from exc


def _sheet_note(path):
    """The same "read sheet 'X' - N other sheet(s) ignored" notice cli.py
    prints to stderr for a multi-sheet .xlsx path, or None if `path` isn't a
    multi-sheet .xlsx - the MCP tools had no equivalent at all (issue #386),
    silently profiling only the first sheet with nothing telling the calling
    agent other sheets existed."""
    info = get_xlsx_sheet_info(path)
    if info is None:
        return None
    sheet_name, ignored_sheets = info
    if not ignored_sheets:
        return None
    return f"read sheet '{sheet_name}' - {len(ignored_sheets)} other sheet(s) ignored"


def _check_overrides(overrides, known_columns):
    """Mirrors cli.py's _parse_map + _check_map_columns: reject an unknown
    column or an invalid kind instead of detect_columns() silently no-opping
    on it."""
    if not overrides:
        return
    unknown = [col for col in overrides if col not in known_columns]
    if unknown:
        raise ValueError(f"overrides column(s) not found in the dataset: {', '.join(unknown)}")
    bad = {col: kind for col, kind in overrides.items() if kind not in _MAP_CHOICES}
    if bad:
        pairs = ", ".join(f"{col}={kind}" for col, kind in bad.items())
        raise ValueError(f"invalid kind for {pairs}; choose from {', '.join(_MAP_CHOICES)}")


def _build_opts(min_share=None, intersection_floor=None, imbalance_flag=None,
                missing_flag=None, min_group_size=None, cross=None,
                reference_path=None):
    opts = {
        "min_share": min_share,
        "intersection_floor": intersection_floor,
        "imbalance_flag": imbalance_flag,
        "missing_flag": missing_flag,
        "min_group_size": min_group_size,
    }
    if cross:
        if len(cross) != 2 or not all(cross):
            raise ValueError("cross expects exactly two column names")
        if cross[0] == cross[1]:
            raise ValueError(f"cross needs two different columns, got '{cross[0]}' twice")
        opts["cross"] = list(cross)
    if reference_path:
        opts["reference"] = parse_reference(_read_table_or_raise(reference_path))
    return opts


def _profile_dataset_impl(path, overrides=None, cross=None, reference_path=None,
                          min_share=None, intersection_floor=None,
                          imbalance_flag=None, missing_flag=None,
                          min_group_size=None, include_provenance=True):
    overrides = overrides or {}
    df = _read_table_or_raise(path)
    _check_overrides(overrides, df.columns)
    opts = _build_opts(min_share, intersection_floor, imbalance_flag,
                       missing_flag, min_group_size, cross, reference_path)
    result = profile(df, overrides, opts)
    note = _sheet_note(path)
    if note:
        result["sheet_note"] = note
    if include_provenance:
        digests = [("dataset_hash", path)]
        if reference_path:
            digests.append(("reference_hash", reference_path))
        result = dict(result, provenance=build_provenance(digests, _resolve_opts(opts), overrides))
    return result


def _compare_datasets_impl(path_a, path_b, overrides=None,
                           min_share=None, intersection_floor=None,
                           imbalance_flag=None, missing_flag=None,
                           min_group_size=None, include_provenance=True,
                           proxy_hints=False):
    overrides = overrides or {}
    df_a = _read_table_or_raise(path_a)
    df_b = _read_table_or_raise(path_b)
    _check_overrides(overrides, set(df_a.columns) | set(df_b.columns))
    opts = _build_opts(min_share, intersection_floor, imbalance_flag,
                       missing_flag, min_group_size)
    profile_a = profile(df_a, overrides, opts)
    profile_b = profile(df_b, overrides, opts)
    result = compare(profile_a, profile_b, name_a=path_a, name_b=path_b)
    note_a, note_b = _sheet_note(path_a), _sheet_note(path_b)
    if note_a:
        result["sheet_note_a"] = note_a
    if note_b:
        result["sheet_note_b"] = note_b
    if proxy_hints:
        result["proxy_hints_a"] = compute_proxy_hints(df_a, profile_a["dimensions"])
        result["proxy_hints_b"] = compute_proxy_hints(df_b, profile_b["dimensions"])
    if include_provenance:
        provenance = build_provenance(
            [("dataset_hash_a", path_a), ("dataset_hash_b", path_b)],
            _resolve_opts(opts), overrides)
        result = dict(result, provenance=provenance)
    return result


def _proxy_hints_impl(path, overrides=None, min_share=None, min_group_size=None,
                      held_out_with=None):
    """Only min_share/min_group_size are exposed - they're the only two
    threshold knobs that feed dimension detection (profiler.py's
    _dimension()); intersection_floor/imbalance_flag/missing_flag affect
    intersections/flags, which this tool never touches.

    `held_out_with` mirrors the CLI's --proxy-hints-with: a list of
    "PATH=COLUMN" strings for testing a protected attribute that's already
    been dropped from the dataset at `path`. Parsed via proxy.py's shared
    parse_held_out_specs, so the column/row-count validation is identical to
    the CLI's.

    Returns a dict, not a bare list: the MCP SDK splits a list return value
    into one content block per element (confirmed - a 98-item result became
    98 separate content blocks, and an empty list became zero blocks, which
    is indistinguishable from an error to a caller). Wrapping in {"hints":
    [...]} keeps this tool's output shape consistent with the other two -
    always exactly one JSON object - and makes "no hints found" unambiguous.
    """
    overrides = overrides or {}
    df = _read_table_or_raise(path)
    _check_overrides(overrides, df.columns)
    opts = _build_opts(min_share=min_share, min_group_size=min_group_size)
    result = profile(df, overrides, opts)
    held_out = parse_held_out_specs(held_out_with, df, _read_table_or_raise,
                                    flag="held_out_with") if held_out_with else None
    output = {"hints": compute_proxy_hints(df, result["dimensions"], held_out=held_out)}
    notes = [n for n in (_sheet_note(path),) if n]
    notes += [n for spec in (held_out_with or []) for n in (_sheet_note(spec.partition("=")[0]),) if n]
    if notes:
        output["sheet_notes"] = notes
    return output


def _load_explainers_metadata():
    return json.loads(EXPLAINERS_DATA_JSON.read_text(encoding="utf-8"))


def _list_explainers_impl(tag=None):
    """Lists every published explainer's metadata (slug/title/subtitle/
    summary/tags), optionally filtered to those carrying `tag`. Reads the
    same assets/explainers-data.json the website's index page does, so it's
    always exactly the current published set - never re-derived or cached
    separately."""
    entries = _load_explainers_metadata()
    if tag:
        entries = [e for e in entries if tag in e.get("tags", [])]
        if not entries:
            raise ValueError(f"no explainer has tag {tag!r}")
    return {"explainers": [
        {"slug": e["slug"], "title": e["title"], "subtitle": e.get("subtitle"),
         "summary": e.get("summary"), "tags": e.get("tags", [])}
        for e in entries
    ]}


_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _get_explainer_impl(slug):
    """Returns one explainer's full Markdown source plus its metadata, by
    slug (as listed by list_explainers). Raises the same "no explainer
    found" error for an unknown slug, a malformed one, or a path-traversal
    attempt (e.g. "../README") - `slug` is caller-controlled text used to
    build a filesystem path, so it's validated against the exact pattern
    every real slug actually matches (lowercase, digits, hyphens) before
    that path is ever built, plus a belt-and-suspenders check that the
    resolved path still lands under EXPLAINERS_DIR. See issue #387."""
    if not _SLUG_RE.match(slug):
        raise FileNotFoundError(f"no explainer found for slug {slug!r}")
    path = EXPLAINERS_DIR / f"{slug}.md"
    resolved_dir = str(EXPLAINERS_DIR.resolve())
    # Path.is_relative_to() needs Python 3.9+; this package supports 3.8.
    if not str(path.resolve()).startswith(resolved_dir + "/") or not path.is_file():
        raise FileNotFoundError(f"no explainer found for slug {slug!r}")
    meta = next((e for e in _load_explainers_metadata() if e["slug"] == slug), {})
    return {
        "slug": slug,
        "title": meta.get("title"),
        "subtitle": meta.get("subtitle"),
        "tags": meta.get("tags", []),
        "content": path.read_text(encoding="utf-8"),
    }


def _get_benchmark_results_impl(kind="fairness", audit=None, model=None, strategy=None,
                                metric=None, protected_attribute=None):
    """Filters the frozen benchmark CSV named by `kind` ("fairness" or
    "performance") down to rows matching every given (non-None) filter,
    ignoring a filter that names a column the chosen `kind` doesn't have
    (e.g. `protected_attribute` against results_performance.csv, which has
    no such column). Caps the returned rows at _RESULTS_ROW_LIMIT so an
    unfiltered or loosely-filtered call can't flood the calling agent's
    context - `total_matches`/`truncated` tell it whether to narrow the
    query. NaN cells (e.g. results_performance.csv's AUC rows have no
    ci_low/ci_high) become JSON `null`, never a literal NaN token."""
    path = RESULTS_FROZEN_FILES.get(kind)
    if path is None:
        raise ValueError(f"kind must be one of {sorted(RESULTS_FROZEN_FILES)}, got {kind!r}")
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found - restore the package mirror from paper/results-frozen/ "
            "with `scripts.freeze_paper_results.mirror_for_mcp()`")
    df = pd.read_csv(path)
    for column, value in (("audit", audit), ("model", model), ("strategy", strategy),
                          ("metric", metric), ("protected_attribute", protected_attribute)):
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"{column} must be a plain string, got {type(value).__name__}")
        if column in df.columns:
            df = df[df[column] == value]
    total = len(df)
    for column in _RESULTS_NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = df[column].round(_RESULTS_ROUND_DECIMALS)
    head = df.head(_RESULTS_ROW_LIMIT).astype(object)
    rows = head.where(head.notna(), None).to_dict(orient="records")
    return {"results": rows, "total_matches": total, "truncated": total > len(rows)}


def build_server():
    """Build the MCPServer instance with every Phase 1 and Phase 2 tool
    registered."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer(
        "faircode",
        version=__version__,
        instructions=(
            "Profile a tabular dataset for demographic representation gaps, "
            "compare two datasets for representation drift, or flag columns "
            "that may be a statistical proxy for a protected attribute - all "
            "locally, no data leaves this machine. Wraps the same faircode "
            "Python API the `faircode` CLI uses. Also exposes read-only "
            "lookups against this repo's published explainers "
            "(list_explainers, get_explainer) and frozen benchmark results "
            "(get_benchmark_results)."
        ),
    )

    def _as_tool_error(exc):
        return ToolError(str(exc))

    @server.tool()
    def profile_dataset(path: str, overrides: dict[str, str] | None = None,
                        cross: list[str] | None = None,
                        reference_path: str | None = None,
                        min_share: float | None = None,
                        intersection_floor: float | None = None,
                        imbalance_flag: float | None = None,
                        missing_flag: float | None = None,
                        min_group_size: int | None = None,
                        include_provenance: bool = True) -> dict:
        """Profile a tabular dataset (.csv/.tsv/.xlsx/.json/.parquet) for
        demographic representation: per-dimension imbalance/missing/skew,
        intersectional gaps, and an overall score/grade.

        `overall_score`/`grade` are `null` when `dimensions_detected` is false
        (no demographic columns were found) - a dataset that couldn't be
        measured, not one that scored zero. `note` explains why in that case.

        `overrides` forces a column's dimension when auto-detection misses or
        mislabels it, e.g. {"gndr": "sex"}. `cross` picks two columns for the
        intersectional gap (default: the first two detected dimensions).
        `reference_path` scores against a reference baseline file (columns:
        column,group,share). The threshold args override the profiler's
        defaults (min_share=0.05, intersection_floor=0.01, imbalance_flag=3.0,
        missing_flag=0.05, min_group_size=100) when set.

        `include_provenance` (default true) attaches a provenance block -
        faircode version, a SHA-256 hash of the dataset file, and the resolved
        thresholds - so the result can be tied back to exactly what produced
        it later, without having to trust whoever ran it.
        """
        try:
            return _profile_dataset_impl(
                path, overrides, cross, reference_path, min_share,
                intersection_floor, imbalance_flag, missing_flag,
                min_group_size, include_provenance)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            raise _as_tool_error(exc) from exc

    @server.tool()
    def compare_datasets(path_a: str, path_b: str,
                         overrides: dict[str, str] | None = None,
                         min_share: float | None = None,
                         intersection_floor: float | None = None,
                         imbalance_flag: float | None = None,
                         missing_flag: float | None = None,
                         min_group_size: int | None = None,
                         include_provenance: bool = True,
                         proxy_hints: bool = False) -> dict:
        """Compare two tabular datasets (e.g. a training set and a production
        snapshot) for representation drift: which dimensions/groups appeared,
        disappeared, or shifted share, plus a population-stability-index-based
        drift level per dimension. `overrides` and the threshold args are
        applied identically to both datasets - see profile_dataset for what
        each one does, including when a side's `overall_score`/`grade` come
        back `null` (unmeasured, not zero) - `score_delta` is `null` whenever
        either side is. `include_provenance` (default true) attaches
        `dataset_hash_a`/`dataset_hash_b` alongside the resolved thresholds.

        `proxy_hints` (default false), when true, attaches `proxy_hints_a`/
        `proxy_hints_b` - the same chi-squared proxy-hint pairs the standalone
        `proxy_hints` tool computes, run separately against each dataset - so
        a single call can get drift and both datasets' proxy hints together,
        matching `faircode compare --proxy-hints`. Needs the optional 'scipy'
        extra (`pip install faircode[proxy]`).
        """
        try:
            return _compare_datasets_impl(
                path_a, path_b, overrides, min_share, intersection_floor,
                imbalance_flag, missing_flag, min_group_size, include_provenance,
                proxy_hints)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            raise _as_tool_error(exc) from exc

    @server.tool()
    def proxy_hints(path: str, overrides: dict[str, str] | None = None,
                    min_share: float | None = None,
                    min_group_size: int | None = None,
                    held_out_with: list[str] | None = None) -> dict:
        """Flag pairs of detected demographic columns that are strongly
        statistically associated (chi-squared test of independence, p < 0.05)
        - a "this column may be a proxy for that protected attribute" signal.
        Returns {"hints": [...]}, most-significant pair first; an empty list
        means no pair crossed the significance threshold, not an error.

        Needs the optional 'scipy' extra (`pip install faircode[proxy]`).

        This only tests columns present in the dataset at `path` by default:
        if a protected attribute has already been dropped entirely (a common
        but naive attempt at "fixing" bias by removing the sensitive column),
        nothing here can flag a remaining column as a proxy for it unless
        `held_out_with` is given. `held_out_with` is a list of "PATH=COLUMN"
        strings (mirroring the CLI's --proxy-hints-with flag), each pointing
        at a file whose rows align 1:1 with `path` and a column to pull the
        dropped attribute's original values from. See faircode/SPEC.md
        section 3 and issue #328.
        """
        try:
            return _proxy_hints_impl(path, overrides, min_share, min_group_size, held_out_with)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            raise _as_tool_error(exc) from exc

    @server.tool()
    def list_explainers(tag: str | None = None) -> dict:
        """List every published Fair Code explainer's metadata: slug, title,
        subtitle, summary, and topic tags. Pass `tag` (e.g. "detection",
        "metrics", "healthcare") to filter to explainers carrying it - see an
        untagged call's results for the full set of tags in use. Returns
        {"explainers": [...]}. Use the `slug` from a result with
        get_explainer to read that explainer's full text.
        """
        try:
            return _list_explainers_impl(tag)
        except ValueError as exc:
            raise _as_tool_error(exc) from exc

    @server.tool()
    def get_explainer(slug: str) -> dict:
        """Read one explainer's full Markdown source and metadata, by the
        `slug` a list_explainers call returned (e.g. "demographic-parity",
        "proxy-variables"). Returns {"slug", "title", "subtitle", "tags",
        "content"} - `content` is the raw Markdown, the same source the
        website renders to HTML from.
        """
        try:
            return _get_explainer_impl(slug)
        except (ValueError, FileNotFoundError) as exc:
            raise _as_tool_error(exc) from exc

    @server.tool()
    def get_benchmark_results(kind: str = "fairness", audit: str | None = None,
                              model: str | None = None, strategy: str | None = None,
                              metric: str | None = None,
                              protected_attribute: str | None = None) -> dict:
        """Query this repo's frozen benchmark results (`paper/results-frozen/`)
        - the numbers actually cited for each of the seven audits - without
        shelling out or parsing CSV.

        `kind` is "fairness" (default; demographic_parity_diff,
        equalized_odds_diff, etc. per protected attribute) or "performance"
        (accuracy, auc, etc., no protected_attribute column). Every other
        argument filters by exact match on that column - e.g.
        `audit="compas", model="logistic_regression", strategy="baseline"`;
        omit any of them to leave that dimension unfiltered. A filter naming
        a column `kind` doesn't have (e.g. `protected_attribute` with
        kind="performance") is simply ignored, not an error.

        Returns {"results": [...], "total_matches": N, "truncated": bool} -
        results are capped at 200 rows even when more match, so narrow the
        query with more filters if `truncated` is true rather than assuming
        the first 200 are representative.
        """
        try:
            return _get_benchmark_results_impl(kind, audit, model, strategy, metric,
                                               protected_attribute)
        except (ValueError, FileNotFoundError) as exc:
            raise _as_tool_error(exc) from exc

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
