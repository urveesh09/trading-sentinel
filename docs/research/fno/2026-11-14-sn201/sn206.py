"""SN206 - machine-learning risk model on WK-S (PLAN.md SN205 rule, applied to WK-S by the amendment).
Samples: the WK-S structure / exit / stop at every k in {1, 2, 3, F} (k is a feature); label = the trade loses at
Rs 100. LightGBM (7 leaves, 200 trees, lr 0.03, min leaf 20, seed 205) on the entry features; an LSTM (the last 20
sessions of log RV, return, range, gap + k; hidden 16, dropout 0.2, 30 epochs, Adam 1e-3, seed 205); their average.
Quarterly expanding refits (>= 80 training samples, else trade unfiltered). Skip when the predicted loss probability
>= the 67th percentile of that model's predictions on its own training set. Scored on WK-S's own k. Null: random skip
of the same per-year count. Final models refitted on all development are saved for SN209."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat  # noqa: E402
import sn205  # noqa: E402
import wk  # noqa: E402

SEED = 205


def lgb_fit(X, y):
    import lightgbm as lgb
    m = lgb.LGBMClassifier(num_leaves=7, n_estimators=200, learning_rate=0.03, min_child_samples=20, random_state=SEED,
                           deterministic=True, force_row_wise=True, verbose=-1)
    m.fit(X, y)
    return m


class LSTMModel:
    def __init__(self):
        import torch
        torch.manual_seed(SEED)
        self.torch = torch
        nn = torch.nn

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(5, 16, batch_first=True)
                self.drop = nn.Dropout(0.2)
                self.out = nn.Linear(16, 1)

            def forward(self, x):
                h, _ = self.lstm(x)
                return self.out(self.drop(h[:, -1, :])).squeeze(-1)
        self.net = Net()

    def fit(self, S, y):
        torch = self.torch
        self.mu = S.reshape(-1, S.shape[-1]).mean(0)
        self.sd = S.reshape(-1, S.shape[-1]).std(0) + 1e-9
        X = torch.tensor((S - self.mu) / self.sd, dtype=torch.float32)
        Y = torch.tensor(y, dtype=torch.float32)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        lossf = torch.nn.BCEWithLogitsLoss()
        g = torch.Generator().manual_seed(SEED)
        self.net.train()
        for _ep in range(30):
            perm = torch.randperm(len(X), generator=g)
            for b in range(0, len(X), 32):
                idx = perm[b:b + 32]
                opt.zero_grad()
                lossf(self.net(X[idx]), Y[idx]).backward()
                opt.step()
        return self

    def predict(self, S):
        torch = self.torch
        self.net.eval()
        with torch.no_grad():
            return torch.sigmoid(self.net(torch.tensor((S - self.mu) / self.sd, dtype=torch.float32))).numpy()


def samples(D, weeks, A, dl, beta=None, mk=wk.NIFTY):
    s, _k, ex, st = A
    rows = []
    for k in (1, 2, 3, "F"):
        for t in wk.book(mk, D, weeks, (s, k, ex, st)):
            f = feat.features(dl, t, beta)
            q = feat.sequence(dl, t)
            if f is None or q is None:
                continue
            rows.append({"t": t, "k_tag": k, "x": np.array([f[n] for n in feat.FEATURES], dtype=float), "seq": q,
                         "y": int(t["net"] < 0)})
    return sorted(rows, key=lambda r: r["t"]["entry"])


if __name__ == "__main__":
    out_path = HERE / "results-sn206.json"
    if out_path.exists():
        raise SystemExit("SN206 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    A = pickle.loads((wk.LOCAL / "sn204-picks.pkl").read_bytes())["WK-S"]
    dl = feat.Daily(D)
    rows = samples(D, weeks, A, dl)
    quarters = sorted({feat.quarter(r["t"]["entry"]) for r in rows})
    pred = {"lgb": {}, "lstm": {}, "avg": {}}
    trained_q = []
    for q in quarters:
        tr_rows = [r for r in rows if r["t"]["expiry"] < f"{q[:4]}-{(int(q[5]) - 1) * 3 + 1:02d}-01"]
        te_rows = [r for r in rows if feat.quarter(r["t"]["entry"]) == q]
        if len(tr_rows) < 80 or not te_rows:
            continue
        trained_q.append(q)
        X = np.array([r["x"] for r in tr_rows])
        y = np.array([r["y"] for r in tr_rows])
        m1 = lgb_fit(X, y)
        p1_tr = m1.predict_proba(X)[:, 1]
        p1 = m1.predict_proba(np.array([r["x"] for r in te_rows]))[:, 1]
        m2 = LSTMModel().fit(np.array([r["seq"] for r in tr_rows]), y.astype(np.float32))
        p2_tr = m2.predict(np.array([r["seq"] for r in tr_rows]))
        p2 = m2.predict(np.array([r["seq"] for r in te_rows]))
        th = {"lgb": np.quantile(p1_tr, 0.67), "lstm": np.quantile(p2_tr, 0.67), "avg": np.quantile((p1_tr + p2_tr) / 2, 0.67)}
        for r, a, b in zip(te_rows, p1, p2):
            key = (r["t"]["expiry"], str(r["k_tag"]))
            pred["lgb"][key] = (float(a), a >= th["lgb"])
            pred["lstm"][key] = (float(b), b >= th["lstm"])
            pred["avg"][key] = (float((a + b) / 2), (a + b) / 2 >= th["avg"])
    own = [r for r in rows if str(r["k_tag"]) == str(A[1])]
    tr_own = [r["t"] for r in own]
    unf = round(sum(t["net"] for t in tr_own))
    res = {"variant": wk.vname(A), "samples": len(rows), "scored_weeks": len(own), "trained_quarters": trained_q,
           "unfiltered_sum": unf, "unfiltered_by_year": {y: round(sum(t["net"] for t in tr_own if t["entry"][:4] == y)) for y in wk.YEARS}}
    from sklearn.metrics import roc_auc_score
    decisions = {}
    for name in ("lgb", "lstm", "avg"):
        keep = [not pred[name].get((r["t"]["expiry"], str(r["k_tag"])), (0, False))[1] for r in own]
        decisions[name] = {t["expiry"]: bool(k) for t, k in zip(tr_own, keep)}
        ys = [(r["y"], pred[name][(r["t"]["expiry"], str(r["k_tag"]))][0]) for r in own if (r["t"]["expiry"], str(r["k_tag"])) in pred[name]]
        auc = roc_auc_score([a for a, _b in ys], [b for _a, b in ys]) if len({a for a, _b in ys}) == 2 else None
        net = round(sum(t["net"] for t, k in zip(tr_own, keep) if k))
        p95, nm = sn205.null_p95(tr_own, keep)
        by = {y: round(sum(t["net"] for t, k in zip(tr_own, keep) if k and t["entry"][:4] == y)) for y in wk.YEARS}
        res[name] = {"auc_out_of_sample": round(auc, 3) if auc else None, "net": net, "skipped": len(keep) - sum(keep), "by_year": by,
                     "null_p95": p95, "null_mean": nm, "PASS": bool(net > unf and net > p95)}
        print(f"SN206 {name}:", json.dumps(res[name]), flush=True)
    (wk.LOCAL / "sn206-decisions.pkl").write_bytes(pickle.dumps(decisions))
    X = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])
    m1 = lgb_fit(X, y)
    m2 = LSTMModel().fit(np.array([r["seq"] for r in rows]), y.astype(np.float32))
    th = {"lgb": float(np.quantile(m1.predict_proba(X)[:, 1], 0.67)),
          "lstm": float(np.quantile(m2.predict(np.array([r["seq"] for r in rows])), 0.67))}
    th["avg"] = float(np.quantile((m1.predict_proba(X)[:, 1] + m2.predict(np.array([r["seq"] for r in rows]))) / 2, 0.67))
    (wk.LOCAL / "sn206-models.pkl").write_bytes(pickle.dumps({"lgb": m1, "lstm_state": m2.net.state_dict(), "lstm_mu": m2.mu,
                                                             "lstm_sd": m2.sd, "thresholds": th}))
    print("SN206", json.dumps({k: v for k, v in res.items() if k not in ("lgb", "lstm", "avg")}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
