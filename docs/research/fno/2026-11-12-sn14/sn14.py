"""SN14 - combined candidates and the owner's wallet with growth stopped after step k, per year (descriptive, in-sample).
Lots: full = floor(W / 15,000); on a low-volatility day (SN13 rule) max(1, full // 2). Loss limit 20% of W.
A step: net profit since the last step >= W -> W x 1.5."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03"), str(HERE.parent / "2026-11-12-sn13")]
import sn03 as B
import sn13 as V

def ledger(years, vol, W0, cap, vol_rule=True, one_lot=False):
    W, steps, prog = float(W0), 0, 0.0
    per = {y: {"net": 0.0, "refilled": 0.0, "won": 0, "lost": 0, "none": 0} for y in B.YEARS}
    worst, step_days = 0.0, []
    for y in B.YEARS:
        Y = years[y]; n11 = Y.sigs("N11")
        for S in Y.ordered():
            full = 1 if one_lot else max(1, int(W // 15000))
            lots = full if (not vol_rule or vol.get(S.day)) else max(1, full // 2)
            x = B.play_day(S, n11.get(S.day, []), {"lots": lots}, W, 0.2 * W)["net"]
            p = per[y]; p["net"] += x; p["refilled"] += max(0.0, -x); p["won" if x > 0 else "lost" if x < 0 else "none"] += 1
            worst = min(worst, x); prog += x
            while prog >= W and steps < cap:
                prog -= W; W *= 1.5; steps += 1; step_days.append([S.day, round(W)])
    return {"per_year": {y: {k: round(v) for k, v in per[y].items()} for y in B.YEARS}, "steps": steps, "final_wallet": round(W),
            "worst_day": round(worst), "step_days": step_days, "total": round(sum(per[y]["net"] for y in B.YEARS)),
            "refilled": round(sum(per[y]["refilled"] for y in B.YEARS))}

if __name__ == "__main__":
    vol = V.vol_days()
    years = {y: B.Year(y) for y in B.YEARS}
    out = {}
    cases = [("A benchmark: Rs 15k, 1 lot, farm", 15000, 0, False, True),
             ("B Rs 20k, 1 lot, farm", 20000, 0, False, True),
             ("C Rs 30k, vol-sized, farm", 30000, 0, True, False)]
    cases += [(f"D start Rs 15k, vol-sized, grow, stop after step {k}", 15000, k, True, False) for k in range(0, 7)]
    cases += [(f"E start Rs 20k, vol-sized, grow, stop after step {k}", 20000, k, True, False) for k in (1, 2, 3, 4, 5)]
    for name, W0, cap, vr, one in cases:
        r = ledger(years, vol, W0, cap, vol_rule=vr, one_lot=one)
        out[name] = r
        py = r["per_year"]
        print(f"{name:50s}", " ".join(f"{py[y]['net']:>8}/{py[y]['refilled']:<7}" for y in B.YEARS),
              f"| {r['total']:>8} refill {r['refilled']:>8} won/lost/none {sum(py[y]['won'] for y in B.YEARS)}/{sum(py[y]['lost'] for y in B.YEARS)}/{sum(py[y]['none'] for y in B.YEARS)} worst {r['worst_day']} wallet {r['final_wallet']}", flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
