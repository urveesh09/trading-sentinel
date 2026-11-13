"""SN166 - the triple-barrier dataset (PLAN.md). For every session (all 742; TEST rows are built but only SN181 reads
their labels) and every minute 09:30-14:45 (the SN131 feature rows), four actions bought at the ask with as many lots
as Rs 15k buys: ATM CE, ATM PE, 2-OTM CE, 2-OTM PE. Which comes first: +Rs 1,500 net (limit on the bid high), -Rs 1,500
net (stop on the bid low; ties to the stop) or 15:10; with the net, exit minute, lots and ask (pw.trade, house fills).
Cached in _local/barrier.pkl, aligned to SN131's dataset rows (day, minute). The printed analysis uses DEVELOPMENT rows
only: base rates by action, minute, weekday, gap and morning volatility."""
from __future__ import annotations

import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

LOCAL = HERE / "_local"
ACTIONS = (("ATM CE", "CE", 0), ("ATM PE", "PE", 0), ("OTM2 CE", "CE", 2), ("OTM2 PE", "PE", 2))
I0, I1 = 15, 330
WALLET, WAGE, STOP = 15000.0, 1500.0, 1500.0
SN131_DATA = HERE.parent / "2026-11-13-sn131" / "_local" / "dataset.pkl"


def _year(year):
    import pw as _pw
    C = _pw.C
    out = []
    for S in C.years()[year].ordered():
        n = I1 - I0 + 1
        lab = np.zeros((len(ACTIONS), n), dtype=np.int8)
        net = np.full((len(ACTIONS), n), np.nan, dtype=np.float32)
        jx = np.zeros((len(ACTIONS), n), dtype=np.int16)
        lots = np.zeros((len(ACTIONS), n), dtype=np.int8)
        ask = np.full((len(ACTIONS), n), np.nan, dtype=np.float32)
        for a, (_name, opt, off) in enumerate(ACTIONS):
            d = 1 if opt == "CE" else -1
            for k, i in enumerate(range(I0, I1 + 1)):
                r = _pw.trade(S, i, opt, _pw.atm(S, i) + d * off * _pw.STEP, WALLET, target=WAGE, stop=-STOP)
                if r is None:
                    continue
                lab[a, k] = 1 if r["reason"] == "target" else (-1 if r["reason"] == "stop" else 0)
                net[a, k], jx[a, k], lots[a, k], ask[a, k] = r["net"], r["j"], r["lots"], r["ask"]
        out.append((S.day, lab, net, jx, lots, ask))
    return out


def build():
    p = LOCAL / "barrier.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    LOCAL.mkdir(exist_ok=True)
    with Pool(4) as pool:
        parts = pool.map(_year, list(pw.C.YEARS))
    sess = sorted((x for part in parts for x in part), key=lambda t: t[0])
    data = {"days": [t[0] for t in sess], "label": np.stack([t[1] for t in sess]), "net": np.stack([t[2] for t in sess]),
            "j": np.stack([t[3] for t in sess]), "lots": np.stack([t[4] for t in sess]), "ask": np.stack([t[5] for t in sess]),
            "actions": [a[0] for a in ACTIONS], "minutes": list(range(I0, I1 + 1))}
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(data))
    tmp.replace(p)
    return data


def aligned():
    """(SN131 dataset, barrier data) with a row index: SN131 row r <-> (session s, minute k)."""
    d131 = pickle.loads(SN131_DATA.read_bytes())
    bar = build()
    pos = {d: s for s, d in enumerate(bar["days"])}
    s_idx = np.array([pos[d] for d in d131["day"]])
    k_idx = d131["minute"].astype(int) - I0
    return d131, bar, s_idx, k_idx


if __name__ == "__main__":
    out_path = HERE / "results-sn166.json"
    if out_path.exists():
        raise SystemExit("SN166 is scored once")
    d131, bar, s_idx, k_idx = aligned()
    dev = np.array([not pw.is_test(d) for d in d131["day"]])
    X, F = d131["X"], list(d131["features"])
    res = {"rows_dev": int(dev.sum()), "sessions_dev": int(len(set(d131["day"][dev])))}
    for a, name in enumerate(bar["actions"]):
        lab = bar["label"][s_idx, a, k_idx]
        net = bar["net"][s_idx, a, k_idx]
        ok = dev & ~np.isnan(net)
        r = {"rows": int(ok.sum()), "target_first": round(float((lab[ok] == 1).mean()), 4),
             "stop_first": round(float((lab[ok] == -1).mean()), 4), "time": round(float((lab[ok] == 0).mean()), 4),
             "mean_net_if_always_taken": round(float(net[ok].mean()), 1),
             "mean_lots": round(float(bar["lots"][s_idx, a, k_idx][ok].mean()), 2)}
        buckets = {}
        mins = d131["minute"]
        for lo, hi, tag in ((15, 45, "09:30-10:00"), (45, 105, "10:00-11:00"), (105, 225, "11:00-13:00"), (225, 331, "13:00-14:45")):
            m = ok & (mins >= lo) & (mins < hi)
            buckets[tag] = {"target_first": round(float((lab[m] == 1).mean()), 4), "mean_net": round(float(net[m].mean()), 1)}
        r["by_minute"] = buckets
        wd = X[:, F.index("weekday")]
        r["by_weekday"] = {str(int(w)): round(float(net[ok & (wd == w)].mean()), 1) for w in range(5) if (ok & (wd == w)).any()}
        rt = X[:, F.index("r_today")]
        qs = np.nanquantile(rt[ok], [0.2, 0.4, 0.6, 0.8])
        r["by_r_today_quintile"] = [round(float(net[ok & (rt >= lo) & (rt < hi)].mean()), 1)
                                    for lo, hi in zip([-np.inf, *qs], [*qs, np.inf])]
        gap = np.abs(X[:, F.index("gap")])
        gq = np.nanquantile(gap[ok], [0.5, 0.8])
        r["by_abs_gap"] = {"small half": round(float(net[ok & (gap < gq[0])].mean()), 1),
                           "50-80%": round(float(net[ok & (gap >= gq[0]) & (gap < gq[1])].mean()), 1),
                           "top 20%": round(float(net[ok & (gap >= gq[1])].mean()), 1)}
        res[name] = r
        print(f"SN166 {name}: {json.dumps(r)}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
