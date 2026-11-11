# GitHub Actions workflows

This table is a quick guide to the workflows in this directory. The `Audits`
workflow's seven `run-audits` jobs are the required merge checks listed in the
active `Protect main` repository ruleset. Other workflow runs are informative
or conditional; their presence alone does not make them merge requirements.

| Workflow | Trigger | Merge gate | Script or action |
| --- | --- | --- | --- |
| [Audits](audits.yml) | Push to `main`; pull requests | Required: `run-audits` matrix | `fair.py` and `unfair.py` for each audit; conditional `profiler` job runs `make coverage-fast` (the suite without the `slow` tests, with coverage), and conditional `benchmark-harness` job runs every test marked `slow` |
| [Benchmark diff](benchmark-diff.yml) | Pull requests; manual dispatch; `rerun-benchmark` label | Informational; full rerun opt-in | `scripts/diff_results.py` and benchmark CLI |
| [Build Explainers](build-explainers.yml) | Push to `main`; pull requests matching documentation paths | Informational | `scripts/build_explainers.py`, `scripts/generate_og_images.py`, and generated-file checks |
| [Validate CITATION.cff](citation.yml) | Push or pull request changing `CITATION.cff` | Informational | `citation-file-format/cffconvert-github-action` |
| [CODEOWNERS Access](codeowners-access.yml) | Changes to `.github/CODEOWNERS`; weekly schedule; manual dispatch | Informational | `actions/github-script` checks declared owners' access |
| [CodeQL](codeql.yml) | Push or pull request to `main`; weekly schedule | Informational | GitHub CodeQL actions |
| [External links](external-links.yml) | Weekly schedule; manual dispatch | Informational | `scripts/check_external_links.py` |
| [Contributors vs merged pull requests](contributors-drift.yml) | Weekly schedule; manual dispatch | Informational | `scripts/check_contributors.py --pending` |
| [Favicons](favicons.yml) | Changes to the logo or favicon generator | Informational | `scripts/generate_favicons.py` |
| [First Interaction](first.interaction.yml) | New issue opened | Informational | `actions/github-script` sends the first-contributor greeting |
| [lint](lint.yml) | Push; pull request | Informational | `make lint` and `scripts/check_issue_refs.py` |
| [PR Review Ping](pr-review-ping.yml) | Pull request opened or reopened | Informational | `actions/github-script` notifies path owners |
| [Traction vs GitHub](traction-live.yml) | Weekly schedule; manual dispatch | Informational | `scripts/check_traction.py --live` |
| [Validate workflow YAML](validate-workflow.yml) | Push or pull request changing workflow files | Informational | PyYAML validates workflow YAML |

The repository ruleset is the source of truth for required checks; update the
merge-gate column if that policy changes.
