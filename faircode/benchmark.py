"""Cross-domain fairness benchmark harness - Layer 2 of the two-layer
architecture documented in faircode/MANIFEST_SPEC.md.

Reads every audit.yaml manifest and runs the SAME pipeline over each one -
five mitigation strategies (faircode.strategies) x three model families
(faircode.models) x six fairness metrics, each with a bootstrap CI and a
permutation p-value (faircode.metrics), plus accuracy/AUC/F1 (also
faircode.metrics), plus the intersectional gap for every pair of declared
protected attributes (faircode.significance.intersectional_report) - and
returns two tidy results tables (fairness, performance). One code path, same
seed, same splits, same metric definitions, for every domain: a cross-domain
comparison is only as trustworthy as that uniformity, and this module is
what makes it literally true rather than an assertion in a write-up.

Contributors add a dataset + audit.yaml (Layer 1). They never touch this
module. faircode.figures reads this module's output tables to render the
paper figures - it never re-runs a model.

Reproducibility: every manifest's `random_state` (all seven ship with 42),
every model family (faircode.models), and every bootstrap/permutation draw
(faircode.significance, faircode.metrics) already take an explicit seed -
nothing here reads numpy's global random state. GLOBAL_SEED exists as a
defense-in-depth seed for any future strategy/model that isn't explicitly
seeded; it is not what makes today's runs reproducible, the explicit seeds
threaded through every call are. Do not change a manifest's random_state on
a run whose numbers are cited anywhere - see "Reproducibility & Results
History" in README.md before regenerating results/ for a citation.
"""

from __future__ import annotations

import difflib
import hashlib
import itertools
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import warnings
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import train_test_split

from .manifest import discover_manifests, load_manifest
from .metrics import METRICS, PERFORMANCE_METRICS, compute_metrics, compute_performance_metrics
from .models import MODEL_FAMILIES, build_model
from .significance import intersectional_report
from .strategies import (
    STRATEGIES,
    encode_features,
    fit_in_processing,
    fit_post_processing,
    predict_in_processing,
    predict_post_processing,
    strategy_features,
)

GLOBAL_SEED = 42


def _load_dataset(manifest):
    df = pd.read_csv(manifest.dataset_path, low_memory=False)
    required_columns = [
        manifest.target.column,
        *(row_filter.column for row_filter in manifest.row_filters),
        *(pa.column for pa in manifest.protected_attributes),
        *manifest.core_features,
        *manifest.proxy_features,
    ]
    missing_columns = list(
        dict.fromkeys(column for column in required_columns if column not in df.columns)
    )
    if missing_columns:
        available = ", ".join(repr(column) for column in df.columns)
        details = []
        for column in missing_columns:
            detail = repr(column)
            suggestion = difflib.get_close_matches(column, df.columns, n=1, cutoff=0.6)
            if suggestion:
                detail += f" (did you mean {suggestion[0]!r}?)"
            details.append(detail)
        raise ValueError(
            f"dataset {manifest.dataset_path.name!r} is missing column(s): "
            f"{', '.join(details)}. Available columns: {available}."
        )

    for row_filter in manifest.row_filters:
        df = row_filter.apply(df)
    df = df.reset_index(drop=True)

    y, target_known = manifest.target.compute(df)

    protected_masks = {}
    known_mask = target_known.copy()
    for pa in manifest.protected_attributes:
        disadv, known = pa.disadvantaged_mask(df)
        protected_masks[pa.name] = disadv
        known_mask &= known

    df = df[known_mask].reset_index(drop=True)
    y = y[known_mask].reset_index(drop=True)
    protected_masks = {
        name: mask[known_mask].reset_index(drop=True) for name, mask in protected_masks.items()
    }
    return df, y, protected_masks


