# Generated from explainers/auc-gaps-by-group.md by scripts/build_explainers.py. Edit the markdown, not this file.
import numpy as np
from math import erf, sqrt
from faircode.benchmark import load_audit
from faircode.models import build_model

def placement(score, other_sorted, above):
    """Share of the other class each score beats (ties count half), from two binary searches instead of a loop."""
    below = np.searchsorted(other_sorted, score, side="left")
    through = np.searchsorted(other_sorted, score, side="right")
    return (below + 0.5 * (through - below)) / len(other_sorted) if above else 1 - (below + 0.5 * (through - below)) / len(other_sorted)

def delong_auc_var(y, score):
    """AUC and its DeLong variance (DeLong, DeLong, Clarke-Pearson 1988) for one sample."""
    pos, neg = score[y == 1], score[y == 0]
    v10 = placement(pos, np.sort(neg), above=True)       # each positive: share of negatives it beats
    v01 = placement(neg, np.sort(pos), above=False)      # each negative: share of positives that beat it
    return v10.mean(), v10.var(ddof=1) / len(pos) + v01.var(ddof=1) / len(neg)

def fast_auc(y, level, n_levels):
    """AUC of a resample from its tie-aware score levels: two bincounts and a cumulative sum, no sorting."""
    pos = np.bincount(level[y == 1], minlength=n_levels)
    neg = np.bincount(level[y == 0], minlength=n_levels)
    if pos.sum() == 0 or neg.sum() == 0:
        raise ValueError("a bootstrap sample needs both classes")
    return float((pos * (np.cumsum(neg) - neg + 0.5 * neg)).sum() / (pos.sum() * neg.sum()))

def audit_auc(folder, attribute, n_boot=2000):
    """Per-group AUC, the gap with its two intervals, and the error rates at the default 0.5 cutoff."""
    data = load_audit(folder)
    tr, te = data.idx_train, data.idx_test
    model = build_model("logistic_regression", data.random_state).fit(data.X.iloc[tr], data.y.iloc[tr])
    p = model.predict_proba(data.X.iloc[te])[:, 1]
    y = data.y.iloc[te].to_numpy()
    s = data.group(attribute)[te]                       # 1 = disadvantaged group
    print(f"{folder} - {attribute}  (test rows: advantaged {(s == 0).sum()}, disadvantaged {(s == 1).sum()})")
    auc, var = {}, {}
    for g, name in ((0, "advantaged"), (1, "disadvantaged")):
        auc[g], var[g] = delong_auc_var(y[s == g], p[s == g])
        pred = p[s == g] >= 0.5
        yg = y[s == g]
        print(f"  {name:13s} AUC {auc[g]:.3f} | FPR at 0.5 {pred[yg == 0].mean():.3f} | TPR at 0.5 {pred[yg == 1].mean():.3f}")
    gap = auc[1] - auc[0]
    z = gap / sqrt(var[0] + var[1])
    p_value = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    rng = np.random.default_rng(data.random_state)
    idx = {g: np.flatnonzero(s == g) for g in (0, 1)}
    levels = {g: np.unique(p[idx[g]], return_inverse=True)[1] for g in (0, 1)}    # tie-aware rank of each row's score
    boots = []
    for _ in range(n_boot):
        a = []
        for g in (0, 1):
            pick = rng.choice(len(idx[g]), size=len(idx[g]), replace=True)       # the same draws as picking rows of idx[g]
            a.append(fast_auc(y[idx[g]][pick], levels[g][pick], levels[g].max() + 1))
        boots.append(a[1] - a[0])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"  AUC gap {gap:+.3f} | bootstrap 95% interval [{lo:+.3f}, {hi:+.3f}] | DeLong z {z:+.2f}, p {p_value:.3f}")

audit_auc("Tenant Screening", "race")
audit_auc("Healthcare Readmission", "age")
audit_auc("Insurance Denial", "gender")
