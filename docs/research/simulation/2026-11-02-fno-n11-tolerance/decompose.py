"""Against N11, trade by trade: what the extra lots earned themselves, and what the knock-on effects did. From saved replays only. A development view."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-02-fno-n11"))
import screen_view as V  # noqa: E402

V.LOCAL = HERE / "_local"
YEARS = V.YEARS


def main(phase: str, base: str, names: list) -> None:
    for name in names:
        print("=====", name)
        total = {"raised_own": 0.0, "kids": 0.0, "lost": 0.0, "added": 0.0, "lowered": 0.0}
        for y in YEARS:
            a = {(t["entry_time"], t["tradingsymbol"]): t for t in V.load(V.LOCAL, phase, y, base)["trades"]}
            b = {(t["entry_time"], t["tradingsymbol"]): t for t in V.load(V.LOCAL, phase, y, name)["trades"]}
            raised, lowered, kids, same = [], [], 0.0, 0.0
            for k in a.keys() & b.keys():
                ta, tb = a[k], b[k]
                diff = tb["net_pnl"] - ta["net_pnl"]
                if tb["entry_qty"] > ta["entry_qty"]:
                    raised.append((k[0][:16], tb["member"], tb["direction"][0], tb["entry_premium"], tb["exit_reason"][:12], round(ta["net_pnl"]), round(tb["net_pnl"]), len(tb.get("n10_children") or [])))
                elif tb["entry_qty"] < ta["entry_qty"]:
                    lowered.append((k[0][:16], tb["member"], tb["direction"][0], tb["entry_premium"], tb["exit_reason"][:12], round(ta["net_pnl"]), round(tb["net_pnl"])))
                else:
                    kids += diff
            lost = sum(t["net_pnl"] for k, t in a.items() if k not in b)
            added = sum(t["net_pnl"] for k, t in b.items() if k not in a)
            own = sum(r[6] - r[5] for r in raised)
            down = sum(r[6] - r[5] for r in lowered)
            print(f"{y}: raised {len(raised)} own {own:,.0f} | lowered {len(lowered)} {down:,.0f} | same size, earned-lot change {kids:,.0f} | trades lost {lost:,.0f} added {added:,.0f}")
            for r in raised:
                print("    +", r)
            for r in lowered:
                print("    -", r)
            total["raised_own"] += own
            total["kids"] += kids
            total["lost"] += -lost
            total["added"] += added
            total["lowered"] += down
        print("TOTAL", {k: round(v) for k, v in total.items()}, "=", round(sum(total.values())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
