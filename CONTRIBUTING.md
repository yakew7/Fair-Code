# Contributing to Fair Code

<div align="center">

**Bias audits. Clear explainers. Reproducible results.**

[Issue templates](.github/ISSUE_TEMPLATE/) are the preferred way to claim work before you start.

</div>

> **Before opening a PR, read [CLAUDE.md](CLAUDE.md)** — the repo is under a paper freeze and some changes are on hold until publication.

Thanks for contributing. Fair Code accepts two kinds of additions:

- **Audits** - a real dataset, a biased model, a fair model, proxy analysis, and before/after results
- **Explainers** - a clear explanation of a fairness concept, with examples and runnable code

Consistency matters here. It is what makes the repo credible and easy to review.

---

## Contributing during the paper freeze

Fair Code's benchmark results are cited in a research paper currently in peer review, so the repo is under a **paper freeze**. This changes *what* you can contribute right now, not *whether* you can — most of the project is still wide open.

**✅ Open now — merges as usual:**

- **Explainers** — new `.md` files in `explainers/`
- **Website content** and `assets/*.json` entries
- **Documentation** — README prose, this guide, `CHANGELOG.md`
- **Typo and clarity fixes** in prose
- **Social media caption files**

**⏸️ On hold until the paper is published:**

- **New audits** — the paper covers exactly seven domains, so new audits cannot merge into `main` yet. This is a **timing hold, not a rejection**: open a PR anyway (it will be parked on a branch or labeled `post-paper`) and it merges once the freeze lifts.
- **Any change to the frozen results** or the reproducibility parameters (`random_state`, split, iteration counts, the fairness constraint or metrics). If you think you found a bug in the analysis code, **flag it in an issue — do not silently fix it.**
- **`requirements-lock.txt`** — this is a fixed `pip freeze` snapshot, not a normal dependency file. Dependabot doesn't know that and will keep opening version-bump PRs against it; **please close those without merging**, even though they look like routine, safe updates. See [CLAUDE.md](CLAUDE.md) §1.

**One rule for explainers:** if your explainer quotes a Fair Code result, use the frozen numbers in [`paper/results-frozen/`](paper/results-frozen/) — never re-run your own.

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
> enforced by `tests/test_js_parity.py::test_python_js_compare_parity` (via `scripts/engine-js.js compare`).
> HTML report changes need the same treatment on both sides: `faircode/report.py`'s `to_html`/
> `compare_to_html` and their hand-ported equivalents in `assets/profiler-ui.js`/
> `assets/profiler-compare.js`. Update `SPEC.md` first - it is the source of truth.

---

## Local setup and checks

A `Makefile` and a `.pre-commit-config.yaml` reproduce what CI runs, so you can catch failures before you open a PR:

```bash
make setup             # install faircode + pytest + pre-commit
make check             # everything CI runs: em-dash lint + full test suite
make test              # just the test suite
make build-explainers  # regenerate explainer pages, sitemap, and OG images after editing explainers/*.md
make favicons          # regenerate favicon.ico/PNGs + apple-touch-icon.png after editing logo.svg
make lint              # em-dash-free check only
```

Optionally install the git hooks so the checks run automatically:

```bash
pre-commit install
```

With the hooks installed, the em-dash lint runs on every commit (and explainer pages rebuild when you touch `explainers/*.md`), while the full test suite runs on `git push`. Run `make check` any time to reproduce CI on demand.

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
