"""SN193 - LSTM direction, the 'stock prediction' claim (PLAN.md). Every 15 minutes 09:45-14:30 (20 decisions a
session), the last 60 one-minute bars (seq.py) -> will the index be higher 15 minutes later? Per year-fold trained on
earlier development years. Out-of-sample accuracy against 50%, 'same as the last 15 minutes' and 'opposite'. Traded on
Gold's empty days: P >= theta buys the ATM call, P <= 1 - theta the put (1 lot, +Rs 1,000 / -Rs 1,000, the day stops
at +Rs 1,000 or -Rs 2,000); theta in {0.55, 0.6} chosen per fold on the other folds; matched random-side null."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import seq  # noqa: E402

pw = pe.pw
DEC = tuple(range(30, 316, 15))
FOLDS = ("2024", "2025", "2026")
THETAS = (0.55, 0.6)
LOCAL = pe.LOCAL


def build():
    p = LOCAL / "sn193-data.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    rows = []
    for S in pw.sessions():
        f = seq.session_feats(S)
        c = S.F["c"]
        for i in DEC:
            rows.append((S.day, i, seq.window(f, i), float(c[i + 15] > c[i]), float(c[i] > c[i - 15])))
    data = {"day": np.array([r[0] for r in rows]), "i": np.array([r[1] for r in rows]), "X": np.stack([r[2] for r in rows]),
            "Y": np.array([[r[3]] for r in rows], dtype=np.float32), "last15_up": np.array([r[4] for r in rows])}
    LOCAL.mkdir(exist_ok=True)
    p.write_bytes(pickle.dumps(data))
    return data


def day_trades(S, decisions, theta, rng=None):
    """decisions: [(i, p)] in time order."""
    free, net, n = -1, 0.0, 0
    for i, p in decisions:
        if i <= free or net >= 1000.0 - 1e-6 or net <= -2000.0 + 1e-6:
            continue
        if rng is None:
            if p >= theta:
                d = 1
            elif p <= 1 - theta:
                d = -1
            else:
                continue
        else:
            d = 1 if rng.random() < 0.5 else -1
        r = pw.trade(S, i, "CE" if d > 0 else "PE", pw.atm(S, i), 1e9, target=1000.0, stop=-1000.0, max_lots=1)
        if r is None:
            continue
        net += r["net"]
        n += 1
        free = r["j"]
    return (net, n) if n else (None, 0)


if __name__ == "__main__":
    out_path = HERE / "results-sn193.json"
    if out_path.exists():
        raise SystemExit("SN193 is scored once")
    data = build()
    year = np.array([d[:4] for d in data["day"]])
    dev = data["day"] < pw.TEST_FROM
    P = np.full(len(year), np.nan, dtype=np.float32)
    res = {"accuracy": {}}
    for fy in FOLDS:
        tr, te = dev & (year < fy), dev & (year == fy)
        st = seq.Standard(data["X"][tr])
        net = seq.train_lstm(st(data["X"][tr]), data["Y"][tr], seed=193)
        P[te] = seq.predict(net, st(data["X"][te]))[:, 0]
        yt = data["Y"][te, 0]
        res["accuracy"][fy] = {"lstm": round(float(((P[te] >= 0.5) == (yt == 1)).mean()), 4),
                               "same_as_last_15": round(float((data["last15_up"][te] == yt).mean()), 4),
                               "opposite": round(float((data["last15_up"][te] != yt).mean()), 4),
                               "always_up": round(float(yt.mean()), 4), "n": int(te.sum())}
        print(f"SN193 fold {fy}: {json.dumps(res['accuracy'][fy])}", flush=True)
    sess = {S.day: S for S in pw.sessions()}
    empty = [S.day for S in pe.empty_sessions() if S.day[:4] in FOLDS]
    dec = {}
    for r in np.flatnonzero(dev & (year >= "2024")):
        dec.setdefault(data["day"][r], []).append((int(data["i"][r]), float(P[r])))
    per = {th: {} for th in THETAS}
    for th in THETAS:
        for d in empty:
            n, _k = day_trades(sess[d], dec.get(d, []), th)
            if n is not None:
                per[th][d] = n
    loyo = {}
    for fy in FOLDS:
        th = max(THETAS, key=lambda t: sum(v for d, v in per[t].items() if d[:4] != fy))
        xs = {d: v for d, v in per[th].items() if d[:4] == fy}
        loyo[fy] = {"theta": th, "net": round(sum(xs.values())), "trade_days": len(xs)}
    rng = np.random.default_rng(193)
    nulls = []
    for _ in range(100):
        t = 0.0
        for fy in FOLDS:
            for d in (d for d, _v in per[loyo[fy]["theta"]].items() if d[:4] == fy):
                n, _k = day_trades(sess[d], dec.get(d, []), 0.5, rng)
                t += n or 0.0
        nulls.append(t)
    total = sum(v["net"] for v in loyo.values())
    res.update({"loyo": loyo, "total": total, "null_mean": round(float(np.mean(nulls))), "null_p95": round(float(np.percentile(nulls, 95)))})
    res["dev_pass_partial"] = bool(total > 0 and sum(v["net"] > 0 for v in loyo.values()) >= 2 and total > res["null_p95"])
    st = seq.Standard(data["X"][dev])
    net = seq.train_lstm(st(data["X"][dev]), data["Y"][dev], seed=193)
    P_test = np.full(len(year), np.nan, dtype=np.float32)
    P_test[~dev] = seq.predict(net, st(data["X"][~dev]))[:, 0]
    th = max(THETAS, key=lambda t: sum(per[t].values()))
    (LOCAL / "sn193_test.pkl").write_bytes(pickle.dumps({"P_test": P_test, "theta": th, "mu": st.mu, "sd": st.sd}))
    import torch
    torch.save(net.state_dict(), LOCAL / "sn193-lstm.pt")
    print("SN193", json.dumps({k: v for k, v in res.items() if k != "accuracy"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
