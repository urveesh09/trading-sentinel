"""SN327: Gold v5's real-money risk against the owner's limit (PLAN.md, frozen). Gold v5 at Rs 30,000 growing (stop 3), Jan
2023 - Oct 28 2026, the parity player. From the day log: refills per calendar month and per 20 sessions against the wallet
then; the longest run of losing sessions (flat days skipped and counted); worst month and deepest drawdown against the
wallet. The owner's limit: a refill never more than the wallet's full amount. If any calendar month's refills exceed the
wallet, the frozen cap (no new Gold trade for the rest of a calendar month once that month's refills reach the wallet) is
replayed at Rs 205 and Rs 400 and reported with what it costs."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import gw  # noqa: E402
import sn310_311 as G  # noqa: E402

ow = gw.ow
CAP = {"on": False, "month": None, "refilled": 0.0}
_PLAY = ow.play_day


def capped_play(S, sigs, v, wallet, full_lots, ctx, vol_day):
    m = S.day[:7]
    if CAP["month"] != m:
        CAP.update(month=m, refilled=0.0)
    if CAP["on"] and CAP["refilled"] >= wallet:
        ow.DAYLOG.append((S.day, wallet, 0.0, 0, 0.0))
        return 0.0
    net = _PLAY(S, sigs, v, wallet, full_lots, ctx, vol_day)
    if net < 0:
        CAP["refilled"] += -net
    return net


def risk(days):
    months = collections.defaultdict(lambda: {"refill": 0.0, "net": 0.0, "wallet": None})
    for d, w, n, _t, _l in days:
        m = months[d[:7]]
        m["wallet"] = m["wallet"] or w
        m["net"] += n
        m["refill"] += max(0.0, -n)
    ratios = {k: round(v["refill"] / v["wallet"], 3) for k, v in months.items()}
    roll = []
    for k in range(len(days)):
        seg = days[max(0, k - 19): k + 1]
        roll.append(sum(max(0.0, -n) for _d, _w, n, _t, _l in seg) / days[k][1])
    run = best = 0
    for _d, _w, n, _t, _l in days:
        if n < 0:
            run += 1
            best = max(best, run)
        elif n > 0:
            run = 0
    cum = peak = 0.0
    dd_ratio = 0.0
    for _d, w, n, _t, _l in days:
        cum += n
        peak = max(peak, cum)
        dd_ratio = max(dd_ratio, (peak - cum) / w)
    worst = min(months, key=lambda k: months[k]["net"])
    return {"months": len(months), "max_month_refill_over_wallet": max(ratios.values()), "month_of_max": max(ratios, key=ratios.get),
            "months_refill_over_half_wallet": sum(r > 0.5 for r in ratios.values()), "months_refill_over_wallet": sum(r > 1.0 for r in ratios.values()),
            "max_20_session_refill_over_wallet": round(max(roll), 3), "longest_losing_run_sessions": best,
            "worst_month": worst, "worst_month_net": round(months[worst]["net"]), "worst_month_over_wallet": round(months[worst]["net"] / months[worst]["wallet"], 3),
            "deepest_drawdown_over_wallet": round(dd_ratio, 3)}


if __name__ == "__main__":
    out_path = HERE / "results-sn327.json"
    if out_path.exists():
        raise SystemExit("SN327 is run once")
    gw.install()
    res = {}
    for stress in (205.0, 400.0):
        row, days, log = G.run(None, stress)
        if stress == 205.0:
            assert row["net"] == 850882, row["net"]
        res[f"gold_v5 @{int(stress)}"] = {"net": row["net"], **risk(days)}
        print("SN327", int(stress), json.dumps(res[f"gold_v5 @{int(stress)}"]), flush=True)
    crossed = res["gold_v5 @205"]["months_refill_over_wallet"] > 0 or res["gold_v5 @400"]["months_refill_over_wallet"] > 0
    res["limit_crossed"] = crossed
    if crossed:
        ow.play_day = capped_play
        CAP["on"] = True
        for stress in (205.0, 400.0):
            CAP.update(month=None, refilled=0.0)
            row, days, log = G.run(None, stress)
            res[f"monthly_cap @{int(stress)}"] = {"net": row["net"], **risk(days), "metrics": G.metrics(row, days, log)}
            print("SN327 cap", int(stress), json.dumps(res[f"monthly_cap @{int(stress)}"]), flush=True)
        ow.play_day = _PLAY
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