def _run_strategy(strategy, model_name, manifest, X_all, y, protected_masks, idx_train, idx_test):
    protected_cols = [pa.column for pa in manifest.protected_attributes]
    feature_cols = strategy_features(strategy, manifest.core_features, manifest.proxy_features, protected_cols)
    X = X_all[feature_cols]
    X_train, X_test = X.iloc[idx_train], X.iloc[idx_test]
    y_train = y.iloc[idx_train].to_numpy()
    y_test = y.iloc[idx_test].to_numpy()
    rs = manifest.random_state

    # S3/S4 key their fairness constraint off the manifest's FIRST declared
    # protected attribute, passed as sensitive_features - never as a column
    # of X_train/X_test. It is not deleted from the dataset anywhere; it
    # simply never entered X_all's column selection for these two strategies
    # (see strategy_features). Every strategy is still scored against every
    # declared protected attribute below, regardless of which one drove S3/S4.
    primary = manifest.protected_attributes[0].name
    sensitive_train = protected_masks[primary].iloc[idx_train].to_numpy().astype(int)
    sensitive_test = protected_masks[primary].iloc[idx_test].to_numpy().astype(int)

    if strategy == "in_processing":
        mitigator = fit_in_processing(build_model(model_name, rs), X_train, y_train, sensitive_train)
        y_pred, y_proba = predict_in_processing(mitigator, X_test, rs)
    elif strategy == "post_processing":
        optimizer = fit_post_processing(
            build_model(model_name, rs), X_train, y_train, sensitive_train, random_state=rs)
        y_pred, y_proba = predict_post_processing(optimizer, X_test, sensitive_test, rs)
    else:
        model = build_model(model_name, rs)
        model.fit(X_train, y_train)
        y_proba = model.predict_proba(X_test)[:, 1]
        y_pred = np.asarray(model.predict(X_test)).astype(int)

    return y_test, y_pred, y_proba


@dataclass
class AuditData:
    """One audit prepared exactly the way `run_audit` prepares it (#1078).

    `X_all` holds every encoded column (core, proxy and protected); `X` is the
    subset a strategy trains on (see `faircode.strategies.strategy_features`).
    `masks` maps each protected attribute name to a 0/1 Series that is 1 for the
    disadvantaged group, aligned with `X_all` and `y`. `idx_train`/`idx_test` are
    the manifest's stratified split, so a row computed from them matches `results/`. `df` holds the filtered
    raw rows (same order as `X_all`), for columns the harness does not encode.
    """
    manifest: object
    X_all: pd.DataFrame
    X: pd.DataFrame
    y: pd.Series
    masks: dict
    idx_train: np.ndarray
    idx_test: np.ndarray
    random_state: int
    df: pd.DataFrame | None = None   # the filtered raw rows, for columns the harness does not encode

    def group(self, name) -> np.ndarray:
        """The mask of protected attribute `name` as a plain 0/1 integer array (1 = the disadvantaged group), aligned with
        `X_all` and `y`. `masks` holds boolean Series; this avoids `.to_numpy().astype(int)` at every use (#1133)."""
        if name not in self.masks:
            raise KeyError(f"no protected attribute {name!r}; this audit has {sorted(self.masks)}")
        return self.masks[name].to_numpy().astype(int)

    def train_group(self, name) -> np.ndarray:
        """`group(name)` for the manifest's training rows (`idx_train`)."""
        return self.group(name)[self.idx_train]

    def test_group(self, name) -> np.ndarray:
        """`group(name)` for the manifest's test rows (`idx_test`)."""
        return self.group(name)[self.idx_test]


def prepare_audit(manifest, strategy=None, random_state=None) -> AuditData:
    """Load, encode and split one manifest. `run_audit` and `load_audit` both call this,
    so the two cannot drift apart. `strategy` picks the columns of `X`; None keeps the
    S2 feature set (core features only: no protected columns, no proxies)."""
    rs = manifest.random_state if random_state is None else random_state
    df, y, protected_masks = _load_dataset(manifest)

    protected_cols = [pa.column for pa in manifest.protected_attributes]
    all_cols = list(dict.fromkeys(manifest.core_features + manifest.proxy_features + protected_cols))
    X_all = encode_features(df, all_cols)

    idx_train, idx_test = train_test_split(
        np.arange(len(df)), test_size=manifest.test_size, random_state=rs,
        stratify=y if y.nunique() > 1 else None,
    )
    feature_cols = strategy_features(
        strategy or "unawareness_proxy_removal", manifest.core_features, manifest.proxy_features, protected_cols)
    return AuditData(manifest, X_all, X_all[feature_cols], y, protected_masks, idx_train, idx_test, rs, df)


