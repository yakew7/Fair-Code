<div align="center">

# Fair Code - Metrics Tracker

![Stars](https://img.shields.io/badge/Stars-46-brightgreen?style=flat-square&logo=github)
![Contributors](https://img.shields.io/badge/Contributors-27-blue?style=flat-square)
![Forks](https://img.shields.io/badge/Forks-31-orange?style=flat-square)
![Watching](https://img.shields.io/badge/Watching-8-yellow?style=flat-square)
![Explainers](https://img.shields.io/badge/Explainers-53-blueviolet?style=flat-square)
![Countries](https://img.shields.io/badge/Countries-20-informational?style=flat-square)
![Updated](https://img.shields.io/badge/Updated-Weekly-lightgrey?style=flat-square)

Weekly snapshot of project health. Updated every Friday.

[How to Update](#how-to-update) · [Weekly Metrics](#weekly-metrics) · [Targets](#targets) · [Notes](#notes)

</div>

---

## How to Update

1. Check GitHub for stars, forks, watchers, and contributor count
2. Check Instagram and LinkedIn for combined impressions/followers
3. Check site analytics for the count of unique countries visiting thefaircode.xyz
4. Count issues closed this week
5. Count code audits published this week
6. Add a new row to the table below

---

## Weekly Metrics

| Week | Stars | Forks | Watching | Contributors | Social Views | Countries | Issues Closed | Code Audits |
|------|------:|------:|---------:|-------------:|-------------:|----------:|--------------:|------------:|
| 2026-W26 (baseline) | 27 | 8 | - | 7 | ~10K total | - | - | 6 total |
| 2026-W27 | 27 | 8 | - | 7 | ~10K total | - | - | 6 total |
| 2026-W30 | 40 | 17 | 8 | 11 | ~21K total | - | 3 | 7 total |
| 2026-W31 | 41 | 18 | 8 | 12 | ~23K total | - | 22 | 7 total |
| 2026-W32 | 42 | 22 | 8 | 14 | 26K+ total | 17 | 11 | 7 total |
| 2026-W33 | 43 | 21 | 8 | 15 | 27K+ total | 17 | 55 | 7 total |
| 2026-W34 | 43 | 22 | 8 | 17 | 30K+ total | 18 | 35 | 7 total |
| 2026-W35 | 47 | 25 | 8 | 21 | 30K+ total | 18 | 33 | 7 total |
| 2026-W36 | 46 | 31 | 8 | 27 | 30K+ total | 20 | 68 | 7 total |

> **2026-W27 - v1.2.0 shipped:** Open Dataset Profiler (CLI + client-side web tool) released; 23 explainers total.
>
> **2026-W30 - v1.3.0-v1.3.2 shipped since last snapshot:** Tenant Screening audit (#07) and intersectional bias analysis (v1.3.0), Unsupervised Learning + Model Drift explainers (v1.3.1), Selection Bias explainer (v1.3.2), plus author attribution/schema, `llms.txt`, and a canonical-URL/sitemap fix for AI-crawler and Google Search Console indexing. Watching tracked for the first time this week. **Gap notice:** no snapshot was logged for three weeks (W28-W29) - issues-closed reflects the trailing 7 days, not the full gap.
>
> **2026-W31 - tooling + healthcare push under the freeze:** profiler confidence intervals (#83), shareable HTML/PDF report (#85), a `--fail-under` CI gate (#115) and `--min-group-size` small-subgroup warnings (#124), an automated em-dash CI lint (#112), and the "Why Accuracy Is Not Enough in Healthcare AI" explainer (#64). New contributors @tomatotomata and @ahmdkaml. **Note on issues-closed (22):** inflated by a one-time triage - 11 new-audit proposals were closed as `post-paper` (a timing hold aligning the tracker with the paper freeze, not rejected work), the rest are the tooling/explainer issues shipped above.
>
> **2026-W32 - GEO/SEO push, JSON/Parquet input, compare HTML reports, and a theme-toggle fix:** JSON-LD/FAQPage/Dataset schema, OpenGraph social-preview images, and an expanded `robots.txt` for AI crawlers across the site; `faircode profile`/`compare` gained `.json` and `.parquet` input (#127) and `faircode compare --html` plus a matching web-UI download button (#111, #128); `.github/CODEOWNERS` (#142, closes #138) and a theme toggle that now respects `prefers-color-scheme` (#143, closes #135). New contributor @anujkamdar. **Note on issues-closed (11):** the tooling issues shipped above, not a triage batch like W31's.
>
> **2026-W32 (later in week) - JS parity, client-side Excel, and a CI/security hardening batch:** JSON edge-case coverage and clearer parse errors (#175), client-side `.xlsx` support for the web profiler with a Subresource Integrity hash on its CDN script (#158), a `results/`-vs-`paper/results-frozen/` drift check (#173), a merge-base fix for the frozen-files check (#163), CodeQL extended to JavaScript (#162), a scripted favicon pipeline (#164), consolidated JS CLI-bridge scripts (#170), an audit-manifest `row_filters` validation test (#168), a GitHub Actions version-bump audit process (#167), removal of ~35K lines of dead vendored CI code, and CodeQL/Dependabot process docs (#161, #165). **Countries tracked for the first time this week** (16, unique countries visiting [thefaircode.xyz](https://www.thefaircode.xyz) per site analytics - distinct from the Instagram/LinkedIn-based social views figure).
>
> **2026-W32 (traction refresh) - forks and countries caught up to live data:** forks `19 → 22` (GitHub's API, was stale since the last snapshot), countries reached `16 → 17`. Contributors badge/targets/resume line also corrected to `14` - the weekly table row already had it, the rest of the doc hadn't caught up.
>
> **2026-W33 - three healthcare explainers close out the roadmap's "planned" list down to three:** Miscalibration in Clinical Risk Scores Across Groups (#106), Missing Data as Bias in Electronic Health Records (#107, with a real 10.7-point payer-code missingness gap by race computed straight from the Healthcare Readmission CSV), and Why Medical Imaging Models Fail on Underrepresented Groups (#108) - explainer count `36 → 39`. Stars, forks, watching, and contributors are unchanged from last week's live GitHub numbers. **Note on issues-closed (55):** not a triage batch like W31's - 36 PRs merged this week across CI hardening (CodeQL v4, CITATION.cff validation, workflow YAML validation, CODEOWNERS access checks), profiler tooling (XLSX/JSON edge cases, HTML report tests), and the three explainers above, several closing more than one linked issue.
>
> **2026-W33 (later in week) - a supply-chain/CI hardening + accessibility batch:** two real, previously-unnoticed drifts caught and fixed - `matplotlib`/`numpy` missing from `pyproject.toml` despite being imported unconditionally (#235, closes the same class of gap Pillow once had), and `scikit-learn` locked at `1.8.0` while `pyproject.toml` required `>=1.9.0` after the test that caught it was deleted rather than fixed (#255, restored by `@ahmdkaml`). `check-frozen-files`/`Build Explainers` now also run on direct pushes to `main`, not just PRs (#246, `@ahmdkaml`). `audits.yml`'s `profiler`/`benchmark-harness` jobs are now change-aware, skipping on docs-only pushes the same way the pre-push hook already did (#237); `run-audits` itself is left unconditional since it's the one required status check (#160). A new `scripts/check_broken_links.py` (#253) caught five real broken links in explainer markdown (a misspelled dataset-folder name, a missing `../`) plus a second bug in `build_explainers.py`'s own link resolver that had silently broken every such link in the generated `.html` too. The theme-toggle button now exposes its state via `aria-pressed` (#250), `faircode/report.py`'s HTML report tables get proper `<th scope="col">`/`<caption>` markup (#254, `@propcgamer20-png`), and `ruff check` lands as the repo's first general-purpose Python linter (#248, `@evanjain-dot`). Stars `42 → 43`; forks, watching, and contributors unchanged. Issues-closed for the week isn't re-tallied here since several of these closed same-day as this note.
>
> **2026-W33 (weekend update) - five more explainers, non-gating coverage reporting, and a new contributor:** five healthcare-adjacent explainers landed in one PR ([@Shreyash0712](https://github.com/Shreyash0712), #262) - What Is the Base Rate Fallacy?, The Obermeyer Case, Race Correction in Clinical Algorithms, What Is Reject Inference?, and Underdiagnosis Bias in Healthcare AI - closing out Phase 2's planned-healthcare-explainer backlog entirely; explainer count `39 → 44`. `make coverage` (pytest-cov, informational only, no CI gate) landed via three coordinated PRs (#263/#264 by `@ahmdkaml`, #265/#266 by new contributor **Circout-sudo**), but the profiler CI job's install step was never updated to include `pytest-cov`, so the new "Report test coverage" step failed on every run since - masked as an overall job success by `continue-on-error: true`. Fixed directly by adding `pytest-cov` to the install line; verified in a clean venv that it now reports real coverage numbers instead of erroring. Also fixed a stale `Build Explainers` CI failure from #262 skipping `make build-explainers` before opening the PR. **Contributors `14 → 15`** (Circout-sudo's first merged PR): GitHub's contributors API hadn't caught up at check time (same lag pattern as the W32 forks correction) - counted from `CONTRIBUTORS.md`'s manually-verified list instead, which is the more current source. Forks `22 → 21` (a real decrease, per GitHub's live API - not a data error). Stars `43` unchanged.
>
> **2026-W34 - traction refresh:** combined Instagram/LinkedIn impressions crossed `27K+ → 30K+`. Countries reached steady at 17. Stars, forks, watching, and contributors unchanged from last week's live numbers - this week's earlier merged work (#276-#279: a citation-links explainer pass, CLI error-handling test coverage plus a real `--html` traceback fix, favicon-parsing test coverage, and a docstring fix) was fixes and test coverage, not new explainers or audits.
>
> **2026-W34 (later in week) - two stale explainer issues closed, two real gaps filled:** cross-checking every open "Explainer:" issue against `explainers/` found four that were already done and never closed (#93, #94, #98, #99, plus #103 and #104 found in a second pass) - all closed with a pointer to the PR that already resolved them. Two were genuine gaps: [What Is Equal Opportunity?](explainers/equal-opportunity.md) (closes #80) and [What Is Intersectional Bias?](explainers/intersectional-bias.md) (closes #67) - both anchored to real frozen benchmark numbers (`equal_opportunity_diff`/`equalized_odds_diff` for COMPAS and Tenant Screening; a superadditive `intersectional_demographic_parity_diff` for Benefits Denial) rather than invented ones. Explainer count `45 → 47`.
>
> **2026-W34 (traction refresh) - forks, contributors, and countries caught up to live data:** forks `21 → 22` and countries `17 → 18` per live site analytics; contributors `15 → 17` - one from [@nivedmahendran](https://github.com/nivedmahendran)'s first merged PR (#287), the other from GitHub's contributors API finally catching up on [@TanishGoyal-Dev](https://github.com/TanishGoyal-Dev), whose own first PR it had been missing since the W32 lag note. Counted from `CONTRIBUTORS.md`'s manually-verified list rather than the raw API count (16), which still lags by that one contributor - the same reasoning as the W32/W33 corrections. Stars and watching unchanged at 43 and 8.
>
> **2026-W35 - two report-rendering parity bugs fixed, two contributor-submitted one-liners:** [@AnayDhawan](https://github.com/AnayDhawan) fixed `to_html()`/the web profiler's downloadable report missing their imbalance/missing/skew meta line and reference-baseline section (#294, closing #283 and #272), with [@Shreyash0712](https://github.com/Shreyash0712) following up on the web profiler side (#295). New contributor [@VedantMadane](https://github.com/VedantMadane) dropped `--min-group-size`'s hardcoded CLI default (#312, closing #299), and [@propcgamer20-png](https://github.com/propcgamer20-png) added the missing `proxy` extra to `audits.yml`'s profiler job, which had left `tests/test_proxy.py` silently skipped in CI (#311, closing #298). [@ahmdkaml](https://github.com/ahmdkaml)'s #288 added the `cli.py` `benchmark` subcommand test coverage issue #270 asked for, but never referenced the issue number - found and closed manually with a credit comment. Stars `43 → 47`, forks `22 → 23` (live GitHub numbers); contributors `17 → 18` (VedantMadane's first merged PR - counted from `CONTRIBUTORS.md`, the raw API still lags on `@TanishGoyal-Dev`). Countries and social reach unchanged. Explainers and audits unchanged - this week's merged work was fixes and test coverage, not new content.
>
> **2026-W35 (later in week) - all 12 open non-explainer issues closed:** #247 (`--proxy-hints` on `compare`), #251 (stdin support), #284 (web profiler advanced-thresholds panel), #302 and #271 (test coverage for `compare_to_html` and `benchmark.py`'s intersectional/`run_benchmark()` paths), #303-#306 (four web profiler bugs: keyboard focus, JSON-without-extension detection, compare-view scroll-jacking, same-dimension crossing), #301 (`--map` unknown-column error), #286 (`build-explainers.yml` trigger gap), and #309 (a ROADMAP/README contradiction) - each committed and pushed individually, verified with tests/manual CLI runs before every commit. Also credited [@propcgamer20-png](https://github.com/propcgamer20-png)'s bundled #314 (closing #300, #307, #308, #310, merged the same day). No numeric changes this note - same live GitHub snapshot as the entry above, just a lot more closed issues.
>
> **2026-W35 (weekend update) - a 12-issue re-seed, then the first one closed:** with the backlog cleared, 12 fresh non-explainer issues were opened (#315-#326) covering real, independently-reproduced gaps - a Python/JS parity break in age-band labeling on date columns (#315), literal NUL bytes in `profiler-engine.js` that hide the file from plain `grep` (#316), a silently-misparsed split-orient JSON shape (#317), a spurious 100%-drift false positive when a column auto-detects to different kinds across two datasets (#318), a `parse_reference()`/JS parity break on percent-formatted shares (#319), plus several smaller CLI/report/tooling gaps (#320-#326). Separately, a contributor conversation about wanting to verify a profiler result after the fact - "was this actually produced from this dataset, these thresholds, this version of the tool" - turned into three more issues (#327-#329) once the code confirmed the gap was real: `to_json()` echoed none of that. New contributor [@mahirhir](https://github.com/mahirhir) closed the first one same-day: `faircode/provenance.py` (#330) attaches a `provenance` block - dataset SHA-256, `faircode` version, resolved params - to `--json` exports, at the export boundary so the JS-parity test needs no change. **Contributors `18 → 19`** (mahirhir's first merged PR, counted from `CONTRIBUTORS.md` - the raw API still lags). Forks `23 → 24` (live GitHub numbers). Stars, watching, countries, and social reach unchanged.
>
> **2026-W35 (later still) - the MCP server ships, `faircode` goes live on PyPI, and a second same-week new contributor:** Phase 1 of the MCP plan discussed for #327-#329 landed - `faircode/mcp_server.py` exposes `profile_dataset`, `compare_datasets`, and `proxy_hints` as MCP tools over stdio, a thin adapter over the existing `profile()`/`compare()`/`proxy_hints()` functions with no new analysis logic and the same local-only trust boundary as the CLI. `faircode` was then published to PyPI for the first time (`pip install faircode` / `faircode[mcp]` now work without cloning the repo). New contributor [@Ayaan-20-11](https://github.com/Ayaan-20-11) fixed `scripts/render_terminal_png.py`'s hardcoded macOS-only font path (#331, closing #323) - it now uses the repo-bundled `assets/fonts/IBMPlexMono-Regular.ttf`, the same font `generate_og_images.py` already uses. **Contributors `19 → 20`** (Ayaan's first merged PR). Forks `24 → 25` (live GitHub numbers). Stars, watching, countries, and social reach unchanged.
>
> **2026-W35 (yet later) - a third same-week new contributor:** [@StudentSuite3](https://github.com/StudentSuite3) added the guard the web profiler already had (#306) but the CLI didn't - `faircode profile --cross COLA,COLA` (the same column crossed with itself) silently produced flags claiming an absent subgroup that was really just the tautological zero of a same-column crosstab. Now errors with a clear message (#337, closing #320). **Contributors `20 → 21`** (StudentSuite3's first merged PR). Stars, forks, watching, countries, and social reach unchanged from the entry above.
>
> **2026-W36 - new week, traction refresh:** Stars `47 → 48`, forks `25 → 26` (live GitHub numbers). Countries reached `18 → 20`, per site analytics. Contributors, watching, social reach, explainers, and audits unchanged from last week's snapshot. Issues-closed resets to `0` for the new week - nothing has closed yet since the #320 close that closed out W35's count.
>
> **2026-W36 (later) - web profiler provenance parity, a stale-hash bug caught in review, and a CODEOWNERS gap closed:** new contributor [@lovishmenaria14-gif](https://github.com/lovishmenaria14-gif) added a `provenance` block to the web profiler's "Copy as JSON" export (#339, closing #329), mirroring #330's Python-side shape via client-side `crypto.subtle.digest`. Review caught a real bug before crediting it as complete: the exported `dataset_hash` went stale after loading the sample dataset following a real upload, since the cached `File` object was never updated off that path - fixed directly (not part of the PR) by threading the file through as an explicit parameter instead of a side effect. Same contributor also fixed README.md's stale `explainer.html` comment (#340, closing #326) - a docs-only PR that triggered no CODEOWNERS review-request ping, since no top-level doc (`README.md`, `CHANGELOG.md`, `CONTRIBUTORS.md`, `METRICS.md`, `ROADMAP.md`) had an owner. Added `@yakew7`/`@Shreyash0712` to all five, verified both already hold write access via the `CODEOWNERS Access` workflow. **Contributors `21 → 22`** (lovishmenaria14-gif's first merged PR). Issues closed this week: `0 → 2` (#329, #326). Stars, forks, watching, countries, and social reach unchanged from the entry above.
>
> **2026-W36 (weekend) - the full open backlog cleared, 6 explainers added, and a fresh 15-issue batch opened:** all 10 remaining open non-explainer issues (#315-#319, #321-#322, #324-#325, #328) closed with individually verified, individually committed fixes - an age/date-labeling bug and a compare() drift false-positive in the profiler, three CLI validation/UX gaps, an HTML report styling gap, a markdown table-parsing regex fix (plus a same-class fix in `model-drift.html`, caught by CI's own generated-files check), a redirect-shim fix, and the `proxy_hints()` held-out-column capability (`--proxy-hints-with`). Also closed all 6 long-open explainer-request issues (#81, #280, #281, #282, #296, #297) by writing and shipping the actual explainers - accuracy equality, bootstrap confidence intervals, mitigation strategies, fairness through unawareness, LIME, and counterfactual explanation - each anchored to real frozen numbers from `paper/results-frozen/`. **Explainer count `47 → 53`.** New contributor [@sushicat75](https://github.com/sushicat75) fixed a bug found during that same batch's research - three already-published explainers stuck showing "coming soon" on the homepage roadmap grid (#341, via #356). With the backlog fully cleared, opened 15 fresh issues (#341-#355) with a deliberate difficulty spread (2 very easy, 4 easy including 3 new explainer topics, 6 normal, 3 docs-area issues tagging the two doc code owners directly) - three of those docs-area issues (#353-#355) were closed not-planned by the maintainers same-day. **Contributors `22 → 23`** (sushicat75's first merged PR). Forks `26 → 27` (live GitHub numbers). Issues closed this week: `2 → 22`. Stars, watching, countries, and social reach unchanged.
>
> **2026-W36 (later still) - three more first-time contributors, and a review-caught correctness bug fixed in a PR already merged:** [@oxura](https://github.com/oxura) fixed the MCP `get_benchmark_results` tool's missing-mirror error message, which blamed `paper/results-frozen/` and suggested an unnecessary, citation-affecting re-freeze when the actual missing file was the package-internal `faircode/_results_frozen/` mirror (#408, closing #396). [@Zinniacodes01](https://github.com/Zinniacodes01) fixed README.md's `faircode/` repo-tree, which had never been updated to list `mcp_server.py`, `_explainers/`, or `_results_frozen/` since they were added (#411, closing #409). [@shauryagangrade](https://github.com/shauryagangrade) closed a real silent-wrong-answer gap in `strategy_features()`, which fell through to a bare `else` for any unrecognized strategy name instead of erroring (#425, closing #418). [@AnayDhawan](https://github.com/AnayDhawan) excluded the generated `faircode/_explainers/` mirror from `check_em_dash.py`'s scan, which had been double-reporting the same em dash under two paths (#412, closing #393). Separately, [@nitishchauhan002](https://github.com/nitishchauhan002)'s first merged PR (#410, closing #405) set out to fix `loaders_extra.py` silently mis-parsing index-oriented JSON as columns-oriented - but review after merge found the submitted heuristic still silently transposed data in shapes its own tests didn't cover (a wide columns-oriented export, and a square all-string export). Fixed directly, not as part of the PR: replaced the heuristic entirely with a hard failure - any ambiguous dict-of-dicts JSON now raises a clear error pointing at `orient="split"` instead of guessing; README's JSON-orientation docs and `tests/test_loaders.py`'s prior columns-orientation round-trip assertion updated to match. **Contributors `23 → 27`** (oxura, Zinniacodes01, shauryagangrade, and nitishchauhan002's first merged PRs). Stars `48 → 46` (a real decrease, live GitHub API - not a data error, same pattern as the W33 forks correction). Forks `27 → 31` (live GitHub numbers). Issues closed this week: `22 → 68`. Watching, explainers, and audits unchanged. Countries and social reach not re-checked this note (no fresh analytics/social pull).

---

## Targets

| Metric | Current | Target | Timeline |
|--------|--------:|-------:|----------|
| Stars | 46 | 50+ | End of 2026 |
| Forks | 31 | 25+ | End of 2026 |
| Watching | 8 | 12+ | End of 2026 |
| Contributors | 27 | 20+ | End of 2026 |
| Social reach | 30K+ | 40K+ | End of 2026 |
| Countries reached | 20 | 20+ | End of 2026 |
| Issues closed | 68 (past 7 days) | Track weekly | Ongoing |
| Code audits | 7 | 8+ | End of 2026 |
| Explainers | 53 | 60+ | End of 2026 |

---

## Notes

- Social views = combined Instagram + LinkedIn impressions
- Countries = unique countries visiting the live website ([thefaircode.xyz](https://www.thefaircode.xyz)), via site analytics - not the social-views figure above
- Contributors = external contributors only (excluding Yash), via GitHub's contributors API
- Watching = GitHub repo watchers/subscribers, via GitHub's repo API
- Issues closed = issues merged or resolved that week, not total open
- Code audits = cumulative total published in repo
- Explainers = cumulative total in `explainers/`

---

*Resume-ready line (fill in at application time):*

> Created and scaled Fair Code, an open-source responsible AI platform explaining algorithmic bias through code audits, healthcare-bias case studies, beginner explainers, and contributor-led GitHub documentation; grew the project to **47 stars**, **18 contributors**, **23 forks**, **30K+ social views**, and website visitors from **18 countries**.
