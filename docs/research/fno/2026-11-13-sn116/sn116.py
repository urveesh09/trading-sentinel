"""SN116 - where should the next rupee go? (PLAN.md) Matched total capital: Gold alone at the smaller wallet, Gold +
SN95-L in the shared wallet, Gold + a separate Rs 15k straddle sleeve, Gold alone at the full capital, and the same
stepping after 50% profit; fixed / growing (stop 3) / growing (stop 5); totals Rs 45k and Rs 50k."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pc  # noqa: E402

C, pa, pb, sn110 = pc.C, pc.pa, pc.pb, pc.sn110
MODES = (("fixed", 0), ("grow stop 3", 3), ("grow stop 5", 5))


if __name__ == "__main__":
    out_path = HERE / "results-sn116.json"
    if out_path.exists():
        raise SystemExit("SN116 is scored once")
    adm = pa.admission()
    sleeve = {S.day: pb.net(pa.path(S, pb.I10)) for S in pb.signal_days(adm, True)}
    sleeve_days = sorted((d, n) for d, n in sleeve.items() if n != 0)
    sn95l = lambda d: pa.sn95l(adm, d)  # noqa: E731
    res = {"sleeve_alone": {"net": round(sum(sleeve.values())), "by_year": pc.by_year(sleeve_days), **pc.series_stats(sleeve_days),
                            "refilled": round(sum(-n for n in sleeve.values() if n < 0))}}
    print("Rs 15k straddle sleeve alone", res["sleeve_alone"], flush=True)
    for total, small in ((45000.0, 30000.0), (50000.0, 35000.0)):
        for mname, cap in MODES:
            ws, wt = (f"{int(small / 1000)}k {mname}", small, "grow", cap), (f"{int(total / 1000)}k {mname}", total, "grow", cap)
            arms = {}
            p, dl = pc.gold_days(C.V5, ws)
            arms[f"Gold {int(small / 1000)}k alone"] = (p, dl, small)
            p2, dl2 = pc.gold_days(sn110.arm(sn95l), ws)
            arms[f"Gold {int(small / 1000)}k + straddle in Gold's wallet"] = (p2, dl2, small)
            arms[f"Gold {int(small / 1000)}k + separate 15k straddle sleeve"] = (
                {**p, "net": p["net"] + res["sleeve_alone"]["net"], "refilled": p["refilled"] + res["sleeve_alone"]["refilled"]},
                pc.merge(dl, sleeve_days), total)
            p4, dl4 = pc.gold_days(C.V5, wt)
            arms[f"Gold {int(total / 1000)}k alone"] = (p4, dl4, total)
            p5, dl5 = pc.gold_days({**C.V5, "g_trig": 0.5}, wt)
            arms[f"Gold {int(total / 1000)}k, step after 50%"] = (p5, dl5, total)
            block = {}
            for name, (p_, dl_, cap_) in arms.items():
                block[name] = {"capital": cap_, "net": round(p_["net"]), "by_year": pc.by_year(dl_), "refilled": round(p_["refilled"]),
                               **pc.series_stats(dl_), "net_per_1000_capital": round(1000 * p_["net"] / cap_)}
            res[f"total {int(total / 1000)}k | {mname}"] = block
            print(f"=== total Rs {int(total / 1000)}k | {mname}")
            for name, b in block.items():
                print(f"   {name:44s} net {b['net']:>9} by year {b['by_year']} refilled {b['refilled']:>8} worst day {b['worst_day']:>8} "
                      f"max drawdown {b['max_drawdown']:>8} per Rs 1,000 {b['net_per_1000_capital']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