def load_audit(folder, strategy=None, random_state=None) -> AuditData:
    """Public helper for explainers, notebooks and tests: load the audit in `folder`
    (a directory holding `audit.yaml`, or the manifest path itself) with the same
    loader, encoding, feature selection and split the benchmark harness uses.

        data = load_audit("Benefits Denial")
        model = build_model("logistic_regression", data.random_state)
        model.fit(data.X.iloc[data.idx_train], data.y.iloc[data.idx_train])
    """
    path = Path(folder)
    is_manifest = path.is_file() or path.suffix.lower() in {".yaml", ".yml"}
    manifest_path = path if is_manifest else path / "audit.yaml"
    try:
        manifest = load_manifest(manifest_path)
    except FileNotFoundError as error:
        audit_folder = path.parent if is_manifest else path
        message = (
            f"Could not find audit manifest at {manifest_path}. "
            "`folder` must be an audit folder or a manifest path."
        )
        if not audit_folder.exists():
            manifests = discover_manifests(audit_folder.parent)
            audit_folders = [manifest.parent.name for manifest in manifests]
            if audit_folders:
                message += f" Audit folders next to it: {', '.join(audit_folders)}."
                matches = difflib.get_close_matches(audit_folder.name, audit_folders, n=1)
                if matches:
                    message += f" Did you mean {matches[0]!r}?"
        raise FileNotFoundError(message) from error
    return prepare_audit(manifest, strategy, random_state)


def _timed_strategy_run(*args, **kwargs):
    """`_run_strategy`, timed, with scikit-learn's ConvergenceWarnings counted instead of printed (#1328, #1329).

    Returns (the usual result, seconds, number of ConvergenceWarnings). Every other warning is re-issued unchanged, and nothing
    about the fit changes: the warnings are only recorded while it runs."""
    start = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _run_strategy(*args, **kwargs)
    seconds = time.perf_counter() - start
    stopped = 0
    for item in caught:
        if issubclass(item.category, ConvergenceWarning):
            stopped += 1
        else:
            warnings.warn_explicit(item.message, item.category, item.filename, item.lineno)
    return result, seconds, stopped


def convergence_summary(diagnostics: list[dict]) -> list[str]:
    """One line per audit naming the (strategy, model) combinations in which a fit stopped at max_iter, from the `diagnostics`
    `run_audit` collected; empty when every fit converged (#1328)."""
    lines = []
    for audit in dict.fromkeys(item["audit"] for item in diagnostics):
        mine = [item for item in diagnostics if item["audit"] == audit]
        stopped = [item for item in mine if item["convergence_warnings"]]
        if stopped:
            fits = sum(item["convergence_warnings"] for item in stopped)
            names = ", ".join(f"{item['strategy']}/{item['model']}" for item in stopped)
            lines.append(f"{audit}: {len(stopped)} of {len(mine)} combinations had a fit stop at max_iter "
                         f"({fits} fit(s) in all): {names}; see tests/test_benchmark_convergence.py")
    return lines


