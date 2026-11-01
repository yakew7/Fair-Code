<div align="center">

# Fair Code - Public Roadmap

![Phase 1](https://img.shields.io/badge/Phase%201-Complete-brightgreen?style=flat-square)
![Phase 2](https://img.shields.io/badge/Phase%202-In%20Progress-yellow?style=flat-square)
![Phase 3](https://img.shields.io/badge/Phase%203-In%20Progress-yellow?style=flat-square)
![Phase 4](https://img.shields.io/badge/Phase%204-In%20Progress-yellow?style=flat-square)
![Phase 5](https://img.shields.io/badge/Phase%205-In%20Progress-yellow?style=flat-square)
![Phase 6](https://img.shields.io/badge/Phase%206-Paused%20%2D%20Retargeted-lightgrey?style=flat-square)

This is the public roadmap for Fair Code. It tracks what has been built, what is actively in progress, and what comes next.

*Last updated: October 2026*

[Where We Are](#where-we-are) · Phase 1 · Phase 2 · Phase 3 · Phase 4 · Phase 5 · Phase 6 · [Content Schedule](#content-schedule) · [How to Contribute](#how-to-contribute)

</div>

---

## Where We Are

Fair Code is an open-source responsible AI platform explaining algorithmic bias, fairness, and AI accountability through code audits, explainers, healthcare-bias case studies, and contributor-led GitHub documentation.

**Current traction (October 2026):**

| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits | Explainers | CI |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 54 | 58 | 67 | 8 | 30K+ | 20 | 7 | 108 | ✅ every push/PR |

> The earlier paper freeze has lifted - the real paper, with fresh results, is now planned for next
> year. `paper/results-frozen/` (tag `v1.0-paper`, commit `bbef2ba`) is kept as a reference snapshot.
> See [CLAUDE.md](CLAUDE.md) for the current policy.

**Version & release gate:**

- Current release: **v2.3.0**
- The next major version can now bundle a re-run benchmark and new audits without waiting on a
  publication gate. Phase 6 below lists the prerequisites for next year's real paper submission
  that can start now (a fresh full run, a snapshot diff, a venue decision, and the next freeze
  trigger).

---

## Phase 1 - Bias Glossary and Beginner Explainers ✅

**Status: Foundational library complete - 114 explainers published, past the original 60+ target and the 90+ goal, working toward 120+**

Build the foundational vocabulary and explain core fairness concepts clearly enough for a non-technical reader.

- [x] Proxy Variables
- [x] Equalized Odds
- [x] Sampling Bias
- [x] SHAP Values
- [x] Disparate Impact (The 80% Rule)
- [x] Disparate Treatment
- [x] Why Fairness Metrics Conflict
- [x] Calibration
- [x] Demographic Parity
- [x] Feedback Loop Bias
- [x] Label Bias
- [x] Individual Fairness
- [x] Counterfactual Fairness
- [x] What Happens Inside a Neural Network
- [x] Why AI Hallucinates
- [x] What Is Reinforcement Learning
- [x] Proxy Entanglement
- [x] What Is Machine Learning Bias
- [x] What Is Data Leakage
- [x] How AI Detects Patterns
- [x] What Is Distribution Shift
- [x] The Biggest Myth About AI Objectivity
- [x] What Is a Confounding Variable?
- [x] What Is Predictive Parity?
- [x] False Positives vs. False Negatives in Medical Risk Models
- [x] What Is Supervised Learning?
- [x] What Is Unsupervised Learning?
- [x] What Is Model Drift?
- [x] What Is Selection Bias?
- [x] What Is Automation Bias?
- [x] What Is a ROC Curve and AUC?
- [x] What Is a Protected Attribute?
- [x] What Is a Confusion Matrix?
- [x] What Is Class Imbalance?
- [x] What Is the Bias-Variance Trade-off?
- [x] What Is the Base Rate Fallacy?
- [x] What Is Reject Inference?
- [x] What Is a Precision-Recall Curve?
- [x] What Is Algorithmic Recourse?
- [x] What Is Max-Min (Rawlsian) Fairness?
- [x] What Is Distributionally Robust Optimization (DRO) for Fairness?
- [x] What Is Fairness in Ranking?
- [x] What Is Reweighing?
- [x] What Are Group-Specific Thresholds?
- [x] What Is a Permutation Test for a Fairness Gap?
- [x] What Is Adversarial Debiasing?
- [x] What Is a Fairness Regularizer?
- [x] What Is Fair Representation Learning?
- [x] What Is Measurement Bias?
- [x] What Is Aggregation Bias?
- [x] What Is Survivorship Bias?
- [x] What Is Disaggregated Evaluation?
- [x] What Is Leave-One-Group-Out Evaluation?
- [x] How Do You Choose a Fairness Metric?
- [x] What Is a Model Card?
- [x] What Is a Datasheet for a Dataset?
- [x] What Is an Algorithmic Impact Assessment?
- [x] How Do You Measure Fairness When the Protected Attribute Is Missing?
- [x] What Is Fairness Without Demographics?
- [x] Adverse Action Notices
- [x] Geographic Proxies and Redlining
- [x] Risk-Based Pricing Gaps
- [x] Race in Clinical Models
- [x] Utilization as a Label
- [x] Discharge Leakage in Readmission Models
- [x] Seed and Split Sensitivity
- [x] Cross-Validation for Fairness
- [x] Stratified Test Sets for Fairness
- [x] Feature Importance by Group
- [x] Partial Dependence by Group
- [x] Explanation Disagreement
- [x] Hiring Pipeline Adverse Impact
- [x] Compounding Disparities
- [x] Differential Validity
- [x] Minimum Detectable Gap
- [x] Small-Group Shrinkage
- [x] Confidence Intervals for Ratios
- [x] Monitoring Fairness in Production
- [x] Label Shift and Fairness
- [x] Delayed Feedback
- [x] Causal Graphs for Fairness
- [x] Path-Specific Effects
- [x] Randomized Post-Processing
- [x] Fairness-Accuracy Pareto Frontier
- [x] Choosing a Mitigation Strategy
- [x] What Is an AUC Gap Between Groups?
- [x] What Is Decision Curve Analysis by Group?
- [x] How Does Unequal Cost Change a Fairness Evaluation?
- [x] What Is Popularity Bias?
- [x] What Is Two-Sided Fairness in a Marketplace?
- [x] How Does Position Bias Distort What a Ranking Learns?

---

## Phase 2 - Healthcare AI Bias Examples ✅ / 🔄 In Progress

**Status: Audits complete - healthcare explainers shipped alongside them**

Publish healthcare-specific bias audits and explainers that show how AI discrimination shows up in clinical and insurance contexts.

- [x] Insurance Denial bias audit
- [x] Benefits Denial bias audit
- [x] Healthcare Readmission bias audit
- [x] Jupyter notebooks for all three healthcare audits
- [x] Explainer: Why Accuracy Is Not Enough in Healthcare AI
- [x] Explainer: False Positives and False Negatives in Medical Risk Models
- [x] Explainer: Miscalibration in Clinical Risk Scores Across Groups - when the same risk score means a different real-world risk depending on the patient's group
- [x] Explainer: Missing Data as Bias in Electronic Health Records - how unequal access to care turns into unequal missingness, and how models misread it
- [x] Explainer: Why Medical Imaging Models Fail on Underrepresented Groups - representation gaps in imaging datasets and the skin-tone / equipment confounders they hide
- [x] Case study write-up: Insurance Denial Bias 
- [x] Case study write-up: Benefits Denial Bias (standalone 
- [x] Case study write-up: Healthcare Readmission Bias 
- [x] Explainer: Race Correction in Clinical Algorithms - why "race-adjusted" formulas (eGFR kidney function, spirometry, VBAC calculators) bake bias directly into the math
- [x] Explainer: The Obermeyer Case - When Cost Becomes a Proxy for Health Need - a dedicated case study of the 2019 algorithm that under-referred sicker Black patients
- [x] Explainer: Underdiagnosis Bias - When the Label Itself Is Sicker for One Group - why historical care gaps make the training target unequal before modeling starts

No further healthcare explainers are currently planned - the backlog from this phase is now fully shipped.

---

## Phase 3 - Code Audits 🔄 In Progress

**Status: 7 of 9 planned audits published - the remaining two are open to contribute**

Each audit follows the same pipeline: train a biased model → measure the fairness gap → remove proxies → retrain → measure again. New audits now merge to `main` as usual (see [CLAUDE.md](CLAUDE.md)).

- [x] COMPAS - Criminal Justice Bias
- [x] AI Fair Recruitment - Hiring Bias
- [x] German Credit Lending - Lending Bias
- [x] Insurance Denial - Healthcare Bias
- [x] Benefits Denial - Welfare Eligibility Bias
- [x] Healthcare Readmission - Clinical Bias
- [x] Tenant Screening - Rental Application Bias
- [ ] LLM bias audit
- [ ] HMDA Mortgage Lending Bias
- [ ] Facial Recognition Accuracy Gaps (MIT Gender Shades methodology)

---

## Phase 4 - Contributor Expansion 🔄 In Progress

**Status: Goal exceeded - 52 external contributors, past the original 15+ target**

Goal: grow to 15+ contributors with quality-controlled contributions.

- [x] CONTRIBUTING.md
- [x] Issue templates (bug report, new audit, new explainer)
- [x] PR template
- [x] CODE_OF_CONDUCT.md
- [x] CI pipeline (all audit scripts run on push/PR)
- [x] Good-first-issue and help-wanted labels
- [x] First-interaction workflow (greets new contributors)
- [ ] Target: 10–15 labelled issues open at all times (a moving snapshot, not a maintained invariant; no automated mechanism keeps it true over time)
- [x] Contributor list in README
- [x] METRICS.md tracking contributor growth weekly

---

## Phase 5 - Fairness Metrics and Notebooks ✅

**Status: Complete - cross-domain benchmark harness and its interactive results dashboard both shipped**

Go deeper on measurement - fairness dashboards, interactive notebooks, and statistical tools for auditors.

- [x] Fairness audit web dashboard - **Open Dataset Profiler** ([profiler.html](profiler.html))
- [x] Bias detection utility library (`faircode/` module) - diagnostic representation profiler + CLI
- [x] Profiler: two-dataset comparison for representation drift (`faircode compare`, PSI)
- [x] Profiler: manual column mapping, reference-population baseline, choosable intersection pair, tunable thresholds, and chi-squared proxy hints
- [x] Fairlearn integration: `ExponentiatedGradient` in-processing + `ThresholdOptimizer` post-processing, as two rungs of a five-strategy mitigation ladder (S0-S4) run uniformly across every audit
- [x] Cross-domain benchmark harness - declarative `audit.yaml` manifests (`faircode/MANIFEST_SPEC.md`) + `faircode benchmark`: 5 strategies x 3 model families x 6 fairness metrics (bootstrap CI + permutation p-value) + accuracy/AUC/F1, written to `results/`
- [x] Intersectional bias notebook (auditing across multiple protected attributes simultaneously)
- [x] Statistical significance testing for fairness gaps
- [x] Fairness dashboard for the benchmark harness results (interactive `results/` explorer, mirroring the Open Dataset Profiler's web/CLI split) - [benchmark.html](benchmark.html)
- [x] Export parity: `--csv` on `faircode profile`/`compare` plus matching web Download CSV buttons, proxy-hint detection and a significance-level control on CLI, MCP and web, and a `--sample` demo dataset
- [x] Proxy-hint depth: multiple-comparison correction, any number of held-out (already-dropped) columns per dataset in the CLI, MCP and web, and CSV provenance, with a benchmark-dashboard roll-up tab, per-audit figures and chart download
- [x] Proxy-hint trustworthiness: small-expected-cell warnings (#810), the number of pairs tested behind `p_adjusted` (#821), held-out files recorded in provenance (#811), an optional join key instead of row order (#822), and ignored-sheet notes for held-out workbooks on the web (#816)
- [x] Input robustness and data quality: `--encoding` plus BOM sniffing (#843), terminal-safe output (#845), implausible-age flagging with `--max-age` (#840), Spanish/German/French/Portuguese column names (#847), and `compare --csv` rows for one-sided dimensions (#842)
- [x] Benchmark dashboard polish: a significance filter on the roll-up tab (#819) and chart export that follows the page theme with Light/Dark/Transparent options (#813)
- [x] Detection and encodings: `estado_civil` no longer typed as geography (#855), user-extensible vocabulary via `--keywords` plus Italian/Dutch built-ins (#856), a web encoding picker (#857) and the encoding recorded in provenance (#858)
- [x] Proxy follow-ups: composite and normalised held-out keys (#859), provenance on the MCP `proxy_hints` tool (#860), an exact-test fallback for small cells (#861), colon-named held-out columns (#869)
- [x] Age handling: birth-year conversion with `--age-reference-year` (#862) and negative-sentinel flagging (#863)
- [x] Dashboard and compare: a per-tab significance toggle (#864), a hatch cue and colour-blind palette (#865), rename suggestions (#866) and data-quality flags (#868) in `compare`, `--csv-bom` (#867) and an ignored-`--encoding` notice (#870)
- [x] Proxy and MCP follow-ups: the MCP `proxy_hints` tool honouring `max_age`/`age_reference_year`/`keywords` (#883), Unicode-safe key normalisation (#884), a visible `chi2-capped` note when `--proxy-exact` is capped (#885), faster permutation p-values (#886), held-out encodings in provenance (#891) and per-spec key normalisation on the CLI (#892)
- [x] Compare and web polish: rename suggestions for recoded labels (#887) and in the compare CSV (#896), keywords textarea persistence and error text (#888, #889), the reference baseline honouring the encoding picker (#890)
- [x] Dashboard and tooling: Export colours in the deep link (#893), a key for the hatched bars (#894), and a `slow` marker with `make test-fast` so the benchmark tests do not dominate local runs (#895)
- [x] Reproducibility and parity: Python/JS key-normalisation parity for trimmed characters and case folding (#897, #911), proxy alpha/correction/exact and the xlsx sheet recorded in provenance (#898, #899), `42.0` against `42` keys (#903), the `~` and `!` markers in the CLI and web (#907, #912), per-file held-out encodings (#914), and a Copy as CLI command button (#915)
- [x] Compare, web and exact-test: rename suggestions from column names (#902) and `--rename` to act on them (#913), the reference baseline re-applied when the picker changes (#900), synced keyword boxes (#901), the Summary-tab chart key (#905), exact-test shuffles and row cap as parameters (#906) with a re-measured cap (#909), near-unique held-out columns skipped with a note (#908), and a pre-push hook and `slow` marker that keep the fast suite near 30 s (#904, #910)
- [x] Held-out, key and exact-test hardening: shuffles capped and configurable in the web (#925, #926), skipped near-unique columns in JSON and provenance (#921), encoding notices and `@ENCODING` in the web (#923, #924), NFKC key folding and a case-folding generator (#935, #939), group-count tolerance and `--rename` pairs in the compare CSV (#918, #920), plus contributor fixes for rename tokens, identity renames and numeric ages (#917, #919, #937)
- [x] Copy as CLI command and docs: `--sample`, export options and quoting tests (#928, #929, #934), the restored-keywords note (#930), README held-out syntax and the MCP parameter tables (#922, #931), the asset-source record for `brag-output/` (#936), one coverage run in CI (#932), a faster OG-image test (#933), the PRNG oracle in the tests (#927) and a split parity test file (#938)
- [x] Portability, reproducibility and checks: no regex lookbehind in browser scripts (#956), web exports with `tested: false` and notes (#951), a verified case-folding table (#946), `\=` in held-out paths (#958), a named near-unique constant (#957), the compare HTML rename sections (#953), one MCP `notes` key (#950), an explicit held-out report (#947), parsed README commands (#948), a roadmap issue-number checker (#963), the SPEC proxy section (#955) and the brag-output licences (#954)
- [x] Web and test hardening: inline errors for the exact inputs (#962), a content-named keywords file (#944), the workbook encoding notice (#952), `pythonpath` for shared helpers (#945), and tests for `python -m faircode`, compare flags, MCP reader errors, delimiter sniffing, proxy-hint rendering and rename tolerance (#966, #959, #965, #964, #960, #949)
- [x] Engine parity and correctness: only ASCII digits in the numeric check (#967), a repeated held-out column after a skip (#980), array and object columns skipped by the web engine (#973), a loud failure for an unhandled subcommand (#971), and tests for the validation, empty-subgroup, manifest, stdin, `--rename`, `--keywords`, `--csv -` and provenance branches (#968-#970, #972, #974-#979)
- [x] Web and tooling: shared helpers for the two views (#983), a browser-level smoke test with its own workflow (#988), an MCP stdio test and the alias removal plan (#987, #984), a missing-node fallback for the key-fold check (#982), the issue-number checker for contributors and metrics (#981) and a smaller profile parity test file (#985)
- [x] Engine and loader fixes: nested JSON objects in the web engine (#992), mixed number and string labels (#993), unused pandas categories (#994), empty files (#1010), unreadable reference shares (#1002) and the row-filter rules in MANIFEST_SPEC (#999)
- [x] Tooling, web and test follow-ups: a clear message when the mcp extra is missing (#995), one source for the web version (#996), `make test-browser` (#997), more browser interactions (#1000), the shared view helpers (#1008) and tests for compare HTML, metrics, loaders, sniffing, workbooks and the figures command (#1001, #1003-#1007)
- [x] Label and number parity between the engines: float-looking codes, booleans, `1.0`, large integers, exponents and the order of labels outside the BMP (#1011-#1016)
- [x] Input handling: `.xls` (#1018), binary files, JSON Lines, ragged rows, unterminated quotes, NUL bytes and JSON `NaN` (#1019, #1023-#1027)
- [x] Reports and gates: `compare --fail-on-drift` with nothing to compare (#1017), long group labels (#1021), an empty proxy-hint result (#1022), blank reference shares (#1028), the em-dash check's file types (#1020) and labels that differ only in case (#1009)
- [x] Engine parity follow-ups: JSON strings `NA` and empty (#1036), XLSX dates (#1039), numeric and blank headers (#1045, #1046), long labels that still collide (#1038)
- [x] Scale and flags: quadratic flag building and tens of thousands of flags for a high-cardinality column in the profile and compare views (#1042, #1043, #1052)
- [x] MCP, CLI and docs follow-ups: `--fail-under` range (#1037), undocumented benchmark flags (#1040), unknown benchmark filters (#1041), proxy hints on one dimension (#1044), the citation version (#1047), stale benchmark and snapshot wording (#1048, #1049), workflow timeouts (#1050), the leaked workbook handle (#1051), subprocess coverage (#986) and the contributor notes for the new checks (#989)
- [x] Tooling and tests for the results workflow: `scripts/diff_results.py` (#1065) with `--audit` and `--summary` (#1081), `get_benchmark_results` with a `source` argument (#1049) and its README parameters (#1082), a public `load_audit()` helper (#1078), browser tests for the flag caps (#1080), an opt-in `benchmark-diff` workflow for lockfile bumps (#1079), grouped Dependabot updates (#1069), a check that README and `llms.txt` list every explainer (#1077), 1904-system XLSX dates (#1076), and the no-op `frozen-files` workflow removed (#1061)
- [x] Metrics, SEO and test hardening: no `disparate_impact_ratio` when the advantaged group is almost never selected (#1094), page titles and meta descriptions within search limits (#1104, #1105), a Limitations section and two inbound links for every explainer (#1107, #1108), and the explainer build tested end to end (#1110)
- [x] Tooling sweep: an ignore list for links the external-link check cannot verify (#1174), the dead NIJ dataset link (#1175, #1186), OG images that are no longer rewritten on another machine (#1144), `scripts/check_contributors.py` (#1149) and `check_traction.py --live` with a weekly workflow (#1148)
- [ ] Tooling follow-ups: a failing generated-files test on a clean checkout (#1192), stale ignore entries and a shared retry path in the link check (#1193, #1194, #1196), archive lookups for 403 links (#1195), OG card inputs (#1197, #1198), contributor checks (#1199, #1200, #1201), traction and METRICS (#1202), partial benchmark reruns, progress and convergence tests (#1203, #1204, #1205), workflow docs, templates and tests (#1206, #1207, #1209, #1210) and a dataset-link check (#1208)

---

## Phase 6 - Research Paper and Publication - Paused, Retargeted for Next Year

**Status: Freeze lifted - the manuscript was never actually submitted this cycle**

The original plan was to publish a peer-reviewed paper on the cross-domain fairness benchmark and
freeze the repo's results against it. The manuscript submission step never actually happened, so
freezing development ahead of it was premature - the freeze has been lifted (see
[CLAUDE.md](CLAUDE.md)), and this phase is retargeted for a real submission **next year**, built on
a fresh run of results.

- [x] Freeze benchmark results at tag `v1.0-paper` (commit `bbef2ba`) - kept as a reference snapshot
- [x] `CLAUDE.md` paper-freeze policy for the benchmark and audits - lifted; will be re-established for next year's real submission
- [x] Development reopened: `results/`, audits, and the analysis core are unfrozen; `paper/results-frozen/` stays untouched as the historical reference for this earlier snapshot

**Prerequisites that can start now** (nothing below waits for the submission date):

- [x] **Fresh full benchmark run on the current lockfile** - rerun `faircode benchmark` on `requirements-lock.txt` and refresh `results/` (tracked in [#1068](https://github.com/yakew7/Fair-Code/issues/1068)). This is the run the paper will be built on, so doing it early shows what moved.
- [x] **Compare it with the earlier snapshot** - `python3 scripts/diff_results.py` lists every row that moved against `paper/results-frozen/`; explain each flagged row before it goes into a manuscript.
- [x] **Decide how library bumps are handled** - Dependabot groups the harmless updates and keeps `numpy`, `pandas`, `scikit-learn`, `scipy`, `fairlearn` and `matplotlib` as one PR each, with a benchmark diff before merging (see [CONTRIBUTING.md](CONTRIBUTING.md#dependency-updates)).
- [ ] **Choose the target venue** - a maintainer decision, to be written here. It sets the page limit, the artifact and reproducibility requirements, and the submission window, so it comes before any manuscript writing. Candidates to weigh are a fairness-and-accountability conference, a datasets-and-benchmarks track, or a journal.
- [ ] **Define the next freeze trigger** - the freeze starts when all of these hold: the venue is chosen, the full run above is merged, the `audit.yaml` manifests and the seven audits are final for the paper, and a maintainer has tagged the snapshot. Until then the repo stays fully open; when it starts, `CLAUDE.md` and `CONTRIBUTING.md` are updated in the same PR.

**Gated on the submission date** (next year):

- [ ] Submit manuscript to peer review (with the fresh results)
- [ ] Address reviewer feedback
- [ ] Paper accepted and published
- [ ] Add citation and DOI to [README.md](README.md) and [CITATION.cff](CITATION.cff)

---

## Content Schedule

**During school:**
- Monday: AI bias explainer
- Wednesday: Healthcare AI / fairness example
- Friday: Code audit or project update

**During holidays:**
- Monday–Friday posting acceptable if sustainable

---

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) to claim an open issue or propose a new audit or explainer.

New audits are welcome and merge into `main` like any other contribution - the earlier freeze on new audits has lifted. Explainers, docs, and website content merge as usual too. See [CLAUDE.md](CLAUDE.md) before opening a PR.

---

*Fair Code is maintained by [Yash Kewlani](https://github.com/yakew7). Follow the project at [@thefaircodeproject](https://www.instagram.com/thefaircodeproject).*
