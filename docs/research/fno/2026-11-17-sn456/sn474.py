"""SN474 (own): Gold's exit clock against liquidity (PLAN.md section 3, frozen at 83e1b444; details fixed here before any number).
Research only; Gold's files are untouched (module constants patched for a run and restored).

(a) Archive depth: the 42 sealed archive days (qa), non-expiry days only; the front weekly's ATM (from the front future's ltp at
    that minute) and 1-ITM CE / PE at 15:00 / 15:05 / 15:10 / 15:15 / 15:20 (indexes 345 / 350 / 355 / 360 / 365): the share
    of snapshots that are usable with a 5-level bid holding >= 65 and >= 390 units (one and six lots), the median 5-level bid
    units and the median best-level spread (absent or unusable snapshots count as not holding).
(b) Gold's exit clock in its replay (DEPLOYED, gold.Y22 and gold.Y2326, Rs 205 and 400). Gold's time exit is N11's planned exit
    j_n11 = min(max(stream j, i + 1), M.EXIT_MIN) with M.EXIT_MIN = 360, and the extension's end ext_end = 355 (stream time exits
    sit at 355 = 15:10):
      E345     M.EXIT_MIN = 345, ext_end = 345 (every exit by 15:00; signals at or after 345 are skipped, as the lab does)
      E350     M.EXIT_MIN = 350, ext_end = 350
      DEPLOYED M.EXIT_MIN = 360, ext_end = 355 (parity: 2023-26 at Rs 205 = 8,50,882 / 883)
      EXT360   ext_end = 360 (the extension may run to 15:15; N11's own 15:10 time exits unchanged)
    Net, trades, months positive, worst day per arm, period and stress.
An earlier clock is worth proposing only if it costs < 2% of DEPLOYED's net in both periods (at Rs 205) AND its 390-unit
full-depth share is >= 10 points above 15:10's; otherwise 15:10 stays.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn441"))
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import sn441  # noqa: E402
import gold  # noqa: E402

qa, sn428 = sn441.qa, sn441.sn428
OUT = HERE / "results-sn474.json"
CLK = {"15:00": 345, "15:05": 350, "15:10": 355, "15:15": 360, "15:20": 365}
ARMS = {"E345": (345, 345), "E350": (350, 350), "DEPLOYED": (360, 355), "EXT360": (360, 360)}


def depth():
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    acc = {c: {"n": 0, "u65": 0, "u390": 0, "units": [], "spread": []} for c in CLK}
    used = 0
    for d in days:
        q = qa.load(d)
        cons = sn428.contracts(q, d)
        exps = sorted({k[1] for k in cons})
        if not exps or exps[0] == d:
            continue
        used += 1
        front = exps[0]
        fut = qa.front_fut(q, "NIFTY")
        for c, m in CLK.items():
            F = fut["ltp"][m] if fut is not None and m < len(fut["ltp"]) else np.nan
            if np.isnan(F):
                continue
            atm = int(round(F / 50.0) * 50)
            for side in ("CE", "PE"):
                for k in (atm, atm + (-50 if side == "CE" else 50)):
                    rec = q["opt"].get(("NIFTY", front, k, side))
                    acc[c]["n"] += 1
                    if rec is None or not rec["usable"][m]:
                        continue
                    u = float(np.nansum(rec["bidq"][:, m]))
                    acc[c]["units"].append(u)
                    acc[c]["u65"] += u >= 65
                    acc[c]["u390"] += u >= 390
                    if not np.isnan(rec["bid"][m]) and not np.isnan(rec["ask"][m]):
                        acc[c]["spread"].append(float(rec["ask"][m] - rec["bid"][m]))
    out = {"days": used}
    for c, a in acc.items():
        out[c] = {"contracts": a["n"], "share_65": round(a["u65"] / max(1, a["n"]), 3), "share_390": round(a["u390"] / max(1, a["n"]), 3),
                  "median_bid_units": float(np.median(a["units"])) if a["units"] else None,
                  "median_spread": round(float(np.median(a["spread"])), 2) if a["spread"] else None}
    return out


def replay():
    M = gold.L.M
    old = M.EXIT_MIN
    out = {}
    try:
        for arm, (em, ee) in ARMS.items():
            M.EXIT_MIN = em
            for pname, years in (("2022", gold.Y22), ("2023-26", gold.Y2326)):
                for st in (205.0, 400.0):
                    days, log, _ = gold.run(years, gold.DEPLOYED, st, ext_end=ee)
                    sm = gold.summary(days, log)
                    if arm == "DEPLOYED" and pname == "2023-26" and st == 205.0:
                        assert sm["net"] in (850882, 850883), sm["net"]
                    out[f"{arm} {pname} @{int(st)}"] = {k: sm[k] for k in ("net", "trades", "months_positive", "months", "worst_day", "per_session")}
                    print(arm, pname, st, out[f"{arm} {pname} @{int(st)}"], flush=True)
    finally:
        M.EXIT_MIN = old
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN474 is scored once")
    res = {"depth": depth()}
    print(json.dumps(res["depth"], indent=1), flush=True)
    res["replay"] = replay()
    dep = {p: res["replay"][f"DEPLOYED {p} @205"]["net"] for p in ("2022", "2023-26")}
    prop = {}
    for arm, clock in (("E345", "15:00"), ("E350", "15:05")):
        cost_ok = all(dep[p] - res["replay"][f"{arm} {p} @205"]["net"] < 0.02 * abs(dep[p]) for p in dep)
        depth_ok = res["depth"][clock]["share_390"] - res["depth"]["15:10"]["share_390"] >= 0.10
        prop[arm] = {"cost_ok": bool(cost_ok), "depth_ok": bool(depth_ok), "propose": bool(cost_ok and depth_ok)}
    res["decision"] = prop
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(prop, indent=1))


if __name__ == "__main__":
    main()