def run_audit(
    manifest, n_resamples=2000, n_permutations=2000, random_state=None, progress_callback=None, diagnostics=None
):
    """Run the full strategy x model x metric grid for one manifest.

    Returns (fairness_rows, performance_rows). fairness_rows has one dict per
    (strategy, model, protected attribute, metric), plus one per (strategy,
    model, attribute pair) for the intersectional gap when two or more
    protected attributes are declared. performance_rows has one dict per
    (strategy, model, performance metric). If provided, progress_callback is
    called with the audit, strategy and model after each combination completes. If `diagnostics` is a list, one dict per
    combination is appended to it: the audit, strategy, model, the seconds the fit took and how many scikit-learn
    ConvergenceWarnings it raised (which are then not printed); results are unaffected either way.
    """
    data = prepare_audit(manifest, random_state=random_state)
    rs, X_all, y, protected_masks = data.random_state, data.X_all, data.y, data.masks
    idx_train, idx_test = data.idx_train, data.idx_test

    fairness_rows = []
    performance_rows = []
    for strategy in STRATEGIES:
        for model_name in MODEL_FAMILIES:
            if diagnostics is None:
                y_test, y_pred, y_proba = _run_strategy(
                    strategy, model_name, manifest, X_all, y, protected_masks, idx_train, idx_test)
            else:
                (y_test, y_pred, y_proba), seconds, stopped = _timed_strategy_run(
                    strategy, model_name, manifest, X_all, y, protected_masks, idx_train, idx_test)
                diagnostics.append({"audit": manifest.name, "strategy": strategy, "model": model_name,
                                    "seconds": round(seconds, 3), "convergence_warnings": stopped})

            perf = compute_performance_metrics(y_test, y_pred, y_proba, n_resamples, random_state=rs)
            for metric_name in PERFORMANCE_METRICS:
                p = perf[metric_name]
                performance_rows.append({
                    "audit": manifest.name, "strategy": strategy, "model": model_name,
                    "metric": metric_name, **p,
                })

            for pa in manifest.protected_attributes:
                disadv_test = protected_masks[pa.name].iloc[idx_test].to_numpy()
                metrics = compute_metrics(
                    y_test, y_pred, disadv_test, n_resamples, n_permutations, random_state=rs)
                for metric_name in METRICS:
                    m = metrics[metric_name]
                    fairness_rows.append({
                        "audit": manifest.name, "strategy": strategy, "model": model_name,
                        "protected_attribute": pa.name, "metric": metric_name, **m,
                    })

            if len(manifest.protected_attributes) >= 2:
                for pa_a, pa_b in itertools.combinations(manifest.protected_attributes, 2):
                    mask_a = protected_masks[pa_a.name].iloc[idx_test].to_numpy()
                    mask_b = protected_masks[pa_b.name].iloc[idx_test].to_numpy()
                    inter = intersectional_report(
                        y_pred, mask_a, mask_b, n_resamples, n_permutations, random_state=rs)
                    isr = inter["intersectional"]
                    # An empty "both" or "neither" cell makes the gap
                    # undefined (NaN) - intersectional_report still runs
                    # significance_report on it unconditionally, which can
                    # report p_value=0.0/significant=True on a meaningless
                    # comparison. Don't trust either field in that case.
                    cell_empty = (inter["cell_sizes"]["both"] == 0
                                  or inter["cell_sizes"]["neither"] == 0)
                    fairness_rows.append({
                        "audit": manifest.name, "strategy": strategy, "model": model_name,
                        "protected_attribute": f"{pa_a.name}_x_{pa_b.name}",
                        "metric": "intersectional_demographic_parity_diff",
                        "value": isr["gap"], "ci_low": isr["ci_low"], "ci_high": isr["ci_high"],
                        "p_value": None if cell_empty else isr["p_value"],
                        "significant": False if cell_empty else isr["significant"],
                        "n_disadvantaged": isr["n_a"], "n_advantaged": isr["n_b"],
                        "small_sample_warning": isr["small_sample_warning"],
                        "note": ("empty_intersectional_cell" if cell_empty
                                  else "superadditive" if inter["superadditive"] else None),
                    })
            if progress_callback is not None:
                progress_callback(manifest.name, strategy, model_name)
    return fairness_rows, performance_rows


