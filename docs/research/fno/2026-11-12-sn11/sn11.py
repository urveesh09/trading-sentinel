"""SN11 - the owner's "exit when it rises, before it dips again" on N11's entries, Rs 15,000 wallet (research only).
Once the option is up `act`, exit at the first sign the rise is over: RED = the first 1-minute close below the previous
close; DD = the bid falls `dd` below its best close; EMA = the index's 1-minute close crosses back over its 5-minute EMA
against the trade. Otherwise N11's own exit. Stops / day limit as the benchmark. Leave one year out."""
import itertools, json, math, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
from sn03_run import loyo
M = B.M

def play(S, sigs, v, wallet=15000.0, loss=3000.0, stress=205.0):
    realized, free = 0.0, 0
    ema5 = S.F["ema5"]; c = S.F["c"]
    for sg in sorted(sigs, key=lambda x: x["i"]):
        i = sg["i"]
        if i < free or i >= M.EXIT_MIN or sg["expiry"] != S.s["expiry"]:
            continue
        strike, opt = sg["strike"], sg["opt"]
        rec = S.option(strike, opt)
        if rec is None or not rec[6][i]:
            continue
        ask = M.ask_of(float(rec[0][3][i]))
        if ask * M.LOT > wallet:
            strike += M.STEP if opt == "CE" else -M.STEP
            rec = S.option(strike, opt)
            if rec is None or not rec[6][i]:
                continue
            ask = M.ask_of(float(rec[0][3][i]))
            if ask * M.LOT > wallet:
                continue
        a, bo, bh, bl, bc, bm, tr = rec
        qty, d = M.LOT, (1 if opt == "CE" else -1)
        room = loss + realized
        stop = M._ceil_tick(ask - (room - M.charges(ask, ask, qty) - stress) / qty)
        j_exit = min(max(sg["j"], i + 1), M.EXIT_MIN)
        armed, peak, prev, px, j = False, ask, ask, None, i
        for j in range(i + 1, M.EXIT_MIN + 1):
            if tr[j]:
                if bl[j] <= stop:
                    px = min(stop, bo[j]); break
                if bc[j] >= ask * (1 + v["act"]):
                    armed = True
                if armed:
                    m = v["mode"]
                    if (m == "RED" and bc[j] < prev) or (m == "DD" and bc[j] <= peak * (1 - v["dd"])) or \
                       (m == "EMA" and (c[j] - ema5[j]) * d < 0):
                        px = bc[j]; break
                peak, prev = max(peak, bc[j]), bc[j]
            if j >= j_exit:
                px = bc[j] if tr[j] else bm[j]; break
        px = float(px)
        realized += (px - ask) * qty - M.charges(ask, px, qty) - stress
        free = j + 1
        if loss + realized < loss * 0.05:
            break
    return realized

GRID = {"benchmark": None}
for act in (0.05, 0.10, 0.20, 0.30, 0.50):
    GRID[f"RED after +{int(act*100)}%"] = {"mode": "RED", "act": act}
    GRID[f"EMA after +{int(act*100)}%"] = {"mode": "EMA", "act": act}
    for dd in (0.03, 0.05, 0.10):
        GRID[f"DD {int(dd*100)}% after +{int(act*100)}%"] = {"mode": "DD", "act": act, "dd": dd}

if __name__ == "__main__":
    table = {}
    for y in B.YEARS:
        Y = B.Year(y); n11 = Y.sigs("N11")
        for name, v in GRID.items():
            nets = [B.play_day(S, n11.get(S.day, []), {}, 15000.0, 3000.0)["net"] if v is None else play(S, n11.get(S.day, []), v)
                    for S in Y.ordered()]
            table.setdefault(name, {})[y] = {"net": round(sum(nets)), "green": sum(x > 0 for x in nets), "red": sum(x < 0 for x in nets),
                                             "none": sum(x == 0 for x in nets), "refilled": round(sum(-x for x in nets if x < 0))}
    top = sorted(table.items(), key=lambda kv: -sum(x["net"] for x in kv[1].values()))[:8]
    for n, per in top:
        print(f"{n:22s}", [per[y]["net"] for y in B.YEARS], sum(per[y]["net"] for y in B.YEARS), "won/lost", sum(per[y]["green"] for y in B.YEARS), sum(per[y]["red"] for y in B.YEARS))
    worst = sorted(table.items(), key=lambda kv: sum(x["net"] for x in kv[1].values()))[:2]
    for n, per in worst:
        print("worst", n, sum(per[y]["net"] for y in B.YEARS), "won/lost", sum(per[y]["green"] for y in B.YEARS), sum(per[y]["red"] for y in B.YEARS))
    L = loyo(table, "profit")
    print("LOYO", {y: (L[y]["pick"], L[y]["net"]) for y in B.YEARS}, "sum", L["sum"])
    (HERE / "results.json").write_text(json.dumps({"table": table, "loyo": L}, indent=1), encoding="utf-8")
