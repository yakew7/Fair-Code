# Contributing to Fair Code

<div align="center">

**Bias audits. Clear explainers. Reproducible results.**

[Issue templates](.github/ISSUE_TEMPLATE/) are the preferred way to claim work before you start.

</div>

> **Before opening a PR, read [CLAUDE.md](CLAUDE.md)** for the current project policy.

Thanks for contributing. Fair Code accepts two kinds of additions:

- **Audits** - a real dataset, a biased model, a fair model, proxy analysis, and before/after results
- **Explainers** - a clear explanation of a fairness concept, with examples and runnable code

Consistency matters here. It is what makes the repo credible and easy to review.

---

## Contributing right now

The repo's earlier paper freeze has lifted (see [CLAUDE.md](CLAUDE.md)) - development is fully open:

- **Audits** merge to `main` as usual, same as any other contribution.
- **Everything else** - explainers, website content, documentation, `faircode/` changes, tests, tooling - is open too.
- **`requirements-lock.txt`** no longer needs special handling; Dependabot's version-bump PRs against it can be reviewed and merged like any other dependency update (see [Dependency updates](#dependency-updates)).

**When running a new audit:** New audits and reruns should update `results/` only. Do not modify `paper/results-frozen/` or the `v1.0-paper` tag when contributing new results. Run `python3 scripts/freeze_paper_results.py` only when deliberately creating a new reference snapshot for a paper. This script replaces the existing frozen snapshot and mirrors its CSV files into `faircode/_results_frozen/`, so do not run it as part of an ordinary audit.

**One rule for explainers:** if your explainer quotes a Fair Code result, say which source it's from - `results/` (current) or [`paper/results-frozen/`](paper/results-frozen/) (an earlier reference snapshot, kept for comparison) - so a reader isn't left guessing which numbers are live.

Full policy: [CLAUDE.md](CLAUDE.md).

---

## Quick path

