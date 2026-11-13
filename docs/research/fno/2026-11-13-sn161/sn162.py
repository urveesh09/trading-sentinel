"""SN162 - seen vs kept (PLAN.md). Development sessions. At 09:20 buy the ATM CE, the ATM PE (1 lot each, and max
lots at Rs 15k) and a random side; hold to 15:10 with no exit. For each: the day's best net (peak, from the bid high
of every printed minute) and the 15:10 net. Shares of days a position touched +Rs 1,500 and of days it kept it; the
same for the better side in hindsight (what a human remembers) and for a 30% give-back exit after a +Rs 1,500 touch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

I920 = 5
WAGE = 1500.0


def giveback_exit(S, i, opt, strike, wallet, max_lots):
    """Hold; once the net touches +WAGE, sell when it falls to 70% of its best (at the bid close)."""
    rec = S.option(strike, opt)
    if rec is None or not rec[6][i]:
        return None
    ask = pw.M.ask_of(float(rec[0][3][i]))
    n = pw.lots_for(ask, wallet, max_lots)
    if n < 1:
        return None
    qty = n * pw.LOT
    best, armed, v = -1e18, False, None
    for j in range(i + 1, pw.FLAT + 1):
        b = float(rec[4][j]) if rec[6][j] else float(rec[5][j])
        if b != b:
            continue
        v = pw.net_at(ask, b, qty, n, pw.STRESS)
        best = max(best, v)
        armed = armed or best >= WAGE
        if armed and v <= 0.7 * best:
            return v
    return v


if __name__ == "__main__":
    out_path = HERE / "results-sn162.json"
    if out_path.exists():
        raise SystemExit("SN162 is scored once")
    res = {}
    for label, wallet, max_lots in (("1 lot", 10 ** 9, 1), ("max lots at Rs 15k", 15000.0, None)):
        rows = []
        for S in pw.dev_sessions():
            K = pw.atm(S, I920)
            got = {}
            for opt in ("CE", "PE"):
                r = pw.trade(S, I920, opt, K, wallet, end=pw.FLAT, max_lots=max_lots, record_path=True)
                got[opt] = r
            if got["CE"] is None or got["PE"] is None:
                continue
            rnd = got["CE"] if np.random.default_rng(pw.seed_of(S.day)).random() < 0.5 else got["PE"]
            better = max(got.values(), key=lambda r: r["peak"])
            gb = giveback_exit(S, I920, "CE" if rnd is got["CE"] else "PE", K, wallet, max_lots)
            rows.append({"day": S.day, "ce_peak": got["CE"]["peak"], "ce_close": got["CE"]["net"], "pe_peak": got["PE"]["peak"],
                         "pe_close": got["PE"]["net"], "rnd_peak": rnd["peak"], "rnd_close": rnd["net"],
                         "best_peak": better["peak"], "best_close": better["net"], "rnd_giveback": gb})
        n = len(rows)

        def share(f):
            return round(sum(1 for r in rows if f(r)) / n, 4)
        out = {"sessions": n,
               "random side: touched +1,500": share(lambda r: r["rnd_peak"] >= WAGE),
               "random side: kept +1,500 at 15:10": share(lambda r: r["rnd_close"] >= WAGE),
               "random side: total at 15:10": round(sum(r["rnd_close"] for r in rows)),
               "random side: 30% give-back exit total": round(sum(r["rnd_giveback"] or 0 for r in rows)),
               "random side: give-back exit wage days": share(lambda r: (r["rnd_giveback"] or 0) >= WAGE),
               "better side in hindsight: touched +1,500": share(lambda r: r["best_peak"] >= WAGE),
               "better side in hindsight: mean peak": round(float(np.mean([r["best_peak"] for r in rows]))),
               "either side touched +1,500": share(lambda r: max(r["ce_peak"], r["pe_peak"]) >= WAGE),
               "both sides touched +1,500": share(lambda r: min(r["ce_peak"], r["pe_peak"]) >= WAGE),
               "mean peak random side": round(float(np.mean([r["rnd_peak"] for r in rows]))),
               "mean 15:10 random side": round(float(np.mean([r["rnd_close"] for r in rows])))}
        by_year = {}
        for y in pw.DEV_YEARS:
            ry = [r for r in rows if r["day"][:4] == y]
            if ry:
                by_year[y] = {"touched": round(sum(r["rnd_peak"] >= WAGE for r in ry) / len(ry), 3),
                              "kept": round(sum(r["rnd_close"] >= WAGE for r in ry) / len(ry), 3),
                              "net_15_10": round(sum(r["rnd_close"] for r in ry))}
        out["by_year (random side)"] = by_year
        res[label] = out
        print(f"=== SN162 {label}: " + json.dumps(out), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
