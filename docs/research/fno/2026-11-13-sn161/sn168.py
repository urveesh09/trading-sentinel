"""SN168 - meta-labelled signals (PLAN.md). Primary signals (causal, minute closes): RB15 (first break of the
first 15 minutes' range, each side once), VWAPX (index crosses VWAP with the 5-minute EMA9 slope on the same side, at
most one per 15 minutes), IMP (a 1-minute move >= 2 sigma of the last 30 one-minute moves, fresh: the partner's
impulse) and EMAX (EMA9 crosses EMA21). Each event buys the ATM option on its side (max lots at Rs 15k) with SN166's
+/- Rs 1,500 barriers. A LightGBM gate (SN167's features + signal type + side; min_data_in_leaf 50, 200 rounds) learns
which events to take; walk-forward inside development; theta by the development out-of-sample net. Against: every
event taken (no gate), a random gate with the same take rate, and the matched random-minute null. Final gate writes
TEST predictions to _local for SN181."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pml  # noqa: E402
import pw  # noqa: E402
import sn166  # noqa: E402

TYPES = ("RB15", "VWAPX", "IMP", "EMAX")
GATE = {"min_data_in_leaf": 50}
GATE_ROUNDS = 200


def signals(S):
    F = S.F
    c, h, l, vw, e9, e21 = F["c"], F["h"], F["l"], F["vwap"], F["ema9"], F["ema21"]
    ev, hi, lo = [], float(np.max(h[:15])), float(np.min(l[:15]))
    up = dn = False
    last_v = -99
    for i in range(sn166.I0 + 1, sn166.I1 + 1):
        if not up and c[i] > hi and c[i - 1] <= hi:
            ev.append((i, 1, "RB15"))
            up = True
        if not dn and c[i] < lo and c[i - 1] >= lo:
            ev.append((i, -1, "RB15"))
            dn = True
        s0, s1 = np.sign(c[i - 1] - vw[i - 1]), np.sign(c[i] - vw[i])
        if s1 != s0 and s1 != 0 and i - last_v >= 15 and np.sign(e9[i] - e9[i - 5]) == s1:
            ev.append((i, int(s1), "VWAPX"))
            last_v = i
        if i >= 32:
            sd = float(np.std(np.diff(c[i - 30: i + 1])[:-1]))
            sdp = float(np.std(np.diff(c[i - 31: i])[:-1]))
            m, mp = c[i] - c[i - 1], c[i - 1] - c[i - 2]
            if sd > 0 and abs(m) >= 2 * sd and not (sdp > 0 and abs(mp) >= 2 * sdp):
                ev.append((i, int(np.sign(m)), "IMP"))
        x0, x1 = np.sign(e9[i - 1] - e21[i - 1]), np.sign(e9[i] - e21[i])
        if x1 != x0 and x1 != 0:
            ev.append((i, int(x1), "EMAX"))
    return sorted(ev)


def event_table(bar):
    pos = {d: s for s, d in enumerate(bar["days"])}
    rows = []
    for S in pw.sessions():
        s = pos[S.day]
        for i, d, t in signals(S):
            rows.append((s, i - sn166.I0, 0 if d > 0 else 1, TYPES.index(t), d))
    return np.array(rows, dtype=np.int32)


def gated_policy(E, P, bar, theta, scored, max_trades=2):
    """Events in time order per day; take when flat and P >= theta; stop after a wage, a 15:10 exit or max_trades."""
    out, ntr, offered, counts = {}, 0, 0, {}
    by_s = {}
    for r in range(len(E)):
        by_s.setdefault(int(E[r, 0]), []).append(r)
    for s in scored:
        free, trades, net = 0, 0, 0.0
        for r in by_s.get(s, []):
            k, a = int(E[r, 1]), int(E[r, 2])
            if k < free or trades >= max_trades or np.isnan(bar["net"][s, a, k]) or np.isnan(P[r]):
                continue
            offered += 1
            if P[r] < theta:
                continue
            net += float(bar["net"][s, a, k])
            trades += 1
            j = int(bar["j"][s, a, k])
            if bar["label"][s, a, k] == 1 or j >= pw.FLAT:
                break
            free = j + 1 - sn166.I0
        if trades:
            out[bar["days"][s]] = net
            counts[bar["days"][s]] = trades
            ntr += trades
    return out, ntr, offered, counts


if __name__ == "__main__":
    out_path = HERE / "results-sn168.json"
    if out_path.exists():
        raise SystemExit("SN168 is scored once")
    d131, bar, s_idx, k_idx, base, names = pml.load()
    n_sess = len(bar["days"])
    rowgrid = np.full((n_sess, pml.NK), -1, dtype=np.int64)
    rowgrid[s_idx, k_idx] = np.arange(len(s_idx))
    E = event_table(bar)
    r = rowgrid[E[:, 0], E[:, 1]]
    ask = bar["ask"][E[:, 0], E[:, 2], E[:, 1]]
    lots = bar["lots"][E[:, 0], E[:, 2], E[:, 1]].astype(np.float32)
    onehot = np.eye(len(TYPES), dtype=np.float32)[E[:, 3]]
    Xe = np.hstack([base[r], ask[:, None], lots[:, None], onehot, E[:, 4:5].astype(np.float32)]).astype(np.float32)
    lab = bar["label"][E[:, 0], E[:, 2], E[:, 1]]
    ok = ~np.isnan(bar["net"][E[:, 0], E[:, 2], E[:, 1]])
    y = lab == 1
    edays = np.array([bar["days"][s] for s in E[:, 0]])
    oos = pml.walk_forward(Xe, y, ok, edays, GATE, GATE_ROUNDS)
    tp, _m = pml.final_test_pred(Xe, y, ok, edays, GATE, GATE_ROUNDS)
    dev_scored = [s for s, d in enumerate(bar["days"]) if "2024-01-01" <= d < pw.TEST_FROM]
    cal = [bar["days"][s] for s in dev_scored]
    dev_ev = np.isin(E[:, 0], dev_scored) & ok
    res = {"events_dev": int(dev_ev.sum()), "by_type_dev": {}, "thetas": {}}
    for t, name in enumerate(TYPES):
        m = dev_ev & (E[:, 3] == t)
        res["by_type_dev"][name] = {"events": int(m.sum()), "target_first": round(float(y[m].mean()), 4),
                                    "mean_net": round(float(bar["net"][E[m, 0], E[m, 2], E[m, 1]].mean()), 1)}
    ungated, n_un, _o, _c = gated_policy(E, np.ones(len(E), dtype=np.float32), bar, 0.0, dev_scored)
    res["ungated"] = {**pml.summary(ungated, cal), "trades": n_un}
    for th in pml.THETAS:
        dn, ntr, offered, _c = gated_policy(E, oos, bar, th, dev_scored)
        res["thetas"][str(th)] = {**pml.summary(dn, cal), "trades": ntr, "take_rate": round(ntr / max(1, offered), 3)}
        print(f"SN168 theta {th}: {json.dumps(res['thetas'][str(th)])}", flush=True)
    best = max(pml.THETAS, key=lambda t: res["thetas"][str(t)]["net"])
    rate = res["thetas"][str(best)]["take_rate"]
    rng = np.random.default_rng(168)
    rnd = []
    for _ in range(200):
        Pr = np.where(rng.random(len(E)) < rate, 1.0, 0.0).astype(np.float32)
        rnd.append(gated_policy(E, Pr, bar, 0.5, dev_scored)[0])
    res["random_gate"] = pml.null_summary(rnd, cal)
    _dn, _n, _o, taken = gated_policy(E, oos, bar, best, dev_scored)
    res["null_random_minutes"] = pml.null_summary(pml.matched_null(bar, taken), cal)
    ch = res["thetas"][str(best)]
    res["chosen_theta"] = best
    res["dev_pass_ml_analog"] = bool(ch["net"] > 0 and sum(v > 0 for v in ch["by_year"].values()) >= 2
                                     and ch["net"] > res["random_gate"]["net_p95"] and ch["net"] > res["null_random_minutes"]["net_p95"])
    print(f"SN168 ungated {json.dumps(res['ungated'])}\nSN168 chosen {best}: {json.dumps(ch)} | random gate "
          f"{json.dumps(res['random_gate'])} | null {json.dumps(res['null_random_minutes'])} | dev pass {res['dev_pass_ml_analog']}",
          flush=True)
    pml.save("sn168_test.pkl", {"E": E, "P_test": tp, "theta": best, "days": bar["days"]})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
