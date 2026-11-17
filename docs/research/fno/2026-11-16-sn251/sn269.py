"""SN269 - the daily wage from one wallet, without new money (PLAN.md). No gap-day leg passed, so the account is Gold v5
alone (Rs 30k growing, stop after 3). A wage pot inside the account:
  - Gold's profits go to the bank;
  - a wallet step (x1.5) is paid from the bank;
  - a losing day is refilled from the bank while it has money, otherwise from the owner's pocket;
  - a fixed wage is paid from the bank on every calendar session (expiry days included), otherwise from the pocket.
For wages Rs 0 / 250 / 500 / 750 / 1,000 / 1,500 a session and for quarterly starts (Gold restarted from Rs 30k on the
start day), the wages paid, the owner's pocket money (never repaid in this model), the bank at the end, the last day the
pocket was needed, and the owner's net (wages + bank - pocket). In-sample (Gold v5's own years); not a forecast."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import ow  # noqa: E402

WAGES = (0, 250, 500, 750, 1000, 1500)
STARTS = [f"{y}-{m:02d}-01" for y in (2023, 2024, 2025, 2026) for m in (1, 4, 7, 10) if f"{y}-{m:02d}" <= "2026-07"]


def pot(days, cal, start, wage):
    gold = {d: (w, n) for d, w, n, _t, _l in days}
    bank = pocket = 0.0
    paid = 0.0
    last_pocket_day = None
    w_prev = 30000.0
    for d in cal:
        if d < start:
            continue
        w, n = gold.get(d, (w_prev, 0.0))
        if w > w_prev:                       # a wallet step happened before this session: pay it from the bank
            step = w - w_prev
            take = min(bank, step)
            bank -= take
            if step > take:
                pocket += step - take
                last_pocket_day = d
        w_prev = w
        if n >= 0:
            bank += n
        else:
            take = min(bank, -n)
            bank -= take
            if -n > take:
                pocket += -n - take
                last_pocket_day = d
        take = min(bank, wage)
        bank -= take
        if wage > take:
            pocket += wage - take
            last_pocket_day = d
        paid += wage
    return {"wages_paid": round(paid), "pocket_total": round(pocket), "bank_end": round(bank), "last_pocket_day": last_pocket_day,
            "owner_net": round(paid + bank - pocket)}


if __name__ == "__main__":
    out_path = HERE / "results-sn269.json"
    if out_path.exists():
        raise SystemExit("SN269 is run once")
    smp = ow._smp()
    cal = [d for d in smp.cal if "2023-01-01" <= d < gl.TEST_HI]
    res = {"starts": {}, "sessions": len(cal)}
    for s in STARTS:
        v = dict(ow.C.V5)
        if s > "2023-01-01":
            v["from_day"] = s
        _row, days, _l = ow.run_wallet(v, ow.GOLD_30K, None)
        sess = [d for d in cal if d >= s]
        r = {"sessions": len(sess), "gold_net": round(sum(n for d, _w, n, _t, _x in days if d >= s))}
        for wg in WAGES:
            r[f"wage {wg}"] = pot(days, cal, s, wg)
        res["starts"][s] = r
        print("SN269", s, json.dumps(r), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
