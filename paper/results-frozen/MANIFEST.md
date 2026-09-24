# Frozen results provenance

This is a comparison snapshot, not evidence for a live publication. `results/` at the repo
root keeps changing as contributors add audits or rerun the harness; this folder does not -
regenerate it with `scripts/freeze_paper_results.py` only when you want a new fixed point to
compare against.

## Provenance

- **Git commit:** `2fa4a6693210a1c99932b8ec7a0bd20f052597aa`
- **Git branch:** `main`
- **Python:** 3.13.2
- **scikit-learn:** 1.9.0
- **fairlearn:** 0.14.0
- **pandas:** 3.0.2
- **numpy:** 2.4.4
- **Full environment:** `requirements-lock.txt` in this folder

## Audits included (7 domains)

The exact, reproducible set of manifests this snapshot covers - not "whatever was in the
repo that week":

- `AI Fair Recruitment/audit.yaml`
- `Benefits Denial/audit.yaml`
- `COMPAS/audit.yaml`
- `German Credit Lending/audit.yaml`
- `Healthcare Readmission/audit.yaml`
- `Insurance Denial/audit.yaml`
- `Tenant Screening/audit.yaml`

## Reproducing this snapshot

```bash
git checkout 2fa4a6693210a1c99932b8ec7a0bd20f052597aa
pip install -r requirements-lock.txt
pip install -e ".[benchmark]"
faircode benchmark --out results/
python3 scripts/freeze_paper_results.py
```
