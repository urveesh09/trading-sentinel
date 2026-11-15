"""SN191 - the LSTM entry model (PLAN.md). Decisions at 10:00, 11:00, 12:00, 13:00 and 14:00 of every session;
labels: 1 lot ATM CE / PE reaches +Rs 1,000 before -Rs 1,000 by 15:10 (house fills). The LSTM (seq.py) is trained
per year-fold on earlier development years only (2024 on 2023; 2025 on 2023-24; 2026 on 2023-25) and scored on its
fold; LightGBM on SN131's 44 features at the same rows is the comparison. Policy on Gold's empty days: at each decision
after the last exit take the side with the higher P if >= theta; stop at +Rs 1,000 for the day or -Rs 2,000; theta
from {0.5, 0.55, 0.6} chosen for each fold on the other two folds. Matched null: random decision and side, the same
number of trades. Final models (all development) write TEST predictions to _local for SN198 and are saved for SN196."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn161"))
import pe  # noqa: E402
import pml  # noqa: E402
import seq  # noqa: E402

pw = pe.pw
DEC = (45, 105, 165, 225, 285)
GOAL, STOP = 1000.0, 1000.0
THETAS = (0.5, 0.55, 0.6)
FOLDS = ("2024", "2025", "2026")
LOCAL = pe.LOCAL


def build():
    p = LOCAL / "sn191-data.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    rows = []
    for S in pw.sessions():
        f = seq.session_feats(S)
        for i in DEC:
            lab, net, jx = [], [], []
            for opt in ("CE", "PE"):
                r = pw.trade(S, i, opt, pw.atm(S, i), 1e9, target=GOAL, stop=-STOP, max_lots=1)
                lab.append(np.nan if r is None else float(r["reason"] == "target"))
                net.append(np.nan if r is None else r["net"])
                jx.append(-1 if r is None else r["j"])
            rows.append((S.day, i, seq.window(f, i), lab, net, jx))
    data = {"day": np.array([r[0] for r in rows]), "i": np.array([r[1] for r in rows]), "X": np.stack([r[2] for r in rows]),
            "Y": np.array([r[3] for r in rows], dtype=np.float32), "net": np.array([r[4] for r in rows], dtype=np.float32),
            "j": np.array([r[5] for r in rows])}
    LOCAL.mkdir(exist_ok=True)
    p.write_bytes(pickle.dumps(data))
    return data


def policy(data, P, days_ok, theta, rng=None):
    out, counts = {}, {}
    by_day = {}
    for r in range(len(data["day"])):
        by_day.setdefault(data["day"][r], []).append(r)
    for d in sorted(days_ok):
        free, net, n = -1, 0.0, 0
        for r in by_day.get(d, []):
            if data["i"][r] <= free or net >= GOAL - 1e-6 or net <= -2 * STOP + 1e-6:
                continue
            p = P[r]
            if np.all(np.isnan(p)):
                continue
            if rng is None:
                a = int(np.nanargmax(p))
                if p[a] < theta:
                    continue
            else:
                a = int(rng.integers(0, 2))
            if np.isnan(data["net"][r, a]):
                continue
            net += float(data["net"][r, a])
            n += 1
            free = int(data["j"][r, a])
        if n:
            out[d], counts[d] = net, n
    return out, counts


def null_policy(data, counts, rng):
    """For each day the policy traded: random decisions (after the last exit) and random sides, as many trades."""
    by_day = {}
    for r in range(len(data["day"])):
        by_day.setdefault(data["day"][r], []).append(r)
    out = {}
    for d, k in counts.items():
        free, net, n = -1, 0.0, 0
        rows = by_day.get(d, [])
        while n < k and net < GOAL - 1e-6 and net > -2 * STOP + 1e-6:
            cand = [r for r in rows if data["i"][r] > free]
            if not cand:
                break
            r = cand[int(rng.integers(0, len(cand)))]
            a = int(rng.integers(0, 2))
            if np.isnan(data["net"][r, a]):
                free = int(data["i"][r])
                continue
            net += float(data["net"][r, a])
            n += 1
            free = int(data["j"][r, a])
        if n:
            out[d] = net
    return out


def save(name, obj):
    LOCAL.mkdir(exist_ok=True)
    (LOCAL / name).write_bytes(pickle.dumps(obj))


def lgbm_rows(data):
    d131 = pickle.loads(pml.sn166.SN131_DATA.read_bytes())
    key = {(d, int(m)): k for k, (d, m) in enumerate(zip(d131["day"], d131["minute"]))}
    idx = np.array([key[(d, int(i))] for d, i in zip(data["day"], data["i"])])
    return d131["X"][idx]


if __name__ == "__main__":
    out_path = HERE / "results-sn191.json"
    if out_path.exists():
        raise SystemExit("SN191 is scored once")
    data = build()
    XL = lgbm_rows(data)
    year = np.array([d[:4] for d in data["day"]])
    dev = data["day"] < pw.TEST_FROM
    empty = {S.day for S in pe.empty_sessions()}
    P_lstm = np.full(data["Y"].shape, np.nan, dtype=np.float32)
    P_lgbm = np.full(data["Y"].shape, np.nan, dtype=np.float32)
    for y in FOLDS:
        tr, te = dev & (year < y), dev & (year == y)
        st = seq.Standard(data["X"][tr])
        net = seq.train_lstm(st(data["X"][tr]), data["Y"][tr])
        P_lstm[te] = seq.predict(net, st(data["X"][te]))
        for a in range(2):
            ok = tr & ~np.isnan(data["Y"][:, a])
            m = pml.fit(XL[ok], data["Y"][ok, a] == 1, {"min_data_in_leaf": 50}, 200)
            P_lgbm[te, a] = m.predict(XL[te])
        print(f"SN191 fold {y}: trained", flush=True)
    res = {"rows": int(dev.sum()), "base_rate_dev": [round(float(np.nanmean(data["Y"][dev, a])), 4) for a in range(2)], "models": {}}
    for name, P in (("LSTM", P_lstm), ("LightGBM", P_lgbm)):
        per = {}
        for y in FOLDS:
            fd = {d for d in empty if d[:4] == y}
            per[y] = {str(t): policy(data, P, fd, t)[0] for t in THETAS}
        loyo, taken_all = {}, {}
        for y in FOLDS:
            best = max(THETAS, key=lambda t: sum(sum(per[o][str(t)].values()) for o in FOLDS if o != y))
            dn = per[y][str(best)]
            loyo[y] = {"theta": best, "net": round(sum(dn.values())), "trade_days": len(dn),
                       "goal_days": sum(v >= GOAL - 1e-6 for v in dn.values())}
            _dn, cnt = policy(data, P, {d for d in empty if d[:4] == y}, best)
            taken_all.update(cnt)
        rng = np.random.default_rng(191)
        nulls = [sum(null_policy(data, taken_all, rng).values()) for _ in range(300)]
        total = sum(v["net"] for v in loyo.values())
        acc = {}
        for a, side in enumerate(("CE", "PE")):
            m = dev & (year >= "2024") & ~np.isnan(data["Y"][:, a]) & ~np.isnan(P[:, a])
            from sklearn.metrics import roc_auc_score
            acc[side] = round(float(roc_auc_score(data["Y"][m, a], P[m, a])), 3)
        res["models"][name] = {"loyo": loyo, "total": total, "years_positive": sum(v["net"] > 0 for v in loyo.values()),
                               "null_mean": round(float(np.mean(nulls))), "null_p95": round(float(np.percentile(nulls, 95))),
                               "auc_oos": acc}
        res["models"][name]["dev_pass_partial"] = bool(total > 0 and res["models"][name]["years_positive"] >= 2
                                                       and total > res["models"][name]["null_p95"])
        print(f"SN191 {name}: {json.dumps(res['models'][name])}", flush=True)
    st = seq.Standard(data["X"][dev])
    net = seq.train_lstm(st(data["X"][dev]), data["Y"][dev])
    te = ~dev
    P_test = np.full(data["Y"].shape, np.nan, dtype=np.float32)
    P_test[te] = seq.predict(net, st(data["X"][te]))
    import torch
    torch.save(net.state_dict(), LOCAL / "sn191-lstm.pt")
    th = max(THETAS, key=lambda t: sum(policy(data, P_lstm, {d for d in empty if d[:4] in FOLDS}, t)[0].values()))
    res["final_theta_lstm"] = th
    save("sn191_test.pkl", {"P_test": P_test, "P_lstm_oos": P_lstm, "P_lgbm_oos": P_lgbm, "theta": th, "mu": st.mu, "sd": st.sd})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
