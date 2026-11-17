"""SN468 application (PLAN.md section 2, frozen at 83e1b444; details fixed here before any number). Development only.

SN419's opener days (results-sn419.json @205 opener_log: day, exit index j, debit) against Gold's own trades on those days
(gold.run Y2326 DEPLOYED Rs 205): a Gold intent at fill index i <= the opener's exit index j arrives while the companion
holds its lot. Through wallet_sm's rules: free cash = Gold's day wallet - the opener's debit; Gold's initial order = lots0 x
ask0 x 65 (+ wallet_sm.fee); affordable -> FILLED, otherwise DELAYED to the opener's exit (if within 60 s of the intent) or
MISSED. Counted against SN419's own assumption (sell at that minute's bar, Gold enters at once). Fixtures: test_wallet_sm.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402
import wallet_sm as W  # noqa: E402

OUT = HERE / "results-sn468.json"


def main():
    if OUT.exists():
        raise SystemExit("SN468 is scored once")
    s = json.loads((HERE.parent / "2026-11-17-sn411" / "results-sn419.json").read_text(encoding="utf-8"))["@205"]
    op = {r["day"]: r for r in s["opener_log"]}
    days, log, _ = gold.run(gold.Y2326, gold.DEPLOYED, 205.0)
    assert gold.summary(days, log)["net"] in (850882, 850883)
    rows, counts = [], {"FILLED": 0, "DELAYED": 0, "MISSED": 0, "no_overlap": 0}
    for x in log:
        if x["day"] not in op:
            continue
        o = op[x["day"]]
        cost = x["lots0"] * x["ask0"] * 65 + W.fee(x["ask0"], x["lots0"] * 65)
        if x["i"] > o["j"]:
            counts["no_overlap"] += 1
            rows.append({"day": x["day"], "gold_i": x["i"], "opener_exit_j": o["j"], "state": "no_overlap"})
            continue
        free = float(x["wallet"]) - float(o["debit"])
        st = "FILLED" if free >= cost else ("DELAYED" if (o["j"] - x["i"]) * 60 <= W.GOLD_WAIT else "MISSED")
        counts[st] += 1
        rows.append({"day": x["day"], "gold_i": x["i"], "opener_exit_j": o["j"], "gold_cost": round(cost), "free": round(free), "state": st})
    res = {"opener_days": len(op), "gold_trades_on_opener_days": len(rows), "counts": counts,
           "sn419_forced_by_gold": s.get("forced_by_gold"), "rows": rows}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
