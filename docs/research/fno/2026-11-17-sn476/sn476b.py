"""SN476b (supplementary, disclosed in PLAN.md A1 before it ran): C and D on the fixed ONE_15K ledger (Rs 15k, one lot), so the
signal-set and stop-rule effects are seen without the growth wallet's compounding path (SN476 D at Rs 400 moved +1.77 lakh while
the same rule moved -4,941 at Rs 205: a path effect through earlier wallet steps). Same streams and switches as sn476.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn476 as S  # noqa: E402

g, goldx = S.g, S.goldx
OUT = HERE / "results-sn476b.json"


def main():
    if OUT.exists():
        raise SystemExit("SN476b is scored once")
    goldx.install()
    g._orig_stream = S.dispatch
    vt = {"2326": S.vol_table(S.DAILY["2326"]), "22": S.vol_table(S.DAILY["22"])}
    S.RUNTIME["2326"], _ = S.runtime_stream(("2023", "2024", "2025", "2026"), ("2023", "2024", "2025", "2026"), vt["2326"])
    S.RUNTIME["2022"], _ = S.runtime_stream(("2021", "2022"), ("2022",), vt["22"])
    res = {}
    for pname, years in (("2022", g.Y22), ("2023-2026", g.Y2326)):
        for st in S.STRESSES:
            base, _d, lb = S.gold_run(years, g.DEPLOYED, st, wallet=goldx.ONE_15K)
            rt, _d, lr = S.gold_run(years, ("RUNTIME",), st, wallet=goldx.ONE_15K)
            cl, _d, lc = S.gold_run(years, g.DEPLOYED, st, wallet=goldx.ONE_15K, stop_rule="close")
            kb = {(t["day"], t["i"]) for t in lb}
            res[f"{pname} @{int(st)}"] = {"DEPLOYED": base, "RUNTIME": rt, "CLOSE_STOP": cl, "runtime_minus_deployed": rt["net"] - base["net"],
                                          "close_minus_bar_low": cl["net"] - base["net"],
                                          "runtime_only_trades": [[t["day"], t["i"], t.get("expert"), round(t["net"])] for t in lr if (t["day"], t["i"]) not in kb],
                                          "stops": [sum(t["reason"] == "stop" for t in lb), sum(t["reason"] == "stop" for t in lc)]}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: {"dep": v["DEPLOYED"]["net"], "rt-dep": v["runtime_minus_deployed"], "close-low": v["close_minus_bar_low"],
                          "worst": [v["DEPLOYED"]["worst_day"], v["RUNTIME"]["worst_day"], v["CLOSE_STOP"]["worst_day"]], "stops": v["stops"],
                          "rt_only": v["runtime_only_trades"]} for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
