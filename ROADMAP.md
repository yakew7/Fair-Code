<div align="center">

# Fair Code - Public Roadmap

![Phase 1](https://img.shields.io/badge/Phase%201-Complete-brightgreen?style=flat-square)
![Phase 2](https://img.shields.io/badge/Phase%202-In%20Progress-yellow?style=flat-square)
![Phase 3](https://img.shields.io/badge/Phase%203-In%20Progress-yellow?style=flat-square)
![Phase 4](https://img.shields.io/badge/Phase%204-In%20Progress-yellow?style=flat-square)
![Phase 5](https://img.shields.io/badge/Phase%205-In%20Progress-yellow?style=flat-square)
![Phase 6](https://img.shields.io/badge/Phase%206-Paused%20%2D%20Retargeted-lightgrey?style=flat-square)

This is the public roadmap for Fair Code. It tracks what has been built, what is actively in progress, and what comes next.

*Last updated: September 2026*

[Where We Are](#where-we-are) · Phase 1 · Phase 2 · Phase 3 · Phase 4 · Phase 5 · Phase 6 · [Content Schedule](#content-schedule) · [How to Contribute](#how-to-contribute)

</div>

---

## Where We Are

Fair Code is an open-source responsible AI platform explaining algorithmic bias, fairness, and AI accountability through code audits, explainers, healthcare-bias case studies, and contributor-led GitHub documentation.

**Current traction (October 2026):**

| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits | Explainers | CI |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 49 | 50 | 55 | 8 | 30K+ | 20 | 7 | 62 | ✅ every push/PR |

> The earlier paper freeze has lifted - the real paper, with fresh results, is now planned for next
> year. `paper/results-frozen/` (tag `v1.0-paper`, commit `bbef2ba`) is kept as a reference snapshot.
> See [CLAUDE.md](CLAUDE.md) for the current policy.

**Version & release gate:**

- Current release: **v2.3.0**
- The next major version can now bundle a re-run benchmark and new audits without waiting on a
  publication gate - Phase 6 below reflects the earlier plan and will be revisited alongside next
  year's real paper submission.

---

## Phase 1 - Bias Glossary and Beginner Explainers ✅

**Status: Foundational library complete - 62 explainers published, past the original 60+ target, working toward 65+**

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

**Status: Goal exceeded - 50 external contributors, past the original 15+ target**

Goal: grow to 15+ contributors with quality-controlled contributions.

- [x] CONTRIBUTING.md
- [x] Issue templates (bug report, new audit, new explainer)
- [x] PR template
- [x] CODE_OF_CONDUCT.md
- [x] CI pipeline (all audit scripts run on push/PR)
- [x] Good-first-issue and help-wanted labels
- [x] First-interaction workflow (greets new contributors)
- [ ] Target: 10–15 labelled issues open at all times (currently 18 - a moving snapshot, not a maintained invariant; no automated mechanism keeps it true over time)
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
- [ ] Proxy and MCP follow-ups: the MCP `proxy_hints` tool honouring `max_age`/`age_reference_year`/`keywords` (#883), Unicode-safe key normalisation (#884), a visible note when `--proxy-exact` is capped (#885), faster permutation p-values (#886), per-spec key normalisation on the CLI (#895), held-out encodings in provenance (#892)
- [ ] Compare and web polish: renames in the compare CSV (#896) and from column-name similarity (#887), keywords textarea persistence and error text (#888, #889), the reference baseline honouring the encoding picker (#890)
- [ ] Dashboard and tooling: Export colours in the deep link (#893), a key for the hatched bars (#894), and a `slow` marker so the benchmark tests do not dominate local runs (#891)

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
- [ ] Submit manuscript to peer review (next year, with fresh results)
- [ ] Address reviewer feedback
- [ ] Paper accepted and published
- [ ] Add citation and DOI to [README.md](README.md) and [CITATION.cff](CITATION.cff)
- [x] Development reopened: `results/`, audits, and the analysis core are unfrozen; `paper/results-frozen/` stays untouched as the historical reference for this earlier snapshot

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

*Fair Code is maintained by [Yash Kewlani](https://github.com/yakew7). Follow the project at [@thefaircodeproject](https://instagram.com/thefaircodeproject).*
