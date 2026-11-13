"""Reproduce the model comparison behind ADR-0023.

Run from the repository root:  python scripts/model_experiments.py
Outer loop: 5-fold stratified CV repeated 20 times; every metric is computed on
held-out tests only. Part 2 scores the app's three-way output (SPREAD /
MARGINAL / NO SPREAD) to count dangerous errors."""
import json, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF, ConstantKernel

t = pd.read_csv("prototype/data/sibal_bass_table71.csv")
t = t[t.exclude_from_fit.astype(str).str.lower() != "true"].dropna(subset=["o2_pct", "flow_cm_s", "outcome"])
a = pd.DataFrame({"o2": t.o2_pct.astype(float), "flow": t.flow_cm_s.astype(float), "width": t.width_cm.astype(float),
                  "y": (t.outcome == "burned").astype(int)})
add = json.load(open("data/processed/sibal_added_tests.json"))["records"]
widths = {"Saffire I-1": 41, "Saffire II-5": 5, "Saffire II-6": 5, "Saffire III-1": 41, "Saffire IV-1": 41}  # Table 2 "Sample Width (cm)"
b = pd.DataFrame([{"o2": r["oxygen_pct"], "flow": r["flow_cm_s"], "width": widths[r["test_label"]], "y": 1} for r in add])
d = pd.concat([a, b], ignore_index=True)
y = d.y.to_numpy()
lf = np.log(d.flow.clip(lower=0.5)); lw = np.log(d.width)
F = {
  "o2+logF": np.c_[d.o2, lf],
  "o2+logF+logF2 (current)": np.c_[d.o2, lf, lf**2],
  "o2+logF+logW": np.c_[d.o2, lf, lw],
  "o2+logF+logF2+logW": np.c_[d.o2, lf, lf**2, lw],
  "o2*logF interaction": np.c_[d.o2, lf, d.o2 * lf],
}
print(f"n={len(d)}  burned={y.sum()}  went out={len(y)-y.sum()}")
print("went-out tests:", d[d.y == 0][["o2", "flow", "width"]].values.tolist())

def lr(C=1.0, cw=None): return Pipeline([("s", StandardScaler()), ("m", LogisticRegression(C=C, class_weight=cw, max_iter=2000))])
outer = RepeatedStratifiedKFold(n_splits=5, n_repeats=20, random_state=0)

def evaluate(make, X, select=None):
    acc, bal, rec, prec_n, auc, ll = [], [], [], [], [], []
    for tr, te in outer.split(X, y):
        m = make(X[tr], y[tr]) if select else make().fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]; pred = (p >= 0.5).astype(int)
        yt = y[te]
        acc.append((pred == yt).mean())
        r1 = (pred[yt == 1] == 1).mean(); r0 = (pred[yt == 0] == 0).mean() if (yt == 0).any() else np.nan
        bal.append(np.nanmean([r1, r0])); rec.append(r0)
        if len(set(yt)) == 2: auc.append(roc_auc_score(yt, p))
        ll.append(log_loss(yt, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]))
    return dict(acc=np.mean(acc), bal_acc=np.nanmean(bal), out_recall=np.nanmean(rec), auc=np.mean(auc), logloss=np.mean(ll))

rows = []
base = y.mean()
rows.append(("always burns (baseline)", dict(acc=base, bal_acc=0.5, out_recall=0.0, auc=0.5, logloss=float(log_loss(y, np.full(len(y), base))))))
for name, X in F.items():
    for cw in (None, "balanced"):
        rows.append((f"logistic {name}{' balanced' if cw else ''}", evaluate(lambda cw=cw: lr(1.0, cw), X)))
gp = lambda: GaussianProcessClassifier(ConstantKernel() * RBF([1.0, 1.0]), random_state=0)
rows.append(("gaussian process o2+logF", evaluate(gp, np.c_[d.o2, lf])))

