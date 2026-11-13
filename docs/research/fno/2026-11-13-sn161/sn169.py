"""SN169 - the learned exit (PLAN.md). Entries: three random entries a day (seeded minute 09:30-14:30 and side) and
the first SN168 primary event of each type and side a day (<= 8; all ~34 a day would not fit the shared machine),
each buying the ATM option with max lots at Rs 15k and the +/- Rs 1,500 barriers. At each
minute an entry is open (before a barrier ends it) a state is recorded: the index features of that minute (SN167's
base block), the trade's net now, its peak, the give-back from the peak, minutes held, minutes left, ask, lots, side.
Label: from this minute's close, does the trade's minute-close net reach +Rs 500 more before -Rs 500 (else: is the 15:10
net higher)? LightGBM walk-forward inside development; the exit sells at the minute's bid close when P < phi
(phi in {0.3, 0.4, 0.5}, chosen by development out-of-sample net); barriers stay. Against the barrier-only exit on the
same entries (paired), per year, and as a day book (each day's first random entry). Final model writes TEST
state predictions to _local for SN181."""
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
import sn168  # noqa: E402

PHIS = (0.3, 0.4, 0.5)
STEP_NET = 500.0
RANDOM_PER_DAY = 3


def walk_states(S, i, d, wallet=15000.0):
    """(entry dict, list of state tuples) for an ATM buy at minute i on side d with the wage barriers."""
    opt = "CE" if d > 0 else "PE"
    rec = S.option(pw.atm(S, i), opt)
    if rec is None or not rec[6][i]:
        return None
    ask = pw.M.ask_of(float(rec[0][3][i]))
    n = pw.lots_for(ask, wallet)
    if n < 1:
        return None
    qty = n * pw.LOT
    tp = pw.price_for_net(ask, qty, n, 1500.0, pw.STRESS, up=True)
    sp = pw.price_for_net(ask, qty, n, -1500.0, pw.STRESS, up=False)
    _a, bo, bh, bl, bc, bm, tr = rec
    close_net = np.full(pw.FLAT + 1, np.nan)
    for j in range(i + 1, pw.FLAT + 1):
        b = float(bc[j]) if tr[j] else float(bm[j])
        if b == b:
            close_net[j] = pw.net_at(ask, b, qty, n, pw.STRESS)
    exit_j, exit_net = pw.FLAT, None
    for j in range(i + 1, pw.FLAT + 1):
        if tr[j] and sp >= pw.TICK and bl[j] <= sp:
            exit_j, exit_net = j, pw.net_at(ask, min(sp, float(bo[j])), qty, n, pw.STRESS)
            break
        if tr[j] and bh[j] >= tp:
            exit_j, exit_net = j, pw.net_at(ask, tp, qty, n, pw.STRESS)
            break
    if exit_net is None:
        exit_net = close_net[pw.FLAT] if close_net[pw.FLAT] == close_net[pw.FLAT] else -pw.STRESS * n
    states, peak = [], -1e18
    for j in range(i + 1, exit_j):                    # minutes the trade is open after their barrier check
        v = close_net[j]
        if v != v:
            continue
        peak = max(peak, v)
        fut = close_net[j + 1:]
        fut = fut[~np.isnan(fut)]
        up = np.flatnonzero(fut >= v + STEP_NET)
        dn = np.flatnonzero(fut <= v - STEP_NET)
        if len(up) and (not len(dn) or up[0] < dn[0]):
            y = 1
        elif len(dn):
            y = 0
        else:
            y = int(len(fut) > 0 and fut[-1] > v)
        states.append((j, v, peak, j - i, y))
    return {"i": i, "d": d, "ask": ask, "lots": n, "exit_j": exit_j, "exit_net": exit_net}, states


