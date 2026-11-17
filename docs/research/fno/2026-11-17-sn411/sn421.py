"""SN421 (own): Gold's parameter map, one step at a time (PLAN.md section 2, frozen at e5cc95b7; details fixed here before
any number). Learning only; no Gold change follows from this slot.

Base = Gold v5 as deployed (C.V5, GOLD_30K). Each variant changes one thing:
  extension   extend off; ext_x 0.15 / 0.35 (base 0.25); ext_k 2 / 4 (base 3)
  scale-in    in_atr off / 0.5 / 1.5 (base 1.0); in_full off
  ITM choice  itm_if_fits off; itm_auto (15000, 17500) / (20000, 25000) (base (17500, 20000))
  day room    loss_share 0.15 / 0.25 (base 0.20)
  size rule   all (full lots every day) / single (one lot) (base vol: halved on low-volatility days)
  growth      g_trig 0.75 / 1.5 (base 1.0); growth cap 2 / 4 steps (base 3)
Paths 2022 (out of sample for Gold's rules) and 2023-26 (development), Rs 205 / 400. Labels: FRAGILE if the 2023-26 net at
Rs 205 moves > 20% from the base; CONSISTENT if 2022 moves in the same direction as 2023-26 (Rs 205).
Runs cached in _local/sn421-runs.json (slices).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold  # noqa: E402

OUT = HERE / "results-sn421.json"
CACHE = HERE / "_local" / "sn421-runs.json"
G = gold.GOLD_30K
VARIANTS = {
    "base": ({}, G), "extend off": ({"extend": False}, G), "ext_x 0.15": ({"ext_x": 0.15}, G), "ext_x 0.35": ({"ext_x": 0.35}, G),
    "ext_k 2": ({"ext_k": 2.0}, G), "ext_k 4": ({"ext_k": 4.0}, G), "scale-in off": ({"in_atr": None}, G), "in_atr 0.5": ({"in_atr": 0.5}, G),
    "in_atr 1.5": ({"in_atr": 1.5}, G), "in_full off": ({"in_full": False}, G), "itm_if_fits off": ({"itm_if_fits": False}, G),
    "itm_auto 15k/17.5k": ({"itm_auto": (15000, 17500)}, G), "itm_auto 20k/25k": ({"itm_auto": (20000, 25000)}, G),
    "loss_share 0.15": ({"loss_share": 0.15}, G), "loss_share 0.25": ({"loss_share": 0.25}, G), "size all": ({"size": "all"}, G),
    "size single": ({"size": "single"}, G), "g_trig 0.75": ({"g_trig": 0.75}, G), "g_trig 1.5": ({"g_trig": 1.5}, G),
    "growth cap 2": ({}, ("30k grow stop 2", 30000.0, "grow", 2)), "growth cap 4": ({}, ("30k grow stop 4", 30000.0, "grow", 4)),
}
PATHS = {"2022": gold.Y22, "2023-2026": gold.Y2326}


def main():
    if OUT.exists():
        raise SystemExit("SN421 is run once")
    CACHE.parent.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for name, (vx, wallet) in VARIANTS.items():
        for pname, years in PATHS.items():
            for st in (205.0, 400.0):
                k = f"{name} | {pname} @{int(st)}"
                if k in cache:
                    continue
                days, log, _ = gold.run(years, gold.DEPLOYED, st, wallet=wallet, **vx)
                cache[k] = gold.summary(days, log)
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
                print(k, cache[k]["net"], flush=True)
    assert cache["base | 2023-2026 @205"]["net"] in (850882, 850883), cache["base | 2023-2026 @205"]["net"]
    res = {"runs": cache, "table": {}}
    b26, b22 = cache["base | 2023-2026 @205"]["net"], cache["base | 2022 @205"]["net"]
    for name in VARIANTS:
        r = {f"{p} @{st}": cache[f"{name} | {p} @{st}"]["net"] for p in PATHS for st in (205, 400)}
        d26, d22 = r["2023-2026 @205"] - b26, r["2022 @205"] - b22
        r.update({"delta_2023_26@205": d26, "delta_2022@205": d22, "delta_pct_2023_26@205": round(100.0 * d26 / b26, 1),
                  "FRAGILE": abs(d26) > 0.2 * b26, "CONSISTENT": (d26 > 0) == (d22 > 0) if d26 != 0 and d22 != 0 else None,
                  "worst_month_2023_26@205": cache[f"{name} | 2023-2026 @205"]["worst_month"], "months_positive_2023_26@205": cache[f"{name} | 2023-2026 @205"]["months_positive"]})
        res["table"][name] = r
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for name, r in res["table"].items():
        print(f"{name:22s}", r["2022 @205"], r["2023-2026 @205"], r["2022 @400"], r["2023-2026 @400"], r["delta_pct_2023_26@205"], "FRAGILE" if r["FRAGILE"] else "", r["CONSISTENT"])


if __name__ == "__main__":
    main()
