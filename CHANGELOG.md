<div align="center">

# Changelog

![Keep a Changelog](https://img.shields.io/badge/Keep%20a%20Changelog-1.1.0-e05735?style=flat-square)
![SemVer](https://img.shields.io/badge/SemVer-2.2.0-blue?style=flat-square)
![Latest](https://img.shields.io/badge/Latest-v2.2.0-brightgreen?style=flat-square)

All notable changes to Fair Code are documented here, newest first.

</div>

---

> **Paper freeze lifted.** The manuscript this repo's results were being frozen for was never
> actually submitted this cycle - the real paper, with fresh results, is now planned for next year.
> `paper/results-frozen/` (tag [`v1.0-paper`](https://github.com/yakew7/Fair-Code/releases/tag/v1.0-paper))
> is kept as a historical reference snapshot. See [CLAUDE.md](CLAUDE.md).

## [2.2.0] - 02 Sep 2026

Three rounds of a fresh MCP-focused audit, each finding real gaps through direct verification
(not guessed), fixing them, and adding one Phase 2 capability - completing the "read-only lookups
against `paper/results-frozen/` and `explainers/`" plan named as a follow-up when the MCP server
first shipped.

### Added
- **MCP Phase 2: `list_explainers`/`get_explainer`** - read-only lookups against this repo's own published explainers, so an agent can discover and read one without shelling out. `list_explainers(tag=None)` returns every explainer's slug/title/subtitle/summary/tags straight from `assets/explainers-data.json`; `get_explainer(slug)` returns the raw Markdown source plus metadata.
- **MCP Phase 2: `get_benchmark_results`** - filters `results_fairness.csv`/`results_performance.csv` by audit/model/strategy/metric/protected_attribute, capped at 200 rows so an unfiltered call can't flood the calling agent's context.
- **`faircode/_explainers/` and `faircode/_results_frozen/`** - package-internal, generated mirrors of `explainers/*.md`+`explainers-data.json` and the frozen benchmark CSVs, declared as real `package-data` (closes #388). `explainers/` and `paper/results-frozen/` live outside what `pyproject.toml` ships, so a real `pip install faircode[mcp]` never had them on disk - every Phase 2 tool would have raised `FileNotFoundError` for any real end user. Verified end-to-end twice: built an actual wheel, installed it in a clean venv, confirmed both tool groups work with zero repo checkout present. `scripts/build_explainers.py` and `scripts/freeze_paper_results.py` now generate these mirrors automatically.

### Fixed
- **Date strings appended after the first 50 age rows were fabricated into the `75+` band** (closes #432) - date detection now uses a deterministic sample spread across the whole column in both profiler engines.
- **Terminal screenshots silently clipped text beyond 92 characters** (closes #443) - `render_terminal_png.py` now wraps each captured line before measuring and drawing the canvas, preserving explicit blank lines and every rendered glyph within the documented width.
- **MCP tools accepted `path="-"` (stdin), which could hang or corrupt the stdio JSON-RPC transport** (closes #385) - `"-"` is a real, documented CLI shorthand for reading a terminal/pipe on stdin; the MCP server runs *over* stdio, so a tool call reading stdin would block on/consume the same stream the server needs for its own protocol frames. Now rejected with a clear error in the single chokepoint every path argument funnels through.
- **MCP tools silently dropped the multi-sheet `.xlsx` "ignored sheet" notice** (closes #386) - the CLI already reports this for every dataset-reading path; none of the three Phase 1 tools did. Now attached as `sheet_note`/`sheet_note_a`+`sheet_note_b`/`sheet_notes`.
- **`get_explainer` had a path-traversal vulnerability via `slug`** (closes #387) - `slug="../README"` returned this repo's `README.md` content, a file entirely outside `explainers/`, since `slug` was used to build a filesystem path with zero validation. Now validated against the exact pattern every real slug matches before the path is ever built.
- **`profile_dataset`'s `cross` validation didn't reject the same column twice, unlike the CLI** (closes #389) - `cross=["sex","sex"]` silently produced a degenerate diagonal-only intersection table instead of erroring like `faircode profile --cross sex,sex` already does.
- **`get_benchmark_results` crashed uncaught or leaked raw pandas errors on a non-scalar filter value** (closes #390) - a dict value raised an uncaught `NotImplementedError` (not in the tool wrapper's except tuple); a list value raised `ValueError` with pandas' own internal wording. Each filter is now validated as a plain scalar first.
- **`get_benchmark_results` blamed the wrong file when its package mirror was missing** (closes #396, by [@oxura](https://github.com/oxura), [#408](https://github.com/yakew7/Fair-Code/pull/408), first merged PR) - the error now names the actual missing `faircode/_results_frozen/` path and points to `scripts.freeze_paper_results.mirror_for_mcp()`, avoiding advice that could trigger an unnecessary, citation-affecting re-freeze.
- **README.md's MCP section still listed only the original 3 tools** (closes #391) - `SPEC.md` section 11 was already correctly updated for all six.
- **README.md's `faircode/` repo-tree omitted `mcp_server.py`, `_explainers/`, and `_results_frozen/`** (closes #409, by [@Zinniacodes01](https://github.com/Zinniacodes01), [#411](https://github.com/yakew7/Fair-Code/pull/411), first merged PR) - added to the tree. The merge also introduced a stray `S` character before the file's opening `<div align="center">` tag and three tree lines using a plain `|` instead of the box-drawing `│` every other line uses; fixed directly on `main` in the same pass as this changelog sync.
- **`loaders_extra.py` silently mis-parsed index-oriented JSON as columns-oriented (transposed, no error)** (closes #405, by [@nitishchauhan002](https://github.com/nitishchauhan002), [#410](https://github.com/yakew7/Fair-Code/pull/410), first merged PR) - pandas' `columns` and `index` orientations both serialize to the same dict-of-dicts JSON shape, so `pd.read_json(path)`'s default guess (`columns`) silently transposed genuinely index-oriented input. The merged PR's heuristic (prefer whichever dimension is larger; break ties on square shapes by value type-homogeneity) still silently mis-parsed shapes its own tests didn't cover - a columns-oriented export wider than it is tall, and a square all-string export with no type signal to break the tie. Fixed directly (not part of the PR): replaced the heuristic entirely with a hard failure - any dict-of-dicts JSON now raises a clear "ambiguous JSON orientation" error pointing at `orient="split"`, which round-trips unambiguously, instead of guessing. README's JSON-orientation docs and `tests/test_loaders.py`'s prior columns-orientation round-trip test updated to match; new tests added covering the wide and all-string-square shapes the original fix missed.
- **`faircode/_explainers/`'s generated mirror double-reported the same em dash under two paths** (closes #393, by [@AnayDhawan](https://github.com/AnayDhawan), [#412](https://github.com/yakew7/Fair-Code/pull/412)) - `faircode/_explainers/*.md` is a byte-identical, package-internal mirror of `explainers/*.md`; `check_em_dash.py`'s `ALLOW_PREFIXES` only excluded `paper/results-frozen/`, not this newer mirror.
- **`strategy_features()` silently accepted any unrecognized strategy name** (closes #418, by [@shauryagangrade](https://github.com/shauryagangrade), [#425](https://github.com/yakew7/Fair-Code/pull/425), first merged PR) - a typo like `"in_procesing"` fell through a bare `else` shared with the three real core-only strategies, returning a plausible-but-wrong column set instead of erroring. Now raises `ValueError` for anything outside the three recognized strategy names.
- **`fit_post_processing()` crashed on a sparse minority class** (closes #446, by [@be-student](https://github.com/be-student), [#448](https://github.com/yakew7/Fair-Code/pull/448)) - the merged PR's guard (require every class in `y_train` to have 2+ members before stratifying) only prevented `train_test_split`'s own "least populated classes" error; it didn't stop a random fallback split from still landing a class or a sensitive-attribute group entirely on one side, which crashes deeper inside fairlearn instead - `ThresholdOptimizer.fit()`'s own "Degenerate labels for sensitive feature value X", or a bare `IndexError` when the FIT split's base model never saw a class and `predict_proba` returns one column. Verified reproducible across 5 different `random_state` values with the PR merged, all still crashing. Fixed directly (not part of the PR): stratifies on the combined (label, sensitive-group) pair instead of the label alone, guaranteeing every such combination survives on both sides of the split whenever it has 2+ members (confirmed stable across 200+ random states); raises a clear "not enough data to calibrate reliably" error otherwise instead of attempting a split likely to crash confusingly. The PR's own test suite passed because it replaced both the base model and `ThresholdOptimizer` with no-op stubs, so it never exercised the real crash path; replaced with tests against the real classifier and real `ThresholdOptimizer` covering both the genuinely-too-sparse and marginally-viable cases.
- **A profile with no detected dimensions looked identical to a failed fairness score** (closes #444, by [@be-student](https://github.com/be-student), [#449](https://github.com/yakew7/Fair-Code/pull/449)) - `overall_score`/`grade` used to fall back to `0`/`"F"` when nothing was measured, indistinguishable from a genuinely severe fairness result. Python, the web engine, JSON/MCP output, comparisons, and both terminal/HTML reports now represent the unmeasured state explicitly with `null` score/grade plus a `dimensions_detected` flag and a `note`; `--fail-under` now reports that the threshold can't be applied (exit 2) instead of silently comparing against a fake zero. Verified end-to-end against the real repro across every one of those surfaces, plus byte-identical JS/Python parity. Two small follow-ups on top (not part of the PR): the compare report's drift arrow no longer points up/down when `score_delta` is `null` (both engines), and the MCP `profile_dataset`/`compare_datasets` docstrings now say `overall_score`/`grade` can be `null`.
- **19 non-explainer issues, each verified, fixed, and committed individually:**
  - **`loaders_extra.py` didn't recognize `orient="table"` JSON** (closes #406) - a real, valid pandas export (`{"schema": ..., "data": ...}`, the only orientation that round-trips dtypes) fell through to the plain `pd.read_json(path)` call and surfaced pandas' own internal "Mixing dicts with non-Series" error instead of being parsed correctly.
  - **`manifest.py`'s `TargetSpec` didn't validate `equals`/`isin`'s required companion field** (closes #416) - `method="equals"` with no `value` silently compared every row to `None`, producing an all-zero label column with no error at all; `method="isin"` with no `values` raised a raw pandas `TypeError`. Both now validate at construction time.
  - **`manifest.py`'s `ProtectedAttribute` didn't require `threshold` for `numeric_threshold`/`age_interval_threshold`** (closes #415) - `numeric < None` evaluates to all-`False` in pandas rather than raising, so a missing `threshold` field silently produced zero disadvantaged rows, surfacing several steps downstream as a confusing "insufficient_data" result with no pointer back to the real cause.
  - **`manifest.py`'s `ProtectedAttribute.disadvantaged` accepted any string, silently inverting which group is disadvantaged on a typo** (closes #414) - `"Below"`/`"BELOW"`/a trailing space all silently took the `"above"` branch instead of raising. Now validated against the two documented values.
  - **`intersectional_report` reported a statistically "significant" finding on an empty cell** (closes #413) - an empty doubly-disadvantaged or baseline cell produced `gap: nan` alongside `p_value: 0.0` and `significant: True` - a meaningless comparison reported as a confirmed finding. `benchmark.py`'s `run_audit` now checks cell sizes before trusting either field.
  - **`detect.py`'s prefix matching produced false-positive column classifications beyond the known `birth_state` precedence case** (closes #404) - `raceway`, `statement`/`stateless`, `countryside`, `citycenter`, and `regional_manager` all misclassified as demographic columns purely because the word starts with `race`/`state`/`country`/`city`/`region`. Those five stems are now exact-match-only; ported identically to `assets/profiler-engine.js`.
  - **`faircode benchmark` crashed with a raw traceback for a malformed manifest or degenerate dataset** (closes #403) - a YAML syntax error, a missing required key, or a manifest pointing at a 0-row dataset all propagated uncaught to `main()`. `run_benchmark()` now wraps these per-manifest with the manifest's path, and the CLI prints a clean `error: <path>: <message>` at exit code 2.
  - **MCP `get_benchmark_results` returned ~77KB of unrounded float64 precision even with the 200-row cap** (closes #395) - every float carried 15-17 significant digits it doesn't need for a fairness-metric lookup. Numeric columns now round to 6 decimal places.
  - **No CI check kept `faircode/_results_frozen/` in sync with `paper/results-frozen/`** (closes #394) - the MCP mirror was only ever refreshed by the rare, manual `freeze()` action; a direct edit to the source CSVs would silently go stale with nothing to catch it. `check_generated_files_current.py` now covers the mirror, regenerated fresh via `mirror_for_mcp()` in `build-explainers.yml`.
  - **Web profiler's JS engine silently fell back on an unmatched `cross` pair** (closes #420) - Python's `profile()` raises when a requested cross pair doesn't match two real dimensions; the JS engine silently used whichever two dimensions came first, with no error. Now raises the same message.
  - **Web profiler's JS engine silently ignored an unmatched `reference` baseline** (closes #419) - reachable through the live UI: uploading a reference file with a typo'd column name showed a confident "scored vs X" status while the reference did nothing. `reprofile()` now reports success/failure so the upload handler can roll back and show the real error.
  - **Zero test coverage for `faircode/models.py` and `faircode/figures.py`** (closes #417) - `build_model`'s bare `KeyError` on an unrecognized name, hyperparameter/`random_state` propagation, `plot_strategy_comparison`'s empty-subset guard, and `figures.py`'s CLI entry point were all previously untested.
  - **`.github/CODEOWNERS`: `requirements.txt` had no owner while `requirements-lock.txt` did** (closes #397).
  - **`build-explainers.yml` didn't trigger on changes to `faircode/_explainers/`** (closes #392) - `check_generated_files_current.py` already covered the mirror's own drift, but nothing ran the check if only the mirror itself changed.
  - **Inconsistent explicit permissions across GitHub Actions workflows** (closes #402) - `favicons.yml`, `build-explainers.yml`, `audits.yml`, `lint.yml`, and `frozen-files.yml` relied on the default `GITHUB_TOKEN` scope instead of an explicit `contents: read`, unlike `codeql.yml`.
  - **`index.html`'s Methodology section skipped a heading level** (closes #424) - `h2` straight to five `h4`s with no `h3`, violating WCAG 1.3.1. Changed to `h3`.
  - **`index.html`'s roadmap section omitted 3 shipped explainers entirely** (closes #423) - `precision-recall-curve`, `equal-opportunity`, and `intersectional-bias` were live and published but never added to the roadmap list, not even as "coming soon."
  - **`CONTRIBUTING.md`'s explainer reference table was missing 6 real, published explainers** (closes #422) - `accuracy-equality`, `bootstrap-confidence-intervals`, `counterfactual-explanation`, `fairness-through-unawareness`, `lime`, and `mitigation-strategies`.
  - **`.pre-commit-config.yaml` didn't run `check_broken_links.py`/`check_explainer_count.py`, unlike CI** (closes #421) - a contributor got a clean local `pre-commit` run and only discovered a broken link or a stale explainer-count mention in CI. Both now run locally, scoped by files pattern.

## [2.1.1] - 02 Sep 2026

A full sweep of the issue backlog opened alongside this release: 24 non-explainer issues
(#347, #348, #349, #350, #351, #352, #342, #343, #364-#384), each verified, fixed, and committed
individually.

### Added
- **MCP `proxy_hints` tool gained `held_out_with`** (closes #348) - mirrors the CLI's `--proxy-hints-with`, letting an MCP-calling agent test a protected attribute already dropped from the dataset. Extracted the CLI's `PATH=COLUMN` parsing into `proxy.py`'s shared `parse_held_out_specs` so both interfaces validate identically instead of duplicating the logic.
- **MCP `compare_datasets` tool gained `proxy_hints`** (closes #349) - mirrors `compare --proxy-hints`, attaching `proxy_hints_a`/`proxy_hints_b` in one call instead of requiring three separate MCP calls to reconstruct.
- **Web profiler's Compare tab gained an Advanced-thresholds panel** (closes #351) - the Profile view already had one wired to `min_share`/`intersection_floor`/`imbalance_flag`/`missing_flag`/`min_group_size`; Compare was the one surface stuck with defaults. Threaded a new `currentOpts` through `maybeCompare()`'s two `E.profile()` calls the same way `currentOverrides` already is.
- **Test coverage for `scripts/render_terminal_png.py`** (closes #368) - zero coverage despite a documented platform-specific font-path regression (#323); also adds `scripts/__init__.py`, without which `importlib.import_module("scripts.*")` is a namespace-package lookup that can silently lose to an unrelated same-named package elsewhere on `sys.path`.
- **Test coverage for `loaders_extra.py`'s real parquet `ImportError`→`RuntimeError` conversion** (closes #369) - the CLI's own test bypassed it entirely by mocking `read_table` directly.
- **Test coverage for `get_xlsx_sheet_info`'s non-`.xlsx` and except-`Exception` branches** (closes #370).
- **Test coverage for the MCP `ToolError` wrapper on `compare_datasets`/`proxy_hints`** (closes #371) - only `profile_dataset` had a `call_tool`-based test proving the wrapper's exception conversion actually works end-to-end.
- **Test coverage for `detect.py`'s keyword precedence and `MAX_CATEGORICAL_CARD` boundary** (closes #372) - `classify_name("birth_state")` resolving to `"age"` was untested and undocumented as intentional; the categorical-cardinality cutoff was only tested well past its boundary.
- **Test coverage for `scripts/check_generated_files_current.py`** (closes #373) - this CI gate, whose own docstring documents three failed attempts at reliable cross-platform OG-image drift detection, had zero tests protecting that hard-won logic.
- **Test coverage for `report.py`'s group-label truncation slices** (closes #374) - no fixture used a label long enough to hit the `[:18]`/`[:16]` truncation.
- **JS/Python parity tests now exercise non-default options** (closes #376) - every prior parity test used the default `profile()` path only; `--map`/`--cross`/`--reference`/thresholds had zero cross-engine coverage. `scripts/engine-js.js`'s `profile` command now accepts an optional `opts.json`.
- **CI staleness check for favicons** (closes #381) - `generate_og_images.py` had one; `generate_favicons.py` didn't. Safe to byte-compare across platforms (no font rendering, unlike OG images) - new `favicons.yml` workflow.

### Fixed
- **`PROJECT_ANCHORS`/`projectAnchors` maps were missing Tenant Screening** (closes #350, by [@propcgamer20-png](https://github.com/propcgamer20-png), [#357](https://github.com/yakew7/Fair-Code/pull/357)) - both `scripts/build_explainers.py`'s Python map and `assets/explainers-ui.js`'s JS map listed six of the seven audits, so the `[Tenant Screening/](../Tenant%20Screening/)` related-project link in `equal-opportunity.html` and `fairness-through-unawareness.html` never resolved to `../index.html#project-tenant` the way every other audit link does. Also dropped a dead, misspelled legacy JS key (`'Ai Fair Recrutment Dataset'`) that had no Python-side counterpart.
- **`faircode profile --proxy-hints-with` silently no-oped without `--proxy-hints`** (closes #347, by [@evanjain-dot](https://github.com/evanjain-dot), [#359](https://github.com/yakew7/Fair-Code/pull/359)) - `_build_held_out` was only ever called inside `if args.proxy_hints:`, so a typo'd invocation (forgetting `--proxy-hints`) exited 0 with a normal profile report instead of surfacing the mistake. Now errors immediately with `--proxy-hints-with needs --proxy-hints`, matching the CLI's existing style of erroring loudly on likely-typo'd flag combinations (`--map`, `--cross`). Also merged [@ahmdkaml](https://github.com/ahmdkaml)'s independently-submitted fix for the same issue ([#358](https://github.com/yakew7/Fair-Code/pull/358)), which instead makes `--proxy-hints-with` imply `--proxy-hints`; with #359's explicit-error check merged first, that branch is now unreachable in the `profile` command but is harmless.
- **`llms.txt` was missing the 6 most recently added explainers** (closes #342, by [@evanjain-dot](https://github.com/evanjain-dot), [#361](https://github.com/yakew7/Fair-Code/pull/361)) - `llms.txt` is maintained separately from `llms-full.txt` and had drifted: accuracy-equality, bootstrap-confidence-intervals, mitigation-strategies, fairness-through-unawareness, lime, and counterfactual-explanation were all published but invisible to anything that only reads the short index.
- **`scripts/check_em_dash.py` never scanned `.yml`/`.yaml` files** (closes #343, by [@propcgamer20-png](https://github.com/propcgamer20-png), [#362](https://github.com/yakew7/Fair-Code/pull/362)) - the em-dash-free convention is meant to apply repo-wide, but `SCAN_EXT` excluded YAML entirely, leaving two real em dashes in `new_audit.yml`/`new_explainer.yml` unflagged by CI. Added `.yml`/`.yaml` to `SCAN_EXT` and allowlisted those two files, which intentionally show the banned character inside a checkbox label - the same reason `CONTRIBUTING.md` is already allowlisted.
- **Nothing cross-checked the plain-prose "N explainers" count across README.md, CONTRIBUTORS.md, METRICS.md, and ROADMAP.md** (closes #352, by [@evanjain-dot](https://github.com/evanjain-dot), [#363](https://github.com/yakew7/Fair-Code/pull/363)) - a small, explicit list of exact regexes (not a fuzzy scan - METRICS.md's weekly log is full of legitimate historical counts a loose match would false-positive on) now guards four docs files, wired into `build-explainers.yml`. Also fixed the drift the check immediately caught: CONTRIBUTORS.md's maintainer bio still said "the bulk of the 39 explainers" against a real count of 53. A same-day follow-up pushed directly to `main` closed the one gap flagged in review - README.md's Traction table has its own independent "Explainers Published" row that the original check missed - and added a `--fix` mode (`make fix-explainer-count`) so a contributor never has to hand-edit these four files themselves; CI still only checks, since a `pull_request` run from a fork gets a read-only token and couldn't push a fix back anyway.
- **`faircode profile --reference`/`--cross` silently no-opped on a typo'd column** (closes #364, #384) - a reference column or cross pair that didn't match any profiled dimension was silently ignored (zero reference flags) or silently replaced with the first two detected dimensions, instead of erroring like `--map` already does. Both now raise a clear error naming the unmatched column(s); the MCP tools get the fix for free through their existing exception-conversion.
- **`--proxy-hints-with` silently overwrote a real column on a name collision** (closes #365) - `proxy_hints()`'s held-out map unconditionally overwrote a same-named real column with no warning. Now rejected at parse time.
- **`faircode benchmark` raised a raw traceback when matplotlib alone was missing** (closes #366) - the top-level scikit-learn/pyyaml/fairlearn import already converted a missing dependency into a clean error; `write_report`'s lazy matplotlib import (only reached without `--no-plots`) didn't.
- **`--proxy-hints-with` gave no ignored-sheet notice for a multi-sheet `.xlsx` held-out file** (closes #367) - every other dataset-reading path already reports this.
- **Web profiler's Compare tab "Copy as JSON" omitted the provenance block** (closes #375) - the Profile tab's export already attaches `faircode_version`/`engine`/a dataset hash/resolved params; Compare's export was the raw `compare()` result with none of it.
- **Web profiler's threshold-input placeholders were a hardcoded, driftable copy of the engine's real defaults** (closes #377) - now sourced from the engine's own `DEFAULT_OPTS` at init, in both the Profile and Compare views.
- **Inconsistent `accept` MIME lists across the web profiler's four file inputs** (closes #378).
- **CODEOWNERS: all 7 audit dataset directories were unowned except `audit.yaml`** (closes #379) - 42 tracked files (fair.py/unfair.py/CSVs/notebooks) had no reviewer. Six of the seven directory names need GitHub's backslash-escaped-space syntax, which `tests/test_codeowners.py`'s own parser didn't support - fixed the parser too.
- **CODEOWNERS: the explainer system's JS/CSS files were missing from Educational content** (closes #380).
- **README.md's `assets/` repo-tree omitted the explainer system's client-side files** (closes #382).
- **`bug_report.yml`'s "Which file?" dropdown had no `audit.yaml` option** (closes #383).

## [2.1.0] - 30 Aug 2026

The first tagged release since `v2.0.0`. Everything in the `2.0.1` through `2.0.12` entries below
accumulated untagged while the paper freeze held; this release ties them all off under one real,
tagged version, plus the freeze-lift itself.

### Changed
- **Paper freeze lifted** - see [CLAUDE.md](CLAUDE.md). The manuscript this repo's results were
  frozen for was never actually submitted; the real paper, with fresh results, is now planned for
  next year. All previously frozen files and parameters (`faircode/` core, `results/`, audit
  manifests, dataset CSVs, `requirements-lock.txt`) are open to normal development again. Removed
  the freeze-enforcement CI (`frozen-files.yml` reduced to a no-op - kept only because
  `check-frozen-files` is a required branch-protection status check; `results-drift.yml` deleted
  outright) and the freeze banners across `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`,
  `CONTRIBUTORS.md`, `ROADMAP.md`, the PR/issue templates, and the website. `paper/results-frozen/`
  (tag `v1.0-paper`) stays in place as a kept historical reference snapshot, not actively enforced.

### Added (everything below, now tagged together)
- MCP server (`faircode-mcp`), `provenance` metadata on both the CLI and web profiler's JSON
  exports, `--proxy-hints-with` held-out-column proxy detection, 6 new explainers, and the full
  list of profiler/CLI/report bug fixes recorded in `2.0.1` through `2.0.12` below.

## [2.0.12] - 25 Aug 2026 *(folded into `v2.1.0`)*
### Added
- **MCP server (`faircode-mcp`)** - `faircode/mcp_server.py` exposes `profile_dataset`, `compare_datasets`, and `proxy_hints` as [MCP](https://modelcontextprotocol.io) tools over stdio, so an MCP-aware agent can call the profiler directly instead of shelling out to the CLI and parsing text. Thin adapter over the existing `profile()`/`compare()`/`proxy_hints()` functions `cli.py` already wraps - no new analysis logic, same local-only trust boundary as the CLI (stdio, no network listener, no auth). `profile_dataset`/`compare_datasets` return the same shape `--json` does, with the new `provenance` block attached by default. `proxy_hints` returns `{"hints": [...]}` rather than a bare list, since the MCP SDK splits a list return value into one content block per element (a 98-hint result became 98 separate blocks in testing) and turns an empty list into zero blocks - indistinguishable from an error. An anticipated failure (bad path, unknown `overrides` column, `proxy_hints` without the `proxy` extra) is converted to a client-visible `ToolError` at the tool boundary; anything else is treated as a crash and withheld, per the MCP SDK's own design. New optional `mcp` extra (`pip install faircode[mcp]`) and `faircode-mcp` console script. Documented as new SPEC.md section 11. Phase 1 of the plan discussed for #327-#329; Phase 2 (read-only lookups against `paper/results-frozen/` and `explainers/`) is a follow-up.
- **`provenance` block on the web profiler's "Copy as JSON" export** (closes #329, by [@lovishmenaria14-gif](https://github.com/lovishmenaria14-gif), [#339](https://github.com/yakew7/Fair-Code/pull/339), first merged PR) - mirrors #330's Python-side shape (`faircode_version`, `engine: "js"`, `dataset_hash`, `params`, `overrides`) computed client-side via `crypto.subtle.digest`, so a CLI report and a browser report of the same upload are recognisably the same measurement without sharing code. A follow-up fix (not part of the PR) closed a real gap the review caught: the uploaded `File` object was cached once in `readFile()` and never updated afterward, so loading the sample dataset or the `?demo` link after a real upload left the exported hash pointing at the old file while the profile itself reflected the sample data. The file now flows through `runText()`/`runTable()` as an explicit parameter instead of a side effect, so it can't go stale.
- **`provenance` block on `--json` exports** (relates to #327, by [@mahirhir](https://github.com/mahirhir), [#330](https://github.com/yakew7/Fair-Code/pull/330), first merged PR) - an exported result previously carried no answer to "what produced these numbers": the same CSV scores differently under a different `--map`, `--min-share`, or reference baseline, and none of that was visible in the export. New `faircode/provenance.py` attaches `faircode_version`, `engine` ("python", so a matching web-profiler port under #329 can slot in as `"js"`), a `sha256:` dataset digest (over the raw file bytes, so a CLI report and a browser report of the same upload are recognisably the same measurement without sharing code), the resolved `params` (defaults included), and `overrides`. `compare` gets `dataset_hash_a`/`dataset_hash_b`, matching the existing `a`/`b` naming, plus `reference_hash` when a baseline is supplied. Attached at the export boundary rather than inside `profile()`/`compare()`, so the result shape in `faircode/SPEC.md` section 6 is unchanged and `tests/test_js_parity.py`'s `==` comparison needs no edit. `--no-provenance` restores the exact prior export shape. Documented as new SPEC.md section 10. Does not address the web profiler's own JSON export (#329) or the `proxy_hints()` dropped-column blind spot (#328), both still open.
- **`--proxy-hints` on `faircode compare`** (closes #247) - previously only wired into `profile`, even though `proxy_hints()` never depended on anything profile-specific. Computed separately for both datasets (`proxy_hints_a`/`proxy_hints_b`, not a single diff - there's no natural single chi-squared value to subtract) and surfaced in terminal, `--json`, and `--html` output the same way `profile` already does. No JS-side change needed - proxy-hints is documented as deliberately CLI-only.
- **`-` as a stdin path for `faircode profile`/`compare`** (closes #251) - every input path dispatched by file extension, so there was no way to pipe data in without a temp file. Scoped to CSV/TSV via delimiter sniffing, per the issue; `.xlsx`/`.parquet`/`.json` over stdin can be a follow-up.
- **Advanced-thresholds panel in the web profiler** (closes #284) - `assets/profiler-engine.js`'s `resolveOpts()` already accepted `min_share`/`intersection_floor`/`imbalance_flag`/`missing_flag`/`min_group_size` overrides; `assets/profiler-ui.js` never wired any UI to them, unlike the CLI's five matching flags. Added a collapsible panel with one number input per threshold (blank = default, shown as the placeholder), wired generically via each input's `data-opt` attribute.
- **`compare_to_html` test coverage for added/removed dimensions and appeared/disappeared groups** (closes #302) - `compare_to_terminal` already had this; the HTML branch, and the appeared/disappeared group markup itself, had none.
- **End-to-end test coverage for intersectional reporting and `run_benchmark()`** (closes #271) - the two-protected-attribute fairness-reporting block and the `run_benchmark()` discovery/seeding entrypoint were both untested; existing tests only used the one-attribute fixture and called the lower-level `run_audit()` directly. Uses Insurance Denial (1,341 rows, age × gender) - the smallest real two-attribute audit.

### Fixed
- **index.html's roadmap grid still showed 3 already-published explainers as "coming soon"** (closes #341, by [@sushicat75](https://github.com/sushicat75), [#356](https://github.com/yakew7/Fair-Code/pull/356), first merged PR) - Race Correction in Clinical Algorithms, The Obermeyer Case, and Underdiagnosis Bias were all real, shipped explainers, but their roadmap entries were never flipped from `roadmap-status soon` to `roadmap-status done` when they actually went live.
- **README.md's repo-tree comment for `explainer.html` was stale** (closes #326, by [@lovishmenaria14-gif](https://github.com/lovishmenaria14-gif), [#340](https://github.com/yakew7/Fair-Code/pull/340)) - it described `explainer.html` as "rendered per slug by build_explainers.py," but that script never reads or writes the file - it generates `explainers/<slug>.html` from an inline template. Corrected to match `.github/DEAD-FILE-AUDIT.md`'s description: a static `?slug=` redirect shim.
- **`faircode profile --cross COLA,COLA` (same column twice) had no guard** (closes #320, by [@StudentSuite3](https://github.com/StudentSuite3), [#337](https://github.com/yakew7/Fair-Code/pull/337), first merged PR) - the web profiler already guards against crossing a dimension with itself (#306): every off-diagonal cell in that crosstab is a tautological 0, which reads as a real representation gap but isn't one. The CLI's `--cross` validation only checked for two non-empty column names, so `profile(df, opts={"cross": ["sex", "sex"]})` silently produced flags claiming e.g. `sex='F' × sex='M' is absent`. Now errors with a clear message, mirroring the web UI's existing guard.
- **`scripts/render_terminal_png.py` hardcoded a macOS-only font path** (closes #323, by [@Ayaan-20-11](https://github.com/Ayaan-20-11), [#331](https://github.com/yakew7/Fair-Code/pull/331), first merged PR) - `FONT_PATH` was `/System/Library/Fonts/Menlo.ttc`, which crashed with an opaque PIL `OSError` on any non-macOS contributor's machine. Now resolves to the repo-bundled `assets/fonts/IBMPlexMono-Regular.ttf`, the same font `generate_og_images.py` already uses for exactly this reason.
- **Web profiler's reference-file picker strands keyboard focus** (closes #303) - every other file-picker path already returned focus to a visible element after the hidden input's native picker closed; the reference-baseline input was the one exception.
- **Web profiler mis-parses a records-orientation JSON file as CSV without a `.json` extension** (closes #304) - the content sniff only checked for a leading `{`; `E.parseJSON()` already handled the records-array branch correctly, it just never got the chance to run.
- **Web profiler's compare view scroll-jacks the page on every column-mapping change** (closes #305) - `profiler-ui.js`'s single-dataset view already gated its scroll behind an explicit flag for exactly this reason; `profiler-compare.js` had no equivalent.
- **Web profiler lets you cross a dimension with itself** (closes #306) - produced a same-column × same-column intersection grid where every off-diagonal cell is a tautological 0 that renders as a wall of false "empty subgroup" flags. The change handler now swaps the other side back to the vacated value instead of allowing the collision.
- **`--map COL=KIND` silently no-ops on a nonexistent column** (closes #301) - `detect_columns()` only applies an override `if col in overrides` while iterating real `df.columns`, so a typo'd column was dropped with zero feedback. Now errors with the unknown column name(s) listed, checked against both datasets' columns for `compare`.
- **`build-explainers.yml`/pre-commit hook never triggered on `assets/explainers-ui.js` changes** (closes #286) - `build_explainers.py`'s own docstring says it mirrors that file's rendering rules, but it was absent from both the CI path filters and the local rebuild hook. Scoped to the trigger-path gap only; the actual JS/Python parity test is a separate stretch goal.
- **ROADMAP.md and README.md disagreed on whether the LLM bias audit is done** (closes #309) - ROADMAP had it checked off; README's own "What's Next" section, and ROADMAP's own "7 of 9 audits" count, both say it isn't. There's no LLM audit folder or code anywhere in the repo.
- **`faircode compare` never reports ignored `.xlsx` sheets, `bug_report.yml`'s audit dropdown missing two domains, README's stale "five audits" wording, `CODEOWNERS` missing `profiler.css`** (closes #300, #307, #308, #310, by [@propcgamer20-png](https://github.com/propcgamer20-png), [#314](https://github.com/yakew7/Fair-Code/pull/314)) - a bundled four-issue PR; `compare` silently profiled sheet 0 of each workbook with no indication others existed, mirroring the fix already made for `profile`.

## [2.0.11] - 14 Aug 2026 *(folded into `v2.1.0`)*
### Fixed
- **`to_html()`/web profiler HTML reports drop imbalance/missing/skew and the reference section** (closes #283 and #272, by [@AnayDhawan](https://github.com/AnayDhawan), [#294](https://github.com/yakew7/Fair-Code/pull/294); follow-up by [@Shreyash0712](https://github.com/Shreyash0712), [#295](https://github.com/yakew7/Fair-Code/pull/295)) - `faircode/report.py`'s `to_html()` now renders the same `imbalance {ratio}x  missing {pct}%  skew {value}` meta line `to_terminal()` already did, and the web profiler's downloadable report (`buildHtmlReport()`) now includes both that meta line and the reference-baseline comparison section that the live on-page view and the CLI's own `--html` output already had.
- **`--min-group-size` no longer hardcodes `default=100`** (closes #299, by [@VedantMadane](https://github.com/VedantMadane), [#312](https://github.com/yakew7/Fair-Code/pull/312), first merged PR) - it now defers to `profiler.MIN_GROUP_SIZE` like its four sibling threshold flags already do.
- **`audits.yml`'s profiler job installs the `proxy` extra** (closes #298, by [@propcgamer20-png](https://github.com/propcgamer20-png), [#311](https://github.com/yakew7/Fair-Code/pull/311)) - `tests/test_proxy.py`'s scipy-gated tests were silently skipped in CI, not run; verified they actually execute now that scipy is installed.
- **`faircode/cli.py`'s `benchmark` subcommand now has test coverage** (closes #270, by [@ahmdkaml](https://github.com/ahmdkaml), [#288](https://github.com/yakew7/Fair-Code/pull/288)) - the import-error fallback, paper-drift warning, no-manifests error path, and a full success run were all previously untested. The PR didn't reference the issue number, so it was closed manually with a credit comment after verifying the tests actually cover what was asked.
- **Homepage explainer-card pill showed the wrong topic after filtering** - the visible pill always rendered `tags[0]`, so filtering by Metrics could surface a card like `class-imbalance.md` (tags `["data", "metrics", "detection"]`) showing a "Data Bias" pill instead of "Metrics" - a real card, wrong-looking match. The shared search script (`index.html`) now shows whichever tag matches the active filter, falling back to the card's first tag when no filter is active; `assets/explainers-ui.js`'s initial render uses the same friendly label map so the two stay consistent before any interaction.

### Added
- **New "Healthcare" explainer topic filter** - seven explainers (`accuracy-not-enough-healthcare-ai`, `clinical-score-miscalibration`, `missing-data-bias-ehr`, `medical-imaging-representation-gaps`, `obermeyer-cost-proxy`, `underdiagnosis-bias`, `race-correction-clinical-algorithms`) already form the cluster README's own "Healthcare AI Bias Focus" section calls out, but had no way to filter to just them on the homepage. Added a `healthcare` tag to all seven in `assets/explainers-data.json` and a matching filter button alongside Detection/Metrics/Data Bias/Explainability.
- **New "Case Study" explainer topic filter** - nine explainers are anchored in one specific, externally-documented real-world incident rather than a general concept (`ai-hallucinations` - *Mata v. Avianca*; `obermeyer-cost-proxy` and `underdiagnosis-bias` - Obermeyer et al. 2019; `race-correction-clinical-algorithms` - eGFR/spirometry/VBAC; `sampling-bias` - Gender Shades; `unsupervised-learning` - ZIP-code insurance clustering; `medical-imaging-representation-gaps` - Zech et al. 2018 and Larrazabal et al. 2020; `feedback-loop-bias` - PredPol; `reinforcement-learning` - YouTube/Mozilla 2019). Verified each by reading its actual "Real-World Case" section rather than guessing from the title - explicitly excluded explainers whose only "case" is one of this repo's own seven audits, since nearly all 47 explainers already have that and it wouldn't be a distinguishing filter.
- `assets/explainers-data.js`/`sitemap.xml` rebuilt via `make build-explainers` to pick up both new tags - the prior commit had edited `explainers-data.json` directly without rebuilding, which `Build Explainers` CI correctly caught as stale.
- **New contributor [@nivedmahendran](https://github.com/nivedmahendran)** - fixed [CONTRIBUTING.md](CONTRIBUTING.md)'s pre-push trigger-path list, which had drifted from the actual `.pre-commit-config.yaml` regex ([#287](https://github.com/yakew7/Fair-Code/pull/287), closing issue #285, first merged PR). `CONTRIBUTORS.md` updated (Contributors section, Contributions-by-area table, snapshot through PR #287); README's contributors-graph note also corrected while there - it still referenced [@Circout-sudo](https://github.com/Circout-sudo)'s once-lagging first PR, which has long since shown up in GitHub's graph.

### Fixed
- **`CONTRIBUTORS.md` misattributed [@Circout-sudo](https://github.com/Circout-sudo)'s #265/#266 to [@ImMortaL0P](https://github.com/ImMortaL0P)'s entry too** - a copy-paste leftover giving ImMortaL0P credit for a PR pair that's already correctly credited to Circout-sudo elsewhere in the same file. ImMortaL0P's real total is unchanged at 1 merged PR (#175); the incorrect sentence is removed.
- **`check_generated_files_current.py` false-flagged a brand new explainer's own introducing commit as stale** - `build_explainers.py` derives each page's `datePublished`/`dateModified` (JSON-LD) and `<lastmod>` (sitemap.xml) from `git log` on the source `.md` file, which has no commit yet the moment it's first built - contributors necessarily build before their own first commit exists, per CONTRIBUTING.md's own instructions - so a new explainer's first commit is always missing those fields. A fresh regeneration run against that same commit afterwards correctly finds it and fills them in, which read as "stale" under the check's byte-exact comparison even though nothing about the source content had changed. Caught directly: `Build Explainers` failed on the commit adding `equal-opportunity.md`/`intersectional-bias.md` for exactly this reason. `_normalize_dates()` now strips those specific fields before comparing (the same "verify what's meaningful, not what's incidentally timing-dependent" approach already used for OG images), and the two pages' own committed HTML/`sitemap.xml` were rebuilt once their commit existed so the real dates are correct going forward, not just tolerated as missing.
- **`faircode/cli.py`'s `--html` traceback crash, plus test coverage for every previously-untested CLI error branch** (closes #268 and #269, by [@evanjain-dot](https://github.com/evanjain-dot), [#277](https://github.com/yakew7/Fair-Code/pull/277)) - `profile`/`compare --html` crashed with a raw Python traceback if the output directory didn't exist, instead of the clean `error: ...` + exit 2 every other error path in the file uses; now wrapped in `try`/`except OSError`. Added `tests/test_cli.py` coverage for the branches `make coverage` flagged as untested: `--map`'s two error cases, `_read_or_exit`'s three exception branches, malformed `--cross`, a `--reference` file missing required columns, `--proxy-hints`'s `RuntimeError` path, and both `--html` write branches (failure and success). [@Shreyash0712](https://github.com/Shreyash0712)'s review on the PR caught a follow-up: `to_html()`/`compare_to_html()` were being called *inside* the `open()` context, so a formatting exception (not just the `OSError` this PR handles) would leave a truncated 0-byte report file behind - fixed by generating the HTML string before opening the file.
- **`generate_favicons.py`'s malformed-`logo.svg` error paths, now covered by tests** (closes #245, by [@propcgamer20-png](https://github.com/propcgamer20-png), [#278](https://github.com/yakew7/Fair-Code/pull/278)) - `_parse_mark()`'s three `ValueError` branches (non-square/off-origin viewBox, wrong rect count, mismatched stem/bar fill) had no test, only the happy path did. [@ahmdkaml](https://github.com/ahmdkaml)'s review caught that the new tests mutated module-level state (`ICONS_DIR`/`LOGO_SVG`, `THEMES[...]["out_dir"]`) without restoring it - harmless today since nothing else reads it, but would silently leak into a future logo/OG test. Switched both to `monkeypatch.setattr`/`setitem` so pytest restores the originals automatically.
- **`faircode/cli.py`'s benchmark docstring and README's install snippet were missing `matplotlib`** (closes #244, by [@evanjain-dot](https://github.com/evanjain-dot), [#279](https://github.com/yakew7/Fair-Code/pull/279)) - the `benchmark` extra gained `matplotlib` in #235, but both places describing what it installs still listed only `scikit-learn + pyyaml + fairlearn`.
- **`pr-review-ping.yml` now only pings the CODEOWNERS of the paths a PR actually touches** - the #273 fix pinged the union of every CODEOWNERS handle on every new PR, so e.g. [@Shreyash0712](https://github.com/Shreyash0712) (owner of `explainers/` only) got pinged on unrelated core/CI PRs. Now fetches the PR's changed files and applies the same last-matching-pattern-wins CODEOWNERS semantics GitHub itself uses, so each owner is only mentioned when a PR touches a path they own.

### Added
- **[@Shreyash0712](https://github.com/Shreyash0712) added as co-code-owner of `explainers/`** - ten explainers across three PRs since first merging on 2026-06-05 (5 merged PRs, 9 commits total), the most by any non-maintainer contributor, plus a citation cleanup pass across six explainers ([#276](https://github.com/yakew7/Fair-Code/pull/276)) that showed continued upkeep rather than a one-off dump. `.github/CODEOWNERS`'s `/explainers/` line now reads `@yakew7 @Shreyash0712`. `CONTRIBUTORS.md` moved their entry from Contributors to Core contributors accordingly, and updated the maintainer's own entry to note the explainers/ co-ownership.

### Fixed
- **`README.md`'s repository-structure tree brought back in sync with the actual repo** (closes #274) - the tree had drifted badly: `.github/workflows/` listed 2 of 11 workflow files, `scripts/` listed 3 of 10, `tests/` listed 4 of 18 (plus its `fixtures/` folder), `faircode/` omitted `__init__.py`/`__main__.py`/`loaders.py`/`loaders_extra.py`, and the repo root omitted `CLAUDE.md`, `CONTRIBUTORS.md`, `METRICS.md`, `ROADMAP.md`, `llms.txt`, `llms-full.txt`, `robots.txt`, `sitemap.xml`, `explainer.html`, `Makefile`, and `.pre-commit-config.yaml`. Also added the missing `.github/` top-level files (`ACTIONS-AUDIT.md`, `DEAD-FILE-AUDIT.md`, `CODEOWNERS`, `codeql/codeql-config.yml`), the `notebooks/07_intersectional_bias_audit.ipynb` entry, and expanded `assets/` to show its `fonts/`/`icons/`/`og/`/`og-light/` subfolders. Verified every added entry against `git ls-files` rather than assumed.
- **`pr-review-ping.yml` no longer hardcodes a reviewer list that can drift from CODEOWNERS** (closes #273) - `REVIEWERS = ['yakew7', 'ahmdkaml']` duplicated `.github/CODEOWNERS` with nothing keeping the two in sync (the same class of gap #219's `codeowners-access.yml` exists to catch on the CODEOWNERS side, but nothing covered this workflow's own copy). The workflow now checks out the base ref and parses every unique `@handle` out of `.github/CODEOWNERS` at runtime instead, so an added or removed CODEOWNER is picked up automatically with no manual edit required here.

### Added
- **Reference links added to six explainers' citations** (by [@Shreyash0712](https://github.com/Shreyash0712), [#276](https://github.com/yakew7/Fair-Code/pull/276)) - `ai-objectivity-myth.md`, `base-rate-fallacy.md`, `false-positives-vs-false-negatives.md`, `precision-recall-curve.md`, `predictive-parity.md`, and `roc-curve-auc.md` each had a Further Reading citation left as plain text instead of a hyperlink; all six now link out. Verified all five added URLs resolve (one ResearchGate link 403s to automated fetches, a known bot-blocking behavior on that host, not a broken link). `CONTRIBUTORS.md` updated: [@Shreyash0712](https://github.com/Shreyash0712) now at 5 merged PRs / 9 commits.
- **CONTRIBUTORS.md updated through PR #275** - re-sorted [@evanjain-dot](https://github.com/evanjain-dot) up to first place (6 merged PRs, 28 commits) for the precision-recall-curve explainer above ([#275](https://github.com/yakew7/Fair-Code/pull/275)); [@Circout-sudo](https://github.com/Circout-sudo)'s small Makefile refinement ([#267](https://github.com/yakew7/Fair-Code/pull/267): comment clarity + a `-q` flag on the `coverage` target) puts them at 3 merged PRs, moving their entry up from the tied-at-2 tier to its own position right after the two 4-PR contributors, per the count-based ordering.
- **`.github/CODEOWNERS`: three real gaps closed** - `/assets/og-light/` was never added alongside `/assets/og/` when the light-theme OG images shipped, leaving it with no reviewer coverage at all; `assets/explainers-data.json` (the structured counterpart every explainer contribution also edits, per CONTRIBUTING.md) had no owner despite `/explainers/` having one; `requirements-lock.txt` - explicitly called out in [CLAUDE.md](CLAUDE.md) §1 as frozen and repeatedly targeted by Dependabot's version-bump PRs - wasn't covered at all, unlike `pyproject.toml` right next to it. All three now route to `@yakew7`, matching their nearest existing sibling rule.
- **Explainer: What Is a Precision-Recall Curve?** (closes #92, by [@evanjain-dot](https://github.com/evanjain-dot)) - `explainers/precision-recall-curve.md`. Covers why ROC/AUC's own arithmetic stays lenient about rare positives (false positive rate's denominator is dominated by true negatives) while precision's denominator - all positive predictions - is much smaller under class imbalance, letting precision collapse at a threshold AUC never flags as a problem. Anchored to Healthcare Readmission's real 11.2% base rate: the frozen baseline logistic regression hits 88.7% accuracy and 0.62 AUC (`paper/results-frozen/results_performance.csv`) but only a 0.039 F1 - verified against the actual dataset and frozen results rather than assumed. Includes per-group average-precision detection code (tested against a simulated dataset, including the one-class-per-group edge case). Wired into README (explainers table + count 44→45 + repository tree), ROADMAP (Phase 1 item checked, count 45), METRICS badge, CONTRIBUTING table, `llms.txt`, and `assets/explainers-data.json`.
- **`make coverage`: informational test-coverage reporting** (closes #249, by [@ahmdkaml](https://github.com/ahmdkaml) and [@Circout-sudo](https://github.com/Circout-sudo)) - a `pytest --cov=faircode --cov-report=term-missing` target ([#263](https://github.com/yakew7/Fair-Code/pull/263)), a `test` extra (`pytest`, `pytest-cov`) in `pyproject.toml` ([#265](https://github.com/yakew7/Fair-Code/pull/265)/[#266](https://github.com/yakew7/Fair-Code/pull/266)), and a non-gating "Report test coverage" step in `audits.yml`'s `profiler` job ([#264](https://github.com/yakew7/Fair-Code/pull/264)) - no `--cov-fail-under` anywhere, so it can never fail a PR on a threshold, visibility only, as the issue asked. Baseline: 82% overall, with `figures.py`/`cli.py`/`report.py`/`benchmark.py` as the weakest spots.
- **Five more explainers** (closes the last of Phase 2's planned healthcare backlog, by [@Shreyash0712](https://github.com/Shreyash0712), [#262](https://github.com/yakew7/Fair-Code/pull/262)) - [What Is the Base Rate Fallacy?](explainers/base-rate-fallacy.md), [The Obermeyer Case: When Cost Becomes a Proxy for Health Need](explainers/obermeyer-cost-proxy.md), [Race Correction in Clinical Algorithms](explainers/race-correction-clinical-algorithms.md), [What Is Reject Inference?](explainers/reject-inference.md), and [Underdiagnosis Bias in Healthcare AI](explainers/underdiagnosis-bias.md) - explainer count `39 → 44`. `README.md`/`ROADMAP.md`/`METRICS.md`/`CONTRIBUTING.md`/`llms.txt` wired accordingly.
- **`ruff check` as a Python linter** (closes #248, by [@evanjain-dot](https://github.com/evanjain-dot)) - the only automated Python check was the em-dash rule; nothing caught unused imports, undefined names, or redefinitions. Added `[tool.ruff.lint] select = ["F"]` (Pyflakes only) to `pyproject.toml` - deliberately narrower than ruff's own default (`E4, E7, E9, F`), since `E4`'s `E402` false-positives on the `pytest.importorskip(...)` then `from x import y` guard idiom used throughout `tests/*.py`; flagging that would be exactly the style churn the issue asked to avoid. Wired into `make lint`/`lint.yml` (a `pip install ruff` step added there, since it's the first `make lint` check needing one) and `.pre-commit-config.yaml` (mirroring the em-dash hook's `always_run`/`pass_filenames` style, per the issue's own suggestion), and added to `make setup`'s installed dev tools. Running it found two real, tiny bugs, both fixed: a duplicated `import importlib` in `tests/test_generate_images.py`, and an unused `Manifest` import in `tests/test_manifest.py`.
- **`frozen-files`/`Build Explainers` now run on direct pushes to `main`, not just PRs** (closes #246, by [@ahmdkaml](https://github.com/ahmdkaml)) - both workflows only had `on: pull_request`, so a direct push to `main` (which branch protection's bypass list allows for some accounts) ran `lint`/`CodeQL`/`Audits`/`Results Drift` but skipped the two checks specifically meant to guard the paper freeze and the explainer build - verified directly: a push touching only docs + a pre-commit config change triggered exactly those four workflows and nothing else. Added `push: branches: [main]` to both ([#258](https://github.com/yakew7/Fair-Code/pull/258)), then a follow-up fix ([#259](https://github.com/yakew7/Fair-Code/pull/259)) after the first version failed on direct pushes for relying on PR-specific event fields; also pins Pillow to the frozen `11.1.0` to keep OG image generation deterministic.
- **`tests/test_dependency_versions.py` restored, and the scikit-learn drift it caught actually fixed** (closes #255, by [@ahmdkaml](https://github.com/ahmdkaml)) - #233 added this test (comparing `requirements-lock.txt` pins against `pyproject.toml` minimums) and it correctly caught `scikit-learn` locked at `1.8.0` while `pyproject.toml` required `>=1.9.0`; the test was then deleted outright instead of the drift being fixed, silently losing the check. Restored the test and lowered the declared floor to `>=1.8.0` to match what's actually locked - `requirements-lock.txt` itself, frozen for the paper, is untouched.
- **`tests/test_generate_images.py`** (closes #212, by [@ahmdkaml](https://github.com/ahmdkaml)) - basic coverage for `scripts/generate_favicons.py` and `scripts/generate_og_images.py`: verifies the expected output files are actually produced, non-empty, and have the dimensions each function claims to render at.
- **`profiler.html`: documents `--proxy-hints`** (closes #217, by [@ahmdkaml](https://github.com/ahmdkaml)) - a short note on the web profiler's landing copy pointing at the CLI-only `--proxy-hints` flag, so it's discoverable from the page that otherwise only shows the browser-side feature set.
- **`tests/test_declared_dependencies.py`** (closes #235) - asserts every third-party package actually imported by `faircode/`, `scripts/`, or `tests/` is declared somewhere in `pyproject.toml` (core `dependencies` or an `[project.optional-dependencies]` extra), the general check #235 asked for after Pillow was once missing from declared dependencies while tests imported `PIL`. Running it against the current tree caught two more real gaps of the same shape: `numpy` (imported unconditionally by `faircode/metrics.py`, `benchmark.py`, `strategies.py`, `significance.py`, previously only pulled in transitively via `pandas`) and `matplotlib` (imported by `faircode/figures.py`, whose own docstring already claimed it ships with the `benchmark` extra - it didn't). Both are now declared in `pyproject.toml`: `numpy` in core `dependencies`, `matplotlib` added to the `benchmark` extra.
- **Change-aware pre-push tests** (closes #237, follow-up to #220's pre-push runtime doc which is now folded into this) - the pre-push `pytest` hook in `.pre-commit-config.yaml` was `always_run: true`, so it ran the full suite (benchmark tests included) on every push regardless of what changed, unlike the `build-explainers`/`generate-og-images` hooks which already use `files:` filtering. Gave it the same treatment: it now runs only when the push touches `faircode/`, `scripts/`, `tests/`, a dataset CSV, an audit's `fair.py`/`unfair.py`, `pyproject.toml`, `requirements*.txt`, or `.github/CODEOWNERS`. A prose-only push (docs, explainers, website copy) skips it entirely. `CONTRIBUTING.md` updated to describe the new condition instead of "runs on every push."
- **Change-aware CI: `profiler`/`benchmark-harness` skip on docs-only changes** - extends the same idea to `.github/workflows/audits.yml`. A new `changes` job diffs the push/PR against its base commit and gates `profiler` (the full pytest suite) and `benchmark-harness` (the fairlearn end-to-end smoke test) behind whether anything test-relevant changed - same path set as the pre-push hook above, kept in sync deliberately. `run-audits` is left untouched and always runs: it's the one job in this workflow that's a required status check (#160), and a job skipped via `if:` can leave a required check permanently "waiting to be reported" instead of green, which would block merging every docs-only PR. `profiler`/`benchmark-harness` aren't required checks, so skipping them is risk-free.
- **Theme-toggle button now exposes its state to assistive tech** (closes #250) - `#themeToggle`/`#explainerThemeToggle` had a dynamic `aria-label` ("Switch to light/dark mode") but nothing a screen reader announces as state, unlike the visible ☀/☾ glyph swap. Added `aria-pressed="true"/"false"` (`true` = dark mode active), kept in sync everywhere the label/glyph already update - initial load and on click - across `index.html`, `profiler.html`, and the explainer-page template in `scripts/build_explainers.py` (`make build-explainers` re-run to regenerate all 39 explainer pages).
- **`scripts/check_broken_links.py`** (closes #253) - checks every tracked `.md` file for a `[text](#anchor)` that doesn't match any heading on that page, or a relative link/anchor to another file that doesn't exist. Wired into `make lint`/`lint.yml` alongside the em-dash check (that job is renamed `lint` accordingly). The anchor slugifier was reverse-engineered against all 71 real anchor links already in the repo (70 matched cleanly; the one holdout is a `#link-to-section` placeholder inside a CONTRIBUTING.md code-fence example, correctly ignored) rather than assumed, since GitHub's exact algorithm isn't public. Running it against the current tree found five real, previously-unnoticed broken links in the raw markdown - three explainers linked a misspelled/nonexistent `Ai Fair Recrutment Dataset` folder instead of `AI Fair Recruitment`, and `proxy-entanglement.md` linked a notebook path missing its `../` prefix - fixed in `explainers/neural-networks.md`, `proxy-variables.md`, `shap-values.md`, and `proxy-entanglement.md`.
- **`faircode/report.py`'s HTML report tables get proper headers** (closes #254, by [@propcgamer20-png](https://github.com/propcgamer20-png)) - the per-column breakdown table and the drift-comparison table had no `<th>` header row at all (only the smaller reference-deviation table did, and even that had no `scope`); a screen reader had nothing to announce when reading a data cell. Added a `<thead>`/`<th scope="col">` row plus a `<caption>` to all three tables (in both `to_html` and `compare_to_html`), with matching `th`/`caption` CSS in each report's embedded stylesheet - the caption text stands on its own since the report is often shared outside the page it was generated on (CI output, email, a PR comment).
### Fixed
- **`build-explainers.yml`'s drift check compared OG PNGs against a fresh regeneration, which turned out to be unfixable from either side** - the same class of failure as #262's, recurring even after regenerating locally with CI's exact pinned Pillow (`11.1.0`). Three attempts, in order: (1) a fixed `compress_level=9` instead of `optimize=True`'s heuristic filter search - CI still failed, `0 insertions(+), 0 deletions(-)`, purely binary diffs; (2) `scripts/check_generated_files_current.py` decoding and comparing *pixel content* instead of file bytes - CI still failed, and this time genuinely on pixels, not compression: confirmed directly that a macOS-side regeneration reproduces the macOS-committed original byte-for-byte and pixel-for-pixel, while CI's Ubuntu-side regeneration of the identical inputs does not, meaning Pillow's bundled FreeType renders the same text with different pixels depending on platform - not a staleness bug, an inherent rendering difference neither side can fix. (3) The actual fix: stop comparing OG PNGs against a fresh regeneration at all. `check_generated_files_current.py` now verifies what's platform-independent and actually matters - a dark and light image exists for every current explainer slug, is non-empty, and is exactly 1200×630 (the same invariant `tests/test_generate_images.py` already checks for the generator itself, just applied to what's committed) - while keeping byte-exact `git diff` for the text-based generated files (explainer HTML, `explainers-data.js`, `sitemap.xml`, `llms-full.txt`), which never showed any of this and stayed reliable throughout. Verified all four directions: up-to-date passes; a missing image, a wrong-dimension image, and a stale text file are each still correctly caught and fail.
- **`llms.txt` and CONTRIBUTING.md's explainer table were missing the five new #262 explainers** - found while verifying a changelog claim that they'd already been wired: `README.md` was correctly updated by #262 itself, but `llms.txt` (hand-maintained, not regenerated by `build_explainers.py`) and CONTRIBUTING.md's explainer-summary table were not. Added all five to both.
- **`audits.yml`'s new "Report test coverage" step failed on every run since #263/#264 merged, silently** - the profiler job's install line was never updated to include `pytest-cov`, so `make coverage`'s `--cov=faircode` flag errored with "unrecognized arguments" every time; `continue-on-error: true` on the step masked it as an overall job success, so nobody noticed. Verified by simulating the exact install line in a clean venv before and after the fix. Added `pytest-cov` to the install line; also gitignores `.coverage`, the artifact `make coverage` produces locally.
- **`Build Explainers` CI failing on `main` after #262 merged** - the PR added five new explainers without running `make build-explainers` first, so the committed `.html` pages, their OG images, and `sitemap.xml` didn't match a fresh build. Verified Pillow was pinned to CI's exact version (`11.1.0`) before regenerating, so this reproduces CI's output rather than introducing a second mismatch.
- **`scripts/build_explainers.py`'s `resolve_link_target()` silently broke every generic cross-repo-root link in an explainer** - found while fixing #253 above: rebuilding after the notebook-link fix showed the generated `.html` still pointing at the old broken path. Its fallback branch stripped a leading `../` from any relative link that wasn't a known explainer `.md` or a recognized project folder, even though `explainers/*.md` and the `.html` generated from it live in the same directory, so a plain relative link needs no rewriting at all. This wasn't just the notebook link - `disparate-impact.md`'s links to `unfair.py`/`fair.py` in `AI Fair Recruitment/` had the exact same bug, already live on the deployed site. Also removed a `PROJECT_ANCHORS` entry that hardcoded the misspelled `"Ai Fair Recrutment Dataset"` folder name as a redirect target - a band-aid for the exact typo fixed at the source above, now dead code.

## [2.0.10] - 12 Aug 2026 *(folded into `v2.1.0`)*
### Added
- **Both light and dark OG/social-preview images now offered per page** - follow-up to the light-theme image generation below: `index.html`, `profiler.html`, and `build_explainers.py`'s `PAGE_TEMPLATE` (all 39 explainer pages) now declare a second `og:image` pointing at the matching `assets/og-light/` card, right after the existing dark one, each with its own `og:image:width/height/type/alt`. This doesn't make the image switch with the viewer's theme - OG has no `prefers-color-scheme` equivalent - it offers a second image some consuming platforms (e.g. Facebook's share composer) let the person sharing pick between. `twitter:image` is untouched and stays dark-only, since Twitter Cards support exactly one image. The missing-OG-image build guard now checks `assets/og-light/` too, not just `assets/og/`.
- **README: collapsible sections for the biggest content blocks** - the file had grown to 1000+ lines, most of it seven full audit write-ups (dataset, before/after tables, code, key insight - 60-90 lines each), a 125-line repository tree, a 39-row explainer table, and a 44-item completed-work checklist, all rendered inline regardless of whether a reader wanted that detail. Each of the 7 "## Projects" audits, "## Repository Structure"'s tree, "## Explainers"'s full table, and "## What's Next"'s completed checkmarks now collapse behind a `<details>/<summary>` toggle, so the page reads as headings and one-line hooks first, full detail on click. "## What's Next" also now surfaces the 3 actually-open items (facial recognition, HMDA, LLM audit) above the fold instead of buried after 41 checked-off ones. Every heading stays a real markdown heading outside the `<summary>` tag, so `#projects`, `#explainers`, `#01--compas--criminal-justice-bias`, and every other anchor this file and others link to still resolves unchanged - no prose, numbers, or links were altered.
- **Light-theme OG/social-preview images** - `scripts/generate_og_images.py` only ever rendered share cards (homepage, profiler, every explainer) in the site's dark palette, even though `index.html` ships both a light (`:root`, default) and dark (`html[data-theme="dark"]`) theme. Refactored the hardcoded palette into a `THEMES` dict keyed by theme name, with each theme's bg/accent/fg/muted/border matching `index.html`'s CSS custom properties exactly; the brand mark's green crossbar stays fixed across themes. Dark output is unchanged and still byte-identical in `assets/og/`; light output is new, in `assets/og-light/`. Not yet wired into any `og:image`/`twitter:image` tag - OG's protocol has no `prefers-color-scheme` equivalent, so a page can only declare one static image - kept as a companion asset set for now. `.github/workflows/build-explainers.yml`'s drift check, `Makefile`, and `CONTRIBUTING.md` updated to cover the new directory; `.github/DEAD-FILE-AUDIT.md` updated with what it's for.
- **Explainer: Why Medical Imaging Models Fail on Underrepresented Groups** (closes #108) - `explainers/medical-imaging-representation-gaps.md`. Covers the difference between a plain representation gap and shortcut confounding (a model keying off a scanner or hospital-site artifact instead of the pathology), why internal validation cannot rule out the latter, and per-group AUC plus a chi-squared proxy-detection check for a non-clinical confounder. Anchored to two documented real-world cases: Zech et al. (2018)'s hospital-site shortcut in cross-institution pneumonia detection, and Larrazabal et al. (2020)'s controlled sex-imbalance study in chest X-ray diagnosis. Wired into README (explainers table + healthcare list, count 38->39), ROADMAP (Phase 2 item checked, count 39), METRICS badge, CONTRIBUTING table, `llms.txt`, and the `index.html` roadmap timeline.
- **Explainer: Missing Data as Bias in Electronic Health Records** (closes #107) - `explainers/missing-data-bias-ehr.md`. Covers the MCAR/MAR/MNAR framework, why naive imputation and row-dropping both make access-driven missingness worse, and why a missingness indicator can become a new proxy for the protected attribute it was meant to work around. Anchored to real missingness rates computed directly from the Healthcare Readmission CSV already in this repo (`payer_code` missing for 48.2% of African American patients vs. 37.5% of Caucasian patients), not a benchmark run. Wired into README (explainers table + healthcare list, count 37->38), ROADMAP (Phase 2 item checked, count 38), METRICS badge, CONTRIBUTING table, `llms.txt`, and the `index.html` roadmap timeline.
- **Explainer: Miscalibration in Clinical Risk Scores Across Groups** (closes #106) - `explainers/clinical-score-miscalibration.md`, a healthcare-specific companion to [`calibration.md`](explainers/calibration.md). Covers reliability diagrams and per-group calibration slope/intercept, why a score calibrated to the wrong target (as in Obermeyer et al. 2019) can look fine on average, and why the Healthcare Readmission dataset's highest-risk bucket has too few African American patients (128 vs. 363 Caucasian) to trust a clean-looking calibration result there. Wired into README (explainers table + healthcare list, count 36->37), ROADMAP (Phase 2 item checked, count 37), METRICS badge, CONTRIBUTING table, `llms.txt`, and the `index.html` roadmap timeline.
- **CI: `CITATION.cff` validation** (closes #221, by [@ahmdkaml](https://github.com/ahmdkaml)) - `.github/workflows/citation.yml` validates the Citation File Format on every push/PR touching it, so a schema violation (a dropped required field, a malformed date) gets caught at review time instead of only when someone clicks GitHub's "Cite this repository" button and finds it broken.
- **CI: workflow YAML validation** (closes #213, by [@ahmdkaml](https://github.com/ahmdkaml)) - `.github/workflows/validate-workflow.yml` parses every file under `.github/workflows/` and fails on a syntax error, so a hand-edited workflow with bad indentation fails at PR time rather than only when GitHub actually tries to run it.
- **`make setup` installs the optional extras** (closes #214, by [@ahmdkaml](https://github.com/ahmdkaml)) - was `pip install -e . pytest pre-commit`, silently leaving xlsx/parquet/proxy-hint tests skipped locally even though CI exercises them. Now installs `.[excel,parquet,proxy]` too.
- **`faircode benchmark`: warns on non-default resample/permutation counts** (by [@ahmdkaml](https://github.com/ahmdkaml)) - CLAUDE.md §2 lists the bootstrap resample and permutation counts as parameters that must not change from the frozen paper run (both default to 2000). `--n-resamples`/`--n-permutations` let a user override them freely with no indication the output would no longer match the frozen reference - now prints a stderr warning when either differs from the default. CLI-only change; `faircode/benchmark.py` itself untouched.
- **`.github/workflows/codeowners-access.yml`** (closes #219) - verifies every `.github/CODEOWNERS`-listed user *and team* actually has write access to the repo before GitHub will route a review request to them - a valid-looking `@handle` with read access or a team with no repo access is otherwise silently skipped, no error anywhere. Runs on every CODEOWNERS change plus weekly, since access can drift without the file itself changing. Team checking works by fetching every team with any access to the repo in one call (`GET /repos/{owner}/{repo}/teams`) and checking each CODEOWNERS team entry against that list, rather than querying per-team.
### Fixed
- **`first.interaction.yml`'s first-time-contributor check relied on undocumented search-ranking behavior** (closes #216) - it searched `repo:X is:issue|pr author:Y`, took the top 5 results with no explicit sort, and checked whether any had a lower number than the current one. GitHub's default sort for a query with no free-text terms is documented only as "best match," with no guaranteed order - it happens to come back newest-first today (verified against a contributor with 100+ PRs: the default-sort top 5 never included their actual first PR, #123, at all), which is *why* this hasn't visibly misfired yet, not because it was correct. Pinned `sort: created, order: asc, per_page: 1` and check only the single oldest match directly - cheaper (1 result instead of 5) and no longer dependent on an undocumented tie-break.
- **`github/codeql-action` bumped v3 → v4 without going through the audit process #188 set up for exactly this** (`.github/ACTIONS-AUDIT.md`) - the bump itself (commit `b632cfb`) is safe: v4's breaking changes (Node 24 runtime, removed `add-snippets` input, deprecated `CODEQL_ACTION_CLEANUP_TRAP_CACHES`) don't touch anything this repo's `codeql.yml` actually sets. But it landed as a direct commit instead of being checked against `ACTIONS-AUDIT.md` first, which is the specific gap #188 asked to close - #188 tracked the *next* bump landing safely, not the audit happening *before* it merged. Backfilled the audit entry after the fact; flagging the process gap rather than treating "the bump happened to be safe" as the same thing as "the process worked."
### Added
- **Brand refresh: the "corrected F" logo** - replaces the old dot mark (a beige square with an orange circle) across every favicon, app icon, and social-preview image. The new mark is a standard F with its crossbar moved to true vertical center and set in a single accent green (`#4F7A5B`) - the fix, made visible inside the letterform itself. Imported from the Fair Code Logo System design project.
  - `logo.svg` rewritten to the new mark (three rects: stem, top bar, accent crossbar) - still the master source `scripts/generate_favicons.py` rasterizes from.
  - `scripts/generate_favicons.py` rewritten for the new shape: renders `favicon-16x16.png`/`favicon-32x32.png`/`favicon.ico` as the mark in dark "ink" (`#14171A`) on transparent (for light browser chrome), and `apple-touch-icon.png` plus two new outputs, `icon-192.png` (PWA/app icon) and `icon-512.png` (GitHub avatar/social profile), as the mark in near-white (`#F2F1EC`) on an opaque near-black tile (`#0D0F0E`) - matching the logo system's own light/dark-context rule. The old script only understood a background rect + one circle; this one understands the new three-rect shape and still raises clearly if the mark ever gets more complex than that.
  - `scripts/generate_og_images.py`: the small brand mark drawn in the corner of every OG/Twitter card (next to the "Fair Code." wordmark) is now the same F symbol instead of a filled circle, in the card's own dark-theme white plus the same accent green. Regenerated all 38 `assets/og/*.png` cards.
  - The inline SVG `<link rel="icon">` fallback (`index.html`, `profiler.html`, and the explainer-page template in `scripts/build_explainers.py`) updated to the new mark; all 36 explainer pages regenerated to pick it up.
  - `icon-192.png` wired into `<link rel="icon" sizes="192x192">` alongside the existing favicon/apple-touch-icon links. `icon-512.png` is provided for manual use (GitHub org/repo avatar, social profile pictures) rather than linked from any page - see Note.
  - `Makefile`/`CONTRIBUTING.md`'s `make favicons` description updated to mention the two new outputs.
- **`.github/workflows/pr-review-ping.yml`** - comments on every new PR tagging `@yakew7`/`@ahmdkaml`, so both maintainers get notified even when GitHub's own CODEOWNERS auto-request doesn't fire (an invited collaborator who hasn't accepted yet, or a PR that doesn't touch a CODEOWNERS-matched path). Notification only - doesn't request review, assign, or gate merging.
- **CODEOWNERS: `@ahmdkaml` added to profiler, scripts, and tests** - he's authored nearly every recent PR touching `assets/profiler-engine.js`, `profiler-compare.js`, `profiler-ui.js`, `profiler.html`, `scripts/`, and `tests/`, but those paths listed only `@yakew7` (or, for `profiler-ui.js`, no owner at all). Note: GitHub only honors a CODEOWNERS entry for someone with *write* access to the repo, so this also required inviting him as a collaborator (see Changed) - the entries won't actually route review requests until he accepts.
- **Web profiler: shows which `.xlsx` sheet was read** (PR #197, related to #182, by [@ahmdkaml](https://github.com/ahmdkaml)) - `parseXLSX()` only ever profiled the first sheet in a workbook, silently. It now returns `{ table, sheetName, ignoredSheets }`, and the dropzone, compare view, and reference-baseline upload all surface which sheet was used and how many others were ignored, so a multi-sheet upload doesn't look like a partial-data bug.
- **Web profiler: lazy-loaded SheetJS** (PR #192, by [@ahmdkaml](https://github.com/ahmdkaml)) - the `.xlsx` CDN `<script>` tag (added for #158) blocked every profiler page load even for visitors who never touch an Excel file. `parseXLSX()` now injects the pinned, SRI-hashed SheetJS `<script>` on first actual `.xlsx` use instead, caching the in-flight load so concurrent uploads share one script tag; `profile-xlsx`/`compare` call sites in `scripts/engine-js.js` and `assets/profiler-compare.js`/`profiler-ui.js` updated for the now-async `parseXLSX()`.
- **`tests/test_js_parity.py::test_sheetjs_cdn_url_matches`** (PR #193, by [@ahmdkaml](https://github.com/ahmdkaml)) - asserts the CDN URL hardcoded in `assets/profiler-engine.js` and the one in `scripts/engine-js.js` (used to prefetch the library for the Node/CLI parity tests) stay identical, so a future version bump to one can't silently desync from the other.
- **`.xlsx` edge-case coverage** (PR #194, closes #187, by [@ahmdkaml](https://github.com/ahmdkaml)) - `tests/test_xlsx_edge_cases.py` covers a headers-only sheet, a fully empty workbook, and data sitting in a second/hidden sheet behind an empty first one, against both `faircode.loaders.read_table()` and the JS engine.
- **CI: figure-filename drift check** (PR #195, by [@ahmdkaml](https://github.com/ahmdkaml)) - `.github/workflows/results-drift.yml` (added for #173) only diffed the three CSVs; extended it to also diff `results/figures/` filenames against `paper/results-frozen/figures/`, so a renamed or missing figure doesn't slip past the same drift check. Read-only.
- **`.github/ACTIONS-AUDIT.md`: maintenance note** (PR #196, by [@ahmdkaml](https://github.com/ahmdkaml)) - documents that a future major-version bump on any already-audited Action needs the audit and this doc redone, not just the four current entries left to go stale.
- **CI: `results/` vs. `paper/results-frozen/` drift check** (closes #173) - new `.github/workflows/results-drift.yml` diffs the two directories' CSVs on every push/PR, catching silent divergence that the path-based `frozen-files.yml` check can't see (it only flags a PR that *touches* a protected path, not one that leaves the live `results/` inconsistent with the frozen copy some other way). Read-only; never modifies either directory. Failure message points at CLAUDE.md §6 ("flag it, don't silently fix it").
- **`.github/ACTIONS-AUDIT.md`** (closes #167) - documents how to review a Dependabot GitHub-Actions-ecosystem major-version bump for actual behavior changes before merging, instead of merging on green CI alone.
- **CI: CodeQL now scans JavaScript** (closes #162) - `.github/workflows/codeql.yml`'s language list extended beyond Python, since the client-side profiler engine and UI have real DOM-manipulation surface CodeQL was never looking at.
- **`scripts/generate_favicons.py`** (closes #164) - regenerates `favicon.ico`, both PNG sizes, and `apple-touch-icon.png` from `logo.svg` in one command (`make favicons`), replacing an undocumented manual process; the four current favicon binaries were regenerated as its first run.
- **`scripts/engine-js.js`** (closes #170) - consolidates the four near-identical Node CLI-bridge scripts (`profile-js.js`, `compare-js.js`, `profile-json-js.js`, `profile-xlsx-js.js`, each mostly repeated boilerplate) into one dispatched entry point. `tests/test_js_parity.py`, `CONTRIBUTING.md`, and `faircode/SPEC.md` updated to the new call sites.
- **Web profiler: client-side `.xlsx` input** (closes #158) - `assets/profiler-engine.js`/`profiler-compare.js`/`profiler-ui.js` parse Excel files in-browser via [SheetJS](https://sheetjs.com) loaded from a pinned CDN version; the file still never leaves the browser, matching the tool's existing client-side-only guarantee. Parquet stays CLI-only. README's Open Dataset Profiler section reworded accordingly; new `tests/fixtures/adult_sample.xlsx` and a parity test.
- **`tests/test_manifest.py`: `row_filters` column validation** (closes #168) - extends the existing per-manifest checks to also assert every column an `audit.yaml`'s `row_filters` references actually exists in that audit's dataset CSV, not just the target/protected-attribute columns. Test-only; no manifest or dataset touched.
- **Docs: CodeQL alert triage process** (closes #161) - `SECURITY.md` gains a section on how to triage a CodeQL alert.
- **Docs: Dependabot vs. `requirements-lock.txt` warning** (closes #165) - `CONTRIBUTING.md` now tells contributors directly not to merge a Dependabot PR into `requirements-lock.txt`, echoing the CLAUDE.md §1 note added earlier in this release after that file drifted (see Fixed, 2.0.9 above).
- **`scripts/build_explainers.py`: missing-OG-image guard** (PR #191, by [@Swastik-Yadav](https://github.com/Swastik-Yadav)) - refuses to generate explainer pages if any `assets/explainers-data.json` entry is missing its `assets/og/<slug>.png`, with a pointer to run `generate_og_images.py` first, instead of silently shipping a page with a broken social-preview image.
- **Web profiler: JSON "columns" orientation** - `assets/profiler-engine.js`'s `parseJSON()` now handles `{"col": {"0": v, ...}}` (pandas' default `read_json` orientation for a plain object), matching the CLI (#155 documented and tested it there, but nothing had checked the browser engine actually agreed - it threw). Added `test_python_js_json_parity_columns_orientation` alongside the existing records/split parity tests.
- **CI: Frozen Files check** (#157, by [@ahmdkaml](https://github.com/ahmdkaml)) - `.github/workflows/frozen-files.yml` fails a PR that touches anything on CLAUDE.md §1's list (`paper/results-frozen/`, `results/`, the eight `faircode/` core files, any `audit.yaml`, any audit-folder dataset CSV), so a repeat of the #127 incident gets caught before merge instead of after. Extended its protected-path list to also cover `requirements-lock.txt` (see Fixed).
- **CI: CodeQL scanning** (#153, closes #139, by [@ahmdkaml](https://github.com/ahmdkaml)) - weekly + per-push/PR security analysis of the Python codebase.
- **CI: audit manifest column validation** (#156, closes #136, by [@ahmdkaml](https://github.com/ahmdkaml)) - `tests/test_manifest.py` now loads every shipped audit's actual dataset CSV and asserts the manifest's target and protected-attribute columns exist in it, not just that the manifest itself parses.
- **Static favicon assets** (#154, closes #134, by [@ahmdkaml](https://github.com/ahmdkaml)) - `favicon.ico`, 16x16/32x32 PNGs, and an `apple-touch-icon.png` (from a new `logo.svg` source), wired into `index.html`, `profiler.html`, every explainer page, and the page-generator template, alongside the existing inline-SVG favicon.
- **Dependabot: GitHub Actions ecosystem** (#146, closes #137, by [@ahmdkaml](https://github.com/ahmdkaml)) - action versions in `.github/workflows/*.yml` now get automated update PRs too, not just pip packages.
- **JSON orientation docs** (#155, by [@ahmdkaml](https://github.com/ahmdkaml)) - README and `tests/test_loaders.py` now cover and test all three orientations `read_table()` already accepted (`records`, `split`, `columns` - the last one worked all along via pandas' default, just wasn't documented or tested).
- **`tests/test_report.py`** (#172, closes #130, by [@ahmdkaml](https://github.com/ahmdkaml)) - baseline smoke tests for `to_html()`/`compare_to_html()` against hand-written mock profile/compare results, closing the test-coverage gap those functions have had since they were first added.
- **CODEOWNERS: @ahmdkaml added for CI/automation** (#174, closes #171, by [@ahmdkaml](https://github.com/ahmdkaml)) - `/.github/workflows/` and `/.github/CODEOWNERS` now route to both maintainers, recognizing the CI/testing infrastructure work in #126, #142, #146, #153, #156, #157.
- **JSON edge-case coverage + clearer parse errors** (#175, closes #169, by [@ImMortaL0P](https://github.com/ImMortaL0P)) - truncated/invalid JSON used to leak a raw engine-specific error (a browser `SyntaxError` in `assets/profiler-engine.js`, an internal pandas `ValueError` retried under `orient="split"` only to fail again in `faircode/loaders_extra.py`); both now fail fast with the same `"Unsupported JSON format"` message the tabular-shape checks already use. Also tightened the JS engine's "columns orientation" detection, which was silently misreading a deeply-nested non-tabular structure (`{"a": {"b": {"c": 1}}}`) as a one-column table instead of rejecting it. New `tests/test_json_edge_cases.py` (8 tests) covers truncated JSON, a bare array of primitives, `{}`, and deep nesting on both engines; documents that pandas is intentionally left more lenient than the JS engine for the first two.
### Changed
- Traction refreshed again as the project grew: forks `19 -> 22` (GitHub's API - the prior snapshot had gone stale), countries reached `16 -> 17`. Also caught contributors `13 -> 14` never having propagated past the weekly table row into `METRICS.md`'s badge, Targets table, and resume line - all three now match. Forks' target bumped `20+ -> 25+` since the metric already passed it. Applied across `METRICS.md`, `README.md`, and `ROADMAP.md`.
- **Repo settings: `main` branch protection enabled** - was previously unprotected (anyone with write access could push directly, no PR required). Now requires a pull request with at least one approval, including from a code owner where CODEOWNERS names one, before merging. `@ahmdkaml` invited as a write collaborator (pending acceptance) so the CODEOWNERS entries added above can actually take effect, per GitHub's requirement that a code owner have write access.
- External contributors `13 -> 14` (see `METRICS.md`). Applied across `METRICS.md`, `README.md`, and `ROADMAP.md`.
- Traction refreshed as the project grew (see `METRICS.md`): combined social reach ~25K -> **26K+**; **Countries reached** (16, unique countries visiting thefaircode.xyz per site analytics - not a social-platform figure) tracked for the first time. Applied across `METRICS.md`, `README.md`, and `ROADMAP.md`.
- `ROADMAP.md` Phase 1 status line said "35 explainers published," one behind the actual count (36) already reflected everywhere else - corrected to match `README.md`, `METRICS.md`, and `assets/explainers-data.json`.
- Ran `scripts/build_explainers.py` against the current `explainers/*.md` and `assets/explainers-data.json` sources: all 36 pages, `assets/explainers-data.js`, and `llms-full.txt` regenerated byte-identical; `sitemap.xml` picked up `profiler.html`'s new `<lastmod>` (2026-08-05 -> 2026-08-07) from this batch's SRI-hash and client-side-xlsx commits.
### Fixed
- **PR #197 broke the CLI's `.xlsx` support outright** - changing `parseXLSX()`'s return value from a bare table to `{ table, sheetName, ignoredSheets }` updated every browser call site (`profiler-ui.js`, `profiler-compare.js`) but missed `scripts/engine-js.js`, which still did `E.profile(await E.parseXLSX(...))` - passing the whole wrapper object where `profile()` expected `{columns, rows}`. This crashed `node scripts/engine-js.js profile-xlsx` unconditionally and failed 5 tests (`test_python_js_xlsx_parity`, all 4 of `test_xlsx_js_edge_cases_match_python`) - confirmed failing on `main` before this fix. Updated the missed call site to `E.profile(result.table)`; also normalised indentation in `profiler-ui.js`'s two xlsx callbacks, which the same PR left one level short.
- **PR #194 broke CLI/web parity for edge-case `.xlsx` files** - its new `parseXLSX()` threw `"The workbook contains no usable data."` for a headers-only sheet or an empty first sheet, while `faircode.loaders.read_table()` (and its own new `tests/test_xlsx_edge_cases.py` Python assertions, in the same PR) return a valid empty/headers-only DataFrame for the exact same files - confirmed by running both engines on all four new fixtures directly. The two engines disagreeing on whether a file is even valid is exactly what `faircode/SPEC.md`'s bit-for-bit parity rule exists to prevent. Rewrote `parseXLSX()` to mirror pandas: a fully blank sheet returns `{columns: [], rows: []}`, a headers-only sheet keeps its column names with zero rows, and updated `test_xlsx_js_edge_cases_match_python` to assert the JS and Python results agree instead of asserting the JS engine errors. Verified all four fixtures now match on `n_rows`/`n_cols` between engines.
- **PR #192's lazy `loadSheetJS()` couldn't recover from a failed load** - `sheetJsPromise` cached the *rejected* promise forever once the CDN script failed once (e.g. a transient network blip), so every subsequent `.xlsx` upload for the rest of the page session got the same stale rejection instead of retrying. Reset `sheetJsPromise` to `null` in the `onerror` handler so the next upload attempt re-injects the script.
- `tests/test_js_parity.py` (PR #193): a decorator lost its required blank lines above it, `import re` landed in the wrong (third-party) import group, and a new test had a stray blank line - normalised to the file's existing PEP8 style. `assets/profiler-ui.js` (PR #192): `reader.onload =async function` was missing its space.
- **CodeQL false-positive suppression was broken** - the `# lgtm[rule-id]` comments added to suppress `py/clear-text-logging-sensitive-data` on the audit scripts' aggregate-statistics prints are from the retired LGTM.com service and aren't honored by the current `codeql-action` at all; worse, editing those lines gave CodeQL a new alert fingerprint, so the same 35 alerts came back under new numbers on the next scan. Reverted all six files to their pristine content and replaced the comments with a proper `.github/codeql/codeql-config.yml` `query-filters` exclusion, which disables the rule repo-wide instead of alert-by-alert and can't be invalidated by nearby edits.
- **`requirements-lock.txt` had drifted from its frozen snapshot** - Dependabot's `pip` ecosystem scan can't be scoped to skip one file in a directory it manages, so it had repeatedly bumped peripheral packages (`click`, `fastjsonschema`, `fonttools`, `mistune`, `narwhals`, `pillow`, `platformdirs`, `prompt_toolkit`, `pyreadstat`, `soupsieve`, `traitlets`, `xlrd`) in this file over time, all merged without anyone noticing it's supposed to be a fixed `pip freeze` snapshot. The numerically-relevant packages (`numpy`, `pandas`, `scikit-learn`, `scipy`, `fairlearn`) were never touched, so the paper's actual numbers were never at risk - but the file's own "this is the exact environment" claim was false. Reverted to match the untouched copy in `paper/results-frozen/requirements-lock.txt`, and added it to CLAUDE.md §1 and the new Frozen Files check so future Dependabot PRs against it get flagged instead of silently merged.
- The Web paragraph in README's Open Dataset Profiler section still said "Excel `.xlsx`, JSON, and Parquet aren't supported client-side yet," left over from before #144 added client-side JSON support - JSON just wasn't in that sentence's exclusion list anymore.
- **`frozen-files.yml` compared the wrong range** (closes #163) - it diffed `base_sha..head_sha` (two-dot), which can pull in files `main` picked up after a PR branched, so the check could flag or miss protected-path changes that were never actually part of the PR. Switched to diffing from the real `git merge-base` instead.
- **xlsx parity test could fail CI** (follow-up to #158) - `test_python_js_xlsx_parity` called `pd.read_excel()` with no skip guard, unlike the existing xlsx tests; CI's profiler job doesn't install the optional Excel extra. Added the same `requires_openpyxl` skipif marker the other xlsx tests already use.
- **SheetJS CDN script had no integrity check** - the `.xlsx` CDN `<script>` tag added for #158 shipped with no `integrity`/`crossorigin` attributes, so a compromised CDN or npm publish for that pinned version could have served tampered JS with nothing to catch it. Added a sha384 Subresource Integrity hash, cross-checked against jsdelivr's own published hash for the same file.
- **Dead vendored first-interaction action code** - `main.ts`, `v1_action.yml`, `v3_action.yml`, and `first_interaction_index.js` (~35K lines, mostly a bundled dependency tree) were leftovers from before the project switched to an inline `actions/github-script` step and were never deleted. Confirmed unreferenced and removed; also clears a CodeQL `js/weak-cryptographic-algorithm` alert on that dead code, surfaced now that CodeQL scans JS (see Added).
### Note
- **`icon-512.png` isn't wired into any page** - it's sized for GitHub's repo/org avatar and social-card profile picture, both of which are uploaded through Settings, not linked from HTML. Recommend uploading it by hand: Settings → General → repo icon (or the org's avatar settings).
- The new `check-frozen-files` job (like `Build Explainers` before it) is not yet a *required* branch-protection status check, so a PR that fails it can still be merged - I attempted to add it to the ruleset and the action was blocked by this session's permission settings as too sensitive to change autonomously. Recommend doing this by hand: Settings → Rules → "Protect main" → add `check-frozen-files` to the required status checks alongside `run-audits`.

## [2.0.8] - 04 Aug 2026 *(folded into `v2.1.0`)*
### Added
- **SEO/GEO: FAQPage structured data + sitemap `<lastmod>`** - every explainer's schema.org block gained a `FAQPage` entry (question/answer pairs drawn from the explainer's own definition and "why it matters" text) alongside the existing `DefinedTerm`, so AI answer engines and search can extract Q&A directly; `sitemap.xml` gained a per-URL `<lastmod>` dated from each file's last commit. Regenerated by `scripts/build_explainers.py`.
- **SEO/GEO: `llms-full.txt`** - the full explainer corpus in one file (the `llms.txt` convention's "complete text" companion to the existing index), generated from `explainers/*.md` and linked from `llms.txt`, so LLM crawlers can ground on every explainer in a single fetch.
- **Homepage FAQ, Contact, and Legal** - a new "FAQ" section (what the project is and isn't, the fairness metric used, profiler data privacy, contributing during the freeze, licensing) reachable from the nav and scrollspy; footer gained a `Contact` mailto link and an MIT License / disclaimer line.
- **JS/Python profiler parity test suite** (#126, by [@ahmdkaml](https://github.com/ahmdkaml)) - `tests/test_js_parity.py` runs the same CSV through `faircode.profile()` and a new Node harness (`scripts/profile-js.js`) and asserts identical structured output; CI (`audits.yml`) now provisions Node 20 to run it. Includes a small parity fix in `assets/profiler-engine.js` (excludes lowercase `"none"` from the missing-value tokens, matching `pandas.read_csv`'s case-sensitive defaults) and brings the `small_group` warning flag over from the Python profiler.
- **`faircode profile`/`compare`: JSON and Parquet input** (#127, by [@ahmdkaml](https://github.com/ahmdkaml)) - `faircode/loaders_extra.py` reads `.json` (records or split orient) and `.parquet` (needs the new `parquet` extra: `pip install faircode[parquet]`) and falls through to the existing `faircode/loaders.py` for everything else. Kept out of `loaders.py` itself since that file is on the frozen list (see CLAUDE.md); the benchmark harness reads its CSVs directly via `pd.read_csv` and never imports `loaders.py`, so this has no bearing on any published number, but the frozen file now stays byte-identical to `v1.0-paper` regardless. CLI help text and the README's Open Dataset Profiler section updated for the two new formats.
- **`faircode compare --html`** (#128, by [@ahmdkaml](https://github.com/ahmdkaml)) - `compare_to_html()` in `faircode/report.py` renders a self-contained, print-to-PDF-ready HTML representation-drift report (score summary, per-dimension PSI/TVD cards with before/after bars, drift flags), mirroring the existing `faircode profile --html` report. Doesn't touch any frozen file or the drift computation itself, just adds a renderer for `compare()`'s existing output.
- **`.github/CODEOWNERS`** (#142, closes #138, by [@ahmdkaml](https://github.com/ahmdkaml)) - auto-requests review based on which part of the repo a PR touches, with high-stakes areas (core library, research artifacts, CI, project policy) routed separately from documentation and website changes; everything routes to the maintainer for now.
- **Theme toggle respects `prefers-color-scheme`** (#143, closes #135, by [@anujkamdar](https://github.com/anujkamdar)) - a first-time visitor with a dark-mode OS/browser preference now gets the dark theme by default instead of a hardcoded light one, via `window.matchMedia('(prefers-color-scheme: dark)')`. An explicit prior choice saved in `localStorage` still wins. Fixed consistently across `index.html`, `profiler.html`, every explainer page, and `scripts/build_explainers.py`'s page template, so future-generated explainers get it too.
- **Web profiler: client-side JSON input** (#144, closes #129, by [@ahmdkaml](https://github.com/ahmdkaml)) - `assets/profiler-engine.js` gained `parseJSON()` (records and split orientation), wired into the dropzone, the reference-baseline upload, and the two-dataset compare view in `profiler.html`/`profiler-ui.js`/`profiler-compare.js`. `.xlsx`/`.parquet` stay CLI-only for now.
### Fixed
- The parity PR had copied four dataset CSVs (~25MB) into `tests/fixtures/` that were byte-identical to files already tracked in their audit folders. Pointed the tests at the existing audit-folder datasets instead and removed the duplicates.
- The JSON/Parquet PR (#127) landed with two gaps: it modified `faircode/loaders.py` directly (frozen file - relocated to `loaders_extra.py`, see above) and its `.parquet` error message pointed at a `faircode[parquet]` extra that didn't exist in `pyproject.toml` (added it, alongside `pyarrow>=10.0`).
- **#111 was closed prematurely** - it asked for a web compare-view download button and Python/JS parity for the drift report alongside the CLI's `--html` flag, but #128 only shipped the CLI half. Completed the rest: `profiler.html`/`assets/profiler-compare.js` gained a matching "Download report (HTML)" / "Copy as JSON" action bar (`buildCompareHtmlReport()` ports `compare_to_html()` field-for-field), and `scripts/compare-js.js` + `tests/test_js_parity.py::test_python_js_compare_parity` now automatically check `faircode.compare()` against the JS engine's `compare()` - the analogue of the existing profile() parity test, which compare() never had. `CONTRIBUTING.md`'s profiler parity note extended to cover `compare.py`/`profiler-compare.js` and the `to_html`/`compare_to_html` report pair, not just `profiler.py`/`profiler-engine.js`.
- `.github/workflows/build-explainers.yml` pushed its regenerated-files commit straight to `main`; once the repo's branch-protection ruleset started requiring PRs, `github-actions[bot]` (not in the ruleset's bypass list) could no longer push and the job failed outright. Converted it to a check that fails if `explainers/*.html`, `assets/explainers-data.js`, `sitemap.xml`, `llms-full.txt`, or `assets/og/*.png` are out of sync with their sources, matching the `make build-explainers` step `CONTRIBUTING.md` already documents - no bot commits, no new secrets.
- The JSON web-profiler PR (#144) had two bugs: `parseJSON()`'s records-orientation branch derived columns from only the first record, silently dropping any column that first appeared in a later one (`pandas.read_json` unions keys across every record - a JSON file with inconsistent per-record keys produced a genuinely different, incomplete audit in the browser than the CLI reported for the same file); and `profiler-ui.js`'s `reportBaseName()` used an unanchored regex (`/\.csv|\.tsv|\.json$/i`) that could strip the wrong substring from filenames containing `.csv`/`.tsv` before the real extension, producing a malformed download name. Fixed both, and added `test_python_js_json_parity_inconsistent_keys` (via `scripts/profile-json-js.js`) to catch the first one again.

## [2.0.7] - 04 Aug 2026 *(folded into `v2.1.0`)*
### Added
- **Contributor task runner** (#114, by [@propcgamer20-png](https://github.com/propcgamer20-png)) - a `Makefile` (`setup`, `test`, `build-explainers`, `lint`, `check`) and a `.pre-commit-config.yaml` that mirror CI, so `make check` reproduces the em-dash lint plus the full test suite locally, and the git hooks run the fast checks on commit with the test suite on push. Documented in a new "Local setup and checks" section of `CONTRIBUTING.md`.
- **Per-audit reproducibility READMEs** (#86) - each of the seven audit folders now has a `README.md` with a reproducibility checklist (pinned `random_state=42`, `requirements-lock.txt`, stratified 80/20 split, and the exact `unfair.py` / `fair.py` commands) plus the published before/after fairness numbers copied verbatim from the main results table (paper-aligned, not re-run). Standardised in `CONTRIBUTING.md` (folder layout + a rule) so future audits ship one too.

## [2.0.6] - 02 Aug 2026 *(folded into `v2.1.0`)*
### Added
- **Profiler: configurable small-subgroup warnings** (#124, by [@ahmdkaml](https://github.com/ahmdkaml)) - every group now carries a `small_group` flag (raw count below `min_group_size`, default 100), shown as a "small group" warning in the terminal report, the HTML report, and the web UI, and tunable via `faircode profile --min-group-size N` or `opts.min_group_size`. Below that size a share and its confidence interval are noisy enough that a gap is a lead to investigate, not a confirmed finding.
### Fixed
- Restored Python/JS parity for the feature. The merged PR added `small_group` to `faircode/profiler.py` only; mirrored it into the browser engine `assets/profiler-engine.js`, documented it in `faircode/SPEC.md` (sections 3, 6, 7), and wired the warning into the web UI (`assets/profiler-ui.js` live view + downloaded report, `assets/profiler.css`) so the CLI and the web tool return identical results per the SPEC parity rule. Also normalised a couple of PEP8 nits in the Python change.

## [2.0.5] - 31 Jul 2026 *(folded into `v2.1.0`)*
### Added
- **Profiler: 95% confidence intervals on every group share** (#83) - a deterministic Wilson score interval per group, so a share read off a small sample carries its sampling uncertainty. Implemented identically in `faircode/profiler.py` and the JS port `assets/profiler-engine.js` (parity preserved - Wilson is deterministic, no resampling), documented in `faircode/SPEC.md` section 3, and surfaced in the terminal report, the HTML report, JSON, and the web UI.
- **Profiler: shareable HTML / PDF report** (#85) - the generated report is print-optimised so it saves straight to PDF from the browser, alongside the existing `faircode profile --html` and web "Download report" export.
- **`faircode profile --fail-under N` CI gate** (#115, by [@tomatotomata](https://github.com/tomatotomata)) - exits non-zero when a dataset's representation score falls below `N`, so the profiler can gate a CI pipeline; `--json` output stays machine-readable. The boundary is strict (a score equal to `N` passes), verified by an equality test (#123, by [@ahmdkaml](https://github.com/ahmdkaml)).
- **CI: automatic em-dash enforcement** (#112) - `scripts/check_em_dash.py` plus a `lint` workflow fail the build on an em dash (U+2014) in tracked source/prose (en dashes for numeric ranges are allowed), so the em-dash-free contribution rule is enforced automatically instead of by eye.
### Changed
- Dependency bumps (Dependabot): `pillow` 11.1.0 -> 12.3.0, `prompt-toolkit` 3.0.52 -> 3.0.53, `fastjsonschema` 2.21.2 -> 2.22.1, `narwhals` 2.20.0 -> 2.24.0, `pyreadstat` 1.3.4 -> 1.3.5.
- Traction refreshed as the project grew (see `METRICS.md`): forks 15 -> 17, external contributors 9 -> 11, social reach ~18K -> ~21K.
### Fixed
- `scripts/check_em_dash.py` no longer flagged its own source - the em-dash character is referenced by code point so the file contains no literal em dash.
- Normalised the `--fail-under` equality test to PEP8 (blank lines before the new function, trailing newline).

## [2.0.4] - 28 Jul 2026 *(folded into `v2.1.0`)*
### Added
- **Explainer: Why Accuracy Is Not Enough in Healthcare AI** (`accuracy-not-enough-healthcare-ai.md`, closes #64) - the accuracy paradox on rare clinical outcomes (a "predict nothing" model scoring 97% while catching zero at-risk patients), why one aggregate score masks per-group recall / false-negative gaps, anchored to the Healthcare Readmission audit (Audit 06) and Obermeyer et al. (2019), with per-group accuracy-vs-recall detection code. Repo figures use the frozen `paper/results-frozen/` numbers per the freeze.
### Changed
- Explainer count `35 → 36` across `README.md`, `ROADMAP.md` (traction table + Phase 2 item checked off), and `METRICS.md`.
- `README.md` explainers table gained the accuracy explainer plus the previously-missing `roc-curve-auc` row; the homepage "healthcare AI explainers" list moved from *Upcoming* to *Published*.
- `index.html` roadmap timeline caught up: added the six explainers it was missing (roc-curve-auc, protected-attribute, confusion-matrix, class-imbalance, bias-variance-tradeoff, accuracy-not-enough-healthcare-ai). The homepage explainer grid is generated from `explainers-data.js` and already tracked every explainer.
- `CONTRIBUTING.md` explainers table and `llms.txt` list updated for the accuracy explainer.
- Metric targets revised in `METRICS.md`: explainers `30+ → 60+`, forks `15+ → 20+`, watching `15+ → 12+`, social reach `10K/mo → 40K+`.
- Roadmap pivot for the freeze: added a planned **healthcare-explainer** track (race correction in clinical algorithms, the Obermeyer cost-as-proxy case, underdiagnosis bias, clinical-score miscalibration, EHR missing-data bias, medical-imaging representation gaps) to `ROADMAP.md` Phase 2, the `README.md` healthcare section, and the `index.html` roadmap - the freeze-safe way to keep the healthcare focus moving while new audits are on hold.

## [2.0.3] - 28 Jul 2026 *(folded into `v2.1.0`)*
### Added
- **Four explainers** contributed by [@Shreyash0712](https://github.com/Shreyash0712) (PR #102), from the topics requested in issues #98 / #96 / #99 / #100:
  - **What Is a Protected Attribute?** (`protected-attribute.md`) - what a protected attribute is, which ones the law recognizes, and why removing them outright just hides the bias behind proxies.
  - **What Is a Confusion Matrix?** (`confusion-matrix.md`) - the TP/FP/FN/TN building block behind most fairness metrics, and everything (precision, recall, FPR, FNR) derived from it.
  - **What Is Class Imbalance?** (`class-imbalance.md`) - why skewed positive/negative ratios wreck naive accuracy and hit minority subgroups hardest, and when resampling helps or hurts fairness.
  - **What Is the Bias-Variance Trade-off?** (`bias-variance-tradeoff.md`) - the classic underfit/overfit trade-off, distinguished from the societal/algorithmic bias the other explainers mean.
  Each ships as `explainers/<slug>.md` + generated page + an `assets/explainers-data.json` entry + `sitemap.xml`.
### Changed
- Explainer count `31 → 35` across `README.md`, `ROADMAP.md` (traction table + Phase 1 checklist), and `METRICS.md` (badge + targets).
- `CONTRIBUTING.md` explainers table: rows added for the four new explainers plus the previously-missing `roc-curve-auc.md`.
- `llms.txt` Explainers list: added the four new explainers plus the previously-missing `automation-bias` and `roc-curve-auc` (`robots.txt` needs no change - it allows all crawlers and points at `sitemap.xml`, which already lists every page).
- Paper-freeze notice surfaced at the point of contribution: the issue forms (`new_audit.yml` audit-hold banner, `new_explainer.yml` frozen-numbers rule), `PULL_REQUEST_TEMPLATE.md` (don't-touch paths + flag-don't-fix), and `llms.txt` (status line for AI crawlers).

## [2.0.2] - 27 Jul 2026 *(folded into `v2.1.0`)*
### Added
- **Explainer: What Is a ROC Curve and AUC?** - `explainers/roc-curve-auc.md` + generated page, registry entry in `assets/explainers-data.json`, and sitemap. Covers what a ROC curve and AUC actually measure (ranking quality), and why a single threshold-free number hides the two things fairness depends on: where the decision threshold sits, and whether ranking quality is equal across groups. Anchored to COMPAS's ordinary **0.68** baseline AUC (quoted from `paper/results-frozen/`, per the freeze) sitting on top of a large racial false-positive gap; includes per-group AUC / overlaid-ROC detection code. Brings the explainer count to **31**.
### Fixed
- `scripts/build_explainers.py` had drifted out of sync with the committed site: it used the bare `thefaircode.xyz` host and had dropped the `author` (`Yash Kewlani`) `<meta>` tag and `Person` JSON-LD. Left unfixed, the CI rebuild would have stripped author attribution and reverted canonical URLs across every page. Restored to `www.thefaircode.xyz` + the author schema, so a rebuild is now idempotent (28 of 30 existing pages regenerate byte-identical).
- Regenerated two stale pages, `explainers/automation-bias.html` and `explainers/selection-bias.html`, whose committed HTML predated the styled-table renderer (bare `<table>` with no `explainer-table` classes); `automation-bias.html` was also missing from `sitemap.xml`.
### Changed
- `CONTRIBUTING.md`: new **"Contributing during the paper freeze"** section spelling out what is open (explainers, docs, website, captions) vs. on hold (new audits, frozen-results changes), plus the frozen-numbers rule for explainers (closes #97).
- Explainer count `30 → 31` across `README.md`, `ROADMAP.md`, and `METRICS.md`.

## [2.0.1] - 27 Jul 2026 *(folded into `v2.1.0`)*
### Added
- **`CLAUDE.md`** - standing paper-freeze policy for AI agents and contributors: the DO-NOT-TOUCH list (`paper/results-frozen/`, `results/`, the `faircode/` core, every `audit.yaml` and dataset CSV, the `v1.0-paper` tag), the parameters that must not change (`random_state=42`, `test_size=0.2` stratified, `EXPONENTIATED_GRADIENT_MAX_ITER=50`, DemographicParity, the six metrics, bootstrap/permutation counts), the no-new-audits-on-`main` rule, the flag-don't-silently-fix escape hatch, and what happens when the freeze lifts.
- **`ROADMAP.md` Phase 6 - Research Paper and Publication**: makes the paper a tracked goal and explicitly gates `v3.0.0` on publication; freeze notice + version/release-gate block added under "Where We Are".
### Changed
- Traction metrics refreshed from live GitHub data: stars `38 → 40`, forks `14 → 15`, watching `7 → 8`, social reach `~16K → ~18K`; the **Posts** column dropped from `METRICS.md`. Applied across `METRICS.md`, `README.md`, and `ROADMAP.md`.
- `CLAUDE.md` and `ROADMAP.md` freeze commit references aligned to the `v1.0-paper` tag (`bbef2ba`); noted that the frozen `MANIFEST.md`'s provenance commit `2fa4a66` has byte-identical code and reproduces the same numbers.
- `ROADMAP.md`: Phase 3 relabeled - the two unbuilt audits (HMDA, Facial Recognition) marked *(post-paper)*; "How to Contribute" rewritten so it no longer invites work that cannot merge during the freeze.

---

## [v1.0-paper] - 24 Jul 2026 · Frozen benchmark results (paper reference)

A reference tag, not a normal release. It freezes the exact benchmark numbers cited by the research paper (in peer review) so the paper's tables and the repo can never drift apart. Published as a GitHub release, deliberately **not** marked "Latest" so it does not displace `v2.0.0`. `paper/results-frozen/` is permanent and must never change - see [CLAUDE.md](CLAUDE.md).

### Added
- **`v1.0-paper` tag** (commit `bbef2ba`) + GitHub [release](https://github.com/yakew7/Fair-Code/releases/tag/v1.0-paper) freezing `paper/results-frozen/`: the final paper run (`ExponentiatedGradient` `max_iter=50`) across all seven domains, with a `MANIFEST.md` recording provenance (commit `2fa4a66`, identical code), pinned package versions, and the exact seven `audit.yaml` manifests covered. Release notes carry the freeze policy and the no-new-audits notice.

---

## [2.0.0] - 23 Jul 2026

A major version bump: Fair Code moves from seven bespoke bias audits to a cross-domain benchmark
harness that runs one uniform, reproducible pipeline over all of them - the core of what a
research paper built on this repo would cite. Nothing about the existing audits (`unfair.py` /
`fair.py`, the website, the explainers) changed or broke; this release is additive.

### Added
- **Cross-domain fairness benchmark harness** (`faircode benchmark`, optional `faircode[benchmark]` extra) - applies one uniform pipeline to all seven audits instead of seven bespoke scripts, so a cross-domain comparison rests on a single code path
  - **Layer 1 - `audit.yaml`**: a declarative manifest per audit folder naming its label column, protected attributes, proxy features, and core (fair) feature set. Schema documented in `faircode/MANIFEST_SPEC.md`. All seven audits (COMPAS, AI Fair Recruitment, German Credit Lending, Insurance Denial, Benefits Denial, Healthcare Readmission, Tenant Screening) now carry one
  - **Layer 2 - the harness**: five mitigation strategies run per audit (`faircode/strategies.py`) - `baseline` → `unawareness` → `unawareness_proxy_removal` (the existing `fair.py` method) → `in_processing` (`fairlearn.reductions.ExponentiatedGradient` under a fairness constraint) → `post_processing` (`fairlearn.postprocessing.ThresholdOptimizer`, per-group decision thresholds) - across three model families (`faircode/models.py`: logistic regression, random forest, gradient boosting, fixed hyperparameters + seed)
  - Six fairness metrics per (strategy, model, protected attribute) - demographic parity diff, disparate impact ratio, equal opportunity diff, equalized odds diff, predictive parity diff, accuracy equality diff - each with a bootstrap CI and permutation-test p-value, plus accuracy/AUC/F1 as plain performance metrics (`faircode/metrics.py`)
  - Intersectional gap for every pair of declared protected attributes (reuses `faircode.significance.intersectional_report`)
  - `faircode/benchmark.py` orchestrates manifests → strategies → metrics and writes `results_fairness.csv` / `results_performance.csv` / `summary.csv`; `faircode/figures.py` renders one 300-dpi `<audit>_strategies.png` per audit straight from those CSVs, so re-plotting a different metric never re-runs a model
  - `faircode/manifest.py` loads/validates `audit.yaml` and discovers every manifest in the repo
  - Full run across all seven audits committed to `results/` at the repo root
- **Reproducibility & paper-freeze infrastructure**, so a paper cites a defined, reproducible set of numbers instead of "whatever was in the repo that week"
  - Verified and documented that every model, split, bootstrap resample, and permutation shuffle already takes an explicit `random_state` (all seven manifests default to 42); a defense-in-depth global seed added in `benchmark.py`; the "don't change `random_state` on a cited run" invariant stated in `faircode/MANIFEST_SPEC.md`
  - `requirements-lock.txt` - an exact `pip freeze` of the environment that produced the committed `results/` (Python 3.13.2, scikit-learn 1.8.0, fairlearn 0.14.0, pandas 3.0.2)
  - `scripts/freeze_paper_results.py` - snapshots `results/` into `paper/results-frozen/` with a `MANIFEST.md` recording the git commit, package versions, and the exact list of `audit.yaml` manifests included; prints (never runs) the `git tag` / `git push --tags` command, since tagging is a deliberate public action
  - New README.md section: [Reproducibility & Paper Freeze](README.md#reproducibility--results-history) (later renamed "Reproducibility & Results History" once the freeze lifted)
- **Test suite for the benchmark harness** (50 new tests, 108 total, ~10s)
  - `tests/test_metrics.py` - all six fairness metrics hand-computed against a worked tiny example, plus a regression test reproducing COMPAS's published 86.77% headline gap from reconstructed rate arrays
  - `tests/test_manifest.py` - manifest loading/validation, malformed YAML and missing-field failures, parametrized over all seven shipped manifests
  - `tests/test_strategies.py` - exact S0-S4 column-set assertions and `encode_features` behaviour
  - `tests/test_benchmark.py` - genuine end-to-end `run_audit()` against German Credit Lending (smallest dataset), not a mock of it
  - CI: new `benchmark-harness` job in `.github/workflows/audits.yml` runs these tests plus a CLI-level smoke test on that same small audit. The full seven-domain sweep stays out of CI (fairlearn's in-processing strategy takes minutes per audit on the larger datasets) - run it locally and commit `results/` output
- README.md: new [Benchmark Harness](README.md#benchmark-harness) section documenting the manifest schema, the five strategies, and the `faircode benchmark` CLI; `Repository Structure` tree and `Tech Stack` table updated to match
- `scripts/render_terminal_png.py` - renders a script's captured stdout as a terminal-style PNG (dark background, monospace), matching the existing `fair.png`/`unfair.png` screenshot style
### Fixed
- `faircode.strategies.fit_post_processing` (S4): `ThresholdOptimizer`'s default `prefit=False` behaviour calibrates per-group thresholds on the same rows the base estimator was fit on - on an overfit `RandomForestClassifier`, this produced a near-zero demographic parity gap on the calibration data but a +0.22 gap on held-out test data (German Credit Lending). Fixed by fitting the base estimator on a FIT split of the training data and calibrating thresholds on a separate, held-out CALIBRATION split of that same training data (`prefit=True`) - closed the generalization gap to +0.07, consistent with the other strategies' residual variance
- All 14 `fair.png` / `unfair.png` screenshots regenerated from a fresh run of every `unfair.py` / `fair.py` - the previous images predated the bootstrap CI / permutation-test / proxy-analysis output `faircode.significance` added, so they only showed the bare headline gap. Every audit's underlying values were independently re-verified against what `index.html` already displays (all seven matched exactly - the scripts are deterministic with a fixed `random_state=42`, so only the screenshots were stale, not the published numbers)
### Changed
- `ROADMAP.md`: Phase 5 status changed from "Planned" to "In Progress"; checklist gains the Fairlearn in-processing/post-processing integration and the cross-domain benchmark harness as completed items, plus a new planned item for an interactive results dashboard
- `pyproject.toml` / `requirements.txt`: `fairlearn>=0.14.0` and `pyyaml>=6.0` added to the `benchmark` optional-dependency group
- `faircode/__init__.py`: package version `0.1.0` → `2.0.0`, aligned to this release (was tracked separately before the benchmark harness existed)
- `CITATION.cff`: version `1.3.3` → `2.0.0`; abstract updated to mention the benchmark harness

---

## [1.3.4] - 21 Jul 2026
### Added
- Explainer: What Is Automation Bias? - `automation-bias.md` created, added to `index.html`, `README.md`, `CONTRIBUTING.md`, and `ROADMAP.md`
  - Full explainer on the cognitive tendency to defer to automated systems - covering omission and commission errors, default acceptance, and authority transfer
  - Real-world proof anchored to Audit 01 (COMPAS): the 86.77% fairness gap was not just a statistical problem - it became a civil-rights problem because judges in multiple states treated the score as dispositive, with the Wisconsin Supreme Court's *State v. Loomis* (2016) ruling on COMPAS use at sentencing as the legal case study
  - Detection code: `automation_bias_audit()` - measures overall human-model agreement rate, override rates by protected group, and whether final human decisions produce a *larger* fairness gap than the model alone (disparity amplification)
  - Six mitigation strategies (friction by design, counterfactual display, blind review first, disagreement logging, calibrated thresholds per group, human-in-the-loop training) with honest limitations on each
  - Four numbered limitations, cross-links to ml-bias, proxy-variables, label-bias, confounding-variable, and ai-objectivity-myth, and four further reading citations (Goddard et al. 2012, Skitka et al. 1999, Obermeyer et al. 2019, *State v. Loomis*)
  - Roadmap item added on the website
### Changed
- `README.md`: `automation-bias.md` added to the explainers table, repository structure tree, and What's Next checklist; Traction explainer count updated to 30
- `CONTRIBUTING.md`: `automation-bias.md` added to the existing explainers table
- `ROADMAP.md`: Phase 1 checklist gains `automation-bias.md`
- `assets/explainers-data.json`: automation-bias entry added so the website's Explainers grid, search, and count pick it up

---


## [1.3.3] - 21 Jul 2026
### Added
- `llms.txt` at the site root - a plain-text index of audits, tools, and explainers for AI assistants and crawlers to read directly, following the [llmstxt.org](https://llmstxt.org) convention
- `Person` schema (author + founder, name "Yash Kewlani") and a `<meta name="author">` tag added to the homepage and all 29 explainer pages, so structured data and AI grounding have an unambiguous, machine-readable attribution source instead of guessing from the GitHub handle
### Fixed
- Sitemap/canonical host mismatch: every `<link rel="canonical">`, `og:url`, and JSON-LD `url` field, plus `sitemap.xml` and the `Sitemap:` line in `robots.txt`, referenced the bare apex domain (`thefaircode.xyz`), which 308-redirects to `www.thefaircode.xyz` - the host that actually serves the site. Google Search Console rejected the sitemap ("Sitemap could not be read") because none of its listed URLs matched the host it was fetched from. All 33 affected files now consistently use `www.thefaircode.xyz`
### Changed
- `robots.txt`, canonical URLs, and homepage JSON-LD structured data added (`WebSite`/`Organization` schema) to make the site properly crawlable for search and AI discovery
- All 29 explainer pages made crawlable for SEO/AI search (canonical tags, `og:type=article`, per-page `DefinedTerm` JSON-LD)
- `METRICS.md`: new 2026-W30 snapshot - stars 27 -> 38, forks 8 -> 14, contributors 7 -> 9, code audits 6 -> 7, social reach ~10K -> ~16K; **Watching** (7) tracked for the first time; targets table refreshed to match
- `ROADMAP.md`: traction table refreshed (38 stars, 9 contributors, 14 forks, 7 watching), Phase 4 status updated to 9 external contributors
- `README.md`: Traction table refreshed to match METRICS.md; Star History section removed
- `CITATION.cff`: version `1.3.2` → `1.3.3`; release date updated to 2026-07-21

---

## [1.3.2] - 20 Jul 2026
### Added
- Explainer: What Is Selection Bias? - `selection-bias.md` created, added to `index.html`, `README.md`, `CONTRIBUTING.md`, and `ROADMAP.md`
  - Full explainer on the earlier-stage sibling of sampling bias: a dataset can look perfectly balanced on every demographic check available and still be biased, because the process that decided whether a unit became a row at all - getting hospitalized, getting arrested, getting approved for a loan - depended on the outcome being studied. Frames this as conditioning on a collider (Berkson's paradox) rather than a representation problem, and scopes itself explicitly against the existing `sampling-bias.md`, which already lists "selection bias" as one row in its representation-problems table
  - Real-world proof anchored to Audit 03 (German Credit Lending): `credit_customers.csv`'s `class` column takes only `good` (700 rows) and `bad` (300 rows) across all 1,000 rows, with zero rows for a rejected-before-underwriting applicant, because a turned-down applicant never generates a repayment outcome to record. Named as the classic "reject inference" problem in credit-scoring literature - the audit's 7.16% -> 1.89% proxy-variable fix (Audit 03) describes bias only among the population that already cleared the original approval gate, a limitation neither `unfair.py` nor `fair.py` can see
  - Detection code: `simulate_selection_bias()`, a from-scratch reproduction of Berkson's paradox (two independent features become correlated purely from conditioning on a shared downstream selection gate), and `check_outcome_rate_against_reference()`, a lightweight check against an external reference rate - framed honestly as the only test available, since the excluded population left no row to inspect directly
  - Five numbered limitations (invisible from inside the sample, blurry line against sampling bias, statistical corrections rest on unverifiable assumptions, a skewed base rate is a hint not a verdict, fixing the upstream gate is usually outside the model builder's control), cross-links to sampling-bias, label-bias, confounding-variable, and distribution-shift, and three further reading citations (Berkson 1946, Hand & Henley 1997, Heckman 1979)
  - Roadmap item added on the website
### Changed
- `scripts/build_explainers.py` run to regenerate `explainers/selection-bias.html`, `assets/explainers-data.js`, and `sitemap.xml` from the new `assets/explainers-data.json` entry
- `README.md`: `selection-bias.md` added to the explainers table and What's Next checklist; Traction explainer count updated to 29
- `ROADMAP.md`: Phase 1 checklist gains `selection-bias.md` plus five prior explainers that were missing from the list (predictive-parity, false-positives-vs-false-negatives, supervised-learning, unsupervised-learning, model-drift); traction table explainer count updated to 29; "last updated" and "current traction" dates refreshed to July 2026
- `CONTRIBUTING.md`: existing explainers table gains a `selection-bias.md` row
- `METRICS.md`: explainer count updated to 29
- `CITATION.cff`: version `1.3.1` → `1.3.2`; release date updated to 2026-07-20

---

## [1.3.1] - 14 Jul 2026
### Added
- Explainer: What Is Unsupervised Learning? - `unsupervised-learning.md` created (contributed by @AnayDhawan, #35/#74), added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer on learning structure from unlabelled data: with no `y` to score against, a clustering algorithm has no concept of protected groups, yet can still sort people along demographic lines as a side effect of the features it is given
  - Real-world proof anchored to Audit 04 (Benefits Denial): running k-means (`k=2`) on the UCI Adult Census file with `sex`, `race`, and `native.country` excluded from the feature set still recovers a strong sex split (one cluster 89.3% male) and a real race split (Black applicants at more than 2x the rate between clusters). National origin is kept as an honest counterexample - it lands at essentially the same rate in both clusters (10.2% vs 10.7%) - rather than overclaiming
  - Detection code: `cluster_without_protected_attributes()` and `check_cluster_demographic_skew()` - k-means on a deliberately protected-attribute-free feature set, paired with a post-hoc crosstab of cluster assignment against each protected attribute
  - Four numbered limitations (no ground truth to evaluate against, `k` and distance metric as assumptions, disparate impact harder to audit without labels, dimensionality reduction erasing the very signal an audit needs), cross-links to proxy-variables, proxy-entanglement, ml-bias, and supervised-learning, and three further reading citations (ProPublica mortgage-algorithm investigation, Chierichetti et al. 2017 Fair Clustering, Barocas, Hardt & Narayanan)
  - Roadmap item added on the website
- Explainer: What Is Model Drift? - `model-drift.md` created (contributed by @AnayDhawan, #36/#75), added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer on the operational, over-time side of distribution shift: a model that clears a bias audit at launch can drift back into an unfair state while sitting still, with no code change, no retraining, and no alert, unless someone monitors it. Distinguishes data drift (`P(X)` moves) from concept drift (`P(Y|X)` moves) because they need different fixes
  - Scoped explicitly against the existing `distribution-shift.md`: that explainer covers the one-shot reference-vs-current taxonomy (covariate/label/concept) with a single KS/chi-squared test; this one covers ongoing rolling-window monitoring of an already-deployed model
  - Real-world proof anchored to Audit 03 (German Credit Lending): re-measuring the age fairness gap across five sequential 200-row windows shows it swinging from 4.3% to 15.1%, versus the audit's single 6.39% snapshot - the instability a rolling view catches and a one-shot audit cannot. PSI on three features flags `credit_amount` (0.119) as the feature that moved most, ahead of `age` (0.096)
  - Detection code: `population_stability_index()`, `page_hinkley_test()` (change-point detection), and `rolling_fairness_gap()` - numpy/pandas, no new dependencies
  - Five numbered limitations (row order is not real time, data vs concept drift need different fixes, monitoring infrastructure is the real bottleneck, threshold choices are judgment calls, small windows inflate both PSI and the gap), cross-links to distribution-shift, feedback-loop-bias, and supervised-learning, and three further reading citations (Roberts et al. 2021, Gama et al. 2014, Page 1954)
  - Roadmap item added on the website
### Changed
- `README.md`: `unsupervised-learning.md` and `model-drift.md` added to the explainers table, repository structure tree, and What's Next checklist; Traction explainer count updated to 28
- `CONTRIBUTING.md`: both explainers added to the existing explainers table
- `assets/explainers-data.js`: both explainers added so the website's Explainers grid, search, and count pick them up
- `METRICS.md`: explainer count updated to 28
- `CITATION.cff`: version `1.3.0` → `1.3.1`; release date updated to 2026-07-14

---

## [1.3.0] - 13 Jul 2026
### Added
- Audit 07 - Tenant Screening / Rental Application Bias (#68) - a new domain (housing) auditing the criminal-history / recidivism-risk scores that real tenant-screening products (CoreLogic, TransUnion SmartMove, RealPage) sell to landlords as a risk flag on rental applicants
  - **Dataset: [`Tenant Screening/tenant-screening-data.csv`](Tenant%20Screening/)** - NIJ's Recidivism Challenge Full Dataset (Georgia Dept. of Community Supervision, 25,835 records, public domain via DOJ/NIJ). A reframed source: there is no clean public per-applicant screening dataset, so the audit treats `Recidivism_Within_3years` as the risk flag a background-check algorithm hands a landlord. Rows where the original challenge withheld the label are filtered out before training. Dataset choice and reframing rationale posted on issue #68 per CONTRIBUTING §1
  - **Protected attribute: Race** (Black vs White) - single-attribute audit, so no intersectional report per CONTRIBUTING
  - **`Tenant Screening/unfair.py` / `fair.py`** - Random Forest (`n_estimators=100`, `random_state=42`, 80/20 split), gap reported with `significance_report`. Twelve proxies dropped in `fair.py`: `Prior_Arrest_Episodes_{Felony,Violent,Property,Drug,GunCharges}`, the matching `Prior_Conviction_Episodes_*` fields, `Gang_Affiliated` (criminal record as a proxy for race), and `Residence_Changes` (housing instability standing in for eviction history). All twelve differ by race at chi-squared p far below 0.05
  - **Result: race gap 7.17% → 5.07% (29% reduction).** The residual gap stays statistically significant (p=0.0007) - the honest finding: the bias lives in the label itself (re-arrest is a policed quantity), so no feature removal fully closes it
  - **Notebook: [`07_tenant_screening_bias_audit.ipynb`](notebooks/07_tenant_screening_bias_audit.ipynb)** - the standard 8-section walkthrough, including a chi-squared proxy analysis with crosstab output. Docs site (`index.html`) gains a Project 07 card, nav + ticker entries, and a Housing filter; `ROADMAP.md` Phase 3 lists it as published
- Intersectional bias analysis - auditing two protected attributes at once, so the doubly-disadvantaged group at their intersection is measured directly instead of being averaged away into each single-axis gap (closes the roadmap's last open Phase 5 item)
  - **`intersectional_report()` in [`faircode/significance.py`](faircode/significance.py)** - takes an outcome and two boolean masks (each marking the disadvantaged side of one attribute), splits the population into the four `mask_a × mask_b` quadrants, and compares the doubly-disadvantaged cell against the baseline cell with the same bootstrap CI + permutation p-value the single-axis audits already use. Also returns each attribute's marginal gap (what it would report on its own), a `superadditive` flag (true when the compounded gap exceeds the sum of the two marginals), and per-quadrant rates/sizes so a thin intersection cell is visible before the small-sample warning fires. Pure numpy/pandas, no new dependencies
  - **Wired into the three audits that already track 2+ protected attributes**, as a new printed block after the existing single-attribute output in both `unfair.py` and `fair.py`: Insurance Denial (age × sex), Benefits Denial (sex × race), Healthcare Readmission (sex × race). COMPAS, AI Fair Recruitment, and German Credit Lending track one attribute each and are unchanged - there is nothing to cross
  - **Notebook: [`07_intersectional_bias_audit.ipynb`](notebooks/07_intersectional_bias_audit.ipynb)** - explains what intersectionality means (Crenshaw 1989) and why marginal fairness gaps can hide a worse compounded one, then runs `intersectional_report` on the biased vs. mitigated models for all three pairs. Finding: proxy removal closes the intersectional gap roughly in step with the marginals for Benefits and Healthcare, but for Insurance the marginal age/sex gaps shrink while the young-women gap does not, tipping the mitigated model into superadditive territory - the harm a marginal-only audit could not surface
  - Three new tests in `tests/test_significance.py` (additive → not superadditive, superadditive → flagged and significant, small doubly-disadvantaged cell → warning) - 50 significance tests passing
### Changed
- `README.md`: methodology note that audits tracking 2+ protected attributes also report an intersectional (combined) gap, linking notebook 07
- `ROADMAP.md`: Phase 5 "Intersectional bias notebook" item marked complete
- `CONTRIBUTING.md`: audit-script template now asks audits tracking 2+ attributes to report at least one intersectional pair with `intersectional_report`, following the three wired audits
- `CITATION.cff`: version `1.2.0` → `1.3.0`; release date updated to 2026-07-13; abstract extended to cover intersectional bias analysis

---

## [1.2.5] - 13 Jul 2026
### Added
- Open Dataset Profiler - a wave of six enhancements, all sharing one spec ([`faircode/SPEC.md`](faircode/SPEC.md)) so CLI and web stay bit-for-bit identical
  - **Two-dataset comparison for representation drift** (#60) - `faircode compare A.csv B.csv` and side-by-side A/B dropzones in the web profiler. Reports per-dimension drift with the Population Stability Index (PSI), Total Variation Distance, per-group share shifts, and appeared/disappeared groups; flags significant drift and overall-score drops. New `faircode/compare.py`, `assets/profiler-compare.js`, SPEC §8, `tests/test_compare.py`
  - **Manual column mapping** (#62) - override auto-detection when a column is oddly named (`gndr`, `patient_region_code`). `faircode profile --map COL=KIND` (repeatable) and editable per-column dropdowns in the web profiler that re-run the audit in place. Forced columns are exempt from the high-cardinality drop. SPEC §1
  - **Reference-population baseline** (#56) - score a dataset against an external population (e.g. Census age×sex), not just internal balance. `faircode profile --reference baseline.csv` and a web upload; surfaces per-group expected-vs-actual deltas, a deviation metric, and under-representation-vs-reference flags. SPEC §9
  - **Choosable intersection pair** (#58) - cross any two demographic columns, not just the first two detected. `faircode profile --cross colA,colB` and two dropdowns in the web profiler. SPEC §4
  - **Chi-squared proxy hints** (#61) - opt-in `faircode profile --proxy-hints` flags strongly-associated column pairs (a "this may be a proxy for that protected attribute" signal) with p-values and Cramér's V. Python/CLI-only via the optional `scipy` extra; never affects the score, so the two engines stay in sync. New `faircode/proxy.py`, `tests/test_proxy.py`
  - **Tunable thresholds** (#63) - `--min-share`, `--intersection-floor`, `--imbalance-flag`, `--missing-flag` on the CLI, threaded through `profile(df, opts=...)` and the JS engine. SPEC §7
### Changed
- `faircode/profiler.py`: `profile()` gains an `opts` argument (thresholds, `cross`, `reference`) plus a `parse_reference()` helper; `detect_columns()`/`profile()` gain manual overrides
- `assets/profiler-engine.js`: mirrors the new `opts`, `parseReference`, and `compare` surface (verified bit-for-bit against the Python CLI)
- `assets/profiler-ui.js`, `profiler.html`, `assets/profiler.css`: column-mapping panel, cross-dimension selectors, and reference-baseline controls
- `pyproject.toml`: new optional `proxy` extra (`scipy`)
- `README.md`, `ROADMAP.md`: Open Dataset Profiler capabilities and Phase 5 status updated

---

## [1.2.4] - 12 Jul 2026
### Changed
- Live site domain moved from `fair-code-five.vercel.app` to **[thefaircode.xyz](https://www.thefaircode.xyz)**
  - `README.md`: live-website link, repository-structure comment, Open Dataset Profiler section, and Website section updated to the new domain
  - `SECURITY.md`: website-vulnerability scope link updated
  - `CITATION.cff`: `url` field updated
  - `pyproject.toml`: `project.urls.Website` updated
  - `.github/workflows/first.interaction.yml`: first-issue greeting link updated

---

## [1.2.3] - 12 Jul 2026
### Added
- Explainer: What Is Supervised Learning? - `supervised-learning.md` created, added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer covering the input-label-mapping mechanism behind every audit in this repo: features and a ground-truth label go in, a fitted model that generalises to unseen inputs comes out
  - Walks through `train_test_split` and `model.fit()` in the AI Fair Recruitment audit's `unfair.py` directly, showing the learning step has no way to distinguish a legitimate pattern from a discriminatory one
  - Real-world proof anchored to Audit 02 (AI Fair Recruitment): the published 4.51% gender hiring gap collapsing to 0.12% (97.3% reduction) once gender and age are dropped from the feature set, with German Credit Lending (Audit 03) referenced as a second supervised task with a different label type
  - Detection code: `train_supervised_classifier()` and `compare_label_vs_prediction_gap()` - pandas/scikit-learn training on labeled data plus a group-wise comparison of the label gap against the prediction gap on held-out rows
  - Four numbered limitations (label as proxy for the real target, matching labels not implying fairness, mapping expiry under population shift, generalization assuming the future resembles the past), cross-links to label-bias, ml-bias, distribution-shift, and calibration, and three further reading citations (Hastie, Tibshirani & Friedman; Barocas, Hardt & Narayanan; Mehrabi et al. 2021)
  - Nav dropdown (desktop + mobile), ticker strips, and roadmap updated on website
### Changed
- `README.md`: `supervised-learning.md` added to explainers table, repository structure tree, and What's Next checklist
- `CONTRIBUTING.md`: `supervised-learning.md` added to existing explainers table

---

## [1.2.2] - 10 Jul 2026
### Added
- Explainer: False Positives vs. False Negatives in Medical Risk Models - `false-positives-vs-false-negatives.md` created, added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer covering the false positive / false negative trade-off at a model's decision threshold, and why asymmetric clinical costs (a missed diagnosis vs. a false alarm) make this trade-off higher-stakes in medical risk models than elsewhere
  - Comparison table contrasting false positives and false negatives by immediate cost, downstream cost, and who absorbs each
  - Real-world proof anchored to Audit 06 (Healthcare Readmission): its published demographic parity gaps (race 0.08% to 0.06%, age 0.28% to 0.09%), paired with Obermeyer et al.'s 2019 finding that correcting a cost-as-proxy-for-illness algorithm would raise the share of Black patients identified for extra care from 17.7% to 46.5%
  - Detection code: `error_rate_gaps()` and `cost_weighted_threshold()` - pandas/scikit-learn group-wise FPR/FNR computation and a cost-weighted threshold sweep
  - Four numbered limitations (cost-ratio value judgments, per-group threshold vs. disparate treatment, small-subgroup FPR/FNR noise, equal error rates not guaranteeing equal outcomes), cross-links to equalized-odds, calibration, predictive-parity, and disparate-treatment, and three further reading citations (Obermeyer et al. 2019, Rajkomar et al. 2018, Chouldechova 2017)
  - Nav dropdown (desktop + mobile), ticker strips, and roadmap updated on website
### Changed
- `README.md`: `false-positives-vs-false-negatives.md` added to explainers table, repository structure tree, and What's Next checklist; corresponding item in the Healthcare AI Bias Focus "Upcoming" list replaced with a link to the published explainer; Traction explainer count updated to 24
- `CONTRIBUTING.md`: `false-positives-vs-false-negatives.md` added to existing explainers table

---

## [1.2.1] - 6 Jul 2026
### Added
- Explainer: Predictive Parity - `predictive-parity.md` created (contributed by @propcgamer20-png), added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer covering predictive parity as a sufficiency metric: Positive Predictive Value equal across groups, and why that is a fundamentally different fairness check than error-rate parity
  - Comparison table across Demographic Parity, Equalized Odds, and Predictive Parity by what each conditions on
  - Real-world proof anchored to Audit 01 (COMPAS): the 2016 ProPublica vs Northpointe dispute, where ProPublica's error-rate reading found a roughly 2x false-positive gap for Black defendants while Northpointe's predictive-parity reading found PPV close across race, and Chouldechova's proof for why both readings can be correct at once
  - Detection code: `predictive_parity_gap()` and `base_rate_gap()` - pandas group-wise PPV and base-rate computation, paired to surface the Chouldechova trade-off signature
  - Four numbered limitations (impossibility with Equalized Odds under unequal base rates, uneven harm despite equal PPV, small-subgroup PPV noise, threshold-tuning blind spot), cross-links to equalized-odds, demographic-parity, disparate-impact, and fairness-metric-conflicts, and three further reading citations (Angwin et al. 2016, Chouldechova 2017, Kleinberg et al. 2017)
  - Nav dropdown (desktop + mobile), ticker strips, and roadmap updated on website
### Changed
- `README.md`: `predictive-parity.md` added to explainers table, repository structure tree, and What's Next checklist
- `CONTRIBUTING.md`: `predictive-parity.md` added to existing explainers table

---

<details>
<summary><strong>Older releases (v1.2.0 and earlier)</strong> - click to expand</summary>

## [1.2.0] - "Open Tools & Causal Foundations" - 30 Jun 2026

First release since **v1.1.0** (9 Jun 2026). The headline is the **Open Dataset Profiler** - Fair Code's first interactive, bring-your-own-data tool, turning the project from a showcase of six fixed audits into something visitors run on their own CSVs. This release also bundles the six explainers shipped between v1.1.0 and now, which deepen the causal and statistical foundations behind the audits.

### Added - Open Dataset Profiler (CLI + web)
- **`faircode/` Python package + CLI** - the diagnostic counterpart to the audits: instead of measuring a *model's* prediction gap, it audits a *dataset's* demographic representation **before any model is trained** (no model, no train/test split, no proxy removal). `pip install -e .` exposes a `faircode profile <csv>` command with terminal, `--json`, and `--html` output.
  - Detects demographic columns (sex, race, age, geography) by tokenized, prefix-aware name matching; computes per-dimension metrics - subgroup shares, an entropy-based balance score (0–100) with A–F grade, imbalance ratio, under-represented groups (<5%), missing-data %, numeric-age skewness, and intersectional gaps - all defined once in `faircode/SPEC.md`
  - Pure **pandas**; deliberately **does not depend on `ydata-profiling`** (a heavy, general-purpose profiler) - only a thin, fairness-specific slice is needed, so the metrics are computed directly
  - Domain-agnostic: validated on health (`insurance.csv`, `diabetic_data.csv`) and non-health (`adult.csv`, COMPAS) datasets; correctly handles numeric ages, `[70-80)`-style interval ages, and drops date-of-birth/identifier columns
- **`profiler.html` - client-side web tool** - drop in a CSV (or hit "Try a sample") and get an instant representation audit in the browser. **The file never leaves the visitor's machine** - no upload, no backend - which matters for health data. Built in the "Audit Ledger" design system: score ring, per-dimension bar charts (green = balanced, red = under-represented), flags list, and intersectional gaps; light/dark theme; a `?demo` deep-link auto-loads the sample dataset
- **`assets/profiler-engine.js`** - a JavaScript port of the Python engine, **verified bit-for-bit identical** to the CLI across every bundled dataset (same scores, dimensions, flags) by sharing the `faircode/SPEC.md` spec
- **Tests + CI** - `tests/test_profiler.py` (14 tests) and a dedicated `profiler` job in `.github/workflows/audits.yml` that runs the tests and smoke-tests the CLI on every push and PR
- Wired into the site: a **Profiler** nav link and a feature callout on `index.html`

### Added - Explainers (shipped since v1.1.0)
- **What Is Machine Learning Bias?** - `ml-bias.md`: the four entry points through which bias enters a model (training data, labels, proxies, feedback loops); detection via `demographic_parity_report()` and `check_proxy()`; anchored to COMPAS *(prev. 1.1.1)*
- **What Is Data Leakage?** - `data-leakage.md`: target leakage vs. train-test contamination; `detect_target_leakage()` and `check_preprocessing_leakage()`; anchored to COMPAS `CustodyStatus` *(prev. 1.1.2)*
- **How AI Detects Patterns** - `how-ai-detects-patterns.md`: Random Forest splitting, aggregation, and feature importance, and why the model can't tell a causal pattern from a discriminatory one; `get_pattern_reliance()` and `flag_correlated_patterns()` *(prev. 1.1.3)*
- **What Is Distribution Shift?** - `distribution-shift.md`: covariate / label / concept drift and why a one-time fairness audit expires; `detect_covariate_shift()` (KS + chi-squared) and `detect_label_shift()` *(prev. 1.1.4)*
- **The Biggest Myth About AI Objectivity** - `ai-objectivity-myth.md`: why "it's just math" fails once a model is trained on biased history; `audit_objectivity_claim()` and `find_features_explaining_gap()`; anchored to COMPAS *(prev. 1.1.5)*
- **What Is a Confounding Variable?** - `confounding-variable.md`: how a hidden third variable creates spurious associations that survive protected-attribute removal, and confounder vs. proxy vs. collider; `check_confounding()`; anchored to COMPAS *(prev. 1.1.6)*
- Each explainer ships with a full write-up, detection code, numbered limitations, cross-links, and further reading, and was added to `index.html` (nav dropdown, ticker strips, roadmap), `README.md`, and `CONTRIBUTING.md`

### Added - Tooling
- `pyproject.toml` - packages the `faircode` console script (single dependency: pandas)

### Changed
- `README.md`: six new explainers added to the explainers table, repository-structure tree, and What's Next checklist (total: 23 explainers); new **Open Dataset Profiler** section and Contents entry; "Fairness audit web dashboard" and `faircode/` module boxes checked
- `ROADMAP.md`: Phase 5 - "Fairness audit web dashboard" and "Bias detection utility library (`faircode/` module)" marked complete, pointing to the Profiler
- `CONTRIBUTING.md`: six new explainers added to the explainers table
- `CITATION.cff`: version `1.0.0` → `1.2.0`; release date updated to 2026-06-30; abstract extended to cover welfare-eligibility audits and the dataset profiler
- `METRICS.md`: explainer count corrected to 23; week 2026-W27 snapshot noting the Profiler release
- `.gitignore`: ignores Python build/cache artifacts (`__pycache__/`, `*.egg-info/`, `build/`, `dist/`, `.pytest_cache/`)

---

## [1.0.5] - 9 Jun 2026
### Added
- Explainer: Proxy Entanglement - `proxy-entanglement.md` created (PR #49, commits 475de938, 64a90772), added to `index.html`, `README.md`, and `CONTRIBUTING.md` (commits c018d8e8, 476a2771, 46d534fa)
  - Full explainer covering proxy entanglement as the failure mode where multiple correlated features encode the same protected signal through independent administrative channels, requiring cluster-level removal rather than one-variable-at-a-time removal
  - Real-world proof anchored to Audit 06 (Healthcare Readmission): `payer_code` (Medicaid rate encodes race: Hispanic 9.0%, AfricanAmerican 5.5%, Caucasian 2.7%), `discharge_disposition_id` (SNF access: Caucasian 17.3% vs AfricanAmerican 10.7%), `medical_specialty` (insurance access and geography), and `number_inpatient` (prior hospitalisation count: AfricanAmerican 0.70 vs Asian 0.48) identified as an entangled cluster sharing a common causal root in structural inequality
  - Results: removing the full cluster produces 25% reduction in race gap and 68% reduction in age gap; single-variable removal leaves most of the bias mechanism intact
  - `detect_proxy_entanglement()` detection code: two-pass chi-squared analysis - each candidate proxy tested against the protected attribute first, then confirmed proxies cross-tested against each other to surface the entangled cluster
  - Entangled cluster table (feature → what it encodes → causal root), limitations table (causal root ambiguity, accuracy trade-off, base-rate sensitivity in large datasets, distinction from multicollinearity), takeaway callout, and three further reading links (Obermeyer et al. *Science* 2019, Chiappa & Isaac 2019, Kilbertus et al. 2017)
  - Nav dropdown (desktop + mobile), ticker strips (original and dupe), roadmap, AI Hallucinates footer pills, and RL roadmap item (previously live but missing from roadmap) updated on website
### Changed
- `README.md`: `proxy-entanglement.md` added to explainers table, repository structure tree, and What's Next checklist (commit c018d8e8)
- `CONTRIBUTING.md`: `proxy-entanglement.md` added to existing explainers table (commit 476a2771)

---

## [1.0.4] - 8 Jun 2026
### Added
- Audit 06: Healthcare Readmission - Clinical Bias (Diabetes 130-US Hospitals 1999–2008, 101,766 records)
  - `fair.py` and `unfair.py` added to `Healthcare Readmission/` (commits ba226003, cec4a098)
  - Jupyter notebook: `06_healthcare_readmission_bias_audit.ipynb` (commit 9a8abd07)
  - Protected attributes audited: race, gender, age
  - Proxy variables identified and removed: `payer_code` (Medicaid rate encodes race: Hispanic 9.0%, AfricanAmerican 5.5%, Caucasian 2.7%), `discharge_disposition_id` (SNF access encodes insurance and geography: Caucasian 17.3% vs AfricanAmerican 10.7%), `medical_specialty` (encodes insurance type and geography), `number_inpatient` (prior hospitalisation count encodes preventive care access gap: AfricanAmerican 0.70 vs Asian 0.48)
  - Results: race gap 0.08% → 0.06% (25% reduction), age gap 0.28% → 0.09% (68% reduction), gender gap 0.02% → 0.04% (increased - proxy variables carried no meaningful gender signal; documented honestly)
  - Healthcare Readmission audit added to CI workflow (commit 60b4aa7f)
  - `index.html` updated: project card added with terminal outputs, bias bars, and key insight; desktop and mobile nav updated with `06 - Healthcare Readmission` link (commit d93fd1cf)
### Changed
- `README.md` and `CONTRIBUTING.md` updated: audit 06 added to results table, repository structure tree, projects section, and What's Next checklist (commits eced8281, 3d6f4ead)
- `.gitignore` updated to prevent `.DS_Store` from being committed (commit a175c40c)

---

## [1.0.3] - 7 Jun 2026
### Added
- Explainer: Reinforcement Learning - `reinforcement-learning.md` created by evanjain-dot (PR #48, commit a785ea95), added to `index.html`, `README.md`, and `CONTRIBUTING.md` (commit e3928af7)
  - Full explainer covering the three-part RL loop (state → action → reward → policy), reward function design as a political act, reward hacking, and the credit assignment problem
  - Real-world proof using COMPAS as an RL-adjacent system: biased policy produces 86.77% Black/White fairness gap; removing race + `CustodyStatus` proxy reduces gap to 15.69% (71% reduction)
  - Results table: biased policy vs. race-only removal vs. race + proxy removal
  - Second case: YouTube recommendation engine using watch time as reward signal - documents asymmetric demographic consequences and outrage optimisation
  - `fairness_gap()` detection code with chi-squared proxy check for state representation audit
  - Limitations table: reward misspecification, credit assignment failure, proxy exploitation, political nature of reward asymmetry
  - Further reading: Dressel & Farid (Science Advances, 2018), Sutton & Barto (MIT Press, 2018), Krakovna et al. DeepMind specification gaming catalogue (2020)
  - Nav dropdown (desktop + mobile), ticker, and AI Hallucinates footer pills updated on website
### Changed
- `README.md`: `reinforcement-learning.md` added to explainers table, repository structure tree, and What's Next checklist
- `CONTRIBUTING.md`: `reinforcement-learning.md` added to existing explainers table, folder structure tree, and blocked concepts list
- `.github/workflows/update-changelog.yml` deleted - Dependabot auto-changelog workflow removed (commit d4f1c0bb, PR #47)
- `README.md`: `update-changelog.yml` description removed (commit 63edce9a)
- PR template refined for improved contributor guidance (commit e611e442)

---

## [1.0.2] - 5–6 Jun 2026
### Added
- Explainer: Why AI Hallucinates - `ai-hallucinations.md` created by Shreyash0712 (PR #43), added to `index.html`, `README.md`, and `CONTRIBUTING.md` (commits 928ae7ae, 68c4de61, 46cd32e8)
  - Full explainer covering hallucination as out-of-distribution confidence failure, real-world proof using the Insurance Denial audit (sparse BMI/smoking/diabetic sub-populations), tabular density vs. confidence table, `audit_hallucination_risk()` detection code, four mitigation patterns (retrieval-first, source grounding, adversarial verification, confidence calibration), and limitations (confabulation vs. extrinsic vs. intrinsic hallucination taxonomy, RAG limitations, RLHF over-conservatism)
  - Legally documented real-world case: *Mata v. Avianca, Inc.* (678 F.Supp.3d 443) - ChatGPT-fabricated court citations resulting in federal sanctions
  - Nav dropdown (desktop + mobile), ticker, roadmap, and explainer footer pills updated on website
- Branch protection rules documented in `CONTRIBUTING.md`: PRs required, CI must pass, force pushes blocked, branch deletion restricted (commit 6574b20b)
- First interaction workflow added for issues and PRs (commit 60874af6)
- Dependabot configuration added for Python packages with daily changelog updates (commits fa519387, 82f6b262, 9301061c)
### Changed
- `README.md`: `ai-hallucinations.md` added to explainers table, repository structure tree, and What's Next checklist; dataset structure section refactored (commits 9a0eab2e, 6574b20b)
- `CONTRIBUTING.md`: `ai-hallucinations.md` added to existing explainers table, folder structure tree, and blocked concepts list; branch protection steps documented
- Dependencies bumped by Dependabot: `scikit-learn` ≥ 1.9.0 (PR #41, commit d8c6f9b4), `numpy` ≥ 2.4.6 (PR #39, commit 98efd433), `pandas` ≥ 3.0.3 (PR #38, commit 01e747f5), `matplotlib` ≥ 3.10.9 (PR #37, commit 3fd010cb)

---

## [1.0.1] - 4 Jun 2026
### Added
- Explainer: What Happens Inside a Neural Network - `neural-networks.md` created, added to `index.html`, `README.md`, and `CONTRIBUTING.md` (commits 4ff97866, c1023432, d372c002, f997fc52)
  - Full explainer covering forward pass, weights, loss function, backpropagation, and the three-part training loop
  - Real-world proof using the AI Fair Recruitment dataset: 20.9% → 0.1% gender gap after removing gender + age proxy
  - SHAP inspection code, what-each-component-does table, limitations table, and further reading
  - Nav dropdown (desktop + mobile), ticker, roadmap, and counterfactual fairness footer pills updated on website
### Changed
- `README.md`: neural-networks.md added to explainers table, repository structure tree, and What's Next checklist
- `CONTRIBUTING.md`: neural-networks.md added to existing explainers table, folder structure tree, and blocked concepts list

---

## [0.8.1] - 2 Jun 2026
### Added
- Explainer: Counterfactual Fairness - `counterfactual-fairness.md` created by evanjain-dot (PR #31), added to `index.html`, `README.md`, and `CONTRIBUTING.md`
  - Full explainer with SCM formal definition, COMPAS policing causal chain proof, detection code (biased model → counterfactual audit → fair model fix), IF vs CF comparison table, limitations, and further reading
  - Nav dropdown, mobile nav, and roadmap updated on website
### Changed
- `README.md` updated: counterfactual fairness added to explainers table, repository structure tree, and What's Next checklist
- `CONTRIBUTING.md` updated: counterfactual fairness added to existing explainers table and blocked concepts list
- `index.html`: CI badge added to README (commit 63c49cd8); CONTRIBUTING.md CI audit checks documented (commit 37f960c6); README formatting fixes (commit 646a3560)

---

## [0.8.0] - 2 Jun 2026
### Added
- CI pipeline: `.github/workflows/audits.yml` - runs all audit scripts (`unfair.py` and `fair.py`) automatically on every push and pull request (PR by Anjali Tiwari)
### Changed
- Dataset paths standardised across all audit scripts so every script resolves its dataset relative to its own file location, scripts now run correctly from the repo root, from within their own folder, and in CI (PR by Anjali Tiwari)

---

## [0.7.0] - 1 Jun 2026
### Added
- Explainer: Individual Fairness - added to index.html, README, and concepts covered
### Fixed
- HTML section closing tag bug in index.html (impact section broken)
- Mobile nav max-height increased for full scrollability on small screens
- Dataset path corrected in AI Fair Recruitment `fair.py` / `unfair.py` scripts (PR by Anjali Tiwari)
### Changed
- Code of Conduct revised for clarity and inclusivity
- scipy and shap package versions corrected in requirements.txt
- `CHANGELOG.md` added to project structure

---

## [0.6.0] - 31 May 2026
### Added
- Explainer: Label Bias - added to index.html, explainers directory, and CONTRIBUTING.md
### Changed
- README updated with new bias topics and explainers

---

## [0.5.1] - 30 May 2026
### Changed
- CONTRIBUTING.md revised for improved instructions
- README refactored for clarity and formatting

---

## [0.5.0] - 28–29 May 2026
### Added
- Explainer: Disparate Treatment - added to index.html, README, and CONTRIBUTING.md
- Explainer: Feedback Loop Bias - added to index.html, README, and CONTRIBUTING.md
- Welfare/Benefits Denial project button and project data on website
### Changed
- README updated with feedback loop bias and disparate treatment explainers

---

## [0.4.2] - 26–27 May 2026
### Added
- Explainer: Demographic Parity - added to index.html and CONTRIBUTING.md
- Star History section added to README
- Vercel deployment badge added to README
### Changed
- README formatting fixes

---

## [0.4.1] - 24 May 2026
### Added
- GitHub Issue Templates: bug report, new audit proposal, new explainer proposal (YAML)
- Pull request template
### Changed
- CONTRIBUTING.md updated with templates information
- README updated with PR and issue template references

---

## [0.4.0] - 21–23 May 2026
### Added
- Explainer: Calibration - `calibration.md`, added to index.html, README, CONTRIBUTING.md
- Explainer: Fairness Metric Conflicts - `fairness-metric-conflicts.md`
- Search placeholder and explainer card text updated on website
### Fixed
- Formatting fixes in CONTRIBUTING.md and README.md
### Changed
- Merged PR #26 (sofiya-iii): file additions

---

## [0.3.0] - 22 May 2026
### Added
- Audit 05: Benefits Denial (UCI Adult Census Income, 48,842 records)
  - `fair.py` and `unfair.py` for welfare eligibility bias
  - Dataset added
  - Jupyter notebook: `05_benefits_denial_bias_audit.ipynb`
  - README updated with Benefits Denial section and results
### Changed
- CONTRIBUTING.md updated for Benefits Denial audit

---

## [0.2.2] - 21 May 2026
### Added
- All five Jupyter notebooks added (`01` through `05`)
- `CITATION.cff` for project citation guidelines
- `SECURITY.md` for vulnerability reporting policy
- `requirements.txt` updated with full dependencies and instructions
### Fixed
- Various small website bugs
- Accessibility improvements and style refactors in index.html
- Cursor style set to pointer for navigation items

---

## [0.2.1] - 19–20 May 2026
### Added
- Explainer: Disparate Impact (80% Rule) - added to index.html, README, CONTRIBUTING.md
- Explainer: Equalized Odds - merged via PR #13 (TanishGoyal-Dev)
- Explainer: SHAP Values - merged via PR #12 (shwetagupta1234)
- Search bar with filtering for projects and explainers
- Copy and share buttons on website
- Back-to-top button for mobile
### Changed
- Website styles refactored: light mode, dark mode, navigation dropdowns
- Navigation improved with social media links and dropdown menus
- `requirements.txt` updated with pandas and scikit-learn

---

## [0.2.0] - 18–19 May 2026
### Added
- Audit 04: Insurance Denial (Kaggle, 1,340 records)
  - `fair.py`, `unfair.py`, dataset, and proof images
  - README and CONTRIBUTING.md updated
- Explainer: Sampling Bias - merged via PR #2 (evanjain-dot)
- `shap-values.md` added to explainers directory
- `CODE_OF_CONDUCT.md` added
### Changed
- CONTRIBUTING.md refined for explainer and audit submission guidelines
- README revised for project names, structure, and clarity

---

## [0.1.0] - 17–18 May 2026
### Added
- Audit 03: German Credit Lending Bias - merged via PR #1 (Aarav Sharma)
  - Random Forest model, dataset, `fair.py` / `unfair.py`
- Explainer section added to website with responsive styles
- Navigation dropdowns implemented in index.html
- Social media links added to navigation
### Changed
- README revised for project overview and results
- CONTRIBUTING.md created with audit guidelines

---

## [0.0.0] - 13–16 May 2026
### Added
- Audit 01: COMPAS Criminal Justice Bias (ProPublica, 70k+ records)
  - `fair.py`, `unfair.py`, dataset, proof images
- Audit 02: AI Fair Recruitment Bias (Kaggle)
  - `fair.py`, `unfair.py`, dataset, proof images
- Interactive website (`index.html`) deployed at fair-code-five.vercel.app
  - Light mode, mobile-responsive layout
- README with project overview, results table, and methodology

</details>