def run_benchmark(
    root=".", audits=None, n_resamples=2000, n_permutations=2000, progress_callback=None, diagnostics=None
):
    """Discover every audit.yaml under root (or use explicit manifest paths)
    and run them all. Returns (fairness_df, performance_df) across every audit.
    If provided, progress_callback and diagnostics are passed to each audit run."""
    np.random.seed(GLOBAL_SEED)  # defense-in-depth; see module docstring
    paths = [Path(a) for a in audits] if audits else discover_manifests(root)
    all_fairness = []
    all_performance = []
    for path in paths:
        try:
            manifest = load_manifest(path)
            extra = {} if diagnostics is None else {"diagnostics": diagnostics}
            if progress_callback is None:
                fairness_rows, performance_rows = run_audit(manifest, n_resamples, n_permutations, **extra)
            else:
                fairness_rows, performance_rows = run_audit(
                    manifest, n_resamples, n_permutations,
                    progress_callback=progress_callback, **extra,
                )
        except (yaml.YAMLError, KeyError, ValueError, FileNotFoundError) as exc:
            # A malformed manifest (bad YAML syntax, a missing required key)
            # or a degenerate dataset (e.g. filtered down to 0 rows, which
            # sklearn's train_test_split rejects with its own ValueError)
            # would otherwise propagate as a raw, manifest-path-less
            # traceback all the way to the CLI. Validation errors raised by
            # Manifest.from_dict already name the manifest, so prefix only
            # the ones that do not (#1179).
            message = str(exc)
            if not message.startswith(str(path)):
                message = f"{path}: {message}"
            raise ValueError(message) from exc
        all_fairness.extend(fairness_rows)
        all_performance.extend(performance_rows)
    return pd.DataFrame(all_fairness), pd.DataFrame(all_performance)


