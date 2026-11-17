"""SN341: how much capital Gold can carry (PLAN.md frozen at 95287d3f). SN312's real-quote grid (41 sealed days, NIFTY
front-weekly CE / PE every 15 minutes 09:30-15:00) extended to 6, 8, 10, 12, 15 and 20 lots at ATM and 1-3 strikes in the
money: the walked round-trip cost per lot against the model, and the share with too little visible depth. Gold V8's lot
ceiling = the smallest size where the real cost exceeds the model by > Rs 100 a lot (or visible depth is missing in > 5% of
cases) at the depths Gold uses (1 and 3 in the money)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import sn312  # noqa: E402

sn312.NS = (6, 8, 10, 12, 15, 20)

if __name__ == "__main__":
    out_path = HERE / "results-sn341.json"
    if out_path.exists():
        raise SystemExit("SN341 is run once")
    rows = sn312.grid()
    summ = sn312.summarise(rows)
    for k, v in summ.items():
        print("SN341", k, json.dumps(v), flush=True)
    ceiling = None
    for n in sn312.NS:
        bad = [k for k, v in summ.items() if k.endswith(f"x{n}") and (" itm1 " in f" {k} " or " itm3 " in f" {k} ")
               and ((v["excess_mean"] is not None and v["excess_mean"] > 100) or v["no_depth_share"] > 0.05)]
        if bad:
            ceiling = n
            break
    res = {"grid": summ, "cases": len(rows), "first_size_over_the_bar": ceiling,
           "lot_ceiling": (None if ceiling is None else sn312.NS[max(0, sn312.NS.index(ceiling) - 1)])}
    print("SN341 first size over the bar", ceiling, flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
