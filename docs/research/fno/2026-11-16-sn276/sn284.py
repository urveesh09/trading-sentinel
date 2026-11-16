"""SN284 (information only, PLAN.md amendment): the pre-holiday ITM call inside Gold v5's one wallet (ow.py), Jan 2023 -
Oct 2026, Rs 30k growing. Gold alone vs Gold + call: net, months positive, worst day / month, the call's trades."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SN251 = HERE.parent / "2026-11-16-sn251"
sys.path.insert(0, str(SN251))
import gl  # noqa: E402
import ow  # noqa: E402
import sn259  # noqa: E402

I920 = gl.I["09:20"]


class PreHolidayCall:
    def intraday(self, smp, d, i_from, budget, room, stop_at):
        if d not in smp.s or not sn259.pre_holiday(smp, d) or i_from > I920 or (stop_at is not None and stop_at <= I920):
            return None
        s = smp.s[d]
        K = gl.atm(smp, s, I920) - smp.mk["step"]
        p = gl.Pos(smp, s, [(K, "CE", 1)], I920)
        if not p.ok or p.premium > budget:
            return None
        end = gl.FLAT if stop_at is None else min(gl.FLAT, stop_at)
        net, j, why = gl.walk(p, s, I920, end, room=room)
        if net is None:
            return None
        if stop_at is not None and j >= stop_at and why == "time":
            why = "forced"
        return net, j, why


def account(days):
    x = {d: n for d, _w, n, _t, _l in days}
    m = {}
    for d, n in x.items():
        m[d[:7]] = m.get(d[:7], 0.0) + n
    mv = np.array(list(m.values()))
    return {"net": round(sum(x.values())), "months_positive": int((mv > 0).sum()), "months": len(mv),
            "worst_month": round(float(mv.min())), "worst_day": round(min(x.values())), "green_days": sum(v > 0 for v in x.values())}


if __name__ == "__main__":
    out = HERE / "results-sn284.json"
    if out.exists():
        raise SystemExit("SN284 is run once")
    _r0, d0, _l0 = ow.run_wallet(ow.C.V5, ow.GOLD_30K, None)
    _r1, d1, l1 = ow.run_wallet(ow.C.V5, ow.GOLD_30K, PreHolidayCall())
    res = {"gold_alone": account(d0), "gold_plus_call": account(d1),
           "call_trades": [{"day": t["day"], "net": round(t["net"]), "why": t["why"], "wallet": t["wallet"]} for t in l1],
           "call_net": round(sum(t["net"] for t in l1)), "note": "information only: a post-hoc signal (SN272 / SN281), not a pass"}
    print("SN284", json.dumps({k: v for k, v in res.items() if k != "call_trades"}), "trades", len(l1), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