def summarize(fairness_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (audit, strategy, protected_attribute, metric): the point
    estimate averaged across the three model families, plus how many of
    them found the gap statistically significant."""
    if fairness_df.empty:
        return fairness_df
    return (
        fairness_df.groupby(["audit", "strategy", "protected_attribute", "metric"], as_index=False)
        .agg(mean_value=("value", "mean"),
             n_models_significant=("significant", "sum"),
             n_models=("model", "count"))
    )


PROVENANCE_FILE = "PROVENANCE.json"
PROVENANCE_LIBRARIES = ("numpy", "pandas", "scikit-learn", "scipy", "fairlearn", "matplotlib", "PyYAML")
RESULT_FILES = ("results_fairness.csv", "results_performance.csv", "summary.csv")


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_provenance(audits, n_resamples, n_permutations, description="full run", timings=None) -> dict:
    """What produced a set of result files (#1129): the commit and whether the tree was dirty, the Python and library
    versions, the hash of requirements-lock.txt, the resample and permutation counts and the audits included. `timings` (the
    seconds each strategy/model combination took, from run_audit's diagnostics) is added as a `timings` list when given (#1329);
    it is additive, so older records and the consistency checks are unaffected."""
    repo = Path(__file__).resolve().parent.parent

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    versions = {}
    for name in PROVENANCE_LIBRARIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    lock = repo / "requirements-lock.txt"
    status = git("status", "--porcelain", "--untracked-files=no")
    record = {
        "description": description,
        "commit": git("rev-parse", "HEAD"),
        "dirty": None if status is None else bool(status),
        "python": platform.python_version(),
        "libraries": versions,
        "lockfile_sha256": _sha256(lock) if lock.is_file() else None,
        "n_resamples": n_resamples,
        "n_permutations": n_permutations,
        "audits": sorted(audits),
    }
    if timings is not None:
        record["timings"] = [{"audit": item["audit"], "strategy": item["strategy"], "model": item["model"],
                              "seconds": item["seconds"]} for item in timings]
    return record


def write_provenance(out_dir, runs) -> Path:
    """Writes PROVENANCE.json next to the result CSVs: one entry per run that contributed rows, plus the SHA-256 of
    each result file, so a file edited by hand (or a stale record) is detectable."""
    out_dir = Path(out_dir)
    record = {
        "schema": 1,
        "files": {name: _sha256(out_dir / name) for name in RESULT_FILES if (out_dir / name).is_file()},
        "runs": list(runs),
    }
    path = out_dir / PROVENANCE_FILE
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _validate_existing_result_outputs(out_dir, requested_audits, provenance, *, allow_other_audits=False):
    """Validate existing results before report writes to prevent partial replacement."""
    out_dir = Path(out_dir)
    paths = {name: out_dir / name for name in RESULT_FILES}
    provenance_path = out_dir / PROVENANCE_FILE
    if not any(path.exists() for path in paths.values()) and not provenance_path.exists():
        return

    missing = [name for name in RESULT_FILES if not paths[name].exists()]
    if missing:
        raise ValueError(
            "existing benchmark output is incomplete (missing " + ", ".join(missing)
            + "); refusing to overwrite it. Restore the files or choose a new --out directory."
        )

    audit_sets = {}
    for name, path in paths.items():
        try:
            table = pd.read_csv(path)
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise ValueError(
                f"existing benchmark output is malformed ({name}: {exc}); refusing to overwrite it. "
                "Restore the file or choose a new --out directory."
            ) from exc
        if table.empty or "audit" not in table or table["audit"].isna().any():
            raise ValueError(
                f"existing benchmark output is malformed ({name} has no usable audit rows); "
                "refusing to overwrite it. Restore the file or choose a new --out directory."
            )
        audit_sets[name] = set(table["audit"].astype(str))

    existing_audits = audit_sets[RESULT_FILES[0]]
    if any(audits != existing_audits for audits in audit_sets.values()):
        raise ValueError(
            "existing benchmark result files contain different audit sets; refusing to overwrite them. "
            "Restore a consistent result set or choose a new --out directory."
        )

    if provenance_path.exists():
        try:
            record = json.loads(provenance_path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("provenance is not a JSON object")
            if record.get("schema") != 1 or not isinstance(record.get("files"), dict):
                raise ValueError("unsupported or incomplete provenance record")
            if not isinstance(record.get("runs"), list):
                raise ValueError("missing run records")
            for name, path in paths.items():
                if record["files"].get(name) != _sha256(path):
                    raise ValueError(f"{name} does not match its recorded hash")
            recorded_audits = set()
            for run in record["runs"]:
                if not isinstance(run, dict) or not isinstance(run.get("audits"), list):
                    raise ValueError("malformed run audit list")
                recorded_audits.update(run["audits"])
            if recorded_audits != existing_audits:
                raise ValueError("recorded audits do not match the result files")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(
                f"existing benchmark provenance is malformed or inconsistent ({exc}); "
                "refusing to overwrite it. Restore the files or choose a new --out directory."
            ) from exc
        if provenance is None:
            raise ValueError(
                "existing benchmark output has provenance but this report does not; "
                "refusing to leave stale provenance. Supply provenance or choose a new --out directory."
            )

    other_audits = existing_audits - requested_audits
    if other_audits and not allow_other_audits:
        names = ", ".join(sorted(other_audits))
        raise ValueError(
            f"existing benchmark output contains results for other audits ({names}); "
            "refusing to overwrite them. Run all audits or choose a new --out directory."
        )


def _write_merged_report(fairness_df, performance_df, out_dir, make_plots, plot_metric, provenance):
    """Stage a merged result set and roll back replaced files if installation fails."""
    out_dir = Path(out_dir)
    old_fairness = pd.read_csv(out_dir / RESULT_FILES[0])
    old_performance = pd.read_csv(out_dir / RESULT_FILES[1])
    old_record = json.loads((out_dir / PROVENANCE_FILE).read_text(encoding="utf-8"))
    if list(old_fairness.columns) != list(fairness_df.columns) or list(old_performance.columns) != list(performance_df.columns):
        raise ValueError("--merge requires result tables with the existing column layout")
    selected = set(fairness_df["audit"].astype(str))
    merged_fairness = pd.concat(
        [old_fairness[~old_fairness["audit"].astype(str).isin(selected)], fairness_df],
        ignore_index=True,
    )
    merged_performance = pd.concat(
        [old_performance[~old_performance["audit"].astype(str).isin(selected)], performance_df],
        ignore_index=True,
    )

    with tempfile.TemporaryDirectory(prefix=".faircode-merge-", dir=out_dir.parent) as temporary:
        stage = Path(temporary) / "stage"
        stage.mkdir()
        merged_fairness.to_csv(stage / RESULT_FILES[0], index=False)
        merged_performance.to_csv(stage / RESULT_FILES[1], index=False)
        summarize(merged_fairness).to_csv(stage / RESULT_FILES[2], index=False)
        if make_plots and not merged_fairness.empty:
            from .figures import generate_figures
            generate_figures(stage, metric=plot_metric)
        write_provenance(stage, [*old_record["runs"], provenance])

        staged = [stage / name for name in RESULT_FILES]
        if make_plots and (stage / "figures").is_dir():
            staged.extend(sorted((stage / "figures").glob("*.png")))
        staged.append(stage / PROVENANCE_FILE)
        backup = Path(temporary) / "backup"
        backup.mkdir()
        installed = []
        saved = []
        try:
            for source in staged:
                relative = source.relative_to(stage)
                destination = out_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    saved_path = backup / relative
                    saved_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, saved_path)
                    saved.append((saved_path, destination))
                installed.append(destination)
                os.replace(source, destination)
        except BaseException:
            for destination in reversed(installed):
                destination.unlink(missing_ok=True)
            for saved_path, destination in reversed(saved):
                os.replace(saved_path, destination)
            raise
    return out_dir


def write_report(fairness_df: pd.DataFrame, performance_df: pd.DataFrame, out_dir,
                 make_plots: bool = True, plot_metric: str = "demographic_parity_diff", provenance=None,
                 merge: bool = False):
    """Write results_fairness.csv, results_performance.csv, and a summary.csv
    to out_dir, plus (if make_plots) render figures/*.png via faircode.figures.
    With `provenance` (a dict from collect_provenance) also write PROVENANCE.json (#1129).
    `merge=True` replaces only the requested audits in an existing verified result set."""
    fairness_audits = set(fairness_df["audit"].astype(str)) if "audit" in fairness_df else set()
    performance_audits = set(performance_df["audit"].astype(str)) if "audit" in performance_df else set()
    if fairness_audits != performance_audits:
        raise ValueError("benchmark result tables contain different audit sets; refusing to write output")
    if merge:
        out_dir = Path(out_dir)
        if not fairness_audits:
            raise ValueError("--merge requires at least one audit")
        if not isinstance(provenance, dict):
            raise ValueError("--merge requires provenance for the new benchmark run")
        run_audits = provenance.get("audits")
        if not isinstance(run_audits, list) or set(map(str, run_audits)) != fairness_audits:
            raise ValueError("--merge provenance audits do not match the benchmark result tables")
        if not (out_dir / PROVENANCE_FILE).is_file():
            raise ValueError("--merge requires an existing, provenance-verified benchmark output")
        _validate_existing_result_outputs(out_dir, fairness_audits, provenance, allow_other_audits=True)
        return _write_merged_report(fairness_df, performance_df, out_dir, make_plots, plot_metric, provenance)

    _validate_existing_result_outputs(out_dir, fairness_audits, provenance)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fairness_df.to_csv(out_dir / "results_fairness.csv", index=False)
    performance_df.to_csv(out_dir / "results_performance.csv", index=False)
    summarize(fairness_df).to_csv(out_dir / "summary.csv", index=False)
    if make_plots and not fairness_df.empty:
        from .figures import generate_figures
        generate_figures(out_dir, metric=plot_metric)
    if provenance is not None:
        write_provenance(out_dir, [provenance])
    return out_dir