if __name__ == "__main__":
    out_path = HERE / "results-sn169.json"
    if out_path.exists():
        raise SystemExit("SN169 is scored once")
    d131, bar, s_idx, k_idx, base, names = pml.load()
    n_sess = len(bar["days"])
    pos = {d: s for s, d in enumerate(bar["days"])}
    rowgrid = np.full((n_sess, pml.NK), -1, dtype=np.int64)
    rowgrid[s_idx, k_idx] = np.arange(len(s_idx))
    entries, X_rows, extra, Y, owner = [], [], [], [], []
    for S in pw.sessions():
        s = pos[S.day]
        rng = np.random.default_rng(pw.seed_of(S.day, 0, 169))
        cand = [(int(rng.integers(pw.I_MIN, pw.I_MAX + 1)), 1 if rng.random() < 0.5 else -1, "random", q)
                for q in range(RANDOM_PER_DAY)]
        seen = set()
        for i, d, t in sn168.signals(S):                  # the first event of each type and side a day (<= 8)
            if (t, d) not in seen:
                seen.add((t, d))
                cand.append((i, d, "signal", None))
        for i, d, kind, q in cand:
            got = walk_states(S, i, d)
            if got is None:
                continue
            e, st = got
            e.update({"s": s, "kind": kind, "q": q, "first_state": len(Y), "n_states": len(st)})
            entries.append(e)
            for j, v, peak, held, y in st:
                X_rows.append(rowgrid[s, min(j, sn166.I1) - sn166.I0])
                extra.append((v, peak, peak - v, held, pw.FLAT - j, e["ask"], e["lots"], d))
                Y.append(y)
                owner.append(len(entries) - 1)
    X_rows = np.array(X_rows)
    Xs = np.hstack([base[X_rows], np.array(extra, dtype=np.float32)]).astype(np.float32)
    Y = np.array(Y, dtype=bool)
    sdays = np.array([bar["days"][entries[o]["s"]] for o in owner])
    ok = np.ones(len(Y), dtype=bool)
    oos = pml.walk_forward(Xs, Y, ok, sdays)
    tp, _m = pml.final_test_pred(Xs, Y, ok, sdays)
    print(f"SN169 entries {len(entries)} states {len(Y)}", flush=True)

    def exit_net(e, P, phi):
        """Barrier-only result unless the learned exit fires first (sell at that minute's close net)."""
        if phi is None:
            return e["exit_net"]
        a, n = e["first_state"], e["n_states"]
        for t in range(a, a + n):
            if P[t] == P[t] and P[t] < phi:
                return float(extra[t][0])
        return e["exit_net"]
    dev = [e for e in entries if "2024-01-01" <= bar["days"][e["s"]] < pw.TEST_FROM]
    res = {"entries_dev": len(dev), "states_total": int(len(Y)), "phis": {}}
    for phi in (None, *PHIS):
        row = {}
        for kind in ("random", "signal"):
            xs = [(bar["days"][e["s"]], exit_net(e, oos, phi)) for e in dev if e["kind"] == kind]
            row[kind] = {"net": round(sum(v for _d, v in xs)), "per_trade": round(float(np.mean([v for _d, v in xs])), 1),
                         "wins": round(float(np.mean([v > 0 for _d, v in xs])), 4),
                         "by_year": {y: round(sum(v for d, v in xs if d[:4] == y)) for y in ("2024", "2025", "2026")}}
        day_book = {bar["days"][e["s"]]: exit_net(e, oos, phi) for e in dev if e["kind"] == "random" and e["q"] == 0}
        row["day book (first random entry)"] = pml.summary(day_book, sorted({bar["days"][e["s"]] for e in dev}))
        res["phis"]["barriers only" if phi is None else str(phi)] = row
        print(f"SN169 phi {phi}: {json.dumps(row)}", flush=True)
    best = max(PHIS, key=lambda p: res["phis"][str(p)]["random"]["net"] + res["phis"][str(p)]["signal"]["net"])
    base_row, ch = res["phis"]["barriers only"], res["phis"][str(best)]
    res["chosen_phi"] = best
    res["dev_improves_both"] = bool(ch["random"]["net"] > base_row["random"]["net"] and ch["signal"]["net"] > base_row["signal"]["net"])
    res["dev_profitable"] = bool(ch["random"]["net"] > 0 or ch["signal"]["net"] > 0)
    print(f"SN169 chosen phi {best}; improves both {res['dev_improves_both']}; profitable {res['dev_profitable']}", flush=True)
    pml.save("sn169_test.pkl", {"entries": entries, "P_test": tp, "extra_net": np.array([x[0] for x in extra]), "phi": best})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