# Nested selection: inner 4-fold CV picks feature set, C and class weight by
# log loss; the outer folds score the whole selection procedure (honest).
grid = [(n, C, cw) for n in F for C in (0.3, 1.0, 3.0) for cw in (None, "balanced")]
def nested_make(Xtr_idx_unused=None, ytr=None): pass
def run_nested():
    acc, bal, rec, auc, ll, picks = [], [], [], [], [], []
    for tr, te in outer.split(F["o2+logF"], y):
        inner = StratifiedKFold(4, shuffle=True, random_state=1)
        best, best_ll = None, 1e9
        for n, C, cw in grid:
            X = F[n]; s = []
            for itr, ite in inner.split(X[tr], y[tr]):
                m = lr(C, cw).fit(X[tr][itr], y[tr][itr]); p = m.predict_proba(X[tr][ite])[:, 1]
                s.append(log_loss(y[tr][ite], np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]))
            if np.mean(s) < best_ll: best_ll, best = np.mean(s), (n, C, cw)
        n, C, cw = best; picks.append(best)
        m = lr(C, cw).fit(F[n][tr], y[tr]); p = m.predict_proba(F[n][te])[:, 1]; pred = (p >= .5).astype(int); yt = y[te]
        acc.append((pred == yt).mean()); r1 = (pred[yt == 1] == 1).mean(); r0 = (pred[yt == 0] == 0).mean()
        bal.append((r1 + r0) / 2); rec.append(r0); auc.append(roc_auc_score(yt, p)); ll.append(log_loss(yt, np.clip(p, 1e-6, 1-1e-6), labels=[0, 1]))
    from collections import Counter
    return dict(acc=np.mean(acc), bal_acc=np.mean(bal), out_recall=np.mean(rec), auc=np.mean(auc), logloss=np.mean(ll)), Counter(picks).most_common(4)
nres, picks = run_nested()
rows.append(("NESTED auto-selection (honest)", nres))

print(f"\n{'model':48s} {'acc':>6s} {'bal_acc':>8s} {'out_rec':>8s} {'AUC':>6s} {'logloss':>8s}")
for n, r in rows:
    print(f"{n:48s} {r['acc']:6.3f} {r['bal_acc']:8.3f} {r['out_recall']:8.3f} {r['auc']:6.3f} {r['logloss']:8.3f}")
print("\nnested picks (most common):", picks)

# ---- Part 2: three-way output and dangerous errors ----
# Three-way output as the app reports it: SPREAD if P>=hi, NO SPREAD if P<=lo, else MARGINAL.
def three_way(make, X, lo, hi):
    burned = {"spread": 0, "marginal": 0, "no_spread": 0}; out = dict(burned)
    for tr, te in outer.split(X, y):
        p = make().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        for pi, yi in zip(p, y[te]):
            k = "spread" if pi >= hi else "no_spread" if pi <= lo else "marginal"
            (burned if yi == 1 else out)[k] += 1
    nb, no = sum(burned.values()), sum(out.values())
    return {k: v / nb for k, v in burned.items()}, {k: v / no for k, v in out.items()}
print(f"{'model':38s} {'band':10s} | {'BURNED tests ->':>15s} spread  marg  NO_SPREAD(danger) | {'WENT-OUT tests ->':>17s} spread(miss)  marg  no_spread")
for name, X, cw in [("current U-shaped", F["o2+logF+logF2 (current)"], None), ("simpler o2+logF", F["o2+logF"], None), ("o2+logF balanced", F["o2+logF"], "balanced")]:
    for lo, hi in [(0.4, 0.6), (0.3, 0.7), (0.2, 0.8)]:
        b, o = three_way(lambda cw=cw: lr(1.0, cw), X, lo, hi)
        print(f"{name:38s} {lo:.1f}-{hi:.1f}   | {'':15s} {b['spread']:6.2f} {b['marginal']:5.2f} {b['no_spread']:8.2f}          | {'':17s} {o['spread']:6.2f}      {o['marginal']:5.2f} {o['no_spread']:6.2f}")
