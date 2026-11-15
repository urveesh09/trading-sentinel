"""SN222 - engine parity and the four-sample board (PLAN.md).
Parity: with no hedge, wk3 = wk.trade for every naked variant of the grid's exits (settle, stop 1.0, pre, pre stop 1.0)
and wk3's gate = wk2.simulate(WK-S, gate -0.25), trade by trade, on DEV, TEST, N2122 and SENSEX.
Board: SN201-SN220's recipes on all four seen samples, with the PLAN's score (net / weekly expiries in the sample)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

wk = wk3.wk
wk2 = wk3.wk2
EXMAP = {("settle", None): "settle", ("settle", 1.0): "settle stop1", ("pre", None): "pre", ("pre", 1.0): "pre stop1"}
BOARD = {"WK-S (SN204)": ("STRANGLE 0.5", 3, "settle stop1", "none", "none"),
         "WK-G (SN217)": ("STRANGLE 0.5", 3, "gate stop1", "none", "none"),
         "pre base": ("STRANGLE 0.5", 3, "pre stop1", "none", "none"),
         "k1 ATM straddle": ("STRADDLE", 1, "settle", "none", "none")}
EXTRA = {"runner-up STRADDLE kF stop 0.5": ("wk", ("STRADDLE", "F", "settle", 0.5)),
         "WK-A IC 1.0/1.0 k1": ("wk", ("IC 1.0/1.0", 1, "settle", None)),
         "breach 0.5 + gate (SN218)": ("wk2", {"breach": 0.5, "gate": -0.25})}


def parity(name):
    s = wk3.sample(name)
    n = bad = 0
    worst = 0.0
    for v in wk.naked_variants():
        st, k, ex, stop = v
        en = EXMAP.get((ex, stop))
        if en is None:
            continue
        a = {t["expiry"]: t["net"] for t in wk.book(s.mk, s.data, s.weeks, v)}
        b = {r[1]: r[3] for r in grid.rows(name, (st, k, en, "none", "none"))}
        n += 1
        d = max((abs(a[e] - b[e]) for e in a if e in b), default=0.0)
        worst = max(worst, d)
        bad += int(set(a) != set(b) or d > 1e-6)
    a = {t["expiry"]: t["net"] for t in wk2.book2(s.mk, s.data, s.mins, s.weeks, wk2.WK_S, {"gate": -0.25})}
    b = {r[1]: r[3] for r in grid.rows(name, BOARD["WK-G (SN217)"])}
    dg = max((abs(a[e] - b[e]) for e in a if e in b), default=0.0)
    return {"naked_variants": n, "mismatches": bad, "max_abs_diff_rs": round(worst, 6),
            "gate_same_weeks": set(a) == set(b), "gate_max_abs_diff_rs": round(dg, 6)}


def board(name):
    s = wk3.sample(name)
    out = {}
    for lab, v in BOARD.items():
        out[lab] = grid.summary(grid.rows(name, v), s.W)
    for lab, (eng, spec) in EXTRA.items():
        if eng == "wk":
            tr = wk.book(s.mk, s.data, s.weeks, spec)
        else:
            tr = wk2.book2(s.mk, s.data, s.mins, s.weeks, wk2.WK_S, spec)
        rr = [{"entry": t["entry"], "expiry": t["expiry"], "exit_day": t["exit_day"], "net": t["net"],
               "wing_clamped": t.get("wing_clamped", 0)} for t in tr]
        out[lab] = wk3.summary(rr, s.W)
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn222.json"
    if out_path.exists():
        raise SystemExit("SN222 is run once")
    res = {"parity": {}, "board": {}}
    for name in wk3.SEEN:
        res["parity"][name] = parity(name)
        print("SN222 parity", name, json.dumps(res["parity"][name]), flush=True)
    for name in wk3.SEEN:
        res["board"][name] = board(name)
    labs = list(res["board"]["DEV"])
    res["min_score"] = {}
    for lab in labs:
        sc = {n: res["board"][n][lab]["per_week"] for n in wk3.SEEN}
        res["min_score"][lab] = {"scores": sc, "min": min(sc.values()), "positive_samples": sum(res["board"][n][lab]["net"] > 0 for n in wk3.SEEN),
                                 "total": sum(res["board"][n][lab]["net"] for n in wk3.SEEN)}
        print(f"SN222 {lab:32s}", " | ".join(f"{n} {res['board'][n][lab]['net']:>9} ({res['board'][n][lab]['trades']}w, "
                                             f"mo {res['board'][n][lab]['worst_month']})" for n in wk3.SEEN),
              f"| min/wk {res['min_score'][lab]['min']:>7} total {res['min_score'][lab]['total']:>9}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
