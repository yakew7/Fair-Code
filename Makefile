# Fair Code - contributor task runner.  See CONTRIBUTING.md.
# Reproduces locally what CI runs (.github/workflows: audits.yml, lint.yml,
# build-explainers.yml) so you can catch failures before you push.

.DEFAULT_GOAL := help
PY := python3

.PHONY: help setup test test-fast test-browser setup-browser coverage key-fold key-fold-check build-explainers favicons fix-explainer-count external-links traction-live contributors-commits contributors-pending metrics-row doctor lint audits check

help:  ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS = ":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

setup:  ## Install the package plus the dev tools (pytest, pytest-cov, pytest-xdist, pre-commit, ruff)
	$(PY) -m pip install -e ".[excel,parquet,proxy,mcp,benchmark]" pytest pytest-cov pytest-xdist pre-commit ruff
	$(MAKE) --no-print-directory doctor || true

test:  ## Run the full test suite (mirrors CI)
	$(PY) -m pytest tests/ -q

# pytest-xdist (installed by `make setup`) runs the tests on every core: 1,464 tests take about 95 s in one process and
# about 35 s with it (#1256). Without it the run is serial, and the ten slowest tests are listed either way.
# Each worker's BLAS is limited to one thread: with all of them multi-threaded the CPU is oversubscribed and the
# CPU-heavy explainer smoke test hit its 30 s timeout once.
XDIST = $(shell $(PY) -c "import importlib.util as u; print('-n auto' if u.find_spec('xdist') else '')" 2>/dev/null)
XDIST_ENV = $(if $(XDIST),OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1,)

test-fast:  ## Run the suite without the slow model-training benchmark tests or the Chromium tests (make test-browser), in parallel when pytest-xdist is installed (CI still runs everything)
	$(XDIST_ENV) $(PY) -m pytest tests/ -q -m "not slow" --ignore=tests/browser $(XDIST) --durations=10

setup-browser:  ## Install Playwright and Chromium for the browser smoke test (tests/browser)
	$(PY) -m pip install -e ".[browser]" && $(PY) -m playwright install chromium

test-browser:  ## Open the real pages in Chromium and fail on any console error (run `make setup-browser` once first)
	$(PY) -m pytest tests/browser -q

coverage:  ## Run the full test suite with a faircode/ coverage report (what CI's profiler job runs; the figure is informational, not a gate)
	$(PY) -m pytest tests/ -q --cov=faircode --cov-report=term-missing

key-fold:  ## Regenerate the JS case-folding table (KEY_FOLD) from this machine's Python and node, e.g. after a Unicode upgrade
	$(PY) scripts/generate_key_fold.py

key-fold-check:  ## Verify KEY_FOLD against Python for every code point both runtimes assign (reports what it could not compare)
	$(PY) scripts/generate_key_fold.py --check

build-explainers:  ## Regenerate explainer pages, data.js, sitemap, and OG images (dark + light)
	$(PY) scripts/build_explainers.py
	$(PY) scripts/generate_og_images.py

favicons:  ## Regenerate favicon.ico/PNGs and apple-touch-icon.png from logo.svg
	$(PY) scripts/generate_favicons.py

fix-explainer-count:  ## Correct stale "N explainers" mentions in README/CONTRIBUTORS/METRICS/ROADMAP
	$(PY) scripts/check_explainer_count.py --fix

external-links:  ## Report dead external links in the docs and explainers (a report, never a gate; the weekly workflow runs the same script)
	$(PY) scripts/check_external_links.py

traction-live:  ## Compare the traction figures with GitHub (needs gh; opt-in, the weekly traction-live workflow runs the same check)
	$(PY) scripts/check_traction.py --live

contributors-commits:  ## Compare CONTRIBUTORS.md PR and commit counts with GitHub at the snapshot (needs gh, about a minute)
	$(PY) scripts/check_contributors.py --commits

contributors-pending:  ## List who merged after the CONTRIBUTORS.md snapshot (needs gh; exit 1 if anyone, the weekly contributors-drift workflow runs the same list)
	$(PY) scripts/check_contributors.py --pending

metrics-row:  ## Print the next weekly METRICS.md row from GitHub's live figures (needs gh; prints, never edits; add ARGS=--apply to write the figures too)
	$(PY) scripts/draft_metrics_row.py $(ARGS)

doctor:  ## Warn when an installed package shadows a standard library module (an old pathlib.py backport once broke imports)
	$(PY) scripts/check_environment.py

lint:  ## Enforce the em-dash-free rule + check for broken doc links + issue numbers in docs (needs gh, skipped offline) + explainer counts and listings + explainer structure + traction figures agreeing across README/ROADMAP/METRICS + dataset source links agreeing between the README and the audit scripts + CONTRIBUTORS.md matching the merged PRs (needs gh, skipped offline) + ruff (mirrors the lint workflow)
	$(PY) scripts/check_em_dash.py
	$(PY) scripts/check_broken_links.py
	$(PY) scripts/check_issue_refs.py
	$(PY) scripts/check_explainer_count.py
	$(PY) scripts/check_explainer_structure.py
	$(PY) scripts/check_traction.py
	$(PY) scripts/check_dataset_sources.py
	$(PY) scripts/check_contributors.py
	ruff check faircode scripts tests

audits:  ## Run every audit's unfair.py/fair.py + the CLI smoke tests (mirrors audits.yml's required run-audits job, plus profiler/benchmark-harness's CLI steps)
	@set -e; \
	for d in "COMPAS" "AI Fair Recruitment" "German Credit Lending" "Insurance Denial" \
	         "Benefits Denial" "Healthcare Readmission" "Tenant Screening"; do \
		echo "== $$d - unfair.py =="; \
		$(PY) "$$d/unfair.py"; \
		echo "== $$d - fair.py =="; \
		$(PY) "$$d/fair.py"; \
	done
	@echo "== CLI smoke test: faircode profile =="
	faircode profile "Insurance Denial/insurance.csv"
	faircode profile "Benefits Denial/adult.csv" --json > /dev/null
	@echo "== CLI smoke test: faircode benchmark =="
	@tmp=$$(mktemp -d); \
	faircode benchmark "German Credit Lending/audit.yaml" \
		--n-resamples 100 --n-permutations 100 --no-plots \
		--out "$$tmp"; \
	test -s "$$tmp/results_fairness.csv"; \
	test -s "$$tmp/results_performance.csv"; \
	echo "Benchmark harness smoke test passed: $$(wc -l < "$$tmp/results_fairness.csv") fairness rows written"; \
	rm -rf "$$tmp"

check: doctor lint key-fold-check test audits  ## Run everything CI runs (environment check + lint + full test suite + audits/CLI smoke tests)
	@echo "All checks passed."
