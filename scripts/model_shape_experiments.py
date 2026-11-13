"""Reproduce the boundary-shape comparison behind ADR-0024.

Run from the repository root:  python scripts/model_shape_experiments.py
Compares O2 + {log U, 1/U, log U + 1/U, log U + log U^2, with sample width}
with 5-fold CV repeated 20 times, nested shape selection, and the distance to
the authors' quenching line read from NTRS 20150008962 Fig. 7 (+/-0.1)."""
import json, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.metrics import roc_auc_score, log_loss

t = pd.read_csv("prototype/data/sibal_bass_table71.csv")
t = t[t.exclude_from_fit.astype(str).str.lower() != "true"].dropna(subset=["o2_pct", "flow_cm_s", "outcome"])
a = pd.DataFrame({"o2": t.o2_pct.astype(float), "U": t.flow_cm_s.astype(float), "w": t.width_cm.astype(float),
                  "y": (t.outcome == "burned").astype(int), "lab": t.test_label, "out": t.outcome})
add = json.load(open("data/processed/sibal_added_tests.json"))["records"]
wid = {"Saffire I-1": 41, "Saffire II-5": 5, "Saffire II-6": 5, "Saffire III-1": 41, "Saffire IV-1": 41}
b = pd.DataFrame([{"o2": r["oxygen_pct"], "U": r["flow_cm_s"], "w": wid[r["test_label"]], "y": 1, "lab": r["test_label"], "out": "burned"} for r in add])
d = pd.concat([a, b], ignore_index=True); y = d.y.to_numpy()
U = d.U.clip(lower=0.5)
def feats(df, kind):
    u = df.U.clip(lower=0.5); lu = np.log(u); lw = np.log(df.w)
    return {"logU": np.c_[df.o2, lu], "1/U": np.c_[df.o2, 1/u], "logU+1/U": np.c_[df.o2, lu, 1/u],
            "logU+logU2": np.c_[df.o2, lu, lu**2], "1/U+logW": np.c_[df.o2, 1/u, lw], "logU+1/U+logW": np.c_[df.o2, lu, 1/u, lw]}[kind]
def lr(): return Pipeline([("s", StandardScaler()), ("m", LogisticRegression(C=1.0, max_iter=5000))])
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=20, random_state=0)
# NASA's six quench tests (Table 7.1), the points the authors' line is drawn through.
quench = d[d.out == "self_extinguished"]
print("quench tests:", quench[["lab", "o2", "U", "w"]].values.tolist())
print(f"\n{'shape':16s} {'acc':>6s} {'AUC':>6s} {'logloss':>8s} {'danger':>8s} {'ext.flag':>8s} | P(burn) at the 6 quench tests (held out)   | O2 at P=0.5, 2.2cm: U=2.2  3.0  5.0  10")
for kind in ["logU", "1/U", "logU+1/U", "logU+logU2", "1/U+logW", "logU+1/U+logW"]:
    X = feats(d, kind); acc, auc, ll = [], [], []; dang = nb = flag = no = 0
    pq = {i: [] for i in quench.index}
    for tr, te in cv.split(X, y):
        m = lr().fit(X[tr], y[tr]); p = m.predict_proba(X[te])[:, 1]; yt = y[te]
        acc.append(((p >= .5) == yt).mean()); auc.append(roc_auc_score(yt, p)); ll.append(log_loss(yt, np.clip(p, 1e-6, 1-1e-6), labels=[0, 1]))
        cls = np.where(p >= .7, 2, np.where(p <= .3, 0, 1))
        dang += ((cls == 0) & (yt == 1)).sum(); nb += (yt == 1).sum(); flag += ((cls <= 1) & (yt == 0)).sum(); no += (yt == 0).sum()
        for j, idx in enumerate(te):
            if idx in pq: pq[idx].append(p[j])
    full = lr().fit(X, y)
    o2grid = np.linspace(14, 24, 2001); bnd = []
    for u in (2.2, 3.0, 5.0, 10.0):
        g = pd.DataFrame({"o2": o2grid, "U": u, "w": 2.2}); pp = full.predict_proba(feats(g, kind))[:, 1]
        k = np.argmin(abs(pp - .5)); bnd.append(f"{o2grid[k]:5.1f}" if abs(pp[k] - .5) < .05 else "  n/a")
    qp = " ".join(f"{np.mean(pq[i]):.2f}" for i in quench.index)
    print(f"{kind:16s} {np.mean(acc):6.3f} {np.mean(auc):6.3f} {np.mean(ll):8.3f} {dang:4d}/{nb:<4d} {flag:3d}/{no:<4d} | {qp:42s} | {'  '.join(bnd)}")

# ---- Nested selection over the 6 shapes (honest score of "pick the best shape") ----
from sklearn.model_selection import StratifiedKFold
kinds = ["logU", "1/U", "logU+1/U", "logU+logU2", "1/U+logW", "logU+1/U+logW"]
acc, auc, picks = [], [], []
for tr, te in cv.split(d, y):
    inner = StratifiedKFold(4, shuffle=True, random_state=1); best, bl = None, 9
    for k in kinds:
        X = feats(d, k); s = []
        for itr, ite in inner.split(X[tr], y[tr]):
            p = lr().fit(X[tr][itr], y[tr][itr]).predict_proba(X[tr][ite])[:, 1]
            s.append(log_loss(y[tr][ite], np.clip(p, 1e-6, 1-1e-6), labels=[0, 1]))
        if np.mean(s) < bl: bl, best = np.mean(s), k
    picks.append(best); X = feats(d, best)
    p = lr().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    acc.append(((p >= .5) == y[te]).mean()); auc.append(roc_auc_score(y[te], p))
from collections import Counter
print(f"\nNESTED shape selection: acc {np.mean(acc):.3f}  AUC {np.mean(auc):.3f}  picks {Counter(picks).most_common()}")

# ---- Distance to the authors' dashed quenching line (read from Fig. 7, about +/-0.1) ----
traced = [(2.19, 18.9), (2.47, 18.4), (2.72, 17.6), (3.07, 17.0), (3.69, 16.8)]
for kind in ["logU", "1/U"]:
    full = lr().fit(feats(d, kind), y); o2grid = np.linspace(14, 24, 4001); diffs = []
    for u, o in traced:
        g = pd.DataFrame({"o2": o2grid, "U": u, "w": 2.2}); pp = full.predict_proba(feats(g, kind))[:, 1]
        diffs.append(o2grid[np.argmin(abs(pp - .5))] - o)
    print(f"{kind:6s} model minus authors' line (O2 points) at U={[u for u,_ in traced]}: {[round(x,2) for x in diffs]}  mean |diff| {np.mean(np.abs(diffs)):.2f}")