1. Check the roadmap in [README.md](README.md#whats-next).
2. Open an issue using the matching template.
3. Build your audit or explainer to match the structure below.
4. Open a PR and include the requested proof.

If you are unsure whether an idea fits, open an issue first and ask.

> **Contributing to the Open Dataset Profiler?** The `faircode/` CLI and the client-side
> `profiler.html` share one analysis spec - [`faircode/SPEC.md`](faircode/SPEC.md). Any change to
> the metrics, thresholds, detection rules, or result fields **must** be made in `faircode/profiler.py` **and**
> `assets/profiler-engine.js` together, and must keep them producing identical results (run
> `pytest tests/` and cross-check a CSV through both). The same rule covers the two-dataset
> **compare** (drift) view: `faircode/compare.py` and `assets/profiler-compare.js` must agree too,
> enforced by `tests/test_js_parity_profile.py::test_python_js_compare_parity` (via `scripts/engine-js.js compare`).
> HTML report changes need the same treatment on both sides: `faircode/report.py`'s `to_html`/
> `compare_to_html` and their hand-ported equivalents in `assets/profiler-ui.js`/
> `assets/profiler-compare.js`. Update `SPEC.md` first - it is the source of truth.

---

## Local setup and checks

A `Makefile` and a `.pre-commit-config.yaml` reproduce what CI runs, so you can catch failures before you open a PR:

```bash
make setup             # install faircode + pytest + pre-commit + ruff
make check             # everything CI runs: environment check (`make doctor`) + lint + full test suite + audits
make test              # just the test suite
make test-fast         # the suite minus the ~80 s model-training benchmark tests (marked `slow`) and the Chromium tests (`make test-browser`), on every core when pytest-xdist is installed (about 35 s instead of 95 s on an idle 8-core laptop; `make setup` installs it) and with the ten slowest tests listed; CI still runs everything; the pre-push hook uses the same fast set
make audits            # every audit's unfair.py/fair.py + the CLI smoke tests (mirrors audits.yml's required run-audits job, plus the profiler/benchmark-harness jobs' CLI steps)
make setup-browser     # once: install Playwright + Chromium for the browser smoke test (tests/browser, #988)
make test-browser      # open profiler.html, benchmark.html and index.html in Chromium; fails on any console error
make coverage          # test suite with pytest-cov line coverage (informational, not a CI gate)
make build-explainers  # regenerate explainer pages, sitemap, and OG images (dark + light) after editing explainers/*.md
python3 scripts/generate_og_images.py --force  # re-render every existing OG image (by default a card whose PNG exists is skipped, so adding one explainer changes only its two PNGs); use after changing the card design or an explainer's title or summary
make fix-explainer-count  # correct any stale "N explainers" mention in README/CONTRIBUTORS/METRICS/ROADMAP after adding/removing an explainer
make key-fold         # regenerate the JS case-folding table (assets/profiler-engine.js KEY_FOLD) after a Unicode upgrade
make key-fold-check   # verify the JS case-folding table (KEY_FOLD) against Python for every code point both runtimes assign, and report what it could not compare (needs node; `make check` runs it)
make favicons          # regenerate favicon.ico, apple-touch-icon.png, icon-{192,512}.png after editing logo.svg
make external-links    # report dead external links (a report, never a gate); a link that is correct but cannot pass an anonymous check goes in scripts/external-links-ignore.txt as `URL reason`, and the report still counts it; a link that moved permanently (301 or 308) is listed with its new address
python3 scripts/check_external_links.py --fix-moved  # rewrite permanently moved links to their new address in the files that cite them (then `make build-explainers` if an explainer changed)
make traction-live     # compare the traction figures with GitHub (needs gh; the same check runs weekly)
make contributors-commits  # compare CONTRIBUTORS.md PR and commit counts with GitHub at the snapshot (needs gh, about a minute)
make contributors-pending  # list who merged after the CONTRIBUTORS.md snapshot (needs gh)
make metrics-row         # print the next weekly METRICS.md row from GitHub's live figures (needs gh; the social, countries and audits cells are carried over)
make doctor              # warn when a package in site-packages shadows a standard library module (an old pathlib.py backport once broke the CLI tests with an ImportError on collections)
make lint              # em-dash-free check + broken internal doc link check + issue-number check + explainer counts + traction figures + dataset source links + CONTRIBUTORS.md vs merged PRs + ruff
```

Prerequisites for the full `make check`: Python 3.10 or newer, Node 18 or newer (`key-fold-check` and the JavaScript parity tests run the browser engines under `node`), and the GitHub CLI `gh` signed in (`scripts/check_issue_refs.py` asks GitHub whether an issue or PR number cited in the docs exists; it is skipped offline, and the lint workflow runs it as informational only).

### Checks you may meet

| If this fails | What it means | How to fix it |
|---|---|---|
| `check_em_dash.py` | A tracked file contains an em dash | Replace it with a hyphen, comma or colon |
| `check_broken_links.py` | A relative link in the docs points at a missing file or heading | Fix the path or heading |
| `check_issue_refs.py` | A `#NNN` in ROADMAP, CHANGELOG, CONTRIBUTORS or METRICS is not a real issue or PR | Correct the number |
| `check_explainer_count.py` | An "N explainers" figure, or an explainer listing in the README or `llms.txt`, is stale | `make fix-explainer-count` (a missing listing has to be added by hand) |
| `check_explainer_structure.py` | An explainer is missing a required section (definition, why it matters, concrete example, detection code, limitations, related concepts, further reading), has no `python` block, has fewer than two Further Reading entries, or lacks the footer line | Add the section (the check accepts the usual heading variants, e.g. "Why This Matters"); pages with a known gap are listed in `KNOWN_EXCEPTIONS` in the script, and an exception is removed when its page is fixed |
| `check_traction.py` | Stars, forks, contributors, watching, social reach, countries or audits differ between README, ROADMAP and METRICS, or the README's "Show N completed items" differs from its `- [x]` lines | Edit the figure in the file(s) the message names so they agree; the README's "External Contributors" is one below the total; `--live` (opt-in, needs `gh`, run weekly by `traction-live.yml`) also compares stars, forks, watching, contributors and Issues Closed for the latest METRICS ISO week with GitHub |
| `check_dataset_sources.py` | A URL in a comment of an audit's `unfair.py` or `fair.py` is not on that audit's `**Dataset:**` line in the README | Change the link in both places so they match (a script with no link is fine) |
| `check_contributors.py` | An entry in CONTRIBUTORS.md has a merged-PR count or first-merged date that differs from `gh pr list --state merged` (counted only up to the PR the snapshot line names), an entry is out of order (PRs, then commits, then first merge), a merged-PR author has no entry, or an entry is in no row of the Contributions by area table | Run `python3 scripts/check_contributors.py --fix` to refresh known counts/dates and restore order (profile prose is never changed); add `--commits` (needs `gh`) to also refresh commit counts and move the snapshot line to the newest merged PR. For a new person run `--stub LOGIN` first (add `--commits` to take their commit count from GitHub instead of a PR-count placeholder): it moves the snapshot, adds an entry with their merged PRs and a TODO sentence, lists them in an area row and sorts; replace the TODO by hand and run `--fix --commits`. `--identities` (needs the full git history, not a shallow clone) checks that every commit author and `Co-authored-by` trailer maps to an entry or a Git identity map row; it is run by hand because the file lags new commits by design. Use `--prs FILE` to supply saved JSON from `gh pr list --state merged --limit 5000 --json number,author,mergedAt,title`; without GitHub data the fixer refuses to write. `--commits` (needs `gh`, about a minute) also compares each commit count with the contributors graph at the snapshot (live count minus commits made since) |
| `key-fold-check` | The JavaScript case-folding table `KEY_FOLD` no longer matches Python | `make key-fold`, then commit `assets/profiler-engine.js` |
| A test that runs a README command | Every `faircode ...` line in the README, CONTRIBUTING and SPEC code blocks is checked against the CLI's argument parser; one of them uses a flag or value that no longer exists | Fix the example or the CLI |
| `check_generated_files_current.py` (CI) | Generated explainer pages, sitemap, OG images or `llms-full.txt` are out of date | `make build-explainers`, then commit the result |

**Contributor check exceptions.** `scripts/contributors-exceptions.json` has two sections for people the checks cannot cover (a data file, so no code change is needed), and each entry needs a reason, which the script refuses to load without (`--exceptions FILE` reads another file):

- `commit_exceptions` (keyed by lower-case GitHub handle): a contributor with merged pull requests whose commits no GitHub API counts, because the commit email is not linked to the account (for example a local hostname or a placeholder address). `--commits` reports them as excused instead of failing. Add one only after checking that both `gh api repos/yakew7/Fair-Code/contributors` and `commits?author=LOGIN` return nothing for the login, and explain the unlinked email in the person's row of the Git identity map.
- `unlisted_authors` (keyed by lower-case git author name or co-author name): a commit author who deliberately has no entry, such as a commit that cites a pull request that does not exist. `--identities` skips them. Give the commit and what was decided.

Everyone else is expected to have an entry and a Git identity map row (their git author names in backticks), so a new contributor is added to the file, not to these lists.

The tests run in any pytest import mode, including `--import-mode=importlib`: `pyproject.toml` puts the repo root and `tests/` on `pythonpath`. The helpers shared by the JavaScript parity tests (`tests/test_js_parity_*.py`) live in `tests/js_helpers.py`.

Optionally install the git hooks so the checks run automatically:

```bash
pre-commit install
```
With the hooks installed, the em-dash lint runs on every commit (and explainer pages rebuild when you touch `explainers/*.md`, `assets/explainers-data.json`, or `assets/explainers-ui.js`), the same checks `make lint` runs run on the files they read (issue references, traction figures, dataset source links and CONTRIBUTORS.md when you touch ROADMAP/CHANGELOG/METRICS/README/CONTRIBUTORS or an audit script; the two that need `gh` skip themselves without it), while the full test suite runs on `git push` - but only when the push actually touches something the suite covers (`faircode/`, `scripts/`, `tests/`, a dataset CSV, an audit's `fair.py`/`unfair.py`/`audit.yaml`, `pyproject.toml`, `requirements*.txt`, `assets/profiler-engine.js`, `assets/profiler-compare.js`, `assets/profiler-ui.js`, or `.github/CODEOWNERS`). A prose-only push (docs, `README.md`, `explainers/*.md`, website copy) skips it entirely. When it does run, expect several seconds to tens of seconds because it includes the benchmark tests. Run `make check` any time to reproduce CI on demand regardless of what changed.

---

## 1. Before you start

- Read the relevant section in this guide before writing code.
- Claim the work in an issue before you begin.
- Keep the scope focused: one audit or one explainer per PR.
- Do not start on a duplicate topic if someone else is already working on it.

Example issue text:

> Taking on HMDA mortgage lending bias - starting with the federal HMDA dataset.

or

> Writing an explainer on predictive parity.

---

## 2. Audit contributions

An audit proves bias exists, shows where it comes from, and demonstrates a mitigation.

### Folder layout

Each audit lives in its own top-level folder named after the domain, not the dataset.

```text
Fair-Code/
├── Your-Domain-Here/
│   ├── unfair.py
│   ├── fair.py
│   ├── your-dataset.csv
│   ├── unfair.png
│   ├── fair.png
│   └── README.md
└── notebooks/
    └── 06_your_domain_bias_audit.ipynb
```

Rules:

- Keep the audit folder flat.
- Do not add extra subfolders.
- Use the existing naming style for the folder and files.
- Add a notebook only if you can make it useful and complete.
- Add a `README.md` with the reproducibility checklist (pinned seed, exact commands, and expected before/after numbers) - copy the format from any existing audit folder.

### The two required scripts

Every audit must include exactly two scripts.

#### `unfair.py`

This is the biased baseline. It must:

- load the dataset
- train a Random Forest Classifier
- include protected attributes in the model
- use `random_state=42`
- use an 80/20 train/test split
- report the fairness gap with `significance_report` from `faircode.significance`
  (`from faircode.significance import significance_report`), passing the two groups'
  raw per-row predictions - do not reimplement the statistics
- if the audit tracks 2+ protected attributes, also report at least one intersectional
  (combined) pair with `intersectional_report` from `faircode.significance`, following the
  pattern in `Insurance Denial/unfair.py`, `Benefits Denial/unfair.py`, or
  `Healthcare Readmission/unfair.py` - single-attribute audits skip this
- print results in this format:

```text
--- BIASED MODEL RESULTS ---

[Group A] [Outcome] Rate: XX.XX%
[Group B] [Outcome] Rate: XX.XX%

Fairness Gap: XX.XX%
95% CI: [XX.XX%, XX.XX%] (bootstrap, n=10,000 resamples)
Permutation test p-value: X.XXXX (statistically significant at α=0.05)
```

#### `fair.py`

This is the mitigated version. It must:

- drop the protected attribute(s)
- drop any proxy variables you identified
- retrain on the remaining features
- report the fairness gap with `significance_report` from `faircode.significance`,
  the same way `unfair.py` does
- print results in this format:

```text
--- MITIGATED (UNBIASED) RESULTS ---

[Group A] [Outcome] Rate: XX.XX%
[Group B] [Outcome] Rate: XX.XX%

New Fairness Gap: XX.XX%
95% CI: [XX.XX%, XX.XX%] (bootstrap, n=10,000 resamples)
Permutation test p-value: X.XXXX (not statistically significant at α=0.05)
```

### Notebook expectations

Notebooks are optional, but strongly encouraged.

Use the next sequential filename:

```text
notebooks/06_your_domain_bias_audit.ipynb
```

Recommended structure:

| # | Section | What it should do |
|:-:|---------|-------------------|
| 1 | Title | Audit number, domain, and a one-line hook |
| 2 | Setup | Imports and the shared plot styling |
| 3 | Load and explore | Load the CSV, inspect shape/columns, and show the raw disparity |
| 4 | Proxy analysis | Use chi-squared for categorical features or Pearson correlation for continuous ones |
| 5 | Train biased model | Match `unfair.py` exactly |
| 6 | Train fair model | Match `fair.py` exactly |
| 7 | Compare results | Before/after bar charts and reduction summary |
| 8 | Key insight | One short markdown paragraph in plain language |

The proxy analysis section is required. Do not skip it.

---

## 3. Proxy variables

Removing the protected attribute alone is rarely enough.

A proxy variable is a feature that carries the same signal as the protected attribute, even after the protected column is removed.

| Audit | Protected attribute | Proxy variable(s) | Why it matters |
|-------|---------------------|-------------------|----------------|
| COMPAS | Race | `CustodyStatus` | Historical over-policing can leak race back into the model |
| German Credit Lending | Age | `employment` (tenure) | Young applicants cannot have long work histories |
| Insurance Denial | Race, class | `bmi`, `smoker`, `diabetic` | Structural disparities show up in health-related features |
| Benefits Denial | Sex | `relationship`, `marital.status`, `hours.per.week` | Family roles and caregiving patterns encode sex |
| Benefits Denial | Race | `occupation` | Occupational segregation can reconstruct race |
| Healthcare Readmission | Race, income | `payer_code`, `discharge_disposition_id`, `number_inpatient` | Insurance type encodes race; discharge destination and prior hospitalisation count encode access gaps, not clinical severity |

How to check likely proxies:

```python
import pandas as pd

df = pd.read_csv("your-dataset.csv")

# Continuous features
print(df[["potential_proxy", "protected_attribute"]].corr())

# Categorical features
print(pd.crosstab(df["potential_proxy"], df["protected_attribute"], normalize="columns").round(3))
```

If you keep a feature that correlates strongly with a protected attribute, explain why it is a legitimate signal and not a proxy.

---

## 4. Screenshots

After running both scripts, save terminal screenshots as PNG files:

| File | Content |
|------|---------|
| `unfair.png` | Output from `unfair.py` |
| `fair.png` | Output from `fair.py` |

Requirements:

- PNG only
- place both files in the audit folder
- make sure the output is readable

---

## 5. Dataset requirements

Datasets must be:

- public
- real
- easy to access

Good sources include Kaggle, government data, ProPublica, and academic releases.

If the dataset is under about 50 MB, commit it with the audit. If it is larger, add a `DATA.md` file with a direct download link and setup steps.

---

## 6. Update the README

Add your audit to the results table in `README.md`:

```markdown
| 06 | [Your Domain](#link-to-section) | Protected Attribute | Proxies Removed | Gap Before -> After | Reduction |
```

Then add a full project section using the same pattern as the existing audits:

1. Opening quote
2. Dataset description and context
3. The problem section with biased results
4. Code showing what you removed and why
5. The fix section with mitigated results
6. A short key insight paragraph
7. Notebook link, if applicable

The key insight paragraph is required. Keep it short, concrete, and jargon-free.

---

## 7. Fairness metric

All audits use **Demographic Parity** by default: the difference in positive prediction rates between groups.

If your domain truly needs another metric, open an issue first and explain why. See [Equalized Odds](explainers/equalized-odds.md) for a good example of when a different metric is appropriate.

---

## 8. Explainer contributions

Explainers live in `explainers/` and should make one fairness concept easy to understand.

### Existing explainers

A short sample, not a full list. README.md and llms.txt list every explainer, and `scripts/check_explainer_count.py` fails if either leaves one out.

| File | Concept |
|------|---------|
| `proxy-variables.md` | Why AI stays biased after protected attributes are removed |
| `equalized-odds.md` | Error-rate parity across groups |
| `sampling-bias.md` | Why training data can misrepresent the real world |
| `shap-values.md` | How to explain a model decision and catch bias |
| `disparate-impact.md` | The 80% rule in hiring, lending, and insurance |
| `disparate-treatment.md` | Intentional discrimination via direct inputs or proxies |
| `fairness-metric-conflicts.md` | Why major fairness metrics cannot all be satisfied at once |
| `calibration.md` | Why equal accuracy does not guarantee equal treatment |
| `demographic-parity.md` | Equal positive prediction rates across groups |
| `feedback-loop-bias.md` | How retraining can amplify bias |
| `label-bias.md` | How historical labels inherit human prejudice |
| `individual-fairness.md` | Treating similar people similarly |
| `counterfactual-fairness.md` | Decisions that stay stable under demographic changes |
| `neural-networks.md` | How networks learn bias from data |
| `ai-hallucinations.md` | Why confident predictions can still be wrong |
| `reinforcement-learning.md` | How RL agents learn from reward signals - and why that makes bias hard to see and harder to fix |
| `proxy-entanglement.md` | Why removing proxies one at a time fails when multiple features encode the same protected signal through correlated, redundant channels |
| `ml-bias.md` | The four entry points - training data, labels, proxies, and feedback loops - that let bias enter a model, with detection code and real examples |
| `data-leakage.md` | Why a model that scores 99% on every internal test can still fail at deployment - target leakage, train-test contamination, and detection code |
| `how-ai-detects-patterns.md` | How a Random Forest detects patterns through splits, aggregation, and feature importance, and why it can't distinguish causal patterns from discriminatory ones |
| `distribution-shift.md` | Why a model that passes a fairness audit can become biased again as the population it serves changes |
| `ai-objectivity-myth.md` | Why "it's just math" isn't a defense - models trained on biased history reproduce that bias |
| `confounding-variable.md` | How a hidden third variable creates spurious correlations that persist after protected-attribute removal - and how to detect and adjust for it |
| `predictive-parity.md` | Why an equally trustworthy positive prediction across groups can still hide an unequal false-positive burden |
| `false-positives-vs-false-negatives.md` | Why the direction of a model's error matters in medicine, and why false negatives cluster in historically undertreated groups |
| `supervised-learning.md` | How a model turns labeled examples into a decision rule, and why it reproduces whatever pattern - fair or not - sits in the labels it's trained on |
| `unsupervised-learning.md` | How k-means clustering recovers a demographic split with no label and no protected attribute in the feature set, purely from correlated proxy features |
| `model-drift.md` | Why a fairness gap measured once at launch can drift after deployment, and how rolling-window monitoring (PSI, Page-Hinkley) catches what a single audit snapshot misses |
| `selection-bias.md` | Why the process that decides whether someone enters a dataset at all can bias a model before any protected attribute or proxy variable is even considered, with a Berkson's-paradox simulation and the German Credit Lending reject-inference gap as proof |
| `automation-bias.md` | Why judges, recruiters, and clinicians defer to AI scores even when biased - and how automation bias amplifies disparities beyond the model alone, with detection code for disparity amplification in human-in-the-loop decisions |
| `roc-curve-auc.md` | Why a single threshold-free AUC can look strong while hiding where the decision threshold sits and whether ranking quality is equal across groups, with per-group AUC / overlaid-ROC detection code |
| `protected-attribute.md` | What a protected attribute is, which ones the law recognizes, and why removing them outright just hides the bias behind proxies |
| `confusion-matrix.md` | The TP/FP/FN/TN building block behind most fairness metrics, and everything (precision, recall, FPR, FNR) derived from it |
| `class-imbalance.md` | Why skewed positive/negative ratios wreck naive accuracy and hit minority subgroups hardest, and when resampling helps or hurts fairness |
| `bias-variance-tradeoff.md` | The classic underfit/overfit trade-off, and why statistical "bias" here is not the societal bias the rest of these explainers mean |
| `accuracy-not-enough-healthcare-ai.md` | Why a 95%-accurate model can still miss the sickest patients in one group - the accuracy paradox on rare clinical outcomes, per-group recall gaps, and why a missed case and a false alarm are never equally costly |
| `clinical-score-miscalibration.md` | Why a clinical risk score well-calibrated on average can still mean a different real-world risk depending on the patient's group, with per-group reliability and calibration-slope detection code |
| `missing-data-bias-ehr.md` | Why unequal access to care turns into unequal missingness in EHR data, and why naive imputation encodes the disparity rather than fixing it |
| `medical-imaging-representation-gaps.md` | Why dermatology, radiology, and retinal imaging models underperform on groups thin in the training data, and the shortcut-learning failure mode where a model keys off scanner or hospital-site artifacts instead of the pathology |
| `base-rate-fallacy.md` | Why ignoring background prevalence makes screening tools mostly wrong, and why differing base rates across demographic groups drive fairness metric conflicts |
| `obermeyer-cost-proxy.md` | Why predicting healthcare spending instead of illness systematically under-refers sicker Black patients - target proxy bias, spending disparities, and care re-allocation |
| `race-correction-clinical-algorithms.md` | Why race-adjusted clinical formulas (eGFR, spirometry, VBAC) bake bias into the math and delay care for minority patients |
| `reject-inference.md` | Why models trained only on approved applicants miss the risk of everyone else - sample selection bias, missing ground-truth outcomes, and IPW/parceling corrections |
| `underdiagnosis-bias.md` | Why historical gaps in diagnostic testing cause ground-truth labels to under-count active disease in underserved groups - training models to systematically under-flag those exact patients |
| `precision-recall-curve.md` | Why ROC/AUC looks fine while precision collapses under the class imbalance most fairness audits actually live in, with per-group average-precision detection code |
| `equal-opportunity.md` | Why passing the true-positive-rate check (Equal Opportunity) doesn't mean passing the false-positive-rate one (Equalized Odds), with two real frozen results showing them coincide and diverge |
| `intersectional-bias.md` | Why checking one protected attribute at a time can hide a compounding gap at the intersection, with a real superadditive result and crosstab detection code |
| `accuracy-equality.md` | Why equal accuracy across groups can hide two completely different, offsetting error profiles |
| `bootstrap-confidence-intervals.md` | Why a fairness gap without a confidence interval attached is a number, not a finding, and how bootstrap CIs and permutation tests tell the two apart |
| `counterfactual-explanation.md` | What changed the outcome for one prediction, and how that differs from counterfactual fairness's "should the outcome have changed at all" |
| `fairness-through-unawareness.md` | Why removing the protected attribute doesn't remove what correlates with it |
| `lime.md` | A local, approximate surrogate model - the other major way to explain one prediction, alongside SHAP |
| `mitigation-strategies.md` | Where in the pipeline you intervene - pre-, in-, or post-processing - changes what a fairness fix can and can't do |
| `multiple-comparisons.md` | Why running dozens of p-values per audit inflates the odds of a false "significant," and how Bonferroni, Holm, and Benjamini-Hochberg FDR each answer that differently on a real 90-p-value COMPAS slice |
| `fairness-accuracy-tradeoff.md` | Why closing a fairness gap often costs predictive accuracy, and why the two aren't always improved together, with a real S0-S4 fairness-vs-accuracy table from the COMPAS audit |
| `treatment-equality.md` | Why two groups with matching TPR/FPR gaps can still have opposite-skewed error types underneath, with a real 0.13-vs-31.0 FN:FP ratio split from the COMPAS audit |
| `conditional-demographic-parity.md` | Why holding a "legitimate" factor fixed before comparing group outcome rates can launder bias instead of removing it, depending on what factor you pick |
| `differential-privacy.md` | Why the accuracy cost of privacy-preserving training noise falls hardest on the underrepresented groups a fairness audit is trying to protect |
| `reject-option-classification.md` | A post-processing mitigation that hands the favorable outcome to the disadvantaged group only in the model's least-confident cases |
| `simpsons-paradox.md` | Why a model can look fair pooled across groups while every disaggregated subgroup shows the opposite pattern |
| `subgroup-fairness.md` | Why passing every single-attribute fairness check doesn't rule out a large gap hiding in an unchecked combination of attributes |
| `algorithmic-recourse.md` | What an applicant can realistically change to flip a model's decision, and why recourse can cost one group more than another |
| `maxmin-fairness.md` | Judging a model by its worst-off group instead of by parity, and why the two can disagree |
| `distributionally-robust-optimization.md` | Training against the worst-case group instead of constraining one parity metric, and what it costs the other groups |
| `fairness-in-ranking.md` | Why classification metrics cannot see the harm of an ordered list, and how exposure measures it |
| `reweighing.md` | A pre-processing mitigation that weights each (group, label) cell as if group and label were independent |
| `group-specific-thresholds.md` | A post-processing mitigation that keeps the model and moves the score cutoff per group |
| `permutation-test-fairness-gaps.md` | Shuffling group labels to tell a real gap from sampling noise, and why the same gap can be significant or not by sample size |
| `adversarial-debiasing.md` | Training a predictor against an adversary that tries to read the protected attribute from its output |
| `fairness-regularization.md` | Putting a price on the parity gap in the training loss, and why the soft gap is not the gap on decisions |
| `fair-representation-learning.md` | Removing the directions that predict the group, and why a representation clean to a linear reader can leak to a forest |
| `measurement-bias.md` | When a feature or label is recorded worse for one group, creating a gap the true values do not have |
| `aggregation-bias.md` | Why one pooled model can fit every group worse than a model fitted to that group alone |
| `survivorship-bias.md` | How training only on the people who passed an earlier filter shifts base rates and shrinks the gating feature's effect |
| `disaggregated-evaluation.md` | Reporting every metric per group and intersection with an interval, and how fast intervals widen as groups shrink |
| `leave-one-group-out-evaluation.md` | Holding out one group at a time to test generalization to people the training data left out |
| `choosing-a-fairness-metric.md` | A decision path from the harm you worry about to the metric that measures it |
| `model-cards.md` | A short standard disclosure of what a model is for, how it performs for each group, and where it should not be used |
| `datasheets-for-datasets.md` | The questions about where data came from, answered in writing so an unknown is visible as an unknown |
| `algorithmic-impact-assessment.md` | A structured review of who a decision system affects, with the fairness audit as its measurement section |
| `inferring-protected-attributes.md` | Estimating group membership from other fields and what that does to a measured gap |
| `fairness-without-demographics.md` | Improving the worst-off groups with no group labels by upweighting the rows the model gets wrong |
| `adverse-action-notices.md` | How reason codes on a credit decline are derived from a model, and how they can expose a proxy: personal_status shows up 15 points more for under-30s. |
| `geographic-proxies-and-redlining.md` | How a location feature can reveal race, and why proxy strength and effect on the parity gap are separate measurements, shown on Tenant Screening. |
| `risk-based-pricing-gaps.md` | How to measure a group gap in a quoted amount or price when everyone is approved, with a bootstrap interval, shown on German Credit Lending. |
| `race-in-clinical-models.md` | Comparing a hospital readmission model with and without race on accuracy, calibration and who gets a limited place: the effect is small either way. |
| `utilization-as-a-label.md` | How to test whether a utilization label records access, by comparing groups at the same illness burden, shown on Healthcare Readmission. |
| `discharge-leakage-in-readmission-models.md` | How discharge disposition can leak the outcome in a readmission model, and what end-of-life rows do to the base rate, shown on 99,492 patients. |
| `seed-and-split-sensitivity.md` | How much a fairness gap changes with the random split seed: on 1,000 German Credit rows the spread is as large as the effect; on 32,561 rows it is tiny. |
| `cross-validation-for-fairness.md` | Cross-validating a fairness gap with folds stratified by group and label, so every row is tested once and no fold lacks the small cells. |
| `stratified-test-sets-for-fairness.md` | Oversampling a small group in an evaluation set to narrow its interval, and weighting rows back to the population for an overall number. |
| `feature-importance-by-group.md` | Running permutation importance per group to see whether a model relies on different features for different people, shown on Benefits Denial. |
| `partial-dependence-by-group.md` | Partial dependence drawn per group, with method brute so each curve averages over its own rows, and the row counts behind each point. |
| `explanation-disagreement.md` | Comparing permutation importance, SHAP and logistic coefficients on one model, and why a fairness claim should say which method it rests on. |
| `hiring-pipeline-adverse-impact.md` | Computing the four-fifths ratio with intervals at each hiring stage and for the whole funnel, shown on AI Fair Recruitment where the gap enters at the decision. |
| `compounding-disparities.md` | Why stage ratios multiply: four stages at 0.90 each pass the four-fifths check and give 0.666 end to end, shown in a simulation with correlated stages too. |
| `differential-validity.md` | Equal validity does not mean equal prediction: on AI Fair Recruitment each score has the same AUC for women and men, but women are hired less at the same score. |
| `minimum-detectable-gap.md` | How large a fairness gap must be for an audit to detect it at 80% power, checked with the permutation test and applied to the benchmark's groups. |
| `small-group-shrinkage.md` | Empirical-Bayes shrinkage cuts the error of small-group rates by two thirds on Healthcare Readmission, and can hide a real gap in the smallest cell. |
| `confidence-intervals-for-ratios.md` | Intervals for a disparate impact ratio by percentile bootstrap and the log-ratio delta method, and why a near-zero denominator has no honest interval. |
| `monitoring-fairness-in-production.md` | Control-charting a fairness gap after deployment: how batch size and window change detection delay and false alarms, simulated on Benefits Denial. |
| `label-shift-and-fairness.md` | Which fairness metrics change under label shift: TPR and FPR gaps stay fixed while parity and precision gaps swing, shown on Benefits Denial. |
| `delayed-feedback.md` | How late outcomes bias a monitored group gap, and counting only mature cases as the fix, simulated on 99,492 hospital discharges. |
| `causal-graphs-for-fairness.md` | How the assumed causal graph decides which variables to adjust for: the same sex gap is -0.196, -0.157 or -0.034 depending on the adjustment set. |
| `path-specific-effects.md` | Splitting the sex gap in income into direct and mediated paths with bootstrap intervals, and what must be assumed for the split to mean anything. |
| `randomized-post-processing.md` | The linear programme for randomized equalized-odds post-processing on Tenant Screening: gap 0.149 down to under 0.02, with random decisions in a few rows. |
| `fairness-accuracy-pareto-frontier.md` | A sweep of 1,681 threshold pairs on Tenant Screening gives a nearly flat frontier, and shows where the benchmark's five strategies sit against it. |
| `choosing-a-mitigation-strategy.md` | Choosing among the five mitigation strategies from the benchmark's results: what each needs, the median accuracy cost and the gap left, over 13 pairs. |
| `auc-gaps-by-group.md` | Per-group AUC and its gap with bootstrap and DeLong intervals: when equal AUC hides unequal errors, and when a threshold hides a real ranking gap. |
| `decision-curve-analysis-by-group.md` | Net benefit by group against treating everyone or no one: how to read a decision curve per group and see where a model helps one group and not another. |
| `cost-sensitive-evaluation.md` | Per-group expected cost under unequal false positive and false negative costs, the cost-optimal threshold, and how it relates to group-specific thresholds. |
| `popularity-bias.md` | A simulated popularity feedback loop on a real audit: the shown set freezes, merit stops ordering exposure, and a group imbalance is locked in. |
| `two-sided-fairness.md` | Exposure for the ranked side and nDCG for the searcher on one re-ranking sweep, and where fairness to one side starts to cost the other. |
| `position-bias-and-click-models.md` | Simulated clicks from a known relevance: why a ranker trained on raw clicks learns position, how inverse propensity weighting fixes it, and its limits. |

### A good explainer should include

| # | Section | What to include |
|:-:|---------|-----------------|
| 1 | Definition | Plain-language definition, no jargon |
| 2 | Why it matters | One short paragraph on the real-world impact |
| 3 | Concrete example | A real case from this repo or a documented real-world example |
| 4 | Detection code | Runnable Python using `pandas` and `scikit-learn` where possible |
| 5 | Limitations | Honest trade-offs and edge cases |
| 6 | Related concepts | Links to other explainers or audits |
| 7 | Further reading | 2-3 primary sources, not link farms |

The `assets/explainers-data.json` entry has `slug`, `title`, `subtitle`, `summary` and `tags`, and two optional fields the build checks: `description` (the meta description, 70 to 160 characters; when it is missing the summary is cut at the last sentence that fits, and a summary that cannot be shortened sensibly fails the build) and `seo_title` (a shorter page title when `title` plus the site name would pass 65 characters, so at most 53).

If the page tells the reader to run its code, say so with the path `explainers/code/<slug>.py` in the sentence just before the python block (for example: Run from the repo root (`PYTHONPATH=. python3 explainers/code/<slug>.py`; that file is generated from the block below).). `make build-explainers` writes that file from the block, removes stale ones, and the generated-files check fails if it is out of date, so never edit it by hand.

Explainers with code should run against a real audit. To opt a Python fence into the smoke test, put `# runnable` on the first nonblank line inside the fence. The test executes each marked block in a subprocess from the repository root, reports the explainer and block number on failure, and applies a timeout. Add `# slow` on the next line for examples that need the longer timeout and should be skipped by `make test-fast`; the full CI test suite still runs them. Keep setup self-contained and avoid network access.

 `faircode.benchmark.load_audit("Benefits Denial")` loads an audit with the same loader, encoding and train/test split as the benchmark harness, so a baseline in your explainer matches `results/`.

File naming:

```text
explainers/your-concept-name.md
```

Use lowercase and hyphens only.

When you add an explainer, update the Explainers table in `README.md`:

```markdown
| [Your Concept](explainers/your-concept-name.md) | One-line description |
```

---

## 9. Style guidelines

One rule that applies to every file in this repo:

**No em dashes.** Use a hyphen with spaces ( ` - ` ) instead.

| Wrong | Correct |
| ----- | ------- |
| `The model — trained on biased data — fails.` | `The model - trained on biased data - fails.` |
| `## Phase 1 — Bias Glossary` | `## Phase 1 - Bias Glossary` |
| `# Dropped race — a proxy for bias` | `# Dropped race - a proxy for bias` |

This applies to markdown files, Python comments, JavaScript comments, and everything else in the repo. The issue templates have a required checkbox to confirm this before your PR is opened.

---

## 10. CI and branch rules

Every push and pull request runs the audit scripts in `.github/workflows/audits.yml`.

What this means:

- scripts must run from the repository root
- dataset paths must be resolved relative to the script file, not the current working directory
- failing CI blocks merge

Recommended pattern:

```python
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(BASE_DIR, "your-dataset.csv"))
```

Branch rules on `main`:

- PRs are required
- CI must pass
- force pushes are blocked
- the branch cannot be deleted

If CI fails, push a new commit to your branch and let the check rerun.

### Dependency updates

`.github/dependabot.yml` opens at most five pip and five GitHub Actions PRs a week, grouped like this:

- **Minor and patch bumps of tooling, notebook and transitive packages** arrive as one weekly pip PR (and one for Actions). Review it like any other PR: CI passing is the bar.
- **`numpy`, `pandas`, `scikit-learn`, `scipy`, `fairlearn` and `matplotlib`** are not grouped, so each bump is its own PR. They compute the numbers in `results/` (models, splits, metrics, intervals), so a bump can change a result without touching a line of code.
- **Major bumps** are never grouped; read the changelog before merging.

Before merging a bump of one of those six libraries, rerun the benchmark on the new versions and compare it with the committed results:

```bash
python3 -m pip install -r requirements-lock.txt   # on the PR branch
faircode benchmark --out /tmp/bump-results
python3 scripts/diff_results.py --current /tmp/bump-results --reference results --threshold 0.001
```

If rows moved, say so in the PR and refresh `results/` in the same PR or an immediate follow-up; if nothing moved, say that. Do not touch `paper/results-frozen/`. The rerun is slow, so it is not an automatic check. Add the `rerun-benchmark` label to the PR (or run the *Benchmark diff* workflow from the Actions tab with the PR number) and `.github/workflows/benchmark-diff.yml` reruns the full benchmark on that PR's lockfile and comments the diff, with no commit and no change to `paper/results-frozen/`.

Observed on a throwaway pull request (#1142, 2026-10-24): the `refs/pull/N/merge` checkout and the locked install worked, the full benchmark took about 34 minutes on a hosted `ubuntu-latest` runner (the job limit is 120), and the comment was posted. The runner uses Python 3.12 and the reference results were made on 3.13, so the comment lists the library versions that differ; a row that moved with only a Python change is not a library effect. The moved-rows section lists at most 100 rows per kind and is cut at 50,000 characters, well under GitHub's 65,536 limit. A change to the workflow or to `scripts/diff_results.py` also runs a smoke job on one small audit before it can merge.

---

## 11. How to submit

### Audit PRs

1. Fork the repo.
2. Create a branch: `git checkout -b audit/your-domain`.
3. Add the folder, scripts, dataset, and screenshots.
4. Add a notebook if you wrote one.
5. Update `README.md`.
6. Open a PR titled like: `Audit: HMDA Mortgage Lending Bias`.
7. Confirm the `run-audits` check passes.

Include in the PR description:

- dataset source
- bias type
- before/after fairness gap numbers
- proxy variables found and why you dropped them
- whether you included a notebook

### Explainer PRs

1. Fork the repo.
2. Create a branch: `git checkout -b explainer/your-concept`.
3. Add your markdown file to `explainers/`.
4. Update the Explainers table in `README.md`.
5. Open a PR titled like: `Explainer: Predictive Parity`.
6. Confirm the `run-audits` check passes.

Include in the PR description:

- the concept you are explaining
- why it belongs in this repo

---

## 12. What will not be merged

### Audits

- synthetic or toy datasets
- missing `random_state=42`
- inconsistent train/test splitting
- fair models that only work by collapsing accuracy
- no proxy analysis
- `.jpg` or `.jpeg` screenshots
- datasets that require login or payment

### Notebooks

- proxy analysis skipped
- inconsistent styling or color palette
- numbering that does not follow the existing sequence

### Explainers

- concept defined but not demonstrated
- no limitations or trade-offs
- toy examples as the main evidence
- topics already covered in the repo

---

All datasets used in this project are publicly available. Fair Code is for educational and awareness purposes.
 
