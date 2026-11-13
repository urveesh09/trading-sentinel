"""SN103 - which expiry buys the move (PLAN.md): on the quote archive's sealed days, the ATM straddle of the nearest
and of the next weekly NIFTY expiry bought at the real asks at 10:00 and sold at the real bids at 15:10. Description;
nothing is selected. Expiry days of the nearest contract are skipped (the SN books never trade them)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402
import qa  # noqa: E402

C, M = pa.C, pa.M
STRESSES = (0.0, 100.0, 205.0)


def atm_pair(day_q, exp, i0):
    """(strike, minute) with the smallest |call mid - put mid| among strikes quoted two-sided at the first usable minute."""
    strikes = sorted({k[2] for k in day_q["opt"] if k[0] == "NIFTY" and k[1] == exp})
    for i in range(i0, i0 + 3):
        best = None
        for s in strikes:
            ce, pe = day_q["opt"].get(("NIFTY", exp, s, "CE")), day_q["opt"].get(("NIFTY", exp, s, "PE"))
            if ce is None or pe is None or not (ce["usable"][i] and pe["usable"][i]):
                continue
            if np.isnan(ce["ask"][i]) or np.isnan(pe["ask"][i]) or np.isnan(ce["bid"][i]) or np.isnan(pe["bid"][i]):
                continue
            gap = abs((ce["bid"][i] + ce["ask"][i]) / 2 - (pe["bid"][i] + pe["ask"][i]) / 2)
            if best is None or gap < best[0]:
                best = (gap, s)
        if best:
            return best[1], i
    return None


def straddle(day_q, exp, lot):
    got = atm_pair(day_q, exp, pa.I10)
    if got is None:
        return None
    s, i = got
    legs = [day_q["opt"][("NIFTY", exp, s, o)] for o in ("CE", "PE")]
    asks = [float(r["ask"][i]) for r in legs]
    outs = []
    for r in legs:
        j = qa.last_before(r, pa.FLAT, i + 1)
        if j is None:
            return None
        outs.append(float(r["bid"][j]))
    gross = sum((b - a) * lot for a, b in zip(asks, outs))
    fees = sum(M.charges(a, b, lot) for a, b in zip(asks, outs))
    return {"strike": s, "entry_min": i, "premium": sum(asks) * lot, "gross": gross, "fees": fees,
            **{f"net_{int(x)}": gross - fees - 2 * x for x in STRESSES},
            "spread_paid": sum((float(r["ask"][i]) - float(r["bid"][i])) for r in legs) * lot}


if __name__ == "__main__":
    out_path = HERE / "results-sn103.json"
    if out_path.exists():
        raise SystemExit("SN103 is scored once")
    adm = pa.admission()
    C.years()
    expiries = sorted(qa.manifest()["option_expiries"]["NIFTY"])
    rows = []
    for day in qa.days():
        if day in expiries:
            continue
        later = [e for e in expiries if e > day]
        if len(later) < 2:
            continue
        q = qa.load(day)
        lot = q["lot"]["NIFTY"]
        near, nxt = straddle(q, later[0], lot), straddle(q, later[1], lot)
        rows.append({"day": day, "near_expiry": later[0], "next_expiry": later[1], "lot": lot, "near": near, "next": nxt,
                     "sn95l_signal": pa.sn95l(adm, day) if day <= "2026-10-28" else None,
                     "dte_near": C.sessions_until(day, later[0]) if day <= "2026-10-28" else None})
    both = [r for r in rows if r["near"] and r["next"]]
    summ = {"days": len(rows), "both_priced": len(both)}
    for x in STRESSES:
        k = f"net_{int(x)}"
        summ[f"near total {k}"] = round(sum(r["near"][k] for r in both))
        summ[f"next total {k}"] = round(sum(r["next"][k] for r in both))
        summ[f"next minus near mean {k}"] = round(float(np.mean([r["next"][k] - r["near"][k] for r in both])))
        summ[f"next better share {k}"] = round(float(np.mean([r["next"][k] > r["near"][k] for r in both])), 3)
    summ["premium mean near / next"] = (round(float(np.mean([r["near"]["premium"] for r in both]))), round(float(np.mean([r["next"]["premium"] for r in both]))))
    summ["net per Rs 1,000 premium (205) near / next"] = (round(1000 * sum(r["near"]["net_205"] for r in both) / sum(r["near"]["premium"] for r in both), 1),
                                                         round(1000 * sum(r["next"]["net_205"] for r in both) / sum(r["next"]["premium"] for r in both), 1))
    summ["spread paid per straddle near / next"] = (round(float(np.mean([r["near"]["spread_paid"] for r in both]))), round(float(np.mean([r["next"]["spread_paid"] for r in both]))))
    summ["unseen Oct 29 - Nov 11 near / next (205)"] = (round(sum(r["near"]["net_205"] for r in both if r["day"] > "2026-10-28")),
                                                       round(sum(r["next"]["net_205"] for r in both if r["day"] > "2026-10-28")),
                                                       sum(1 for r in both if r["day"] > "2026-10-28"))
    sig = [r for r in both if r["sn95l_signal"]]
    summ["SN95-L signal days"] = {"n": len(sig), "near_205": round(sum(r["near"]["net_205"] for r in sig)), "next_205": round(sum(r["next"]["net_205"] for r in sig))}
    print(json.dumps(summ, indent=1), flush=True)
    for r in both:
        print(f"  {r['day']} near {r['near_expiry']} {round(r['near']['net_205']):>6} prem {round(r['near']['premium']):>6} | next {r['next_expiry']} "
              f"{round(r['next']['net_205']):>6} prem {round(r['next']['premium']):>6} | SN95-L {r['sn95l_signal']}")
    out_path.write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, default=float), encoding="utf-8")
