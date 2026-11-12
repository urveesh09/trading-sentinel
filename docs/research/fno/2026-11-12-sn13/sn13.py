"""SN13 - sizing and day-limit refinements on N11 entries (research only). Wallet Rs 30,000 (2 lots possible) unless noted.
Second lot: always / high-volatility days (yesterday's ATR% >= its median of the prior sessions, >= 60 needed: N11's
rule) / TPB trades only / after a green day / never. Day loss limits 10-30% at Rs 15,000. Leave one year out."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
from sn03_run import loyo
D = B.D

def vol_days():
    seen = {}
    for y in B.YEARS:
        con = sqlite3.connect(f"file:{(D.DATASETS[y] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
        for st, o, h, l, c in con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' ORDER BY datetime"):
            d = st[:10]
            b = seen.setdefault(d, [h, l, c]); b[0], b[1], b[2] = max(b[0], h), min(b[1], l), c
        con.close()
    days = sorted(seen); atr, out, hist = None, {}, []
    for k in range(1, len(days)):
        h, l, c = seen[days[k]]; pc = seen[days[k - 1]][2]
        tr = max(h - l, abs(h - pc), abs(l - pc)) / pc
        atr = tr if atr is None else atr + (tr - atr) / 14
        if k + 1 < len(days):
            if len(hist) >= 60:
                out[days[k + 1]] = atr >= float(np.median(hist[-250:]))
            hist.append(atr)
    return out

if __name__ == "__main__":
    vol = vol_days()
    years = {y: B.Year(y) for y in B.YEARS}
    table = {}
    def run(name, W, rule, loss_share=0.20):
        for y in B.YEARS:
            Y = years[y]; n11 = Y.sigs("N11"); nets = []; prev = 0.0
            for S in Y.ordered():
                sigs = n11.get(S.day, [])
                if rule == "never": lots = 1
                elif rule == "always": lots = 2
                elif rule == "vol": lots = 2 if vol.get(S.day) else 1
                elif rule == "after_green": lots = 2 if prev > 0 else 1
                elif rule == "tpb":
                    lots = None
                if rule == "tpb":
                    x = 0.0
                    for part, l in (([s for s in sigs if s["expert"] == "TPB"], 2), ([s for s in sigs if s["expert"] != "TPB"], 1)):
                        pass
                    x = B.play_day(S, sigs, {"lots": 2 if any(s["expert"] == "TPB" for s in sigs) else 1}, W, loss_share * W)["net"]
                else:
                    x = B.play_day(S, sigs, {"lots": lots}, W, loss_share * W)["net"]
                nets.append(x)
                if sigs: prev = x
            table.setdefault(name, {})[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets),
                                             "none": sum(v == 0 for v in nets), "refilled": round(sum(-v for v in nets if v < 0)), "worst": round(min(nets))}
    for rule in ("never", "always", "vol", "tpb", "after_green"):
        run(f"30k second lot: {rule}", 30000.0, rule)
    for ls in (0.10, 0.20, 0.30):
        run(f"15k day limit {int(ls*100)}%", 15000.0, "never", ls)
    for n, per in table.items():
        print(f"{n:30s}", [per[y]["net"] for y in B.YEARS], sum(per[y]["net"] for y in B.YEARS), "won/lost", sum(per[y]["green"] for y in B.YEARS),
              sum(per[y]["red"] for y in B.YEARS), "refill", sum(per[y]["refilled"] for y in B.YEARS), "worst", min(per[y]["worst"] for y in B.YEARS))
    for grp in ("30k", "15k"):
        L = loyo({k: v for k, v in table.items() if k.startswith(grp)}, "profit")
        print("LOYO", grp, {y: (L[y]["pick"], L[y]["net"]) for y in B.YEARS}, "sum", L["sum"]["net"])
    (HERE / "results.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
