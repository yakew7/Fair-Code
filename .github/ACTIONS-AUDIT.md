# GitHub Actions major-version bump audit

Dependabot's `github-actions` ecosystem (added in #146) merged several major-version
jumps purely on "CI stayed green": `actions/checkout` v4→v7, `actions/setup-python`
v5→v7, `actions/setup-node` v4→v7, `actions/github-script` v8→v9. #167 asked for a
one-time read of each action's release notes to confirm nothing behavior-relevant
changed silently. Findings below - re-run this check the next time any of these
jump a major version.

## `actions/checkout` (v4 → v7)

**Real change:** v4.4.0+/v7.0.0 added a safety block for checking out fork PRs
under `pull_request_target` / `workflow_run` triggers (an `allow-unsafe-pr-checkout`
override was added, marked `[BREAKING]`).

**Applicability:** `.github/workflows/first.interaction.yml` is the only workflow
using `pull_request_target` in this repo, and it never calls `actions/checkout` -
it only uses `actions/github-script`. No checkout step anywhere in the repo runs
under a privileged trigger against untrusted fork code. **Not applicable.**

## `actions/setup-python` (v5 → v7)

**Real changes:** v6.0.0 requires Node 24 (runner ≥ v2.327.1); v7.0.0 removed the
`pip-install` input.

**Applicability:** every `setup-python` step in this repo only sets `python-version`
and, in `audits.yml`, `cache: 'pip'` - neither removed nor Node-runtime-sensitive.
**Not applicable.**

## `actions/setup-node` (v4 → v7)

**Real changes:** v5.0.0 auto-enables caching when `package.json` has a
`packageManager` field (opt out via `package-manager-cache: false`); v6.0.0 scoped
automatic caching to npm only; v7.0.0 removed a dummy `NODE_AUTH_TOKEN` export.

**Applicability:** this repo has no `package.json` at all (no npm dependency
management), so there's nothing for the `packageManager` auto-caching to detect,
and nothing depends on `NODE_AUTH_TOKEN`. **Not applicable.**

## `actions/github-script` (v8 → v9)

**Real changes:** `@actions/github` is now ESM-only, so `require('@actions/github')`
no longer works; scripts that declare `const getOctokit = ...`/`let getOctokit = ...`
now collide with the injected parameter of the same name.

**Applicability:** `first.interaction.yml`'s script only uses the injected
`github`/`context` globals directly - no `require()`, no `getOctokit` redeclaration.
**Not applicable.**

## Conclusion

All four version jumps are confirmed safe for how this repo actually uses them.
None of the breaking changes in any release apply to the specific inputs/triggers
configured here.
