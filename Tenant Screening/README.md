# Audit 07: Tenant Screening - Rental Application Bias - Reproducibility

Part of [Fair Code](../README.md#results-at-a-glance). This documents how to reproduce this audit and the exact numbers to expect. It does not change any result - the figures below are the published, paper-aligned numbers. See [CLAUDE.md](../CLAUDE.md) for the paper-freeze policy.

## Reproducibility checklist

- [ ] Install pinned dependencies: `pip install -r ../requirements-lock.txt` (the exact versions used for the published run), or `pip install -r ../requirements.txt` for loose ranges
- [ ] Randomness is fixed: `random_state: 42` (declared in `audit.yaml`, and used in `unfair.py` / `fair.py`)
- [ ] Split: 80/20 train/test, stratified (`test_size: 0.2`)
- [ ] Run both scripts from the repository root, so dataset paths resolve

## Reproduce

```bash
python3 "Tenant Screening/unfair.py"   # biased baseline (protected attribute included)
python3 "Tenant Screening/fair.py"     # mitigated (protected attribute + proxies dropped)
```

## What the audit controls

- Protected attribute(s): Race
- Proxy feature(s) removed in `fair.py`: Prior Arrest/Conviction Episodes, Gang Affiliated, Residence Changes
- Fairness metric: Demographic Parity (difference in positive-prediction rate between groups)

## Expected result (published, paper-aligned)

| Group | Gap, biased (`unfair.py`) | Gap, mitigated (`fair.py`) | Reduction |
|-------|--------------------------:|---------------------------:|----------:|
| Race | 6.68% | 5.16% | 23% |

These match the "Results at a Glance" table in the [main README](../README.md#results-at-a-glance). Both scripts train a seeded `RandomForestClassifier(random_state=42)`, which is not guaranteed bit-identical across CPU architectures / BLAS backends - the figures above were confirmed reproducible on two independent runs in this repo's pinned environment, but if your numbers differ in the low-order digits, that is more likely this than a real bug; check your package versions and report your exact environment before assuming the documented figures are wrong.
